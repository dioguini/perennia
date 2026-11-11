"""Entradas dos desportos, estatísticas por desporto e os dois inventários
(artigos e exercícios)."""
from __future__ import annotations

from datetime import date, timedelta

from pyglet.window import key

from perennia.core import gym, inventory, muscles
from perennia.core.i18n import t, tr
from perennia.ui.app import Screen
from perennia.ui.sport_screens import EditPopup, EditScreen
from perennia.ui.widgets import Item


def SportHub(app, sport: str):                     # noqa: N802 — fábrica
    """O menu do desporto (separadores Treinar · Construtor · Lista · Histórico ·
    Estatísticas)."""
    if sport == "cycling":
        from perennia.ui.app import MainMenu
        return MainMenu(app)
    if sport == "rowing":
        from perennia.ui.rowing_screens import RowingMenu
        return RowingMenu(app)
    if sport in ("running", "swimming"):
        from perennia.ui.endurance_screens import EnduranceHub
        return EnduranceHub(app, sport)
    from perennia.ui.gym_screens import GymHub
    return GymHub(app)


def stats_screen(app, sport: str | None, hub=None):
    """As estatísticas, já no desporto pedido (None = todos). Com `hub` (o menu
    do desporto), abrem no separador Estatísticas dele e o desporto fica fixo."""
    from perennia.ui import stats_screens
    from perennia.ui.app import Screen
    Screen._pending_hub = hub
    try:
        return stats_screens.for_sport(app, sport)
    finally:
        Screen._pending_hub = None


# ============================================================ inventário


