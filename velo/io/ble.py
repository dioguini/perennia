"""Bluetooth Low Energy: FTMS, Cycling Power, Heart Rate, CSC (req. 1, 26, 27, 28).

O FTMS é obrigatório para controlar a resistência; o Cycling Power é lido em
paralelo porque é o único que transporta o balanço esquerda/direita e o
torque. Vários dispositivos podem estar ligados ao mesmo tempo.

Os descodificadores no topo do ficheiro são funções puras e têm testes. A
parte que fala com o rádio está em baixo, isolada, e só é importada quando
a `bleak` está instalada.
"""
from __future__ import annotations

import asyncio
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from velo.core.ride import Reading

# ------------------------------------------------------------------- UUIDs

BLUETOOTH_BASE = "-0000-1000-8000-00805f9b34fb"


def uuid16(value: int) -> str:
    """Expande um UUID de 16 bits para a forma completa que a bleak usa."""
    return f"{value:08x}"[-8:] + BLUETOOTH_BASE


SVC_FTMS = uuid16(0x1826)
SVC_CPS = uuid16(0x1818)
SVC_HRS = uuid16(0x180D)
SVC_CSCS = uuid16(0x1816)

CH_INDOOR_BIKE = uuid16(0x2AD2)
CH_FTMS_CONTROL = uuid16(0x2AD9)
CH_FTMS_STATUS = uuid16(0x2ADA)
CH_FTMS_FEATURE = uuid16(0x2ACC)
CH_CPS_MEASUREMENT = uuid16(0x2A63)
CH_HR_MEASUREMENT = uuid16(0x2A37)
CH_CSC_MEASUREMENT = uuid16(0x2A5B)

# Op-codes do FTMS Control Point.
OP_REQUEST_CONTROL = 0x00
OP_RESET = 0x01
OP_SET_TARGET_RESISTANCE = 0x04
OP_SET_TARGET_POWER = 0x05
OP_START_RESUME = 0x07
OP_STOP_PAUSE = 0x08
OP_SET_SIM = 0x11
OP_SPIN_DOWN = 0x13
OP_RESPONSE = 0x80

RESULT_TEXT = {
    0x01: "ok", 0x02: "op-code não suportado", 0x03: "parâmetro inválido",
    0x04: "falhou", 0x05: "controlo não permitido",
}


# -------------------------------------------------------------- codificação


def encode_sim(grade_pct: float, crr: float = 0.004, cw: float = 0.32,
               wind_mps: float = 0.0) -> bytes:
    """Set Indoor Bike Simulation Parameters.

    vento i16 (0,001 m/s) · declive i16 (0,01 %) · crr u8 (0,0001) ·
    cw u8 (0,01 kg/m). Os valores são truncados para o alcance do protocolo.
    """
    wind = max(-32768, min(32767, int(round(wind_mps * 1000))))
    grade = max(-32768, min(32767, int(round(grade_pct * 100))))
    crr_raw = max(0, min(255, int(round(crr / 0.0001))))
    cw_raw = max(0, min(255, int(round(cw / 0.01))))
    return struct.pack("<BhhBB", OP_SET_SIM, wind, grade, crr_raw, cw_raw)


def encode_target_power(watts: int) -> bytes:
    return struct.pack("<Bh", OP_SET_TARGET_POWER, max(-32768, min(32767, int(watts))))


RESISTANCE_LEVEL_MAX = 25.5     # uint8 com resolução 0,1


def encode_target_resistance_level(level: float) -> bytes:
    """Set Target Resistance Level (op 0x04).

    No FTMS este parâmetro é um uint8 com resolução 0,1, logo vai de 0 a
    25,5 — não é uma percentagem, e a escala é definida pelo fabricante.
    A aplicação não depende desta operação: a resistência extra é aplicada
    somando declive em modo de simulação, que é portável entre trainers.
    """
    raw = max(0, min(254, int(round(min(level, RESISTANCE_LEVEL_MAX) * 10))))
    return struct.pack("<BB", OP_SET_TARGET_RESISTANCE, raw)


