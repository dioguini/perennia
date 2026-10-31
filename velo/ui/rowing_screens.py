"""Remo: menu, sessão (com campos configuráveis), treinos e construtor,
Challenge, histórico, estatísticas e a máquina de remo."""
from __future__ import annotations

import threading
import time

import pyglet
from pyglet.window import key

from velo.core import rowing as rw
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.gfx.compat import label as make_label
from velo.io import rower as rower_io
from velo.io.rower import pace_text
from velo.ui.app import BOARD_W, Screen, SportHub, StartOptions
from velo.ui.challenge_screens import train_items
from velo.ui.sport_screens import EditScreen
from velo.ui.brief import BriefScreen as _BriefBase
from velo.ui.widgets import (ACCENT, BAD, BoardPanel, Chart, DIM, GOOD, P, PANEL, TEXT, Item,
                             SessionClock)


def _m(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v / 1000:.2f} km" if v >= 10000 else f"{v:.0f} m"


# ======================================================== campos do ecrã

# Os campos do ecrã de remo vivem em velo.core.layouts (o editor de ecrãs usa-os).
from velo.core.layouts import ROW_DEFAULT as DEFAULT_FIELDS  # noqa: E402
from velo.core.layouts import ROW_FIELDS as FIELDS  # noqa: E402

N_FIELDS = 12          # quadrados por página (3 filas × 4)
PAGES = 2              # V muda de página


def field_names(db) -> list[str]:
    total = N_FIELDS * PAGES
    v = [x for x in (db.get("row_fields") or []) if x in FIELDS][:total]
    return v + DEFAULT_FIELDS[len(v):total]


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

    def subtitle(self) -> str:
        a = self.app
        b = rw.bests(a.db)
        machine = getattr(a, "rower", None)
        status = machine.name if machine is not None else tr("nenhuma máquina ligada",
                                                             "no machine connected")
        return tr("Melhor ritmo {p} · {n} sessões · {d} no total · {m}",
                  "Best pace {p} · {n} sessions · {d} total · {m}",
                  p=pace_text(b.get("pace")), n=b.get("n") or 0, d=_m(b.get("total") or 0),
                  m=status)

    def enter(self) -> None:
        rw.link_tests(self.app.db)
        super().enter()

    def items_train(self) -> list[Item]:
        # a máquina de remo liga-se em Dispositivos; a FTP do remo está nas
        # Definições (Atleta)
        a = self.app
        return train_items(a, "rowing", session=Item(
            tr("Sessão de treino", "Training session"),
            detail=tr("Remo livre, com voltas manuais (L)", "Free row, with manual laps (L)"),
            action=lambda: self._start({}))) + [
            Item(tr("Campos do ecrã de remo", "Rowing screen fields"),
                 action=lambda: a.push(RowFieldsScreen(a)))]

    def items_builder(self) -> list[Item]:
        a = self.app
        from velo.ui import builder_screens as bs
        items = [Item(tr("+ Novo treino (arrastar blocos)", "+ New workout (drag blocks)"),
                      action=lambda: a.push(bs.BlockBuilder(a, "rowing", None)))]
        for w in rw.workouts(a.db):
            dur = " + ".join(x for x in (hms(w["total_s"]) if w["total_s"] else "",
                                         _m(w["total_m"]) if w["total_m"] else "") if x)
            items.append(Item(w["name"], value=dur,
                              detail=tr("Enter: blocos · P: passos (resistência, voga)",
                                        "Enter: blocks · P: steps (resistance, rate)"),
                              action=lambda wid=w["id"]: a.push(bs.BlockBuilder(a, "rowing",
                                                                                wid)),
                              data=("row_workout", w["id"])))
        return items

    def items_library(self) -> list[Item]:
        a = self.app
        out = []
        for w in rw.workouts(a.db):
            dur = " + ".join(x for x in (hms(w["total_s"]) if w["total_s"] else "",
                                         _m(w["total_m"]) if w["total_m"] else "") if x)
            out.append(Item(w["name"], value=dur, detail=w["description"] or "",
                            action=lambda wid=w["id"]: a.push(RowWorkoutPreview(a, wid))))
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
        return out

    def items_stats(self) -> list[Item]:
        a = self.app
        b = rw.bests(a.db)
        return super().items_stats() + [
            Item(tr("Sessões", "Sessions"), value=str(b.get("n") or 0), enabled=False),
            Item(tr("Distância total", "Total distance"), value=_m(b.get("total") or 0),
                 enabled=False),
            Item(tr("Melhor ritmo", "Best pace"), value=pace_text(b.get("pace")),
                 enabled=False),
            Item(tr("Maior distância", "Longest"), value=_m(b.get("dist")), enabled=False),
            Item(tr("Mais potência média", "Best avg power"),
                 value=f"{b['w']:.0f} W" if b.get("w") else "—", enabled=False)]

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and isinstance(item.data, tuple) and item.data[0] == "row_workout" \
                and symbol == key.P:
            self.app.push(RowWorkoutEditor(self.app, item.data[1]))
            return True
        return super().on_key(symbol, modifiers)

    def _start(self, kw: dict) -> None:
        start_session(self.app, **kw)


