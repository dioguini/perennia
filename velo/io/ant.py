"""ANT+ sobre USB: FE-C, medidor de potência e frequência cardíaca (req. 1, 26, 28).

O FE-C (Fitness Equipment Control) é o equivalente ANT+ do FTMS: é por ele
que se envia o declive e a potência alvo. A comunicação é feita diretamente
com a antena USB via pyusb, porque não existe uma biblioteca ANT+ estável e
multiplataforma que valha a dependência.

Como no módulo BLE, os descodificadores e os codificadores de página no topo
são funções puras com testes; a conversa com o rádio está isolada em baixo.
"""
from __future__ import annotations

import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from velo.core.ride import Reading
from velo.io.stall import StallDetector

# ----------------------------------------------------------------- constantes

ANT_VID = 0x0FCF
ANT_PIDS = (0x1008, 0x1009, 0x100B, 0x1004)   # ANTUSB2, ANTUSB-m, etc.

ANT_PLUS_NETWORK_KEY = bytes((0xB9, 0xA5, 0x21, 0xFB, 0xBD, 0x72, 0xC3, 0x45))
RF_FREQUENCY_ANT_PLUS = 57       # 2457 MHz
SYNC = 0xA4

# Mensagens do protocolo ANT.
MSG_RESET = 0x4A
MSG_SET_NETWORK_KEY = 0x46
MSG_UNASSIGN_CHANNEL = 0x41
MSG_ASSIGN_CHANNEL = 0x42
MSG_SET_CHANNEL_ID = 0x51
MSG_SET_RF_FREQ = 0x45
MSG_SET_PERIOD = 0x43
MSG_SET_SEARCH_TIMEOUT = 0x44
MSG_OPEN_CHANNEL = 0x4B
MSG_CLOSE_CHANNEL = 0x4C
MSG_BROADCAST_DATA = 0x4E
MSG_ACKNOWLEDGED_DATA = 0x4F
MSG_BURST_DATA = 0x50
MSG_CHANNEL_EVENT = 0x40
MSG_REQUEST = 0x4D
MSG_CHANNEL_ID = 0x51            # resposta a um pedido: o mesmo código do «set»
MSG_CHANNEL_STATUS = 0x52
MSG_CAPABILITIES = 0x54
MSG_ADD_TO_LIST = 0x59
MSG_CONFIG_LIST = 0x5A

# Códigos de evento de canal (mensagem 0x40, terceiro byte).
EVENT_RX_SEARCH_TIMEOUT = 0x01
EVENT_CHANNEL_CLOSED = 0x07
SEARCH_FOREVER = 0xFF            # tempo de procura infinito

CHANNEL_TYPE_SLAVE = 0x00        # recebe
CHANNEL_TYPE_SLAVE_SHARED = 0x20

# Tipos de dispositivo ANT+ e respectivos períodos de canal.
DEVICE_FEC = 17
DEVICE_POWER = 11
DEVICE_HR = 120
DEVICE_SPEED_CADENCE = 121

CHANNEL_PERIOD = {DEVICE_FEC: 8192, DEVICE_POWER: 8182, DEVICE_HR: 8070,
                  DEVICE_SPEED_CADENCE: 8086}

DEVICE_NAMES = {DEVICE_FEC: "Rolo FE-C", DEVICE_POWER: "Potência",
                DEVICE_HR: "Cardio", DEVICE_SPEED_CADENCE: "Velocidade/cadência"}


def device_name(device_type: int, number: int, note: str = "") -> str:
    base = DEVICE_NAMES.get(device_type, f"tipo {device_type}")
    return f"ANT+ {base} #{number}" + (f" ({note})" if note else "")


def parse_channel_id(payload: bytes) -> tuple[int, int, int] | None:
    """Resposta 0x51: (canal, número do dispositivo, tipo).

    O bit 7 do tipo é o de emparelhamento e não faz parte do tipo. Número 0
    quer dizer que o canal ainda não encontrou ninguém.
    """
    if len(payload) < 4:
        return None
    channel = payload[0]
    number = struct.unpack("<H", payload[1:3])[0]
    dtype = payload[3] & 0x7F
    return channel, number, dtype