def resistance_level_from_pct(pct: float) -> float:
    """Converte 0–100 % na escala de nível do FTMS, por aproximação linear."""
    return max(0.0, min(100.0, pct)) / 100.0 * RESISTANCE_LEVEL_MAX


def encode_spindown(start: bool = True) -> bytes:
    return struct.pack("<BB", OP_SPIN_DOWN, 0x01 if start else 0x02)


# ------------------------------------------------------------ descodificação


class _Cur:
    """Leitor little-endian tolerante a pacotes curtos."""

    def __init__(self, data: bytes):
        self.d = data
        self.i = 0

    def _take(self, n: int) -> bytes | None:
        if self.i + n > len(self.d):
            return None
        out = self.d[self.i:self.i + n]
        self.i += n
        return out

    def u8(self):
        b = self._take(1)
        return b[0] if b else None

    def i8(self):
        b = self._take(1)
        return struct.unpack("<b", b)[0] if b else None

    def u16(self):
        b = self._take(2)
        return struct.unpack("<H", b)[0] if b else None

    def i16(self):
        b = self._take(2)
        return struct.unpack("<h", b)[0] if b else None

    def u24(self):
        b = self._take(3)
        return struct.unpack("<I", b + b"\x00")[0] if b else None

    def u32(self):
        b = self._take(4)
        return struct.unpack("<I", b)[0] if b else None

    def skip(self, n: int):
        self.i += n


def parse_indoor_bike(data: bytes) -> Reading:
    """Indoor Bike Data (0x2AD2).

    Atenção ao bit 0: chama-se "More Data" e a semântica é invertida — a zero
    significa que a velocidade instantânea VEM no pacote.
    """
    c = _Cur(data)
    flags = c.u16() or 0
    r = Reading()
    if not flags & (1 << 0):
        v = c.u16()
        r.speed_mps = v * 0.01 / 3.6 if v is not None else None
    if flags & (1 << 1):
        c.skip(2)
    if flags & (1 << 2):
        v = c.u16()
        r.cadence_rpm = int(v * 0.5) if v is not None else None
    if flags & (1 << 3):
        c.skip(2)
    if flags & (1 << 4):
        c.u24()                      # distância total: usamos a nossa
    if flags & (1 << 5):
        c.i16()                      # nível de resistência
    if flags & (1 << 6):
        r.power_w = c.i16()
    if flags & (1 << 7):
        c.skip(2)
    if flags & (1 << 8):
        c.skip(5)                    # energia: total u16, por hora u16, por min u8
    if flags & (1 << 9):
        r.hr_bpm = c.u8()
    return r


def parse_cps(data: bytes) -> tuple[Reading, dict]:
    """Cycling Power Measurement (0x2A63).

    Devolve também os contadores acumulados: a cadência do CPS obtém-se da
    diferença entre pacotes, não vem pronta.
    """
    c = _Cur(data)
    flags = c.u16() or 0
    r = Reading()
    r.power_w = c.i16()
    raw: dict[str, Any] = {}
    if flags & (1 << 0):
        v = c.u8()
        if v is not None:
            r.balance_left = v * 0.5
    if flags & (1 << 2):
        v = c.u16()
        if v is not None:
            raw["torque_acc"] = v / 32.0
    if flags & (1 << 4):
        raw["wheel_revs"] = c.u32()
        raw["wheel_time"] = c.u16()
    if flags & (1 << 5):
        raw["crank_revs"] = c.u16()
        raw["crank_time"] = c.u16()
    return r, raw


def parse_hr(data: bytes) -> int | None:
    c = _Cur(data)
    flags = c.u8()
    if flags is None:
        return None
    return c.u16() if flags & 1 else c.u8()


def parse_csc(data: bytes) -> dict:
    c = _Cur(data)
    flags = c.u8() or 0
    out: dict[str, Any] = {}
    if flags & (1 << 0):
        out["wheel_revs"] = c.u32()
        out["wheel_time"] = c.u16()
    if flags & (1 << 1):
        out["crank_revs"] = c.u16()
        out["crank_time"] = c.u16()
    return out


