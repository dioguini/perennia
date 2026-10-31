"""Ginásio: separadores do desporto, as modalidades e os seus treinos.

Cada modalidade tem: Treino livre (montas o plano primeiro e só depois
começa o relógio; podes guardá-lo), Treino surpresa, os seus treinos, criar
treino, os exercícios e o histórico. O Conditioning (voltas de máquina e
de força) monta um plano de voltas.
"""
from __future__ import annotations

import time

from pyglet.window import key

from velo.core import gym, inventory
from velo.core import laps_session as ls
from velo.core import strength as st
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.ui.app import Screen, SportHub, StartOptions
from velo.ui.sport_screens import (EditScreen, LapSessionScreen, StrengthPreview,
                                   StrengthSessionDetail, StrengthSessionScreen,
                                   StrengthWorkoutEditor)
from velo.ui.widgets import Item


def _kind(k: str) -> str:
    return t(f"laps.kind.{k}")


class GymHub(SportHub):
    SPORT = "gym"

    def subtitle(self) -> str:
        hub = self.app.hub
        try:
            hr = hub.reading().hr_bpm
        except Exception:
            hr = None
        hr_txt = tr("FC {b} bpm", "HR {b} bpm", b=hr) if hr else tr(
            "sem FC (liga a banda ou o relógio em Dispositivos)",
            "no HR (connect the strap or watch in Devices)")
        return tr("{n} modalidades · {h}", "{n} modalities · {h}", n=len(gym.modalities()),
                  h=hr_txt)

    def items_train(self) -> list[Item]:
        a = self.app
        items = []
        for m in gym.modalities():
            n = len(gym.workouts(a.db, m.key)) if not m.laps else len(ls.plans(a.db, m.key))
            items.append(Item(m.name, value=tr("{n} treinos", "{n} workouts", n=n) if n else "",
                              detail=m.desc, action=lambda k=m.key: a.push(ModalityScreen(a, k)),
                              data=("modality", m.key)))
        from velo.ui.hub_screens import ExerciseInventory, InventoryScreen
        items += [Item(tr("Exercícios", "Exercises"),
                       detail=tr("O inventário de exercícios de cada modalidade",
                                 "Each modality's exercise list"),
                       action=lambda: a.push(ExerciseInventory(a))),
                  Item(tr("Inventário de artigos", "Equipment"),
                       detail=tr("O teu material: o treino surpresa só usa o que tens",
                                 "Your equipment: the surprise workout only uses what you have"),
                       action=lambda: a.push(InventoryScreen(a)))]
        return items

    def items_builder(self) -> list[Item]:
        a = self.app
        items = [Item(tr("+ Novo treino", "+ New workout"),
                      detail=tr("Escolhe a modalidade", "Pick the modality"),
                      action=lambda: a.push(ModalityPicker(a)))]
        for w in gym.workouts(a.db):
            m = gym.modality(w.get("modality"))
            items.append(Item(w["name"], value=m.name,
                              detail=tr("{n} exercícios · {s} séries", "{n} exercises · {s} sets",
                                        n=w["n_items"], s=w["n_sets"]),
                              action=lambda wid=w["id"], mk=m.key: a.push(
                                  _builder(a, mk, wid))))
        for p in ls.plans(a.db, "conditioning"):
            items.append(Item(p["name"], value="Conditioning",
                              detail=tr("{n} voltas", "{n} laps", n=len(p["items"])),
                              action=lambda pid=p["id"]: a.push(LapPlanEditor(a, pid))))
        return items

    def items_library(self) -> list[Item]:
        a = self.app
        items = []
        for m in gym.modalities():
            ws = gym.workouts(a.db, m.key) if not m.laps else []
            ps = ls.plans(a.db, "conditioning") if m.laps else []
            if not ws and not ps:
                continue
            items.append(Item(f"— {m.name} —", enabled=False))
            for w in ws:
                plan = st.workout_items(a.db, w["id"])
                items.append(Item(w["name"], value=f"≈ {hms(st.plan_seconds(plan))}",
                                  detail=tr("{n} exercícios", "{n} exercises", n=len(plan)),
                                  action=lambda wid=w["id"]: a.push(StrengthPreview(a, wid))))
            for p in ps:
                items.append(Item(p["name"], value=f"≈ {hms(ls.plan_seconds(p['items']))}",
                                  action=lambda pid=p["id"]: start_laps(a, "conditioning",
                                                                        ls.plan(a.db, pid)[
                                                                            "items"])))
        return items

    def items_history(self) -> list[Item]:
        a = self.app
        out = []
        for s in gym.sessions(a.db):
            mod = s.get("modality") or ("conditioning" if s.get("mode") in
                                        ("free", "conditioning") else "strength")
            out.append(Item(f"{str(s['started_at'])[:16].replace('T', ' ')}  {_pretty(s['name'])}",
                            value=hms(s["elapsed_s"] or 0),
                            detail=gym.modality(mod).name
                            + (f" · {s['total_sets']} " + tr("séries", "sets")
                               if s.get("total_sets") else "")
                            + (f" · {s['avg_hr']:.0f} bpm" if s.get("avg_hr") else ""),
                            action=lambda sid=s["id"]: a.push(_analysis(a, sid))))
        return out

    def items_stats(self) -> list[Item]:
        ss = gym.sessions(self.app.db, None, 1000)
        hours = sum(s["elapsed_s"] or 0 for s in ss) / 3600
        vol = sum(s.get("volume_kg") or 0 for s in ss)
        a = self.app
        return super().items_stats() + [
            Item(tr("Estatísticas por exercício", "Exercise statistics"),
                 detail=tr("Evolução da carga, 1RM, volume, RPE e tempo de cada exercício",
                           "Progress of load, 1RM, volume, RPE and time per exercise"),
                 action=lambda: a.push(_exercise_stats(a))),
            Item(tr("Sessões", "Sessions"), value=str(len(ss)), enabled=False),
            Item(tr("Horas", "Hours"), value=f"{hours:.1f}", enabled=False),
            Item(tr("Volume total", "Total volume"), value=f"{vol:,.0f} kg".replace(",", " "),
                 enabled=False)]

    def update(self, dt: float) -> None:
        self.app.hub.tick(dt)


