"""Física do ciclista e comando de resistência (req. 23, 24, 26).

Modelo clássico de Martin et al. (1998): a potência medida no trainer é
convertida em velocidade sobre o perfil real da rota. É isto que faz uma
subida de 8 % ser lenta mesmo com o mesmo esforço.
"""
from __future__ import annotations

import math

G = 9.80665
RHO = 1.225          # densidade do ar ao nível do mar, 15 °C
MAX_SPEED_MPS = 30.0  # 108 km/h: travão de segurança numérica

# Os trainers não produzem tração negativa útil; abaixo disto a roda
# apenas gira livre, por isso não vale a pena pedir mais.
MIN_TRAINER_GRADE = -5.0
MAX_TRAINER_GRADE = 25.0


def power_required(mass_kg: float, cda: float, crr: float, v: float, grade: float) -> float:
    """Potência (W) para manter `v` m/s num declive `grade` (fração)."""
    theta = math.atan(grade)
    f_grav = mass_kg * G * math.sin(theta)
    f_roll = mass_kg * G * crr * math.cos(theta)
    f_aero = 0.5 * RHO * cda * v * v
    return (f_grav + f_roll + f_aero) * v


def step_velocity(mass_kg: float, cda: float, crr: float, v: float, watts: float,
                  grade: float, dt: float) -> float:
    """Integra um passo de `dt` segundos e devolve a nova velocidade.

    Usa v_eff com um mínimo para evitar divisão por zero no arranque: à
    partida, com v = 0, a força motriz seria infinita. O mínimo de 1 m/s
    também garante que uns watts residuais de ruído não fazem a bicicleta
    arrastar-se sozinha quando o atleta parou de pedalar.
    """
    v_eff = max(v, 1.0)
    f_drive = watts / v_eff
    f_resist = power_required(mass_kg, cda, crr, v_eff, grade) / v_eff
    a = (f_drive - f_resist) / mass_kg
    return min(max(v + a * dt, 0.0), MAX_SPEED_MPS)


def trainer_grade(route_grade_pct: float, difficulty: float, extra_pct: float) -> float:
    """Declive a enviar ao trainer.

    `difficulty` (0–1.5) escala a sensação de declive: a 0.5, uma rampa de
    10 % sente-se como 5 %, mas a velocidade no mundo continua a ser
    calculada com os 10 % reais — tal como fazem as outras aplicações.
    `extra_pct` soma resistência de base, para endurecer o plano.
    """
    g = route_grade_pct * difficulty + extra_pct
    return min(max(g, MIN_TRAINER_GRADE), MAX_TRAINER_GRADE)


def torque_nm(watts: float | None, rpm: float | None) -> float | None:
    """Torque no eixo: τ = P / ω, com ω = rpm · 2π / 60."""
    if not watts or not rpm or rpm < 1.0:
        return None
    return watts / (rpm * 2.0 * math.pi / 60.0)


def speed_from_power(mass_kg: float, cda: float, crr: float, watts: float,
                     grade: float, tol: float = 0.01) -> float:
    """Velocidade de equilíbrio para uma potência constante (bissecção).

    Serve para estimativas (tempo restante), não para o loop da sessão.
    """
    if watts <= 0:
        return 0.0
    lo, hi = 0.0, MAX_SPEED_MPS
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if power_required(mass_kg, cda, crr, mid, grade) < watts:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2.0


def normalized_power(power_series: list[float]) -> float | None:
    """NP de Coggan: média móvel de 30 s, elevada a 4, média, raiz quarta."""
    if len(power_series) < 30:
        return None
    rolling: list[float] = []
    acc = 0.0
    for i, p in enumerate(power_series):
        acc += p
        if i >= 30:
            acc -= power_series[i - 30]
        if i >= 29:
            rolling.append(acc / 30.0)
    if not rolling:
        return None
    return (sum(r ** 4 for r in rolling) / len(rolling)) ** 0.25


def training_stress_score(np_w: float | None, ftp_w: int, seconds: int) -> float | None:
    """TSS = (s · NP · IF) / (FTP · 3600) · 100."""
    if not np_w or ftp_w <= 0 or seconds <= 0:
        return None
    intensity = np_w / ftp_w
    return seconds * np_w * intensity / (ftp_w * 3600.0) * 100.0


def power_curve(power_series: list[float],
                durations: tuple[int, ...] = (1, 5, 10, 15, 20, 30, 60, 120, 300, 600,
                                              1200, 1800, 3600)) -> list[tuple[int, float]]:
    """Melhor média para cada duração (MMP), com somas prefixadas."""
    n = len(power_series)
    if n == 0:
        return []
    prefix = [0.0]
    for p in power_series:
        prefix.append(prefix[-1] + p)
    out: list[tuple[int, float]] = []
    for d in durations:
        if d > n:
            continue
        best = max(prefix[i + d] - prefix[i] for i in range(n - d + 1)) / d
        out.append((d, best))
    return out


def zone_of(value: float, bounds_pct: list[float], reference: float) -> int:
    """Zona 1-based a partir de limiares em % de uma referência (FTP ou LTHR)."""
    if reference <= 0:
        return 1
    pct = value / reference * 100.0
    zone = 1
    for b in bounds_pct:
        if pct > b:
            zone += 1
        else:
            break
    return zone
