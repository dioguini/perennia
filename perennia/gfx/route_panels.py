"""Dois painéis da sessão de ciclismo com uma rota (.gpx):

* **Mapa** (`RouteMap`) — a rota vista de cima, com a parte já feita, os segmentos a
  vermelho e o ponto onde estás agora (a seta mostra o sentido). Liga e desliga com a tecla M
  (ou põe-se no ecrã em Definições → Desportos → Ciclismo → Disposição dos painéis).
* **Segmento** (`SegmentPanel`) — aparece sozinho quando entras num segmento: a altimetria do
  segmento com o **KOM** a vermelho, **o teu melhor** a azul e **tu agora** a rosa, e ao lado
  a tabela com o tempo de cada um, a diferença (Δ) no mesmo ponto e os W/kg.

Os dois desenham-se num batch próprio, por cima do HUD; as formas criam-se uma vez e só se
mexem (o mapa só se refaz quando muda a rota ou o tamanho).
"""
from __future__ import annotations

import math

import pyglet
import pyglet.shapes

from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.gfx import theme as _theme
from perennia.gfx.compat import label as make_label
from perennia.gfx.compat import line as make_line

KOM_RGB = (214, 48, 49)          # vermelho
BEST_RGB = (36, 110, 214)        # azul
ME_RGB = (232, 84, 160)          # rosa
OFF = -20000.0


def _rgb(c) -> tuple:
    return tuple(c[:3])


