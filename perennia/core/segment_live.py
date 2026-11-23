"""O segmento em tempo real: ao entrares num segmento (do Strava ou da Perennia), a sessão
mostra a altimetria do segmento com três pontos — **KOM** (vermelho), o **teu melhor tempo**
(azul) e **tu agora** (rosa) — e uma tabela com a diferença para cada um e os W/kg.

* **Tu agora** — a posição real e o tempo desde que entraste; os W/kg são a tua potência média
  desde a entrada a dividir pelo teu peso.
* **O teu melhor** — se o melhor tempo foi feito aqui, numa sessão com amostras (na mesma
  rota), a posição dele em cada segundo é a verdadeira e os W/kg são os que fizeste nesse dia;
  senão (um PR do Strava, por exemplo) a posição e os W/kg são **estimados** pela física do
  segmento (o mesmo planeador do Segment Pace) para fazer esse tempo — com «≈».
* **KOM** — só se sabe o tempo. A posição em cada segundo é estimada pela física (um ritmo que
  acompanha as rampas), e os W/kg, se aparecem, são os **necessários com o teu peso e a tua
  bicicleta** para fazer esse tempo (≈). Não são os do dono do KOM.

A diferença («Δ») é quanto tempo estás atrás (+) ou à frente (−) de cada um no **mesmo ponto**
do segmento. O tempo final é o deles; o teu é a projeção ao ritmo de agora.

Sem pyglet: o HUD só desenha o que `snapshot()` devolve. O cálculo da física para o KOM e
para o melhor estimado corre num fio à parte, para não travar a sessão; até acabar usa-se um
ritmo constante.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from .i18n import tr

PROFILE_POINTS = 80


@dataclass
class Rival:
    """Um dos três: o KOM, o teu melhor ou tu."""
    key: str                         # kom | best | me
    total_s: float | None            # o tempo do segmento (o teu: a projeção)
    track: object | None = None      # segment_pace.Track: distância ↔ tempo, desde a entrada
    wkg: float | None = None
    estimated: bool = False          # a posição e os W/kg são estimados (≈)
    source: str = ""                 # de onde vem («strava», «perennia», «física»…)


@dataclass
class SegmentLive:
    seg: object
    length_m: float
    profile: list[tuple[float, float]]           # (metros desde a entrada, altitude)
    weight_kg: float
    kom: Rival | None = None
    best: Rival | None = None
    energy_j: float = 0.0
    moving_s: float = 0.0
    _last_t: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # -------------------------------------------------------------- ao vivo

    def feed(self, t_s: float, power_w: float | None) -> None:
        """A potência de agora (a cada frame): acumula a energia desde a entrada."""
        if self._last_t is not None:
            dt = max(0.0, min(2.0, t_s - self._last_t))
            if power_w is not None:
                self.energy_j += float(power_w) * dt
                self.moving_s += dt
        self._last_t = t_s

    def my_avg_w(self) -> float | None:
        return self.energy_j / self.moving_s if self.moving_s >= 1.0 else None

    def snapshot(self, elapsed_s: float, frac: float) -> dict:
        """O que o painel mostra agora: as três posições (metros desde a entrada) e a tabela."""
        me_m = max(0.0, min(self.length_m, frac * self.length_m))
        avg = self.my_avg_w()
        rows = []
        pos = {"me": me_m}
        with self._lock:
            rivals = [r for r in (self.kom, self.best) if r is not None and r.total_s]
        for r in rivals:
            track = r.track or _even(self.length_m, r.total_s)
            their_here = track.time_at(me_m)                 # quando passaram aqui
            pos[r.key] = min(self.length_m, track.dist_at(elapsed_s))
            rows.append({"key": r.key, "label": label(r.key), "total_s": r.total_s,
                         "delta_s": elapsed_s - their_here if frac > 0.005 else None,
                         "wkg": r.wkg, "estimated": r.estimated, "source": r.source})
        projected = elapsed_s / frac if frac > 0.02 else None
        rows.append({"key": "me", "label": label("me"), "total_s": projected,
                     "elapsed_s": elapsed_s, "delta_s": None,
                     "wkg": (avg / self.weight_kg) if avg and self.weight_kg else None,
                     "avg_w": avg, "estimated": False, "source": ""})
        return {"name": getattr(self.seg, "name", ""), "length_m": self.length_m,
                "frac": frac, "elapsed_s": elapsed_s, "positions": pos, "rows": rows,
                "profile": self.profile,
                "source": "Strava" if getattr(self.seg, "source", "") == "strava"
                else "Perennia"}


def label(key: str) -> str:
    return {"kom": "KOM", "best": tr("O meu melhor", "My best"),
            "me": tr("Eu agora", "Me now")}[key]


def _even(length_m: float, total_s: float):
    """Um ritmo constante: a posição antes de a física acabar (ou se não der)."""
    from .segment_pace import Track
    return Track([0.0, float(length_m)], [0.0, float(total_s)])


# ------------------------------------------------------------------ montar


def segment_profile(route, start_m: float, end_m: float, n: int = PROFILE_POINTS
                    ) -> list[tuple[float, float]]:
    length = max(1.0, end_m - start_m)
    return [(length * k / (n - 1), route.ele_at(start_m + length * k / (n - 1)))
            for k in range(n)]


def best_from_samples(db, seg, route, best_s: int | None) -> Rival | None:
    """O teu melhor esforço a partir das amostras de uma sessão nesta rota: a posição de cada
    segundo e a potência média (W/kg com o peso desse dia). None se não houver."""
    from . import segments as segs
    from .segment_pace import Track
    rid = getattr(seg, "route_id", None)
    if not rid:
        return None
    try:
        efforts = segs.efforts(db, getattr(seg, "source", "strava"), seg.id)
    except Exception:
        return None
    total = route.total_m
    for eff in efforts:
        if eff.get("kind") != "ride" or not eff.get("session_id"):
            continue
        ride = db.conn.execute("SELECT route_id, weight_at_ride_kg FROM rides WHERE id = ?",
                               (eff["session_id"],)).fetchone()
        if ride is None or ride["route_id"] != rid:
            continue
        rows = db.conn.execute("SELECT t_s, dist_m, power_w FROM ride_samples WHERE ride_id = ?"
                               " ORDER BY t_s", (eff["session_id"],)).fetchall()
        win = _window(rows, seg.start_m, seg.end_m, total, float(eff["elapsed_s"]))
        if win is None:
            continue
        dist, tim, watts = win
        avg = sum(watts) / len(watts) if watts else None
        weight = ride["weight_at_ride_kg"] or db.athlete().weight_kg
        if best_s and abs(tim[-1] - best_s) > max(3.0, 0.05 * best_s):
            continue                        # não é o esforço do melhor tempo
        return Rival("best", float(best_s or tim[-1]), Track(dist, tim),
                     (avg / weight) if avg and weight else None, False,
                     tr("o teu esforço de {d}", "your effort of {d}",
                        d=str(eff.get("created_at") or "")[:10]))
    return None


def _window(rows, start_m: float, end_m: float, route_total: float, want_s: float):
    """Das amostras de uma sessão, a passagem pelo segmento mais parecida com `want_s`:
    (metros desde a entrada, segundos desde a entrada, potências)."""
    best, best_err = None, None
    inside, t0, dist, tim, watts = False, 0.0, [], [], []
    prev = None
    for r in rows:
        d = float(r["dist_m"] or 0.0)
        pos = d % route_total if route_total > 0 else d
        if not inside:
            if start_m <= pos < start_m + 30.0 and (prev is None or prev < start_m
                                                    or prev > pos):
                inside, t0 = True, float(r["t_s"])
                dist, tim, watts = [pos - start_m], [0.0], []
        else:
            if pos >= end_m or (prev is not None and pos < prev):
                dist.append(end_m - start_m)
                tim.append(float(r["t_s"]) - t0)
                err = abs(tim[-1] - want_s)
                if best_err is None or err < best_err:
                    best, best_err = (dist, tim, watts), err
                inside = False
            else:
                dist.append(pos - start_m)
                tim.append(float(r["t_s"]) - t0)
                if r["power_w"] is not None:
                    watts.append(float(r["power_w"]))
        prev = pos
    return best


def build(db, athlete, route, seg, physics: bool = True, wait: bool = False) -> SegmentLive:
    """O painel de um segmento: a altimetria, o KOM e o teu melhor (com as amostras se as há).
    Com `physics`, a física do KOM (e do melhor sem amostras) corre num fio (`wait` espera
    por ela — para os testes)."""
    from .segment_pace import kom_seconds, my_best
    length = max(1.0, seg.end_m - seg.start_m)
    live = SegmentLive(seg, length, segment_profile(route, seg.start_m, seg.end_m),
                       float(athlete.weight_kg or 70.0))
    kom_s = kom_seconds(getattr(seg, "kom", None))
    if kom_s:
        live.kom = Rival("kom", float(kom_s), None, None, True, tr("física", "physics"))
    best_s = my_best(seg)
    real = best_from_samples(db, seg, route, best_s) if best_s else None
    if real is not None:
        live.best = real
    elif best_s:
        live.best = Rival("best", float(best_s), None, None, True,
                          "Strava" if seg.pr_s and best_s == seg.pr_s else "Perennia")
    if physics and (live.kom is not None or (live.best is not None and live.best.estimated)):
        th = threading.Thread(target=_physics, args=(live, athlete, route, seg),
                              name="segment-live", daemon=True)
        th.start()
        if wait:
            th.join(30)
    return live


def _physics(live: SegmentLive, athlete, route, seg) -> None:
    """A física do segmento: onde estaria (e com quantos W/kg) quem faz o tempo do KOM ou o
    teu melhor estimado, com o teu peso e a tua bicicleta."""
    try:
        from .segment_pace import Planner, capacity_curve
        planner = Planner(route, seg.start_m, seg.end_m, athlete.total_mass_kg, athlete.cda,
                          athlete.crr, athlete.ftp_w, capacity_curve(athlete.ftp_w, None),
                          lead_in_m=100.0)
    except Exception:
        return
    w = float(athlete.weight_kg or 70.0)
    for r in (live.kom, live.best):
        if r is None or not r.estimated or not r.total_s:
            continue
        try:
            plan = planner.plan_time(r.total_s)
        except Exception:
            continue
        with live._lock:
            if plan.track is not None:
                r.track = plan.track
            r.wkg = plan.avg_w / w if plan.avg_w and w else None
