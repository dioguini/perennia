"""Glossário: os termos da Perennia e do treino, um separador por tema.

Enter num termo mostra-o por inteiro (com Editar e Apagar); «+ Novo termo» acrescenta um teu
ao separador onde estás. Os termos de origem editados ou apagados voltam com «Repor»."""
from __future__ import annotations

from perennia.core import glossary
from perennia.core.i18n import tr
from perennia.ui.app import ConfirmScreen, Screen
from perennia.ui.hub_screens import _excerpt, note_row
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Dropdown, Item


class GlossaryScreen(Screen):
    """Os termos, por separador. A pesquisa do topo procura no termo e na definição."""

    TABBED = True

    def __init__(self, app, tab: str | None = None):
        glossary.ensure(app.db)
        super().__init__(app)
        self.list.detail_below = True
        self._hay: dict[str, str] = {}
        self.list.matches = self._matches           # a pesquisa vê também a definição inteira
        if tab in glossary.tab_keys():
            self.tab = glossary.tab_keys().index(tab)
            if self.tabs is not None:
                self.tabs.select(self.tab)

    def tab_labels(self) -> list[str]:
        return [name for _k, name in glossary.tabs()]

    def tab_key(self) -> str:
        keys = glossary.tab_keys()
        return keys[self.tab % len(keys)]

    def _matches(self, it: Item, words: list[str]) -> bool:
        hay = self._hay.get(it.data[1]) if isinstance(it.data, tuple) else None
        if hay is None:
            hay = self.list.norm(" ".join((it.label or "", it.value or "", it.detail or "")))
        return all(w in hay for w in words)

    def query(self) -> str:
        return self.search_box.text.strip() if self.search_box is not None else ""

    def search_set(self, text: str) -> None:
        super().search_set(text)
        self.enter()                  # com texto, procura em todos os separadores

    def row(self, e: dict, with_tab: bool = False) -> Item:
        a = self.app
        mark = tr("meu", "mine") if not e["builtin"] else (
            tr("editado", "edited") if e["edited"] else "")
        if with_tab:
            mark = glossary.tab_name(e["tab"]) + (" · " + mark if mark else "")
        self._hay[e["ref"]] = self.list.norm(e["term"] + " " + e["definition"] + " " + mark)
        return Item(e["term"], value=mark, detail=_excerpt(e["definition"], 160),
                    action=lambda ref=e["ref"]: open_term(a, ref), data=("term", e["ref"]))

    def enter(self) -> None:
        a = self.app
        tab = self.tab_key()
        searching = bool(self.query())
        rows = glossary.all_entries(a.db) if searching else glossary.entries(a.db, tab)
        self._hay = {}
        items = [self.row(e, with_tab=searching) for e in rows]
        if not items:
            items = [Item(tr("Ainda não há termos neste separador", "No terms in this tab yet"),
                          enabled=False)]
        items.append(Item(tr("+ Novo termo", "+ New term"), top=True,
                          action=lambda: a.push(TermEditor(a, None, tab))))
        changed = glossary.deleted_builtins(a.db) or any(
            e["edited"] for e in glossary.all_entries(a.db))
        if changed:
            items.append(Item(tr("Repor os termos de origem", "Restore the built-in terms"),
                              button=True, action=self.ask_restore_all))
        self.chrome.set(tr("Glossário", "Glossary"),
                        tr("{n} termos em todos os separadores",
                           "{n} terms in all the tabs", n=len(rows)) if searching else
                        tr("{n} termos em «{t}» · {m} no total",
                           "{n} terms in «{t}» · {m} in total", n=len(rows),
                           t=glossary.tab_name(tab), m=len(glossary.all_entries(a.db))),
                        tr("Tab separador · Enter abre o termo · / pesquisa · Esc voltar",
                           "Tab tab · Enter opens the term · / search · Esc back"))
        self.list.set_items(items, keep_index=True)

    def ask_restore_all(self) -> None:
        a = self.app

        def go() -> None:
            n = glossary.restore_all(a.db)
            a.message(tr("{n} termos repostos", "{n} terms restored", n=n))
            self.enter()
        a.confirm(tr("Repor os termos de origem?", "Restore the built-in terms?"),
                  tr("As tuas edições e os termos de origem que apagaste voltam ao original. "
                     "Os termos que acrescentaste não mudam.",
                     "Your edits and the built-in terms you deleted go back to the original. "
                     "The terms you added do not change."), go, yes=tr("Repor", "Restore"))

    def agent_data(self) -> dict:
        return {"separador": glossary.tab_name(self.tab_key()),
                "termos": [{"termo": e["term"], "definicao": e["definition"]}
                           for e in glossary.entries(self.app.db, self.tab_key())]}


