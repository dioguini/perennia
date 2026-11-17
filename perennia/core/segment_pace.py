"""Segment Pace e Segment KOM (Challenge do ciclismo).

Dois jogos sobre um segmento que já existe na Perennia (do Strava, da biblioteca
ou criado aqui) — de qualquer inclinação: subida, plano ou descida.

* **Segment Pace** — dás um alvo (tempo mm:ss, «o teu melhor + x %» ou potência média)
  e a Perennia conduz o esforço: parte o segmento em secções pela inclinação e
  calcula, **por física** (massa, CdA, Crr, perfil real), os watts de cada uma para que
  o tempo total seja o alvo. Não é potência constante: mais nas partes duras, menos nas
  fáceis, e nas descidas recuperas — com a variação limitada (`VARIATION_PCT`) e um
  mínimo (`FLOOR_PCT`). Uma «guia» vai à frente (o mesmo mecanismo dos fantasmas) com a
  diferença em tempo; o ERG vem ligado por omissão (desligado: segues o sinal). Se te
  atrasas, os watts das secções que faltam são recalculados.
* **Segment KOM** — dois alvos: **O meu KOM** (o melhor entre o PR do Strava e o melhor
  tempo aqui feito) e **KOM do segmento** (o tempo do Strava, só se existir). Esforço
  máximo, sem ERG, com fantasmas e a diferença ao vivo.

No fim há a tabela por secção (watts do plano, watts reais e o tempo ganho ou perdido).

Aviso honesto: um tempo do Strava foi feito na estrada (vento, aspiração, curvas) e aqui
a física é a do rolo. Por isso mostramos **a potência necessária aqui** para esse tempo,
sem fingir que as duas coisas são iguais.

Tudo corre offline com o que está guardado (PR e KOM vêm da biblioteca/rota).
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from . import physics
from .boards import Board, Row
from .games import MIN_BLOCK_S, Game, capacity_at, capacity_curve
from .i18n import t, tr
from .units import delta, hms

# ---- valores afináveis (Definições → Avançado → «Segment Pace e KOM»)
LEAD_IN_M = 500.0          # entrada antes do segmento
VARIATION_PCT = 20.0       # ± em volta da média
FLOOR_PCT = 50.0           # nunca abaixo desta % da média (descidas)
SECTION_MIN_M = 250.0      # secção mais curta
SECTION_MAX_M = 1000.0     # secção mais longa
GRADE_TOL_PCT = 1.5        # mudança de inclinação que abre uma secção nova
GRADE_REF_PCT = 4.0        # diferença de inclinação que dá a variação toda
HARD_PCT = 95.0            # a partir daqui (% da capacidade) o alvo é «duro»
TOL_PCT = 1.0              # o Pace conta como cumprido dentro desta % do alvo
REPLAN = True              # recalcular o que falta quando há atraso

# Precisão interna (não são preferências): passo da simulação, célula do perfil e
# limites da procura de watts.
SIM_DT_S = 0.5
CELL_M = 25.0
SEARCH_W = (5.0, 2500.0)
MAX_SIM_S = 6 * 3600.0

PACE, KOM = "seg_pace", "seg_kom"
PACE_KINDS = ("time", "pr_pct", "power")
KOM_KINDS = ("my_kom", "kom")


# ------------------------------------------------------------------ tempos


def parse_clock(text, bare: str = "s") -> int | None:
    """«5:01», «1:02:03», «47s», «1m 5s», «12 min» → segundos. Um número sozinho vale
    `bare` («s» segundos ou «min» minutos). Devolve None se não se perceber."""
    if text is None:
        return None
    s = str(text).strip().lower().replace(",", ".")
    if not s:
        return None
    m = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", s)
    if m:
        h, mi, sec = int(m.group(1) or 0), int(m.group(2)), float(m.group(3))
        return int(round(h * 3600 + mi * 60 + sec))
    m = re.fullmatch(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*(?:m|min))?\s*(?:(\d+(?:\.\d+)?)\s*s)?", s)
    if m and any(m.groups()):
        return int(round(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
                         + float(m.group(3) or 0)))
    m = re.fullmatch(r"\d+(?:\.\d+)?", s)
    if m:
        v = float(s)
        return int(round(v * (60 if bare == "min" else 1)))
    return None


def kom_seconds(text) -> int | None:
    """O KOM do Strava vem como texto («5:01», «47s»); None se não há."""
    return parse_clock(text, bare="s")


def my_best(seg) -> int | None:
    """O meu melhor tempo no segmento: o melhor entre o PR do Strava e o feito aqui."""
    vals = [int(v) for v in (getattr(seg, "pr_s", None), getattr(seg, "local_best_s", None))
            if v]
    return min(vals) if vals else None


# ------------------------------------------------------------------- plano


@dataclass
class Section:
    idx: int
    start_m: float
    end_m: float
    grade: float                 # inclinação média, %
    watts: float = 0.0
    plan_s: float = 0.0          # tempo previsto na secção

    @property
    def length_m(self) -> float:
        return max(1.0, self.end_m - self.start_m)


class Track:
    """Distância → tempo (e o inverso) de um plano, para desenhar a guia e comparar."""

    def __init__(self, dist: list[float], time: list[float]):
        self.dist, self.time = dist, time
        self.total_m = dist[-1] if dist else 0.0
        self.total_s = time[-1] if time else 0.0

    def time_at(self, d: float) -> float:
        if not self.dist:
            return 0.0
        i = bisect.bisect_left(self.dist, d)
        if i <= 0:
            return self.time[0]
        if i >= len(self.dist):
            return self.time[-1]
        d0, d1, t0, t1 = self.dist[i - 1], self.dist[i], self.time[i - 1], self.time[i]
        f = 0.0 if d1 - d0 <= 1e-9 else (d - d0) / (d1 - d0)
        return t0 + f * (t1 - t0)

    def dist_at(self, s: float) -> float:
        if not self.time:
            return 0.0
        i = bisect.bisect_left(self.time, s)
        if i <= 0:
            return self.dist[0]
        if i >= len(self.time):
            return self.dist[-1]
        t0, t1, d0, d1 = self.time[i - 1], self.time[i], self.dist[i - 1], self.dist[i]
        f = 0.0 if t1 - t0 <= 1e-9 else (s - t0) / (t1 - t0)
        return d0 + f * (d1 - d0)


@dataclass
class Plan:
    sections: list[Section]
    target_s: float | None
    total_s: float               # o que a simulação dá com estes watts
    avg_w: float                 # média ponderada pelo tempo
    track: Track
    reachable: bool = True       # False: nem com o máximo se chega ao alvo

    @property
    def watts(self) -> list[float]:
        return [s.watts for s in self.sections]


def build_sections(route, start_m: float, end_m: float, *, min_m: float | None = None,
                   max_m: float | None = None, tol: float | None = None) -> list[Section]:
    """Parte o segmento em secções de inclinação parecida (e nunca mais longas que `max_m`)."""
    min_m = SECTION_MIN_M if min_m is None else min_m
    max_m = SECTION_MAX_M if max_m is None else max(max_m, min_m)
    tol = GRADE_TOL_PCT if tol is None else tol
    a, b = float(start_m), float(end_m)
    if b - a < 1.0:
        return []
    cells: list[tuple[float, float, float]] = []
    d = a
    while d < b - 1e-6:
        e = min(b, d + CELL_M)
        cells.append((d, e, (route.ele_at(e) - route.ele_at(d)) / max(1e-6, e - d) * 100.0))
        d = e
    look = max(2, int(min_m / (2 * CELL_M)))
    groups: list[list[tuple[float, float, float]]] = [[cells[0]]]
    for i in range(1, len(cells)):
        cur = groups[-1]
        length = cur[-1][1] - cur[0][0]
        mean = (route.ele_at(cur[-1][1]) - route.ele_at(cur[0][0])) / max(1e-6, length) * 100.0
        ahead = cells[i:i + look]
        ahead_g = (sum(c[2] * (c[1] - c[0]) for c in ahead)
                   / max(1e-6, sum(c[1] - c[0] for c in ahead)))
        if length >= max_m or (length >= min_m and abs(ahead_g - mean) > tol):
            groups.append([cells[i]])
        else:
            cur.append(cells[i])
    if len(groups) > 1 and groups[-1][-1][1] - groups[-1][0][0] < min_m:
        tail = groups.pop()                            # o restinho junta-se à anterior
        groups[-1] += tail
    out = []
    for i, g in enumerate(groups):
        s0, s1 = g[0][0], g[-1][1]
        out.append(Section(i, s0, s1, (route.ele_at(s1) - route.ele_at(s0)) / (s1 - s0) * 100.0))
    return out


def shape_factors(sections: list[Section], var_pct: float | None = None,
                  floor_pct: float | None = None, ref_pct: float | None = None) -> list[float]:
    """Quanto cada secção se afasta da média: >1 onde é mais duro que o resto, <1 onde é
    mais fácil. Fica sempre entre `1 − variação` (com o mínimo `FLOOR_PCT`) e `1 + variação`."""
    var = (VARIATION_PCT if var_pct is None else var_pct) / 100.0
    floor = (FLOOR_PCT if floor_pct is None else floor_pct) / 100.0
    ref = max(0.1, GRADE_REF_PCT if ref_pct is None else ref_pct)
    total = sum(s.length_m for s in sections) or 1.0
    gbar = sum(s.grade * s.length_m for s in sections) / total
    lo, hi = max(1.0 - var, floor), 1.0 + var
    return [min(hi, max(lo, 1.0 + var * max(-1.0, min(1.0, (s.grade - gbar) / ref))))
            for s in sections]


class Planner:
    """Calcula watts por secção. Uma instância por segmento e atleta."""

    def __init__(self, route, start_m: float, end_m: float, mass_kg: float, cda: float,
                 crr: float, ftp: int, curve: dict | None = None, *,
                 lead_in_m: float | None = None, sections: list[Section] | None = None):
        self.route = route
        self.start_m, self.end_m = float(start_m), float(end_m)
        self.mass, self.cda, self.crr = mass_kg, cda, crr
        self.ftp = max(50, int(ftp))
        self.curve = curve or capacity_curve(self.ftp, None)
        self.lead_in_m = LEAD_IN_M if lead_in_m is None else lead_in_m
        self.sections = sections or build_sections(route, self.start_m, self.end_m)
        self.shape = shape_factors(self.sections)
        self._merge_short()

    @property
    def length_m(self) -> float:
        return max(1.0, self.end_m - self.start_m)

    # ------------------------------------------------------------ simulação

    def _v0(self, watts: float, grade_pct: float) -> float:
        if self.lead_in_m < 50.0:
            return 0.0                              # parte parado
        return physics.speed_from_power(self.mass, self.cda, self.crr, watts, grade_pct / 100.0)

    def simulate(self, watts: list[float], first: int = 0, v0: float | None = None,
                 record: bool = False):
        """Tempo (s) das secções `first…` com `watts` (um por secção), a partir do início da
        secção `first`. Devolve (total, tempos por secção, pista ou None)."""
        secs = self.sections[first:]
        if not secs:
            return 0.0, [], None
        v = self._v0(watts[0], secs[0].grade) if v0 is None else v0
        pos, now = secs[0].start_m, 0.0
        times: list[float] = []
        dist, tim = [pos - self.start_m], [0.0]
        sec_t0 = 0.0
        for k, s in enumerate(secs):
            while pos < s.end_m - 1e-9:
                v = physics.step_velocity(self.mass, self.cda, self.crr, v, watts[k],
                                          self.route.grade_at(pos) / 100.0, SIM_DT_S)
                step = v * SIM_DT_S
                if now > MAX_SIM_S:
                    return MAX_SIM_S, times + [MAX_SIM_S] * (len(secs) - len(times)), None
                if pos + step >= s.end_m:
                    f = (s.end_m - pos) / max(step, 1e-9)
                    now += f * SIM_DT_S
                    pos = s.end_m
                else:
                    pos += step
                    now += SIM_DT_S
                if record:
                    dist.append(pos - self.start_m)
                    tim.append(now)
            times.append(now - sec_t0)
            sec_t0 = now
        return now, times, (Track(dist, tim) if record else None)

    def _merge_short(self) -> None:
        """Nenhuma secção dura menos que o mínimo de um bloco (dá tempo ao rolo)."""
        for _ in range(len(self.sections)):
            if len(self.sections) < 2:
                break
            w = [max(self.ftp * 0.7, 1.0) * f for f in self.shape]
            _, times, _ = self.simulate(w)
            short = next((i for i, x in enumerate(times) if x < MIN_BLOCK_S), None)
            if short is None:
                break
            j = short - 1 if short > 0 else 1
            a, b = sorted((short, j))
            sa, sb = self.sections[a], self.sections[b]
            merged = Section(a, sa.start_m, sb.end_m,
                             (self.route.ele_at(sb.end_m) - self.route.ele_at(sa.start_m))
                             / (sb.end_m - sa.start_m) * 100.0)
            self.sections[a:b + 1] = [merged]
            for i, s in enumerate(self.sections):
                s.idx = i
            self.shape = shape_factors(self.sections)

    # --------------------------------------------------------------- solvers

    def _weights(self, first: int = 0) -> list[float]:
        return self.shape[first:]

    def _solve(self, goal, first: int = 0, v0: float | None = None):
        """Bissecção de `m` (a escala dos watts) até `goal(total, avg)` ser 0.
        `goal` devolve >0 se ainda falta potência (muito lento)."""
        shape = self._weights(first)
        lo, hi = SEARCH_W
        best = None
        for _ in range(48):
            m = (lo + hi) / 2.0
            w = [m * f for f in shape]
            total, times, _ = self.simulate(w, first, v0)
            avg = sum(x * y for x, y in zip(w, times)) / max(total, 1e-9)
            g = goal(total, avg)
            best = (m, w, total, times, avg)
            if abs(g) < 0.05:
                break
            if g > 0:
                lo = m
            else:
                hi = m
            if hi - lo < 0.02:
                break
        return best

    def _finish(self, m_w_total_times_avg, target_s, first: int = 0, v0=None,
                reachable: bool = True) -> Plan:
        w = m_w_total_times_avg[1]
        # a pista final com registo (para a guia)
        total, times, track = self.simulate(w, first, v0, record=True)
        secs = []
        for s, x, y in zip(self.sections[first:], w, times):
            secs.append(Section(s.idx, s.start_m, s.end_m, s.grade, x, y))
        avg = sum(x * y for x, y in zip(w, times)) / max(total, 1e-9)
        return Plan(secs, target_s, total, avg, track, reachable)

    def plan_time(self, target_s: float) -> Plan:
        """Os watts por secção para fazer o segmento em `target_s`."""
        target_s = max(20.0, float(target_s))
        r = self._solve(lambda total, avg: total - target_s)
        reachable = abs(r[2] - target_s) < max(1.0, target_s * 0.01)
        return self._finish(r, target_s, reachable=reachable)

    def plan_power(self, avg_w: float) -> Plan:
        """O tempo que dá uma potência média de `avg_w` (distribuída pelas secções)."""
        avg_w = max(SEARCH_W[0], float(avg_w))
        r = self._solve(lambda total, avg: avg_w - avg)
        return self._finish(r, r[2])

    def replan(self, first: int, v0: float, remaining_s: float, floor_w: float,
               cap_w: float) -> tuple[list[float], bool]:
        """Recalcula os watts das secções `first…` para fazer o que falta em `remaining_s`,
        a partir da velocidade `v0`. Nunca pede mais do que `cap_w` (a capacidade para
        essa duração) nem menos do que `floor_w`. Devolve (watts, alcançável)."""
        remaining_s = max(5.0, remaining_s)
        r = self._solve(lambda total, avg: total - remaining_s, first, max(v0, 1.0))
        w, total, avg = r[1], r[2], r[4]
        ok = abs(total - remaining_s) < max(1.0, remaining_s * 0.02)
        if avg > cap_w > 0:
            k = cap_w / avg
            w = [x * k for x in w]
            ok = False
        w = [max(floor_w, x) for x in w]
        return w, ok


# -------------------------------------------------------------- viabilidade


def feasibility(avg_w: float, seconds: float, ftp: int, curve: dict) -> dict:
    """O alvo cabe na tua capacidade? Compara a potência média com o máximo estimado para
    essa duração (a curva de potência recente, ou a típica pela FTP)."""
    cap = capacity_at(curve, max(1.0, seconds))
    pct_ftp = avg_w / max(1, ftp) * 100.0
    ratio = avg_w / max(1.0, cap) * 100.0
    if ratio > 100.0:
        level = "over"
        msg = tr("Pede {w} W ({p} % da FTP); o teu máximo estimado para esta duração é "
                 "{c} W: está acima do que consegues.",
                 "It needs {w} W ({p} % of FTP); your estimated maximum for this duration is "
                 "{c} W: it is above what you can do.", w=round(avg_w), p=round(pct_ftp),
                 c=round(cap))
    elif ratio >= HARD_PCT:
        level = "hard"
        msg = tr("Pede {w} W ({p} % da FTP); o teu máximo estimado para esta duração é "
                 "{c} W: é no limite.",
                 "It needs {w} W ({p} % of FTP); your estimated maximum for this duration is "
                 "{c} W: right at your limit.", w=round(avg_w), p=round(pct_ftp), c=round(cap))
    else:
        level = "ok"
        msg = tr("Pede {w} W ({p} % da FTP); o teu máximo estimado para esta duração é "
                 "{c} W: é possível.",
                 "It needs {w} W ({p} % of FTP); your estimated maximum for this duration is "
                 "{c} W: doable.", w=round(avg_w), p=round(pct_ftp), c=round(cap))
    return {"level": level, "avg_w": avg_w, "pct_ftp": pct_ftp, "cap_w": cap,
            "ratio_pct": ratio, "text": msg}


# ------------------------------------------------------------ alvos e preparação


@dataclass
class Setup:
    """Tudo o que o ecrã e o jogo precisam: o plano, a viabilidade e as guias."""
    segment: object
    planner: Planner
    mode: str
    kind: str
    plan: Plan                                   # o alvo principal
    feas: dict
    guides: list = field(default_factory=list)   # [(rótulo, tempo alvo, Plano)]
    label: str = ""
    note: str = ""


def target_choices(mode: str, seg) -> list[tuple[str, str]]:
    """(tipo, nome) dos alvos possíveis para este segmento."""
    if mode == PACE:
        return [("time", tr("Tempo (mm:ss)", "Time (mm:ss)")),
                ("pr_pct", tr("O meu melhor + x %", "My best + x %")),
                ("power", tr("Potência média (W)", "Average power (W)"))]
    out = []
    if my_best(seg):
        out.append(("my_kom", tr("O meu KOM", "My KOM")))
    if kom_seconds(getattr(seg, "kom", None)):
        out.append(("kom", tr("KOM do segmento", "Segment KOM")))
    return out


def planner_for(db, athlete, route_id: str, seg, best: dict | None = None,
                lead_in_m: float | None = None) -> Planner:
    from .route_index import RouteIndex
    pts = db.route_points(route_id)
    if not pts:
        raise ValueError("rota sem pontos")
    curve = capacity_curve(athlete.ftp_w, best)
    return Planner(RouteIndex(pts), seg.start_m, seg.end_m, athlete.total_mass_kg, athlete.cda,
                   athlete.crr, athlete.ftp_w, curve, lead_in_m=lead_in_m)


def prepare(planner: Planner, seg, mode: str, kind: str, value: float | None = None
            ) -> Setup:
    """Resolve o alvo escolhido num plano. Levanta `ValueError` com a razão se não der."""
    ftp, curve = planner.ftp, planner.curve
    guides: list = []
    label = ""
    note = ""
    if mode == PACE:
        if kind == "time":
            if not value or value <= 0:
                raise ValueError(tr("Indica o tempo (mm:ss).", "Enter the time (mm:ss)."))
            plan = planner.plan_time(value)
            label = tr("Tempo {x}", "Time {x}", x=hms(value))
        elif kind == "pr_pct":
            best = my_best(seg)
            if not best:
                raise ValueError(tr("Este segmento ainda não tem o teu melhor tempo: usa um "
                                    "tempo ou uma potência.",
                                    "This segment has no best time of yours yet: use a time "
                                    "or a power."))
            pct = float(value or 0.0)
            plan = planner.plan_time(best * (1.0 + pct / 100.0))
            label = tr("Melhor {b} {s} %", "Best {b} {s} %", b=hms(best),
                       s=f"{pct:+.1f}".replace(".0", ""))
        elif kind == "power":
            if not value or value <= 0:
                raise ValueError(tr("Indica a potência média (W).", "Enter the average "
                                    "power (W)."))
            plan = planner.plan_power(value)
            label = tr("{w} W de média", "{w} W average", w=round(value))
        else:
            raise ValueError("alvo desconhecido")
        guides = [(tr("Guia", "Guide"), plan.total_s if kind == "power" else plan.target_s,
                   plan)]
    elif mode == KOM:
        mine, theirs = my_best(seg), kom_seconds(getattr(seg, "kom", None))
        wanted = {"my_kom": mine, "kom": theirs}.get(kind)
        if not wanted:
            raise ValueError(tr("Este alvo não existe neste segmento.",
                                "This target does not exist for this segment."))
        plan = planner.plan_time(wanted)
        label = tr("O meu KOM {x}", "My KOM {x}", x=hms(wanted)) if kind == "my_kom" else \
            tr("KOM {x}", "KOM {x}", x=hms(wanted))
        if mine:
            guides.append((tr("O meu KOM", "My KOM"), float(mine),
                           plan if kind == "my_kom" else planner.plan_time(mine)))
        if theirs:
            guides.append((tr("KOM", "KOM"), float(theirs),
                           plan if kind == "kom" else planner.plan_time(theirs)))
        note = tr("Os tempos do Strava foram feitos na estrada (vento, aspiração): aqui vês "
                  "a potência de que precisas no rolo para esse tempo.",
                  "Strava times were set on the road (wind, drafting): here you see the "
                  "power you need on the trainer for that time.")
    else:
        raise ValueError("modo desconhecido")
    feas = feasibility(plan.avg_w, plan.total_s, ftp, curve)
    if not plan.reachable:
        feas = dict(feas, level="over", text=tr(
            "Nem com a potência máxima se chega a este tempo: está fora do alcance.",
            "This time cannot be reached even at maximum power: it is out of reach."))
    return Setup(seg, planner, mode, kind, plan, feas, guides, label, note)


def parse_target(mode: str, kind: str, text: str) -> float | None:
    """O que se escreveu no ecrã → o valor do alvo."""
    s = (text or "").strip().lower().replace(",", ".")
    if kind == "time":
        return parse_clock(s, bare="min")
    if kind in ("pr_pct", "power"):
        try:
            return float(s.replace("%", "").replace("w", "").replace("+", "").strip() or "0")
        except ValueError:
            return None
    return None


def segments_of(db, route_id: str | None) -> list:
    """Segmentos da rota que dão para jogar (com comprimento)."""
    from . import segments as seg_mod
    return [s for s in seg_mod.load(db, route_id) if s.length_m >= 100.0] if route_id else []


# ------------------------------------------------------------------- o jogo


class SegmentGame(Game):
    """Base de Segment Pace e Segment KOM: o segmento, a guia e a tabela por secção."""

    has_duration = False
    has_bots = False
    erg_default = False
    default_minutes = 0
    durations = ()
    needs_segment = True
    mode = ""

    def __init__(self, ftp: int, weight_kg: float = 75.0, *, setup: Setup | None = None,
                 spec: dict | None = None, **kw):
        self.setup_ = setup
        self.spec = dict(spec or {})
        super().__init__(ftp, weight_kg, **kw)

    # ----------------------------------------------------------- preparação

    def setup(self) -> None:
        s = self.setup_
        self.phase = "lead"             # lead | run | done
        self.idx = 0
        self.t0 = 0.0
        self.sec_t0 = 0.0
        self.sec_psum = 0.0
        self.sec_pn = 0
        self.tot_psum = 0.0
        self.tot_pn = 0
        self.rows: list[dict] = []
        self.elapsed: float | None = None
        self.pos = 0.0
        self.now = 0.0
        self.speed = 0.0
        self.delta_s = 0.0
        self.replans = 0
        self.reachable = True
        self.start_m = 0.0
        self.watts: list[float] = []
        if s is None:
            return
        seg = s.segment
        self.seg_name = seg.name
        self.start_m = max(0.0, seg.start_m - s.planner.lead_in_m)
        self.watts = [float(w) for w in s.plan.watts]
        self.sections = s.plan.sections
        self.target_s = float(s.plan.target_s or s.plan.total_s)
        self.pace_floor_w = FLOOR_PCT / 100.0 * s.plan.avg_w
        self.guide_list = list(s.guides)

    @property
    def n_sections(self) -> int:
        return len(self.watts)

    # --------------------------------------------------------- do motor

    def guides(self) -> list[tuple[str, float, float]]:
        """(etiqueta, posição na rota da guia, diferença em s) — para o HUD."""
        s = self.setup_
        if s is None:
            return []
        seg = s.segment
        run = self.phase != "lead"
        tau = (self.elapsed if self.phase == "done" and self.elapsed is not None
               else (self.now - self.t0 if run else 0.0))
        out = []
        for label, _tgt, plan in self.guide_list:
            tr_ = plan.track
            d = tr_.dist_at(tau)
            mine_d = max(0.0, self.pos - seg.start_m)
            delta_s = (tau - tr_.time_at(mine_d)) if run else 0.0
            out.append((label, seg.start_m + d, delta_s))
        return out

    def observe(self, pos_m: float, t_s: float, speed_mps: float) -> list[tuple[str, dict]]:
        """Chamado a cada frame: onde estou? Fecha secções e o segmento."""
        if self.finished or self.setup_ is None:
            return []
        seg = self.setup_.segment
        self.pos, self.now, self.speed = pos_m, t_s, speed_mps
        ev: list[tuple[str, dict]] = []
        v = max(speed_mps, 0.5)
        if self.phase == "lead":
            if pos_m >= seg.start_m:
                self.t0 = self.sec_t0 = t_s - (pos_m - seg.start_m) / v
                self.phase = "run"
                self.idx = 0
                self.target_w = int(round(self.watts[0])) if self.mode == PACE else None
                ev.append(("game_cue", {"text": self._cue(0)}))
            return ev
        if self.phase != "run":
            return ev
        secs = self.sections
        while self.idx < len(secs) and pos_m >= secs[self.idx].end_m:
            sec = secs[self.idx]
            crossed = t_s - max(0.0, pos_m - sec.end_m) / v
            self._close_section(sec, crossed)
            self.idx += 1
            self.sec_t0 = crossed
            self.sec_psum = 0.0
            self.sec_pn = 0
            if self.idx < len(secs):
                if self.mode == PACE and REPLAN:
                    self._replan(self.idx, crossed, v)
                if self.mode == PACE:
                    self.target_w = int(round(self.watts[self.idx]))
                ev.append(("game_cue", {"text": self._cue(self.idx)}))
            else:
                self.elapsed = crossed - self.t0
        if self.idx >= len(secs):
            self.phase = "done"
            ev += self._complete()
        return ev

    def _cue(self, i: int) -> str:
        s = self.sections[i]
        if self.mode == PACE:
            return tr("Secção {i}/{n} · {g} % · {w} W", "Section {i}/{n} · {g} % · {w} W",
                      i=i + 1, n=self.n_sections, g=f"{s.grade:.1f}", w=round(self.watts[i]))
        return tr("Secção {i}/{n} · {g} %", "Section {i}/{n} · {g} %", i=i + 1,
                  n=self.n_sections, g=f"{s.grade:.1f}")

    def _close_section(self, sec: Section, crossed: float) -> None:
        real_s = crossed - self.sec_t0
        real_w = self.sec_psum / self.sec_pn if self.sec_pn else None
        plan_s = self.primary_plan.sections[sec.idx].plan_s
        self.rows.append({"idx": sec.idx, "start_m": round(sec.start_m - self.setup_.segment.start_m),
                          "length_m": round(sec.length_m), "grade": round(sec.grade, 1),
                          "plan_w": round(self.primary_plan.sections[sec.idx].watts),
                          "sign_w": round(self.watts[sec.idx]),
                          "real_w": None if real_w is None else round(real_w),
                          "plan_s": round(plan_s, 1), "real_s": round(real_s, 1),
                          "delta_s": round(real_s - plan_s, 1)})

    @property
    def primary_plan(self) -> Plan:
        return self.setup_.plan

    def _replan(self, idx: int, crossed: float, v: float) -> None:
        left = self.target_s - (crossed - self.t0)
        cap = capacity_at(self.curve, max(1.0, left))
        w, ok = self.setup_.planner.replan(idx, v, left, self.pace_floor_w, cap)
        self.watts[idx:] = [float(x) for x in w]
        self.reachable = ok
        self.replans += 1

    def _complete(self) -> list[tuple[str, dict]]:
        self.target_w = None
        self.finished = True
        self.won = self._won()
        return [("game_over", self.result())]

    def end(self) -> list[tuple[str, dict]]:
        if self.finished:
            return []
        self.finished = True
        self.target_w = None
        self.won = False if self.elapsed is None else self._won()
        return [("game_over", self.result())]

    def _won(self) -> bool:
        return self.elapsed is not None and self.elapsed <= self.target_s * (1 + TOL_PCT / 100.0)

    # --------------------------------------------------------------- 1 Hz

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        if self.phase == "lead":
            left = max(0.0, self.setup_.segment.start_m - self.pos)
            self.headline = tr("A caminho do segmento", "Heading to the segment")
            self.detail = tr("{name} · começa daqui a {m} m", "{name} · starts in {m} m",
                             name=self.seg_name, m=round(left))
            self.mood = "neutral"
            self.progress = 0.0
            self.target_w = None
            return []
        if self.phase != "run":
            return []
        self.sec_psum += power
        self.sec_pn += 1
        self.tot_psum += power
        self.tot_pn += 1
        seg = self.setup_.segment
        self.progress = max(0.0, min(1.0, (self.pos - seg.start_m) / seg.length_m))
        tau = self.now - self.t0
        gl = self.guides()
        main = self.main_guide(gl)
        self.delta_s = main[2] if main else 0.0
        self.headline, self.detail, self.mood = self._texts(tau)
        return []

    def main_guide(self, gl):
        """A guia do alvo principal (a primeira no Pace; a escolhida no KOM)."""
        return gl[self.main_index()] if gl else None

    def main_index(self) -> int:
        return 0

    def _texts(self, tau: float):
        raise NotImplementedError

    def _mood_for(self, delta_s: float) -> str:
        tol = max(1.0, self.target_s * TOL_PCT / 100.0)
        if abs(delta_s) <= tol:
            return "good"
        return "bad" if delta_s > 0 else "warn"

    # --------------------------------------------------------------- saída

    def summary_text(self) -> str:
        if self.elapsed is None:
            return tr("Segmento não concluído", "Segment not completed")
        d = self.elapsed - self.target_s
        return tr("{t} · {d} face ao alvo", "{t} · {d} vs target", t=hms(self.elapsed),
                  d=delta(d))

    def format_score(self, v: float) -> str:
        return hms(abs(v))

    def result(self) -> dict:
        s = self.setup_
        seg = s.segment if s else None
        avg = self.tot_psum / self.tot_pn if self.tot_pn else None
        others = []
        for label, tgt, _plan in getattr(self, "guide_list", []):
            others.append({"label": label, "target_s": round(tgt),
                           "delta_s": (None if self.elapsed is None
                                       else round(self.elapsed - tgt, 1))})
        return {"game": self.key, "score": -round(self.elapsed) if self.elapsed else None,
                "rank": None, "total": None, "won": self.won,
                "seconds": int(self.elapsed if self.elapsed is not None else self.t),
                "summary": self.summary_text(), "mode": self.mode,
                "segment": ({"key": seg.key, "id": seg.id, "source": seg.source,
                             "name": seg.name, "length_m": round(seg.length_m),
                             "grade": seg.avg_grade, "route_id": self.spec.get("route_id")}
                            if seg else None),
                "target": {"kind": self.spec.get("kind"), "label": s.label if s else "",
                           "s": round(self.target_s) if s else None},
                "elapsed_s": None if self.elapsed is None else round(self.elapsed, 1),
                "avg_w": None if avg is None else round(avg),
                "plan_avg_w": round(s.plan.avg_w) if s else None,
                "completed": self.elapsed is not None,
                "replans": self.replans, "others": others, "sections": list(self.rows)}

    def board(self, history: list | None = None) -> Board:
        rows = [Row(None, hms(self.target_s), tr("Alvo", "Target"))]
        if self.phase == "run" and self.progress > 0.02:
            proj = (self.now - self.t0) / self.progress
            rows.append(Row(None, hms(proj), tr("Projeção", "Projected"), me=True))
            rows.append(Row(None, delta(self.delta_s), tr("Diferença", "Gap")))
        for label, tgt, _p in self.guide_list[1:] if self.mode == KOM else []:
            rows.append(Row(None, hms(tgt), label))
        sub = (t("game.best", score=self.format_score(history[0])) if history
               else t("game.live"))
        return Board(self.seg_name if self.setup_ else self.title, rows, subtitle=sub)


class SegmentPace(SegmentGame):
    key = PACE
    mode = PACE
    erg_default = True

    def _texts(self, tau: float):
        i = min(self.idx, self.n_sections - 1)
        s = self.sections[i]
        left = max(0.0, s.end_m - self.pos)
        w = round(self.watts[i])
        head = tr("▶ {w} W", "▶ {w} W", w=w)
        det = tr("Secção {i}/{n} · {g} % · faltam {m} m · {d}",
                 "Section {i}/{n} · {g} % · {m} m to go · {d}", i=i + 1, n=self.n_sections,
                 g=f"{s.grade:.1f}", m=round(left), d=delta(self.delta_s))
        if not self.reachable:
            det += " · " + tr("alvo fora de alcance", "target out of reach")
        return head, det, self._mood_for(self.delta_s)


class SegmentKom(SegmentGame):
    key = KOM
    mode = KOM
    erg_default = False

    def main_index(self) -> int:
        for i, (_label, _t, plan) in enumerate(self.guide_list):
            if plan is self.setup_.plan:
                return i
        return 0

    def _texts(self, tau: float):
        i = min(self.idx, self.n_sections - 1)
        s = self.sections[i]
        left = max(0.0, s.end_m - self.pos)
        head = tr("KOM {x} · {d}", "KOM {x} · {d}", x=hms(self.target_s),
                  d=delta(self.delta_s))
        det = tr("Secção {i}/{n} · {g} % · faltam {m} m · ritmo do alvo {w} W",
                 "Section {i}/{n} · {g} % · {m} m to go · target pace {w} W", i=i + 1,
                 n=self.n_sections, g=f"{s.grade:.1f}", m=round(left),
                 w=round(self.setup_.plan.sections[i].watts))
        mood = "good" if self.delta_s <= 0 else ("warn" if self.delta_s < 10 else "bad")
        return head, det, mood

    def _won(self) -> bool:
        return self.elapsed is not None and self.elapsed < self.target_s


def create(cls, spec: dict, athlete, db, best: dict | None = None, **kw) -> SegmentGame:
    """Monta o jogo a partir do que o ecrã escolheu (`spec`): rota, segmento e alvo."""
    from . import segments as seg_mod
    route_id = spec.get("route_id")
    seg = next((s for s in seg_mod.load(db, route_id) if s.key == spec.get("segment")), None)
    if seg is None:
        raise ValueError(tr("O segmento já não existe nesta rota.",
                            "The segment no longer exists on this route."))
    if best is None:
        from . import stats
        best = dict(stats.power_curve(db, days=90))
    planner = planner_for(db, athlete, route_id, seg, best, spec.get("lead_in_m"))
    setup = prepare(planner, seg, cls.mode, spec.get("kind") or "", spec.get("value"))
    return cls(athlete.ftp_w, athlete.weight_kg, setup=setup, spec=spec, best=best,
               erg=spec.get("erg"), seed=spec.get("seed", 1), **kw)


# --------------------------------------------------------- histórico por segmento


def segment_history(db, seg_key: str, mode: str | None = None, limit: int = 10) -> list[dict]:
    """As sessões Pace/KOM neste segmento (as mais recentes primeiro)."""
    import json
    from .games import ensure_table
    ensure_table(db)
    keys = (mode,) if mode else (PACE, KOM)
    q = ",".join("?" * len(keys))
    out = []
    for r in db.conn.execute(
            f"SELECT game, score, won, seconds, details, created_at FROM game_results"
            f" WHERE game IN ({q}) ORDER BY id DESC", keys):
        try:
            d = json.loads(r["details"] or "{}")
        except ValueError:
            continue
        if (d.get("segment") or {}).get("key") != seg_key:
            continue
        out.append({"game": r["game"], "date": str(r["created_at"])[:10], "won": r["won"],
                    "elapsed_s": d.get("elapsed_s"), "target_s": (d.get("target") or {}).get("s"),
                    "label": (d.get("target") or {}).get("label", ""),
                    "avg_w": d.get("avg_w"), "completed": d.get("completed", False)})
        if len(out) >= limit:
            break
    return out


def history_board(db, seg_key: str, mode: str, title: str, limit: int = 8) -> Board:
    rows = []
    for i, h in enumerate(segment_history(db, seg_key, mode, limit), 1):
        if h["elapsed_s"] is None:
            continue
        label = h["date"] + (f" · {h['avg_w']} W" if h["avg_w"] else "")
        if h["target_s"]:
            label += " · " + delta(h["elapsed_s"] - h["target_s"])
        rows.append(Row(i, hms(h["elapsed_s"]), label))
    return Board(title, rows, empty=t("board.empty"))


# registo no Challenge (o módulo dos jogos não conhece este à partida)
from . import games as _games  # noqa: E402

_games.CLASSES[PACE] = SegmentPace
_games.CLASSES[KOM] = SegmentKom
