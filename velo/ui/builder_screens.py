"""Construtor de treinos interativo: arrastam-se blocos e vê-se o treino.

- Da paleta (Z1…Z6, Descanso, Rampa, Livre) arrasta-se um bloco para o
  gráfico; largar entre dois blocos põe-no ali. Um clique na paleta junta-o
  a seguir ao bloco escolhido.
- No gráfico: arrastar o meio de um bloco muda-o de lugar; a aresta direita
  muda a duração; a aresta de cima muda a intensidade (numa rampa, a metade
  esquerda muda o início e a direita o fim).
- Os separadores mudam a vista: zonas de potência, FC, RPE ou ritmo. O
  treino é o mesmo; a escala do eixo e os números é que mudam.
- Teclado: ←/→ escolhem o bloco, ↑/↓ intensidade (Shift: ±5), + / −
  duração, D duplica, Del apaga.

Funciona para ciclismo, remo, corrida e natação; cada um guarda no seu
formato (o ciclismo no mesmo de sempre, que se exporta para .zwo/.erg/.mrc/.fit).
"""
from __future__ import annotations

from dataclasses import replace

import pyglet
from pyglet.window import key

from velo.core import intensity as it
from velo.core.blocks import (Block, block_seconds, estimate, load_blocks,  # noqa: F401
                               save_blocks)
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx.compat import label as make_label
from velo.ui.sport_screens import EditScreen
from velo.ui.widgets import ACCENT, DIM, GRID, PANEL, PANEL2, TEXT, Item

SNAP_S = 10
SNAP_M = {"rowing": 50, "running": 100, "swimming": 25, "cycling": 100}
EDGE_PX = 9


PALETTE = (("Z1", 50), ("Z2", 68), ("Z3", 83), ("Z4", 98), ("Z5", 112), ("Z6", 130),
           ("rest", 45), ("ramp", None), ("free", None))


# ================================================================= ecrã


