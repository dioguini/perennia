"""Editor do ecrã da sessão, um por desporto: arrasta as métricas para onde
as queres ver.

Em cima, uma miniatura do ecrã da sessão (as 6 caixas do ciclismo, ou a
grelha de quadrados do remo, da corrida, da natação e do ginásio); em baixo,
todas as métricas que o desporto conhece.

Rato: arrasta uma métrica da paleta para um lugar; arrasta um lugar para
outro para trocar (nas caixas do ciclismo, para mudar de caixa ou de ordem);
arrasta o título de uma caixa para outra para trocar as caixas.
Teclado: setas escolhem o lugar · Enter escolhe a métrica numa lista ·
,/. trocam pela anterior/seguinte · Del esvazia · R repõe · Tab página.
Grava sozinho a cada mudança.
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import layouts as lay
from velo.core import sports as sp
from velo.core.i18n import tr
from velo.gfx import theme as _theme
from velo.gfx.compat import label as make_label
from velo.ui.app import Screen
from velo.ui.widgets import Item

SPORTS = ("cycling", "rowing", "running", "swimming", "gym")

EXAMPLES = {
    "pace": "2:05", "avg_pace": "2:08", "best_pace": "1:58", "split500": "2:04", "spm": "24",
    "avg_spm": "23", "power": "212 W", "avg_power": "198 W", "max_power": "402 W",
    "pct_ftp": "88 %", "wkg": "2,9", "distance": "3,42 km", "time": "14:20", "strokes": "331",
    "dps": "10,3 m", "hr": "148", "avg_hr": "141", "max_hr": "166", "zone": "Z3",
    "hr_zone": "Z3", "resistance": "6", "kcal": "182", "kcal_h": "760", "load": "21",
    "lap": "2 · 1:12", "lap_time": "1:12", "lap_dist": "500 m", "lap_pace": "2:03",
    "last_lap_pace": "2:06", "step_left": "2:40", "target": "2:05–2:10", "target_delta": "+3 s",
    "projected": "8:12", "finish": "28:40", "cur_pace": "5:10", "speed": "11,6 km/h",
    "lengths": "24 × 25 m", "sets": "7/16", "reps": "64", "volume": "2 340 kg",
    "exercise": "3/6", "session_time": "24:10", "phase_time": "0:45", "jps": "620 J",
}


def sport_title(sport: str) -> str:
    return tr("Ginásio", "Gym") if sport == "gym" else sp.name(sport)


class LayoutSportPicker(Screen):
    def enter(self) -> None:
        a = self.app
        items = []
        for s in SPORTS:
            sh = lay.shape(s)
            what = (tr("6 caixas de métricas, com a estrada 3D", "6 metric boxes over the 3D road")
                    if sh.kind == "boxes" else
                    tr("{n} quadrados", "{n} tiles", n=sh.groups * sh.per_group))
            items.append(Item(sport_title(s), detail=what,
                              action=lambda k=s: a.push(LayoutEditor(a, k))))
        self.chrome.set(tr("Ecrã da sessão", "Session screen"),
                        tr("Escolhe o desporto e arrasta as métricas para onde as queres ver",
                           "Pick the sport and drag metrics where you want them"), self.footer())
        self.list.set_items(items, keep_index=True)


class LayoutEditor(Screen):
    AGENT = False
    MAX_CHIPS = 60

    def __init__(self, app, sport: str):
        self.sport = sport
        self.sh = lay.shape(sport)
        self.TABBED = self.sh.kind == "grid" and self.sh.groups > 1
        super().__init__(app)
        self.groups = lay.load(app.db, sport)
        self.cat = lay.catalog(sport)
        self.sel: tuple[int, int] | None = (0, 0)
        self.drag: dict | None = None
        self._armed_reset = False
        self.list.y = -2000
        self._build()
        self._layout()
        self._refresh()

    def tab_labels(self) -> list[str]:
        return list(self.sh.group_names) if self.TABBED else []

    @property
    def page(self) -> int:
        return self.tab if self.TABBED else 0

    # ------------------------------------------------------------ construção

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        dim, txt = _theme.rgba(P.dim), _theme.rgba(P.text)
        self.frame_out = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b)
        self.frame = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.bg, batch=b)
        self.clock = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.header, batch=b)
        self.clock_l = make_label("", font_size=9, bold=True, color=_theme.rgba(P.header_text),
                                  anchor_x="center", anchor_y="center", batch=b)
        self.prev_title = make_label("", font_size=11, bold=True, color=txt, anchor_y="top",
                                     batch=b)
        self.prev_note = make_label("", font_size=9, color=dim, anchor_x="right", anchor_y="top",
                                    batch=b)
        n_slots = self.sh.groups * self.sh.per_group if self.sh.kind == "boxes" else \
            self.sh.per_group
        self.slots = []
        for _ in range(n_slots):
            self.slots.append({
                "out": pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                "bg": pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b),
                "cap": make_label("", font_size=8, color=dim, anchor_y="top", batch=b),
                "val": make_label("", font_size=14, bold=True, color=txt, anchor_y="top",
                                  batch=b)})
        self.box_heads = []
        if self.sh.kind == "boxes":
            for _ in range(self.sh.groups):
                self.box_heads.append((
                    pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel2, batch=b),
                    make_label("", font_size=9, bold=True, color=_theme.rgba(P.accent),
                               anchor_y="center", batch=b)))
        self.pal_title = make_label("", font_size=11, bold=True, color=txt, anchor_y="top",
                                    batch=b)
        self.chips = [(pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.border, batch=b),
                       pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.panel, batch=b),
                       make_label("", font_size=9, color=txt, anchor_x="center",
                                  anchor_y="center", batch=b))
                      for _ in range(self.MAX_CHIPS)]
        self.ghost = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.accent, batch=b)
        self.ghost.opacity = 0
        self.ghost_l = make_label("", font_size=9, bold=True,
                                  color=_theme.rgba(P.accent_text), anchor_x="center",
                                  anchor_y="center", batch=b)
        self.mark = pyglet.shapes.Rectangle(0, 0, 1, 3, color=P.accent, batch=b)
        self.mark.opacity = 0

    # --------------------------------------------------------------- medidas

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        top = self.content_top(h) + 14
        left, right = 48, w - 48
        if self.sh.kind == "boxes":
            prev_h = 24 + 26 + self.sh.per_group * 22 + 14
        else:
            prev_h = 24 + 58 + self.sh.rows * 66 + 10
        prev_h = min(prev_h, int((top - 70) * 0.58))
        self.prev_rect = (left, top - prev_h, right - left, prev_h)
        self.pal_top = top - prev_h - 16

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -2000
        self._layout()
        self._refresh()

    def on_tab(self) -> None:
        self.sel = (self.page, 0)

    # -------------------------------------------------------------- conteúdo

    def enter(self) -> None:
        self.chrome.set(tr("Ecrã da sessão · {s}", "Session screen · {s}",
                           s=sport_title(self.sport)),
                        tr("Arrasta as métricas da paleta para o ecrã · grava sozinho",
                           "Drag metrics from the palette onto the screen · saves itself"),
                        tr("Setas lugar · Enter escolher · ,/. trocar · Del esvaziar · "
                           "R repor · Esc voltar", "Arrows slot · Enter choose · ,/. swap · "
                           "Del clear · R reset · Esc back"))
        self.list.set_items([])
        self._refresh()

    def _refresh(self) -> None:
        P = _theme.P
        x, y, w, h = self.prev_rect
        self.frame_out.x, self.frame_out.y = x - 1, y - 1
        self.frame_out.width, self.frame_out.height = w + 2, h + 2
        self.frame.x, self.frame.y, self.frame.width, self.frame.height = x, y, w, h
        self.prev_title.text = tr("Pré-visualização do ecrã da sessão", "Session screen preview")
        self.prev_title.x, self.prev_title.y = x + 12, y + h - 8
        self.prev_note.text = tr("o tempo total fica sempre ao centro, em cima",
                                 "total time always stays top centre")
        self.prev_note.x, self.prev_note.y = x + w - 12, y + h - 10
        cw = 200
        self.clock.x, self.clock.y = x + w / 2 - cw / 2, y + h - 54
        self.clock.width, self.clock.height = cw, 24
        self.clock_l.text = tr("TEMPO TOTAL  0:00", "TOTAL TIME  0:00")
        self.clock_l.x, self.clock_l.y = x + w / 2, y + h - 42
        self.slot_geo: list[tuple[int, int, float, float, float, float]] = []
        if self.sh.kind == "boxes":
            self._draw_boxes()
        else:
            self._draw_grid()
        self._draw_palette()
        _ = P

    def _style_slot(self, s: dict, sel: bool, empty: bool) -> None:
        P = _theme.P
        s["out"].color = P.accent if sel else P.border
        s["bg"].color = P.select if sel else (P.bg if empty else P.panel)

    def _draw_grid(self) -> None:
        x, y, w, h = self.prev_rect
        g = self.page
        cols, rows = self.sh.cols, self.sh.rows
        gap = 8
        gx, gy_top = x + 14, y + h - 66
        tw = (w - 28 - gap * (cols - 1)) / cols
        th = min(58, (gy_top - (y + 10) - gap * (rows - 1)) / rows)
        for i, s in enumerate(self.slots[:cols * rows]):
            r, c = divmod(i, cols)
            sx, sy = gx + c * (tw + gap), gy_top - (r + 1) * th - r * gap
            key_ = self.groups[g][i] if i < len(self.groups[g]) else None
            sel = self.sel == (g, i)
            s["out"].x, s["out"].y, s["out"].width, s["out"].height = sx - 1, sy - 1, tw + 2, th + 2
            s["bg"].x, s["bg"].y, s["bg"].width, s["bg"].height = sx, sy, tw, th
            self._style_slot(s, sel, key_ is None)
            s["cap"].text = (lay.label(self.sport, key_).upper()[:int(tw / 6)] if key_
                             else tr("VAZIO", "EMPTY"))
            s["cap"].x, s["cap"].y = sx + 8, sy + th - 6
            s["val"].text = EXAMPLES.get(key_, "—") if key_ else tr("arrasta aqui", "drop here")
            s["val"].font_size = 14 if key_ else 10
            s["val"].color = _theme.rgba(_theme.P.text if key_ else _theme.P.faint)
            s["val"].x, s["val"].y = sx + 8, sy + th - 22
            self.slot_geo.append((g, i, sx, sy, tw, th))

    def _draw_boxes(self) -> None:
        from velo.core import boxes as bx
        from velo.core import metrics
        x, y, w, h = self.prev_rect
        n = self.sh.groups
        gap = 8
        bw = (w - 28 - gap * (n - 1)) / n
        head_y = y + h - 66
        row_h = min(22, (head_y - 24 - (y + 8)) / self.sh.per_group)
        names = bx.load(self.app.db, metrics.REGISTRY)
        self.head_geo = []
        for gi in range(n):
            bx0 = x + 14 + gi * (bw + gap)
            hr, hl = self.box_heads[gi]
            hr.x, hr.y, hr.width, hr.height = bx0, head_y - 22, bw, 22
            hl.text = bx.title(names, gi)[:int(bw / 6.5)]
            hl.x, hl.y = bx0 + 6, head_y - 11
            self.head_geo.append((gi, bx0, head_y - 22, bw, 22))
            for k in range(self.sh.per_group):
                s = self.slots[gi * self.sh.per_group + k]
                sy = head_y - 24 - (k + 1) * row_h
                group = self.groups[gi]
                key_ = group[k] if k < len(group) else None
                is_next = k == len(group)
                sel = self.sel == (gi, k)
                visible = key_ is not None or is_next
                for part in ("out", "bg"):
                    s[part].opacity = 255 if visible else 0
                s["out"].x, s["out"].y = bx0 - 1, sy
                s["out"].width, s["out"].height = bw + 2, row_h
                s["bg"].x, s["bg"].y, s["bg"].width, s["bg"].height = bx0, sy + 1, bw, row_h - 2
                self._style_slot(s, sel, key_ is None)
                if key_:
                    s["cap"].text = ""
                    s["val"].text = metrics.REGISTRY[key_].label[:int(bw / 6.2)] \
                        if key_ in metrics.REGISTRY else key_
                    s["val"].font_size = 9
                    s["val"].color = _theme.rgba(_theme.P.text)
                elif is_next and len(group) < self.sh.per_group:
                    s["cap"].text = ""
                    s["val"].text = tr("+ arrasta aqui", "+ drop here")
                    s["val"].font_size = 8
                    s["val"].color = _theme.rgba(_theme.P.faint)
                else:
                    s["cap"].text = s["val"].text = ""
                s["val"].x, s["val"].y = bx0 + 6, sy + row_h - 4
                if visible:
                    self.slot_geo.append((gi, k, bx0, sy, bw, row_h))

    def _draw_palette(self) -> None:
        P = _theme.P
        w = self.app.window.width
        x0, x1 = 48, w - 48
        self.pal_title.text = tr("Métricas · arrasta para o ecrã (as que já estão no ecrã ficam "
                                 "realçadas)", "Metrics · drag onto the screen (the ones already "
                                 "shown are highlighted)")
        self.pal_title.x, self.pal_title.y = x0, self.pal_top
        used = {m for g in self.groups for m in g if m}
        cx, cy = x0, self.pal_top - 22
        ch, gap = 24, 6
        self.chip_geo = []
        bottom = 64
        for i, (o, r, l) in enumerate(self.chips):
            if i >= len(self.cat):
                o.opacity = r.opacity = 0
                l.text = ""
                continue
            k, name = self.cat[i]
            text = name if len(name) <= 24 else name[:23] + "…"
            cw = len(text) * 6.3 + 18
            if cx + cw > x1:
                cx, cy = x0, cy - ch - gap
            if cy - ch < bottom:
                o.opacity = r.opacity = 0
                l.text = ""
                continue
            on = k in used
            o.opacity = r.opacity = 255
            o.x, o.y, o.width, o.height = cx - 1, cy - ch - 1, cw + 2, ch + 2
            r.x, r.y, r.width, r.height = cx, cy - ch, cw, ch
            r.color = P.select if on else P.panel
            o.color = P.accent if on else P.border
            l.text = text
            l.color = _theme.rgba(P.accent if on else P.text)
            l.x, l.y = cx + cw / 2, cy - ch / 2
            self.chip_geo.append((k, cx, cy - ch, cw, ch))
            cx += cw + gap

    # ------------------------------------------------------------- mexer

    def _slot_at(self, x: float, y: float):
        for g, i, sx, sy, tw, th in self.slot_geo:
            if sx <= x <= sx + tw and sy <= y <= sy + th:
                return g, i
        return None

    def _head_at(self, x: float, y: float):
        for gi, hx, hy, hw, hh in getattr(self, "head_geo", []):
            if hx <= x <= hx + hw and hy <= y <= hy + hh:
                return gi
        return None

    def _chip_at(self, x: float, y: float):
        for k, cx, cy, cw, ch in self.chip_geo:
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                return k
        return None

    def _find(self, metric: str):
        for g, grp in enumerate(self.groups):
            for i, m in enumerate(grp):
                if m == metric:
                    return g, i
        return None

    def place(self, metric: str, g: int, i: int) -> None:
        """Põe a métrica no lugar (g, i). Se já estava no ecrã, sai de onde estava."""
        old = self._find(metric)
        if self.sh.kind == "boxes":
            grp = self.groups[g]
            if old is not None:
                og, oi = old
                self.groups[og].pop(oi)
                if og == g and oi < i:
                    i -= 1
            i = max(0, min(i, len(grp)))
            if len(grp) >= self.sh.per_group and (old is None or old[0] != g):
                self.app.message(tr("Esta caixa já tem 7 métricas", "This box already has 7"))
                if old is not None:                     # devolve-a ao sítio
                    self.groups[old[0]].insert(old[1], metric)
                return
            grp.insert(i, metric)
            self.sel = (g, i)
        else:
            if old is not None:
                og, oi = old
                self.groups[og][oi] = self.groups[g][i] if (og, oi) != (g, i) else metric
            self.groups[g][i] = metric
            self.sel = (g, i)
        self._changed()

    def swap(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        (ga, ia), (gb, ib) = a, b
        if self.sh.kind == "boxes":
            if ia >= len(self.groups[ga]):
                return
            m = self.groups[ga].pop(ia)
            if ga == gb and ia < ib:
                ib -= 1
            if gb != ga and len(self.groups[gb]) >= self.sh.per_group:
                self.groups[ga].insert(ia, m)
                self.app.message(tr("Esta caixa já tem 7 métricas", "This box already has 7"))
                return
            self.groups[gb].insert(min(ib, len(self.groups[gb])), m)
            self.sel = (gb, min(ib, len(self.groups[gb]) - 1))
        else:
            self.groups[ga][ia], self.groups[gb][ib] = self.groups[gb][ib], self.groups[ga][ia]
            self.sel = b
        self._changed()

    def swap_boxes(self, a: int, b: int) -> None:
        from velo.core import boxes as bx
        from velo.core import metrics
        if a == b:
            return
        self.groups[a], self.groups[b] = self.groups[b], self.groups[a]
        names = bx.load(self.app.db, metrics.REGISTRY)
        names[a]["name"], names[b]["name"] = names[b]["name"], names[a]["name"]
        bx.save(self.app.db, [{"name": n["name"], "metrics": self.groups[i]}
                              for i, n in enumerate(names)])
        self._changed()

    def clear(self, g: int, i: int) -> None:
        if self.sh.kind == "boxes":
            if i < len(self.groups[g]):
                self.groups[g].pop(i)
        else:
            self.groups[g][i] = None
        self._changed()

    def _changed(self) -> None:
        lay.save(self.app.db, self.sport, self.groups)
        self._refresh()

    # --------------------------------------------------------------- rato

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.app.pop()
            return True
        if self.tabs is not None:
            i = self.tabs.hit(x, y)
            if i is not None:
                self.set_tab(i)
                return True
        k = self._chip_at(x, y)
        if k is not None:
            self.drag = {"what": "chip", "metric": k, "moved": False}
            return True
        hd = self._head_at(x, y)
        if hd is not None:
            self.drag = {"what": "box", "g": hd, "moved": False}
            return True
        s = self._slot_at(x, y)
        if s is not None:
            self.sel = s
            g, i = s
            grp = self.groups[g]
            if i < len(grp) and grp[i]:
                self.drag = {"what": "slot", "from": s, "moved": False}
            self._refresh()
            return True
        return False

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        d = self.drag
        if d is None:
            return False
        d["moved"] = True
        if d["what"] == "chip":
            text = lay.label(self.sport, d["metric"])
        elif d["what"] == "slot":
            g, i = d["from"]
            text = lay.label(self.sport, self.groups[g][i])
        else:
            text = tr("Caixa {n}", "Box {n}", n=d["g"] + 1)
        text = text[:22]
        gw = len(text) * 6.3 + 20
        self.ghost.x, self.ghost.y, self.ghost.width, self.ghost.height = x - gw / 2, y - 12, gw, 24
        self.ghost.opacity = 210
        self.ghost_l.text = text
        self.ghost_l.x, self.ghost_l.y = x, y
        target = self._slot_at(x, y)
        if target is not None:
            for g, i, sx, sy, tw, th in self.slot_geo:
                if (g, i) == target:
                    self.mark.x, self.mark.y, self.mark.width = sx, sy + th - 2, tw
                    self.mark.opacity = 255
        else:
            self.mark.opacity = 0
        return True

    def on_release(self, x: int, y: int) -> bool:
        d, self.drag = self.drag, None
        self.ghost.opacity = 0
        self.ghost_l.text = ""
        self.mark.opacity = 0
        if d is None:
            return False
        if d["what"] == "box":
            hd = self._head_at(x, y)
            if hd is not None and d["moved"]:
                self.swap_boxes(d["g"], hd)
            return True
        target = self._slot_at(x, y)
        if d["what"] == "chip":
            if target is not None:
                self.place(d["metric"], *target)
            elif not d["moved"] and self.sel is not None:
                self.place(d["metric"], *self.sel)      # clique: põe no lugar escolhido
            return True
        if d["what"] == "slot" and target is not None and d["moved"] and target != d["from"]:
            self.swap(d["from"], target)
        return True

    # ------------------------------------------------------------- teclado

    def _slots_on_page(self) -> list[tuple[int, int]]:
        return [(g, i) for g, i, *_ in self.slot_geo]

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.tabs is not None and symbol == key.TAB:
            self.set_tab(self.tab + (-1 if modifiers & key.MOD_SHIFT else 1))
            return True
        if symbol == key.ESCAPE:
            self.app.pop()
            return True
        if self.sel is None:
            self.sel = (self.page, 0)
        g, i = self.sel
        if symbol in (key.LEFT, key.RIGHT, key.UP, key.DOWN):
            self._move(symbol)
            return True
        if symbol in (key.DELETE, key.BACKSPACE):
            self.clear(g, i)
            return True
        if symbol in (key.PERIOD, key.COMMA, key.PLUS, key.MINUS, key.EQUAL):
            step = 1 if symbol in (key.PERIOD, key.PLUS, key.EQUAL) else -1
            keys_ = [k for k, _ in self.cat]
            cur = self.groups[g][i] if i < len(self.groups[g]) else None
            nxt = keys_[(keys_.index(cur) + step) % len(keys_)] if cur in keys_ else keys_[0]
            if self.sh.kind == "boxes" and cur is not None:
                self.groups[g][i] = nxt if nxt not in self.groups[g] else cur
                self._changed()
            else:
                self.place(nxt, g, i)
            return True
        if symbol in (key.ENTER, key.RETURN):
            self.app.push(MetricPicker(self.app, self, g, i))
            return True
        if symbol == key.R:
            if self._armed_reset:
                lay.reset(self.app.db, self.sport)
                self.groups = lay.load(self.app.db, self.sport)
                self._armed_reset = False
                self.app.message(tr("Ecrã reposto", "Screen reset"))
                self._refresh()
            else:
                self._armed_reset = True
                self.app.message(tr("R outra vez para repor o ecrã de origem",
                                    "R again to reset the screen"))
            return True
        return super().on_key(symbol, modifiers)

    def _move(self, symbol: int) -> None:
        g, i = self.sel
        if self.sh.kind == "boxes":
            n = self.sh.groups
            if symbol == key.LEFT:
                g = (g - 1) % n
            elif symbol == key.RIGHT:
                g = (g + 1) % n
            elif symbol == key.UP:
                i = max(0, i - 1)
            else:
                i += 1
            i = min(i, len(self.groups[g]), self.sh.per_group - 1)
        else:
            cols, total = self.sh.cols, self.sh.cols * self.sh.rows
            step = {key.LEFT: -1, key.RIGHT: 1, key.UP: -cols, key.DOWN: cols}[symbol]
            i = (i + step) % total
            g = self.page
        self.sel = (g, i)
        self._refresh()

    def agent_data(self) -> dict:
        return {"desporto": self.sport, "ecra": self.groups}

    def draw(self) -> None:
        self.chrome.draw()
        if self.tabs is not None:
            self.tabs.draw()
        self.batch.draw()
        if self.back_button is not None:
            self.back_button.draw()


class MetricPicker(Screen):
    """Escolher a métrica de um lugar pelo teclado (alternativa a arrastar)."""

    def __init__(self, app, editor: LayoutEditor, g: int, i: int):
        super().__init__(app)
        self.editor, self.g, self.i = editor, g, i

    def enter(self) -> None:
        used = {m for grp in self.editor.groups for m in grp if m}
        items = [Item(name, value="✓" if k in used else "",
                      action=lambda kk=k: self._pick(kk)) for k, name in self.editor.cat]
        self.chrome.set(tr("Escolher a métrica", "Choose a metric"),
                        sport_title(self.editor.sport), self.footer())
        self.list.set_items(items, keep_index=True)

    def _pick(self, k: str) -> None:
        self.app.pop()
        self.editor.place(k, self.g, self.i)
