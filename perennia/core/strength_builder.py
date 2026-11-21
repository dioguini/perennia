"""Construtor de treinos de força por blocos (como o «Strength Workout
Builder» do TrainingPeaks).

Um treino é uma lista de **blocos**: exercício único, superset, circuito,
aquecimento e retorno à calma. Cada bloco tem exercícios; cada exercício tem
**parâmetros** (repetições, carga, % da 1RM, RPE, RIR, tempo, distância,
descanso) e uma linha por **série**, com o valor de cada parâmetro (vazio
= «–», por preencher). Os rótulos seguem o costume: blocos A, B, C…, e os
exercícios de um bloco A1, A2…

* **Superset** — as séries alternam entre os exercícios (A1, A2, A1, A2…);
  na sessão pode-se mexer à vontade.
* **Circuito** — dá-se a volta a todos os exercícios, «voltas» vezes; o bloco
  faz-se inteiro.
* **Aquecimento / Retorno à calma** — como um superset, no início ou no fim.

Grava-se em `strength_structures` (JSON) e, para o resto da aplicação
continuar igual, também como a lista simples de sempre
(`strength_workout_items`): um item por exercício. A sessão lê a estrutura
para saber a ordem das séries e o alvo de cada uma.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from .i18n import tr

KINDS = ("single", "superset", "circuit", "warmup", "cooldown")
PARAMS = ("reps", "load", "pct1rm", "rpe", "rir", "time", "distance", "rest")
DEFAULT_PARAMS = ["reps", "load", "rest"]
DEFAULT_TIME_PARAMS = ["time", "rest"]


def kind_name(kind: str) -> str:
    return {"single": tr("Exercício único", "Single exercise"),
            "superset": tr("Superset", "Superset"), "circuit": tr("Circuito", "Circuit"),
            "warmup": tr("Aquecimento", "Warm up"),
            "cooldown": tr("Retorno à calma", "Cool down")}.get(kind, kind)


def param_name(p: str) -> str:
    return {"reps": tr("Reps", "Reps"), "load": tr("Carga (kg)", "Weight (kg)"),
            "pct1rm": tr("% 1RM", "% 1RM"), "rpe": "RPE", "rir": "RIR",
            "time": tr("Tempo (s)", "Time (s)"), "distance": tr("Distância (m)", "Distance (m)"),
            "rest": tr("Descanso (s)", "Rest (s)")}.get(p, p)


def param_help(p: str) -> str:
    return {"rpe": tr("RPE: esforço de 1 a 10 (RPE 8 ≈ 2 repetições em reserva)",
                      "RPE: effort 1–10 (RPE 8 ≈ 2 reps in reserve)"),
            "rir": tr("RIR: repetições que ficam em reserva", "RIR: reps left in reserve"),
            "pct1rm": tr("% da 1RM estimada: a carga sai do teu histórico",
                         "% of estimated 1RM: the load comes from your history")}.get(p, "")


# ================================================================== modelo


def new_set(params: list[str], like: dict | None = None) -> dict:
    s = {p: None for p in params}
    if like:
        for p in params:
            s[p] = like.get(p)
    return s


def new_exercise(ex: dict, measure: str = "reps") -> dict:
    params = list(DEFAULT_TIME_PARAMS if measure == "time" else DEFAULT_PARAMS)
    return {"exercise_id": int(ex["id"]), "name": ex["name"], "notes": "",
            "params": params, "sets": [new_set(params) for _ in range(3)]}


def new_block(kind: str, exercises: list[dict] | None = None) -> dict:
    return {"kind": kind, "rounds": 3 if kind == "circuit" else 1,
            "rest_s": 90 if kind in ("superset", "circuit") else 0, "notes": "",
            "exercises": list(exercises or [])}


def empty() -> dict:
    return {"instructions": "", "start_time": "", "blocks": []}


def letter(i: int) -> str:
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def label(bi: int, ei: int, block: dict) -> str:
    if len(block["exercises"]) <= 1 and block["kind"] == "single":
        return letter(bi)
    return f"{letter(bi)}{ei + 1}"


def normalize(struct: dict) -> dict:
    """Corrige o que vier estragado: blocos vazios saem, superset com um só
    exercício volta a ser exercício único, os parâmetros e as séries batem."""
    out = {"instructions": str(struct.get("instructions") or ""),
           "start_time": str(struct.get("start_time") or ""), "blocks": []}
    for b in struct.get("blocks") or []:
        exs = [e for e in (b.get("exercises") or []) if e.get("exercise_id") is not None]
        if not exs:
            continue
        kind = b.get("kind") if b.get("kind") in KINDS else "single"
        if kind == "single" and len(exs) > 1:
            kind = "superset"
        if kind == "superset" and len(exs) == 1:
            kind = "single"
        nb = {"kind": kind, "rounds": max(1, int(b.get("rounds") or 1)),
              "rest_s": max(0, int(b.get("rest_s") or 0)), "notes": str(b.get("notes") or ""),
              "exercises": []}
        for e in exs:
            params = [p for p in (e.get("params") or DEFAULT_PARAMS) if p in PARAMS]
            params = list(dict.fromkeys(params)) or list(DEFAULT_PARAMS)
            sets = [new_set(params, s) for s in (e.get("sets") or [])] or [new_set(params)]
            nb["exercises"].append({"exercise_id": int(e["exercise_id"]),
                                    "name": str(e.get("name") or ""),
                                    "notes": str(e.get("notes") or ""),
                                    "params": params, "sets": sets})
        out["blocks"].append(nb)
    return out


# ================================================================ operações


def add_block(struct: dict, kind: str, exercises: list[dict]) -> int:
    struct["blocks"].append(new_block(kind, exercises))
    return len(struct["blocks"]) - 1


def remove_block(struct: dict, bi: int) -> None:
    del struct["blocks"][bi]


def move_block(struct: dict, src: int, dst: int) -> int:
    """Muda o bloco `src` para a posição `dst` (antes do bloco que lá está)."""
    blocks = struct["blocks"]
    b = blocks.pop(src)
    if dst > src:
        dst -= 1
    dst = max(0, min(len(blocks), dst))
    blocks.insert(dst, b)
    return dst


def combine(struct: dict, src: int, dst: int) -> int:
    """Larga o bloco `src` em cima do `dst`: os exercícios juntam-se num
    superset (ou entram no circuito / aquecimento que lá estiver)."""
    if src == dst:
        return dst
    blocks = struct["blocks"]
    moving = blocks[src]["exercises"]
    target = blocks[dst]
    target["exercises"].extend(moving)
    if target["kind"] == "single":
        target["kind"] = "superset"
        target["rest_s"] = target["rest_s"] or 90
    del blocks[src]
    return dst - 1 if src < dst else dst


def unlink(struct: dict, bi: int, ei: int) -> int:
    """Tira o exercício do bloco e põe-no num bloco só dele, logo a seguir."""
    block = struct["blocks"][bi]
    if len(block["exercises"]) <= 1:
        return bi
    ex = block["exercises"].pop(ei)
    if block["kind"] == "superset" and len(block["exercises"]) == 1:
        block["kind"] = "single"
    struct["blocks"].insert(bi + 1, new_block("single", [ex]))
    return bi + 1


def convert(struct: dict, bi: int, kind: str) -> None:
    block = struct["blocks"][bi]
    block["kind"] = kind
    if kind == "circuit" and block.get("rounds", 1) < 2:
        block["rounds"] = 3
    if kind in ("superset", "circuit") and not block.get("rest_s"):
        block["rest_s"] = 90


def add_param(struct: dict, bi: int, ei: int, param: str) -> None:
    ex = struct["blocks"][bi]["exercises"][ei]
    if param in ex["params"] or param not in PARAMS:
        return
    ex["params"].append(param)
    for s in ex["sets"]:
        s.setdefault(param, None)
    # RPE e RIR dizem o mesmo: só um de cada vez
    other = {"rpe": "rir", "rir": "rpe", "load": "pct1rm", "pct1rm": "load"}.get(param)
    if other and other in ex["params"] and param in ("rpe", "rir"):
        remove_param(struct, bi, ei, other)


def remove_param(struct: dict, bi: int, ei: int, param: str) -> None:
    ex = struct["blocks"][bi]["exercises"][ei]
    if param in ex["params"] and len(ex["params"]) > 1:
        ex["params"].remove(param)
        for s in ex["sets"]:
            s.pop(param, None)


def replace_param(struct: dict, bi: int, ei: int, old: str, new: str) -> None:
    ex = struct["blocks"][bi]["exercises"][ei]
    if old not in ex["params"] or new in ex["params"]:
        return
    ex["params"][ex["params"].index(old)] = new
    for s in ex["sets"]:
        s[new] = s.pop(old, None) if old in ("rpe", "rir") and new in ("rpe", "rir") else None
        if old in ("rpe", "rir") and new in ("rpe", "rir") and s[new] is not None:
            s[new] = 10 - s[new]                       # RPE 8 ≈ RIR 2


def add_set(struct: dict, bi: int, ei: int) -> None:
    ex = struct["blocks"][bi]["exercises"][ei]
    last = ex["sets"][-1] if ex["sets"] else None
    ex["sets"].append(new_set(ex["params"], last))


def remove_set(struct: dict, bi: int, ei: int, si: int) -> None:
    ex = struct["blocks"][bi]["exercises"][ei]
    if len(ex["sets"]) > 1:
        del ex["sets"][si]


def set_value(struct: dict, bi: int, ei: int, si: int, param: str, value: Any) -> None:
    ex = struct["blocks"][bi]["exercises"][ei]
    if param not in ex["params"]:
        return
    if value is not None:
        lim = {"reps": (0, 500), "load": (0, 1000), "pct1rm": (1, 120), "rpe": (1, 10),
               "rir": (0, 10), "time": (0, 7200), "distance": (0, 100000),
               "rest": (0, 3600)}[param]
        value = max(lim[0], min(lim[1], value))
        if param in ("reps", "time", "distance", "rest", "rir"):
            value = int(round(value))
    ex["sets"][si][param] = value


def fill_down(struct: dict, bi: int, ei: int, si: int, param: str) -> None:
    """Copia o valor desta série para as de baixo (como no TrainingPeaks)."""
    ex = struct["blocks"][bi]["exercises"][ei]
    v = ex["sets"][si].get(param)
    for s in ex["sets"][si + 1:]:
        s[param] = v


# ================================================================== leitura


def fmt_value(param: str, v) -> str:
    if v is None:
        return "–"
    if param in ("load", "rpe") and isinstance(v, float):
        return f"{v:g}"
    if param == "pct1rm":
        return f"{v:g}%"
    return f"{v:g}" if isinstance(v, float) else str(v)


def _range(values: list) -> str:
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    if len(set(vals)) == 1:
        return f"{vals[0]:g}" if isinstance(vals[0], float) else str(vals[0])
    return "/".join(f"{v:g}" if isinstance(v, float) else str(v) for v in values
                    if v is not None)


def prescription(ex: dict) -> str:
    """«3 × 5 @ 100 kg · RPE 8 · 90 s» ou «5/5/3 reps @ 100/105/110 kg»."""
    sets = ex["sets"]
    n = len(sets)
    p = ex["params"]
    bits = []
    if "reps" in p:
        r = _range([s.get("reps") for s in sets])
        bits.append(f"{n} × {r}" if r and "/" not in r else (
            f"{r} reps" if r else tr("{n} séries", "{n} sets", n=n)))
    elif "time" in p:
        tt = _range([s.get("time") for s in sets])
        bits.append(f"{n} × {tt} s" if tt and "/" not in tt else (
            f"{tt} s" if tt else tr("{n} séries", "{n} sets", n=n)))
    else:
        bits.append(tr("{n} séries", "{n} sets", n=n))
    if "load" in p:
        ld = _range([s.get("load") for s in sets])
        if ld:
            bits[-1] += f" @ {ld} kg"
    if "pct1rm" in p:
        pc = _range([s.get("pct1rm") for s in sets])
        if pc:
            bits[-1] += f" @ {pc}% 1RM"
    if "distance" in p:
        d = _range([s.get("distance") for s in sets])
        if d:
            bits.append(f"{d} m")
    for k, pre in (("rpe", "RPE "), ("rir", "RIR ")):
        if k in p:
            v = _range([s.get(k) for s in sets])
            if v:
                bits.append(pre + v)
    if "rest" in p:
        v = _range([s.get("rest") for s in sets])
        if v:
            bits.append(f"{v} s")
    return " · ".join(bits)


def summary_lines(struct: dict) -> list[tuple[str, str, str]]:
    """[(rótulo, exercício, prescrição)] para o painel do resumo."""
    out = []
    for bi, b in enumerate(struct["blocks"]):
        head = kind_name(b["kind"])
        if b["kind"] == "circuit":
            head += tr(" · {n} voltas", " · {n} rounds", n=b["rounds"])
        out.append((letter(bi), head, ""))
        for ei, e in enumerate(b["exercises"]):
            out.append((label(bi, ei, b), e["name"], prescription(e)))
    return out


def rounds_of(block: dict) -> int:
    return block["rounds"] if block["kind"] == "circuit" else 1


def sequence(struct: dict) -> list[tuple[int, int]]:
    """A ordem das séries na sessão: [(índice do exercício, n.º da série)].
    O índice do exercício é a posição na lista simples (por blocos)."""
    seq: list[tuple[int, int]] = []
    item = 0
    for b in struct["blocks"]:
        exs = b["exercises"]
        base = item
        if b["kind"] == "single" or len(exs) == 1 and b["kind"] != "circuit":
            for k, e in enumerate(exs):
                seq += [(base + k, s) for s in range(len(e["sets"]))]
        elif b["kind"] == "circuit":
            for r in range(b["rounds"]):
                for k, e in enumerate(exs):
                    for s in range(len(e["sets"])):
                        seq.append((base + k, r * len(e["sets"]) + s))
        else:                                       # superset, aquecimento, retorno
            depth = max(len(e["sets"]) for e in exs)
            for s in range(depth):
                for k, e in enumerate(exs):
                    if s < len(e["sets"]):
                        seq.append((base + k, s))
        item += len(exs)
    return seq


def set_rest(struct: dict, item_idx: int, set_idx: int) -> int:
    """O descanso depois desta série: o da série; nos supersets e circuitos,
    só no fim da volta (o descanso do bloco)."""
    item = 0
    for b in struct["blocks"]:
        exs = b["exercises"]
        if item <= item_idx < item + len(exs):
            k = item_idx - item
            e = exs[k]
            s = e["sets"][set_idx % len(e["sets"])]
            own = s.get("rest")
            if b["kind"] in ("superset", "circuit", "warmup", "cooldown") and len(exs) > 1:
                last = k == len(exs) - 1
                return int(b.get("rest_s") or own or 60) if last else int(own or 0)
            return int(own if own is not None else 90)
        item += len(exs)
    return 90


def flat_items(struct: dict, e1rms: dict[int, float] | None = None) -> list[dict]:
    """A lista simples (um item por exercício), para gravar como sempre."""
    out = []
    for b in struct["blocks"]:
        for e in b["exercises"]:
            sets = e["sets"]
            first = sets[0] if sets else {}
            reps = first.get("reps") if "reps" in e["params"] else first.get("time")
            load = first.get("load")
            if load is None and first.get("pct1rm") and e1rms and e1rms.get(e["exercise_id"]):
                load = round(e1rms[e["exercise_id"]] * first["pct1rm"] / 100 / 2.5) * 2.5
            rpe = first.get("rpe")
            if rpe is None and first.get("rir") is not None:
                rpe = 10 - first["rir"]
            out.append({"exercise_id": e["exercise_id"], "name": e["name"],
                        "sets": len(sets) * rounds_of(b), "reps": int(reps or 10),
                        "load_kg": load, "rpe": rpe,
                        "rest_s": int(first.get("rest") if first.get("rest") is not None
                                      else (b.get("rest_s") or 90)),
                        "notes": e.get("notes") or None})
    return out


def set_targets(struct: dict, e1rms: dict[int, float] | None = None) -> list[list[dict]]:
    """Por exercício (pela ordem da lista simples), o alvo de cada série."""
    out = []
    for b in struct["blocks"]:
        for e in b["exercises"]:
            tg = []
            for _r in range(rounds_of(b)):
                for s in e["sets"]:
                    load = s.get("load")
                    if load is None and s.get("pct1rm") and e1rms and e1rms.get(e["exercise_id"]):
                        load = round(e1rms[e["exercise_id"]] * s["pct1rm"] / 100 / 2.5) * 2.5
                    rpe = s.get("rpe")
                    if rpe is None and s.get("rir") is not None:
                        rpe = 10 - s["rir"]
                    reps = s.get("reps") if "reps" in e["params"] else s.get("time")
                    tg.append({"reps": reps, "load_kg": load, "rpe": rpe,
                               "rest_s": s.get("rest"), "distance": s.get("distance")})
            out.append(tg)
    return out


def estimate_seconds(struct: dict) -> int:
    total = 0
    for b in struct["blocks"]:
        for e in b["exercises"]:
            for _r in range(rounds_of(b)):
                for s in e["sets"]:
                    total += int(s.get("time") or ((s.get("reps") or 10) * 3 + 10))
    seq = sequence(struct)
    for it_idx, s_idx in seq[:-1]:                 # não há descanso depois da última
        total += set_rest(struct, it_idx, s_idx)
    return total


def planned_volume(struct: dict, e1rms: dict[int, float] | None = None) -> float:
    vol = 0.0
    for tg_list in set_targets(struct, e1rms):
        for tg in tg_list:
            if tg.get("load_kg") and tg.get("reps"):
                vol += tg["load_kg"] * tg["reps"]
    return vol


def from_items(items: list) -> dict:
    """Estrutura a partir da lista simples (planos antigos): um bloco por
    exercício, as séries iguais."""
    s = empty()
    for it in items:
        g = (lambda k: it.get(k)) if isinstance(it, dict) else (lambda k: getattr(it, k, None))
        measure = g("measure") or "reps"
        params = ["time", "rest"] if measure == "time" else ["reps", "load", "rest"]
        if g("rpe"):
            params.insert(-1, "rpe")
        one = {p: None for p in params}
        if measure == "time":
            one["time"] = g("reps")
        else:
            one["reps"], one["load"] = g("reps"), g("load_kg")
        if "rpe" in params:
            one["rpe"] = g("rpe")
        one["rest"] = g("rest_s")
        s["blocks"].append(new_block("single", [{
            "exercise_id": int(g("exercise_id")), "name": g("name") or "",
            "notes": g("notes") or "", "params": params,
            "sets": [dict(one) for _ in range(int(g("sets") or 1))]}]))
    return s


# ================================================================ guardar


def ensure(db) -> None:
    db.conn.execute("CREATE TABLE IF NOT EXISTS strength_structures (workout_id TEXT PRIMARY KEY,"
                    " data TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    db.conn.commit()


def stored(db, wid: str | None) -> dict | None:
    if not wid:
        return None
    ensure(db)
    r = db.conn.execute("SELECT data FROM strength_structures WHERE workout_id = ?",
                        (wid,)).fetchone()
    if r is None:
        return None
    try:
        return normalize(json.loads(r[0]))
    except (ValueError, TypeError):
        return None


def load(db, wid: str | None) -> dict:
    """A estrutura do treino (ou uma feita da lista simples, se for antigo)."""
    got = stored(db, wid)
    if got is not None:
        return got
    if not wid:
        return empty()
    from . import strength as st
    s = from_items(st.workout_items(db, wid))
    wk = st.workout(db, wid) or {}
    s["instructions"] = wk.get("description") or ""
    return s


def e1rm_map(db) -> dict[int, float]:
    """A melhor 1RM estimada de cada exercício (para planear por % da 1RM)."""
    from . import strength as st
    out: dict[int, float] = {}
    for ex in st.exercises_with_history(db):
        prog = st.exercise_progress(db, ex["id"])
        best = [p["best_e1rm"] for p in prog[-6:] if p.get("best_e1rm")]
        if best:
            out[ex["id"]] = max(best)
    return out


def save(db, wid: str | None, name: str, struct: dict, modality: str = "strength",
         hidden: bool = False) -> str:
    from . import gym
    struct = normalize(struct)
    items = flat_items(struct, e1rm_map(db))
    if not items:
        raise ValueError(tr("O treino não tem exercícios.", "The workout has no exercises."))
    gym.ensure(db)
    wid = gym.save_plan(db, wid, name, struct.get("instructions") or None, items, modality,
                        hidden=hidden)
    ensure(db)
    db.conn.execute("INSERT INTO strength_structures (workout_id, data) VALUES (?,?)"
                    " ON CONFLICT(workout_id) DO UPDATE SET data=excluded.data,"
                    " updated_at=CURRENT_TIMESTAMP",
                    (wid, json.dumps(struct, ensure_ascii=False)))
    db.conn.commit()
    return wid


def clone(struct: dict) -> dict:
    return copy.deepcopy(struct)
