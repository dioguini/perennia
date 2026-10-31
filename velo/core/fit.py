"""Codificador de ficheiros .FIT (req. 11).

Escrito do zero sobre a especificação FIT, sem dependências. Produz um
ficheiro de atividade que o Garmin Connect, o Strava e o Intervals.icu
aceitam por upload manual.

Estrutura: cabeçalho de 14 bytes · mensagens de definição e de dados ·
CRC-16 final. Cada tipo de mensagem é definido uma vez e depois repetido
em modo compacto.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .db import Athlete, Lap, RideSummary, Sample

# A época do FIT é 1989-12-31T00:00:00Z, não a do Unix.
FIT_EPOCH = 631_065_600
SEMICIRCLES = 2 ** 31 / 180.0

PROFILE_VERSION = 2140
PROTOCOL_VERSION = 0x20
MANUFACTURER_DEVELOPMENT = 255

# (código do tipo base, tamanho em bytes, valor "inválido")
_BASE = {
    "enum":    (0x00, 1, b"\xff"),
    "sint8":   (0x01, 1, b"\x7f"),
    "uint8":   (0x02, 1, b"\xff"),
    "sint16":  (0x83, 2, b"\x7f\xff"),
    "uint16":  (0x84, 2, b"\xff\xff"),
    "sint32":  (0x85, 4, b"\x7f\xff\xff\xff"),
    "uint32":  (0x86, 4, b"\xff\xff\xff\xff"),
    "uint8z":  (0x0a, 1, b"\x00"),
    "uint16z": (0x8b, 2, b"\x00\x00"),
    "uint32z": (0x8c, 4, b"\x00\x00\x00\x00"),
    "string":  (0x07, 0, b""),          # tamanho fixo por campo, terminado em zero
}
_PACK = {
    "enum": "<B", "uint8": "<B", "uint8z": "<B", "sint8": "<b",
    "uint16": "<H", "uint16z": "<H", "sint16": "<h",
    "uint32": "<I", "uint32z": "<I", "sint32": "<i",
}

_CRC_TABLE = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
              0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)


def crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        for nibble in (byte & 0x0F, byte >> 4):
            tmp = _CRC_TABLE[crc & 0x0F]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ _CRC_TABLE[nibble]
    return crc


def to_fit_time(unix_seconds: float) -> int:
    return max(0, int(unix_seconds) - FIT_EPOCH)


def to_semicircles(degrees: float) -> int:
    return int(round(degrees * SEMICIRCLES))


@dataclass(frozen=True)
class Field:
    name: str
    num: int
    type: str
    scale: float = 1.0
    offset: float = 0.0
    length: int = 0                     # só para "string"

    @property
    def size(self) -> int:
        return self.length if self.type == "string" else _BASE[self.type][1]

    def encode(self, value: Any) -> bytes:
        if self.type == "string":
            return encode_string(value, self.length)
        code, size, invalid = _BASE[self.type]
        if value is None:
            return invalid
        try:
            raw = int(round((float(value) + self.offset) * self.scale))
        except (TypeError, ValueError):
            return invalid
        fmt = _PACK[self.type]
        lo, hi = _limits(self.type)
        if raw < lo or raw > hi:
            return invalid
        return struct.pack(fmt, raw)


def encode_string(value: Any, length: int) -> bytes:
    """UTF-8, cortado sem partir caracteres, com zero no fim e preenchido."""
    raw = str(value or "").encode("utf-8")
    if len(raw) > length - 1:
        raw = raw[:length - 1].decode("utf-8", "ignore").encode("utf-8")
    return raw + b"\x00" * (length - len(raw))


def _limits(t: str) -> tuple[int, int]:
    if t in ("enum", "uint8", "uint8z"):
        return 0, 0xFE
    if t == "sint8":
        return -0x80, 0x7E
    if t in ("uint16", "uint16z"):
        return 0, 0xFFFE
    if t == "sint16":
        return -0x8000, 0x7FFE
    if t in ("uint32", "uint32z"):
        return 0, 0xFFFFFFFE
    return -0x80000000, 0x7FFFFFFE


# ------------------------------------------------------- definições de mensagem

MSG_FILE_ID, MSG_USER_PROFILE, MSG_DEVICE_INFO, MSG_SPORT = 0, 3, 23, 12
NAME_LEN = 64
MSG_SESSION, MSG_LAP, MSG_RECORD, MSG_EVENT, MSG_ACTIVITY = 18, 19, 20, 21, 34

FILE_ID = (MSG_FILE_ID, [
    Field("type", 0, "enum"),
    Field("manufacturer", 1, "uint16"),
    Field("product", 2, "uint16"),
    Field("serial_number", 3, "uint32z"),
    Field("time_created", 4, "uint32"),
])

USER_PROFILE = (MSG_USER_PROFILE, [
    Field("message_index", 254, "uint16"),
    Field("age", 2, "uint8"),
    Field("weight", 4, "uint16", scale=10),
    Field("functional_threshold_power", 33, "uint16"),
])

DEVICE_INFO = (MSG_DEVICE_INFO, [
    Field("timestamp", 253, "uint32"),
    Field("device_index", 0, "uint8"),
    Field("manufacturer", 2, "uint16"),
    Field("product", 4, "uint16"),
    Field("software_version", 5, "uint16", scale=100),
])

EVENT = (MSG_EVENT, [
    Field("timestamp", 253, "uint32"),
    Field("event", 0, "enum"),
    Field("event_type", 1, "enum"),
])

RECORD = (MSG_RECORD, [
    Field("timestamp", 253, "uint32"),
    Field("position_lat", 0, "sint32"),
    Field("position_long", 1, "sint32"),
    Field("altitude", 2, "uint16", scale=5, offset=500),
    Field("heart_rate", 3, "uint8"),
    Field("cadence", 4, "uint8"),
    Field("distance", 5, "uint32", scale=100),
    Field("speed", 6, "uint16", scale=1000),
    Field("power", 7, "uint16"),
    Field("grade", 9, "sint16", scale=100),
    Field("left_right_balance", 30, "uint8"),
    Field("left_torque_effectiveness", 43, "uint8", scale=2),
    Field("right_torque_effectiveness", 44, "uint8", scale=2),
    Field("left_pedal_smoothness", 45, "uint8", scale=2),
    Field("right_pedal_smoothness", 46, "uint8", scale=2),
    Field("combined_pedal_smoothness", 47, "uint8", scale=2),
])

# Perfil desportivo: é aqui que vai o nome da atividade e o «virtual».
SPORT = (MSG_SPORT, [
    Field("sport", 0, "enum"),
    Field("sub_sport", 1, "enum"),
    Field("name", 3, "string", length=NAME_LEN),
])

LAP = (MSG_LAP, [
    Field("timestamp", 253, "uint32"),
    Field("message_index", 254, "uint16"),
    Field("event", 0, "enum"),
    Field("event_type", 1, "enum"),
    Field("start_time", 2, "uint32"),
    Field("total_elapsed_time", 7, "uint32", scale=1000),
    Field("total_timer_time", 8, "uint32", scale=1000),
    Field("total_distance", 9, "uint32", scale=100),
    Field("avg_speed", 13, "uint16", scale=1000),
    Field("avg_heart_rate", 15, "uint8"),
    Field("max_heart_rate", 16, "uint8"),
    Field("avg_cadence", 17, "uint8"),
    Field("avg_power", 19, "uint16"),
    Field("max_power", 20, "uint16"),
    Field("total_ascent", 21, "uint16"),
    Field("lap_trigger", 24, "enum"),
    Field("sport", 25, "enum"),
    Field("left_right_balance", 37, "uint16"),
    Field("sub_sport", 39, "enum"),
    Field("avg_left_torque_effectiveness", 91, "uint8", scale=2),
    Field("avg_right_torque_effectiveness", 92, "uint8", scale=2),
    Field("avg_left_pedal_smoothness", 93, "uint8", scale=2),
    Field("avg_right_pedal_smoothness", 94, "uint8", scale=2),
    Field("avg_combined_pedal_smoothness", 95, "uint8", scale=2),
])

SESSION = (MSG_SESSION, [
    Field("timestamp", 253, "uint32"),
    Field("message_index", 254, "uint16"),
    Field("event", 0, "enum"),
    Field("event_type", 1, "enum"),
    Field("start_time", 2, "uint32"),
    Field("sport", 5, "enum"),
    Field("sub_sport", 6, "enum"),
    Field("total_elapsed_time", 7, "uint32", scale=1000),
    Field("total_timer_time", 8, "uint32", scale=1000),
    Field("total_distance", 9, "uint32", scale=100),
    Field("total_calories", 11, "uint16"),
    Field("avg_speed", 14, "uint16", scale=1000),
    Field("max_speed", 15, "uint16", scale=1000),
    Field("avg_heart_rate", 16, "uint8"),
    Field("max_heart_rate", 17, "uint8"),
    Field("avg_cadence", 18, "uint8"),
    Field("avg_power", 20, "uint16"),
    Field("max_power", 21, "uint16"),
    Field("total_ascent", 22, "uint16"),
    Field("total_descent", 23, "uint16"),
    Field("first_lap_index", 25, "uint16"),
    Field("num_laps", 26, "uint16"),
    Field("normalized_power", 34, "uint16"),
    Field("training_stress_score", 35, "uint16", scale=10),
    Field("intensity_factor", 36, "uint16", scale=1000),
    Field("left_right_balance", 37, "uint16"),
    Field("avg_left_torque_effectiveness", 101, "uint8", scale=2),
    Field("avg_right_torque_effectiveness", 102, "uint8", scale=2),
    Field("avg_left_pedal_smoothness", 103, "uint8", scale=2),
    Field("avg_right_pedal_smoothness", 104, "uint8", scale=2),
    Field("avg_combined_pedal_smoothness", 105, "uint8", scale=2),
    Field("sport_profile_name", 110, "string", length=NAME_LEN),
])

ACTIVITY = (MSG_ACTIVITY, [
    Field("timestamp", 253, "uint32"),
    Field("total_timer_time", 0, "uint32", scale=1000),
    Field("num_sessions", 1, "uint16"),
    Field("type", 2, "enum"),
    Field("event", 3, "enum"),
    Field("event_type", 4, "enum"),
])

# Valores de enumerações que usamos.
FILE_TYPE_ACTIVITY = 4
SPORT_CYCLING = 2
SUB_SPORT_INDOOR_CYCLING = 6
# «virtual_activity»: é o que faz o Strava mostrar «Virtual Ride» e o Garmin
# Connect «Ciclismo virtual», como numa sessão do Zwift.
SUB_SPORT_VIRTUAL = 58
EVENT_TIMER = 0
EVENT_TYPE_START, EVENT_TYPE_STOP_ALL = 0, 4
ACTIVITY_TYPE_MANUAL = 0
EVENT_ACTIVITY = 26
LAP_TRIGGER = {"manual": 0, "time": 1, "distance": 2, "position_start": 3,
               "session_end": 7, "climb": 0, "workout_step": 5, "end": 7,
               "route_loop": 2}


class FitWriter:
    """Acumula mensagens e escreve o ficheiro final."""

    def __init__(self) -> None:
        self._body = bytearray()
        self._locals: dict[tuple, int] = {}   # (global, campos) -> tipo local
        self._next_local = 0

    def _ensure_definition(self, msgdef: tuple[int, list[Field]]) -> int:
        global_num, fields = msgdef
        # a mesma mensagem global pode ter definições diferentes (um registo
        # só com FC, outro completo): cada definição tem o seu tipo local
        key = (global_num, tuple(f.num for f in fields))
        if key in self._locals:
            return self._locals[key]
        if self._next_local > 15:
            raise RuntimeError("demasiados tipos de mensagem locais")
        local = self._next_local
        self._next_local += 1
        self._locals[key] = local

        out = bytearray()
        out.append(0x40 | local)                       # cabeçalho de definição
        out.append(0)                                   # reservado
        out.append(0)                                   # arquitetura: little endian
        out += struct.pack("<H", global_num)
        out.append(len(fields))
        for f in fields:
            out.append(f.num)
            out.append(f.size)
            out.append(_BASE[f.type][0])
        self._body += out
        return local

    def write(self, msgdef: tuple[int, list[Field]], **values: Any) -> None:
        local = self._ensure_definition(msgdef)
        _, fields = msgdef
        out = bytearray()
        out.append(local)                               # cabeçalho de dados
        for f in fields:
            out += f.encode(values.get(f.name))
        self._body += out

    def to_bytes(self) -> bytes:
        header = bytearray()
        header.append(14)
        header.append(PROTOCOL_VERSION)
        header += struct.pack("<H", PROFILE_VERSION)
        header += struct.pack("<I", len(self._body))
        header += b".FIT"
        header += struct.pack("<H", crc16(bytes(header[:12])))
        full = bytes(header) + bytes(self._body)
        return full + struct.pack("<H", crc16(full))


def _pedal_avgs(pedal: dict | None) -> dict:
    p = pedal or {}
    return {
        "avg_left_torque_effectiveness": p.get("te_left"),
        "avg_right_torque_effectiveness": p.get("te_right"),
        "avg_left_pedal_smoothness": p.get("ps_left"),
        "avg_right_pedal_smoothness": p.get("ps_right"),
        "avg_combined_pedal_smoothness": p.get("ps_combined"),
    }


def _avg(values: Sequence[float | int | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def _max(values: Sequence[float | int | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return max(vals) if vals else None


def write_activity(path: str | Path, athlete: Athlete, samples: Sequence[Sample],
                   laps: Sequence[Lap], summary: RideSummary,
                   start_unix: float, include_coords: bool = True,
                   coord_at: Any = None, name: str = "",
                   virtual: bool = True) -> Path:
    """Escreve o .fit completo da sessão.

    `coord_at(dist_m) -> (lat, lon, ele)` fornece as coordenadas da rota; se
    for None (ou `include_coords` falso) o ficheiro sai sem posições, o que
    é legítimo para uma atividade indoor.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = FitWriter()
    t0 = to_fit_time(start_unix)

    w.write(FILE_ID, type=FILE_TYPE_ACTIVITY, manufacturer=MANUFACTURER_DEVELOPMENT,
            product=1, serial_number=1, time_created=t0)
    w.write(DEVICE_INFO, timestamp=t0, device_index=0,
            manufacturer=MANUFACTURER_DEVELOPMENT, product=1, software_version=1.0)
    w.write(USER_PROFILE, message_index=0, age=athlete.age, weight=athlete.weight_kg,
            functional_threshold_power=athlete.ftp_w)
    sub_sport = SUB_SPORT_VIRTUAL if virtual else SUB_SPORT_INDOOR_CYCLING
    w.write(SPORT, sport=SPORT_CYCLING, sub_sport=sub_sport, name=name or "Perennia")
    w.write(EVENT, timestamp=t0, event=EVENT_TIMER, event_type=EVENT_TYPE_START)

    for s in samples:
        lat = lon = None
        if include_coords and coord_at is not None:
            try:
                lat, lon, _ = coord_at(s.dist_m)
            except Exception:
                lat = lon = None
        w.write(
            RECORD,
            timestamp=t0 + s.t_s,
            position_lat=to_semicircles(lat) if lat is not None else None,
            position_long=to_semicircles(lon) if lon is not None else None,
            altitude=s.ele_m,
            heart_rate=s.hr_bpm,
            cadence=s.cadence_rpm,
            distance=s.dist_m,
            speed=s.speed_mps,
            power=s.power_w,
            grade=s.grade_pct,
            left_right_balance=balance_8(s.balance_left),
            left_torque_effectiveness=s.te_left,
            right_torque_effectiveness=s.te_right,
            left_pedal_smoothness=s.ps_left,
            right_pedal_smoothness=s.ps_right,
            combined_pedal_smoothness=s.ps_combined,
        )

    last_t = samples[-1].t_s if samples else summary.elapsed_s
    w.write(EVENT, timestamp=t0 + last_t, event=EVENT_TIMER,
            event_type=EVENT_TYPE_STOP_ALL)

    for i, lap in enumerate(laps):
        w.write(
            LAP,
            timestamp=t0 + lap.end_t_s,
            message_index=i,
            event=9,                      # lap
            event_type=1,                 # stop
            start_time=t0 + lap.start_t_s,
            total_elapsed_time=lap.end_t_s - lap.start_t_s,
            total_timer_time=lap.end_t_s - lap.start_t_s,
            total_distance=lap.end_dist_m - lap.start_dist_m,
            avg_speed=lap.avg_speed_mps,
            avg_heart_rate=lap.avg_hr,
            max_heart_rate=lap.max_hr,
            avg_cadence=lap.avg_cadence,
            avg_power=lap.avg_power_w,
            max_power=lap.max_power_w,
            total_ascent=lap.ascent_m,
            lap_trigger=LAP_TRIGGER.get(lap.trigger, 0),
            sport=SPORT_CYCLING,
            left_right_balance=balance_100(getattr(lap, "avg_balance_left", None)),
            sub_sport=sub_sport,
            **_pedal_avgs(getattr(lap, "pedal", None)),
        )

    w.write(
        SESSION,
        timestamp=t0 + last_t,
        message_index=0,
        event=8,                          # session
        event_type=1,
        start_time=t0,
        sport=SPORT_CYCLING,
        sub_sport=sub_sport,
        sport_profile_name=name or "Perennia",
        **_pedal_avgs(summary.pedal),
        total_elapsed_time=summary.elapsed_s,
        total_timer_time=summary.moving_s or summary.elapsed_s,
        total_distance=summary.distance_m,
        total_calories=int((summary.work_kj or 0) / 4.184 * 4.184) or None,
        avg_speed=summary.avg_speed_mps,
        max_speed=_max([s.speed_mps for s in samples]),
        avg_heart_rate=summary.avg_hr,
        max_heart_rate=summary.max_hr,
        avg_cadence=summary.avg_cadence,
        avg_power=summary.avg_power_w,
        max_power=summary.max_power_w,
        total_ascent=summary.ascent_m,
        total_descent=None,
        first_lap_index=0,
        num_laps=max(1, len(laps)),
        normalized_power=summary.np_w,
        training_stress_score=summary.tss,
        intensity_factor=summary.intensity_factor,
        left_right_balance=balance_100(summary.avg_balance_left),
    )

    w.write(ACTIVITY, timestamp=t0 + last_t,
            total_timer_time=summary.moving_s or summary.elapsed_s,
            num_sessions=1, type=ACTIVITY_TYPE_MANUAL,
            event=EVENT_ACTIVITY, event_type=EVENT_TYPE_STOP_ALL)

    path.write_bytes(w.to_bytes())
    return path


