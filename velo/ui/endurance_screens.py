"""Corrida e natação: menu por separadores, sessão, resumo e histórico."""
from __future__ import annotations

import time

import pyglet
from pyglet.window import key

from velo.core import endurance as en
from velo.core import intensity as it
from velo.core import sports as sp
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.gfx.compat import label as make_label
from velo.ui.app import BOARD_W, Screen, SportHub, StartOptions
from velo.ui.brief import BriefScreen, endurance_brief
from velo.ui.widgets import ACCENT, DIM, GOOD, PANEL, TEXT, Item, SessionClock


def _m(v) -> str:
    if not v:
        return "—"
    return f"{v / 1000:.2f} km" if v >= 1000 else f"{v:.0f} m"


def pace_unit(sport: str) -> str:
    return "/km" if sport == "running" else "/100 m"


def start(app, sport: str, workout_id: str | None = None, replace: bool = False) -> None:
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
    scr = StartOptions(app, sport, title, go, lines=lines, options=opts)
    app.replace(scr) if replace else app.push(scr)


class EnduranceHub(SportHub):
    def __init__(self, app, sport: str):
        self.SPORT = sport
        super().__init__(app)

    def subtitle(self) -> str:
        db = self.app.db
        if self.SPORT == "running":
            return tr("Ritmo de limiar {p} /km (nas Definições)",
                      "Threshold pace {p} /km (in Settings)",
                      p=hms(float(db.get("run_threshold_pace_s", 300))))
        return tr("Ritmo crítico {p} /100 m (nas Definições)", "CSS {p} /100 m (in Settings)",
                  p=hms(float(db.get("swim_css_s", 120))))

    def items_train(self) -> list[Item]:
        from velo.ui.challenge_screens import train_items
        a = self.app
        free = tr("Corrida livre", "Free run") if self.SPORT == "running" else \
            tr("Natação livre", "Free swim")
        return train_items(a, self.SPORT, Item(
            tr("Sessão de treino", "Training session"),
            detail=free + " · " + tr("sem plano: tempo, distância, voltas e FC",
                                     "no plan: time, distance, laps and HR"),
            action=lambda: start(a, self.SPORT)))

    def items_builder(self) -> list[Item]:
        a = self.app
        from velo.ui import builder_screens as bs
        items = [Item(tr("+ Novo treino (arrastar blocos)", "+ New workout (drag blocks)"),
                      action=lambda: a.push(bs.BlockBuilder(a, self.SPORT, None)))]
        for w in en.workouts(a.db, self.SPORT):
            items.append(Item(w["name"], value=self._dur(w),
                              detail=it.mode_name(w["mode"]) + " · " + (w["description"] or ""),
                              action=lambda wid=w["id"]: a.push(
                                  bs.BlockBuilder(a, self.SPORT, wid))))
        return items

    def _dur(self, w: dict) -> str:
        return " + ".join(x for x in (hms(w["total_s"]) if w["total_s"] else "",
                                      _m(w["total_m"]) if w["total_m"] else "") if x)

    def items_library(self) -> list[Item]:
        a = self.app
        return [Item(w["name"], value=self._dur(w), detail=w["description"] or "",
                     action=lambda wid=w["id"]: a.push(EndurancePreview(a, self.SPORT, wid)))
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
                for s in en.sessions(a.db, self.SPORT)]

    def items_stats(self) -> list[Item]:
        ss = en.sessions(self.app.db, self.SPORT, 1000)
        dist = sum(s["distance_m"] or 0 for s in ss)
        hours = sum(s["moving_s"] or 0 for s in ss) / 3600
        best = min((s["avg_pace_s"] for s in ss if s["avg_pace_s"]), default=None)
        return super().items_stats() + [
            Item(tr("Sessões", "Sessions"), value=str(len(ss)), enabled=False),
            Item(tr("Distância total", "Total distance"), value=_m(dist), enabled=False),
            Item(tr("Horas", "Hours"), value=f"{hours:.1f}", enabled=False),
            Item(tr("Melhor ritmo médio", "Best avg pace"),
                 value=(hms(best) + " " + pace_unit(self.SPORT)) if best else "—",
                 enabled=False)]


def _health():
    from velo.ui import health_screens
    return health_screens


class EndurancePreview(BriefScreen):
    """O treino antes de começar: objetivo, blocos e alvos (ver velo.ui.brief)."""

    def __init__(self, app, sport: str, wid: str):
        self.SPORT, self.sport = sport, sport
        super().__init__(app, wid)

    def make_brief(self):
        return endurance_brief(self.app.db, self.sport, self.wid)

    def start(self) -> None:
        start(self.app, self.sport, self.wid, replace=True)

    def extra_actions(self) -> list[Item]:
        a = self.app
        from velo.ui.builder_screens import BlockBuilder
        return [Item(tr("Abrir no construtor", "Open in the builder"),
                     action=lambda: a.push(BlockBuilder(a, self.sport, self.wid)))]