# Páginas FE-C.
PAGE_CALIBRATION_REQUEST = 1
PAGE_CALIBRATION_PROGRESS = 2
PAGE_GENERAL_FE = 16
PAGE_GENERAL_SETTINGS = 17
PAGE_TRAINER_DATA = 25
PAGE_BASIC_RESISTANCE = 48
PAGE_TARGET_POWER = 49
PAGE_WIND_RESISTANCE = 50
PAGE_TRACK_RESISTANCE = 51
PAGE_FE_CAPABILITIES = 54
PAGE_USER_CONFIG = 55

TRAINER_STATUS = {0: "ok", 1: "a aguardar potência", 2: "calibração necessária",
                  3: "calibração em curso"}


# ------------------------------------------------------------ enquadramento


def checksum(frame: bytes) -> int:
    x = 0
    for b in frame:
        x ^= b
    return x


def build_message(msg_id: int, payload: bytes) -> bytes:
    """Monta uma mensagem ANT: SYNC, tamanho, id, dados, checksum."""
    head = bytes((SYNC, len(payload), msg_id))
    return head + payload + bytes((checksum(head + payload),))


def parse_messages(buffer: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """Extrai mensagens completas; devolve (mensagens, resto do buffer).

    O USB entrega blocos arbitrários, por isso é preciso guardar o que sobra
    entre leituras e descartar ruído até ao próximo SYNC.
    """
    out: list[tuple[int, bytes]] = []
    i = 0
    while i < len(buffer):
        if buffer[i] != SYNC:
            i += 1
            continue
        if i + 3 > len(buffer):
            break
        length = buffer[i + 1]
        total = 4 + length
        if i + total > len(buffer):
            break
        frame = buffer[i:i + total]
        if checksum(frame[:-1]) == frame[-1]:
            out.append((frame[2], frame[3:-1]))
            i += total
        else:
            i += 1          # checksum errado: salta um byte e tenta ressincronizar
    return out, buffer[i:]


# ------------------------------------------------------- codificação de páginas


def encode_track_resistance(grade_pct: float, crr: float = 0.004) -> bytes:
    """Página 51: simulação de terreno. É esta que faz o declive (req. 26).

    Declive em 0,01 % com deslocamento de −200 %; coeficiente de rolamento
    em passos de 5 × 10⁻⁵.
    """
    grade = max(0, min(0xFFFF, int(round((grade_pct + 200.0) * 100))))
    crr_raw = max(0, min(254, int(round(crr / 5e-5))))
    return struct.pack("<BBBBBHB", PAGE_TRACK_RESISTANCE, 0xFF, 0xFF, 0xFF, 0xFF,
                       grade, crr_raw)


def encode_target_power(watts: float) -> bytes:
    """Página 49: potência alvo em passos de 0,25 W (modo ERG)."""
    raw = max(0, min(0xFFFF, int(round(watts / 0.25))))
    return struct.pack("<BBBBBBH", PAGE_TARGET_POWER, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, raw)


def encode_basic_resistance(pct: float) -> bytes:
    """Página 48: resistência em passos de 0,5 %."""
    raw = max(0, min(200, int(round(pct / 0.5))))
    return struct.pack("<BBBBBBBB", PAGE_BASIC_RESISTANCE, 0xFF, 0xFF, 0xFF, 0xFF,
                       0xFF, 0xFF, raw)


def encode_user_config(rider_kg: float, bike_kg: float,
                       wheel_diameter_m: float = 0.7) -> bytes:
    """Página 55: peso do conjunto, para o trainer calcular a inércia."""
    user = max(0, min(0xFFFF, int(round(rider_kg / 0.01))))
    bike = max(0, min(0xFFF, int(round(bike_kg / 0.05))))
    diameter = max(0, min(254, int(round(wheel_diameter_m / 0.01))))
    # byte 4: nibble baixo = offset do diâmetro, nibble alto = LSN do peso
    b4 = ((bike & 0x0F) << 4) | 0x0F
    b5 = (bike >> 4) & 0xFF
    return struct.pack("<BHBBBBB", PAGE_USER_CONFIG, user, 0xFF, b4, b5, diameter, 0xFF)


def encode_calibration_request(spindown: bool = True, zero_offset: bool = False) -> bytes:
    """Página 1: pede calibração. O spindown é o teste de desaceleração (req. 28)."""
    flags = 0
    if zero_offset:
        flags |= 1 << 6
    if spindown:
        flags |= 1 << 7
    return struct.pack("<BBBBBBBB", PAGE_CALIBRATION_REQUEST, flags, 0xFF, 0xFF,
                       0xFF, 0xFF, 0xFF, 0xFF)


# ----------------------------------------------------- descodificação de páginas


def decode_general_fe(data: bytes) -> dict:
    """Página 16: velocidade, distância, frequência cardíaca."""
    if len(data) < 8:
        return {}
    speed_raw = struct.unpack("<H", data[4:6])[0]
    out: dict[str, Any] = {
        "elapsed_s": data[2] * 0.25,
        "distance_m": data[3],
        "state": (data[7] >> 4) & 0x07,
    }
    if speed_raw != 0xFFFF:
        out["speed_mps"] = speed_raw * 0.001
    if data[6] != 0xFF:
        out["hr_bpm"] = data[6]
    return out


def decode_trainer_data(data: bytes) -> dict:
    """Página 25: cadência e potência instantânea.

    A potência instantânea ocupa 12 bits: 8 no byte 5 e 4 no nibble baixo
    do byte 6, cujo nibble alto é o estado do trainer.
    """
    if len(data) < 8:
        return {}
    out: dict[str, Any] = {"event_count": data[1]}
    if data[2] != 0xFF:
        out["cadence_rpm"] = data[2]
    acc = struct.unpack("<H", data[3:5])[0]
    if acc != 0xFFFF:
        out["accumulated_power"] = acc
    power = data[5] | ((data[6] & 0x0F) << 8)
    if power != 0x0FFF:
        out["power_w"] = power
    status_bits = (data[6] >> 4) & 0x0F
    out["status_bits"] = status_bits
    out["calibration_needed"] = bool(status_bits & 0x01)
    out["flags"] = data[7]
    return out


def decode_power_only(data: bytes) -> dict:
    """Página 0x10 do perfil de potência: inclui o balanço esquerda/direita."""
    if len(data) < 8:
        return {}
    out: dict[str, Any] = {"event_count": data[1]}
    balance = data[2]
    if balance != 0xFF:
        # bit 7 indica que o valor se refere à perna direita
        pct = balance & 0x7F
        out["balance_left"] = float(100 - pct) if balance & 0x80 else float(pct)
    if data[3] != 0xFF:
        out["cadence_rpm"] = data[3]
    acc = struct.unpack("<H", data[4:6])[0]
    if acc != 0xFFFF:
        out["accumulated_power"] = acc
    power = struct.unpack("<H", data[6:8])[0]
    if power != 0xFFFF:
        out["power_w"] = power
    return out


def decode_te_ps(data: bytes) -> dict:
    """Página 0x13: eficácia do binário e suavidade da pedalada, por perna.

    Valores em passos de 0,5 % (0–200). 0xFF = não disponível. Se o byte da
    suavidade direita for 0xFE, o da esquerda é a suavidade combinada das
    duas pernas (medidores que não as separam).
    """
    if len(data) < 6:
        return {}

    def pct(b: int) -> float | None:
        return b / 2.0 if b <= 200 else None

    out: dict[str, Any] = {"event_count": data[1],
                           "te_left": pct(data[2]), "te_right": pct(data[3])}
    if data[5] == 0xFE:
        out["ps_combined"] = pct(data[4])
    else:
        out["ps_left"] = pct(data[4])
        out["ps_right"] = pct(data[5])
    return {k: v for k, v in out.items() if v is not None}


def decode_crank_torque(data: bytes) -> dict:
    """Página 0x12: torque acumulado, de onde sai o torque médio por pedalada."""
    if len(data) < 8:
        return {}
    return {
        "event_count": data[1],
        "crank_ticks": data[2],
        "cadence_rpm": data[3] if data[3] != 0xFF else None,
        "accumulated_period": struct.unpack("<H", data[4:6])[0],
        "accumulated_torque": struct.unpack("<H", data[6:8])[0],
    }


def decode_hr(data: bytes) -> dict:
    """Perfil de frequência cardíaca: o valor calculado está no último byte."""
    if len(data) < 8:
        return {}
    hr = data[7]
    return {"hr_bpm": hr} if hr not in (0, 0xFF) else {}


def decode_calibration_progress(data: bytes) -> dict:
    """Página 2: estado do spindown em curso."""
    if len(data) < 8:
        return {}
    temp = data[3]
    target_speed = struct.unpack("<H", data[6:8])[0]
    out: dict[str, Any] = {
        "spindown_pending": bool(data[1] & 0x80),
        "zero_offset_pending": bool(data[1] & 0x40),
    }
    if temp != 0xFF:
        out["temperature_c"] = temp * 0.5 - 25.0
    if target_speed != 0xFFFF:
        out["target_speed_mps"] = target_speed * 0.001
    return out


def decode_calibration_response(data: bytes) -> dict:
    """Página 1 enviada pelo trainer: resultado da calibração."""
    if len(data) < 8:
        return {}
    spindown_time = struct.unpack("<H", data[6:8])[0]
    return {
        "success": bool(data[1] & 0x80),
        "spindown_time_ms": spindown_time if spindown_time != 0xFFFF else None,
    }


def torque_from_crank(prev: dict, now: dict) -> float | None:
    """Torque médio (Nm) entre dois pacotes de torque de pedaleira."""
    if not prev or not now:
        return None
    d_event = (now["event_count"] - prev["event_count"]) % 256
    d_torque = (now["accumulated_torque"] - prev["accumulated_torque"]) % 65536
    if d_event == 0:
        return None
    return d_torque / (32.0 * d_event)


# ====================================================================
#  Parte dependente da pyusb.
# ====================================================================


def pyusb_available() -> bool:
    try:
        import usb.core  # noqa: F401
        return True
    except Exception:
        return False


def _backend() -> Any:
    """libusb vindo do pacote `libusb-package`, que traz a DLL no Windows e
    no macOS. Sem ele, a pyusb procura uma libusb instalada no sistema."""
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except Exception:
        return None


def find_stick() -> Any:
    """Procura a antena USB. None se não estiver ligada ou sem driver."""
    if not pyusb_available():
        return None
    import usb.core
    backend = _backend()
    for pid in ANT_PIDS:
        try:
            dev = usb.core.find(idVendor=ANT_VID, idProduct=pid, backend=backend)
        except Exception:
            dev = None
        if dev is not None:
            return dev
    try:
        return usb.core.find(idVendor=ANT_VID, backend=backend)
    except Exception:
        return None


def diagnose() -> str:
    """Explica porque é que a antena não aparece, em português simples."""
    if not pyusb_available():
        return "Falta a biblioteca pyusb: pip install pyusb libusb-package"
    import usb.core
    try:
        dev = usb.core.find(idVendor=ANT_VID, backend=_backend())
    except usb.core.NoBackendError:
        return ("Falta a libusb: pip install libusb-package "
                "(no Linux: sudo apt install libusb-1.0-0)")
    except Exception as e:
        return f"Erro ao procurar a antena: {e}"
    if dev is None:
        return ("Antena ANT+ não encontrada. Está ligada? No Windows precisa do "
                "driver WinUSB (Zadig) — vê o RUN.md, secção ANT+.")
    return ("A antena existe mas não abriu: no Windows, instala o driver WinUSB "
            "com o Zadig; no Linux, falta a regra udev (RUN.md, secção ANT+). "
            "Fecha também outras aplicações que a estejam a usar (Zwift, Garmin Express).")


@dataclass
class AntDiscovered:
    device_number: int
    device_type: int
    name: str
    trainer_twin: bool = False     # perfil de potência emitido pelo próprio rolo

    @property
    def device_id(self) -> str:
        return f"ant:{self.device_number}:{self.device_type}"

    @property
    def role(self) -> str:
        return {DEVICE_FEC: "trainer", DEVICE_POWER: "power_meter",
                DEVICE_HR: "hr_monitor",
                DEVICE_SPEED_CADENCE: "speed_cadence"}.get(self.device_type, "trainer")

    @property
    def can_control(self) -> bool:
        return self.device_type == DEVICE_FEC


class AntStick:
    """Antena ANT+. Abre canais de receção e envia páginas de controlo."""

    def __init__(self, on_event: Callable[[str, dict], None] | None = None):
        self.dev: Any = None
        self._ep_in: Any = None
        self._ep_out: Any = None
        self._buffer = b""
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False
        self._handlers: dict[int, Callable[[int, bytes], None]] = {}
        self._channels: dict[int, AntDiscovered] = {}
        self._channel_types: dict[int, int] = {}
        self._requested: set[int] = set()
        self._notes: dict[int, str] = {}
        self._on_event = on_event or (lambda kind, data: None)

    # ---------------------------------------------------------------- abrir

    def open(self) -> bool:
        self.dev = find_stick()
        if self.dev is None:
            return False
        import usb.util
        try:
            try:
                self.dev.set_configuration()
            except Exception:
                pass            # já configurada
            cfg = self.dev.get_active_configuration()
            intf = cfg[(0, 0)]
            self._ep_out = usb.util.find_descriptor(
                intf, custom_match=lambda e: usb.util.endpoint_direction(
                    e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
            self._ep_in = usb.util.find_descriptor(
                intf, custom_match=lambda e: usb.util.endpoint_direction(
                    e.bEndpointAddress) == usb.util.ENDPOINT_IN)
            if self._ep_in is None or self._ep_out is None:
                return False
        except Exception as e:
            self._on_event("ant_error", {"error": f"não foi possível abrir a antena: {e}"})
            return False

        self._send(MSG_RESET, bytes((0,)))
        time.sleep(0.6)
        self._send(MSG_SET_NETWORK_KEY, bytes((0,)) + ANT_PLUS_NETWORK_KEY)
        time.sleep(0.05)
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, name="ant", daemon=True)
        self._thread.start()
        return True

    def close(self) -> None:
        self._running = False
        for ch in list(self._channels):
            try:
                self._send(MSG_CLOSE_CHANNEL, bytes((ch,)))
            except Exception:
                pass
        try:
            self._send(MSG_RESET, bytes((0,)))
        except Exception:
            pass
        self._thread = None

    # -------------------------------------------------------------- envio

    def _send(self, msg_id: int, payload: bytes) -> None:
        if self._ep_out is None:
            return
        data = build_message(msg_id, payload)
        with self._lock:
            try:
                self._ep_out.write(data, timeout=1000)
            except Exception as e:
                self._on_event("ant_error", {"error": f"escrita falhou: {e}"})

    def open_channel(self, channel: int, device_type: int,
                     device_number: int = 0, exclude: tuple[int, ...] = (),
                     note: str = "", search_timeout: int = 30) -> None:
        """Abre um canal de receção. `device_number` 0 procura qualquer um.

        `exclude` são números de dispositivo a ignorar na procura: serve para
        o canal de potência não se agarrar ao rolo, que também emite como
        medidor de potência, e encontrar os pedais.
        """
        period = CHANNEL_PERIOD.get(device_type, 8192)
        self._channel_types[channel] = device_type
        if note:
            self._notes[channel] = note
        self._send(MSG_ASSIGN_CHANNEL, bytes((channel, CHANNEL_TYPE_SLAVE, 0)))
        time.sleep(0.02)
        self._send(MSG_SET_CHANNEL_ID,
                   struct.pack("<BHBB", channel, device_number, device_type, 0))
        time.sleep(0.02)
        if exclude:
            for i, number in enumerate(exclude[:4]):
                self._send(MSG_ADD_TO_LIST,
                           struct.pack("<BHBBB", channel, number, device_type, 0, i))
                time.sleep(0.02)
            self._send(MSG_CONFIG_LIST, bytes((channel, min(len(exclude), 4), 1)))
            time.sleep(0.02)
        self._send(MSG_SET_RF_FREQ, bytes((channel, RF_FREQUENCY_ANT_PLUS)))
        time.sleep(0.02)
        self._send(MSG_SET_PERIOD, struct.pack("<BH", channel, period))
        time.sleep(0.02)
        self._send(MSG_SET_SEARCH_TIMEOUT, bytes((channel, search_timeout)))  # × 2,5 s
        time.sleep(0.02)
        self._send(MSG_OPEN_CHANNEL, bytes((channel,)))

    def send_acknowledged(self, channel: int, page: bytes) -> None:
        """Páginas de controlo vão em modo confirmado: o trainer responde."""
        self._send(MSG_ACKNOWLEDGED_DATA, bytes((channel,)) + page[:8].ljust(8, b"\xff"))

    def on_broadcast(self, channel: int, handler: Callable[[int, bytes], None]) -> None:
        self._handlers[channel] = handler

    def close_channel(self, channel: int) -> None:
        self._handlers.pop(channel, None)
        self._send(MSG_CLOSE_CHANNEL, bytes((channel,)))

    def reopen(self, channel: int) -> None:
        """Volta a abrir um canal que fechou por ninguém responder.

        Os pedais adormecem parados; se a pausa passar do tempo de procura
        (cerca de 75 s), a antena fecha o canal. Reabre-se a procurar só esse
        aparelho, e sem limite de tempo: quando voltares a pedalar, ele acorda
        e é encontrado.
        """
        info = self._channels.get(channel)
        dtype = info.device_type if info else self._channel_types.get(channel, 0)
        number = info.device_number if info else 0
        self._send(MSG_UNASSIGN_CHANNEL, bytes((channel,)))
        time.sleep(0.02)
        self.open_channel(channel, dtype, number, search_timeout=SEARCH_FOREVER)

    def close_unused(self) -> None:
        """No fim da procura: fecha os canais que não encontraram ninguém."""
        for channel in list(self._channel_types):
            if channel not in self._channels:
                self._send(MSG_CLOSE_CHANNEL, bytes((channel,)))
                self._channel_types.pop(channel, None)

    @property
    def found(self) -> dict[int, AntDiscovered]:
        return dict(self._channels)

    # ------------------------------------------------------------- receção

    def _read_loop(self) -> None:
        while self._running:
            try:
                raw = self._ep_in.read(64, timeout=1000)
            except Exception:
                continue                     # tempo esgotado é normal
            self._buffer += bytes(raw)
            messages, self._buffer = parse_messages(self._buffer)
            for msg_id, payload in messages:
                self._dispatch(msg_id, payload)

    def _dispatch(self, msg_id: int, payload: bytes) -> None:
        if msg_id in (MSG_BROADCAST_DATA, MSG_ACKNOWLEDGED_DATA) and payload:
            channel = payload[0]
            # Primeiro dado num canal em procura: pergunta à antena quem é.
            # Ela só diz o número do dispositivo se lho pedirem.
            if channel not in self._channels and channel not in self._requested:
                self._requested.add(channel)
                self._send(MSG_REQUEST, bytes((channel, MSG_CHANNEL_ID)))
            handler = self._handlers.get(channel)
            if handler is not None:
                handler(channel, payload[1:9])
        elif msg_id == MSG_CHANNEL_EVENT and len(payload) >= 3:
            channel, code = payload[0], payload[2]
            self._on_event("ant_channel_event", {
                "channel": channel, "message": payload[1], "code": code})
            if (code == EVENT_CHANNEL_CLOSED and self._running
                    and channel in self._handlers):
                # um sensor em uso perdeu-se: volta a procurá-lo, noutro fio
                threading.Thread(target=self.reopen, args=(channel,),
                                 name=f"ant-reopen-{channel}", daemon=True).start()
        elif msg_id == MSG_CHANNEL_ID:
            parsed = parse_channel_id(payload)
            if parsed is None:
                return
            channel, number, dtype = parsed
            if number == 0:
                self._requested.discard(channel)      # ainda à procura: volta a pedir
                return
            dtype = dtype or self._channel_types.get(channel, 0)
            found = AntDiscovered(number, dtype,
                                  device_name(dtype, number, self._notes.get(channel, "")))
            self._channels[channel] = found
            self._on_event("ant_device_found", {"device": found})


class AntSensor:
    """Um dispositivo ANT+ num canal. Empurra leituras para o hub."""

    transport = "ant"

    def __init__(self, stick: Any, channel: int, info: AntDiscovered, hub: Any,
                 on_event: Callable[[str, dict], None] | None = None):
        self.stick = stick
        self.channel = channel
        self.info = info
        self.hub = hub
        self.name = info.name
        self.device_id = info.device_id
        self.profiles = ["fec"] if info.can_control else []
        self.connected = True
        self._prev_torque: dict = {}
        self._stall = StallDetector()
        self._on_event = on_event or (lambda kind, data: None)
        self._priority: dict[str, int] = {}
        stick.on_broadcast(channel, self._on_page)

    def _push(self, metric: str, value: Any) -> None:
        if value is not None:
            self.hub.push(self.device_id, metric, value, self._priority.get(metric, 10))

    def _on_page(self, _channel: int, data: bytes) -> None:
        """Os números de página só têm significado dentro de cada perfil:
        a 0x10 é a página geral num rolo FE-C e a de potência e balanço num
        medidor. Por isso decide-se primeiro pelo tipo de dispositivo."""
        if not data:
            return
        page = data[0] & 0x7F          # bit 7 = mudança de página (toggle), no cardio
        dtype = self.info.device_type
        if dtype == DEVICE_HR:
            self._push("hr", decode_hr(data).get("hr_bpm"))
        elif dtype == DEVICE_POWER:
            self._on_power_page(page, data)
        else:
            self._on_fec_page(page, data)

    def _on_power_page(self, page: int, data: bytes) -> None:
        if page == 0x10:
            d = decode_power_only(data)
            if not self._stall.fresh(0x10, d.get("event_count")):
                # pedais parados a repetir a última página: zero, como manda a norma
                self._push("power", 0)
                self._push("cadence", 0)
                return
            self._push("power", d.get("power_w"))
            self._push("cadence", d.get("cadence_rpm"))
            self._push("balance", d.get("balance_left"))
        elif page == 0x12:
            d = decode_crank_torque(data)
            if not self._stall.fresh(0x12, d.get("event_count")):
                self._push("cadence", 0)
                return
            nm = torque_from_crank(self._prev_torque, d)
            self._push("torque", nm)
            self._push("cadence", d.get("cadence_rpm"))
            self._prev_torque = d
        elif page == 0x13:
            d = decode_te_ps(data)
            if not self._stall.fresh(0x13, d.get("event_count")):
                return                    # parado: os valores antigos caducam sozinhos
            for key in ("te_left", "te_right", "ps_left", "ps_right", "ps_combined"):
                self._push(key, d.get(key))

    def _on_fec_page(self, page: int, data: bytes) -> None:
        if page == PAGE_TRAINER_DATA:
            d = decode_trainer_data(data)
            if not self._stall.fresh(PAGE_TRAINER_DATA, d.get("event_count")):
                self._push("power", 0)
                self._push("cadence", 0)
                return
            self._push("power", d.get("power_w"))
            self._push("cadence", d.get("cadence_rpm"))
            if d.get("calibration_needed"):
                self._on_event("calibration_needed", {"device": self.name})
        elif page == PAGE_GENERAL_FE:
            d = decode_general_fe(data)
            self._push("speed", d.get("speed_mps"))
            self._push("hr", d.get("hr_bpm"))
        elif page == PAGE_CALIBRATION_PROGRESS:
            self._on_event("calibration_progress", decode_calibration_progress(data))
        elif page == PAGE_CALIBRATION_REQUEST:
            self._on_event("calibration_result", decode_calibration_response(data))

    # ------------------------------------------------------ interface trainer

    def request_control(self) -> None:
        return None                 # no FE-C não há pedido de controlo explícito

    def release_control(self) -> None:
        self.set_sim(0.0)

    def set_sim(self, grade_pct: float, crr: float = 0.004, cda: float = 0.32,
                wind_mps: float = 0.0) -> None:
        self.stick.send_acknowledged(self.channel,
                                     encode_track_resistance(grade_pct, crr))

    def set_target_power(self, watts: int) -> None:
        self.stick.send_acknowledged(self.channel, encode_target_power(watts))

    def set_resistance_pct(self, pct: float) -> None:
        self.stick.send_acknowledged(self.channel, encode_basic_resistance(pct))

    def set_user_weight(self, rider_kg: float, bike_kg: float) -> None:
        self.stick.send_acknowledged(self.channel,
                                     encode_user_config(rider_kg, bike_kg))

    def start_spindown(self) -> None:
        self.stick.send_acknowledged(self.channel, encode_calibration_request(True))

    def reading(self) -> Reading | None:
        return None

    def tick(self, dt: float) -> None:
        return None

    def disconnect(self) -> None:
        self.connected = False
        try:
            self.stick.close_channel(self.channel)
        except Exception:
            pass

    @property
    def supports_sim(self) -> bool:
        return self.info.can_control

    @property
    def supports_erg(self) -> bool:
        return self.info.can_control

    @property
    def supports_spindown(self) -> bool:
        return self.info.can_control


def scan(timeout: float = 10.0,
         on_event: Callable[[str, dict], None] | None = None
         ) -> tuple[AntStick | None, list[tuple[int, AntDiscovered]]]:
    """Abre canais à procura de trainer, potência e cardio.

    Devolve a antena e os dispositivos encontrados. Sem antena ligada,
    devolve (None, []) — a aplicação segue com o Bluetooth.
    """
    stick = AntStick(on_event=on_event)
    if not stick.open():
        return None, []
    run_scan(stick, timeout)
    stick.close_unused()
    return stick, sorted(stick.found.items())


def run_scan(stick: Any, timeout: float = 10.0, sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic) -> None:
    """Procura rolo, potência e cardio, e trata do caso rolo + pedais.

    Um rolo FE-C costuma emitir também como medidor de potência, com o mesmo
    número. Se o canal de potência apanhar o rolo, abre-se outro canal de
    potência que o exclui — é esse que encontra os pedais (Assioma, Favero,
    Garmin Rally…).
    """
    for channel, dtype in enumerate((DEVICE_FEC, DEVICE_POWER, DEVICE_HR)):
        stick.open_channel(channel, dtype)
    deadline = clock() + timeout
    extra_opened = False
    while clock() < deadline:
        found = stick.found
        fec, power = found.get(0), found.get(1)
        if (not extra_opened and fec is not None and power is not None
                and fec.device_number == power.device_number):
            power.name = device_name(DEVICE_POWER, power.device_number, "do rolo")
            power.trainer_twin = True
            stick.open_channel(3, DEVICE_POWER, exclude=(fec.device_number,))
            extra_opened = True
            deadline = max(deadline, clock() + timeout / 2)
        expected = 4 if extra_opened else 3
        if len(found) >= expected:
            break
        sleep(0.25)
