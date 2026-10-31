"""Análise pós-treino da força e o histórico de cada exercício.

**Análise de uma sessão** (como a do TrainingPeaks): para cada exercício, o
cumprimento (feito ÷ prescrito, pelo volume quando há carga, senão pelas
repetições), as repetições, o volume e a 1RM estimada, com a diferença para
a sessão anterior desse exercício; e, série a série, o prescrito ao lado do
feito (repetições, carga, RPE, quanto tempo durou, FC).

**Histórico de um exercício**: por sessão, a carga máxima e média, a melhor
1RM estimada, o volume, as repetições, o RPE médio e o tempo que demorou
(do início da 1.ª série ao fim da última, e o tempo em série).
"""
from __future__ import annotations

from . import strength as st
from . import strength_builder as sb
from .i18n import tr

GREEN, YELLOW, RED = "good", "warn", "bad"


def compliance_tone(c: float | None) -> str:
    """Cores do cumprimento, como no TrainingPeaks: verde perto do prescrito,
    amarelo um pouco fora, vermelho muito fora."""
    if c is None:
        return ""
    if 0.8 <= c <= 1.2:
        return GREEN
    if 0.5 <= c <= 1.5:
        return YELLOW
    return RED


def _planned(db, workout_id: str | None, items: list) -> tuple[list[list[dict]], list[str]]:
    """Por exercício, a lista das séries prescritas, e os rótulos A1, B1…"""
    struct = sb.stored(db, workout_id) if workout_id else None
    if struct is not None:
        tg = sb.set_targets(struct, sb.e1rm_map(db))
        labels = [sb.label(bi, ei, b) for bi, b in enumerate(struct["blocks"])
                  for ei in range(len(b["exercises"]))]
        if len(tg) == len(items):
            return tg, labels
    out, labels = [], []
    for i, it in enumerate(items):
        out.append([{"reps": it.reps, "load_kg": it.load_kg, "rpe": it.rpe}
                    for _ in range(it.sets)])
        labels.append(sb.letter(i))
    return out, labels


