"""O radar (aranha): um polígono com um eixo por categoria, de 0 a 100.

Serve ao índice de longevidade e à página de cada sessão (o que treinou: Z2 →
100 % aeróbio). Desenha com linhas e pontos; os eixos levam o nome e o valor.
"""
from __future__ import annotations

import math

import pyglet
import pyglet.graphics
import pyglet.shapes

from perennia.gfx.compat import label as make_label
from perennia.ui.widgets import ACCENT, DIM, GRID, TEXT, _line

MAX_AXES = 16
RINGS = (25, 50, 75, 100)


class RadarChart:
    def __init__(self):
        self.batch = pyglet.graphics.Batch()
        self.cx = self.cy = 0.0
        self.radius = 100.0
        self.values: list[tuple[str, float, str]] = []
        self._rings = [[_line(0, 0, 0, 0, GRID, self.batch) for _ in range(MAX_AXES)]
                       for _ in RINGS]
        self._spokes = [_line(0, 0, 0, 0, GRID, self.batch) for _ in range(MAX_AXES)]
        self._edges = [_line(0, 0, 0, 0, ACCENT[:3], self.batch) for _ in range(MAX_AXES)]
        self._dots = [pyglet.shapes.Circle(0, 0, 4, color=ACCENT[:3], batch=self.batch)
                      for _ in range(MAX_AXES)]
        self._labels = [make_label("", font_size=12, bold=True, color=TEXT, anchor_x="center",
                                   anchor_y="center", batch=self.batch)
                        for _ in range(MAX_AXES)]
        self._vals = [make_label("", font_size=11, color=DIM, anchor_x="center",
                                 anchor_y="center", batch=self.batch)
                      for _ in range(MAX_AXES)]
        self.empty = make_label("", font_size=13, color=DIM, anchor_x="center",
                                anchor_y="center", batch=self.batch)
        self.caption = make_label("", font_size=13, bold=True, color=ACCENT, anchor_x="center",
                                  anchor_y="center", batch=self.batch)

    # ------------------------------------------------------------ dados

    def layout(self, cx: float, cy: float, radius: float) -> None:
        self.cx, self.cy, self.radius = cx, cy, max(20.0, radius)
        self._place()

    def set(self, values: list[tuple[str, float, str]], empty: str = "") -> None:
        """`values`: [(rótulo, 0–100, texto do valor)] — pelo menos três para haver polígono."""
        self.values = list(values)[:MAX_AXES]
        self.empty.text = empty if not self.values else ""
        self._place()

    # --------------------------------------------------------- geometria

    def _angle(self, i: int, n: int) -> float:
        return math.pi / 2 - 2 * math.pi * i / max(1, n)

    def point(self, i: int, n: int, frac: float) -> tuple[float, float]:
        a = self._angle(i, n)
        return (self.cx + math.cos(a) * self.radius * frac,
                self.cy + math.sin(a) * self.radius * frac)

    def _hide(self, shape) -> None:
        shape.opacity = 0

    def _place(self) -> None:
        n = len(self.values)
        self.empty.x, self.empty.y = self.cx, self.cy
        self.caption.x, self.caption.y = self.cx, self.cy + self.radius + 58
        for k, ring in enumerate(self._rings):
            for i, ln in enumerate(ring):
                if i < n and n >= 3:
                    ln.x, ln.y = self.point(i, n, RINGS[k] / 100.0)
                    ln.x2, ln.y2 = self.point((i + 1) % n, n, RINGS[k] / 100.0)
                    ln.opacity = 255 if RINGS[k] == 100 else 110
                else:
                    ln.opacity = 0
        for i in range(MAX_AXES):
            spoke, edge, dot = self._spokes[i], self._edges[i], self._dots[i]
            lab, val = self._labels[i], self._vals[i]
            if i >= n or n < 3:
                for sh in (spoke, edge, dot):
                    sh.opacity = 0
                lab.text = val.text = ""
                continue
            name, v, text = self.values[i]
            f = max(0.0, min(100.0, v)) / 100.0
            spoke.x, spoke.y = self.cx, self.cy
            spoke.x2, spoke.y2 = self.point(i, n, 1.0)
            spoke.opacity = 110
            edge.x, edge.y = self.point(i, n, f)
            edge.x2, edge.y2 = self.point((i + 1) % n, n, max(0.0, min(100.0, self.values[
                (i + 1) % n][1])) / 100.0)
            edge.opacity = 255
            dot.x, dot.y = self.point(i, n, f)
            dot.opacity = 255
            lx, ly = self.point(i, n, 1.0)
            ox, oy = lx - self.cx, ly - self.cy
            norm = math.hypot(ox, oy) or 1.0
            lab.text, val.text = name, text
            lab.x, lab.y = lx + ox / norm * 44, ly + oy / norm * 22 + 8
            val.x, val.y = lab.x, lab.y - 16

    def draw(self) -> None:
        self.batch.draw()