def verify(path: str | Path) -> dict[str, Any]:
    """Relê o ficheiro e confirma cabeçalho, tamanho e CRC.

    Serve de autoteste: se isto passar, o ficheiro é estruturalmente válido.
    """
    data = Path(path).read_bytes()
    if len(data) < 16:
        raise ValueError("ficheiro demasiado pequeno")
    header_size = data[0]
    data_size = struct.unpack("<I", data[4:8])[0]
    signature = data[8:12]
    if signature != b".FIT":
        raise ValueError("assinatura .FIT ausente")
    if header_size >= 14:
        expected = struct.unpack("<H", data[12:14])[0]
        if expected != 0 and expected != crc16(data[:12]):
            raise ValueError("CRC do cabeçalho inválido")
    end = header_size + data_size
    if end + 2 > len(data):
        raise ValueError("tamanho declarado excede o ficheiro")
    file_crc = struct.unpack("<H", data[end:end + 2])[0]
    if file_crc != crc16(data[:end]):
        raise ValueError("CRC do ficheiro inválido")
    # Conta mensagens por tipo local.
    counts: dict[int, int] = {}
    i = header_size
    defs: dict[int, tuple[int, int]] = {}   # local -> (global, tamanho dos dados)
    while i < end:
        h = data[i]
        if h & 0x40:                        # definição
            local = h & 0x0F
            global_num = struct.unpack("<H", data[i + 3:i + 5])[0]
            n = data[i + 5]
            size = sum(data[i + 6 + k * 3 + 1] for k in range(n))
            defs[local] = (global_num, size)
            i += 6 + n * 3
        else:
            local = h & 0x0F
            if local not in defs:
                raise ValueError(f"dados sem definição para o tipo local {local}")
            global_num, size = defs[local]
            counts[global_num] = counts.get(global_num, 0) + 1
            i += 1 + size
    if i != end:
        raise ValueError("mensagens não alinham com o tamanho declarado")
    return {"bytes": len(data), "data_size": data_size, "messages": counts}


