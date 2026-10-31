"""Análise pós-treino de uma sessão de força (como a do TrainingPeaks).

Em cima, os números da sessão: cumprimento, volume, séries, repetições, RPE,
tempo em série e FC. À esquerda, um exercício por linha: séries, repetições,
carga máxima, volume, 1RM estimada (com a diferença para a vez anterior) e o
cumprimento, a cores. À direita, o exercício escolhido série a série:
prescrito ao lado do feito, quanto durou cada série e a FC, e um gráfico da
carga prescrita e feita.

↑↓ exercício · Enter histórico do exercício · F feedback · S séries · Esc voltar.
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import strength_analysis as sa
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx import theme as _theme
from velo.gfx.compat import label as make_label
from velo.ui.app import Screen
from velo.ui.brief import wrap
from velo.ui.widgets import Item

MAX_EX = 12
MAX_SETS = 10


def _kg(v) -> str:
    return "—" if v in (None, 0) else f"{v:,.1f}".replace(",", " ").replace(".0", "") + " kg"


def _pct(c) -> str:
    return "—" if c is None else f"{c * 100:.0f} %"


def tone_color(tone: str):
    P = _theme.P
    return {"good": P.good, "warn": P.warn, "bad": P.bad}.get(tone, P.dim)


class StrengthAnalysisScreen(Screen):
    def __init__(self, app, session_id: str):
        self.sid = session_id
        super().__init__(app)
        self.data = sa.session(app.db, session_id)
        self.sel = 0
        self.list.y = -3000
        self._build()
        self._layout()

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        R = lambda c=P.panel: pyglet.shapes.Rectangle(0, 0, 0, 0, color=c, batch=b)  # noqa: E731
        L = lambda size=10, bold=False, color=None, **kw: make_label(  # noqa: E731
            "", font_size=size, bold=bold, color=color or _theme.rgba(P.text), batch=b, **kw)
        dim = _theme.rgba(P.dim)
        self.band = R(P.header)
        self.kpi = [(R(P.border), R(P.panel), L(8, True, dim, anchor_y="top"),
                     L(15, True, anchor_y="top"), L(8, color=dim, anchor_y="top"))
                    for _ in range(6)]
        self.t_out, self.t_bg = R(P.border), R(P.panel)
        self.t_sel = R(P.select)
        self.t_title = L(11, True, anchor_y="top")
        self.t_head = [L(8, True, dim, anchor_y="center") for _ in range(8)]
        self.t_rows = []
        for _ in range(MAX_EX):
            self.t_rows.append({"chip": R(P.panel2),
                                "cells": [L(9, anchor_y="center") for _ in range(8)]})
        self.d_out, self.d_bg = R(P.border), R(P.panel)
        self.d_title = L(11, True, anchor_y="top")
        self.d_sub = L(9, color=dim, anchor_y="top")
        self.d_head = [L(8, True, dim, anchor_y="center") for _ in range(6)]
        self.d_rows = [[L(9, anchor_y="center") for _ in range(6)] for _ in range(MAX_SETS)]
        self.bars_p = [R(P.panel2) for _ in range(MAX_SETS)]
        self.bars_d = [R(P.accent) for _ in range(MAX_SETS)]
        self.bar_labels = [L(8, color=dim, anchor_x="center", anchor_y="top")
                           for _ in range(MAX_SETS)]
        self.d_chart_title = L(8, True, dim, anchor_y="bottom")
        self.d_hint = L(9, color=_theme.rgba(P.accent), anchor_y="bottom")
        self.empty = L(11, color=dim, anchor_x="center", anchor_y="center")
        self.chrome.title.color = _theme.rgba(P.header_text)
        self.chrome.subtitle.color = _theme.rgba(P.header_dim)

    # ---------------------------------------------------------------- medidas

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        self.chrome.title.font_size = 18
        self.band.x, self.band.y, self.band.width, self.band.height = 0, h - 26 - 76, w, 76
        self.chrome.title.y, self.chrome.subtitle.y = h - 38, h - 72
        self.top = h - 26 - 76 - 12
        self._fill()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -3000
        self._layout()

    def enter(self) -> None:
        d = self.data
        if d is None:
            self.chrome.set(tr("Sessão não encontrada", "Session not found"), "", "")
            return
        day = str(d["started_at"])[:10]
        from velo.core.naming import pretty
        self.chrome.set(tr("Análise pós-treino · {n}", "Post-workout analysis · {n}",
                           n=pretty(d["name"]) or tr("Força", "Strength")),
                        f"{day[8:10]}/{day[5:7]}/{day[:4]} · {hms(d['elapsed_s'])} · "
                        + tr("{a} de {b} séries", "{a} of {b} sets", a=d["done_sets"],
                             b=d["planned_sets"] or d["done_sets"]),
                        tr("↑↓ exercício · Enter histórico · F feedback · S séries · Esc voltar",
                           "↑↓ exercise · Enter history · F feedback · S sets · Esc back"))
        self.list.set_items([Item(tr("Histórico do exercício", "Exercise history"),
                                  action=self.open_history)])
        self._fill()

    # ---------------------------------------------------------------- conteúdo

    def _fill(self) -> None:
        d = self.data
        if d is None:
            return
        P = _theme.P
        w = self.app.window.width
        top = self.top
        # ---- números da sessão
        work = d["work_s"]
        kp = [(tr("CUMPRIMENTO", "COMPLIANCE"), _pct(d["compliance"]),
               tr("feito ÷ prescrito", "done ÷ planned"), d["tone"]),
              (tr("VOLUME", "VOLUME"), _kg(d["volume"]),
               tr("prescrito {v}", "planned {v}", v=_kg(d["planned_volume"])), ""),
              (tr("SÉRIES", "SETS"), f"{d['done_sets']}/{d['planned_sets'] or d['done_sets']}",
               "", ""),
              (tr("REPETIÇÕES", "REPS"), f"{d['done_reps']}/{d['planned_reps'] or d['done_reps']}",
               "", ""),
              (tr("RPE MÉDIO", "AVG RPE"), f"{d['avg_rpe']:.1f}" if d.get("avg_rpe") else "—",
               "", ""),
              (tr("TEMPO EM SÉRIE", "TIME UNDER SETS"), hms(work) if work else "—",
               tr("FC média {h}", "avg HR {h}", h=f"{d['avg_hr']:.0f}") if d.get("avg_hr")
               else tr("total {t}", "total {t}", t=hms(d["elapsed_s"])), "")]
        n = len(self.kpi)
        gap = 10
        kw = (w - 96 - gap * (n - 1)) / n
        kh = 62
        for i, ((o, r, cap, val, sub), (c, v, s, tone)) in enumerate(zip(self.kpi, kp)):
            x = 48 + i * (kw + gap)
            o.x, o.y, o.width, o.height = x - 1, top - kh - 1, kw + 2, kh + 2
            r.x, r.y, r.width, r.height = x, top - kh, kw, kh
            cap.text, val.text, sub.text = c, v, s
            cap.x, cap.y = x + 10, top - 8
            val.x, val.y = x + 10, top - 22
            val.color = _theme.ink(tone_color(tone)) if tone else _theme.rgba(P.text)
            sub.x, sub.y = x + 10, top - 46
        # ---- tabela dos exercícios
        y_top = top - kh - 14
        bottom = 66
        tw = (w - 96) * 0.58
        tx = 48
        self.t_out.x, self.t_out.y = tx - 1, bottom - 1
        self.t_out.width, self.t_out.height = tw + 2, y_top - bottom + 2
        self.t_bg.x, self.t_bg.y, self.t_bg.width, self.t_bg.height = tx, bottom, tw, y_top - bottom
        self.t_title.text = tr("Exercícios", "Exercises")
        self.t_title.x, self.t_title.y = tx + 12, y_top - 8
        cols = [0, 0.06, 0.36, 0.45, 0.55, 0.67, 0.79, 1.0]
        heads = ["", tr("Exercício", "Exercise"), tr("Séries", "Sets"), "Reps",
                 tr("Carga máx.", "Top load"), tr("Volume", "Volume"), tr("1RM est.", "e1RM"),
                 tr("Cumpr.", "Compl.")]
        inner = tw - 24
        hy = y_top - 36
        for lab, c, text in zip(self.t_head, cols, heads):
            lab.text = text
            lab.x, lab.y = tx + 12 + c * inner - (48 if c == 1.0 else 0), hy
        exs = d["exercises"]
        row_h = 26
        self.row_geo = []
        self.t_sel.opacity = 0
        for i, row in enumerate(self.t_rows):
            ry = hy - 20 - i * row_h
            if i < len(exs) and ry > bottom + 10:
                e = exs[i]
                dl = None
                if e["best_e1rm"] and e["prev_e1rm"]:
                    dl = e["best_e1rm"] - e["prev_e1rm"]
                timed = e["measure"] == "time"
                vals = [e["label"], wrap(e["name"], 0.29 * inner, 9, 1),
                        f"{e['done_sets']}/{e['planned_sets'] or e['done_sets']}",
                        (hms(e["done_reps"]) if timed else
                         f"{e['done_reps']}/{e['planned_reps'] or e['done_reps']}"),
                        _kg(e["max_load"]), _kg(e["volume"]) if not timed else "—",
                        (f"{e['best_e1rm']:.0f} kg" + (f" {dl:+.0f}" if dl and abs(dl) >= 0.5
                                                        else ""))
                        if e["best_e1rm"] else "—", _pct(e["compliance"])]
                for k, (lab, c, text) in enumerate(zip(row["cells"], cols, vals)):
                    lab.text = text
                    lab.x, lab.y = tx + 12 + c * inner - (48 if c == 1.0 else 0), ry
                    lab.color = _theme.rgba(P.text)
                    if k == 6 and dl:
                        lab.color = _theme.rgba(P.good if dl > 0 else P.bad)
                chip = row["chip"]
                cx = tx + 12 + inner - 52
                chip.x, chip.y, chip.width, chip.height = cx, ry - 9, 56, 18
                chip.color = _theme.mix(tone_color(e["tone"]), P.panel, 0.8)
                chip.opacity = 255 if e["tone"] else 0
                row["cells"][7].color = _theme.ink(tone_color(e["tone"]))
                if i == self.sel:
                    self.t_sel.x, self.t_sel.y = tx + 3, ry - row_h / 2 + 1
                    self.t_sel.width, self.t_sel.height = tw - 6, row_h - 2
                    self.t_sel.opacity = 255
                self.row_geo.append((i, ry - row_h / 2, ry + row_h / 2, tx, tx + tw))
            else:
                for lab in row["cells"]:
                    lab.text = ""
                row["chip"].opacity = 0
        self.empty.text = "" if exs else tr("Esta sessão não tem séries registadas",
                                            "This session has no logged sets")
        self.empty.x, self.empty.y = tx + tw / 2, (y_top + bottom) / 2
        # ---- detalhe do exercício escolhido
        dx = tx + tw + 16
        dw = w - 48 - dx
        self.d_out.x, self.d_out.y = dx - 1, bottom - 1
        self.d_out.width, self.d_out.height = dw + 2, y_top - bottom + 2
        self.d_bg.x, self.d_bg.y, self.d_bg.width, self.d_bg.height = dx, bottom, dw, y_top - bottom
        e = exs[self.sel] if exs and self.sel < len(exs) else None
        for lab in self.d_head:
            lab.text = ""
        for row in self.d_rows:
            for lab in row:
                lab.text = ""
        for r in self.bars_p + self.bars_d:
            r.width = r.height = 0
        for lab in self.bar_labels:
            lab.text = ""
        if e is None:
            self.d_title.text = self.d_sub.text = self.d_chart_title.text = self.d_hint.text = ""
            return
        self.d_title.text = wrap(f"{e['label']} · {e['name']}", dw - 24, 11, 1)
        self.d_title.x, self.d_title.y = dx + 12, y_top - 8
        sub = []
        if e["best_e1rm"]:
            sub.append(tr("1RM est. {v}", "e1RM {v}", v=_kg(e["best_e1rm"])))
            if e["prev_e1rm"]:
                sub.append(tr("antes {v}", "before {v}", v=_kg(e["prev_e1rm"])))
        if e["time_s"]:
            sub.append(tr("{t} no exercício", "{t} on exercise", t=hms(e["time_s"])))
        self.d_sub.text = " · ".join(sub)
        self.d_sub.x, self.d_sub.y = dx + 12, y_top - 26
        dcols = [0, 0.11, 0.40, 0.65, 0.77, 0.90]
        dheads = [tr("Série", "Set"), tr("Prescrito", "Planned"), tr("Feito", "Done"), "RPE",
                  tr("Tempo", "Time"), tr("FC", "HR")]
        dinner = dw - 24
        dhy = y_top - 48
        for lab, c, text in zip(self.d_head, dcols, dheads):
            lab.text = text
            lab.x, lab.y = dx + 12 + c * dinner, dhy
        unit = "s" if e["measure"] == "time" else ""
        chart_h = 70
        max_rows = int((dhy - 20 - (bottom + chart_h + 40)) // 20)
        for k, row in enumerate(self.d_rows):
            if k >= len(e["sets"]) or k >= max_rows:
                break
            s = e["sets"][k]
            ry = dhy - 20 - k * 20
            plan = (f"{s['plan_reps']}{unit}" if s["plan_reps"] else "—") + \
                (f" × {s['plan_load']:g}" if s["plan_load"] else "") + \
                (f" @{s['plan_rpe']:g}" if s["plan_rpe"] else "")
            done = ((f"{s['reps']}{unit}" + (f" × {s['load']:g}" if s["load"] else ""))
                    if s["reps"] is not None else tr("por fazer", "not done"))
            vals = [str(s["set_no"]), plan, done, f"{s['rpe']:g}" if s["rpe"] else "—",
                    hms(s["dur_s"]) if s["dur_s"] else "—",
                    f"{s['avg_hr']:.0f}" if s["avg_hr"] else "—"]
            for lab, c, text in zip(row, dcols, vals):
                lab.text = text
                lab.x, lab.y = dx + 12 + c * dinner, ry
                lab.color = _theme.rgba(P.text if s["reps"] is not None or c < 0.4 else P.faint)
            if s["reps"] is not None and s["plan_reps"]:
                short = (s["reps"] or 0) < s["plan_reps"] or (
                    s["plan_load"] and (s["load"] or 0) < s["plan_load"])
                row[2].color = _theme.rgba(P.warn if short else P.good)
        # gráfico: carga (ou reps) prescrita e feita, por série
        self.d_chart_title.text = tr("Carga por série: prescrita (claro) e feita",
                                     "Load per set: planned (light) and done") \
            if any(s["plan_load"] or s["load"] for s in e["sets"]) else \
            tr("Repetições por série: prescritas (claro) e feitas",
               "Reps per set: planned (light) and done")
        use_load = "Carga" in self.d_chart_title.text or "Load" in self.d_chart_title.text
        by = bottom + 30
        self.d_chart_title.x, self.d_chart_title.y = dx + 12, by + chart_h + 6
        vals_p = [(s["plan_load"] if use_load else s["plan_reps"]) or 0 for s in e["sets"]]
        vals_d = [(s["load"] if use_load else s["reps"]) or 0 for s in e["sets"]]
        peak = max(vals_p + vals_d + [1])
        ns = min(MAX_SETS, len(e["sets"]))
        slot = (dw - 24) / max(1, ns)
        bw = min(26, slot * 0.35)
        for k in range(ns):
            cx = dx + 12 + k * slot + slot / 2
            p, q = self.bars_p[k], self.bars_d[k]
            p.x, p.y, p.width, p.height = cx - bw - 1, by, bw, vals_p[k] / peak * chart_h
            q.x, q.y, q.width, q.height = cx + 1, by, bw, vals_d[k] / peak * chart_h
            q.color = P.accent
            self.bar_labels[k].text = str(k + 1)
            self.bar_labels[k].x, self.bar_labels[k].y = cx, by - 2
        self.d_hint.text = tr("Enter: histórico e evolução deste exercício",
                              "Enter: this exercise's history and progress")
        self.d_hint.x, self.d_hint.y = dx + 12, bottom + 8

    # ---------------------------------------------------------------- ações

    def open_history(self) -> None:
        d = self.data
        if not d or not d["exercises"]:
            return
        from velo.ui.exercise_stats_screens import ExerciseStatsScreen
        self.app.push(ExerciseStatsScreen(self.app, d["exercises"][self.sel]["exercise_id"]))

    def open_feedback(self) -> None:
        from velo.ui.feedback_screens import FeedbackScreen
        self.app.push(FeedbackScreen(self.app, "strength", self.sid))

    def open_sets(self) -> None:
        from velo.ui.sport_screens import StrengthSessionDetail
        self.app.push(StrengthSessionDetail(self.app, self.sid))

    def on_key(self, symbol: int, modifiers: int) -> bool:
        n = len(self.data["exercises"]) if self.data else 0
        if symbol in (key.UP, key.DOWN) and n:
            self.sel = (self.sel + (1 if symbol == key.DOWN else -1)) % n
            self._fill()
            return True
        if symbol in (key.ENTER, key.RETURN):
            self.open_history()
            return True
        if symbol == key.F:
            self.open_feedback()
            return True
        if symbol == key.S:
            self.open_sets()
            return True
        return super().on_key(symbol, modifiers)

    def on_mouse(self, x: int, y: int) -> bool:
        for i, y0, y1, x0, x1 in getattr(self, "row_geo", []):
            if x0 <= x <= x1 and y0 <= y <= y1:
                if i == self.sel:
                    self.open_history()
                else:
                    self.sel = i
                    self._fill()
                return True
        return super().on_mouse(x, y)

    def agent_data(self) -> dict:
        d = self.data or {}
        return {"cumprimento": d.get("compliance"), "volume": d.get("volume"),
                "exercicios": [{k: e[k] for k in ("label", "name", "done_sets", "planned_sets",
                                                  "done_reps", "planned_reps", "volume",
                                                  "best_e1rm", "prev_e1rm", "compliance")}
                               for e in d.get("exercises", [])]}

    def draw(self) -> None:
        self.batch.draw()
        self.chrome.draw()
        if self.back_button is not None:
            self.back_button.draw()
