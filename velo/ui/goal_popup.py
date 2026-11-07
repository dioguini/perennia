"""A janela onde se escreve o objetivo de um treino ou de um bloco (no
construtor de treinos, em todos os desportos)."""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core.i18n import tr
from velo.gfx.compat import label as make_label
from velo.ui.app import PopupMixin, Screen, SnapshotUnsaved
from velo.ui.widgets import ACCENT, DIM, PANEL, TEXT, Item, set_wrap


class GoalPopup(SnapshotUnsaved, PopupMixin, Screen):
    """Escreve-se o texto (várias linhas se for comprido); Enter guarda, Esc
    cancela (com alterações pergunta primeiro)."""

    W, H = 820, 380
    SEARCH = False

    def __init__(self, app, title: str, subtitle: str, text: str, limit: int, on_save):
        super().__init__(app)
        self.title_text, self.sub_text = title, subtitle
        self.text = text or ""
        self.limit = limit
        self.on_text_saved = on_save
        self.back_button = None
        self._init_popup()
        self.batch = pyglet.graphics.Batch()
        self.box = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=self.batch)
        self.edge = pyglet.shapes.Rectangle(0, 0, 10, 2, color=ACCENT[:3], batch=self.batch)
        self.body = make_label("", font_size=15, color=TEXT, anchor_y="top", batch=self.batch)
        self.counter = make_label("", font_size=11, color=DIM, anchor_x="right",
                                  batch=self.batch)
        self._place_body()
        self.mark_saved()

    def snapshot_state(self):
        return self.text

    def _place_body(self) -> None:
        p = self.popup
        x, y, w, h = p.x + 24, p.y + 84, p.w - 48, p.h - 176
        self.box.x, self.box.y, self.box.width, self.box.height = x, y, w, h
        self.edge.x, self.edge.y, self.edge.width = x, y, w
        set_wrap(self.body, w - 28)
        self.body.x, self.body.y = x + 14, y + h - 12
        self.counter.x, self.counter.y = x + w - 8, y - 18

    def _place(self) -> None:
        super()._place()
        if hasattr(self, "box"):
            self._place_body()

    def enter(self) -> None:
        self.chrome.set(self.title_text, self.sub_text,
                        tr("Escreve · Enter guarda · Esc cancela", "Type · Enter saves · "
                           "Esc cancels"))
        self.list.set_items([
            Item(tr("Cancelar", "Cancel"), button=True, action=self.cancel),
            Item(tr("Guardar", "Save"), button=True, primary=True, action=self.save)])
        self._render()

    def _render(self) -> None:
        self.body.text = self.text + "▏"
        self.counter.text = f"{len(self.text)} / {self.limit}"

    def on_text(self, text: str) -> bool:
        clean = "".join(c for c in text if c.isprintable()).replace("\r", "")
        if clean:
            self.text = (self.text + clean)[:self.limit]
            self._render()
        return True

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.BACKSPACE:
            self.text = self.text[:-1]
            self._render()
            return True
        if symbol in (key.ENTER, key.RETURN):
            self.save()
            return True
        if symbol == key.ESCAPE:
            self.cancel()
            return True
        if symbol in (key.UP, key.DOWN, key.TAB, key.LEFT, key.RIGHT):
            return super().on_key(symbol, modifiers)
        return True               # o resto é texto (o Espaço, J, K… não carregam em botões)

    def on_save(self) -> bool:
        self.save()
        return True

    def save(self) -> None:
        value = self.text.strip()
        self.mark_saved()
        self.app.pop(force=True)
        self.on_text_saved(value)

    def cancel(self) -> None:
        if self.has_unsaved():
            self.app.ask_unsaved(self)
        else:
            self.app.pop(force=True)

    def close_outside(self) -> None:
        self.cancel()

    def draw(self) -> None:
        super().draw()
        self.batch.draw()
