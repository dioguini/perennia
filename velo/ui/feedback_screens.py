"""«Como correu esta sessão?» — o feedback no fim de cada sessão.

À esquerda, «Prescrito e realizado»: os blocos do treino (cor = zona) com a
potência (ou o ritmo) e a FC por cima, e por baixo a análise, que cruza o
objetivo do treino com o que disseste. À direita, o formulário: RPE, dores,
sensação geral, objetivo cumprido e comentário. Tudo opcional.

Teclado: ↑↓ linha · ←/→ valor (ou o número) · Backspace limpa · escrever no
comentário · Ctrl+S ou «Guardar e analisar» · Esc fecha sem guardar.
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import feedback as fbm
from velo.core import intensity as it
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx import theme as _theme
from velo.gfx.compat import label as make_label
from velo.gfx.compat import line as make_line
from velo.ui.app import Screen
from velo.ui.brief import sport_kind, wrap
from velo.ui.widgets import Item

ROWS = ("rpe", "pain", "feel", "goal", "comment", "save", "close")


def ask_enabled(db) -> bool:
    return bool(db.get("ask_feedback", True))


def maybe_ask(screen, kind: str, sid: str | None) -> None:
    """Chamado pelos ecrãs de resumo: abre o feedback uma vez por sessão."""
    if not sid or getattr(screen, "_feedback_asked", False):
        return
    screen._feedback_asked = True
    db = screen.app.db
    if not ask_enabled(db) or fbm.get(db, kind, sid) is not None:
        return
    screen.app.push(FeedbackScreen(screen.app, kind, sid))


def summary_item(app, kind: str, sid: str | None) -> Item | None:
    """A linha «Como correu esta sessão?» dos resumos e dos detalhes."""
    if not sid:
        return None
    got = fbm.get(app.db, kind, sid)
    return Item(tr("Como correu esta sessão?", "How did this session go?"),
                value=(got or {}).get("verdict", "") and "✓",
                detail=(got or {}).get("verdict") or tr("Dar feedback (RPE, dores, comentário)",
                                                        "Give feedback (RPE, pain, comment)"),
                action=lambda: app.push(FeedbackScreen(app, kind, sid)))


class FeedbackScreen(Screen):
    AGENT = False
    MAX_PTS = 240

    def __init__(self, app, kind: str, sid: str):
        self.kind, self.sid = kind, sid
        super().__init__(app)
        db = app.db
        self.sess = fbm.load_session(db, kind, sid)
        self.brief = fbm.prescribed(db, self.sess) if self.sess else None
        old = fbm.get(db, kind, sid) or {}
        self.v = {"rpe": old.get("rpe"), "pain": old.get("pain"), "feel": old.get("feel"),
                  "goal": old.get("goal_met"), "comment": old.get("comment") or ""}
        self.saved = bool(old)
        self.row = 0
        self._build()
        self._layout()
        self._refresh()

    # ------------------------------------------------------------ construção

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        self.band = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.header, batch=b)
        self.cards = [(pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                       pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b))
                      for _ in range(3)]
        lab = lambda size=11, bold=False, color=None, **kw: make_label(  # noqa: E731
            "", font_size=size, bold=bold, color=color or _theme.rgba(P.text), batch=b, **kw)
        dim = _theme.rgba(P.dim)
        self.h_chart = lab(13, True, anchor_y="top")
        self.h_chart_sub = lab(10, color=dim, anchor_y="top")
        self.h_form = lab(13, True, anchor_y="top")
        self.h_form_sub = lab(9, color=dim, anchor_y="top", multiline=True, width=300)
        self.h_an = lab(13, True, anchor_y="top")
        # gráfico
        self.chart_bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b)
        self.grid = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.grid, batch=b) for _ in range(5)]
        self.yl = [lab(8, color=dim, anchor_x="right", anchor_y="center") for _ in range(5)]
        self.yr = [lab(8, color=_theme.ink(P.hr_line), anchor_y="center") for _ in range(5)]
        self.xl = [lab(8, color=dim, anchor_x="center", anchor_y="top") for _ in range(7)]
        self.blocks = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=(200, 200, 200), batch=b)
                       for _ in range(200)]
        self.pow_lines = [make_line(0, 0, 0, 0, thickness=1.5, color=P.power_line, batch=b)
                          for _ in range(self.MAX_PTS)]
        self.hr_lines = [make_line(0, 0, 0, 0, thickness=1.5, color=P.hr_line, batch=b)
                         for _ in range(self.MAX_PTS)]
        self.legend = lab(9, color=dim, anchor_y="top")
        self.legend2 = lab(9, color=dim, anchor_x="right", anchor_y="top")
        self.empty = lab(11, color=dim, anchor_x="center", anchor_y="center")
        # análise
        self.chip_bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel2, batch=b)
        self.chip = lab(10, True, anchor_y="center")
        self.an_titles = [lab(10, True, anchor_y="top") for _ in range(5)]
        self.an_texts = [lab(10, anchor_y="top", multiline=True, width=300) for _ in range(5)]
        self.an_note = lab(9, color=dim, anchor_y="top")
        # formulário
        self.row_bar = pyglet.shapes.Rectangle(0, 0, 3, 10, color=P.accent, batch=b)
        self.row_titles = {k: lab(11, True, anchor_y="top") for k in ("rpe", "pain", "feel",
                                                                      "goal", "comment")}
        self.row_hints = {k: lab(8, color=dim, anchor_y="top") for k in ("rpe", "pain")}
        self.chips: dict[str, list] = {}
        for k, n in (("rpe", 10), ("pain", 11), ("feel", 5), ("goal", 3)):
            self.chips[k] = [(pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                              pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel2, batch=b),
                              lab(10, True, anchor_x="center", anchor_y="center"))
                             for _ in range(n)]
        self.box_out = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b)
        self.box = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b)
        self.box_text = lab(10, anchor_y="top", multiline=True, width=300)
        self.btn_save = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.accent, batch=b)
        self.btn_save_l = lab(11, True, color=_theme.rgba(P.accent_text), anchor_x="center",
                              anchor_y="center")
        self.btn_close = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel2, batch=b)
        self.btn_close_l = lab(11, True, anchor_x="center", anchor_y="center")
        self.list.y = -2000
        self.chrome.title.color = _theme.rgba(P.header_text)
        self.chrome.subtitle.color = _theme.rgba(P.header_dim)

    # --------------------------------------------------------------- medidas

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        self.chrome.title.font_size = 18
        self.band.x, self.band.y, self.band.width, self.band.height = 0, h - 26 - 76, w, 76
        self.chrome.title.y, self.chrome.subtitle.y = h - 38, h - 72
        m = self.chrome.message               # o aviso «guardado» fica na faixa do topo
        m.anchor_x, m.x, m.y = "right", w - 48, h - 44
        m.color = _theme.rgba(_theme.P.header_text)
        top, bottom = h - 26 - 76 - 14, 62
        lw = int((w - 96 - 20) * 0.56)
        self.left = (48, top, lw)
        rx = 48 + lw + 20
        self.right = (rx, top, w - 48 - rx)
        chart_h = int(max(120, min(210, (top - bottom) * 0.34)))
        # cartões: gráfico, análise, formulário
        geo = [(48, top - chart_h - 70, lw, chart_h + 70),
               (48, bottom, lw, top - chart_h - 70 - 12 - bottom),
               (rx, bottom, w - 48 - rx, top - bottom)]
        for (o, c), (x, y, cw, ch) in zip(self.cards, geo):
            o.x, o.y, o.width, o.height = x - 1, y - 1, cw + 2, ch + 2
            c.x, c.y, c.width, c.height = x, y, cw, ch
        self.geo = geo
        x, y, cw, ch = geo[0]
        self.h_chart.x, self.h_chart.y = x + 14, y + ch - 10
        self.h_chart_sub.x, self.h_chart_sub.y = x + 14, y + ch - 30
        self.chart_rect = (x + 46, y + 34, cw - 46 - 40, ch - 70 - 18)
        self.legend.x, self.legend.y = x + 14, y + 18
        self.legend2.x, self.legend2.y = x + cw - 14, y + 18
        x, y, cw, ch = geo[1]
        self.h_an.x, self.h_an.y = x + 14, y + ch - 10
        x, y, cw, ch = geo[2]
        self.h_form.x, self.h_form.y = x + 14, y + ch - 10
        self.h_form_sub.x, self.h_form_sub.y = x + 14, y + ch - 30
        self.h_form_sub.width = int(cw - 28)
        self.form_x, self.form_w = x + 14, cw - 28
        self.form_top = y + ch - 62

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -2000
        self._layout()
        self._refresh()

    # -------------------------------------------------------------- conteúdo

    def _fb(self) -> dict:
        v = self.v
        return {"rpe": v["rpe"], "pain": v["pain"], "feel": v["feel"], "goal_met": v["goal"],
                "comment": v["comment"]}

    def enter(self) -> None:
        s = self.sess
        if s is None:
            self.chrome.set(tr("Sessão não encontrada", "Session not found"), "", "")
            return
        when = (s.started_at or "")[:10]
        d = f"{when[8:10]}/{when[5:7]}" if len(when) == 10 else when
        title = s.title or (self.brief.title if self.brief else "")
        self.chrome.set(f"{sport_kind(s.sport).capitalize()}: {title}".rstrip(": "),
                        f"{d} · {sport_kind(s.sport)} · {hms(s.moving_s or s.elapsed_s or 0)}",
                        tr("↑↓ linha · ←/→ valor · Backspace limpa · Ctrl+S guardar · "
                           "Esc fechar", "↑↓ row · ←/→ value · Backspace clears · Ctrl+S save · "
                           "Esc close"))
        self.list.set_items([])
        self._refresh()

    def _refresh(self) -> None:
        if self.sess is None:
            return
        self._draw_chart()
        self._draw_analysis()
        self._draw_form()

    # ---- gráfico: prescrito e realizado
    def _draw_chart(self) -> None:
        P = _theme.P
        s, br = self.sess, self.brief
        self.h_chart.text = tr("Prescrito e realizado", "Prescribed and done")
        self.h_chart_sub.text = (tr("Prescrito: {w}", "Prescribed: {w}", w=br.title) if br else
                                 tr("Sessão livre: sem treino prescrito",
                                    "Free session: no prescribed workout"))
        x, y, w, h = self.chart_rect
        self.chart_bg.x, self.chart_bg.y, self.chart_bg.width, self.chart_bg.height = x, y, w, h
        total = max(s.moving_s or 0, s.elapsed_s or 0, br.seconds if br else 0,
                    max((t for t, *_ in s.samples), default=0), 1)
        pcts = [p for _t, p, _r, _h in s.samples if p is not None]
        peak = max([150.0] + [min(250.0, p) for p in pcts] +
                   ([max(b.lo or 0, b.hi or 0) for b in br.raw_blocks] if br else []))
        top = (int(peak / 50) + 1) * 50

        def py(p: float) -> float:
            return y + max(0.0, min(1.0, p / top)) * h

        watts = s.sport in ("cycling", "rowing") and s.ftp_w
        for k, (g, l) in enumerate(zip(self.grid, self.yl)):
            p = top * k / 4
            g.x, g.y, g.width, g.height = x, py(p), w, 1
            l.text = (f"{p * s.ftp_w / 100:.0f}" if watts else f"{p:.0f}%") if s.sport != "gym" \
                else ""
            l.x, l.y = x - 4, py(p)
        hrs = [hh for *_x, hh in s.samples if hh]
        hlo, hhi = (min(hrs) - 5, max(hrs) + 5) if hrs else (60, 180)
        hhi = max(hhi, hlo + 20)
        for k, l in enumerate(self.yr):
            v = hlo + (hhi - hlo) * k / 4
            l.text = f"{v:.0f}" if hrs else ""
            l.x, l.y = x + w + 6, y + h * k / 4
        for k, l in enumerate(self.xl):
            l.text = hms(total * k / (len(self.xl) - 1))
            l.x, l.y = x + w * k / (len(self.xl) - 1), y - 3
        # blocos prescritos
        n, acc = 0, 0.0
        if br is not None and s.sport != "gym":
            for blk in br.raw_blocks:
                x0 = x + acc / total * w
                bw = blk.seconds / total * w
                acc += blk.seconds
                ramp = blk.lo is not None and blk.hi is not None and abs(blk.hi - blk.lo) > 0.5
                slices = 5 if ramp and bw > 10 else 1
                for k in range(slices):
                    if n >= len(self.blocks):
                        break
                    if blk.lo is None:
                        pct, col = 50.0, (196, 202, 210)
                    else:
                        pct = blk.lo + ((blk.hi if blk.hi is not None else blk.lo) - blk.lo) * (
                            (k + 0.5) / slices)
                        col = it.zone_color(pct)
                    r = self.blocks[n]
                    n += 1
                    r.x, r.y = x0 + k * bw / slices, y
                    r.width, r.height = max(1.0, bw / slices), max(2.0, py(pct) - y)
                    r.color, r.opacity = col[:3], 120
        for r in self.blocks[n:]:
            r.width = r.height = 0
            r.opacity = 0
        # linhas realizadas
        pts = self._downsample([(t, p) for t, p, _r, _h in s.samples if p is not None])
        self._polyline(self.pow_lines, [(x + t / total * w, py(min(p, top))) for t, p in pts])
        hpts = self._downsample([(t, hh) for t, _p, _r, hh in s.samples if hh])
        self._polyline(self.hr_lines, [(x + t / total * w, y + (hh - hlo) / (hhi - hlo) * h)
                                       for t, hh in hpts])
        what = {"cycling": tr("Potência real", "Actual power"),
                "rowing": tr("Potência real", "Actual power"),
                "running": tr("Ritmo real (% do limiar)", "Actual pace (% threshold)"),
                "swimming": tr("Ritmo real (% da CSS)", "Actual pace (% CSS)")}.get(s.sport, "")
        self.legend.text = "   ".join(x for x in (
            ("— " + what) if pts else "", tr("— FC real (eixo à direita)",
                                             "— Actual HR (right axis)") if hpts else "") if x)
        self.legend2.text = tr("Blocos = prescrito; linhas = realizado",
                               "Blocks = prescribed; lines = done") if br else ""
        self.empty.text = "" if (pts or hpts or (br and n)) else tr(
            "Sem amostras gravadas nesta sessão", "No samples recorded in this session")
        self.empty.x, self.empty.y = x + w / 2, y + h / 2
        _ = P

    def _downsample(self, pts: list) -> list:
        if len(pts) <= self.MAX_PTS:
            return pts
        step = len(pts) / self.MAX_PTS
        out = []
        for i in range(self.MAX_PTS):
            chunk = pts[int(i * step):int((i + 1) * step)] or [pts[min(len(pts) - 1,
                                                                       int(i * step))]]
            out.append((chunk[len(chunk) // 2][0], sum(c[1] for c in chunk) / len(chunk)))
        return out

    @staticmethod
    def _polyline(pool: list, pts: list) -> None:
        for i, ln in enumerate(pool):
            if i + 1 < len(pts):
                (ln.x, ln.y), (ln.x2, ln.y2) = pts[i], pts[i + 1]
                ln.opacity = 255
            else:
                ln.x = ln.x2 = ln.y = ln.y2 = 0
                ln.opacity = 0

    # ---- análise
    def _draw_analysis(self) -> None:
        P = _theme.P
        res = fbm.analyse(self.app.db, self.sess, self._fb())
        self.analysis = res
        x, y, cw, ch = self.geo[1]
        self.h_an.text = tr("Análise", "Analysis")
        tone_bg = {"good": _theme.mix(P.good, P.panel, 0.82), "warn": P.warn_bg,
                   "bad": _theme.mix(P.bad, P.panel, 0.82)}[res["tone"]]
        tone_fg = {"good": P.good, "warn": P.warn, "bad": P.bad}[res["tone"]]
        useful = {"yes": tr("Proveitosa", "Worthwhile"), "partial": tr("Proveitosa em parte",
                                                                        "Partly worthwhile"),
                  "no": tr("Pouco proveitosa", "Not worthwhile")}.get(res["useful"], "")
        text = f"{useful} · {res['verdict']}" if useful else res["verdict"]
        text = wrap(text, cw - 40, 10, 1)
        self.chip.text = text
        self.chip.color = _theme.rgba(tone_fg)
        cy = y + ch - 40
        self.chip_bg.x, self.chip_bg.y = x + 14, cy - 12
        self.chip_bg.width = min(cw - 28, len(text) * 7.0 + 20)
        self.chip_bg.height = 24
        self.chip_bg.color = tone_bg
        self.chip.x, self.chip.y = x + 24, cy
        ty = cy - 24
        width = cw - 28
        for k, (tl, tx) in enumerate(zip(self.an_titles, self.an_texts)):
            if k < len(res["sections"]) and ty > y + 30:
                title, body = res["sections"][k]
                room = int((ty - (y + 14)) // 15) - 1
                lines = max(1, min(5, room))
                tl.text = title
                tl.x, tl.y = x + 14, ty
                tx.text = wrap(body, width, 10, lines)
                tx.width = int(width)
                tx.x, tx.y = x + 14, ty - 16
                ty -= 16 + 15 * (tx.text.count("\n") + 1) + 8
            else:
                tl.text = tx.text = ""
        self.an_note.text = "" if self.saved else tr(
            "Prévia: guarda para ficar registada (e ir para o agente treinador).",
            "Preview: save to record it (and send it to the coach agent).")
        self.an_note.x, self.an_note.y = x + 14, y + 16

    # ---- formulário
    def _draw_form(self) -> None:
        P = _theme.P
        x, w = self.form_x, self.form_w
        self.h_form.text = tr("Como correu esta sessão?", "How did this session go?")
        self.h_form_sub.text = wrap(tr(
            "O que escreves fica guardado e vai com o pedido de análise. Podes deixar campos "
            "em branco.", "What you write is saved and goes with the analysis request. You "
            "can leave fields blank."), w, 9, 2)
        y = self.form_top
        self.row_y: dict[str, tuple[float, float]] = {}
        titles = {"rpe": tr("Esforço percebido (RPE)", "Perceived effort (RPE)"),
                  "pain": tr("Dores (na mesma escala)", "Pain (same scale)"),
                  "feel": tr("Sensação geral", "Overall feeling"),
                  "goal": tr("O objetivo foi cumprido?", "Was the goal met?"),
                  "comment": tr("Comentário", "Comment")}
        hints = {"rpe": tr("1 = muito fácil, 10 = esforço máximo", "1 = very easy, 10 = max"),
                 "pain": tr("0 = sem dores, 10 = dor máxima", "0 = no pain, 10 = max pain")}
        if self.brief is not None and self.brief.target_rpe:
            hints["rpe"] += tr(" · previsto {r}", " · planned {r}", r=f"{self.brief.target_rpe:g}")
        labels = {"rpe": [str(i) for i in range(1, 11)], "pain": [str(i) for i in range(11)],
                  "feel": [fbm.feel_name(i) for i in range(1, 6)],
                  "goal": [fbm.goal_met_name(g) for g in fbm.GOAL_MET]}
        values = {"rpe": [i for i in range(1, 11)], "pain": list(range(11)),
                  "feel": list(range(1, 6)), "goal": list(fbm.GOAL_MET)}
        compact = self.app.window.height < 700
        chip_h = 24 if compact else 28
        for key_ in ("rpe", "pain", "feel", "goal"):
            t_ = self.row_titles[key_]
            t_.text = titles[key_] + ("  ·  " + tr("limpar: Backspace", "clear: Backspace")
                                      if self.v[key_] is not None and
                                      ROWS[self.row] == key_ else "")
            t_.x, t_.y = x, y
            yy = y - 18
            n = len(self.chips[key_])
            gap = 4
            cw = (w - gap * (n - 1)) / n
            for i, (o, r, l) in enumerate(self.chips[key_]):
                on = self.v[key_] == values[key_][i]
                cx = x + i * (cw + gap)
                o.x, o.y, o.width, o.height = cx - 1, yy - chip_h - 1, cw + 2, chip_h + 2
                r.x, r.y, r.width, r.height = cx, yy - chip_h, cw, chip_h
                r.color = P.header if on else P.panel2
                o.color = P.header if on else P.border
                lab = labels[key_][i]
                l.text = lab if len(lab) * 6.4 < cw - 4 else lab[:max(1, int((cw - 4) / 6.4))]
                l.color = _theme.rgba(P.header_text if on else P.text)
                l.x, l.y = cx + cw / 2, yy - chip_h / 2
            bottom = yy - chip_h
            if key_ in self.row_hints:
                hl = self.row_hints[key_]
                hl.text = hints[key_]
                hl.x, hl.y = x, bottom - 3
                bottom -= 13
            self.row_y[key_] = (bottom - 2, y + 4)
            y = bottom - (8 if compact else 12)
        # comentário
        t_ = self.row_titles["comment"]
        t_.text = titles["comment"]
        t_.x, t_.y = x, y
        box_h = max(40, min(80, y - 18 - (self.geo[2][1] + 60)))
        bx, by = x, y - 18 - box_h
        self.box_out.x, self.box_out.y, self.box_out.width, self.box_out.height = (
            bx - 1, by - 1, w + 2, box_h + 2)
        self.box.x, self.box.y, self.box.width, self.box.height = bx, by, w, box_h
        focus = ROWS[self.row] == "comment"
        self.box_out.color = P.accent if focus else P.border
        lines = max(1, int((box_h - 8) // 14))
        txt = self.v["comment"] + ("▏" if focus else "")
        self.box_text.text = wrap(txt, w - 16, 10, lines) if txt else ""
        if not self.v["comment"] and not focus:
            self.box_text.text = tr("ex.: dores nas pernas, a corrida de ontem ainda pesa…",
                                    "e.g. sore legs, yesterday's run still weighs…")
            self.box_text.color = _theme.rgba(P.faint)
        else:
            self.box_text.color = _theme.rgba(P.text)
        self.box_text.width = int(w - 16)
        self.box_text.x, self.box_text.y = bx + 8, by + box_h - 6
        self.row_y["comment"] = (by, y + 4)
        # botões: em baixo, à direita, como em todos os ecrãs (o principal à direita)
        from velo.ui.widgets import BUTTON_H, BUTTON_Y, button_width
        self.btn_save_l.text = tr("Guardar e reanalisar", "Save and re-analyse") if self.saved \
            else tr("Guardar e analisar", "Save and analyse")
        self.btn_close_l.text = tr("Fechar", "Close") if self.saved else tr("Agora não", "Not now")
        bw = button_width(self.btn_save_l.text)
        cw2 = button_width(self.btn_close_l.text)
        right = self.app.window.width - 48
        y2 = BUTTON_Y
        self.btn_save.x, self.btn_save.y = right - bw, y2
        self.btn_save.width, self.btn_save.height = bw, BUTTON_H
        self.btn_save_l.x, self.btn_save_l.y = right - bw / 2, y2 + BUTTON_H / 2
        self.btn_close.x, self.btn_close.y = right - bw - 10 - cw2, y2
        self.btn_close.width, self.btn_close.height = cw2, BUTTON_H
        self.btn_close_l.x, self.btn_close_l.y = right - bw - 10 - cw2 / 2, y2 + BUTTON_H / 2
        self.row_y["save"] = (y2, y2 + BUTTON_H)
        self.row_y["close"] = (y2, y2 + BUTTON_H)
        self.btn_save.color = _theme.mix(P.accent, P.header, 0.35) if ROWS[self.row] == "save" \
            else P.accent
        self.btn_close.color = P.select if ROWS[self.row] == "close" else P.panel2
        lo, hi = self.row_y[ROWS[self.row]]
        bar_x = x - 10
        if ROWS[self.row] in ("save", "close"):
            bar_x = (self.btn_save if ROWS[self.row] == "save" else self.btn_close).x - 6
        self.row_bar.x, self.row_bar.y, self.row_bar.height = bar_x, lo, hi - lo

    # ---------------------------------------------------------------- ações

    def save(self) -> dict:
        v = self.v
        res = fbm.save(self.app.db, self.kind, self.sid, v["rpe"], v["pain"], v["feel"],
                       v["goal"], v["comment"])
        self.saved = True
        self.app.message(tr("Feedback guardado", "Feedback saved"))
        self._refresh()
        return res

    def set_value(self, key_: str, value) -> None:
        self.v[key_] = value
        self._refresh()

    def _cycle(self, step: int) -> None:
        k = ROWS[self.row]
        options = {"rpe": list(range(1, 11)), "pain": list(range(11)), "feel": list(range(1, 6)),
                   "goal": list(fbm.GOAL_MET)}.get(k)
        if options is None:
            return
        cur = self.v[k]
        if cur is None:
            i = 0 if step > 0 else len(options) - 1
            if k == "rpe" and self.brief is not None and self.brief.target_rpe:
                i = options.index(int(round(self.brief.target_rpe)))
        else:
            i = max(0, min(len(options) - 1, options.index(cur) + step))
        self.v[k] = options[i]
        self._refresh()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        k = ROWS[self.row]
        if symbol == key.S and modifiers & key.MOD_CTRL:
            self.save()
            return True
        if symbol == key.ESCAPE:
            self.app.pop()
            return True
        if symbol in (key.DOWN, key.TAB) and not (modifiers & key.MOD_SHIFT):
            self.row = min(len(ROWS) - 1, self.row + 1)
            self._refresh()
            return True
        if symbol == key.UP or (symbol == key.TAB and modifiers & key.MOD_SHIFT):
            self.row = max(0, self.row - 1)
            self._refresh()
            return True
        if k == "comment":
            if symbol == key.BACKSPACE:
                self.v["comment"] = self.v["comment"][:-1]
                self._refresh()
            elif symbol in (key.ENTER, key.RETURN):
                self.row += 1
                self._refresh()
            return True                       # o resto escreve (on_text)
        if symbol in (key.LEFT, key.RIGHT):
            if k in ("save", "close"):
                self.row = ROWS.index("close" if symbol == key.RIGHT else "save")
                self._refresh()
            else:
                self._cycle(1 if symbol == key.RIGHT else -1)
            return True
        if symbol in (key.BACKSPACE, key.DELETE) and k in ("rpe", "pain", "feel", "goal"):
            self.v[k] = None
            self._refresh()
            return True
        if symbol in (key.ENTER, key.RETURN, key.SPACE):
            if k == "save":
                self.save()
            elif k == "close":
                self.app.pop()
            else:
                self.row += 1
                self._refresh()
            return True
        return True

    def on_text(self, text: str) -> bool:
        k = ROWS[self.row]
        clean = "".join(c for c in text if c.isprintable() and c not in "\r\n\t")
        if not clean:
            return True
        if k == "comment":
            self.v["comment"] = (self.v["comment"] + clean)[:600]
            self._refresh()
            return True
        if k in ("rpe", "pain") and clean.isdigit():
            n = int(clean[-1])
            if k == "rpe":
                n = 10 if n == 0 else n
            self.v[k] = n
            self._refresh()
        return True

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.app.pop()
            return True
        values = {"rpe": list(range(1, 11)), "pain": list(range(11)), "feel": list(range(1, 6)),
                  "goal": list(fbm.GOAL_MET)}
        for k, chips in self.chips.items():
            for i, (_o, r, _l) in enumerate(chips):
                if r.x <= x <= r.x + r.width and r.y <= y <= r.y + r.height:
                    self.row = ROWS.index(k)
                    self.v[k] = None if self.v[k] == values[k][i] else values[k][i]
                    self._refresh()
                    return True
        b = self.box
        if b.x <= x <= b.x + b.width and b.y <= y <= b.y + b.height:
            self.row = ROWS.index("comment")
            self._refresh()
            return True
        for r, name in ((self.btn_save, "save"), (self.btn_close, "close")):
            if r.x <= x <= r.x + r.width and r.y <= y <= r.y + r.height:
                self.row = ROWS.index(name)
                self.save() if name == "save" else self.app.pop()
                return True
        return False

    def agent_data(self) -> dict:
        return {"feedback": self._fb(), "analise": getattr(self, "analysis", {})}

    def draw(self) -> None:
        self.batch.draw()
        self.chrome.draw()
        if self.back_button is not None:
            self.back_button.draw()
