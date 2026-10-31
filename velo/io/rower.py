"""Máquinas de remo: Domyos (protocolo próprio por Bluetooth) e FTMS.

O protocolo da Domyos foi reimplementado a partir dos factos documentados no
projeto qdomyos-zwift (serviço, características, formato dos pacotes e
comandos); nenhum código desse projeto (GPLv3) foi copiado.

- Domyos Rowing 500B: serviço UART 49535343-…; cada trama começa por 0xF0 e
  termina com uma soma de controlo (soma dos bytes anteriores, & 0xFF). A
  máquina responde a uma consulta periódica (`f0 ac 9c`) com 26 bytes:
  remadas, ritmo por 500 m, remadas por minuto, kcal, distância, resistência
  (1–15) e FC. Não dá potência: calcula-se do ritmo com a fórmula da Concept2.
- FTMS Rower Data (0x2AD1): o padrão; é o que um Concept2 PM5 recente, e
  alguns Domyos, expõem.

As funções no topo são puras e têm testes. A parte do rádio está em baixo,
e só é usada com a `bleak` instalada. Nada disto foi testado numa máquina
real: os valores da Domyos podem precisar de afinação.
"""
from __future__ import annotations

import math
import random
import struct
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from velo.io.ble import SVC_FTMS, CH_FTMS_CONTROL, _Cur, uuid16

SVC_DOMYOS = "49535343-fe7d-4ae5-8fa9-9fafd205e455"
CH_DOMYOS_WRITE = "49535343-8841-43f4-a8d4-ecbe34729bb3"
CH_DOMYOS_NOTIFY = "49535343-1e4d-4bd9-ba61-23c647249616"
CH_ROWER_DATA = uuid16(0x2AD1)

RESISTANCE_MIN, RESISTANCE_MAX = 1, 15
STALE_AFTER_S = 5.0
MTU = 20


# ------------------------------------------------------------ ritmo e watts


def watts_from_pace(pace_s: float | None) -> int | None:
    """Fórmula da Concept2: P = 2,80 / (s/m)³, com o ritmo em s por 500 m."""
    if not pace_s or pace_s <= 0 or pace_s > 1200:
        return None
    return int(round(2.80 / (pace_s / 500.0) ** 3))


def pace_from_watts(watts: float | None) -> float | None:
    if not watts or watts <= 0:
        return None
    return 500.0 * (2.80 / watts) ** (1.0 / 3.0)


def speed_from_pace(pace_s: float | None) -> float:
    return 500.0 / pace_s if pace_s and pace_s > 0 else 0.0


def pace_text(pace_s: float | None) -> str:
    """1:52,3 → «1:52.3»; sem ritmo, «—»."""
    if not pace_s or pace_s <= 0 or pace_s > 1200:
        return "—"
    m, s = divmod(pace_s, 60)
    return f"{int(m)}:{s:04.1f}"


@dataclass
class RowerData:
    strokes: int | None = None
    spm: float | None = None
    pace_s: float | None = None          # s / 500 m
    power_w: int | None = None
    distance_m: float | None = None      # o total que a máquina conta (se der)
    kcal: float | None = None
    resistance: int | None = None
    hr_bpm: int | None = None
    elapsed_s: int | None = None
    source: str = ""

    @property
    def watts(self) -> int | None:
        return self.power_w if self.power_w else watts_from_pace(self.pace_s)


# --------------------------------------------------------------------- FTMS


def parse_ftms_rower(data: bytes) -> RowerData:
    """Rower Data (0x2AD1). Bit 0 a 0 = «há remadas»: ritmo de remada (0,5) e
    número de remadas vêm logo a seguir às flags."""
    c = _Cur(bytes(data))
    flags = c.u16() or 0
    out = RowerData(source="ftms")
    if not flags & 0x0001:
        spm = c.u8()
        out.spm = None if spm is None else spm / 2.0
        out.strokes = c.u16()
    if flags & 0x0002:
        c.u8()                                       # média de remadas por minuto
    if flags & 0x0004:
        out.distance_m = c.u24()
    if flags & 0x0008:
        p = c.u16()
        out.pace_s = float(p) if p else None
    if flags & 0x0010:
        c.u16()                                      # ritmo médio
    if flags & 0x0020:
        out.power_w = c.i16()
    if flags & 0x0040:
        c.i16()                                      # potência média
    if flags & 0x0080:
        r = c.i16()
        out.resistance = None if r is None else int(round(r / 10.0)) if r > 25 else r
    if flags & 0x0100:
        out.kcal = c.u16()
        c.u16()
        c.u8()
    if flags & 0x0200:
        out.hr_bpm = c.u8() or None
    if flags & 0x0400:
        c.u8()                                       # MET
    if flags & 0x0800:
        out.elapsed_s = c.u16()
    return out


