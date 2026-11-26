"""O radar do que uma sessão treinou e o seu efeito no índice de longevidade, ao lado do
resto das páginas de resumo e da análise de cada sessão (todos os desportos).

Quando a sessão foi feita com um **treino por potência** (ciclismo e remo), aparece também o
painel **«Treino: feito vs plano»** (ronda 30): o IF feito contra o IF alvo do treino, a TSS, o
efeito em cada sistema do desporto (Resistência, Tempo, Limiar, VO2máx, Anaeróbio, Sprint) com
a barra do plano por baixo da barra do que se fez, e o impacto no índice de longevidade (plano e
feito). O radar sobrepõe o polígono do plano (a laranja) ao do que a sessão treinou.
Ver `perennia.core.workout_impact`.
"""
from __future__ import annotations

import pyglet

from perennia.core import intensity as it
from perennia.core import longevity as lg
from perennia.core import workout_impact as wi
from perennia.core.i18n import tr
from perennia.gfx.compat import label as make_label
from perennia.ui.radar import OVERLAY, RadarChart
from perennia.ui.widgets import ACCENT, BAD, DIM, GOOD, GRID, PANEL, TEXT, Item, fit_text

SYSTEM_ZONE = {"endurance": 2, "tempo": 3, "threshold": 4, "vo2max": 5, "anaerobic": 6,
               "sprint": 7}
VERDICT_COLOR = {"on": GOOD, "above": BAD, "below": (224, 150, 40), "none": DIM}


