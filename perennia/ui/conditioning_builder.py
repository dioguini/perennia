"""O construtor de treinos de Conditioning (ronda 26).

Um treino de Conditioning junta **blocos de vários desportos** — ciclismo, passadeira,
remo, ginásio — e descansos, numa só página:

* em cima, a **faixa dos blocos**: um retângulo por bloco, da cor do desporto e da largura
  do tempo dele. **Arrasta-se com o rato** para mudar o bloco de lugar; um clique escolhe-o;
* por baixo, a **lista**: o nome do treino, as tags (as automáticas e as tuas), os blocos e
  os botões. Num bloco: **Enter** abre-o no construtor do desporto dele, **D** duplica,
  **Alt+↑/↓** (ou Shift+←/→) muda-o de lugar, **Del** tira-o;
* **+ Adicionar bloco**: escolhes o desporto (uma lista), e depois se é **Manual ou ERG**
  (ciclismo, passadeira, remo) ou a **modalidade** (ginásio). Abre-se o construtor desse
  desporto noutra página, com o botão **«Adicionar bloco a treino de Conditioning»** em baixo.
  O descanso junta-se logo (o tempo muda-se com ←/→ na linha dele).

Grava-se como um plano de Conditioning (`lap_plans`); começar abre a sessão por voltas, com
um bloco por volta planeada (ver perennia.core.conditioning).
"""
from __future__ import annotations

import pyglet
from pyglet.window import key

from perennia.core import conditioning as cnd
from perennia.core import laps_session as ls
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.gfx import theme as _theme
from perennia.gfx.compat import label as make_label
from perennia.ui.sport_screens import EditScreen
from perennia.ui.widgets import ROW_H, Item, fit_text

STRIP_H = 64                 # a altura da faixa dos blocos
MIN_BLOCK_W = 34             # um bloco muito curto continua a ver-se e a agarrar-se
MAX_SHAPES = 40              # blocos desenhados na faixa (o resto fica no fim, a «+n»)


def sport_color(sport: str):
    P = _theme.P
    return {"cycling": P.accent, "running": P.good, "rowing": P.warn, "gym": P.bad,
            "rest": P.panel2}.get(sport, P.panel2)


def open_new(app, draft: bool = False) -> None:
    app.push(ConditioningBuilder(app, None, draft=draft))


