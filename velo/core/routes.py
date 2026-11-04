"""As rotas (.gpx) da Perennia, para todos os desportos.

O menu **Rotas** (ecrã inicial) é o único sítio onde se carregam ficheiros
.gpx; o ciclismo e a corrida escolhem só entre as rotas que já existem. Aqui
estão as contas que o menu mostra: o perfil de altimetria, quantas vezes
cada rota já foi feita (no ciclismo e na corrida) e as sessões feitas nela.
"""
from __future__ import annotations

from .db import Database


def times_done(db: Database, route_id: str) -> dict:
    """{"cycling": n, "running": n, "total": n} — sessões terminadas na rota."""
    from . import endurance as en
    en.ensure(db)
    ride = db.conn.execute("SELECT COUNT(*) FROM rides WHERE route_id = ? AND"
                           " status = 'completed'", (route_id,)).fetchone()[0]
    run = db.conn.execute("SELECT COUNT(*) FROM endurance_sessions WHERE route_id = ? AND"
                          " status = 'completed'", (route_id,)).fetchone()[0]
    return {"cycling": int(ride), "running": int(run), "total": int(ride) + int(run)}


def times_text(n: dict) -> str:
    from .i18n import tr
    if not n["total"]:
        return tr("ainda não feita", "not done yet")
    bits = []
    if n["cycling"]:
        bits.append(tr("{n}× ciclismo", "{n}× cycling", n=n["cycling"]))
    if n["running"]:
        bits.append(tr("{n}× corrida", "{n}× running", n=n["running"]))
    return tr("feita {n}×", "done {n}×", n=n["total"]) + " (" + " · ".join(bits) + ")"


def profile(db: Database, route_id: str, n: int = 160) -> list[tuple[float, float, float]]:
    """(distância m, altitude m, inclinação %) em `n` pontos ao longo da rota."""
    pts = db.route_points(route_id)
    if not pts:
        return []
    total = pts[-1].dist_m or 1.0
    out = []
    j = 0
    for k in range(n):
        d = total * k / (n - 1)
        while j < len(pts) - 1 and pts[j + 1].dist_m < d:
            j += 1
        p = pts[j]
        q = pts[min(j + 1, len(pts) - 1)]
        span = max(1e-6, q.dist_m - p.dist_m)
        f = max(0.0, min(1.0, (d - p.dist_m) / span))
        out.append((d, p.ele_m + (q.ele_m - p.ele_m) * f, q.grade_pct if f > 0.5 else p.grade_pct))
    return out


def sessions(db: Database, route_id: str, limit: int = 30) -> list[dict]:
    """As sessões feitas na rota (as mais recentes primeiro)."""
    from . import endurance as en
    en.ensure(db)
    rows = [dict(r) | {"kind": "ride", "sport": "cycling"} for r in db.conn.execute(
        "SELECT id, name, started_at, elapsed_s, moving_s, distance_m, avg_power_w, avg_hr"
        " FROM rides WHERE route_id = ? AND status = 'completed'", (route_id,))]
    rows += [dict(r) | {"kind": "endurance", "sport": "running", "avg_power_w": None}
             for r in db.conn.execute(
                 "SELECT id, name, started_at, elapsed_s, moving_s, distance_m, avg_hr"
                 " FROM endurance_sessions WHERE route_id = ? AND status = 'completed'",
                 (route_id,))]
    rows.sort(key=lambda r: r["started_at"] or "", reverse=True)
    return rows[:limit]