# ------------------------------------------------------------------ força

MSG_SET, MSG_WORKOUT, MSG_WORKOUT_STEP = 225, 26, 27
SPORT_TRAINING = 10
SUB_SPORT_STRENGTH = 20
FILE_TYPE_WORKOUT = 5

HR_RECORD = (MSG_RECORD, [
    Field("timestamp", 253, "uint32"),
    Field("heart_rate", 3, "uint8"),
])

SET = (MSG_SET, [
    Field("timestamp", 254, "uint32"),
    Field("duration", 0, "uint32", scale=1000),
    Field("repetitions", 3, "uint16"),
    Field("weight", 4, "uint16", scale=16),
    Field("set_type", 5, "uint8"),
    Field("start_time", 6, "uint32"),
    Field("category", 7, "uint16"),
    Field("weight_display_unit", 9, "uint16"),
    Field("message_index", 10, "uint16"),
    Field("wkt_step_index", 11, "uint16"),
])


def write_strength(path: str | Path, athlete: Athlete, hr: Sequence[tuple[int, int | None]],
                   sets: Sequence[Any], items: Sequence[Any], summary: dict,
                   start_unix: float, name: str = "") -> Path:
    """Sessão de força: registos de FC a 1 Hz e uma mensagem «set» por série
    (e pelo descanso entre séries), como os relógios Garmin gravam. O Garmin
    Connect mostra as séries com repetições, carga e a família do exercício."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = FitWriter()
    t0 = to_fit_time(start_unix)
    end_t = max([summary.get("elapsed_s") or 0] + [t for t, _ in hr]
                + [getattr(s, "end_t", 0) for s in sets])
    w.write(FILE_ID, type=FILE_TYPE_ACTIVITY, manufacturer=MANUFACTURER_DEVELOPMENT,
            product=1, serial_number=1, time_created=t0)
    w.write(DEVICE_INFO, timestamp=t0, device_index=0,
            manufacturer=MANUFACTURER_DEVELOPMENT, product=1, software_version=1.0)
    w.write(USER_PROFILE, message_index=0, age=athlete.age, weight=athlete.weight_kg,
            functional_threshold_power=athlete.ftp_w)
    w.write(SPORT, sport=SPORT_TRAINING, sub_sport=SUB_SPORT_STRENGTH,
            name=name or "Perennia")
    w.write(EVENT, timestamp=t0, event=EVENT_TIMER, event_type=EVENT_TYPE_START)
    for t, h in hr:
        w.write(HR_RECORD, timestamp=t0 + int(t), heart_rate=h)

    idx = 0
    ordered = sorted(sets, key=lambda s: (s.start_t, s.end_t))
    for k, s in enumerate(ordered):
        item = items[s.item_idx] if 0 <= s.item_idx < len(items) else None
        timed = item is not None and getattr(item, "measure", "reps") == "time"
        w.write(SET, timestamp=t0 + s.end_t, duration=max(0, s.end_t - s.start_t),
                repetitions=None if timed else s.reps, weight=s.load_kg, set_type=1,
                start_time=t0 + s.start_t,
                category=getattr(item, "fit_category", None) if item else None,
                weight_display_unit=1, message_index=idx, wkt_step_index=s.item_idx)
        idx += 1
        nxt = ordered[k + 1] if k + 1 < len(ordered) else None
        if nxt is not None and nxt.start_t > s.end_t:
            w.write(SET, timestamp=t0 + nxt.start_t, duration=nxt.start_t - s.end_t,
                    set_type=0, start_time=t0 + s.end_t, message_index=idx)
            idx += 1

    w.write(EVENT, timestamp=t0 + end_t, event=EVENT_TIMER, event_type=EVENT_TYPE_STOP_ALL)
    w.write(LAP, timestamp=t0 + end_t, message_index=0, event=9, event_type=1,
            start_time=t0, total_elapsed_time=end_t, total_timer_time=end_t,
            avg_heart_rate=summary.get("avg_hr"), max_heart_rate=summary.get("max_hr"),
            lap_trigger=LAP_TRIGGER["session_end"], sport=SPORT_TRAINING,
            sub_sport=SUB_SPORT_STRENGTH)
    w.write(SESSION, timestamp=t0 + end_t, message_index=0, event=8, event_type=1,
            start_time=t0, sport=SPORT_TRAINING, sub_sport=SUB_SPORT_STRENGTH,
            sport_profile_name=name or "Perennia", total_elapsed_time=end_t,
            total_timer_time=end_t, avg_heart_rate=summary.get("avg_hr"),
            max_heart_rate=summary.get("max_hr"), first_lap_index=0, num_laps=1,
            training_stress_score=summary.get("load"))
    w.write(ACTIVITY, timestamp=t0 + end_t, total_timer_time=end_t, num_sessions=1,
            type=ACTIVITY_TYPE_MANUAL, event=EVENT_ACTIVITY, event_type=EVENT_TYPE_STOP_ALL)
    path.write_bytes(w.to_bytes())
    return path


def write_lap_session(path: str | Path, athlete: Athlete,
                      hr: Sequence[tuple[int, int | None]], laps: Sequence[Any],
                      summary: dict, start_unix: float, name: str = "") -> Path:
    """Treino livre / Conditioning: uma volta FIT por volta da sessão (com a
    distância nas da passadeira), séries nas voltas de força e a FC."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = FitWriter()
    t0 = to_fit_time(start_unix)
    end_t = max([int(summary.get("elapsed_s") or 0)] + [t for t, _ in hr]
                + [int(lp.end_t or 0) for lp in laps])
    w.write(FILE_ID, type=FILE_TYPE_ACTIVITY, manufacturer=MANUFACTURER_DEVELOPMENT,
            product=1, serial_number=1, time_created=t0)
    w.write(DEVICE_INFO, timestamp=t0, device_index=0,
            manufacturer=MANUFACTURER_DEVELOPMENT, product=1, software_version=1.0)
    w.write(USER_PROFILE, message_index=0, age=athlete.age, weight=athlete.weight_kg,
            functional_threshold_power=athlete.ftp_w)
    w.write(SPORT, sport=SPORT_TRAINING, sub_sport=SUB_SPORT_STRENGTH,
            name=name or "Perennia")
    w.write(EVENT, timestamp=t0, event=EVENT_TIMER, event_type=EVENT_TYPE_START)
    for t, h in hr:
        w.write(HR_RECORD, timestamp=t0 + int(t), heart_rate=h)
    idx = 0
    for lap in laps:
        if lap.kind == "strength":
            timed = getattr(lap, "measure", "reps") == "time"
            w.write(SET, timestamp=t0 + int(lap.end_t or lap.start_t),
                    duration=max(0.0, (lap.end_t or lap.start_t) - lap.start_t),
                    repetitions=None if timed else lap.reps, weight=lap.load_kg, set_type=1,
                    start_time=t0 + int(lap.start_t), category=lap.fit_category,
                    weight_display_unit=1, message_index=idx)
            idx += 1
        elif lap.kind == "rest":
            w.write(SET, timestamp=t0 + int(lap.end_t or lap.start_t),
                    duration=max(0.0, (lap.end_t or lap.start_t) - lap.start_t),
                    set_type=0, start_time=t0 + int(lap.start_t), message_index=idx)
            idx += 1
    w.write(EVENT, timestamp=t0 + end_t, event=EVENT_TIMER, event_type=EVENT_TYPE_STOP_ALL)
    for i, lap in enumerate(laps):
        secs = max(0.0, (lap.end_t or lap.start_t) - lap.start_t)
        dist_m = (lap.distance_km or 0.0) * 1000.0 if lap.kind in ("treadmill", "cardio",
                                                                   "rowing") else None
        w.write(LAP, timestamp=t0 + int(lap.end_t or lap.start_t), message_index=i, event=9,
                event_type=1, start_time=t0 + int(lap.start_t), total_elapsed_time=secs,
                total_timer_time=secs, total_distance=dist_m,
                avg_speed=(dist_m / secs) if dist_m and secs else None,
                avg_heart_rate=lap.avg_hr, max_heart_rate=lap.max_hr,
                lap_trigger=LAP_TRIGGER["manual"], sport=SPORT_TRAINING,
                sub_sport=SUB_SPORT_STRENGTH)
    total_dist = (summary.get("distance_km") or 0.0) * 1000.0
    w.write(SESSION, timestamp=t0 + end_t, message_index=0, event=8, event_type=1,
            start_time=t0, sport=SPORT_TRAINING, sub_sport=SUB_SPORT_STRENGTH,
            sport_profile_name=name or "Perennia", total_elapsed_time=end_t,
            total_timer_time=end_t, total_distance=total_dist or None,
            avg_heart_rate=summary.get("avg_hr"), max_heart_rate=summary.get("max_hr"),
            first_lap_index=0, num_laps=max(1, len(laps)),
            training_stress_score=summary.get("load"))
    w.write(ACTIVITY, timestamp=t0 + end_t, total_timer_time=end_t, num_sessions=1,
            type=ACTIVITY_TYPE_MANUAL, event=EVENT_ACTIVITY, event_type=EVENT_TYPE_STOP_ALL)
    path.write_bytes(w.to_bytes())
    return path


