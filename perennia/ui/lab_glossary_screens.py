"""Saúde → Glossário das análises: um componente por linha, agrupados por categoria.

Cada linha mostra o teu último valor (com ▲/▼) e a descrição sumária; com o rato por cima
aparece também a estratégia para ficar no intervalo. Enter abre a ficha inteira — o que é, o que
faz subir e descer, o que é bom e mau, e as estratégias — com Editar e Apagar. «+ Novo
componente» acrescenta um teu; os de origem editados ou apagados voltam com «Repor».

A ficha também se abre a partir de um resultado de uma colheita (tecla G).
"""
from __future__ import annotations

import pyglet

from perennia.core import lab_glossary as lg
from perennia.core.i18n import tr
from perennia.ui.app import ModalScreen
from perennia.ui.hub_screens import note_row
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import ACCENT, DIM, TEXT, Dropdown, Item, make_label, set_wrap

TAB_KEY = "labs_glossary"


def tab_name() -> str:
    return tr("Glossário das análises", "Lab glossary")


def glossary_tab(menu) -> None:
    """Enche a lista do separador do menu Saúde."""
    a = menu.app
    db = a.db
    lg.ensure(db)
    entries = lg.all_entries(db)
    last = lg.latest_values(db)
    rows: list[Item] = []
    cat = None
    for e in entries:
        if e["category"] != cat:
            cat = e["category"]
            rows.append(Item(lg.category_name(cat), header=True))
        v = last.get(e["ref"])
        value = ""
        if v:
            mark = {"high": " ▲", "low": " ▼"}.get(v["flag"] or "", "")
            value = f"{v['text']} {v['unit']}".strip() + mark
        mark = "" if e["builtin"] and not e["edited"] else (
            tr(" · meu", " · mine") if not e["builtin"] else tr(" · editado", " · edited"))
        rows.append(Item(e["name"] + mark, value=value, detail=e["summary"],
                         tip=lg.tooltip(e), action=lambda ref=e["ref"]: open_component(a, ref),
                         data=("labterm", e["ref"])))
    rows.append(Item(tr("+ Novo componente", "+ New component"), top=True,
                     action=lambda: a.push(ComponentEditor(a, None))))
    if lg.deleted_builtins(db) or lg.edited_builtins(db):
        rows.append(Item(tr("Repor os de origem", "Restore the built-in ones"), button=True,
                         action=lambda: ask_restore_all(menu)))
    from perennia.ui import health_extra_screens as hx
    rows.append(hx.new_tab_button(menu))
    menu.chrome.set(menu.TITLE(),
                    tr("{n} componentes · o teu último valor à direita · Enter abre a ficha · "
                       "rato por cima: resumo e estratégias · não substitui o médico",
                       "{n} components · your last value on the right · Enter opens the card · "
                       "hover: summary and strategies · does not replace your doctor",
                       n=len(entries)), menu.footer())
    menu.list.detail_below = True            # o nome inteiro, com o resumo por baixo
    menu.list.set_items(rows, keep_index=True)


def ask_restore_all(menu) -> None:
    a = menu.app

    def go() -> None:
        n = lg.restore_all(a.db)
        a.message(tr("{n} componentes repostos", "{n} components restored", n=n))
        menu.enter()
    a.confirm(tr("Repor os componentes de origem?", "Restore the built-in components?"),
              tr("As tuas edições e os componentes de origem que apagaste voltam ao original. "
                 "Os que acrescentaste não mudam.", "Your edits and the built-in components "
                 "you deleted go back to the original. The ones you added do not change."),
              go, yes=tr("Repor", "Restore"))


def open_component(app, ref: str) -> None:
    e = lg.get(app.db, ref)
    if e is not None:
        app.push(ComponentView(app, ref))


def open_for_marker(app, marker: str) -> bool:
    """A ficha do componente de um resultado (pelo nome); False se não houver."""
    e = lg.match(app.db, marker)
    if e is None:
        app.message(tr("«{m}» ainda não está no glossário das análises — podes acrescentá-lo.",
                       "«{m}» is not in the lab glossary yet — you can add it.", m=marker))
        return False
    open_component(app, e["ref"])
    return True