class BlockBuilder(EditScreen):
    TABBED = True
    AGENT = True
    PAL_H = 34

    def __init__(self, app, sport: str, wid: str | None):
        self.sport = sport
        self.modes = list(it.SPORT_MODES.get(sport, ("power", "hr", "rpe")))
        self.wid = wid
        self.name, self.desc, mode, self.blocks = load_blocks(app.db, sport, wid)
        from velo.core import objectives as ob
        saved = ob.stored(app.db, sport, wid)
        self.wgoal = saved.get("goal") or ob.library_goal(self.name)
        for b, g in zip(self.blocks, saved.get("blocks") or []):
            b.goal = (g or {}).get("goal", "") if isinstance(g, dict) else ""
        self.mode = mode if mode in self.modes else self.modes[0]
        self.ctx = it.Context.from_db(app.db, sport)
        self.sel = 0 if self.blocks else -1
        self.drag: dict | None = None
        self.repeat_n = 4
        self.dirty = False
        self._rects: list = []
        self._labels: list = []
        super().__init__(app)
        self.tab = self.modes.index(self.mode)
        if self.tabs is not None:
            self.tabs.select(self.tab)
        b = self.batch = pyglet.graphics.Batch()
        self.canvas_bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
        self.pal = []
        for name, pct in PALETTE:
            r = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL2, batch=b)
            lab = make_label(self._pal_text(name), font_size=10, bold=True, color=TEXT,
                             anchor_x="center", anchor_y="center", batch=b)
            self.pal.append((name, pct, r, lab))
        self.ghost = pyglet.shapes.Rectangle(0, 0, 10, 10, color=ACCENT[:3], batch=b)
        self.ghost.opacity = 0
        self.insert_mark = pyglet.shapes.Rectangle(0, 0, 3, 10, color=ACCENT[:3], batch=b)
        self.insert_mark.opacity = 0
        self.summary = make_label("", font_size=11, color=TEXT, anchor_y="top", batch=b,
                                  multiline=True, width=300)
        self.axis = [make_label("", font_size=9, color=DIM, anchor_x="right",
                                anchor_y="center", batch=b) for _ in range(6)]
        self.grid = [pyglet.shapes.Rectangle(0, 0, 10, 1, color=GRID, batch=b)
                     for _ in range(6)]
        self.time_labels = [make_label("", font_size=9, color=DIM, anchor_x="center",
                                       anchor_y="top", batch=b) for _ in range(7)]
        self.zone_bar = [pyglet.shapes.Rectangle(0, 0, 0, 8, color=c, batch=b)
                         for c in it.ZONE_COLORS]
        self._layout()
        self.redraw()

    # ----------------------------------------------------------- separadores

    def tab_labels(self) -> list[str]:
        modes = getattr(self, "modes", None) or ["power"]
        return [it.mode_name(m) for m in modes]

    def on_tab(self) -> None:
        # mudar de vista não mexe no treino: não conta como alteração
        self.mode = self.modes[self.tab % len(self.modes)]
        for name, pct, r, lab in self.pal:
            lab.text = self._pal_text(name)
        self.redraw()

    def _pal_text(self, name: str) -> str:
        if name in ("rest",):
            return tr("Descanso", "Rest")
        if name == "ramp":
            return tr("Rampa", "Ramp")
        if name == "free":
            return tr("Livre", "Free")
        pct = dict(PALETTE)[name]
        ctx = getattr(self, "ctx", None)
        mode = getattr(self, "mode", "power")
        if ctx is None or mode == "power":
            return name
        return f"{name} · {ctx.short(mode, pct)}"

    # ---------------------------------------------------------------- layout

    def content_top(self, h: int) -> int:
        return int(h * 0.36)

    def _list_width(self, w: int) -> int:
        # a lista ocupa a largura toda, em colunas: assim cabe sem páginas
        return w - 96

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        pal_top = h - 98 - 40
        n = len(self.pal)
        pw = (w - 96 - (n - 1) * 6) / n
        for i, (_n, _p, r, lab) in enumerate(self.pal):
            r.x, r.y, r.width, r.height = 48 + i * (pw + 6), pal_top - self.PAL_H, pw, self.PAL_H
            lab.x, lab.y = r.x + pw / 2, r.y + self.PAL_H / 2
            pct = dict(PALETTE)[_n]
            r.color = it.zone_color(pct)[:3] if pct else PANEL2
        self.cx0, self.cx1 = 96, w - 48
        self.cy1 = pal_top - self.PAL_H - 14
        self.cy0 = self.content_top(h) + 46
        self.canvas_bg.x, self.canvas_bg.y = self.cx0, self.cy0
        self.canvas_bg.width, self.canvas_bg.height = self.cx1 - self.cx0, self.cy1 - self.cy0
        # o resumo (duração, carga, IF) vai no subtítulo; a distribuição pelas
        # zonas é uma barra fina logo por baixo do gráfico, da largura dele
        self.summary.x, self.summary.y = -3000, -3000
        for r in self.zone_bar:
            r.x, r.y, r.height = self.cx0, self.content_top(h) + 20, 6
        self.list.y = self.content_top(h)
        self.list.width = self._list_width(w)
        self.list.set_visible_rows(max(2, (self.content_top(h) - 70) // 38))

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()
        self.redraw()

    # ----------------------------------------------------------- geometria

    def y_max(self) -> float:
        top = max([b.lo or 0 for b in self.blocks] + [b.end_pct or 0 for b in self.blocks] + [0])
        return max(150.0, top + 15)

    def x_of(self, secs: float, total: float) -> float:
        return self.cx0 + (self.cx1 - self.cx0) * secs / max(total, 1.0)

    def y_of(self, pct: float) -> float:
        return self.cy0 + (self.cy1 - self.cy0) * max(0.0, pct) / self.y_max()

    def pct_at(self, y: float) -> float:
        return max(30.0, min(200.0, (y - self.cy0) / max(1, self.cy1 - self.cy0) * self.y_max()))

    def spans(self) -> tuple[list[tuple[float, float]], float]:
        out, t = [], 0.0
        for b in self.blocks:
            s = block_seconds(b, self.ctx)
            out.append((t, t + s))
            t += s
        return out, max(t, 600.0)

    def block_at(self, x: float, y: float) -> tuple[int, str] | None:
        if not (self.cx0 <= x <= self.cx1 and self.cy0 - 4 <= y <= self.cy1 + 4):
            return None
        spans, total = self.spans()
        for i, (a, b) in enumerate(spans):
            x0, x1 = self.x_of(a, total), self.x_of(b, total)
            if x0 <= x <= x1 + 2:
                blk = self.blocks[i]
                if x1 - x <= EDGE_PX:
                    return i, "resize"
                frac = (x - x0) / max(1.0, x1 - x0)
                pct = blk.mid() if blk.lo is None else (
                    blk.lo + ((blk.end_pct or blk.lo) - blk.lo) * frac)
                top = self.y_of(pct)
                if abs(y - top) <= EDGE_PX and blk.lo is not None:
                    return i, ("top_lo" if blk.ramp and frac < 0.5 else
                               "top_hi" if blk.ramp else "top")
                if y <= top + 2:
                    return i, "move"
                return i, "move"
        return None

    def insert_index(self, x: float) -> int:
        spans, total = self.spans()
        for i, (a, b) in enumerate(spans):
            if x < (self.x_of(a, total) + self.x_of(b, total)) / 2:
                return i
        return len(self.blocks)

    # ---------------------------------------------------------------- desenho

    def _rect(self, i: int):
        while len(self._rects) <= i:
            self._rects.append(pyglet.shapes.Rectangle(0, 0, 1, 1, color=(80, 80, 80),
                                                       batch=self.batch))
        return self._rects[i]

    def _label(self, i: int):
        while len(self._labels) <= i:
            self._labels.append(make_label("", font_size=9, bold=True, color=(20, 22, 28, 255),
                                           anchor_x="center", anchor_y="bottom",
                                           batch=self.batch))
        return self._labels[i]

    def redraw(self) -> None:
        spans, total = self.spans()
        n = 0
        nl = 0
        for i, (blk, (a, b)) in enumerate(zip(self.blocks, spans)):
            x0, x1 = self.x_of(a, total), self.x_of(b, total)
            w = max(2.0, x1 - x0 - 2)
            if i == self.sel:                          # contorno do bloco escolhido
                r = self._rect(n)
                n += 1
                top = max(self.y_of(blk.lo or 50), self.y_of(blk.end_pct or blk.lo or 50))
                r.x, r.y, r.width, r.height = x0 - 2, self.cy0 - 3, w + 4, top - self.cy0 + 5
                r.color, r.opacity = ACCENT[:3], 255
            slices = 8 if blk.ramp else 1
            for k in range(slices):
                frac = (k + 0.5) / slices
                if blk.lo is None:
                    pct, color = 50.0, (168, 176, 188)
                else:
                    pct = blk.lo + ((blk.end_pct or blk.lo) - blk.lo) * frac
                    color = it.zone_color(pct)
                r = self._rect(n)
                n += 1
                sw = w / slices
                r.x, r.y = x0 + k * sw, self.cy0
                r.width, r.height = max(1.0, sw + (0.5 if k < slices - 1 else 0)), \
                    max(2.0, self.y_of(pct) - self.cy0)
                r.color, r.opacity = color[:3], 255 if i == self.sel else 225
            if w > 46:
                lab = self._label(nl)
                nl += 1
                dur = hms(blk.dur) if blk.dur_type == "time" else (
                    f"{blk.dur / 1000:g} km" if blk.dur >= 1000 else f"{blk.dur:.0f} m")
                inten = tr("livre", "free") if blk.lo is None else self.ctx.short(
                    self.mode, blk.mid())
                lab.text = dur if w < 80 else f"{dur} · {inten}"
                lab.x, lab.y = x0 + w / 2, self.cy0 + 4
        for r in self._rects[n:]:
            r.opacity = 0
            r.width = 0
        for lab in self._labels[nl:]:
            lab.text = ""
        # eixo: limites das zonas na vista escolhida
        ym = self.y_max()
        for k, (g, lab) in enumerate(zip(self.grid, self.axis)):
            pct = it.ZONE_BOUNDS[k] if k < len(it.ZONE_BOUNDS) else None
            if pct is None or pct > ym:
                g.opacity = 0
                lab.text = ""
                continue
            y = self.y_of(pct)
            g.x, g.y, g.width, g.opacity = self.cx0, y, self.cx1 - self.cx0, 255
            lab.x, lab.y = self.cx0 - 6, y
            lab.text = self.ctx.short(self.mode, pct) if self.mode != "power" else f"{pct}%"
        for k, lab in enumerate(self.time_labels):
            secs = total * k / (len(self.time_labels) - 1)
            lab.text = hms(secs)
            lab.x, lab.y = self.x_of(secs, total), self.cy0 - 4
        est = estimate(self.blocks, self.ctx)
        dist = f" · {est['meters'] / 1000:.2f} km" if est["meters"] else ""
        load = "TSS" if self.sport == "cycling" else tr("Carga", "Load")
        self.summary.text = (
            f"{tr('Duração', 'Duration')} ≈ {hms(est['seconds'])}{dist}\n"
            f"{load} ≈ {est['tss']:.0f} · IF {est['if']:.2f}\n"
            f"{len(self.blocks)} {tr('blocos', 'blocks')} · {tr('vista', 'view')}: "
            f"{it.mode_name(self.mode)}")
        tot = sum(est["zones"]) or 1.0
        x = self.cx0
        width = self.cx1 - self.cx0
        for r, secs in zip(self.zone_bar, est["zones"]):
            r.x = x
            r.width = width * secs / tot
            x += r.width
        self.chrome.subtitle.text = self.summary.text.replace("\n", "  ·  ")

    def draw(self) -> None:
        super().draw()
        self.batch.draw()

    # ------------------------------------------------------------------- lista

    def enter(self) -> None:
        blk = self.blocks[self.sel] if 0 <= self.sel < len(self.blocks) else None
        rows: list[Item] = []
        if blk is not None:
            kinds = {"warmup": tr("Aquecimento", "Warm-up"), "active": tr("Trabalho", "Work"),
                     "rest": tr("Descanso", "Rest"), "cooldown": tr("Retorno à calma",
                                                                   "Cool-down")}
            rows += [
                Item(tr("Bloco {i} de {n} · tipo", "Block {i} of {n} · kind",
                        i=self.sel + 1, n=len(self.blocks)),
                     value=kinds.get(blk.kind, blk.kind), data="cyc:kind"),
            ]
            if self.sport != "cycling":
                rows.append(Item(tr("Duração por", "Duration by"),
                                 value=tr("tempo", "time") if blk.dur_type == "time"
                                 else tr("distância", "distance"), data="cyc:dur_type"))
            dur = hms(blk.dur) if blk.dur_type == "time" else f"{blk.dur:.0f} m"
            rows.append(Item(tr("Duração", "Duration"), value=dur, data="num:dur",
                             detail=tr("arrasta a aresta direita, ou ←/→",
                                       "drag the right edge, or ←/→")))
            if blk.lo is None:
                rows.append(Item(tr("Intensidade", "Intensity"), value=tr("livre", "free"),
                                 data="cyc:free", detail=tr("←/→ dá-lhe um alvo",
                                                            "←/→ gives it a target")))
            else:
                rows.append(Item(tr("Início" if blk.ramp else "Intensidade",
                                    "Start" if blk.ramp else "Intensity"),
                                 value=self.ctx.text(self.mode, blk.lo), data="num:lo",
                                 detail=f"Z{it.zone(blk.lo)} · {it.zone_name(it.zone(blk.lo))}"))
                rows.append(Item(tr("Fim (rampa)", "End (ramp)"),
                                 value=self.ctx.text(self.mode, blk.end_pct) if blk.ramp
                                 else tr("igual", "same"), data="num:hi"))
            if self.sport == "rowing":
                res = blk.extra.get("resistance")
                rows.append(Item(tr("Resistência", "Resistance"),
                                 value=str(res) if res else tr("não mexer", "leave it"),
                                 data="num:resistance"))
            rows += [Item(tr("Objetivo do bloco", "Block goal"), value=(blk.goal or "") + "▏",
                          data="text:goal", detail=tr("O que se treina aqui (aparece na sessão)",
                                                      "What this block trains (shown in session)")),
                     Item(tr("Mensagem", "Cue"), value=(blk.cue or "") + "▏", data="text:cue"),
                     Item(tr("Duplicar o bloco (D)", "Duplicate the block (D)"),
                          action=self._duplicate),
                     Item(tr("Repetir os 2 últimos blocos", "Repeat the last 2 blocks"),
                          value=f"× {self.repeat_n}", data="cyc:repeat", action=self._repeat),
                     Item(tr("Apagar o bloco (Del)", "Delete the block (Del)"),
                          action=self._delete)]
        rows += [Item(tr("Objetivo do treino", "Workout goal"),
                      value=(self.wgoal[:46] + "…" if len(self.wgoal) > 47 else self.wgoal) + "▏",
                      data="text:wgoal", detail=tr("Numa frase: o que este treino deve trabalhar",
                                                   "In one sentence: what this workout trains")),
                 Item(tr("Nome do treino", "Workout name"), value=self.name + "▏",
                      data="text:name"),
                 Item(tr("Guardar", "Save") + (" •" if self.dirty else ""), action=self._save,
                      button=True, primary=True)]
        sport_name = {"cycling": tr("Ciclismo", "Cycling"), "rowing": tr("Remo", "Rowing"),
                      "running": tr("Corrida", "Running"),
                      "swimming": tr("Natação", "Swimming")}[self.sport]
        self.chrome.set(tr("Construtor de treinos", "Workout builder") + f" · {sport_name}",
                        self.summary.text.replace("\n", "  ·  "),
                        tr("Arrasta blocos da paleta · ←/→ bloco · ↑↓ linha · +/− duração · "
                           "D duplicar · Del apagar · Tab vista",
                           "Drag palette blocks · ←/→ block · ↑↓ row · +/− duration · "
                           "D duplicate · Del delete · Tab view"))
        self.list.set_items(rows, keep_index=True)

    @property
    def block(self) -> Block | None:
        return self.blocks[self.sel] if 0 <= self.sel < len(self.blocks) else None

    def changed(self) -> None:
        self.dirty = True
        self.redraw()
        self.enter()

    # ----------------------------------------------------------- campos

    def cycle(self, field: str, step: int) -> None:
        b = self.block
        if field == "repeat":
            self.repeat_n = max(2, min(20, self.repeat_n + (1 if step > 0 else -1)))
            return
        if b is None:
            return
        if field == "kind":
            ks = ["warmup", "active", "rest", "cooldown"]
            b.kind = ks[(ks.index(b.kind) + step) % len(ks)] if b.kind in ks else "active"
        elif field == "dur_type":
            if b.dur_type == "time":
                b.dur_type, b.dur = "distance", float(SNAP_M.get(self.sport, 100) * 4)
            else:
                b.dur_type, b.dur = "time", 300.0
        elif field == "free":
            b.lo = 75.0
        self.dirty = True
        self.redraw()

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        b = self.block
        if b is None:
            return
        if field == "dur":
            self._nudge_duration(steps * (6 if big else 1))
        elif field in ("lo", "hi"):
            cur = (b.lo if field == "lo" else b.end_pct) or 75.0
            v = max(30.0, min(200.0, cur + steps * (5 if big else 1)))
            if field == "lo":
                b.lo = v
                if not b.ramp:
                    b.hi = None
            else:
                b.hi = v
        elif field == "resistance":
            cur = b.extra.get("resistance") or 5
            b.extra["resistance"] = max(1, min(15, cur + steps))
        self.dirty = True
        self.redraw()

    def num_set(self, field: str, value) -> None:
        b = self.block
        if b is None or value is None:
            return
        if field == "dur":
            # escrito: minutos no tempo, metros na distância
            b.dur = max(10.0, value * 60) if b.dur_type == "time" else max(25.0, value)
        elif field in ("lo", "hi"):
            pct = self.ctx.pct_from(self.mode, value) if self.mode != "power" else value
            if field == "lo":
                b.lo = max(30.0, min(200.0, pct))
            else:
                b.hi = max(30.0, min(200.0, pct))
        elif field == "resistance":
            b.extra["resistance"] = max(1, min(15, int(value)))
        self.dirty = True
        self.redraw()

    def text_input(self, field: str, text: str) -> None:
        if field == "name":
            self.name += text
        elif field == "wgoal":
            self.wgoal = (self.wgoal + text)[:300]
        elif field == "goal" and self.block is not None:
            self.block.goal = (self.block.goal + text)[:160]
        elif self.block is not None:
            self.block.cue += text
        self.dirty = True
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "name":
            self.name = self.name[:-1]
        elif field == "wgoal":
            self.wgoal = self.wgoal[:-1]
        elif field == "goal" and self.block is not None:
            self.block.goal = self.block.goal[:-1]
        elif self.block is not None:
            self.block.cue = self.block.cue[:-1]
        self.dirty = True
        self.enter()

    def _nudge_duration(self, steps: int) -> None:
        b = self.block
        if b is None:
            return
        if b.dur_type == "time":
            unit = SNAP_S if b.dur < 120 else 30
            b.dur = max(10.0, b.dur + steps * unit)
        else:
            b.dur = max(25.0, b.dur + steps * SNAP_M.get(self.sport, 100))

    # ----------------------------------------------------------- ações

    def add_block(self, name: str, index: int | None = None) -> None:
        pct = dict(PALETTE).get(name)
        prev = self.block
        dur_type = prev.dur_type if prev is not None and self.sport != "cycling" else \
            ("distance" if self.sport == "swimming" else "time")
        dur = (300.0 if dur_type == "time" else float(SNAP_M.get(self.sport, 100) * 4))
        if name == "rest":
            blk = Block("rest", dur_type, 120.0 if dur_type == "time" else dur / 2, 45)
        elif name == "ramp":
            blk = Block("warmup", dur_type, dur, 55, 95)
        elif name == "free":
            blk = Block("active", dur_type, dur, None)
        else:
            blk = Block("active", dur_type, dur, float(pct))
        i = (self.sel + 1 if self.sel >= 0 else len(self.blocks)) if index is None else index
        self.blocks.insert(i, blk)
        self.sel = i
        self.changed()

    def _duplicate(self) -> None:
        b = self.block
        if b is None:
            return
        self.blocks.insert(self.sel + 1, replace(b, extra=dict(b.extra)))
        self.sel += 1
        self.changed()

    def _repeat(self) -> None:
        if len(self.blocks) < 2:
            return
        pair = self.blocks[-2:]
        for _ in range(self.repeat_n - 1):
            self.blocks += [replace(b, extra=dict(b.extra)) for b in pair]
        self.changed()

    def _delete(self) -> None:
        if self.block is None:
            return
        del self.blocks[self.sel]
        self.sel = min(self.sel, len(self.blocks) - 1)
        self.changed()

    def _save(self) -> None:
        if not self.blocks:
            self.app.message(tr("O treino não tem blocos.", "The workout has no blocks."))
            return
        self.wid = save_blocks(self.app.db, self.sport, self.wid, self.name.strip() or
                               tr("Treino", "Workout"), self.desc, self.mode, self.blocks)
        from velo.core import objectives as ob
        ob.save(self.app.db, self.sport, self.wid, self.wgoal.strip(),
                [{"name": "", "goal": b.goal} for b in self.blocks])
        self.dirty = False
        self.app.message(tr("Treino guardado", "Workout saved"))
        self.enter()

    # ----------------------------------------------------------- teclado

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self._field("text:") is None:
            if symbol in (key.LEFT, key.RIGHT) and self._field("num:") is None and \
                    self._field("cyc:") is None:
                if self.blocks:
                    self.sel = (self.sel + (1 if symbol == key.RIGHT else -1)) % len(self.blocks)
                    self.redraw()
                    self.enter()
                return True
            if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD, key.MINUS, key.NUM_SUBTRACT):
                self._nudge_duration(1 if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD) else -1)
                self.changed()
                return True
            if symbol == key.D:
                self._duplicate()
                return True
        if symbol == key.S and modifiers & key.MOD_CTRL:
            self._save()
            return True
        if self._field("text:") is None and symbol == key.DELETE:
            self._delete()
            return True
        return super().on_key(symbol, modifiers)

    def on_save(self) -> bool:
        self._save()
        return True

    def has_unsaved(self) -> bool:
        return self.dirty

    # --------------------------------------------------------------- rato

    def on_mouse(self, x: int, y: int) -> bool:
        for name, _pct, r, _lab in self.pal:
            if r.x <= x <= r.x + r.width and r.y <= y <= r.y + r.height:
                self.drag = {"what": "palette", "name": name, "x0": x, "y0": y, "moved": False}
                return True
        hit = self.block_at(x, y)
        if hit is not None:
            i, part = hit
            self.sel = i
            b = self.blocks[i]
            self.drag = {"what": part, "i": i, "x0": x, "y0": y, "dur0": b.dur,
                         "moved": False}
            self.redraw()
            self.enter()
            return True
        return super().on_mouse(x, y)

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        d = self.drag
        if d is None:
            return False
        d["moved"] = True
        what = d["what"]
        if what == "palette":
            self.ghost.opacity = 160
            self.ghost.x, self.ghost.y, self.ghost.width, self.ghost.height = x - 30, y - 14, 60, 28
            if self.cx0 <= x <= self.cx1 and self.cy0 <= y <= self.cy1:
                i = self.insert_index(x)
                spans, total = self.spans()
                xm = self.x_of(spans[i][0], total) if i < len(spans) else self.cx1
                self.insert_mark.x, self.insert_mark.y = xm - 1, self.cy0
                self.insert_mark.height = self.cy1 - self.cy0
                self.insert_mark.opacity = 255
            else:
                self.insert_mark.opacity = 0
            return True
        b = self.blocks[d["i"]]
        spans, total = self.spans()
        if what == "resize":
            a, _ = spans[d["i"]]
            secs = max(10.0, (x - self.cx0) / max(1, self.cx1 - self.cx0) * total - a)
            if b.dur_type == "time":
                unit = SNAP_S if secs < 120 else 30
                b.dur = max(10.0, round(secs / unit) * unit)
            else:
                meters = secs * self.ctx.speed_mps(b.mid())
                unit = SNAP_M.get(self.sport, 100)
                b.dur = max(float(unit), round(meters / unit) * unit)
        elif what in ("top", "top_lo", "top_hi"):
            pct = round(self.pct_at(y))
            if what == "top":
                b.lo = float(pct)
                b.hi = None
            elif what == "top_lo":
                b.lo = float(pct)
            else:
                b.hi = float(pct)
        elif what == "move":
            j = self.insert_index(x)
            i = d["i"]
            if j > i:
                j -= 1
            if j != i and 0 <= j < len(self.blocks):
                blk = self.blocks.pop(i)
                self.blocks.insert(j, blk)
                d["i"] = self.sel = j
        self.dirty = True
        self.redraw()
        return True

    def on_release(self, x: int, y: int) -> bool:
        d = self.drag
        self.drag = None
        self.ghost.opacity = 0
        self.insert_mark.opacity = 0
        if d is None:
            return False
        if d["what"] == "palette":
            inside = self.cx0 <= x <= self.cx1 and self.cy0 <= y <= self.cy1
            if d["moved"] and inside:
                self.add_block(d["name"], self.insert_index(x))
            elif not d["moved"]:
                self.add_block(d["name"])
            return True
        self.enter()
        return True

    def agent_data(self) -> dict:
        est = estimate(self.blocks, self.ctx)
        return {"desporto": self.sport, "vista": self.mode,
                "blocos": [{"tipo": b.kind, "duracao": b.dur, "por": b.dur_type,
                            "intensidade_pct": b.lo, "fim_pct": b.end_pct} for b in self.blocks],
                "estimativa": {k: est[k] for k in ("seconds", "meters", "tss", "if")}}
