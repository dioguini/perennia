"""Preparar uma sessão numa só janela — ciclismo, corrida e remo.

«Sessão de treino» pergunta primeiro **Livre** ou **Carregar treino**:

* *Carregar treino* abre a lista de treinos do desporto; a ficha do treino
  tem, em baixo à direita, «Configurar sessão de treino», que abre esta
  mesma janela (no ciclismo e na corrida a rota é opcional);
* *Livre* abre logo esta janela. No ciclismo a sessão livre precisa de uma
  rota (.gpx).

A janela junta tudo o que se escolhe antes de começar, de cima para baixo:
os aparelhos (abre o emparelhamento), a rota (.gpx: uma das tuas ou uma nova)
e os segmentos do Strava dessa rota, o modo da sessão (sozinho ou contra as
tuas sessões anteriores), o ERG nos treinos ERG, as opções do Challenge
(duração, bots) e o auto lap. A qualidade do 3D está nas Definições.

**Strava sem internet.** Se a procura dos segmentos falhar, aparece um aviso
(«não foi possível ligar ao Strava») e escolhes: prosseguir sem os segmentos
ou cancelar a sessão.
"""
from __future__ import annotations

import time

from pyglet.window import key

from velo.core import sports as sp
from velo.core import workout_meta as wm
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.ui.app import (AutoLapOptions, ConfirmScreen, GpxPicker, PopupMixin, RideScreen,
                         Screen)
from velo.ui.widgets import Item


# ------------------------------------------------------------- a pergunta


def ask_start(app, sport: str, hub=None) -> None:
    """«Sessão de treino»: tudo numa só janela — o modo da sessão (Livre,
    Carregar treino, Do computador, Challenge ou Testes) e, a seguir, a
    preparação."""
    app.push(SessionModePopup(app, sport, hub))


