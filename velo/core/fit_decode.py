"""Leitor de ficheiros .fit (o formato dos relógios Garmin, Wahoo, Zwift…),
escrito de raiz — o contrário do `fit.py`, que os escreve.

Lê só o que a Perennia precisa: o cabeçalho, as definições de mensagens e os
dados (incluindo cabeçalhos de tempo comprimido e campos de programador, que
se saltam). Devolve as mensagens de interesse já com o nome do campo:
`file_id`, `sport`, `session`, `lap`, `record`, `activity`.
"""
from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# tipo base → (formato struct, tamanho, valor inválido)
BASE = {
    0x00: ("B", 1, 0xFF), 0x01: ("b", 1, 0x7F), 0x02: ("B", 1, 0xFF), 0x83: ("h", 2, 0x7FFF),
    0x84: ("H", 2, 0xFFFF), 0x85: ("i", 4, 0x7FFFFFFF), 0x86: ("I", 4, 0xFFFFFFFF),
    0x88: ("f", 4, None), 0x89: ("d", 8, None), 0x0A: ("B", 1, 0x00), 0x8B: ("H", 2, 0x0000),
    0x8C: ("I", 4, 0x00000000), 0x0D: ("B", 1, 0xFF), 0x8E: ("q", 8, 0x7FFFFFFFFFFFFFFF),
    0x8F: ("Q", 8, 0xFFFFFFFFFFFFFFFF), 0x90: ("Q", 8, 0x0),
}
BASE_ALIAS = {0x03: 0x83, 0x04: 0x84, 0x05: 0x85, 0x06: 0x86, 0x08: 0x88, 0x09: 0x89,
              0x0B: 0x8B, 0x0C: 0x8C, 0x0E: 0x8E, 0x0F: 0x8F, 0x10: 0x90}

MESSAGES = {0: "file_id", 12: "sport", 18: "session", 19: "lap", 20: "record", 34: "activity"}

FIELDS = {
    "file_id": {0: "type", 1: "manufacturer", 2: "product", 3: "serial", 4: "time_created"},
    "sport": {0: "sport", 1: "sub_sport", 3: "name"},
    "session": {
        2: "start_time", 5: "sport", 6: "sub_sport", 7: "total_elapsed_time",
        8: "total_timer_time", 9: "total_distance", 11: "total_calories", 14: "avg_speed",
        15: "max_speed", 16: "avg_heart_rate", 17: "max_heart_rate", 18: "avg_cadence",
        19: "max_cadence", 20: "avg_power", 21: "max_power", 22: "total_ascent",
        23: "total_descent", 34: "normalized_power", 35: "training_stress_score",
        36: "intensity_factor", 124: "enhanced_avg_speed", 125: "enhanced_max_speed",
        44: "pool_length", 33: "num_active_lengths"},
    "lap": {2: "start_time", 7: "total_elapsed_time", 9: "total_distance"},
    "record": {253: "timestamp", 0: "lat", 1: "lon", 2: "altitude", 3: "heart_rate",
               4: "cadence", 5: "distance", 6: "speed", 7: "power", 73: "enhanced_speed",
               78: "enhanced_altitude"},
    "activity": {253: "timestamp", 0: "total_timer_time", 1: "num_sessions", 2: "type"},
}
# escalas: valor bruto / escala (− deslocamento)
SCALES = {
    ("session", "total_elapsed_time"): 1000.0, ("session", "total_timer_time"): 1000.0,
    ("session", "total_distance"): 100.0, ("session", "avg_speed"): 1000.0,
    ("session", "max_speed"): 1000.0, ("session", "enhanced_avg_speed"): 1000.0,
    ("session", "enhanced_max_speed"): 1000.0, ("session", "intensity_factor"): 1000.0,
    ("session", "training_stress_score"): 10.0, ("session", "pool_length"): 100.0,
    ("lap", "total_elapsed_time"): 1000.0, ("lap", "total_distance"): 100.0,
    ("record", "distance"): 100.0, ("record", "speed"): 1000.0,
    ("record", "enhanced_speed"): 1000.0, ("activity", "total_timer_time"): 1000.0,
}
OFFSETS = {("record", "altitude"): 500.0, ("record", "enhanced_altitude"): 500.0}

SPORTS = {0: "generic", 1: "running", 2: "cycling", 3: "transition", 4: "fitness_equipment",
          5: "swimming", 10: "training", 11: "walking", 15: "rowing", 17: "hiking",
          13: "alpine_skiing", 19: "paddling", 20: "e_biking"}
