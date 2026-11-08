"""O índice de longevidade.

Um número (0–100) por período — 1 dia, 1 semana, 1 mês… 20 anos — que diz
quanto do que o corpo precisa para durar mais tem sido feito, e um radar com os
**eixos** onde o treino tem estado concentrado (e onde falta):

    aeróbio · limiar · VO2máx · anaeróbio · força · potência · mobilidade ·
    estabilidade (isométricos, tendões) · recuperação

Tudo o que fazes entra: cada sessão (ciclismo, remo, corrida, natação, ginásio)
pelos minutos que passou em cada zona/modalidade; os hábitos (sono, HRV) na
recuperação; os resultados dos testes (os de longevidade e os de aptidão).

A fórmula, para cada eixo `a` e período de `D` dias:

    R_a   = minutos do eixo / (D / 7)          (minutos por semana)
    S_a   = 100 · (1 − e^(−R_a / T_a))          (satura: o último minuto vale menos)
    S_a'  = 0,75 · S_a + 0,25 · teste_a          (se houver teste do eixo no período)
    índice = Σ w_a · S_a' / Σ w_a

`T_a` é a dose semanal que dá 63 % da nota (a «dose de referência» do eixo) e
`w_a` o peso do eixo (o VO2máx, a força e o aeróbio pesam mais: são os que mais
se ligam à longevidade). Até haver `D` dias de histórico, divide-se pelos dias
que há (no mínimo 7), para quem começou ontem não ficar a zero em 20 anos.
"""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import tags as tg
from .i18n import tr

AXES = ("aerobic", "threshold", "vo2max", "anaerobic", "strength", "power", "mobility",
        "stability", "recovery")
LABELS = {
    "aerobic": ("Aeróbio", "Aerobic"), "threshold": ("Limiar", "Threshold"),
    "vo2max": ("VO2máx", "VO2max"), "anaerobic": ("Anaeróbio", "Anaerobic"),
    "strength": ("Força", "Strength"), "power": ("Potência", "Power"),
    "mobility": ("Mobilidade", "Mobility"), "stability": ("Estabilidade", "Stability"),
    "recovery": ("Recuperação", "Recovery"),
}
WEIGHTS = {"aerobic": 1.5, "threshold": 1.0, "vo2max": 1.5, "anaerobic": 0.5, "strength": 1.5,
           "power": 0.8, "mobility": 1.0, "stability": 1.0, "recovery": 1.0}
# minutos por semana que dão 63 % da nota do eixo
TARGETS = {"aerobic": 240.0, "threshold": 30.0, "vo2max": 15.0, "anaerobic": 6.0,
           "strength": 90.0, "power": 20.0, "mobility": 60.0, "stability": 40.0,
           "recovery": 300.0}

PERIODS: tuple[tuple[str, int], ...] = (
    ("1d", 1), ("1w", 7), ("1m", 30), ("3m", 91), ("6m", 182), ("9m", 274), ("1y", 365),
    ("2y", 730), ("3y", 1095), ("5y", 1825), ("10y", 3650), ("15y", 5475), ("20y", 7300))
PERIOD_DAYS = dict(PERIODS)

# a zona de potência (7) ou de FC (5) conta para um eixo
POWER_ZONE_AXIS = ("recovery", "aerobic", "aerobic", "threshold", "vo2max", "anaerobic",
                   "anaerobic")
HR_ZONE_AXIS = ("recovery", "aerobic", "aerobic", "threshold", "vo2max")
# o tipo de treino → eixo, quando não há zonas (importadas, sem amostras)
TYPE_AXIS = {"recovery": "recovery", "endurance": "aerobic", "tempo": "aerobic",
             "threshold": "threshold", "vo2max": "vo2max", "anaerobic": "anaerobic",
             "work": "threshold", "race_warmup": "aerobic", "race": "vo2max",
             "test": "threshold", "technique": "aerobic", "strength": "strength",
             "mobility": "mobility"}
