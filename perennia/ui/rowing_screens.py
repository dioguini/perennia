"""Remo: menu, sessão (com campos configuráveis), treinos e construtor,
Challenge, histórico, estatísticas e a máquina de remo."""
from __future__ import annotations

import threading
import time

import pyglet
from pyglet.window import key

from perennia.core import rowing as rw
from perennia.core.i18n import t, tr
from perennia.core.units import hms
from perennia.gfx.compat import label as make_label
from perennia.io import rower as rower_io
from perennia.io.rower import pace_text
from perennia.ui.app import BOARD_W, Screen, SportHub, StartOptions
from perennia.ui.challenge_screens import train_items
from perennia.ui.session_flow import FinishFlow
from perennia.ui.session_radar import RadarSide
from perennia.ui.session_panels import OFF, ArrangedPanels
from perennia.ui.sport_screens import EditScreen, LiveEditPopup
from perennia.ui.brief import BriefScreen as _BriefBase
from perennia.ui.widgets import (ACCENT, BAD, BoardPanel, Chart, DIM, GOOD, P, PANEL, TEXT, Item,
                             LapPanel, CountdownBadge)


def _m(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1000:.2f} km" if v >= 10000 else f"{v:.0f} m"


# ======================================================== campos do ecrã

# Os campos do ecrã de remo vivem em perennia.core.layouts (o editor de ecrãs usa-os).
from perennia.core.layouts import ROW_DEFAULT as DEFAULT_FIELDS  # noqa: E402
from perennia.core.layouts import ROW_FIELDS as FIELDS  # noqa: E402

N_FIELDS = 12          # no máximo, quadrados por página (V muda de página)


def field_names(db) -> list[str]:
    """As métricas do ecrã, pela ordem: o número é o escolhido nas Definições."""
    v = [x for x in (db.get("row_fields") or []) if x in FIELDS]
    return v or list(DEFAULT_FIELDS)


def field_value(e: rw.RowEngine, name: str) -> str:
    def w(v):
        return f"{v:.0f} W" if v else "—"
    if name == "pace":
        return pace_text(e.pace_s)
    if name == "avg_pace":
        return pace_text(e.avg_pace_s)
    if name == "best_pace":
        return pace_text(e._best_pace)
    if name == "split500":
        return hms(e.split(500)) if e.split(500) else "—"
    if name == "spm":
        return f"{e.spm:.0f}" if e.spm else "—"
    if name == "avg_spm":
        return f"{e.avg_spm:.1f}" if e.avg_spm else "—"
    if name == "power":
        return w(e.power_w)
    if name == "avg_power":
        return w(e.avg_power_w)
    if name == "max_power":
        return w(e._max_w)
    if name == "pct_ftp":
        return f"{e.pct_ftp:.0f} %" if e.pct_ftp else "—"
    if name == "jps":
        j = e.joules_per_stroke
        return f"{j:.0f} J" if j else "—"
    if name == "distance":
        return _m(e.distance_m)
    if name == "time":
        return hms(e.t)
    if name == "strokes":
        return str(e.strokes)
    if name == "hr":
        return f"{e.hr_bpm}" if e.hr_bpm else "—"
    if name == "avg_hr":
        return f"{e.avg_hr:.0f}" if e.avg_hr else "—"
    if name == "max_hr":
        return f"{e.max_hr}" if e.max_hr else "—"
    if name == "zone":
        return f"Z{e.hr_zone}" if e.hr_zone else "—"
    if name == "resistance":
        return f"{e.resistance}/15" if e.resistance else "—"
    if name == "kcal":
        return f"{e.kcal:.0f}"
    if name == "kcal_h":
        k = e.kcal_per_hour
        return f"{k:.0f}" if k else "—"
    if name == "load":
        return f"{e.live_load:.0f}"
    if name == "wkg":
        p = e.power_w
        return f"{p / e.athlete.weight_kg:.2f}" if p and e.athlete.weight_kg else "—"
    if name == "dps":
        d = e.dist_per_stroke
        return f"{d:.1f} m" if d else "—"
    if name == "lap":
        lp = e._lap
        if lp is None:
            return "—"
        return f"{_m(e.distance_m - lp.start_m)} · {hms(e.t - lp.start_t)}"
    if name == "lap_time":
        return hms(e.lap_elapsed_s)
    if name == "lap_dist":
        return _m(e.lap_distance_m)
    if name == "lap_pace":
        return pace_text(e.lap_pace_s)
    if name == "last_lap_pace":
        lp = e.last_lap
        return pace_text(lp.avg_pace_s) if lp else "—"
    if name == "step_left":
        return e.workout.remaining_text() if e.workout and e.workout.step else "—"
    if name == "target":
        s = e.workout.step if e.workout else None
        if s is None:
            return "—"
        rng = s.pace_range(e.ftp)
        return pace_text(rng[0]) if rng else s.target_text(e.ftp)[:10]
    if name == "target_delta":
        d = e.target_delta()
        return "—" if d is None else f"{d:+.1f} s"
    if name == "projected":
        p = e.avg_pace_s
        return hms(p * 4) if p else "—"
    if name == "finish":
        f = e.projected_finish()
        return hms(f) if f else "—"
    return "—"


# ===================================================================== menu


