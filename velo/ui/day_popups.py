"""O dia do calendário, numa janela, e o planeamento de um treino.

**DayPopup** (um clique num dia do calendário do ecrã inicial): o que foi feito e o que está
planeado nesse dia; por baixo, a **nota do dia**; e os botões **Nota do dia**, **Diário de
saúde** (o menu da Saúde, nesse dia) e **+ Planear treino**.

**Planear** abre, por esta ordem, janelas encadeadas:

1. o **desporto**;
2. a **origem**, que depende do dia:
   * hoje ou mais tarde → importar um treino **da lista**, importar **do computador** ou
     **criar no construtor**;
   * um dia que já passou → carregar uma atividade **.fit**, ou sincronizar (**HRV4Training**,
     **dados de saúde** em .csv, **GarminDB**).
"""
from __future__ import annotations

from datetime import date

import pyglet
import pyglet.graphics
import pyglet.shapes
from pyglet.window import key

from velo.core import calendar_view as cv
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx.compat import label as make_label
from velo.ui import calendar_screens as cs
from velo.ui.app import PopupMixin, Screen
from velo.ui.widgets import DIM, PANEL, TEXT, Item

SPORTS = ("cycling", "rowing", "running", "swimming", "gym")


def plan_it(app, day: date, sport: str, wid: str, name: str) -> None:
    """Põe o treino no plano do dia (sem duplicar) e avisa. Dias que já passaram não se
    planeiam."""
    if day < date.today():
        app.message(tr("Um dia que já passou não se planeia: carrega o treino que fizeste.",
                       "A day in the past can't be planned: upload the workout you did."))
        return
    have = [p for p in cv.planned_for(app.db, day) if p.workout_id == wid and p.sport == sport]
    if not have:
        cv.plan_add(app.db, day, sport, wid, name)
    app.message(tr("«{n}» planeado para {d}", "«{n}» planned for {d}", n=name,
                   d=day.strftime("%d/%m")))


# ===================================================================== o dia