def session(db, session_id: str) -> dict | None:
    r = db.conn.execute("SELECT * FROM strength_sessions WHERE id = ?", (session_id,)).fetchone()
    if r is None:
        return None
    s = dict(r)
    sets = st.session_sets(db, session_id)
    items = st.workout_items(db, s["workout_id"]) if s.get("workout_id") else []
    plan, labels = _planned(db, s.get("workout_id"), items)
    body = s.get("weight_at_session_kg") or db.athlete().weight_kg
    ex_rows: list[dict] = []
    by_item: dict[int, list[dict]] = {}
    for x in sets:
        by_item.setdefault(x["item_idx"] if x["item_idx"] is not None else -1, []).append(x)
    indices = list(range(len(items))) + sorted(k for k in by_item if k >= len(items) or k < 0)
    for idx in indices:
        done = by_item.get(idx, [])
        it = items[idx] if 0 <= idx < len(items) else None
        planned = plan[idx] if 0 <= idx < len(plan) else []
        if not done and not planned:
            continue
        ex_id = it.exercise_id if it else done[0]["exercise_id"]
        ex = st.exercise(db, ex_id) or {"bodyweight": 0.0, "measure": "reps",
                                        "name": done[0]["name"] if done else "?"}
        bw = ex.get("bodyweight") or 0.0
        measure = ex.get("measure") or "reps"
        name = it.name if it else ex.get("name", "?")
        # uma célula vazia no plano vale o que o exercício pede (como na sessão)
        base_reps = it.reps if it else None
        planned = [dict(p, reps=p.get("reps") or base_reps) for p in planned]
        p_vol = sum((p.get("load_kg") or 0) * (p.get("reps") or 0) for p in planned
                    if measure == "reps")
        d_vol = sum(st.set_volume(x["load_kg"], x["reps"], bw, body, measure) for x in done)
        d_vol_ext = sum((x["load_kg"] or 0) * x["reps"] for x in done) if measure == "reps" else 0
        # nos exercícios por tempo, «reps» são segundos: compara-se o tempo
        p_reps = sum(p.get("reps") or 0 for p in planned)
        d_reps = sum(x["reps"] for x in done)
        if p_vol > 0:
            comp = d_vol_ext / p_vol
        elif p_reps > 0:
            comp = d_reps / p_reps
        elif planned:
            comp = len(done) / len(planned)
        else:
            comp = None
        best = None
        for x in done:
            if measure == "reps":
                est = st.e1rm((x["load_kg"] or 0) + bw * body, x["reps"], x["rpe"])
                if est and (best is None or est > best):
                    best = est
        prev = previous_best(db, ex_id, s["started_at"])
        rows = []
        for k in range(max(len(done), len(planned))):
            p = planned[k] if k < len(planned) else {}
            d = done[k] if k < len(done) else None
            rows.append({"set_no": k + 1, "plan_reps": p.get("reps"), "plan_load": p.get("load_kg"),
                         "plan_rpe": p.get("rpe"),
                         "reps": d["reps"] if d else None, "load": d["load_kg"] if d else None,
                         "rpe": d["rpe"] if d else None,
                         "dur_s": (d["end_t_s"] - d["start_t_s"]) if d and d["end_t_s"] is not None
                         and d["start_t_s"] is not None else None,
                         "avg_hr": d["avg_hr"] if d else None})
        span = None
        if done and done[0]["start_t_s"] is not None and done[-1]["end_t_s"] is not None:
            span = done[-1]["end_t_s"] - done[0]["start_t_s"]
        ex_rows.append({
            "label": labels[idx] if 0 <= idx < len(labels) else "+", "item_idx": idx,
            "exercise_id": ex_id, "name": name, "measure": measure,
            "planned_sets": len(planned), "done_sets": len(done),
            "planned_reps": p_reps, "done_reps": d_reps,
            "planned_volume": p_vol, "volume": d_vol,
            "max_load": max((x["load_kg"] or 0 for x in done), default=0) or None,
            "avg_rpe": (sum(x["rpe"] for x in done if x["rpe"]) /
                        max(1, sum(1 for x in done if x["rpe"]))) if any(x["rpe"] for x in done)
            else None,
            "best_e1rm": best, "prev_e1rm": prev, "compliance": comp,
            "tone": compliance_tone(comp), "time_s": span,
            "work_s": sum(r["dur_s"] or 0 for r in rows), "sets": rows})
    p_vol = sum(e["planned_volume"] for e in ex_rows)
    d_vol = sum((e["volume"] if e["measure"] == "reps" else 0) for e in ex_rows)
    weights = [(e["planned_volume"] or e["planned_reps"] or e["planned_sets"] or 1,
                e["compliance"]) for e in ex_rows if e["compliance"] is not None]
    total_c = (sum(w * min(c, 1.5) for w, c in weights) / sum(w for w, _ in weights)) \
        if weights else None
    return {"id": session_id, "name": s.get("name") or "", "started_at": s["started_at"],
            "workout_id": s.get("workout_id"), "elapsed_s": s.get("elapsed_s") or 0,
            "avg_hr": s.get("avg_hr"), "max_hr": s.get("max_hr"), "load": s.get("load"),
            "avg_rpe": s.get("avg_rpe"),
            "planned_sets": sum(e["planned_sets"] for e in ex_rows),
            "done_sets": sum(e["done_sets"] for e in ex_rows),
            "planned_reps": sum(e["planned_reps"] for e in ex_rows if e["measure"] == "reps"),
            "done_reps": sum(e["done_reps"] for e in ex_rows if e["measure"] == "reps"),
            "planned_volume": p_vol, "volume": d_vol, "compliance": total_c,
            "tone": compliance_tone(total_c),
            "work_s": sum(e["work_s"] for e in ex_rows), "exercises": ex_rows}


def previous_best(db, exercise_id: int, before: str) -> float | None:
    """A melhor 1RM estimada desse exercício na sessão anterior a `before`."""
    hist = [h for h in history(db, exercise_id) if h["started_at"] < before]
    for h in reversed(hist):
        if h["best_e1rm"]:
            return h["best_e1rm"]
    return None


