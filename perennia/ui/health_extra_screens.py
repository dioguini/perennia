"""Saúde: a pressão arterial (várias medições por dia, por período), os separadores criados
por ti (sempre com Notas) e o separador do Assistente de saúde.

As três funções `bp_tab`, `assistant_tab` e `custom_tab` enchem a lista do menu Saúde quando o
separador é o delas; o resto são as janelas que elas abrem.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from perennia.core import bp, health_tabs, options
from perennia.core import health_assistant as ha
from perennia.core.i18n import tr
from perennia.ui.app import Screen
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Dropdown, Item

DAYS_LISTED = 60
NOTE_MAX = 4000
TITLE_MAX = 80


def _day_label(d: date | str) -> str:
    from perennia.ui.health_screens import day_label
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return day_label(d)


def _excerpt(text, n=70):
    from perennia.ui.health_screens import _excerpt as ex
    return ex(text, n)


def new_tab_button(menu) -> Item:
    return Item(tr("+ Separador", "+ Tab"), top=True, action=lambda: new_tab(menu))


def new_tab(menu) -> None:
    from perennia.ui.goal_popup import GoalPopup

    def save(name: str) -> None:
        try:
            key = health_tabs.add_tab(menu.app.db, name)
        except ValueError as e:
            menu.app.message(str(e))
            return
        menu.refresh_tabs(select=menu.CUSTOM + key)
    menu.app.push(GoalPopup(menu.app, tr("Novo separador da Saúde", "New Health tab"),
                            tr("Ganha um separador próprio, sempre com Notas",
                               "Gets its own tab, always with Notes"), "",
                            health_tabs.NAME_MAX, save))


# ====================================================================== pressão arterial


def summary_text(db, s: dict, with_n: bool = True) -> str:
    """«Manhã 126/82 (3) · Noite 117/75 (2)»."""
    bits = []
    for k, m in s["periods"]:
        t = f"{bp.period_name(db, k)} {bp.fmt(m)}"
        if with_n:
            t += f" ({m['n']})"
        bits.append(t)
    return " · ".join(bits)


def diary_bp_row(app, day: date) -> Item:
    s = bp.day_summary(app.db, day)
    if s["daily"]:
        value = bp.fmt(s["daily"]) + " mmHg"
        detail = tr("média do dia · ", "day mean · ") + summary_text(app.db, s) + \
            tr(" · Enter abre as medições", " · Enter opens the readings")
    else:
        value = "—"
        detail = tr("Enter abre as medições (várias por dia, por período)",
                    "Enter opens the readings (several a day, by period)")
    return Item(tr("Pressão arterial", "Blood pressure"), value=value, detail=detail,
                action=lambda: app.push(BPDayScreen(app, day)), data="bp")


def bp_tab(menu) -> None:
    a = menu.app
    db = a.db
    bp.ensure(db)
    rd = int(options.get(db, "health_window_days"))
    rows: list[Item] = []
    recent = bp.window_mean(db, rd)
    if recent:
        cat = bp.classify(db, recent["sys"], recent["dia"])
        rows.append(Item(tr("Média dos últimos {n} dias", "Mean of the last {n} days", n=rd),
                         value=bp.fmt_full(recent),
                         detail=tr("{c} · {d} dia(s) com medições", "{c} · {d} day(s) with readings",
                                   c=bp.category_name(cat), d=recent["days"]), enabled=False))
        per = []
        for k, name in bp.periods(db):
            m = bp.window_mean(db, rd, period=k)
            if m:
                per.append(f"{name} {bp.fmt(m)}")
        if per:
            rows.append(Item(tr("Por período", "By period"), value=" · ".join(per),
                             enabled=False))
    today = date.today()
    listed = bp.days(db, limit=DAYS_LISTED)
    have = {s["day"] for s in listed}
    if today.isoformat() not in have:
        rows.append(Item(_day_label(today), value="—",
                         detail=tr("ainda sem medições hoje · Enter abre o dia",
                                   "no readings today yet · Enter opens the day"),
                         action=lambda: a.push(BPDayScreen(a, today)), data=("day", "today")))
    for s in listed:
        d = date.fromisoformat(s["day"])
        cat = bp.classify(db, s["daily"]["sys"], s["daily"]["dia"]) if s["daily"] else None
        mark = {"high": " ▲", "crisis": " ▲▲", "low": " ▼"}.get(cat or "", "")
        rows.append(Item(_day_label(d), value=bp.fmt(s["daily"]) + mark,
                         detail=summary_text(db, s),
                         action=lambda dd=d: a.push(BPDayScreen(a, dd)), data=("day", s["day"])))
    rows += [new_tab_button(menu),
             Item(tr("Períodos", "Periods"), button=True,
                  action=lambda: a.push(BPPeriodsPopup(a))),
             Item(tr("Outro dia…", "Another day…"), button=True,
                  action=lambda: _pick_day(a)),
             Item(tr("Assistente de saúde", "Health assistant"), button=True,
                  action=lambda: open_component(a, "bp")),
             Item(tr("+ Medição", "+ Reading"), button=True, primary=True,
                  action=lambda: a.push(BPReadingEditor(a, None, today)))]
    menu.chrome.set(menu.TITLE(),
                    tr("Várias medições por dia · a média de cada período e a média diária · "
                       "Enter abre o dia", "Several readings a day · each period's mean and the "
                       "daily mean · Enter opens the day"), menu.footer())
    menu.list.set_items(rows, keep_index=True)


def _pick_day(app) -> None:
    from perennia.ui.pickers import pick_date
    pick_date(app, tr("Medições de que dia?", "Readings for which day?"), date.today(),
              lambda iso: app.push(BPDayScreen(app, date.fromisoformat(iso))),
              max_day=date.today())


class BPDayScreen(Screen):
    """As medições de um dia, por período, com a média de cada período e a média do dia."""

    SEARCH = False

    def __init__(self, app, day: date):
        super().__init__(app)
        self.day = day

    def enter(self) -> None:
        a = self.app
        db = a.db
        rs = bp.readings(db, self.day)
        s = bp.summarise(db, rs)
        rows: list[Item] = []
        if s["daily"]:
            cat = bp.classify(db, s["daily"]["sys"], s["daily"]["dia"])
            mode = options.choice_label(options.BY_KEY["bp_daily_mode"],
                                        options.get(db, "bp_daily_mode"))
            rows.append(Item(tr("Média do dia", "Day mean"), value=bp.fmt_full(s["daily"]),
                             detail=f"{bp.category_name(cat)} · {mode}", enabled=False,
                             data="daily"))
        means = dict(s["periods"])
        for k, m in s["periods"]:
            used = "" if m["used"] == m["n"] else tr(" · a 1.ª não conta", " · 1st not counted")
            rows.append(Item(bp.period_name(db, k), header=True,
                             detail=tr("média {v} · {n} medições", "mean {v} · {n} readings",
                                       v=bp.fmt_full(means[k]), n=m["n"]) + used))
            for r in (x for x in rs if x["period"] == k):
                rows.append(Item(r["at"] or "—", value=f"{r['sys']:.0f}/{r['dia']:.0f}"
                                 + (f" · {r['pulse']:.0f} bpm" if r["pulse"] is not None else ""),
                                 detail=_excerpt(r["notes"], 60) if r["notes"] else "",
                                 action=lambda rid=r["id"]: a.push(BPReadingEditor(
                                     a, rid, self.day)), data=("reading", r["id"]), indent=1))
        if not rs:
            rows.append(Item(tr("Ainda sem medições neste dia", "No readings on this day yet"),
                             detail=tr("faz 2–3 seguidas em cada período: fica a média",
                                       "take 2–3 in a row in each period: the mean is kept"),
                             enabled=False))
        rows += [Item(tr("Dia anterior", "Previous day"), button=True,
                      action=lambda: self._shift(-1)),
                 Item(tr("Dia seguinte", "Next day"), button=True,
                      action=lambda: self._shift(1), enabled=self.day < date.today()),
                 Item(tr("+ Medição", "+ Reading"), button=True, primary=True,
                      action=lambda: a.push(BPReadingEditor(a, None, self.day)))]
        self.chrome.set(tr("Pressão arterial", "Blood pressure"), _day_label(self.day),
                        tr("Enter numa medição edita-a · Esc voltar",
                           "Enter on a reading edits it · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def _shift(self, n: int) -> None:
        d = self.day + timedelta(days=n)
        if d <= date.today():
            self.day = d
            self.list.index = 0
            self.enter()


class BPReadingEditor(EditPopup):
    """Uma medição: dia, período, hora, máxima, mínima, pulsação e nota. «Guardar e mais uma»
    deixa a janela aberta para a medição seguinte do mesmo período."""

    W = 760

    def __init__(self, app, reading_id: int | None, day: date):
        super().__init__(app)
        self.reading_id = reading_id
        db = app.db
        r = bp.reading(db, reading_id) if reading_id else None
        if r:
            self.v = {"day": r["day"], "period": r["period"], "at": r["at"] or "",
                      "sys": r["sys"], "dia": r["dia"], "pulse": r["pulse"],
                      "notes": r["notes"] or ""}
        else:
            now = datetime.now().strftime("%H:%M") if day == date.today() else ""
            self.v = {"day": day.isoformat(), "period": bp.guess_period(db, now or None),
                      "at": now, "sys": None, "dia": None, "pulse": None, "notes": ""}
        self.saved_n = 0

    def title(self) -> str:
        return tr("Editar medição", "Edit reading") if self.reading_id \
            else tr("Nova medição", "New reading")

    def subtitle(self) -> str:
        s = bp.day_summary(self.app.db, self.v["day"])
        base = _day_label(self.v["day"])
        return base + (" · " + summary_text(self.app.db, s) if s["n"] else "")

    def _periods(self) -> list[tuple[str, str]]:
        ps = bp.periods(self.app.db)
        if self.v["period"] == bp.NO_PERIOD:
            ps = ps + [(bp.NO_PERIOD, bp.period_name(self.app.db, bp.NO_PERIOD))]
        return ps

    def rows(self) -> list[Item]:
        v = self.v
        ps = self._periods()
        keys = [k for k, _ in ps]

        def n(x, unit):
            return "—" if x is None else f"{x:.0f} {unit}"
        cur = keys.index(v["period"]) if v["period"] in keys else 0
        rows = [Item(tr("Dia", "Day"), value=_day_label(v["day"]), data="cyc:day"),
                Item(tr("Período", "Period"), value=ps[cur][1], data="cyc:period",
                     dropdown=Dropdown([name for _k, name in ps], cur, self._pick_period)),
                Item(tr("Hora", "Time"), value=(v["at"] or "") + "▏", data="text:at",
                     detail=tr("opcional · 8, 0830 ou 8:30", "optional · 8, 0830 or 8:30")),
                Item(tr("Máxima (sistólica)", "Systolic"), value=n(v["sys"], "mmHg"),
                     data="num:sys"),
                Item(tr("Mínima (diastólica)", "Diastolic"), value=n(v["dia"], "mmHg"),
                     data="num:dia"),
                Item(tr("Pulsação", "Pulse"), value=n(v["pulse"], "bpm"), data="num:pulse",
                     detail=tr("opcional", "optional")),
                Item(tr("Nota", "Note"), value=(v["notes"] or "") + "▏", data="text:notes")]
        if self.reading_id:
            rows.append(Item(tr("Apagar esta medição", "Delete this reading"),
                             action=self._delete))
        return rows

    def buttons(self) -> list[Item]:
        out = [Item(tr("Cancelar", "Cancel"), action=self.cancel, button=True)]
        if not self.reading_id:
            out.append(Item(tr("Guardar e mais uma", "Save and one more"), button=True,
                            action=self.save_more))
        out.append(Item(tr("Guardar e sair", "Save and close"), action=self.save_exit,
                        button=True, primary=True))
        return out

    def _pick_period(self, k: int) -> None:
        self.v["period"] = self._periods()[k][0]

    def cycle(self, field: str, step: int) -> None:
        if field == "day":
            d = date.fromisoformat(self.v["day"]) + timedelta(days=step)
            if d <= date.today():
                self.v["day"] = d.isoformat()
        elif field == "period":
            keys = [k for k, _ in self._periods()]
            i = keys.index(self.v["period"]) if self.v["period"] in keys else 0
            self.v["period"] = keys[(i + step) % len(keys)]

    def date_get(self, field: str) -> str | None:
        return self.v["day"]

    def date_set(self, field: str, iso: str) -> None:
        if date.fromisoformat(iso) <= date.today():
            self.v["day"] = iso
        self.refresh()

    GUESS = {"sys": 120.0, "dia": 80.0, "pulse": 60.0}

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        cur = self.v[field]
        if cur is None:
            cur = self.GUESS[field] - steps * (10 if big else 1)
        self.v[field] = max(0.0, cur + steps * (10 if big else 1))

    def num_set(self, field: str, value: float | None) -> None:
        self.v[field] = value

    def text_input(self, field: str, text: str) -> None:
        limit = 5 if field == "at" else 200
        self.v[field] = (self.v[field] + text)[:limit]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def commit(self) -> bool:
        v = self.v
        if v["at"].strip() and bp.parse_time(v["at"]) is None:
            self.app.message(tr("A hora não se percebe: escreve 8, 0830 ou 8:30.",
                                "The time is unclear: type 8, 0830 or 8:30."))
            return False
        try:
            self.reading_id = bp.save_reading(
                self.app.db, self.reading_id, day=v["day"], period=v["period"], sys=v["sys"],
                dia=v["dia"], pulse=v["pulse"], at=v["at"] or None, notes=v["notes"])
        except (ValueError, TypeError) as e:
            self.app.message(str(e) or tr("Escreve a máxima e a mínima.",
                                          "Type the systolic and the diastolic."))
            return False
        self.saved_n += 1
        return True

    def saved_message(self) -> str:
        s = bp.day_summary(self.app.db, self.v["day"])
        m = dict(s["periods"]).get(self.v["period"])
        if not m:
            return tr("Guardado", "Saved")
        return tr("Guardado · {p}: média {v} ({n})", "Saved · {p}: mean {v} ({n})",
                  p=bp.period_name(self.app.db, self.v["period"]), v=bp.fmt(m), n=m["n"])

    def save_more(self) -> None:
        """Guarda e deixa a janela pronta para a medição seguinte (mesmo dia e período)."""
        if not self.commit():
            return
        self.app.message(self.saved_message())
        self.reading_id = None
        self.v.update(sys=None, dia=None, pulse=None, notes="",
                      at=datetime.now().strftime("%H:%M")
                      if self.v["day"] == date.today().isoformat() else self.v["at"])
        self._saved_state = self.state()
        self.list.select_data("num:sys")
        self.enter()

    def _delete(self) -> None:
        def go() -> None:
            bp.delete_reading(self.app.db, self.reading_id)
            self._saved_state = self.state()
            self.close()
        self.app.confirm(tr("Apagar esta medição?", "Delete this reading?"),
                         tr("A média do período e a do dia são refeitas.",
                            "The period and day means are recomputed."), go,
                         yes=tr("Apagar", "Delete"))


class BPPeriodsPopup(EditPopup):
    """Os períodos do dia em que medes (manhã, tarde, noite… ou os teus): um por linha."""

    W = 720
    MAX = 6

    def __init__(self, app):
        super().__init__(app)
        self.v = [name for _k, name in bp.periods(app.db)]

    def title(self) -> str:
        return tr("Períodos das medições", "Reading periods")

    def subtitle(self) -> str:
        return tr("Cada período tem a sua média · uma linha vazia tira o período",
                  "Each period has its own mean · an empty row removes the period")

    def rows(self) -> list[Item]:
        rows = [Item(tr("Período {i}", "Period {i}", i=i + 1), value=name + "▏",
                     data=f"text:{i}") for i, name in enumerate(self.v)]
        if len(self.v) < self.MAX:
            rows.append(Item(tr("+ Juntar um período", "+ Add a period"), action=self._add))
        rows.append(Item(tr("Repor manhã, tarde e noite", "Reset to morning, afternoon, night"),
                         action=self._reset))
        return rows

    def _add(self) -> None:
        self.v.append("")
        self.enter()
        self.list.select_data(f"text:{len(self.v) - 1}")
        self.enter()

    def _reset(self) -> None:
        self.v = [tr(pt, en) for _k, pt, en in bp.DEFAULT_PERIODS]
        self.enter()

    def text_input(self, field: str, text: str) -> None:
        i = int(field)
        self.v[i] = (self.v[i] + text)[:24]
        self.enter()

    def text_backspace(self, field: str) -> None:
        i = int(field)
        self.v[i] = self.v[i][:-1]
        self.enter()

    def commit(self) -> bool:
        try:
            bp.set_periods(self.app.db, self.v)
        except ValueError as e:
            self.app.message(str(e))
            return False
        self.v = [name for _k, name in bp.periods(self.app.db)]
        return True


# ====================================================================== assistente de saúde


def open_component(app, name: str, **kw) -> None:
    from perennia.ui.advice_screens import AdviceScreen
    app.push(AdviceScreen(app, "health", lambda: ha.component(app.db, name, **kw)))


def assistant_tab(menu) -> None:
    from perennia.ui.advice_screens import mode_row
    a = menu.app
    db = a.db
    rows: list[Item] = [mode_row(menu, "health")]
    marks = {"good": "✓", "warn": "!", "bad": "✗", "info": "·"}
    for name in ha.COMPONENTS:
        adv = ha.component(db, name)
        rows.append(Item(f"{marks.get(adv.tone, '·')}  {ha.component_name(name)}",
                         detail=adv.verdict, action=lambda n=name: open_component(a, n),
                         data=("component", name)))
    rows.append(Item(ha.disclaimer(), enabled=False))
    rows.append(new_tab_button(menu))
    menu.chrome.set(menu.TITLE(),
                    tr("O Assistente de saúde lê as análises, a pressão arterial, o diário, as "
                       "tuas notas e sinais do treino · Enter abre", "The Health assistant "
                       "reads lab results, blood pressure, the daily log, your notes and "
                       "training signals · Enter opens"), menu.footer())
    menu.list.detail_below = True
    menu.list.set_items(rows, keep_index=True)


# ====================================================================== separadores teus


def custom_tab(menu, key: str) -> None:
    a = menu.app
    db = a.db
    t = health_tabs.tab(db, key)
    if t is None:
        menu.refresh_tabs()
        return
    rows: list[Item] = [Item(tr("Notas", "Notes"), header=True)]
    ns = health_tabs.notes(db, key)
    for n in ns:
        rows.append(Item(_day_label(n["day"]), value=_excerpt(n["title"], 40) or "",
                         detail=_excerpt(n["text"], 110),
                         action=lambda nid=n["id"]: a.push(NoteEditor(a, key, nid)),
                         data=("note", n["id"])))
    if not ns:
        rows.append(Item(tr("Ainda sem notas", "No notes yet"),
                         detail=tr("«+ Nota» em baixo · o módulo próprio deste separador vem "
                                   "depois", "'+ Note' below · this tab's own module comes "
                                   "later"), enabled=False))
    rows += [new_tab_button(menu),
             Item(tr("Apagar separador", "Delete tab"), button=True,
                  action=lambda: _delete_tab(menu, t)),
             Item(tr("Mudar o nome", "Rename"), button=True,
                  action=lambda: _rename_tab(menu, t)),
             Item(tr("+ Nota", "+ Note"), button=True, primary=True,
                  action=lambda: a.push(NoteEditor(a, key, None)))]
    menu.chrome.set(menu.TITLE(), t["name"] + " · " + tr("{n} notas · Enter abre uma nota",
                                                         "{n} notes · Enter opens a note",
                                                         n=len(ns)), menu.footer())
    menu.list.detail_below = True
    menu.list.set_items(rows, keep_index=True)


def _rename_tab(menu, t: dict) -> None:
    from perennia.ui.goal_popup import GoalPopup

    def save(name: str) -> None:
        try:
            health_tabs.rename_tab(menu.app.db, t["key"], name)
        except ValueError as e:
            menu.app.message(str(e))
            return
        menu.refresh_tabs(select=menu.CUSTOM + t["key"])
    menu.app.push(GoalPopup(menu.app, tr("Nome do separador", "Tab name"), "", t["name"],
                            health_tabs.NAME_MAX, save))


def _delete_tab(menu, t: dict) -> None:
    def go() -> None:
        health_tabs.delete_tab(menu.app.db, t["key"])
        menu.refresh_tabs()
    menu.app.confirm(tr("Apagar o separador «{n}»?", "Delete the tab «{n}»?", n=t["name"]),
                     tr("As {k} notas dele também se apagam. Não dá para desfazer.",
                        "Its {k} notes are deleted too. This cannot be undone.", k=t["n"]), go,
                     yes=tr("Apagar", "Delete"))


class NoteEditor(EditPopup):
    """Uma nota de um separador: data, título e texto."""

    W = 820

    def __init__(self, app, tab_key: str, note_id: int | None):
        super().__init__(app)
        self.tab_key = tab_key
        self.note_id = note_id
        n = health_tabs.note(app.db, note_id) if note_id else None
        self.v = {"day": (n or {}).get("day") or date.today().isoformat(),
                  "title": (n or {}).get("title") or "", "text": (n or {}).get("text") or ""}

    def title(self) -> str:
        return tr("Editar nota", "Edit note") if self.note_id else tr("Nova nota", "New note")

    def subtitle(self) -> str:
        t = health_tabs.tab(self.app.db, self.tab_key)
        return t["name"] if t else ""

    def rows(self) -> list[Item]:
        v = self.v
        rows = [Item(tr("Dia", "Day"), value=_day_label(v["day"]), data="cyc:day"),
                Item(tr("Título", "Title"), value=v["title"] + "▏", data="text:title"),
                Item(tr("Texto", "Text"), value=_excerpt(v["text"], 60) or "—",
                     detail=tr("Enter escreve numa janela maior", "Enter writes in a larger "
                               "window"), action=self._edit_text, data="note_text")]
        if self.note_id:
            rows.append(Item(tr("Apagar esta nota", "Delete this note"), action=self._delete))
        return rows

    def _edit_text(self) -> None:
        from perennia.ui.goal_popup import GoalPopup

        def save(text: str) -> None:
            self.v["text"] = text or ""
        self.app.push(GoalPopup(self.app, tr("Texto da nota", "Note text"), self.v["title"],
                                self.v["text"], NOTE_MAX, save, multiline=True))

    def cycle(self, field: str, step: int) -> None:
        if field == "day":
            self.v["day"] = (date.fromisoformat(self.v["day"])
                             + timedelta(days=step)).isoformat()

    def date_get(self, field: str) -> str | None:
        return self.v["day"]

    def date_set(self, field: str, iso: str) -> None:
        self.v["day"] = iso
        self.refresh()

    def text_input(self, field: str, text: str) -> None:
        self.v[field] = (self.v[field] + text)[:TITLE_MAX]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def commit(self) -> bool:
        try:
            self.note_id = health_tabs.save_note(self.app.db, self.note_id, self.tab_key,
                                                 day=self.v["day"], title=self.v["title"],
                                                 text=self.v["text"])
        except ValueError as e:
            self.app.message(str(e))
            return False
        return True

    def _delete(self) -> None:
        def go() -> None:
            health_tabs.delete_note(self.app.db, self.note_id)
            self._saved_state = self.state()
            self.close()
        self.app.confirm(tr("Apagar esta nota?", "Delete this note?"),
                         tr("Não dá para desfazer.", "This cannot be undone."), go,
                         yes=tr("Apagar", "Delete"))