class DayPopup(PopupMixin, Screen):
    W, H = 940, 760
    SEARCH = False
    AGENT = False
    NOTE_H = 150                         # a secção da nota, por cima dos botões

    def __init__(self, app, day: date):
        super().__init__(app)
        self.day = day
        self.back_button = None
        self.note_batch = pyglet.graphics.Batch()
        self.note_bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL[:3],
                                               batch=self.note_batch)
        self.note_head = make_label("", font_size=12, bold=True, color=DIM, anchor_y="top",
                                    batch=self.note_batch)
        self.note_text = make_label("", font_size=13, color=TEXT, anchor_y="top",
                                    batch=self.note_batch, multiline=True, width=400)
        self._init_popup()

    @property
    def past(self) -> bool:
        return self.day < date.today()

    def _place(self) -> None:
        super()._place()
        p = self.popup
        rows = max(2, int((p.h - 92 - 96 - self.NOTE_H) // 38) + 1)
        self.list.set_visible_rows(rows)
        self.note_bg.x, self.note_bg.y = p.x + 28, p.y + 74
        self.note_bg.width, self.note_bg.height = p.w - 56, self.NOTE_H - 14
        self.note_head.x, self.note_head.y = p.x + 40, p.y + 74 + self.NOTE_H - 22
        self.note_text.x, self.note_text.y = p.x + 40, p.y + 74 + self.NOTE_H - 44
        self.note_text.width = p.w - 80

    # ------------------------------------------------------------ conteúdo

    def enter(self) -> None:
        a = self.app
        from velo.core import health
        from velo.core import objectives as ob
        done = cv.sessions_between(a.db, self.day, self.day)
        plan = cv.planned_between(a.db, self.day, self.day, done)
        items: list[Item] = []
        for e in done:
            bits = [x for x in (f"{e.distance_m / 1000:.1f} km" if e.distance_m else "",
                                tr("carga {l}", "load {l}", l=f"{e.load:.0f}") if e.load else "",
                                e.verdict) if x]
            items.append(Item(f"✓ {cs.sport_label(e.sport)} · {e.title}", value=hms(e.seconds),
                              detail=" · ".join(bits) or tr("sem feedback", "no feedback"),
                              action=lambda ee=e: self._open_session(ee), data=("done", e)))
        for e in plan:
            b = ob.workout_brief(a.db, e.sport, e.workout_id)
            items.append(Item(("✓ " if e.done else "◷ ") + tr("Planeado", "Planned")
                              + f" · {cs.sport_label(e.sport)} · {e.title}",
                              value=hms(e.seconds) if e.seconds else "",
                              detail=(b.goal if b else "") + ("  ·  " + tr(
                                  "Del tira do plano", "Del removes it") if not e.done else ""),
                              action=lambda ee=e: self._open_plan(ee), data=("plan", e)))
        if not items:
            items.append(Item(tr("Nada feito nem planeado neste dia", "Nothing done or planned "
                                 "on this day"), enabled=False))
        done_h, total_h = health.completeness(a.db, self.day)
        items += [Item(tr("Nota do dia", "Day note"), button=True, action=self._edit_note),
                  Item(tr("Diário de saúde", "Health log") + f" {done_h}/{total_h}", button=True,
                       action=self._open_log)]
        if self.past:
            # um dia que já passou não se planeia: ver o que se fez e, se o treino foi feito
            # noutro sítio, carregar o ficheiro
            items.append(Item(tr("Carregar treino", "Upload a workout"), button=True,
                               primary=True, action=lambda: a.push(LoadDayPopup(a, self.day))))
        else:
            items.append(Item(tr("+ Planear treino", "+ Plan a workout"), button=True,
                              primary=True, action=lambda: a.push(PlanSportPopup(a, self.day))))
        wd = cv.weekday_name(self.day.weekday())
        self.chrome.set(f"{wd}, {self.day.day} {cv.month_name(self.day.month)} {self.day.year}",
                        tr("Feitas: {a} · planeadas: {b} · Enter abre · Del tira do plano · "
                           "N nota · Esc fecha", "Done: {a} · planned: {b} · Enter opens · Del "
                           "removes from the plan · N note · Esc closes", a=len(done),
                           b=len(plan)), "")      # sem rodapé: os três botões ocupam-no
        self.list.set_items(items, keep_index=True)
        self._fill_note()

    def _fill_note(self) -> None:
        from velo.core import health
        note = health.day_note(self.app.db, self.day)
        self.note_head.text = tr("NOTA DO DIA", "DAY NOTE")
        self.note_text.text = (note if note else tr(
            "Sem nota. Carrega em «Nota do dia» (ou N) para escrever: viagem, doença, como te "
            "sentiste…", "No note. Press “Day note” (or N) to write: travel, illness, how you "
            "felt…"))
        self.note_text.color = TEXT if note else DIM
        # só cabem umas linhas: o resto vê-se ao editar
        lines = self.note_text.text.splitlines()
        if len(lines) > 4:
            self.note_text.text = "\n".join(lines[:4]) + " …"

    def draw(self) -> None:
        self.popup.draw()
        self._wrap_subtitle()
        self.chrome.set_footer_limit(self.list.buttons_left)
        self.chrome.draw()
        self.note_batch.draw()
        self.list.draw()

    # -------------------------------------------------------------- ações

    def _edit_note(self) -> None:
        from velo.core import health
        from velo.ui.health_screens import TextEditScreen
        self.app.push(TextEditScreen(
            self.app, tr("Nota do dia", "Day note"), self.day.strftime("%d/%m/%Y"),
            health.day_note(self.app.db, self.day),
            lambda text: health.set_day_note(self.app.db, self.day, text)))

    def _open_log(self) -> None:
        from velo.ui.health_screens import DailyLogScreen
        self.app.push(DailyLogScreen(self.app, self.day))

    def _open_session(self, e) -> None:
        cs.DayScreen._open_session(self, e)

    def _open_plan(self, e) -> None:
        cs.DayScreen._open_plan(self, e)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.N:
            self._edit_note()
            return True
        item = self.list.selected
        if symbol in (key.DELETE, key.BACKSPACE) and item is not None and \
                isinstance(item.data, tuple) and item.data[0] == "plan":
            pid = item.data[1].id

            def gone() -> None:
                cv.plan_remove(self.app.db, pid)
                self.app.message(tr("Tirado do plano", "Removed from the plan"))
                self.enter()
            self.app.confirm(tr("Tirar «{n}» do plano?", "Remove «{n}» from the plan?",
                                n=item.label),
                             tr("O treino continua na lista; só sai deste dia.",
                                "The workout stays in the list; it only leaves this day."),
                             gone, yes=tr("Tirar do plano", "Remove"))
            return True
        return super().on_key(symbol, modifiers)


# =============================================================== planear


class PlanSportPopup(PopupMixin, Screen):
    """1.º passo: o desporto."""
    W, H = 640, 480
    SEARCH = False
    AGENT = False

    def __init__(self, app, day: date, on_planned=None):
        super().__init__(app)
        self.day = day
        self.on_planned = on_planned
        self.back_button = None
        self._init_popup()

    def enter(self) -> None:
        items = [Item(cs.sport_label(s), action=lambda k=s: self._pick(k), data=s)
                 for s in SPORTS]
        items.append(Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop))
        self.chrome.set(tr("Planear um treino", "Plan a workout"),
                        tr("{d} · escolhe o desporto", "{d} · pick the sport",
                           d=self.day.strftime("%d/%m/%Y")), "")
        self.list.set_items(items, keep_index=True)

    def _pick(self, sport: str) -> None:
        a = self.app
        a.pop()
        a.push(PlanSourcePopup(a, self.day, sport, self.on_planned))


class PlanSourcePopup(PopupMixin, Screen):
    """2.º passo: de onde vem o treino (só para hoje e dias futuros)."""
    W, H = 760, 520
    SEARCH = False
    AGENT = False

    def __init__(self, app, day: date, sport: str, on_planned=None):
        super().__init__(app)
        self.day, self.sport = day, sport
        self.on_planned = on_planned
        self.back_button = None
        self._init_popup()

    def enter(self) -> None:
        a = self.app
        items = [
            Item(tr("Importar um treino da lista", "Import a workout from the list"),
                 detail=tr("os treinos já guardados de {s}", "the saved {s} workouts",
                           s=cs.sport_label(self.sport)), action=self._from_list),
            Item(tr("Importar um treino do computador", "Import a workout from the computer"),
                 detail=tr(".zwo, .fit, .mrc, .erg… (pergunta se fica na lista)",
                           ".zwo, .fit, .mrc, .erg… (asks whether to keep it in the list)"),
                 action=self._from_computer),
            Item(tr("Criar um treino no construtor", "Create a workout in the builder"),
                 detail=tr("fica na lista e já planeado neste dia", "kept in the list and "
                           "already planned on this day"), action=self._create)]
        sub = tr("{d} · de onde vem o treino de {s}?", "{d} · where does the {s} workout "
                 "come from?", d=self.day.strftime("%d/%m/%Y"), s=cs.sport_label(self.sport))
        items.append(Item(tr("Cancelar", "Cancel"), button=True, action=a.pop))
        self.chrome.set(tr("Planear · {s}", "Plan · {s}", s=cs.sport_label(self.sport)), sub, "")
        self.list.set_items(items, keep_index=True)

    # -------------------------------------------------------------- origens

    def _done(self, wid: str, name: str) -> None:
        plan_it(self.app, self.day, self.sport, wid, name)
        if self.on_planned is not None:
            self.on_planned()

    def _from_list(self) -> None:
        a = self.app
        a.pop()
        a.push(PlanWorkoutPopup(a, self.day, self.sport, self.on_planned))

    def _from_computer(self) -> None:
        a = self.app
        a.pop()
        from velo.ui.workout_import import WorkoutFilePopup

        def done(wid: str) -> None:
            names = {w[0]: w[1] for w in cs.workouts_for(a.db, self.sport)}
            self._done(wid, names.get(wid, ""))
        a.push(WorkoutFilePopup(a, self.sport, mode="list", on_done=done))

    def _create(self) -> None:
        """O construtor do desporto; ao guardar, o treino fica planeado neste dia."""
        a = self.app
        a.pop()
        if self.sport == "gym":
            from velo.ui.gym_screens import ModalityPicker
            a.push(ModalityPicker(a, plan_day=self.day))
            return
        from velo.ui import builder_screens as bs
        from velo.core import workout_meta as wm
        ctl = wm.default_control(self.sport)
        a.push(bs.BlockBuilder(a, self.sport, None, control=ctl, plan_day=self.day))

class LoadDayPopup(PopupMixin, Screen):
    """Um dia que já passou não se planeia: aqui carrega-se o que se fez noutro sítio."""
    W, H = 760, 480
    SEARCH = False
    AGENT = False

    def __init__(self, app, day: date):
        super().__init__(app)
        self.day = day
        self.back_button = None
        self._init_popup()

    def enter(self) -> None:
        items = [
            Item(tr("Carregar um ficheiro de treino (.fit, .tcx)", "Upload a workout file "
                    "(.fit, .tcx)"),
                 detail=tr("o treino que fizeste nesse dia noutro sítio: Upload manual",
                           "the workout you did that day elsewhere: manual upload"),
                 action=lambda: self._sync("Upload manual"), data="upload"),
            Item(tr("Sincronizar a HRV (HRV4Training)", "Sync HRV (HRV4Training)"),
                 detail=tr("importa o .csv do HRV4Training", "imports the HRV4Training .csv"),
                 action=lambda: self._sync("HRV4Training")),
            Item(tr("Sincronizar dados de saúde (.csv)", "Sync health data (.csv)"),
                 detail=tr("o .csv do diário de saúde, por data", "the health-log .csv, by date"),
                 action=lambda: self._sync("Saúde")),
            Item(tr("Sincronizar o GarminDB", "Sync GarminDB"),
                 detail=tr("atividades, sono, HRV, passos…", "activities, sleep, HRV, steps…"),
                 action=lambda: self._sync("GarminDB")),
            Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop)]
        self.chrome.set(tr("Carregar treino", "Upload a workout"),
                        tr("{d} já passou: não se planeia, carrega-se o que aconteceu",
                           "{d} is in the past: nothing to plan, load what happened",
                           d=self.day.strftime("%d/%m/%Y")), "")
        self.list.set_items(items, keep_index=True)

    def _sync(self, source: str) -> None:
        a = self.app
        a.pop()
        a.open_backups(source=source)


