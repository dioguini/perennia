"""Fusão de vários sensores em simultâneo (req. 27).

O caso real: o trainer dá potência e cadência, e a frequência cardíaca vem
de uma cinta ou de um relógio. Se houver medidor de potência nos pedais,
esse tem prioridade sobre o trainer, mas a cadência pode continuar a vir do
trainer. Cada métrica escolhe a sua fonte por prioridade, e um valor que
pare de chegar é descartado por antiguidade em vez de ficar congelado no ecrã.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from velo.core.ride import Reading

METRICS = ("power", "cadence", "hr", "speed", "balance", "torque",
           "te_left", "te_right", "ps_left", "ps_right", "ps_combined")
PEDAL_METRICS = METRICS[6:]
STALE_AFTER_S = 5.0

# Prioridade por omissão: um sensor dedicado vale mais do que o trainer.
DEFAULT_PRIORITY = {
    "power_meter": {"power": 20, "cadence": 15, "balance": 20, "torque": 20,
                    "te_left": 20, "te_right": 20, "ps_left": 20, "ps_right": 20,
                    "ps_combined": 20},
    "hr_monitor": {"hr": 20},
    "speed_cadence": {"cadence": 12, "speed": 12},
    "trainer": {"power": 10, "cadence": 10, "speed": 10, "hr": 2},
    "simulated": {"power": 1, "cadence": 1, "hr": 1, "balance": 1},
}


@dataclass
class _Value:
    value: Any
    priority: int
    device_id: str
    at: float


class SensorHub:
    def __init__(self, stale_after_s: float = STALE_AFTER_S,
                 clock=time.monotonic):
        self._lock = threading.Lock()
        self._values: dict[str, list[_Value]] = {m: [] for m in METRICS}
        self._pull: list[tuple[Any, dict[str, int]]] = []
        self._stale = stale_after_s
        self._clock = clock
        self._seen: dict[str, float] = {}
        self.trainer: Any = None
        # Transporte preferido: ganha empates entre aparelhos do mesmo papel
        # (a Assioma por ANT+ e por Bluetooth ao mesmo tempo). Um ponto chega:
        # nunca passa à frente de um papel mais forte.
        self.preferred_transport: str | None = "ant"
        self.lost: list[str] = []          # perdidos desde o último aviso
        self.lost_set: set[str] = set()    # perdidos agora
        self.back: list[str] = []          # voltaram desde o último aviso
        self.names: dict[str, str] = {}

    # ------------------------------------------------------------ registo

    def add_source(self, source: Any, role: str = "trainer",
                   priority: dict[str, int] | None = None,
                   is_trainer: bool = False) -> None:
        """Adiciona uma fonte. `role` escolhe a tabela de prioridades."""
        prio = dict(DEFAULT_PRIORITY.get(role, DEFAULT_PRIORITY["trainer"]))
        if priority:
            prio.update(priority)
        transport = getattr(source, "transport", None)
        if transport and transport == self.preferred_transport:
            prio = {m: p + 1 for m, p in prio.items()}
            # métricas que o papel não lista entram com 10 por omissão
            for m in METRICS:
                prio.setdefault(m, 11)
        dev_id = getattr(source, "device_id", str(id(source)))
        self.names[dev_id] = getattr(source, "name", dev_id)
        if hasattr(source, "reading"):
            self._pull.append((source, prio))
        # Uma fonte declarada como trainer manda sempre. Só se infere pelo
        # facto de ter `set_sim` quando ainda não há nenhum declarado — senão
        # um sensor qualquer que exponha a interface rouba o papel.
        if is_trainer:
            self.trainer = source
        elif self.trainer is None and hasattr(source, "set_sim"):
            self.trainer = source
        setattr(source, "_hub_priority", prio)
        # Os adaptadores BLE e ANT+ empurram leituras com `self._priority`.
        # Sem isto, todos entravam com prioridade 10 e, num empate, ganhava a
        # leitura mais recente: a potência saltava entre pedais e rolo.
        if hasattr(source, "_priority"):
            source._priority = prio

    def remove_source(self, device_id: str) -> None:
        with self._lock:
            self._pull = [(s, p) for s, p in self._pull
                          if getattr(s, "device_id", None) != device_id]
            for m in METRICS:
                self._values[m] = [v for v in self._values[m] if v.device_id != device_id]
            self._seen.pop(device_id, None)
            self.lost_set.discard(device_id)
            if self.trainer is not None and getattr(self.trainer, "device_id", None) == device_id:
                self.trainer = None

    @property
    def sources(self) -> list[Any]:
        return [s for s, _ in self._pull]

    def has_power(self) -> bool:
        r = self.reading()
        return r.power_w is not None or r.speed_mps is not None

    # ----------------------------------------------------- entrada de dados

    def push(self, device_id: str, metric: str, value: Any, priority: int = 10) -> None:
        """Usado pelos adaptadores que recebem notificações (BLE, ANT+)."""
        if metric not in self._values or value is None:
            return
        now = self._clock()
        with self._lock:
            entries = [v for v in self._values[metric] if v.device_id != device_id]
            entries.append(_Value(value, priority, device_id, now))
            self._values[metric] = entries
            self._seen[device_id] = now

    def push_reading(self, device_id: str, r: Reading, priority: dict[str, int]) -> None:
        for metric, value in (("power", r.power_w), ("cadence", r.cadence_rpm),
                              ("hr", r.hr_bpm), ("speed", r.speed_mps),
                              ("balance", r.balance_left), ("torque", r.torque_nm)) + tuple(
                (m, getattr(r, m, None)) for m in PEDAL_METRICS):
            if value is not None:
                self.push(device_id, metric, value, priority.get(metric, 10))

    def tick(self, dt: float) -> None:
        """Avança as fontes que se simulam e recolhe as que se consultam."""
        for source, prio in list(self._pull):
            if hasattr(source, "tick"):
                try:
                    source.tick(dt)
                except Exception:
                    pass
            try:
                r = source.reading()
            except Exception:
                continue
            if r is not None:
                dev = getattr(source, "device_id", str(id(source)))
                self.push_reading(dev, r, prio)
        self._detect_lost()

    def _detect_lost(self) -> None:
        """Um aparelho que deixa de mandar dados fica «perdido» (avisa-se uma
        vez); quando volta, deixa de o estar."""
        now = self._clock()
        for dev, at in list(self._seen.items()):
            stale = now - at > self._stale
            if stale and dev not in self.lost_set:
                self.lost_set.add(dev)
                self.lost.append(dev)
            elif not stale and dev in self.lost_set:
                self.lost_set.discard(dev)
                self.back.append(dev)

    def check_lost(self) -> None:
        """Só verifica (não avança as fontes): a aplicação chama isto sempre."""
        self._detect_lost()

    def drain_lost(self) -> list[str]:
        """Os aparelhos que se perderam desde a última vez (cada um uma vez)."""
        out, self.lost = list(self.lost), []
        return [self.names.get(d, d) for d in out]

    def drain_back(self) -> list[str]:
        out, self.back = list(self.back), []
        return [self.names.get(d, d) for d in out]

    def is_lost(self, device_id: str) -> bool:
        return device_id in self.lost_set

    # ------------------------------------------------------------- saída

    def _best(self, metric: str) -> Any:
        now = self._clock()
        candidates = [v for v in self._values[metric] if now - v.at <= self._stale]
        if not candidates:
            return None
        return max(candidates, key=lambda v: (v.priority, v.at)).value

    def reading(self) -> Reading:
        with self._lock:
            power = self._best("power")
            cadence = self._best("cadence")
            hr = self._best("hr")
            speed = self._best("speed")
            balance = self._best("balance")
            torque = self._best("torque")
            pedal = {m: self._best(m) for m in PEDAL_METRICS}
        return Reading(
            **{m: (float(v) if v is not None else None) for m, v in pedal.items()},
            power_w=int(power) if power is not None else None,
            cadence_rpm=int(cadence) if cadence is not None else None,
            hr_bpm=int(hr) if hr is not None else None,
            speed_mps=float(speed) if speed is not None else None,
            balance_left=float(balance) if balance is not None else None,
            torque_nm=float(torque) if torque is not None else None,
        )

    def source_of(self, metric: str) -> str | None:
        """Qual o dispositivo que está a fornecer esta métrica, para a UI mostrar."""
        now = self._clock()
        with self._lock:
            candidates = [v for v in self._values.get(metric, [])
                          if now - v.at <= self._stale]
        if not candidates:
            return None
        best = max(candidates, key=lambda v: (v.priority, v.at))
        return self.names.get(best.device_id, best.device_id)

    # ------------------------------------------------- passagem ao trainer

    def set_sim(self, grade_pct: float, crr: float = 0.004, cda: float = 0.32) -> None:
        if self.trainer is not None:
            self.trainer.set_sim(grade_pct, crr, cda)

    def set_target_power(self, watts: int) -> None:
        if self.trainer is not None:
            self.trainer.set_target_power(watts)

    def set_user_weight(self, rider_kg: float, bike_kg: float) -> None:
        if self.trainer is not None and hasattr(self.trainer, "set_user_weight"):
            self.trainer.set_user_weight(rider_kg, bike_kg)

    def request_control(self) -> None:
        if self.trainer is not None:
            self.trainer.request_control()

    def release_control(self) -> None:
        if self.trainer is not None:
            self.trainer.release_control()

    def start_spindown(self) -> None:
        if self.trainer is not None and hasattr(self.trainer, "start_spindown"):
            self.trainer.start_spindown()

    @property
    def can_control(self) -> bool:
        return self.trainer is not None and hasattr(self.trainer, "set_sim")
