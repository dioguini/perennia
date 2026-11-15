"""Complexos (kettlebell e afins): criar e editar um exercício feito de outros exercícios.

Cada linha é um exercício do complexo com as repetições por ronda (←/→ ou escrever o número);
Enter troca o exercício, Del tira-o, Ctrl+↑/↓ muda-lhe a ordem. «+ Juntar exercício» acrescenta
mais um. No treino, o complexo é um só exercício (as «repetições» são as rondas) e a sessão
mostra os exercícios que o compõem."""
from __future__ import annotations

from pyglet.window import key

from perennia.core import complexes, gym
from perennia.core.i18n import tr
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Dropdown, Item


class ComplexEditor(EditPopup):
    MAX_H = 720

    def __init__(self, app, cid: int | None, modality: str = "kettlebell"):
        super().__init__(app)
        complexes.ensure(app.db)
        self.cid = cid
        e = gym.exercise(app.db, cid) if cid else None
        mods = (e or {}).get("modalities") or [modality if modality in gym.MODALITIES
                                               else "kettlebell"]
        self.v = {"name": (e or {}).get("name") or "", "mod": mods[0],
                  "parts": [[p["exercise_id"], p["name"], p["reps"], p["measure"]]
                            for p in complexes.parts(app.db, cid)] if cid else []}

    def title(self) -> str:
        return tr("Complexo", "Complex") if self.cid else tr("Novo complexo", "New complex")

    def subtitle(self) -> str:
        v = self.v
        if not v["parts"]:
            return tr("Junta os exercícios, pela ordem em que se fazem",
                      "Add the exercises, in the order you do them")
        return " → ".join(f"{p[1]} {p[2]}" for p in v["parts"])

    def rows(self) -> list[Item]:
        v = self.v
        mods = list(gym.MODALITIES)
        rows = [Item(tr("Nome", "Name"), value=v["name"] + "▏", data="text:name"),
                Item(tr("Modalidade", "Modality"), value=gym.modality(v["mod"]).name,
                     dropdown=Dropdown([gym.modality(k).name for k in mods],
                                       mods.index(v["mod"]) if v["mod"] in mods else 0,
                                       self._pick_mod, title=tr("Modalidade", "Modality")))]
        for i, (_eid, name, reps, measure) in enumerate(v["parts"]):
            unit = tr("s por ronda", "s per round") if measure == "time" else \
                tr("rep. por ronda", "reps per round")
            rows.append(Item(f"{i + 1}. {name}", value=f"{reps} {unit}", data=f"num:p{i}",
                             action=lambda k=i: self._swap(k),
                             detail=tr("←/→ repetições · Enter troca o exercício · Del tira · "
                                       "Ctrl+↑/↓ muda a ordem",
                                       "←/→ reps · Enter swaps the exercise · Del removes · "
                                       "Ctrl+↑/↓ reorders")))
        rows.append(Item(tr("+ Juntar exercício", "+ Add exercise"), action=self._add,
                         detail=tr("escolhe um exercício da lista (não pode ser outro complexo)",
                                   "pick an exercise from the list (not another complex)")))
        if self.cid:
            rows.append(Item(tr("Apagar o complexo", "Delete the complex"), action=self._ask_delete,
                             detail=tr("o histórico mantém-se", "the history is kept")))
        return rows

    def _pick_mod(self, i: int) -> None:
        self.v["mod"] = list(gym.MODALITIES)[i]
        self.enter()

    # -------------------------------------------------------- exercícios

    def _chooser(self, cb) -> None:
        from perennia.ui.hub_screens import ExerciseInventory

        def picked(ex: dict) -> None:
            if ex.get("complex"):
                self.app.message(tr("Um complexo não pode conter outro complexo.",
                                    "A complex cannot contain another complex."))
                return
            cb(ex)
        self.app.push(ExerciseInventory(self.app, self.v["mod"], pick=picked))

    def _add(self) -> None:
        def cb(ex: dict) -> None:
            self.v["parts"].append([ex["id"], ex["name"], complexes.PART_REPS,
                                    ex.get("measure") or "reps"])
            self.enter()
        self._chooser(cb)

    def _swap(self, i: int) -> None:
        def cb(ex: dict) -> None:
            if 0 <= i < len(self.v["parts"]):
                p = self.v["parts"][i]
                p[0], p[1], p[3] = ex["id"], ex["name"], ex.get("measure") or "reps"
            self.enter()
        self._chooser(cb)

    def _field_index(self) -> int | None:
        f = self._field("num:p")
        return int(f) if f is not None and f.isdigit() else None

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field.startswith("p") and field[1:].isdigit():
            p = self.v["parts"][int(field[1:])]
            p[2] = max(1, min(200, p[2] + steps * (5 if big else 1)))

    def num_set(self, field: str, value) -> None:
        if field.startswith("p") and field[1:].isdigit():
            self.v["parts"][int(field[1:])][2] = max(1, min(200, int(value or 1)))

    def on_key(self, symbol: int, modifiers: int) -> bool:
        i = self._field_index()
        if i is not None and symbol == key.DELETE:
            del self.v["parts"][i]
            self.enter()
            return True
        if i is not None and symbol in (key.UP, key.DOWN) and modifiers & key.MOD_CTRL:
            j = i + (-1 if symbol == key.UP else 1)
            ps = self.v["parts"]
            if 0 <= j < len(ps):
                ps[i], ps[j] = ps[j], ps[i]
                self.enter()
                self.list.select_data(f"num:p{j}")
            return True
        return super().on_key(symbol, modifiers)

    def text_input(self, field: str, text: str) -> None:
        if len(self.v[field]) < 80:
            self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    # ------------------------------------------------------------ guardar

    def saved_message(self) -> str:
        return tr("Complexo guardado", "Complex saved")

    def commit(self) -> bool:
        v = self.v
        try:
            self.cid = complexes.save_complex(
                self.app.db, self.cid, v["name"], [(p[0], p[2]) for p in v["parts"]],
                mods=[v["mod"]], equipment=("kettlebell",) if v["mod"] == "kettlebell" else ())
        except ValueError as exc:
            self.app.message(str(exc))
            return False
        return True

    def _ask_delete(self) -> None:
        def go() -> None:
            complexes.delete_complex(self.app.db, self.cid)
            self._saved_state = self.state()
            self.close()
        self.app.confirm(tr("Apagar este complexo?", "Delete this complex?"),
                         tr("Deixa de aparecer nas listas; as sessões já feitas mantêm-no.",
                            "It stops showing in the lists; past sessions keep it."), go,
                         yes=tr("Apagar", "Delete"))