class SessionModePopup(PopupMixin, Screen):
    """A janela da «Sessão de treino». Afinal tudo pode ser uma sessão de
    treino; muda só o modo:

    * **Livre** — escolhes os aparelhos e a rota (.gpx) e começas;
    * **Carregar treino** — a lista de treinos do desporto;
    * **Do computador** — um .zwo ou .fit;
    * **Challenge** — fuga, jogos, provas…;
    * **Testes** — os testes de aptidão (FTP, 2000 m, Cooper…).

    O que se escolhe numa lista abre-se aqui mesmo (Esc volta ao passo
    anterior); escolhida uma coisa, a janela passa para a preparação da sessão."""

    W, H = 920, 660
    SEARCH_ENTER_PICKS = False

    def __init__(self, app, sport: str, hub=None):
        super().__init__(app)
        self.sport = sport
        self.hub = hub
        self.level: str | None = None          # None = os modos
        self.back_button = None
        self._init_popup()

    # ------------------------------------------------------------- os modos

    def _after(self, action):
        """Fecha a janela e faz a ação (o que abre por cima volta ao menu do desporto)."""
        def go() -> None:
            self.app.pop()
            action()
        return go

    def _sub(self, name: str) -> tuple[str, list[Item]]:
        """O título e as linhas de uma lista (treinos, Challenge ou testes), lidas
        dos menus que já existem."""
        a = self.app
        if name.startswith(("mod:", "gymwk:")):
            return self._gym_sub(name)
        if name == "workouts":
            rows = self.hub.items_for("library") if self.hub is not None else []
            title = tr("Carregar treino", "Load a workout")
        elif name == "challenge":
            from velo.ui.challenge_screens import challenge_menu
            scr = challenge_menu(a, self.sport)
            scr.enter()
            rows = list(scr.list.all_items or scr.list.items)
            title = "Challenge"
        else:
            from velo.ui.app import _extra_health
            scr = _extra_health().TestsMenu(a, "longevity" if self.sport == "gym"
                                            else self.sport)
            scr.enter()
            rows = list(scr.list.all_items or scr.list.items)       # com «Adicionar teste»
            title = tr("Testes", "Tests")
        out = []
        for r in rows:
            if r.header or r.action is None and not r.enabled:
                out.append(Item(r.label, value=r.value, detail=r.detail, enabled=False,
                                header=r.header))
                continue
            out.append(Item(r.label, value=r.value, detail=r.detail, data=r.data,
                            button=r.button, primary=r.primary, action=self._after(r.action)))
        if not out:
            out = [Item(tr("Nada por aqui ainda", "Nothing here yet"), enabled=False)]
        return title, out

    def mode_rows(self) -> list[Item]:
        a, sport = self.app, self.sport

        def free() -> None:
            a.push(SessionSetup(a, sport, kind="free"))

        def from_pc() -> None:
            from velo.ui.workout_import import WorkoutFilePopup
            a.push(WorkoutFilePopup(a, sport, mode="session"))
        if sport == "gym":                 # no ginásio escolhe-se a modalidade
            from velo.core import gym
            from velo.core import laps_session as ls
            from velo.ui import gym_screens as gs
            rows = []
            for m in gym.modalities():
                n = len(gym.workouts(a.db, m.key)) if not m.laps else len(ls.plans(a.db, m.key))
                rows.append(Item(m.name, value=tr("{n} treinos", "{n} workouts", n=n) if n
                                 else "", detail=m.desc, data=("modality", m.key),
                                 action=lambda k=m.key: self.open_level(f"mod:{k}")))
            rows += [Item("Challenge", detail=_challenge_help(sport),
                          action=lambda: self.open_level("challenge"), data="challenge"),
                     Item(tr("Testes", "Tests"), detail=tr("força, equilíbrio e mobilidade",
                                                          "strength, balance and mobility"),
                          action=lambda: self.open_level("tests"), data="tests")]
            return rows
        free_help = {"cycling": tr("escolhes os aparelhos e a rota (.gpx) e pedalas",
                                   "pick the devices and the route (.gpx) and ride"),
                     "running": tr("passadeira, com ou sem rota (.gpx)",
                                   "treadmill, with or without a route (.gpx)"),
                     "rowing": tr("remo sem plano, com voltas", "row with no plan, with laps")
                     }.get(sport, "")
        return [
            Item(tr("Livre", "Free"), detail=free_help, action=self._after(free), data="free"),
            Item(tr("Carregar treino", "Load workout"),
                 detail=tr("a lista de treinos de {s}", "the {s} workout list", s=sp.name(sport)),
                 action=lambda: self.open_level("workouts"), data="workouts"),
            Item(tr("Do computador", "From the computer"),
                 detail=tr("um .zwo ou .fit (pergunta se fica na lista)",
                           "a .zwo or .fit (asks whether to keep it in the list)"),
                 action=self._after(from_pc), data="pc"),
            Item("Challenge", detail=_challenge_help(sport),
                 action=lambda: self.open_level("challenge"), data="challenge"),
            Item(tr("Testes", "Tests"),
                 detail=tr("testes de aptidão: o resultado vem da própria sessão",
                           "fitness tests: the result comes from the session itself"),
                 action=lambda: self.open_level("tests"), data="tests")]

    @staticmethod
    def parent_of(level: str | None) -> str | None:
        """O passo anterior: lista de treinos → opções da modalidade → modalidades."""
        if level and level.startswith("gymwk:"):
            return "mod:" + level.split(":", 1)[1]
        return None

    def open_level(self, name: str | None) -> None:
        self.level = name
        self.list.index = 0
        self.enter()

    # --------------------------------------------- ginásio: a modalidade escolhida

    def _gym_sub(self, name: str) -> tuple[str, list[Item]]:
        """As opções de uma modalidade, na mesma janela: treino livre, surpresa, carregar
        treino (a lista da modalidade), livre por blocos, do computador, Challenge e Testes."""
        from velo.core import gym
        from velo.core import laps_session as ls
        from velo.ui import gym_screens as gs
        a = self.app
        kind, mod = name.split(":", 1)
        m = gym.modality(mod)
        if kind == "gymwk":
            return self._gym_workouts(mod)
        if m.laps:                                         # Conditioning: planos de voltas
            rows = [
                Item(tr("Treino livre", "Free workout"),
                     detail=tr("Monta o plano de voltas e depois começa",
                               "Build the lap plan, then start"),
                     action=self._after(lambda: a.push(gs.LapPlanEditor(a, None, draft=True)))),
                Item(tr("Treino surpresa", "Surprise workout"),
                     detail=tr("Voltas de máquina e de força à sorte",
                               "Random machine and strength laps"),
                     action=self._after(lambda: a.push(gs.LapPlanEditor(
                         a, None, draft=True, items=ls.surprise_plan(
                             a.db, int(time.time()) % 100000)))))]
            for p in ls.plans(a.db, "conditioning"):
                rows.append(Item(p["name"], value=f"≈ {hms(ls.plan_seconds(p['items']))}",
                                 detail=tr("{n} voltas", "{n} laps", n=len(p["items"])),
                                 action=self._after(lambda pid=p["id"]: gs.start_laps(
                                     a, "conditioning", ls.plan(a.db, pid)["items"]))))
            rows += self._gym_common_rows()
            return m.name, rows
        n = len(gym.workouts(a.db, mod))
        rows = [
            Item(tr("Treino livre", "Free workout"),
                 detail=tr("Monta o plano e depois começa (podes guardá-lo)",
                           "Build the plan, then start (you can save it)"),
                 action=self._after(lambda: a.push(gs.GymPlanEditor(a, mod, None, draft=True)))),
            Item(tr("Treino surpresa", "Surprise workout"),
                 detail=tr("Exercícios à sorte, só com o material que tens",
                           "Random exercises, only with the equipment you have"),
                 action=self._after(lambda: a.push(gs.SurpriseScreen(a, mod)))),
            Item(tr("Carregar treino", "Load workout"),
                 value=tr("{n} treinos", "{n} workouts", n=n) if n else "",
                 detail=tr("a lista de treinos de {m}", "the {m} workout list", m=m.name),
                 action=lambda: self.open_level(f"gymwk:{mod}")),
            Item(tr("Treino livre por blocos", "Free workout in the block builder"),
                 detail=tr("Monta no construtor por blocos e começa; guardar é opcional",
                           "Build it in the block builder and start; saving is optional"),
                 action=self._after(lambda: a.push(gs._builder(a, mod, draft=True)))),
            Item(tr("Do computador", "From the computer"),
                 detail=tr(".csv, .json, .txt ou .fit (de um treino criado, por exemplo, no "
                           "TrainingPeaks)", ".csv, .json, .txt or .fit (of a workout made, for "
                           "example, in TrainingPeaks)"),
                 action=self._after(lambda: self._gym_from_computer(mod)))]
        rows += self._gym_common_rows()
        return m.name, rows

    def _gym_common_rows(self) -> list[Item]:
        return [Item("Challenge", detail=_challenge_help("gym"),
                     action=lambda: self.open_level("challenge"), data="challenge"),
                Item(tr("Testes", "Tests"),
                     detail=tr("força, equilíbrio e mobilidade", "strength, balance and mobility"),
                     action=lambda: self.open_level("tests"), data="tests")]

    def _gym_workouts(self, mod: str) -> tuple[str, list[Item]]:
        from velo.core import gym
        from velo.core import strength as st
        from velo.ui.gym_screens import GymSessionSetup
        a = self.app
        rows = []
        for w in gym.workouts(a.db, mod):
            plan = st.workout_items(a.db, w["id"])
            rows.append(Item(w["name"], value=f"≈ {hms(st.plan_seconds(plan))}",
                             detail=tr("{n} exercícios", "{n} exercises", n=len(plan)),
                             action=self._after(lambda wid=w["id"]: a.push(
                                 GymSessionSetup(a, wid)))))
        if not rows:
            rows = [Item(tr("Ainda não há treinos de {m}", "No {m} workouts yet",
                            m=gym.modality(mod).name),
                         detail=tr("cria um em «+ Novo treino» na Lista de treinos",
                                   "make one with “+ New workout” in the workout list"),
                         enabled=False)]
        return tr("Carregar treino", "Load a workout") + " · " + gym.modality(mod).name, rows

    def _gym_from_computer(self, mod: str) -> None:
        from velo.ui.workout_import import WorkoutFilePopup
        self.app.push(WorkoutFilePopup(self.app, "gym", mode="session", modality=mod))

    def enter(self) -> None:
        sport = sp.name(self.sport)
        if self.level is None:
            items = self.mode_rows()
            self.chrome.set(tr("Sessão de treino", "Training session") + f" · {sport}",
                            tr("Escolhe a modalidade ou o modo", "Pick the modality or the mode")
                            if self.sport == "gym" else
                            tr("Tudo pode ser uma sessão de treino: escolhe o modo",
                               "Anything can be a training session: pick the mode"),
                            tr("↑↓ escolher · Enter abre · Esc cancela",
                               "↑↓ pick · Enter opens · Esc cancels"))
            items.append(Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop))
        else:
            title, items = self._sub(self.level)
            self.chrome.set(f"{title} · {sport}",
                            tr("Escolhe e a janela passa à preparação · Esc volta",
                               "Pick one and the window moves on to the set-up · Esc goes back"),
                            tr("↑↓ escolher · Enter abre · Esc volta", "↑↓ pick · Enter opens · "
                               "Esc goes back"))
            items.append(Item(tr("Voltar", "Back"), button=True,
                              action=lambda: self.open_level(self.parent_of(self.level))))
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.ESCAPE and self.level is not None:
            self.open_level(self.parent_of(self.level))
            return True
        return super().on_key(symbol, modifiers)


