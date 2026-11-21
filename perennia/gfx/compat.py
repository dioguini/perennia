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

# O tamanho da letra de toda a aplicação, em % (Definições → Aspeto; opção `ui_font_pct`).
# É aqui, num só sítio, que se multiplica: o código continua a pedir «font_size=15» e a etiqueta
# nasce com 15 × FONT_PCT / 100. Os ecrãs já abertos mantêm o que tinham até se reabrirem.
FONT_PCT = 100


def scaled(size: float) -> float:
    """O tamanho de letra pedido, já com a escala (nunca abaixo de 6)."""
    return max(6.0, round(float(size) * FONT_PCT / 100.0, 1)) if FONT_PCT != 100 else size


def scale_factor() -> float:
    return FONT_PCT / 100.0


_CLASSES: dict = {}


def _scaled_class(base):
    """A classe da etiqueta, derivada da `pyglet.text.Label` que existir **agora** (os testes
    trocam-na por uma de mentira), com um `font_size` que é sempre o **pedido** (sem escala):
    quem lê ou escreve continua a pensar em «15», e a letra que se vê é 15 × FONT_PCT / 100.
    Assim os ecrãs que ajustam o tamanho ao espaço (`val.font_size = size`) respeitam a escala
    sem mudar."""
    cls = _CLASSES.get(base)
    if cls is None:
        base_prop = getattr(base, "font_size", None)

        class _ScaledLabel(base):
            @property
            def font_size(self):
                return self.__dict__.get("_fs_req", 12)

            @font_size.setter
            def font_size(self, value) -> None:
                self.__dict__["_fs_req"] = value
                real = scaled(value)
                if isinstance(base_prop, property):
                    base_prop.fset(self, real)
                else:                          # a pyglet de mentira dos testes
                    self.__dict__["_fs_shown"] = real
        cls = _CLASSES[base] = _ScaledLabel
    return cls


def label(text: str = "", *, bold: bool = False, **kw) -> pyglet.text.Label:
    """Cria uma etiqueta, traduzindo `bold` para a API da versão instalada."""
    global _label_style
    kw.setdefault("font_name", FONT)
    asked = kw.get("font_size")
    if asked is not None and FONT_PCT != 100:
        kw["font_size"] = scaled(asked)
    if "color" not in kw:                 # por omissão, a cor do texto do tema
        from perennia.gfx import theme
        kw["color"] = theme.rgba(theme.P.text)
    if _label_style == "weight":
        out = _scaled_class(pyglet.text.Label)(text, weight="bold" if bold else "normal", **kw)
    elif _label_style == "bold":
        out = _scaled_class(pyglet.text.Label)(text, bold=bold, **kw)
    else:
        # primeira chamada: experimenta a API nova e cai para a antiga
        try:
            out = _scaled_class(pyglet.text.Label)(text, weight="bold" if bold else "normal", **kw)
            _label_style = "weight"
        except TypeError:
            out = _scaled_class(pyglet.text.Label)(text, bold=bold, **kw)
            _label_style = "bold"
    if asked is not None:
        out.__dict__["_fs_req"] = asked      # o pedido, sem escala (ver _ScaledLabel)
    return out


def line(x: float, y: float, x2: float, y2: float, *, thickness: float = 2,
         color=(255, 255, 255), batch=None) -> pyglet.shapes.Line:
    try:
        return pyglet.shapes.Line(x, y, x2, y2, thickness=thickness, color=color,
                                  batch=batch)
    except TypeError:
        return pyglet.shapes.Line(x, y, x2, y2, width=thickness, color=color,
                                  batch=batch)
