"""Planos de treino de X semanas (ginásio).

Um **plano** junta treinos específicos num calendário de várias semanas — StrongLifts 5×5,
Starting Strength, 5/3/1… Ao **começar** um plano, a Perennia cria o treino de cada sessão
(com as séries, as repetições e as cargas dessa semana), põe-nos todos no **calendário** e
daí para a frente é só abrir a sessão do dia e fazê-la.

O formato Perennia de um plano (o mesmo para os que vêm com a aplicação e para os que
importas; ver `packaging/planos/FORMATO-DO-PLANO.md` e o ficheiro modelo):

```json
{
  "format": "perennia-plan", "version": 1,
  "name": "StrongLifts 5×5", "category": "strength", "level": "beginner",
  "weeks": 12, "days_per_week": 3, "weekdays": [1, 3, 5],
  "description": "…", "equipment": ["barbell", "plates", "rack", "bench"],
  "exercises": {"squat": {"name": "Agachamento com barra", "group": "legs"}},
  "sessions": {"A": {"name": "Treino A", "blocks": [
      {"exercise": "squat", "sets": 5, "reps": 5, "rest": 180, "add_kg": 2.5,
       "start_pct": 50}]}},
  "rotation": ["A", "B"]
}
```

* **`rotation`** — as sessões alternam por esta ordem ao longo de todos os dias do plano;
  ou **`schedule`** — a lista das sessões de cada semana (repete-se se for mais curta).
* Um valor pode ser **um por semana**: `"pct1rm": [70, 75, 80]` (o último repete-se).
* **`sets`** é um número (séries iguais) ou a lista das séries: `[{"reps": 5, "pct1rm": 65},
  {"reps": "5+", "pct1rm": 85}]`.
* **Progressão linear:** `"add_kg": 2.5` soma essa carga de cada vez que o exercício volta
  (`"per": "session"`) ou por semana (`"per": "week"`). A carga inicial pede-se ao começar
  (sugerida por `start_pct` da tua 1RM estimada). Numa série, `"of_top": 0.75` é a fração da
  carga principal (rampas e séries de recuo).
* **`pct1rm`** — a carga sai da tua 1RM estimada no momento da sessão.

Nada disto usa rede. Um ficheiro importado é só dados (JSON): é validado antes de entrar.
"""
from __future__ import annotations

import copy
import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import calendar_view as cal
from . import gym, inventory, options
from . import strength_builder as sb
from .db import Database, now_iso
from .i18n import tr

FORMAT = "perennia-plan"
VERSION = 1
EXT = ".perennia-plan.json"
HIDDEN_PLAN = 2                   # strength_workouts.hidden: 2 = treino de um plano em curso
REBASED_AT = "__from"             # nas cargas de um plano em curso: a sessão onde recomeçam
TITLE_SEP = " · "

# limites do formato (um ficheiro que os passe é recusado)
MAX_WEEKS = 104
MAX_SESSIONS = 60
MAX_BLOCKS = 30
MAX_EXERCISES_PER_BLOCK = 12
MAX_SETS = 30
MAX_EXERCISES = 200
MAX_TEXT = 4000
MAX_NAME = 80

CATEGORIES = ("strength", "powerlifting", "bodybuilding", "strongman", "grip", "longevity",
              "general", "conditioning", "athletic", "glutes", "other")
LEVELS = ("beginner", "intermediate", "advanced")
GROUPS = ("legs", "hips", "chest", "back", "shoulders", "arms", "core", "full", "mobility")
BLOCK_KINDS = ("single", "superset", "circuit", "warmup", "cooldown")
SET_FIELDS = ("reps", "load", "pct1rm", "rpe", "rir", "time", "distance", "rest")
WEEKDAY_PRESETS = {1: ((3,), (1,), (6,)), 2: ((2, 5), (1, 4), (3, 6)),
                   3: ((1, 3, 5), (2, 4, 6), (1, 3, 6)), 4: ((1, 2, 4, 5), (1, 3, 5, 6),
                                                             (2, 3, 5, 6)),
                   5: ((1, 2, 3, 5, 6), (1, 2, 4, 5, 6)), 6: ((1, 2, 3, 4, 5, 6),),
                   7: ((1, 2, 3, 4, 5, 6, 7),)}


class PlanError(ValueError):
    """O plano não obedece ao formato (a mensagem diz onde)."""


def category_name(c: str) -> str:
    return {"strength": tr("Força", "Strength"), "powerlifting": "Powerlifting",
            "bodybuilding": tr("Hipertrofia", "Bodybuilding"), "strongman": "Strongman",
            "grip": tr("Força de mãos", "Grip"), "longevity": tr("Longevidade", "Longevity"),
            "general": tr("Forma geral", "General fitness"),
            "conditioning": tr("Condicionamento", "Conditioning"),
            "athletic": tr("Desempenho atlético", "Athletic performance"),
            "glutes": tr("Glúteos", "Glutes"), "other": tr("Outros", "Other")}.get(c, c)


def level_name(lv: str) -> str:
    return {"beginner": tr("Iniciante", "Beginner"), "intermediate": tr("Intermédio",
                                                                         "Intermediate"),
            "advanced": tr("Avançado", "Advanced")}.get(lv, lv)


def weekday_name(n: int, short: bool = True) -> str:
    names = ((tr("Seg", "Mon"), tr("Ter", "Tue"), tr("Qua", "Wed"), tr("Qui", "Thu"),
              tr("Sex", "Fri"), tr("Sáb", "Sat"), tr("Dom", "Sun")) if short else
             (tr("Segunda", "Monday"), tr("Terça", "Tuesday"), tr("Quarta", "Wednesday"),
              tr("Quinta", "Thursday"), tr("Sexta", "Friday"), tr("Sábado", "Saturday"),
              tr("Domingo", "Sunday")))
    return names[(int(n) - 1) % 7]


def weekdays_text(days: list[int] | tuple[int, ...]) -> str:
    return ", ".join(weekday_name(d) for d in days)


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))
                  .lower()).strip()


def slug(text: str) -> str:
    return _fold(text).replace(" ", "_") or "plano"


# ====================================================================== validar


