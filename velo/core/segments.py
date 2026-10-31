"""Segmentos do Strava numa rota da Perennia.

Busca os segmentos que cruzam a rota (em janelas de ~3 km ao longo dela),
encontra o início e o fim de cada um no percurso, e guarda-os com o teu
recorde pessoal. Durante o passeio o `SegmentTracker` diz quando entras num
segmento e compara o teu tempo com o PR ao mesmo ponto (como se o PR
seguisse a um ritmo constante), e no fim regista o teu tempo na Perennia.

Nota: um passeio no rolo não conta para o Strava; a comparação é contigo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .boards import Board, Row
from .db import Database, now_iso
from .i18n import t
from .units import delta, hms

MATCH_RADIUS_M = 45.0
TILE_M = 3000.0
MAX_TILES = 30
MAX_DETAILS = 40


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS strava_segments (
      route_id     TEXT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
      segment_id   INTEGER NOT NULL,
      name         TEXT NOT NULL,
      distance_m   REAL,
      avg_grade    REAL,
      climb_cat    INTEGER,
      start_m      REAL NOT NULL,
      end_m        REAL NOT NULL,
      pr_s         INTEGER,
      pr_date      TEXT,
      effort_count INTEGER,
      kom          TEXT,
      fetched_at   TEXT NOT NULL,
      PRIMARY KEY (route_id, segment_id)
    ) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS strava_efforts (
      id         INTEGER PRIMARY KEY,
      ride_id    TEXT REFERENCES rides(id) ON DELETE CASCADE,
      segment_id INTEGER NOT NULL,
      elapsed_s  INTEGER NOT NULL,
      created_at TEXT NOT NULL
    );
    """)


@dataclass
class Segment:
    id: int
    name: str
    start_m: float
    end_m: float
    distance_m: float | None = None
    avg_grade: float | None = None
    pr_s: int | None = None
    pr_date: str | None = None
    effort_count: int | None = None
    kom: str | None = None
    local_best_s: int | None = None

    @property
    def length_m(self) -> float:
        return max(1.0, self.end_m - self.start_m)


# ------------------------------------------------------------------ geometria


def _m(lat1, lon1, lat2, lon2) -> float:
    """Distância aproximada em metros (equiretangular; chega para 50 m)."""
    k = math.cos(math.radians((lat1 + lat2) / 2))
    dx = (lon2 - lon1) * 111320.0 * k
    dy = (lat2 - lat1) * 110540.0
    return math.hypot(dx, dy)


def nearest(points: Sequence, lat: float, lon: float, after_m: float = -1.0
            ) -> tuple[float, float] | None:
    """(distância na rota, afastamento em m) do ponto da rota mais perto."""
    best = None
    for p in points:
        if p.dist_m <= after_m:
            continue
        d = _m(p.lat, p.lon, lat, lon)
        if best is None or d < best[1]:
            best = (p.dist_m, d)
    return best


def tiles(points: Sequence, size_m: float = TILE_M) -> list[tuple[float, float, float, float]]:
    """Janelas (sw_lat, sw_lng, ne_lat, ne_lng) ao longo da rota."""
    out = []
    chunk: list = []
    start = points[0].dist_m if points else 0.0
    for p in points:
        chunk.append(p)
        if p.dist_m - start >= size_m:
            out.append(chunk)
            chunk = [p]
            start = p.dist_m
    if len(chunk) > 1:
        out.append(chunk)
    boxes = []
    for c in out:
        lats = [p.lat for p in c]
        lons = [p.lon for p in c]
        pad = 0.002
        boxes.append((min(lats) - pad, min(lons) - pad, max(lats) + pad, max(lons) + pad))
    return boxes[:MAX_TILES]


def match(points: Sequence, seg: dict) -> tuple[float, float] | None:
    """Início e fim do segmento na rota, se a rota o percorre no mesmo sentido."""
    s, e = seg.get("start_latlng"), seg.get("end_latlng")
    if not s or not e:
        return None
    a = nearest(points, s[0], s[1])
    if a is None or a[1] > MATCH_RADIUS_M:
        return None
    b = nearest(points, e[0], e[1], after_m=a[0])
    if b is None or b[1] > MATCH_RADIUS_M:
        return None
    length = b[0] - a[0]
    dist = seg.get("distance") or length
    if length <= 0 or not (0.75 * dist <= length <= 1.3 * dist):
        return None
    return a[0], b[0]


# ---------------------------------------------------------------- busca