class ImpactPanel:
    """O painel «Treino: feito vs plano»: IF, TSS, as barras sobrepostas de cada sistema e a
    longevidade. Desenha-se num retângulo (`layout`)."""

    def __init__(self):
        b = self.batch = pyglet.graphics.Batch()
        self.bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
        self.title = make_label(tr("Treino: feito vs plano", "Workout: done vs plan"),
                                font_size=12, bold=True, color=ACCENT, anchor_y="center",
                                batch=b)
        self.if_big = make_label("", font_size=18, bold=True, color=TEXT, anchor_y="center",
                                 batch=b)
        self.if_note = make_label("", font_size=10, bold=True, color=DIM, anchor_y="center",
                                  batch=b)
        self.tss = make_label("", font_size=10, color=DIM, anchor_y="center", batch=b)
        self.legend = make_label("", font_size=9, color=DIM, anchor_x="right",
                                 anchor_y="center", batch=b)
        self.rows = []
        for s in wi.SYSTEMS:
            name = make_label(wi.system_name(s), font_size=9, bold=True, color=TEXT,
                              anchor_y="center", batch=b)
            track = pyglet.shapes.Rectangle(0, 0, 10, 12, color=GRID, batch=b)
            plan = pyglet.shapes.Rectangle(0, 0, 0, 12, color=OVERLAY, batch=b)
            plan.opacity = 110
            done = pyglet.shapes.Rectangle(0, 0, 0, 6, color=it.ZONE_COLORS[
                SYSTEM_ZONE[s] - 1], batch=b)
            mark = pyglet.shapes.Rectangle(0, 0, 2, 14, color=OVERLAY, batch=b)
            val = make_label("", font_size=9, color=TEXT, anchor_y="center", batch=b)
            self.rows.append((s, name, track, plan, done, mark, val))
        self.lon = make_label("", font_size=10, bold=True, color=TEXT, anchor_y="center",
                              batch=b)
        self.lon2 = make_label("", font_size=9, color=DIM, anchor_y="center", batch=b)
        self.box = (0.0, 0.0, 0.0, 0.0)
        self.data: dict | None = None

    def layout(self, x: float, y: float, w: float, h: float) -> None:
        self.box = (x, y, w, h)
        self._place()

    def set(self, cmp: dict | None) -> None:
        self.data = cmp
        self._place()

    def texts(self) -> dict:
        """Os textos (também para os testes)."""
        c = self.data
        if not c:
            return {}
        comp = c["compare"]
        plan_if, done_if = comp["if"]
        pct = comp["if_pct"]
        if_big = f"IF {wi.fmt_if(done_if)}"
        short = {"on": tr("no alvo", "on target"), "above": tr("acima", "above"),
                 "below": tr("abaixo", "below")}.get(comp["if_key"], "")
        if_note = tr("alvo {t}", "target {t}", t=wi.fmt_if(plan_if)) \
            + (f" · {pct:.0f} %" if pct else "") + (f" · {short}" if short else "")
        pt, dt = comp["tss"]
        tss = tr("TSS {d} feito · {p} plano", "TSS {d} done · {p} plan",
                 d="—" if dt is None else f"{dt:.0f}", p="—" if pt is None else f"{pt:.0f}")
        rows = {s: f"{d:.1f} / {p:.1f}" for s, (p, d) in comp["systems"].items()}
        lp, ld = comp["longevity"].get("1m", (None, None))
        lon = tr("Longevidade (1 mês) {d} feito · {p} plano",
                 "Longevity (1 month) {d} done · {p} plan",
                 d="—" if ld is None else lg.fmt_delta(ld), p="—" if lp is None else
                 lg.fmt_delta(lp))
        w1p, w1d = comp["longevity"].get("1w", (None, None))
        m3p, m3d = comp["longevity"].get("3m", (None, None))
        bits = []
        if w1d is not None and w1p is not None:
            bits.append(tr("1 sem {d} / {p}", "1 wk {d} / {p}", d=lg.fmt_delta(w1d),
                           p=lg.fmt_delta(w1p)))
        if m3d is not None and m3p is not None:
            bits.append(tr("3 meses {d} / {p}", "3 mo {d} / {p}", d=lg.fmt_delta(m3d),
                           p=lg.fmt_delta(m3p)))
        return {"if": if_big, "if_note": if_note, "if_key": comp["if_key"], "tss": tss,
                "rows": rows, "longevity": lon, "longevity2": " · ".join(bits)}

    def _place(self) -> None:
        x, y, w, h = self.box
        show = bool(self.data) and w > 40 and h > 40
        self.bg.x, self.bg.y, self.bg.width, self.bg.height = x, y, max(0, w), max(0, h)
        self.bg.opacity = 255 if show else 0
        labels = (self.title, self.if_big, self.if_note, self.tss, self.legend, self.lon,
                  self.lon2)
        if not show:
            for lab in labels:
                lab.text = ""
            self.title.text = ""
            for _s, name, track, plan, done, mark, val in self.rows:
                name.text = val.text = ""
                for sh in (track, plan, done, mark):
                    sh.opacity = 0
            return
        tx = self.texts()
        pad = 12
        top = y + h
        room = w - 2 * pad
        self.title.text = tr("Treino: feito vs plano", "Workout: done vs plan")
        self.title.x, self.title.y = x + pad, top - 16
        self.legend.text = tr("barra = feito · laranja = plano", "bar = done · orange = plan")
        self.legend.x, self.legend.y = x + w - pad, y + 10
        self.if_big.text = tx["if"]
        self.if_big.x, self.if_big.y = x + pad, top - 42
        self.if_note.text = fit_text(tx["if_note"], room - 110, 10, bold=True)
        self.if_note.color = VERDICT_COLOR.get(tx["if_key"], DIM)
        self.if_note.x, self.if_note.y = x + pad + 108, top - 42
        self.tss.text = fit_text(tx["tss"], room, 10)
        self.tss.x, self.tss.y = x + pad, top - 62
        rows_top = top - 82
        bottom_room = 50
        row_h = max(14.0, min(24.0, (rows_top - (y + bottom_room)) / len(self.rows)))
        bar_x = x + pad + 92
        bar_w = max(40.0, w - 2 * pad - 92 - 70)
        for k, (s, name, track, plan, done, mark, val) in enumerate(self.rows):
            ry = rows_top - k * row_h
            p, d = self.data["compare"]["systems"].get(s, (0.0, 0.0))
            name.text = wi.system_name(s)
            name.x, name.y = x + pad, ry
            track.x, track.y, track.width, track.height = bar_x, ry - 6, bar_w, 12
            plan.x, plan.y, plan.height = bar_x, ry - 6, 12
            plan.width = bar_w * max(0.0, min(1.0, p / wi.EFFECT_MAX))
            done.x, done.y, done.height = bar_x, ry - 3, 6
            done.width = bar_w * max(0.0, min(1.0, d / wi.EFFECT_MAX))
            mark.x, mark.y = bar_x + plan.width - 1, ry - 7
            track.opacity, plan.opacity, done.opacity = 255, 110, 255
            mark.opacity = 255 if p > 0.05 else 0
            val.text = tx["rows"][s]
            val.x, val.y = bar_x + bar_w + 8, ry
            name.color = ACCENT if s == self.data["actual"].focus else TEXT
        base = rows_top - len(self.rows) * row_h - 2
        self.lon.text = fit_text(tx["longevity"], room, 10, bold=True)
        self.lon.x, self.lon.y = x + pad, base
        self.lon2.text = fit_text(tx["longevity2"], room, 9)
        self.lon2.x, self.lon2.y = x + pad, base - 15

    def draw(self) -> None:
        if self.data:
            self.batch.draw()