class RouteMap:
    MAX_LINES = 360

    def __init__(self):
        self.batch = pyglet.graphics.Batch()
        self.visible = False
        self.points: list = []
        self.segments: list = []
        self.rect = (OFF, OFF, 10.0, 10.0)
        self.bg = pyglet.shapes.Rectangle(OFF, OFF, 10, 10, color=_rgb(_theme.P.hud_panel),
                                          batch=self.batch)
        self.bg.opacity = 215
        self.title = make_label("", font_size=10, bold=True, batch=self.batch)
        self.info = make_label("", font_size=10, anchor_x="right", batch=self.batch)
        self._lines: list = []
        self._done: list = []
        self._seg_lines: list = []
        self.dot = pyglet.shapes.Circle(OFF, OFF, 6, color=ME_RGB, batch=self.batch)
        self.ring = pyglet.shapes.Circle(OFF, OFF, 9, color=(255, 255, 255), batch=self.batch)
        self.ring.opacity = 160
        self.arrow = make_line(OFF, OFF, OFF, OFF, thickness=3, color=ME_RGB, batch=self.batch)
        self.start = pyglet.shapes.Circle(OFF, OFF, 4, color=(40, 160, 90), batch=self.batch)
        self._key = None
        self._xy: list[tuple[float, float]] = []          # o ecrã de cada ponto desenhado
        self._dist: list[float] = []
        self.pos_m = 0.0

    # ------------------------------------------------------------ dados

    def set_route(self, points, segments=()) -> None:
        self.points = list(points or [])
        self.segments = list(segments or [])
        self._key = None

    def _project(self) -> None:
        """Os pontos da rota no retângulo, com a mesma escala nos dois eixos."""
        x, y, w, h = self.rect
        pts = self.points
        if len(pts) < 2:
            self._xy, self._dist = [], []
            return
        step = max(1, len(pts) // self.MAX_LINES)
        sample = pts[::step]
        if sample[-1] is not pts[-1]:
            sample.append(pts[-1])
        xs = [p.x_m for p in sample]
        ys = [p.y_m for p in sample]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        pad, head = 12, 22
        sw, sh = max(1.0, w - 2 * pad), max(1.0, h - 2 * pad - head)
        scale = min(sw / max(1.0, maxx - minx), sh / max(1.0, maxy - miny))
        ox = x + pad + (sw - (maxx - minx) * scale) / 2
        oy = y + pad + (sh - (maxy - miny) * scale) / 2
        self._xy = [(ox + (p.x_m - minx) * scale, oy + (p.y_m - miny) * scale) for p in sample]
        self._dist = [p.dist_m for p in sample]

    def _rebuild(self) -> None:
        for coll in (self._lines, self._done, self._seg_lines):
            for ln in coll:
                try:
                    ln.delete()
                except Exception:
                    pass
            coll.clear()
        self._project()
        base = _rgb(_theme.P.dim)
        for (a, b) in zip(self._xy, self._xy[1:]):
            self._lines.append(make_line(a[0], a[1], b[0], b[1], thickness=3, color=base,
                                         batch=self.batch))
        accent = _rgb(_theme.P.accent)
        for (a, b) in zip(self._xy, self._xy[1:]):
            ln = make_line(a[0], a[1], b[0], b[1], thickness=4, color=accent, batch=self.batch)
            ln.opacity = 0
            self._done.append(ln)
        for seg in self.segments:
            for i, (a, b) in enumerate(zip(self._xy, self._xy[1:])):
                d = self._dist[i]
                if seg.start_m <= d <= seg.end_m:
                    ln = make_line(a[0], a[1], b[0], b[1], thickness=5, color=KOM_RGB,
                                   batch=self.batch)
                    ln.opacity = 170
                    self._seg_lines.append(ln)
        if self._xy:
            self.start.x, self.start.y = self._xy[0]
        # o ponto e a seta ficam por cima (criados de novo depois das linhas)
        for s in (self.ring, self.dot, self.arrow):
            try:
                s.delete()
            except Exception:
                pass
        self.ring = pyglet.shapes.Circle(OFF, OFF, 9, color=(255, 255, 255), batch=self.batch)
        self.ring.opacity = 170
        self.dot = pyglet.shapes.Circle(OFF, OFF, 6, color=ME_RGB, batch=self.batch)
        self.arrow = make_line(OFF, OFF, OFF, OFF, thickness=3, color=ME_RGB, batch=self.batch)

    def layout(self, x: float, y: float, w: float, h: float) -> None:
        self.rect = (x, y, w, h)
        self.bg.x, self.bg.y, self.bg.width, self.bg.height = x, y, w, h
        self.title.x, self.title.y = x + 10, y + h - 16
        self.info.x, self.info.y = x + w - 10, y + h - 16
        self._key = None

    # ------------------------------------------------------------ ao vivo

    def screen_at(self, dist_m: float) -> tuple[float, float] | None:
        """Onde fica no ecrã um ponto da rota (para os testes e a seta)."""
        if not self._xy:
            return None
        import bisect
        i = bisect.bisect_left(self._dist, dist_m)
        if i <= 0:
            return self._xy[0]
        if i >= len(self._xy):
            return self._xy[-1]
        d0, d1 = self._dist[i - 1], self._dist[i]
        f = 0.0 if d1 <= d0 else (dist_m - d0) / (d1 - d0)
        (ax, ay), (bx, by) = self._xy[i - 1], self._xy[i]
        return ax + f * (bx - ax), ay + f * (by - ay)

    def update(self, pos_m: float, total_m: float | None = None) -> None:
        if not self.visible or not self.points:
            return
        key = (self.rect, len(self.points), len(self.segments))
        if key != self._key:
            self._rebuild()
            self._key = key
        self.pos_m = pos_m
        for i, ln in enumerate(self._done):
            ln.opacity = 255 if self._dist[i + 1] <= pos_m else 0
        p = self.screen_at(pos_m)
        if p is not None:
            self.dot.x, self.dot.y = p
            self.ring.x, self.ring.y = p
            q = self.screen_at(pos_m + 60.0)
            if q is not None and (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 > 1:
                ang = math.atan2(q[1] - p[1], q[0] - p[0])
                self.arrow.x, self.arrow.y = p
                self.arrow.x2, self.arrow.y2 = p[0] + 16 * math.cos(ang), p[1] + \
                    16 * math.sin(ang)
        total = total_m or (self.points[-1].dist_m if self.points else 0.0)
        self.title.text = tr("Mapa", "Map")
        self.info.text = f"{pos_m / 1000:.1f} / {total / 1000:.1f} km · M"

    def draw(self) -> None:
        if self.visible and self.points:
            self.batch.draw()


class SegmentPanel:
    """A altimetria do segmento com os três pontos, e a tabela ao lado."""

    COLS = ("", "Tempo", "Δ", "W/kg")

    def __init__(self):
        self.batch = pyglet.graphics.Batch()
        self.visible = False
        self.rect = (OFF, OFF, 10.0, 10.0)
        self.bg = pyglet.shapes.Rectangle(OFF, OFF, 10, 10, color=_rgb(_theme.P.hud_panel),
                                          batch=self.batch)
        self.bg.opacity = 225
        self.edge = pyglet.shapes.Rectangle(OFF, OFF, 10, 3, color=ME_RGB, batch=self.batch)
        self.title = make_label("", font_size=13, bold=True, batch=self.batch)
        self.sub = make_label("", font_size=10, batch=self.batch)
        self._bars: list = []
        self._markers: dict[str, tuple] = {}
        for key, rgb in (("kom", KOM_RGB), ("best", BEST_RGB), ("me", ME_RGB)):
            ln = pyglet.shapes.Rectangle(OFF, OFF, 2, 10, color=rgb, batch=self.batch)
            dot = pyglet.shapes.Circle(OFF, OFF, 6 if key == "me" else 5, color=rgb,
                                       batch=self.batch)
            self._markers[key] = (ln, dot)
        self.cells: list[list] = []
        for r in range(4):
            row = []
            for c in range(4):
                row.append(make_label("", font_size=11 if r else 9, bold=(r == 0 or c == 0),
                                      anchor_x="left" if c == 0 else "right",
                                      batch=self.batch))
            self.cells.append(row)
        self.swatches = [pyglet.shapes.Rectangle(OFF, OFF, 8, 8, color=rgb, batch=self.batch)
                         for rgb in (KOM_RGB, BEST_RGB, ME_RGB)]
        self._profile_key = None
        self._chart = (OFF, OFF, 10.0, 10.0)
        self.snapshot: dict | None = None

    def layout(self, x: float, y: float, w: float, h: float) -> None:
        self.rect = (x, y, w, h)
        self.bg.x, self.bg.y, self.bg.width, self.bg.height = x, y, w, h
        self.edge.x, self.edge.y, self.edge.width = x, y + h - 3, w
        self.title.x, self.title.y = x + 12, y + h - 22
        self.sub.x, self.sub.y = x + 12, y + h - 40
        table_w = min(330.0, w * 0.45)
        cw = max(60.0, w - table_w - 36)
        self._chart = (x + 12, y + 12, cw, max(20.0, h - 64))
        tx = x + 12 + cw + 18
        col_x = [tx + 14, tx + table_w * 0.55, tx + table_w * 0.78, tx + table_w - 6]
        top = y + h - 22
        rh = max(18.0, min(28.0, (h - 40) / 4))
        for r, row in enumerate(self.cells):
            for c, lab in enumerate(row):
                lab.x, lab.y = col_x[c], top - r * rh
        for k, sw in enumerate(self.swatches):
            sw.x, sw.y = tx, top - (k + 1) * rh + 1
        self._profile_key = None

    def _build_profile(self, profile) -> None:
        for b in self._bars:
            try:
                b.delete()
            except Exception:
                pass
        self._bars = []
        cx, cy, cw, ch = self._chart
        if not profile:
            return
        eles = [e for _d, e in profile]
        lo, hi = min(eles), max(eles)
        span = max(5.0, hi - lo)
        n = len(profile)
        bw = cw / n
        for i, (_d, e) in enumerate(profile):
            hgt = 6 + (e - lo) / span * (ch - 6)
            nxt = profile[min(i + 1, n - 1)][1]
            grade = (nxt - e) / max(1.0, profile[1][0] - profile[0][0]) * 100.0 if n > 1 else 0
            from perennia.gfx.hud import _grade_color
            bar = pyglet.shapes.Rectangle(cx + i * bw, cy, bw + 0.6, hgt,
                                          color=_grade_color(grade), batch=self.batch)
            bar.opacity = 170
            self._bars.append(bar)
        # os marcadores por cima das barras
        for key, rgb in (("kom", KOM_RGB), ("best", BEST_RGB), ("me", ME_RGB)):
            for s in self._markers[key]:
                try:
                    s.delete()
                except Exception:
                    pass
            ln = pyglet.shapes.Rectangle(OFF, OFF, 2, ch, color=rgb, batch=self.batch)
            dot = pyglet.shapes.Circle(OFF, OFF, 7 if key == "me" else 5, color=rgb,
                                       batch=self.batch)
            self._markers[key] = (ln, dot)
        self._eles = (lo, span)

    def marker_x(self, key: str) -> float | None:
        """Onde está o marcador de cada um (para os testes)."""
        ln, _dot = self._markers[key]
        return None if ln.x <= OFF + 1 else ln.x

    def update(self, snap: dict | None) -> None:
        self.snapshot = snap
        self.visible = snap is not None
        if snap is None:
            return
        key = (self.rect, id(snap["profile"]))
        if key != self._profile_key:
            self._build_profile(snap["profile"])
            self._profile_key = key
        cx, cy, cw, ch = self._chart
        length = max(1.0, snap["length_m"])
        lo, span = getattr(self, "_eles", (0.0, 1.0))
        prof = snap["profile"]
        for k in ("kom", "best", "me"):
            ln, dot = self._markers[k]
            m = snap["positions"].get(k)
            if m is None:
                ln.x = dot.x = OFF
                continue
            x = cx + cw * max(0.0, min(1.0, m / length))
            i = min(len(prof) - 1, max(0, int(round(m / length * (len(prof) - 1)))))
            y = cy + 6 + (prof[i][1] - lo) / span * (ch - 6) if prof else cy + ch / 2
            ln.x, ln.y, ln.height = x - 1, cy, ch
            ln.opacity = 120
            dot.x, dot.y = x, y
        self.title.text = snap["name"]
        self.sub.text = (f"{snap['source']} · {snap['frac'] * 100:.0f} % · "
                         f"{length / 1000:.2f} km · " + hms(snap["elapsed_s"]))
        heads = ("", tr("Tempo", "Time"), "Δ", "W/kg")
        for c, lab in enumerate(self.cells[0]):
            lab.text = heads[c]
        rows = {r["key"]: r for r in snap["rows"]}
        for r_i, k in enumerate(("kom", "best", "me"), start=1):
            row = rows.get(k)
            cells = self.cells[r_i]
            if row is None:
                cells[0].text = {"kom": "KOM", "best": tr("O meu melhor", "My best"),
                                 "me": tr("Eu agora", "Me now")}[k]
                cells[1].text, cells[2].text, cells[3].text = "—", "", ""
                continue
            cells[0].text = row["label"]
            approx = "≈" if row.get("estimated") else ""
            cells[1].text = hms(row["total_s"]) if row.get("total_s") else "—"
            d = row.get("delta_s")
            cells[2].text = "" if d is None else ("+" if d >= 0 else "−") + hms(abs(d))
            cells[2].color = _theme.rgba(_theme.P.danger) if d and d > 0 else \
                _theme.rgba(_theme.P.good)
            cells[3].text = (approx + f"{row['wkg']:.1f}") if row.get("wkg") else "—"

    def texts(self) -> list[str]:
        return [lab.text for row in self.cells for lab in row] + [self.title.text,
                                                                  self.sub.text]

    def draw(self) -> None:
        if self.visible:
            self.batch.draw()