def fetch_for_route(db: Database, client, route_id: str, progress=None) -> dict:
    """Vai ao Strava buscar os segmentos da rota e os teus PR; guarda-os."""
    ensure(db)
    points = db.route_points(route_id)
    if not points:
        raise ValueError("rota sem pontos")
    found: dict[int, dict] = {}
    boxes = tiles(points)
    for i, box in enumerate(boxes):
        for seg in client.explore(box):
            found.setdefault(int(seg["id"]), seg)
        if progress:
            progress(i + 1, len(boxes))
    matched = []
    for sid, seg in found.items():
        where = match(points, seg)
        if where:
            matched.append((sid, seg, where))
    matched.sort(key=lambda x: x[2][0])
    db.conn.execute("DELETE FROM strava_segments WHERE route_id = ?", (route_id,))
    details = 0
    for sid, seg, (a, b) in matched:
        pr_s = pr_date = count = kom = None
        if details < MAX_DETAILS:
            try:
                det = client.segment(sid)
                details += 1
                stats = det.get("athlete_segment_stats") or {}
                pr_s = stats.get("pr_elapsed_time")
                pr_date = (stats.get("pr_date") or "")[:10] or None
                count = stats.get("effort_count")
                kom = (det.get("xoms") or {}).get("kom")
            except Exception:
                pass
        db.conn.execute(
            "INSERT OR REPLACE INTO strava_segments(route_id, segment_id, name, distance_m,"
            " avg_grade, climb_cat, start_m, end_m, pr_s, pr_date, effort_count, kom, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (route_id, sid, seg.get("name") or str(sid), seg.get("distance"),
             seg.get("avg_grade"), seg.get("climb_category"), a, b, pr_s, pr_date, count, kom,
             now_iso()))
    db.conn.commit()
    return {"explored": len(found), "matched": len(matched), "tiles": len(boxes)}


def load(db: Database, route_id: str | None) -> list[Segment]:
    ensure(db)
    if not route_id:
        return []
    rows = db.conn.execute(
        "SELECT s.*, (SELECT MIN(elapsed_s) FROM strava_efforts e WHERE e.segment_id ="
        " s.segment_id) AS best FROM strava_segments s WHERE route_id = ? ORDER BY start_m",
        (route_id,)).fetchall()
    return [Segment(r["segment_id"], r["name"], r["start_m"], r["end_m"], r["distance_m"],
                    r["avg_grade"], r["pr_s"], r["pr_date"], r["effort_count"], r["kom"],
                    r["best"]) for r in rows]


def save_effort(db: Database, ride_id: str | None, segment_id: int, elapsed_s: int) -> None:
    ensure(db)
    db.conn.execute("INSERT INTO strava_efforts(ride_id, segment_id, elapsed_s, created_at)"
                    " VALUES (?,?,?,?)", (ride_id, segment_id, int(elapsed_s), now_iso()))
    db.conn.commit()


# --------------------------------------------------------------- ao vivo


class SegmentTracker:
    def __init__(self, segments: Sequence[Segment]):
        self.segments = list(segments)
        self.active: list[tuple[Segment, float]] = []     # (segmento, início em s)
        self.done: set[int] = set()

    def reset(self) -> None:
        """Nova volta à rota: os segmentos voltam a contar."""
        self.active = []
        self.done = set()

    def observe(self, pos_m: float, t_s: float) -> list[tuple[str, dict]]:
        ev = []
        for seg in self.segments:
            if seg.id in self.done or any(s.id == seg.id for s, _ in self.active):
                continue
            if seg.start_m <= pos_m < seg.start_m + 30 and pos_m < seg.end_m:
                self.active.append((seg, t_s))
                ev.append(("strava_start", {"name": seg.name, "pr_s": seg.pr_s,
                                            "distance_m": seg.length_m,
                                            "grade": seg.avg_grade}))
        still = []
        for seg, t0 in self.active:
            if pos_m >= seg.end_m:
                elapsed = t_s - t0
                self.done.add(seg.id)
                ev.append(("strava_end", {"id": seg.id, "name": seg.name,
                                          "elapsed_s": elapsed, "pr_s": seg.pr_s,
                                          "local_best_s": seg.local_best_s}))
                if seg.local_best_s is None or elapsed < seg.local_best_s:
                    seg.local_best_s = int(elapsed)
            else:
                still.append((seg, t0))
        self.active = still
        return ev

    def current(self, pos_m: float, t_s: float) -> dict | None:
        if not self.active:
            return None
        seg, t0 = self.active[-1]
        frac = max(0.0, min(1.0, (pos_m - seg.start_m) / seg.length_m))
        mine = t_s - t0
        out = {"name": seg.name, "frac": frac, "elapsed_s": mine, "segment": seg}
        if seg.pr_s and frac > 0.02:
            out["delta_pr"] = mine - seg.pr_s * frac
            out["projected_s"] = mine / frac
        return out

    def board(self, pos_m: float, t_s: float) -> Board | None:
        cur = self.current(pos_m, t_s)
        if cur is None:
            return None
        seg = cur["segment"]
        rows = []
        if seg.kom:
            rows.append(Row(None, str(seg.kom), "KOM"))
        if seg.pr_s:
            rows.append(Row(None, hms(seg.pr_s), t("seg.pr") + (f" · {seg.pr_date}"
                                                                 if seg.pr_date else "")))
        if seg.local_best_s:
            rows.append(Row(None, hms(seg.local_best_s), t("seg.local_best")))
        if "projected_s" in cur:
            rows.append(Row(None, hms(cur["projected_s"]),
                            f"{t('board.me')} · {delta(cur['delta_pr'])}", me=True))
        else:
            rows.append(Row(None, hms(cur["elapsed_s"]), t("board.me"), me=True))
        sub = f"Strava · {cur['frac'] * 100:.0f} % · {seg.length_m / 1000:.2f} km"
        return Board(seg.name, rows, subtitle=sub)