# -------------------------------------------------------- treino estruturado

WORKOUT = (MSG_WORKOUT, [
    Field("sport", 4, "enum"),
    Field("num_valid_steps", 6, "uint16"),
    Field("wkt_name", 8, "string", length=NAME_LEN),
])

WORKOUT_STEP = (MSG_WORKOUT_STEP, [
    Field("message_index", 254, "uint16"),
    Field("wkt_step_name", 0, "string", length=32),
    Field("duration_type", 1, "enum"),
    Field("duration_value", 2, "uint32"),
    Field("target_type", 3, "enum"),
    Field("target_value", 4, "uint32"),
    Field("custom_target_value_low", 5, "uint32"),
    Field("custom_target_value_high", 6, "uint32"),
    Field("intensity", 7, "enum"),
    Field("notes", 8, "string", length=NAME_LEN),
])

WKT_DURATION_TIME = 0
WKT_TARGET_OPEN, WKT_TARGET_POWER = 2, 4
INTENSITY = {"active": 0, "rest": 1, "warmup": 2, "cooldown": 3}


def write_workout(path: str | Path, name: str, steps: Sequence[dict]) -> Path:
    """Ficheiro de treino (.fit do tipo «workout») para um Garmin Edge, um
    relógio ou um Wahoo. `steps`: [{"name", "seconds", "low", "high",
    "unit" ("pct"|"watts"|None), "intensity", "notes"}]. Em % da FTP o
    aparelho calcula os watts com a FTP que lá tiver."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = FitWriter()
    import time as _time
    w.write(FILE_ID, type=FILE_TYPE_WORKOUT, manufacturer=MANUFACTURER_DEVELOPMENT,
            product=1, serial_number=1, time_created=to_fit_time(_time.time()))
    w.write(WORKOUT, sport=SPORT_CYCLING, num_valid_steps=len(steps), wkt_name=name)
    for i, st in enumerate(steps):
        unit = st.get("unit")
        if unit is None or st.get("low") is None:
            target_type, lo, hi = WKT_TARGET_OPEN, None, None
        else:
            target_type = WKT_TARGET_POWER
            # FIT: 0–1000 é % da FTP; acima de 1000 são watts + 1000
            offset = 1000 if unit == "watts" else 0
            lo = int(round(st["low"])) + offset
            hi = int(round(st.get("high") or st["low"])) + offset
        w.write(WORKOUT_STEP, message_index=i, wkt_step_name=st.get("name") or "",
                duration_type=WKT_DURATION_TIME,
                duration_value=int(round(st["seconds"] * 1000)),
                target_type=target_type, target_value=0 if target_type == WKT_TARGET_POWER
                else None, custom_target_value_low=lo, custom_target_value_high=hi,
                intensity=INTENSITY.get(st.get("intensity") or "active", 0),
                notes=st.get("notes") or "")
    path.write_bytes(w.to_bytes())
    return path


# ------------------------------------------------------- equilíbrio E/D
#
# A norma FIT guarda a percentagem de UMA perna e um bit a dizer qual. Sem
# o bit, a perna é "desconhecida" e o Garmin Connect, o Strava ou o Golden
# Cheetah não sabem de que lado está. Guardamos sempre a direita, com o
# bit ligado, que é o que os aparelhos Garmin fazem.

def balance_8(left_pct: float | None) -> int | None:
    """Campo `left_right_balance` (uint8) dos registos: bit 7 = direita."""
    if left_pct is None:
        return None
    right = int(round(max(0.0, min(100.0, 100.0 - left_pct))))
    return 0x80 | (right & 0x7F)


def balance_100(left_pct: float | None) -> int | None:
    """Campo `left_right_balance_100` (uint16) de voltas e sessão:
    percentagem × 100 nos bits 0–13, bit 15 = direita."""
    if left_pct is None:
        return None
    right = int(round(max(0.0, min(100.0, 100.0 - left_pct)) * 100))
    return 0x8000 | (right & 0x3FFF)


def balance_left_from_8(raw: int | None) -> float | None:
    """Inverso de `balance_8`, para ler de volta (e para os testes)."""
    if raw is None or raw == 0xFF:
        return None
    pct = raw & 0x7F
    return float(100 - pct) if raw & 0x80 else float(pct)


# ---------------------------------------------------------------- leitura


_READ_FMT = {0x00: "<B", 0x01: "<b", 0x02: "<B", 0x83: "<h", 0x84: "<H", 0x85: "<i",
             0x86: "<I", 0x0A: "<B", 0x8B: "<H", 0x8C: "<I"}


def read_messages(path: str | Path) -> list[tuple[int, dict[int, Any]]]:
    """Lê o ficheiro e devolve [(mensagem global, {campo: valor bruto})].

    Valores inválidos ficam de fora; textos vêm como str. Não aplica escalas:
    quem lê sabe o campo que procura. Serve para confirmar o que se escreveu.
    """
    data = Path(path).read_bytes()
    verify(path)
    header_size = data[0]
    end = header_size + struct.unpack("<I", data[4:8])[0]
    defs: dict[int, tuple[int, list[tuple[int, int, int]]]] = {}
    out: list[tuple[int, dict[int, Any]]] = []
    i = header_size
    while i < end:
        h = data[i]
        local = h & 0x0F
        if h & 0x40:
            global_num = struct.unpack("<H", data[i + 3:i + 5])[0]
            n = data[i + 5]
            fields = [(data[i + 6 + k * 3], data[i + 7 + k * 3], data[i + 8 + k * 3])
                      for k in range(n)]
            defs[local] = (global_num, fields)
            i += 6 + n * 3
            continue
        global_num, fields = defs[local]
        i += 1
        values: dict[int, Any] = {}
        for num, size, base in fields:
            chunk = data[i:i + size]
            i += size
            if base == 0x07:
                text = chunk.split(b"\x00", 1)[0].decode("utf-8", "replace")
                if text:
                    values[num] = text
                continue
            fmt = _READ_FMT.get(base)
            if fmt is None:
                continue
            raw = struct.unpack(fmt, chunk)[0]
            invalid = _BASE_INVALID.get(base)
            if raw != invalid:
                values[num] = raw
        out.append((global_num, values))
    return out


_BASE_INVALID = {0x00: 0xFF, 0x01: 0x7F, 0x02: 0xFF, 0x83: 0x7FFF, 0x84: 0xFFFF,
                 0x85: 0x7FFFFFFF, 0x86: 0xFFFFFFFF, 0x0A: 0, 0x8B: 0, 0x8C: 0}


# ------------------------------------------------------------------- remo

SPORT_ROWING = 15
SUB_SPORT_INDOOR_ROWING = 14

ROW_RECORD = (MSG_RECORD, [
    Field("timestamp", 253, "uint32"),
    Field("heart_rate", 3, "uint8"),
    Field("cadence", 4, "uint8"),                  # remadas por minuto
    Field("distance", 5, "uint32", scale=100),
    Field("speed", 6, "uint16", scale=1000),
    Field("power", 7, "uint16"),
])

ROW_SESSION = (SESSION[0], SESSION[1] + [Field("total_cycles", 10, "uint32")])
ROW_LAP = (LAP[0], LAP[1] + [Field("total_cycles", 10, "uint32")])


def write_rowing(path: str | Path, athlete: Athlete, samples: Sequence[dict],
                 laps: Sequence[dict], summary: dict, start_unix: float,
                 name: str = "", sport: int = SPORT_ROWING,
                 sub_sport: int = SUB_SPORT_INDOOR_ROWING) -> Path:
    """Remo indoor (sport 15, sub_sport 14): registos a 1 Hz com distância,
    velocidade, potência, remadas por minuto e FC; uma volta FIT por volta."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = FitWriter()
    t0 = to_fit_time(start_unix)
    end_t = max([int(summary.get("elapsed_s") or 0)] + [int(s["t_s"]) for s in samples])
    w.write(FILE_ID, type=FILE_TYPE_ACTIVITY, manufacturer=MANUFACTURER_DEVELOPMENT,
            product=1, serial_number=1, time_created=t0)
    w.write(DEVICE_INFO, timestamp=t0, device_index=0,
            manufacturer=MANUFACTURER_DEVELOPMENT, product=1, software_version=1.0)
    w.write(USER_PROFILE, message_index=0, age=athlete.age, weight=athlete.weight_kg,
            functional_threshold_power=summary.get("ftp_w") or athlete.ftp_w)
    w.write(SPORT, sport=sport, sub_sport=sub_sport,
            name=name or "Perennia")
    w.write(EVENT, timestamp=t0, event=EVENT_TIMER, event_type=EVENT_TYPE_START)
    for s in samples:
        w.write(ROW_RECORD, timestamp=t0 + int(s["t_s"]), heart_rate=s.get("hr_bpm"),
                cadence=None if s.get("spm") is None else int(round(s["spm"])),
                distance=s.get("dist_m"), speed=s.get("speed_mps"), power=s.get("power_w"))
    w.write(EVENT, timestamp=t0 + end_t, event=EVENT_TIMER, event_type=EVENT_TYPE_STOP_ALL)
    laps = list(laps) or [{"start_t": 0, "end_t": end_t, "distance_m": summary.get("distance_m"),
                           "avg_hr": summary.get("avg_hr"), "max_hr": summary.get("max_hr"),
                           "avg_power_w": summary.get("avg_power_w"),
                           "avg_spm": summary.get("avg_spm"), "strokes": summary.get("strokes"),
                           "trigger": "session_end"}]
    for i, lp in enumerate(laps):
        secs = max(0.0, (lp["end_t"] or 0) - lp["start_t"])
        dist = lp.get("distance_m")
        w.write(ROW_LAP, timestamp=t0 + int(lp["end_t"] or 0), message_index=i, event=9,
                event_type=1, start_time=t0 + int(lp["start_t"]), total_elapsed_time=secs,
                total_timer_time=secs, total_distance=dist,
                avg_speed=(dist / secs) if dist and secs else None,
                avg_heart_rate=lp.get("avg_hr"), max_heart_rate=lp.get("max_hr"),
                avg_cadence=None if lp.get("avg_spm") is None else int(round(lp["avg_spm"])),
                avg_power=lp.get("avg_power_w"),
                lap_trigger=LAP_TRIGGER.get(lp.get("trigger") or "manual", LAP_TRIGGER["manual"]),
                sport=sport, sub_sport=sub_sport,
                total_cycles=lp.get("strokes"))
    dist = summary.get("distance_m") or None
    w.write(ROW_SESSION, timestamp=t0 + end_t, message_index=0, event=8, event_type=1,
            start_time=t0, sport=sport, sub_sport=sub_sport,
            sport_profile_name=name or "Perennia", total_elapsed_time=end_t,
            total_timer_time=summary.get("moving_s") or end_t, total_distance=dist,
            total_calories=summary.get("kcal"),
            avg_speed=(dist / summary["moving_s"]) if dist and summary.get("moving_s") else None,
            avg_heart_rate=summary.get("avg_hr"), max_heart_rate=summary.get("max_hr"),
            avg_cadence=None if summary.get("avg_spm") is None else int(round(summary["avg_spm"])),
            avg_power=summary.get("avg_power_w"), max_power=summary.get("max_power_w"),
            normalized_power=summary.get("np_w"), first_lap_index=0,
            num_laps=len(laps), training_stress_score=summary.get("load"),
            total_cycles=summary.get("strokes"))
    w.write(ACTIVITY, timestamp=t0 + end_t, total_timer_time=end_t, num_sessions=1,
            type=ACTIVITY_TYPE_MANUAL, event=EVENT_ACTIVITY, event_type=EVENT_TYPE_STOP_ALL)
    path.write_bytes(w.to_bytes())
    return path


