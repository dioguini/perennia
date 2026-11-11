"""Corrida e natação: menu por separadores, sessão, resumo e histórico."""
from __future__ import annotations

import time

import pyglet
from pyglet.window import key

from perennia.core import endurance as en
from perennia.core import intensity as it
from perennia.core import sports as sp
from perennia.core.i18n import t, tr
from perennia.core.units import hms
from perennia.gfx.compat import label as make_label
from perennia.ui.app import Screen, SportHub, StartOptions
from perennia.ui.brief import BriefScreen, endurance_brief
from perennia.ui.session_flow import FinishFlow
from perennia.ui.session_radar import RadarSide
from perennia.ui.session_panels import OFF, ArrangedPanels
from perennia.ui.widgets import (ACCENT, DIM, GOOD, HEADER, HEADER_TEXT, PANEL, TEXT, CountdownBadge,
                             Item, LapPanel)


def _m(v) -> str:
    if not v:
        return "—"
    return f"{v / 1000:.2f} km" if v >= 1000 else f"{v:.0f} m"


def pace_unit(sport: str) -> str:
    return "/km" if sport == "running" else "/100 m"


def start(app, sport: str, workout_id: str | None = None, replace: bool = False) -> None:
    """Abre a preparação da sessão. Corrida: a janela da sessão (aparelhos,
    rota .gpx opcional, velocidade, auto lap). Natação: piscina e auto lap."""
    if sport == "running":
        from perennia.ui.session_setup import SessionSetup
        app.push(SessionSetup(app, "running", kind="workout" if workout_id else "free",
                              workout_id=workout_id))
        return
    title = sp.name(sport)
    if workout_id:
        w = en.workout(app.db, workout_id)
        title = w["name"] if w else title
    opts = {"pool_m": 25.0} if sport == "swimming" else {"speed_kmh": 10.0}

    def go(autolap: dict, o: dict) -> None:
        app.replace(EnduranceSession(app, sport, workout_id=workout_id, autolap=autolap,
                                     pool_m=o.get("pool_m", 25.0),
                                     speed_kmh=o.get("speed_kmh", 10.0)))
    lines = [tr("Passadeira: + / − mudam a velocidade; T escreve o total do visor.",
                "Treadmill: + / − change the speed; T types the display total.")] \
        if sport == "running" else [tr("Na piscina: + conta uma piscina (− corrige).",
                                       "In the pool: + counts a length (− corrects).")]
    scr = StartOptions(app, sport, title, go, lines=lines, options=opts,
                       structured=bool(workout_id))
    app.replace(scr) if replace else app.push(scr)


class EnduranceHub(SportHub):
    def __init__(self, app, sport: str):
        self.SPORT = sport
        super().__init__(app)

    def items_train(self) -> list[Item]:
        from perennia.ui.challenge_screens import train_items
        a = self.app
        free = tr("Corrida livre", "Free run") if self.SPORT == "running" else \
            tr("Natação livre", "Free swim")
        if self.SPORT == "swimming":
            return train_items(a, self.SPORT, None)
        return train_items(a, self.SPORT, Item(
            tr("Sessão de treino", "Training session"),
            detail=free + tr(" ou carregar um treino · com ou sem rota (.gpx)",
                             " or load a workout · with or without a route (.gpx)"),
            action=lambda: self._ask()))

    def _ask(self) -> None:
        from perennia.ui.session_setup import ask_start
        ask_start(self.app, self.SPORT, self)

    def _dur(self, w: dict) -> str:
        return " + ".join(x for x in (hms(w["total_s"]) if w["total_s"] else "",
                                      _m(w["total_m"]) if w["total_m"] else "") if x)

    def items_library(self) -> list[Item]:
        a = self.app
        from perennia.ui.workout_import import import_item
        return [import_item(a, self.SPORT, on_done=lambda _w: self.enter())] + [
            Item(w["name"], value=self._dur(w), detail=w["description"] or "",
                 action=lambda wid=w["id"]: a.push(EndurancePreview(a, self.SPORT, wid)),
                 data=("endurance_workout", w["id"]))
            for w in en.workouts(a.db, self.SPORT)]

    def items_history(self) -> list[Item]:
        a = self.app
        return [Item(f"{str(s['started_at'])[:16].replace('T', ' ')}  {_pretty(s['name'])}",
                     value=_m(s["distance_m"]),
                     detail=f"{hms(s['moving_s'] or 0)} · "
                            f"{hms(s['avg_pace_s']) if s['avg_pace_s'] else '—'} "
                            f"{pace_unit(self.SPORT)}"
                            + (f" · {s['avg_hr']:.0f} bpm" if s["avg_hr"] else ""),
                     action=lambda sid=s["id"]: a.push(EnduranceDetail(a, sid)))
                for s in en.sessions(a.db, self.SPORT)] + _synced(a, self.SPORT)

    def items_stats(self) -> list[Item]:
        return super().items_stats() + record_items(self.app, self.SPORT)


