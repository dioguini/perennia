"""Ícones (PNG em velo/assets/icons) e que ícone vai com cada métrica.

Imagens em vez de símbolos de texto: os símbolos dependem dos tipos de
letra de cada computador e saem às vezes como quadrados vazios.
"""
from __future__ import annotations

from velo import paths

METRIC_ICONS = {
    "power": "power", "power_3s": "power", "avg_power": "power", "np": "power",
    "power_zone": "zones", "avg_power_zone": "zones", "power_zone_range": "zones",
    "wkg": "weight", "avg_wkg": "weight", "power_lr": "balance",
    "power_balance": "balance", "avg_balance": "balance",
    "torque_eff": "gear", "avg_torque_eff": "gear",
    "pedal_smooth": "wave", "avg_pedal_smooth": "wave",
    "torque": "wrench", "avg_torque": "wrench",
    "work_kj": "battery", "tss_accum": "flame",
    "hr": "heart", "avg_hr": "heart", "hr_zone": "heart", "avg_hr_zone": "heart",
    "hr_zone_range": "heart",
    "cadence": "cadence", "avg_cadence": "cadence",
    "speed": "speed", "avg_speed": "speed",
    "dist_done": "distance", "dist_left": "flag", "eta": "flag",
    "ascent": "mountain", "grade_now": "grade", "loops": "loops",
    "elapsed": "clock", "target_power": "target",
}


def metric_icon(mid: str) -> str:
    if mid in METRIC_ICONS:
        return METRIC_ICONS[mid]
    if mid.startswith("avg_grade"):
        return "grade"
    return "target"


_cache: dict[str, object] = {}


def image(name: str):
    """A imagem, carregada uma vez. None se não existir (não rebenta)."""
    if name in _cache:
        return _cache[name]
    import pyglet
    path = paths.resource("velo", "assets", "icons", f"{name}.png")
    try:
        img = pyglet.image.load(str(path))
    except Exception:
        img = None
    _cache[name] = img
    return img


def sprite(name: str, x: float, y: float, size: float, batch=None, opacity: int = 230,
           tint=None):
    """Sprite do ícone com `size` px de lado, ou None se faltar a imagem.

    Os PNG são claros; a cor vem do tema (`tint`, por omissão a cor do texto),
    para o ícone se ver tanto num tema claro como no de pouca luz."""
    import pyglet
    img = image(name)
    if img is None:
        return None
    try:
        sp = pyglet.sprite.Sprite(img, x=x, y=y, batch=batch)
        sp.scale = size / max(img.width, 1)
        sp.opacity = opacity
        set_tint(sp, tint)
        return sp
    except Exception:
        return None


def set_tint(sp, tint=None) -> None:
    """Muda a cor de um ícone já criado (None = cor do texto do tema)."""
    if sp is None:
        return
    from velo.gfx import theme
    c = tint if tint is not None else theme.P.text
    try:
        sp.color = (int(c[0]), int(c[1]), int(c[2]))
    except Exception:
        pass