def encode_ftms_resistance(level: int) -> bytes:
    """Set Target Resistance Level: uint8 com resolução 0,1."""
    lv = max(RESISTANCE_MIN, min(RESISTANCE_MAX, int(level)))
    return bytes([0x04, min(255, lv * 10)])


# ------------------------------------------------------------------- Domyos


def checksum(body: bytes) -> int:
    return sum(body) & 0xFF


def frame(body: bytes) -> bytes:
    return bytes(body) + bytes([checksum(body)])


def valid(packet: bytes) -> bool:
    return len(packet) >= 3 and packet[0] == 0xF0 and packet[-1] == checksum(packet[:-1])


DOMYOS_POLL = frame(b"\xf0\xac")                     # f0 ac 9c
DOMYOS_INIT = [frame(bytes(b)) for b in (
    (0xF0, 0xC8, 0x01), (0xF0, 0xC9), (0xF0, 0xA3), (0xF0, 0xA4), (0xF0, 0xA5),
    (0xF0, 0xAB), (0xF0, 0xC4, 0x03))]


def encode_domyos_resistance(level: int) -> bytes:
    lv = max(RESISTANCE_MIN, min(RESISTANCE_MAX, int(level)))
    body = bytearray([0xF0, 0xAD] + [0xFF] * 20)
    body[10] = lv
    body[17] = 0x00
    body[18] = 0x01
    return frame(bytes(body))


def chunks(payload: bytes, size: int = MTU) -> list[bytes]:
    return [payload[i:i + size] for i in range(0, len(payload), size)]


def parse_domyos(packet: bytes) -> RowerData | None:
    """Pacote de estado de 26 bytes (os outros ignoram-se)."""
    p = bytes(packet)
    if len(p) != 26 or p[0] != 0xF0:
        return None
    strokes = (p[2] << 8) | p[3]
    raw_pace = (p[6] << 8) | p[7]
    spm = p[9]
    pace = float(raw_pace) if 0 < raw_pace < 65000 and spm > 0 else None
    res = p[14] if RESISTANCE_MIN <= p[14] <= RESISTANCE_MAX else None
    hr = p[18] or None
    return RowerData(strokes=strokes, spm=float(spm), pace_s=pace,
                     power_w=None, distance_m=((p[12] << 8) | p[13]) / 10.0,
                     kcal=float((p[10] << 8) | p[11]), resistance=res, hr_bpm=hr,
                     source="domyos")


def build_domyos_packet(strokes: int = 0, pace_s: float | None = None, spm: int = 0,
                        kcal: int = 0, distance_raw: int = 0, resistance: int = 1,
                        hr: int = 0) -> bytes:
    """Monta um pacote de estado, para os testes e o simulador."""
    p = bytearray(26)
    p[0], p[1] = 0xF0, 0xBC
    p[2:4] = struct.pack(">H", strokes & 0xFFFF)
    p[6:8] = struct.pack(">H", int(pace_s) if pace_s else 0)
    p[9] = spm & 0xFF
    p[10:12] = struct.pack(">H", kcal & 0xFFFF)
    p[12:14] = struct.pack(">H", distance_raw & 0xFFFF)
    p[14] = resistance & 0xFF
    p[18] = hr & 0xFF
    p[25] = checksum(bytes(p[:25]))
    return bytes(p)