WKT_DURATION_DISTANCE = 1


def write_row_workout(path: str | Path, name: str, steps: Sequence[dict]) -> Path:
    """Treino de remo (.fit «workout», sport 15): passos por tempo ou por
    distância, com o alvo em watts. `steps`: [{"name", "seconds" | "meters",
    "lo_w", "hi_w", "intensity", "notes"}]."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w = FitWriter()
    import time as _time
    w.write(FILE_ID, type=FILE_TYPE_WORKOUT, manufacturer=MANUFACTURER_DEVELOPMENT,
            product=1, serial_number=1, time_created=to_fit_time(_time.time()))
    w.write(WORKOUT, sport=SPORT_ROWING, num_valid_steps=len(steps), wkt_name=name)
    for i, st in enumerate(steps):
        if st.get("lo_w"):
            tt, lo, hi = WKT_TARGET_POWER, int(st["lo_w"]) + 1000, int(st.get("hi_w")
                                                                      or st["lo_w"]) + 1000
        else:
            tt, lo, hi = WKT_TARGET_OPEN, None, None
        if st.get("meters"):
            dt, dv = WKT_DURATION_DISTANCE, int(round(st["meters"] * 100))
        else:
            dt, dv = WKT_DURATION_TIME, int(round((st.get("seconds") or 0) * 1000))
        w.write(WORKOUT_STEP, message_index=i, wkt_step_name=st.get("name") or "",
                duration_type=dt, duration_value=dv, target_type=tt,
                target_value=0 if tt == WKT_TARGET_POWER else None,
                custom_target_value_low=lo, custom_target_value_high=hi,
                intensity=INTENSITY.get(st.get("intensity") or "active", 0),
                notes=st.get("notes") or "")
    path.write_bytes(w.to_bytes())
    return path
