"""Seletores em janela: uma lista com pesquisa (para escolher entre muitas
opções sem andar às setas) e um calendário (para todas as datas).

* `ChoicePopup` — as opções numa lista; escreve-se logo para filtrar e
  Enter escolhe. Abre-se com Enter numa linha de escolha (`cyc:` nos
  editores e as escolhas das Definições). As setas ←/→ continuam a dar para
  passar à seguinte (útil nos números).
* `DatePickerPopup` — o mês em grelha: ←/→ um dia, ↑/↓ uma semana,
  PgUp/PgDn um mês, H hoje, Enter escolhe; também se pode escrever a data
  (AAAA-MM-DD ou DD/MM/AAAA) e um clique num dia escolhe-o.

`probe_choices` descobre as opções de uma linha de escolha sem as conhecer:
passa por elas uma a uma (como as setas fariam) até voltar ao início.
"""
from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, timedelta

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core.i18n import tr
from velo.gfx.compat import label as make_label
from velo.ui.app import PopupMixin, Screen
from velo.ui.widgets import ACCENT, ACCENT_TEXT, BORDER, DIM, PANEL, SELECT, TEXT, Item

MAX_OPTIONS = 80


# ================================================================ escolhas


def _value_of(screen, data) -> str | None:
    for it in screen.list.all_items or screen.list.items:
        if it.data == data:
            return it.value
    return None


def probe_choices(screen, data, step_fn) -> list[str] | None:
    """As opções de uma linha de escolha, a começar na atual. `step_fn()`
    passa à seguinte (como →). Volta sempre ao ponto de partida; None se a
    escolha não der a volta (não é uma lista fechada)."""
    keep = {k: getattr(screen, k) for k in ("dirty",) if k in vars(screen)}
    start = _value_of(screen, data)
    if start is None:
        return None
    labels = [start]
    back = False
    for _ in range(MAX_OPTIONS):
        step_fn()
        screen.enter()
        v = _value_of(screen, data)
        if v == start:
            back = True
            break
        labels.append(v if v is not None else "")
    if not back:
        # não deu a volta: anda para trás até ao início
        for _ in range(len(labels)):
            step_fn(-1)
        screen.enter()
        labels = None
    for k, v in keep.items():
        setattr(screen, k, v)
    return labels


def open_choices(screen, item, step_fn) -> bool:
    """Enter numa linha de escolha: a lista com pesquisa (o Enter não muda o
    valor sozinho). Devolve True se tratou a tecla."""
    data = item.data
    options = probe_choices(screen, data, step_fn)
    if options is None:
        return False

    def pick(k: int) -> None:
        for _ in range(k):
            step_fn()
        screen.enter()
    screen.app.push(ChoicePopup(screen.app, item.label, options, 0, pick))
    return True


class ChoicePopup(PopupMixin, Screen):
    """As opções numa lista; o que se escreve filtra logo; Enter escolhe."""

    W, H = 640, 560
    SEARCH_ENTER_PICKS = True

    def __init__(self, app, title: str, options: list[str], current: int, on_pick):
        super().__init__(app)
        self.title_text = title
        self.options = options
        self.current = current
        self.on_pick = on_pick
        self.back_button = None
        self._init_popup()
        self.search_focus(True)

    def enter(self) -> None:
        items = [Item(opt or "—", value="✓" if k == self.current else "",
                      action=lambda k=k: self._pick(k), data=k)
                 for k, opt in enumerate(self.options)]
        items.append(Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop))
        self.chrome.set(self.title_text,
                        tr("Escreve para filtrar · ↑↓ · Enter escolhe · Esc fecha",
                           "Type to filter · ↑↓ · Enter picks · Esc closes"), "")
        self.list.set_items(items, keep_index=True)
        self.list.select_data(self.current)

    def _pick(self, k: int) -> None:
        self.app.pop()
        self.on_pick(k)

    def search_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.ESCAPE and not self.search_box.text:
            self.app.pop()
            return True
        return super().search_key(symbol, modifiers)


