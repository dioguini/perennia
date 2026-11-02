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
    """«Sessão de treino»: Livre ou Carregar treino."""
    def free() -> None:
        app.pop()
        app.push(SessionSetup(app, sport, kind="free"))

    def load() -> None:
        app.pop()
        if hub is not None:
            hub.tab_named(tr("Lista de treinos", "Workouts"))
    sub = {"cycling": tr("Livre: escolhes os aparelhos e a rota (.gpx). Carregar treino: abre a "
                         "lista de treinos.", "Free: pick the devices and the route (.gpx). "
                         "Load workout: opens the workout list."),
           "running": tr("Livre: passadeira, com ou sem rota (.gpx). Carregar treino: abre a "
                         "lista de treinos.", "Free: treadmill, with or without a route (.gpx). "
                         "Load workout: opens the workout list."),
           "rowing": tr("Livre: remo sem plano, com voltas. Carregar treino: abre a lista de "
                        "treinos.", "Free: row with no plan, with laps. Load workout: opens "
                        "the workout list.")}.get(sport, "")
    app.push(ConfirmScreen(app, tr("Sessão de treino", "Training session") + f" · {sp.name(sport)}",
                           sub, [(tr("Cancelar", "Cancel"), app.pop),
                                 (tr("Carregar treino", "Load workout"), load),
                                 (tr("Livre", "Free"), free)],
                           default=2, buttons=True, cancel=app.pop))


class GpxPickerPopup(PopupMixin, GpxPicker):
    """O seletor de .gpx numa janela, por cima da preparação da sessão."""

    W, H = 760, 480

    def __init__(self, app, on_pick):
        super().__init__(app, on_pick=on_pick)
        self._init_popup()


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

    W, H = 820, 600
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
            return next((w["name"] for w in db.workouts() if w["id"] == self.workout_id), "")
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
            value = tr("nenhuma — carrega um .gpx", "none — load a .gpx")
        else:
            value = tr("sem rota", "no route")
        detail = tr("←/→ outra das tuas rotas", "←/→ another of your routes")
        if self.needs_route:
            detail += tr(" · a sessão livre precisa de uma rota", " · a free session needs a route")
        elif self.sport == "running":
            detail += tr(" · a inclinação da rota aparece na sessão",
                         " · the route's gradient shows in the session")
        else:
            detail += tr(" · opcional: no treino a estrada é paisagem",
                         " · optional: in a workout the road is scenery")
        rows = [Item(tr("Rota (.gpx)", "Route (.gpx)"), value=value, detail=detail, data="route"),
                Item(tr("Carregar um .gpx novo", "Load a new .gpx"),
                     detail=tr("procura nas pastas gpx, Transferências e Documentos",
                               "looks in the gpx, Downloads and Documents folders"),
                     action=self._new_gpx, data="new_gpx")]
        if self.sport == "cycling":
            rows.append(self.strava_item())
        return rows

    def strava_item(self) -> Item:
        from velo.core import segments as seg_mod
        segs = seg_mod.load(self.app.db, self.route_id) if self.route_id else []
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
        a = self.app
        if self.sport == "rowing":
            from velo.ui.rowing_screens import RowerDeviceScreen
            a.push(RowerDeviceScreen(a))
        else:
            a.open_devices()

    def _new_gpx(self) -> None:
        self.app.push(GpxPickerPopup(self.app, self._picked))

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