MODALITY_AXIS = {"strength": "strength", "calisthenics": "strength", "rings": "strength",
                 "bands": "strength", "kettlebell": "strength", "sandbag": "strength",
                 "plyometrics": "power", "hiit": "power", "cardio": "aerobic",
                 "conditioning": "aerobic", "animal_flow": "mobility", "yoga": "mobility",
                 "longevity": "stability", "mobility": "mobility", "tendons": "stability",
                 "isometric": "stability"}
# os testes por palavra do nome (sem acentos) → eixo
TEST_WORDS = (("ftp", "threshold"), ("20 min", "threshold"), ("rampa", "threshold"),
              ("vo2", "vo2max"), ("5 min", "vo2max"), ("2000", "vo2max"), ("cooper", "vo2max"),
              ("sprint", "anaerobic"), ("1 min", "anaerobic"), ("30 s", "anaerobic"),
              ("flex", "strength"), ("elevac", "strength"), ("agachamento", "strength"),
              ("sentar e levantar em 30", "strength"), ("suspensao", "strength"),
              ("prancha", "stability"), ("equilibrio", "stability"),
              ("do chao", "mobility"), ("salto", "power"), ("caminhada", "aerobic"))


def axis_label(axis: str) -> str:
    pt, en = LABELS.get(axis, (axis, axis))
    return tr(pt, en)


def period_label(key: str) -> str:
    pt = {"1d": "1 dia", "1w": "1 semana", "1m": "1 mês", "3m": "3 meses", "6m": "6 meses",
          "9m": "9 meses", "1y": "1 ano", "2y": "2 anos", "3y": "3 anos", "5y": "5 anos",
          "10y": "10 anos", "15y": "15 anos", "20y": "20 anos"}
    en = {"1d": "1 day", "1w": "1 week", "1m": "1 month", "3m": "3 months", "6m": "6 months",
          "9m": "9 months", "1y": "1 year", "2y": "2 years", "3y": "3 years", "5y": "5 years",
          "10y": "10 years", "15y": "15 years", "20y": "20 years"}
    return tr(pt.get(key, key), en.get(key, key))


@dataclass
class Dose:
    """Os minutos de uma sessão em cada eixo."""
    day: date
    sport: str
    sid: str
    mins: dict = field(default_factory=dict)


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def _add(acc: dict, axis: str, minutes: float) -> None:
    if minutes > 0:
        acc[axis] = acc.get(axis, 0.0) + minutes


def _zones_to_axes(seconds: list[float], mapping: tuple[str, ...]) -> dict:
    acc: dict = {}
    for z, sec in enumerate(seconds):
        if sec:
            _add(acc, mapping[min(z, len(mapping) - 1)], sec / 60.0)
    return acc


def shares(mins: dict) -> dict:
    """A parte (0–100 %) de cada eixo numa sessão: o radar da sessão. Z2 → 100 % aeróbio."""
    total = sum(v for v in mins.values() if v > 0)
    if total <= 0:
        return {}
    return {a: 100.0 * mins.get(a, 0.0) / total for a in AXES if mins.get(a, 0.0) > 0}


# ----------------------------------------------------- doses de cada sessão


def _json_list(text) -> list:
    try:
        v = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return v if isinstance(v, list) else []


def _endurance_mins(zone_s: list, seconds: float, mapping, fallback_type: str | None) -> dict:
    mins = _zones_to_axes([float(x or 0) for x in zone_s], mapping) if zone_s else {}
    if not mins and seconds > 0:
        axis = TYPE_AXIS.get(fallback_type or "endurance", "aerobic")
        mins = {axis: seconds / 60.0}
    return mins


def _tag_type(db, sport: str, sid: str) -> str | None:
    try:
        return tg.load(db, sport, sid).get("workout_type")
    except Exception:
        return None


