"""Verifica, contra a pyglet falsa, se o texto cabe nas caixas onde foi posto.

Cada etiqueta tem uma posição, uma âncora e um tamanho de letra; mede-se a largura com uma letra
real (Liberation Sans, a mesma largura do Segoe UI/Arial) e vê-se:
- se passa dos limites da janela;
- se passa dos limites da caixa mais pequena (um retângulo visível) que contém o ponto onde o
  texto está ancorado.
Os textos em várias linhas (`multiline`) quebram sozinhos e só se verifica a altura.

Uso nos testes: `issues = textfit.scan(created_labels, created_rects, window_w, window_h)`.
"""
from __future__ import annotations

from pathlib import Path

try:                                    # sem a Pillow não há medição: os testes saltam
    from PIL import ImageFont
except Exception:                       # pragma: no cover
    ImageFont = None

_FONT_DIRS = ("/usr/share/fonts/truetype/liberation", "C:/Windows/Fonts")
_FILES = {False: ("LiberationSans-Regular.ttf", "segoeui.ttf"),
          True: ("LiberationSans-Bold.ttf", "segoeuib.ttf")}
_CACHE: dict = {}
PX_PER_PT = 96.0 / 72.0                 # a pyglet mede o tamanho em pontos a 96 ppp
SLACK = 2.0                             # tolerância em píxeis


def available() -> bool:
    return ImageFont is not None and _font(12, False) is not None


def _font(size_px: float, bold: bool):
    key = (round(size_px, 1), bold)
    if key in _CACHE:
        return _CACHE[key]
    font = None
    if ImageFont is not None:
        for d in _FONT_DIRS:
            for name in _FILES[bold]:
                p = Path(d) / name
                if p.exists():
                    try:
                        font = ImageFont.truetype(str(p), max(1, int(round(size_px))))
                    except Exception:
                        font = None
                    break
            if font:
                break
    _CACHE[key] = font
    return font


def width_of(text: str, size_pt: float, bold: bool) -> float:
    f = _font(size_pt * PX_PER_PT, bold)
    if f is None:
        return len(text) * size_pt * PX_PER_PT * 0.52
    return max((f.getlength(line) for line in text.split("\n")), default=0.0)


def span(label) -> tuple[float, float, float]:
    """(x0, x1, largura) do texto de uma etiqueta."""
    size = float(getattr(label, "__dict__", {}).get("_fs_shown")
                 or getattr(label, "font_size", 12) or 12)       # já com a escala da letra
    bold = getattr(label, "weight", "normal") == "bold" or bool(getattr(label, "bold", False))
    w = width_of(str(label.text), size, bold)
    ax = getattr(label, "anchor_x", "left")
    x = float(label.x)
    if ax == "center":
        return x - w / 2, x + w / 2, w
    if ax == "right":
        return x - w, x, w
    return x, x + w, w


def _alive(obj) -> bool:
    return not getattr(obj, "deleted", False)


def _visible_rect(r, win_w: float, win_h: float) -> bool:
    if not _alive(r) or getattr(r, "opacity", 255) <= 0:
        return False
    w, h = float(r.width), float(r.height)
    if w < 24 or h < 14:
        return False
    return not (w >= win_w - 2 and h >= win_h - 2)        # o véu que cobre tudo não é uma caixa


def scan(labels, rects, win_w: float, win_h: float) -> list[dict]:
    """As etiquetas com texto que não cabem. Cada uma: texto, largura, limite, onde."""
    boxes = [r for r in rects if _visible_rect(r, win_w, win_h)]
    out = []
    for lab in labels:
        text = str(getattr(lab, "text", "") or "")
        if not text.strip() or not _alive(lab):
            continue
        if getattr(lab, "multiline", False):
            continue
        x0, x1, w = span(lab)
        if x0 < -SLACK or x1 > win_w + SLACK:
            out.append({"text": text, "w": round(w), "kind": "janela", "x0": round(x0),
                        "x1": round(x1), "limit": round(win_w)})
            continue
        # a caixa mais pequena que contém o ponto de ancoragem (um pouco acima da linha de base)
        px = float(lab.x)
        py = float(lab.y) + 2
        best = None
        for r in boxes:
            if r.x - 1 <= px <= r.x + r.width + 1 and r.y - 1 <= py <= r.y + r.height + 1:
                if best is None or r.width * r.height < best.width * best.height:
                    best = r
        if best is None:
            continue
        if x0 < best.x - SLACK or x1 > best.x + best.width + SLACK:
            out.append({"text": text, "w": round(w), "kind": "caixa", "x0": round(x0),
                        "x1": round(x1), "limit": f"{round(best.x)}–{round(best.x + best.width)}",
                        "box": (round(best.width), round(best.height)), "y": round(py)})
    return out


def scan_frame(frame, win_w: float, win_h: float) -> list[dict]:
    """Como `scan`, mas sobre o que se desenhou num fotograma, por ordem: uma etiqueta só conta
    com as caixas que foram desenhadas **antes** dela (as de cima tapam as de baixo)."""
    out = []
    seen = []
    for obj in frame:
        if hasattr(obj, "text"):
            out += scan([obj], seen, win_w, win_h)
        elif hasattr(obj, "width") and hasattr(obj, "height"):
            if (getattr(obj, "opacity", 255) > 0 and obj.width >= win_w - 2
                    and obj.height >= win_h - 2):
                seen = []                  # um véu a tapar tudo: o que estava por baixo não conta
            else:
                seen.append(obj)
    return out
