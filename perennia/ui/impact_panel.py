"""O painel «Impacto do treino» (ronda 30): o IF e a TSS, o efeito em cada sistema do desporto
(Resistência, Tempo, Limiar, VO2máx, Anaeróbio, Sprint, de 0 a 5, com uma barra na cor da zona),
a característica do perfil que o treino puxa (★ o ponto fraco) e o impacto no índice de
longevidade. O mesmo painel aparece no construtor (ao vivo) e na ficha do treino.

Os números vêm de `perennia.core.workout_impact.planned`; isto só desenha.
"""
from __future__ import annotations

import pyglet

from perennia.core import intensity as it
from perennia.core import longevity as lg
from perennia.core import workout_impact as wi
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.gfx.compat import label as make_label
from perennia.ui.widgets import ACCENT, DIM, GRID, PANEL, TEXT, fit_text

SYSTEM_ZONE = {"endurance": 2, "tempo": 3, "threshold": 4, "vo2max": 5, "anaerobic": 6,
               "sprint": 7}
PANEL_W = 340                  # a largura de referência do painel
PANEL_H = 200                  # a altura que precisa para ficar folgado


def texts_for(imp: wi.Impact | None, links: dict | None) -> dict:
    """Os textos do painel: {"if", "sub", "rows": {sistema: texto}, "longevity", "longevity2",
    "note", "weak", "focus"} (vazio sem impacto)."""
    if imp is None:
        return {}
    links = links or {}
    rows = {}
    for sname in wi.SYSTEMS:
        v = imp.systems.get(sname, 0.0)
        rows[sname] = f"{v:.1f} · {wi.effect_level(v)}"
    d = (imp.longevity or {}).get("deltas") or {}
    top = (imp.longevity or {}).get("top") or []
    if d:
        lon = tr("Longevidade {v} num mês", "Longevity {v} in a month",
                 v=lg.fmt_delta(d.get("1m", 0.0)))
        bits = [tr("1 sem {v}", "1 wk {v}", v=lg.fmt_delta(d.get("1w", 0.0))),
                tr("3 meses {v}", "3 mo {v}", v=lg.fmt_delta(d.get("3m", 0.0)))]
        if top:
            bits.append(tr("mais em ", "mostly ") + ", ".join(lg.axis_label(a)
                                                              for a, _v in top[:2]))
        lon2 = " · ".join(bits)
    else:
        lon, lon2 = tr("Longevidade: sem efeito", "Longevity: no effect"), ""
    focus = imp.focus
    note = ""
    weak = [sn for sn, ln in links.items() if ln.get("weakest")]
    if weak:
        ln = links[weak[0]]
        note = tr("★ puxa o teu ponto fraco: {n} ({l})", "★ works your weakest point: {n} ({l})",
                  n=ln["name"], l=ln["level"])
    elif focus and focus in links:
        ln = links[focus]
        note = tr("Perfil: {n} — {l}", "Profile: {n} — {l}", n=ln["name"], l=ln["level"])
    elif focus:
        note = tr("Foco: {s}", "Focus: {s}", s=wi.system_name(focus))
    sub = f"TSS {imp.tss:.0f} · {hms(imp.seconds)}" if imp.tss is not None else ""
    return {"if": f"IF {wi.fmt_if(imp.if_)}", "sub": sub, "rows": rows, "longevity": lon,
            "longevity2": lon2, "note": note, "weak": weak, "focus": focus}