class RowingMenu(SportHub):
    """Remo, por separadores."""

    SPORT = "rowing"

    def enter(self) -> None:
        rw.link_tests(self.app.db)
        super().enter()

    def items_train(self) -> list[Item]:
        # a máquina de remo liga-se em Dispositivos; a FTP do remo está nas
        # Definições (Atleta)
        a = self.app
        # os campos do ecrã estão em Definições → Ecrã da sessão
        return train_items(a, "rowing", session=Item(
            tr("Sessão de treino", "Training session"),
            detail=tr("Remo livre (com voltas) ou carregar um treino",
                      "Free row (with laps) or load a workout"),
            action=lambda: self._ask()))

    def _ask(self) -> None:
        from perennia.ui.session_setup import ask_start
        ask_start(self.app, "rowing", self)

    def items_library(self) -> list[Item]:
        a = self.app
        from perennia.ui.workout_import import import_item
        out = [import_item(a, "rowing", on_done=lambda _w: self.enter())]
        for w in rw.workouts(a.db):
            dur = " + ".join(x for x in (hms(w["total_s"]) if w["total_s"] else "",
                                         _m(w["total_m"]) if w["total_m"] else "") if x)
            out.append(Item(w["name"], value=dur, detail=w["description"] or "",
                            action=lambda wid=w["id"]: a.push(RowWorkoutPreview(a, wid)),
                            data=("row_workout", w["id"])))
        return out

    def items_history(self) -> list[Item]:
        a = self.app
        out = []
        for s in rw.sessions(a.db):
            out.append(Item(f"{str(s['started_at'])[:16].replace('T', ' ')}  {_pretty(s['name'])}",
                            value=_m(s["distance_m"]),
                            detail=f"{hms(s['moving_s'] or 0)} · "
                                   f"{pace_text(s['avg_pace_s'])} /500 m"
                                   + (f" · {s['avg_power_w']:.0f} W" if s["avg_power_w"]
                                      else ""),
                            action=lambda sid=s["id"]: a.push(RowSessionDetail(a, sid))))
        from perennia.ui.sync_screens import history_items
        return out + history_items(a, "rowing")

    def items_stats(self) -> list[Item]:
        return super().items_stats() + record_items(self.app)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and isinstance(item.data, tuple) and item.data[0] == "row_workout" \
                and symbol == key.P:
            self.app.push(RowWorkoutEditor(self.app, item.data[1]))
            return True
        return super().on_key(symbol, modifiers)

    def _start(self, kw: dict) -> None:
        start_session(self.app, **kw)


def record_items(app) -> list[Item]:
    """Os recordes do remo, cada um com a sessão onde foi feito (Enter abre-a)."""
    a = app
    b = rw.bests(a.db)
    ses = b.get("sessions") or {}

    def record(label: str, key_: str, value: str) -> Item:
        """Um recorde e a sessão onde foi feito (Enter abre-a)."""
        s = ses.get(key_)
        if s is None:
            return Item(label, value=value, enabled=False)
        when = str(s["started_at"])[:16].replace("T", " ")
        return Item(label, value=value,
                    detail=tr("em {d} · {n}", "on {d} · {n}", d=when,
                              n=_pretty(s["name"]) or tr("Remo", "Rowing")),
                    action=lambda sid=s["id"]: a.push(RowSessionDetail(a, sid)),
                    data=("record", key_, s["id"]))

    avg = ses.get("avg_pace", {}).get("avg_pace_s") if ses.get("avg_pace") else None
    spm = ses.get("spm", {}).get("avg_spm") if ses.get("spm") else None
    mx = ses.get("max_w", {}).get("max_power_w") if ses.get("max_w") else None
    longest = ses.get("time")
    return [
        Item(tr("Sessões", "Sessions"), value=str(b.get("n") or 0), enabled=False),
        Item(tr("Distância total", "Total distance"), value=_m(b.get("total") or 0),
             enabled=False),
        record(tr("Melhor ritmo (500 m)", "Best pace (500 m)"), "pace",
               pace_text(b.get("pace"))),
        record(tr("Melhor ritmo médio de uma sessão", "Best session avg pace"), "avg_pace",
               pace_text(avg)),
        record(tr("Maior distância", "Longest"), "dist", _m(b.get("dist"))),
        record(tr("Sessão mais longa", "Longest session"), "time",
               hms((longest.get("moving_s") or longest.get("elapsed_s") or 0))
               if longest else "—"),
        record(tr("Mais potência média", "Best avg power"), "w",
               f"{b['w']:.0f} W" if b.get("w") else "—"),
        record(tr("Mais potência máxima", "Best max power"), "max_w",
               f"{mx:.0f} W" if mx else "—"),
        record(tr("Voga média mais alta", "Highest avg stroke rate"), "spm",
               f"{spm:.0f} spm" if spm else "—")]


def _health():
    from perennia.ui import health_screens
    return health_screens


def start_session(app, replace: bool = False, **kw) -> None:
    """Abre a sessão, ou pede a máquina primeiro."""
    if getattr(app, "rower", None) is None:
        app.message(tr("Liga primeiro a máquina de remo (ou usa a simulada).",
                       "Connect the rowing machine first (or use the simulated one)."))
        app.open_devices()                      # a janela dos aparelhos, por cima da preparação
        return
    if kw.get("resume") is not None:
        scr = RowingSessionScreen(app, **kw)
        app.replace(scr) if replace else app.push(scr)
        return
    title = None
    if kw.get("game_spec"):
        title = rw.game_title(kw["game_spec"]["key"])
    elif kw.get("protocol"):
        title = tr("Teste", "Test")
    from perennia.ui.session_setup import SessionSetup
    kind = "workout" if kw.get("workout_id") else "game" if kw.get("game_spec") else \
        "test" if kw.get("protocol") else "free"
    app.push(SessionSetup(app, "rowing", kind=kind, workout_id=kw.get("workout_id"),
                          protocol=kw.get("protocol"), game_spec=kw.get("game_spec"),
                          title=title))


# ================================================================== sessão


