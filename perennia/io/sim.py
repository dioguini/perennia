"""Trainer simulado — permite usar e testar a aplicação sem hardware.

Não é um brinquedo: implementa a mesma interface que os adaptadores BLE e
ANT+, responde a comandos de declive e de ERG, e produz dados plausíveis.
É com ele que os testes do motor correm, e é ele que aparece na lista de
dispositivos quando não há nada emparelhado.
"""
from __future__ import annotations

import math
import random

from perennia.core.ride import Reading


class SimulatedTrainer:
    """Ciclista virtual. Em modo ERG segue o alvo; em simulação, aguenta
    uma potência de base e sobe um pouco quando a estrada inclina.

    Como um rolo a sério, só dá o que um rolo dá: potência, cadência (e o
    equilíbrio e a suavidade dos pedais). **Não dá frequência cardíaca** — essa
    vem da banda cardíaca (`SimulatedHeartStrap`); `with_hr=True` só serve
    para os testes que querem tudo num aparelho."""

    name = "SEM HARDWARE - Trainer"
    device_id = "sim:trainer"
    profiles = ("ftms", "cps", "hrs")
    supports_sim = True
    supports_erg = True
    supports_spindown = True

    def __init__(self, base_power: int = 180, seed: int | None = 7,
                 with_hr: bool = False, with_balance: bool = True):
        self.base_power = base_power
        self.with_hr = with_hr
        self.with_balance = with_balance
        self._rng = random.Random(seed)
        self._t = 0.0
        self._grade = 0.0
        self._target: int | None = None
        self._controlled = False
        self._hr = 95.0
        self._power = float(base_power)
        self._cadence = 85.0 if base_power > 0 else 0.0
        self.commands: list[tuple[str, float]] = []   # histórico, útil nos testes

    # ------------------------------------------------------------- controlo

    def request_control(self) -> None:
        self._controlled = True
        self.commands.append(("request_control", 0.0))

    def release_control(self) -> None:
        self._controlled = False
        self._target = None
        self.commands.append(("release_control", 0.0))

    def set_sim(self, grade_pct: float, crr: float = 0.004, cda: float = 0.32,
                wind_mps: float = 0.0) -> None:
        self._grade = grade_pct
        self._target = None
        self.commands.append(("set_sim", grade_pct))

    def set_target_power(self, watts: int) -> None:
        self._target = int(watts)
        self.commands.append(("set_target_power", float(watts)))

    def set_resistance_pct(self, pct: float) -> None:
        self.commands.append(("set_resistance_pct", pct))

    def set_user_weight(self, rider_kg: float, bike_kg: float) -> None:
        self.commands.append(("set_user_weight", rider_kg + bike_kg))

    def start_spindown(self) -> None:
        self.commands.append(("start_spindown", 0.0))

    # -------------------------------------------------------------- leitura

    def tick(self, dt: float) -> None:
        """Avança o ciclista virtual. A app chama isto quando usa o simulador."""
        self._t += dt
        if self._target is not None:
            want = float(self._target)
        else:
            # mais força a subir, menos a descer, com uma ondulação lenta
            want = self.base_power * (1.0 + 0.045 * self._grade)
            want *= 1.0 + 0.04 * math.sin(self._t / 23.0)
        # Um trainer real reporta 0 W quando se para de pedalar; o ruído só
        # faz sentido em cima de um esforço.
        if want > 0:
            want += self._rng.uniform(-8.0, 8.0)
        # a resposta do ciclista não é instantânea
        self._power += (max(0.0, want) - self._power) * min(1.0, dt * 1.5)

        if want > 0:
            cad_want = 88.0 - 1.6 * self._grade + self._rng.uniform(-2.0, 2.0)
            self._cadence += (max(50.0, min(110.0, cad_want)) - self._cadence) * min(1.0, dt)
        else:
            # pernas paradas: a cadência cai depressa para zero, como num trainer
            self._cadence = max(0.0, self._cadence - 60.0 * dt)

        if self.with_hr:
            hr_want = 95.0 + self._power * 0.26
            self._hr += (min(185.0, hr_want) - self._hr) * min(1.0, dt * 0.06)

    def reading(self) -> Reading:
        bal = None
        pedal: dict = {}
        if self.with_balance and self._power > 5:
            # Como uns pedais de duplo lado: perna esquerda um pouco mais fraca
            # (48–49 %), a variar devagar e a cada pedalada, e a piorar quando
            # se puxa mais (a perna dominante assume).
            effort = min(1.0, self._power / 300.0)
            bal = (48.8 - 1.2 * effort + 1.1 * math.sin(self._t / 37.0)
                   + 0.6 * math.sin(self._t / 5.3) + self._rng.uniform(-0.4, 0.4))
            # eficácia do binário ~75–80 % e suavidade ~20–25 %, por perna
            pedal = {"te_left": 77.0 + 2.0 * math.sin(self._t / 17.0),
                     "te_right": 79.0 + 2.0 * math.sin(self._t / 13.0),
                     "ps_left": 22.0 + 1.5 * math.sin(self._t / 19.0),
                     "ps_right": 23.5 + 1.5 * math.sin(self._t / 15.0)}
        return Reading(
            **pedal,
            power_w=int(round(self._power)),
            cadence_rpm=int(round(self._cadence)),
            hr_bpm=int(round(self._hr)) if self.with_hr else None,
            speed_mps=None,              # a velocidade vem da física, não do trainer
            balance_left=bal,
            torque_nm=None,
        )

    # --------------------------------------------------------------- estado

    @property
    def last_grade(self) -> float:
        return self._grade

    @property
    def last_target(self) -> int | None:
        return self._target

    @property
    def controlled(self) -> bool:
        return self._controlled