def _health():
    from velo.ui import health_screens
    return health_screens


def start_session(app, replace: bool = False, **kw) -> None:
    """Abre a sessão, ou pede a máquina primeiro."""
    if getattr(app, "rower", None) is None:
        app.message(tr("Liga primeiro a máquina de remo (ou usa a simulada).",
                       "Connect the rowing machine first (or use the simulated one)."))
        app.push(RowerDeviceScreen(app, then=kw))
        return
    if kw.get("resume") is not None:
        scr = RowingSessionScreen(app, **kw)
        app.replace(scr) if replace else app.push(scr)
        return
    title = tr("Remo", "Rowing")
    if kw.get("workout_id"):
        w = rw.workout(app.db, kw["workout_id"])
        title = w["name"] if w else title
    elif kw.get("game_spec"):
        title = rw.game_title(kw["game_spec"]["key"])
    elif kw.get("protocol"):
        title = tr("Teste", "Test")

    def go(autolap: dict, _opts: dict) -> None:
        app.replace(RowingSessionScreen(app, autolap=autolap, **kw))
    opts = StartOptions(app, "rowing", title, go,
                        lines=[tr("Máquina: {n}", "Machine: {n}", n=app.rower.name)])
    app.replace(opts) if replace else app.push(opts)


# ================================================================== sessão