def record_items(app, sport: str) -> list[Item]:
    """Os recordes da corrida ou da natação, com a sessão de cada um."""
    a = app
    ss = en.sessions(a.db, sport, 1000)
    dist = sum(s["distance_m"] or 0 for s in ss)
    hours = sum(s["moving_s"] or 0 for s in ss) / 3600

    def record(label: str, pick, value) -> Item:
        """O recorde e a sessão onde foi feito (Enter abre-a)."""
        cands = [s for s in ss if pick(s) is not None]
        if not cands:
            return Item(label, value="—", enabled=False)
        s = min(cands, key=pick)
        return Item(label, value=value(s),
                    detail=tr("em {d} · {n}", "on {d} · {n}",
                              d=str(s["started_at"])[:16].replace("T", " "),
                              n=_pretty(s["name"]) or sp.name(sport)),
                    action=lambda sid=s["id"]: a.push(EnduranceDetail(a, sid)))
    unit = " " + pace_unit(sport)
    extra = []
    if sport == "running":
        from perennia.ui.evolution_screens import EvolutionScreen
        extra = [Item(tr("Métricas de evolução da corrida", "Running progress metrics"),
                      value="›", detail=tr("Eficiência, desacoplamento, durabilidade, previsões "
                                           "e zonas de ritmo", "Efficiency, decoupling, "
                                           "durability, predictions and pace zones"),
                      action=lambda: a.push(EvolutionScreen(a, tab=1)))]
    return extra + [
        Item(tr("Sessões", "Sessions"), value=str(len(ss)), enabled=False),
        Item(tr("Distância total", "Total distance"), value=_m(dist), enabled=False),
        Item(tr("Horas", "Hours"), value=f"{hours:.1f}", enabled=False),
        record(tr("Melhor ritmo médio", "Best avg pace"),
               lambda s: s["avg_pace_s"] or None, lambda s: hms(s["avg_pace_s"]) + unit),
        record(tr("Maior distância", "Longest"),
               lambda s: -(s["distance_m"] or 0) or None, lambda s: _m(s["distance_m"])),
        record(tr("Sessão mais longa", "Longest session"),
               lambda s: -(s["moving_s"] or 0) or None, lambda s: hms(s["moving_s"] or 0)),
        record(tr("FC média mais alta", "Highest avg HR"),
               lambda s: -(s["avg_hr"] or 0) or None, lambda s: f"{s['avg_hr']:.0f} bpm")]


def _health():
    from perennia.ui import health_screens
    return health_screens


def _synced(app, sport: str) -> list[Item]:
    from perennia.ui.sync_screens import history_items
    return history_items(app, sport)


class EndurancePreview(BriefScreen):
    """O treino antes de começar: objetivo, blocos e alvos (ver perennia.ui.brief)."""

    def __init__(self, app, sport: str, wid: str):
        self.SPORT, self.sport = sport, sport
        self.CAN_START = sport != "swimming"       # a natação não tem sessão de treino
        super().__init__(app, wid)

    def make_brief(self):
        return endurance_brief(self.app.db, self.sport, self.wid)

    def start(self) -> None:
        start(self.app, self.sport, self.wid, replace=self.sport != "running")



