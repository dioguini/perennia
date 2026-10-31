"""HUD da sessão.

Disposição, de cima para baixo:

* cabeçalho: relógio e distância · resistência (− / +) · Pausa · Terminar;
* 6 caixas numeradas de métricas, com ícones (escolhidas nas Definições);
* zona do meio — à esquerda: barras das zonas de potência e de FC, e o
  plano do treino (passo atual e os seguintes); ao centro: subida e fuga;
  à direita: classificação e, por baixo, as voltas (sempre visíveis);
* em baixo: tempo em cada zona, o perfil dos próximos 2 km e o perfil da
  rota completa, de lado a lado, com as linhas de potência e de FC por cima.

Os objetos de texto e as formas são criados uma vez e só se lhes muda o
conteúdo: criar etiquetas a cada frame é o erro mais fácil e mais caro.
Tudo o que é caro de recalcular (perfil, traço, classificação) atualiza-se
algumas vezes por segundo, não a cada frame.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pyglet
import pyglet.shapes

TOPBAR_H = 26          # a faixa de aparelhos da aplicação (velo.ui.widgets.TopBar)
import pyglet.text
from pyglet.gl import GL_DEPTH_TEST, glDisable, glEnable
from pyglet.math import Mat4

from velo.core import boxes as boxes_mod
from velo.core import metrics as metrics_mod
from velo.core import zones as zones_mod
from velo.core.chase import WARN_GAPS_M
from velo.core.i18n import t, tr
from velo.core.units import balance_text, format_metric, hms, km
from velo.core.units import delta as fmt_delta
from velo.gfx import icons
from velo.gfx.compat import label as make_label
from velo.gfx.compat import line as make_line

from velo.gfx import theme as _theme


def _palette() -> None:
    """As cores do HUD saem do tema: caixas claras e translúcidas por cima da
    estrada, texto escuro (ou o contrário, no tema de pouca luz)."""
    global PANEL, ACCENT, TEXT, DIM, GOOD, BAD, POWER_LINE, HR_LINE, HUD_BG, HUD_A
    global TRACK, BTN, ON_DARK
    p = _theme.P
    PANEL = p.hud_panel + (p.hud_alpha,)
    ACCENT, TEXT, DIM = _theme.rgba(p.accent), _theme.rgba(p.text), _theme.rgba(p.dim)
    GOOD, BAD = _theme.rgba(p.good), _theme.rgba(p.bad)
    POWER_LINE, HR_LINE = p.power_line, p.hr_line
    HUD_BG, HUD_A = p.hud_panel, p.hud_alpha
    TRACK, BTN = p.panel2, p.panel2
    ON_DARK = (255, 255, 255, 255)


def _theme_changed(_old, _new) -> None:
    _palette()


_palette()

from velo.core.intensity import ZONE_COLORS as _ZC

ZONE_COLORS = [tuple(c) for c in _ZC]
HR_ZONE_COLORS = [tuple(c) for c in _ZC[:5]]


def zone_color(n: int, kind: str = "power") -> tuple[int, int, int]:
    table = ZONE_COLORS if kind == "power" else HR_ZONE_COLORS
    return table[max(0, min(len(table) - 1, int(n) - 1))]


def _grade_color(g: float) -> tuple[int, int, int]:
    """Cor do declive, igual nos dois perfis."""
    if g > 8:
        return (226, 110, 96)
    if g > 4:
        return (238, 170, 86)
    if g > 1:
        return (236, 212, 110)
    if g < -3:
        return (120, 190, 220)
    return (130, 170, 140)


def _rect(batch, color=None, opacity=0):
    color = color if color is not None else HUD_BG
    r = pyglet.shapes.Rectangle(0, 0, 1, 1, color=color[:3], batch=batch)
    r.opacity = opacity
    return r


def _hit(r, x, y) -> bool:
    return r.x <= x <= r.x + r.width and r.y <= y <= r.y + r.height


@dataclass
class Toast:
    text: str
    born: float
    duration: float = 3.5
    emphasis: bool = False


@dataclass
class Sign:
    title: str
    subtitle: str
    born: float
    duration: float = 4.0


class Hud:
    # Medidas fixas (px)
    PAD = 16
    HEADER_H = 46
    BOX_GAP = 8
    BOX_TITLE_H = 24
    BOX_ROW_STACKED = 38
    BOX_ROW_INLINE = 24
    STRIP_H = 80
    PROFILE_H = 84
    SIDE_W = 300
    GAUGE_H = 66
    PLAN_ROW = 24
    GOAL_H = 16            # o objetivo do bloco em curso, por baixo do título do plano
    LAP_CELL_H = 34
    LAP_PREV_ROW = 18
    PROFILE_BAR_PX = 2
    PROFILE_EDGE_PX = 6
    STRIP_BAR_PX = 2
    TRACE_PX = 3

    def __init__(self, window, db, athlete):
        self.window = window
        self.db = db
        self.athlete = athlete
        self.units = db.get("units", "metric")
        self.boxes = boxes_mod.load(db, metrics_mod.REGISTRY)
        self.lookahead = int(db.get("workout_lookahead", 2))

        self.batch = pyglet.graphics.Batch()
        self.top_batch = pyglet.graphics.Batch()      # o diálogo de confirmação, por cima
        self.toasts: list[Toast] = []
        self.sign: Sign | None = None
        self.climb: dict | None = None
        self.climb_started_at: float | None = None
        self.workout_info: dict | None = None
        self.paused = False
        self.status = "waiting"
        self.confirm_visible = False
        self.has_workout = False
        self.brief = None                 # velo.core.objectives.Brief do treino, se houver
        self.lap_flash_at: float | None = None
        self._board_at = 0.0
        self._last_rank: int | None = None
        self._board_ctx = ""
        self._slow_at = 0.0
        self._profile_at = 0.0
        self._trace_at = 0.0
        self._box_widgets: list[dict] = []
        self._build_static()

    # ============================================================ construção

    def _build_static(self) -> None:
        b = self.batch
        w, h = self.window.width, self.window.height

        # ---- cabeçalho
        self._clock = make_label("0:00", font_size=30, bold=True, color=ACCENT,
                                 anchor_x="center", anchor_y="top", batch=b)
        self._clock_cap = make_label("", font_size=10, color=DIM, anchor_x="center",
                                     anchor_y="top", batch=b)
        self._dist = make_label("", font_size=14, color=DIM, anchor_y="top", batch=b)
        self._loops_label = make_label("", font_size=12, color=ACCENT, anchor_y="top",
                                       batch=b)
        self._stop_bg = _rect(b, _theme.P.danger, 235)
        self._stop_label = make_label(t("ride.stop"), font_size=13, bold=True, color=ON_DARK,
                                      anchor_x="center", anchor_y="center", batch=b)
        self._pause_bg = _rect(b, _theme.P.header, 235)
        self._pause_label = make_label(t("ride.pause_btn"), font_size=13, bold=True,
                                       color=ON_DARK, anchor_x="center", anchor_y="center",
                                       batch=b)
        self._res_minus = _rect(b, _theme.P.header, 235)
        self._res_plus = _rect(b, _theme.P.header, 235)
        self._res_minus_label = make_label("−", font_size=18, bold=True, color=ON_DARK,
                                           anchor_x="center", anchor_y="center", batch=b)
        self._res_plus_label = make_label("+", font_size=18, bold=True, color=ON_DARK,
                                          anchor_x="center", anchor_y="center", batch=b)
        self._res_label = make_label("", font_size=11, color=TEXT, anchor_x="center",
                                     anchor_y="center", batch=b)

        # ---- as 6 caixas
        for i in range(boxes_mod.N_BOXES):
            bg = _rect(b, PANEL[:3], PANEL[3])
            title = make_label(boxes_mod.title(self.boxes, i), font_size=10, bold=True,
                               color=ACCENT, anchor_y="top", batch=b)
            rows = []
            for _ in range(boxes_mod.MAX_PER_BOX):
                rows.append((make_label("", font_size=9, color=DIM, anchor_y="top", batch=b),
                             make_label("", font_size=17, bold=True, color=TEXT,
                                        anchor_y="top", batch=b)))
            self._box_widgets.append({"bg": bg, "title": title, "rows": rows,
                                      "icons": [None] * boxes_mod.MAX_PER_BOX})

        # ---- barras das zonas (potência e FC), com o intervalo
        self._gauges: dict[str, dict] = {}
        for kind, n in (("power", 7), ("hr", 5)):
            self._gauges[kind] = {
                "bg": _rect(b, HUD_BG, 0),
                "title": make_label("", font_size=12, bold=True, color=TEXT,
                                    anchor_y="top", batch=b),
                "value": make_label("", font_size=12, bold=True, color=TEXT,
                                    anchor_x="right", anchor_y="top", batch=b),
                "range": make_label("", font_size=10, color=DIM, anchor_y="top", batch=b),
                "segs": [_rect(b, zone_color(i + 1, kind), 0) for i in range(n)],
                "fill": _rect(b, TEXT[:3], 0),
                "marker": _rect(b, TEXT[:3], 0),
                "icon": None,
            }

        # ---- plano do treino
        self._plan_bg = _rect(b, HUD_BG, 0)
        self._plan_goal = make_label("", font_size=9, color=TEXT, anchor_y="top", batch=b,
                                     multiline=True, width=self.SIDE_W - 20)
        self._plan_title = make_label("", font_size=11, bold=True, color=ACCENT,
                                      anchor_y="top", batch=b)
        self._plan_rows = [(make_label("", font_size=12, bold=True, color=TEXT,
                                       anchor_y="top", batch=b),
                            make_label("", font_size=12, color=TEXT, anchor_x="right",
                                       anchor_y="top", batch=b))
                           for _ in range(5)]
        self._plan_track = _rect(b, TRACK, 0)
        self._plan_bar = _rect(b, GOOD[:3], 0)

        # ---- subida em curso
        self._climb_bg = _rect(b, HUD_BG, 0)
        self._climb_title = make_label("", font_size=15, bold=True, color=ACCENT,
                                       anchor_x="center", anchor_y="top", batch=b)
        self._climb_detail = make_label("", font_size=12, color=TEXT, anchor_x="center",
                                        anchor_y="top", batch=b)

        # ---- fuga
        self._chase_bg = _rect(b, HUD_BG, 0)
        self._chase_title = make_label("", font_size=17, bold=True, color=TEXT,
                                       anchor_x="center", anchor_y="top", batch=b)
        self._chase_detail = make_label("", font_size=12, color=DIM, anchor_x="center",
                                        anchor_y="top", batch=b)
        self._chase_track = _rect(b, TRACK, 0)
        self._chase_bar = _rect(b, GOOD[:3], 0)

        # ---- fantasmas
        self._ghost_labels = [make_label("", font_size=14, bold=True, anchor_x="right",
                                         color=TEXT, batch=b) for _ in range(4)]

        # ---- voltas: sempre visíveis, à direita, por baixo da classificação
        self._laps_bg = _rect(b, HUD_BG, HUD_A)
        self._laps_flash = _rect(b, ACCENT[:3], 0)
        self._lap_title = make_label("", font_size=13, bold=True, color=ACCENT,
                                     anchor_y="top", batch=b)
        self._lap_rows = [(make_label("", font_size=9, color=DIM, anchor_y="top", batch=b),
                           make_label("", font_size=13, bold=True, color=TEXT,
                                      anchor_y="top", batch=b)) for _ in range(6)]
        self._lap_prev = [make_label("", font_size=10, color=DIM, anchor_y="top", batch=b)
                          for _ in range(4)]

        # ---- tempo em cada zona (barras empilhadas que vão enchendo)
        self._tiz: dict[str, dict] = {}
        for kind, n in (("power", 7), ("hr", 5)):
            self._tiz[kind] = {
                "title": make_label("", font_size=9, color=DIM, anchor_y="bottom", batch=b),
                "track": _rect(b, TRACK, 0),
                "segs": [_rect(b, zone_color(i + 1, kind), 0) for i in range(n)],
                "pcts": [make_label("", font_size=8, color=(16, 18, 24, 255),
                                    anchor_x="center", anchor_y="center", batch=b)
                         for _ in range(n)],
                "bar_y": 0,
            }

        # ---- perfil dos próximos 2 km
        self._profile_bg = _rect(b, HUD_BG, HUD_A)
        self._profile_bars: list = []
        self._profile_edge: list = []
        self._profile_marker = _rect(b, ACCENT[:3], 255)
        self._profile_label = make_label("", font_size=10, color=DIM, anchor_y="bottom",
                                         batch=b)

        # ---- perfil da rota completa, com as linhas de potência e FC
        self._strip_bg = _rect(b, HUD_BG, HUD_A)
        self._strip_bars: list = []
        self._strip_key: tuple | None = None
        self._strip_done = _rect(b, TEXT[:3], 0)
        self._strip_window = _rect(b, ACCENT[:3], 0)
        self._trace_power: list = []
        self._trace_hr: list = []
        self._strip_marker = _rect(b, ACCENT[:3], 0)
        self._strip_label = make_label("", font_size=10, color=DIM, anchor_y="top", batch=b)
        self._strip_legend = make_label("", font_size=9, color=DIM, anchor_x="right",
                                        anchor_y="top", batch=b)

        # ---- placas e avisos
        self._sign_bg = _rect(b, HUD_BG, 0)
        self._sign_title = make_label("", font_size=30, bold=True, color=ACCENT,
                                      anchor_x="center", anchor_y="center", batch=b)
        self._sign_sub = make_label("", font_size=16, color=TEXT, anchor_x="center",
                                    anchor_y="center", batch=b)
        self._toast_labels = [make_label("", font_size=14, color=TEXT, anchor_x="center",
                                         batch=b) for _ in range(3)]
        self._status_bg = _rect(b, HUD_BG, 0)
        self._paused_label = make_label("", font_size=22, bold=True, color=ACCENT,
                                        anchor_x="center", anchor_y="center", batch=b)

        # ---- diálogo «tem a certeza?»
        tb = self.top_batch
        self._confirm_shade = _rect(tb, _theme.P.shade, 0)
        self._confirm_box = _rect(tb, _theme.P.panel, 0)
        self._confirm_title = make_label("", font_size=22, bold=True, color=TEXT,
                                         anchor_x="center", anchor_y="center", batch=tb)
        self._confirm_sub = make_label("", font_size=13, color=DIM, anchor_x="center",
                                       anchor_y="center", batch=tb)
        self._confirm_yes = _rect(tb, _theme.P.danger, 0)
        self._confirm_no = _rect(tb, _theme.P.panel2, 0)
        self._confirm_discard = _rect(tb, _theme.P.danger_soft, 0)
        self._confirm_discard_label = make_label("", font_size=12, bold=True, color=BAD,
                                                 anchor_x="center", anchor_y="center",
                                                 batch=tb)
        self._confirm_yes_label = make_label("", font_size=14, bold=True, color=ON_DARK,
                                             anchor_x="center", anchor_y="center", batch=tb)
        self._confirm_no_label = make_label("", font_size=14, bold=True, color=TEXT,
                                            anchor_x="center", anchor_y="center", batch=tb)

        # ---- classificação ao vivo
        from velo.ui.widgets import BoardPanel     # import tardio: widgets usa compat
        self._BoardPanel = BoardPanel
        self.board_panel = BoardPanel(0, 0, self.SIDE_W, max_rows=6, opacity=170)
        self.layout(w, h)

    # ================================================================ layout

    def _box_rows(self) -> int:
        return max(1, max(len(bx["metrics"]) for bx in self.boxes))

    def layout(self, w: int, h: int) -> None:
        """Reposiciona tudo. No arranque, ao mudar o tamanho e quando aparece
        um treino (o plano ocupa espaço na coluna da esquerda)."""
        pad = self.PAD
        self._w, self._h = w, h
        top = h - pad - TOPBAR_H          # a faixa dos aparelhos fica por cima
        # Ecrãs baixos (menos de 720 px): caixas em linhas compactas e perfis
        # mais baixos, para a zona do meio caber.
        compact = h < 720
        strip_h = 56 if compact else type(self).STRIP_H
        profile_h = 64 if compact else type(self).PROFILE_H
        # Colunas laterais: 300 px, ou menos (até 240) se o ecrã for estreito.
        side = int(max(240, min(type(self).SIDE_W, (w - 2 * pad - 420) / 2)))
        self.SIDE_W = side
        center_w = max(320, w - 2 * pad - 2 * side - 24)

        # ---------------- cabeçalho
        btn_y = top - 38
        rx0 = w - pad - 250 - 12 - 200
        # tempo total ao centro do cabeçalho, destacado (entre a distância e os botões)
        cx = max(pad + 260, min(w / 2, (pad + 200 + rx0) / 2))
        self._clock.x, self._clock.y = cx, top + 2
        self._clock_cap.x, self._clock_cap.y = cx, top - 38
        self._dist.x, self._dist.y = pad, top - 4
        self._loops_label.x, self._loops_label.y = pad, top - 26
        self._stop_bg.x, self._stop_bg.y, self._stop_bg.width, self._stop_bg.height = \
            w - pad - 120, btn_y, 120, 34
        self._stop_label.x, self._stop_label.y = w - pad - 60, btn_y + 17
        self._pause_bg.x, self._pause_bg.y, self._pause_bg.width, self._pause_bg.height = \
            w - pad - 250, btn_y, 120, 34
        self._pause_label.x, self._pause_label.y = w - pad - 190, btn_y + 17
        rx = w - pad - 250 - 12 - 200
        self._res_minus.x, self._res_minus.y, self._res_minus.width, self._res_minus.height = \
            rx, btn_y, 34, 34
        self._res_plus.x, self._res_plus.y, self._res_plus.width, self._res_plus.height = \
            rx + 166, btn_y, 34, 34
        self._res_minus_label.x, self._res_minus_label.y = rx + 17, btn_y + 18
        self._res_plus_label.x, self._res_plus_label.y = rx + 183, btn_y + 18
        self._res_label.x, self._res_label.y = rx + 100, btn_y + 17

        # ---------------- caixas
        n = boxes_mod.N_BOXES
        box_w = (w - 2 * pad - (n - 1) * self.BOX_GAP) / n
        rows = self._box_rows()
        stacked = rows <= boxes_mod.STACKED_MAX and not compact
        row_h = self.BOX_ROW_STACKED if stacked else self.BOX_ROW_INLINE
        box_h = self.BOX_TITLE_H + rows * row_h + 6
        box_top = top - self.HEADER_H
        big = 17 if box_w >= 185 else 14
        for i, wid in enumerate(self._box_widgets):
            x = pad + i * (box_w + self.BOX_GAP)
            wid["bg"].x, wid["bg"].y = x, box_top - box_h
            wid["bg"].width, wid["bg"].height = box_w, box_h
            wid["title"].x, wid["title"].y = x + 10, box_top - 6
            for k, (label, value) in enumerate(wid["rows"]):
                y = box_top - self.BOX_TITLE_H - k * row_h
                label.x, label.y = x + 28, y
                if stacked:
                    value.anchor_x = "left"
                    value.x, value.y = x + 10, y - 12
                    value.font_size = big
                else:
                    value.anchor_x = "right"
                    value.x, value.y = x + box_w - 10, y + 1
                    value.font_size = 12
            self._place_box_icons(i, x, box_top, row_h)
        self._box_width = box_w
        self._box_stacked = stacked
        mid_top = box_top - box_h - 12

        # ---------------- fundo: rota completa, 2 km, tempo em zona
        sx, sy = pad, pad
        self._strip_geometry = (sx, sy, w - 2 * pad, strip_h)
        self._strip_bg.x, self._strip_bg.y = sx, sy
        self._strip_bg.width, self._strip_bg.height = w - 2 * pad, strip_h
        self._strip_label.x, self._strip_label.y = sx + 8, sy + strip_h - 4
        self._strip_legend.x, self._strip_legend.y = w - pad - 8, sy + strip_h - 4
        self._strip_key = None

        prof_w = min(w - 2 * pad - 2 * 180, max(560, int(w * 0.45)))
        px, py = (w - prof_w) // 2, sy + strip_h + 8
        self._profile_bg.x, self._profile_bg.y = px, py
        self._profile_bg.width, self._profile_bg.height = prof_w, profile_h
        self._profile_label.x, self._profile_label.y = px + 8, py + profile_h - 16
        self._profile_marker.x, self._profile_marker.y = px, py
        self._profile_marker.width, self._profile_marker.height = 2, profile_h
        self._profile_geometry = (px, py, prof_w, profile_h)
        self._build_profile(prof_w)

        # tempo em cada zona: à esquerda do perfil dos 2 km
        tiz_w = px - pad - 12
        self._tiz_geometry = (pad, py, tiz_w, profile_h)
        for k, kind in enumerate(("power", "hr")):
            tz = self._tiz[kind]
            bar_y = py + profile_h - 30 - k * (profile_h // 2)
            tz["title"].x, tz["title"].y = pad, bar_y + 16
            tz["track"].x, tz["track"].y = pad, bar_y
            tz["track"].width, tz["track"].height = max(1, tiz_w), 14
            tz["track"].opacity = 200 if tiz_w > 60 else 0
            tz["bar_y"] = bar_y
        bottom_top = py + profile_h + 12

        # avisos: ao centro, por cima dos perfis
        for i, lab in enumerate(self._toast_labels):
            lab.x, lab.y = w // 2, bottom_top + 8 + i * 24
        mid_bottom = bottom_top + 4

        # ---------------- coluna da direita: classificação + voltas
        right_x = w - pad - self.SIDE_W
        avail = mid_top - mid_bottom
        prev_rows = 3
        laps_h = self._laps_height(prev_rows)
        board_rows = int((avail - laps_h - 8 - 58) // self._BoardPanel.ROW)
        while board_rows < 2 and prev_rows > 0:
            prev_rows -= 1
            laps_h = self._laps_height(prev_rows)
            board_rows = int((avail - laps_h - 8 - 58) // self._BoardPanel.ROW)
        board_rows = max(2, min(6, board_rows))
        if board_rows != self.board_panel.max_rows:
            old = self.board_panel.board
            self.board_panel = self._BoardPanel(0, 0, self.SIDE_W, max_rows=board_rows,
                                                opacity=170)
            self.board_panel.set(old)
        self.board_panel.layout(right_x, mid_top, self.SIDE_W)
        laps_top = mid_top - self.board_panel.height - 8
        self._layout_laps(right_x, laps_top, prev_rows)

        # ---------------- coluna da esquerda: zonas e plano do treino
        y = mid_top
        for kind in ("power", "hr"):
            self._layout_gauge(kind, pad, y)
            y -= self.GAUGE_H + 6
        plan_rows = 1 + max(0, min(4, self.lookahead)) if self.has_workout else 0
        goal_h = self.GOAL_H if self.brief is not None else 0
        plan_h = 30 + goal_h + plan_rows * self.PLAN_ROW + 14
        if goal_h and y - plan_h < mid_bottom:
            goal_h = 0                 # sem espaço: o objetivo aparece no aviso de cada bloco
            plan_h = 30 + plan_rows * self.PLAN_ROW + 14
        while plan_rows > 1 and y - plan_h < mid_bottom:
            plan_rows -= 1
            plan_h = 30 + goal_h + plan_rows * self.PLAN_ROW + 14
        self._goal_h = goal_h
        self._plan_rows_used = plan_rows
        self._layout_plan(pad, y, plan_h)

        # fantasmas: à esquerda da coluna da direita
        for i, lab in enumerate(self._ghost_labels):
            lab.x, lab.y = right_x - 14, mid_top - 18 - i * 26

        # ---------------- centro: subida e fuga
        cw = int(min(460, center_w))
        self._climb_bg.x, self._climb_bg.width = w // 2 - cw // 2, cw
        self._climb_bg.y, self._climb_bg.height = mid_top - 58, 58
        self._climb_title.x, self._climb_title.y = w // 2, mid_top - 6
        self._climb_detail.x, self._climb_detail.y = w // 2, mid_top - 30
        c_top = mid_top - 66
        self._chase_bg.x, self._chase_bg.width = w // 2 - cw // 2, cw
        self._chase_bg.y, self._chase_bg.height = c_top - 66, 66
        self._chase_title.x, self._chase_title.y = w // 2, c_top - 6
        self._chase_detail.x, self._chase_detail.y = w // 2, c_top - 30
        self._chase_track_w = cw - 40
        self._chase_track.x, self._chase_track.y = w // 2 - cw // 2 + 20, c_top - 58
        self._chase_track.width, self._chase_track.height = cw - 40, 8
        self._chase_bar.x, self._chase_bar.y = w // 2 - cw // 2 + 20, c_top - 58
        self._chase_bar.height = 8

        # placa e estado ao centro, sempre acima da zona dos avisos
        mid_y = max((mid_top + mid_bottom) // 2, bottom_top + 3 * 24 + 80)
        sw_ = int(min(640, center_w))
        self._sign_bg.x, self._sign_bg.width = w // 2 - sw_ // 2, sw_
        self._sign_bg.y, self._sign_bg.height = mid_y - 70, 140
        self._sign_title.x, self._sign_title.y = w // 2, mid_y + 20
        self._sign_sub.x, self._sign_sub.y = w // 2, mid_y - 28
        self._paused_label.x, self._paused_label.y = w // 2, mid_bottom + 70
        self._status_bg.x, self._status_bg.width = w // 2 - sw_ // 2, sw_
        self._status_bg.y, self._status_bg.height = mid_bottom + 70 - 27, 54
        self._mid_zone = (mid_bottom, mid_top)

        # ---------------- diálogo
        self._confirm_shade.x, self._confirm_shade.y = 0, 0
        self._confirm_shade.width, self._confirm_shade.height = w, h
        bw, bh = 560, 240
        bx, by = (w - bw) // 2, (h - bh) // 2
        self._confirm_box.x, self._confirm_box.y = bx, by
        self._confirm_box.width, self._confirm_box.height = bw, bh
        self._confirm_title.x, self._confirm_title.y = w // 2, by + bh - 42
        self._confirm_sub.x, self._confirm_sub.y = w // 2, by + bh - 80
        for r, x0 in ((self._confirm_yes, bx + 30), (self._confirm_no, bx + bw // 2 + 10)):
            r.x, r.y, r.width, r.height = x0, by + 76, bw // 2 - 40, 50
        self._confirm_yes_label.x = bx + 30 + (bw // 2 - 40) // 2
        self._confirm_no_label.x = bx + bw // 2 + 10 + (bw // 2 - 40) // 2
        self._confirm_yes_label.y = self._confirm_no_label.y = by + 101
        d = self._confirm_discard
        d.x, d.y, d.width, d.height = bx + 30, by + 20, bw - 60, 40
        self._confirm_discard_label.x, self._confirm_discard_label.y = w // 2, by + 40

    def _place_box_icons(self, i: int, x: float, box_top: float, row_h: int) -> None:
        wid = self._box_widgets[i]
        for k in range(boxes_mod.MAX_PER_BOX):
            old = wid["icons"][k]
            if old is not None:
                try:
                    old.delete()
                except Exception:
                    pass
                wid["icons"][k] = None
            if k >= len(self.boxes[i]["metrics"]):
                continue
            y = box_top - self.BOX_TITLE_H - k * row_h - 12
            wid["icons"][k] = icons.sprite(icons.metric_icon(self.boxes[i]["metrics"][k]),
                                           x + 9, y, 13, batch=self.batch, opacity=200)

    def _laps_height(self, prev_rows: int) -> int:
        extra = prev_rows * self.LAP_PREV_ROW + 6 if prev_rows else 0
        return 28 + 3 * self.LAP_CELL_H + extra + 4

    def _layout_laps(self, x: float, top: float, prev_rows: int) -> None:
        h = self._laps_height(prev_rows)
        for r in (self._laps_bg, self._laps_flash):
            r.x, r.y, r.width, r.height = x, top - h, self.SIDE_W, h
        self._lap_title.x, self._lap_title.y = x + 12, top - 7
        for i, (label, value) in enumerate(self._lap_rows):
            col, row = i % 2, i // 2
            cx = x + 12 + col * (self.SIDE_W // 2)
            cy = top - 30 - row * self.LAP_CELL_H
            label.x, label.y = cx, cy
            value.x, value.y = cx, cy - 12
        for i, lab in enumerate(self._lap_prev):
            lab.x = x + 12
            lab.y = top - 30 - 3 * self.LAP_CELL_H - 4 - i * self.LAP_PREV_ROW
        self._lap_prev_rows = prev_rows
        self._laps_geometry = (x, top - h, self.SIDE_W, h)

    def _layout_gauge(self, kind: str, x: float, top: float) -> None:
        g = self._gauges[kind]
        g["bg"].x, g["bg"].y = x, top - self.GAUGE_H
        g["bg"].width, g["bg"].height = self.SIDE_W, self.GAUGE_H
        g["title"].x, g["title"].y = x + 30, top - 6
        g["value"].x, g["value"].y = x + self.SIDE_W - 10, top - 6
        g["range"].x, g["range"].y = x + 10, top - 26
        g["bar"] = (x + 10, top - self.GAUGE_H + 10, self.SIDE_W - 20, 12)
        if g["icon"] is not None:
            try:
                g["icon"].delete()
            except Exception:
                pass
        g["icon"] = icons.sprite("zones" if kind == "power" else "heart", x + 10, top - 21,
                                 14, batch=self.batch, opacity=0)

    def _layout_plan(self, x: float, top: float, h: float) -> None:
        self._plan_bg.x, self._plan_bg.y = x, top - h
        self._plan_bg.width, self._plan_bg.height = self.SIDE_W, h
        self._plan_title.x, self._plan_title.y = x + 10, top - 6
        goal_h = getattr(self, "_goal_h", 0)
        self._plan_goal.x, self._plan_goal.y = x + 10, top - 24
        for i, (left, right) in enumerate(self._plan_rows):
            y = top - 28 - goal_h - i * self.PLAN_ROW
            left.x, left.y = x + 10, y
            right.x, right.y = x + self.SIDE_W - 10, y
        self._plan_track.x, self._plan_track.y = x + 10, top - h + 6
        self._plan_track.width, self._plan_track.height = self.SIDE_W - 20, 6
        self._plan_bar.x, self._plan_bar.y = x + 10, top - h + 6
        self._plan_bar.height = 6
        self._plan_geometry = (x, top, h)

    # =============================================================== eventos

    def handle(self, event) -> None:
        """Traduz um evento do motor em algo visível."""
        kind, data = event.kind, event.data
        now = time.monotonic()
        if kind == "section_start":
            self.climb = dict(data)
            self.climb_started_at = now
            self.sign = Sign(
                t("sign.climb_start"),
                f"{data.get('name', '')} · "
                f"{t('sign.category', cat=data.get('category', '4'))} · "
                f"{data.get('length_m', 0) / 1000.0:.1f} km @ "
                f"{data.get('avg_grade_pct', 0):.1f} %", now)
        elif kind == "section_sign":
            value, unit = km(data.get("left_m", 0.0), self.units)
            self.sign = Sign(t("sign.to_top", dist=f"{value:.1f} {unit}"),
                             data.get("name", ""), now, duration=2.6)
        elif kind == "section_finish":
            self.climb = None
            self.climb_started_at = None
            parts = [hms(data.get("elapsed_s", 0))]
            if data.get("avg_power_w"):
                parts.append(f"{data['avg_power_w']:.0f} W")
            if data.get("avg_hr"):
                parts.append(f"{data['avg_hr']:.0f} bpm")
            if data.get("avg_cadence"):
                parts.append(f"{data['avg_cadence']:.0f} rpm")
            if data.get("avg_balance_left") is not None:
                parts.append(f"E/D {balance_text(data['avg_balance_left'])}")
            if data.get("total"):
                parts.append(t("toast.rank", rank=data.get("rank", 0),
                               total=data.get("total", 0)))
            self.sign = Sign(t("sign.climb_finish"), " · ".join(parts), now, 5.0)
            if data.get("is_pr"):
                self.toast(t("toast.pr"), emphasis=True)
        elif kind == "strava_start":
            bits = [data.get("name", ""), f"{data.get('distance_m', 0) / 1000.0:.2f} km"]
            if data.get("grade") is not None:
                bits.append(f"{data['grade']:.1f} %")
            if data.get("pr_s"):
                bits.append(f"PR {hms(data['pr_s'])}")
            self.sign = Sign(t("seg.start"), " · ".join(bits), now, 4.0)
        elif kind == "strava_end":
            parts = [data.get("name", ""), hms(data.get("elapsed_s", 0))]
            if data.get("pr_s"):
                parts.append(t("seg.vs_pr", delta=fmt_delta(data["elapsed_s"] - data["pr_s"])))
            self.sign = Sign(t("seg.finish"), " · ".join(parts), now, 5.0)
            if data.get("local_pr") and data.get("local_best_s") is not None:
                self.toast(t("seg.local_pr"), emphasis=True)
        elif kind == "lap":
            if data.get("trigger") in ("manual", "route_loop", "time", "distance"):
                self.lap_flash_at = now
                bits = [t("lap.panel", n=data.get("lap_no", 0)), hms(data.get("elapsed_s", 0))]
                if data.get("avg_power_w"):
                    bits.append(f"{data['avg_power_w']:.0f} W")
                self.toast(" · ".join(bits), emphasis=True)
        elif kind == "resistance":
            key = "res.intensity" if data.get("mode") == "erg" else "res.feel"
            self.toast(t(key, pct=f"{data.get('value', 1.0) * 100:.0f}"), emphasis=True)
        elif kind == "challenge_done":
            self.toast(t("toast.challenge_done", name=data.get("name", "")), emphasis=True)
        elif kind == "route_loop":
            self.toast(t("toast.route_loop", n=data.get("loops", 0),
                         time=hms(data.get("loop_time_s", 0))), emphasis=True)
        elif kind == "workout_done":
            self.toast(t("toast.workout_done"), emphasis=True)
        elif kind == "workout_step":
            self.workout_info = dict(data)
            goal = self.block_goal_full(data.get("idx", data.get("index")))
            if goal:
                self.toast(goal)
            elif data.get("cue"):
                self.toast(data["cue"])
        elif kind == "trainer_error":
            self.toast(f"{t('common.error')}: {data.get('message', '')}")
        elif kind == "ride_started":
            self.toast(t("toast.started"))
        elif kind == "auto_resume":
            self.toast(t("toast.auto_resume"))
        elif kind == "chase_wave":
            self.toast(t("chase.wave", watts=data.get("watts", 0)), emphasis=True)
        elif kind == "chase_close":
            self.toast(t("chase.close", gap=f"{max(0.0, data.get('gap_m', 0)):.0f}"),
                       emphasis=True)
        elif kind == "chase_caught":
            self.sign = Sign(t("chase.caught", time=hms(data.get("survived_s", 0))),
                             t("chase.after_caught"), now, 6.0)
        elif kind == "chase_saved":
            if data.get("clean") and data.get("total"):
                self.toast(t("toast.rank", rank=data.get("rank", 0),
                             total=data.get("total", 0)), emphasis=True)
            if data.get("is_pr"):
                self.toast(t("toast.pr"), emphasis=True)
        elif kind == "chase_unranked":
            self.toast(t("chase.unranked"), emphasis=True)
        elif kind == "recovered":
            self.toast(t("recover.toast"), emphasis=True)
        elif kind == "game_cue":
            self.toast(data.get("text", ""))
        elif kind == "game_judge":
            self.toast(data.get("text", ""), emphasis=True)
        elif kind == "game_over":
            self.sign = Sign(t("game.over"), data.get("summary", ""), now, duration=6.0)

    def toast(self, text: str, emphasis: bool = False) -> None:
        self.toasts.append(Toast(text, time.monotonic(), emphasis=emphasis))
        self.toasts = self.toasts[-4:]

    # ============================================================ atualização

    def update(self, engine) -> None:
        state = engine.state
        now = time.monotonic()

        workout = getattr(engine, "workout", None) is not None
        if workout != self.has_workout:
            self.has_workout = workout
            self.layout(self._w, self._h)

        self._clock.text = hms(state.t_s)
        lap_t = getattr(engine, "lap_elapsed_s", None)
        self._clock_cap.text = (tr("TEMPO TOTAL · volta {t}", "TOTAL TIME · lap {t}",
                                   t=hms(lap_t)) if lap_t is not None
                                else tr("TEMPO TOTAL", "TOTAL TIME"))
        dist_v, dist_u = km(state.dist_m, self.units)
        if state.route is not None:
            pos_v, _ = km(state.pos_m, self.units)
            total_v, _ = km(state.route.total_m, self.units)
            self._dist.text = f"{pos_v:.2f} / {total_v:.2f} {dist_u}"
            self._loops_label.text = (
                f"{t('metric.loops')}: {state.loops} · {dist_v:.1f} {dist_u}"
                if state.loops else "")
        else:
            self._dist.text = f"{dist_v:.2f} {dist_u}"
            self._loops_label.text = ""

        erg = workout and getattr(engine.workout, "erg_enabled", False)
        pct = getattr(state, "intensity", 1.0) if erg else getattr(state, "difficulty", 1.0)
        self._res_label.text = t("res.intensity" if erg else "res.feel",
                                 pct=f"{pct * 100:.0f}")

        self._update_boxes(state)
        self._update_gauges(state)
        self._update_plan(engine, state)
        self._update_laps(engine, now)
        self._update_climb(engine, state)
        self._update_chase(engine, state)
        self._update_board(engine, now)
        self._update_ghosts(engine)
        self._update_sign(now)
        self._update_toasts(now)
        if self._slow_at == 0.0 or now - self._slow_at >= 0.5:
            self._slow_at = now
            self._update_time_in_zones(state)
        self._update_profile(state)
        self._update_strip(state)
        self._update_trace(engine, state, now)

        self.paused = engine.paused
        self.status = state.status
        text = {"waiting": t("ride.waiting"), "paused": t("ride.paused"),
                "auto_paused": t("ride.auto_paused")}.get(state.status, "")
        if self.confirm_visible:
            text = ""
        self._paused_label.text = text
        self._status_bg.opacity = HUD_A if text else 0
        self._pause_label.text = (t("ride.resume_btn") if state.status == "paused"
                                  else t("ride.pause_btn"))

    # ---------------------------------------------------------------- caixas

    def _update_boxes(self, state) -> None:
        stacked = self._box_stacked
        max_chars = max(6, int(self._box_width / (10.5 if stacked else 7.5)))
        label_chars = 26 if stacked else max(8, int(self._box_width / 7.5) - 10)
        for box, wid in zip(self.boxes, self._box_widgets):
            for k, (label, value) in enumerate(wid["rows"]):
                if k >= len(box["metrics"]):
                    label.text = value.text = ""
                    continue
                mid = box["metrics"][k]
                name, text = metrics_mod.formatted(mid, state, self.units)
                name = name.upper()
                value.text = text if len(text) <= max_chars else text[:max_chars - 1] + "…"
                if not stacked:
                    # na mesma linha: o nome só usa o espaço que o valor deixa livre
                    free = self._box_width - 28 - 10 - len(value.text) * 8.5 - 8
                    label_chars = max(3, int(free / 6.8))
                label.text = name if len(name) <= label_chars else name[:label_chars - 1] + "…"
                value.color = self._metric_color(mid, state)

    @staticmethod
    def _metric_color(mid: str, state) -> tuple:
        if mid in ("power_zone", "avg_power_zone", "hr_zone", "avg_hr_zone"):
            z = metrics_mod.value(mid, state)
            if z:
                return _theme.ink(zone_color(z, "hr" if "hr" in mid else "power"))
        return TEXT

    # ---------------------------------------------------- barras das zonas

    def _update_gauges(self, state) -> None:
        p = state.power_3s if state.power_3s is not None else state.power_w
        weight = getattr(state, "weight_kg", None)
        pz = zones_mod.power_zones(state.ftp_w or 200, weight, state.power_zone_bounds)
        value_txt = "—"
        if p is not None:
            value_txt = f"{p:.0f} W" + (f" · {p / weight:.1f} W/kg" if weight else "")
        self._draw_gauge("power", p, pz, value_txt)
        hz = zones_mod.hr_zones(state.lthr, state.hr_zone_bounds) if state.lthr else []
        self._draw_gauge("hr", state.hr_bpm, hz,
                         f"{state.hr_bpm} bpm" if state.hr_bpm is not None else "—")

    def _draw_gauge(self, kind: str, value, zs, value_txt: str) -> None:
        g = self._gauges[kind]
        bar_x, bar_y, bar_w, bar_h = g["bar"]
        if not zs:
            g["bg"].opacity = 0
            g["title"].text = g["value"].text = g["range"].text = ""
            for seg in g["segs"]:
                seg.opacity = 0
            g["fill"].opacity = g["marker"].opacity = 0
            if g["icon"] is not None:
                g["icon"].opacity = 0
            return
        g["bg"].opacity = HUD_A
        if g["icon"] is not None:
            g["icon"].opacity = 220
        for seg, (a0, a1) in zip(g["segs"], zones_mod.segments(zs)):
            seg.x, seg.y = bar_x + a0 * bar_w, bar_y
            seg.width, seg.height = max(1.0, (a1 - a0) * bar_w - 1), bar_h
            seg.opacity = 70
        ga = zones_mod.gauge(value, zs)
        g["value"].text = value_txt
        if ga is None:
            g["title"].text = t("gauge.power" if kind == "power" else "gauge.hr")
            g["title"].color = TEXT
            g["range"].text = ""
            g["fill"].opacity = g["marker"].opacity = 0
            return
        color = zone_color(ga.zone.n, kind)
        g["title"].text = f"Z{ga.zone.n} · {ga.zone.name}"
        g["title"].color = _theme.ink(color)
        g["range"].text = ga.zone.range_text()
        g["fill"].x, g["fill"].y = bar_x, bar_y
        g["fill"].width, g["fill"].height = max(1.0, ga.position * bar_w), bar_h
        g["fill"].color = color
        g["fill"].opacity = 235
        g["marker"].x, g["marker"].y = bar_x + ga.position * bar_w - 1, bar_y - 3
        g["marker"].width, g["marker"].height = 3, bar_h + 6
        g["marker"].opacity = 255

    # ----------------------------------------------------------- plano do treino

    def _update_plan(self, engine, state) -> None:
        runner = getattr(engine, "workout", None)
        rows = getattr(self, "_plan_rows_used", 0)
        plan = runner.plan(state.t_s, ahead=max(0, rows - 1)) if runner is not None and rows \
            else []
        if not plan:
            self._plan_bg.opacity = 0
            self._plan_title.text = ""
            self._plan_goal.text = ""
            for left, right in self._plan_rows:
                left.text = right.text = ""
            self._plan_track.opacity = self._plan_bar.opacity = 0
            return
        self._plan_bg.opacity = HUD_A
        mode = t("wk.erg_on") if runner.erg_enabled else t("plan.erg_off")
        total = len(runner.workout.steps)
        self._plan_title.text = f"{t('wk.step', n=plan[0]['idx'] + 1, total=total)} · {mode}"
        self._plan_goal.text = self.block_goal_text(plan[0]["idx"]) \
            if getattr(self, "_goal_h", 0) else ""
        for i, (left, right) in enumerate(self._plan_rows):
            if i >= len(plan):
                left.text = right.text = ""
                continue
            st = plan[i]
            if st["watts"] is None:
                target = t("plan.free")
            elif st["watts"][0] == st["watts"][1]:
                target = f"{st['watts'][0]} W ({st['pct'][0]:.0f} %)"
            else:
                target = f"{st['watts'][0]}→{st['watts'][1]} W"
            if st.get("cadence"):
                target += f" · {st['cadence']} rpm"
            if st["current"]:
                left.text = f"{t('plan.now')}  {hms(st['remaining_s'])}"
                left.color = ACCENT
                right.color = TEXT
            else:
                word = t("plan.next") if i == 1 else t("plan.then")
                left.text = f"{word}  {hms(st['duration_s'])}"
                left.color = DIM
                right.color = DIM
            right.text = target
        cur = plan[0]
        done = 1.0 - (cur["remaining_s"] / cur["duration_s"] if cur["duration_s"] else 0.0)
        actual = state.power_3s if state.power_3s is not None else state.power_w
        compliance = runner.compliance(actual, state.target_power_w)
        self._plan_track.opacity = 200
        self._plan_bar.opacity = 230
        self._plan_bar.width = max(1.0, (self.SIDE_W - 20) * max(0.0, min(1.0, done)))
        self._plan_bar.color = (GOOD if compliance == 0 else BAD)[:3]

    def set_brief(self, brief) -> None:
        """O resumo do treino (objetivo e blocos), para mostrar o objetivo do
        bloco em curso."""
        self.brief = brief
        self.layout(self.window.width, self.window.height)

    def block_goal_full(self, idx) -> str:
        """«Principal: … · Alvo: …» para o aviso no início de cada bloco."""
        b = self.brief
        if b is None or idx is None or not (0 <= int(idx) < len(b.raw_blocks)):
            return ""
        blk = b.raw_blocks[int(idx)]
        return f"{blk.name}: {blk.goal} · {tr('Alvo', 'Target')} {blk.target}"

    def block_goal_text(self, idx: int) -> str:
        b = self.brief
        if b is None or not (0 <= idx < len(b.raw_blocks)):
            return ""
        blk = b.raw_blocks[idx]
        text = f"{blk.name}: {blk.goal}"
        per = int((self.SIDE_W - 20) / (9 * 0.62))
        if len(text) > per * 2:
            text = text[:per * 2 - 1].rstrip()
        words, lines, cur = text.split(), [], ""
        for wd in words:
            if len(cur) + len(wd) + 1 > per and cur:
                lines.append(cur)
                cur = wd
            else:
                cur = f"{cur} {wd}".strip()
        lines.append(cur)
        return lines[0] if len(lines) == 1 else lines[0].rstrip(".,;: ") + "…"

    # ---------------------------------------------------------------- voltas

    def _update_laps(self, engine, now: float) -> None:
        info = engine.current_lap() if hasattr(engine, "current_lap") else None
        if info is None:
            return
        self._lap_title.text = t("lap.current", n=info["lap_no"])
        dv, du = km(info.get("distance_m") or 0.0, self.units)
        zone = info.get("avg_power_zone")
        cells = [
            ("lap.time", hms(info.get("elapsed_s") or 0)),
            ("lap.distance", f"{dv:.2f} {du}"),
            ("lap.avg_power", f"{info['avg_power_w']:.0f} W" if info.get("avg_power_w")
             else "—"),
            ("lap.power_zone", format_metric(zone, "pzone") if zone else "—"),
            ("lap.avg_cadence", f"{info['avg_cadence']:.0f} rpm" if info.get("avg_cadence")
             else "—"),
            ("lap.avg_hr", f"{info['avg_hr']:.0f} bpm" if info.get("avg_hr") else "—"),
        ]
        for (label, value), (key, text) in zip(self._lap_rows, cells):
            label.text = t(key).upper()
            value.text = text
            value.color = _theme.ink(zone_color(zone)) if key == "lap.power_zone" and zone \
                else TEXT
        done = [lp for lp in getattr(engine, "laps", [])
                if lp.trigger in ("manual", "route_loop")]
        rows = getattr(self, "_lap_prev_rows", 0)
        recent = list(reversed(done))[:rows]
        for i, lab in enumerate(self._lap_prev):
            if i < len(recent):
                lp = recent[i]
                d, u = km(lp.end_dist_m - lp.start_dist_m, self.units)
                bits = [f"{lp.lap_no}.", hms(lp.end_t_s - lp.start_t_s), f"{d:.2f} {u}"]
                if lp.avg_power_w:
                    bits.append(f"{lp.avg_power_w:.0f} W")
                if lp.avg_cadence:
                    bits.append(f"{lp.avg_cadence:.0f} rpm")
                if lp.avg_hr:
                    bits.append(f"{lp.avg_hr:.0f} bpm")
                lab.text = "  ".join(bits)
            else:
                lab.text = ""
        if self.lap_flash_at is not None and now - self.lap_flash_at < 1.5:
            self._laps_flash.opacity = int(90 * (1.5 - (now - self.lap_flash_at)) / 1.5)
        else:
            self._laps_flash.opacity = 0

    # -------------------------------------------------------- tempo em zona

    def _update_time_in_zones(self, state) -> None:
        x0, _, width, _ = self._tiz_geometry
        for kind, secs in (("power", getattr(state, "power_zone_s", None)),
                           ("hr", getattr(state, "hr_zone_s", None))):
            tz = self._tiz[kind]
            total = sum(secs) if secs else 0.0
            tz["title"].text = (t("tiz.power" if kind == "power" else "tiz.hr")
                                if width >= 60 else "")
            if width < 60 or not total:
                for seg, lab in zip(tz["segs"], tz["pcts"]):
                    seg.opacity = 0
                    lab.text = ""
                continue
            x = x0
            for i, (seg, lab) in enumerate(zip(tz["segs"], tz["pcts"])):
                share = secs[i] / total if i < len(secs) else 0.0
                seg.x, seg.y = x, tz["bar_y"]
                seg.width, seg.height = max(0.0, share * width), 14
                seg.opacity = 235 if share > 0 else 0
                lab.text = f"{share * 100:.0f}%" if share * width >= 26 else ""
                lab.x, lab.y = x + share * width / 2, tz["bar_y"] + 7
                x += share * width

    # ----------------------------------------------------- perfil dos 2 km

    def _build_profile(self, width: int) -> None:
        bars = max(48, int(width // self.PROFILE_BAR_PX))
        edges = max(24, int(width // self.PROFILE_EDGE_PX))
        if len(self._profile_bars) == bars and len(self._profile_edge) == edges:
            return
        for obj in self._profile_bars + self._profile_edge:
            try:
                obj.delete()
            except Exception:
                pass
        b = self.batch
        self._profile_bars = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=(120, 140, 160),
                                                      batch=b) for _ in range(bars)]
        self._profile_edge = [make_line(0, 0, 0, 0, thickness=2, color=TEXT[:3],
                                        batch=b) for _ in range(edges)]
        self._profile_at = 0.0

    def _update_profile(self, state) -> None:
        px, py, pw, ph = self._profile_geometry
        route = state.route
        if route is None:
            for bar in self._profile_bars:
                bar.height = 0
            for ln in self._profile_edge:
                ln.x = ln.x2 = ln.y = ln.y2 = 0
            self._profile_label.text = ""
            return
        now = time.monotonic()
        if now - self._profile_at < 0.25:
            return
        self._profile_at = now
        window_m = 2000.0
        n = len(self._profile_bars)
        pts, lo, hi = route.profile_normalized(state.pos_m, window_m, n)
        bar_w = pw / n
        usable = ph - 18
        for i, (bar, (_, y)) in enumerate(zip(self._profile_bars, pts)):
            bar.x, bar.y = px + i * bar_w, py
            bar.width, bar.height = bar_w + 0.6, max(2.0, y * usable)
            d = (state.pos_m + window_m * i / (n - 1)) % max(route.total_m, 1.0)
            bar.color = _grade_color(route.grade_at(d))
        m = len(self._profile_edge)
        for k, ln in enumerate(self._profile_edge):
            i0 = min(n - 1, int(k * (n - 1) / m))
            i1 = min(n - 1, int((k + 1) * (n - 1) / m))
            ln.x, ln.x2 = px + i0 * bar_w + bar_w / 2, px + i1 * bar_w + bar_w / 2
            ln.y = py + max(2.0, pts[i0][1] * usable)
            ln.y2 = py + max(2.0, pts[i1][1] * usable)
        self._profile_label.text = f"{lo:.0f}–{hi:.0f} m   ·   {t('profile.next2')}"

    # ----------------------------------------- perfil da rota + potência e FC

    def _update_strip(self, state) -> None:
        sx, sy, sw, sh = self._strip_geometry
        route = state.route
        if route is None or route.total_m <= 0:
            self._strip_bg.opacity = 0
            for obj in (self._strip_done, self._strip_window, self._strip_marker):
                obj.opacity = 0
            for bar in self._strip_bars:
                bar.height = 0
            self._strip_label.text = self._strip_legend.text = ""
            return
        self._strip_bg.opacity = HUD_A
        key = (id(route), sw)
        if self._strip_key != key:
            self._build_strip(route, sx, sy, sw, sh)
            self._strip_key = key
        frac = max(0.0, min(1.0, state.pos_m / route.total_m))
        self._strip_done.x, self._strip_done.y = sx, sy
        self._strip_done.width, self._strip_done.height = sw * frac, sh
        self._strip_done.opacity = 90
        win = min(1.0, 2000.0 / route.total_m)
        self._strip_window.x, self._strip_window.y = sx + sw * frac, sy
        self._strip_window.width = max(2.0, min(sw * win, sw - sw * frac))
        self._strip_window.height = sh
        self._strip_window.opacity = 40
        self._strip_marker.x, self._strip_marker.y = sx + sw * frac - 1, sy
        self._strip_marker.width, self._strip_marker.height = 3, sh
        self._strip_marker.opacity = 255
        pos_v, unit = km(state.pos_m, self.units)
        tot_v, _ = km(route.total_m, self.units)
        self._strip_label.text = (f"{t('profile.route')} · {pos_v:.1f} / {tot_v:.1f} {unit}"
                                  f" · {state.ele_m:.0f} m")
        self._strip_legend.text = t("profile.legend")

    def _build_strip(self, route, sx, sy, sw, sh) -> None:
        for bar in self._strip_bars:
            try:
                bar.delete()
            except Exception:
                pass
        n = max(48, int(sw // self.STRIP_BAR_PX))
        pts, _, _ = route.profile_normalized(0.0, route.total_m, n)
        usable = sh - 18
        bar_w = sw / n
        self._strip_bars = []
        for i, (_, y) in enumerate(pts):
            d = route.total_m * i / max(n - 1, 1)
            bar = pyglet.shapes.Rectangle(sx + i * bar_w, sy, bar_w + 0.6,
                                          max(2.0, y * usable),
                                          color=_grade_color(route.grade_at(d)),
                                          batch=self.batch)
            bar.opacity = 150
            self._strip_bars.append(bar)
        # as linhas de potência e FC criam-se depois das barras (ficam por cima)
        for ln in self._trace_power + self._trace_hr:
            try:
                ln.delete()
            except Exception:
                pass
        cols = max(16, int(sw // self.TRACE_PX))
        self._trace_power = [make_line(0, 0, 0, 0, thickness=2, color=POWER_LINE,
                                       batch=self.batch) for _ in range(cols)]
        self._trace_hr = [make_line(0, 0, 0, 0, thickness=2, color=HR_LINE,
                                    batch=self.batch) for _ in range(cols)]
        self._trace_at = 0.0

    def _update_trace(self, engine, state, now: float) -> None:
        """Potência (amarelo) e FC (vermelho) ao longo do que já se pedalou nesta
        volta, por cima do perfil da rota. Uma coluna a cada 3 px, uma vez por
        segundo."""
        route = state.route
        if route is None or not self._trace_power:
            return
        if self._trace_at and now - self._trace_at < 1.0:
            return
        self._trace_at = now
        trace = getattr(engine, "trace", None) or ()
        sx, sy, sw, sh = self._strip_geometry
        cols = len(self._trace_power)
        p_sum, p_n = [0.0] * cols, [0] * cols
        h_sum, h_n = [0.0] * cols, [0] * cols
        for pos, p, hr in trace:
            c = min(cols - 1, max(0, int(pos / route.total_m * cols)))
            if p is not None:
                p_sum[c] += p
                p_n[c] += 1
            if hr is not None:
                h_sum[c] += hr
                h_n[c] += 1
        p_top = max(1.0, (state.ftp_w or 200) * 1.6)
        h_lo, h_hi = 60.0, max(120.0, (state.lthr or 170) * 1.15)
        usable = sh - 20

        def draw(lines, sums, counts, lo, hi):
            prev = None
            for c, ln in enumerate(lines):
                if counts[c]:
                    v = sums[c] / counts[c]
                    y = sy + 4 + max(0.0, min(1.0, (v - lo) / (hi - lo))) * usable
                    x = sx + (c + 0.5) * sw / cols
                    if prev is not None:
                        ln.x, ln.y, ln.x2, ln.y2 = prev[0], prev[1], x, y
                    else:
                        ln.x, ln.y, ln.x2, ln.y2 = x, y, x, y
                    ln.opacity = 255
                    prev = (x, y)
                else:
                    ln.x = ln.x2 = ln.y = ln.y2 = 0
                    ln.opacity = 0
                    prev = None

        draw(self._trace_power, p_sum, p_n, 0.0, p_top)
        draw(self._trace_hr, h_sum, h_n, h_lo, h_hi)

    # ------------------------------------------------------- subida e fuga

    def _update_climb(self, engine, state) -> None:
        active = engine.active_climb() if hasattr(engine, "active_climb") else None
        if self.climb is None or active is None:
            self._climb_bg.opacity = 0
            self._climb_title.text = self._climb_detail.text = ""
            return
        self._climb_bg.opacity = HUD_A
        name = self.climb.get("name", "")
        cat = self.climb.get("category", "4")
        self._climb_title.text = f"{name} · {t('sign.category', cat=cat)}"
        climb_time = max(0.0, active[1])
        left = max(0.0, self.climb.get("end_m", 0.0) - state.pos_m)
        left_v, left_u = km(left, self.units)
        gain = self.climb.get("gain_m", 0.0)
        grade = self.climb.get("avg_grade_pct", 0.0)
        self._climb_detail.text = (
            f"{hms(climb_time)}   ·   {t('sign.to_top', dist=f'{left_v:.1f} {left_u}')}"
            f"   ·   ↑ {gain:.0f} m @ {grade:.1f} %")

    def _update_game(self, game) -> None:
        """O painel do centro serve o jogo do modo Challenge: instrução, estado e
        uma barra de progresso (do bloco, da corda, da volta…)."""
        self._chase_bg.opacity = HUD_A
        if game.finished:
            self._chase_title.text = t("game.over")
            self._chase_detail.text = game.summary_text()
            self._chase_title.color = ACCENT
            self._chase_track.opacity = self._chase_bar.opacity = 0
            return
        self._chase_title.text = game.headline
        self._chase_detail.text = game.detail
        color = {"good": GOOD, "warn": ACCENT, "bad": BAD}.get(game.mood, TEXT)
        self._chase_title.color = color
        self._chase_track.opacity = 200
        self._chase_bar.opacity = 230
        self._chase_bar.color = color[:3]
        ratio = max(0.0, min(1.0, game.progress))
        self._chase_bar.width = max(2.0, getattr(self, "_chase_track_w", 420) * ratio)

    def _update_chase(self, engine, state) -> None:
        game = getattr(engine, "game", None)
        if game is not None and engine.started:
            self._update_game(game)
            return
        ch = getattr(engine, "chase", None)
        if ch is None or not engine.started:
            self._chase_bg.opacity = self._chase_track.opacity = self._chase_bar.opacity = 0
            self._chase_title.text = self._chase_detail.text = ""
            return
        self._chase_bg.opacity = HUD_A
        if not ch.active:
            self._chase_title.text = (t("chase.caught", time=hms(ch.t_s)) if ch.caught
                                      else t("chase.escaped", time=hms(ch.t_s)))
            self._chase_detail.text = t("chase.after_caught")
            self._chase_track.opacity = self._chase_bar.opacity = 0
            return
        gap = ch.gap_m(state.dist_m)
        gap_s = ch.gap_s(state.dist_m)
        self._chase_title.text = (f"{t('chase.gap')}: {max(0.0, gap):.0f} m · "
                                  f"{max(0.0, gap_s):.1f} s")
        self._chase_detail.text = (f"{t('chase.chaser')} {ch.watts} W · "
                                   f"{t('chase.next_wave', s=int(ch.next_wave_in_s))} · "
                                   f"{hms(ch.t_s)}")
        ratio = max(0.0, min(1.0, gap / 300.0))
        self._chase_track.opacity = 200
        self._chase_bar.opacity = 230
        self._chase_bar.width = max(2.0, getattr(self, "_chase_track_w", 420) * ratio)
        if gap < WARN_GAPS_M[-1]:
            color = BAD
        elif gap < WARN_GAPS_M[1]:
            color = _theme.rgba(_theme.P.warn)
        elif gap < WARN_GAPS_M[0]:
            color = ACCENT
        else:
            color = GOOD
        self._chase_bar.color = color[:3]
        self._chase_title.color = color

    def _update_board(self, engine, now: float) -> None:
        if not hasattr(engine, "live_board"):
            return
        if now - self._board_at < 0.5 and self.board_panel.board is not None:
            return
        self._board_at = now
        try:
            board = engine.live_board()
        except Exception:                 # uma consulta falhada não pára a sessão
            return
        self.board_panel.set(board)
        ch = getattr(engine, "chase", None)
        if board.title != self._board_ctx:
            self._board_ctx = board.title
        elif (ch is not None and ch.active and board.my_rank and self._last_rank
              and board.my_rank < self._last_rank):
            self.toast(t("chase.rank_up", rank=board.my_rank), emphasis=True)
        self._last_rank = board.my_rank

    def _update_ghosts(self, engine) -> None:
        positions = engine.ghost_positions() if hasattr(engine, "ghost_positions") else []
        for i, lab in enumerate(self._ghost_labels):
            if i < len(positions):
                label, _dist, delta_s = positions[i]
                lab.text = f"{label}  {fmt_delta(delta_s)}"
                lab.color = GOOD if delta_s < 0 else BAD
            else:
                lab.text = ""

    def _update_sign(self, now: float) -> None:
        if self.sign is None or now - self.sign.born > self.sign.duration:
            self.sign = None
            self._sign_bg.opacity = 0
            self._sign_title.text = self._sign_sub.text = ""
            return
        age = now - self.sign.born
        fade = 1.0 if age < self.sign.duration - 0.8 else \
            max(0.0, (self.sign.duration - age) / 0.8)
        self._sign_bg.opacity = int(190 * fade)
        self._sign_title.text = self.sign.title
        self._sign_sub.text = self.sign.subtitle
        self._sign_title.color = ACCENT[:3] + (int(255 * fade),)
        self._sign_sub.color = TEXT[:3] + (int(255 * fade),)

    def _update_toasts(self, now: float) -> None:
        self.toasts = [x for x in self.toasts if now - x.born < x.duration]
        for i, lab in enumerate(self._toast_labels):
            if i < len(self.toasts):
                toast = self.toasts[len(self.toasts) - 1 - i]
                fade = min(1.0, (toast.duration - (now - toast.born)) / 0.8)
                base = ACCENT[:3] if toast.emphasis else TEXT[:3]
                lab.text = toast.text
                lab.color = base + (int(255 * max(0.0, min(1.0, fade))),)
            else:
                lab.text = ""

    # ============================================================ diálogo

    def show_confirm(self) -> None:
        self.confirm_visible = True
        self._confirm_shade.opacity = _theme.P.shade_alpha
        self._confirm_box.opacity = 245
        self._confirm_yes.opacity = self._confirm_no.opacity = 255
        self._confirm_discard.opacity = 255
        self._confirm_discard_label.text = tr("Terminar sem guardar (D)", "Finish without saving (D)")
        self._confirm_title.text = t("confirm.title")
        self._confirm_sub.text = t("confirm.sub")
        self._confirm_yes_label.text = t("confirm.yes")
        self._confirm_no_label.text = t("confirm.no")

    def hide_confirm(self) -> None:
        self.confirm_visible = False
        for r in (self._confirm_shade, self._confirm_box, self._confirm_yes,
                  self._confirm_no, self._confirm_discard):
            r.opacity = 0
        for lab in (self._confirm_title, self._confirm_sub, self._confirm_yes_label,
                    self._confirm_no_label, self._confirm_discard_label):
            lab.text = ""

    def confirm_hit(self, x: float, y: float) -> str | None:
        if not self.confirm_visible:
            return None
        if _hit(self._confirm_yes, x, y):
            return "yes"
        if _hit(self._confirm_no, x, y):
            return "no"
        if _hit(self._confirm_discard, x, y):
            return "discard"
        return None

    # ============================================================== botões

    def stop_button_hit(self, x: float, y: float) -> bool:
        return _hit(self._stop_bg, x, y)

    def pause_button_hit(self, x: float, y: float) -> bool:
        return _hit(self._pause_bg, x, y)

    def resistance_hit(self, x: float, y: float) -> int:
        """−1, +1, ou 0 se o clique não foi nos botões da resistência."""
        if _hit(self._res_minus, x, y):
            return -1
        if _hit(self._res_plus, x, y):
            return 1
        return 0

    # ============================================================== desenho

    def draw(self) -> None:
        glDisable(GL_DEPTH_TEST)
        self.window.projection = Mat4.orthogonal_projection(
            0, self.window.width, 0, self.window.height, -255, 255)
        self.window.view = Mat4()
        self.batch.draw()
        self.board_panel.draw()
        if self.confirm_visible:
            self.top_batch.draw()
        glEnable(GL_DEPTH_TEST)
