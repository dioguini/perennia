"""«Carga e prontidão»: fitness, fadiga e carga diária; a forma com as faixas
(fresco, neutro, ótimo, risco); e a prontidão dos check-ins com o «ramp»
(quanto o fitness subiu numa semana). Todos os desportos juntos.

←/→ muda o período (30, 60, 90, 180 ou 365 dias).
"""
from __future__ import annotations

from datetime import date, timedelta

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import stats
from velo.core.i18n import tr
from velo.gfx import theme as _theme
from velo.gfx.compat import label as make_label
from velo.gfx.compat import line as make_line
from velo.ui.app import Screen
from velo.ui.widgets import Item

RANGES = (30, 60, 90, 180, 365)
FIT_C, FAT_C, FORM_C = (28, 132, 214), (214, 54, 128), (206, 146, 20)
LOAD_C, RAMP_C, READY_C = (196, 200, 208), (150, 206, 160), (16, 104, 196)
# faixas da forma (como no intervals.icu)
BANDS = ((5, 25, (214, 232, 248), ("Fresco", "Fresh")),
         (-10, 5, (232, 234, 238), ("Neutro", "Grey zone")),
         (-30, -10, (214, 238, 216), ("Ótimo", "Optimal")),
         (-60, -30, (248, 220, 218), ("Risco", "High risk")))
MAX_DAYS = 365


def form_band(tsb: float) -> str:
    for lo, hi, _c, names in BANDS:
        if lo <= tsb < hi:
            return tr(*names)
    return tr("Transição", "Transition") if tsb >= 25 else tr("Risco", "High risk")


def readiness_series(db, days: int, today: date) -> dict:
    """{dia: 0–100} dos check-ins (HRV4Training: pontos de recuperação)."""
    try:
        from velo.core import health
        m = health.metric_by_key(db, "hrv_score")
        if m is None:
            return {}
        vals = {d: v for d, v in health.series(db, m["id"], days, today) if v is not None}
    except Exception:
        return {}
    if vals and max(vals.values()) <= 10.5:            # escala de 0 a 10 → 0 a 100
        vals = {d: v * 10 for d, v in vals.items()}
    return vals


class LoadReadinessScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.days = int(app.db.get("load_days", 60))
        if self.days not in RANGES:
            self.days = 60
        self.list.y = -2000
        self._build()
        self._load()

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        dim = _theme.rgba(P.dim)
        self.card_out = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b)
        self.card = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b)
        self.note = make_label("", font_size=10, color=dim, anchor_y="top", batch=b)
        self.kpis = [make_label("", font_size=11, bold=True, anchor_y="top", batch=b)
                     for _ in range(5)]
        self.bands = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=c, batch=b)
                      for _lo, _hi, c, _n in BANDS]
        self.band_labels = [make_label("", font_size=8, color=dim, anchor_x="right",
                                       anchor_y="center", batch=b) for _ in BANDS]
        self.panels = []
        for _ in range(3):
            self.panels.append({
                "title": make_label("", font_size=9, bold=True, anchor_y="bottom", batch=b),
                "grid": [pyglet.shapes.Rectangle(0, 0, 0, 1, color=P.grid, batch=b)
                         for _ in range(4)],
                "yl": [make_label("", font_size=8, color=dim, anchor_x="right",
                                  anchor_y="center", batch=b) for _ in range(4)],
                "yr": [make_label("", font_size=8, color=dim, anchor_y="center", batch=b)
                       for _ in range(4)]})
        self.fit_fill = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=(214, 230, 246), batch=b)
                         for _ in range(MAX_DAYS)]
        self.load_bars = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=LOAD_C, batch=b)
                          for _ in range(MAX_DAYS)]
        self.ramp_bars = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=RAMP_C, batch=b)
                          for _ in range(MAX_DAYS)]
        mk = lambda c: [make_line(0, 0, 0, 0, thickness=2, color=c, batch=b)  # noqa: E731
                        for _ in range(MAX_DAYS)]
        self.fit_l, self.fat_l, self.form_l, self.ready_l = mk(FIT_C), mk(FAT_C), mk(FORM_C), \
            mk(READY_C)
        self.ready_dots = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=READY_C, batch=b)
                           for _ in range(MAX_DAYS)]
        self.xl = [make_label("", font_size=8, color=dim, anchor_x="center", anchor_y="top",
                              batch=b) for _ in range(9)]
        self.zero = pyglet.shapes.Rectangle(0, 0, 0, 1, color=P.dim, batch=b)

    # ---------------------------------------------------------------- dados

    def _load(self) -> None:
        today = date.today()
        self.today = today
        fit = stats.fitness(self.app.db, self.days + 7, today=today)
        self.series = fit[-self.days:] if fit else []
        by = {f["date"]: f for f in fit}
        self.ramp = [(f["ctl"] - by[f["date"] - timedelta(days=7)]["ctl"])
                     if (f["date"] - timedelta(days=7)) in by else 0.0 for f in self.series]
        self.ready = readiness_series(self.app.db, self.days, today)
        self._layout()

    def enter(self) -> None:
        self._load()
        n = sum(1 for f in self.series if f["load"] > 0)
        first = self.series[0]["date"] if self.series else self.today
        self.chrome.set(tr("Carga e prontidão", "Load and readiness"),
                        tr("Todos os desportos · {d} dias", "All sports · {d} days", d=self.days),
                        tr("←/→ período · Esc voltar", "←/→ period · Esc back"))
        self.note.text = tr("Últimos {d} dias ({a} a {b}) · {n} dias com treino.",
                            "Last {d} days ({a} to {b}) · {n} training days.", d=self.days,
                            a=first.strftime("%d/%m"), b=self.today.strftime("%d/%m"), n=n)
        self.list.set_items([Item(tr("Período", "Period"), value=f"{self.days}",
                                  data="range")])

    # --------------------------------------------------------------- desenho

    def _layout(self) -> None:
        P = _theme.P
        w, h = self.app.window.width, self.app.window.height
        x0, x1 = 48, w - 48
        top, bottom = h - 116, 62
        self.card_out.x, self.card_out.y = x0 - 1, bottom - 1
        self.card_out.width, self.card_out.height = x1 - x0 + 2, top - bottom + 2
        self.card.x, self.card.y, self.card.width, self.card.height = x0, bottom, x1 - x0, \
            top - bottom
        self.note.x, self.note.y = x0 + 14, top - 10
        cur = self.series[-1] if self.series else None
        ready_now = None
        for k in range(4):                    # o check-in mais recente (até 3 dias)
            ready_now = self.ready.get(self.today - timedelta(days=k)) if self.ready else None
            if ready_now is not None:
                break
        kp = [(tr("Fitness {v}", "Fitness {v}", v=f"{cur['ctl']:.0f}") if cur else "", FIT_C),
              (tr("Fadiga {v}", "Fatigue {v}", v=f"{cur['atl']:.1f}") if cur else "", FAT_C),
              (tr("Forma {v} ({b})", "Form {v} ({b})", v=f"{cur['tsb']:+.1f}",
                  b=form_band(cur["tsb"])) if cur else "", FORM_C),
              (f"Ramp {self.ramp[-1]:.1f}" if self.ramp else "", P.text),
              (tr("Prontidão {v}", "Readiness {v}", v=f"{ready_now:.0f}")
               if ready_now is not None else tr("Prontidão —", "Readiness —"), P.text)]
        kx = x0 + 14
        for lab, (text, col) in zip(self.kpis, kp):
            lab.text = text
            lab.color = _theme.ink(col) if col in (FIT_C, FAT_C, FORM_C) else _theme.rgba(col)
            lab.x, lab.y = kx, top - 30
            kx += len(text) * 7.4 + 22
        inner_top, inner_bottom = top - 62, bottom + 22
        span = inner_top - inner_bottom
        hs = (span * 0.46, span * 0.24, span * 0.24)
        gap = (span - sum(hs)) / 2
        lx, rx = x0 + 52, x1 - 52
        y = inner_top
        rects = []
        for hh in hs:
            rects.append((lx, y - hh, rx - lx, hh))
            y -= hh + gap
        self.rects = rects
        n = len(self.series)
        if n < 2:
            return
        dx = (rx - lx) / (n - 1)
        xs = [lx + i * dx for i in range(n)]
        # ---- 1: fitness, fadiga, carga diária
        x, yb, wd, ht = rects[0]
        p = self.panels[0]
        p["title"].text = tr("■ Fadiga   ■ Fitness   ■ Carga diária",
                             "■ Fatigue   ■ Fitness   ■ Daily load")
        p["title"].color = _theme.rgba(P.dim)
        p["title"].x, p["title"].y = x, yb + ht + 3
        top_f = max(10.0, max(max(f["ctl"], f["atl"]) for f in self.series) * 1.1)
        top_l = max(10.0, max(f["load"] for f in self.series) * 1.1)
        self._axes(p, rects[0], 0, top_f, 0, top_l)
        bw = max(1.0, dx * 0.7)
        for i, bar in enumerate(self.load_bars):
            if i < n and self.series[i]["load"] > 0:
                bar.x, bar.y = xs[i] - bw / 2, yb
                bar.width, bar.height = bw, self.series[i]["load"] / top_l * ht
                bar.opacity = 255
            else:
                bar.width = bar.height = 0
        for i, r in enumerate(self.fit_fill):
            if i < n:
                r.x, r.y, r.width = xs[i] - dx / 2, yb, dx + 0.5
                r.height = self.series[i]["ctl"] / top_f * ht
                r.opacity = 150
            else:
                r.width = r.height = 0
        self._poly(self.fit_l, [(xs[i], yb + self.series[i]["ctl"] / top_f * ht)
                                for i in range(n)])
        self._poly(self.fat_l, [(xs[i], yb + self.series[i]["atl"] / top_f * ht)
                                for i in range(n)])
        # ---- 2: forma com as faixas
        x, yb, wd, ht = rects[1]
        p = self.panels[1]
        p["title"].text = tr("■ Forma (fitness − fadiga)", "■ Form (fitness − fatigue)")
        p["title"].color = _theme.ink(FORM_C)
        p["title"].x, p["title"].y = x, yb + ht + 3
        tsbs = [f["tsb"] for f in self.series]
        lo, hi = min(-35.0, min(tsbs) - 5), max(20.0, max(tsbs) + 5)

        def fy(v: float) -> float:
            return yb + (max(lo, min(hi, v)) - lo) / (hi - lo) * ht

        for (blo, bhi, _c, names), r, lab in zip(BANDS, self.bands, self.band_labels):
            a, b_ = fy(max(blo, lo)), fy(min(bhi, hi))
            r.x, r.y, r.width, r.height = x, a, wd, max(0.0, b_ - a)
            lab.text = tr(*names)
            lab.x, lab.y = x + wd - 4, (a + b_) / 2
        self._axes(p, rects[1], lo, hi, None, None)
        self.zero.x, self.zero.y, self.zero.width = x, fy(0), wd
        self._poly(self.form_l, [(xs[i], fy(tsbs[i])) for i in range(n)])
        # ---- 3: prontidão e ramp
        x, yb, wd, ht = rects[2]
        p = self.panels[2]
        p["title"].text = tr("■ Prontidão (check-in)   ■ Ramp", "■ Readiness (check-in)   ■ Ramp")
        p["title"].color = _theme.rgba(P.dim)
        p["title"].x, p["title"].y = x, yb + ht + 3
        rmax = max(3.0, max(abs(v) for v in self.ramp) * 1.2) if self.ramp else 3.0
        self._axes(p, rects[2], 0, 100, -rmax, rmax)
        mid = yb + ht / 2
        for i, bar in enumerate(self.ramp_bars):
            if i < n and abs(self.ramp[i]) > 0.05:
                hgt = self.ramp[i] / rmax * ht / 2
                bar.x, bar.width = xs[i] - bw / 2, bw
                bar.y, bar.height = (mid, hgt) if hgt >= 0 else (mid + hgt, -hgt)
                bar.opacity = 220
            else:
                bar.width = bar.height = 0
        pts = [(xs[i], yb + self.ready[f["date"]] / 100 * ht)
               for i, f in enumerate(self.series) if f["date"] in self.ready]
        self._poly(self.ready_l, pts)
        for i, d in enumerate(self.ready_dots):
            if i < len(pts):
                d.x, d.y, d.width, d.height = pts[i][0] - 3, pts[i][1] - 3, 6, 6
                d.opacity = 255
            else:
                d.width = d.height = 0
        # datas
        for k, lab in enumerate(self.xl):
            i = int(round(k * (n - 1) / (len(self.xl) - 1)))
            lab.text = self.series[i]["date"].strftime("%d/%m")
            lab.x, lab.y = xs[i], rects[2][1] - 4

    def _axes(self, p: dict, rect, lo, hi, rlo, rhi) -> None:
        x, yb, wd, ht = rect
        for k, (g, yl, yr) in enumerate(zip(p["grid"], p["yl"], p["yr"])):
            frac = k / 3
            g.x, g.y, g.width = x, yb + frac * ht, wd
            yl.text = f"{lo + (hi - lo) * frac:.0f}"
            yl.x, yl.y = x - 6, yb + frac * ht
            yr.text = f"{rlo + (rhi - rlo) * frac:.0f}" if rlo is not None else ""
            yr.x, yr.y = x + wd + 6, yb + frac * ht

    @staticmethod
    def _poly(pool: list, pts: list) -> None:
        for i, ln in enumerate(pool):
            if i + 1 < len(pts):
                (ln.x, ln.y), (ln.x2, ln.y2) = pts[i], pts[i + 1]
                ln.opacity = 255
            else:
                ln.x = ln.x2 = ln.y = ln.y2 = 0
                ln.opacity = 0

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -2000
        self._layout()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol in (key.LEFT, key.RIGHT):
            i = RANGES.index(self.days)
            self.days = RANGES[max(0, min(len(RANGES) - 1, i + (1 if symbol == key.RIGHT
                                                                else -1)))]
            self.app.db.set("load_days", self.days)
            self.enter()
            return True
        return super().on_key(symbol, modifiers)

    def agent_data(self) -> dict:
        cur = self.series[-1] if self.series else {}
        return {"dias": self.days, "fitness": cur.get("ctl"), "fadiga": cur.get("atl"),
                "forma": cur.get("tsb"), "ramp": self.ramp[-1] if self.ramp else None}

    def draw(self) -> None:
        self.chrome.draw()
        self.batch.draw()
        if self.back_button is not None:
            self.back_button.draw()