class RunControls:
    """Corrida livre: **velocidade** e **inclinação** ao meio do ecrã, em dois cartões, cada um
    com − valor +. A velocidade muda de 0,1 em 0,1 km/h e a inclinação de 0,5 em 0,5 % (o passo
    das Definições → Desportos → Corrida). O que escolhes fica registado ao segundo e vê-se na
    análise da sessão."""

    W, H, GAP = 430, 170, 24

    def __init__(self, batch):
        self.cards = []
        for kind in ("speed", "incline"):
            outline = pyglet.shapes.Rectangle(0, 0, 10, 10, color=P_BORDER(), batch=batch)
            bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=batch)
            title = make_label("", font_size=12, bold=True, color=DIM, anchor_x="center",
                               anchor_y="top", batch=batch)
            value = make_label("", font_size=32, bold=True, color=TEXT, anchor_x="center",
                               anchor_y="center", batch=batch)
            hint = make_label("", font_size=11, color=DIM, anchor_x="center",
                              anchor_y="bottom", batch=batch)
            btns = []
            for sign in ("−", "+"):
                bb = pyglet.shapes.Rectangle(0, 0, 10, 10, color=HEADER[:3], batch=batch)
                bl = make_label(sign, font_size=30, bold=True, color=HEADER_TEXT,
                                anchor_x="center", anchor_y="center", batch=batch)
                btns.append((bb, bl))
            self.cards.append({"kind": kind, "outline": outline, "bg": bg, "title": title,
                               "value": value, "hint": hint, "btns": btns, "rects": {}})
        self.visible = False

    def layout(self, cx: float, cy: float) -> None:
        total = 2 * self.W + self.GAP
        left = cx - total / 2
        bottom = cy - self.H / 2
        for i, c in enumerate(self.cards):
            x = left + i * (self.W + self.GAP)
            c["outline"].x, c["outline"].y = x - 1, bottom - 1
            c["outline"].width, c["outline"].height = self.W + 2, self.H + 2
            c["bg"].x, c["bg"].y, c["bg"].width, c["bg"].height = x, bottom, self.W, self.H
            c["title"].x, c["title"].y = x + self.W / 2, bottom + self.H - 12
            c["value"].x, c["value"].y = x + self.W / 2, bottom + self.H / 2 + 2
            c["hint"].x, c["hint"].y = x + self.W / 2, bottom + 8
            by = bottom + self.H / 2 - 32
            for j, (bb, bl) in enumerate(c["btns"]):
                bx = x + 14 if j == 0 else x + self.W - 14 - 64
                bb.x, bb.y, bb.width, bb.height = bx, by, 64, 64
                bl.x, bl.y = bx + 32, by + 32
                c["rects"]["-" if j == 0 else "+"] = (bx, by, 64, 64)

    def set(self, speed_kmh: float, incline_pct: float, incline_step: float) -> None:
        self.cards[0]["title"].text = tr("VELOCIDADE", "SPEED")
        self.cards[0]["value"].text = f"{speed_kmh:.1f} km/h"
        self.cards[0]["hint"].text = tr("passo 0,1 km/h · + / −", "step 0.1 km/h · + / −")
        self.cards[1]["title"].text = tr("INCLINAÇÃO", "INCLINE")
        self.cards[1]["value"].text = f"{incline_pct:.1f} %"
        self.cards[1]["hint"].text = tr(f"passo {incline_step:g} % · ↑ / ↓".replace(".", ","),
                                        f"step {incline_step:g} % · ↑ / ↓")

    def hit(self, x: float, y: float) -> tuple[str, int] | None:
        """(«speed» ou «incline», ±1) se o clique foi num botão."""
        if not self.visible:
            return None
        for c in self.cards:
            for sign, (bx, by, bw, bh) in c["rects"].items():
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    return c["kind"], (1 if sign == "+" else -1)
        return None

    def show(self, on: bool) -> None:
        self.visible = on
        for c in self.cards:
            for r in (c["outline"], c["bg"]):
                r.opacity = 255 if on else 0
            for bb, bl in c["btns"]:
                bb.opacity = 255 if on else 0
                bl.opacity = 255 if on else 0
            if not on:
                for k in ("title", "value", "hint"):
                    c[k].text = ""


def P_BORDER():
    from perennia.gfx import theme
    return theme.P.border[:3]