class EnduranceSession(Screen):
    AGENT = False
    IN_SESSION = True

    def __init__(self, app, sport: str, workout_id: str | None = None,
                 autolap: dict | None = None, pool_m: float = 25.0, speed_kmh: float = 10.0,
                 resume: dict | None = None):
        super().__init__(app)
        cfg = (resume or {}).get("config", {})
        self.engine = en.EnduranceEngine(
            app.db, app.db.athlete(), cfg.get("sport", sport), sensors=app.hub,
            workout_id=workout_id or cfg.get("workout_id"),
            autolap=autolap if resume is None else cfg.get("autolap"),
            pool_m=cfg.get("pool_m", pool_m), out_dir=app.data_dir / "endurance", resume=resume)
        if resume is None and self.engine.sport == "running":
            self.engine.set_speed(speed_kmh)
        self.session = self.engine
        self.confirming = False
        self.typing: str | None = None
        self.toast = ""
        self._toast_until = 0.0
        b = self.batch = pyglet.graphics.Batch()
        self.clock = SessionClock(app.window, batch=b)
        self.cells = []
        for _ in range(8):
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
        self.chrome.title.font_size = 18
        self._layout()

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        left, right, top = 48, w - 48, h - 128
        cols, gap = 4, 10
        cw = (right - left - gap * (cols - 1)) / cols
        ch = max(80, min(116, (h - 360) / 2))
        for i, (bg, cap, val) in enumerate(self.cells):
            r, c = divmod(i, cols)
            x, y = left + c * (cw + gap), top - r * (ch + gap)
            bg.x, bg.y, bg.width, bg.height = x, y - ch, cw, ch
            cap.x, cap.y = x + 12, y - 8
            val.x, val.y = x + 12, y - 28
        y2 = top - 2 * (ch + gap) - 6
        self.status.x, self.status.y = left, y2
        self.toast_label.x, self.toast_label.y = left + 460, y2
        self.plan.x, self.plan.y, self.plan.width = left, y2 - 28, int(right - left)
        self.list.y = -1000
        self.clock.layout()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()

    def footer(self) -> str:
        e = self.engine
        if e.sport == "running":
            return tr("Espaço começa · +/− velocidade · T total do visor · L volta · P pausa · "
                      "Esc terminar", "Space starts · +/− speed · T display total · L lap · "
                      "P pause · Esc finish")
        return tr("Espaço começa · + piscina (− corrige) · L volta · P pausa · Esc terminar",
                  "Space starts · + length (− corrects) · L lap · P pause · Esc finish")

    def enter(self) -> None:
        e = self.engine
        if self.confirming:
            self.list.y = self.app.window.height - 330
            self.chrome.set(tr("Terminar a sessão?", "Finish the session?"),
                            f"{_m(e.distance_m)} · {hms(e.t)}", "")
            self.list.set_items([Item(t("str.confirm_no"), action=self._cancel),
                                 Item(t("str.confirm_yes"), action=self._finish),
                                 Item(tr("Terminar sem guardar", "Finish without saving"),
                                      action=self._discard)])
            return
        self.list.y = -1000
        self.list.set_items([])
        self.chrome.set(e.title, sp.name(e.sport), self.footer())

    def cells_data(self) -> list[tuple[str, str]]:
        """Os 8 quadrados, pela ordem escolhida no editor do ecrã (Definições)."""
        from velo.core import layouts
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
        self.clock.set(e.t, tr("volta {t}", "lap {t}", t=hms(e.lap_elapsed_s)) + (
            f" · {tr('passo', 'step')} {e.workout.remaining_text()}"
            if e.workout is not None and e.workout.step is not None else ""))
        for (bg, cap, val), (c, v) in zip(self.cells, self.cells_data()):
            cap.text, val.text = c.upper(), v
            # o valor tem de caber no quadrado (≈ 0,62 da letra por carácter)
            size = 26
            while size > 12 and len(v) * size * 0.66 > bg.width - 20:
                size -= 2
            val.font_size = size
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

    def _plan_title(self) -> str:
        e = self.engine
        if e.workout is None:
            return sp.name(e.sport).upper()
        s = e.workout.step
        if s is None:
            return tr("TREINO CONCLUÍDO", "WORKOUT DONE")
        return f"{tr('PASSO', 'STEP')} {e.workout.idx + 1}/{len(e.workout.steps)} · " \
               f"{e.workout.remaining_text()}"

    def _plan_text(self) -> str:
        e = self.engine
        if e.workout is None or e.workout.step is None:
            return ""
        s = e.workout.step
        lines = [f"{s.duration_text()} · {tr('alvo', 'target')} {e.target_text()}"]
        if getattr(self, "_goal_line", None) is None:
            from velo.ui.brief import GoalLine
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
               "lap": tr("Volta {n} · {d} · {t}", "Lap {n} · {d} · {t}", n=data.get("no"),
                         d=_m(data.get("distance_m")), t=hms(data.get("seconds", 0))),
               "workout_done": tr("Treino concluído!", "Workout done!"),
               "recovered": t("recover.toast")}.get(kind)
        if kind == "step" and data.get("cue"):
            msg = data["cue"]
        if msg:
            self.toast, self._toast_until = msg, time.monotonic() + 3.0

    def on_device_lost(self, name: str) -> None:
        self.toast = tr("⚠ {n} desligou-se", "⚠ {n} disconnected", n=name)
        self._toast_until = time.monotonic() + 6.0

    def on_key(self, symbol: int, modifiers: int) -> bool:
        e = self.engine
        if self.confirming:
            if symbol == key.ESCAPE:
                self._cancel()
                return True
            return super().on_key(symbol, modifiers)
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
            if e.sport == "running":
                e.set_speed(e.speed_kmh + (0.5 if plus else -0.5) *
                            (2 if modifiers & key.MOD_SHIFT else 1))
            else:
                e.add_length(1 if plus else -1)
            return True
        if symbol == key.T and e.sport == "running":
            self.typing = ""
            return True
        if symbol == key.L:
            e.lap("manual")
            return True
        if symbol == key.P:
            e.toggle_pause()
            return True
        if symbol in (key.ESCAPE, key.F10):
            self.confirming = True
            self.enter()
            return True
        return True

    def on_text(self, text: str) -> bool:
        if self.typing is not None:
            self.typing += "".join(c for c in text if c in "0123456789.,")
        return True

    def _cancel(self) -> None:
        self.confirming = False
        self.enter()

    def _finish(self) -> None:
        e = self.engine
        if not e.started or e.t < 1:
            e.abort(delete=True)
            self.app.pop()
            return
        self.app.replace(EnduranceSummary(self.app, e.finish()))

    def _discard(self) -> None:
        self.engine.discard()
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

    def leave(self) -> None:
        if not self.engine.finished:
            self.engine.suspend()

    def draw(self) -> None:
        self.chrome.draw()
        if self.confirming:
            self.list.draw()
            return
        self.batch.draw()
        if self.back_button is not None:
            self.back_button.draw()


