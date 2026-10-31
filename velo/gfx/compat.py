"""Compatibilidade entre versões da pyglet (2.0 e 2.1+).

A 2.1 mudou a API das etiquetas: `bold=True` passou a `weight="bold"`, e
passar o argumento antigo levanta TypeError em vez de ser ignorado. Todo o
código da interface cria etiquetas por aqui, para a diferença viver num só
sítio. O mesmo se aplica à espessura das linhas (`width` → `thickness`).
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
import pyglet.text

# Tipos de letra por ordem de preferência: a pyglet aceita uma sequência e
# usa o primeiro que existir no sistema. Sem isto, no Windows caía no tipo
# por omissão sem avisar.
FONT = ("Segoe UI", "DejaVu Sans", "Helvetica Neue", "Helvetica", "Arial",
        "Liberation Sans", "Noto Sans")

_label_style: str | None = None      # "weight" | "bold", descoberto à primeira


def label(text: str = "", *, bold: bool = False, **kw) -> pyglet.text.Label:
    """Cria uma etiqueta, traduzindo `bold` para a API da versão instalada."""
    global _label_style
    kw.setdefault("font_name", FONT)
    if "color" not in kw:                 # por omissão, a cor do texto do tema
        from velo.gfx import theme
        kw["color"] = theme.rgba(theme.P.text)
    if _label_style == "weight":
        return pyglet.text.Label(text, weight="bold" if bold else "normal", **kw)
    if _label_style == "bold":
        return pyglet.text.Label(text, bold=bold, **kw)
    # primeira chamada: experimenta a API nova e cai para a antiga
    try:
        out = pyglet.text.Label(text, weight="bold" if bold else "normal", **kw)
        _label_style = "weight"
        return out
    except TypeError:
        out = pyglet.text.Label(text, bold=bold, **kw)
        _label_style = "bold"
        return out


def line(x: float, y: float, x2: float, y2: float, *, thickness: float = 2,
         color=(255, 255, 255), batch=None) -> pyglet.shapes.Line:
    try:
        return pyglet.shapes.Line(x, y, x2, y2, thickness=thickness, color=color,
                                  batch=batch)
    except TypeError:
        return pyglet.shapes.Line(x, y, x2, y2, width=thickness, color=color,
                                  batch=batch)
