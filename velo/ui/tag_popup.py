"""A janela do fim da sessão: as etiquetas que o .fit vai levar.

Mostra o tipo de treino (o do próprio treino, ou — numa sessão livre — o
sugerido pelo esforço; muda-se na lista), o tipo de sessão (`Perennia`,
`Indoor Cycling`, `Virtual …` quando segue um .gpx) e as etiquetas livres.
Ao escrever uma nova, as que já existem aparecem logo a sugerir.
"""
from __future__ import annotations

from velo.core import tags as tg
from velo.core.i18n import tr
from velo.ui.app import PopupMixin, Screen
from velo.ui.widgets import Item


def open_session_tags(screen, sport: str, *, workout_id: str | None, has_route: bool,
                      summary, on_done, on_back) -> None:
    """Abre a janela das etiquetas por cima de `screen`. `on_done(info)` quando se
    guarda; `on_back()` se se volta atrás."""
    db = screen.app.db
    info = tg.defaults(db, sport, workout_id=workout_id, has_route=has_route,
                       summary=summary)
    suggested = tg.suggest_for(summary) if summary is not None else None
    screen.app.push(SessionTagsPopup(screen.app, sport, info, suggested, on_done, on_back,
                                     fixed_type=tg.workout_type(db, sport, workout_id)))


class SessionTagsPopup(PopupMixin, Screen):
    W, H = 760, 600
    SEARCH = False
    AGENT = False

    def __init__(self, app, sport: str, info: dict, suggested: str | None, on_done, on_back,
                 fixed_type: str | None = None):
        super().__init__(app)
        self.sport = sport
        self.info = {"workout_type": info.get("workout_type"),
                     "session": list(info.get("session") or []),
                     "custom": list(info.get("custom") or [])}
        self.suggested = suggested
        self.fixed_type = fixed_type            # o tipo do próprio treino (se tiver)
        self.on_done = on_done
        self.on_back = on_back
        self.back_button = None
        self._closing = False
        self._focused = False
        self._init_popup()

    # ------------------------------------------------------------- lista

    def enter(self) -> None:
        wt = self.info.get("workout_type")
        if wt and wt == self.fixed_type:
            why = tr("o do treino · Enter muda", "the workout's · Enter changes")
        elif wt and wt == self.suggested:
            why = tr("sugerido pelo esforço · Enter muda", "suggested by effort · Enter changes")
        else:
            why = tr("Enter escolhe", "Enter picks")
        items = [
            Item(tr("Tipo de treino", "Workout type"), value=tg.type_label(wt) or "—",
                 detail=why, action=self._pick_type),
            Item(tr("Tipo de sessão", "Session type"),
                 value=" · ".join(self.info["session"]) or "—", enabled=False,
                 detail=tr("automático: o aparelho e a rota", "automatic: the device and route")),
        ]
        for tag in self.info["custom"]:
            items.append(Item(tag, value=tr("remover", "remove"),
                              action=lambda t=tag: self._remove(t)))
        items.append(Item(tr("+ Adicionar etiqueta", "+ Add a tag"), action=self._add))
        items.append(Item(tr("No .fit", "In the .fit"), value=tg.fit_text(self.info),
                          enabled=False))
        items.append(Item(tr("Voltar à sessão", "Back to the session"), button=True,
                          action=self.go_back))
        items.append(Item(tr("Guardar e terminar", "Save and finish"), button=True,
                          primary=True, action=self._done, data="done"))
        self.chrome.set(tr("Etiquetas da sessão", "Session tags"),
                        tr("O .fit leva estas etiquetas", "The .fit carries these tags"), "")
        self.list.set_items(items, keep_index=True)
        if not self._focused:                    # Enter, Enter: termina com as etiquetas sugeridas
            self._focused = True
            self.list.select_data("done")

    # ------------------------------------------------------------ ações

    def _pick_type(self) -> None:
        from velo.ui.pickers import ChoicePopup
        labels = tg.type_labels()
        cur = tg.TYPE_KEYS.index(self.info["workout_type"]) \
            if self.info.get("workout_type") in tg.TYPE_KEYS else 0

        def pick(k: int) -> None:
            self.info["workout_type"] = tg.TYPE_KEYS[k]
            self.enter()
        self.app.push(ChoicePopup(self.app, tr("Tipo de treino", "Workout type"), labels, cur,
                                  pick))

    def _add(self) -> None:
        self.app.push(AddTagPopup(self.app, self.info["custom"], self._added))

    def _added(self, tag: str) -> None:
        if tag and tag not in self.info["custom"]:
            self.info["custom"].append(tag)
        self.enter()

    def _remove(self, tag: str) -> None:
        if tag in self.info["custom"]:
            self.info["custom"].remove(tag)
        self.enter()

    def _done(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.app.pop()
        self.on_done(self.info)

    def go_back(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.app.pop()
        self.on_back()


class AddTagPopup(PopupMixin, Screen):
    """Escreve-se a etiqueta; as que já existem (sem contar maiúsculas nem acentos)
    aparecem por baixo e escolhem-se; se não existir, «Criar …» faz uma nova."""
    W, H = 640, 520
    SEARCH_ENTER_PICKS = True
    AGENT = False

    def __init__(self, app, taken: list[str], on_add):
        super().__init__(app)
        self.taken = {tg._fold(t) for t in taken}
        self.on_add = on_add
        self.typed = ""
        self.back_button = None
        self._init_popup()
        self.search_focus(True)

    def search_set(self, text: str) -> None:
        if self.search_box is None:
            self.search_focus(False)
        self.typed = text
        self.search_box.text = text
        self._place_search()
        self.enter()

    def enter(self) -> None:
        db = self.app.db
        typed = " ".join(self.typed.split())
        if typed:
            found = tg.match(db, typed, limit=12)
        else:
            found = tg.known_tags(db)[:12]
        found = [t for t in found if tg._fold(t) not in self.taken]
        items: list[Item] = []
        exact = any(tg._fold(t) == tg._fold(typed) for t in found)
        can_create = bool(typed) and not exact and tg._fold(typed) not in self.taken
        if can_create:
            items.append(Item(tr("Criar «{t}»", "Create “{t}”", t=typed[:32]),
                              detail=tr("etiqueta nova", "new tag"),
                              action=lambda: self._pick(typed)))
        elif not typed:
            items.append(Item(tr("Escreve o nome para criar uma etiqueta nova",
                                 "Type a name to create a new tag"),
                              detail=tr("ou escolhe uma das que já existem", "or pick one that "
                                        "already exists"), enabled=False))
        for t in found:
            items.append(Item(t, detail=tr("já existe", "already exists"),
                              action=lambda t=t: self._pick(t)))
        items.append(Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop))
        items.append(Item(tr("+ Criar etiqueta nova", "+ Create a new tag"), button=True,
                          primary=True, enabled=can_create,
                          action=lambda: self._pick(typed)))
        self.chrome.set(tr("Adicionar etiqueta", "Add a tag"),
                        tr("Escreve · as existentes aparecem · Enter escolhe · Esc fecha",
                           "Type · existing ones show up · Enter picks · Esc closes"), "")
        self.list.set_items(items)

    def _pick(self, tag: str) -> None:
        self.app.pop()
        self.on_add(tg.normalize(self.app.db, tag))

    def search_key(self, symbol: int, modifiers: int) -> bool:
        from pyglet.window import key
        if symbol == key.ESCAPE and not self.search_box.text:
            self.app.pop()
            return True
        return super().search_key(symbol, modifiers)
