"""O Treinador na aplicação.

`CoachMenu` (cartão «Treinador» no ecrã inicial) tem cinco separadores:

* **Hoje** — o que fazer hoje e os comportamentos a cuidar, com o botão que abre o treino
  sugerido no construtor;
* **Eventos** — os eventos numa data (resistência ou força): criar (o Treinador faz as
  perguntas), ver o plano e pô-lo no calendário;
* **Desafios** — os desafios da Perennia, cada um com o que o Treinador acha; Enter abre o
  feedback (onde se diz a importância e se ajustam os treinos);
* **Longevidade** — o caminho proposto a partir das fraquezas do índice;
* **Programar treino** — desporto, foco e duração; abre no construtor de treinos.

O Treinador aparece também no fim de cada sessão (a avaliação do treino), no detalhe de um
desafio, no menu Longevidade e no construtor de treinos (botão «Treinador»).
"""
from __future__ import annotations

from datetime import date, timedelta

from perennia.core import coach, options
from perennia.core import sport_challenges as sc
from perennia.core import strength as st
from perennia.core.i18n import tr
from perennia.ui.advice_screens import AdviceScreen, advice_rows, llm_rows, mode_row
from perennia.ui.app import Screen
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Dropdown, Item

DURATIONS = (30, 45, 60, 75, 90, 105, 120, 150, 180, 240)
MARK = {"good": "✓", "warn": "!", "bad": "✗", "info": "·"}


