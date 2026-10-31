"""Entradas dos desportos, estatísticas por desporto e os dois inventários
(artigos e exercícios)."""
from __future__ import annotations

from pyglet.window import key

from velo.core import gym, inventory
from velo.core.i18n import t, tr
from velo.ui.app import Screen
from velo.ui.sport_screens import EditScreen
from velo.ui.widgets import Item


def SportHub(app, sport: str):                     # noqa: N802 — fábrica
    """O menu do desporto (separadores Treinar · Construtor · Lista · Histórico ·
    Estatísticas)."""
    if sport == "cycling":
        from velo.ui.app import MainMenu
        return MainMenu(app)
    if sport == "rowing":
        from velo.ui.rowing_screens import RowingMenu
        return RowingMenu(app)
    if sport in ("running", "swimming"):
        from velo.ui.endurance_screens import EnduranceHub
        return EnduranceHub(app, sport)
    from velo.ui.gym_screens import GymHub
    return GymHub(app)


def stats_screen(app, sport: str | None):
    """As estatísticas, já no desporto pedido (None = todos)."""
    from velo.ui import stats_screens
    return stats_screens.for_sport(app, sport)


# ============================================================ inventário


class InventoryScreen(Screen):
    """O teu material, por grupos (máquinas, pesos livres, estações…)."""

    TABBED = True

    def tab_labels(self) -> list[str]:
        return [tr(*v) for v in inventory.GROUPS.values()]

    def group(self) -> str:
        return list(inventory.GROUPS)[self.tab % len(inventory.GROUPS)]

    def enter(self) -> None:
        a = self.app
        g = self.group()
        kinds = [k for k, v in inventory.KINDS.items() if v[2] == g]
        items = [Item(tr("+ Novo artigo", "+ New item"),
                      action=lambda: a.push(ItemEditor(a, None, kinds[0] if kinds else "other")))]
        for r in inventory.items(a.db):
            if r["kind"] not in kinds:
                continue
            w = f" · {r['weight_kg']:g} kg" if r["weight_kg"] else ""
            items.append(Item(r["name"], value=f"× {r['qty']}",
                              detail=inventory.kind_name(r["kind"]) + w
                              + (" · " + r["notes"] if r["notes"] else ""),
                              action=lambda iid=r["id"]: a.push(ItemEditor(a, iid)),
                              data=("item", r["id"])))
        summ = inventory.summary(a.db)
        self.chrome.set(tr("Inventário de artigos", "Equipment"),
                        tr("{a} artigos · {u} unidades", "{a} items · {u} units",
                           a=summ["articles"], u=summ["units"]),
                        tr("Tab grupo · Enter editar · Esc voltar",
                           "Tab group · Enter edit · Esc back"))
        self.list.set_items(items, keep_index=True)

    def agent_data(self) -> dict:
        return {"artigos": [{k: r[k] for k in ("name", "kind", "qty", "weight_kg")}
                            for r in inventory.items(self.app.db)]}