def open_term(app, ref: str) -> None:
    """Mostra um termo por inteiro, com Editar e Apagar."""
    e = glossary.get(app.db, ref)
    if e is None:
        return
    sub = e["definition"] or tr("(sem definição)", "(no definition)")

    def edit() -> None:
        app.pop()
        app.push(TermEditor(app, ref))

    def delete() -> None:
        app.pop()
        ask_delete(app, ref)
    app.push(TermView(app, e["term"], sub,
                      [(tr("Fechar", "Close"), app.pop),
                       (tr("Apagar", "Delete"), delete),
                       (tr("Editar", "Edit"), edit)],
                      default=2, buttons=True, cancel=app.pop))


class TermView(ConfirmScreen):
    """A janela de leitura de um termo (maior que uma pergunta, porque a definição é longa)."""

    W, H = 820, 380


def ask_delete(app, ref: str) -> None:
    e = glossary.get(app.db, ref)
    if e is None:
        return

    def gone() -> None:
        glossary.delete(app.db, ref)
        app.message(tr("Termo apagado", "Term deleted"))
        cur = app.current
        if isinstance(cur, TermEditor):            # apagado a partir do editor: fecha-o
            cur._saved_state = cur.state()
            cur.close()
        elif cur is not None:
            cur.enter()
    if e["builtin"]:
        text = tr("É um termo de origem: fica escondido e podes repô-lo com «Repor os termos "
                  "de origem».", "It is a built-in term: it is hidden and you can bring it "
                  "back with «Restore the built-in terms».")
    else:
        text = tr("É um termo teu. Não dá para desfazer.", "It is a term of yours. This cannot "
                  "be undone.")
    app.confirm(tr("Apagar «{t}»?", "Delete «{t}»?", t=e["term"]), text, gone,
                yes=tr("Apagar", "Delete"))


class TermEditor(EditPopup):
    """Criar ou editar um termo: separador, nome e definição (numa janela grande)."""

    def __init__(self, app, ref: str | None, tab: str | None = None):
        super().__init__(app)
        self.ref = ref
        e = glossary.get(app.db, ref) if ref else None
        self.entry = e
        self.v = {"tab": (e or {}).get("tab") or tab or glossary.tab_keys()[0],
                  "term": (e or {}).get("term") or "",
                  "definition": (e or {}).get("definition") or ""}

    def title(self) -> str:
        return tr("Termo", "Term") if self.ref else tr("Novo termo", "New term")

    def subtitle(self) -> str:
        if self.entry is not None and self.entry["builtin"]:
            return tr("Termo de origem · as tuas alterações ficam à parte e podes repor o "
                      "original", "Built-in term · your changes are kept apart and you can "
                      "restore the original")
        return glossary.tab_name(self.v["tab"])

    def _tab_pick(self, i: int) -> None:
        self.v["tab"] = glossary.tab_keys()[i]
        self.enter()

    def rows(self) -> list[Item]:
        v = self.v
        keys = glossary.tab_keys()
        rows = [Item(tr("Separador", "Tab"), value=glossary.tab_name(v["tab"]),
                     dropdown=Dropdown([n for _k, n in glossary.tabs()], keys.index(v["tab"]),
                                       self._tab_pick, title=tr("Separador", "Tab")),
                     detail=tr("Enter abre a lista", "Enter opens the list")),
                Item(tr("Termo", "Term"), value=(v["term"] or "") + "▏", data="text:term",
                     detail=tr("o nome do conceito, ex.: Cadência",
                               "the concept's name, e.g. Cadence")),
                note_row(self, "definition", v["term"] or tr("Novo termo", "New term"),
                         label=tr("Definição", "Definition"),
                         detail=tr("Enter escreve a definição numa janela grande",
                                   "Enter writes the definition in a large window"))]
        if self.entry is not None and self.entry["builtin"] and (
                self.entry["edited"]):
            rows.append(Item(tr("Repor o texto original", "Restore the original text"),
                             action=self._restore,
                             detail=tr("deita fora a tua edição deste termo",
                                       "throws away your edit of this term")))
        if self.ref:
            rows.append(Item(tr("Apagar o termo", "Delete the term"),
                             action=lambda: ask_delete(self.app, self.ref),
                             detail=tr("pede confirmação", "asks for confirmation")))
        return rows

    def text_input(self, field: str, text: str) -> None:
        if len(self.v[field]) < glossary.max_term(self.app.db):
            self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def saved_message(self) -> str:
        return tr("Termo guardado", "Term saved")

    def commit(self) -> bool:
        v = self.v
        if not (v["term"] or "").strip():
            self.app.message(tr("Falta o nome do termo.", "The term's name is missing."))
            return False
        try:
            self.ref = glossary.save(self.app.db, self.ref, v["term"], v["definition"],
                                     v["tab"])
        except ValueError as exc:
            self.app.message(str(exc))
            return False
        self.entry = glossary.get(self.app.db, self.ref)
        return True

    def _restore(self) -> None:
        glossary.restore(self.app.db, self.ref)
        self._saved_state = None
        self.app.message(tr("Texto original reposto", "Original text restored"))
        self.close()
