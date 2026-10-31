"""Resumo de um treino antes de começar: objetivo, gráfico dos blocos e, para
cada bloco, o que se faz e o alvo.

Segue o desenho dos cartões de treino do intervals.icu: o título, «bicicleta
indoor · 30 min», a intensidade em palavras, o objetivo numa frase, o gráfico
(altura = intensidade, largura = tempo, cor = zona, a linha tracejada é o
limiar) e a lista de blocos com «Alvo: …».
"""
from __future__ import annotations

import pyglet
import pyglet.shapes

from velo.core import intensity as it
from velo.core import objectives as ob
from velo.core import sports as sp
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.gfx.compat import label as make_label
from velo.ui.app import Screen
from velo.ui.widgets import BORDER, DIM, GRID, PANEL, TEXT, Item


def wrap(text: str, width_px: float, size: float, max_lines: int = 0) -> str:
    """Parte o texto em linhas que cabem na largura (estimativa por carácter)."""
    per = max(8, int(width_px / (size * 0.68)))
    lines: list[str] = []
    for para in (text or "").split("\n"):
        cur = ""
        for word in para.split():
            if len(cur) + len(word) + (1 if cur else 0) <= per:
                cur = f"{cur} {word}" if cur else word
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(0, per - 1)].rstrip() + "…"
    return "\n".join(lines)


def sport_kind(sport: str) -> str:
    return {"cycling": tr("bicicleta indoor", "indoor cycling"),
            "rowing": tr("remo indoor", "indoor rowing"),
            "running": tr("corrida em passadeira", "treadmill run"),
            "swimming": tr("natação em piscina", "pool swim"),
            "gym": tr("ginásio", "gym")}.get(sport, sport)