def all_doses(db) -> list[Dose]:
    """A dose de todas as sessões concluídas, de todos os desportos."""
    from . import stats
    out: list[Dose] = []
    # ciclismo: tempo em cada zona de potência (ou de FC), em cache na base
    try:
        zones = stats.ride_zone_seconds(db)
    except Exception:
        zones = {}
    for r in db.conn.execute("SELECT id, started_at, moving_s, elapsed_s FROM rides"
                             " WHERE status='completed'"):
        z = zones.get(r["id"]) or {}
        secs = float(r["moving_s"] or r["elapsed_s"] or 0)
        day = z.get("day") or stats._local_date(r["started_at"])
        if day is None:
            continue
        power, hr = z.get("power") or [], z.get("hr") or []
        if sum(power) > 0:
            mins = _zones_to_axes(power, POWER_ZONE_AXIS)
        elif sum(hr) > 0:
            mins = _zones_to_axes(hr, HR_ZONE_AXIS)
        else:
            mins = _endurance_mins([], secs, HR_ZONE_AXIS, _tag_type(db, "cycling", r["id"]))
        if mins:
            out.append(Dose(day, "cycling", r["id"], mins))
    for table, sport, sid_col in (("row_sessions", "rowing", "id"),
                                  ("endurance_sessions", None, "id")):
        try:
            rows = db.conn.execute(f"SELECT * FROM {table} WHERE status='completed'").fetchall()
        except Exception:
            continue
        for r in rows:
            day = stats._local_date(r["started_at"])
            if day is None:
                continue
            sp = sport or r["sport"]
            secs = float(r["moving_s"] or r["elapsed_s"] or 0)
            mins = _endurance_mins(_json_list(r["hr_zone_s"]), secs, HR_ZONE_AXIS,
                                   _tag_type(db, sp, r[sid_col]))
            if mins:
                out.append(Dose(day, sp, r[sid_col], mins))
    out += _strength_doses(db)
    return out


def _strength_doses(db) -> list[Dose]:
    from . import stats
    out: list[Dose] = []
    try:
        sessions = db.conn.execute("SELECT * FROM strength_sessions WHERE status='completed'"
                                   ).fetchall()
    except Exception:
        return out
    mods: dict = {}
    try:
        for r in db.conn.execute("SELECT exercise_id, modality FROM exercise_modalities"):
            mods.setdefault(r["exercise_id"], []).append(r["modality"])
    except Exception:
        pass
    for s in sessions:
        day = stats._local_date(s["started_at"])
        if day is None:
            continue
        total_min = float(s["elapsed_s"] or 2700) / 60.0
        sets = db.conn.execute("SELECT exercise_id, COUNT(*) AS n FROM strength_sets WHERE"
                               " session_id = ? GROUP BY exercise_id", (s["id"],)).fetchall()
        n_all = sum(r["n"] for r in sets)
        mins: dict = {}
        for r in sets:
            share = total_min * r["n"] / n_all
            ms = [m for m in mods.get(r["exercise_id"], []) if m in MODALITY_AXIS] or \
                [s["modality"] or "strength"]
            for m in ms:
                _add(mins, MODALITY_AXIS.get(m, "strength"), share / len(ms))
        if not mins:
            _add(mins, MODALITY_AXIS.get(s["modality"] or "strength", "strength"), total_min)
        out.append(Dose(day, "strength", s["id"], mins))
    return out


def session_mins(db, sport: str, sid: str) -> dict:
    """Os minutos por eixo de uma sessão (para o radar dela)."""
    sport = {"ride": "cycling", "row": "rowing"}.get(sport, sport)
    for d in all_doses(db):
        if d.sport == sport and d.sid == str(sid):
            return d.mins
    return {}


def blocks_mins(blocks, sport: str, bounds=None) -> dict:
    """Os minutos por eixo de um treino ainda por fazer (os blocos do construtor):
    cada bloco conta pela zona do seu alvo (% do limiar)."""
    bounds = list(bounds or (55, 75, 90, 105, 120, 150))
    acc: dict = {}
    for b in blocks:
        secs = tg.block_seconds(b, sport)
        lo = getattr(b, "lo", None)
        if secs <= 0:
            continue
        pct = 70.0 if lo is None else b.mid()
        z = sum(1 for x in bounds if pct >= x)
        _add(acc, POWER_ZONE_AXIS[min(z, len(POWER_ZONE_AXIS) - 1)], secs / 60.0)
    return acc