class ImpactPanel:
    """O painel, num retângulo (`layout`) com o impacto que lhe derem (`set`). Pode desenhar
    num batch alheio (o do construtor) ou no seu (`draw`)."""

    def __init__(self, batch=None, background=PANEL, title: bool = False):
        self.own_batch = batch is None
        b = self.batch = batch if batch is not None else pyglet.graphics.Batch()
        self.bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=background, batch=b)
        self.title = make_label("", font_size=11, bold=True, color=DIM, anchor_y="center",
                                batch=b)
        self.show_title = title
        self.if_label = make_label("", font_size=20, bold=True, color=ACCENT,
                                   anchor_y="center", batch=b)
        self.sub = make_label("", font_size=10, color=DIM, anchor_x="right",
                              anchor_y="center", batch=b)
        self.rows = []
        for sname in wi.SYSTEMS:
            name = make_label(wi.system_name(sname), font_size=9, bold=True, color=TEXT,
                              anchor_y="center", batch=b)
            track = pyglet.shapes.Rectangle(0, 0, 10, 8, color=GRID, batch=b)
            fill = pyglet.shapes.Rectangle(0, 0, 0, 8, color=it.ZONE_COLORS[
                SYSTEM_ZONE[sname] - 1], batch=b)
            val = make_label("", font_size=9, color=TEXT, anchor_y="center", batch=b)
            self.rows.append((sname, name, track, fill, val))
        self.lon = make_label("", font_size=10, bold=True, color=TEXT, anchor_y="center",
                              batch=b)
        self.lon2 = make_label("", font_size=9, color=DIM, anchor_y="center", batch=b)
        self.note = make_label("", font_size=9, color=DIM, anchor_y="center", batch=b)
        self.box: tuple | None = None
        self.impact: wi.Impact | None = None
        self.links: dict = {}

    # ---------------------------------------------------------------- dados

    def set(self, imp: wi.Impact | None, links: dict | None = None) -> None:
        self.impact, self.links = imp, links or {}
        self._fill()

    def texts(self) -> dict:
        return texts_for(self.impact, self.links)

    @property
    def visible(self) -> bool:
        return self.box is not None and self.impact is not None

    # ---------------------------------------------------------------- medidas

    def layout(self, x0: float, x1: float, y0: float, y1: float) -> None:
        """O retângulo do painel; com `x1 <= x0` o painel esconde-se."""
        show = x1 > x0 and y1 > y0
        self.box = (x0, x1, y0, y1) if show else None
        self.bg.x, self.bg.y = x0, y0
        self.bg.width, self.bg.height = max(0, x1 - x0), max(0, y1 - y0)
        pad = 12
        head = 20 if self.show_title else 0
        self.title.x, self.title.y = x0 + pad, y1 - 14
        self.if_label.x, self.if_label.y = x0 + pad, y1 - 22 - head
        self.sub.x, self.sub.y = x1 - pad, y1 - 22 - head
        rows_top = y1 - 50 - head
        bottom_lines = 3 * 15 + 4
        row_h = max(13.0, min(20.0, (rows_top - (y0 + bottom_lines)) / len(self.rows)))
        for k, (_s, name, track, fill, val) in enumerate(self.rows):
            ry = rows_top - k * row_h
            name.x, name.y = x0 + pad, ry
            track.x, track.y, track.width, track.height = x0 + pad + 96, ry - 4, 96, 8
            fill.x, fill.y, fill.height = track.x, track.y, 8
            val.x, val.y = track.x + track.width + 8, ry
        base = rows_top - len(self.rows) * row_h - 2
        self.lon.x, self.lon.y = x0 + pad, base
        self.lon2.x, self.lon2.y = x0 + pad, base - 15
        self.note.x, self.note.y = x0 + pad, base - 30
        self._fill()

    def _fill(self) -> None:
        on = self.visible
        self.bg.opacity = 255 if on else 0
        for _s, _n, track, fill, _v in self.rows:
            track.opacity = fill.opacity = 255 if on else 0
        if not on:
            for lab in (self.title, self.if_label, self.sub, self.lon, self.lon2, self.note):
                lab.text = ""
            for _s, name, _t, _f, val in self.rows:
                name.text = val.text = ""
            return
        x0, x1, _y0, _y1 = self.box
        tx = self.texts()
        imp = self.impact
        room = x1 - x0 - 24
        self.title.text = tr("Impacto do treino", "Workout impact") if self.show_title else ""
        self.if_label.text = tx["if"]
        self.sub.text = fit_text(tx["sub"], room - 110, 10)
        for sname, name, track, fill, val in self.rows:
            v = imp.systems.get(sname, 0.0)
            star = "★ " if sname in tx["weak"] else ""
            name.text = star + wi.system_name(sname)
            name.color = ACCENT if (star or sname == tx["focus"]) else TEXT
            fill.width = track.width * max(0.0, min(1.0, v / wi.EFFECT_MAX))
            val.text = fit_text(tx["rows"][sname], x1 - val.x - 10, 9)
        self.lon.text = fit_text(tx["longevity"], room, 10, bold=True)
        self.lon2.text = fit_text(tx["longevity2"], room, 9)
        self.note.text = fit_text(tx["note"], room, 9)

    def draw(self) -> None:
        if self.own_batch and self.visible:
            self.batch.draw()
