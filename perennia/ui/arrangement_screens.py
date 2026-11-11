"""Disposição do ecrã da sessão: arrasta os painéis (caixas de métricas,
voltas, classificação, plano, gráficos, tabelas) para onde os queres, e
muda-lhes o tamanho pelo canto de baixo, à direita.

Um separador por desporto (ciclismo, remo, corrida, natação). Em cima, o
ecrã da sessão em ponto pequeno, com a grelha; em baixo, os painéis que não
estão no ecrã — arrasta um para o pôr (ou clica nele). Um painel não pode
pisar outro.

Teclado: , e . escolhem o painel · setas movem · Shift+setas mudam o
tamanho · Del tira do ecrã · Enter põe o painel escolhido da paleta.
Guarda-se com **Guardar**; **Cancelar** volta ao gravado; **Repor** põe a
disposição de origem.
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from perennia.core import screen_layout as sl
from perennia.core import sports as sp
from perennia.core.i18n import tr
from perennia.gfx import theme as _theme
from perennia.gfx.compat import label as make_label
from perennia.ui.app import Screen
from perennia.ui.widgets import Item

HANDLE = 14             # o canto que muda o tamanho


class ArrangementEditor(Screen):
    AGENT = False
    TABBED = True

    def __init__(self, app, sport: str = "cycling"):
        self.sport = sport if sport in sl.SPORTS else "cycling"
        super().__init__(app)
        self.drafts: dict[str, dict] = {}
        self.saved: dict[str, str] = {}
        self.drag: dict | None = None
        self.sel: str | None = None
        self.pal_sel = 0
        self.tab = 0                  # um só separador: o do desporto de onde se veio
        if self.tabs is not None:
            self.tabs.select(0)
        self._load_sport(self.sport)

    def tab_labels(self) -> list[str]:
        return [sp.name(self.sport)]

    def on_tab(self) -> None:
        pass                          # só há o separador do desporto

    def _load_sport(self, sport: str) -> None:
        self.sport = sport
        if sport not in self.drafts:
            cur = sl.load(self.app.db, sport)
            self.saved[sport] = repr(cur)
            self.drafts[sport] = dict(cur)
        self.panels = self.drafts[sport]
        on = [k for k, r in self.panels.items() if r]
        self.sel = on[0] if on else None
        self.pal_sel = 0
        self.drag = None
        self._build()
        self._refresh()

    # ------------------------------------------------------------- rascunho

    @property
    def dirty(self) -> bool:
        return any(repr(d) != self.saved.get(s) for s, d in self.drafts.items())

    def has_unsaved(self) -> bool:
        return self.dirty

    def on_save(self) -> bool:
        self.save()
        return True

    def save(self) -> None:
        for s, d in self.drafts.items():
            if repr(d) != self.saved.get(s):
                sl.save(self.app.db, s, d)
                self.drafts[s] = dict(sl.load(self.app.db, s))
                self.saved[s] = repr(self.drafts[s])
        self.panels = self.drafts[self.sport]
        self.app.message(tr("Disposição guardada", "Layout saved"))
        self.enter()

    def cancel(self) -> None:
        self.drafts.clear()
        self._load_sport(self.sport)
        self.enter()

    def reset(self) -> None:
        self.drafts[self.sport] = sl.defaults(self.sport)
        self.panels = self.drafts[self.sport]
        on = [k for k, r in self.panels.items() if r]
        self.sel = on[0] if on else None
        self.enter()

    # ------------------------------------------------------------ construção

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        self.frame_out = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b)
        self.frame = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.bg, batch=b)
        self.header = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.header, batch=b)
        self.header_l = make_label("", font_size=9, bold=True, color=_theme.rgba(P.header_text),
                                   anchor_x="center", anchor_y="center", batch=b)
        self.grid_v = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.grid, batch=b)
                       for _ in range(sl.COLS - 1)]
        self.grid_h = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.grid, batch=b)
                       for _ in range(sl.ROWS - 1)]
        self.cards = {}
        for k, _name, _desc in sl.catalog(self.sport):
            self.cards[k] = {
                "out": pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                "bg": pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b),
                "title": make_label("", font_size=11, bold=True, color=_theme.rgba(P.text),
                                    anchor_y="top", batch=b),
                "desc": make_label("", font_size=9, color=_theme.rgba(P.dim), anchor_y="top",
                                   batch=b),
                "size": make_label("", font_size=8, color=_theme.rgba(P.dim),
                                   anchor_x="right", anchor_y="bottom", batch=b),
                "handle": pyglet.shapes.Rectangle(0, 0, HANDLE, HANDLE, color=P.accent,
                                                  batch=b)}
        self.pal_title = make_label("", font_size=11, bold=True, color=_theme.rgba(P.text),
                                    anchor_y="top", batch=b)
        self.chips = [(pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                       pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b),
                       make_label("", font_size=10, color=_theme.rgba(P.text),
                                  anchor_x="center", anchor_y="center", batch=b))
                      for _ in range(len(self.cards))]
        self.ghost = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.accent, batch=b)
        self.ghost.opacity = 0

    # --------------------------------------------------------------- medidas

    def canvas(self) -> tuple[float, float, float, float]:
        """(x, y_baixo, largura, altura) da miniatura do ecrã."""
        w, h = self.app.window.width, self.app.window.height
        top = self.content_top(h) + 14
        bottom = 150
        return 48.0, float(bottom), float(w - 96), float(max(160, top - bottom))

    def grid_area(self) -> tuple[float, float, float, float]:
        x, y, w, h = self.canvas()
        return x, y, w, h - 26                         # o cabeçalho (o tempo) fica em cima

    def cell_of(self, mx: float, my: float) -> tuple[int, int]:
        x, y, w, h = self.grid_area()
        cx = int((mx - x) / (w / sl.COLS))
        cy = int((y + h - my) / (h / sl.ROWS))
        return max(0, min(sl.COLS - 1, cx)), max(0, min(sl.ROWS - 1, cy))

    def hidden(self) -> list[str]:
        return [k for k, _n, _d in sl.catalog(self.sport) if not self.panels.get(k)]

    # -------------------------------------------------------------- conteúdo

    def enter(self) -> None:
        sub = tr("Por guardar: Guardar (Ctrl+S) ou Cancelar", "Unsaved: Save (Ctrl+S) or Cancel") \
            if self.dirty else tr("Arrasta os painéis; o canto de baixo muda o tamanho",
                                  "Drag the panels; the bottom corner resizes")
        self.chrome.set(tr("Disposição do ecrã da sessão", "Session screen layout"), sub,
                        tr(", . painel · setas mover · Shift+setas tamanho · Del tirar · "
                           "Enter pôr", ", . panel · arrows move · Shift+arrows size · "
                           "Del remove · Enter add"))
        self.list.set_items([
            Item(tr("Repor a de origem", "Restore the original"), action=self.reset,
                 button=True),
            Item(tr("Cancelar", "Cancel"), action=self.cancel, button=True, enabled=self.dirty),
            Item(tr("Guardar", "Save"), action=self.save, button=True, primary=True,
                 enabled=self.dirty)], keep_index=True)
        self.list.index = 2 if self.dirty else 0
        self.list._sync()
        self.list.y = -2000
        self._refresh()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -2000
        self._refresh()

    def _refresh(self) -> None:
        P = _theme.P
        x, y, w, h = self.canvas()
        self.frame_out.x, self.frame_out.y = x - 1, y - 1
        self.frame_out.width, self.frame_out.height = w + 2, h + 2
        self.frame.x, self.frame.y, self.frame.width, self.frame.height = x, y, w, h
        self.header.x, self.header.y, self.header.width, self.header.height = x, y + h - 24, w, 24
        self.header_l.text = tr("tempo total e botões (fixos, em cima)",
                                "total time and buttons (fixed, at the top)")
        self.header_l.x, self.header_l.y = x + w / 2, y + h - 12
        gx, gy, gw, gh = self.grid_area()
        for i, r in enumerate(self.grid_v):
            r.x, r.y, r.width, r.height = gx + (i + 1) * gw / sl.COLS, gy, 1, gh
            r.opacity = 90
        for i, r in enumerate(self.grid_h):
            r.x, r.y, r.width, r.height = gx, gy + (i + 1) * gh / sl.ROWS, gw, 1
            r.opacity = 90
        names = {k: (n, d) for k, n, d in sl.catalog(self.sport)}
        for k, c in self.cards.items():
            r = self.panels.get(k)
            if not r:
                for part in ("out", "bg", "handle"):
                    c[part].opacity = 0
                c["title"].text = c["desc"].text = c["size"].text = ""
                continue
            px, py, pw, ph = sl.to_px(r, (gx, gy, gw, gh), gap=4)
            on = k == self.sel
            c["out"].x, c["out"].y, c["out"].width, c["out"].height = px - 2, py - 2, pw + 4, ph + 4
            c["out"].color = P.accent if on else P.border
            c["bg"].x, c["bg"].y, c["bg"].width, c["bg"].height = px, py, pw, ph
            c["bg"].color = P.panel2 if on else P.panel
            for part in ("out", "bg"):
                c[part].opacity = 255
            c["title"].text = _fit(names[k][0], pw - 16, 11)
            c["title"].x, c["title"].y = px + 8, py + ph - 6
            c["desc"].text = _fit(names[k][1], pw - 16, 9) if ph > 40 else ""
            c["desc"].x, c["desc"].y = px + 8, py + ph - 24
            c["size"].text = f"{r[2]} × {r[3]}"
            c["size"].x, c["size"].y = px + pw - HANDLE - 6, py + 3
            c["handle"].x, c["handle"].y = px + pw - HANDLE, py
            c["handle"].opacity = 255 if on else 140
        # paleta: os painéis fora do ecrã
        hid = self.hidden()
        self.pal_title.text = tr("Painéis fora do ecrã (arrasta ou clica para pôr)",
                                 "Panels off the screen (drag or click to add)") if hid else \
            tr("Todos os painéis estão no ecrã · Del tira o escolhido",
               "Every panel is on the screen · Del removes the chosen one")
        self.pal_title.x, self.pal_title.y = x, y - 12
        cx = x
        self._chip_rects = []
        for i, (out, bg, lab) in enumerate(self.chips):
            if i >= len(hid):
                out.opacity = bg.opacity = 0
                lab.text = ""
                continue
            k = hid[i]
            text = names[k][0]
            cw = max(120.0, len(text) * 7.2 + 26)
            out.x, out.y, out.width, out.height = cx - 1, y - 72, cw + 2, 34
            bg.x, bg.y, bg.width, bg.height = cx, y - 71, cw, 32
            out.color = P.accent if i == self.pal_sel else P.border
            out.opacity = bg.opacity = 255
            lab.text = text
            lab.x, lab.y = cx + cw / 2, y - 55
            self._chip_rects.append((k, cx, y - 71, cw, 32))
            cx += cw + 10

    # ----------------------------------------------------------------- rato

    def _panel_at(self, mx: float, my: float):
        gx, gy, gw, gh = self.grid_area()
        for k, r in self.panels.items():
            if not r:
                continue
            px, py, pw, ph = sl.to_px(r, (gx, gy, gw, gh), gap=4)
            if px <= mx <= px + pw and py <= my <= py + ph:
                corner = mx >= px + pw - HANDLE - 4 and my <= py + HANDLE + 4
                return k, corner
        return None, False

    def _chip_at(self, mx: float, my: float):
        for k, x, y, w, h in getattr(self, "_chip_rects", []):
            if x <= mx <= x + w and y <= my <= y + h:
                return k
        return None

    def on_mouse(self, x: int, y: int) -> bool:
        k, corner = self._panel_at(x, y)
        if k is not None:
            self.sel = k
            r = self.panels[k]
            cx, cy = self.cell_of(x, y)
            self.drag = {"what": "resize" if corner else "move", "panel": k,
                         "dx": cx - r[0], "dy": cy - r[1], "moved": False}
            self._refresh()
            return True
        chip = self._chip_at(x, y)
        if chip is not None:
            self.drag = {"what": "add", "panel": chip, "moved": False}
            return True
        return super().on_mouse(x, y)

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        d = self.drag
        if d is None:
            return False
        d["moved"] = True
        k = d["panel"]
        cx, cy = self.cell_of(x, y)
        if d["what"] == "move":
            r = self.panels[k]
            cand = (cx - d["dx"], cy - d["dy"], r[2], r[3])
            cand = (max(0, min(sl.COLS - r[2], cand[0])), max(0, min(sl.ROWS - r[3], cand[1])),
                    r[2], r[3])
            if sl.fits(self.panels, k, cand):
                self.panels[k] = cand
        elif d["what"] == "resize":
            r = self.panels[k]
            mw, mh = sl.min_size(self.sport, k)
            cand = (r[0], r[1], max(mw, cx - r[0] + 1), max(mh, cy - r[1] + 1))
            if sl.fits(self.panels, k, cand):
                self.panels[k] = cand
        else:
            gx, gy, gw, gh = self.grid_area()
            self.ghost.opacity = 120
            self.ghost.x, self.ghost.y, self.ghost.width, self.ghost.height = x - 40, y - 15, 80, 30
        self._refresh()
        return True

    def on_release(self, x: int, y: int) -> bool:
        d = self.drag
        self.drag = None
        self.ghost.opacity = 0
        if d is None:
            return False
        if d["what"] == "add":
            if d["moved"]:
                cx, cy = self.cell_of(x, y)
                self.add(d["panel"], at=(cx, cy))
            else:
                self.add(d["panel"])
            return True
        self.enter()
        return True

    # ---------------------------------------------------------------- ações

    def add(self, k: str, at: tuple[int, int] | None = None) -> bool:
        """Põe um painel no ecrã: onde o largaste, ou no primeiro sítio livre."""
        dflt = sl.defaults(self.sport).get(k)
        mw, mh = sl.min_size(self.sport, k)
        sizes = [(dflt[2], dflt[3])] if dflt else []
        sizes += [(max(mw, 8), max(mh, 4)), (mw, mh)]
        for w, h in sizes:
            if at is not None:
                cand = (max(0, min(sl.COLS - w, at[0])), max(0, min(sl.ROWS - h, at[1])), w, h)
                if sl.fits(self.panels, k, cand):
                    self.panels[k] = cand
                    break
            spot = sl.free_spot(self.panels, w, h, skip=k)
            if spot is not None:
                self.panels[k] = spot
                break
        else:
            if not self._make_room(k):
                self.app.message(tr("Não há espaço livre: tira ou encolhe outro painel.",
                                    "No free space: remove or shrink another panel."))
                return False
        self.sel = k
        self.pal_sel = 0
        self.enter()
        return True

    def _make_room(self, k: str) -> bool:
        """Ecrã cheio: o painel novo fica com a parte de baixo do maior painel."""
        mw, mh = sl.min_size(self.sport, k)
        dflt = sl.defaults(self.sport).get(k)
        want_h = max(mh, min(dflt[3], 6)) if dflt else max(mh, 4)
        best = None
        for other, r in self.panels.items():
            if not r or other == k:
                continue
            omw, omh = sl.min_size(self.sport, other)
            if r[2] >= mw and r[3] - want_h >= omh:
                if best is None or r[2] * r[3] > best[1][2] * best[1][3]:
                    best = (other, r)
        if best is None:
            return False
        other, (x, y, w, h) = best
        self.panels[other] = (x, y, w, h - want_h)
        self.panels[k] = (x, y + h - want_h, w, want_h)
        return True

    def remove(self, k: str | None) -> None:
        if not k or not self.panels.get(k):
            return
        self.panels[k] = None
        on = [p for p, r in self.panels.items() if r]
        self.sel = on[0] if on else None
        self.enter()

    def nudge(self, dx: int, dy: int, resize: bool) -> None:
        k = self.sel
        r = self.panels.get(k) if k else None
        if not r:
            return
        if resize:
            mw, mh = sl.min_size(self.sport, k)
            cand = (r[0], r[1], max(mw, r[2] + dx), max(mh, r[3] + dy))
        else:
            cand = (r[0] + dx, r[1] + dy, r[2], r[3])
        if sl.fits(self.panels, k, cand):
            self.panels[k] = cand
            self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        shift = bool(modifiers & key.MOD_SHIFT)
        moves = {key.LEFT: (-1, 0), key.RIGHT: (1, 0), key.UP: (0, -1), key.DOWN: (0, 1)}
        if symbol in moves:
            dx, dy = moves[symbol]
            self.nudge(dx, dy, shift)
            return True
        on = [k for k, r in self.panels.items() if r]
        if symbol in (key.COMMA, key.PERIOD) and on:
            i = on.index(self.sel) if self.sel in on else 0
            self.sel = on[(i + (1 if symbol == key.PERIOD else -1)) % len(on)]
            self._refresh()
            return True
        if symbol in (key.DELETE, key.BACKSPACE):
            self.remove(self.sel)
            return True
        if symbol in (key.ENTER, key.RETURN):
            hid = self.hidden()
            if hid:
                self.add(hid[self.pal_sel % len(hid)])
                return True
            return super().on_key(symbol, modifiers)
        return super().on_key(symbol, modifiers)

    def agent_data(self) -> dict:
        return {}

    def draw(self) -> None:
        self.chrome.set_footer_limit(self.list.buttons_left)
        self.chrome.draw()
        if self.tabs is not None:
            self.tabs.draw()
        self.batch.draw()
        self.list.draw()
        if self.back_button is not None:
            self.back_button.draw()


def _fit(text: str, width: float, size: int) -> str:
    n = max(3, int(width / (size * 0.6)))
    return text if len(text) <= n else text[:n - 1] + "…"
