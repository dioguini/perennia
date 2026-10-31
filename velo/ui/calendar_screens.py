"""Calendário mensal (estilo intervals.icu) e o dia aberto.

Teclado: ←/→ dia · ↑/↓ semana · PgUp/PgDn (ou [ / ]) mês · T hoje ·
Enter abre o dia. Rato: um clique escolhe o dia, outro abre-o; ‹ Hoje › em cima.
"""
from __future__ import annotations

from datetime import date, timedelta

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import calendar_view as cv
from velo.core import sports as sp
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx import theme as _theme
from velo.gfx.compat import label as make_label
from velo.ui.app import Screen
from velo.ui.widgets import Item

MAX_WEEKS = 6
MAX_CARDS = 4


def _short_time(s: float) -> str:
    s = int(s or 0)
    h, m = divmod(s // 60, 60)
    return f"{h}:{m:02d}" if h else f"{m} min"


def sport_label(sport: str) -> str:
    return tr("Ginásio", "Gym") if sport == "gym" else sp.name(sport)


class CalendarScreen(Screen):
    AGENT = True

    def __init__(self, app, when: date | None = None):
        super().__init__(app)
        today = date.today()
        self.sel = when or today
        self.year, self.month = self.sel.year, self.sel.month
        self.data: dict = {}
        self.list.y = -2000
        self._build()
        self._load()

    # ------------------------------------------------------------ construção

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        dim, txt = _theme.rgba(P.dim), _theme.rgba(P.text)
        self.month_l = make_label("", font_size=18, bold=True, color=txt, anchor_y="center",
                                  batch=b)
        self.nav = []
        for _ in range(3):
            self.nav.append((pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                             pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b),
                             make_label("", font_size=10, bold=True, color=txt,
                                        anchor_x="center", anchor_y="center", batch=b)))
        self.heads = [make_label("", font_size=9, bold=True, color=dim, anchor_y="center",
                                 batch=b) for _ in range(8)]
        self.grid_bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b)
        self.cells = []
        for _ in range(MAX_WEEKS * 7):
            bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b)  # por baixo
            cards = []
            for _ in range(MAX_CARDS):
                cards.append((pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.panel2, batch=b),
                              pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.accent, batch=b),
                              make_label("", font_size=8, color=txt, anchor_y="center",
                                         batch=b),
                              pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.good, batch=b)))
            self.cells.append({
                "bg": bg,
                "today": pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.accent, batch=b),
                "num": make_label("", font_size=9, bold=True, color=txt, anchor_y="top",
                                  batch=b),
                "load": make_label("", font_size=8, color=dim, anchor_x="right",
                                   anchor_y="top", batch=b),
                "more": make_label("", font_size=8, color=dim, anchor_y="bottom", batch=b),
                "cards": cards})
        self.sel_out = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.accent, batch=b)
                        for _ in range(4)]
        self.weeks = []
        for _ in range(MAX_WEEKS):
            self.weeks.append({
                "bg": pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel2, batch=b),
                "lines": [make_label("", font_size=8 if k else 10, bold=(k == 0),
                                     color=txt if k == 0 else dim, anchor_y="top", batch=b)
                          for k in range(4)]})

    # --------------------------------------------------------------- dados

    def _load(self) -> None:
        self.data = cv.month_data(self.app.db, self.year, self.month)
        self._layout()

    def go_month(self, step: int) -> None:
        self.year, self.month = cv.shift_month(self.year, self.month, step)
        try:
            self.sel = self.sel.replace(year=self.year, month=self.month)
        except ValueError:
            self.sel = date(self.year, self.month, 28)
        self._load()
        self.enter()

    def go_day(self, d: date) -> None:
        self.sel = d
        if (d.year, d.month) != (self.year, self.month):
            self.year, self.month = d.year, d.month
            self._load()
        else:
            self._layout()
        self.enter()

    # -------------------------------------------------------------- medidas

    def _layout(self) -> None:
        P = _theme.P
        w, h = self.app.window.width, self.app.window.height
        x0, x1 = 48, w - 48
        top = h - 112
        # cabeçalho: mês e navegação
        self.month_l.text = f"{cv.month_name(self.month).capitalize()} {self.year}"
        self.month_l.x, self.month_l.y = x0, top
        prev_y, prev_m = cv.shift_month(self.year, self.month, -1)
        next_y, next_m = cv.shift_month(self.year, self.month, 1)
        texts = [f"‹ {cv.month_name(prev_m)}", tr("Hoje", "Today"), f"{cv.month_name(next_m)} ›"]
        bx = x1
        self.nav_geo = []
        for (o, r, lab), text in reversed(list(zip(self.nav, texts))):
            bw = len(text) * 7 + 24
            bx -= bw
            o.x, o.y, o.width, o.height = bx - 1, top - 14, bw + 2, 30
            r.x, r.y, r.width, r.height = bx, top - 13, bw, 28
            lab.text = text
            lab.x, lab.y = bx + bw / 2, top + 1
            self.nav_geo.insert(0, (bx, top - 13, bw, 28))
            bx -= 8
        # grelha
        weeks = self.data.get("weeks", [])
        n = len(weeks)
        sum_w = max(130, int((x1 - x0) * 0.15))
        day_w = (x1 - x0 - sum_w) / 7
        head_y = top - 34
        for i, lab in enumerate(self.heads):
            lab.text = cv.weekday_name(i) if i < 7 else tr("Semana", "Week")
            lab.x = x0 + i * day_w + 6
            lab.y = head_y
        grid_top = head_y - 12
        bottom = 60
        cell_h = (grid_top - bottom) / max(1, n)
        self.grid_bg.x, self.grid_bg.y = x0 - 1, grid_top - n * cell_h - 1
        self.grid_bg.width, self.grid_bg.height = x1 - x0 + 2, n * cell_h + 2
        today = date.today()
        by_day = self.data.get("by_day", {})
        self.cell_geo = []
        per_card = 18
        max_cards = max(1, min(MAX_CARDS, int((cell_h - 24) // per_card)))
        for wi in range(MAX_WEEKS):
            wk = weeks[wi] if wi < n else None
            for di in range(7):
                c = self.cells[wi * 7 + di]
                if wk is None:
                    self._hide_cell(c)
                    continue
                d = wk[di]
                cx, cy = x0 + di * day_w, grid_top - (wi + 1) * cell_h
                bg = c["bg"]
                bg.x, bg.y, bg.width, bg.height = cx + 1, cy + 1, day_w - 1, cell_h - 1
                inside = d.month == self.month
                bg.color = P.panel if inside else _theme.mix(P.panel2, P.panel, 0.4)
                bg.opacity = 255
                c["num"].text = str(d.day) if d.day != 1 else f"1 {cv.month_name(d.month)[:3]}"
                c["num"].color = _theme.rgba(P.header_text if d == today else
                                             (P.text if inside else P.faint))
                c["num"].x, c["num"].y = cx + 7, cy + cell_h - 5
                tr_ = c["today"]
                if d == today:
                    tw = len(c["num"].text) * 7 + 10
                    tr_.x, tr_.y, tr_.width, tr_.height = cx + 3, cy + cell_h - 20, tw, 17
                    tr_.opacity = 255
                else:
                    tr_.width = tr_.height = 0
                    tr_.opacity = 0
                entries = by_day.get(d, [])
                load = sum((e.load or 0) for e in entries if not e.planned)
                c["load"].text = f"{load:.0f}" if load else ""
                c["load"].x, c["load"].y = cx + day_w - 6, cy + cell_h - 6
                for k, (card, strip, lab, dot) in enumerate(c["cards"]):
                    if k < len(entries) and k < max_cards:
                        e = entries[k]
                        ky = cy + cell_h - 24 - (k + 1) * per_card + 2
                        card.x, card.y, card.width, card.height = cx + 4, ky, day_w - 9, per_card - 3
                        strip.x, strip.y, strip.width, strip.height = cx + 4, ky, 3, per_card - 3
                        strip.color = e.color
                        if e.planned:
                            card.color = P.panel
                            card.opacity = 255
                            mark = "◷ "
                            lab.color = _theme.rgba(P.dim)
                        else:
                            card.color = _theme.mix(e.color, P.panel, 0.86)
                            card.opacity = 255
                            mark = "✓ " if e.done else ""
                            lab.color = _theme.rgba(P.text)
                        strip.opacity = 255
                        room = int((day_w - 30) / 5.4)
                        text = f"{mark}{_short_time(e.seconds)} {e.title or sport_label(e.sport)}"
                        lab.text = text if len(text) <= room else text[:max(4, room - 1)] + "…"
                        lab.x, lab.y = cx + 11, ky + (per_card - 3) / 2
                        if e.tone:
                            dot.color = {"good": P.good, "warn": P.warn, "bad": P.bad}.get(
                                e.tone, P.dim)
                            dot.x, dot.y, dot.width, dot.height = cx + day_w - 12, ky + 5, 5, 5
                            dot.opacity = 255
                        else:
                            dot.width = dot.height = 0
                            dot.opacity = 0
                    else:
                        for o in (card, strip, dot):
                            o.width = o.height = 0
                            o.opacity = 0
                        lab.text = ""
                hidden = len(entries) - max_cards
                c["more"].text = f"+{hidden}" if hidden > 0 else ""
                c["more"].x, c["more"].y = cx + 8, cy + 3
                self.cell_geo.append((d, cx, cy, day_w, cell_h))
            # resumo da semana
            ws = self.weeks[wi]
            if wk is None:
                ws["bg"].opacity = 0
                for lab in ws["lines"]:
                    lab.text = ""
                continue
            s = self.data["summaries"][wi]
            sx, sy = x0 + 7 * day_w, grid_top - (wi + 1) * cell_h
            ws["bg"].x, ws["bg"].y = sx + 1, sy + 1
            ws["bg"].width, ws["bg"].height = sum_w - 1, cell_h - 1
            ws["bg"].opacity = 255
            lines = [hms(s.seconds) if s.seconds else "—",
                     " · ".join(x for x in (
                         f"{s.distance_m / 1000:.0f} km" if s.distance_m >= 1000 else "",
                         (tr("{n} sessões", "{n} sessions", n=s.sessions) if s.sessions != 1
                          else tr("1 sessão", "1 session")) if s.sessions else "") if x),
                     " · ".join(x for x in (
                         tr("Carga {l}", "Load {l}", l=f"{s.load:.0f}") if s.load else "",
                         tr("plano {p}", "plan {p}", p=_short_time(s.planned_s))
                         if s.planned_s else "") if x),
                     tr("Forma {f} (F {c} · C {a})", "Form {f} (F {c} · A {a})",
                        f=f"{s.tsb:+.0f}", c=f"{s.ctl:.0f}", a=f"{s.atl:.0f}")
                     if s.ctl is not None and (s.ctl >= 0.5 or s.atl >= 0.5) else ""]
            rows_fit = max(1, int((cell_h - 8) // 14))
            for k, lab in enumerate(ws["lines"]):
                lab.text = lines[k] if k < rows_fit else ""
                if k == 3 and s.tsb is not None:
                    lab.color = _theme.rgba(P.good if s.tsb > -10 else
                                            (P.warn if s.tsb > -30 else P.bad))
                lab.x, lab.y = sx + 9, sy + cell_h - 6 - k * 15
        self._place_selection()

    @staticmethod
    def _hide_cell(c: dict) -> None:
        c["bg"].opacity = 0
        c["today"].opacity = 0
        c["num"].text = c["load"].text = c["more"].text = ""
        for card, strip, lab, dot in c["cards"]:
            for o in (card, strip, dot):
                o.width = o.height = 0
                o.opacity = 0
            lab.text = ""

    def _place_selection(self) -> None:
        for d, cx, cy, cw, ch in self.cell_geo:
            if d == self.sel:
                t_, b_, l_, r_ = self.sel_out
                for rect, (x, y, w, h) in zip((t_, b_, l_, r_), (
                        (cx, cy + ch - 2, cw + 1, 2), (cx, cy, cw + 1, 2),
                        (cx, cy, 2, ch), (cx + cw - 1, cy, 2, ch))):
                    rect.x, rect.y, rect.width, rect.height = x, y, w, h
                    rect.opacity = 255
                return
        for rect in self.sel_out:
            rect.opacity = 0

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -2000
        self._layout()

    # --------------------------------------------------------------- ecrã

    def enter(self) -> None:
        self._load()
        entries = self.data.get("by_day", {}).get(self.sel, [])
        done = [e for e in entries if not e.planned]
        plan = [e for e in entries if e.planned]
        bits = [self.sel.strftime("%d/%m/%Y")]
        if done:
            bits.append(tr("{n} feita", "{n} done", n=1) if len(done) == 1 else
                        tr("{n} feitas", "{n} done", n=len(done)))
        if plan:
            bits.append(tr("{n} planeada", "{n} planned", n=1) if len(plan) == 1 else
                        tr("{n} planeadas", "{n} planned", n=len(plan)))
        self.chrome.set(tr("Calendário", "Calendar"), " · ".join(bits),
                        tr("←/→ dia · ↑↓ semana · PgUp/PgDn mês · T hoje · Enter abrir",
                           "←/→ day · ↑↓ week · PgUp/PgDn month · T today · Enter open"))
        self.list.set_items([Item(tr("Abrir o dia", "Open the day"), action=self.open_day)])

    def open_day(self) -> None:
        self.app.push(DayScreen(self.app, self.sel))

    def on_key(self, symbol: int, modifiers: int) -> bool:
        moves = {key.LEFT: -1, key.RIGHT: 1, key.UP: -7, key.DOWN: 7}
        if symbol in moves:
            self.go_day(self.sel + timedelta(days=moves[symbol]))
            return True
        if symbol in (key.PAGEUP, key.BRACKETLEFT):
            self.go_month(-1)
            return True
        if symbol in (key.PAGEDOWN, key.BRACKETRIGHT):
            self.go_month(1)
            return True
        if symbol == key.T:
            self.go_day(date.today())
            return True
        if symbol in (key.ENTER, key.RETURN, key.SPACE):
            self.open_day()
            return True
        return super().on_key(symbol, modifiers)

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.app.pop()
            return True
        for i, (bx, by, bw, bh) in enumerate(getattr(self, "nav_geo", [])):
            if bx <= x <= bx + bw and by <= y <= by + bh:
                if i == 1:
                    self.go_day(date.today())
                else:
                    self.go_month(-1 if i == 0 else 1)
                return True
        for d, cx, cy, cw, ch in self.cell_geo:
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                if d == self.sel:
                    self.open_day()
                else:
                    self.go_day(d)
                return True
        return False

    def agent_data(self) -> dict:
        by_day = self.data.get("by_day", {})
        return {"mes": f"{self.year}-{self.month:02d}", "dias": {
            d.isoformat(): [{"desporto": e.sport, "treino": e.title, "planeado": e.planned,
                             "duracao_s": round(e.seconds), "carga": e.load,
                             "feedback": e.verdict} for e in es]
            for d, es in by_day.items()}}

    def draw(self) -> None:
        self.chrome.draw()
        self.batch.draw()
        if self.back_button is not None:
            self.back_button.draw()


# ======================================================================= dia


class DayScreen(Screen):
    """Um dia: o que foi feito (com o feedback) e o que está planeado."""

    def __init__(self, app, day: date):
        super().__init__(app)
        self.day = day

    def enter(self) -> None:
        a = self.app
        done = cv.sessions_between(a.db, self.day, self.day)
        plan = cv.planned_between(a.db, self.day, self.day, done)
        items: list[Item] = []
        for e in done:
            bits = [x for x in (f"{e.distance_m / 1000:.1f} km" if e.distance_m else "",
                                tr("carga {l}", "load {l}", l=f"{e.load:.0f}") if e.load else "",
                                e.verdict) if x]
            items.append(Item(f"✓ {sport_label(e.sport)} · {e.title}", value=hms(e.seconds),
                              detail=" · ".join(bits) or tr("sem feedback", "no feedback"),
                              action=lambda ee=e: self._open_session(ee), data=("done", e)))
        for e in plan:
            from velo.core import objectives as ob
            b = ob.workout_brief(a.db, e.sport, e.workout_id)
            items.append(Item(("✓ " if e.done else "◷ ") + tr("Planeado", "Planned")
                              + f" · {sport_label(e.sport)} · {e.title}",
                              value=hms(e.seconds) if e.seconds else "",
                              detail=(b.goal if b else "") + ("  ·  " + tr(
                                  "Del tira do plano", "Del removes it") if not e.done else ""),
                              action=lambda ee=e: self._open_plan(ee), data=("plan", e)))
        items.append(Item(tr("+ Planear um treino neste dia", "+ Plan a workout on this day"),
                          action=lambda: a.push(PlanSportPicker(a, self.day))))
        wd = cv.weekday_name(self.day.weekday())
        self.chrome.set(f"{wd}, {self.day.day} {cv.month_name(self.day.month)} {self.day.year}",
                        tr("Feitas: {a} · planeadas: {b}", "Done: {a} · planned: {b}",
                           a=len(done), b=len(plan)),
                        tr("Enter abrir · Del tirar do plano · Esc voltar",
                           "Enter open · Del remove from plan · Esc back"))
        self.list.set_items(items, keep_index=True)

    def _open_session(self, e: cv.Entry) -> None:
        a = self.app
        if e.kind == "ride":
            from velo.ui.app import RideDetailScreen
            a.push(RideDetailScreen(a, e.id))
        elif e.kind == "row":
            from velo.ui.rowing_screens import RowSessionDetail
            a.push(RowSessionDetail(a, e.id))
        elif e.kind == "endurance":
            from velo.ui.endurance_screens import EnduranceDetail
            a.push(EnduranceDetail(a, e.id))
        else:
            from velo.ui.strength_analysis_screens import StrengthAnalysisScreen
            a.push(StrengthAnalysisScreen(a, e.id))

    def _open_plan(self, e: cv.Entry) -> None:
        a = self.app
        if not e.workout_id:
            return
        if e.sport == "cycling":
            from velo.ui.brief import CyclingBrief
            a.push(CyclingBrief(a, e.workout_id))
        elif e.sport == "rowing":
            from velo.ui.rowing_screens import RowWorkoutPreview
            a.push(RowWorkoutPreview(a, e.workout_id))
        elif e.sport in ("running", "swimming"):
            from velo.ui.endurance_screens import EndurancePreview
            a.push(EndurancePreview(a, e.sport, e.workout_id))
        else:
            from velo.ui.sport_screens import StrengthPreview
            a.push(StrengthPreview(a, e.workout_id))

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol in (key.DELETE, key.BACKSPACE) and item is not None and \
                isinstance(item.data, tuple) and item.data[0] == "plan":
            cv.plan_remove(self.app.db, item.data[1].id)
            self.app.message(tr("Tirado do plano", "Removed from the plan"))
            self.enter()
            return True
        return super().on_key(symbol, modifiers)


class PlanSportPicker(Screen):
    def __init__(self, app, day: date):
        super().__init__(app)
        self.day = day

    def enter(self) -> None:
        a = self.app
        items = [Item(sport_label(s), action=lambda k=s: a.replace(PlanWorkoutPicker(
            a, self.day, k))) for s in ("cycling", "rowing", "running", "swimming", "gym")]
        self.chrome.set(tr("Planear um treino", "Plan a workout"),
                        self.day.strftime("%d/%m/%Y"), self.footer())
        self.list.set_items(items, keep_index=True)


def workouts_for(db, sport: str) -> list[tuple[str, str, str]]:
    """[(id, nome, nota)] dos treinos guardados de um desporto."""
    if sport == "cycling":
        return [(w["id"], w["name"], w["description"] or "") for w in db.workouts()]
    if sport == "rowing":
        from velo.core import rowing as rw
        return [(w["id"], w["name"], w["description"] or "") for w in rw.workouts(db)]
    if sport in ("running", "swimming"):
        from velo.core import endurance as en
        return [(w["id"], w["name"], w["description"] or "") for w in en.workouts(db, sport)]
    from velo.core import gym
    out = []
    for m in gym.modalities():
        if m.laps:
            continue
        for w in gym.workouts(db, m.key):
            out.append((w["id"], w["name"], m.name))
    return out


class PlanWorkoutPicker(Screen):
    def __init__(self, app, day: date, sport: str):
        super().__init__(app)
        self.day, self.sport = day, sport

    def enter(self) -> None:
        a = self.app
        items = [Item(name, detail=note, action=lambda w=wid, n=name: self._pick(w, n))
                 for wid, name, note in workouts_for(a.db, self.sport)]
        if not items:
            items = [Item(tr("Ainda não há treinos guardados neste desporto",
                             "No saved workouts in this sport yet"), enabled=False)]
        self.chrome.set(tr("Planear · {s}", "Plan · {s}", s=sport_label(self.sport)),
                        self.day.strftime("%d/%m/%Y"), self.footer())
        self.list.set_items(items, keep_index=True)

    def _pick(self, wid: str, name: str) -> None:
        cv.plan_add(self.app.db, self.day, self.sport, wid, name)
        self.app.message(tr("«{n}» planeado para {d}", "«{n}» planned for {d}", n=name,
                            d=self.day.strftime("%d/%m")))
        self.app.pop()