class ComponentView(ModalScreen):
    """A ficha de um componente: um bloco por secção, com o título a cor e o texto partido em
    linhas. Botões: Fechar · Apagar · Editar."""

    W, H = 1000, 700
    BODY = 12
    LINE_H = 18

    def __init__(self, app, ref: str):
        self.ref = ref
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self._labels: list = []

    def entry(self) -> dict | None:
        return lg.get(self.app.db, self.ref)

    def enter(self) -> None:
        e = self.entry()
        if e is None:
            self.app.pop()
            return
        last = lg.latest_values(self.app.db).get(self.ref)
        sub = lg.category_name(e["category"])
        if last:
            mark = {"high": " ▲", "low": " ▼"}.get(last["flag"] or "", "")
            sub += " · " + tr("o teu último valor: ", "your last value: ") + \
                f"{last['text']} {last['unit']}".strip() + mark + f" ({last['done_on']})"
        self.chrome.set(e["name"], sub, "")
        self.list.set_items([Item(tr("Fechar", "Close"), button=True, action=self.app.pop),
                             Item(tr("Apagar", "Delete"), button=True, action=self._delete),
                             Item(tr("Editar", "Edit"), button=True, primary=True,
                                  action=self._edit)])
        self.list.index = 2
        self._build(e)

    def sections(self, e: dict) -> list[tuple[str, str]]:
        out = [(tr("Resumo", "Summary"), e.get("summary") or "")] if e.get("summary") else []
        out += [(title, e.get(f) or "") for f, title in lg.section_titles() if e.get(f)]
        return out + [(tr("Nota", "Note"), lg.disclaimer())]

    def _body_height(self, lab, text: str, width: float) -> float:
        """A altura do texto partido em linhas: a medida da pyglet, ou uma estimativa."""
        h = getattr(lab, "content_height", None)
        if isinstance(h, (int, float)) and h > 0:
            return float(h)
        return _lines(text, width, self.BODY) * self.LINE_H

    def _build(self, e: dict) -> None:
        """Os blocos das secções, um por baixo do outro; a janela cresce (até à altura da
        aplicação) para os caber."""
        self.batch = pyglet.graphics.Batch()
        self._labels = []
        width = self.W - 64
        made = []
        for title, body in self.sections(e):
            head = make_label(title.upper(), font_size=10, bold=True, color=ACCENT,
                              batch=self.batch)
            lab = make_label(body, font_size=self.BODY, color=DIM if title == tr(
                "Nota", "Note") else TEXT, anchor_y="top", batch=self.batch)
            set_wrap(lab, width)
            made.append((head, lab, self._body_height(lab, body, width)))
            self._labels += [head, lab]
        need = 108 + sum(20 + h + 12 for _h, _l, h in made) + 70
        self.set_popup_size(self.W, need)
        p = self.popup
        y = p.y + p.h - 94
        for head, lab, h in made:
            head.x, head.y = p.x + 28, y
            lab.x, lab.y = p.x + 28, y - 6
            y -= 20 + h + 12

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        e = self.entry()
        if e is not None:
            self._build(e)

    def draw(self) -> None:
        super().draw()
        self.batch.draw()

    def texts(self) -> list[str]:
        """O que a ficha mostra (para os testes e o agente)."""
        return [lab.text for lab in self._labels]

    def _edit(self) -> None:
        self.app.pop()
        self.app.push(ComponentEditor(self.app, self.ref))

    def _delete(self) -> None:
        self.app.pop()
        ask_delete(self.app, self.ref)


def _lines(text: str, width: float, size: float) -> int:
    from perennia.ui.widgets import Tooltip
    return Tooltip.lines_of(text, width, size) if text else 1


def ask_delete(app, ref: str) -> None:
    e = lg.get(app.db, ref)
    if e is None:
        return

    def gone() -> None:
        lg.delete(app.db, ref)
        app.message(tr("Componente apagado", "Component deleted"))
        cur = app.current
        if isinstance(cur, ComponentEditor):
            cur._saved_state = cur.state()
            cur.close()
        elif cur is not None:
            cur.enter()
    if e["builtin"]:
        text = tr("É um componente de origem: fica escondido e podes repô-lo com «Repor os de "
                  "origem».", "It is a built-in component: it is hidden and you can bring it "
                  "back with «Restore the built-in ones».")
    else:
        text = tr("É um componente teu. Não dá para desfazer.",
                  "It is a component of yours. This cannot be undone.")
    app.confirm(tr("Apagar «{t}»?", "Delete «{t}»?", t=e["name"]), text, gone,
                yes=tr("Apagar", "Delete"))