class ConditioningBuilder(EditScreen):
    """Ver o módulo."""
    SEARCH = False
    LIST_TOP_GAP = 24

    def __init__(self, app, pid: str | None, draft: bool = False,
                 items: list[dict] | None = None):
        super().__init__(app)
        self.pid = pid
        self.draft = draft
        p = ls.plan(app.db, pid) if pid else None
        self.name = p["name"] if p else (tr("Conditioning livre", "Free conditioning")
                                         if draft else tr("Treino de Conditioning",
                                                          "Conditioning workout"))
        self.blocks: list[dict] = cnd.from_items(p["items"] if p else (items or []))
        from perennia.core import tags as tags_mod
        self.wtags = tags_mod.workout_tags(app.db, "strength", pid)
        from perennia.core import objectives as ob
        self.wnotes = ob.notes(app.db, "conditioning", pid) if pid else ""
        self.sel = 0 if self.blocks else -1
        self.drag: dict | None = None
        self._saved_state = self._state()
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        self.strip_bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=P.panel, batch=b)
        self.rects = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.panel2, batch=b)
                      for _ in range(MAX_SHAPES)]
        self.sel_box = pyglet.shapes.Rectangle(0, 0, 0, 3, color=P.text, batch=b)
        self.mark = pyglet.shapes.Rectangle(0, 0, 3, 10, color=P.accent, batch=b)
        self.mark.opacity = 0
        self.labels = [make_label("", font_size=9, bold=True, color=_theme.rgba(P.text),
                                  anchor_x="center", anchor_y="center", batch=b)
                       for _ in range(MAX_SHAPES)]
        self.subs = [make_label("", font_size=8, color=_theme.rgba(P.text),
                                anchor_x="center", anchor_y="center", batch=b)
                     for _ in range(MAX_SHAPES)]
        self.empty = make_label("", font_size=11, color=_theme.rgba(P.dim), anchor_x="center",
                                anchor_y="center", batch=b)
        self._geo: list[tuple[float, float]] = []      # (x0, x1) de cada bloco na faixa
        self._layout()

    # ------------------------------------------------------------- estado

    def _state(self) -> str:
        return repr((self.name, self.blocks, self.wtags, self.wnotes))

    def has_unsaved(self) -> bool:
        return not self.draft and self._state() != self._saved_state

    def on_save(self) -> bool:
        if self.blocks:
            self._save()
        return True

    # ------------------------------------------------------------ geometria

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        top = h - 98 - 34 - 6
        self.sx0, self.sx1 = 48.0, float(w - 48)
        self.sy1 = float(top)
        self.sy0 = self.sy1 - STRIP_H
        self.strip_bg.x, self.strip_bg.y = self.sx0, self.sy0
        self.strip_bg.width, self.strip_bg.height = self.sx1 - self.sx0, STRIP_H
        lv = self.list
        lv.x, lv.width = 48, w - 96
        lv.row_h = ROW_H
        list_top = self.sy0 - self.LIST_TOP_GAP
        lv.y = list_top - ROW_H / 2
        rows = max(3, int((list_top - 70) // ROW_H))
        lv.set_visible_rows(rows)
        self.redraw()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()

    def _spans(self) -> list[float]:
        """A duração de cada bloco — calculada uma vez por mudança (não a cada fotograma)."""
        sig = repr(self.blocks)
        if getattr(self, "_spans_sig", None) != sig:
            self._ctx_cache: dict = getattr(self, "_ctx_cache", {})
            self._spans_val = [max(1.0, cnd.seconds(self.app.db, b, self._ctx_cache))
                               for b in self.blocks]
            self._spans_sig = sig
        return self._spans_val

    def redraw(self) -> None:
        P = _theme.P
        secs = self._spans()
        n = min(len(secs), MAX_SHAPES)
        width = self.sx1 - self.sx0
        gap = 3.0
        # larguras pelo tempo, com um mínimo para os blocos curtos
        total = sum(secs[:n]) or 1.0
        free = max(1.0, width - gap * max(0, n - 1))
        ws = [max(MIN_BLOCK_W, free * s / total) for s in secs[:n]]
        scale = free / sum(ws) if ws and sum(ws) > free else 1.0
        ws = [x * scale for x in ws]
        self._geo = []
        x = self.sx0
        for i in range(MAX_SHAPES):
            r, lab, sub = self.rects[i], self.labels[i], self.subs[i]
            if i >= n:
                r.width = r.height = 0
                lab.text = sub.text = ""
                continue
            b = self.blocks[i]
            col = sport_color(b["sport"])
            r.x, r.y, r.width, r.height = x, self.sy0 + 4, ws[i], STRIP_H - 8
            r.color = col
            r.opacity = 255 if b["sport"] != "rest" else 200
            fg = _theme.rgba(P.text) if b["sport"] == "rest" else \
                _theme.rgba(P.accent_text)
            lab.color = sub.color = fg
            lab.x = sub.x = x + ws[i] / 2
            lab.y, sub.y = self.sy0 + STRIP_H / 2 + 8, self.sy0 + STRIP_H / 2 - 9
            name = cnd.sport_name(b["sport"])
            if b["sport"] in cnd.ERG_SPORTS and b.get("control") == "erg":
                name += " · ERG"
            lab.text = fit_text(name, ws[i] - 8, 9, True)
            sub.text = fit_text(hms(secs[i]), ws[i] - 8, 8)
            self._geo.append((x, x + ws[i]))
            x += ws[i] + gap
        if 0 <= self.sel < len(self._geo):
            a, z = self._geo[self.sel]
            self.sel_box.x, self.sel_box.y, self.sel_box.width = a, self.sy0, z - a
            self.sel_box.opacity = 255
        else:
            self.sel_box.opacity = 0
        self.empty.x, self.empty.y = (self.sx0 + self.sx1) / 2, self.sy0 + STRIP_H / 2
        self.empty.text = "" if self.blocks else fit_text(
            tr("Ainda sem blocos · + Adicionar bloco (em baixo)",
               "No blocks yet · + Add block (below)"), width - 20, 11)

    def draw(self) -> None:
        super().draw()
        self.batch.draw()

    # ---------------------------------------------------------------- lista

    def _auto_tags(self) -> list[str]:
        from perennia.core import tags as tags_mod
        return tags_mod.builder_auto_tags("conditioning",
                                          sports=cnd.sports_used(self.blocks))

    def enter(self) -> None:
        db = self.app.db
        auto = self._auto_tags()
        rows = [Item(tr("Nome", "Name"), value=self.name + "▏", data="text:name"),
                Item(tr("Tags", "Tags"),
                     value=" · ".join(auto + self.wtags),
                     detail=tr("as automáticas vêm dos blocos · Enter junta as tuas",
                               "the automatic ones come from the blocks · Enter adds yours"),
                     action=self._edit_tags)]
        from perennia.ui.goal_popup import notes_item
        rows.append(notes_item(self.wnotes, self._edit_notes))
        total = sum(self._spans()) if self.blocks else 0.0
        rows.append(Item(tr("Blocos · {n} · ≈ {t}", "Blocks · {n} · ≈ {t}", n=len(self.blocks),
                            t=hms(total)), header=True))
        spans = self._spans()
        for i, b in enumerate(self.blocks):
            secs = spans[i]
            label = f"{i + 1}. {cnd.sport_name(b['sport'])}"
            if b.get("name") and b["name"] != cnd.sport_name(b["sport"]):
                label += f" · {b['name']}"
            if b["sport"] == "rest":
                rows.append(Item(label, value=hms(secs), data=f"num:{i}",
                                 detail=tr("←/→ ±15 s (Shift ±1 min) · escreve minutos",
                                           "←/→ ±15 s (Shift ±1 min) · type minutes")))
            else:
                rows.append(Item(label, value=hms(secs), data=f"blk:{i}",
                                 detail=cnd.summary(db, b) + tr(" · Enter edita",
                                                                " · Enter edits"),
                                 action=lambda i=i: self._edit(i)))
        rows.append(Item(tr("+ Adicionar bloco", "+ Add block"), action=self._add,
                         detail=tr("ciclismo, passadeira, remo, ginásio ou descanso",
                                   "cycling, treadmill, rowing, gym or rest")))
        if 0 <= self.sel < len(self.blocks):
            rows += [Item(tr("Duplicar o bloco {i} (D)", "Duplicate block {i} (D)",
                             i=self.sel + 1), action=self._duplicate),
                     Item(tr("Tirar o bloco {i} (Del)", "Remove block {i} (Del)",
                             i=self.sel + 1), action=self._remove)]
        rows += [Item(tr("▶ Começar", "▶ Start"), button=True, action=self._start)]
        if not self.draft or self.pid:
            rows.append(Item(tr("Guardar", "Save") + (" •" if self.has_unsaved() else ""),
                             button=True, primary=True, action=self._save))
        else:
            rows.append(Item(tr("Guardar na lista", "Save to the list"), button=True,
                             primary=True, action=self._save))
        if self.pid:
            rows.append(Item(tr("Apagar", "Delete"), button=True, action=self._delete))
        by = cnd.total_by_sport(db, self.blocks, getattr(self, "_ctx_cache", None))
        sub = " · ".join(f"{cnd.sport_name(s)} {hms(v)}" for s, v in by.items())
        self.chrome.set(tr("Treino de Conditioning", "Conditioning workout"),
                        fit_text(sub or tr("Junta blocos de vários desportos",
                                           "Put blocks of several sports together"),
                                 self.app.window.width - 96, 13),
                        tr("Arrasta os blocos na faixa · Enter edita · D duplica · Alt+↑↓ muda "
                           "de lugar · Del tira · Ctrl+S guarda",
                           "Drag blocks on the strip · Enter edits · D duplicates · Alt+↑↓ "
                           "moves · Del removes · Ctrl+S saves"))
        self.list.set_items(rows, keep_index=True)
        self._sync_sel()
        self.redraw()

    def _row_block(self) -> int | None:
        it = self.list.selected
        d = getattr(it, "data", None)
        if isinstance(d, str) and (d.startswith("blk:") or d.startswith("num:")):
            try:
                return int(d.split(":", 1)[1])
            except ValueError:
                return None
        return None

    def _sync_sel(self) -> None:
        i = self._row_block()
        if i is not None and i != self.sel:
            self.sel = i
            self.redraw()

    def _select(self, i: int) -> None:
        self.sel = i
        for k, it in enumerate(self.list.items):
            if it.data in (f"blk:{i}", f"num:{i}"):
                self.list.index = k
                break
        self.enter()

    # ------------------------------------------------------------ ações

    def changed(self, sel: int | None = None) -> None:
        if sel is not None:
            self.sel = sel
            self._select(sel)
        else:
            self.enter()

    def _edit_tags(self) -> None:
        from perennia.ui.tag_popup import WorkoutTagsPopup

        def done(tags: list[str]) -> None:
            self.wtags = tags
            self.enter()
        self.app.push(WorkoutTagsPopup(self.app, self.name, self.wtags, done,
                                       auto=self._auto_tags()))

    def _add(self) -> None:
        from perennia.ui.pickers import ChoicePopup
        names = [cnd.sport_name(s) for s in cnd.SPORTS]
        self.app.push(ChoicePopup(self.app, tr("Que desporto tem o bloco?",
                                               "Which sport is the block?"),
                                  names, -1, lambda k: self._add_sport(cnd.SPORTS[k])))

    def _insert_at(self) -> int:
        return (self.sel + 1) if 0 <= self.sel < len(self.blocks) else len(self.blocks)

    def _add_sport(self, sport: str) -> None:
        at = self._insert_at()

        def put(block: dict) -> None:
            self.blocks.insert(at, block)
            self.changed(at)
        if sport == "rest":
            put(cnd.new_block("rest"))
            return
        if sport == "gym":
            from perennia.core import gym
            mods = [m for m in gym.modalities() if not m.laps]
            from perennia.ui.pickers import ChoicePopup

            def mod_pick(k: int) -> None:
                from perennia.ui.strength_builder_screens import StrengthBuilder
                self.app.push(StrengthBuilder(self.app, mods[k].key, None, cond_cb=put))
            self.app.push(ChoicePopup(self.app, tr("Que modalidade de ginásio?",
                                                   "Which gym modality?"),
                                      [m.name for m in mods], -1, mod_pick))
            return
        self._ask_control(sport, put)

    def _ask_control(self, sport: str, put) -> None:
        """Manual ou ERG — como ao criar um treino desse desporto."""
        from perennia.core import workout_meta as wm
        from perennia.ui.app import ConfirmScreen
        from perennia.ui.builder_screens import BlockBuilder

        def go(control: str) -> None:
            self.app.pop()
            self.app.push(BlockBuilder(self.app, sport, None, control=control, cond_cb=put))
        self.app.push(ConfirmScreen(
            self.app, tr("{s}: bloco Manual ou ERG?", "{s}: Manual or ERG block?",
                         s=cnd.sport_name(sport)),
            tr("ERG: {e}.  Manual: {m}.", "ERG: {e}.  Manual: {m}.",
               e=wm.control_help(sport, "erg"), m=wm.control_help(sport, "manual")),
            [(tr("Cancelar", "Cancel"), self.app.pop), (tr("Manual", "Manual"),
                                                         lambda: go("manual")),
             ("ERG", lambda: go("erg"))], default=2, buttons=True, cancel=self.app.pop))

    def _edit(self, i: int) -> None:
        if not (0 <= i < len(self.blocks)):
            return
        b = self.blocks[i]
        self.sel = i

        def put(block: dict) -> None:
            self.blocks[i] = block
            self.changed(i)
        if b["sport"] == "gym":
            from perennia.ui.strength_builder_screens import StrengthBuilder
            self.app.push(StrengthBuilder(self.app, b.get("modality") or "strength", None,
                                          cond_cb=put, cond_block=b))
        elif b["sport"] in cnd.ENDURANCE:
            from perennia.ui.builder_screens import BlockBuilder
            self.app.push(BlockBuilder(self.app, b["sport"], None,
                                       control=b.get("control") or "manual", cond_cb=put,
                                       cond_block=b))

    def _duplicate(self) -> None:
        if 0 <= self.sel < len(self.blocks):
            self.changed(cnd.duplicate(self.blocks, self.sel))

    def _move(self, step: int) -> None:
        if 0 <= self.sel < len(self.blocks):
            self.changed(cnd.move(self.blocks, self.sel, self.sel + step))

    def _remove(self) -> None:
        i = self.sel
        if not (0 <= i < len(self.blocks)):
            return

        def gone() -> None:
            del self.blocks[i]
            self.sel = min(i, len(self.blocks) - 1)
            self.enter()
        self.app.confirm(tr("Tirar o bloco {i}?", "Remove block {i}?", i=i + 1),
                         tr("Até guardares, sair sem guardar desfaz.",
                            "Until you save, leaving without saving undoes it."),
                         gone, yes=tr("Tirar", "Remove"))

    def _save(self) -> None:
        if not self.blocks:
            self.app.message(tr("Junta pelo menos um bloco.", "Add at least one block."))
            return
        from perennia.core import tags as tags_mod
        self.pid = ls.save_plan(self.app.db, self.pid, self.name.strip() or
                                tr("Treino de Conditioning", "Conditioning workout"),
                                "conditioning", cnd.to_items(self.app.db, self.blocks))
        self.wtags = tags_mod.set_workout_tags(self.app.db, "strength", self.pid, self.wtags)
        from perennia.core import objectives as ob
        ob.save_notes(self.app.db, "conditioning", self.pid, self.wnotes)
        self.draft = False
        self._saved_state = self._state()
        self.app.message(tr("Treino de Conditioning guardado", "Conditioning workout saved"))
        self.enter()

    def _edit_notes(self, extra: str = "") -> None:
        """As notas do treinador (pré-treino) do treino de Conditioning."""
        from perennia.ui.goal_popup import edit_notes

        def save(value: str) -> None:
            self.wnotes = value
            self.enter()
        edit_notes(self.app, self.name, self.wnotes + extra, save)

    def _start(self) -> None:
        if not self.blocks:
            self.app.message(tr("Junta pelo menos um bloco.", "Add at least one block."))
            return
        from perennia.ui.gym_screens import start_laps
        start_laps(self.app, "conditioning", cnd.to_items(self.app.db, self.blocks),
                   replace=True, plan_id=self.pid)

    def _delete(self) -> None:
        def gone() -> None:
            ls.delete_plan(self.app.db, self.pid)
            self.app.pop(force=True)
        self.app.confirm(tr("Apagar o treino «{n}»?", "Delete the workout «{n}»?", n=self.name),
                         tr("As sessões já feitas com ele guardam a sua cópia.",
                            "Sessions already done with it keep their copy."),
                         gone, yes=tr("Apagar", "Delete"))

    # ------------------------------------------------------- números (descanso)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        b = self.blocks[int(field)]
        b["seconds"] = max(10.0, float(b.get("seconds") or 0) + steps * (60 if big else 15))

    def num_set(self, field: str, value) -> None:
        if value is not None:
            self.blocks[int(field)]["seconds"] = max(10.0, float(value) * 60)

    def text_input(self, field: str, text: str) -> None:
        if field == "wnotes":
            self._edit_notes(text)               # as notas escrevem-se numa janela
            return
        self.name += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "wnotes":
            return
        self.name = self.name[:-1]
        self.enter()

    # ---------------------------------------------------------------- teclado

    def on_key(self, symbol: int, modifiers: int) -> bool:
        i = self._row_block()
        if i is not None:
            self.sel = i
            alt = modifiers & key.MOD_ALT
            if symbol in (key.UP, key.DOWN) and alt:
                self._move(-1 if symbol == key.UP else 1)
                return True
            if symbol in (key.LEFT, key.RIGHT) and modifiers & key.MOD_SHIFT and \
                    self._field("num:") is None:
                self._move(-1 if symbol == key.LEFT else 1)
                return True
            if symbol == key.D and self._field("text:") is None:
                self._duplicate()
                return True
            if symbol == key.DELETE:
                self._remove()
                return True
        if symbol == key.S and modifiers & key.MOD_CTRL:
            self._save()
            return True
        handled = super().on_key(symbol, modifiers)
        self._sync_sel()
        return handled

    # ----------------------------------------------------------------- rato

    def _block_at(self, x: float, y: float) -> int | None:
        if not (self.sy0 <= y <= self.sy1):
            return None
        for i, (a, z) in enumerate(self._geo):
            if a <= x <= z:
                return i
        return None

    def _insert_index(self, x: float) -> int:
        for i, (a, z) in enumerate(self._geo):
            if x < (a + z) / 2:
                return i
        return len(self._geo)

    def on_mouse(self, x: int, y: int) -> bool:
        i = self._block_at(x, y)
        if i is not None:
            self.drag = {"i": i, "x0": x, "moved": False}
            self._select(i)
            return True
        return super().on_mouse(x, y)

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        d = self.drag
        if d is None:
            return False
        if abs(x - d["x0"]) > 4:
            d["moved"] = True
        j = self._insert_index(x)
        xm = self._geo[j][0] - 2 if j < len(self._geo) else (self._geo[-1][1] + 1
                                                               if self._geo else self.sx0)
        self.mark.x, self.mark.y, self.mark.height = xm, self.sy0, STRIP_H
        self.mark.opacity = 255
        return True

    def on_release(self, x: int, y: int) -> bool:
        d = self.drag
        self.drag = None
        self.mark.opacity = 0
        if d is None:
            return False
        if d["moved"]:
            j = self._insert_index(x)
            i = d["i"]
            if j > i:
                j -= 1
            if j != i:
                self.changed(cnd.move(self.blocks, i, j))
        return True