class InventoryScreen(Screen):
    """O teu material: a «Visão Geral» (totais) e um separador por grupo
    (máquinas, pesos livres, estações…). **+ Novo artigo** fica em cima, à
    direita; Enter num artigo abre-o para editar (numa janela)."""

    TABBED = True

    def tab_labels(self) -> list[str]:
        return [tr("Visão Geral", "Overview"),
                tr("Lista completa de artigos", "Full item list")] + \
            [tr(*v) for v in inventory.GROUPS.values()]

    def group(self) -> str | None:
        i = self.tab % len(self.tab_labels())
        if i == 0:
            return None
        if i == 1:
            return "@all"
        return list(inventory.GROUPS)[(i - 2) % len(inventory.GROUPS)]

    def item_row(self, r: dict, with_kind: bool = True) -> Item:
        a = self.app
        bits = [inventory.kind_name(r["kind"])] if with_kind else []
        if r["weight_kg"]:
            bits.append(f"{r['weight_kg']:g} kg")
        if r.get("purchase_date"):
            d = str(r["purchase_date"])
            bits.append(tr("comprado em {d}", "bought {d}", d=f"{d[8:10]}/{d[5:7]}/{d[:4]}"))
        if r.get("purchase_price") is not None:
            bits.append(f"{r['purchase_price']:,.2f} €".replace(",", " "))
        if r["notes"]:
            bits.append(r["notes"])
        return Item(r["name"], value=f"× {r['qty']}", detail=" · ".join(bits),
                    action=lambda iid=r["id"]: a.push(ItemEditor(a, iid)),
                    data=("item", r["id"]))

    def enter(self) -> None:
        a = self.app
        g = self.group()
        summ = inventory.summary(a.db)
        if g is None:
            items = self.overview()
            first_kind = next(iter(inventory.KINDS))
        elif g == "@all":
            # todos os artigos, por nome, com o grupo e a compra
            first_kind = next(iter(inventory.KINDS))
            items = [self.item_row(r) for r in sorted(inventory.items(a.db),
                                                      key=lambda r: r["name"].lower())]
            total = sum((r.get("purchase_price") or 0) * 1 for r in inventory.items(a.db))
            if items and total:
                items.insert(0, Item(tr("Valor gasto", "Money spent"),
                                     value=f"{total:,.2f} €".replace(",", " "),
                                     detail=tr("a soma dos preços de compra",
                                               "the sum of the purchase prices"),
                                     enabled=False))
            if not items:
                items = [Item(tr("Ainda não há artigos", "No items yet"), enabled=False)]
        else:
            kinds = [k for k, v in inventory.KINDS.items() if v[2] == g]
            first_kind = kinds[0] if kinds else "other"
            items = [self.item_row(r) for r in inventory.items(a.db) if r["kind"] in kinds]
            if not items:
                items = [Item(tr("Ainda nada neste grupo", "Nothing in this group yet"),
                              enabled=False)]
        items.append(Item(tr("+ Novo artigo", "+ New item"), top=True,
                          action=lambda: a.push(ItemEditor(a, None, first_kind))))
        self.chrome.set(tr("Inventário de artigos", "Equipment"),
                        tr("{a} artigos · {u} unidades", "{a} items · {u} units",
                           a=summ["articles"], u=summ["units"]),
                        tr("Tab grupo · Enter editar · Esc voltar",
                           "Tab group · Enter edit · Esc back"))
        self.list.set_items(items, keep_index=True)

    def overview(self) -> list[Item]:
        """Totais: artigos, unidades, quilos (todos e só os pesos livres), por grupo."""
        a = self.app
        rows = inventory.items(a.db)
        kg = sum((r["qty"] or 0) * (r["weight_kg"] or 0) for r in rows)
        out = [Item(tr("Artigos", "Items"), value=str(len(rows)), enabled=False),
               Item(tr("Unidades", "Units"), value=str(sum(r["qty"] or 0 for r in rows)),
                    enabled=False),
               Item(tr("Peso total", "Total weight"), value=f"{kg:,.1f} kg".replace(",", " "),
                    detail=tr("a soma de quantidade × peso de cada artigo",
                              "the sum of quantity × weight of each item"), enabled=False)]
        heavy = max(rows, key=lambda r: r["weight_kg"] or 0, default=None)
        if heavy is not None and heavy["weight_kg"]:
            out.append(Item(tr("O mais pesado", "Heaviest"), value=f"{heavy['weight_kg']:g} kg",
                            detail=heavy["name"], enabled=False))
        for g, names in inventory.GROUPS.items():
            kinds = {k for k, v in inventory.KINDS.items() if v[2] == g}
            grp = [r for r in rows if r["kind"] in kinds]
            if not grp:
                continue
            gkg = sum((r["qty"] or 0) * (r["weight_kg"] or 0) for r in grp)
            out.append(Item(tr(*names), value=tr("{n} artigos", "{n} items", n=len(grp)),
                            detail=tr("{u} unidades", "{u} units",
                                      u=sum(r["qty"] or 0 for r in grp))
                            + (f" · {gkg:,.1f} kg".replace(",", " ") if gkg else ""),
                            enabled=False))
        return out

    def agent_data(self) -> dict:
        return {"artigos": [{k: r[k] for k in ("name", "kind", "qty", "weight_kg")}
                            for r in inventory.items(self.app.db)]}


