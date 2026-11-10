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


# ------------------------------------------------------------------ botões
#
# Todo o botão leva um ícone ao lado da etiqueta, e **o mesmo ícone para a mesma ação**,
# seja num menu ou numa janela. O ícone vem do texto do botão (sem acentos nem maiúsculas).

import re as _re
import unicodedata as _ud

_BUTTON_RULES = (
    (r"^\+?\s*planear|^\+?\s*plan\b", "calendar"),      # «Planear» e «+ Planear treino»: o mesmo
    (r"^\+", "ui_plus"), (r"^[−-]$", "ui_minus"),
    (r"sem guardar|^apagar|^remover|^eliminar|^delete|^remove", "ui_trash"),
    (r"^guardar|^save", "ui_save"),
    (r"^cancelar|^fechar|^cancel|^close|^nao\b|^no\b", "ui_close"),
    (r"^editar|^edit", "ui_edit"),
    (r"^exportar|^export|^descarregar|^download", "export"),
    (r"^importar|^import|^carregar|^trazer|upload", "ui_import"),
    (r"^planear|^plan", "calendar"),
    (r"^configurar|^definicoes|^settings", "gear"),
    (r"sincronizar|^so importar", "recover"),
    (r"^pausa|^pause", "ui_pause"),
    (r"^terminar|^parar|^finish|^stop", "ui_stop"),
    (r"^comecar|^iniciar|^retomar|^continuar|^start|^resume", "ui_play"),
    (r"^voltar|^back|^colheitas", "back"),
    (r"^ok$|^sim\b|^yes\b|^aplicar|^converter|^escolher|^aceitar|^confirmar|^repor|"
     r"^substituir|^juntar|^fazer upload", "ui_check"),
)


def _fold(text: str) -> str:
    s = _ud.normalize("NFKD", text or "")
    return "".join(c for c in s if not _ud.combining(c)).lower().strip()


def button_icon(label: str) -> str:
    """O ícone de um botão pelo seu texto: `+ Novo treino` → mais, `Guardar` → disquete…
    Sem regra própria, a seta."""
    low = _fold(label)
    for pattern, name in _BUTTON_RULES:
        if _re.search(pattern, low):
            return name
    return "ui_next"


def button_text(label: str) -> str:
    """A etiqueta tal como se desenha: o ícone já diz «+», por isso sai o `+ ` do início, e
    o − e o + sozinhos ficam só com o ícone."""
    if label.strip() in ("−", "-", "+"):
        return ""
    return label[2:] if label.startswith("+ ") else label


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