class MultiChoicePopup(PopupMixin, Screen):
    """Várias opções numa lista com pesquisa: Enter marca/desmarca, OK aplica (Esc cancela).
    Para as modalidades e o material de um exercício."""

    W, H = 640, 580
    SEARCH_ENTER_PICKS = True

    def __init__(self, app, title: str, options: list[tuple[str, str]], selected: list[str],
                 on_done, min_one: bool = False):
        super().__init__(app)
        self.title_text = title
        self.options = list(options)
        self.selected = list(selected)
        self.on_done = on_done
        self.min_one = min_one
        self.back_button = None
        self._init_popup()
        self.search_focus(True)

    def enter(self) -> None:
        items = [Item(("✓ " if k in self.selected else "    ") + label, data=k,
                      action=lambda k=k: self._toggle(k))
                 for k, label in self.options]
        items.append(Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop))
        items.append(Item("OK", button=True, primary=True, action=self._ok))
        self.chrome.set(self.title_text,
                        tr("Escreve para filtrar · Enter marca ou desmarca · OK aplica",
                           "Type to filter · Enter ticks or unticks · OK applies"), "")
        self.list.set_items(items, keep_index=True)

    def _toggle(self, k: str) -> None:
        if k in self.selected:
            if self.min_one and len(self.selected) == 1:
                return
            self.selected.remove(k)
        else:
            self.selected.append(k)
        self.enter()

    def _ok(self) -> None:
        self.app.pop()
        self.on_done(list(self.selected))

    def search_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.ESCAPE and not self.search_box.text:
            self.app.pop()
            return True
        return super().search_key(symbol, modifiers)


# ================================================================== datas


def parse_date(text: str | None) -> date | None:
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


MONTHS_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
             "setembro", "outubro", "novembro", "dezembro")
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December")