class ItemEditor(EditPopup):
    """Um artigo do inventário, numa janela."""

    def __init__(self, app, iid: int | None, kind: str = "other"):
        super().__init__(app)
        self.iid = iid
        r = inventory.item(app.db, iid) if iid else None
        self.v = {"name": (r or {}).get("name") or "", "kind": (r or {}).get("kind") or kind,
                  "qty": (r or {}).get("qty", 1), "weight_kg": (r or {}).get("weight_kg"),
                  "notes": (r or {}).get("notes") or "",
                  "purchase_date": (r or {}).get("purchase_date"),
                  "purchase_price": (r or {}).get("purchase_price")}
        self._armed = False

    def title(self) -> str:
        return tr("Artigo", "Item") if self.iid else tr("Novo artigo", "New item")

    def subtitle(self) -> str:
        return inventory.kind_name(self.v["kind"])

    def rows(self) -> list[Item]:
        v = self.v
        rows = [Item(tr("Tipo", "Kind"), value=inventory.kind_name(v["kind"]),
                     data="cyc:kind", detail=tr("←/→ muda · é o que os exercícios pedem",
                                                "←/→ changes · it is what exercises ask for")),
                Item(tr("Nome", "Name"), value=(v["name"] or "") + "▏", data="text:name",
                     detail=tr("ex.: Disco de 1 kg, Domyos Rowing 500B",
                               "e.g. 1 kg plate, Domyos Rowing 500B")),
                Item(tr("Quantidade", "Quantity"), value=str(v["qty"]), data="num:qty",
                     detail=tr("←/→ ±1 · Shift ±5 · ou escreve", "←/→ ±1 · Shift ±5 · or type")),
                Item(tr("Peso (kg)", "Weight (kg)"),
                     value="—" if v["weight_kg"] is None else f"{v['weight_kg']:g} kg",
                     data="num:weight_kg", detail=tr("de cada um (opcional)",
                                                     "each (optional)")),
                Item(tr("Data de compra", "Purchase date"),
                     value=self._date_text(), data="cyc:purchase_date",
                     detail=tr("Enter abre o calendário · ←/→ um dia",
                               "Enter opens the calendar · ←/→ one day")),
                Item(tr("Preço de compra", "Purchase price"),
                     value="—" if v["purchase_price"] is None else
                     f"{v['purchase_price']:,.2f} €".replace(",", " "),
                     data="num:purchase_price",
                     detail=tr("escreve o valor · ←/→ ±1 € · Shift ±10 €",
                               "type the amount · ←/→ ±1 € · Shift ±10 €")),
                Item(tr("Notas", "Notes"), value=(v["notes"] or "") + "▏", data="text:notes")]
        if self.iid:
            rows.append(Item(tr("Apagar o artigo", "Delete the item"), action=self._delete,
                             detail=tr("Enter duas vezes", "Enter twice")))
        return rows

    def _date_text(self) -> str:
        d = self.v.get("purchase_date")
        return f"{d[8:10]}/{d[5:7]}/{d[:4]}" if d else "—"

    def date_get(self, field: str):
        return self.v.get("purchase_date") or date.today().isoformat()

    def date_set(self, field: str, iso: str) -> None:
        self.v["purchase_date"] = iso
        self.enter()

    def cycle(self, field: str, step: int) -> None:
        if field == "purchase_date":
            cur = date.fromisoformat(self.v.get("purchase_date") or date.today().isoformat())
            self.v["purchase_date"] = (cur + timedelta(days=step)).isoformat()
            return
        ks = list(inventory.KINDS)
        self.v["kind"] = ks[(ks.index(self.v["kind"]) + step) % len(ks)]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field == "purchase_price":
            cur = self.v["purchase_price"] or 0.0
            self.v["purchase_price"] = max(0.0, round(cur + steps * (10 if big else 1), 2))
            return
        if field == "qty":
            self.v["qty"] = max(0, self.v["qty"] + steps * (5 if big else 1))
        else:
            cur = self.v["weight_kg"] or 0.0
            self.v["weight_kg"] = max(0.0, round(cur + steps * (5 if big else 0.5), 2))

    def num_set(self, field: str, value) -> None:
        if field == "purchase_price":
            self.v["purchase_price"] = value
            return
        if field == "qty":
            self.v["qty"] = int(value or 0)
        else:
            self.v["weight_kg"] = value

    def text_input(self, field: str, text: str) -> None:
        self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def saved_message(self) -> str:
        return tr("Artigo guardado", "Item saved")

    def commit(self) -> bool:
        v = self.v
        self.iid = inventory.save(self.app.db, self.iid, name=v["name"], kind=v["kind"],
                                  qty=v["qty"], weight_kg=v["weight_kg"],
                                  notes=v["notes"] or None,
                                  purchase_date=v.get("purchase_date"),
                                  purchase_price=v.get("purchase_price"))
        return True

    def _delete(self) -> None:
        def gone() -> None:
            inventory.delete(self.app.db, self.iid)
            self._saved_state = self.state()
            self.close()
        self.app.confirm(tr("Apagar este artigo?", "Delete this item?"), tr("Tens a certeza? Não dá para desfazer.", "Are you sure? This cannot be undone."), gone,
                         yes=tr("Apagar", "Delete"))