SUB_SPORTS = {58: "virtual", 0: "generic", 1: "treadmill", 2: "street", 3: "trail", 4: "track", 5: "spin",
              6: "indoor_cycling", 7: "road", 8: "mountain", 14: "indoor_rowing",
              15: "elliptical", 16: "stair_climbing", 17: "lap_swimming", 18: "open_water",
              20: "strength_training", 26: "cardio_training", 45: "indoor_running"}


class FitError(ValueError):
    pass


def _when(seconds: int) -> datetime:
    return FIT_EPOCH + timedelta(seconds=int(seconds))


def decode(path: str | Path) -> dict[str, list[dict]]:
    """{nome: [mensagem, …]} do ficheiro. FitError se não for um .fit."""
    data = Path(path).read_bytes()
    if len(data) < 14 or data[8:12] != b".FIT":
        raise FitError("não é um ficheiro .fit")
    hdr = data[0]
    size = struct.unpack_from("<I", data, 4)[0]
    if len(data) < hdr + size + 2:
        raise FitError("o ficheiro .fit está incompleto")
    end = min(len(data) - 2, hdr + size)
    pos = hdr
    defs: dict[int, dict] = {}
    out: dict[str, list[dict]] = {n: [] for n in MESSAGES.values()}
    last_ts = 0
    while pos < end:
        rh = data[pos]
        pos += 1
        if rh & 0x80:                                   # tempo comprimido
            local = (rh >> 5) & 0x03
            offset = rh & 0x1F
            if last_ts:
                ts = (last_ts & ~0x1F) + offset
                if offset < (last_ts & 0x1F):
                    ts += 0x20
                last_ts = ts
            d = defs.get(local)
            if d is None:
                raise FitError("dados sem definição")
            msg, pos = _read_data(data, pos, d, None)
            msg["timestamp"] = _when(last_ts) if last_ts else None
            _keep(out, d, msg)
            continue
        local = rh & 0x0F
        if rh & 0x40:                                   # definição
            has_dev = bool(rh & 0x20)
            pos += 1                                    # reservado
            arch = data[pos]
            pos += 1
            endian = ">" if arch == 1 else "<"
            glob = struct.unpack_from(endian + "H", data, pos)[0]
            pos += 2
            n = data[pos]
            pos += 1
            fields = []
            for _ in range(n):
                fields.append((data[pos], data[pos + 1], data[pos + 2]))
                pos += 3
            dev = 0
            if has_dev:
                nd = data[pos]
                pos += 1
                for _ in range(nd):
                    dev += data[pos + 1]
                    pos += 3
            defs[local] = {"endian": endian, "global": glob, "fields": fields, "dev": dev}
            continue
        d = defs.get(local)
        if d is None:
            raise FitError("dados sem definição")
        msg, pos = _read_data(data, pos, d, None)
        if "timestamp" in msg and isinstance(msg["timestamp"], datetime):
            last_ts = int((msg["timestamp"] - FIT_EPOCH).total_seconds())
        _keep(out, d, msg)
    return out


def _read_data(data: bytes, pos: int, d: dict, _unused) -> tuple[dict, int]:
    """A mensagem lida (campos com o nome da norma ou «f<n>») e a posição a seguir."""
    msg: dict = {"_global": d["global"]}
    name = MESSAGES.get(d["global"])
    for num, size, btype in d["fields"]:
        raw = data[pos:pos + size]
        pos += size
        key_ = FIELDS.get(name, {}).get(num, f"f{num}") if name else f"f{num}"
        if btype == 0x07:                               # texto
            msg[key_] = raw.split(b"\x00")[0].decode("utf-8", "replace")
            continue
        base = BASE.get(btype) or BASE.get(BASE_ALIAS.get(btype, -1))
        if base is None:
            continue
        fmt, bsize, invalid = base
        if size < bsize or len(raw) < bsize:
            continue
        val = struct.unpack_from(d["endian"] + fmt, raw, 0)[0]   # 1.º valor (os campos são escalares)
        if invalid is not None and val == invalid:
            continue
        if isinstance(val, float) and val != val:
            continue
        msg[key_] = val
    pos += d["dev"]
    return msg, pos


def _keep(out: dict, d: dict, msg: dict) -> None:
    name = MESSAGES.get(d["global"])
    if name is None:
        return
    m: dict = {}
    for k, v in msg.items():
        if k == "_global":
            continue
        scale = SCALES.get((name, k))
        if scale and isinstance(v, (int, float)):
            v = v / scale
        off = OFFSETS.get((name, k))
        if off and isinstance(v, (int, float)):
            v = v / 5.0 - off
        if k in ("timestamp", "start_time", "time_created") and isinstance(v, int):
            v = _when(v)
        if k in ("lat", "lon") and isinstance(v, int):
            v = v * (180.0 / 2 ** 31)
        m[k] = v
    out[name].append(m)