class RowingSessionScreen(FinishFlow, ArrangedPanels, Screen):
    KEY_SCOPE = "rowing"
    AGENT = False
    HAS_BOARD = True
    IN_SESSION = True

    def __init__(self, app, workout_id: str | None = None, protocol: str | None = None,
                 game_spec: dict | None = None, resume: dict | None = None,
                 autolap: dict | None = None):
        super().__init__(app)
        a = app
        cfg = (resume or {}).get("config", {})
        self.engine = rw.RowEngine(
            a.db, a.db.athlete(), a.rower, sensors=a.hub,
            workout_id=workout_id or cfg.get("workout_id"),
            protocol=protocol or cfg.get("protocol"),
            game_spec=game_spec or cfg.get("game"), out_dir=a.data_dir / "rowing",
            resume=resume, autolap=autolap)
        self.start_countdown(resume)          # 15 s; depois conta a partir da 1.ª remada
        self.page = 0
        self.session = self.engine           # o fecho da aplicação trata dela
        self.init_finish()                    # o diálogo de terminar, como no ciclismo
        self.toast = ""
        self._toast_until = 0.0
        self.names = field_names(a.db)
        from perennia.core import layouts as _lay
        self.sizes = _lay.page_sizes("rowing", len(self.names))     # quadrados por página
        self.pages = len(self.sizes)
        b = self.batch = pyglet.graphics.Batch()
        self.cells = []
        for _ in range(max(self.sizes)):
            bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
            cap = make_label("", font_size=12, color=DIM, anchor_y="top", batch=b)
            val = make_label("", font_size=34, bold=True, color=TEXT, anchor_y="top", batch=b)
            self.cells.append((bg, cap, val))
        self.status = make_label("", font_size=16, bold=True, color=ACCENT, anchor_y="top",
                                 batch=b)
        self.plan = make_label("", font_size=14, color=TEXT, anchor_y="top", batch=b,
                               multiline=True, width=400)
        self.toast_label = make_label("", font_size=15, bold=True, color=GOOD,
                                      anchor_y="top", batch=b)
        self.track = pyglet.shapes.Rectangle(0, 0, 10, 8, color=P().panel2, batch=b)
        self.bar = pyglet.shapes.Rectangle(0, 0, 0, 8, color=ACCENT[:3], batch=b)
        self.clock = CountdownBadge(app.window, batch=b)   # só os últimos segundos de um bloco
        self.laps_panel = LapPanel()        # as voltas: sempre aqui, como no ciclismo
        self.chrome.title.font_size = 18
        self.arr_load("rowing")             # Definições → Ecrã da sessão → Disposição
        self._layout()
        for kind, data in self.engine.drain_events():
            self._event(kind, data)

    # ---------------------------------------------------------------- layout

    def _list_width(self, w: int) -> int:
        return 300

    def _layout(self) -> None:
        from perennia.core import layouts as _lay
        cols, rows = _lay.grid_for(len(self.cells), "rowing")
        gap = 10
        m = self.arr_rect("metrics")
        if m is not None:
            mx, my, mw, mh = m
            cw = (mw - gap * (cols - 1)) / cols
            ch = max(56.0, min(108.0, (mh - gap * (rows - 1)) / rows))
            top = my + mh
        for i, (bg, cap, val) in enumerate(self.cells):
            if m is None:
                bg.x = cap.x = val.x = OFF
                continue
            r, c = divmod(i, cols)
            x = mx + c * (cw + gap)
            y = top - r * (ch + gap)
            bg.x, bg.y, bg.width, bg.height = x, y - ch, cw, ch
            cap.x, cap.y = x + 12, y - 8
            val.x, val.y = x + 12, y - 26
            val.font_size = 30 if cw > 220 and ch > 90 else (24 if cw > 150 else 20)
            self._val_size = val.font_size
            cap.font_size = 11 if cw > 170 else 9
        st = self.arr_rect("status")
        if st is not None:
            sx, sy, sw, sh = st
            self.status.x, self.status.y = sx, sy + sh
            self.toast_label.x, self.toast_label.y = sx + min(420, sw * 0.55), sy + sh
            self.plan.x, self.plan.y = sx, sy + sh - 30
            self.plan.width = int(sw)
            self.track.x, self.track.y, self.track.width = sx, sy + 4, sw
            self.bar.x, self.bar.y = sx, sy + 4
            self._bar_w = sw
        else:
            self.status.x = self.toast_label.x = self.plan.x = OFF
            self.track.x = self.bar.x = OFF
            self._bar_w = 10
        self.list.y = -1000                                 # a lista fica escondida
        self.clock.layout()
        bd = self.arr_rect("board")
        if self.board_panel is not None:
            if bd is not None:
                self.board_panel.layout(bd[0], bd[1] + bd[3], bd[2])
            else:
                self.board_panel.layout(OFF, OFF, BOARD_W)
        lp = self.arr_rect("laps")
        lr, br = self.arrangement.get("laps"), self.arrangement.get("board")
        if lp is not None and self.engine.game is None and br is not None and \
                (br[0], br[2], br[1]) == (lr[0], lr[2], lr[1] + lr[3]):
            # sem jogo não há classificação: as voltas ocupam o lugar dela
            from perennia.core import screen_layout as sl
            lp = sl.to_px((lr[0], lr[1], lr[2], lr[3] + br[3]), self.arr_area())
        if lp is not None:
            self.laps_panel.layout(lp[0], lp[1] + lp[3], lp[2], lp[1])
        else:
            self.laps_panel.layout(OFF, OFF + 400, 200, OFF)
        self.arr_layout_extras()
        self._layout_finish()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()

    def lap_data(self) -> tuple[str, list[tuple[str, str]], list[str]]:
        """A volta em curso (seis números) e as já feitas, para o painel."""
        e = self.engine
        lp = e._lap
        acc = getattr(lp, "acc", None) or {}
        avg_w = acc.get("w", 0) / acc["wn"] if acc.get("wn") else None
        avg_spm = acc.get("spm", 0) / acc["sn"] if acc.get("sn") else None
        avg_hr = acc.get("hr", 0) / acc["hn"] if acc.get("hn") else None
        no = lp.no if lp is not None else len(e.laps) + 1
        cells = [(tr("Tempo", "Time"), hms(e.lap_elapsed_s)),
                 (tr("Distância", "Distance"), _m(e.lap_distance_m)),
                 (tr("Ritmo /500 m", "Pace /500 m"), pace_text(e.lap_pace_s)),
                 (tr("Potência média", "Avg power"), f"{avg_w:.0f} W" if avg_w else "—"),
                 (tr("Voga média", "Avg rate"), f"{avg_spm:.0f} spm" if avg_spm else "—"),
                 (tr("FC média", "Avg HR"), f"{avg_hr:.0f} bpm" if avg_hr else "—")]
        prev = []
        for x in reversed(e.laps):
            if x.trigger == "start" and not x.distance_m:
                continue
            bits = [f"{x.no}.", hms((x.end_t or 0) - x.start_t), _m(x.distance_m),
                    pace_text(x.avg_pace_s) + " /500 m" if x.avg_pace_s else ""]
            if x.avg_power_w:
                bits.append(f"{x.avg_power_w:.0f} W")
            if x.avg_spm:
                bits.append(f"{x.avg_spm:.0f} spm")
            if x.avg_hr:
                bits.append(f"{x.avg_hr:.0f} bpm")
            prev.append("  ".join(b for b in bits if b))
        return tr("Volta {n}", "Lap {n}", n=no), cells, prev

    def footer(self) -> str:
        eng = getattr(self, "engine", None)
        if eng is not None and not eng.manual_laps:
            return tr("+/− resistência · V outra página · P pausa · F10 terminar e guardar",
                      "+/− resistance · V other page · P pause · F10 stop and save")
        return tr("+/− resistência · L volta · V outra página · P pausa · "
                  "F10 terminar e guardar", "+/− resistance · L lap · V other page · "
                  "P pause · F10 stop and save")

    # ------------------------------------------------------------- quadro

    def side_board(self):
        e = self.engine
        if e.game is not None:
            return e.game.board(rw.game_history(e.db, e.game))
        from perennia.core.boards import Board, Row
        rows = [Row(lp.no, f"{_m(lp.distance_m)} · {pace_text(lp.avg_pace_s)}",
                    hms((lp.end_t or 0) - lp.start_t)) for lp in e.laps[-6:]
                if lp.trigger != "start" or lp.distance_m > 0]
        empty = tr("L marca uma volta", "L marks a lap") if e.manual_laps else \
            tr("cada bloco do treino é uma volta", "each workout block is a lap")
        return Board(tr("Voltas", "Laps"), rows, subtitle=e.title, empty=empty)

    # ---------------------------------------------------------------- ciclo

    def enter(self) -> None:
        e = self.engine
        self.list.y = -1000
        self.refresh_buttons(force=True)                  # − + Pausa Terminar, em baixo
        self.chrome.set(e.title, "", self.footer())

    def update(self, dt: float) -> None:
        a = self.app
        a.hub.tick(dt)
        e = self.engine
        e.update(dt)
        self.refresh_buttons()
        for kind, data in e.drain_events():
            self._event(kind, data)
        from perennia.ui.session_flow import workout_step_cues
        self.clock.alert(workout_step_cues(self, e.workout) if e.started else None)
        lap = e.lap_elapsed_s if e._lap is not None else 0.0
        self.clock.set(e.t, tr("volta {t}", "lap {t}", t=hms(lap)) + (
            f" · {tr('passo', 'step')} {e.workout.remaining_text()}"
            if e.workout is not None and e.workout.step is not None else ""))
        start = sum(self.sizes[:self.page])
        for i, (bg, cap, val) in enumerate(self.cells):
            if i >= self.sizes[self.page]:             # a última página pode ter menos
                bg.opacity = 0
                cap.text = val.text = ""
                continue
            bg.opacity = 255
            name = self.names[start + i]
            pt, en = FIELDS[name]
            cap.text = tr(pt, en).upper()
            val.text = field_value(e, name)
            val.color = _zone_ink(e.hr_zone) if name == "zone" and e.hr_zone else TEXT
            size = getattr(self, "_val_size", 24)
            while size > 12 and len(val.text) * size * 0.66 > bg.width - 20:
                size -= 2
            val.font_size = size
        st = {"waiting": tr("REMA PARA COMEÇAR", "ROW TO START"),
              "paused": tr("EM PAUSA (P)", "PAUSED (P)"),
              "auto_paused": tr("PAUSA AUTOMÁTICA", "AUTO PAUSE"),
              "running": "", "finished": ""}[e.status]
        self.status.text = st or self._plan_title()
        self.plan.text = self._plan_text()
        self.bar.width = self._bar_w * self._progress()
        if self.toast and time.monotonic() > self._toast_until:
            self.toast = ""
        self.toast_label.text = self.toast
        if self.board_panel is not None and e.game is not None and int(e.t) % 2 == 0:
            self.refresh_board()
        title, cells, prev = self.lap_data()
        self.laps_panel.set(title, cells, prev, tr("VOLTAS FEITAS", "LAPS DONE"))
        self.laps_panel.update(time.monotonic())
        if e.started:
            self.arr_sample(dt, e.power_w, e.spm, getattr(e, "hr_zone_s", None))

    def _plan_title(self) -> str:
        e = self.engine
        if e.workout is not None:
            s = e.workout.step
            if s is None:
                return tr("TREINO CONCLUÍDO", "WORKOUT DONE")
            return (f"{tr('PASSO', 'STEP')} {e.workout.idx + 1}/{len(e.workout.steps)} · "
                    f"{e.workout.remaining_text()}")
        if e.game is not None:
            return e.game.headline.upper() if e.game.headline else e.game.title.upper()
        if e.test:
            if e.result_value is not None:
                return tr("TESTE CONCLUÍDO", "TEST DONE")
            dist, secs, _ = e.test
            return (f"{_m(max(0.0, dist - e.distance_m))} " + tr("para o fim", "to go")
                    if dist else hms(max(0.0, secs - e.t)) + " " + tr("para o fim", "to go"))
        return ""                       # remo livre: sem texto a meio do ecrã

    def _plan_text(self) -> str:
        e = self.engine
        if e.workout is not None and e.workout.step is not None:
            s = e.workout.step
            lines = [f"{_kind(s.kind)} · {s.duration_text()}"
                     f" · {tr('alvo', 'target')} {s.target_text(e.ftp)}"
                     + (f" · {tr('nível', 'level')} {s.resistance}" if s.resistance else "")]
            if getattr(self, "_goal_line", None) is None:
                from perennia.ui.brief import GoalLine
                self._goal_line = GoalLine(self.app.db, "rowing", getattr(e, "workout_id", None))
            goal = self._goal_line.text(e.workout.idx)
            if goal:
                lines.insert(0, goal)
            ok = e.workout.in_target(e.pace_s, e.power_w, e.spm)
            if ok is not None:
                lines.append(tr("✓ no alvo", "✓ on target") if ok else
                             tr("✗ fora do alvo", "✗ off target"))
            if s.cue:
                lines.append(s.cue)
            nxt = e.workout.next_step
            if nxt is not None:
                lines.append(tr("A seguir: ", "Next: ") + f"{_kind(nxt.kind)} · "
                             f"{nxt.duration_text()} · {nxt.target_text(e.ftp)}")
            return "\n".join(lines)
        if e.game is not None:
            g = e.game
            bits = [g.detail]
            if g.target_w:
                bits.append(tr("Alvo {w} W ≈ {p} /500 m", "Target {w} W ≈ {p} /500 m",
                               w=g.target_w, p=pace_text(rw.pace_from_watts(g.target_w))))
            return "\n".join(b for b in bits if b)
        if e.test and e.result_value is not None:
            from perennia.core import fitness_tests as ft
            return tr("Resultado: {v}", "Result: {v}", v=ft.fmt_value(e.result_value,
                                                                      e.test[2]))
        return ""

    def _progress(self) -> float:
        e = self.engine
        if e.workout is not None:
            return e.workout.progress()
        if e.game is not None:
            return e.game.progress
        if e.test:
            dist, secs, _ = e.test
            return min(1.0, e.distance_m / dist) if dist else min(1.0, e.t / secs)
        return 0.0

    def _event(self, kind: str, data: dict) -> None:
        msg = {
            "recovered": t("recover.toast"),
            "started": tr("A remar!", "Rowing!"),
            "auto_pause": tr("Pausa automática", "Auto pause"),
            "resistance": tr("Resistência {n}", "Resistance {n}", n=data.get("level")),
            "resistance_hint": tr("Põe a resistência no {n}", "Set the resistance to {n}",
                                  n=data.get("level")),
            "lap": tr("Volta {n} marcada", "Lap {n} marked", n=data.get("no")),
            "workout_done": tr("Treino concluído!", "Workout done!"),
            "test_done": tr("Teste concluído!", "Test done!"),
            "game_over": tr("Fim do jogo", "Game over"),
        }.get(kind)
        if kind == "step" and data.get("cue"):
            msg = data["cue"]
        if kind == "lap" and hasattr(self, "laps_panel"):
            self.laps_panel.pulse(time.monotonic())
        if msg:
            self.toast = msg
            self._toast_until = time.monotonic() + 3.0
        if kind == "workout_done":
            self.plan_complete()

    # ------------------------------------------------------------- teclas

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.confirming or self.pause_popup:   # o diálogo de terminar e o popup «PAUSA»
            return self.finish_key(symbol)
        e = self.engine
        if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD, getattr(key, "PAGEUP", -1)):
            e.adjust_resistance(+1)
            return True
        if symbol in (key.MINUS, key.NUM_SUBTRACT, getattr(key, "PAGEDOWN", -1)):
            e.adjust_resistance(-1)
            return True
        if symbol == key.L:
            if not e.manual_laps:
                self.toast = tr("Num treino, cada bloco é uma volta (voltas à mão só na sessão livre)", "In a workout each block is a lap (manual laps only in a free session)")
                self._toast_until = time.monotonic() + 4.0
                return True
            if e.lap("manual") is not None:
                self.laps_panel.pulse(time.monotonic())
            return True
        if symbol == key.V:
            self.page = (self.page + 1) % self.pages
            return True
        if symbol == key.N:                        # saltar o bloco (passo) em curso
            if e.skip_step():
                self.toast = tr("Bloco saltado", "Block skipped")
            else:
                self.toast = tr("Não há bloco para saltar", "No block to skip")
            self._toast_until = time.monotonic() + 3.0
            return True
        if symbol == key.P:
            self._flow_toggle_pause()
            return True
        if symbol in (key.ESCAPE, key.F10):        # Esc pausa · F10 pergunta (como no ciclismo)
            return self.finish_key(symbol)
        return True

    def on_mouse(self, x: int, y: int) -> bool:
        handled = self.finish_mouse(x, y)
        return handled if handled is not None else self.list.on_mouse_press(x, y)

    def _tag_context(self):
        e = self.engine
        if not e.started:
            return None
        s = e.summary()
        return ("rowing", e.workout_id, False,
                {"ftp_w": s.get("ftp_w"), "np_w": s.get("np_w"),
                 "avg_power_w": s.get("avg_power_w"), "load": s.get("load"),
                 "moving_s": s.get("moving_s"), "elapsed_s": s.get("elapsed_s")})

    def _flow_adjust(self, step: int, mult: int = 1) -> None:
        self.engine.adjust_resistance(step)

    def _flow_can_pause(self) -> bool:
        return bool(self.engine.started)

    def _flow_paused(self) -> bool:
        return bool(self.engine.manual_pause)

    def _flow_set_paused(self, paused: bool) -> None:
        e = self.engine
        if e.started and bool(e.manual_pause) != paused:
            e.toggle_pause()

    def _discard(self) -> None:
        self.engine.discard()
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

    def cancel_countdown(self) -> None:
        self._discard()

    def on_device_lost(self, name: str) -> None:
        self.toast = tr("⚠ {n} desligou-se", "⚠ {n} disconnected", n=name)
        self._toast_until = time.monotonic() + 6.0

    def _finish(self) -> None:
        e = self.engine
        if not e.started:
            e.abort()
            self.app.pop()
            return
        self.app.replace(RowSummaryScreen(self.app, e.finish()))

    def leave(self) -> None:
        if not self.engine.finished:
            self.engine.suspend()

    def draw(self) -> None:
        self.chrome.draw()
        self.batch.draw()
        if self.board_panel is not None and self.engine.game is not None:
            self.board_panel.draw()
        self.laps_panel.draw()
        self.arr_draw()
        if self.back_button is not None:
            self.back_button.draw()
        self.list.draw()                                  # os botões em baixo, à direita
        self.draw_finish()