class RowingSessionScreen(Screen):
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
        self.page = 0
        self.session = self.engine           # o fecho da aplicação trata dela
        self.confirming = False
        self.toast = ""
        self._toast_until = 0.0
        self.names = field_names(a.db)
        b = self.batch = pyglet.graphics.Batch()
        self.cells = []
        for _ in range(N_FIELDS):
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
        self.clock = SessionClock(app.window, batch=b)
        self.chrome.title.font_size = 18
        self._layout()
        for kind, data in self.engine.drain_events():
            self._event(kind, data)

    # ---------------------------------------------------------------- layout

    def _list_width(self, w: int) -> int:
        return 300

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        left = 48
        right = w - 48 - BOARD_W - 24
        top = h - 128
        cols = 4
        gap = 10
        cw = (right - left - gap * (cols - 1)) / cols
        ch = max(74, min(108, (h - 390) / 3))
        for i, (bg, cap, val) in enumerate(self.cells):
            r, c = divmod(i, cols)
            x = left + c * (cw + gap)
            y = top - r * (ch + gap)
            bg.x, bg.y, bg.width, bg.height = x, y - ch, cw, ch
            cap.x, cap.y = x + 12, y - 8
            val.x, val.y = x + 12, y - 26
            val.font_size = 30 if cw > 220 and ch > 90 else (24 if cw > 150 else 20)
            self._val_size = val.font_size
            cap.font_size = 11 if cw > 170 else 9
        y2 = top - 3 * (ch + gap) - 4
        self.status.x, self.status.y = left, y2
        self.toast_label.x, self.toast_label.y = left + 420, y2
        self.plan.x, self.plan.y = left, y2 - 30
        self.plan.width = int(right - left)
        self.track.x, self.track.y, self.track.width = left, 70, right - left
        self.bar.x, self.bar.y = left, 70
        self._bar_w = right - left
        self.list.y = -1000                                 # a lista fica escondida
        self.clock.layout()
        if self.board_panel is not None:
            self.board_panel.layout(w - 48 - BOARD_W, h - 124, BOARD_W)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()

    def footer(self) -> str:
        return tr("+/− resistência · L volta · V outra página · P pausa · Esc terminar",
                  "+/− resistance · L lap · V other page · P pause · Esc finish")

    # ------------------------------------------------------------- quadro

    def side_board(self):
        e = self.engine
        if e.game is not None:
            return e.game.board(rw.game_history(e.db, e.game))
        from velo.core.boards import Board, Row
        rows = [Row(lp.no, f"{_m(lp.distance_m)} · {pace_text(lp.avg_pace_s)}",
                    hms((lp.end_t or 0) - lp.start_t)) for lp in e.laps[-6:]
                if lp.trigger != "start" or lp.distance_m > 0]
        return Board(tr("Voltas", "Laps"), rows, subtitle=e.title,
                     empty=tr("L marca uma volta", "L marks a lap"))

    # ---------------------------------------------------------------- ciclo

    def enter(self) -> None:
        e = self.engine
        if self.confirming:
            self.list.y = self.app.window.height - 330
            self.chrome.set(tr("Terminar a sessão?", "Finish the session?"),
                            f"{_m(e.distance_m)} · {hms(e.t)}", self.footer())
            self.list.set_items([Item(t("str.confirm_no"), action=self._cancel),
                                 Item(t("str.confirm_yes"), action=self._finish),
                                 Item(tr("Terminar sem guardar", "Finish without saving"),
                                      action=self._discard)])
            return
        self.list.y = -1000
        self.list.set_items([])
        self.chrome.set(e.title, f"FTP {e.ftp} W · {getattr(e.rower, 'name', '')}",
                        self.footer())

    def update(self, dt: float) -> None:
        a = self.app
        a.hub.tick(dt)
        e = self.engine
        e.update(dt)
        for kind, data in e.drain_events():
            self._event(kind, data)
        lap = e.lap_elapsed_s if e._lap is not None else 0.0
        self.clock.set(e.t, tr("volta {t}", "lap {t}", t=hms(lap)) + (
            f" · {tr('passo', 'step')} {e.workout.remaining_text()}"
            if e.workout is not None and e.workout.step is not None else ""))
        for i, (bg, cap, val) in enumerate(self.cells):
            name = self.names[self.page * N_FIELDS + i]
            pt, en = FIELDS[name]
            cap.text = tr(pt, en).upper()
            val.text = field_value(e, name)
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
        if self.board_panel is not None and int(e.t) % 2 == 0:
            self.refresh_board()

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
        return tr("REMO LIVRE", "FREE ROW")

    def _plan_text(self) -> str:
        e = self.engine
        if e.workout is not None and e.workout.step is not None:
            s = e.workout.step
            lines = [f"{_kind(s.kind)} · {s.duration_text()}"
                     f" · {tr('alvo', 'target')} {s.target_text(e.ftp)}"
                     + (f" · {tr('nível', 'level')} {s.resistance}" if s.resistance else "")]
            if getattr(self, "_goal_line", None) is None:
                from velo.ui.brief import GoalLine
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
            from velo.core import fitness_tests as ft
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
            "lap": tr("Volta {n} · {d} · {p}", "Lap {n} · {d} · {p}", n=data.get("no"),
                      d=_m(data.get("distance_m")), p=pace_text(data.get("avg_pace_s"))),
            "workout_done": tr("Treino concluído!", "Workout done!"),
            "test_done": tr("Teste concluído!", "Test done!"),
            "game_over": tr("Fim do jogo", "Game over"),
        }.get(kind)
        if kind == "step" and data.get("cue"):
            msg = data["cue"]
        if msg:
            self.toast = msg
            self._toast_until = time.monotonic() + 3.0

    # ------------------------------------------------------------- teclas

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.confirming:
            if symbol == key.ESCAPE:
                self._cancel()
                return True
            return super().on_key(symbol, modifiers)
        e = self.engine
        if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD, getattr(key, "PAGEUP", -1)):
            e.adjust_resistance(+1)
            return True
        if symbol in (key.MINUS, key.NUM_SUBTRACT, getattr(key, "PAGEDOWN", -1)):
            e.adjust_resistance(-1)
            return True
        if symbol == key.L:
            e.lap("manual")
            self.refresh_board()
            return True
        if symbol == key.V:
            self.page = (self.page + 1) % PAGES
            return True
        if symbol == key.P:
            e.toggle_pause()
            return True
        if symbol in (key.ESCAPE, key.F10):
            self.confirming = True
            self.enter()
            return True
        return True

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.confirming = True
            self.enter()
            return True
        return self.list.on_mouse_press(x, y)

    def _cancel(self) -> None:
        self.confirming = False
        self.enter()

    def _discard(self) -> None:
        self.engine.discard()
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

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
        if self.confirming:
            self.list.draw()
            return
        self.batch.draw()
        if self.board_panel is not None:
            self.board_panel.draw()
        if self.back_button is not None:
            self.back_button.draw()