class ItemEditor(EditScreen):
    def __init__(self, app, iid: int | None, kind: str = "other"):
        super().__init__(app)
        self.iid = iid
        r = inventory.item(app.db, iid) if iid else None
        self.v = {"name": (r or {}).get("name") or "", "kind": (r or {}).get("kind") or kind,
                  "qty": (r or {}).get("qty", 1), "weight_kg": (r or {}).get("weight_kg"),
                  "notes": (r or {}).get("notes") or ""}
        self._armed = False

    def enter(self) -> None:
        v = self.v
        items = [Item(tr("Tipo", "Kind"), value=inventory.kind_name(v["kind"]),
                      data="cyc:kind", detail=tr("←/→ muda · é o que os exercícios pedem",
                                                 "←/→ changes · it is what exercises ask for")),
                 Item(tr("Nome", "Name"), value=(v["name"] or "") + "▏", data="text:name",
                      detail=tr("ex.: Disco de 1 kg, Domyos Rowing 500B",
                                "e.g. 1 kg plate, Domyos Rowing 500B")),
                 Item(tr("Quantidade", "Quantity"), value=str(v["qty"]), data="num:qty"),
                 Item(tr("Peso (kg)", "Weight (kg)"),
                      value="—" if v["weight_kg"] is None else f"{v['weight_kg']:g} kg",
                      data="num:weight_kg", detail=tr("de cada um (opcional)",
                                                      "each (optional)")),
                 Item(tr("Notas", "Notes"), value=(v["notes"] or "") + "▏", data="text:notes"),
                 Item(tr("✓ Guardar", "✓ Save"), action=self._save),
                 Item(tr("Apagar", "Delete"), action=self._delete, enabled=bool(self.iid))]
        self.chrome.set(tr("Artigo", "Item"), inventory.kind_name(v["kind"]), self.footer())
        self.list.set_items(items, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        ks = list(inventory.KINDS)
        self.v["kind"] = ks[(ks.index(self.v["kind"]) + step) % len(ks)]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field == "qty":
            self.v["qty"] = max(0, self.v["qty"] + steps * (5 if big else 1))
        else:
            cur = self.v["weight_kg"] or 0.0
            self.v["weight_kg"] = max(0.0, round(cur + steps * (5 if big else 0.5), 2))

    def num_set(self, field: str, value) -> None:
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

    def _save(self) -> None:
        v = self.v
        inventory.save(self.app.db, self.iid, name=v["name"], kind=v["kind"], qty=v["qty"],
                       weight_kg=v["weight_kg"], notes=v["notes"] or None)
        self.app.message(tr("Artigo guardado", "Item saved"))
        self.app.pop()

    def _delete(self) -> None:
        if not self._armed:
            self._armed = True
            self.app.message(tr("Escolhe outra vez para apagar.", "Choose again to delete."))
            return
        inventory.delete(self.app.db, self.iid)
        self.app.pop()


# =========================================================== exercícios


class ExerciseInventory(Screen):
    """Os exercícios de cada modalidade do ginásio: ver, juntar, editar.
    Com `pick`, escolhe um para um treino (e só mostra os da modalidade)."""

    TABBED = True

    def __init__(self, app, modality: str | None = None, pick=None):
        self.fixed = modality
        self.pick = pick
        self.only_available = False
        super().__init__(app)
        if modality:
            keys = [m.key for m in gym.modalities()]
            self.tab = keys.index(modality) if modality in keys else 0
            if self.tabs is not None:
                self.tabs.select(self.tab)

    def tab_labels(self) -> list[str]:
        return [m.name for m in gym.modalities()]

    def modality(self) -> str:
        mods = gym.modalities()
        return mods[self.tab % len(mods)].key

    def enter(self) -> None:
        a = self.app
        mod = self.modality()
        m = gym.modality(mod)
        items = [Item(tr("+ Novo exercício", "+ New exercise"),
                      action=lambda: a.push(ExerciseEditor(a, None, mod))),
                 Item(tr("Só o que posso fazer com o meu material",
                         "Only what my equipment allows"),
                      value=tr("sim", "yes") if self.only_available else tr("não", "no"),
                      action=self._toggle)]
        exs = gym.exercises(a.db, mod, available_only=self.only_available)
        for e in exs:
            kit = ", ".join(inventory.kind_name(k) for k in e["equipment"]) or \
                tr("sem material", "no equipment")
            missing = gym.missing_equipment(a.db, e) if inventory.items(a.db) else []
            unit = tr("tempo", "time") if e["measure"] == "time" else tr("reps", "reps")
            other = [gym.modality(x).name for x in e["modalities"] if x != mod]
            detail = kit + f" · {unit}"
            if other and not m.multi:
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


class ExerciseEditor(EditScreen):
    GROUPS = ("legs", "hips", "chest", "back", "shoulders", "arms", "core", "full", "mobility")

    def __init__(self, app, eid: int | None, modality: str = "strength"):
        super().__init__(app)
        self.eid = eid
        e = gym.exercise(app.db, eid) if eid else None
        self.v = {"name": (e or {}).get("name") or "",
                  "group": (e or {}).get("category") or "full",
                  "measure": (e or {}).get("measure") or "reps",
                  "bodyweight": (e or {}).get("bodyweight") or 0.0,
                  "mods": list((e or {}).get("modalities") or [modality]),
                  "kit": list((e or {}).get("equipment") or []),
                  "description": (e or {}).get("description") or ""}
        self.mod_cursor = 0
        self.kit_cursor = 0

    def enter(self) -> None:
        v = self.v
        mods = gym.modalities()
        kinds = list(inventory.KINDS)
        mc = mods[self.mod_cursor % len(mods)]
        kc = kinds[self.kit_cursor % len(kinds)]
        items = [
            Item(tr("Nome", "Name"), value=v["name"] + "▏", data="text:name"),
            Item(tr("Grupo muscular", "Muscle group"), value=t(f"str.group.{v['group']}"),
                 data="cyc:group"),
            Item(tr("Mede-se em", "Measured in"),
                 value=tr("repetições", "reps") if v["measure"] == "reps"
                 else tr("tempo (s)", "time (s)"), data="cyc:measure"),
            Item(tr("Peso do corpo no volume", "Bodyweight in volume"),
                 value=f"{v['bodyweight'] * 100:.0f} %", data="num:bodyweight",
                 detail=tr("flexões ≈ 65 %, elevações ≈ 100 %", "push-ups ≈ 65 %, pull-ups ≈ 100 %")),
            Item(tr("Modalidades", "Modalities"),
                 value=", ".join(gym.modality(x).name for x in v["mods"]) or "—",
                 enabled=False),
            Item(("✓ " if mc.key in v["mods"] else "   ") + mc.name,
                 detail=tr("←/→ outra modalidade · Enter junta/tira",
                           "←/→ another modality · Enter adds/removes"),
                 data="cyc:modcur", action=lambda: self._toggle_mod(mc.key)),
            Item(tr("Material", "Equipment"),
                 value=", ".join(inventory.kind_name(k) for k in v["kit"]) or
                 tr("nenhum", "none"), enabled=False),
            Item(("✓ " if kc in v["kit"] else "   ") + inventory.kind_name(kc),
                 detail=tr("←/→ outro material · Enter junta/tira",
                           "←/→ another item · Enter adds/removes"),
                 data="cyc:kitcur", action=lambda: self._toggle_kit(kc)),
            Item(tr("Descrição", "Description"), value=(v["description"] or "") + "▏",
                 data="text:description"),
            Item(tr("✓ Guardar", "✓ Save"), action=self._save),
        ]
        if self.eid:
            items.append(Item(tr("Arquivar (deixa de aparecer)", "Archive (hide it)"),
                              action=self._archive))
        self.chrome.set(tr("Exercício", "Exercise"), v["name"], self.footer())
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        cyc = self._field("cyc:")
        if cyc in ("modcur", "kitcur") and symbol in (key.ENTER, key.RETURN, key.SPACE):
            self.list.activate()
            return True
        return super().on_key(symbol, modifiers)

    def cycle(self, field: str, step: int) -> None:
        v = self.v
        if field == "group":
            g = list(self.GROUPS)
            v["group"] = g[(g.index(v["group"]) + step) % len(g)] if v["group"] in g else g[0]
        elif field == "measure":
            v["measure"] = "time" if v["measure"] == "reps" else "reps"
        elif field == "modcur":
            self.mod_cursor += step
        elif field == "kitcur":
            self.kit_cursor += step

    def _toggle_mod(self, key_: str) -> None:
        mods = self.v["mods"]
        if key_ in mods and len(mods) > 1:
            mods.remove(key_)
        elif key_ not in mods:
            mods.append(key_)
        self.enter()

    def _toggle_kit(self, kind: str) -> None:
        kit = self.v["kit"]
        kit.remove(kind) if kind in kit else kit.append(kind)
        self.enter()

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

    def _save(self) -> None:
        v = self.v
        if not v["name"].strip():
            self.app.message(tr("Escreve o nome do exercício.", "Type the exercise name."))
            return
        self.eid = gym.save_exercise(self.app.db, self.eid, name=v["name"], mods=v["mods"],
                                     group=v["group"], measure=v["measure"],
                                     bodyweight=v["bodyweight"], equipment=v["kit"],
                                     description=v["description"] or None)
        self.app.message(tr("Exercício guardado", "Exercise saved"))
        self.app.pop()

    def _archive(self) -> None:
        gym.archive_exercise(self.app.db, self.eid)
        self.app.pop()