def is_rower(name: str, service_uuids: list[str]) -> str | None:
    """«domyos», «ftms» ou None, pelo anúncio (nome e serviços)."""
    s = {u.lower() for u in service_uuids}
    n = (name or "").upper()
    if SVC_DOMYOS in s or n.startswith("DOMYOS-ROW"):
        return "domyos"
    if n.startswith("PM5") or ("ROW" in n and SVC_FTMS in s):
        return "ftms"
    return None


# ================================================================ simulador


class SimulatedRower:
    """Remador virtual: rema a ~24 spm e responde à resistência."""

    name = "Remo simulado"
    device_id = "sim:rower"
    protocol = "sim"
    connected = True

    def __init__(self, watts: float = 160.0, spm: float = 24.0, seed: int | None = 3,
                 with_hr: bool = True):
        self.base_w = watts
        self.base_spm = spm
        self.with_hr = with_hr
        self.level = 6
        self.rowing = True
        self._rng = random.Random(seed)
        self._t = 0.0
        self._strokes = 0.0
        self._dist = 0.0
        self._kcal = 0.0
        self._hr = 90.0
        self._w = 0.0
        self.commands: list[tuple[str, int]] = []

    def set_resistance(self, level: int) -> None:
        self.level = max(RESISTANCE_MIN, min(RESISTANCE_MAX, int(level)))
        self.commands.append(("resistance", self.level))

    def tick(self, dt: float) -> None:
        self._t += dt
        want = 0.0
        if self.rowing:
            want = self.base_w * (0.85 + 0.025 * self.level)
            want *= 1.0 + 0.05 * math.sin(self._t / 19.0) + self._rng.uniform(-0.03, 0.03)
        self._w += (want - self._w) * min(1.0, dt * 1.2)
        if self.rowing:
            spm = self.base_spm + 0.15 * (self.level - 6)
            self._strokes += spm / 60.0 * dt
            pace = pace_from_watts(self._w)
            self._dist += speed_from_pace(pace) * dt
            self._kcal += (self._w * 4 + 300) / 4184 * dt
        if self.with_hr:
            target = 90 + self._w * 0.42
            self._hr += (min(188.0, target) - self._hr) * min(1.0, dt * 0.05)

    def data(self) -> RowerData | None:
        spm = self.base_spm + 0.15 * (self.level - 6) if self.rowing and self._w > 15 else 0.0
        pace = pace_from_watts(self._w) if spm else None
        return RowerData(strokes=int(self._strokes), spm=round(spm, 1), pace_s=pace,
                         power_w=None, distance_m=self._dist, kcal=self._kcal,
                         resistance=self.level,
                         hr_bpm=int(self._hr) if self.with_hr else None, source="sim")

    def disconnect(self) -> None: ...


class ScriptedRower:
    """Leituras fixas, para testes determinísticos do motor."""

    name = "Remo de teste"
    device_id = "sim:rower-script"
    protocol = "sim"
    connected = True

    def __init__(self, data: RowerData):
        self.current = data
        self.commands: list[tuple[str, int]] = []

    def set_resistance(self, level: int) -> None:
        self.commands.append(("resistance", int(level)))
        self.current = replace(self.current, resistance=int(level))

    def tick(self, dt: float) -> None: ...

    def data(self) -> RowerData | None:
        return self.current

    def disconnect(self) -> None: ...


# ===================================================================== rádio