class ModalityPicker(Screen):
    def enter(self) -> None:
        a = self.app
        self.chrome.set(tr("Novo treino de ginásio", "New gym workout"),
                        tr("Escolhe a modalidade", "Pick the modality"), self.footer())
        self.list.set_items([Item(m.name, detail=m.desc, action=lambda k=m.key: a.replace(
            LapPlanEditor(a, None) if gym.modality(k).laps else _builder(a, k)))
            for m in gym.modalities()])


class ModalityScreen(Screen):
    """Uma modalidade: treino livre, surpresa, os seus treinos, exercícios."""

    def __init__(self, app, mod: str):
        super().__init__(app)
        self.mod = mod

    def enter(self) -> None:
        a = self.app
        m = gym.modality(self.mod)
        from velo.ui.hub_screens import ExerciseInventory
        if m.laps:
            items = [Item(tr("Treino livre", "Free workout"),
                          detail=tr("Monta o plano de voltas e depois começa",
                                    "Build the lap plan, then start"),
                          action=lambda: a.push(LapPlanEditor(a, None, draft=True))),
                     Item(tr("Treino surpresa", "Surprise workout"),
                          detail=tr("Voltas de máquina e de força à sorte",
                                    "Random machine and strength laps"),
                          action=lambda: a.push(LapPlanEditor(
                              a, None, draft=True, items=ls.surprise_plan(
                                  a.db, int(time.time()) % 100000)))),
                     Item(tr("+ Criar plano", "+ Create plan"),
                          action=lambda: a.push(LapPlanEditor(a, None)))]
            for p in ls.plans(a.db, "conditioning"):
                items.append(Item(p["name"], value=f"≈ {hms(ls.plan_seconds(p['items']))}",
                                  detail=tr("{n} voltas · E editar", "{n} laps · E edit",
                                            n=len(p["items"])),
                                  action=lambda pid=p["id"]: start_laps(
                                      a, "conditioning", ls.plan(a.db, pid)["items"]),
                                  data=("plan", p["id"])))
        else:
            items = [Item(tr("Treino livre", "Free workout"),
                          detail=tr("Monta o plano e depois começa (podes guardá-lo)",
                                    "Build the plan, then start (you can save it)"),
                          action=lambda: a.push(GymPlanEditor(a, self.mod, None, draft=True))),
                     Item(tr("Treino surpresa", "Surprise workout"),
                          detail=tr("Exercícios à sorte, só com o material que tens",
                                    "Random exercises, only with the equipment you have"),
                          action=lambda: a.push(SurpriseScreen(a, self.mod))),
                     Item(tr("+ Criar treino (construtor por blocos)",
                             "+ Create workout (block builder)"),
                          detail=tr("Exercício único, superset, circuito, aquecimento, retorno à "
                                    "calma · séries, carga, RPE/RIR, % 1RM, tempo",
                                    "Single, superset, circuit, warm up, cool down · sets, "
                                    "load, RPE/RIR, % 1RM, time"),
                          action=lambda: a.push(_builder(a, self.mod))),
                     Item(tr("Treino livre por blocos", "Free workout in the block builder"),
                          detail=tr("Monta no construtor e começa; guardar é opcional",
                                    "Build it in the builder and start; saving is optional"),
                          action=lambda: a.push(_builder(a, self.mod, draft=True))),
                     Item(tr("+ Criar treino (editor simples)", "+ Create workout (simple editor)"),
                          action=lambda: a.push(GymPlanEditor(a, self.mod, None)))]
            for w in gym.workouts(a.db, self.mod):
                plan = st.workout_items(a.db, w["id"])
                last = f" · {t('str.last')} {w['last_done'][:10]}" if w.get("last_done") else ""
                items.append(Item(w["name"], value=f"≈ {hms(st.plan_seconds(plan))}",
                                  detail=tr("{n} exercícios", "{n} exercises", n=len(plan))
                                  + last + tr(" · E editar", " · E edit"),
                                  action=lambda wid=w["id"]: a.push(StrengthPreview(a, wid)),
                                  data=("workout", w["id"])))
        items.append(Item(tr("Exercícios de {m}", "{m} exercises", m=m.name),
                          value=str(len(gym.exercises(a.db, self.mod))),
                          action=lambda: a.push(ExerciseInventory(a, self.mod))))
        n_hist = len(gym.sessions(a.db, self.mod))
        items.append(Item(tr("Histórico", "History"), value=str(n_hist),
                          action=lambda: a.push(ModalityHistory(a, self.mod))))
        self.chrome.set(m.name, m.desc, self.footer())
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.E and item is not None and isinstance(item.data, tuple):
            if item.data[0] == "workout":
                self.app.push(_builder(self.app, self.mod, item.data[1]))
                return True
            if item.data[0] == "plan":
                self.app.push(LapPlanEditor(self.app, item.data[1]))
                return True
        return super().on_key(symbol, modifiers)