def parse_ftms_feature(data: bytes) -> dict:
    """Fitness Machine Feature (0x2ACC): o que o trainer sabe medir e controlar."""
    if len(data) < 8:
        return {"sim": False, "erg": False, "spindown": False, "resistance": False,
                "power": False, "cadence": False}
    machine, target = struct.unpack("<II", data[:8])
    return {
        "cadence": bool(machine & (1 << 1)),
        "power": bool(machine & (1 << 14)),
        "heart_rate": bool(machine & (1 << 10)),
        "resistance": bool(target & (1 << 2)),
        "erg": bool(target & (1 << 3)),
        "sim": bool(target & (1 << 13)),
        "spindown": bool(target & (1 << 15)),
    }


def parse_control_response(data: bytes) -> tuple[int, int] | None:
    """(op-code pedido, resultado) de uma indicação do Control Point."""
    if len(data) < 3 or data[0] != OP_RESPONSE:
        return None
    return data[1], data[2]


def cadence_from_cranks(prev: dict, now: dict) -> float | None:
    """Cadência a partir de dois pacotes com contadores de pedalada.

    O tempo vem em 1/1024 s e dá a volta aos 65536; a subtração em módulo
    trata disso. Sem rotações novas, devolve 0 em vez de None: o atleta
    parou de pedalar, o que é informação e não ausência dela.
    """
    if "crank_revs" not in prev or "crank_revs" not in now:
        return None
    d_revs = (now["crank_revs"] - prev["crank_revs"]) % 65536
    d_time = (now["crank_time"] - prev["crank_time"]) % 65536
    if d_time == 0:
        return None
    rpm = d_revs / (d_time / 1024.0) * 60.0
    if rpm > 250.0:
        return None
    return rpm


def speed_from_wheel(prev: dict, now: dict, circumference_m: float = 2.096) -> float | None:
    if "wheel_revs" not in prev or "wheel_revs" not in now:
        return None
    d_revs = (now["wheel_revs"] - prev["wheel_revs"]) % (2 ** 32)
    d_time = (now["wheel_time"] - prev["wheel_time"]) % 65536
    if d_time == 0:
        return None
    mps = d_revs * circumference_m / (d_time / 1024.0)
    return mps if mps < 30.0 else None


def classify(service_uuids: list[str]) -> tuple[list[str], str]:
    """Dos serviços anunciados, deduz os perfis e o papel para as prioridades."""
    s = {u.lower() for u in service_uuids}
    profiles = []
    if SVC_FTMS in s:
        profiles.append("ftms")
    if SVC_CPS in s:
        profiles.append("cps")
    if SVC_HRS in s:
        profiles.append("hrs")
    if SVC_CSCS in s:
        profiles.append("cscs")
    if "ftms" in profiles:
        role = "trainer"
    elif "cps" in profiles:
        role = "power_meter"
    elif "hrs" in profiles:
        role = "hr_monitor"
    elif "cscs" in profiles:
        role = "speed_cadence"
    else:
        role = "trainer"
    return profiles, role


@dataclass
class Discovered:
    address: str
    name: str
    profiles: list[str]
    role: str
    rssi: int | None = None

    @property
    def device_id(self) -> str:
        return f"ble:{self.address}"

    @property
    def can_control(self) -> bool:
        return "ftms" in self.profiles


# ====================================================================
#  A partir daqui é a parte que precisa da biblioteca `bleak`.
# ====================================================================


def bleak_available() -> bool:
    try:
        import bleak  # noqa: F401
        return True
    except Exception:
        return False


class BleWorker:
    """Corre um ciclo asyncio num fio próprio.

    O resto da aplicação é síncrono (o ciclo de render), por isso toda a
    conversa com o rádio acontece aqui e os resultados são entregues por
    chamadas de retorno protegidas.
    """

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ble", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def submit(self, coro) -> Any:
        if self.loop is None:
            raise RuntimeError("fio BLE não arrancou")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, coro, timeout: float = 20.0) -> Any:
        return self.submit(coro).result(timeout=timeout)

    def stop(self) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread = None