def _kind(k: str) -> str:
    return {"warmup": tr("Aquecimento", "Warm-up"), "active": tr("Trabalho", "Work"),
            "rest": tr("Descanso", "Rest"), "cooldown": tr("Retorno à calma", "Cool-down")
            }.get(k, k)


# ================================================================== resumo


class RowSummaryScreen(Screen):
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
            from velo.core import fitness_tests as ft
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
        if r.get("fit_path"):
            add(".fit", r.get("name") or "", str(r["fit_path"]))
        items.append(Item(tr("Voltar ao remo", "Back to rowing"), action=self.app.pop))
        self.chrome.set(r.get("title") or t("home.rowing"), r.get("name") or "", self.footer())
        fb_item = _feedback().summary_item(self.app, "row", self.result.get("session_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
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
    """O treino antes de começar: objetivo, blocos e alvos (ver velo.ui.brief)."""

    SPORT = "rowing"

    def make_brief(self):
        from velo.ui.brief import endurance_brief
        return endurance_brief(self.app.db, "rowing", self.wid)

    def start(self) -> None:
        start_session(self.app, replace=True, workout_id=self.wid)

    def extra_actions(self) -> list[Item]:
        a = self.app
        from velo.ui.builder_screens import BlockBuilder
        return [Item(tr("Editar", "Edit"), action=lambda: a.push(RowWorkoutEditor(a, self.wid))),
                Item(tr("Abrir no construtor", "Open in the builder"),
                     action=lambda: a.push(BlockBuilder(a, "rowing", self.wid)))]


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
        self.app.message(tr("Treino guardado", "Workout saved"))
        self.app.pop()

    def _export(self) -> None:
        from velo.core import fit
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
        from velo.core import naming
        path = folder / f"remo_{naming.clean(self.name) or 'treino'}.fit"
        try:
            fit.write_row_workout(path, self.name, steps)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        self.export_path = path
        self.app.message(tr("Exportado: {p}", "Exported: {p}", p=path))

    def _delete(self) -> None:
        if not self._armed:
            self._armed = True
            self.app.message(tr("Escolhe outra vez para apagar.", "Choose again to delete."))
            return
        rw.delete_workout(self.app.db, self.wid)
        self.app.pop(force=True)


class RowStepEditor(EditScreen):
    def __init__(self, app, editor: RowWorkoutEditor, idx: int):
        super().__init__(app)
        self.ed = editor
        self.idx = idx

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
                  Item(tr("Mensagem", "Cue"), value=(s.cue or "") + "▏", data="text:cue"),
                  Item(tr("Remover o passo", "Remove the step"), action=self._remove, button=True),
                  Item(tr("Feito", "Done"), action=self.app.pop, button=True, primary=True)]
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
        self.app.pop()

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
            from velo.core import games as games_mod
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


class RowSessionDetail(Screen):
    def __init__(self, app, sid: str):
        super().__init__(app)
        self.sid = sid

    def enter(self) -> None:
        a = self.app
        s = a.db.conn.execute("SELECT * FROM row_sessions WHERE id = ?", (self.sid,)).fetchone()
        if s is None:
            a.pop()
            return
        items = [Item(tr("Distância", "Distance"), value=_m(s["distance_m"]), enabled=False),
                 Item(tr("Tempo", "Time"), value=hms(s["moving_s"] or 0), enabled=False),
                 Item(tr("Ritmo médio", "Avg pace"), value=pace_text(s["avg_pace_s"]),
                      enabled=False),
                 Item(tr("Potência média", "Avg power"),
                      value=f"{s['avg_power_w']:.0f} W" if s["avg_power_w"] else "—",
                      enabled=False),
                 Item(tr("Voga média", "Avg stroke rate"),
                      value=f"{s['avg_spm']:.1f}" if s["avg_spm"] else "—", enabled=False),
                 Item(tr("Carga", "Load"), value=f"{s['load']:.0f}" if s["load"] else "—",
                      enabled=False)]
        for lp in rw.session_laps(a.db, self.sid):
            if not lp["distance_m"]:
                continue
            items.append(Item(f"  {tr('Volta', 'Lap')} {lp['lap_no']}",
                              value=hms((lp["end_t"] or 0) - (lp["start_t"] or 0)),
                              detail=f"{_m(lp['distance_m'])} · {pace_text(lp['avg_pace_s'])}"
                                     + (f" · {lp['avg_power_w']:.0f} W" if lp["avg_power_w"]
                                        else ""), enabled=False))
        if s["fit_path"]:
            items.append(Item(".fit", value=s["name"] or "", detail=s["fit_path"], enabled=False))
        self.chrome.set(s["name"] or t("home.rowing"), str(s["started_at"])[:16], self.footer())
        fb_item = _feedback().summary_item(self.app, "row", self.sid)
        if fb_item is not None:
            items.insert(0, fb_item)
        self.list.set_items(items, keep_index=True)


def RowStatsScreen(app):                     # noqa: N802 — compatibilidade
    from velo.ui.stats_screens import SportStatsScreen
    return SportStatsScreen(app, "rowing")


class RowFieldsScreen(EditScreen):
    TABBED = True

    def tab_labels(self) -> list[str]:
        return [tr("Página {n}", "Page {n}", n=i + 1) for i in range(PAGES)]

    def enter(self) -> None:
        names = field_names(self.app.db)
        off = self.tab * N_FIELDS
        items = [Item(tr("Campo {n}", "Field {n}", n=i + 1), value=tr(*FIELDS[n]),
                      data=f"cyc:{off + i}") for i, n in enumerate(names[off:off + N_FIELDS])]
        items.append(Item(tr("Repor os campos", "Reset the fields"), action=self._reset))
        self.chrome.set(tr("Campos do ecrã de remo", "Rowing screen fields"),
                        tr("←/→ muda o que cada quadrado mostra",
                           "←/→ changes what each box shows"), self.footer())
        self.list.set_items(items, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        names = field_names(self.app.db)
        keys = list(FIELDS)
        i = int(field)
        names[i] = keys[(keys.index(names[i]) + step) % len(keys)]
        self.app.db.set("row_fields", names)

    def _reset(self) -> None:
        self.app.db.set("row_fields", list(DEFAULT_FIELDS))
        self.enter()


# ============================================================= máquina


class RowerDeviceScreen(Screen):
    def __init__(self, app, then: dict | None = None):
        super().__init__(app)
        self.then = then
        self.found: list[tuple[str, str, str]] = []
        self.scanning = False
        self._result: list | None = None
        self._connecting: threading.Thread | None = None
        self._conn_result: tuple | None = None
        self.note = ""

    def enter(self) -> None:
        a = self.app
        cur = getattr(a, "rower", None)
        items = []
        if cur is not None:
            d = cur.data() if hasattr(cur, "data") else None
            live = ""
            if d is not None:
                live = " · ".join(x for x in (
                    f"{d.spm:.0f} spm" if d.spm else "", pace_text(d.pace_s) if d.pace_s else "",
                    tr("nível {n}", "level {n}", n=d.resistance) if d.resistance else "") if x)
            items.append(Item(f"✓ {cur.name}", value=cur.protocol.upper(),
                              detail=live or tr("ligada", "connected")))
            items.append(Item(tr("Desligar", "Disconnect"), action=self._disconnect))
            if self.then is not None:
                items.insert(0, Item(tr("▶ Continuar para a sessão", "▶ Go to the session"),
                                     action=self._go))
        items.append(Item(tr("Procurar máquina de remo (Bluetooth)",
                             "Search for a rowing machine (Bluetooth)") if not self.scanning
                          else tr("A procurar…", "Searching…"), action=self._scan,
                          enabled=not self.scanning,
                          detail=tr("Domyos (ex.: Rowing 500B) ou FTMS (ex.: Concept2 PM5)",
                                    "Domyos (e.g. Rowing 500B) or FTMS (e.g. Concept2 PM5)")))
        for addr, name, proto in self.found:
            items.append(Item(name, value=proto.upper(), detail=addr,
                              action=lambda ad=addr, n=name, p=proto: self._connect(ad, n, p)))
        if cur is None or cur.protocol != "sim":
            items.append(Item(tr("Usar a máquina simulada", "Use the simulated machine"),
                              action=self._sim))
        items.append(Item(tr("A FC", "Heart rate"), enabled=False,
                          detail=tr("Vem da banda ou do relógio (Dispositivos); senão, da "
                                    "máquina.", "From the strap or the watch (Devices); "
                                    "otherwise from the machine.")))
        self.chrome.set(tr("Máquina de remo", "Rowing machine"), self.note, self.footer())
        self.list.set_items(items, keep_index=True)

    def update(self, dt: float) -> None:
        if self.scanning and self._result is not None:
            self.found, self._result, self.scanning = self._result, None, False
            self.note = tr("{n} encontradas", "{n} found", n=len(self.found)) if self.found \
                else tr("Nenhuma encontrada", "None found")
            self.enter()
        if self._conn_result is not None:
            ok, sensor = self._conn_result
            self._conn_result = None
            if ok:
                self.app.set_rower(sensor)
                self.note = tr("Ligada: {n}", "Connected: {n}", n=sensor.name)
            else:
                self.note = tr("Não foi possível ligar", "Could not connect")
            self.enter()

    def _scan(self) -> None:
        from velo.io import ble
        if not ble.bleak_available():
            self.note = tr("Falta a biblioteca bleak (pip install bleak).",
                           "The bleak library is missing (pip install bleak).")
            self.enter()
            return
        self.scanning = True
        self.enter()

        def work():
            try:
                self._result = rower_io.scan_rowers()
            except Exception:
                self._result = []
        threading.Thread(target=work, daemon=True).start()

    def _connect(self, address: str, name: str, proto: str) -> None:
        sensor = rower_io.RowerSensor(address, name, proto)

        def work():
            try:
                self._conn_result = (sensor.connect(), sensor)
            except Exception:
                self._conn_result = (False, sensor)
        threading.Thread(target=work, daemon=True).start()
        self.note = tr("A ligar…", "Connecting…")
        self.enter()

    def _sim(self) -> None:
        self.app.set_rower(rower_io.SimulatedRower())
        self.note = tr("Máquina simulada ligada", "Simulated machine connected")
        self.enter()

    def _disconnect(self) -> None:
        self.app.set_rower(None)
        self.enter()

    def _go(self) -> None:
        kw = self.then or {}
        self.then = None
        start_session(self.app, replace=True, **kw)


def _pretty(name) -> str:
    from velo.core.naming import pretty
    return pretty(name)


def _feedback():
    from velo.ui import feedback_screens
    return feedback_screens