class ModalityHistory(Screen):
    def __init__(self, app, mod: str):
        super().__init__(app)
        self.mod = mod

    def enter(self) -> None:
        a = self.app
        items = [Item(f"{str(s['started_at'])[:16].replace('T', ' ')}  {_pretty(s['name'])}",
                      value=hms(s["elapsed_s"] or 0),
                      action=lambda sid=s["id"]: a.push(_analysis(a, sid)))
                 for s in gym.sessions(a.db, self.mod)]
        if not items:
            items = [Item(tr("Ainda sem sessões", "No sessions yet"), enabled=False)]
        self.chrome.set(tr("Histórico", "History"), gym.modality(self.mod).name, self.footer())
        self.list.set_items(items, keep_index=True)


# ============================================================ planos


class GymPlanEditor(StrengthWorkoutEditor):
    """O plano de uma modalidade. No treino livre (`draft`): monta-se, começa-se
    (o relógio só arranca na primeira série) e pode guardar-se como treino."""

    def __init__(self, app, mod: str, wid: str | None, draft: bool = False,
                 items: list[dict] | None = None):
        super().__init__(app, wid)
        self.mod = mod
        self.draft = draft
        m = gym.modality(mod)
        if wid is None:
            self.name = (tr("Treino livre", "Free workout") if draft else
                         tr("Treino de {m}", "{m} workout", m=m.name)) + \
                time.strftime(" · %d/%m")
        if items:
            for it in items:
                ex = st.exercise(app.db, it["exercise_id"]) or {}
                d = dict(it)
                d.update(name=ex.get("name", "?"), measure=ex.get("measure") or "reps",
                         bodyweight=ex.get("bodyweight") or 0.0, notes=it.get("notes"))
                self.items.append(d)

    def enter(self) -> None:
        super().enter()
        m = gym.modality(self.mod)
        rows = list(self.list.items)
        # o seletor de exercícios é o da modalidade (a Longevidade vê todos)
        for r in rows:
            if r.label == t("str.add_exercise"):
                r.action = self._pick
        if self.draft:
            rows = [r for r in rows if r.label not in (t("str.save"), t("str.save_train"))]
            rows += [Item(tr("▶ Começar o treino", "▶ Start the workout"),
                          detail=tr("o relógio só arranca na 1.ª série",
                                    "the clock starts with the 1st set"),
                          action=self._start, enabled=bool(self.items)),
                     Item(tr("Guardar como treino da modalidade", "Save as a modality workout"),
                          action=self._keep, enabled=bool(self.items))]
        self.chrome.title.text = (tr("Treino livre", "Free workout") if self.draft else
                                  t("menu.builder")) + f" · {m.name}" + (" *" if self.dirty
                                                                         else "")
        self.list.set_items(rows, keep_index=True)

    def _pick(self) -> None:
        from velo.ui.hub_screens import ExerciseInventory
        self.app.push(ExerciseInventory(self.app, self.mod, pick=self._add_exercise))

    def _save(self) -> str | None:
        if not self.items:
            self.app.message(t("str.empty_plan"))
            return None
        self.workout_id = gym.save_plan(self.app.db, self.workout_id, self.name,
                                        self.description or None, self.items, self.mod,
                                        hidden=self.draft)
        self.dirty = False
        self._esc_armed = False
        if not self.draft:
            self.app.message(t("str.saved", name=self.name))
        self.enter()
        return self.workout_id

    def _keep(self) -> None:
        self.draft = False
        wid = self._save()
        if wid:
            gym.keep_plan(self.app.db, wid, self.name)
            self.app.message(tr("Guardado em {m}: {n}", "Saved in {m}: {n}",
                                m=gym.modality(self.mod).name, n=self.name))
            self.draft = True                 # continua a poder começar daqui
            self._kept = True
            self.enter()

    def _start(self) -> None:
        kept = getattr(self, "_kept", False)
        if kept:
            self.draft = False
        wid = self._save()
        if wid:
            self.app.replace(StrengthSessionScreen(self.app, wid))