# ------------------------------------------------------- testes e hábitos


def _test_axis(test: dict) -> str | None:
    name = _fold(test.get("name") or "")
    proto = _fold(test.get("protocol") or "")
    for word, axis in TEST_WORDS:
        if word in name or word == proto:
            return axis
    return None


def test_scores(db, start: date, end: date) -> dict:
    """{eixo: nota 0–100} pelos testes feitos no período: o último resultado face ao
    melhor de sempre (com um só resultado não há termo de comparação: 60)."""
    out: dict = {}
    try:
        from . import fitness_tests as ft
        ft.ensure(db)
        tests = db.conn.execute("SELECT * FROM fitness_tests WHERE active = 1").fetchall()
    except Exception:
        return out
    per_axis: dict = {}
    for t_ in tests:
        axis = _test_axis(dict(t_))
        if axis is None:
            continue
        res = db.conn.execute("SELECT done_on, value FROM test_results WHERE test_id = ?"
                              " ORDER BY done_on", (t_["id"],)).fetchall()
        res = [(r["done_on"][:10], float(r["value"])) for r in res]
        res = [(d, v) for d, v in res if d <= end.isoformat()]
        inside = [(d, v) for d, v in res if d >= start.isoformat()]
        if not inside:
            continue
        last = inside[-1][1]
        vals = [v for _d, v in res]
        if len(vals) < 2:
            score = 60.0
        elif t_["better"] == "lower":
            score = 100.0 * min(vals) / last if last > 0 else 0.0
        else:
            best = max(vals)
            score = 100.0 * last / best if best > 0 else 0.0
        per_axis.setdefault(axis, []).append(max(0.0, min(100.0, score)))
    for axis, vals in per_axis.items():
        out[axis] = sum(vals) / len(vals)
    return out


def habit_minutes(db, start: date, end: date) -> float:
    """Recuperação dos hábitos: 30 min por dia com 7 h ou mais de sono, 15 por dia com
    HRV registada (a consistência conta)."""
    total = 0.0
    try:
        q = ("SELECT d.day AS day, m.key AS k, d.num AS num FROM daily_values d JOIN"
             " metric_defs m ON m.id = d.metric_id WHERE d.day >= ? AND d.day <= ? AND"
             " m.key IN ('sleep_hours', 'hrv_rmssd', 'hrv_score')")
        sleep_days, hrv_days = set(), set()
        for r in db.conn.execute(q, (start.isoformat(), end.isoformat())):
            if r["k"] == "sleep_hours" and (r["num"] or 0) >= 7:
                sleep_days.add(r["day"])
            elif r["k"] in ("hrv_rmssd", "hrv_score") and r["num"] is not None:
                hrv_days.add(r["day"])
        total = 30.0 * len(sleep_days) + 15.0 * len(hrv_days)
    except Exception:
        pass
    return total


# ------------------------------------------------------------------ índice


def compute(db, as_of: date | None = None, *, doses: list[Dose] | None = None,
            exclude: tuple | None = None, extra: list[Dose] | None = None) -> dict:
    """{período: {"days", "index", "axes": {eixo: nota}}} para todos os períodos.
    `exclude=(desporto, id)` tira uma sessão (para ver o que ela acrescentou) e `extra`
    junta sessões que ainda não aconteceram (o construtor)."""
    as_of = as_of or date.today()
    base = all_doses(db) if doses is None else list(doses)
    if exclude:
        base = [d for d in base if (d.sport, d.sid) != (exclude[0], str(exclude[1]))]
    base += list(extra or [])
    days_with = [d.day for d in base]
    first = min(days_with) if days_with else as_of
    span = max(7, (as_of - first).days + 1)
    out: dict = {}
    for key, days in PERIODS:
        start = as_of - timedelta(days=days - 1)
        acc = {a: 0.0 for a in AXES}
        for d in base:
            if start <= d.day <= as_of:
                for a, m in d.mins.items():
                    acc[a] += m
        acc["recovery"] += habit_minutes(db, start, as_of)
        weeks = max(7, min(days, span)) / 7.0
        tests = test_scores(db, start, as_of)
        axes = {}
        for a in AXES:
            s = 100.0 * (1.0 - math.exp(-(acc[a] / weeks) / TARGETS[a]))
            if a in tests:
                s = 0.75 * s + 0.25 * tests[a]
            axes[a] = s
        index = sum(WEIGHTS[a] * axes[a] for a in AXES) / sum(WEIGHTS.values())
        out[key] = {"days": days, "index": index, "axes": axes}
    return out