class SimulatedHeartStrap:
    """Banda cardíaca simulada («SEM HARDWARE - Banda cardíaca»): manda só a
    FC, como uma banda de peito. A FC segue o esforço da sessão — `effort`
    devolve o esforço de agora em fração do limiar (1.0 = no limiar; None =
    parado) — com o atraso de um coração verdadeiro e uma pequena variação.
    Serve todos os desportos (no ginásio, o esforço vem das séries)."""

    name = "SEM HARDWARE - Banda cardíaca"
    device_id = "sim:hr"
    profiles = ("hrs",)

    def __init__(self, effort=None, rest_bpm: int = 62, max_bpm: int = 188,
                 seed: int | None = 11):
        self.effort = effort
        self.rest_bpm = rest_bpm
        self.max_bpm = max_bpm
        self._rng = random.Random(seed)
        self._t = 0.0
        self._hr = float(rest_bpm + 8)

    def target(self) -> float:
        try:
            e = self.effort() if self.effort is not None else None
        except Exception:
            e = None
        if e is None:
            return self.rest_bpm + 8.0
        e = max(0.0, min(1.4, float(e)))
        # ~ 60 % da reserva no Z2, ~ 90 % no limiar, perto do máximo acima
        reserve = self.max_bpm - self.rest_bpm
        return self.rest_bpm + reserve * min(1.0, 0.25 + 0.68 * e)

    def tick(self, dt: float) -> None:
        self._t += dt
        want = self.target() + 1.5 * math.sin(self._t / 11.0)
        # o coração sobe mais depressa do que desce
        rate = 0.09 if want > self._hr else 0.05
        self._hr += (want - self._hr) * min(1.0, dt * rate)
        self._hr = max(40.0, min(float(self.max_bpm), self._hr))

    def reading(self) -> Reading:
        return Reading(hr_bpm=int(round(self._hr + self._rng.uniform(-0.6, 0.6))))


class SimulatedTreadmill:
    """Passadeira simulada («SEM HARDWARE - Passadeira»): recebe a velocidade e a
    inclinação (como uma passadeira FTMS), chega lá aos poucos e devolve o que
    uma passadeira dá — velocidade, inclinação e cadência dos passos. **Não dá
    FC** (vem da banda cardíaca)."""

    name = "SEM HARDWARE - Passadeira"
    device_id = "sim:treadmill"
    profiles = ("ftms-treadmill",)
    connected = True
    ACCEL_KMH_S = 0.8                 # km/h por segundo
    INCLINE_PCT_S = 0.5               # % por segundo

    def __init__(self, max_kmh: float = 20.0, max_incline: float = 15.0,
                 seed: int | None = 5):
        self.max_kmh = float(max_kmh)
        self.max_incline = float(max_incline)
        self._rng = random.Random(seed)
        self._target_kmh = 0.0
        self._target_incline = 0.0
        self.speed_kmh = 0.0
        self.incline_pct = 0.0
        self.commands: list[tuple[str, float]] = []

    def set_speed(self, kmh: float) -> None:
        self._target_kmh = max(0.0, min(self.max_kmh, float(kmh)))
        self.commands.append(("speed", self._target_kmh))

    def set_incline(self, pct: float) -> None:
        self._target_incline = max(0.0, min(self.max_incline, float(pct)))
        self.commands.append(("incline", self._target_incline))

    def tick(self, dt: float) -> None:
        step = self.ACCEL_KMH_S * dt
        self.speed_kmh += max(-step, min(step, self._target_kmh - self.speed_kmh))
        istep = self.INCLINE_PCT_S * dt
        self.incline_pct += max(-istep, min(istep, self._target_incline - self.incline_pct))

    def reading(self) -> Reading:
        cad = 0
        if self.speed_kmh > 3.0:
            cad = int(round(140 + 3.2 * (self.speed_kmh - 8.0) + self._rng.uniform(-1.5, 1.5)))
        return Reading(speed_mps=self.speed_kmh / 3.6, cadence_rpm=cad)

    def disconnect(self) -> None: ...


class ScriptedSource:
    """Fonte de leituras fixas, para testes determinísticos."""

    name = "Fonte de teste"
    device_id = "sim:scripted"

    def __init__(self, readings: list[Reading], loop: bool = True):
        self._readings = readings
        self._i = 0
        self._loop = loop

    def reading(self) -> Reading:
        if not self._readings:
            return Reading()
        r = self._readings[min(self._i, len(self._readings) - 1)]
        self._i += 1
        if self._loop and self._i >= len(self._readings):
            self._i = 0
        return r

    # a interface de trainer, sem efeito
    def request_control(self) -> None: ...
    def release_control(self) -> None: ...
    def set_sim(self, *a, **k) -> None: ...
    def set_target_power(self, *a, **k) -> None: ...
    def set_resistance_pct(self, *a, **k) -> None: ...
    def set_user_weight(self, *a, **k) -> None: ...
    def start_spindown(self) -> None: ...
    def tick(self, dt: float) -> None: ...