class SurpriseScreen(Screen):
    """O treino surpresa da modalidade: vês, trocas por outro, começas ou guardas."""

    def __init__(self, app, mod: str, seed: int | None = None):
        super().__init__(app)
        self.mod = mod
        self.seed = seed if seed is not None else int(time.time()) % 100000
        self.items = gym.surprise(app.db, mod, self.seed)

    def enter(self) -> None:
        a = self.app
        m = gym.modality(self.mod)
        rows = [Item(tr("▶ Começar", "▶ Start"), action=self._start),
                Item(tr("↻ Outra surpresa", "↻ Another surprise"), action=self._again),
                Item(tr("Ajustar antes de começar", "Adjust before starting"),
                     action=lambda: a.replace(GymPlanEditor(a, self.mod, None, draft=True,
                                                            items=self.items)))]
        plan = []
        for i, it in enumerate(self.items):
            ex = st.exercise(a.db, it["exercise_id"]) or {}
            unit = " s" if ex.get("measure") == "time" else ""
            rows.append(Item(f"{i + 1}. {ex.get('name', '?')}",
                             value=f"{it['sets']} × {it['reps']}{unit}",
                             detail=tr("descanso {r}", "rest {r}", r=hms(it["rest_s"])),
                             enabled=False))
            plan.append(st.PlanItem(it["exercise_id"], ex.get("name", ""), it["sets"],
                                    it["reps"], rest_s=it["rest_s"],
                                    measure=ex.get("measure") or "reps"))
        have = inventory.items(a.db)
        note = tr("com o teu material", "with your equipment") if have else \
            tr("inventário vazio: conta com tudo", "empty inventory: assumes everything")
        self.chrome.set(tr("Treino surpresa", "Surprise workout") + f" · {m.name}",
                        f"≈ {hms(st.plan_seconds(plan))} · {note}", self.footer())
        self.list.set_items(rows, keep_index=True)

    def _again(self) -> None:
        self.seed += 1
        self.items = gym.surprise(self.app.db, self.mod, self.seed)
        self.enter()

    def _start(self) -> None:
        if not self.items:
            self.app.message(tr("Sem exercícios para esta modalidade.",
                                "No exercises for this modality."))
            return
        wid = gym.save_plan(self.app.db, None, tr("Surpresa", "Surprise") + " · " +
                            gym.modality(self.mod).name + time.strftime(" · %d/%m"), None,
                            self.items, self.mod, hidden=True)
        self.app.replace(StrengthSessionScreen(self.app, wid))