class EnduranceSession(FinishFlow, ArrangedPanels, Screen):
    KEY_SCOPE = "endurance"
    AGENT = False
    IN_SESSION = True

    def __init__(self, app, sport: str, workout_id: str | None = None,
                 autolap: dict | None = None, pool_m: float = 25.0, speed_kmh: float = 10.0,
                 resume: dict | None = None, route_id: str | None = None):
        super().__init__(app)
        cfg = (resume or {}).get("config", {})
        # corrida com uma rota (.gpx): segue-se a distância e mostra-se a
        # inclinação da estrada nesse ponto, para pôr na passadeira
        route_id = route_id or cfg.get("route_id")
        self.route_id = route_id
        self.route_name = ""
        self.route_pts: list = []
        # os segmentos da rota (Perennia e Strava): começam e acabam sozinhos
        self.segments = None
        self._route_d = 0.0
        if route_id:
            row = app.db.route(route_id)
            self.route_name = row["name"] if row else ""
            self.route_pts = app.db.route_points(route_id)
            from perennia.core import segments as seg_mod
            try:
                segs = seg_mod.load(app.db, route_id)
            except Exception:
                segs = []
            self.segments = seg_mod.SegmentTracker(segs) if segs else None
        self.engine = en.EnduranceEngine(
            app.db, app.db.athlete(), cfg.get("sport", sport), sensors=app.hub,
            workout_id=workout_id or cfg.get("workout_id"),
            autolap=autolap if resume is None else cfg.get("autolap"),
            pool_m=cfg.get("pool_m", pool_m), out_dir=app.data_dir / "endurance", resume=resume,
            route_id=route_id)
        if self.engine.sport == "running" and getattr(app, "treadmill", None) is not None:
            self.engine.treadmill = app.treadmill       # a passadeira simulada ou real
        if resume is None and self.engine.sport == "running":
            self.engine.set_speed(speed_kmh)
        self.session = self.engine
        self.start_countdown(resume)          # 15 s e começa sozinha
        self.init_finish()                    # o diálogo de terminar, como no ciclismo
        self.typing: str | None = None
        self.toast = ""
        self._toast_until = 0.0
        b = self.batch = pyglet.graphics.Batch()
        self.clock = CountdownBadge(app.window, batch=b)   # só os últimos segundos de um bloco
        self.controls = RunControls(b)       # corrida livre: velocidade e inclinação
        self.controls.show(False)
        self.cells = []
        from perennia.core import layouts as _lay
        for _ in range(max(1, len(_lay.keys(app.db, self.engine.sport)))):    # nº de métricas
            bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
            cap = make_label("", font_size=10, color=DIM, anchor_y="top", batch=b)
            val = make_label("", font_size=26, bold=True, color=TEXT, anchor_y="top", batch=b)
            self.cells.append((bg, cap, val))
        self.status = make_label("", font_size=15, bold=True, color=ACCENT, anchor_y="top",
                                 batch=b)
        self.plan = make_label("", font_size=13, color=TEXT, anchor_y="top", batch=b,
                               multiline=True, width=500)
        self.toast_label = make_label("", font_size=14, bold=True, color=GOOD, anchor_y="top",
                                      batch=b)
        self.laps_panel = LapPanel()        # as voltas: sempre aqui, como no ciclismo
        self.chrome.title.font_size = 18
        # onde fica cada painel: Definições → Ecrã da sessão → Disposição
        self.arr_load(self.engine.sport)
        self._layout()

    def _layout(self) -> None:
        from perennia.core import layouts as _lay
        cols, rows = _lay.grid_for(len(self.cells), self.engine.sport)
        gap = 10
        m = self.arr_rect("metrics")
        if m is not None:
            mx, my, mw, mh = m
            cw = (mw - gap * (cols - 1)) / cols
            ch = max(56.0, min(116.0, (mh - gap * (rows - 1)) / rows))
            top = my + mh
        for i, (bg, cap, val) in enumerate(self.cells):
            if m is None:
                bg.x = cap.x = val.x = OFF
                continue
            r, c = divmod(i, cols)
            x, y = mx + c * (cw + gap), top - r * (ch + gap)
            bg.x, bg.y, bg.width, bg.height = x, y - ch, cw, ch
            cap.x, cap.y = x + 12, y - 8
            val.x, val.y = x + 12, y - 28
        st = self.arr_rect("status")
        if st is not None:
            sx, sy, sw, sh = st
            self.status.x, self.status.y = sx, sy + sh
            self.toast_label.x, self.toast_label.y = sx + min(460, sw * 0.55), sy + sh
            self.plan.x, self.plan.y, self.plan.width = sx, sy + sh - 28, int(sw)
        else:
            self.status.x = self.toast_label.x = self.plan.x = OFF
        lp = self.arr_rect("laps")
        if lp is not None:
            lx, ly, lw, lh = lp
            self.laps_panel.layout(lx, ly + lh, lw, ly)
        else:
            self.laps_panel.layout(OFF, OFF + 400, 200, OFF)
        self.arr_layout_extras()
        self.list.y = -1000
        self.clock.layout()
        # a velocidade e a inclinação, ao meio do ecrã: no meio do espaço livre por baixo dos
        # quadrados (ou, se não houver quadrados, a meio da janela)
        mt = self.arr_rect("metrics")
        low = self.arr_area()[1]
        cy = ((mt[1] + low) / 2 if mt is not None else self.app.window.height / 2)
        cx = (sx + sw / 2) if st is not None else self.app.window.width / 2
        self.controls.layout(cx, cy)
        self._layout_finish()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()

    def footer(self) -> str:
        e = self.engine
        if e.sport == "running":
            if not e.manual_laps:
                return tr("Espaço começa · +/− velocidade · P pausa · F10 terminar e guardar",
                          "Space starts · +/− speed · P pause · F10 stop and save")
            return tr("Espaço começa · +/− velocidade (0,1) · ↑/↓ inclinação (0,5) · T total do "
                      "visor · L volta · P pausa · F10 terminar e guardar",
                      "Space starts · +/− speed (0.1) · ↑/↓ incline (0.5) · T display total · "
                      "L lap · P pause · F10 stop and save")
        return tr("Espaço começa · + piscina (− corrige) · L volta · P pausa · "
                  "F10 terminar e guardar", "Space starts · + length (− corrects) · L lap · "
                  "P pause · F10 stop and save")

    def enter(self) -> None:
        e = self.engine
        self.list.y = -1000
        self.refresh_buttons(force=True)                  # − + Pausa Terminar, em baixo
        self.chrome.set(e.title, "", self.footer())

    def cells_data(self) -> list[tuple[str, str]]:
        """Os 8 quadrados, pela ordem escolhida no editor do ecrã (Definições)."""
        from perennia.core import layouts
        if getattr(self, "_layout_keys", None) is None:
            self._layout_keys = layouts.keys(self.app.db, self.engine.sport)
        out = []
        for k in self._layout_keys[:len(self.cells)]:
            if k is None:
                out.append(("", ""))
            else:
                out.append((layouts.label(self.engine.sport, k), self.metric_value(k)))
        return out

    def metric_value(self, k: str) -> str:
        e = self.engine
        unit = pace_unit(e.sport)
        if k == "distance":
            return _m(e.distance_m)
        if k == "time":
            return hms(e.t)
        if k == "avg_pace":
            return (hms(e.avg_pace_s) + unit) if e.avg_pace_s else "—"
        if k == "cur_pace":
            cur = 3600 / e.speed_kmh if e.sport == "running" and e.speed_kmh else None
            return (hms(cur) + unit) if cur else "—"
        if k == "speed":
            return f"{e.speed_kmh:.1f} km/h"
        if k == "hr":
            return str(e.hr_bpm) if e.hr_bpm else "—"
        if k == "hr_zone":
            return f"Z{e.hr_zone}" if e.hr_zone else "—"
        if k == "avg_hr":
            return f"{e.avg_hr:.0f}" if e.avg_hr else "—"
        if k == "max_hr":
            hrs = [h for h in getattr(e, "_hrs", []) if h]
            return f"{max(hrs):.0f}" if hrs else "—"
        if k == "lap":
            return f"{_m(e.lap_distance_m)} · {hms(e.lap_elapsed_s)}"
        if k == "lap_time":
            return hms(e.lap_elapsed_s)
        if k == "lap_dist":
            return _m(e.lap_distance_m)
        if k == "lap_pace":
            lp = e.pace_s(e.lap_elapsed_s, e.lap_distance_m)
            return (hms(lp) + unit) if lp else "—"
        if k == "lengths":
            return f"{e.lengths} × {e.pool_m:g} m"
        if k == "step_left":
            return e.workout.remaining_text() if e.workout is not None and \
                e.workout.step is not None else "—"
        if k == "target":
            return e.target_text() if e.workout is not None and e.workout.step is not None \
                else "—"
        if k == "load":
            if int(e.t) % 5 == 0 or getattr(self, "_load_txt", None) is None:
                v = e.summary().get("load")      # leve: só de 5 em 5 s
                self._load_txt = f"{v:.0f}" if v else "—"
            return self._load_txt
        return "—"

    def update(self, dt: float) -> None:
        a = self.app
        a.hub.tick(dt)
        e = self.engine
        e.update(dt)
        for kind, data in e.drain_events():
            self._event(kind, data)
        from perennia.ui.session_flow import workout_step_cues
        self.clock.alert(workout_step_cues(self, e.workout) if e.started else None)
        self.clock.set(e.t, tr("volta {t}", "lap {t}", t=hms(e.lap_elapsed_s)) + (
            f" · {tr('passo', 'step')} {e.workout.remaining_text()}"
            if e.workout is not None and e.workout.step is not None else ""))
        keys = getattr(self, "_layout_keys", None) or []
        for i, ((bg, cap, val), (c, v)) in enumerate(zip(self.cells, self.cells_data())):
            cap.text, val.text = c.upper(), v
            if i < len(keys) and keys[i] == "hr_zone" and e.hr_zone:
                from perennia.gfx import theme
                from perennia.gfx.hud import zone_color
                val.color = theme.ink(zone_color(e.hr_zone, "hr"))
            else:
                val.color = TEXT
            # o valor tem de caber no quadrado (≈ 0,62 da letra por carácter)
            size = 26
            while size > 12 and len(v) * size * 0.66 > bg.width - 20:
                size -= 2
            val.font_size = size
        self.refresh_buttons()
        free_run = e.sport == "running" and e.workout is None
        if free_run != self.controls.visible:
            self.controls.show(free_run)
        if free_run:
            from perennia.core import workout_meta as wm
            self.controls.set(e.speed_kmh, e.incline_pct,
                              wm.device_limits(self.app.db)["treadmill_incline_step"])
        status = {"waiting": tr("ESPAÇO PARA COMEÇAR", "SPACE TO START"),
                  "paused": tr("EM PAUSA (P)", "PAUSED (P)")}.get(e.status, "")
        if self.typing is not None:
            status = tr("TOTAL DO VISOR: {v} km (Enter)", "DISPLAY TOTAL: {v} km (Enter)",
                        v=self.typing or "_")
        self.status.text = status or self._plan_title()
        self.plan.text = self._plan_text()
        if self.toast and time.monotonic() > self._toast_until:
            self.toast = ""
        self.toast_label.text = self.toast
        title, cells, prev = self.lap_data()
        self.laps_panel.set(title, cells, prev, tr("VOLTAS FEITAS", "LAPS DONE"))
        self.laps_panel.update(time.monotonic())
        if e.started:
            self.arr_sample(dt, e.hr_bpm, e.speed_kmh if e.sport == "running" else None,
                            e.hr_zone_s)
            self._track_segments()

    def _track_segments(self) -> None:
        """Os segmentos da rota: o início e o fim pela distância corrida na rota."""
        if self.segments is None or self.engine.paused:
            return
        st = self.route_state()
        if st is None:
            return
        d, total, _g = st
        if d + total / 2 < self._route_d:          # nova volta à rota
            self.segments.reset()
        self._route_d = d
        e = self.engine
        from perennia.core import segments as seg_mod
        for kind, data in self.segments.observe(d, e.t):
            src = "Perennia" if data.get("source") == "perennia" else "Strava"
            if kind == "strava_start":
                self.toast = tr("Segmento {s}: {n} · {k} km", "{s} segment: {n} · {k} km",
                                s=src, n=data["name"], k=f"{data['distance_m'] / 1000:.2f}")
            else:
                el = int(data["elapsed_s"])
                best = data.get("local_best_s")
                try:
                    seg_mod.save_effort(self.app.db, e.session_id, data["id"], el,
                                        source=data.get("source", "strava"), kind="endurance",
                                        sport=e.sport)
                except Exception:
                    pass
                self.toast = tr("Fim do segmento {n}: {t}", "Segment {n} done: {t}",
                                n=data["name"], t=hms(el)) + (
                    tr(" · novo melhor!", " · new best!") if best is None or el < best
                    else tr(" · melhor {b}", " · best {b}", b=hms(best)))
            self._toast_until = time.monotonic() + 5.0

    def lap_data(self) -> tuple[str, list[tuple[str, str]], list[str]]:
        """A volta em curso (seis números) e as já feitas, para o painel."""
        e = self.engine
        lp = e._lap
        unit = pace_unit(e.sport)
        pace = e.pace_s(e.lap_elapsed_s, e.lap_distance_m)
        avg_hr = lp.hr_sum / lp.hr_n if lp.hr_n else None
        cells = [(tr("Tempo", "Time"), hms(e.lap_elapsed_s)),
                 (tr("Distância", "Distance"), _m(e.lap_distance_m)),
                 (tr("Ritmo", "Pace"), (hms(pace) + unit) if pace else "—"),
                 (tr("FC média", "Avg HR"), f"{avg_hr:.0f} bpm" if avg_hr else "—"),
                 (tr("FC máxima", "Max HR"), f"{lp.max_hr} bpm" if lp.max_hr else "—"),
                 ((tr("Piscinas", "Lengths"), str(e.lengths - lp.start_len))
                  if e.sport == "swimming" else
                  (tr("Velocidade", "Speed"), f"{e.speed_kmh:.1f} km/h"))]
        prev = []
        for x in reversed(e.laps):
            p = e.pace_s(x.seconds, x.distance_m)
            bits = [f"{x.no}.", hms(x.seconds), _m(x.distance_m),
                    (hms(p) + unit) if p else "",
                    f"{x.avg_hr:.0f} bpm" if x.avg_hr else ""]
            prev.append("  ".join(b for b in bits if b))
        return tr("Volta {n}", "Lap {n}", n=lp.no), cells, prev

    def _plan_title(self) -> str:
        e = self.engine
        if e.workout is None:
            return ""                    # sessão livre: sem o nome do desporto a meio do ecrã
        s = e.workout.step
        if s is None:
            return tr("TREINO CONCLUÍDO", "WORKOUT DONE")
        return f"{tr('PASSO', 'STEP')} {e.workout.idx + 1}/{len(e.workout.steps)} · " \
               f"{e.workout.remaining_text()}"

    def route_state(self) -> tuple[float, float, float] | None:
        """(km na rota, comprimento, inclinação %) — a rota repete-se no fim."""
        pts = self.route_pts
        if not pts:
            return None
        total = pts[-1].dist_m or 1.0
        d = self.engine.distance_m % total
        lo, hi = 0, len(pts) - 1
        while lo < hi:                                   # o primeiro ponto ≥ d
            mid = (lo + hi) // 2
            if pts[mid].dist_m < d:
                lo = mid + 1
            else:
                hi = mid
        return d, total, float(pts[lo].grade_pct or 0.0)

    def route_line(self) -> str:
        st = self.route_state()
        if st is None:
            return ""
        d, total, grade = st
        incline = max(0.0, min(15.0, round(grade * 2) / 2))
        if self.engine.treadmill is not None and self.engine.workout is None:
            self.engine.set_incline(incline)             # a passadeira segue a rota
        line = tr("Rota «{n}» · {a} de {b} km · inclinação da estrada {g} % → põe {i} %",
                  "Route «{n}» · {a} of {b} km · road gradient {g} % → set {i} %",
                  n=self.route_name, a=f"{d / 1000:.2f}", b=f"{total / 1000:.1f}",
                  g=f"{grade:+.1f}", i=f"{incline:g}")
        cur = self.segments.current(d, self.engine.t) if self.segments is not None else None
        if cur is not None:
            line += "\n" + tr("Segmento «{n}» · {p} % · {t}", "Segment «{n}» · {p} % · {t}",
                              n=cur["name"], p=f"{cur['frac'] * 100:.0f}",
                              t=hms(cur["elapsed_s"]))
        return line

    def _plan_text(self) -> str:
        text = self._plan_body()
        route = self.route_line()
        return "\n".join(x for x in (route, text) if x)

    def _plan_body(self) -> str:
        e = self.engine
        if e.workout is None or e.workout.step is None:
            return ""
        s = e.workout.step
        lines = [f"{s.duration_text()} · {tr('alvo', 'target')} {e.target_text()}"]
        if getattr(self, "_goal_line", None) is None:
            from perennia.ui.brief import GoalLine
            self._goal_line = GoalLine(self.app.db, e.sport, getattr(e, "workout_id", None))
        goal = self._goal_line.text(e.workout.idx)
        if goal:
            lines.insert(0, goal)
        if s.cue:
            lines.append(s.cue)
        nxt = e.workout.next_step
        if nxt is not None:
            t_ = tr("livre", "free") if nxt.lo is None else e.ctx.text(e.mode, nxt.mid)
            lines.append(tr("A seguir: ", "Next: ") + f"{nxt.duration_text()} · {t_}")
        return "\n".join(lines)

    def _event(self, kind: str, data: dict) -> None:
        msg = {"started": tr("A contar!", "Go!"),
               "lap": tr("Volta {n} marcada", "Lap {n} marked", n=data.get("no")),
               "workout_done": tr("Treino concluído!", "Workout done!"),
               "recovered": t("recover.toast")}.get(kind)
        if kind == "step" and data.get("cue"):
            msg = data["cue"]
        if kind == "lap":
            self.laps_panel.pulse(time.monotonic())
        if msg:
            self.toast, self._toast_until = msg, time.monotonic() + 3.0
        if kind == "workout_done":
            self.plan_complete()

    def on_device_lost(self, name: str) -> None:
        self.toast = tr("⚠ {n} desligou-se", "⚠ {n} disconnected", n=name)
        self._toast_until = time.monotonic() + 6.0

    def on_key(self, symbol: int, modifiers: int) -> bool:
        e = self.engine
        if self.confirming or self.pause_popup:   # o diálogo de terminar e o popup «PAUSA»
            return self.finish_key(symbol)
        if self.typing is not None:
            if symbol in (key.ENTER, key.RETURN):
                try:
                    e.set_distance(float(self.typing.replace(",", ".")) * 1000)
                except ValueError:
                    pass
                self.typing = None
            elif symbol == key.ESCAPE:
                self.typing = None
            elif symbol == key.BACKSPACE:
                self.typing = self.typing[:-1]
            return True
        if symbol == key.SPACE and not e.started:
            e.start()
            return True
        plus = symbol in (key.PLUS, key.EQUAL, key.NUM_ADD)
        minus = symbol in (key.MINUS, key.NUM_SUBTRACT)
        if plus or minus:
            self._flow_adjust(1 if plus else -1, 5 if modifiers & key.MOD_SHIFT else 1)
            return True
        if symbol in (key.UP, key.DOWN) and e.sport == "running":
            self._incline_step(1 if symbol == key.UP else -1, 2 if modifiers & key.MOD_SHIFT else 1)
            return True
        if symbol == key.T and e.sport == "running":
            if e.speed_locked:
                self._locked_toast()
                return True
            self.typing = ""
            return True
        if symbol == key.L:
            if not e.manual_laps:
                self.toast = tr("Num treino, cada bloco é uma volta (voltas à mão só na sessão livre)", "In a workout each block is a lap (manual laps only in a free session)")
                self._toast_until = time.monotonic() + 4.0
                return True
            e.lap("manual")
            return True
        if symbol == key.N:                        # saltar o bloco em curso
            self._skip_block()
            return True
        if symbol == key.P:
            self._flow_toggle_pause()
            return True
        if symbol in (key.ESCAPE, key.F10):        # Esc pausa · F10 pergunta (como no ciclismo)
            return self.finish_key(symbol)
        return True

    def _skip_block(self) -> None:
        e = self.engine
        if e.skip_step():
            self.toast = tr("Bloco saltado", "Block skipped")
        elif e.workout is None:
            self.toast = tr("Não há blocos: é uma sessão livre", "No blocks: this is a free session")
        else:
            self.toast = tr("Não há bloco para saltar", "No block to skip")
        self._toast_until = time.monotonic() + 3.0

    def on_mouse(self, x: int, y: int) -> bool:
        if not self.confirming and not self.pause_popup:
            hit = self.controls.hit(x, y)           # os − + da velocidade e da inclinação
            if hit is not None:
                kind, sign = hit
                (self._flow_adjust if kind == "speed" else self._incline_step)(sign, 1)
                return True
        handled = self.finish_mouse(x, y)
        return handled if handled is not None else super().on_mouse(x, y)

    def _tag_context(self):
        e = self.engine
        if not e.started or e.t < 1:
            return None
        s = e.summary()
        return (e.sport, e.workout_id, bool(e.route_id),
                {"load": s.get("load"), "moving_s": s.get("moving_s"),
                 "elapsed_s": s.get("elapsed_s")})

    def _flow_has_adjust(self) -> bool:
        """Na corrida livre a velocidade e a inclinação têm os botões ao meio do ecrã; os − + de
        baixo ficam para a natação (piscinas) e para os treinos."""
        e = self.engine
        return not (e.sport == "running" and e.workout is None)

    def _flow_adjust(self, step: int, mult: int = 1) -> None:
        e = self.engine
        if e.sport == "running":
            if e.speed_locked:
                self._locked_toast()
                return
            e.set_speed(e.speed_kmh + 0.1 * step * mult)       # de 0,1 em 0,1 km/h
        else:
            e.add_length(step)

    def _incline_step(self, step: int, mult: int = 1) -> None:
        """A inclinação da passadeira, de 0,5 em 0,5 % (o passo das Definições)."""
        e = self.engine
        if e.sport != "running" or e.speed_locked:
            return
        from perennia.core import workout_meta as wm
        unit = wm.device_limits(self.app.db)["treadmill_incline_step"]
        e.set_incline(e.incline_pct + unit * step * mult)

    def _flow_toggle_pause(self) -> None:
        if not self.engine.started:                 # antes de começar, o botão começa
            self.engine.toggle_pause()
            return
        super()._flow_toggle_pause()

    def _flow_can_pause(self) -> bool:
        return bool(self.engine.started)

    def _flow_paused(self) -> bool:
        return bool(self.engine.paused)

    def _flow_set_paused(self, paused: bool) -> None:
        e = self.engine
        if e.started and bool(e.paused) != paused:
            e.toggle_pause()

    def on_text(self, text: str) -> bool:
        if self.typing is not None:
            self.typing += "".join(c for c in text if c in "0123456789.,")
        return True

    def _finish(self) -> None:
        e = self.engine
        if not e.started or e.t < 1:
            e.abort(delete=True)
            self.app.pop()
            return
        self.app.replace(EnduranceSummary(self.app, e.finish()))

    def _locked_toast(self) -> None:
        self.toast = tr("A velocidade é a do bloco ({v} km/h): a distância conta por ela",
                        "The speed is the block's ({v} km/h): distance follows it",
                        v=f"{self.engine.speed_kmh:.1f}")
        self._toast_until = time.monotonic() + 4.0

    def _discard(self) -> None:
        self.engine.discard()
        from perennia.core import segments as seg_mod
        seg_mod.forget_session(self.app.db, "endurance", self.engine.session_id)
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

    def countdown_done(self) -> None:
        if not self.engine.started:
            self.engine.start()

    def cancel_countdown(self) -> None:
        self._discard()

    def leave(self) -> None:
        if not self.engine.finished:
            self.engine.suspend()

    def draw(self) -> None:
        self.chrome.draw()
        self.batch.draw()
        self.laps_panel.draw()
        self.arr_draw()
        if self.back_button is not None:
            self.back_button.draw()
        self.list.draw()                                  # os botões em baixo, à direita
        self.draw_finish()