class BriefPanel:
    """O cartão do treino (ver o módulo). Formas e etiquetas criadas uma vez."""

    MAX_BARS = 160
    MAX_ROWS = 14

    def __init__(self):
        b = self.batch = pyglet.graphics.Batch()
        self.outline = pyglet.shapes.Rectangle(0, 0, 1, 1, color=BORDER, batch=b)
        self.card = pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL, batch=b)
        self.title = make_label("", font_size=18, bold=True, color=TEXT, anchor_y="top", batch=b)
        self.meta = make_label("", font_size=11, color=DIM, anchor_y="top", batch=b)
        self.intensity = make_label("", font_size=11, color=TEXT, anchor_y="top", batch=b)
        self.goal = make_label("", font_size=12, color=TEXT, anchor_y="top", batch=b,
                               multiline=True, width=400)
        self.auto_note = make_label("", font_size=9, color=DIM, anchor_y="top", batch=b)
        self.chart_bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL, batch=b)
        self.grid = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=GRID, batch=b) for _ in range(4)]
        self.yticks = [make_label("", font_size=8, color=DIM, anchor_x="right",
                                  anchor_y="center", batch=b) for _ in range(4)]
        self.bars = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=(200, 200, 200), batch=b)
                     for _ in range(self.MAX_BARS)]
        self.dashes = [pyglet.shapes.Rectangle(0, 0, 0, 1, color=DIM[:3], batch=b)
                       for _ in range(160)]
        self.thr_label = make_label("", font_size=8, color=DIM, anchor_x="right",
                                    anchor_y="bottom", batch=b)
        self.xticks = [make_label("", font_size=8, color=DIM, anchor_x="center",
                                  anchor_y="top", batch=b) for _ in range(7)]
        self.legend_sq = [pyglet.shapes.Rectangle(0, 0, 9, 9, color=c, batch=b)
                          for c in it.ZONE_COLORS[:6]]
        self.legend_lab = [make_label(f"Z{i + 1}", font_size=9, color=DIM, anchor_y="bottom",
                                      batch=b) for i in range(6)]
        self.legend_note = make_label("", font_size=9, color=DIM, anchor_x="right",
                                      anchor_y="bottom", batch=b)
        self.rows = []
        for _ in range(self.MAX_ROWS):
            self.rows.append({
                "dot": pyglet.shapes.Circle(0, 0, 5, color=(180, 180, 180), batch=b),
                "name": make_label("", font_size=11, bold=True, color=TEXT, anchor_y="top",
                                   batch=b),
                "goal": make_label("", font_size=10, color=TEXT, anchor_y="top", batch=b,
                                   multiline=True, width=300),
                "target": make_label("", font_size=9, color=DIM, anchor_y="top", batch=b),
            })
        self.more = make_label("", font_size=10, color=DIM, anchor_y="top", batch=b)
        self.geometry = (0, 0, 600, 0)
        self.brief: ob.Brief | None = None

    # -------------------------------------------------------------- medidas

    def layout(self, x: float, top: float, w: float, bottom: float) -> None:
        self.geometry = (x, top, w, bottom)
        if self.brief is not None:
            self.set(self.brief)

    def set(self, brief: ob.Brief) -> None:
        self.brief = brief
        x, top, w, bottom = self.geometry
        pad = 18
        self.outline.x, self.outline.y = x - 1, bottom - 1
        self.outline.width, self.outline.height = w + 2, top - bottom + 2
        self.card.x, self.card.y, self.card.width, self.card.height = x, bottom, w, top - bottom
        ix, iw = x + pad, w - 2 * pad
        y = top - 14
        self.title.text = wrap(brief.title, iw, 18, 1)
        self.title.x, self.title.y = ix, y
        y -= 30
        bits = [sport_kind(brief.sport), hms(brief.seconds) if brief.seconds < 3600
                else f"{brief.seconds / 3600:.1f} h".replace(".", ",")]
        if brief.meters:
            bits.append(f"{brief.meters / 1000:.1f} km".replace(".", ","))
        if brief.tss:
            bits.append(f"TSS ≈ {brief.tss:.0f}")
        self.meta.text = " · ".join(bits)
        self.meta.x, self.meta.y = ix, y
        y -= 18
        self.intensity.text = brief.intensity
        self.intensity.x, self.intensity.y = ix, y
        y -= 22
        text = wrap(brief.goal, iw, 12, 3)
        self.goal.text = text
        self.goal.width = int(iw)
        self.goal.x, self.goal.y = ix, y
        y -= 17 * (text.count("\n") + 1) + 2
        self.auto_note.text = "" if brief.goal_written else tr(
            "Objetivo sugerido pela estrutura do treino · «Objetivos» para o escrever",
            "Goal suggested from the workout structure · «Goals» to write your own")
        self.auto_note.x, self.auto_note.y = ix, y
        if not brief.goal_written:
            y -= 14
        avail = y - bottom
        chart_h = max(70, min(150, avail * 0.36))
        y -= 8
        self._chart(ix + 30, y - chart_h, iw - 30, chart_h, brief)
        y -= chart_h + 18
        # legenda
        lx = ix + 30
        show_legend = brief.sport != "gym"
        for sq, lab in zip(self.legend_sq, self.legend_lab):
            sq.x, sq.y = lx, y - 12
            sq.opacity = 255 if show_legend else 0
            lab.x, lab.y = lx + 13, y - 13
            lab.text = lab.text if show_legend else ""
            if show_legend and not lab.text:
                lab.text = f"Z{self.legend_lab.index(lab) + 1}"
            lx += 42
        self.legend_note.text = tr("Altura = intensidade; largura = tempo",
                                   "Height = intensity; width = time")
        self.legend_note.x, self.legend_note.y = ix + iw, y - 13
        y -= 26
        self._rows(ix, y, iw, bottom + 10, brief)

    def _chart(self, x: float, y: float, w: float, h: float, brief: ob.Brief) -> None:
        self.chart_bg.x, self.chart_bg.y, self.chart_bg.width, self.chart_bg.height = x, y, w, h
        raw = brief.raw_blocks
        total = sum(b.seconds for b in raw) or 1.0
        peak = max([max(b.lo or 50, b.hi or b.lo or 50) for b in raw] + [110.0])
        top_pct = min(200.0, (int(peak / 25) + 1) * 25)

        def py(p: float) -> float:
            return y + max(0.0, min(1.0, p / top_pct)) * h

        step = 50 if top_pct > 100 else 25
        ticks = [v for v in range(0, int(top_pct) + 1, step)][:len(self.grid)]
        for k, (g, lab) in enumerate(zip(self.grid, self.yticks)):
            if k < len(ticks):
                p = ticks[k]
                g.x, g.y, g.width, g.height = x, py(p), w, 1
                g.opacity = 255
                lab.text = f"{p}%" if brief.sport != "gym" else ""
                lab.x, lab.y = x - 4, py(p)
            else:
                g.opacity = 0
                lab.text = ""
        n = 0
        acc = 0.0
        for blk in raw:
            x0 = x + acc / total * w
            bw = blk.seconds / total * w
            acc += blk.seconds
            ramp = blk.lo is not None and blk.hi is not None and abs(blk.hi - blk.lo) > 0.5
            slices = 6 if ramp and bw > 12 else 1
            for k in range(slices):
                if n >= len(self.bars):
                    break
                frac = (k + 0.5) / slices
                if blk.lo is None:
                    pct, color = 50.0, (186, 192, 202)
                else:
                    pct = blk.lo + ((blk.hi if blk.hi is not None else blk.lo) - blk.lo) * frac
                    color = it.zone_color(pct)
                r = self.bars[n]
                n += 1
                sw = bw / slices
                r.x, r.y = x0 + k * sw, y
                r.width = max(1.0, sw - (1 if k == slices - 1 and bw > 3 else 0))
                r.height = max(2.0, py(pct) - y)
                r.color = color[:3]
                r.opacity = 235
        for r in self.bars[n:]:
            r.width = r.height = 0
            r.opacity = 0
        # limiar tracejado (100 %)
        show = brief.sport != "gym"
        ty = py(100)
        dash, gap = 6, 4
        cx = x
        for d in self.dashes:
            if show and cx < x + w:
                d.x, d.y, d.width = cx, ty, min(dash, x + w - cx)
                d.opacity = 200
                cx += dash + gap
            else:
                d.width = 0
                d.opacity = 0
        self.thr_label.text = brief.threshold_label if show else ""
        self.thr_label.x, self.thr_label.y = x + w, ty + 2
        # tempo
        for k, lab in enumerate(self.xticks):
            s = total * k / (len(self.xticks) - 1)
            lab.text = hms(s)
            lab.x, lab.y = x + w * k / (len(self.xticks) - 1), y - 3

    def _rows(self, x: float, top: float, w: float, bottom: float, brief: ob.Brief) -> None:
        cols = 2 if w > 520 else 1
        cw = (w - 20 * (cols - 1)) / cols
        row_h = 54
        per_col = max(1, int((top - bottom) // row_h))
        cap = min(len(self.rows), per_col * cols)
        shown = brief.blocks[:cap]
        for i, row in enumerate(self.rows):
            if i < len(shown):
                blk = shown[i]
                c, r = divmod(i, per_col)
                rx, ry = x + c * (cw + 20), top - r * row_h
                color = it.zone_color(((blk.lo or 50) + (blk.hi or blk.lo or 50)) / 2) \
                    if blk.lo is not None else (186, 192, 202)
                row["dot"].x, row["dot"].y = rx + 5, ry - 7
                row["dot"].color = color[:3]
                row["dot"].opacity = 255
                prefix = f"{blk.repeat} × " if blk.repeat > 1 else (
                    "↳ " if blk.repeat < 0 else "")
                row["name"].text = wrap(f"{prefix}{blk.name}  ({blk.dur_text})", cw - 20, 11, 1)
                row["name"].x, row["name"].y = rx + 16, ry
                row["goal"].text = wrap(blk.goal, cw - 20, 10, 1)
                row["goal"].x, row["goal"].y = rx + 16, ry - 17
                row["goal"].width = int(cw - 20)
                row["target"].text = tr("Alvo: {t}", "Target: {t}", t=blk.target)
                row["target"].x, row["target"].y = rx + 16, ry - 32
            else:
                row["dot"].opacity = 0
                row["name"].text = row["goal"].text = row["target"].text = ""
        hidden = len(brief.blocks) - len(shown)
        self.more.text = (tr("+ 1 bloco (ver em «Objetivos»)", "+ 1 block (see «Goals»)")
                          if hidden == 1 else
                          tr("+ {n} blocos (ver em «Objetivos»)", "+ {n} blocks (see «Goals»)",
                             n=hidden) if hidden > 1 else "")
        self.more.x, self.more.y = x + 16, bottom + 4

    def draw(self) -> None:
        if self.brief is not None:
            self.batch.draw()


# ====================================================================== ecrãs


class BriefScreen(Screen):
    """Base: lista curta de ações à esquerda (Começar primeiro) e o cartão do
    treino à direita. Cada desporto diz como se lê o treino e como começa."""

    SPORT = "cycling"

    def __init__(self, app, wid: str):
        self.wid = wid
        super().__init__(app)
        self.panel = BriefPanel()
        self.brief_data: ob.Brief | None = None
        self.about = make_label("", font_size=10, color=DIM, anchor_y="top",
                                multiline=True, width=260, batch=self.panel.batch)
        self.about_title = make_label("", font_size=10, bold=True, color=TEXT, anchor_y="top",
                                      batch=self.panel.batch)
        self._layout_panel()

    def _list_width(self, w: int) -> int:
        return max(230, min(300, int(w * 0.27)))

    def _layout_panel(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        x = 48 + self._list_width(w) + 28
        self.panel.layout(x, self.content_top(h) + 18, w - 48 - x, 66)
        lw = self._list_width(w)
        self.about_title.x, self.about_title.y = 48, self.content_top(h) - 5 * 38 + 4
        self.about.x, self.about.y = 48, self.about_title.y - 18
        self.about.width = lw

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout_panel()

    # para redefinir
    def make_brief(self) -> ob.Brief | None:
        return None

    def start(self) -> None: ...

    def extra_actions(self) -> list[Item]:
        return []

    def enter(self) -> None:
        a = self.app
        b = self.make_brief()
        if b is None:
            a.pop()
            return
        self.brief_data = b
        self.panel.set(b)
        w = self.app.window.width
        desc = b.note.split(" · ", 1)[-1] if b.note else ""
        self.about_title.text = tr("Sobre este treino", "About this workout") if desc else ""
        self.about.text = wrap(desc, self._list_width(w), 10, 9)
        items = [Item(t("mode.start"), action=self.start,
                      detail=tr("Começa com este objetivo", "Start with this goal")),
                 Item(tr("Objetivos do treino e dos blocos", "Workout and block goals"),
                      detail=tr("Escreve o que este treino deve trabalhar",
                                "Write what this workout should train"),
                      action=lambda: a.push(_editor().GoalEditor(a, self.SPORT, self.wid, b)))]
        items += self.extra_actions()
        self.chrome.set(sp.name(self.SPORT) if self.SPORT != "gym" else tr("Ginásio", "Gym"),
                        tr("Objetivo, blocos e alvos antes de começar",
                           "Goal, blocks and targets before you start"), self.footer())
        self.list.set_items(items, keep_index=True)

    def agent_data(self) -> dict:
        return self.brief_data.as_dict() if self.brief_data else {}

    def draw(self) -> None:
        super().draw()
        self.panel.draw()


def _editor():
    from velo.ui import brief_edit
    return brief_edit


def endurance_brief(db, sport: str, wid: str) -> ob.Brief | None:
    """Ciclismo, remo, corrida e natação: lê os blocos como o construtor."""
    return ob.workout_brief(db, sport, wid)


class CyclingBrief(BriefScreen):
    SPORT = "cycling"

    def make_brief(self):
        return endurance_brief(self.app.db, "cycling", self.wid)

    def start(self) -> None:
        from velo.ui.app import WorkoutRouteChoice
        self.app.push(WorkoutRouteChoice(self.app, self.wid))

    def extra_actions(self) -> list[Item]:
        a = self.app
        from velo.ui.builder_screens import BlockBuilder
        return [Item(tr("Abrir no construtor", "Open in the builder"),
                     action=lambda: a.push(BlockBuilder(a, "cycling", self.wid)))]


class GymBrief(BriefScreen):
    SPORT = "gym"

    def make_brief(self):
        from velo.core import strength as st
        db = self.app.db
        wk = st.workout(db, self.wid)
        if wk is None:
            return None
        plan = st.workout_items(db, self.wid)
        mod = wk.get("modality") or "strength"
        return ob.gym_brief(db, self.wid, wk["name"], plan, mod)


class GoalLine:
    """«Principal: trabalho contínuo em Z2…» para o passo em curso de uma sessão."""

    def __init__(self, db, sport: str, wid: str | None):
        self.brief = None
        if wid:
            try:
                self.brief = endurance_brief(db, sport, wid)
            except Exception:
                self.brief = None

    def text(self, idx: int) -> str:
        b = self.brief
        if b is None or not (0 <= idx < len(b.raw_blocks)):
            return ""
        blk = b.raw_blocks[idx]
        return f"{blk.name}: {blk.goal}"