# =============================================================== conditioning


def start_laps(app, mode: str, items: list[dict] | None, replace: bool = False) -> None:
    title = t(f"laps.mode.{mode}")

    def go(autolap: dict, _o: dict) -> None:
        app.replace(LapSessionScreen(app, mode, plan=items, autolap=autolap))
    lines = [tr("{n} voltas no plano", "{n} laps in the plan", n=len(items or []))] if items \
        else []
    scr = StartOptions(app, "gym", title, go, lines=lines)
    app.replace(scr) if replace else app.push(scr)


class LapPlanEditor(EditScreen):
    """Plano de voltas (Conditioning): monta-se antes de começar."""

    KINDS = ("treadmill", "rowing", "strength", "rest", "cardio")

    def __init__(self, app, pid: str | None, draft: bool = False,
                 items: list[dict] | None = None):
        super().__init__(app)
        self.pid = pid
        self.draft = draft
        p = ls.plan(app.db, pid) if pid else None
        self.name = p["name"] if p else (tr("Conditioning livre", "Free conditioning")
                                         if draft else tr("Plano de Conditioning",
                                                          "Conditioning plan"))
        self.items: list[dict] = list(p["items"]) if p else list(items or [])

    def text_of(self, it: dict) -> str:
        bits = [_kind(it["kind"])]
        if it.get("name"):
            bits.append(it["name"])
        return " · ".join(bits)

    def value_of(self, it: dict) -> str:
        if it["kind"] == "strength":
            unit = " s" if it.get("measure") == "time" else ""
            return f"{it.get('reps') or 10}{unit}" + (f" @ {it['load_kg']:g} kg"
                                                      if it.get("load_kg") else "")
        if it.get("km"):
            return f"{it['km']:g} km"
        return hms(it.get("seconds") or 0) if it.get("seconds") else tr("livre", "open")

    def enter(self) -> None:
        rows = [Item(tr("Nome", "Name"), value=self.name + "▏", data="text:name")]
        for i, it in enumerate(self.items):
            rows.append(Item(f"{i + 1}. {self.text_of(it)}", value=self.value_of(it),
                             detail=tr("←/→ muda · Shift+←/→ move · Del apaga",
                                       "←/→ changes · Shift+←/→ moves · Del deletes"),
                             data=f"num:{i}"))
        for k in self.KINDS:
            rows.append(Item(tr("+ Volta: {k}", "+ Lap: {k}", k=_kind(k)),
                             action=lambda kk=k: self._add(kk)))
        rows += [Item(tr("▶ Começar", "▶ Start"), action=self._start,
                      enabled=bool(self.items),
                      detail=tr("o relógio só arranca agora", "the clock starts now")),
                 Item(tr("Guardar o plano", "Save the plan"), action=self._save,
                      enabled=bool(self.items))]
        if self.pid:
            rows.append(Item(tr("Apagar o plano", "Delete the plan"), action=self._delete))
        total = ls.plan_seconds(self.items)
        self.chrome.set(tr("Plano de voltas", "Lap plan") + " · Conditioning",
                        tr("{n} voltas · ≈ {t}", "{n} laps · ≈ {t}", n=len(self.items),
                           t=hms(total)), self.footer())
        self.list.set_items(rows, keep_index=True)

    def _add(self, kind: str) -> None:
        if kind == "strength":
            from velo.ui.hub_screens import ExerciseInventory

            def picked(ex):
                self.items.append({"kind": "strength", "exercise_id": ex["id"],
                                   "name": ex["name"], "measure": ex["measure"],
                                   "reps": 40 if ex["measure"] == "time" else 12})
            self.app.push(ExerciseInventory(self.app, "conditioning", pick=picked))
            return
        default = {"treadmill": 300, "rowing": 300, "rest": 60, "cardio": 300}[kind]
        self.items.append({"kind": kind, "seconds": default})
        self.enter()

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        it = self.items[int(field)]
        if it["kind"] == "strength":
            it["reps"] = max(1, (it.get("reps") or 10) + steps * (5 if big else 1))
        else:
            cur = it.get("seconds") or 0
            it["seconds"] = max(10, cur + steps * (60 if big else (15 if cur < 120 else 30)))

    def num_set(self, field: str, value) -> None:
        it = self.items[int(field)]
        if value is None:
            return
        if it["kind"] == "strength":
            it["reps"] = max(1, int(value))
        else:
            it["seconds"] = max(10, value * 60)          # escrito em minutos

    def on_key(self, symbol: int, modifiers: int) -> bool:
        f = self._field("num:")
        if f is not None:
            i = int(f)
            if symbol in (key.LEFT, key.RIGHT) and modifiers & key.MOD_SHIFT:
                j = i + (1 if symbol == key.RIGHT else -1)
                if 0 <= j < len(self.items):
                    self.items[i], self.items[j] = self.items[j], self.items[i]
                    self.list.index += j - i
                    self.enter()
                return True
            if symbol == key.DELETE:
                del self.items[i]
                self.enter()
                return True
        return super().on_key(symbol, modifiers)

    def text_input(self, field: str, text: str) -> None:
        self.name += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.name = self.name[:-1]
        self.enter()

    def _save(self) -> None:
        self.pid = ls.save_plan(self.app.db, self.pid, self.name, "conditioning", self.items)
        self.app.message(tr("Plano guardado", "Plan saved"))
        self.enter()

    def _start(self) -> None:
        start_laps(self.app, "conditioning", list(self.items), replace=True)

    def _delete(self) -> None:
        ls.delete_plan(self.app.db, self.pid)
        self.app.pop()


def _pretty(name) -> str:
    from velo.core.naming import pretty
    return pretty(name)


def _builder(app, mod: str, wid: str | None = None, draft: bool = False):
    from velo.ui.strength_builder_screens import StrengthBuilder
    return StrengthBuilder(app, mod, wid, draft=draft)


def _analysis(app, sid: str):
    from velo.ui.strength_analysis_screens import StrengthAnalysisScreen
    return StrengthAnalysisScreen(app, sid)


def _exercise_stats(app, eid: int | None = None):
    from velo.ui.exercise_stats_screens import ExerciseStatsScreen
    return ExerciseStatsScreen(app, eid)