def _challenge_help(sport: str) -> str:
    from velo.ui.challenge_screens import challenge_detail
    return challenge_detail(sport)


class GpxPickerPopup(PopupMixin, GpxPicker):
    """O seletor de .gpx numa janela, por cima da preparação da sessão."""

    W, H = 760, 480

    def __init__(self, app, on_pick):
        super().__init__(app, on_pick=on_pick)
        self._init_popup()


class RoutePickerPopup(PopupMixin, Screen):
    """As tuas rotas (.gpx) numa janela: Enter escolhe. «Sem rota» quando a
    rota é opcional. Os .gpx carregam-se só no menu Rotas (ecrã inicial)."""

    W, H = 760, 520

    def __init__(self, app, on_pick, optional: bool = True, current: str | None = None,
                 on_new=None):
        super().__init__(app)
        self.on_pick = on_pick
        self.optional = optional
        self.current = current
        self.on_new = on_new
        self._init_popup()

    def enter(self) -> None:
        a = self.app
        items = []
        if self.optional:
            items.append(Item(tr("Sem rota", "No route"),
                              detail=tr("só o treino; sem estrada", "just the workout; no road"),
                              value="✓" if self.current is None else "",
                              action=lambda: self._choose(None), data=None))
        for r in a.db.routes():
            dv = r["distance_m"] / 1000.0
            bits = [f"↑ {r['ascent_m']:.0f} m", tr("{n} subidas", "{n} climbs",
                                                   n=r["climb_count"])]
            from velo.core import routes as routes_mod
            done = routes_mod.times_done(a.db, r["id"])
            if done["total"]:
                bits.append(routes_mod.times_text(done))
            items.append(Item(("★ " if r["favorite"] else "") + r["name"],
                              value=f"{dv:.1f} km" + ("  ✓" if r["id"] == self.current else ""),
                              detail=" · ".join(bits),
                              action=lambda rid=r["id"]: self._choose(rid), data=r["id"]))
        if not a.db.routes():
            items.append(Item(tr("Ainda não tens rotas", "No routes yet"),
                              detail=tr("carrega um .gpx no menu Rotas (ecrã inicial)",
                                        "load a .gpx in the Routes menu (home screen)"),
                              enabled=False))
        if self.on_new is not None:
            items.append(Item(tr("+ Carregar um .gpx novo", "+ Load a new .gpx"), top=True,
                              action=self._new))
        self.chrome.set(tr("Escolhe a rota", "Pick the route"),
                        tr("{n} rotas · Enter escolhe · Esc volta", "{n} routes · Enter picks · "
                           "Esc goes back", n=len(a.db.routes())), "")
        self.list.set_items(items, keep_index=True)
        if not self.list.select_data(self.current) and self.current is None and self.optional:
            self.list.index = 0
            self.list._sync()

    def _choose(self, route_id: str | None) -> None:
        self.app.pop()
        self.on_pick(route_id)

    def _new(self) -> None:
        self.app.pop()
        self.on_new()


