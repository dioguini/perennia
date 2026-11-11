"""GPX Conversor: de um percurso (.gpx) para um treino manual.

Um rolo ou uma passadeira sem controlo não seguem o percurso sozinhos — és tu que
mudas o nível ou a inclinação. O conversor traduz o perfil do percurso em blocos:

1. a altitude é **alisada** com uma média móvel (`window_m`: 20, 50, 100, 200 m…),
   porque o GPS "treme" e daria subidas e descidas falsas;
2. o percurso parte-se em **troços** de `seg_m` metros e cada troço fica com a sua
   inclinação média. Troços mais curtos seguem o terreno com mais fidelidade —
   e mandam-te mexer no aparelho mais vezes (mais oscilações manuais);
3. a inclinação traduz-se numa regulação do aparelho, por uma **fórmula**:

   Passadeira (corrida)
     * `direct`      inclinação = inclinação do troço (descidas ficam a 0 %);
     * `calibrated`  como a anterior menos 1 %, a compensação habitual da falta de
                     resistência do ar na passadeira (a 1 % corresponde à estrada plana);
     * `effort`      a inclinação anterior **e** uma velocidade que mantém o esforço
                     constante (custo energético de Minetti: sobe devagar, desce depressa).
   Rolo (ciclismo)
     * `linear`      nível = % da FTP plana + ganho × inclinação;
     * `physics`     a força para manter a mesma velocidade na inclinação, relativa à da
                     estrada plana, a partir da física da bicicleta — elevada a 0,4 para o
                     nível do rolo não saturar (a 6 % a força é ~5× a da plana; o nível, ~1,9×).

4. troços seguidos com a mesma regulação juntam-se num só (menos mudanças).

A inclinação respeita o **passo** da tua passadeira (0,1 · 0,5 · 1 %) e o máximo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import physics
from .blocks import Block

RUN_FORMULAS = ("direct", "calibrated", "effort")
BIKE_FORMULAS = ("linear", "physics")
WINDOWS_M = (20, 50, 100, 200)
SEGMENTS_M = (100, 200, 500, 1000)
SPEED_MODES = ("free", "constant", "effort")        # a velocidade na corrida
GRID_M = 10.0

NAMES = {
    "direct": ("Inclinação direta", "Direct incline"),
    "calibrated": ("Inclinação com calibração de 1 %", "Incline with 1 % calibration"),
    "effort": ("Esforço constante (inclinação + ritmo)", "Constant effort (incline + pace)"),
    "linear": ("Linear (ganho por % de inclinação)", "Linear (gain per % of grade)"),
    "physics": ("Física (mesma velocidade)", "Physics (same speed)"),
    "free": ("Livre — decides tu", "Free — you decide"),
    "constant": ("Constante", "Constant"),
}


@dataclass
class Params:
    sport: str = "running"                  # running | cycling
    formula: str = "direct"
    window_m: int = 50
    seg_m: int = 200
    speed_mode: str = "effort"              # corrida: livre · constante · esforço constante
    speed_kmh: float = 10.0                 # velocidade plana (corrida)
    flat_pct: float = 65.0                  # ciclismo: intensidade plana (% da FTP)
    gain: float = 6.0                       # ciclismo: % da FTP por 1 % de inclinação
    incline_step: float = 0.5
    max_incline: float = 15.0
    max_kmh: float = 20.0
    ref_kmh: float = 25.0                   # ciclismo: velocidade de referência
    weight_kg: float = 75.0
    bike_kg: float = 9.0
    cda: float = 0.32
    crr: float = 0.004
    ftp_w: int = 200


@dataclass
class Section:
    """Um troço do percurso e o que se regula nele."""
    start_m: float
    length_m: float
    grade_pct: float
    setting: float                          # corrida: inclinação · ciclismo: % da FTP
    speed_kmh: float | None = None


# ------------------------------------------------------------------- perfil


def profile(points) -> list[tuple[float, float]]:
    """[(distância, altitude)] dos pontos de uma rota (objetos com `dist_m`/`ele_m`)."""
    out = []
    for p in points:
        d = getattr(p, "dist_m", None)
        e = getattr(p, "ele_m", None)
        if d is None:
            continue
        out.append((float(d), float(e or 0.0)))
    return out


def resample(pts: list[tuple[float, float]], step: float = GRID_M) -> list[float]:
    """As altitudes numa grelha regular (de `step` em `step` metros)."""
    if len(pts) < 2:
        return []
    total = pts[-1][0]
    n = int(total // step) + 1
    out, j = [], 0
    for i in range(n):
        d = i * step
        while j + 1 < len(pts) - 1 and pts[j + 1][0] < d:
            j += 1
        (d0, e0), (d1, e1) = pts[j], pts[j + 1]
        f = 0.0 if d1 <= d0 else max(0.0, min(1.0, (d - d0) / (d1 - d0)))
        out.append(e0 + (e1 - e0) * f)
    return out


def moving_average(values: list[float], window_m: float, step: float = GRID_M) -> list[float]:
    """Média móvel centrada (janela de `window_m` metros)."""
    k = max(0, int(round(window_m / step / 2)))
    if k == 0 or not values:
        return list(values)
    out = []
    csum = [0.0]
    for v in values:
        csum.append(csum[-1] + v)
    n = len(values)
    for i in range(n):
        a, b = max(0, i - k), min(n, i + k + 1)
        out.append((csum[b] - csum[a]) / (b - a))
    return out


def section_grades(smooth: list[float], seg_m: float, step: float = GRID_M) -> list[tuple[
        float, float, float]]:
    """[(início, comprimento, inclinação %)] dos troços de `seg_m` (o último pode ser mais
    curto): a inclinação é a do perfil alisado do início ao fim do troço."""
    n_seg = max(1, int(round(seg_m / step)))
    out = []
    i = 0
    while i < len(smooth) - 1:
        j = min(len(smooth) - 1, i + n_seg)
        length = (j - i) * step
        if length <= 0:
            break
        out.append((i * step, length, (smooth[j] - smooth[i]) / length * 100.0))
        i = j
    return out


# ----------------------------------------------------------------- fórmulas


def minetti_cost(grade_frac: float) -> float:
    """Custo energético de correr (J/kg/m) numa inclinação (fração, de −0,45 a 0,45)."""
    g = max(-0.45, min(0.45, grade_frac))
    return 155.4 * g ** 5 - 30.4 * g ** 4 - 43.3 * g ** 3 + 46.3 * g ** 2 + 19.5 * g + 3.6


def quantize(value: float, step: float, top: float) -> float:
    step = step if step > 0 else 0.5
    return max(0.0, min(top, round(round(value / step) * step, 2)))


def run_setting(grade: float, p: Params) -> tuple[float, float | None]:
    """(inclinação da passadeira, velocidade em km/h ou None se livre) para um troço."""
    g = grade - 1.0 if p.formula == "calibrated" else grade
    incline = quantize(max(0.0, g), p.incline_step, p.max_incline)
    if p.speed_mode == "free":
        return incline, None
    if p.speed_mode == "constant" or p.formula != "effort":
        return incline, min(p.max_kmh, p.speed_kmh)
    # esforço constante: v · custo(inclinação) = v_plano · custo(0)
    v = p.speed_kmh * minetti_cost(0.0) / minetti_cost(incline / 100.0)
    return incline, max(3.0, min(p.max_kmh, round(v, 1)))


def bike_pct(grade: float, p: Params) -> float:
    """A intensidade (% da FTP) a pôr no rolo para um troço."""
    if p.formula == "physics":
        mass = p.weight_kg + p.bike_kg
        v = p.ref_kmh / 3.6
        flat = physics.power_required(mass, p.cda, p.crr, v, 0.0)
        here = physics.power_required(mass, p.cda, p.crr, v, grade / 100.0)
        ratio = here / flat if flat > 0 else 1.0
        pct = p.flat_pct * max(ratio, 0.05) ** 0.4        # amortecida: a 6 % não são 5× mais
    else:
        pct = p.flat_pct + p.gain * grade
    return max(40.0, min(140.0, pct))


def sections(points, p: Params) -> list[Section]:
    """Os troços do percurso com a regulação de cada um (já juntos os iguais)."""
    pts = profile(points)
    smooth = moving_average(resample(pts), p.window_m)
    raw = section_grades(smooth, p.seg_m)
    out: list[Section] = []
    for start, length, grade in raw:
        if p.sport == "running":
            setting, speed = run_setting(grade, p)
        else:
            setting, speed = bike_pct(grade, p), None
            setting = round(setting)                      # o nível do rolo é inteiro
        if out and out[-1].setting == setting and out[-1].speed_kmh == speed:
            last = out[-1]
            last.grade_pct = (last.grade_pct * last.length_m + grade * length) / \
                (last.length_m + length)
            last.length_m += length
            continue
        out.append(Section(start, length, grade, setting, speed))
    return out


def _bike_speed_kmh(grade_pct: float, p: Params) -> float:
    """A velocidade com que se percorre um troço de ciclismo (para o tempo do bloco)."""
    if p.formula == "physics":
        return p.ref_kmh
    return max(8.0, min(p.ref_kmh * 1.6, p.ref_kmh * (1.0 - 0.06 * grade_pct)))


def to_blocks(secs: list[Section], p: Params, ctx_pct_from_pace=None) -> list[Block]:
    """Os blocos do construtor. Corrida: com velocidade, por tempo; livre, por distância.
    Ciclismo: por tempo, ao nível (% da FTP) de cada troço."""
    blocks: list[Block] = []
    for s in secs:
        if p.sport == "running":
            extra = {"incline_pct": s.setting} if s.setting else {}
            if s.speed_kmh:
                extra["speed_kmh"] = s.speed_kmh
                lo = ctx_pct_from_pace(3600 / s.speed_kmh) if ctx_pct_from_pace else 75.0
                b = Block(kind="active", dur_type="time", dur=max(10.0, round(
                    s.length_m / (s.speed_kmh / 3.6))), lo=lo, hi=None, extra=extra)
            else:
                b = Block(kind="active", dur_type="distance", dur=round(s.length_m), lo=75.0,
                          hi=None, extra=extra)
        else:
            v = _bike_speed_kmh(s.grade_pct, p) / 3.6
            b = Block(kind="active", dur_type="time", dur=max(10.0, round(s.length_m / v)),
                      lo=float(s.setting), hi=None, extra={})
        b.cue = f"{s.start_m / 1000:.1f}–{(s.start_m + s.length_m) / 1000:.1f} km · " \
                f"{s.grade_pct:+.1f} %"
        blocks.append(b)
    if blocks:
        blocks[0].kind = "warmup" if len(blocks) > 2 else blocks[0].kind
    return blocks


def summary(points, secs: list[Section]) -> dict:
    pts = profile(points)
    total = pts[-1][0] if pts else 0.0
    ele = [e for _d, e in pts]
    ascent = sum(max(0.0, b - a) for a, b in zip(ele, ele[1:]))
    return {"km": total / 1000.0, "ascent_m": ascent, "blocks": len(secs),
            "max_grade": max((s.grade_pct for s in secs), default=0.0),
            "changes": max(0, len(secs) - 1)}
