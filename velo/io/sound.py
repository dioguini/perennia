"""Os bips. Sem ficheiros nem bibliotecas: gera-se um tom (uma onda seno) em memória e toca-se
pelo pyglet; se não houver som no computador (ou na janela sem som), recorre-se ao
«beep» do terminal (o sino, `\\a`), que é o do altifalante da motherboard em muitos PC.
"""
from __future__ import annotations

import io
import math
import struct
import sys
import wave

RATE = 22050
TONES = {"short": (1000, 0.09), "long": (700, 0.45)}      # (Hz, segundos)


def tone_wav(freq: int, seconds: float, volume: float = 0.6) -> bytes:
    """Um tom em WAV (16 bits, mono) com uma entrada e uma saída suaves (sem estalidos)."""
    n = int(RATE * seconds)
    fade = max(1, int(RATE * 0.006))
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        v = int(32767 * volume * env * math.sin(2 * math.pi * freq * i / RATE))
        frames += struct.pack("<h", v)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))
    return buf.getvalue()


class Beeper:
    """`beep("short")` / `beep("long")`. Nunca falha: sem som, não toca (e avisa o terminal)."""

    def __init__(self) -> None:
        self._sources: dict = {}
        self._broken = False
        self.count = 0                    # quantos já tocou (para ver nos testes e no diagnóstico)

    def _source(self, kind: str):
        if kind not in self._sources:
            import pyglet
            freq, secs = TONES[kind]
            self._sources[kind] = pyglet.media.load(f"{kind}.wav",
                                                    file=io.BytesIO(tone_wav(freq, secs)),
                                                    streaming=False)
        return self._sources[kind]

    def beep(self, kind: str = "short") -> None:
        self.count += 1
        if not self._broken:
            try:
                self._source(kind).play()
                return
            except Exception:
                self._broken = True           # sem som aqui: passa para o sino do terminal
        try:
            if sys.stdout.isatty():
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception:
            pass


class SilentBeeper(Beeper):
    """Conta os bips mas não toca (os testes e a opção «sem som»)."""

    def __init__(self) -> None:
        super().__init__()
        self.log: list[str] = []

    def beep(self, kind: str = "short") -> None:
        self.count += 1
        self.log.append(kind)
