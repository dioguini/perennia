"""Picos (como os «Peak Performances» do TrainingPeaks): a melhor média de
cada métrica em cada duração — potência, FC, cadência e velocidade (o ritmo,
na corrida) — numa sessão e no histórico.

Os picos de cada sessão calculam-se uma vez a partir das amostras (1 Hz) e
ficam guardados em `ride_peaks`; o histórico é o melhor de todas.

Também aqui: o relatório de uma sessão de ciclismo para os infográficos —
médias e máximos, NP, IF, TSS, VI, EF, trabalho, tempo em cada zona e o
desacoplamento (decoupling) potência:FC entre a primeira e a segunda metade.
"""
from __future__ import annotations

from .db import Database

DURATIONS = (5, 10, 30, 60, 300, 600, 1200, 1800, 3600, 5400)
METRICS = ("power_w", "hr_bpm", "cadence_rpm", "speed_mps")
VERSION = 1


def duration_label(d: int) -> str:
    if d < 60:
        return f"{d} s"
    if d < 3600:
        return f"{d // 60} min"
    h, m = divmod(d // 60, 60)
    return f"{h} h" + (f" {m:02d}" if m else "")


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS ride_peaks (
      ride_id TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
      metric TEXT NOT NULL, duration_s INTEGER NOT NULL, value REAL NOT NULL,
      version INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (ride_id, metric, duration_s));
    """)
    db.conn.commit()


def series(db: Database, ride_id: str) -> dict[str, list[float | None]]:
    """As amostras da sessão, uma por segundo: {métrica: [valores]}."""
    rows = db.conn.execute(
        "SELECT t_s, power_w, hr_bpm, cadence_rpm, speed_mps FROM ride_samples"
        " WHERE ride_id = ? ORDER BY t_s", (ride_id,)).fetchall()
    out: dict[str, list] = {m: [] for m in METRICS}
    out["t_s"] = []
    for r in rows:
        out["t_s"].append(r["t_s"])
        for m in METRICS:
            out[m].append(r[m])
    return out


def _clean(values: list, hold: bool) -> list[float]:
    """Sem buracos: a FC mantém o último valor; o resto conta zero."""
    out, last = [], 0.0
    for v in values:
        if v is None:
            out.append(last if hold else 0.0)
        else:
            last = float(v)
            out.append(last)
    return out


def best_average(values: list[float], window: int) -> float | None:
    """A melhor média de `window` amostras seguidas (somas acumuladas)."""
    n = len(values)
    if window <= 0 or n < window:
        return None
    acc = sum(values[:window])
    best = acc
    for i in range(window, n):
        acc += values[i] - values[i - window]
        if acc > best:
            best = acc
    return best / window


def compute(s: dict[str, list]) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for m in METRICS:
        raw = s.get(m) or []
        if not any(v for v in raw if v):
            continue
        vals = _clean(raw, hold=(m == "hr_bpm"))
        peaks = {}
        for d in DURATIONS:
            b = best_average(vals, d)
            if b is not None and b > 0:
                peaks[d] = b
        if peaks:
            out[m] = peaks
    return out


def ride_peaks(db: Database, ride_id: str) -> dict[str, dict[int, float]]:
    """Os picos de uma sessão (calcula-os e guarda-os da primeira vez)."""
    ensure(db)
    rows = db.conn.execute("SELECT metric, duration_s, value FROM ride_peaks"
                           " WHERE ride_id = ? AND version = ?", (ride_id, VERSION)).fetchall()
    if rows:
        out: dict[str, dict[int, float]] = {}
        for r in rows:
            if r["duration_s"] >= 0:
                out.setdefault(r["metric"], {})[r["duration_s"]] = r["value"]
        return out
    peaks = compute(series(db, ride_id))
    db.conn.execute("DELETE FROM ride_peaks WHERE ride_id = ?", (ride_id,))
    data = [(ride_id, m, d, v, VERSION) for m, ps in peaks.items() for d, v in ps.items()]
    # uma marca para não voltar a calcular sessões sem amostras
    data.append((ride_id, "_done", -1, 0.0, VERSION))
    db.conn.executemany("INSERT OR REPLACE INTO ride_peaks(ride_id, metric, duration_s, value,"
                        " version) VALUES (?,?,?,?,?)", data)
    db.conn.commit()
    return peaks


def all_peaks(db: Database, since: str | None = None) -> dict[str, dict[int, dict]]:
    """O melhor de cada métrica e duração no histórico (ou desde `since`):
    {métrica: {duração: {"value", "ride_id", "date", "name"}}}."""
    ensure(db)
    sql = "SELECT id, started_at, name FROM rides WHERE status = 'completed'"
    args: list = []
    if since:
        sql += " AND started_at >= ?"
        args.append(since)
    rides = db.conn.execute(sql, args).fetchall()
    best: dict[str, dict[int, dict]] = {}
    for r in rides:
        for m, ps in ride_peaks(db, r["id"]).items():
            for d, v in ps.items():
                cur = best.setdefault(m, {}).get(d)
                if cur is None or v > cur["value"]:
                    best[m][d] = {"value": v, "ride_id": r["id"],
                                  "date": str(r["started_at"])[:10], "name": r["name"] or ""}
    return best


def fmt(metric: str, v: float | None, units: str = "metric") -> str:
    if v is None:
        return "—"
    if metric == "power_w":
        return f"{v:.0f} W"
    if metric == "hr_bpm":
        return f"{v:.0f} bpm"
    if metric == "cadence_rpm":
        return f"{v:.0f} rpm"
    if metric == "speed_mps":
        if units == "imperial":
            return f"{v * 2.236936:.1f} mph"
        return f"{v * 3.6:.1f} km/h"
    return f"{v:.0f}"


# ------------------------------------------------------------- relatório


def _np(power: list[float]) -> float | None:
    """Potência normalizada: média móvel de 30 s, à quarta, média, raiz quarta."""
    if len(power) < 30:
        return None
    acc = sum(power[:30])
    rolled = [acc / 30]
    for i in range(30, len(power)):
        acc += power[i] - power[i - 30]
        rolled.append(acc / 30)
    return (sum(x ** 4 for x in rolled) / len(rolled)) ** 0.25


def _zone(v: float, bounds: list, ref: float) -> int:
    z = 0
    for b in bounds:
        if v > b / 100 * ref:
            z += 1
    return z


def report(db: Database, ride_id: str) -> dict:
    """Tudo o que os infográficos mostram de uma sessão de ciclismo."""
    r = db.conn.execute("SELECT * FROM rides WHERE id = ?", (ride_id,)).fetchone()
    if r is None:
        return {}
    s = series(db, ride_id)
    p = _clean(s["power_w"], False)
    hr = _clean(s["hr_bpm"], True)
    cad = _clean(s["cadence_rpm"], False)
    spd = _clean(s["speed_mps"], False)
    ftp = float(r["ftp_at_ride_w"] or db.athlete().ftp_w or 200)
    n = len(p)
    out: dict = {"ride_id": ride_id, "name": r["name"] or "", "started_at": r["started_at"],
                 "seconds": n, "ftp": ftp, "series": {"power_w": p, "hr_bpm": hr,
                                                     "cadence_rpm": cad, "speed_mps": spd}}
    moving = [x for x in p if x > 0]
    out["avg_power"] = sum(p) / n if n else None
    out["avg_power_moving"] = sum(moving) / len(moving) if moving else None
    out["max_power"] = max(p) if p else None
    np_ = _np(p)
    out["np"] = np_
    out["if"] = np_ / ftp if np_ else None
    out["tss"] = (n * np_ * (np_ / ftp)) / (ftp * 3600) * 100 if np_ else None
    out["vi"] = np_ / out["avg_power"] if np_ and out["avg_power"] else None
    hrs = [x for x in hr if x > 0]
    out["avg_hr"] = sum(hrs) / len(hrs) if hrs else None
    out["max_hr"] = max(hrs) if hrs else None
    cads = [x for x in cad if x > 0]
    out["avg_cadence"] = sum(cads) / len(cads) if cads else None
    out["max_cadence"] = max(cads) if cads else None
    out["avg_speed"] = sum(spd) / n if n else None
    out["max_speed"] = max(spd) if spd else None
    out["work_kj"] = sum(p) / 1000.0
    out["ef"] = np_ / out["avg_hr"] if np_ and out["avg_hr"] else None
    # desacoplamento: (potência/FC) da 1.ª metade face à 2.ª
    out["decoupling"] = None
    if n >= 600 and hrs:
        half = n // 2

        def ratio(a, b):
            pp = [x for x in p[a:b]]
            hh = [x for x in hr[a:b] if x > 0]
            if not hh or not pp:
                return None
            return (sum(pp) / len(pp)) / (sum(hh) / len(hh))
        r1, r2 = ratio(0, half), ratio(half, n)
        if r1 and r2:
            out["decoupling"] = (r1 - r2) / r1 * 100.0
            out["ef_halves"] = (r1, r2)
    # tempo em zona
    p_bounds = db.get("power_zones_pct", [55, 75, 90, 105, 120, 150])
    h_bounds = db.get("hr_zones_pct_lthr", [68, 83, 94, 105])
    from .ride import estimate_lthr
    lthr = estimate_lthr(db.athlete())
    pz = [0.0] * (len(p_bounds) + 1)
    for x in p:
        pz[_zone(x, p_bounds, ftp)] += 1.0
    hz = [0.0] * (len(h_bounds) + 1)
    if lthr:
        for x in hrs:
            hz[_zone(x, h_bounds, lthr)] += 1.0
    out["power_zones"], out["hr_zones"] = pz, hz
    out["peaks"] = ride_peaks(db, ride_id)
    # curva de potência da sessão (melhor média por duração, até ao comprimento)
    curve_d = [d for d in (1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600, 5400, 7200)
               if d <= n]
    out["curve"] = [(d, best_average(p, d) or 0.0) for d in curve_d]
    return out