_worker = BleWorker()


def scan(timeout: float = 8.0) -> list[Discovered]:
    """Procura dispositivos. Devolve lista vazia se não houver Bluetooth."""
    if not bleak_available():
        return []
    from bleak import BleakScanner

    async def _scan() -> list[Discovered]:
        found: list[Discovered] = []
        results = await BleakScanner.discover(timeout=timeout, return_adv=True)
        for address, (device, adv) in results.items():
            uuids = list(adv.service_uuids or [])
            profiles, role = classify(uuids)
            name = device.name or adv.local_name or ""
            if not profiles and not name:
                continue
            found.append(Discovered(address=address, name=name or "(sem nome)",
                                    profiles=profiles, role=role, rssi=adv.rssi))
        # dispositivos reconhecidos primeiro, depois por sinal
        found.sort(key=lambda d: (not d.profiles, -(d.rssi or -999)))
        return found

    _worker.start()
    try:
        return _worker.call(_scan(), timeout=timeout + 10.0)
    except Exception:
        return []


class BleSensor:
    """Um dispositivo BLE ligado. Empurra leituras para o hub.

    Implementa também a interface de trainer quando o dispositivo tem FTMS,
    para que o motor da sessão não tenha de saber de que transporte se trata.
    """

    transport = "ble"

    def __init__(self, info: Discovered, hub: Any,
                 on_event: Callable[[str, dict], None] | None = None):
        self.info = info
        self.hub = hub
        self.name = info.name
        self.device_id = info.device_id
        self.profiles = info.profiles
        self.features: dict = {}
        self.connected = False
        self._client: Any = None
        self._prev_cps: dict = {}
        self._prev_csc: dict = {}
        from velo.io.stall import StallDetector
        self._stall = StallDetector()
        self._on_event = on_event or (lambda kind, data: None)
        self._priority = {}
        self._pending_response: dict[int, float] = {}

    # ---------------------------------------------------------- ligação

    def connect(self, timeout: float = 20.0) -> bool:
        if not bleak_available():
            return False
        from bleak import BleakClient

        async def _connect() -> bool:
            client = BleakClient(self.info.address,
                                 disconnected_callback=self._on_disconnect)
            await client.connect()
            self._client = client
            services = {c.uuid.lower() for s in client.services for c in s.characteristics}

            if CH_FTMS_FEATURE in services:
                try:
                    raw = await client.read_gatt_char(CH_FTMS_FEATURE)
                    self.features = parse_ftms_feature(bytes(raw))
                except Exception:
                    self.features = {}

            for uuid, handler in (
                (CH_INDOOR_BIKE, self._on_indoor_bike),
                (CH_CPS_MEASUREMENT, self._on_cps),
                (CH_HR_MEASUREMENT, self._on_hr),
                (CH_CSC_MEASUREMENT, self._on_csc),
                (CH_FTMS_CONTROL, self._on_control),
                (CH_FTMS_STATUS, self._on_status),
            ):
                if uuid in services:
                    try:
                        await client.start_notify(uuid, handler)
                    except Exception:
                        pass
            return True

        _worker.start()
        try:
            self.connected = bool(_worker.call(_connect(), timeout=timeout))
        except Exception as e:
            self._on_event("connect_failed", {"device": self.name, "error": str(e)})
            self.connected = False
        if self.connected:
            self._on_event("connected", {"device": self.name,
                                         "features": self.features})
        return self.connected

    def _on_disconnect(self, _client: Any) -> None:
        self.connected = False
        self._on_event("disconnected", {"device": self.name})

    def disconnect(self) -> None:
        if self._client is None:
            return

        async def _dc():
            try:
                await self._client.disconnect()
            except Exception:
                pass
        try:
            _worker.call(_dc(), timeout=10.0)
        except Exception:
            pass
        self.connected = False

    # -------------------------------------------------------- notificações

    def _push(self, metric: str, value: Any) -> None:
        if value is None:
            return
        self.hub.push(self.device_id, metric, value,
                      self._priority.get(metric, 10))

    def _on_indoor_bike(self, _h: Any, data: bytearray) -> None:
        r = parse_indoor_bike(bytes(data))
        self._push("power", r.power_w)
        self._push("cadence", r.cadence_rpm)
        self._push("speed", r.speed_mps)
        self._push("hr", r.hr_bpm)

    def _on_cps(self, _h: Any, data: bytearray) -> None:
        r, raw = parse_cps(bytes(data))
        if "crank_revs" in raw and not self._stall.fresh("cranks", raw["crank_revs"]):
            # pedaleira parada a repetir a última notificação
            self._push("power", 0)
            self._push("cadence", 0)
            self._prev_cps = raw
            return
        self._push("power", r.power_w)
        self._push("balance", r.balance_left)
        rpm = cadence_from_cranks(self._prev_cps, raw)
        if rpm is not None:
            self._push("cadence", rpm)
        if "torque_acc" in raw and "torque_acc" in self._prev_cps:
            # o torque do CPS é acumulado; o instantâneo sai da potência
            pass
        if raw:
            self._prev_cps = raw

    def _on_hr(self, _h: Any, data: bytearray) -> None:
        self._push("hr", parse_hr(bytes(data)))

    def _on_csc(self, _h: Any, data: bytearray) -> None:
        now = parse_csc(bytes(data))
        rpm = cadence_from_cranks(self._prev_csc, now)
        if rpm is not None:
            self._push("cadence", rpm)
        mps = speed_from_wheel(self._prev_csc, now)
        if mps is not None:
            self._push("speed", mps)
        if now:
            self._prev_csc = now

    def _on_control(self, _h: Any, data: bytearray) -> None:
        parsed = parse_control_response(bytes(data))
        if parsed is None:
            return
        op, result = parsed
        self._on_event("control_response", {
            "op": op, "result": result, "ok": result == 0x01,
            "text": RESULT_TEXT.get(result, "desconhecido"), "device": self.name,
        })

    def _on_status(self, _h: Any, data: bytearray) -> None:
        self._on_event("machine_status", {"raw": bytes(data).hex(), "device": self.name})

    # ------------------------------------------------------ interface trainer

    def _write(self, payload: bytes) -> None:
        if self._client is None or not self.connected:
            return

        async def _w():
            try:
                await self._client.write_gatt_char(CH_FTMS_CONTROL, payload,
                                                   response=True)
            except Exception as e:
                self._on_event("write_failed", {"device": self.name, "error": str(e)})
        try:
            _worker.submit(_w())
        except Exception:
            pass

    def request_control(self) -> None:
        self._write(bytes([OP_REQUEST_CONTROL]))
        self._write(bytes([OP_START_RESUME]))

    def release_control(self) -> None:
        self._write(bytes([OP_RESET]))

    def set_sim(self, grade_pct: float, crr: float = 0.004, cda: float = 0.32,
                wind_mps: float = 0.0) -> None:
        self._write(encode_sim(grade_pct, crr, cda, wind_mps))

    def set_target_power(self, watts: int) -> None:
        self._write(encode_target_power(int(watts)))

    def set_resistance_pct(self, pct: float) -> None:
        self._write(encode_target_resistance_level(resistance_level_from_pct(pct)))

    def set_user_weight(self, rider_kg: float, bike_kg: float) -> None:
        # O FTMS não tem campo para o peso; a física é calculada na app.
        return None

    def start_spindown(self) -> None:
        self._write(encode_spindown(True))

    def reading(self) -> Reading | None:
        # As leituras chegam por notificação e vão diretas para o hub.
        return None

    def tick(self, dt: float) -> None:
        return None

    @property
    def supports_sim(self) -> bool:
        return self.features.get("sim", "ftms" in self.profiles)

    @property
    def supports_erg(self) -> bool:
        return self.features.get("erg", "ftms" in self.profiles)

    @property
    def supports_spindown(self) -> bool:
        return self.features.get("spindown", False)


def shutdown() -> None:
    _worker.stop()
