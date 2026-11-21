"""Estatísticas por exercício (Ginásio): a evolução da carga, da 1RM estimada,
do volume, do RPE, do tempo que demoraste e das repetições, sessão a sessão,
com as últimas sessões em tabela. Também é o «Ver histórico» do construtor.

Tab muda a métrica · ←/→ muda o exercício · Enter escolhe-o numa lista ·
clica num ponto do gráfico para ver a sessão (Enter abre a análise).
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from perennia.core import strength_analysis as sa
from perennia.core import strength as st
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.gfx import theme as _theme
from perennia.gfx.compat import label as make_label
from perennia.ui.app import Screen
from perennia.ui.widgets import Chart, Dropdown, Item

TABLE_ROWS = 6


def _fmt(metric: str, v: float | None) -> str:
    if v is None:
        return "—"
    if metric == "time_s":
        return f"{v:.1f} min"
    if metric == "avg_rpe":
        return f"{v:.1f}"
    if metric == "reps":
        return f"{v:.0f}"
    return f"{v:,.1f} kg".replace(",", " ").replace(".0 kg", " kg")


class ExerciseStatsScreen(Screen):
    TABBED = True

    def __init__(self, app, exercise_id: int | None = None):
        super().__init__(app)
        self.exs = st.exercises_with_history(app.db)
        ids = [e["id"] for e in self.exs]
        if exercise_id is not None and exercise_id not in ids:
            ex = st.exercise(app.db, exercise_id)
            if ex is not None:
                self.exs.insert(0, {"id": exercise_id, "name": ex["name"], "n": 0})
                ids.insert(0, exercise_id)
        self.idx = ids.index(exercise_id) if exercise_id in ids else 0
        self.point: int | None = None
        w, h = app.window.width, app.window.height
        self.chart = Chart(80, 200, w - 160, 200)
        b = self.batch = pyglet.graphics.Batch()
        P = _theme.P
        self.kpis = [make_label("", font_size=10, bold=True, color=_theme.rgba(P.text),
                                anchor_y="top", batch=b) for _ in range(4)]
        self.table_out = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b)
        self.table_bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b)
        self.sel_bg = pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.select, batch=b)
        self.head = [make_label("", font_size=9, bold=True, color=_theme.rgba(P.dim),
                                anchor_y="center", batch=b) for _ in range(6)]
        self.cells = [[make_label("", font_size=9, color=_theme.rgba(P.text), anchor_y="center",
                                  batch=b) for _ in range(6)] for _ in range(TABLE_ROWS)]
        self._layout()

    def tab_labels(self) -> list[str]:
        return [sa.metric_name(m) for m in sa.METRICS]

    @property
    def metric(self) -> str:
        return sa.METRICS[self.tab % len(sa.METRICS)]

    @property
    def exercise(self) -> dict | None:
        return self.exs[self.idx % len(self.exs)] if self.exs else None

    def on_tab(self) -> None:
        self.point = None

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        top = self.content_top(h) - 2 * 38 - 12
        table_h = 26 + TABLE_ROWS * 22
        bottom = 70 + table_h + 30
        self.kpi_y = top - 4
        self.chart.x, self.chart.y = 80, bottom
        self.chart.width, self.chart.height = w - 160, max(80, self.kpi_y - 70 - bottom)
        self.chart._place_static()
        self.table_geo = (48, 66, w - 96, table_h)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()
        self.enter()

    def enter(self) -> None:
        a = self.app
        ex = self.exercise
        if ex is None:
            self.chrome.set(tr("Estatísticas por exercício", "Exercise statistics"),
                            tr("Ainda não há séries registadas", "No sets logged yet"),
                            self.footer())
            self.list.set_items([Item(tr("Treina primeiro um plano de força",
                                         "Train a strength plan first"), enabled=False)])
            self.chart.show_line("", [], empty_text="—")
            return
        self.hist = sa.history(a.db, ex["id"])
        self.list.set_items([
            Item(tr("Exercício", "Exercise"), value=f"‹ {ex['name']} ›", data="exercise",
                 detail=tr("Enter abre a lista (escreve para pesquisar) · ←/→ outro",
                           "Enter opens the list (type to search) · ←/→ another"),
                 dropdown=Dropdown(self._exercise_labels, self.idx, self._chosen,
                                   title=tr("Escolher o exercício", "Choose the exercise"))),
            Item(tr("Sessões com este exercício", "Sessions with this exercise"),
                 value=str(len(self.hist)), enabled=False)], keep_index=True)
        self.list.set_visible_rows(2)
        self.chrome.set(tr("Estatísticas por exercício", "Exercise statistics"),
                        tr("Ginásio · evolução da carga, do RPE e do tempo",
                           "Gym · progress of load, RPE and time"),
                        tr("Tab métrica · ←/→ exercício · clica num ponto · Esc voltar",
                           "Tab metric · ←/→ exercise · click a point · Esc back"))
        self._refresh()

    def _refresh(self) -> None:
        m = self.metric
        data = sa.series(self.hist, m)
        labels = [f"{d[8:10]}/{d[5:7]}" for d, _ in data]
        vals = [v for _, v in data]
        title = f"{sa.metric_name(m)}" + (f" ({sa.metric_unit(m)})" if sa.metric_unit(m) else "")
        empty = tr("Sem dados desta métrica ainda", "No data for this metric yet")
        fmt = (lambda v: f"{v:.0f}") if m != "avg_rpe" else (lambda v: f"{v:.1f}")
        if m in ("volume", "time_s", "reps") or len(vals) < 2:
            self.chart.show_bars(title, vals, labels, empty_text=empty, fmt=fmt)
        else:
            self.chart.show_line(title, vals, labels, empty_text=empty, fmt=fmt)
        if self.point is not None and self.point < len(data):
            self.chart.select(self.point, f"{data[self.point][0]}: {_fmt(m, data[self.point][1])}")
        # números do topo
        last = vals[-1] if vals else None
        best = (max(vals) if m != "time_s" else min(vals)) if vals else None
        tr_ = sa.trend(vals)
        k = [tr("Última: {v}", "Last: {v}", v=_fmt(m, last)),
             tr("Melhor: {v}", "Best: {v}", v=_fmt(m, best)),
             tr("Tendência: {v}", "Trend: {v}", v=f"{tr_:+.0f} %" if tr_ is not None else "—"),
             tr("{n} sessões", "{n} sessions", n=len(self.hist))]
        x = 48
        for lab, text in zip(self.kpis, k):
            lab.text = text
            lab.x, lab.y = x, self.kpi_y
            x += len(text) * 7.4 + 28
        # tabela das últimas sessões
        P = _theme.P
        tx, ty, tw, th = self.table_geo
        self.table_out.x, self.table_out.y = tx - 1, ty - 1
        self.table_out.width, self.table_out.height = tw + 2, th + 2
        self.table_bg.x, self.table_bg.y, self.table_bg.width, self.table_bg.height = tx, ty, tw, th
        cols = [0, 0.13, 0.55, 0.67, 0.79, 0.89]
        heads = [tr("Data", "Date"), tr("Séries (reps × kg)", "Sets (reps × kg)"),
                 tr("Carga máx.", "Top load"), tr("1RM est.", "Est. 1RM"), "RPE",
                 tr("Tempo", "Time")]
        for lab, c, text in zip(self.head, cols, heads):
            lab.text = text
            lab.x, lab.y = tx + 12 + c * (tw - 24), ty + th - 13
        recent = list(reversed(self.hist))[:TABLE_ROWS]
        sel_session = None
        if self.point is not None:
            data_sessions = [h for h in self.hist if h.get(m) is not None]
            if self.point < len(data_sessions):
                sel_session = data_sessions[self.point]["session_id"]
        self.sel_bg.opacity = 0
        self.table_rows = []
        for r, row in enumerate(self.cells):
            y = ty + th - 26 - r * 22 - 11
            if r < len(recent):
                h = recent[r]
                sets = ", ".join(f"{rp}×{ld:g}" if ld else f"{rp}" for rp, ld, _p in h["sets"])
                vals_ = [h["date"][8:10] + "/" + h["date"][5:7], sets[:46],
                         _fmt("max_load", h["max_load"]), _fmt("best_e1rm", h["best_e1rm"]),
                         _fmt("avg_rpe", h["avg_rpe"]),
                         hms(h["time_s"]) if h["time_s"] is not None else "—"]
                if h["session_id"] == sel_session:
                    self.sel_bg.x, self.sel_bg.y = tx + 2, y - 10
                    self.sel_bg.width, self.sel_bg.height = tw - 4, 20
                    self.sel_bg.opacity = 255
                self.table_rows.append((h["session_id"], y))
            else:
                vals_ = [""] * 6
            for lab, c, text in zip(row, cols, vals_):
                lab.text = text
                lab.x, lab.y = tx + 12 + c * (tw - 24), y
        _ = P

    # ------------------------------------------------------------- ações

    def _exercise_labels(self) -> list[str]:
        return [f"{e['name']}  ·  " + tr("{n} séries", "{n} sets", n=e.get("n", 0))
                for e in self.exs]

    def _chosen(self, k: int) -> None:
        self.idx = k
        self.point = None
        self.enter()