class PlanWorkoutPopup(PopupMixin, Screen):
    """Os treinos guardados do desporto, numa janela com pesquisa: Enter planeia."""
    W, H = 760, 560
    SEARCH_ENTER_PICKS = True
    AGENT = False

    def __init__(self, app, day: date, sport: str, on_planned=None):
        super().__init__(app)
        self.day, self.sport = day, sport
        self.on_planned = on_planned
        self.back_button = None
        self._init_popup()
        self.search_focus(True)

    def enter(self) -> None:
        a = self.app
        items = [Item(name, detail=note, action=lambda w=wid, n=name: self._pick(w, n))
                 for wid, name, note in cs.workouts_for(a.db, self.sport)]
        if not items:
            items = [Item(tr("Ainda não há treinos guardados neste desporto",
                             "No saved workouts in this sport yet"), enabled=False)]
        items.append(Item(tr("Cancelar", "Cancel"), button=True, action=a.pop))
        self.chrome.set(tr("Planear · {s}", "Plan · {s}", s=cs.sport_label(self.sport)),
                        tr("{d} · escreve para filtrar · Enter escolhe",
                           "{d} · type to filter · Enter picks", d=self.day.strftime("%d/%m/%Y")),
                        "")
        self.list.set_items(items, keep_index=True)

    def _pick(self, wid: str, name: str) -> None:
        self.app.pop()
        plan_it(self.app, self.day, self.sport, wid, name)
        if self.on_planned is not None:
            self.on_planned()

    def search_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.ESCAPE and not self.search_box.text:
            self.app.pop()
            return True
        return super().search_key(symbol, modifiers)