class DatePickerPopup(PopupMixin, Screen):
    """O seletor de datas: um mês em grelha."""

    W, H = 520, 520
    SEARCH = False

    def __init__(self, app, title: str, current: str | date | None, on_pick,
                 max_day: date | None = None, min_day: date | None = None):
        super().__init__(app)
        if isinstance(current, str):
            current = parse_date(current)
        self.sel = current or date.today()
        self.title_text = title
        self.on_pick = on_pick
        self.max_day, self.min_day = max_day, min_day
        self.typed = ""
        self.back_button = None
        self._init_popup()
        b = self.batch = pyglet.graphics.Batch()
        self.month_l = make_label("", font_size=15, bold=True, color=TEXT, anchor_x="center",
                                  anchor_y="center", batch=b)
        self.heads = [make_label("", font_size=10, bold=True, color=DIM, anchor_x="center",
                                 anchor_y="center", batch=b) for _ in range(7)]
        self.cells = [(pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL, batch=b),
                       make_label("", font_size=12, color=TEXT, anchor_x="center",
                                  anchor_y="center", batch=b)) for _ in range(42)]
        self._rects: list[tuple[float, float, float, float, date]] = []

    def _clamp(self, d: date) -> date:
        if self.max_day and d > self.max_day:
            return self.max_day
        if self.min_day and d < self.min_day:
            return self.min_day
        return d

    def enter(self) -> None:
        months = MONTHS_PT if tr("pt", "en") == "pt" else MONTHS_EN
        sub = tr("←/→ dia · ↑/↓ semana · PgUp/PgDn mês · H hoje · escreve a data · Enter",
                 "←/→ day · ↑/↓ week · PgUp/PgDn month · H today · type the date · Enter")
        if self.typed:
            sub = tr("A escrever: {t}", "Typing: {t}", t=self.typed)
        self.chrome.set(self.title_text, sub, "")
        self.month_l.text = f"{months[self.sel.month - 1].capitalize()} {self.sel.year}"
        self.list.set_items([
            Item(tr("Hoje", "Today"), button=True, action=self._today),
            Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop),
            Item(tr("Escolher {d}", "Pick {d}", d=self.sel.strftime("%d/%m/%Y")), button=True,
                 primary=True, action=self._choose)], keep_index=True)
        self.list.index = 2
        self.list._sync()
        self._layout()

    def _layout(self) -> None:
        p = self.popup
        days = tr("S T Q Q S S D", "M T W T F S S").split()
        gx, gw = p.x + 30, p.w - 60
        top = p.y + p.h - 110
        self.month_l.x, self.month_l.y = p.x + p.w / 2, top
        cw = gw / 7
        ch = min(44.0, (top - 30 - (p.y + 70)) / 7)
        for i, lab in enumerate(self.heads):
            lab.text = days[i]
            lab.x, lab.y = gx + cw * i + cw / 2, top - 26
        first = date(self.sel.year, self.sel.month, 1)
        start = first - timedelta(days=first.weekday())
        self._rects = []
        today = date.today()
        for k, (bg, lab) in enumerate(self.cells):
            d = start + timedelta(days=k)
            r, c = divmod(k, 7)
            x, y = gx + c * cw, top - 46 - (r + 1) * ch
            bg.x, bg.y, bg.width, bg.height = x + 2, y + 2, cw - 4, ch - 4
            lab.text = str(d.day)
            lab.x, lab.y = x + cw / 2, y + ch / 2
            out = (self.max_day and d > self.max_day) or (self.min_day and d < self.min_day)
            if d == self.sel:
                bg.color, lab.color = ACCENT[:3], ACCENT_TEXT
            else:
                bg.color = SELECT if d == today else PANEL
                lab.color = DIM if (d.month != self.sel.month or out) else TEXT
            self._rects.append((x, y, cw, ch, d))

    def go(self, d: date) -> None:
        self.sel = self._clamp(d)
        self.typed = ""
        self.enter()

    def _today(self) -> None:
        self.go(date.today())

    def _choose(self) -> None:
        d = self.sel
        self.app.pop()
        self.on_pick(d.isoformat())

    def on_key(self, symbol: int, modifiers: int) -> bool:
        moves = {key.LEFT: -1, key.RIGHT: 1, key.UP: -7, key.DOWN: 7}
        if symbol in moves:
            self.go(self.sel + timedelta(days=moves[symbol]))
            return True
        if symbol in (key.PAGEUP, key.PAGEDOWN):
            step = -1 if symbol == key.PAGEUP else 1
            m = self.sel.month - 1 + step
            y = self.sel.year + m // 12
            m = m % 12 + 1
            day = min(self.sel.day, _cal.monthrange(y, m)[1])
            self.go(date(y, m, day))
            return True
        if symbol == key.H and not self.typed:
            self._today()
            return True
        if symbol == key.BACKSPACE and self.typed:
            self.typed = self.typed[:-1]
            self.enter()
            return True
        if symbol in (key.ENTER, key.RETURN):
            if self.typed:
                d = parse_date(self.typed)
                if d is None:
                    self.app.message(tr("Data inválida: usa AAAA-MM-DD ou DD/MM/AAAA.",
                                        "Invalid date: use YYYY-MM-DD or DD/MM/YYYY."))
                    return True
                self.sel = self._clamp(d)
            self._choose()
            return True
        if symbol == key.ESCAPE:
            self.app.pop()
            return True
        return super().on_key(symbol, modifiers)

    def on_text(self, text: str) -> bool:
        chars = "".join(c for c in text if c.isdigit() or c in "-/.")
        if chars:
            self.typed = (self.typed + chars)[:10]
            d = parse_date(self.typed)
            if d is not None:
                self.sel = self._clamp(d)
            self.enter()
        return True

    def on_mouse(self, x: int, y: int) -> bool:
        for rx, ry, rw, rh, d in self._rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.sel = self._clamp(d)
                self._choose()
                return True
        return super().on_mouse(x, y)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


def pick_date(app, title: str, current, on_pick, **kw) -> None:
    app.push(DatePickerPopup(app, title, current, on_pick, **kw))
