"""Planos de treino de X semanas, no ginásio (Lista de treinos → «Planos de X semanas»).

* `ProgramsScreen` — os planos em curso e a biblioteca por categoria; importar um plano de
  um ficheiro e guardar o ficheiro modelo.
* `ProgramDetail` — a ficha de um plano: descrição, material (o que te falta), os exercícios
  que seriam criados, as semanas e as sessões; «Começar este plano».
* `ProgramStart` — a data de início, os dias da semana e as cargas iniciais das progressões.
  Ao confirmar, as sessões vão todas para o calendário.
* `RunScreen` — um plano em curso: o que já fizeste, a próxima sessão, adiar, recalcular as
  cargas, terminar.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from perennia.core import inventory, options
from perennia.core import programs as pg
from perennia.core.i18n import tr
from perennia.ui.app import PopupMixin, Screen
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Dropdown, Item

WEEKS_LISTED = 104


def _excerpt(text: str, n: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _day(d: date) -> str:
    return f"{pg.weekday_name(d.isoweekday())} {d.strftime('%d/%m')}"


def _user_dir(app, name: str) -> Path:
    return Path(app.data_dir) / name


def plans_item(app) -> Item:
    """A linha «Planos de X semanas» no topo da Lista de treinos do ginásio."""
    active = pg.runs(app.db, active_only=True)
    n = len(pg.library(app.db))
    detail = tr("StrongLifts 5×5, Starting Strength, 5/3/1… ao começar um, as sessões vão "
                "para o calendário", "StrongLifts 5×5, Starting Strength, 5/3/1… starting one "
                "puts its sessions on the calendar")
    if active:
        detail = tr("em curso: {x}", "in progress: {x}", x=", ".join(r["name"] for r in active))
    return Item(tr("Planos de X semanas", "Multi-week plans"),
                value=tr("{n} planos", "{n} plans", n=n), detail=detail,
                action=lambda: app.push(ProgramsScreen(app)), data="programs")


def next_item(app) -> Item | None:
    """No separador Treinar: a próxima sessão do plano em curso."""
    nxt = pg.next_session(app.db)
    if nxt is None:
        return None
    run, d = nxt
    when = tr("hoje", "today") if d["date"] == date.today() else _day(d["date"])
    late = d["date"] < date.today()
    return Item(tr("Plano em curso: próxima sessão", "Plan in progress: next session"),
                value=when + (tr(" (atrasada)", " (late)") if late else ""),
                detail=d["title"], action=lambda: open_session(app, d), data="program_next")


def open_session(app, d: dict) -> None:
    """Abre a sessão de um plano (a ficha do treino, com «Configurar sessão de treino»)."""
    if not d.get("workout_id"):
        app.message(tr("O treino desta sessão já não existe.",
                       "This session's workout no longer exists."))
        return
    from perennia.core import strength as st
    if st.workout(app.db, d["workout_id"]) is None:
        app.message(tr("O treino desta sessão já não existe.",
                       "This session's workout no longer exists."))
        return
    from perennia.ui.sport_screens import StrengthPreview
    scr = StrengthPreview(app, d["workout_id"])
    if d.get("date") and d["date"] > date.today():     # agendada para depois: só se vê
        scr.planned_day = d["date"]
    app.push(scr)


# ====================================================================== biblioteca


class ProgramsScreen(Screen):
    def enter(self) -> None:
        a = self.app
        db = a.db
        for name in pg.finish_if_done(db):
            a.message(tr("Plano «{n}» concluído!", "Plan «{n}» completed!", n=name))
        rows: list[Item] = []
        active = pg.runs(db, active_only=True)
        if active:
            rows.append(Item(tr("Em curso", "In progress"), header=True))
            for r in active:
                p = pg.progress(db, r["id"])
                nxt = p["next"]
                detail = (tr("próxima: {t} · {d}", "next: {t} · {d}",
                             t=nxt["title"].split(pg.TITLE_SEP, 1)[-1], d=_day(nxt["date"]))
                          if nxt else tr("todas as sessões feitas", "all sessions done"))
                if p["missed"]:
                    detail += tr(" · {n} em atraso", " · {n} late", n=p["missed"])
                rows.append(Item(r["name"], value=f"{p['done']}/{p['total']}", detail=detail,
                                 action=lambda rid=r["id"]: a.push(RunScreen(a, rid)),
                                 data=("run", r["id"])))
        cat = None
        for p in pg.library(db):
            if p["category"] != cat:
                cat = p["category"]
                rows.append(Item(pg.category_name(cat), header=True))
            rows.append(Item(p["name"],
                             value=tr("{w} sem. · {d}×/sem.", "{w} wk · {d}×/wk", w=p["weeks"],
                                      d=p["days_per_week"]),
                             detail=pg.level_name(p["level"])
                             + (tr(" · importado", " · imported") if p["origin"] == "imported"
                                else "") + " · " + _excerpt(p["description"], 90),
                             action=lambda k=p["key"]: a.push(ProgramDetail(a, k)),
                             data=("plan", p["key"])))
        ended = [r for r in pg.runs(db) if r["status"] != "active"]
        if ended:
            rows.append(Item(tr("Terminados", "Finished"), header=True))
            for r in ended:
                p = pg.progress(db, r["id"])
                rows.append(Item(r["name"], value=f"{p['done']}/{p['total']}",
                                 detail=tr("começou em {d}", "started on {d}",
                                           d=r["start_day"]),
                                 action=lambda rid=r["id"]: a.push(RunScreen(a, rid)),
                                 data=("run", r["id"])))
        rows += [Item(tr("Ficheiro modelo", "Template file"), button=True,
                      action=self._template),
                 Item(tr("Importar plano…", "Import plan…"), button=True, primary=True,
                      action=lambda: a.push(ProgramFilePopup(a)))]
        self.list.detail_below = True
        self.chrome.set(tr("Planos de X semanas", "Multi-week plans"),
                        tr("Ao começar um plano, as sessões vão todas para o calendário · "
                           "escreve para procurar", "Starting a plan puts all its sessions on "
                           "the calendar · type to search"),
                        tr("↑↓ mover · Enter abre · Esc voltar", "↑↓ move · Enter opens · Esc "
                           "back"))
        self.list.set_items(rows, keep_index=True)

    def _template(self) -> None:
        a = self.app
        try:
            paths = pg.write_template(_user_dir(a, "planos"))
        except OSError as e:
            a.message(tr("Não consegui escrever o ficheiro modelo: {e}",
                         "Could not write the template file: {e}", e=e))
            return
        a.message(tr("Ficheiro modelo e descrição do formato em {p}",
                     "Template file and format description in {p}", p=paths[0].parent))


class ProgramFilePopup(PopupMixin, Screen):
    """Os ficheiros de plano (`*.perennia-plan.json`) encontrados no computador."""

    W, H = 820, 560

    def __init__(self, app, folders: list[str] | None = None):
        super().__init__(app)
        self.folders = folders
        self.files: list[Path] = []
        self._init_popup()

    def _folders(self) -> list[str] | None:
        if self.folders is not None:
            return self.folders
        return None

    def enter(self) -> None:
        a = self.app
        extra = [str(_user_dir(a, "planos"))]
        if self.folders is None:
            from perennia import paths
            from perennia.core.workout_files import FOLDERS
            folders = [str(p) for p in paths.user_folder("workouts")] + extra + list(FOLDERS)
        else:
            folders = self.folders
        self.files = pg.scan(folders)
        items = [Item(p.name, detail=str(p.parent), action=lambda q=p: self.pick(q))
                 for p in self.files]
        if not items:
            items = [Item(tr("Nenhum plano encontrado", "No plan found"),
                          detail=tr("Põe ficheiros «{e}» na pasta «workouts» ao lado da "
                                    "aplicação, em Transferências, em Documentos ou em {p}.",
                                    "Put '{e}' files in the 'workouts' folder next to the app, "
                                    "in Downloads, in Documents or in {p}.", e=pg.EXT,
                                    p=extra[0]), enabled=False)]
        self.chrome.set(tr("Importar um plano", "Import a plan"),
                        tr("{n} ficheiro(s) «{e}» · Enter importa · Esc volta",
                           "{n} '{e}' file(s) · Enter imports · Esc goes back",
                           n=len(self.files), e=pg.EXT), "")
        self.list.set_items(items, keep_index=True)

    def pick(self, path) -> None:
        a = self.app
        try:
            key = pg.import_file(a.db, path)
        except pg.PlanError as e:
            a.message(tr("Plano recusado: {e}", "Plan refused: {e}", e=e))
            return
        a.pop()
        a.message(tr("Plano importado", "Plan imported"))
        a.push(ProgramDetail(a, key))


# ====================================================================== ficha


class ProgramDetail(Screen):
    SEARCH = False

    def __init__(self, app, key: str):
        super().__init__(app)
        self.key = key

    def enter(self) -> None:
        from perennia.ui.advice_screens import text_rows
        a = self.app
        db = a.db
        p = pg.get(db, self.key)
        if p is None:
            a.pop()
            return
        rows: list[Item] = []
        rows += text_rows(self, p["description"])
        rows.append(Item(tr("O plano", "The plan"), header=True))
        rows.append(Item(tr("Categoria e nível", "Category and level"),
                         value=f"{pg.category_name(p['category'])} · "
                               f"{pg.level_name(p['level'])}", enabled=False))
        rows.append(Item(tr("Duração", "Length"),
                         value=tr("{w} semanas · {d} sessões por semana · {n} sessões",
                                  "{w} weeks · {d} sessions a week · {n} sessions",
                                  w=p["weeks"], d=p["days_per_week"], n=pg.total_sessions(p)),
                         enabled=False))
        rows.append(Item(tr("Dias por omissão", "Default days"),
                         value=pg.weekdays_text(p["weekdays"]), enabled=False))
        if p.get("source"):
            rows.append(Item(tr("Origem", "Source"), value=_excerpt(p["source"], 70),
                             enabled=False))
        missing = pg.missing_equipment(db, p)
        kit = ", ".join(inventory.kind_name(k) for k in p["equipment"]) or tr("nenhum", "none")
        rows.append(Item(tr("Material", "Equipment"), value=_excerpt(kit, 80),
                         detail=(tr("não tens no Inventário: {m}", "not in your Inventory: {m}",
                                    m=", ".join(inventory.kind_name(k) for k in missing))
                                 if missing else tr("tens tudo no Inventário",
                                                    "all in your Inventory")), enabled=False))
        new = pg.new_exercises(db, p)
        if new:
            rows.append(Item(tr("Exercícios novos", "New exercises"), value=str(len(new)),
                             detail=tr("são criados ao começar: {x}", "created on start: {x}",
                                       x=_excerpt(", ".join(new), 120)), enabled=False))
        tracks = pg.tracks(p)
        if tracks:
            rows.append(Item(tr("Progressão linear", "Linear progression"),
                             value=str(len(tracks)),
                             detail=tr("a carga inicial de cada uma pede-se ao começar",
                                       "each one's starting load is asked on start"),
                             enabled=False))
        rows.append(Item(tr("Semanas", "Weeks"), header=True))
        names = {k: s["name"] for k, s in p["sessions"].items()}
        ol = pg.outline(p)
        i = 0
        while i < len(ol) and i < WEEKS_LISTED:          # semanas iguais seguidas: uma linha
            j = i
            while j + 1 < len(ol) and ol[j + 1] == ol[i]:
                j += 1
            label = (tr("Semana {a}", "Week {a}", a=i + 1) if j == i else
                     tr("Semanas {a}–{b}", "Weeks {a}–{b}", a=i + 1, b=j + 1))
            rows.append(Item(label, value=_excerpt(" · ".join(names[k] for k in ol[i]), 90),
                             enabled=False))
            i = j + 1
        for key, s in p["sessions"].items():
            rows.append(Item(s["name"], header=True))
            for b in s["blocks"]:
                group = b["kind"] != "single"
                if group:
                    kind = {"superset": tr("Superset", "Superset"),
                            "circuit": tr("Circuito", "Circuit"),
                            "warmup": tr("Aquecimento", "Warm-up"),
                            "cooldown": tr("Retorno à calma", "Cool-down")}[b["kind"]]
                    extra = tr(" · {n} voltas", " · {n} rounds", n=b["rounds"]) \
                        if b["rounds"] > 1 else ""
                    rows.append(Item(kind + extra, detail=b.get("notes") or "", enabled=False,
                                     indent=1))
                for e in b["exercises"]:
                    rows.append(Item(p["exercises"][e["exercise"]]["name"],
                                     value=_excerpt(pg.entry_text(p, e, 1), 70),
                                     detail=e.get("notes") or "", enabled=False,
                                     indent=2 if group else 1))
        if p["origin"] == "imported":
            rows.append(Item(tr("Apagar", "Delete"), button=True, action=self._delete))
        rows += [Item(tr("Exportar (.json)", "Export (.json)"), button=True,
                      action=self._export),
                 Item(tr("Começar este plano", "Start this plan"), button=True, primary=True,
                      action=lambda: a.push(ProgramStart(a, self.key)))]
        self.list.detail_below = True
        self.chrome.set(p["name"],
                        tr("{w} semanas · {d}×/semana · as cargas mostradas são as da semana 1",
                           "{w} weeks · {d}×/week · loads shown are week 1's", w=p["weeks"],
                           d=p["days_per_week"]),
                        tr("↑↓ percorrer · Esc voltar", "↑↓ scroll · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def _export(self) -> None:
        a = self.app
        p = pg.get(a.db, self.key)
        try:
            path = pg.export_file(p, _user_dir(a, "planos"))
        except OSError as e:
            a.message(tr("Não consegui exportar: {e}", "Could not export: {e}", e=e))
            return
        a.message(tr("Exportado para {p}", "Exported to {p}", p=path))

    def _delete(self) -> None:
        a = self.app
        p = pg.get(a.db, self.key)

        def go() -> None:
            pg.delete_plan(a.db, self.key)
            a.pop()
        a.confirm(tr("Apagar o plano «{n}» da biblioteca?", "Delete the plan «{n}» from the "
                     "library?", n=p["name"]),
                  tr("Os planos em curso que começaste com ele continuam.",
                     "Plans in progress you started from it carry on."), go,
                  yes=tr("Apagar", "Delete"))


# ====================================================================== começar


class ProgramStart(EditPopup):
    """A data de início, os dias da semana e a carga inicial de cada progressão linear."""

    W = 820

    def __init__(self, app, key: str):
        super().__init__(app)
        self.key = key
        self.plan = pg.get(app.db, key)
        today = date.today()
        self.v = {"day": today.isoformat(), "weekdays": list(self.plan["weekdays"]),
                  "loads": pg.suggest_loads(app.db, self.plan)}
        self.run_id: int | None = None

    def title(self) -> str:
        return tr("Começar «{n}»", "Start «{n}»", n=self.plan["name"])

    def subtitle(self) -> str:
        days = pg.plan_days(self.plan, date.fromisoformat(self.v["day"]), self.v["weekdays"])
        return tr("{n} sessões no calendário, de {a} a {b}",
                  "{n} sessions on the calendar, from {a} to {b}", n=len(days),
                  a=days[0]["day"].strftime("%d/%m/%Y"), b=days[-1]["day"].strftime("%d/%m/%Y"))

    def _presets(self) -> list[list[int]]:
        dpw = self.plan["days_per_week"]
        out = [list(self.plan["weekdays"])]
        for w in pg.WEEKDAY_PRESETS[dpw]:
            if list(w) not in out:
                out.append(list(w))
        if self.v["weekdays"] not in out:
            out.append(list(self.v["weekdays"]))
        return out

    def rows(self) -> list[Item]:
        v = self.v
        presets = self._presets()
        d = date.fromisoformat(v["day"])
        rows = [Item(tr("Início", "Start"), value=f"{_day(d)}/{d.year}", data="cyc:day",
                     detail=tr("Enter abre o calendário", "Enter opens the calendar")),
                Item(tr("Dias da semana", "Weekdays"), value=pg.weekdays_text(v["weekdays"]),
                     data="cyc:weekdays",
                     dropdown=Dropdown([pg.weekdays_text(w) for w in presets],
                                       presets.index(v["weekdays"]),
                                       lambda k: v.__setitem__("weekdays", presets[k]))),
                Item(tr("Outros dias…", "Other days…"),
                     detail=tr("escolhe exatamente {n}", "pick exactly {n}",
                               n=self.plan["days_per_week"]), action=self._custom_days)]
        tracks = pg.tracks(self.plan)
        if tracks:
            rows.append(Item(tr("Cargas iniciais", "Starting loads"), header=True))
            for t in tracks:
                per = tr("por sessão", "per session") if t["per"] == "session" \
                    else tr("por semana", "per week")
                label = t["name"] + ("" if t["track"] == t["exercise"] else f" ({t['track']})")
                rows.append(Item(label, value=f"{v['loads'][t['track']]:g} kg",
                                 detail=f"+{t['add_kg']:g} kg {per}",
                                 data=f"num:{t['track']}"))
        return rows

    def buttons(self) -> list[Item]:
        return [Item(tr("Cancelar", "Cancel"), action=self.cancel, button=True),
                Item(tr("Começar e pôr no calendário", "Start and put on calendar"),
                     action=self.save_exit, button=True, primary=True)]

    def _custom_days(self) -> None:
        from perennia.ui.pickers import MultiChoicePopup
        need = self.plan["days_per_week"]

        def done(keys: list[str]) -> None:
            days = sorted(int(k) for k in keys)
            if len(days) != need:
                self.app.message(tr("Escolhe exatamente {n} dias.", "Pick exactly {n} days.",
                                    n=need))
            else:
                self.v["weekdays"] = days
            self.enter()
        self.app.push(MultiChoicePopup(
            self.app, tr("Em que dias treinas? ({n})", "Which days do you train? ({n})", n=need),
            [(str(i), pg.weekday_name(i, short=False)) for i in range(1, 8)],
            [str(d) for d in self.v["weekdays"]], done, min_one=True))

    def cycle(self, field: str, step: int) -> None:
        if field == "day":
            self.v["day"] = (date.fromisoformat(self.v["day"])
                             + timedelta(days=step)).isoformat()
        elif field == "weekdays":
            presets = self._presets()
            i = presets.index(self.v["weekdays"])
            self.v["weekdays"] = presets[(i + step) % len(presets)]

    def date_get(self, field: str) -> str | None:
        return self.v["day"]

    def date_set(self, field: str, iso: str) -> None:
        self.v["day"] = iso
        self.refresh()

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        step = float(options.get(self.app.db, "plan_round_kg"))
        cur = self.v["loads"][field]
        self.v["loads"][field] = max(0.0, cur + steps * step * (4 if big else 1))

    def num_set(self, field: str, value: float | None) -> None:
        self.v["loads"][field] = max(0.0, min(1000.0, float(value or 0)))

    def commit(self) -> bool:
        if self.run_id is not None:
            return True
        try:
            self.run_id = pg.start(self.app.db, self.key, date.fromisoformat(self.v["day"]),
                                   self.v["weekdays"], self.v["loads"])
        except pg.PlanError as e:
            self.app.message(str(e))
            return False
        return True

    def saved_message(self) -> str:
        n = len(pg.days(self.app.db, self.run_id)) if self.run_id else 0
        return tr("Plano começado: {n} sessões no calendário",
                  "Plan started: {n} sessions on the calendar", n=n)

    def close(self) -> None:
        super().close()
        if self.run_id is not None:
            self.app.push(RunScreen(self.app, self.run_id))


# ====================================================================== em curso


class RunScreen(Screen):
    SEARCH = False

    def __init__(self, app, run_id: int):
        super().__init__(app)
        self.run_id = run_id

    def enter(self) -> None:
        a = self.app
        db = a.db
        pg.finish_if_done(db)
        r = pg.run(db, self.run_id)
        if r is None:
            a.pop()
            return
        ds = pg.days(db, self.run_id)
        p = pg.progress(db, self.run_id)
        today = date.today()
        active = r["status"] == "active"
        rows: list[Item] = [Item(tr("Progresso", "Progress"),
                                 value=tr("{d} de {t} sessões", "{d} of {t} sessions",
                                          d=p["done"], t=p["total"]),
                                 detail=(tr("acaba em {d}", "ends on {d}",
                                            d=p["last_day"].strftime("%d/%m/%Y"))
                                         if p["last_day"] else "")
                                 + (tr(" · {n} em atraso", " · {n} late", n=p["missed"])
                                    if p["missed"] and active else "")
                                 + ("" if active else tr(" · terminado", " · finished")),
                                 enabled=False)]
        week = None
        for d in ds:
            if d["week"] != week:
                week = d["week"]
                rows.append(Item(tr("Semana {n}", "Week {n}", n=week), header=True))
            name = d["title"].split(pg.TITLE_SEP, 2)[-1]
            if d["done"]:
                state = tr("feita em {d}", "done on {d}", d=d["done_on"][8:] + "/"
                           + d["done_on"][5:7])
                mark = "✓"
            elif d["date"] == today:
                state, mark = tr("hoje", "today"), "▶"
            elif d["date"] < today:
                state, mark = tr("em atraso", "late"), "!"
            else:
                state, mark = "", " "
            rows.append(Item(f"{mark}  {_day(d['date'])}  {name}", value=state,
                             action=lambda dd=d: self._open(dd), data=("day", d["idx"]),
                             enabled=bool(d.get("workout_id"))))
        if active:
            n_shift = int(options.get(db, "plan_shift_days"))
            rows.append(Item(tr("Terminar plano", "End plan"), button=True, action=self._end))
            rows.append(Item(tr("Adiar o que falta ({n} dias)", "Postpone the rest ({n} days)",
                                n=n_shift), button=True, action=self._shift))
            if pg.tracks(pg.validate(r["data"])):
                rows.append(Item(tr("Recalcular cargas", "Recalculate loads"), button=True,
                                 action=lambda: a.push(RebasePopup(a, self.run_id))))
            if p["next"]:
                rows.append(Item(tr("Fazer a próxima sessão", "Do the next session"),
                                 button=True, primary=True,
                                 action=lambda: open_session(a, p["next"])))
        else:
            rows.append(Item(tr("Apagar do registo", "Delete from the record"), button=True,
                             action=self._delete))
        self.chrome.set(r["name"],
                        tr("Começou em {d} · {w} · Enter abre a sessão",
                           "Started on {d} · {w} · Enter opens the session",
                           d=date.fromisoformat(r["start_day"]).strftime("%d/%m/%Y"),
                           w=pg.weekdays_text(r["weekdays"])),
                        tr("↑↓ mover · Enter abre a sessão · Esc voltar",
                           "↑↓ move · Enter opens the session · Esc back"))
        if self.list.index == 0 and p["next"]:
            self.list.set_items(rows)
            self.list.select_data(("day", p["next"]["idx"]))
        else:
            self.list.set_items(rows, keep_index=True)

    def _open(self, d: dict) -> None:
        if d["done"] and d.get("session_id"):
            from perennia.ui.gym_screens import _analysis
            self.app.push(_analysis(self.app, d["session_id"]))
        else:
            open_session(self.app, d)

    def _shift(self) -> None:
        a = self.app
        n = int(options.get(a.db, "plan_shift_days"))

        def go() -> None:
            moved = pg.shift(a.db, self.run_id, n)
            a.message(tr("{m} sessões adiadas {n} dias", "{m} sessions postponed {n} days",
                         m=moved, n=n))
            self.enter()
        a.confirm(tr("Adiar as sessões por fazer {n} dias?", "Postpone the remaining sessions "
                     "{n} days?", n=n),
                  tr("As que já fizeste ficam onde estão; as outras mudam no calendário.",
                     "The ones you did stay; the others move on the calendar."), go,
                  yes=tr("Adiar", "Postpone"))

    def _end(self) -> None:
        a = self.app

        def go() -> None:
            pg.end(a.db, self.run_id)
            a.message(tr("Plano terminado: as sessões por fazer saíram do calendário",
                         "Plan ended: the remaining sessions left the calendar"))
            self.enter()
        a.confirm(tr("Terminar este plano?", "End this plan?"),
                  tr("As sessões por fazer saem do calendário. O que já fizeste fica no "
                     "histórico.", "The remaining sessions leave the calendar. What you did "
                     "stays in the history."), go, yes=tr("Terminar", "End"))

    def _delete(self) -> None:
        a = self.app

        def go() -> None:
            pg.end(a.db, self.run_id, delete=True)
            a.pop()
        a.confirm(tr("Apagar este plano do registo?", "Delete this plan from the record?"),
                  tr("As sessões que fizeste continuam no histórico.",
                     "The sessions you did stay in the history."), go,
                  yes=tr("Apagar", "Delete"))


class RebasePopup(EditPopup):
    """Novas cargas principais para as sessões que faltam (falhaste, estiveste parado, ou a
    progressão ficou curta): as sessões por fazer são refeitas a partir destas cargas."""

    W = 760

    def __init__(self, app, run_id: int):
        super().__init__(app)
        self.run_id = run_id
        r = pg.run(app.db, run_id)
        self.plan = pg.validate(r["data"])
        self.v = dict(pg.current_loads(app.db, run_id))
        self.done_n = 0

    def title(self) -> str:
        return tr("Recalcular cargas", "Recalculate loads")

    def subtitle(self) -> str:
        return tr("A carga de cada progressão na próxima sessão; as seguintes somam a partir "
                  "daqui", "Each progression's load in the next session; later ones add from "
                  "here")

    def rows(self) -> list[Item]:
        rows = []
        for t in pg.tracks(self.plan):
            label = t["name"] + ("" if t["track"] == t["exercise"] else f" ({t['track']})")
            rows.append(Item(label, value=f"{self.v.get(t['track'], 0.0):g} kg",
                             detail=f"+{t['add_kg']:g} kg", data=f"num:{t['track']}"))
        pct = float(options.get(self.app.db, "plan_deload_pct"))
        rows.append(Item(tr("Baixar tudo {p:g} %", "Lower everything {p:g} %", p=pct),
                         action=self._deload))
        return rows

    def _deload(self) -> None:
        pct = float(options.get(self.app.db, "plan_deload_pct"))
        for k in self.v:
            self.v[k] = pg.round_load(self.app.db, self.v[k] * (1.0 - pct / 100.0))
        self.enter()

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        step = float(options.get(self.app.db, "plan_round_kg"))
        self.v[field] = max(0.0, self.v.get(field, 0.0) + steps * step * (4 if big else 1))

    def num_set(self, field: str, value: float | None) -> None:
        self.v[field] = max(0.0, min(1000.0, float(value or 0)))

    def commit(self) -> bool:
        self.done_n = pg.rebase(self.app.db, self.run_id, self.v)
        return True

    def saved_message(self) -> str:
        return tr("{n} sessões refeitas com as novas cargas", "{n} sessions rebuilt with the "
                  "new loads", n=self.done_n)
