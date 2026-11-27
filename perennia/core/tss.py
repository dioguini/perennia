"""A carga de cada sessão como o TrainingPeaks a calcula.

* Ciclismo e remo (potência): TSS = h · IF² · 100, com IF = NP / FTP
  (NP de Coggan: média móvel de 30 s, à 4.ª potência).
* Corrida: rTSS = h · IF² · 100, com IF = NGS / velocidade de limiar — o NGS
  (normalized graded speed, o inverso do NGP) calcula-se como o NP: média
  móvel de 30 s da velocidade ajustada à inclinação, à 4.ª potência. Na
  passadeira, sem inclinação gravada, a inclinação conta como 0.
* Natação: sTSS = h · IF³ · 100, com IF = velocidade média / velocidade
  crítica (CSS) — ao cubo, como no TrainingPeaks.
* Sem os dados de que a fórmula precisa, não há carga: não se substitui pela FC nem pelo
  ritmo médio (ronda 37). O ginásio (força) tem a sua própria carga (FC ou RPE da sessão).
* Atividades importadas: a TSS que vem no ficheiro; senão, a do .fit (potência → TSS,
  ritmo → rTSS) ou da distância (natação → sTSS), pelo teu FTP / ritmo de limiar / CSS.
"""
from __future__ import annotations


def normalized(values: list[float], window: int = 30) -> float | None:
    """Média móvel de `window` amostras, à 4.ª potência, média e raiz quarta."""
    vals = [float(v or 0.0) for v in values]
    if len(vals) < window:
        return (sum(v ** 4 for v in vals) / len(vals)) ** 0.25 if vals else None
    acc = sum(vals[:window])
    rolling = [acc / window]
    for i in range(window, len(vals)):
        acc += vals[i] - vals[i - window]
        rolling.append(acc / window)
    return (sum(r ** 4 for r in rolling) / len(rolling)) ** 0.25


def grade_factor(grade_pct: float) -> float:
    """Quanto custa correr a esta inclinação, face ao plano (Minetti, 2002)."""
    g = max(-0.45, min(0.45, grade_pct / 100.0))
    cost = 155.4 * g ** 5 - 30.4 * g ** 4 - 43.3 * g ** 3 + 46.3 * g ** 2 + 19.5 * g + 3.6
    return max(0.3, cost / 3.6)


def rtss(speeds_mps: list[float], seconds: float, threshold_mps: float,
         grades: list[float] | None = None) -> float | None:
    if not speeds_mps or seconds <= 0 or threshold_mps <= 0:
        return None
    adj = speeds_mps if not grades else [v * grade_factor(g) for v, g in
                                         zip(speeds_mps, grades)]
    ngs = normalized(adj)
    if not ngs:
        return None
    if_ = ngs / threshold_mps
    return seconds / 3600.0 * if_ * if_ * 100.0


def stss(distance_m: float, seconds: float, css_s_per_100: float) -> float | None:
    if not distance_m or seconds <= 0 or css_s_per_100 <= 0:
        return None
    if_ = (distance_m / seconds) / (100.0 / css_s_per_100)
    return seconds / 3600.0 * if_ ** 3 * 100.0


def recompute_endurance(db) -> int:
    """Volta a calcular a carga das corridas e das natações já gravadas com as
    fórmulas do TrainingPeaks (uma vez, ao atualizar)."""
    from . import endurance as en
    from . import intensity as it
    en.ensure(db)
    n = 0
    run_ctx = it.Context.from_db(db, "running")
    swim_ctx = it.Context.from_db(db, "swimming")
    for r in db.conn.execute("SELECT id, sport, moving_s, distance_m FROM endurance_sessions"
                             " WHERE status = 'completed'").fetchall():
        secs = float(r["moving_s"] or 0)
        load = None
        if r["sport"] == "running":
            speeds = [x[0] or 0.0 for x in db.conn.execute(
                "SELECT speed_mps FROM endurance_samples WHERE session_id = ? ORDER BY t_s",
                (r["id"],))]
            if len(speeds) >= 30:
                load = rtss(speeds, secs, 1000.0 / run_ctx.run_pace_s)
        elif r["sport"] == "swimming":
            load = stss(float(r["distance_m"] or 0), secs, swim_ctx.swim_css_s)
        if load is not None:
            db.conn.execute("UPDATE endurance_sessions SET load = ?, load_source = ? WHERE id = ?",
                            (load, "rtss" if r["sport"] == "running" else "stss", r["id"]))
            n += 1
    db.conn.commit()
    return n


def for_imported(db, sport: str, seconds: float, *, np_w: float | None = None,
                 speeds: list | None = None, grades: list | None = None,
                 distance_m: float | None = None) -> tuple[float | None, float | None, str | None]:
    """(TSS, IF, fonte) de uma atividade importada, com as fórmulas do TrainingPeaks e os teus
    limiares. Sem os dados de que a fórmula do desporto precisa, (None, None, None)."""
    from . import intensity as it
    if seconds <= 0:
        return None, None, None
    if sport in ("cycling", "rowing") and np_w:
        try:
            ftp = float(db.athlete().ftp_w or 0)
        except Exception:
            ftp = 0.0
        if ftp > 0:
            if_ = np_w / ftp
            return seconds / 3600.0 * if_ * if_ * 100.0, if_, "power"
        return None, None, None
    if sport == "running" and speeds and len(speeds) >= 30:
        ctx = it.Context.from_db(db, "running")
        if ctx.run_pace_s:
            thr = 1000.0 / ctx.run_pace_s
            load = rtss(speeds, seconds, thr, grades)
            if load is not None:
                ngs = normalized([v * grade_factor(g) for v, g in zip(speeds, grades)]
                                 if grades else speeds)
                return load, (ngs / thr if ngs else None), "rtss"
        return None, None, None
    if sport == "swimming" and distance_m:
        ctx = it.Context.from_db(db, "swimming")
        if ctx.swim_css_s:
            load = stss(distance_m, seconds, ctx.swim_css_s)
            if load is not None:
                return load, (distance_m / seconds) / (100.0 / ctx.swim_css_s), "stss"
    return None, None, None


def clear_substitutes(db) -> int:
    """Tira a carga que tinha sido calculada por substituição (pela FC ou pelo ritmo médio) às
    corridas, natações e remadas — como o TrainingPeaks, sem os dados não há carga."""
    n = 0
    for table in ("endurance_sessions", "row_sessions"):
        try:
            cur = db.conn.execute(f"UPDATE {table} SET load = NULL, load_source = NULL"
                                  " WHERE load_source IN ('hr', 'pace')")
            n += cur.rowcount or 0
        except Exception:
            continue
    db.conn.commit()
    return n