def _zone_ink(z: int):
    """A cor da zona de FC (a mesma do construtor), legível sobre o painel."""
    from perennia.gfx import theme
    from perennia.gfx.hud import zone_color
    return theme.ink(zone_color(z, "hr"))


def _kind(k: str) -> str:
    return {"warmup": tr("Aquecimento", "Warm-up"), "active": tr("Trabalho", "Work"),
            "rest": tr("Descanso", "Rest"), "cooldown": tr("Retorno à calma", "Cool-down")
            }.get(k, k)


# ================================================================== resumo


class RowSummaryScreen(RadarSide, Screen):
    def __init__(self, app, result: dict):
        super().__init__(app)
        self.result = result

    def enter(self) -> None:
        r = self.result
        items = []

        def add(label, value, detail=""):
            items.append(Item(label, value=value, detail=detail, enabled=False))
        add(tr("Distância", "Distance"), _m(r.get("distance_m")))
        add(tr("Tempo", "Time"), hms(r.get("moving_s") or 0),
            tr("em pausa {p}", "paused {p}", p=hms(r.get("paused_s") or 0)))
        add(tr("Ritmo médio", "Avg pace"), pace_text(r.get("avg_pace_s")) + " /500 m",
            tr("melhor {p}", "best {p}", p=pace_text(r.get("best_pace_s"))))
        if r.get("avg_power_w"):
            add(tr("Potência média", "Avg power"), f"{r['avg_power_w']:.0f} W",
                f"NP {r['np_w']:.0f} W · máx {r.get('max_power_w') or 0} W" if r.get("np_w")
                else "")
        add(tr("Remadas", "Strokes"), str(r.get("strokes") or 0),
            f"{r['avg_spm']:.1f} spm" if r.get("avg_spm") else "")
        if r.get("avg_hr"):
            add(tr("FC média", "Avg HR"), f"{r['avg_hr']:.0f} bpm", f"máx {r.get('max_hr')}")
        if r.get("load") is not None:
            add(tr("Carga", "Load"), f"{r['load']:.0f}",
                tr("pela potência", "from power") if r.get("load_source") == "power"
                else tr("pela FC", "from HR"))
        if r.get("kcal"):
            add("kcal", f"{r['kcal']:.0f}")
        if r.get("result") is not None and r.get("protocol"):
            from perennia.core import fitness_tests as ft
            unit = rw.TESTS[r["protocol"]][2]
            add(tr("Resultado do teste", "Test result"), ft.fmt_value(r["result"], unit),
                tr("guardado nos testes do remo", "saved in the rowing tests"))
        g = r.get("game")
        if g:
            add(rw.game_title(g["game"]), g.get("summary", ""))
        for lp in r.get("laps", []):
            if lp.trigger == "start" and not lp.distance_m:
                continue
            add(f"  {tr('Volta', 'Lap')} {lp.no}", hms((lp.end_t or 0) - lp.start_t),
                f"{_m(lp.distance_m)} · {pace_text(lp.avg_pace_s)} /500 m"
                + (f" · {lp.avg_power_w:.0f} W" if lp.avg_power_w else "")
                + (f" · {lp.avg_spm:.0f} spm" if lp.avg_spm else ""))
        # o título e o rodapé são os do resumo do ciclismo
        fit = r.get("fit_path")
        sub = t("summary.saved_fit", path=fit) if fit else \
            f"{t('common.error')}: o .fit não foi escrito"
        if r.get("name"):
            sub = f"{r['name']} · {sub}"
        self.chrome.set(t("summary.title"), sub, self.footer())
        fb_item = _feedback().summary_item(self.app, "row", self.result.get("session_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        items[1:1] = self.radar_attach("rowing", self.result.get("session_id"))
        self.list.set_items(items, keep_index=True)
        _feedback().maybe_ask(self, "row", self.result.get("session_id"))

    def agent_data(self) -> dict:
        r = self.result
        return {k: r.get(k) for k in ("distance_m", "moving_s", "avg_pace_s", "avg_power_w",
                                      "avg_spm", "avg_hr", "load", "kind", "result")}


# ================================================================== treinos


class RowWorkoutLibrary(Screen):
    def __init__(self, app, builder: bool = False):
        super().__init__(app)
        self.builder = builder

    def enter(self) -> None:
        a = self.app
        items = []
        if self.builder:
            items.append(Item(tr("+ Novo treino", "+ New workout"),
                              action=lambda: a.push(RowWorkoutEditor(a, None))))
        ftp = rw.row_ftp(a.db)
        for w in rw.workouts(a.db):
            dur = []
            if w["total_s"]:
                dur.append(hms(w["total_s"]))
            if w["total_m"]:
                dur.append(_m(w["total_m"]))
            act = (lambda wid=w["id"]: a.push(RowWorkoutEditor(a, wid))) if self.builder \
                else (lambda wid=w["id"]: a.push(RowWorkoutPreview(a, wid)))
            items.append(Item(w["name"], value=" + ".join(dur),
                              detail=f"{len(w['steps'])} " + tr("passos", "steps") + " · "
                              + (w["description"] or ""), action=act))
        title = tr("Construtor de treinos de remo", "Rowing workout builder") if self.builder \
            else tr("Treinos de remo", "Rowing workouts")
        self.chrome.set(title, f"FTP {ftp} W", self.footer())
        self.list.set_items(items, keep_index=True)


class RowWorkoutPreview(_BriefBase):
    """O treino antes de começar: objetivo, blocos e alvos (ver perennia.ui.brief)."""

    SPORT = "rowing"

    def make_brief(self):
        from perennia.ui.brief import endurance_brief
        return endurance_brief(self.app.db, "rowing", self.wid)

    def start(self) -> None:
        start_session(self.app, replace=True, workout_id=self.wid)



class RowWorkoutEditor(EditScreen):
    def __init__(self, app, wid: str | None):
        super().__init__(app)
        self.wid = wid
        w = rw.workout(app.db, wid) if wid else None
        self.name = w["name"] if w else tr("Novo treino", "New workout")
        self.desc = (w or {}).get("description") or ""
        self.steps: list[rw.Step] = list(w["steps"]) if w else [
            rw.Step("warmup", "time", 300, "power", 50, 65, 4, ""),
            rw.Step("active", "time", 600, "power", 80, 90, 6, ""),
            rw.Step("cooldown", "time", 300, "power", 45, 55, 3, "")]
        self.builtin = bool(w and w["builtin"])
        self.repeat_n = 4
        self._armed = False
        self._saved_state = self._state()

    def _state(self) -> str:
        return repr((self.name, self.desc, [vars(s) for s in self.steps]))

    def has_unsaved(self) -> bool:
        return self._state() != self._saved_state

    def on_save(self) -> bool:
        self._save()
        return True

    def enter(self) -> None:
        a = self.app
        ftp = rw.row_ftp(a.db)
        items = [Item(tr("Nome", "Name"), value=self.name + "▏", data="text:name"),
                 Item(tr("Descrição", "Description"), value=(self.desc or "") + "▏",
                      data="text:desc")]
        for i, s in enumerate(self.steps):
            items.append(Item(f"{i + 1}. {_kind(s.kind)} · {s.duration_text()}",
                              value=s.target_text(ftp),
                              detail=(tr("nível {n}", "level {n}", n=s.resistance)
                                      if s.resistance else tr("resistência livre",
                                                              "free resistance")),
                              action=lambda k=i: a.push(RowStepEditor(a, self, k))))
        items += [Item(tr("+ Adicionar passo", "+ Add step"), action=self._add),
                  Item(tr("Repetir os 2 últimos passos", "Repeat the last 2 steps"),
                       value=f"× {self.repeat_n}", data="cyc:repeat", action=self._repeat,
                       detail=tr("←/→ quantas vezes · Enter repete",
                                 "←/→ how many times · Enter repeats")),
                  Item(tr("Apagar o treino", "Delete the workout"), action=self._delete,
                       enabled=bool(self.wid), button=True),
                  Item(tr("Exportar (.fit)", "Export (.fit)"), action=self._export, button=True),
                  Item(tr("Guardar", "Save"), action=self._save, button=True, primary=True)]
        tot_s, tot_m = rw.totals(self.steps)
        self.chrome.set(tr("Treino de remo", "Rowing workout"),
                        " + ".join(x for x in (hms(tot_s) if tot_s else "",
                                               _m(tot_m) if tot_m else "") if x)
                        + f" · FTP {ftp} W", self.footer())
        self.list.set_items(items, keep_index=True)

    def text_input(self, field: str, text: str) -> None:
        setattr(self, field, getattr(self, field) + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        setattr(self, field, getattr(self, field)[:-1])
        self.enter()

    def cycle(self, field: str, step: int) -> None:
        if field == "repeat":
            self.repeat_n = max(2, min(20, self.repeat_n + (1 if step > 0 else -1)))

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self._field("cyc:") == "repeat" and symbol in (key.ENTER, key.RETURN):
            self._repeat()
            return True
        return super().on_key(symbol, modifiers)

    def _add(self) -> None:
        last = self.steps[-1] if self.steps else rw.Step()
        self.steps.append(rw.Step("active", last.dur_type, last.dur_value, last.target,
                                  last.lo, last.hi, last.resistance, ""))
        self.app.push(RowStepEditor(self.app, self, len(self.steps) - 1))

    def _repeat(self) -> None:
        if len(self.steps) < 2:
            return
        block = self.steps[-2:]
        for _ in range(self.repeat_n - 1):
            self.steps += [rw.Step(**vars(s)) for s in block]
        self.app.message(tr("{n} passos", "{n} steps", n=len(self.steps)))
        self.enter()

    def _save(self) -> None:
        self.wid = rw.save_workout(self.app.db, self.wid, self.name, self.desc, self.steps)
        self._saved_state = self._state()
        leaving = getattr(self, "_leaving", False)
        self.app.pop()
        if not leaving:
            self.app.workout_saved(self.name)

    def _export(self) -> None:
        from perennia.core import fit
        ftp = rw.row_ftp(self.app.db)
        steps = []
        for s in self.steps:
            rng = s.watts_range(ftp)
            steps.append({"name": _kind(s.kind), "seconds": s.dur_value
                          if s.dur_type == "time" else None,
                          "meters": s.dur_value if s.dur_type == "distance" else None,
                          "lo_w": rng[0] if rng else None, "hi_w": rng[1] if rng else None,
                          "intensity": s.kind, "notes": s.cue})
        folder = self.app.data_dir / "workouts"
        folder.mkdir(parents=True, exist_ok=True)
        from perennia.core import naming
        path = folder / f"remo_{naming.clean(self.name) or 'treino'}.fit"
        try:
            fit.write_row_workout(path, self.name, steps)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        self.export_path = path
        self.app.message(tr("Exportado: {p}", "Exported: {p}", p=path))

    def _delete(self) -> None:
        def gone() -> None:
            rw.delete_workout(self.app.db, self.wid)
            self.app.pop(force=True)
        from perennia.ui.builder_screens import DELETE_SUB
        self.app.confirm(tr("Apagar o treino «{n}»?", "Delete the workout «{n}»?", n=self.name),
                         tr(*DELETE_SUB), gone, yes=tr("Apagar", "Delete"))


class RowStepEditor(LiveEditPopup):
    """Um passo do treino de remo, numa janela."""

    def __init__(self, app, editor: RowWorkoutEditor, idx: int):
        self.ed = editor
        self.idx = idx
        super().__init__(app)
        self._start_live()

    def live_get(self):
        return self.ed.steps[self.idx] if self.idx < len(self.ed.steps) else None

    def live_set(self, value) -> None:
        self.ed.steps[self.idx] = value

    @property
    def s(self) -> rw.Step:
        return self.ed.steps[self.idx]

    def enter(self) -> None:
        s = self.s
        ftp = rw.row_ftp(self.app.db)
        dur_val = hms(s.dur_value) if s.dur_type == "time" else _m(s.dur_value)
        items = [Item(tr("Tipo", "Kind"), value=_kind(s.kind), data="cyc:kind"),
                 Item(tr("Duração por", "Duration by"),
                      value=tr("tempo", "time") if s.dur_type == "time"
                      else tr("distância", "distance"), data="cyc:dur_type"),
                 Item(tr("Duração", "Duration"), value=dur_val, data="num:dur_value",
                      detail=tr("←/→ ±10 s ou ±50 m · Shift ±1 min ou ±500 m · mín. 10 s",
                                "←/→ ±10 s or ±50 m · Shift ±1 min or ±500 m · min 10 s")),
                 Item(tr("Alvo", "Target"), value={"none": tr("livre", "free"),
                                                   "pace": tr("ritmo /500 m", "pace /500 m"),
                                                   "power": "% FTP", "spm": "spm"}[s.target],
                      data="cyc:target")]
        if s.target != "none":
            fmt = (lambda v: pace_text(v)) if s.target == "pace" else (
                lambda v: "—" if v is None else f"{v:g}")
            hint = tr("←/→ ±1 s · Shift ±5 s", "←/→ ±1 s · Shift ±5 s") \
                if s.target == "pace" else ""
            items += [Item(tr("Alvo: de", "Target: from"), value=fmt(s.lo), data="num:lo",
                           detail=hint),
                      Item(tr("Alvo: até", "Target: to"), value=fmt(s.hi), data="num:hi",
                           detail=s.target_text(ftp))]
        items += [Item(tr("Resistência (1–15)", "Resistance (1–15)"),
                       value=str(s.resistance) if s.resistance else tr("não mexer", "leave it"),
                       data="num:resistance",
                       detail=tr("a app põe este nível no início do passo",
                                 "the app sets this level at the start of the step")),
                  Item(tr("Mensagem", "Cue"), value=(s.cue or "") + "▏", data="text:cue")]
        self.fit_rows(len(items))
        items += self.live_buttons([Item(tr("Remover o passo", "Remove the step"),
                                         action=self._remove, button=True)])
        self.chrome.set(tr("Passo {n}", "Step {n}", n=self.idx + 1), "", self.footer())
        self.list.set_items(items, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        s = self.s
        if field == "kind":
            ks = list(rw.STEP_KINDS)
            s.kind = ks[(ks.index(s.kind) + step) % len(ks)]
        elif field == "dur_type":
            s.dur_type = "distance" if s.dur_type == "time" else "time"
            s.dur_value = 500 if s.dur_type == "distance" else 300
        elif field == "target":
            ts = list(rw.TARGETS)
            s.target = ts[(ts.index(s.target) + step) % len(ts)]
            ftp = rw.row_ftp(self.app.db)
            s.lo, s.hi = {"pace": (round(rw.pace_from_watts(ftp)) + 4,
                                   round(rw.pace_from_watts(ftp))),
                          "power": (85, 95), "spm": (22, 24), "none": (None, None)}[s.target]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        s = self.s
        if field == "dur_value":
            d = (60 if big else 10) if s.dur_type == "time" else (500 if big else 50)
            s.dur_value = max(rw.MIN_STEP_S if s.dur_type == "time" else rw.MIN_STEP_M,
                              s.dur_value + steps * d)
        elif field == "resistance":
            cur = s.resistance or 5
            s.resistance = max(1, min(15, cur + steps * (3 if big else 1)))
        elif field in ("lo", "hi"):
            cur = getattr(s, field) or s.lo or 0
            d = (5 if big else 1)
            setattr(s, field, max(0, cur + steps * d))

    def num_set(self, field: str, value: float | None) -> None:
        s = self.s
        if field == "dur_value":
            if value is not None:
                # escrito: minutos no tempo (ex.: 2,5), metros na distância
                s.dur_value = max(rw.MIN_STEP_S, value * 60) if s.dur_type == "time" \
                    else max(rw.MIN_STEP_M, value)
        elif field == "resistance":
            s.resistance = None if value is None else max(1, min(15, int(value)))
        else:
            setattr(s, field, value)

    def text_input(self, field: str, text: str) -> None:
        self.s.cue += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.s.cue = self.s.cue[:-1]
        self.enter()

    def _remove(self) -> None:
        del self.ed.steps[self.idx]
        self._snap = None
        self.app.pop(force=True)

    def leave(self) -> None:
        self.s.clean() if self.idx < len(self.ed.steps) else None


# ================================================================ Challenge


class RowChallengeMenu(Screen):
    def enter(self) -> None:
        a = self.app
        items = []
        for k in rw.ROW_GAMES:
            desc = tr("Corrida de 500 m a 5 km contra bots ao teu nível.",
                      "A 500 m to 5 km race against bots at your level.") if k == "regatta" \
                else t(f"game.{k}.desc")
            items.append(Item(rw.game_title(k), detail=desc,
                              action=lambda kk=k: a.push(RowGameSetup(a, kk))))
        self.chrome.set("Challenge · " + t("home.rowing"),
                        tr("Tudo relativo à tua FTP do remo ({w} W)",
                           "All relative to your rowing FTP ({w} W)", w=rw.row_ftp(a.db)),
                        self.footer())
        self.list.set_items(items, keep_index=True)


class RowGameSetup(EditScreen):
    BOT_OPTIONS = (1, 3, 5, 7)

    def __init__(self, app, game_key: str):
        super().__init__(app)
        self.key = game_key
        if game_key == "regatta":
            self.durations = rw.REGATTA_DISTANCES
            self.amount = 2000
        else:
            from perennia.core import games as games_mod
            cls = games_mod.CLASSES[game_key]
            self.durations = cls.durations
            self.amount = cls.default_minutes
        self.bots = 1 if game_key == "tug" else 5 if game_key == "regatta" else 4

    def enter(self) -> None:
        items = [Item(t("mode.start"), action=self._start)]
        if self.key == "regatta":
            items.append(Item(tr("Distância", "Distance"), value=_m(self.amount),
                              data="cyc:amount"))
        else:
            items.append(Item(tr("Duração", "Duration"), value=f"{self.amount} min",
                              data="cyc:amount"))
        if self.key not in ("tug",):
            items.append(Item(tr("Adversários (bots)", "Opponents (bots)"), value=str(self.bots),
                              data="cyc:bots"))
        items.append(Item(tr("Resistência", "Resistance"), enabled=False,
                          detail=tr("Escolhes tu (+/−); o alvo é potência, mostrada também em "
                                    "ritmo /500 m.", "You choose (+/−); the target is power, "
                                    "also shown as pace /500 m.")))
        self.chrome.set(rw.game_title(self.key), f"FTP {rw.row_ftp(self.app.db)} W",
                        self.footer())
        self.list.set_items(items, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        if field == "amount":
            ds = list(self.durations)
            i = ds.index(self.amount) if self.amount in ds else 0
            self.amount = ds[(i + step) % len(ds)]
        elif field == "bots":
            bs = list(self.BOT_OPTIONS)
            i = bs.index(self.bots) if self.bots in bs else 0
            self.bots = bs[(i + step) % len(bs)]

    def spec(self) -> dict:
        out = {"key": self.key, "bots": self.bots, "seed": int(time.time()) % 100000}
        if self.key == "regatta":
            out["distance"] = self.amount
        else:
            out["minutes"] = self.amount
        return out

    def _start(self) -> None:
        start_session(self.app, replace=True, game_spec=self.spec())


# ============================================================ histórico/estat.


class RowHistory(Screen):
    def enter(self) -> None:
        a = self.app
        items = []
        for s in rw.sessions(a.db):
            items.append(Item(f"{str(s['started_at'])[:16].replace('T', ' ')}  {_pretty(s['name'])}",
                              value=_m(s["distance_m"]),
                              detail=f"{hms(s['moving_s'] or 0)} · "
                                     f"{pace_text(s['avg_pace_s'])} /500 m"
                                     + (f" · {s['avg_power_w']:.0f} W" if s["avg_power_w"] else "")
                                     + (f" · {s['avg_hr']:.0f} bpm" if s["avg_hr"] else ""),
                              action=lambda sid=s["id"]: a.push(RowSessionDetail(a, sid))))
        if not items:
            items.append(Item(tr("Ainda sem sessões de remo", "No rowing sessions yet"),
                              enabled=False))
        self.chrome.set(tr("Histórico do remo", "Rowing history"), "", self.footer())
        self.list.set_items(items, keep_index=True)


def RowSessionDetail(app, sid: str):                      # noqa: N802 — compatibilidade
    """Uma sessão de remo do histórico: a análise em separadores."""
    from perennia.ui.session_analysis import SessionAnalysis
    return SessionAnalysis(app, "row", sid)


def RowStatsScreen(app):                     # noqa: N802 — compatibilidade
    from perennia.ui.stats_screens import SportStatsScreen
    return SportStatsScreen(app, "rowing")


def _pretty(name) -> str:
    from perennia.core.naming import pretty
    return pretty(name)


def _feedback():
    from perennia.ui import feedback_screens
    return feedback_screens
