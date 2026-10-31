"""Blocos de interface mínimos, construídos sobre pyglet.

Navegação primeiro pelo teclado — quem está em cima da bicicleta não chega
bem ao rato. As setas movem, Enter escolhe, Esc volta atrás; o rato também
funciona para quem está a preparar a sessão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pyglet
import pyglet.shapes
import pyglet.text

from velo.core.curves import log_positions, monotone_cubic
from velo.gfx.compat import label as make_label, line as _line_compat

from velo.gfx import theme as _theme

# As cores vêm do tema (velo.gfx.theme). Os nomes curtos são reatribuídos
# quando se muda de tema; os ecrãs novos já nascem com as cores certas.
_V = _theme.short_values()
BG, PANEL, PANEL2, BORDER, GRID = _V["BG"], _V["PANEL"], _V["PANEL2"], _V["BORDER"], _V["GRID"]
HEADER, HEADER_TEXT, HEADER_DIM = _V["HEADER"], _V["HEADER_TEXT"], _V["HEADER_DIM"]
TEXT, DIM, FAINT = _V["TEXT"], _V["DIM"], _V["FAINT"]
ACCENT, ACCENT_TEXT, SELECT = _V["ACCENT"], _V["ACCENT_TEXT"], _V["SELECT"]
GOOD, BAD, WARN, WARN_BG = _V["GOOD"], _V["BAD"], _V["WARN"], _V["WARN_BG"]
DANGER, DANGER_SOFT, TOOLTIP = _V["DANGER"], _V["DANGER_SOFT"], _V["TOOLTIP"]
del _V


def P():
    """A paleta em uso (para os papéis sem nome curto)."""
    return _theme.P

ROW_H = 38


def _line(x, y, x2, y2, color, batch):
    return _line_compat(x, y, x2, y2, thickness=2, color=color, batch=batch)


@dataclass
class Item:
    """Uma linha de uma lista: rótulo, valor opcional e ação.

    `button=True`: em vez de uma linha, é um botão de ação na faixa de baixo,
    à direita (Guardar, Cancelar…). Continua na lista para o teclado: ↑↓
    chegam lá e Enter carrega nele."""
    label: str
    value: str = ""
    action: Callable[[], None] | None = None
    detail: str = ""
    enabled: bool = True
    data: object = None
    button: bool = False
    primary: bool = False         # o botão principal (Guardar) fica realçado


BUTTON_H = 36
BUTTON_Y = 14


def button_width(text: str) -> float:
    return max(110.0, len(text) * 8.2 + 36)


class ListView:
    """Lista com seleção, sem barra de deslocamento: quando as linhas não cabem
    na altura, continuam numa coluna ao lado (o ecrã é ocupado na largura).
    Só se nem assim couberem é que se passa à «página» seguinte.

    As linhas com `button=True` não aparecem na lista: são os botões de ação
    da faixa de baixo, à direita."""

    MIN_COL_W = 300
    COL_GAP = 28

    def __init__(self, x: int, y: int, width: int, visible_rows: int = 10):
        self.x, self.y, self.width = x, y, width
        self.visible_rows = visible_rows
        self.items: list[Item] = []
        self.index = 0
        self.scroll = 0               # primeira linha da página à vista
        self.columns = 1
        self.max_columns: int | None = None    # None: as que couberem na largura
        self.bar_right: float | None = None    # onde acabam os botões (à direita)
        self.bar_y = BUTTON_Y
        self.batch = pyglet.graphics.Batch()
        self._rows = []
        self._buttons = []
        self._cells: list[tuple[int, float, float, float]] = []   # (índice, x, y, largura)
        self._button_rects: list[tuple[int, float, float, float]] = []
        self.page_label = make_label("", font_size=10, color=DIM, anchor_x="right",
                                     anchor_y="center", batch=self.batch)
        self._add_rows(visible_rows)

    def _add_rows(self, n: int) -> None:
        for _ in range(n):
            highlight = pyglet.shapes.Rectangle(0, 0, self.width, ROW_H - 4,
                                                color=SELECT, batch=self.batch)
            highlight.opacity = 0
            highlight._bar = pyglet.shapes.Rectangle(0, 0, 3, ROW_H - 4, color=ACCENT[:3],
                                                     batch=self.batch)
            highlight._bar.opacity = 0
            label = make_label("", font_size=14, color=TEXT,
                                      anchor_y="center", batch=self.batch)
            value = make_label("", font_size=13, color=DIM,
                                      anchor_x="right", anchor_y="center",
                                      batch=self.batch)
            detail = make_label("", font_size=11, color=DIM,
                                       anchor_y="center", batch=self.batch)
            self._rows.append((highlight, label, value, detail))

    def _add_button(self) -> None:
        outline = pyglet.shapes.Rectangle(0, 0, 10, BUTTON_H + 2, color=BORDER, batch=self.batch)
        bg = pyglet.shapes.Rectangle(0, 0, 10, BUTTON_H, color=PANEL, batch=self.batch)
        lab = make_label("", font_size=13, bold=True, color=TEXT, anchor_x="center",
                         anchor_y="center", batch=self.batch)
        self._buttons.append((outline, bg, lab))

    def set_visible_rows(self, n: int) -> None:
        """Ao mudar o tamanho da janela: tantas linhas desenhadas quantas cabem."""
        n = max(1, n)
        if n > len(self._rows):
            self._add_rows(n - len(self._rows))
        elif n < len(self._rows):
            for highlight, label, value, detail in self._rows[n:]:
                for obj in (highlight, highlight._bar, label, value, detail):
                    try:
                        obj.delete()
                    except Exception:
                        pass
            self._rows = self._rows[:n]
        self.visible_rows = n
        self._sync()

    def set_items(self, items: list[Item], keep_index: bool = False) -> None:
        self.items = items
        if not keep_index or self.index >= len(items):
            self.index = 0
            self.scroll = 0
        self._sync()

    # ------------------------------------------------------------- arrumar

    def row_indices(self) -> list[int]:
        return [i for i, it in enumerate(self.items) if not it.button]

    def button_indices(self) -> list[int]:
        return [i for i, it in enumerate(self.items) if it.button]

    def _columns_for(self, n: int) -> int:
        per = max(1, self.visible_rows)
        fit = max(1, int((self.width + self.COL_GAP) // (self.MIN_COL_W + self.COL_GAP)))
        if self.max_columns is not None:
            fit = max(1, min(fit, self.max_columns))
        return max(1, min(fit, -(-n // per)))

    def _sync(self) -> None:
        rows = self.row_indices()
        per = max(1, self.visible_rows)
        cols = self._columns_for(len(rows))
        self.columns = cols
        page = per * cols
        if self.index in rows:
            pos = rows.index(self.index)
            self.scroll = (pos // page) * page
        self.scroll = max(0, min(self.scroll, max(0, len(rows) - 1)))
        self.scroll -= self.scroll % page
        shown = rows[self.scroll:self.scroll + page]
        need = len(shown)
        if need > len(self._rows):
            self._add_rows(need - len(self._rows))
        col_w = (self.width - self.COL_GAP * (cols - 1)) / cols
        self._cells = []
        for k, (highlight, label, value, detail) in enumerate(self._rows):
            if k >= len(shown):
                highlight.opacity = highlight._bar.opacity = 0
                label.text = value.text = detail.text = ""
                continue
            idx = shown[k]
            c, r = divmod(k, per)
            x = self.x + c * (col_w + self.COL_GAP)
            row_y = self.y - r * ROW_H
            self._cells.append((idx, x, row_y, col_w))
            highlight.x, highlight.y = x - 10, row_y - ROW_H // 2 + 2
            highlight.width = col_w + 20
            highlight.opacity = 255 if idx == self.index else 0
            highlight._bar.x, highlight._bar.y = highlight.x, highlight.y
            highlight._bar.opacity = highlight.opacity
            item = self.items[idx]
            value.text = item.value
            value.x, value.y = x + col_w, row_y
            # o rótulo e a nota não podem passar por baixo do valor à direita
            free = col_w - len(item.value) * 7.5 - 18
            label.text = _fit(item.label, free, 14) if cols > 1 else item.label
            label.x, label.y = x, row_y + (6 if item.detail else 0)
            label.color = (TEXT if item.enabled else DIM) if idx != self.index \
                else ACCENT
            room = int(free / 6.0)
            d = item.detail or ""
            detail.text = d if len(d) <= room else d[:max(0, room - 1)] + "…"
            detail.x, detail.y = x, row_y - 12
        pages = -(-len(rows) // page) if rows else 1
        self.page_label.text = (f"{self.scroll // page + 1}/{pages}  ↑↓"
                                if pages > 1 else "")
        self.page_label.x = self.x + self.width
        self.page_label.y = self.y - per * ROW_H + ROW_H // 2 - 4
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        ids = self.button_indices()
        while len(self._buttons) < len(ids):
            self._add_button()
        self._button_rects = []
        right = self.bar_right
        x = right if right is not None else self.x + self.width
        widths = [button_width(self.items[i].label) for i in ids]
        x -= sum(widths) + 10 * max(0, len(ids) - 1)
        for k, (outline, bg, lab) in enumerate(self._buttons):
            if k >= len(ids):
                outline.opacity = bg.opacity = 0
                lab.text = ""
                continue
            idx = ids[k]
            item = self.items[idx]
            bw = widths[k]
            on = idx == self.index
            bg.x, bg.y, bg.width, bg.height = x, self.bar_y, bw, BUTTON_H
            outline.x, outline.y, outline.width = x - 1, self.bar_y - 1, bw + 2
            outline.height = BUTTON_H + 2
            outline.color = ACCENT[:3] if (on or item.primary) else BORDER
            bg.color = ACCENT[:3] if item.primary and item.enabled else (SELECT if on else PANEL)
            outline.opacity = bg.opacity = 255
            lab.text = item.label
            lab.x, lab.y = x + bw / 2, self.bar_y + BUTTON_H / 2
            if item.primary and item.enabled:
                lab.color = ACCENT_TEXT
            else:
                lab.color = ACCENT if on else (TEXT if item.enabled else DIM)
            self._button_rects.append((idx, x, bw, self.bar_y))
            x += bw + 10

    @property
    def buttons_left(self) -> float | None:
        """Onde começam os botões de ação (para o rodapé não lhes passar por cima)."""
        if not self._button_rects:
            return None
        return self._button_rects[0][1]

    @property
    def selected(self) -> Item | None:
        if 0 <= self.index < len(self.items):
            return self.items[self.index]
        return None

    def move(self, step: int) -> None:
        if not self.items:
            return
        self.index = (self.index + step) % len(self.items)
        self._sync()

    def select_data(self, data) -> bool:
        for i, it in enumerate(self.items):
            if it.data == data:
                self.index = i
                self._sync()
                return True
        return False

    def activate(self) -> None:
        item = self.selected
        if item is not None and item.enabled and item.action is not None:
            item.action()

    def press_button(self, which: str = "primary") -> bool:
        """Carrega no botão principal (Ctrl+S) — devolve False se não houver."""
        for i in self.button_indices():
            it = self.items[i]
            if (which == "primary" and it.primary) and it.enabled and it.action is not None:
                self.index = i
                self._sync()
                it.action()
                return True
        return False

    def on_mouse_press(self, mx: int, my: int) -> bool:
        for idx, x, bw, y in self._button_rects:
            if x <= mx <= x + bw and y <= my <= y + BUTTON_H:
                self.index = idx
                self._sync()
                self.activate()
                return True
        for idx, x, row_y, col_w in self._cells:
            top = row_y + ROW_H // 2
            bottom = top - ROW_H
            if bottom <= my <= top and x - 10 <= mx <= x + col_w + 10:
                self.index = idx
                self._sync()
                self.activate()
                return True
        return False

    def draw(self) -> None:
        self.batch.draw()


class Chrome:
    """Título, subtítulo e rodapé com as teclas disponíveis."""

    def __init__(self, window):
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.title = make_label("", font_size=26, bold=True,
                                       color=TEXT, anchor_y="top", batch=self.batch)
        self.subtitle = make_label("", font_size=13, color=DIM,
                                          anchor_y="top", batch=self.batch)
        self.footer = make_label("", font_size=11, color=DIM,
                                        batch=self.batch)
        self.message = make_label("", font_size=13, color=ACCENT,
                                         anchor_y="top", batch=self.batch)
        self.agent_hint = make_label("", font_size=10, color=DIM, anchor_x="right",
                                     batch=self.batch)
        self.footer_x = 48
        self.footer_full = ""
        self.footer_limit: float | None = None      # onde começam os botões de ação
        self.layout()

    def layout(self) -> None:
        w, h = self.window.width, self.window.height
        self.title.x, self.title.y = 48, h - 40
        self.subtitle.x, self.subtitle.y = 48, h - 78
        self.message.x, self.message.y = 48, 76
        self.footer.x, self.footer.y = self.footer_x, 26
        # a dica do agente fica em cima, à direita: em baixo estão os botões
        self.agent_hint.x, self.agent_hint.y = w - 48, h - 52

    def set(self, title: str, subtitle: str = "", footer: str = "") -> None:
        self.title.text = title
        self.subtitle.text = subtitle
        self.footer_full = footer
        self._fit_footer()

    def set_footer_limit(self, x_right: float | None) -> None:
        if x_right != self.footer_limit:
            self.footer_limit = x_right
            self._fit_footer()

    def _fit_footer(self) -> None:
        right = self.footer_limit if self.footer_limit is not None else self.window.width - 48
        self.footer.text = _fit(self.footer_full, max(60.0, right - 20 - self.footer_x), 11)

    def draw(self) -> None:
        self.batch.draw()


class Chart:
    """Gráfico de barras ou de linha para as estatísticas.

    Mostra os valores no eixo vertical (três marcas), as legendas no eixo do
    tempo, e deixa escolher um ponto — com o rato (`hit`) ou com as setas
    (`select`) — para ver o pormenor numa caixa por cima do gráfico.
    """

    def __init__(self, x: int, y: int, width: int, height: int, max_points: int = 120):
        self.x, self.y, self.width, self.height = x, y, width, height
        self.batch = pyglet.graphics.Batch()
        self._bg = pyglet.shapes.Rectangle(x, y, width, height, color=PANEL,
                                           batch=self.batch)
        self._grid = [pyglet.shapes.Rectangle(x, y, width, 1, color=GRID,
                                              batch=self.batch) for _ in range(3)]
        self._bars = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=P().chart_bar,
                                              batch=self.batch)
                      for _ in range(max_points)]
        self._lines = [_line(0, 0, 0, 0, P().chart_line, self.batch)
                       for _ in range(max_points)]
        self._labels = [make_label("", font_size=9, color=DIM,
                                   anchor_x="center", batch=self.batch)
                        for _ in range(16)]
        self._yticks = [make_label("", font_size=9, color=DIM, anchor_x="right",
                                   anchor_y="center", batch=self.batch) for _ in range(3)]
        self._dots = [pyglet.shapes.Circle(0, 0, 0, color=P().chart_line,
                                           batch=self.batch) for _ in range(16)]
        self._sel_line = pyglet.shapes.Rectangle(0, 0, 2, height, color=TEXT[:3],
                                                 batch=self.batch)
        self._sel_line.opacity = 0
        self._sel_dot = pyglet.shapes.Circle(0, 0, 0, color=TEXT[:3],
                                             batch=self.batch)
        self._tip_bg = pyglet.shapes.Rectangle(0, 0, 10, 26, color=TOOLTIP,
                                               batch=self.batch)
        self._tip_bg.opacity = 0
        self._tip = make_label("", font_size=11, bold=True, color=TEXT,
                               anchor_y="center", batch=self.batch)
        self.title = make_label("", font_size=13, bold=True, color=TEXT, batch=self.batch)
        self.empty = make_label("", font_size=12, color=DIM, anchor_x="center",
                                anchor_y="center", batch=self.batch)
        self.points: list[tuple[float, float]] = []      # (x, y) de cada valor, para o rato
        self.selected: int | None = None
        self._series_lines: list[list] = []              # linhas extra (várias séries)
        self._stack: list = []                           # retângulos das barras empilhadas
        self._legend = [make_label("", font_size=10, color=TEXT, anchor_x="right",
                                   batch=self.batch) for _ in range(4)]
        self._zero = pyglet.shapes.Rectangle(x, y, width, 1, color=DIM[:3],
                                             batch=self.batch)
        self._zero.opacity = 0
        self._place_static()

    def _place_static(self) -> None:
        x, y, w, h = self.x, self.y, self.width, self.height
        self._bg.x, self._bg.y, self._bg.width, self._bg.height = x, y, w, h
        self.title.x, self.title.y = x, y + h + 10
        self.empty.x, self.empty.y = x + w // 2, y + h // 2
        for k, g in enumerate(self._grid):
            g.x, g.width = x, w
            g.y = y + 8 + (h - 16) * k / 2
        self._sel_line.height = h

    def _clear(self) -> None:
        for b in self._bars:
            b.height = 0
            b.width = 0
            b.color = P().chart_bar
            b.opacity = 255
        for ln in self._lines:
            ln.x = ln.x2 = ln.y = ln.y2 = 0
        for lab in self._labels + self._yticks:
            lab.text = ""
        for dot in self._dots:
            dot.radius = 0
        for pool in getattr(self, "_series_lines", []):
            for ln in pool:
                ln.x = ln.x2 = ln.y = ln.y2 = 0
        for rect in getattr(self, "_stack", []):
            rect.width = rect.height = 0
        for lab in getattr(self, "_legend", []):
            lab.text = ""
        if hasattr(self, "_zero"):
            self._zero.opacity = 0
        self.points = []
        self.selected = None
        self._hide_selection()

    def _ticks(self, lo: float, hi: float, fmt) -> None:
        for k, lab in enumerate(self._yticks):
            v = lo + (hi - lo) * k / 2
            lab.text = fmt(v) if fmt else f"{v:.0f}"
            lab.x, lab.y = self.x - 6, self.y + 8 + (self.height - 16) * k / 2

    # ---------------------------------------------------------------- barras

    def show_bars(self, title: str, values: list[float], labels: list[str] | None = None,
                  empty_text: str = "", fmt=None, colors: list | None = None) -> None:
        self._clear()
        self.title.text = title
        if not values or max(values) <= 0:
            self.empty.text = empty_text
            return
        self.empty.text = ""
        n = min(len(values), len(self._bars))
        peak = max(values[:n]) or 1.0
        bar_w = self.width / n
        for i in range(n):
            bar = self._bars[i]
            bar.x = self.x + i * bar_w + 1
            bar.y = self.y
            bar.width = max(1.0, bar_w - 2)
            bar.height = max(1.0, values[i] / peak * (self.height - 16)) if values[i] else 0
            if colors and i < len(colors):
                bar.color = colors[i]
            self.points.append((bar.x + bar.width / 2, self.y + bar.height))
        self._ticks(0.0, peak, fmt)
        if labels:
            step = max(1, -(-n // len(self._labels)))
            for j, lab in enumerate(self._labels):
                i = j * step
                if i < n and i < len(labels):
                    lab.text = labels[i]
                    lab.x = self.x + i * bar_w + bar_w / 2
                    lab.y = self.y - 14

    # ----------------------------------------------------------------- linha

    def show_line(self, title: str, values: list[float], labels: list[str] | None = None,
                  empty_text: str = "", log_x: bool = False,
                  xs: list[float] | None = None, fmt=None) -> None:
        self._clear()
        self.title.text = title
        if len(values) < 2:
            self.empty.text = empty_text
            return
        self.empty.text = ""
        if log_x and xs and len(xs) == len(values):
            self._show_smooth_log(values, labels, xs, fmt)
            return
        n = min(len(values), len(self._lines) + 1)
        peak = max(values[:n]) or 1.0
        floor = min(values[:n])
        span = max(peak - floor, 1.0)
        for i in range(n):
            px = self.x + self.width * i / (n - 1)
            py = self.y + (values[i] - floor) / span * (self.height - 16) + 8
            self.points.append((px, py))
        for i in range(n - 1):
            ln = self._lines[i]
            ln.x, ln.y = self.points[i]
            ln.x2, ln.y2 = self.points[i + 1]
        self._ticks(floor, floor + span, fmt)
        if labels:
            step = max(1, -(-n // len(self._labels)))
            for j, lab in enumerate(self._labels):
                i = j * step
                if i < n and i < len(labels):
                    lab.text = labels[i]
                    lab.x = self.x + self.width * i / max(1, n - 1)
                    lab.y = self.y - 14

    def _show_smooth_log(self, values: list[float], labels: list[str] | None,
                         xs: list[float], fmt=None) -> None:
        """Curva suave em escala logarítmica, com área por baixo e os pontos
        medidos marcados. É assim que se lê uma curva de potência."""
        pos = log_positions(xs)
        n = len(self._lines) + 1
        sx, sy = monotone_cubic(pos, values, n)
        peak = max(max(values), 1.0)
        floor = min(min(values) * 0.9, peak)
        span = max(peak - floor, 1.0)
        top = self.height - 16

        def py(v: float) -> float:
            return self.y + 8 + (v - floor) / span * top

        for i in range(n - 1):
            ln = self._lines[i]
            ln.x, ln.x2 = self.x + sx[i] * self.width, self.x + sx[i + 1] * self.width
            ln.y, ln.y2 = py(sy[i]), py(sy[i + 1])
        cols = len(self._bars)
        for i, bar in enumerate(self._bars):
            v = sy[min(n - 1, int(i * (n - 1) / max(cols - 1, 1)))]
            bar.x = self.x + self.width * i / cols
            bar.y = self.y
            bar.width = self.width / cols + 1
            bar.height = max(0.0, py(v) - self.y)
            bar.color = P().chart_line
            bar.opacity = 46
        for i, (p, v) in enumerate(zip(pos, values)):
            x, y = self.x + p * self.width, py(v)
            self.points.append((x, y))
            if i < len(self._dots):
                dot = self._dots[i]
                dot.x, dot.y, dot.radius = x, y, 3.5
        self._ticks(floor, floor + span, fmt)
        if labels:
            for lab, p, text in zip(self._labels, pos, labels):
                lab.text = text
                lab.x = self.x + p * self.width
                lab.y = self.y - 14

    # ------------------------------------------------------ várias linhas

    def show_lines(self, title: str, series: list[tuple[str, list[float], tuple]],
                   labels: list[str] | None = None, empty_text: str = "",
                   fmt=None) -> None:
        """Várias séries na mesma escala (fitness, fadiga e forma). `series`:
        [(nome, valores, cor)]. A linha do zero aparece se houver negativos."""
        self._clear()
        self.title.text = title
        series = [s for s in series if len(s[1]) >= 2]
        if not series:
            self.empty.text = empty_text
            return
        self.empty.text = ""
        n = min(min(len(v) for _, v, _ in series), len(self._lines) + 1)
        allv = [x for _, v, _ in series for x in v[:n]]
        peak, floor = max(allv), min(allv)
        floor = min(floor, 0.0) if floor < 0 else floor
        span = max(peak - floor, 1.0)

        def py(v: float) -> float:
            return self.y + 8 + (v - floor) / span * (self.height - 16)

        while len(self._series_lines) < len(series) - 1:
            self._series_lines.append([_line(0, 0, 0, 0, TEXT[:3], self.batch)
                                       for _ in range(len(self._lines))])
        for k, (name, values, color) in enumerate(series):
            pool = self._lines if k == 0 else self._series_lines[k - 1]
            pts = [(self.x + self.width * i / (n - 1), py(values[i])) for i in range(n)]
            if k == 0:
                self.points = pts
            for i in range(n - 1):
                ln = pool[i]
                ln.x, ln.y = pts[i]
                ln.x2, ln.y2 = pts[i + 1]
                ln.color = color[:3]
            if k < len(self._legend):
                lab = self._legend[k]
                lab.text = f"— {name}"
                lab.color = _theme.ink(color)
        for ln in self._lines[n - 1:]:
            ln.x = ln.x2 = ln.y = ln.y2 = 0
        self._place_legend()
        if floor < 0 < peak:
            self._zero.x, self._zero.y, self._zero.width = self.x, py(0.0), self.width
            self._zero.opacity = 160
        self._ticks(floor, floor + span, fmt)
        if labels:
            step = max(1, -(-n // len(self._labels)))
            for j, lab in enumerate(self._labels):
                i = j * step
                if i < n and i < len(labels):
                    lab.text = labels[i]
                    lab.x = self.x + self.width * i / max(1, n - 1)
                    lab.y = self.y - 14

    # ------------------------------------------------------ barras empilhadas

    def show_stacked(self, title: str, rows: list[list[float]], colors: list[tuple],
                     labels: list[str] | None = None, empty_text: str = "", fmt=None,
                     legend: list[str] | None = None) -> None:
        """Uma barra por período, partida em fatias (uma por zona ou desporto)."""
        self._clear()
        self.title.text = title
        totals = [sum(r) for r in rows]
        if not rows or max(totals or [0]) <= 0:
            self.empty.text = empty_text
            return
        self.empty.text = ""
        n = min(len(rows), len(self._bars))
        parts = max(len(r) for r in rows[:n])
        need = n * parts
        while len(self._stack) < need:
            self._stack.append(pyglet.shapes.Rectangle(0, 0, 0, 0, color=P().chart_bar,
                                                       batch=self.batch))
        peak = max(totals[:n]) or 1.0
        bar_w = self.width / n
        for i in range(n):
            y = self.y
            for k, v in enumerate(rows[i]):
                rect = self._stack[i * parts + k]
                h = v / peak * (self.height - 16) if v > 0 else 0.0
                rect.x, rect.y = self.x + i * bar_w + 1, y
                rect.width, rect.height = max(1.0, bar_w - 2) if h else 0, h
                rect.color = colors[k % len(colors)][:3]
                y += h
            self.points.append((self.x + i * bar_w + bar_w / 2, y))
        self._ticks(0.0, peak, fmt)
        if labels:
            step = max(1, -(-n // len(self._labels)))
            for j, lab in enumerate(self._labels):
                i = j * step
                if i < n and i < len(labels):
                    lab.text = labels[i]
                    lab.x = self.x + i * bar_w + bar_w / 2
                    lab.y = self.y - 14
        for k, name in enumerate((legend or [])[:len(self._legend)]):
            lab = self._legend[k]
            lab.text = f"■ {name}"
            lab.color = _theme.ink(colors[k % len(colors)])
        self._place_legend()

    def _place_legend(self) -> None:
        """Legenda numa linha por cima do gráfico, encostada à direita (fora
        do caminho da caixa do ponto escolhido)."""
        x = self.x + self.width
        for lab in reversed(self._legend):
            if not lab.text:
                continue
            lab.x, lab.y = x, self.y + self.height + 10
            x -= len(lab.text) * 6.6 + 18

    # ------------------------------------------------------------- seleção

    def hit(self, mx: float, my: float) -> int | None:
        """Índice do ponto mais perto de um clique dentro do gráfico."""
        if not self.points:
            return None
        if not (self.x - 10 <= mx <= self.x + self.width + 10
                and self.y - 20 <= my <= self.y + self.height + 10):
            return None
        return min(range(len(self.points)), key=lambda i: abs(self.points[i][0] - mx))

    def select(self, index: int | None, text: str = "") -> None:
        if index is None or not self.points:
            self.selected = None
            self._hide_selection()
            return
        index = max(0, min(len(self.points) - 1, index))
        self.selected = index
        x, y = self.points[index]
        self._sel_line.x, self._sel_line.y = x - 1, self.y
        self._sel_line.opacity = 120
        self._sel_dot.x, self._sel_dot.y, self._sel_dot.radius = x, y, 6
        self._tip.text = text
        tip_w = max(60, len(text) * 7.2 + 20)
        tx = min(max(self.x, x - tip_w / 2), self.x + self.width - tip_w)
        ty = min(self.y + self.height - 30, y + 14)
        self._tip_bg.x, self._tip_bg.y, self._tip_bg.width = tx, ty, tip_w
        self._tip_bg.opacity = 235 if text else 0
        self._tip.x, self._tip.y = tx + 10, ty + 13

    def _hide_selection(self) -> None:
        self._sel_line.opacity = 0
        self._sel_dot.radius = 0
        self._tip_bg.opacity = 0
        self._tip.text = ""

    def draw(self) -> None:
        self.batch.draw()


class StackedBars:
    """Barras horizontais empilhadas, uma por linha (tempo em zona, perfil de
    potência). Cada parte tem fração, cor e texto; cada linha tem um título
    e uma nota à direita."""

    ROWS = 4
    PARTS = 8

    def __init__(self):
        self.batch = pyglet.graphics.Batch()
        self.rows = []
        for _ in range(self.ROWS):
            self.rows.append({
                "title": make_label("", font_size=12, bold=True, color=TEXT,
                                    anchor_y="bottom", batch=self.batch),
                "note": make_label("", font_size=11, color=DIM, anchor_x="right",
                                   anchor_y="bottom", batch=self.batch),
                "track": pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL2,
                                                 batch=self.batch),
                "parts": [pyglet.shapes.Rectangle(0, 0, 0, 1, color=P().chart_bar,
                                                  batch=self.batch)
                          for _ in range(self.PARTS)],
                "texts": [make_label("", font_size=9, color=(24, 30, 40, 255),
                                     anchor_x="center", anchor_y="center", batch=self.batch)
                          for _ in range(self.PARTS)],
            })
        self.geometry = (0, 0, 0, 0)
        self.visible = False

    def layout(self, x: float, top: float, width: float, row_h: float = 64) -> None:
        self.geometry = (x, top, width, row_h)

    def set_rows(self, rows: list[dict]) -> None:
        """rows: [{"title", "note", "parts": [(fração, cor, texto)]}]"""
        x, top, width, row_h = self.geometry
        self.visible = bool(rows)
        for i, row in enumerate(self.rows):
            data = rows[i] if i < len(rows) else None
            y = top - (i + 1) * row_h + 10
            row["title"].x, row["title"].y = x, y + 26
            row["note"].x, row["note"].y = x + width, y + 26
            row["track"].x, row["track"].y = x, y
            row["track"].width, row["track"].height = width, 22
            row["track"].opacity = 255 if data else 0
            row["title"].text = data["title"] if data else ""
            row["note"].text = data.get("note", "") if data else ""
            cx = x
            parts = data["parts"] if data else []
            for k, (rect, lab) in enumerate(zip(row["parts"], row["texts"])):
                if k < len(parts):
                    frac, color, text = parts[k]
                    w = max(0.0, frac) * width
                    rect.x, rect.y, rect.width, rect.height = cx, y, w, 22
                    rect.color = color[:3]
                    rect.opacity = 235 if w > 0 else 0
                    lab.text = text if w >= max(28, len(text) * 6.5) else ""
                    lab.x, lab.y = cx + w / 2, y + 11
                    cx += w
                else:
                    rect.opacity = 0
                    rect.width = 0
                    lab.text = ""

    def draw(self) -> None:
        if self.visible:
            self.batch.draw()


class BoardPanel:
    """Painel de classificação: título, subtítulo e até seis linhas.

    Serve os menus e o HUD. A linha do atleta («Tu») fica realçada.
    Recebe um `velo.core.boards.Board` e só muda textos — não cria
    etiquetas novas a cada frame.
    """

    ROW = 24

    def __init__(self, x: int, top: int, width: int, max_rows: int = 6,
                 opacity: int = 235):
        self.x, self.top, self.width = x, top, width
        self.max_rows = max_rows
        self.visible = True
        self.batch = pyglet.graphics.Batch()
        self._bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL, batch=self.batch)
        self._bg.opacity = opacity
        self._me_bg = pyglet.shapes.Rectangle(0, 0, 1, self.ROW - 2, color=P().me_bg,
                                              batch=self.batch)
        self._me_bg.opacity = 0
        self.title = make_label("", font_size=14, bold=True, color=ACCENT,
                                anchor_y="top", batch=self.batch)
        self.subtitle = make_label("", font_size=10, color=DIM, anchor_y="top",
                                   batch=self.batch)
        self._rows = []
        for _ in range(max_rows):
            rank = make_label("", font_size=12, bold=True, color=DIM,
                              anchor_x="right", anchor_y="center", batch=self.batch)
            name = make_label("", font_size=11, color=TEXT, anchor_y="center",
                              batch=self.batch)
            value = make_label("", font_size=12, bold=True, color=TEXT,
                               anchor_x="right", anchor_y="center", batch=self.batch)
            self._rows.append((rank, name, value))
        self.empty = make_label("", font_size=11, color=DIM, anchor_y="center",
                                batch=self.batch)
        self.board = None
        self.layout(x, top, width)

    @property
    def height(self) -> int:
        return 58 + self.max_rows * self.ROW

    def layout(self, x: int, top: int, width: int) -> None:
        self.x, self.top, self.width = x, top, width
        self._bg.x, self._bg.y = x, top - self.height
        self._bg.width, self._bg.height = width, self.height
        self.title.x, self.title.y = x + 12, top - 10
        self.subtitle.x, self.subtitle.y = x + 12, top - 32
        self.empty.x, self.empty.y = x + 12, top - 58 - self.ROW // 2
        for i, (rank, name, value) in enumerate(self._rows):
            y = top - 58 - i * self.ROW - self.ROW // 2
            rank.x, rank.y = x + 36, y
            name.x, name.y = x + 44, y
            value.x, value.y = x + width - 12, y
        self.set(self.board)

    def set(self, board) -> None:
        self.board = board
        if board is None:
            self.title.text = self.subtitle.text = self.empty.text = ""
            for rank, name, value in self._rows:
                rank.text = name.text = value.text = ""
            self._me_bg.opacity = 0
            return
        self.title.text = _fit(board.title, self.width - 24, 14)
        self.subtitle.text = _fit(board.subtitle, self.width - 24, 10)
        rows = list(board.rows)[:self.max_rows]
        self.empty.text = board.empty if not rows else ""
        self._me_bg.opacity = 0
        for i, (rank, name, value) in enumerate(self._rows):
            if i < len(rows):
                r = rows[i]
                rank.text = f"{r.rank}." if r.rank else ("•" if not r.me else "")
                name.text = _fit(r.label, self.width - 140, 11)
                value.text = r.value
                color = ACCENT if r.me else TEXT
                name.color = color
                value.color = color
                if r.me:
                    self._me_bg.x = self.x + 4
                    self._me_bg.width = self.width - 8
                    self._me_bg.y = self.top - 58 - i * self.ROW - self.ROW + 1
                    self._me_bg.opacity = 200
            else:
                rank.text = name.text = value.text = ""

    def draw(self) -> None:
        if self.visible and self.board is not None:
            self.batch.draw()


def _fit(text: str, width_px: float, font_size: int) -> str:
    """Corta texto que não cabe, com reticências. Estimativa por carácter."""
    if not text:
        return ""
    max_chars = max(4, int(width_px / (font_size * 0.58)))
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


class BackButton:
    """«← Voltar» no canto de baixo, para voltar atrás com o rato."""

    W, H = 128, 36

    def __init__(self, window):
        from velo.core.i18n import t
        from velo.gfx import icons
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.outline = pyglet.shapes.Rectangle(0, 0, self.W + 2, self.H + 2, color=BORDER,
                                               batch=self.batch)
        self.bg = pyglet.shapes.Rectangle(0, 0, self.W, self.H, color=PANEL, batch=self.batch)
        self.label = make_label(t("common.back"), font_size=13, bold=True, color=TEXT,
                                anchor_y="center", batch=self.batch)
        self.icon = icons.sprite("back", 0, 0, 18, batch=self.batch, opacity=235)
        self.layout()

    def layout(self) -> None:
        x, y = 40, 14
        self.bg.x, self.bg.y = x, y
        self.outline.x, self.outline.y = x - 1, y - 1
        self.label.x, self.label.y = x + 40, y + self.H // 2
        if self.icon is not None:
            self.icon.x, self.icon.y = x + 12, y + (self.H - 18) // 2

    def hit(self, mx: float, my: float) -> bool:
        b = self.bg
        return b.x <= mx <= b.x + b.width and b.y <= my <= b.y + b.height

    def place(self, x: float, y: float, text: str | None = None) -> None:
        if text is not None:
            self.label.text = text
        self.bg.x, self.bg.y = x, y
        self.outline.x, self.outline.y = x - 1, y - 1
        self.label.x, self.label.y = x + 40, y + self.H // 2
        if self.icon is not None:
            self.icon.x, self.icon.y = x + 12, y + (self.H - 18) // 2

    def draw(self) -> None:
        self.batch.draw()


class Tile:
    """Cartão grande com ícone e título (ecrã inicial)."""

    def __init__(self, title: str, icon_name: str, note: str = "", batch=None):
        from velo.gfx import icons
        self.batch = batch
        self.outline = pyglet.shapes.Rectangle(0, 0, 10, 10, color=BORDER, batch=batch)
        self.bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=batch)
        self.border = pyglet.shapes.Rectangle(0, 0, 10, 4, color=ACCENT[:3], batch=batch)
        self.border.opacity = 0
        self.title = make_label(title, font_size=17, bold=True, color=TEXT,
                                anchor_x="center", anchor_y="center", batch=batch)
        self.note = make_label(note, font_size=10, color=DIM, anchor_x="center",
                               anchor_y="center", batch=batch)
        self.icon_name = icon_name
        self.icon = icons.sprite(icon_name, 0, 0, 72, batch=batch, opacity=235)
        self.selected = False

    def layout(self, x: float, y: float, w: float, h: float) -> None:
        self.bg.x, self.bg.y, self.bg.width, self.bg.height = x, y, w, h
        o = self.outline
        o.x, o.y, o.width, o.height = x - 1, y - 1, w + 2, h + 2
        self.border.x, self.border.y, self.border.width = x, y, w
        icon = min(72, h * 0.5, w * 0.6)
        if self.icon is not None:
            self.icon.scale = icon / 64
            self.icon.x, self.icon.y = x + (w - icon) / 2, y + h - icon - 18
        self.title.x, self.title.y = x + w / 2, y + 40
        # o título tem de caber no cartão (≈ 0,62 da altura da letra por carácter)
        size = 17
        while size > 11 and len(self.title.text) * size * 0.62 > w - 16:
            size -= 1
        self.title.font_size = size
        self.note.x, self.note.y = x + w / 2, y + 18

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.bg.color = SELECT if on else PANEL
        self.border.opacity = 255 if on else 0
        self.outline.color = ACCENT[:3] if on else BORDER
        self.title.color = ACCENT if on else TEXT
        from velo.gfx import icons
        icons.set_tint(self.icon, ACCENT if on else None)

    def hit(self, mx: float, my: float) -> bool:
        b = self.bg
        return b.x <= mx <= b.x + b.width and b.y <= my <= b.y + b.height


class Heatmap:
    """Dias treinados das últimas semanas: um quadrado por dia, mais forte
    quanto mais tempo se pedalou."""

    THRESHOLDS = (0, 1, 30, 60, 90)

    @property
    def LEVELS(self):
        return tuple(zip(self.THRESHOLDS, _theme.P.heat))

    def __init__(self, weeks: int = 16, batch=None):
        self.weeks = weeks
        self.cells = [[pyglet.shapes.Rectangle(0, 0, 1, 1, color=_theme.P.heat[0], batch=batch)
                       for _ in range(7)] for _ in range(weeks)]

    def layout(self, x: float, y: float, cell: float, gap: float = 3) -> None:
        for w, col in enumerate(self.cells):
            for d, r in enumerate(col):
                r.x = x + w * (cell + gap)
                r.y = y + (6 - d) * (cell + gap)          # segunda em cima
                r.width = r.height = cell

    def set(self, grid: list[list[float]]) -> None:
        for col, values in zip(self.cells, grid):
            for r, minutes in zip(col, values):
                if minutes < 0:                           # dia que ainda não chegou
                    r.opacity = 0
                    continue
                r.opacity = 255
                color = self.LEVELS[0][1]
                for threshold, c in self.LEVELS:
                    if minutes >= threshold and (threshold > 0 or minutes == 0):
                        color = c
                r.color = color


# ===================================================================== tabs


class TabBar:
    """Uma fila de separadores. Tab / Shift+Tab (ou o rato) mudam."""

    H = 34

    def __init__(self, labels: list[str], x: float = 48, top: float = 0, width: float = 600,
                 small: bool = False):
        self.batch = pyglet.graphics.Batch()
        self.labels_text = list(labels)
        self.index = 0
        self.small = small
        self.x, self.top, self.width = x, top, width
        self.base = pyglet.shapes.Rectangle(0, 0, 1, 2, color=BORDER, batch=self.batch)
        self.bgs: list = []
        self.marks: list = []
        self.labs: list = []
        self._build()

    def _build(self) -> None:
        for coll in (self.bgs, self.marks, self.labs):
            for o in coll:
                try:
                    o.delete()
                except Exception:
                    pass
            coll.clear()
        for text in self.labels_text:
            self.bgs.append(pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=self.batch))
            m = pyglet.shapes.Rectangle(0, 0, 10, 3, color=ACCENT[:3], batch=self.batch)
            m.opacity = 0
            self.marks.append(m)
            self.labs.append(make_label(text, font_size=11 if self.small else 13, bold=True,
                                        color=DIM, anchor_x="center", anchor_y="center",
                                        batch=self.batch))
        self.layout(self.x, self.top, self.width)

    def set_labels(self, labels: list[str]) -> None:
        if list(labels) != self.labels_text:
            self.labels_text = list(labels)
            self.index = min(self.index, max(0, len(labels) - 1))
            self._build()

    def layout(self, x: float, top: float, width: float) -> None:
        self.x, self.top, self.width = x, top, width
        n = max(1, len(self.labels_text))
        h = self.H - (6 if self.small else 0)
        # largura proporcional ao texto, sem passar do espaço disponível
        size = 11 if self.small else 13
        want = [len(t) * size * 0.62 + 28 for t in self.labels_text]
        scale = min(1.0, (width - 4 * (n - 1)) / max(1.0, sum(want)))
        cx = x
        for i, (bg, mark, lab) in enumerate(zip(self.bgs, self.marks, self.labs)):
            w = want[i] * scale
            bg.x, bg.y, bg.width, bg.height = cx, top - h, w, h
            mark.x, mark.y, mark.width = cx, top - h, w
            lab.x, lab.y = cx + w / 2, top - h / 2
            lab.font_size = size if scale > 0.8 else max(9, int(size * scale + 1))
            cx += w + 4
        self.base.x, self.base.y, self.base.width = x, top - h - 2, width
        self.select(self.index)

    @property
    def height(self) -> int:
        return self.H - (6 if self.small else 0)

    def select(self, i: int) -> None:
        if not self.labels_text:
            return
        self.index = i % len(self.labels_text)
        for k, (bg, mark, lab) in enumerate(zip(self.bgs, self.marks, self.labs)):
            on = k == self.index
            bg.color = PANEL if on else PANEL2
            mark.opacity = 255 if on else 0
            lab.color = ACCENT if on else DIM

    def hit(self, mx: float, my: float) -> int | None:
        for i, bg in enumerate(self.bgs):
            if bg.x <= mx <= bg.x + bg.width and bg.y <= my <= bg.y + bg.height:
                return i
        return None

    @property
    def current(self) -> str:
        return self.labels_text[self.index] if self.labels_text else ""

    def draw(self) -> None:
        self.batch.draw()


# =================================================================== topo


class TopBar:
    """Faixa do topo, sempre à vista: os aparelhos e o estado de cada um, e os
    botões Dispositivos, Definições e Ligar/Desligar (sair)."""

    H = 26
    CHIPS = 6

    def __init__(self, window):
        from velo.gfx import icons
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.bg = pyglet.shapes.Rectangle(0, 0, 10, self.H, color=HEADER, batch=self.batch)
        self.brand = make_label("Perennia", font_size=11, bold=True, color=HEADER_TEXT,
                                anchor_y="center", batch=self.batch)
        self.brand_dot = pyglet.shapes.Circle(0, 0, 4, color=_theme.mix(
            _theme.P.good, (255, 255, 255), 0.25), batch=self.batch)
        self.chips = []
        for _ in range(self.CHIPS):
            dot = pyglet.shapes.Rectangle(0, 0, 8, 8, color=GOOD[:3], batch=self.batch)
            lab = make_label("", font_size=10, color=HEADER_TEXT, anchor_y="center",
                             batch=self.batch)
            self.chips.append((dot, lab))
        self.more = make_label("", font_size=10, color=HEADER_DIM, anchor_y="center",
                               batch=self.batch)
        self.buttons: dict[str, tuple] = {}
        for key_, icon in (("devices", "devices"), ("settings", "gear"),
                           ("quit", "power_button")):
            r = pyglet.shapes.Rectangle(0, 0, 10, self.H - 4,
                                        color=_theme.mix(HEADER, (255, 255, 255), 0.13),
                                        batch=self.batch)
            lab = make_label("", font_size=10, bold=True, color=HEADER_TEXT, anchor_y="center",
                             batch=self.batch)
            ic = icons.sprite(icon, 0, 0, 16, batch=self.batch, opacity=235,
                              tint=HEADER_TEXT)
            self.buttons[key_] = (r, lab, ic)
        self.enabled = {"devices": True, "settings": True, "quit": True}
        self.devices: list[tuple[str, str]] = []
        self._chip_rects: list[tuple[float, float, float]] = []
        # data e hora, ao lado do botão Dispositivos
        self.clock = make_label("", font_size=10, bold=True, color=HEADER_TEXT,
                                anchor_x="right", anchor_y="center", batch=self.batch)
        self._clock_key = None
        self.now = None                       # para os testes: uma hora fixa
        self.update_clock()
        self.layout()

    def clock_text(self) -> str:
        import datetime as _dt
        from velo.core.i18n import tr
        now = self.now or _dt.datetime.now()
        days = tr("seg ter qua qui sex sáb dom", "Mon Tue Wed Thu Fri Sat Sun").split()
        return f"{days[now.weekday()]} {now.day:02d}/{now.month:02d}/{now.year} · " \
               f"{now.hour:02d}:{now.minute:02d}"

    def update_clock(self) -> bool:
        """Muda o texto quando muda o minuto (devolve True se mudou)."""
        text = self.clock_text()
        if text == self._clock_key:
            return False
        self._clock_key = text
        self.clock.text = text
        return True

    def set_texts(self, devices: str, settings: str, quit_: str) -> None:
        for k, txt in (("devices", devices), ("settings", settings), ("quit", quit_)):
            self.buttons[k][1].text = txt
        self._clock_key = None
        self.update_clock()
        self.layout()

    def layout(self) -> None:
        w, h = self.window.width, self.window.height
        self.bg.x, self.bg.y, self.bg.width = 0, h - self.H, w
        x = w - 12
        for k in ("quit", "settings", "devices"):
            r, lab, ic = self.buttons[k]
            bw = max(60, len(lab.text) * 6.6 + 34)
            x -= bw
            r.x, r.y, r.width = x, h - self.H + 2, bw
            if ic is not None:
                ic.x, ic.y = x + 6, h - self.H + 5
            lab.x, lab.y = x + 26, h - self.H / 2
            x -= 6
        self.clock.x, self.clock.y = x - 8, h - self.H / 2
        x -= 8 + len(self.clock.text) * 6.6 + 10
        self._buttons_left = x
        self._place_chips()

    def set_devices(self, devices: list[tuple[str, str]]) -> None:
        """[(nome, estado)] com estado em ok | lost | off."""
        if devices != self.devices:
            self.devices = list(devices)
            self._place_chips()

    def _place_chips(self) -> None:
        h = self.window.height
        self.brand_dot.x, self.brand_dot.y = 16, h - self.H / 2
        self.brand.x, self.brand.y = 26, h - self.H / 2
        x = 26 + len(self.brand.text) * 7.6 + 18
        limit = getattr(self, "_buttons_left", self.window.width) - 10
        self._chip_rects = []
        shown = 0
        for (dot, lab), dev in zip(self.chips, self.devices + [None] * self.CHIPS):
            if dev is None:
                lab.text = ""
                dot.opacity = 0
                continue
            name, state = dev
            text = name if len(name) <= 22 else name[:21] + "…"
            wdt = 18 + len(text) * 6.2 + 14
            if x + wdt > limit:
                lab.text = ""
                dot.opacity = 0
                continue
            dot.opacity = 255
            dot.color = {"ok": _theme.mix(GOOD[:3], (255, 255, 255), 0.2),
                         "lost": _theme.mix(BAD[:3], (255, 255, 255), 0.2)}.get(
                state, HEADER_DIM[:3])
            dot.x, dot.y = x, h - self.H / 2 - 4
            lab.text = text
            lab.color = HEADER_TEXT if state == "ok" else (
                _theme.rgba(_theme.mix(BAD[:3], (255, 255, 255), 0.45)) if state == "lost"
                else HEADER_DIM)
            lab.x, lab.y = x + 14, h - self.H / 2
            self._chip_rects.append((x, x + wdt, shown))
            x += wdt
            shown += 1
        hidden = len(self.devices) - shown
        self.more.text = f"+{hidden}" if hidden > 0 else ""
        self.more.x, self.more.y = x, h - self.H / 2
        if not self.devices:
            self.more.text = ""

    def set_enabled(self, key_: str, on: bool) -> None:
        self.enabled[key_] = on
        r, lab, ic = self.buttons[key_]
        lab.color = HEADER_TEXT if on else HEADER_DIM
        r.opacity = 255 if on else 110
        if ic is not None:
            ic.opacity = 235 if on else 70

    def hit(self, mx: float, my: float) -> str | None:
        if my < self.window.height - self.H:
            return None
        for k, (r, _lab, _ic) in self.buttons.items():
            if r.x <= mx <= r.x + r.width:
                return k
        for x0, x1, _i in self._chip_rects:
            if x0 <= mx <= x1:
                return "devices"
        return "bar"

    def draw(self) -> None:
        if self.update_clock():
            self.layout()
        self.batch.draw()


class Popup:
    """Fundo escurecido e um painel ao centro (diálogos e o gestor de aparelhos)."""

    def __init__(self, window, width: float = 720, height: float = 460):
        self.window = window
        self.batch = pyglet.graphics.Batch()
        self.shade = pyglet.shapes.Rectangle(0, 0, 10, 10, color=P().shade, batch=self.batch)
        self.shade.opacity = P().shade_alpha
        self.outline = pyglet.shapes.Rectangle(0, 0, 10, 10, color=BORDER, batch=self.batch)
        self.panel = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=self.batch)
        self.edge = pyglet.shapes.Rectangle(0, 0, 10, 4, color=HEADER, batch=self.batch)
        self.want = (width, height)
        self.layout()

    def layout(self) -> None:
        w, h = self.window.width, self.window.height
        pw = min(self.want[0], w - 60)
        ph = min(self.want[1], h - 80)
        self.shade.x, self.shade.y, self.shade.width, self.shade.height = 0, 0, w, h
        self.x, self.y, self.w, self.h = (w - pw) / 2, (h - ph) / 2 - 6, pw, ph
        self.panel.x, self.panel.y, self.panel.width, self.panel.height = (
            self.x, self.y, self.w, self.h)
        o = self.outline
        o.x, o.y, o.width, o.height = self.x - 1, self.y - 1, self.w + 2, self.h + 2
        self.edge.x, self.edge.y, self.edge.width = self.x, self.y + self.h - 4, self.w

    def inside(self, mx: float, my: float) -> bool:
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h

    def draw(self) -> None:
        self.batch.draw()


class SessionClock:
    """O tempo total da sessão, ao centro do topo e destacado; por baixo, o
    tempo da série / volta / passo em curso."""

    def __init__(self, window, batch=None):
        self.window = window
        self.batch = batch or pyglet.graphics.Batch()
        self._own = batch is None
        self.bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=HEADER, batch=self.batch)
        self.edge = pyglet.shapes.Rectangle(0, 0, 10, 3, color=ACCENT[:3], batch=self.batch)
        self.cap = make_label("", font_size=9, bold=True, color=HEADER_DIM, anchor_x="center",
                              anchor_y="top", batch=self.batch)
        self.value = make_label("0:00", font_size=28, bold=True, color=HEADER_TEXT,
                                anchor_x="center", anchor_y="top", batch=self.batch)
        self.sub = make_label("", font_size=11, color=HEADER_TEXT, anchor_x="center",
                              anchor_y="top", batch=self.batch)
        self.layout()

    def layout(self) -> None:
        w, h = self.window.width, self.window.height
        cw, ch = 230, 84
        x, top = w / 2 - cw / 2, h - 30
        self.bg.x, self.bg.y, self.bg.width, self.bg.height = x, top - ch, cw, ch
        self.edge.x, self.edge.y, self.edge.width = x, top - ch, cw
        self.cap.x, self.cap.y = w / 2, top - 5
        self.value.x, self.value.y = w / 2, top - 18
        self.sub.x, self.sub.y = w / 2, top - 60

    def set(self, total_s: float, sub: str = "", caption: str | None = None) -> None:
        from velo.core.i18n import tr
        from velo.core.units import hms
        self.cap.text = caption if caption is not None else tr("TEMPO TOTAL", "TOTAL TIME")
        self.value.text = hms(total_s)
        self.sub.text = sub

    def draw(self) -> None:
        if self._own:
            self.batch.draw()


class GridView:
    """Cartões em grelha, a ocupar a área toda (sem deslocar): para escolher
    muitas coisas de uma vez, como as métricas disponíveis. Cada cartão tem
    um rótulo, uma nota pequena e um estado (ligado / desligado)."""

    GAP = 8

    def __init__(self):
        self.batch = pyglet.graphics.Batch()
        self.cells: list = []
        self.rects: list[tuple[float, float, float, float]] = []
        self.cols = 1
        self.index = 0
        self.geometry = (48, 600, 800, 80)

    def _cell(self):
        bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=self.batch)
        bar = pyglet.shapes.Rectangle(0, 0, 4, 10, color=GOOD[:3], batch=self.batch)
        lab = make_label("", font_size=12, bold=True, color=TEXT, anchor_y="center",
                         batch=self.batch)
        note = make_label("", font_size=9, color=DIM, anchor_y="center", batch=self.batch)
        mark = make_label("", font_size=12, bold=True, color=GOOD, anchor_x="right",
                          anchor_y="center", batch=self.batch)
        return bg, bar, lab, note, mark

    def layout(self, x: float, top: float, width: float, bottom: float) -> None:
        self.geometry = (x, top, width, bottom)

    def set(self, entries: list[tuple[str, str, bool, bool]], index: int = 0) -> None:
        """entries: [(rótulo, nota, ligado, ativo)]."""
        x, top, width, bottom = self.geometry
        n = len(entries)
        while len(self.cells) < n:
            self.cells.append(self._cell())
        h_all = max(40.0, top - bottom)
        best = None
        for cols in range(1, 9):
            rows = -(-n // cols) if n else 1
            tw = (width - self.GAP * (cols - 1)) / cols
            th = (h_all - self.GAP * (rows - 1)) / rows
            if tw < 150:
                break
            score = abs(tw / max(th, 1) - 4.5) + (100 if th < 30 else 0)
            if best is None or score < best[0]:
                best = (score, cols, tw, min(th, 64))
        _s, cols, tw, th = best or (0, 1, width, 40)
        self.cols = cols
        self.index = max(0, min(index, n - 1)) if n else 0
        self.rects = []
        for k, (bg, bar, lab, note, mark) in enumerate(self.cells):
            if k >= n:
                bg.opacity = bar.opacity = 0
                lab.text = note.text = mark.text = ""
                continue
            text, sub, on, enabled = entries[k]
            r, c = divmod(k, cols)
            cx = x + c * (tw + self.GAP)
            cy = top - (r + 1) * th - r * self.GAP
            self.rects.append((cx, cy, tw, th))
            sel = k == self.index
            bg.x, bg.y, bg.width, bg.height = cx, cy, tw, th
            bg.color = SELECT if sel else (PANEL if on else PANEL2)
            bg.opacity = 255
            bar.x, bar.y, bar.height = cx, cy, th
            bar.color = ACCENT[:3] if sel else GOOD[:3]
            bar.opacity = 255 if (on or sel) else 0
            size = 12 if th >= 40 else 11
            lab.font_size = size
            lab.text = _fit(text, tw - 46, size)
            lab.color = ACCENT if sel else (TEXT if enabled and on else DIM)
            lab.x, lab.y = cx + 14, cy + th / 2 + (7 if sub and th >= 40 else 0)
            note.text = _fit(sub, tw - 46, 9) if th >= 40 else ""
            note.x, note.y = cx + 14, cy + th / 2 - 9
            mark.text = "✓" if on else ""
            mark.x, mark.y = cx + tw - 10, cy + th / 2

    def hit(self, mx: float, my: float) -> int | None:
        for k, (cx, cy, tw, th) in enumerate(self.rects):
            if cx <= mx <= cx + tw and cy <= my <= cy + th:
                return k
        return None

    def draw(self) -> None:
        self.batch.draw()


class TextColumns:
    """Texto em colunas (grupos com título e linhas «tecla — o que faz»), a
    ocupar a área toda: os atalhos de teclado."""

    def __init__(self):
        self.batch = pyglet.graphics.Batch()
        self.labels: list = []
        self.geometry = (48, 600, 800, 80)

    def layout(self, x: float, top: float, width: float, bottom: float) -> None:
        self.geometry = (x, top, width, bottom)

    def set(self, groups: list[tuple[str, list[tuple[str, str]]]]) -> None:
        x, top, width, bottom = self.geometry
        lines = sum(len(rows) + 2 for _g, rows in groups)
        height = max(60.0, top - bottom)
        cols, row_h = 1, 22.0
        for cols in range(1, 6):
            # folga de 10 %: um grupo não se parte no fundo de uma coluna
            row_h = min(22.0, height / max(1, -(-int(lines * 1.1) // cols)))
            if row_h >= 17 or (width - 24 * cols) / (cols + 1) < 220:
                break
        per = max(1, int(height // row_h))
        col_w = (width - 24 * (cols - 1)) / cols
        need = sum(len(rows) * 2 + 1 for _g, rows in groups)
        while len(self.labels) < need:
            self.labels.append(make_label("", font_size=10, color=TEXT, anchor_y="center",
                                          batch=self.batch))
        k = 0
        slot = 0

        def place(text, xx, slot_, bold=False, color=TEXT, anchor="left", size=10):
            nonlocal k
            lab = self.labels[k]
            k += 1
            c, r = divmod(slot_, per)
            lab.text = text
            lab.font_size = size
            lab.color = color
            try:
                lab.bold = bold
                lab.anchor_x = anchor
            except Exception:
                pass
            lab.x = x + c * (col_w + 24) + xx
            lab.y = top - r * row_h - row_h / 2
            return lab

        size = 10 if row_h >= 18 else 9
        key_w = min(150.0, col_w * 0.38)
        for title, rows in groups:
            # um grupo não começa no fundo de uma coluna
            if slot % per and (slot % per) + 2 > per:
                slot += per - slot % per
            place(title, 0, slot, True, ACCENT, size=size + 1)
            slot += 1
            for key_, what in rows:
                place(key_, 0, slot, True, TEXT, size=size)
                place(_fit(what, col_w - key_w - 8, size), key_w, slot, False, DIM, size=size)
                slot += 1
            slot += 1
        for lab in self.labels[k:]:
            lab.text = ""

    def draw(self) -> None:
        self.batch.draw()
