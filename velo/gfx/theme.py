"""Temas da Perennia: paletas claras e profissionais, sem preto.

Cada tema dá cor a papéis (fundo, cartão, texto, destaque…), não a ecrãs.
O resto da interface pede sempre o papel — `theme.P.text`, ou os nomes
curtos de `velo.ui.widgets` (TEXT, PANEL, ACCENT…) — e nunca escreve cores
à mão. Assim, mudar de tema é trocar a paleta e voltar a construir os ecrãs.

Acrescentar um tema: mais uma entrada em THEMES, com todos os papéis.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, fields, replace

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Palette:
    key: str
    name_pt: str
    name_en: str
    light: bool                 # fundo claro (texto escuro)
    bg: RGB                     # fundo da página
    panel: RGB                  # cartões e caixas
    panel2: RGB                 # superfícies secundárias, botões neutros
    border: RGB                 # contornos finos
    grid: RGB                   # linhas de grelha dos gráficos
    header: RGB                 # faixa do topo e cabeçalhos dos diálogos
    header_text: RGB
    header_dim: RGB
    text: RGB
    dim: RGB
    faint: RGB                  # desativado
    accent: RGB                 # ação principal, seleção
    accent_text: RGB            # texto em cima do destaque
    select: RGB                 # fundo da linha escolhida
    good: RGB
    bad: RGB
    warn: RGB
    warn_bg: RGB                # caixa de nota (amarelo claro)
    danger: RGB                 # botão «terminar»
    danger_soft: RGB            # botão «terminar sem guardar»
    chart_bar: RGB
    chart_line: RGB
    tooltip: RGB
    shade: RGB                  # véu por baixo dos diálogos
    shade_alpha: int
    hud_panel: RGB              # caixas do HUD, por cima da estrada 3D
    hud_alpha: int
    me_bg: RGB                  # a tua linha nas classificações
    heat: tuple                 # 5 tons do mapa de dias treinados
    power_line: RGB
    hr_line: RGB


_COMMON_LIGHT = dict(
    light=True, accent_text=(255, 255, 255), header_text=(255, 255, 255),
    good=(30, 132, 78), bad=(196, 50, 50), warn=(176, 112, 8), warn_bg=(254, 243, 205),
    danger=(196, 58, 52), danger_soft=(242, 222, 220), shade_alpha=120, hud_alpha=228,
    me_bg=(254, 241, 196), hr_line=(206, 40, 46),
)

THEMES: dict[str, Palette] = {}


def _add(p: Palette) -> None:
    THEMES[p.key] = p


_add(Palette(
    key="perennia", name_pt="Perennia (azul-marinho)", name_en="Perennia (navy)",
    bg=(242, 244, 248), panel=(255, 255, 255), panel2=(233, 237, 243),
    border=(214, 220, 229), grid=(228, 232, 238),
    header=(27, 38, 64), header_dim=(172, 186, 210),
    text=(28, 38, 54), dim=(104, 113, 128), faint=(166, 174, 186),
    accent=(10, 112, 204), select=(224, 236, 250),
    chart_bar=(122, 170, 222), chart_line=(10, 112, 204), tooltip=(228, 234, 243),
    shade=(22, 32, 54), hud_panel=(255, 255, 255),
    heat=((226, 231, 237), (196, 226, 204), (138, 198, 154), (78, 162, 104), (38, 120, 72)),
    power_line=(28, 38, 54), **_COMMON_LIGHT))

_add(Palette(
    key="salvia", name_pt="Sálvia (verde)", name_en="Sage (green)",
    bg=(242, 245, 241), panel=(255, 255, 255), panel2=(231, 238, 231),
    border=(211, 222, 211), grid=(225, 232, 224),
    header=(33, 66, 54), header_dim=(170, 198, 184),
    text=(28, 44, 37), dim=(98, 115, 106), faint=(160, 174, 166),
    accent=(36, 128, 82), select=(222, 239, 228),
    chart_bar=(128, 186, 150), chart_line=(36, 128, 82), tooltip=(226, 236, 228),
    shade=(24, 44, 36), hud_panel=(255, 255, 255),
    heat=((226, 233, 226), (200, 228, 206), (146, 200, 160), (84, 160, 112), (36, 116, 74)),
    power_line=(28, 44, 37), **_COMMON_LIGHT))

_add(Palette(
    key="areia", name_pt="Areia (quente)", name_en="Sand (warm)",
    bg=(246, 243, 238), panel=(255, 254, 251), panel2=(238, 232, 223),
    border=(223, 214, 201), grid=(234, 227, 217),
    header=(70, 56, 46), header_dim=(206, 190, 172),
    text=(50, 40, 33), dim=(120, 106, 94), faint=(176, 164, 152),
    accent=(176, 92, 36), select=(247, 232, 216),
    chart_bar=(214, 160, 116), chart_line=(176, 92, 36), tooltip=(240, 232, 220),
    shade=(54, 42, 34), hud_panel=(255, 254, 251),
    heat=((234, 228, 219), (212, 228, 200), (160, 200, 150), (100, 162, 104), (54, 120, 70)),
    power_line=(50, 40, 33), **_COMMON_LIGHT))

_add(Palette(
    key="ardosia", name_pt="Ardósia (pouca luz)", name_en="Slate (low light)",
    light=False,
    bg=(46, 56, 71), panel=(57, 69, 86), panel2=(66, 80, 99),
    border=(82, 97, 118), grid=(72, 86, 105),
    header=(33, 44, 59), header_text=(240, 244, 249), header_dim=(150, 166, 188),
    text=(236, 240, 246), dim=(166, 179, 197), faint=(118, 132, 150),
    accent=(104, 178, 240), accent_text=(22, 32, 46), select=(70, 92, 120),
    good=(112, 206, 142), bad=(240, 124, 112), warn=(238, 184, 86), warn_bg=(92, 80, 52),
    danger=(184, 66, 60), danger_soft=(98, 66, 66),
    chart_bar=(108, 160, 214), chart_line=(104, 178, 240), tooltip=(76, 92, 114),
    shade=(16, 22, 32), shade_alpha=150, hud_panel=(46, 56, 71), hud_alpha=210,
    me_bg=(96, 86, 52),
    heat=((66, 80, 99), (66, 104, 84), (88, 146, 104), (112, 190, 134), (164, 222, 150)),
    power_line=(240, 244, 249), hr_line=(240, 110, 110)))

DEFAULT = "perennia"
P: Palette = THEMES[DEFAULT]


def names() -> list[str]:
    return list(THEMES)


def rgba(c: RGB, a: int = 255) -> tuple[int, int, int, int]:
    return (c[0], c[1], c[2], a)


def ink(c) -> tuple[int, int, int, int]:
    """Uma cor de zona (pensada para preencher) usada como texto: num tema
    claro escurece-a, para se ler em cima do branco."""
    r, g, b = c[0], c[1], c[2]
    if P.light:
        k = 0.62
        r, g, b = int(r * k), int(g * k), int(b * k)
    return (r, g, b, 255)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------------------------------------------------------------- nomes curtos
# Nome curto (o que os módulos importam) → papel na paleta. Texto em RGBA.

SHORT = {
    "BG": ("bg", False), "PANEL": ("panel", False), "PANEL2": ("panel2", False),
    "BORDER": ("border", False), "GRID": ("grid", False), "HEADER": ("header", False),
    "HEADER_TEXT": ("header_text", True), "HEADER_DIM": ("header_dim", True),
    "TEXT": ("text", True), "DIM": ("dim", True), "FAINT": ("faint", True),
    "ACCENT": ("accent", True), "ACCENT_TEXT": ("accent_text", True),
    "SELECT": ("select", False), "GOOD": ("good", True), "BAD": ("bad", True),
    "WARN": ("warn", True), "WARN_BG": ("warn_bg", False), "DANGER": ("danger", False),
    "DANGER_SOFT": ("danger_soft", False), "TOOLTIP": ("tooltip", False),
}


def short_values(p: Palette | None = None) -> dict[str, tuple]:
    p = p or P
    out = {}
    for name, (role, is_text) in SHORT.items():
        c = getattr(p, role)
        out[name] = rgba(c) if is_text else tuple(c)
    return out


def apply(key: str) -> Palette:
    """Muda de tema. Atualiza os nomes curtos em todos os módulos da
    aplicação que os importaram (por identidade do valor antigo); os ecrãs
    construídos a seguir já nascem com as cores novas."""
    global P
    new = THEMES.get(key, THEMES[DEFAULT])
    if new is P:
        return P
    old_vals, old_p = short_values(P), P
    P = new
    new_vals = short_values(P)
    for mod_name, mod in list(sys.modules.items()):
        if mod is None or not mod_name.startswith("velo"):
            continue
        hook = getattr(mod, "_theme_changed", None)
        for name, old in old_vals.items():
            cur = getattr(mod, name, None)
            if cur is not None and cur == old and isinstance(cur, tuple):
                try:
                    setattr(mod, name, new_vals[name])
                except Exception:
                    pass
        if callable(hook):
            try:
                hook(old_p, P)
            except Exception:
                pass
    return P


def name(key: str) -> str:
    from velo.core.i18n import tr
    p = THEMES.get(key, THEMES[DEFAULT])
    return tr(p.name_pt, p.name_en)


def palette_roles() -> list[str]:
    return [f.name for f in fields(Palette)]


__all__ = ["Palette", "THEMES", "P", "apply", "ink", "mix", "rgba", "names", "name",
           "short_values", "replace"]