def history(db, exercise_id: int) -> list[dict]:
    """Por sessão (da mais antiga à mais recente): data, séries, carga máxima e
    média, 1RM estimada, volume, repetições, RPE médio, tempo no exercício e
    tempo em série."""
    ex = st.exercise(db, exercise_id) or {"bodyweight": 0.0, "measure": "reps"}
    rows = db.conn.execute(
        "SELECT s.*, ss.started_at, ss.weight_at_session_kg AS body, ss.name AS sname"
        " FROM strength_sets s JOIN strength_sessions ss ON ss.id = s.session_id"
        " WHERE ss.status = 'completed' AND s.exercise_id = ? ORDER BY ss.started_at, s.id",
        (exercise_id,)).fetchall()
    out: dict[str, dict] = {}
    order: list[str] = []
    bw = ex.get("bodyweight") or 0.0
    measure = ex.get("measure") or "reps"
    for r in rows:
        sid = r["session_id"]
        if sid not in out:
            out[sid] = {"session_id": sid, "started_at": r["started_at"],
                        "date": str(r["started_at"])[:10], "name": r["sname"] or "",
                        "sets": [], "volume": 0.0, "reps": 0, "max_load": None,
                        "best_e1rm": None, "_rpe": [], "_first": None, "_last": None,
                        "work_s": 0}
            order.append(sid)
        o = out[sid]
        o["sets"].append((r["reps"], r["load_kg"], r["rpe"]))
        o["reps"] += r["reps"]
        o["volume"] += st.set_volume(r["load_kg"], r["reps"], bw, r["body"] or 0.0, measure)
        if r["load_kg"] is not None:
            o["max_load"] = max(o["max_load"] or 0.0, r["load_kg"])
        if r["rpe"]:
            o["_rpe"].append(r["rpe"])
        if measure == "reps":
            est = st.e1rm((r["load_kg"] or 0.0) + bw * (r["body"] or 0.0), r["reps"], r["rpe"])
            if est and (o["best_e1rm"] is None or est > o["best_e1rm"]):
                o["best_e1rm"] = est
        if r["start_t_s"] is not None:
            o["_first"] = r["start_t_s"] if o["_first"] is None else min(o["_first"],
                                                                        r["start_t_s"])
        if r["end_t_s"] is not None:
            o["_last"] = r["end_t_s"] if o["_last"] is None else max(o["_last"], r["end_t_s"])
            if r["start_t_s"] is not None:
                o["work_s"] += max(0, r["end_t_s"] - r["start_t_s"])
    res = []
    for sid in order:
        o = out[sid]
        loads = [ld for _r, ld, _p in o["sets"] if ld]
        o["avg_load"] = sum(loads) / len(loads) if loads else None
        o["avg_rpe"] = sum(o["_rpe"]) / len(o["_rpe"]) if o["_rpe"] else None
        o["time_s"] = (o["_last"] - o["_first"]) if o["_first"] is not None and \
            o["_last"] is not None else None
        o["n_sets"] = len(o["sets"])
        for k in ("_rpe", "_first", "_last"):
            o.pop(k)
        res.append(o)
    return res


METRICS = ("max_load", "avg_load", "best_e1rm", "volume", "avg_rpe", "time_s", "reps")


def metric_name(m: str) -> str:
    return {"max_load": tr("Carga máxima", "Top load"), "avg_load": tr("Carga média", "Avg load"),
            "best_e1rm": tr("1RM estimada", "Estimated 1RM"), "volume": tr("Volume", "Volume"),
            "avg_rpe": tr("RPE médio", "Avg RPE"),
            "time_s": tr("Tempo no exercício", "Time on exercise"),
            "reps": tr("Repetições", "Reps")}[m]


def metric_unit(m: str) -> str:
    return {"max_load": "kg", "avg_load": "kg", "best_e1rm": "kg", "volume": "kg",
            "avg_rpe": "", "time_s": "min", "reps": ""}[m]


def series(hist: list[dict], metric: str) -> list[tuple[str, float]]:
    out = []
    for h in hist:
        v = h.get(metric)
        if v is None:
            continue
        if metric == "time_s":
            v = v / 60.0
        out.append((h["date"], float(v)))
    return out


def trend(values: list[float]) -> float | None:
    """Variação entre a média das 3 primeiras e das 3 últimas sessões (%)."""
    if len(values) < 2:
        return None
    k = min(3, len(values) // 2)              # as primeiras e as últimas não se sobrepõem
    a = sum(values[:k]) / k
    b = sum(values[-k:]) / k
    return (b - a) / a * 100 if a else None