def _text(v: Any, limit: int, where: str, required: bool = False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise PlanError(tr("{w}: tem de ser texto", "{w}: must be text", w=where))
    v = v.strip()
    if required and not v:
        raise PlanError(tr("{w}: em falta", "{w}: missing", w=where))
    if len(v) > limit:
        raise PlanError(tr("{w}: texto comprido demais (máximo {n})",
                           "{w}: text too long (max {n})", w=where, n=limit))
    return v


def _num(v: Any, where: str, lo: float, hi: float, integer: bool = False):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise PlanError(tr("{w}: tem de ser um número", "{w}: must be a number", w=where))
    if not lo <= v <= hi:
        raise PlanError(tr("{w}: fora dos limites ({a:g} a {b:g})",
                           "{w}: out of range ({a:g} to {b:g})", w=where, a=lo, b=hi))
    return int(v) if integer else float(v)


FIELD_RANGE = {"reps": (0, 1000), "load": (0, 1000), "pct1rm": (1, 150), "rpe": (1, 10),
               "rir": (0, 10), "time": (1, 6 * 3600), "distance": (1, 100000),
               "rest": (0, 3600), "of_top": (0.05, 1.5)}


def _reps(v: Any, where: str) -> Any:
    """Repetições: 5, «8-12», «5+» (pelo menos 5, o máximo que der) ou «max»."""
    if isinstance(v, str):
        s = v.strip().lower().replace("–", "-")
        if s in ("max", "amrap", "máx"):
            return "max"
        m = re.fullmatch(r"(\d{1,3})\+", s)
        if m:
            return f"{int(m.group(1))}+"
        m = re.fullmatch(r"(\d{1,3})\s*-\s*(\d{1,3})", s)
        if m and int(m.group(1)) <= int(m.group(2)):
            return f"{int(m.group(1))}-{int(m.group(2))}"
        if s.isdigit():
            return int(s)
        raise PlanError(tr("{w}: repetições «{v}» não se percebem (5, «8-12», «5+» ou «max»)",
                           "{w}: reps '{v}' are unclear (5, '8-12', '5+' or 'max')", w=where,
                           v=v))
    return _num(v, where, 0, 1000, integer=True)


def _value(field: str, v: Any, where: str) -> Any:
    """Um valor, ou um por semana (lista)."""
    def one(x):
        if field == "reps":
            return _reps(x, where)
        lo, hi = FIELD_RANGE[field]
        return _num(x, where, lo, hi)
    if isinstance(v, list):
        if not v or len(v) > MAX_WEEKS:
            raise PlanError(tr("{w}: a lista por semana está vazia ou é grande demais",
                               "{w}: the per-week list is empty or too large", w=where))
        return [one(x) for x in v]
    return one(v)


def _exercise_entry(e: Any, where: str, known: set[str]) -> dict:
    if not isinstance(e, dict):
        raise PlanError(tr("{w}: tem de ser um objeto", "{w}: must be an object", w=where))
    key = e.get("exercise")
    if not isinstance(key, str) or key not in known:
        raise PlanError(tr("{w}: o exercício «{k}» não está na lista «exercises» do plano",
                           "{w}: exercise '{k}' is not in the plan's 'exercises' list", w=where,
                           k=key))
    out: dict = {"exercise": key}
    sets = e.get("sets", 1)
    if isinstance(sets, list) and sets and all(isinstance(s, dict) for s in sets):
        if len(sets) > MAX_SETS:
            raise PlanError(tr("{w}: séries a mais (máximo {n})", "{w}: too many sets (max {n})",
                               w=where, n=MAX_SETS))
        out["sets"] = []
        for i, s in enumerate(sets):
            row = {}
            for f in SET_FIELDS + ("of_top",):
                if s.get(f) is not None:
                    row[f] = _value(f, s[f], f"{where}, série {i + 1}, {f}")
            unknown = set(s) - set(SET_FIELDS) - {"of_top"}
            if unknown:
                raise PlanError(tr("{w}, série {i}: campo desconhecido «{f}»",
                                   "{w}, set {i}: unknown field '{f}'", w=where, i=i + 1,
                                   f=sorted(unknown)[0]))
            out["sets"].append(row)
    else:
        if isinstance(sets, list):
            out["sets"] = [_num(x, f"{where}, sets", 1, MAX_SETS, integer=True) for x in sets]
            if not out["sets"] or len(out["sets"]) > MAX_WEEKS:
                raise PlanError(tr("{w}: lista de séries inválida", "{w}: bad sets list",
                                   w=where))
        else:
            out["sets"] = _num(sets, f"{where}, sets", 1, MAX_SETS, integer=True)
        for f in SET_FIELDS:
            if e.get(f) is not None:
                out[f] = _value(f, e[f], f"{where}, {f}")
    if e.get("add_kg") is not None:
        out["add_kg"] = _num(e["add_kg"], f"{where}, add_kg", 0, 50)
        per = e.get("per", "session")
        if per not in ("session", "week"):
            raise PlanError(tr("{w}: «per» tem de ser «session» ou «week»",
                               "{w}: 'per' must be 'session' or 'week'", w=where))
        out["per"] = per
        if e.get("start_pct") is not None:
            out["start_pct"] = _num(e["start_pct"], f"{where}, start_pct", 1, 120)
        track = e.get("track", key)
        if not isinstance(track, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", track):
            raise PlanError(tr("{w}: «track» inválido", "{w}: bad 'track'", w=where))
        out["track"] = track
    out["notes"] = _text(e.get("notes"), 300, f"{where}, notes")
    allowed = set(SET_FIELDS) | {"exercise", "sets", "add_kg", "per", "start_pct", "track",
                                 "notes"}
    unknown = set(e) - allowed
    if unknown:
        raise PlanError(tr("{w}: campo desconhecido «{f}»", "{w}: unknown field '{f}'", w=where,
                           f=sorted(unknown)[0]))
    return out


def validate(data: Any) -> dict:
    """Confere e normaliza um plano. Devolve uma cópia limpa; lança `PlanError` com o sítio
    do problema."""
    if not isinstance(data, dict):
        raise PlanError(tr("o ficheiro não é um plano Perennia (esperava um objeto JSON)",
                           "the file is not a Perennia plan (expected a JSON object)"))
    if data.get("format") != FORMAT:
        raise PlanError(tr("falta «format»: «{f}»", "missing 'format': '{f}'", f=FORMAT))
    if data.get("version", 1) != VERSION:
        raise PlanError(tr("versão do formato desconhecida ({v}); esta Perennia lê a {n}",
                           "unknown format version ({v}); this Perennia reads {n}",
                           v=data.get("version"), n=VERSION))
    out: dict = {"format": FORMAT, "version": VERSION}
    out["name"] = _text(data.get("name"), MAX_NAME, "name", required=True)
    out["description"] = _text(data.get("description"), MAX_TEXT, "description")
    out["author"] = _text(data.get("author"), 120, "author")
    out["source"] = _text(data.get("source"), 300, "source")
    cat = data.get("category", "other")
    out["category"] = cat if cat in CATEGORIES else "other"
    lv = data.get("level", "intermediate")
    out["level"] = lv if lv in LEVELS else "intermediate"
    out["weeks"] = _num(data.get("weeks"), "weeks", 1, MAX_WEEKS, integer=True)
    # ---- exercícios
    exs = data.get("exercises")
    if not isinstance(exs, dict) or not exs:
        raise PlanError(tr("«exercises»: em falta (um objeto chave → exercício)",
                           "'exercises': missing (an object key → exercise)"))
    if len(exs) > MAX_EXERCISES:
        raise PlanError(tr("«exercises»: exercícios a mais", "'exercises': too many"))
    out["exercises"] = {}
    for key, e in exs.items():
        w = f"exercises.{key}"
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", key):
            raise PlanError(tr("{w}: a chave só pode ter letras, números, _ e -",
                               "{w}: the key may only have letters, digits, _ and -", w=w))
        if not isinstance(e, dict):
            raise PlanError(tr("{w}: tem de ser um objeto", "{w}: must be an object", w=w))
        ne = {"name": _text(e.get("name"), MAX_NAME, f"{w}.name", required=True)}
        ne["group"] = e.get("group") if e.get("group") in GROUPS else "full"
        ne["measure"] = "time" if e.get("measure") == "time" else "reps"
        ne["bodyweight"] = _num(e.get("bodyweight", 0.0), f"{w}.bodyweight", 0, 1)
        mod = e.get("modality", "strength")
        ne["modality"] = mod if isinstance(mod, str) and mod in gym.MODALITIES else "strength"
        kit = e.get("equipment") or []
        if not isinstance(kit, list) or len(kit) > 12:
            raise PlanError(tr("{w}.equipment: tem de ser uma lista", "{w}.equipment: must be a "
                               "list", w=w))
        ne["equipment"] = [k for k in kit if isinstance(k, str) and k in inventory.KINDS]
        al = e.get("aliases") or []
        if not isinstance(al, list) or len(al) > 12:
            raise PlanError(tr("{w}.aliases: tem de ser uma lista", "{w}.aliases: must be a "
                               "list", w=w))
        ne["aliases"] = [_text(x, MAX_NAME, f"{w}.aliases") for x in al]
        ne["description"] = _text(e.get("description"), 600, f"{w}.description")
        out["exercises"][key] = ne
    known = set(out["exercises"])
    # ---- sessões
    sess = data.get("sessions")
    if not isinstance(sess, dict) or not sess:
        raise PlanError(tr("«sessions»: em falta (um objeto chave → sessão)",
                           "'sessions': missing (an object key → session)"))
    if len(sess) > MAX_SESSIONS:
        raise PlanError(tr("«sessions»: sessões a mais", "'sessions': too many"))
    out["sessions"] = {}
    for key, s in sess.items():
        w = f"sessions.{key}"
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", key):
            raise PlanError(tr("{w}: chave inválida", "{w}: bad key", w=w))
        if not isinstance(s, dict):
            raise PlanError(tr("{w}: tem de ser um objeto", "{w}: must be an object", w=w))
        blocks = s.get("blocks")
        if not isinstance(blocks, list) or not blocks or len(blocks) > MAX_BLOCKS:
            raise PlanError(tr("{w}.blocks: tem de ser uma lista com 1 a {n} blocos",
                               "{w}.blocks: must be a list with 1 to {n} blocks", w=w,
                               n=MAX_BLOCKS))
        ns = {"name": _text(s.get("name"), MAX_NAME, f"{w}.name") or key,
              "notes": _text(s.get("notes"), 1000, f"{w}.notes"), "blocks": []}
        for bi, b in enumerate(blocks):
            bw = f"{w}.blocks[{bi + 1}]"
            if not isinstance(b, dict):
                raise PlanError(tr("{w}: tem de ser um objeto", "{w}: must be an object", w=bw))
            if "exercises" in b or "kind" in b:
                kind = b.get("kind", "superset")
                if kind not in BLOCK_KINDS:
                    raise PlanError(tr("{w}: «kind» desconhecido («{k}»)",
                                       "{w}: unknown 'kind' ('{k}')", w=bw, k=kind))
                lst = b.get("exercises")
                if not isinstance(lst, list) or not lst or len(lst) > MAX_EXERCISES_PER_BLOCK:
                    raise PlanError(tr("{w}.exercises: tem de ser uma lista (1 a {n})",
                                       "{w}.exercises: must be a list (1 to {n})", w=bw,
                                       n=MAX_EXERCISES_PER_BLOCK))
                nb = {"kind": kind,
                      "rounds": _num(b.get("rounds", 1), f"{bw}.rounds", 1, 50, integer=True),
                      "rest": _num(b.get("rest", 0), f"{bw}.rest", 0, 3600, integer=True),
                      "notes": _text(b.get("notes"), 300, f"{bw}.notes"),
                      "exercises": [_exercise_entry(e, f"{bw}.exercises[{i + 1}]", known)
                                    for i, e in enumerate(lst)]}
            else:
                nb = {"kind": "single", "rounds": 1, "rest": 0, "notes": "",
                      "exercises": [_exercise_entry(b, bw, known)]}
            ns["blocks"].append(nb)
        out["sessions"][key] = ns
    # ---- semanas
    rot, sched = data.get("rotation"), data.get("schedule")
    if sched is not None:
        if not isinstance(sched, list) or not sched or len(sched) > MAX_WEEKS:
            raise PlanError(tr("«schedule»: tem de ser a lista das semanas",
                               "'schedule': must be the list of weeks"))
        out["schedule"] = []
        for wi, week in enumerate(sched):
            if not isinstance(week, list) or not week or len(week) > 7:
                raise PlanError(tr("schedule[{i}]: cada semana é uma lista de 1 a 7 sessões",
                                   "schedule[{i}]: each week is a list of 1 to 7 sessions",
                                   i=wi + 1))
            for k in week:
                if k not in out["sessions"]:
                    raise PlanError(tr("schedule[{i}]: a sessão «{k}» não existe",
                                       "schedule[{i}]: session '{k}' does not exist", i=wi + 1,
                                       k=k))
            out["schedule"].append(list(week))
        dpw = max(len(w) for w in out["schedule"])
    elif rot is not None:
        if not isinstance(rot, list) or not rot or len(rot) > MAX_SESSIONS:
            raise PlanError(tr("«rotation»: tem de ser uma lista de sessões",
                               "'rotation': must be a list of sessions"))
        for k in rot:
            if k not in out["sessions"]:
                raise PlanError(tr("rotation: a sessão «{k}» não existe",
                                   "rotation: session '{k}' does not exist", k=k))
        out["rotation"] = list(rot)
        dpw = _num(data.get("days_per_week"), "days_per_week", 1, 7, integer=True)
    else:
        raise PlanError(tr("falta «rotation» ou «schedule» (a ordem das sessões)",
                           "missing 'rotation' or 'schedule' (the order of sessions)"))
    out["days_per_week"] = dpw
    wd = data.get("weekdays")
    if wd is None:
        wd = list(WEEKDAY_PRESETS[dpw][0])
    if (not isinstance(wd, list) or len(wd) != dpw or len(set(wd)) != dpw
            or any(isinstance(d, bool) or not isinstance(d, int) or not 1 <= d <= 7
                   for d in wd)):
        raise PlanError(tr("«weekdays»: {n} dias diferentes, de 1 (segunda) a 7 (domingo)",
                           "'weekdays': {n} different days, from 1 (Monday) to 7 (Sunday)",
                           n=dpw))
    out["weekdays"] = sorted(wd)
    kit = data.get("equipment") or []
    if not isinstance(kit, list):
        raise PlanError(tr("«equipment»: tem de ser uma lista", "'equipment': must be a list"))
    need = {k for k in kit if isinstance(k, str) and k in inventory.KINDS}
    for e in out["exercises"].values():
        need |= set(e["equipment"])
    out["equipment"] = sorted(need)
    return out


# ====================================================================== ler o plano


def at(v: Any, week: int) -> Any:
    """O valor da semana `week` (1…): um valor único, ou a posição da lista (a última repete)."""
    if isinstance(v, list):
        return v[min(week, len(v)) - 1] if v else None
    return v


def outline(plan: dict) -> list[list[str]]:
    """As sessões de cada semana, pela ordem dos dias: [[«A», «B», «A»], [«B», «A», «B»], …]."""
    weeks, dpw = plan["weeks"], plan["days_per_week"]
    if plan.get("schedule"):
        return [list(plan["schedule"][w % len(plan["schedule"])]) for w in range(weeks)]
    rot = plan["rotation"]
    return [[rot[(w * dpw + d) % len(rot)] for d in range(dpw)] for w in range(weeks)]


def total_sessions(plan: dict) -> int:
    return sum(len(w) for w in outline(plan))


def entries(plan: dict, session_key: str) -> list[dict]:
    return [e for b in plan["sessions"][session_key]["blocks"] for e in b["exercises"]]


def tracks(plan: dict) -> list[dict]:
    """As progressões lineares do plano (uma por «track»): a carga inicial pede-se ao começar."""
    seen: dict[str, dict] = {}
    for week in outline(plan):
        for key in week:
            for e in entries(plan, key):
                if "add_kg" in e and e["track"] not in seen:
                    seen[e["track"]] = {"track": e["track"], "exercise": e["exercise"],
                                        "name": plan["exercises"][e["exercise"]]["name"],
                                        "add_kg": e["add_kg"], "per": e["per"],
                                        "start_pct": e.get("start_pct")}
    return list(seen.values())


def reps_text(v: Any) -> str:
    if v == "max":
        return tr("máx.", "max")
    return str(v) if v is not None else "–"


def _fmt_num(v: float) -> str:
    return f"{v:g}"


def entry_text(plan: dict, e: dict, week: int = 1) -> str:
    """«5 × 5 · +2,5 kg por sessão» / «3 × 8–12 · RPE 8» / «5@65 % · 5@75 % · 5+@85 %»."""
    bits: list[str] = []
    sets = e["sets"]
    if isinstance(sets, list) and sets and isinstance(sets[0], dict):
        rows = []
        for s in sets:
            t = reps_text(at(s.get("reps"), week)) if s.get("reps") is not None else ""
            if s.get("time") is not None:
                t = f"{_fmt_num(at(s['time'], week))} s"
            if s.get("pct1rm") is not None:
                t += f"@{_fmt_num(at(s['pct1rm'], week))} %"
            elif s.get("of_top") is not None:
                t += f"@{_fmt_num(at(s['of_top'], week) * 100)} %↑"
            elif s.get("load") is not None:
                t += f"@{_fmt_num(at(s['load'], week))} kg"
            rows.append(t)
        bits.append(" · ".join(rows))
    else:
        n = at(sets, week)
        if e.get("time") is not None:
            bits.append(f"{n} × {_fmt_num(at(e['time'], week))} s")
        elif e.get("distance") is not None:
            bits.append(f"{n} × {_fmt_num(at(e['distance'], week))} m")
        else:
            bits.append(f"{n} × {reps_text(at(e.get('reps'), week))}")
        if e.get("pct1rm") is not None:
            bits.append(f"{_fmt_num(at(e['pct1rm'], week))} % 1RM")
        if e.get("load") is not None:
            bits.append(f"{_fmt_num(at(e['load'], week))} kg")
        if e.get("rpe") is not None:
            bits.append(f"RPE {_fmt_num(at(e['rpe'], week))}")
        if e.get("rir") is not None:
            bits.append(f"RIR {_fmt_num(at(e['rir'], week))}")
    if "add_kg" in e:
        bits.append(tr("+{k:g} kg por sessão", "+{k:g} kg per session", k=e["add_kg"])
                    if e["per"] == "session" else
                    tr("+{k:g} kg por semana", "+{k:g} kg per week", k=e["add_kg"]))
    return " · ".join(b for b in bits if b)


def missing_equipment(db: Database, plan: dict) -> list[str]:
    have = inventory.available_kinds(db)
    return [k for k in plan["equipment"] if k not in have]


# ====================================================================== biblioteca


def ensure(db: Database) -> None:
    gym.ensure(db)
    cal.ensure(db)
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS programs (
      key        TEXT PRIMARY KEY,
      name       TEXT NOT NULL,
      data       TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS program_runs (
      id          INTEGER PRIMARY KEY,
      program_key TEXT NOT NULL,
      name        TEXT NOT NULL,
      start_day   TEXT NOT NULL,
      weekdays    TEXT NOT NULL,
      loads       TEXT NOT NULL DEFAULT '{}',
      status      TEXT NOT NULL DEFAULT 'active',
      data        TEXT NOT NULL,
      created_at  TEXT NOT NULL,
      ended_at    TEXT
    );
    CREATE TABLE IF NOT EXISTS program_days (
      id          INTEGER PRIMARY KEY,
      run_id      INTEGER NOT NULL REFERENCES program_runs(id) ON DELETE CASCADE,
      idx         INTEGER NOT NULL,
      week        INTEGER NOT NULL,
      day         TEXT NOT NULL,
      session_key TEXT NOT NULL,
      title       TEXT NOT NULL,
      workout_id  TEXT,
      plan_id     TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_program_days ON program_days(run_id, idx);
    """)


def builtin() -> dict[str, dict]:
    from . import program_library
    return program_library.plans()


def library(db: Database) -> list[dict]:
    """Todos os planos: os que vêm com a aplicação e os que importaste (com `key` e `origin`)."""
    ensure(db)
    out = []
    for key, p in builtin().items():
        q = dict(p)
        q.update(key=key, origin="builtin")
        out.append(q)
    for r in db.conn.execute("SELECT key, data FROM programs ORDER BY name"):
        try:
            q = validate(json.loads(r["data"]))
        except (ValueError, PlanError):
            continue
        q.update(key=r["key"], origin="imported")
        out.append(q)
    order = {c: i for i, c in enumerate(CATEGORIES)}
    out.sort(key=lambda p: (order.get(p["category"], 99), _fold(p["name"])))
    return out


def get(db: Database, key: str) -> dict | None:
    return next((p for p in library(db) if p["key"] == key), None)


def save_plan(db: Database, data: dict, key: str | None = None) -> str:
    """Guarda um plano teu (importado). Um nome igual a um que já importaste substitui-o."""
    ensure(db)
    plan = validate(data)
    key = key or "u_" + slug(plan["name"])
    if key in builtin():
        key = "u_" + key
    db.conn.execute("INSERT INTO programs (key, name, data, created_at) VALUES (?,?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET name = excluded.name, data = excluded.data",
                    (key, plan["name"], json.dumps(plan, ensure_ascii=False), now_iso()))
    db.conn.commit()
    return key


def delete_plan(db: Database, key: str) -> None:
    """Apaga um plano importado da biblioteca (os planos em curso guardam a sua cópia)."""
    ensure(db)
    db.conn.execute("DELETE FROM programs WHERE key = ?", (key,))
    db.conn.commit()


def read_file(path: Path | str, max_kb: int | None = None) -> dict:
    """Lê e valida um ficheiro de plano: JSON (o formato completo) ou CSV (a via fácil, ver
    `plan_csv`); com limite de tamanho."""
    path = Path(path)
    if path.name.lower().endswith(".csv"):
        from . import plan_csv
        return plan_csv.read_file(path, int(max_kb or 512))
    limit = (max_kb or 512) * 1024
    try:
        size = path.stat().st_size
    except OSError as e:
        raise PlanError(tr("não consegui abrir o ficheiro: {e}", "could not open the file: {e}",
                           e=e)) from None
    if size > limit:
        raise PlanError(tr("o ficheiro tem {a:.0f} kB; o máximo é {b:.0f} kB (Definições → "
                           "Avançado → Planos de treino)", "the file is {a:.0f} kB; the maximum "
                           "is {b:.0f} kB (Settings → Advanced → Training plans)",
                           a=size / 1024, b=limit / 1024))
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise PlanError(tr("o ficheiro não é JSON válido: {e}", "the file is not valid JSON: "
                           "{e}", e=str(e)[:120])) from None
    return validate(data)


def import_file(db: Database, path: Path | str) -> str:
    plan = read_file(path, int(options.get(db, "plan_import_max_kb")))
    return save_plan(db, plan)


def export_text(plan: dict) -> str:
    clean = validate({k: v for k, v in plan.items() if k not in ("key", "origin")})
    return json.dumps(clean, ensure_ascii=False, indent=2) + "\n"


def _unique(folder: Path, stem: str) -> Path:
    path = folder / (stem + EXT)
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}{EXT}"
        n += 1
    return path


def export_file(plan: dict, folder: Path | str) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = _unique(folder, slug(plan["name"]).replace("_", "-"))
    path.write_text(export_text(plan), encoding="utf-8")
    return path


def write_template(folder: Path | str) -> list[Path]:
    """Escreve o ficheiro modelo (um plano pequeno, em JSON e em CSV, comentado no .md ao lado)
    e a descrição do formato na pasta. Não substitui ficheiros que já existam."""
    from . import program_library
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    model = _unique(folder, "plano-modelo")
    model.write_text(export_text(program_library.template_plan()), encoding="utf-8")
    out.append(model)
    doc = folder / "FORMATO-DO-PLANO.md"
    if not doc.exists():
        doc.write_text(program_library.FORMAT_DOC, encoding="utf-8")
    out.append(doc)
    from . import plan_csv
    out.append(plan_csv.write_template(folder))        # a via fácil: o mesmo modelo em CSV
    return out


def scan(folders: list[str] | None = None) -> list[Path]:
    """Os ficheiros de plano (`*.perennia-plan.json`) nas pastas do costume."""
    import os
    from perennia import paths
    from .workout_files import FOLDERS, PER_FOLDER
    if folders is None:
        folders = [str(p) for p in paths.user_folder("workouts")] + \
                  [str(p) for p in paths.user_folder("imports")] + list(FOLDERS)
    found: list[Path] = []
    for folder in dict.fromkeys(folders):
        base = Path(os.path.expanduser(folder))
        if base.is_dir():
            found.extend(sorted(p for p in base.iterdir()
                                if p.is_file() and p.name.lower().endswith(
                                    (EXT, ".perennia-plan.csv")))[:PER_FOLDER])
    return found


# ====================================================================== exercícios


def resolve_exercises(db: Database, plan: dict) -> dict[str, int]:
    """O id de cada exercício do plano: o que já existe com esse nome (ou um dos «aliases»),
    sem contar acentos nem maiúsculas; os que faltam são criados, com o grupo, a medida, o
    material e a modalidade que o plano diz."""
    gym.ensure(db)
    have = {_fold(e["name"]): e["id"] for e in gym.exercises(db, include_archived=True)}
    out: dict[str, int] = {}
    for key, e in plan["exercises"].items():
        eid = None
        for name in [e["name"]] + list(e.get("aliases") or []):
            eid = have.get(_fold(name))
            if eid is not None:
                break
        if eid is None:
            eid = gym.save_exercise(db, None, name=e["name"], mods=[e["modality"]],
                                    group=e["group"], measure=e["measure"],
                                    bodyweight=e["bodyweight"], equipment=e["equipment"],
                                    description=e.get("description") or None)
            have[_fold(e["name"])] = eid
        out[key] = eid
    return out


def new_exercises(db: Database, plan: dict) -> list[str]:
    """Os exercícios do plano que ainda não existem (seriam criados ao começar)."""
    gym.ensure(db)
    have = {_fold(e["name"]) for e in gym.exercises(db, include_archived=True)}
    return [e["name"] for e in plan["exercises"].values()
            if not any(_fold(n) in have for n in [e["name"]] + list(e.get("aliases") or []))]


# ====================================================================== cargas


def round_load(db: Database, kg: float) -> float:
    step = float(options.get(db, "plan_round_kg"))
    return max(0.0, round(kg / step) * step) if step > 0 else kg


def suggest_loads(db: Database, plan: dict) -> dict[str, float]:
    """A carga inicial sugerida para cada progressão: `start_pct` da tua 1RM estimada, ou a
    carga por omissão (opção) quando ainda não há histórico do exercício."""
    ids = resolve_ids_readonly(db, plan)
    e1 = sb.e1rm_map(db)
    out = {}
    for t in tracks(plan):
        best = e1.get(ids.get(t["exercise"], -1))
        if best and t.get("start_pct"):
            out[t["track"]] = round_load(db, best * t["start_pct"] / 100.0)
        else:
            out[t["track"]] = float(options.get(db, "plan_default_start_kg"))
    return out


def resolve_ids_readonly(db: Database, plan: dict) -> dict[str, int]:
    gym.ensure(db)
    have = {_fold(e["name"]): e["id"] for e in gym.exercises(db, include_archived=True)}
    out = {}
    for key, e in plan["exercises"].items():
        for name in [e["name"]] + list(e.get("aliases") or []):
            if _fold(name) in have:
                out[key] = have[_fold(name)]
                break
    return out


# ====================================================================== construir a sessão


def _note_for(e: dict, reps: Any, base: str) -> str:
    bits = [base] if base else []
    if isinstance(reps, str):
        if reps == "max":
            bits.append(tr("máximo de repetições", "max reps"))
        elif reps.endswith("+"):
            bits.append(tr("última série: {n} ou mais (o máximo que der)",
                           "last set: {n} or more (as many as possible)", n=reps[:-1]))
        elif "-" in reps:
            bits.append(tr("{r} repetições", "{r} reps", r=reps.replace("-", "–")))
    return " · ".join(bits)


def _tidy(v: Any) -> Any:
    """180.0 → 180 (os números inteiros ficam inteiros na estrutura do treino)."""
    return int(v) if isinstance(v, float) and v.is_integer() else v


def _reps_number(reps: Any) -> int | None:
    if isinstance(reps, int):
        return reps
    if isinstance(reps, str):
        m = re.match(r"\d+", reps)
        return int(m.group()) if m else None
    return None


def session_struct(db: Database, plan: dict, session_key: str, week: int, ids: dict[str, int],
                   top_loads: dict[str, float] | None = None) -> dict:
    """A estrutura (o formato do construtor de força) da sessão `session_key` na semana
    `week`. `top_loads`: a carga principal de cada progressão nesta ocorrência."""
    top_loads = top_loads or {}
    sess = plan["sessions"][session_key]
    default_rest = int(options.get(db, "plan_default_rest_s"))
    struct = sb.empty()
    struct["instructions"] = sess.get("notes") or ""
    for b in sess["blocks"]:
        exs = []
        for e in b["exercises"]:
            meta = plan["exercises"][e["exercise"]]
            top = top_loads.get(e.get("track", "")) if "add_kg" in e else None
            rows: list[dict] = []
            notes = e.get("notes") or ""
            sets = e["sets"]
            if isinstance(sets, list) and sets and isinstance(sets[0], dict):
                for s in sets:
                    reps = at(s.get("reps"), week)
                    row = {"reps": _reps_number(reps)}
                    notes = _note_for(e, reps, notes) if isinstance(reps, str) and \
                        reps not in notes else notes
                    for f in ("pct1rm", "rpe", "rir", "time", "distance", "rest", "load"):
                        if s.get(f) is not None:
                            row[f] = at(s[f], week)
                    if top is not None:
                        row["load"] = round_load(db, top * float(at(s.get("of_top", 1.0),
                                                                    week)))
                    rows.append(row)
            else:
                n = int(at(sets, week))
                reps = at(e.get("reps"), week)
                notes = _note_for(e, reps, notes)
                row = {"reps": _reps_number(reps)}
                for f in ("pct1rm", "rpe", "rir", "time", "distance", "rest", "load"):
                    if e.get(f) is not None:
                        row[f] = at(e[f], week)
                if top is not None:
                    row["load"] = round_load(db, top)
                rows = [dict(row) for _ in range(n)]
            timed = meta["measure"] == "time" or any(r.get("time") is not None for r in rows)
            params = []
            for f in (("time",) if timed else ("reps",)) + ("load", "pct1rm", "rpe", "rir",
                                                             "distance", "rest"):
                if any(r.get(f) is not None for r in rows) or f in ("reps", "time") and \
                        f == ("time" if timed else "reps"):
                    params.append(f)
            if "load" not in params and "pct1rm" not in params and not timed \
                    and not meta["bodyweight"]:
                params.insert(1, "load")                  # a carga fica por preencher («–»)
            if "rest" not in params and b["kind"] == "single":
                params.append("rest")
                for r in rows:
                    r["rest"] = default_rest
            exs.append({"exercise_id": ids[e["exercise"]], "name": meta["name"],
                        "notes": notes, "params": params,
                        "sets": [{p: _tidy(r.get(p)) for p in params} for r in rows]})
        struct["blocks"].append({"kind": b["kind"], "rounds": b.get("rounds", 1),
                                 "rest_s": b.get("rest", 0), "notes": b.get("notes", ""),
                                 "exercises": exs})
    return sb.normalize(struct)


def _advance(tops: dict[str, float], plan: dict, session_key: str, counted: set[str],
             per: str) -> None:
    for e in entries(plan, session_key):
        if "add_kg" in e and e["per"] == per and e["track"] not in counted:
            counted.add(e["track"])
            tops[e["track"]] = tops.get(e["track"], 0.0) + e["add_kg"]


def plan_days(plan: dict, start: date, weekdays: list[int]) -> list[dict]:
    """As sessões do plano com a data de cada uma: a 1.ª semana começa na semana de `start`
    (os dias dessa semana anteriores a `start` passam para a frente, sem saltar sessões)."""
    wd = sorted(weekdays)
    out = []
    monday = start - timedelta(days=start.weekday())
    slots: list[date] = []
    d = monday
    need = total_sessions(plan)
    while len(slots) < need:
        for k in wd:
            day = d + timedelta(days=k - 1)
            if day >= start and len(slots) < need:
                slots.append(day)
        d += timedelta(days=7)
    i = 0
    for w, week in enumerate(outline(plan), 1):
        for n, key in enumerate(week, 1):
            out.append({"idx": i, "week": w, "day_no": n, "day": slots[i], "session": key})
            i += 1
    return out


def top_loads_by_day(plan: dict, days: list[dict], loads: dict[str, float],
                     from_idx: int = 0) -> dict[int, dict[str, float]]:
    """A carga principal de cada progressão em cada sessão (a partir de `from_idx`, onde as
    cargas são as de `loads`)."""
    tops = {t["track"]: float(loads.get(t["track"], 0.0)) for t in tracks(plan)}
    out: dict[int, dict[str, float]] = {}
    seen: set[str] = set()                # progressões que já apareceram (a 1.ª vez não soma)
    week_seen: dict[str, int] = {}
    for d in days:
        if d["idx"] < from_idx:
            continue
        current = {}
        for e in entries(plan, d["session"]):
            if "add_kg" not in e:
                continue
            t = e["track"]
            if e["per"] == "session":
                if t in seen and t not in current:
                    tops[t] += e["add_kg"]
            else:
                if t in week_seen and week_seen[t] != d["week"] and t not in current:
                    tops[t] += e["add_kg"] * (d["week"] - week_seen[t])
                week_seen[t] = d["week"]
            seen.add(t)
            current[t] = tops[t]
        out[d["idx"]] = current
    return out


# ====================================================================== planos em curso


def _run_row(r) -> dict:
    d = dict(r)
    for k, empty in (("weekdays", "[]"), ("loads", "{}"), ("data", "{}")):
        try:
            d[k] = json.loads(d.get(k) or empty)
        except ValueError:
            d[k] = json.loads(empty)
    return d


def runs(db: Database, active_only: bool = False) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM program_runs"
    if active_only:
        sql += " WHERE status = 'active'"
    return [_run_row(r) for r in db.conn.execute(sql + " ORDER BY status, start_day DESC, id")]


def run(db: Database, run_id: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM program_runs WHERE id = ?", (run_id,)).fetchone()
    return _run_row(r) if r else None


def day_title(plan: dict, d: dict) -> str:
    sess = plan["sessions"][d["session"]]
    return (f"{plan['name']}{TITLE_SEP}" + tr("S{w}", "W{w}", w=d["week"])
            + f"{TITLE_SEP}{sess['name']}")


def start(db: Database, key: str, start_day: date, weekdays: list[int] | None = None,
          loads: dict[str, float] | None = None) -> int:
    """Começa um plano: cria os exercícios que faltem, o treino de cada sessão e as entradas
    do calendário. Devolve o id do plano em curso."""
    ensure(db)
    plan = get(db, key)
    if plan is None:
        raise PlanError(tr("esse plano já não existe", "that plan no longer exists"))
    wd = sorted(weekdays or plan["weekdays"])
    if len(wd) != plan["days_per_week"] or len(set(wd)) != len(wd) or \
            any(not 1 <= d <= 7 for d in wd):
        raise PlanError(tr("escolhe {n} dias da semana diferentes",
                           "pick {n} different weekdays", n=plan["days_per_week"]))
    base = suggest_loads(db, plan)
    base.update({k: float(v) for k, v in (loads or {}).items() if k in base})
    snapshot = {k: v for k, v in plan.items() if k not in ("key", "origin")}
    cur = db.conn.execute(
        "INSERT INTO program_runs (program_key, name, start_day, weekdays, loads, status, data,"
        " created_at) VALUES (?,?,?,?,?,?,?,?)",
        (key, plan["name"], start_day.isoformat(), json.dumps(wd), json.dumps(base), "active",
         json.dumps(snapshot, ensure_ascii=False), now_iso()))
    run_id = int(cur.lastrowid)
    db.conn.commit()
    days = plan_days(plan, start_day, wd)
    _build(db, run_id, plan, days, base, 0)
    return run_id


def _build(db: Database, run_id: int, plan: dict, days: list[dict], loads: dict[str, float],
           from_idx: int) -> None:
    """Cria (ou refaz) os treinos e as entradas do calendário das sessões a partir de
    `from_idx`."""
    ids = resolve_exercises(db, plan)
    tops = top_loads_by_day(plan, days, loads, from_idx)
    for d in days:
        if d["idx"] < from_idx:
            continue
        struct = session_struct(db, plan, d["session"], d["week"], ids, tops.get(d["idx"]))
        title = day_title(plan, d)
        wid = sb.save(db, None, title, struct, "strength", hidden=False)
        db.conn.execute("UPDATE strength_workouts SET hidden = ? WHERE id = ?",
                        (HIDDEN_PLAN, wid))
        pid = cal.plan_add(db, d["day"], "gym", wid, title, plan["name"])
        db.conn.execute(
            "INSERT INTO program_days (run_id, idx, week, day, session_key, title, workout_id,"
            " plan_id) VALUES (?,?,?,?,?,?,?,?)",
            (run_id, d["idx"], d["week"], d["day"].isoformat(), d["session"], title, wid, pid))
    db.conn.commit()


def days(db: Database, run_id: int) -> list[dict]:
    """As sessões de um plano em curso, com `done` (a sessão foi feita — em qualquer dia) e
    `session_id` da última vez."""
    ensure(db)
    out = []
    for r in db.conn.execute("SELECT * FROM program_days WHERE run_id = ? ORDER BY idx",
                             (run_id,)):
        d = dict(r)
        s = db.conn.execute(
            "SELECT id, started_at FROM strength_sessions WHERE workout_id = ? AND status ="
            " 'completed' ORDER BY started_at DESC LIMIT 1", (d["workout_id"],)).fetchone() \
            if d["workout_id"] else None
        d["done"] = s is not None
        d["session_id"] = s["id"] if s else None
        d["done_on"] = str(s["started_at"])[:10] if s else None
        d["date"] = date.fromisoformat(d["day"])
        out.append(d)
    return out


def progress(db: Database, run_id: int) -> dict:
    ds = days(db, run_id)
    done = sum(1 for d in ds if d["done"])
    nxt = next((d for d in ds if not d["done"]), None)
    return {"total": len(ds), "done": done, "next": nxt,
            "last_day": ds[-1]["date"] if ds else None,
            "missed": sum(1 for d in ds if not d["done"] and d["date"] < date.today())}


def next_session(db: Database, today: date | None = None) -> tuple[dict, dict] | None:
    """(plano em curso, sessão) da próxima sessão por fazer de qualquer plano ativo — a mais
    próxima de hoje."""
    today = today or date.today()
    best = None
    for r in runs(db, active_only=True):
        nxt = progress(db, r["id"])["next"]
        if nxt and (best is None or nxt["date"] < best[1]["date"]):
            best = (r, nxt)
    return best


def _remove_day(db: Database, d: dict) -> None:
    if d.get("plan_id"):
        cal.plan_remove(db, d["plan_id"])
    if d.get("workout_id"):
        used = db.conn.execute("SELECT 1 FROM strength_sessions WHERE workout_id = ? LIMIT 1",
                               (d["workout_id"],)).fetchone()
        if not used:
            db.conn.execute("DELETE FROM strength_structures WHERE workout_id = ?",
                            (d["workout_id"],))
            db.conn.execute("DELETE FROM strength_workouts WHERE id = ?", (d["workout_id"],))
    db.conn.execute("DELETE FROM program_days WHERE id = ?", (d["id"],))


def rebase(db: Database, run_id: int, loads: dict[str, float]) -> int:
    """Refaz as sessões **por fazer** com novas cargas principais (a partir da próxima): para
    quando falhaste, estiveste parado, ou a progressão ficou curta. Devolve quantas refez."""
    r = run(db, run_id)
    if r is None:
        return 0
    plan = validate(r["data"])
    ds = days(db, run_id)
    todo = [d for d in ds if not d["done"]]
    if not todo:
        return 0
    first = todo[0]["idx"]
    # as cargas de partida são as que cada progressão teria agora; só mudam as que deres
    now = current_loads(db, run_id)
    keep_dates = {d["idx"]: d["date"] for d in ds}
    for d in ds:
        if d["idx"] >= first and not d["done"]:
            _remove_day(db, d)
    db.conn.commit()
    base = {k: v for k, v in r["loads"].items() if k != REBASED_AT}
    base.update(now)
    base.update({k: float(v) for k, v in loads.items() if k in base})
    base[REBASED_AT] = first              # as cargas passam a contar a partir desta sessão
    all_days = [{"idx": d["idx"], "week": d["week"], "day": keep_dates[d["idx"]],
                 "session": d["session_key"]} for d in ds]
    skip = {d["idx"] for d in ds if d["done"] and d["idx"] >= first}
    _build(db, run_id, plan, [d for d in all_days if d["idx"] not in skip], base, first)
    db.conn.execute("UPDATE program_runs SET loads = ? WHERE id = ?", (json.dumps(base), run_id))
    db.conn.commit()
    return len(todo)


def current_loads(db: Database, run_id: int) -> dict[str, float]:
    """A carga principal que cada progressão teria na próxima sessão por fazer."""
    r = run(db, run_id)
    if r is None:
        return {}
    plan = validate(r["data"])
    ds = days(db, run_id)
    all_days = [{"idx": d["idx"], "week": d["week"], "day": d["date"],
                 "session": d["session_key"]} for d in ds]
    tops = top_loads_by_day(plan, all_days, r["loads"], int(r["loads"].get(REBASED_AT, 0)))
    todo = [d for d in ds if not d["done"]]
    out = {}
    for t in tracks(plan):
        val = None
        for d in todo:
            if t["track"] in tops.get(d["idx"], {}):
                val = tops[d["idx"]][t["track"]]
                break
        out[t["track"]] = val if val is not None else float(r["loads"].get(t["track"], 0.0))
    return out


def shift(db: Database, run_id: int, n_days: int) -> int:
    """Empurra as sessões por fazer `n_days` dias (uma semana de férias, uma gripe)."""
    moved = 0
    for d in days(db, run_id):
        if d["done"]:
            continue
        new = d["date"] + timedelta(days=n_days)
        db.conn.execute("UPDATE program_days SET day = ? WHERE id = ?", (new.isoformat(),
                                                                         d["id"]))
        if d.get("plan_id"):
            cal.plan_move(db, d["plan_id"], new)
        moved += 1
    db.conn.commit()
    return moved


def end(db: Database, run_id: int, delete: bool = False) -> None:
    """Termina um plano em curso: as sessões por fazer saem do calendário (e os treinos delas
    apagam-se); o que já fizeste fica no histórico. `delete`: tira também o registo do plano."""
    for d in days(db, run_id):
        if not d["done"]:
            _remove_day(db, d)
        elif d.get("plan_id"):
            cal.plan_remove(db, d["plan_id"])
    if delete:
        db.conn.execute("DELETE FROM program_days WHERE run_id = ?", (run_id,))
        db.conn.execute("DELETE FROM program_runs WHERE id = ?", (run_id,))
    else:
        db.conn.execute("UPDATE program_runs SET status = 'ended', ended_at = ? WHERE id = ?",
                        (now_iso(), run_id))
    db.conn.commit()


def finish_if_done(db: Database) -> list[str]:
    """Os planos em curso em que já fizeste todas as sessões passam a «terminado»."""
    out = []
    for r in runs(db, active_only=True):
        p = progress(db, r["id"])
        if p["total"] and p["done"] == p["total"]:
            db.conn.execute("UPDATE program_runs SET status = 'ended', ended_at = ? WHERE id = ?",
                            (now_iso(), r["id"]))
            out.append(r["name"])
    db.conn.commit()
    return out


def clone(plan: dict) -> dict:
    return copy.deepcopy(plan)