def _day_text(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return "—"


def open_in_builder(app, sport: str, focus: str, minutes: int) -> None:
    """Abre o construtor de treinos com um treino programado pelo Treinador (por guardar)."""
    from perennia.ui.builder_screens import BlockBuilder
    try:
        w = coach.build_workout(app.db, sport, focus, minutes)
    except ValueError as e:
        app.message(str(e))
        return
    scr = BlockBuilder(app, sport, None, control="erg" if sport != "swimming" else "manual")
    scr.blocks = list(w["blocks"])
    scr.name = w["name"]
    scr.wgoal = w["goal"]
    for b in scr.blocks:
        b.goal = b.goal or b.cue
    scr.sel = 0
    scr._clamp_blocks()
    scr.dirty = True
    scr.coach_asked = True                 # veio do Treinador: o feedback ao vivo fica ligado
    app.push(scr)
    scr.redraw()
    scr.enter()
    app.message(w["note"] or tr("Treino do Treinador: ajusta e guarda.",
                                "Coach's workout: adjust and save."))


def open_challenge(app, challenge: dict) -> None:
    app.push(ChallengeCoach(app, challenge))


def open_longevity(app) -> None:
    def actions(screen, adv):
        return _calendar_buttons(screen, "longevity", adv)
    app.push(AdviceScreen(app, "coach", lambda: coach.longevity_path(app.db), actions=actions))


def _calendar_buttons(screen, key: str, adv) -> list[Item]:
    """«Pôr no calendário» / «Tirar do calendário» para sessões que não são de um evento."""
    a = screen.app
    have = len((a.db.get("coach_plans", {}) or {}).get(key, []))
    out = []
    if have:
        def clear() -> None:
            n = coach.remove_from_calendar(a.db, key)
            a.message(tr("{n} sessões tiradas do calendário", "{n} sessions removed from the "
                         "calendar", n=n))
            screen.enter()
        out.append(Item(tr("Tirar do calendário ({n})", "Remove from calendar ({n})", n=have),
                        button=True, action=clear))
    if adv.schedule:
        def put() -> None:
            n = coach.add_to_calendar(a.db, key, adv.schedule)
            a.message(tr("{n} sessões no calendário", "{n} sessions on the calendar", n=n))
            screen.enter()
        out.append(Item(tr("Pôr no calendário ({n})", "Put on calendar ({n})",
                           n=len(adv.schedule)), button=True, primary=True, action=put))
    return out


# ====================================================================== menu


class CoachMenu(Screen):
    TABBED = True
    SEARCH = False
    TAB_KEYS = ("today", "events", "challenges", "longevity", "build")

    @staticmethod
    def TITLE() -> str:
        return tr("Treinador", "Coach")

    def __init__(self, app, tab: int = 0):
        super().__init__(app)
        self.tab = tab
        if self.tabs is not None:
            self.tabs.select(tab)
        self.build = {"sport": "cycling", "focus": "endurance", "minutes": 60}
        self.advice = None

    def tab_labels(self) -> list[str]:
        return [tr("Hoje", "Today"), tr("Eventos", "Events"), tr("Desafios", "Challenges"),
                tr("Longevidade", "Longevity"), tr("Programar treino", "Program a workout")]

    def tab_key(self) -> str:
        return self.TAB_KEYS[self.tab % len(self.TAB_KEYS)]

    def enter(self) -> None:
        self.advice = None
        self.list.detail_below = False        # os separadores de listas compridas ligam-no
        getattr(self, "_" + self.tab_key())()

    def agent_data(self) -> dict:
        return {} if self.advice is None else {"conselho": self.advice.as_text()}

    def _set(self, rows: list[Item], sub: str) -> None:
        self.chrome.set(self.TITLE(), sub,
                        tr("Tab separador · ↑↓ percorrer · Enter abrir · Esc voltar",
                           "Tab next tab · ↑↓ scroll · Enter open · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def _advice_tab(self, adv, sub: str, buttons: list[Item]) -> None:
        self.advice = adv
        rows = [mode_row(self, "coach")] + llm_rows(self, "coach", adv) + advice_rows(self, adv)
        self._set(rows + buttons, sub)

    # ------------------------------------------------------------ hoje

    def _today(self) -> None:
        a = self.app
        adv = coach.suggest_today(a.db)
        focus = adv.data.get("focus")
        buttons = []
        if focus:
            buttons.append(Item(tr("Abrir este treino no construtor",
                                   "Open this workout in the builder"), button=True,
                                primary=True,
                                action=lambda: open_in_builder(a, self.build["sport"], focus,
                                                               self.build["minutes"])))
        self._advice_tab(adv, tr("O que o Treinador sugere para hoje, pelo que existe na "
                                 "Perennia", "What the coach suggests for today, from what is "
                                 "in Perennia"), buttons)

    # ------------------------------------------------------------ eventos

    def _events(self) -> None:
        a = self.app
        today = date.today()
        rows: list[Item] = []
        evs = coach.events(a.db)
        upcoming = [e for e in evs if e["day"] >= today.isoformat()]
        past = [e for e in evs if e["day"] < today.isoformat()]
        for e in upcoming + past[::-1]:
            adv = coach.plan_event(a.db, e, today)
            left = (date.fromisoformat(e["day"]) - today).days
            when = tr("faltam {n} dias", "{n} days to go", n=left) if left >= 0 \
                else tr("passou", "past")
            kind = tr("Força", "Strength") if e["kind"] == "strength" \
                else coach.sport_name(e.get("sport") or "cycling")
            rows.append(Item(f"{MARK.get(adv.tone, '·')}  {e['name']}",
                             value=_day_text(e["day"]),
                             detail=f"{kind} · {when} · " + adv.verdict
                             + (tr(" · {n} sessões no calendário", " · {n} sessions on the "
                                   "calendar", n=len(e["plan_ids"])) if e["plan_ids"] else ""),
                             action=lambda eid=e["id"]: a.push(event_screen(a, eid)),
                             data=("event", e["id"])))
        if not evs:
            rows.append(Item(tr("Ainda sem eventos", "No events yet"),
                             detail=tr("uma volta numa data, uma prova, um evento de força: o "
                                       "Treinador faz as perguntas e monta o plano",
                                       "a ride on a date, a race, a strength event: the coach "
                                       "asks the questions and builds the plan"),
                             enabled=False))
        rows += [Item(tr("+ Evento de força", "+ Strength event"), button=True,
                      action=lambda: a.push(EventEditor(a, None, "strength"))),
                 Item(tr("+ Evento de resistência", "+ Endurance event"), button=True,
                      primary=True, action=lambda: a.push(EventEditor(a, None, "endurance")))]
        self.list.detail_below = True
        self._set(rows, tr("Planear um evento numa data · Enter abre o plano",
                           "Plan an event on a date · Enter opens the plan"))

    # ------------------------------------------------------------ desafios

    def _challenges(self) -> None:
        a = self.app
        rows: list[Item] = []
        for ch in a.db.challenges("*"):
            ch = dict(ch)
            adv = coach.challenge_feedback(a.db, ch)
            prio = coach.challenge_priority(a.db, ch["id"])
            rows.append(Item(f"{MARK.get(adv.tone, '·')}  {ch['name']}",
                             value=f"{adv.data['desafio']['percentagem']} %",
                             detail=coach.sport_name(ch.get("sport") or "cycling") + " · "
                             + adv.verdict + " · " + (
                                 tr("importância {p}", "importance {p}",
                                    p=coach.priority_name(prio)) if prio
                                 else tr("importância por dizer", "importance not set")),
                             action=lambda c=ch: open_challenge(a, c),
                             data=("challenge", ch["id"])))
        if not rows:
            rows.append(Item(tr("Ainda sem desafios", "No challenges yet"),
                             detail=tr("cria-os no separador Treinar de cada desporto",
                                       "create them in each sport's Train tab"), enabled=False))
        self.list.detail_below = True
        self._set(rows, tr("Os teus desafios, vistos pelo Treinador · Enter abre o feedback",
                           "Your challenges, as the coach sees them · Enter opens the "
                           "feedback"))

    # ------------------------------------------------------------ longevidade

    def _longevity(self) -> None:
        adv = coach.longevity_path(self.app.db)
        self._advice_tab(adv, tr("O caminho para a longevidade, a partir das tuas fraquezas",
                                 "The path to longevity, from your weaknesses"),
                         _calendar_buttons(self, "longevity", adv))

    # ------------------------------------------------------------ programar

    def _build(self) -> None:
        a = self.app
        b = self.build
        sports = list(coach.BUILD_SPORTS)
        focuses = list(coach.FOCUSES)
        durs = list(DURATIONS)

        def pick(key, values):
            return lambda k: b.__setitem__(key, values[k])
        w = coach.build_workout(a.db, b["sport"], b["focus"], b["minutes"])
        adv = coach.review_blocks(a.db, b["sport"], w["blocks"])
        self.advice = adv
        rows = [Item(tr("Desporto", "Sport"), value=coach.sport_name(b["sport"]),
                     data="cyc:sport",
                     dropdown=Dropdown([coach.sport_name(s) for s in sports],
                                       sports.index(b["sport"]), pick("sport", sports))),
                Item(tr("Foco", "Focus"), value=coach.focus_name(b["focus"]), data="cyc:focus",
                     dropdown=Dropdown([coach.focus_name(f) for f in focuses],
                                       focuses.index(b["focus"]), pick("focus", focuses))),
                Item(tr("Duração", "Duration"), value=f"{b['minutes']} min", data="cyc:minutes",
                     dropdown=Dropdown([f"{m} min" for m in durs],
                                       durs.index(b["minutes"]) if b["minutes"] in durs else 2,
                                       pick("minutes", durs))),
                Item(tr("O treino que o Treinador faria", "The workout the coach would build"),
                     header=True),
                Item(w["name"], detail=w["goal"] + (" · " + w["note"] if w["note"] else ""),
                     enabled=False)]
        rows += advice_rows(self, adv)
        rows.append(Item(tr("Abrir no construtor", "Open in the builder"), button=True,
                         primary=True, action=lambda: open_in_builder(a, b["sport"], b["focus"],
                                                                      b["minutes"])))
        self.list.detail_below = True
        self._set(rows, tr("O Treinador programa um treino e abre-o no construtor (ciclismo, "
                           "corrida e remo)", "The coach programs a workout and opens it in "
                           "the builder (cycling, running and rowing)"))


# ====================================================================== eventos


def event_screen(app, event_id: int) -> AdviceScreen:
    def make():
        ev = coach.event(app.db, event_id)
        if ev is None:
            from perennia.core.advice import Advice
            return Advice(tr("Evento apagado", "Event deleted"))
        return coach.plan_event(app.db, ev)

    def actions(screen, adv) -> list[Item]:
        ev = coach.event(app.db, event_id)
        if ev is None:
            return []
        out = [Item(tr("Apagar", "Delete"), button=True, action=lambda: _delete(screen)),
               Item(tr("Editar respostas", "Edit answers"), button=True,
                    action=lambda: app.push(EventEditor(app, event_id, ev["kind"])))]
        if ev["plan_ids"]:
            def clear() -> None:
                n = coach.clear_schedule(app.db, event_id)
                app.message(tr("{n} sessões tiradas do calendário",
                               "{n} sessions removed from the calendar", n=n))
                screen.enter()
            out.append(Item(tr("Tirar do calendário ({n})", "Remove from calendar ({n})",
                               n=len(ev["plan_ids"])), button=True, action=clear))
        if adv.schedule:
            def put() -> None:
                n = coach.apply_schedule(app.db, event_id, adv.schedule)
                app.message(tr("{n} sessões no calendário", "{n} sessions on the calendar", n=n))
                screen.enter()
            out.append(Item(tr("Pôr no calendário ({n})", "Put on calendar ({n})",
                               n=len(adv.schedule)), button=True, primary=True, action=put))
        return out

    def _delete(screen) -> None:
        ev = coach.event(app.db, event_id)

        def go() -> None:
            coach.delete_event(app.db, event_id)
            app.pop()
        app.confirm(tr("Apagar o evento «{n}»?", "Delete the event «{n}»?", n=ev["name"]),
                    tr("As sessões que ele pôs no calendário também saem.",
                       "The sessions it put on the calendar are removed too."), go,
                    yes=tr("Apagar", "Delete"))
    return AdviceScreen(app, "coach", make, actions=actions)


class EventEditor(EditPopup):
    """As perguntas do Treinador para um evento: quando é, o que é, a tua disponibilidade de
    semana e de fim de semana, se há férias antes, e — na resistência — a rota (.gpx), a
    velocidade média pretendida e a hora de partida; na força, os objetivos de cada exercício."""

    W = 900
    MAX_H = 720

    def __init__(self, app, event_id: int | None, kind: str):
        super().__init__(app)
        self.event_id = event_id
        self.kind = kind
        ev = coach.event(app.db, event_id) if event_id else None
        ans = coach.default_answers(app.db, kind)
        if ev:
            ans.update(ev["answers"])
        self.v = {"name": ev["name"] if ev else "",
                  "day": ev["day"] if ev else (date.today() + timedelta(weeks=12)).isoformat(),
                  "sport": (ev or {}).get("sport") or "cycling",
                  "priority": (ev or {}).get("priority") or "medium", "ans": ans}

    def title(self) -> str:
        what = tr("Evento de força", "Strength event") if self.kind == "strength" \
            else tr("Evento de resistência", "Endurance event")
        return what

    def subtitle(self) -> str:
        return tr("O Treinador precisa disto para planear · o que deixares vazio, pergunta-to "
                  "no plano", "The coach needs this to plan · whatever you leave empty, it "
                  "asks in the plan")

    # ------------------------------------------------------------ linhas

    def _routes(self) -> list[tuple[str, str]]:
        out = [("", tr("Sem rota (.gpx)", "No route (.gpx)"))]
        for r in self.app.db.routes():
            out.append((r["id"], f"{r['name']} · {r['distance_m'] / 1000:.0f} km · "
                                 f"{r['ascent_m']:.0f} m"))
        return out

    def rows(self) -> list[Item]:
        v, ans = self.v, self.v["ans"]
        prios = list(coach.PRIORITIES)
        rows = [Item(tr("Nome do evento", "Event name"), value=v["name"] + "▏",
                     data="text:name"),
                Item(tr("Data", "Date"), value=_day_text(v["day"]), data="cyc:day",
                     detail=tr("Enter abre o calendário", "Enter opens the calendar")),
                Item(tr("Prioridade", "Priority"), value=coach.priority_name(v["priority"]),
                     data="cyc:priority",
                     dropdown=Dropdown([coach.priority_name(p) for p in prios],
                                       prios.index(v["priority"]),
                                       lambda k: v.__setitem__("priority", prios[k])))]
        if self.kind == "endurance":
            sports = list(coach.ENDURANCE_SPORTS)
            routes = self._routes()
            rid = ans.get("route_id") or ""
            ri = next((i for i, (k, _n) in enumerate(routes) if k == rid), 0)
            rows += [
                Item(tr("Desporto", "Sport"), value=coach.sport_name(v["sport"]),
                     data="cyc:sport",
                     dropdown=Dropdown([coach.sport_name(s) for s in sports],
                                       sports.index(v["sport"]),
                                       lambda k: v.__setitem__("sport", sports[k]))),
                Item(tr("Rota (.gpx)", "Route (.gpx)"), value=routes[ri][1], data="cyc:route",
                     detail=tr("as rotas importadas no menu Rotas · preenche a distância e a "
                               "subida", "routes imported in the Routes menu · fills distance "
                               "and climbing"),
                     dropdown=Dropdown([n for _k, n in routes], ri, self._pick_route)),
                Item(tr("Distância", "Distance"), value=self._num("distance_km", "km", 1),
                     data="num:distance_km"),
                Item(tr("Subida acumulada", "Total climbing"),
                     value=self._num("ascent_m", "m", 0), data="num:ascent_m"),
                Item(tr("Velocidade média pretendida", "Target average speed"),
                     value=self._num("target_speed_kmh", "km/h", 1),
                     data="num:target_speed_kmh"),
                Item(tr("Hora de partida", "Start time"),
                     value=(ans.get("start_time") or "") + "▏", data="text:start_time",
                     detail=tr("para a alimentação e a hidratação · 7, 0730 ou 7:30",
                               "for food and hydration · 7, 0730 or 7:30"))]
        else:
            rows += [
                Item(tr("Limite de tempo", "Time limit"),
                     value=self._num("time_limit_min", "min", 1) if ans.get("time_limit_min")
                     else tr("sem limite", "no limit"), data="num:time_limit_min",
                     detail=tr("ex.: 200 flexões e 50 elevações em 5 min · 0 = sem limite",
                               "e.g. 200 push-ups and 50 pull-ups in 5 min · 0 = no limit")),
                Item(tr("Sessões por semana", "Sessions per week"),
                     value=str(int(ans.get("sessions_per_week") or 3)),
                     data="num:sessions_per_week")]
            rows.append(Item(tr("Objetivos (exercício · objetivo · hoje)",
                                "Goals (exercise · target · today)"), header=True))
            for i, g in enumerate(ans.get("goals") or []):
                unit = g.get("unit") or "reps"
                rows.append(Item(g.get("name") or "—",
                                 value=f"{float(g.get('target') or 0):g} {unit}",
                                 detail=tr("hoje: {c}", "today: {c}",
                                           c=f"{float(g['current']):g} {unit}"
                                           if g.get("current") else tr("por dizer", "not set")),
                                 action=lambda k=i: self.app.push(GoalEditor(self.app, self, k)),
                                 data=("goal", i)))
            if len(ans.get("goals") or []) < coach.MAX_GOALS:
                rows.append(Item(tr("+ Juntar um exercício", "+ Add an exercise"),
                                 action=lambda: self.app.push(GoalEditor(self.app, self, None))))
        rows += [
            Item(tr("Disponibilidade", "Availability"), header=True),
            Item(tr("Dia de semana", "Weekday"), value=self._num("weekday_min", "min", 0),
                 data="num:weekday_min", detail=tr("minutos por dia", "minutes a day")),
            Item(tr("Dia de fim de semana", "Weekend day"),
                 value=self._num("weekend_min", "min", 0), data="num:weekend_min"),
            Item(tr("Férias: de", "Holidays: from"), value=_day_text(ans.get("vacation_from")),
                 data="cyc:start", detail=tr("um período em que podes treinar mais · Del limpa",
                                             "a period when you can train more · Del clears")),
            Item(tr("Férias: até", "Holidays: to"), value=_day_text(ans.get("vacation_to")),
                 data="cyc:end"),
            Item(tr("Notas para o Treinador", "Notes for the coach"),
                 value=(ans.get("notes") or "") + "▏", data="text:notes")]
        return rows

    def _num(self, key: str, unit: str, dec: int) -> str:
        val = float(self.v["ans"].get(key) or 0)
        return "—" if not val else f"{val:.{dec}f} {unit}"

    def _pick_route(self, k: int) -> None:
        rid = self._routes()[k][0]
        ans = self.v["ans"]
        ans["route_id"] = rid
        facts = coach.route_facts(self.app.db, rid)
        if facts:
            ans["distance_km"] = round(facts["distance_km"], 1)
            ans["ascent_m"] = round(facts["ascent_m"])
            if not self.v["name"]:
                self.v["name"] = facts["name"]

    # ------------------------------------------------------------ campos

    STEPS = {"distance_km": (1.0, 10.0, 0.0, 2000.0), "ascent_m": (50.0, 500.0, 0.0, 30000.0),
             "target_speed_kmh": (0.5, 5.0, 0.0, 60.0), "time_limit_min": (0.5, 5.0, 0.0, 600.0),
             "sessions_per_week": (1.0, 1.0, 1.0, 7.0), "weekday_min": (5.0, 30.0, 0.0, 600.0),
             "weekend_min": (10.0, 60.0, 0.0, 900.0)}

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        small, large, lo, hi = self.STEPS[field]
        cur = float(self.v["ans"].get(field) or 0)
        self.v["ans"][field] = max(lo, min(hi, round(cur + steps * (large if big else small), 2)))

    def num_set(self, field: str, value: float | None) -> None:
        _s, _l, lo, hi = self.STEPS[field]
        self.v["ans"][field] = max(lo if value else 0.0, min(hi, float(value or 0)))

    def cycle(self, field: str, step: int) -> None:
        v, ans = self.v, self.v["ans"]
        if field == "day":
            v["day"] = (date.fromisoformat(v["day"]) + timedelta(days=step)).isoformat()
        elif field in ("start", "end"):
            k = "vacation_from" if field == "start" else "vacation_to"
            base = coach._parse_day(ans.get(k)) or date.today()
            ans[k] = (base + timedelta(days=step)).isoformat()
        elif field == "priority":
            ps = list(coach.PRIORITIES)
            v["priority"] = ps[(ps.index(v["priority"]) + step) % len(ps)]
        elif field == "sport":
            ss = list(coach.ENDURANCE_SPORTS)
            v["sport"] = ss[(ss.index(v["sport"]) + step) % len(ss)]
        elif field == "route":
            routes = self._routes()
            rid = ans.get("route_id") or ""
            i = next((j for j, (k, _n) in enumerate(routes) if k == rid), 0)
            self._pick_route((i + step) % len(routes))

    def date_get(self, field: str) -> str | None:
        if field == "day":
            return self.v["day"]
        return self.v["ans"].get("vacation_from" if field == "start" else "vacation_to") or None

    def date_set(self, field: str, iso: str) -> None:
        if field == "day":
            self.v["day"] = iso
        else:
            self.v["ans"]["vacation_from" if field == "start" else "vacation_to"] = iso
        self.refresh()

    def text_input(self, field: str, text: str) -> None:
        limit = {"name": 60, "start_time": 5, "notes": 300}[field]
        if field == "name":
            self.v["name"] = (self.v["name"] + text)[:limit]
        else:
            self.v["ans"][field] = ((self.v["ans"].get(field) or "") + text)[:limit]
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "name":
            self.v["name"] = self.v["name"][:-1]
        else:
            self.v["ans"][field] = (self.v["ans"].get(field) or "")[:-1]
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        from pyglet.window import key
        if symbol == key.DELETE:
            f = self._field("cyc:")
            if f in ("start", "end"):
                self.v["ans"]["vacation_from" if f == "start" else "vacation_to"] = ""
                self.enter()
                return True
        return super().on_key(symbol, modifiers)

    def commit(self) -> bool:
        v, ans = self.v, dict(self.v["ans"])
        from perennia.core import bp
        if ans.get("start_time") and bp.parse_time(ans["start_time"]) is None:
            self.app.message(tr("A hora de partida não se percebe: escreve 7, 0730 ou 7:30.",
                                "The start time is unclear: type 7, 0730 or 7:30."))
            return False
        if ans.get("start_time"):
            ans["start_time"] = bp.parse_time(ans["start_time"])
        vf, vt = coach._parse_day(ans.get("vacation_from")), coach._parse_day(
            ans.get("vacation_to"))
        if (vf is None) != (vt is None):
            self.app.message(tr("Férias: põe as duas datas (de e até), ou nenhuma.",
                                "Holidays: set both dates (from and to), or neither."))
            return False
        if vf and vt and vt < vf:
            self.app.message(tr("Férias: a data «até» é antes da «de».",
                                "Holidays: the 'to' date is before 'from'."))
            return False
        try:
            self.event_id = coach.save_event(self.app.db, self.event_id, kind=self.kind,
                                             name=v["name"], day=v["day"], sport=v["sport"],
                                             priority=v["priority"], answers=ans)
        except ValueError as e:
            self.app.message(str(e))
            return False
        self.v["ans"] = ans
        return True

    def saved_message(self) -> str:
        return tr("Evento guardado: abre-o para ver o plano", "Event saved: open it to see "
                  "the plan")


class GoalEditor(EditPopup):
    """Um objetivo de um evento de força: o exercício (da tua lista, ou escrito), a unidade,
    o objetivo e o que fazes hoje."""

    W = 760

    def __init__(self, app, editor: EventEditor, index: int | None):
        super().__init__(app)
        self.editor = editor
        self.index = index
        goals = editor.v["ans"].setdefault("goals", [])
        g = dict(goals[index]) if index is not None else {}
        self.v = {"name": g.get("name") or "", "unit": g.get("unit") or "reps",
                  "target": float(g.get("target") or 0), "current": float(g.get("current") or 0)}

    def title(self) -> str:
        return tr("Objetivo", "Goal")

    def subtitle(self) -> str:
        return tr("Escolhe um exercício da lista (Enter) ou escreve o nome",
                  "Pick an exercise from the list (Enter) or type the name")

    def _exercises(self) -> list[str]:
        try:
            return sorted({e["name"] for e in st.exercises(self.app.db)})
        except Exception:
            return []

    def unit_name(self, u: str) -> str:
        return {"reps": tr("repetições", "reps"), "kg": "kg", "s": tr("segundos", "seconds"),
                "m": tr("metros", "metres")}[u]

    def rows(self) -> list[Item]:
        v = self.v
        units = list(coach.GOAL_UNITS)
        names = self._exercises()
        rows = [Item(tr("Exercício", "Exercise"), value=v["name"] or "—", data="cyc:exercise",
                     dropdown=Dropdown(names, names.index(v["name"]) if v["name"] in names
                                       else 0, lambda k: v.__setitem__("name", names[k]),
                                       title=tr("Exercício", "Exercise"))),
                Item(tr("…ou escreve o nome", "…or type the name"), value=v["name"] + "▏",
                     data="text:name"),
                Item(tr("Unidade", "Unit"), value=self.unit_name(v["unit"]), data="cyc:unit",
                     dropdown=Dropdown([self.unit_name(u) for u in units],
                                       units.index(v["unit"]),
                                       lambda k: v.__setitem__("unit", units[k]))),
                Item(tr("Objetivo no dia do evento", "Target on event day"),
                     value=f"{v['target']:g}" if v["target"] else "—", data="num:target"),
                Item(tr("O que fazes hoje (máximo)", "What you do today (max)"),
                     value=f"{v['current']:g}" if v["current"] else "—", data="num:current")]
        if self.index is not None:
            rows.append(Item(tr("Tirar este objetivo", "Remove this goal"),
                             action=self._remove))
        return rows

    def cycle(self, field: str, step: int) -> None:
        if field == "unit":
            us = list(coach.GOAL_UNITS)
            self.v["unit"] = us[(us.index(self.v["unit"]) + step) % len(us)]
        elif field == "exercise":
            names = self._exercises()
            if names:
                i = names.index(self.v["name"]) if self.v["name"] in names else -1
                self.v["name"] = names[(i + step) % len(names)]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        step = (10 if big else 1) if self.v["unit"] != "kg" else (10 if big else 2.5)
        self.v[field] = max(0.0, self.v[field] + steps * step)

    def num_set(self, field: str, value: float | None) -> None:
        self.v[field] = max(0.0, float(value or 0))

    def text_input(self, field: str, text: str) -> None:
        self.v["name"] = (self.v["name"] + text)[:50]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v["name"] = self.v["name"][:-1]
        self.enter()

    def commit(self) -> bool:
        v = self.v
        if not v["name"].strip():
            self.app.message(tr("Escolhe ou escreve o exercício.", "Pick or type the exercise."))
            return False
        if not v["target"]:
            self.app.message(tr("Escreve o objetivo.", "Type the target."))
            return False
        goals = self.editor.v["ans"].setdefault("goals", [])
        g = {"name": v["name"].strip(), "unit": v["unit"], "target": v["target"],
             "current": v["current"]}
        if self.index is None:
            goals.append(g)
            self.index = len(goals) - 1
        else:
            goals[self.index] = g
        return True

    def saved_message(self) -> str:
        return tr("Objetivo no evento (falta guardar o evento)",
                  "Goal on the event (the event still needs saving)")

    def close(self) -> None:
        super().close()
        if self.app.current is self.editor:
            self.editor.enter()

    def _remove(self) -> None:
        goals = self.editor.v["ans"].get("goals") or []
        if self.index is not None and 0 <= self.index < len(goals):
            del goals[self.index]
        self._saved_state = self.state()
        self.close()


# ====================================================================== desafios


class ChallengeCoach(AdviceScreen):
    """O feedback do Treinador a um desafio: longe ou perto, o que falta por semana; pergunta a
    importância (lista) e, com ela, ajusta os treinos — «Pôr no calendário» agenda-os."""

    def __init__(self, app, challenge: dict):
        self.challenge = dict(challenge)
        super().__init__(app, "coach", self._make, extra=self._extra, actions=self._actions)

    def _row(self) -> dict | None:
        row = next((c for c in self.app.db.challenges("*")
                    if c["id"] == self.challenge["id"]), None)
        return dict(row) if row is not None else None

    def _make(self):
        ch = self._row()
        if ch is None:
            from perennia.core.advice import Advice
            return Advice(tr("Desafio apagado", "Challenge deleted"))
        self.challenge = ch
        return coach.challenge_feedback(self.app.db, ch)

    def _extra(self, _screen) -> list[Item]:
        db = self.app.db
        prio = coach.challenge_priority(db, self.challenge["id"])
        values = [None] + list(coach.PRIORITIES)
        labels = [tr("ainda não disse", "not said yet")] + [
            {"low": tr("baixa — fica em pano de fundo", "low — stays in the background"),
             "medium": tr("média — encaixa sem tirar os treinos-chave",
                          "medium — fits without removing key sessions"),
             "high": tr("alta — quero prioritizá-lo", "high — I want to prioritise it")}[p]
            for p in coach.PRIORITIES]

        def pick(k: int) -> None:
            coach.set_challenge_priority(db, self.challenge["id"], values[k])
        return [Item(tr("Quão importante é este desafio para ti?",
                        "How important is this challenge to you?"),
                     value=coach.priority_name(prio) if prio else tr("por dizer", "not set"),
                     data="cyc:priority",
                     detail=tr("Enter abre a lista · o Treinador ajusta os treinos com isto",
                               "Enter opens the list · the coach adjusts training with this"),
                     dropdown=Dropdown(labels, values.index(prio), pick))]

    def _actions(self, screen, adv) -> list[Item]:
        return _calendar_buttons(self, f"challenge:{self.challenge['id']}", adv)


def challenge_button(app, challenge: dict) -> Item:
    return Item(tr("Treinador", "Coach"), button=True,
                action=lambda: open_challenge(app, challenge))


# ====================================================================== construtor


def builder_feedback(app, builder) -> None:
    """O botão «Treinador» do construtor: feedback ao treino que lá está, com a forma atual."""
    builder.coach_asked = True

    def make():
        return coach.review_blocks(app.db, builder.sport, builder.blocks)

    def actions(screen, adv) -> list[Item]:
        scale = (adv.data.get("treino") or {}).get("escala_sugerida")
        if not scale:
            return []

        def lighter() -> None:
            builder.blocks = coach.lighter_blocks(builder.blocks, scale)
            builder.sel = min(builder.sel, len(builder.blocks) - 1)
            builder.dirty = True
            app.pop()
            builder.redraw()
            builder.enter()
            app.message(tr("Versão mais leve aplicada (ainda por guardar).",
                           "Lighter version applied (not saved yet)."))
        return [Item(tr("Aplicar a versão mais leve", "Apply the lighter version"), button=True,
                     primary=True, action=lighter)]
    app.push(AdviceScreen(app, "coach", make, actions=actions,
                          subtitle=tr("O treino que estás a construir, à luz da tua forma",
                                      "The workout you are building, in light of your form")))


def live_verdict(app, builder) -> str:
    """Uma linha para o construtor (depois de pedires feedback uma vez): refaz-se só quando os
    blocos mudam."""
    if not getattr(builder, "coach_asked", False) or \
            not options.get(app.db, "coach_live_feedback"):
        return ""
    sig = tuple((b.kind, b.dur_type, round(b.dur), b.lo, b.hi) for b in builder.blocks)
    if getattr(builder, "_coach_sig", None) != sig:
        builder._coach_sig = sig
        try:
            if getattr(builder, "_coach_snap", None) is None:
                builder._coach_snap = coach.snapshot(app.db)
            adv = coach.review_blocks(app.db, builder.sport, builder.blocks,
                                      snap=builder._coach_snap, with_longevity=False)
            builder._coach_live_text = f"{MARK.get(adv.tone, '·')} " + tr("Treinador", "Coach") \
                + ": " + adv.verdict
        except Exception:
            builder._coach_live_text = ""
    return builder._coach_live_text