def trend(result: dict) -> list[tuple[str, float, float | None]]:
    """[(período, índice, diferença para o período seguinte, mais longo)]: se o curto
    está acima do longo, o corpo está a melhorar."""
    keys = [k for k, _d in PERIODS]
    rows = []
    for i, k in enumerate(keys):
        nxt = result[keys[i + 1]]["index"] if i + 1 < len(keys) else None
        rows.append((k, result[k]["index"], None if nxt is None else result[k]["index"] - nxt))
    return rows


def impact_of(db, mins: dict, *, sport: str = "cycling", sid: str = "new",
              exclude: tuple | None = None, as_of: date | None = None,
              periods: tuple[str, ...] = ("1w", "1m", "3m"),
              doses: list[Dose] | None = None) -> dict:
    """O que uma sessão (os seus minutos por eixo) acrescenta ao índice: {período:
    diferença}, mais os eixos onde mais mexe. Se `exclude` for a própria sessão (já
    gravada), compara com o índice sem ela; senão junta-a como se fosse hoje."""
    as_of = as_of or date.today()
    doses = all_doses(db) if doses is None else doses
    if exclude:
        without = compute(db, as_of, doses=doses, exclude=exclude)
        with_ = compute(db, as_of, doses=doses)
    else:
        without = compute(db, as_of, doses=doses)
        with_ = compute(db, as_of, doses=doses, extra=[Dose(as_of, sport, str(sid), dict(mins))])
    deltas = {p: with_[p]["index"] - without[p]["index"] for p in periods}
    axes = {a: with_["1m"]["axes"][a] - without["1m"]["axes"][a] for a in AXES}
    top = sorted(((a, v) for a, v in axes.items() if v > 0.05), key=lambda kv: -kv[1])
    return {"deltas": deltas, "axes": axes, "top": top[:3]}


def session_impact(db, sport: str, sid: str) -> dict:
    """O impacto de uma sessão já gravada (usado no fim da sessão e na análise)."""
    sport = {"ride": "cycling", "row": "rowing"}.get(sport, sport)
    doses = all_doses(db)
    mine = next((d for d in doses if d.sport == sport and d.sid == str(sid)), None)
    if mine is None or not mine.mins:
        return {"deltas": {}, "axes": {}, "top": [], "mins": {}}
    out = impact_of(db, mine.mins, sport=sport, sid=str(sid), exclude=(sport, str(sid)),
                    as_of=mine.day, doses=doses)
    out["mins"] = mine.mins
    return out


def fmt_delta(v: float) -> str:
    """+0,8 · para diferenças pequenas, duas casas (+0,02): uma sessão curta mexe pouco."""
    return f"{v:+.2f}" if abs(v) < 0.1 else f"{v:+.1f}"


def impact_text(impact: dict) -> str:
    """Uma linha para o resumo: «+0,8 numa semana · +0,3 num mês · mais em: Aeróbio»."""
    d = impact.get("deltas") or {}
    if not d:
        return ""
    names = {"1w": tr("1 sem", "1 wk"), "1m": tr("1 mês", "1 mo"), "3m": tr("3 meses", "3 mo")}
    bits = [f"{names.get(k, k)} {fmt_delta(v)}" for k, v in d.items()]
    if impact.get("top"):
        bits.append(tr("mais em ", "mostly ") + ", ".join(axis_label(a) for a, _v in
                                                          impact["top"][:2]))
    return " · ".join(bits)
