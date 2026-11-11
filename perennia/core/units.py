"""Conversão e formatação de unidades (req. 16).

Internamente tudo é SI: metros, m/s, watts, bpm, rpm, kg, segundos.
A conversão para imperial acontece apenas aqui, na apresentação.
"""
from __future__ import annotations

METRIC = "metric"
IMPERIAL = "imperial"

_MI_PER_KM = 0.621371
_FT_PER_M = 3.28084
_LB_PER_KG = 2.20462


def km(meters: float, system: str = METRIC) -> tuple[float, str]:
    v = meters / 1000.0
    return (v * _MI_PER_KM, "mi") if system == IMPERIAL else (v, "km")


def speed(mps: float, system: str = METRIC) -> tuple[float, str]:
    kph = mps * 3.6
    return (kph * _MI_PER_KM, "mph") if system == IMPERIAL else (kph, "km/h")


def elevation(meters: float, system: str = METRIC) -> tuple[float, str]:
    return (meters * _FT_PER_M, "ft") if system == IMPERIAL else (meters, "m")


def weight(kg: float, system: str = METRIC) -> tuple[float, str]:
    return (kg * _LB_PER_KG, "lb") if system == IMPERIAL else (kg, "kg")


def hms(seconds: float) -> str:
    """Formata duração. Omite as horas quando são zero."""
    s = int(max(0.0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def balance_text(left_pct: float | None) -> str:
    """Equilíbrio esquerda/direita: 49 → «49 / 51». Soma sempre 100."""
    if left_pct is None:
        return "—"
    left = int(round(max(0.0, min(100.0, left_pct))))
    return f"{left} / {100 - left}"


def zone_text(zone: int, kind: str = "power") -> str:
    """3 → «Z3 · Tempo». O nome vem das traduções."""
    from .i18n import t
    key = f"zone.{kind}.{zone}"
    name = t(key)
    return f"Z{zone} · {name}" if name != key else f"Z{zone}"


def watts_pair_text(pair) -> str:
    """(esquerda, direita) em watts → «118 / 122 W»."""
    if not pair or pair[0] is None or pair[1] is None:
        return "—"
    return f"{pair[0]:.0f} / {pair[1]:.0f} W"


def pair_text(pair) -> str:
    """(esquerda, direita[, combinada]) em % → «78 / 80 %». Mostra o que houver."""
    if pair is None:
        return "—"
    left, right = pair[0], pair[1]
    combined = pair[2] if len(pair) > 2 else None
    if left is not None and right is not None:
        return f"{left:.0f} / {right:.0f} %"
    if combined is not None:
        return f"{combined:.0f} %"
    one = left if left is not None else right
    return f"{one:.0f} %" if one is not None else "—"


def delta(seconds: float) -> str:
    """Diferença com sinal, para os fantasmas: -0:12 / +1:05."""
    sign = "-" if seconds < 0 else "+"
    return sign + hms(abs(seconds))


# Como formatar cada unidade do registo de métricas.
# (conversor, decimais) — conversor devolve (valor, sufixo).
_FORMATTERS: dict[str, tuple] = {
    "m": (elevation, 0),
    "km": (km, 2),
    "mps": (speed, 1),
    "W": (None, 0),
    "bpm": (None, 0),
    "rpm": (None, 0),
    "%": (None, 1),
    "Nm": (None, 1),
    "s": (None, 0),
    "zone": (None, 0),
    "pzone": (None, 0),
    "hzone": (None, 0),
    "kJ": (None, 0),
    "TSS": (None, 0),
    "count": (None, 0),
}


def format_metric(value: float | None, unit: str, system: str = METRIC,
                  with_unit: bool = True) -> str:
    """Formata um valor de métrica para o HUD. None vira travessão."""
    if value is None:
        return "—"
    if unit == "s":
        return hms(value)
    if unit == "balance":
        return balance_text(value)
    if unit == "pair_pct":
        return pair_text(value)
    if unit == "pair_w":
        return watts_pair_text(value)
    if unit == "text":
        return str(value)
    if unit == "wkg":
        return f"{value:.2f} W/kg"
    conv, decimals = _FORMATTERS.get(unit, (None, 1))
    if conv is not None:
        value, suffix = conv(value, system)
    else:
        suffix = unit
    text = f"{value:.{decimals}f}"
    if unit == "zone":
        return f"Z{text}"
    if unit in ("pzone", "hzone"):
        return zone_text(int(value), "power" if unit == "pzone" else "hr")
    if unit == "count":
        return text
    return f"{text} {suffix}" if with_unit and suffix else text


def parse_number(text: str) -> float | None:
    """Lê um número escrito à mão, em formato português ou inglês.

    «5000.34», «5000,34», «5,000.34», «5.000,34» e «5 000,34» dão todos
    5000.34. Com os dois separadores, o último é o decimal. Com um só
    separador repetido («1.000.000»), são milhares. Com um só separador
    uma vez, é o decimal: «23,5» e «23.5» são 23,5. Devolve None se não
    houver número.
    """
    s = (text or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if any(c not in "0123456789.," for c in s):
        return None
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        s = s.replace(thousands, "").replace(decimal, ".")
    elif s.count(",") > 1 or s.count(".") > 1:
        s = s.replace(",", "").replace(".", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