class EnduranceSummary(Screen):
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
        if r.get("fit_path"):
            items.append(Item(".fit", value=r.get("name") or "", detail=r["fit_path"],
                              enabled=False))
        items.append(Item(tr("Voltar", "Back"), action=self.app.pop))
        self.chrome.set(r.get("title") or sp.name(r["sport"]), r.get("name") or "",
                        self.footer())
        fb_item = _feedback().summary_item(self.app, "endurance", self.result.get("session_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        self.list.set_items(items, keep_index=True)
        _feedback().maybe_ask(self, "endurance", self.result.get("session_id"))


class EnduranceDetail(Screen):
    def __init__(self, app, sid: str):
        super().__init__(app)
        self.sid = sid

    def enter(self) -> None:
        a = self.app
        s = a.db.conn.execute("SELECT * FROM endurance_sessions WHERE id = ?",
                              (self.sid,)).fetchone()
        if s is None:
            a.pop()
            return
        unit = pace_unit(s["sport"])
        items = [Item(tr("Distância", "Distance"), value=_m(s["distance_m"]), enabled=False),
                 Item(tr("Tempo", "Time"), value=hms(s["moving_s"] or 0), enabled=False),
                 Item(tr("Ritmo médio", "Avg pace"),
                      value=(hms(s["avg_pace_s"]) + " " + unit) if s["avg_pace_s"] else "—",
                      enabled=False)]
        for lp in en.session_laps(a.db, self.sid):
            items.append(Item(f"  {tr('Volta', 'Lap')} {lp['lap_no']}",
                              value=hms((lp["end_t"] or 0) - (lp["start_t"] or 0)),
                              detail=_m(lp["distance_m"]), enabled=False))
        self.chrome.set(s["name"] or sp.name(s["sport"]), str(s["started_at"])[:16],
                        self.footer())
        fb_item = _feedback().summary_item(self.app, "endurance", self.sid)
        if fb_item is not None:
            items.insert(0, fb_item)
        self.list.set_items(items, keep_index=True)


def _pretty(name) -> str:
    from velo.core.naming import pretty
    return pretty(name)


def _feedback():
    from velo.ui import feedback_screens
    return feedback_screens