def strava_warning(app, on_proceed, on_cancel, error: str = "") -> ConfirmScreen:
    """O aviso quando o Strava não responde (sem internet, por exemplo)."""
    sub = tr("Sem internet, ou o Strava não respondeu{e}. Podes prosseguir sem os segmentos "
             "(a sessão corre igual) ou cancelar a sessão.",
             "No internet, or Strava did not answer{e}. You can go on without the segments "
             "(the session runs the same) or cancel the session.",
             e=f" ({error[:60]})" if error else "")
    return ConfirmScreen(app, tr("Não foi possível ligar ao Strava", "Could not connect to Strava"),
                         sub, [(tr("Cancelar a sessão", "Cancel the session"), on_cancel),
                               (tr("Prosseguir sem Strava", "Go on without Strava"), on_proceed)],
                         default=1, buttons=True, cancel=on_proceed)


# ------------------------------------------------------------- a janela


class SessionSetup(PopupMixin, AutoLapOptions, Screen):
    """Ver o módulo. `kind`: "free" (livre), "workout", "ftp_test", "chase",
    "game" (Challenge) ou "test" (remo)."""

    W, H = 960, 700
    HTTP = None                 # cliente HTTP do Strava (os testes trocam-no)
    BOT_OPTIONS = (0, 1, 3, 5, 7)
    GHOSTS_SHOWN = 3

    def __init__(self, app, sport: str = "cycling", *, kind: str = "free",
                 route_id: str | None = None, workout_id: str | None = None,
                 ftp_protocol: str | None = None, chase_level: str | None = None,
                 game_key: str | None = None, game_spec: dict | None = None,
                 protocol: str | None = None, title: str | None = None):
        super().__init__(app)
        self.AUTOLAP_SPORT = sport
        self.sport = sport
        self.kind = kind
        # um treino ou um teste: a volta fecha-se em cada bloco (sem auto lap)
        self.structured = bool(workout_id or ftp_protocol or protocol)
        self.workout_id = workout_id
        self.ftp_protocol = ftp_protocol
        self.chase_level = chase_level
        self.protocol = protocol
        self.game_spec = dict(game_spec or {})
        self.title_text = title
        self.route_id = route_id
        if self.route_id is None and self.needs_route:
            rows = app.db.routes()
            self.route_id = rows[0]["id"] if rows else None
        self.new_route: str | None = None
        self.comparison = False
        self.ghosts: set[str] = set()
        meta = wm.get(app.db, sport, workout_id) if workout_id else None
        self.control = meta["control"] if meta else None
        self.erg = (self.control == "erg") if meta else True
        self.speed_kmh = 10.0
        # Challenge do ciclismo
        self.game_key = game_key
        self.game_cls = None
        if game_key:
            from velo.core import games as games_mod
            self.game_cls = games_mod.CLASSES[game_key]
            self.minutes = self.game_cls.default_minutes
            self.bots = 1 if game_key == "tug" else (5 if game_key == "elimination" else 4)
            self.erg = self.game_cls.erg_default        # sem linha de ERG: o jogo decide
        # Strava
        self.job = None
        self.strava_note = ""
        self.strava_skipped = False
        self._init_popup()
        self.back_button = None

    # --------------------------------------------------------------- regras

    @property
    def has_route(self) -> bool:
        """Só ciclismo e corrida levam rota (o remo não tem estrada)."""
        return self.sport in ("cycling", "running")

    @property
    def needs_route(self) -> bool:
        """A sessão livre de ciclismo precisa de uma rota; o resto não."""
        return self.sport == "cycling" and self.kind == "free"

    def routes(self) -> list:
        rows = list(self.app.db.routes())
        return rows if self.needs_route else [None] + rows

    def route(self):
        return self.app.db.route(self.route_id) if self.route_id else None

    @property
    def can_start(self) -> bool:
        return not (self.needs_route and self.route_id is None)

    def strava_client(self):
        from velo.io import strava as strava_mod
        return strava_mod.StravaClient(self.app.db, http=self.HTTP)

    # ---------------------------------------------------------------- linhas

    def title(self) -> str:
        if self.title_text:
            return self.title_text
        if self.game_key:
            return t(f"game.{self.game_key}")
        if self.chase_level:
            return f"{t('chase.title')} · {t(f'chase.level.{self.chase_level}')}"
        if self.workout_id:
            name = self._workout_name()
            if name:
                return name
        if self.ftp_protocol:
            return t("menu.ftp_test")
        return tr("Sessão livre", "Free session") + f" · {sp.name(self.sport)}"

    def _workout_name(self) -> str:
        db = self.app.db
        if self.sport == "cycling":
            row = db.workout(self.workout_id)        # também os que não estão na lista
            return row["name"] if row is not None else ""
        if self.sport == "rowing":
            from velo.core import rowing as rw
            w = rw.workout(db, self.workout_id)
        else:
            from velo.core import endurance as en
            w = en.workout(db, self.workout_id)
        return w["name"] if w else ""

    def subtitle(self) -> str:
        if self.game_key:
            return tr("Como se joga: ", "How it works: ") + t(f"game.{self.game_key}.desc")
        if self.workout_id and self.control:
            return tr("Treino {c} · {h}", "{c} workout · {h}", c=wm.control_name(self.control),
                      h=wm.control_help(self.sport, self.control))
        if self.needs_route:
            return tr("Aparelhos, rota (.gpx), modo e auto lap — tudo aqui",
                      "Devices, route (.gpx), mode and auto lap — all here")
        return tr("Prepara a sessão", "Get the session ready")

    def device_item(self) -> Item:
        a = self.app
        if self.sport == "rowing":
            cur = getattr(a, "rower", None)
            return Item(tr("Aparelhos", "Devices"),
                        value=cur.name if cur is not None else tr("nenhuma máquina", "no machine"),
                        detail=tr("Enter emparelha (Domyos 500B, FTMS, simulada)",
                                  "Enter pairs (Domyos 500B, FTMS, simulated)"),
                        action=self._devices, data="devices")
        return Item(tr("Aparelhos", "Devices"), value=a.device_summary(),
                    detail=tr("Enter abre o emparelhamento (rolo, FC, cadência…)",
                              "Enter opens pairing (trainer, HR, cadence…)"),
                    action=self._devices, data="devices")

    def route_items(self) -> list[Item]:
        if not self.has_route:
            return []
        r = self.route()
        if r is not None:
            value = f"{r['name']} · {r['distance_m'] / 1000:.1f} km"
        elif self.needs_route:
            value = tr("nenhuma — escolhe uma", "none — pick one")
        else:
            value = tr("sem rota", "no route")
        detail = tr("Enter abre a lista das tuas rotas (carregam-se no menu Rotas)",
                    "Enter opens the list of your routes (loaded in the Routes menu)")
        if self.needs_route:
            detail += tr(" · a sessão livre precisa de uma rota", " · a free session needs a route")
        elif self.sport == "running":
            detail += tr(" · a inclinação da rota aparece na sessão",
                         " · the route's gradient shows in the session")
        else:
            detail += tr(" · opcional: no treino a estrada é paisagem",
                         " · optional: in a workout the road is scenery")
        rows = [Item(tr("Rota (.gpx)", "Route (.gpx)"), value=value, detail=detail, data="route",
                     action=self._pick_route)]
        if self.route_id is not None:
            from velo.core import segments as seg_mod
            mine = seg_mod.load(self.app.db, self.route_id, sources=("perennia",))
            if mine:
                rows.append(Item(tr("Segmentos da Perennia", "Perennia segments"),
                                 value=str(len(mine)),
                                 detail=tr("entram sozinhos na sessão (menu Segmentos)",
                                           "they join the session by themselves (Segments "
                                           "menu)"), enabled=False, data="perennia_segments"))
        if self.sport == "cycling":
            rows.append(self.strava_item())
        return rows

    def strava_item(self) -> Item:
        from velo.core import segments as seg_mod
        segs = seg_mod.load(self.app.db, self.route_id, sources=("strava",)) \
            if self.route_id else []
        busy = self.job is not None and not self.job.done
        label = tr("Segmentos do Strava", "Strava segments")
        if self.route_id is None:
            return Item(label, detail=tr("escolhe primeiro uma rota", "pick a route first"),
                        enabled=False, data="strava")
        connected = self.strava_client().connected
        if busy:
            value, detail = tr("a procurar…", "searching…"), tr("pode demorar uns segundos",
                                                               "may take a few seconds")
        elif segs:
            value = tr("{n} segmentos", "{n} segments", n=len(segs))
            detail = " · ".join(s.name for s in segs[:3]) + (" …" if len(segs) > 3 else "")
            if connected:
                detail += tr(" · Enter atualiza", " · Enter refreshes")
        elif self.strava_skipped:
            value, detail = tr("sem ligação", "no connection"), tr(
                "segue sem segmentos · Enter tenta outra vez", "going without segments · "
                "Enter tries again")
        elif not connected:
            value, detail = "", tr("liga o Strava em Definições → Ligações Externas",
                                   "connect Strava in Settings → External connections")
        else:
            value = tr("procurar", "search") if self.new_route == self.route_id else \
                tr("nenhum", "none")
            detail = tr("Enter procura os segmentos desta rota e os teus PR",
                        "Enter finds this route's segments and your PRs")
        return Item(label, value=value, detail=detail, data="strava",
                    action=self._fetch_strava, enabled=connected and not busy)

    def mode_items(self) -> list[Item]:
        if self.sport != "cycling" or self.kind not in ("free", "workout"):
            return []
        rows = [Item(t("mode.title"),
                     value=t("mode.comparison") if self.comparison else t("mode.alone"),
                     detail=tr("←/→ muda · comparação: contra as tuas sessões nesta rota",
                               "←/→ changes · comparison: against your rides on this route"),
                     data="mode")]
        if self.comparison:
            past = self.app.db.rides(self.route_id) if self.route_id else []
            if not past:
                rows.append(Item(tr("Sem sessões anteriores nesta rota",
                                    "No earlier rides on this route"), enabled=False))
            for r in past[:self.GHOSTS_SHOWN]:
                chosen = r["id"] in self.ghosts
                rows.append(Item(("✓ " if chosen else "   ") +
                                 str(r["started_at"])[:16].replace("T", " "),
                                 value=hms(r["elapsed_s"] or 0),
                                 detail=(f"{r['avg_power_w']:.0f} W" if r["avg_power_w"]
                                         else "") + tr(" · Enter escolhe", " · Enter picks"),
                                 action=lambda rid=r["id"]: self._toggle_ghost(rid)))
        return rows

    def option_items(self) -> list[Item]:
        rows = []
        if self.sport == "cycling" and self.workout_id and self.control == "erg":
            rows.append(Item(t("mode.erg"), value=t("common.on") if self.erg else t("common.off"),
                             detail=tr("←/→ · ligado: o rolo põe os watts de cada bloco",
                                       "←/→ · on: the trainer sets each block's watts"),
                             data="erg"))
        elif self.workout_id and self.control == "manual":
            rows.append(Item(tr("Tipo do treino", "Workout kind"), value=tr("Manual", "Manual"),
                             detail=wm.control_help(self.sport, "manual"), enabled=False))
        if self.game_cls is not None:
            if self.game_cls.has_duration:
                rows.append(Item(tr("Duração", "Duration"), value=f"{self.minutes} min",
                                 detail=tr("←/→ muda", "←/→ changes"), data="minutes"))
            if self.game_cls.has_bots and self.game_key != "tug":
                rows.append(Item(tr("Adversários (bots)", "Opponents (bots)"),
                                 value=str(self.bots), detail=tr("←/→ muda", "←/→ changes"),
                                 data="bots"))
        if self.sport == "running":
            rows.append(Item(tr("Velocidade inicial da passadeira", "Treadmill start speed"),
                             value=f"{self.speed_kmh:.1f} km/h",
                             detail=tr("←/→ ±0,5 · na sessão: + / −",
                                       "←/→ ±0.5 · in session: + / −"), data="speed"))
        return rows

    def buttons(self) -> list[Item]:
        start = Item(t("mode.start"), action=self._start, button=True, primary=True,
                     enabled=self.can_start)
        return [Item(tr("Cancelar", "Cancel"), action=self.app.pop, button=True), start]

    def enter(self) -> None:
        items = [self.device_item()] + self.route_items() + self.mode_items() \
            + self.option_items() + self.autolap_items()
        foot = tr("←/→ muda · Enter abre · Esc cancela", "←/→ changes · Enter opens · Esc cancels")
        if not self.can_start:
            foot = tr("Falta a rota: carrega um .gpx", "Missing the route: load a .gpx")
        self.chrome.set(self.title(), self.subtitle(), foot)
        self.list.set_items(items + self.buttons(), keep_index=True)

    # ---------------------------------------------------------------- teclas

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.autolap_key(symbol):
            return True
        item = self.list.selected
        if item is not None and symbol in (key.LEFT, key.RIGHT) and isinstance(item.data, str):
            step = 1 if symbol == key.RIGHT else -1
            if self.adjust(item.data, step):
                self.enter()
                return True
        if symbol == key.ESCAPE:
            self.app.pop()
            return True
        return super().on_key(symbol, modifiers)

    def adjust(self, field: str, step: int) -> bool:
        if field == "route":
            rs = self.routes()
            if not rs:
                return True
            ids = [r["id"] if r is not None else None for r in rs]
            i = ids.index(self.route_id) if self.route_id in ids else 0
            self.route_id = ids[(i + step) % len(ids)]
            self.ghosts.clear()
            self.strava_skipped = False
        elif field == "mode":
            self.comparison = not self.comparison
            if not self.comparison:
                self.ghosts.clear()
        elif field == "erg":
            self.erg = not self.erg
        elif field == "minutes":
            ds = list(self.game_cls.durations)
            i = ds.index(self.minutes) if self.minutes in ds else 0
            self.minutes = ds[(i + step) % len(ds)]
        elif field == "bots":
            bs = list(self.BOT_OPTIONS)
            i = bs.index(self.bots) if self.bots in bs else 0
            self.bots = bs[(i + step) % len(bs)]
        elif field == "speed":
            self.speed_kmh = max(0.0, min(25.0, self.speed_kmh + 0.5 * step))
        else:
            return False
        return True

    def _toggle_ghost(self, ride_id: str) -> None:
        self.ghosts.symmetric_difference_update({ride_id})
        self.enter()

    # ---------------------------------------------------------------- ações

    def _devices(self) -> None:
        self.app.open_devices()         # o mesmo popup nos três desportos (a máquina de remo também)

    def _new_gpx(self) -> None:
        self.app.push(GpxPickerPopup(self.app, self._picked))

    def _pick_route(self) -> None:
        """A lista das rotas numa janela — escolhe-se ali, sem andar às setas."""
        self.app.push(RoutePickerPopup(self.app, self._route_chosen,
                                       optional=not self.needs_route, current=self.route_id))

    def _route_chosen(self, route_id: str | None) -> None:
        if route_id != self.route_id:
            self.route_id = route_id
            self.ghosts.clear()
            self.strava_skipped = False
        self.enter()

    def _picked(self, route_id: str) -> None:
        self.route_id = self.new_route = route_id
        self.strava_skipped = False
        self.enter()

    def _fetch_strava(self) -> None:
        if self.route_id is None or (self.job is not None and not self.job.done):
            return
        from velo.core import segments as seg_mod
        from velo.ui.connect_screens import Job
        db, rid, client = self.app.db, self.route_id, self.strava_client()
        self.job = Job(lambda: seg_mod.fetch_for_route(db, client, rid))
        self.enter()

    def update(self, dt: float) -> None:
        j = self.job
        if j is None or not j.done:
            return
        self.job = None
        if j.error:
            self.app.push(strava_warning(self.app, self._go_without_strava, self._cancel_all,
                                         j.error))
        else:
            r = j.result or {}
            self.strava_skipped = False
            self.app.message(tr("{m} segmentos do Strava nesta rota",
                                "{m} Strava segments on this route", m=r.get("matched", 0)))
        self.enter()

    def _go_without_strava(self) -> None:
        self.app.pop()                          # o aviso
        self.strava_skipped = True
        self.enter()

    def _cancel_all(self) -> None:
        self.app.pop()                          # o aviso
        if self.app.current is self:
            self.app.pop()                      # e a preparação

    # ---------------------------------------------------------------- começar

    def ride_kind(self) -> str:
        return {"free": "route"}.get(self.kind, self.kind)

    def game(self) -> dict:
        return {"key": self.game_key, "minutes": self.minutes, "bots": self.bots,
                "erg": self.erg, "seed": int(time.time()) % 100000}

    def _start(self) -> None:
        a = self.app
        if not self.can_start:
            a.message(tr("Escolhe uma rota ou carrega um .gpx.", "Pick a route or load a .gpx."))
            return
        autolap = dict(self.autolap_cfg())
        if self.sport == "cycling":
            a.replace(RideScreen(
                a, route_id=self.route_id, workout_id=self.workout_id, kind=self.ride_kind(),
                ghosts=sorted(self.ghosts), erg=self.erg, ftp_protocol=self.ftp_protocol,
                chase_level=self.chase_level, autolap=autolap,
                game_spec=self.game() if self.game_key else None))
        elif self.sport == "running":
            from velo.ui.endurance_screens import EnduranceSession
            a.replace(EnduranceSession(a, "running", workout_id=self.workout_id, autolap=autolap,
                                       speed_kmh=self.speed_kmh, route_id=self.route_id))
        elif self.sport == "rowing":
            if getattr(a, "rower", None) is None:
                a.message(tr("Liga primeiro a máquina de remo (Aparelhos).",
                             "Connect the rowing machine first (Devices)."))
                self._devices()
                return
            from velo.ui.rowing_screens import RowingSessionScreen
            a.replace(RowingSessionScreen(a, workout_id=self.workout_id, protocol=self.protocol,
                                          game_spec=self.game_spec or None, autolap=autolap))


class GameSetup(SessionSetup):
    """O Challenge do ciclismo (desafio adaptativo, jogos): o nome e «como se
    joga» em cima; depois a duração, os bots, a rota e o auto lap. Sem ERG:
    cada jogo sabe se o usa."""

    def __init__(self, app, game_key: str):
        super().__init__(app, "cycling", kind="game", game_key=game_key)
        self.key = game_key
        self.cls = self.game_cls

    def spec(self) -> dict:
        return self.game()

    def side_board(self):
        from velo.core import games as games_mod
        return games_mod.leaderboard(self.app.db, self.key)