class EnduranceSummary(RadarSide, Screen):
    def __init__(self, app, result: dict):
        super().__init__(app)
        self.result = result

    def enter(self) -> None:
        r = self.result
        unit = pace_unit(r["sport"])
        items = [Item(tr("Distância", "Distance"), value=_m(r["distance_m"]), enabled=False),
                 Item(tr("Tempo", "Time"), value=hms(r["moving_s"]), enabled=False,
                      detail=tr("em pausa {p}", "paused {p}", p=hms(r["paused_s"]))),
                 Item(tr("Ritmo médio", "Avg pace"),
                      value=(hms(r["avg_pace_s"]) + " " + unit) if r["avg_pace_s"] else "—",
                      enabled=False)]
        if r.get("avg_hr"):
            items.append(Item(tr("FC média", "Avg HR"), value=f"{r['avg_hr']:.0f} bpm",
                              detail=f"máx {r.get('max_hr')}", enabled=False))
        if r.get("load") is not None:
            items.append(Item(tr("Carga", "Load"), value=f"{r['load']:.0f}", enabled=False))
        if r["sport"] == "swimming":
            items.append(Item(tr("Piscinas", "Lengths"),
                              value=f"{r['lengths']} × {r['pool_m']:g} m", enabled=False))
        for lp in r.get("laps", []):
            p = lp.seconds / lp.distance_m * (1000 if r["sport"] == "running" else 100) \
                if lp.distance_m > 5 else None
            items.append(Item(f"  {tr('Volta', 'Lap')} {lp.no}", value=hms(lp.seconds),
                              detail=f"{_m(lp.distance_m)}" + (f" · {hms(p)} {unit}" if p
                                                               else ""), enabled=False))
        # o título e o rodapé são os do resumo do ciclismo
        fit = r.get("fit_path")
        sub = t("summary.saved_fit", path=fit) if fit else \
            f"{t('common.error')}: o .fit não foi escrito"
        if r.get("name"):
            sub = f"{r['name']} · {sub}"
        self.chrome.set(t("summary.title"), sub, self.footer())
        fb_item = _feedback().summary_item(self.app, "endurance", self.result.get("session_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        items[1:1] = self.radar_attach(r["sport"], self.result.get("session_id"))
        self.list.set_items(items, keep_index=True)
        _feedback().maybe_ask(self, "endurance", self.result.get("session_id"))


def EnduranceDetail(app, sid: str):                       # noqa: N802 — compatibilidade
    """Uma sessão de corrida ou natação do histórico: a análise em separadores."""
    from perennia.ui.session_analysis import SessionAnalysis
    return SessionAnalysis(app, "endurance", sid)


def _pretty(name) -> str:
    from perennia.core.naming import pretty
    return pretty(name)


def _feedback():
    from perennia.ui import feedback_screens
    return feedback_screens