class RadarSide:
    """O radar do que uma sessão treinou, ao lado do resto, e o seu efeito no índice de
    longevidade. Para as páginas de resumo e a análise de cada sessão (todos os desportos).
    Usa-se à esquerda do `Screen`; `radar_attach(desporto, id)` devolve as linhas a juntar.
    Numa sessão feita com um treino por potência, junta também o painel «feito vs plano»."""

    RADAR_BIG = False            # grande, a meio-direita (a análise); senão, na coluna da direita
    radar_visible = True
    _radar: RadarChart | None = None
    _radar_rows: list | None = None
    _impact_panel: ImpactPanel | None = None
    _cmp: dict | None = None
    IMPACT_H = 250               # a altura do painel «feito vs plano»

    def _radar_on(self) -> bool:
        return self._radar is not None and self.radar_visible

    def _relayout_list(self) -> None:
        """A lista muda de largura quando o radar aparece ou desaparece."""
        w, h = self.app.window.width, self.app.window.height
        super().on_resize(w, h)           # só a base (Screen): não volta a pedir o conteúdo

    def _list_width(self, w: int) -> int:
        if self._radar_on() and not self.HAS_BOARD:
            return w - 96 - int(w * 0.45)
        return super()._list_width(w)

    def radar_attach(self, sport: str, sid: str | None) -> list[Item]:
        if not sid:
            return []
        if self._radar_rows is not None:
            return list(self._radar_rows)
        db = self.app.db
        imp = lg.session_impact(db, sport, str(sid))
        mins = imp.get("mins") or {}
        if self._radar is None:
            self._radar = RadarChart()
        share = lg.shares(mins)
        self._radar.caption.text = tr("O que treinou", "What it trained")
        self._radar.set([(lg.axis_label(a), share.get(a, 0.0), f"{share.get(a, 0.0):.0f} %")
                         for a in lg.AXES],
                        empty=tr("Sem tempo em zonas", "No time in zones"))
        rows: list[Item] = []
        try:
            self._cmp = wi.for_session(db, sport, str(sid))
        except Exception:
            self._cmp = None
        if self._cmp:
            rows += self._compare_rows(self._cmp)
            plan_mins = (self._cmp["planned"].longevity or {}).get("mins") or {}
            pshare = lg.shares(plan_mins)
            self._radar.set_overlay([pshare.get(a, 0.0) for a in lg.AXES],
                                    tr("azul = feito · laranja = plano",
                                       "blue = done · orange = plan"))
            if self._impact_panel is None:
                self._impact_panel = ImpactPanel()
            self._impact_panel.set(self._cmp)
            if getattr(self, "board_panel", None) is not None:
                # o painel «feito vs plano» fica no lugar da classificação
                self._hidden_board = self.board_panel
                self.board_panel = None
        if mins:
            d = imp.get("deltas") or {}
            detail = lg.impact_text(imp)
            if self._cmp:
                pd = (self._cmp["planned"].longevity or {}).get("deltas") or {}
                if "1m" in pd:
                    detail = tr("plano {p} · ", "plan {p} · ", p=lg.fmt_delta(pd["1m"])) + detail
            rows.append(Item(tr("Longevidade", "Longevity"),
                             value=lg.fmt_delta(d.get("1m", 0.0)),
                             detail=detail, enabled=False))
        self._radar_rows = rows
        self._relayout_list()
        self._radar_layout()
        return list(rows)

    def _compare_rows(self, cmp: dict) -> list[Item]:
        """As linhas da comparação: o IF (feito e alvo) e o foco do treino."""
        comp = cmp["compare"]
        plan_if, done_if = comp["if"]
        pct = comp["if_pct"]
        rows = [Item(tr("IF feito · alvo", "IF done · target"),
                     value=f"{wi.fmt_if(done_if)} · {wi.fmt_if(plan_if)}",
                     detail=comp["if_text"] + (f" · {pct:.0f} % do alvo" if pct else ""),
                     enabled=False, data=("impact_if", comp["if_key"]))]
        act, plan = cmp["actual"], cmp["planned"]
        f = plan.focus
        if f:
            p, d = comp["systems"][f]
            rows.append(Item(tr("Foco do treino", "Workout focus"),
                             value=f"{wi.system_name(f)} {d:.1f} / {p:.1f}",
                             detail=tr("feito / plano · {l}", "done / plan · {l}",
                                       l=wi.effect_level(d)), enabled=False))
        _ = act
        return rows

    def _radar_layout(self) -> None:
        if self._radar is None:
            return
        from perennia.ui.app import BOARD_W
        w, h = self.app.window.width, self.app.window.height
        panel = self._impact_panel if self._cmp else None
        if self.RADAR_BIG or not self.HAS_BOARD:      # sem classificação, o radar é grande
            x0, x1 = w * 0.55, w - 60
            top = h - 150
            if panel is not None:
                panel.layout(x0, top - self.IMPACT_H, x1 - x0, self.IMPACT_H)
                top -= self.IMPACT_H + 20
            room_h = top - 110
            r = max(50.0, min((x1 - x0) / 2 - 90, (room_h - 90) / 2))
            self._radar.layout((x0 + x1) / 2, 110 + room_h / 2 - 20, r)
        else:
            x0 = w - 48 - BOARD_W
            if panel is not None:
                panel.layout(x0, h - 124 - self.IMPACT_H, BOARD_W, self.IMPACT_H)
                top = h - 124 - self.IMPACT_H - 10
                r = max(50.0, min(100.0, (top - 120 - 80) / 2))
                self._radar.layout(w - 48 - BOARD_W / 2, 120 + (top - 120 - 70) / 2, r)
            else:
                self._radar.layout(w - 48 - BOARD_W / 2, 230, 100)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._radar_layout()

    def draw(self) -> None:
        super().draw()
        if self._radar_on():
            self._radar.draw()
            if self._cmp and self._impact_panel is not None:
                self._impact_panel.draw()