class RowerSensor:
    """Uma máquina de remo ligada por Bluetooth (Domyos ou FTMS)."""

    transport = "ble"

    def __init__(self, address: str, name: str, protocol: str | None = None,
                 on_event: Callable[[str, dict], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.address = address
        self.name = name or "Remo"
        self.device_id = f"rower:{address}"
        self.protocol = protocol or "auto"
        self.connected = False
        self._client: Any = None
        self._latest: RowerData | None = None
        self._at = 0.0
        self._clock = clock
        self._poll = 0.0
        self._want_level: int | None = None
        self._on_event = on_event or (lambda kind, data: None)

    # ---- dados recebidos

    def feed(self, packet: bytes) -> None:
        """Chamado pelas notificações (e pelos testes)."""
        data = parse_domyos(packet) if self.protocol == "domyos" else parse_ftms_rower(packet)
        if data is None:
            return
        self._latest = data
        self._at = self._clock()

    def data(self) -> RowerData | None:
        if self._latest is None or self._clock() - self._at > STALE_AFTER_S:
            return None
        return self._latest

    # ---- ligação

    def connect(self, timeout: float = 20.0) -> bool:
        from velo.io import ble
        if not ble.bleak_available():
            return False
        from bleak import BleakClient

        async def _connect() -> bool:
            client = BleakClient(self.address, disconnected_callback=self._lost)
            await client.connect()
            self._client = client
            chars = {c.uuid.lower() for s in client.services for c in s.characteristics}
            if self.protocol == "auto":
                self.protocol = "domyos" if CH_DOMYOS_NOTIFY in chars else "ftms"
            if self.protocol == "domyos":
                await client.start_notify(CH_DOMYOS_NOTIFY, lambda _h, d: self.feed(bytes(d)))
                for f in DOMYOS_INIT:
                    await client.write_gatt_char(CH_DOMYOS_WRITE, f, response=False)
            else:
                await client.start_notify(CH_ROWER_DATA, lambda _h, d: self.feed(bytes(d)))
                if CH_FTMS_CONTROL in chars:
                    try:
                        await client.start_notify(CH_FTMS_CONTROL, lambda _h, d: None)
                        await client.write_gatt_char(CH_FTMS_CONTROL, b"\x00", response=True)
                    except Exception:
                        pass
            return True

        ble._worker.start()
        try:
            self.connected = bool(ble._worker.call(_connect(), timeout=timeout))
        except Exception as e:
            self._on_event("connect_failed", {"device": self.name, "error": str(e)})
            self.connected = False
        if self.connected:
            self._on_event("connected", {"device": self.name, "protocol": self.protocol})
        return self.connected

    def _lost(self, _c: Any) -> None:
        self.connected = False
        self._on_event("disconnected", {"device": self.name})

    def disconnect(self) -> None:
        from velo.io import ble
        if self._client is None:
            return

        async def _dc():
            try:
                await self._client.disconnect()
            except Exception:
                pass
        try:
            ble._worker.call(_dc(), timeout=10.0)
        except Exception:
            pass
        self.connected = False

    def _write(self, payload: bytes) -> None:
        from velo.io import ble
        if self._client is None or not self.connected:
            return
        domyos = self.protocol == "domyos"

        async def _w():
            try:
                if domyos:
                    for part in chunks(payload):
                        await self._client.write_gatt_char(CH_DOMYOS_WRITE, part,
                                                           response=False)
                else:
                    await self._client.write_gatt_char(CH_FTMS_CONTROL, payload, response=True)
            except Exception as e:
                self._on_event("write_failed", {"device": self.name, "error": str(e)})
        try:
            ble._worker.submit(_w())
        except Exception:
            pass

    # ---- comandos

    def set_resistance(self, level: int) -> None:
        self._want_level = max(RESISTANCE_MIN, min(RESISTANCE_MAX, int(level)))
        self._write(encode_domyos_resistance(self._want_level) if self.protocol == "domyos"
                    else encode_ftms_resistance(self._want_level))

    def tick(self, dt: float) -> None:
        """A Domyos só manda dados quando é consultada: ~2 vezes por segundo."""
        if self.protocol != "domyos" or not self.connected:
            return
        self._poll += dt
        if self._poll >= 0.5:
            self._poll = 0.0
            self._write(DOMYOS_POLL)


def scan_rowers(timeout: float = 8.0) -> list[tuple[str, str, str]]:
    """[(endereço, nome, protocolo)] das máquinas de remo à volta."""
    from velo.io import ble
    if not ble.bleak_available():
        return []
    from bleak import BleakScanner

    async def _scan():
        out = []
        res = await BleakScanner.discover(timeout=timeout, return_adv=True)
        for address, (dev, adv) in res.items():
            name = dev.name or adv.local_name or ""
            kind = is_rower(name, list(adv.service_uuids or []))
            if kind:
                out.append((address, name or "Remo", kind))
        return out

    ble._worker.start()
    try:
        return ble._worker.call(_scan(), timeout=timeout + 10.0)
    except Exception:
        return []
