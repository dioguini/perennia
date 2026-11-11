"""Grupos e subgrupos musculares: o separador «Grupos Musculares» da lista de exercícios
e a janela de cada grupo. As regras estão em `perennia.core.muscles`."""
from __future__ import annotations

from perennia.core import muscles
from perennia.core.i18n import tr
from perennia.ui.app import PopupMixin, Screen
from perennia.ui.goal_popup import GoalPopup
from perennia.ui.widgets import Item


def group_items(app, on_changed) -> list[Item]:
    """As linhas do separador: um grupo por linha (Enter abre) e «+ Novo grupo»."""
    db = app.db
    counts = muscles.exercise_counts(db)
    items = [Item(tr("+ Novo grupo", "+ New group"), top=True,
                  action=lambda: _ask(app, tr("Novo grupo muscular", "New muscle group"), "",
                                      lambda v: (muscles.add_group(db, v), on_changed())))]
    for g in muscles.groups(db):
        subs = ", ".join(s["name"] for s in g["subgroups"]) or tr("sem subgrupos",
                                                                    "no subgroups")
        n = counts["groups"].get(g["key"], 0)
        items.append(Item(g["name"], value=tr("{n} exercícios", "{n} exercises", n=n),
                          detail=subs,
                          action=lambda k=g["key"]: app.push(GroupPopup(app, k, on_changed)),
                          data=("group", g["key"])))
    return items


def _ask(app, title: str, text: str, on_save, sub: str = "") -> None:
    def save(value: str) -> None:
        value = " ".join((value or "").split())
        if value:
            on_save(value)
    app.push(GoalPopup(app, title, sub, text, 60, save))


class GroupPopup(PopupMixin, Screen):
    """Um grupo: os subgrupos (Enter muda o nome, Del apaga), «+ Novo subgrupo»,
    mudar o nome e apagar o grupo."""

    W, H = 760, 600
    SEARCH = False
    AGENT = False

    def __init__(self, app, key: str, on_changed=None):
        super().__init__(app)
        self.key = key
        self.on_changed = on_changed or (lambda: None)
        self.back_button = None
        self._init_popup()

    def _group(self) -> dict | None:
        return next((g for g in muscles.groups(self.app.db) if g["key"] == self.key), None)

    def _changed(self) -> None:
        self.enter()
        self.on_changed()

    def enter(self) -> None:
        g = self._group()
        if g is None:
            self.app.pop()
            return
        db = self.app.db
        counts = muscles.exercise_counts(db)
        items = [Item(tr("Nome do grupo", "Group name"), value=g["name"],
                      detail=tr("Enter muda o nome", "Enter renames"),
                      action=lambda: _ask(self.app, tr("Nome do grupo", "Group name"),
                                          g["name_pt"],
                                          lambda v: (muscles.rename_group(db, g["key"], v),
                                                     self._changed())))]
        for s in g["subgroups"]:
            n = counts["subgroups"].get(s["id"], 0)
            items.append(Item(s["name"], value=tr("{n} exercícios", "{n} exercises", n=n),
                              detail=tr("Enter muda o nome · Del apaga", "Enter renames · "
                                        "Del deletes"),
                              data=("sub", s["id"]),
                              action=lambda s=s: _ask(
                                  self.app, tr("Subgrupo", "Subgroup"), s["name_pt"],
                                  lambda v: (muscles.rename_subgroup(db, s["id"], v),
                                             self._changed()))))
        items.append(Item(tr("+ Novo subgrupo", "+ New subgroup"), top=True,
                          action=lambda: _ask(
                              self.app, tr("Novo subgrupo", "New subgroup"), "",
                              lambda v: (muscles.add_subgroup(db, g["key"], v),
                                         self._changed()), sub=g["name"])))
        if g["key"] != "full":
            items.append(Item(tr("Apagar o grupo", "Delete the group"), button=True,
                              action=self._delete))
        items.append(Item(tr("Fechar", "Close"), button=True, primary=True,
                          action=self.app.pop))
        self.chrome.set(g["name"], tr("Subgrupos deste grupo", "This group's subgroups"), "")
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        from pyglet.window import key
        it = self.list.selected
        if symbol == key.DELETE and it is not None and isinstance(it.data, tuple) and \
                it.data[0] == "sub":
            sid = it.data[1]
            self.app.confirm(tr("Apagar este subgrupo?", "Delete this subgroup?"),
                             tr("Os exercícios ficam sem subgrupo.",
                                "The exercises are left without a subgroup."),
                             lambda: (muscles.delete_subgroup(self.app.db, sid),
                                      self._changed()), yes=tr("Apagar", "Delete"))
            return True
        return super().on_key(symbol, modifiers)

    def _delete(self) -> None:
        self.app.confirm(tr("Apagar o grupo?", "Delete the group?"),
                         tr("Os exercícios passam para «Corpo inteiro».",
                            "The exercises move to “Full body”."),
                         self._do_delete, yes=tr("Apagar", "Delete"))

    def _do_delete(self) -> None:
        muscles.delete_group(self.app.db, self.key)
        self.app.pop()                       # fecha esta janela
        self.on_changed()