# =========================================================== exercícios


class ExerciseInventory(Screen):
    """Os exercícios de cada modalidade do ginásio: ver, juntar, editar.
    Com `pick`, escolhe um para um treino (e só mostra os da modalidade)."""

    TABBED = True

    GROUPS_TAB = "__groups__"

    def __init__(self, app, modality: str | None = None, pick=None):
        self.fixed = modality
        self.pick = pick
        self.only_available = False
        gym.ensure(app.db)                   # as disciplinas que juntaste entram no registo
        super().__init__(app)
        self.list.detail_below = True        # lista grande: a descrição vai por baixo
        if modality:
            keys = self.tab_keys()
            self.tab = keys.index(modality) if modality in keys else 0
            if self.tabs is not None:
                self.tabs.select(self.tab)

    def tab_keys(self) -> list[str]:
        """Uma tab por modalidade (a Longevidade já é um menu à parte) e, no fim, os grupos
        musculares. Quem escolhe exercícios para um treino não vê os grupos."""
        keys = [m.key for m in gym.modalities()]
        if not self.pick:
            keys.append(self.GROUPS_TAB)
        return keys

    def tab_labels(self) -> list[str]:
        return [tr("Grupos Musculares", "Muscle Groups") if k == self.GROUPS_TAB
                else gym.modality(k).name for k in self.tab_keys()]

    def modality(self) -> str:
        keys = self.tab_keys()
        return keys[self.tab % len(keys)]

    def _refresh_tabs(self, select: str | None = None) -> None:
        keys = self.tab_keys()
        if self.tabs is not None:
            self.tabs.set_labels(self.tab_labels())
        if select in keys:
            self.tab = keys.index(select)
        self.tab = min(self.tab, len(keys) - 1)
        if self.tabs is not None:
            self.tabs.select(self.tab)
        self.on_resize(self.app.window.width, self.app.window.height)
        self.enter()

    def _new_discipline(self) -> None:
        from perennia.ui.goal_popup import GoalPopup

        def save(name: str) -> None:
            name = " ".join((name or "").split())
            if not name:
                return
            key = gym.add_discipline(self.app.db, name)
            self._refresh_tabs(select=key)
        self.app.push(GoalPopup(self.app, tr("Nova disciplina", "New discipline"),
                                tr("Ganha um separador próprio na lista de exercícios",
                                   "Gets its own tab in the exercise list"), "", 40, save))

    def _delete_discipline(self, key: str) -> None:
        def go() -> None:
            gym.delete_discipline(self.app.db, key)
            self._refresh_tabs()
        self.app.confirm(tr("Apagar esta disciplina?", "Delete this discipline?"),
                         tr("Os exercícios só dela passam para a Força.",
                            "Exercises only in it move to Strength."), go,
                         yes=tr("Apagar", "Delete"))

    def enter(self) -> None:
        a = self.app
        mod = self.modality()
        if mod == self.GROUPS_TAB:
            from perennia.ui import muscle_screens
            self.chrome.set(tr("Exercícios", "Exercises"),
                            tr("Grupos e subgrupos musculares · Enter abre um grupo",
                               "Muscle groups and subgroups · Enter opens a group"),
                            tr("Tab modalidade · Enter abrir · Esc voltar",
                               "Tab modality · Enter open · Esc back"))
            self.list.set_items(muscle_screens.group_items(a, self.enter), keep_index=True)
            return
        m = gym.modality(mod)
        # adicionar e filtrar: em cima, à direita, alinhados; a lista fica só
        # com os exercícios (Enter abre um para editar, numa janela)
        items = [Item((tr("✓ ", "✓ ") if self.only_available else "") +
                      tr("Só com o meu material", "Only my equipment"),
                      action=self._toggle, top=True),
                 Item(tr("+ Novo exercício", "+ New exercise"),
                      action=lambda: a.push(ExerciseEditor(a, None, mod)), top=True),
                 Item(tr("+ Nova disciplina", "+ New discipline"),
                      action=self._new_discipline, top=True)]
        if gym.is_custom(mod):
            items.append(Item(tr("Apagar esta disciplina", "Delete this discipline"),
                              action=lambda: self._delete_discipline(mod), top=True))
        exs = gym.exercises(a.db, mod, available_only=self.only_available)
        for e in exs:
            kit = ", ".join(inventory.kind_name(k) for k in e["equipment"]) or \
                tr("sem material", "no equipment")
            missing = gym.missing_equipment(a.db, e) if inventory.items(a.db) else []
            unit = tr("tempo", "time") if e["measure"] == "time" else tr("reps", "reps")
            other = [gym.modality(x).name for x in e["modalities"] if x != mod]
            detail = kit + f" · {unit}"
            if other:
                detail += " · " + ", ".join(other[:2])
            if missing:
                detail += " · " + tr("falta: {k}", "missing: {k}",
                                     k=", ".join(inventory.kind_name(k) for k in missing))
            act = (lambda ex=e: self._picked(ex)) if self.pick else \
                (lambda eid=e["id"]: a.push(ExerciseEditor(a, eid, mod)))
            items.append(Item(e["name"], value="✓" if self.pick else "", detail=detail,
                              action=act, data=("exercise", e["id"])))
        title = tr("Escolhe o exercício", "Pick the exercise") if self.pick else \
            tr("Exercícios", "Exercises")
        self.chrome.set(title, f"{m.name} · " + tr("{n} exercícios", "{n} exercises",
                                                   n=len(exs)),
                        tr("Tab modalidade · Enter abrir · Esc voltar",
                           "Tab modality · Enter open · Esc back"))
        self.list.set_items(items, keep_index=True)

    def _toggle(self) -> None:
        self.only_available = not self.only_available
        self.enter()

    def _picked(self, ex: dict) -> None:
        cb = self.pick
        cb(ex)
        self.app.pop()