class ComponentEditor(EditPopup):
    """Criar ou editar um componente: nome, categoria, nomes alternativos e as secções."""

    def __init__(self, app, ref: str | None, name: str = ""):
        super().__init__(app)
        self.ref = ref
        e = lg.get(app.db, ref) if ref else None
        self.entry = e
        self.v = {"name": (e or {}).get("name") or name,
                  "category": (e or {}).get("category") or "other",
                  "aliases_text": ", ".join(a for a in (e or {}).get("aliases", [])
                                            if a != lg.fold((e or {}).get("name", "")))}
        for f in lg.FIELDS:
            self.v[f] = (e or {}).get(f) or ""

    def title(self) -> str:
        return tr("Componente", "Component") if self.ref else tr("Novo componente",
                                                                  "New component")

    def subtitle(self) -> str:
        if self.entry is not None and self.entry["builtin"]:
            return tr("Componente de origem · as tuas alterações ficam à parte e podes repor o "
                      "original", "Built-in component · your changes are kept apart and you "
                      "can restore the original")
        return tr("Os nomes alternativos ligam-no aos resultados das tuas análises",
                  "The other names link it to your lab results")

    def _cat_pick(self, i: int) -> None:
        self.v["category"] = lg.category_keys()[i]
        self.enter()

    def rows(self) -> list[Item]:
        v = self.v
        keys = lg.category_keys()
        title = v["name"] or tr("Novo componente", "New component")
        labels = dict(lg.section_titles())
        rows = [Item(tr("Nome", "Name"), value=(v["name"] or "") + "▏", data="text:name",
                     detail=tr("ex.: Ferritina", "e.g. Ferritin")),
                Item(tr("Categoria", "Category"), value=lg.category_name(v["category"]),
                     dropdown=Dropdown([n for _k, n in lg.categories()],
                                       keys.index(v["category"]) if v["category"] in keys
                                       else len(keys) - 1, self._cat_pick,
                                       title=tr("Categoria", "Category")),
                     detail=tr("Enter abre a lista", "Enter opens the list")),
                note_row(self, "aliases_text", title,
                         label=tr("Nomes alternativos", "Other names"),
                         detail=tr("separados por vírgulas, como aparecem nos boletins "
                                   "(ex.: «ferritina sérica, ferritin»)",
                                   "comma-separated, as they appear in lab reports")),
                note_row(self, "summary", title,
                         label=tr("Descrição sumária", "Short description"),
                         detail=tr("a que aparece com o rato por cima de um resultado",
                                   "the one shown when hovering a result"))]
        for f in ("what", "up", "down", "good", "bad", "act"):
            rows.append(note_row(self, f, title, label=labels[f],
                                 detail=tr("Enter escreve numa janela grande",
                                           "Enter writes in a large window")))
        if self.entry is not None and self.entry["builtin"] and self.entry["edited"]:
            rows.append(Item(tr("Repor o texto original", "Restore the original text"),
                             action=self._restore,
                             detail=tr("deita fora a tua edição deste componente",
                                       "throws away your edit of this component")))
        if self.ref:
            rows.append(Item(tr("Apagar o componente", "Delete the component"),
                             action=lambda: ask_delete(self.app, self.ref),
                             detail=tr("pede confirmação", "asks for confirmation")))
        return rows

    def text_input(self, field: str, text: str) -> None:
        if len(self.v[field]) < 80:
            self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def saved_message(self) -> str:
        return tr("Componente guardado", "Component saved")

    def commit(self) -> bool:
        if not (self.v["name"] or "").strip():
            self.app.message(tr("Falta o nome do componente.", "The component's name is "
                                "missing."))
            return False
        try:
            self.ref = lg.save(self.app.db, self.ref, self.v)
        except ValueError as exc:
            self.app.message(str(exc))
            return False
        self.entry = lg.get(self.app.db, self.ref)
        return True

    def _restore(self) -> None:
        lg.restore(self.app.db, self.ref)
        self._saved_state = None
        self.app.message(tr("Texto original reposto", "Original text restored"))
        self.close()
