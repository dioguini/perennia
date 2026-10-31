"""Modo fuga: pedalar para não ser apanhado pelo pelotão.

O pelotão parte atrás do atleta com uma vantagem fixa e acelera a cada
minuto, como num teste em rampa. Anda na mesma estrada, com o mesmo peso e
a mesma aerodinâmica do atleta, por isso só a potência decide: com a mesma
potência, a vantagem não muda.

A estrada muda o ritmo a que a vantagem fecha: a subir anda-se devagar e
o pelotão ganha menos metros por segundo. Por isso o resultado (o tempo que
o atleta aguentou) fica numa classificação por nível e por rota.

Nada aqui desenha nem fala com sensores. `step()` avança o pelotão e
devolve eventos que o motor da sessão passa ao HUD.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import physics

WAVE_S = 60.0                  # o pelotão acelera de minuto a minuto
HEAD_START_M = 150.0           # vantagem à partida
WARN_GAPS_M = (100.0, 50.0, 20.0)   # avisos à medida que se aproximam


@dataclass(frozen=True)
class ChaseLevel:
    id: str
    start_pct: float           # potência inicial do pelotão, em fração da FTP
    step_pct: float            # aumento por minuto, em fração da FTP


LEVELS: dict[str, ChaseLevel] = {
    "easy": ChaseLevel("easy", 0.50, 0.03),
    "normal": ChaseLevel("normal", 0.60, 0.04),
    "hard": ChaseLevel("hard", 0.70, 0.05),
}
LEVEL_ORDER = ("easy", "normal", "hard")


def minutes_to_ftp(level: ChaseLevel) -> float:
    """Minutos até o pelotão chegar aos 100 % da FTP. Ajuda a escolher."""
    if level.step_pct <= 0:
        return float("inf")
    return max(0.0, (1.0 - level.start_pct) / level.step_pct)


class Chase:
    """O pelotão. `rider_m` é sempre a distância total da sessão."""

    def __init__(self, level: str, ftp_w: int, mass_kg: float, cda: float, crr: float,
                 grade_at: Callable[[float], float] | None = None,
                 head_start_m: float = HEAD_START_M):
        self.level = LEVELS.get(level, LEVELS["normal"])
        self.ftp_w = max(1, int(ftp_w))
        self.mass_kg = mass_kg
        self.cda = cda
        self.crr = crr
        self.grade_at = grade_at
        self.dist_m = -head_start_m
        self.speed_mps = 0.0
        self.t_s = 0.0
        self.wave = 0
        self.active = True
        self.caught = False
        self.clean = True          # sem pausas manuais durante a fuga
        self.saved = False
        self._warned: set[float] = set()
        self._power_sum = 0.0
        self._power_n = 0
        self._rider_dist_start: float | None = None
        self.distance_m = 0.0      # distância do atleta durante a fuga

    # --------------------------------------------------------------- valores

    def watts_at(self, t_s: float) -> int:
        wave = int(t_s // WAVE_S)
        return int(round(self.ftp_w * (self.level.start_pct + self.level.step_pct * wave)))

    @property
    def watts(self) -> int:
        return self.watts_at(self.t_s)

    @property
    def next_wave_in_s(self) -> float:
        return WAVE_S - (self.t_s % WAVE_S)

    def gap_m(self, rider_m: float) -> float:
        return rider_m - self.dist_m

    def gap_s(self, rider_m: float) -> float:
        """Quanto tempo o pelotão demora a chegar onde o atleta está agora."""
        return self.gap_m(rider_m) / max(self.speed_mps, 1.0)

    @property
    def avg_power_w(self) -> float | None:
        return self._power_sum / self._power_n if self._power_n else None

    # ----------------------------------------------------------------- ciclo

    def observe_power(self, watts: int | None) -> None:
        """Chamado a 1 Hz com a potência do atleta, para a média da fuga."""
        if self.active and watts is not None:
            self._power_sum += watts
            self._power_n += 1

    def step(self, dt: float, rider_m: float) -> list[tuple[str, dict]]:
        if not self.active or dt <= 0:
            return []
        if self._rider_dist_start is None:
            self._rider_dist_start = rider_m
        events: list[tuple[str, dict]] = []
        self.t_s += dt
        wave = int(self.t_s // WAVE_S)
        if wave != self.wave:
            self.wave = wave
            events.append(("chase_wave", {"wave": wave, "watts": self.watts}))

        grade = 0.0
        if self.grade_at is not None:
            grade = self.grade_at(max(0.0, self.dist_m))
        self.speed_mps = physics.step_velocity(
            self.mass_kg, self.cda, self.crr, self.speed_mps, float(self.watts),
            grade / 100.0, dt)
        self.dist_m += self.speed_mps * dt
        self.distance_m = rider_m - self._rider_dist_start

        gap = self.gap_m(rider_m)
        for limit in WARN_GAPS_M:
            if gap < limit and limit not in self._warned:
                self._warned.add(limit)
                events.append(("chase_close", {"gap_m": gap, "limit_m": limit}))
            elif gap > limit * 1.6 and limit in self._warned:
                # abriu outra vez: volta a avisar se voltarem a aproximar-se
                self._warned.discard(limit)

        if gap <= 0.0:
            self.active = False
            self.caught = True
            self.dist_m = rider_m
            events.append(("chase_caught", {
                "survived_s": self.t_s, "watts": self.watts,
                "distance_m": self.distance_m}))
        return events

    def stop(self) -> None:
        """O atleta terminou a sessão antes de ser apanhado."""
        self.active = False