class ExerciseEditor(EditPopup):
    """Um exercício (nome, grupo, medida, modalidades, material), numa janela."""

    MAX_H = 720

    def __init__(self, app, eid: int | None, modality: str = "strength"):
        super().__init__(app)
        self.eid = eid
        gym.ensure(app.db)
        e = gym.exercise(app.db, eid) if eid else None
        self.v = {"name": (e or {}).get("name") or "",
                  "group": (e or {}).get("category") or "full",
                  "subgroup": (e or {}).get("subgroup_id"),
                  "measure": (e or {}).get("measure") or "reps",
                  "bodyweight": (e or {}).get("bodyweight") or 0.0,
                  "mods": list((e or {}).get("modalities") or [modality]),
                  "kit": list((e or {}).get("equipment") or []),
                  "description": (e or {}).get("description") or ""}

    def title(self) -> str:
        return tr("Exercício", "Exercise") if self.eid else tr("Novo exercício", "New exercise")

    def subtitle(self) -> str:
        return self.v["name"]

    def rows(self) -> list[Item]:
        v = self.v
        db = self.app.db
        items = [
            Item(tr("Nome", "Name"), value=v["name"] + "▏", data="text:name"),
            Item(tr("Grupo muscular", "Muscle group"), value=muscles.group_name(db, v["group"]),
                 data="cyc:group",
                 detail=tr("Enter abre a lista · os grupos geres no separador Grupos Musculares",
                           "Enter opens the list · manage groups in the Muscle Groups tab")),
            Item(tr("Subgrupo muscular", "Muscle subgroup"),
                 value=muscles.subgroup_name(db, v["subgroup"]), data="cyc:subgroup",
                 detail=tr("os do grupo escolhido", "the chosen group's")),
            Item(tr("Mede-se em", "Measured in"),
                 value=tr("repetições", "reps") if v["measure"] == "reps"
                 else tr("tempo (s)", "time (s)"), data="cyc:measure"),
            Item(tr("Peso do corpo no volume", "Bodyweight in volume"),
                 value=f"{v['bodyweight'] * 100:.0f} %", data="num:bodyweight",
                 detail=tr("flexões ≈ 65 %, elevações ≈ 100 %", "push-ups ≈ 65 %, pull-ups ≈ 100 %")),
            Item(tr("Modalidades", "Modalities"),
                 value=", ".join(gym.modality(x).name for x in v["mods"]) or "—",
                 detail=tr("Enter abre a lista com pesquisa e marca as que quiseres",
                           "Enter opens the searchable list; tick as many as you like"),
                 action=self._pick_mods),
            Item(tr("Material", "Equipment"),
                 value=", ".join(inventory.kind_name(k) for k in v["kit"]) or
                 tr("nenhum", "none"),
                 detail=tr("Enter abre a lista com pesquisa e marca o que usa",
                           "Enter opens the searchable list; tick what it uses"),
                 action=self._pick_kit),
            Item(tr("Descrição", "Description"), value=(v["description"] or "") + "▏",
                 data="text:description"),
        ]
        return items

    def cycle(self, field: str, step: int) -> None:
        v = self.v
        if field == "group":
            g = [x["key"] for x in muscles.groups(self.app.db)] or ["full"]
            new = g[(g.index(v["group"]) + step) % len(g)] if v["group"] in g else g[0]
            if new != v["group"]:
                v["group"], v["subgroup"] = new, None      # os subgrupos são do grupo
        elif field == "subgroup":
            subs = [None] + [s["id"] for x in muscles.groups(self.app.db)
                             if x["key"] == v["group"] for s in x["subgroups"]]
            cur = subs.index(v["subgroup"]) if v["subgroup"] in subs else 0
            v["subgroup"] = subs[(cur + step) % len(subs)]
        elif field == "measure":
            v["measure"] = "time" if v["measure"] == "reps" else "reps"

    def _pick_mods(self) -> None:
        from perennia.ui.pickers import MultiChoicePopup

        def done(sel: list[str]) -> None:
            self.v["mods"] = sel
            self.enter()
        self.app.push(MultiChoicePopup(
            self.app, tr("Modalidades", "Modalities"),
            [(m.key, m.name) for m in gym.modalities()], self.v["mods"], done, min_one=True))

    def _pick_kit(self) -> None:
        from perennia.ui.pickers import MultiChoicePopup

        def done(sel: list[str]) -> None:
            self.v["kit"] = sel
            self.enter()
        self.app.push(MultiChoicePopup(
            self.app, tr("Material", "Equipment"),
            [(k, inventory.kind_name(k)) for k in inventory.KINDS], self.v["kit"], done))

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        self.v["bodyweight"] = max(0.0, min(1.0, round(self.v["bodyweight"] + steps * 0.05, 2)))

    def num_set(self, field: str, value) -> None:
        self.v["bodyweight"] = max(0.0, min(1.0, (value or 0) / 100.0))

    def text_input(self, field: str, text: str) -> None:
        self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def saved_message(self) -> str:
        return tr("Exercício guardado", "Exercise saved")

    def commit(self) -> bool:
        v = self.v
        if not v["name"].strip():
            self.app.message(tr("Escreve o nome do exercício.", "Type the exercise name."))
            return False
        self.eid = gym.save_exercise(self.app.db, self.eid, name=v["name"], mods=v["mods"],
                                     group=v["group"], measure=v["measure"],
                                     bodyweight=v["bodyweight"], equipment=v["kit"],
                                     description=v["description"] or None,
                                     subgroup=v["subgroup"])
        return True
