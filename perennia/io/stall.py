"""Deteção de pedais parados que continuam a emitir.

Um medidor de potência parado não se cala: repete a última mensagem, com a
última potência e a última cadência, até adormecer. A norma ANT+ diz que,
se o contador de eventos não mudar durante cerca de 3 s (12 mensagens a
4 Hz), o recetor deve mostrar potência e cadência a zero. O mesmo vale para
o Bluetooth com o contador de pedaladas.

Sem isto, parar de pedalar deixava a última potência no ecrã e o relógio a
contar, porque para a aplicação continuavas a pedalar.
"""
from __future__ import annotations

import time
from typing import Callable, Hashable

STALL_AFTER_S = 3.0


class StallDetector:
    def __init__(self, after_s: float = STALL_AFTER_S,
                 clock: Callable[[], float] = time.monotonic):
        self.after_s = after_s
        self.clock = clock
        self._last: dict[Hashable, tuple[object, float]] = {}

    def fresh(self, key: Hashable, counter: object) -> bool:
        """True se o contador mudou há menos de `after_s` segundos."""
        now = self.clock()
        prev = self._last.get(key)
        if prev is None or prev[0] != counter:
            self._last[key] = (counter, now)
            return True
        return now - prev[1] < self.after_s
