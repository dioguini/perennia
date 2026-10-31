"""Ecrãs da força, dos construtores de treino, das estatísticas gerais e da
recuperação de sessões interrompidas.

Ficam num módulo à parte para o `app.py` não crescer sem fim. Importam os
blocos de base do `app.py`; este importa-os só quando é preciso.
"""
from __future__ import annotations

import time
from pathlib import Path

import pyglet
from pyglet.window import key

from velo.core import stats
from velo.core import strength as st
from velo.core import workout_export as wx
from velo.core import workouts
from velo.core.i18n import t, tr
from velo.core.units import hms, km, parse_number, zone_text
from velo.gfx.compat import label as make_label
from velo.ui.app import (DeviceScreen, RideScreen, Screen, StatsScreen, SummaryScreen,
                         WorkoutRouteChoice)
from velo.gfx import theme as _theme
from velo.ui.brief import GymBrief
from velo.ui.widgets import ACCENT, BAD, DIM, GOOD, PANEL, TEXT, Item

NUM_CHARS = "0123456789.,"


def _kg(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:g} kg" if abs(v - round(v, 1)) < 1e-9 else f"{v:.2f} kg"


def _rpe(v: float | None) -> str:
    return "—" if v is None else f"{v:g}"


def _amount(reps: int, measure: str) -> str:
    return f"{reps} s" if measure == "time" else f"{reps}"


# =========================================================== ecrã de edição


class EditScreen(Screen):
    """Lista com linhas de números e de escolhas.

    - «num:campo»: ←/→ mudam o valor (Shift: passo maior); escrever números
      substitui-o; Backspace apaga o que se escreveu.
    - «cyc:campo»: ←/→ ou Enter passam à opção seguinte.
    - «text:campo»: texto livre (como no resto da aplicação).
    """

    def __init__(self, app):
        super().__init__(app)
        self._buf = ""
        self._buf_index = -1

    # para redefinir
    def num_adjust(self, field: str, steps: int, big: bool) -> None: ...
    def num_set(self, field: str, value: float | None) -> None: ...
    def cycle(self, field: str, step: int) -> None: ...

    def _field(self, prefix: str) -> str | None:
        item = self.list.selected
        if item is not None and isinstance(item.data, str) and item.data.startswith(prefix):
            return item.data[len(prefix):]
        return None

    def refresh(self) -> None:
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self._buf_index != self.list.index:
            self._buf, self._buf_index = "", self.list.index
        num = self._field("num:")
        cyc = self._field("cyc:")
        big = bool(modifiers & key.MOD_SHIFT)
        if num is not None:
            if symbol in (key.LEFT, key.RIGHT):
                self._buf = ""
                self.num_adjust(num, 1 if symbol == key.RIGHT else -1, big)
                self.refresh()
                return True
            if symbol == key.BACKSPACE:
                self._buf = self._buf[:-1]
                self.num_set(num, parse_number(self._buf) if self._buf else None)
                self.refresh()
                return True
        if cyc is not None and symbol in (key.LEFT, key.RIGHT, key.ENTER, key.RETURN):
            self.cycle(cyc, -1 if symbol == key.LEFT else 1)
            self.refresh()
            return True
        return super().on_key(symbol, modifiers)

    def on_text(self, text: str) -> bool:
        num = self._field("num:")
        if num is None:
            return super().on_text(text)
        if self._buf_index != self.list.index:
            self._buf, self._buf_index = "", self.list.index
        chars = "".join(c for c in text if c in NUM_CHARS)
        if chars:
            self._buf += chars
            self.num_set(num, parse_number(self._buf))
            self.refresh()
        return True


# ================================================================ força


def _gym_hub():
    from velo.ui.gym_screens import GymHub
    return GymHub


class StrengthMenu(Screen):
    """Menu da força: treinar (a partir de um plano), construtor, histórico
    e estatísticas."""

    def enter(self) -> None:
        a = self.app
        self.chrome.set(t("home.strength"), self._hr_status(), self.footer())
        self.list.set_items([
            Item(t("str.train"), detail=t("str.train_detail"),
                 action=lambda: a.push(StrengthWorkoutPicker(a))),
            Item(t("laps.mode.free"), detail=t("laps.free_detail"),
                 action=lambda: a.push(LapSessionScreen(a, "free"))),
            Item(t("laps.mode.conditioning"), detail=t("laps.cond_detail"),
                 action=lambda: a.push(LapSessionScreen(a, "conditioning"))),
            Item(t("menu.builder"), detail=t("str.builder_detail"),
                 action=lambda: a.push(StrengthBuilder(a))),
            Item(t("str.history"), action=lambda: a.push(StrengthHistory(a))),
            Item(t("menu.statistics"), action=lambda: a.push(StrengthStatsScreen(a))),
            Item(t("menu.devices"), detail=t("str.hr_hint"),
                 action=lambda: a.push(DeviceScreen(a))),
        ], keep_index=True)

    def _hr_status(self) -> str:
        hub = self.app.hub
        try:
            hr = hub.reading().hr_bpm
            src = hub.source_of("hr")
        except Exception:
            hr, src = None, None
        if hr:
            return t("str.hr_on", bpm=hr, src=src or "—")
        return t("str.hr_off")

    def update(self, dt: float) -> None:
        self.app.hub.tick(dt)
        self._t = getattr(self, "_t", 0.0) + dt
        if self._t >= 1.0:
            self._t = 0.0
            self.chrome.subtitle.text = self._hr_status()


class StrengthWorkoutPicker(Screen):
    """Escolher o plano. Só se treina a partir de um plano lido antes."""

    def enter(self) -> None:
        a = self.app
        items = []
        for w in st.workouts(a.db):
            plan = st.workout_items(a.db, w["id"])
            last = f" · {t('str.last')} {w['last_done'][:10]}" if w.get("last_done") else ""
            items.append(Item(w["name"], value=f"≈ {hms(st.plan_seconds(plan))}",
                              detail=f"{w['n_items']} {t('str.exercises')} · "
                                     f"{w['n_sets']} {t('str.sets').lower()}{last}",
                              action=lambda wid=w["id"]: a.push(StrengthPreview(a, wid))))
        if not items:
            items = [Item(t("str.no_workouts"), enabled=False),
                     Item(t("menu.builder"), action=lambda: a.push(StrengthBuilder(a)))]
        self.chrome.set(t("str.train"), t("str.pick"), self.footer())
        self.list.set_items(items, keep_index=True)


class StrengthPreview(GymBrief):
    """O plano antes de começar: objetivo e exercícios com o alvo de cada um
    (cartão em velo.ui.brief)."""

    def start(self) -> None:
        a = self.app
        try:
            a.replace(StrengthSessionScreen(a, self.wid))
        except ValueError as e:
            a.message(f"{t('common.error')}: {e}")

    def extra_actions(self) -> list[Item]:
        a = self.app

        def builder():
            from velo.ui.strength_builder_screens import StrengthBuilder
            a.push(StrengthBuilder(a, "strength", self.wid))
        return [Item(tr("Editar no construtor por blocos", "Edit in the block builder"),
                     action=builder),
                Item(tr("Editor simples (lista)", "Simple editor (list)"),
                     action=lambda: a.push(StrengthWorkoutEditor(a, self.wid)))]

    @property
    def workout_id(self):                  # compatibilidade
        return self.wid


class StrengthSessionScreen(EditScreen):
    """A sessão de força: lista de ações à esquerda, painel à direita com a
    série, o descanso, a FC e as séries já feitas deste exercício."""

    AGENT = False
    IN_SESSION = True
    SET_LINES = 8

    def __init__(self, app, workout_id: str | None = None, resume: dict | None = None):
        super().__init__(app)
        self.chrome.title.font_size = 18
        a = app
        athlete = a.db.athlete()
        wid = workout_id or (resume or {}).get("config", {}).get("workout_id")
        self.session = st.StrengthSession(a.db, athlete, wid, sensors=a.hub,
                                          out_dir=a.data_dir / "strength", resume=resume)
        self.confirming = False
        self._sig = None
        self.batch = pyglet.graphics.Batch()
        b = self.batch
        self.panel = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
        self.phase_label = make_label("", font_size=28, bold=True, color=ACCENT,
                                      anchor_y="top", batch=b)
        self.target_label = make_label("", font_size=14, color=TEXT, anchor_y="top", batch=b)
        self.hr_label = make_label("", font_size=34, bold=True, color=TEXT, anchor_y="top",
                                   batch=b)
        self.hr_zone_label = make_label("", font_size=13, color=DIM, anchor_y="top", batch=b)
        self.hr_segs = [pyglet.shapes.Rectangle(0, 0, 1, 10, color=(80, 80, 80), batch=b)
                        for _ in range(5)]
        self.hr_marker = pyglet.shapes.Rectangle(0, 0, 3, 18, color=TEXT[:3], batch=b)
        self.session_label = make_label("", font_size=13, color=DIM, anchor_y="top", batch=b)
        # os 4 quadrados escolhidos no editor do ecrã (Definições → Ecrã da sessão)
        from velo.core import layouts
        self.tile_keys = layouts.keys(app.db, "gym")[:4]
        self.tiles = [(pyglet.shapes.Rectangle(0, 0, 10, 10, color=_theme.P.panel2, batch=b),
                       make_label("", font_size=9, color=DIM, anchor_y="top", batch=b),
                       make_label("", font_size=20, bold=True, color=TEXT, anchor_y="top",
                                  batch=b)) for _ in range(4)]
        self.sets_title = make_label("", font_size=13, bold=True, color=TEXT, anchor_y="top",
                                     batch=b)
        self.set_lines = [make_label("", font_size=13, color=TEXT, anchor_y="top", batch=b)
                          for _ in range(self.SET_LINES)]
        self.next_label = make_label("", font_size=13, color=DIM, anchor_y="top", batch=b,
                                     multiline=True, width=400)
        from velo.ui.widgets import SessionClock
        self.clock = SessionClock(app.window, batch=b)
        self._layout_panel()

    # ------------------------------------------------------------ medidas

    def _list_width(self, w: int) -> int:
        return int(w * 0.44) - 48

    def _layout_panel(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        x = int(w * 0.44) + 24
        top = h - 120
        pw = w - 48 - x
        self.panel.x, self.panel.y, self.panel.width, self.panel.height = x, 96, pw, top - 96
        px = x + 20
        self.phase_label.x, self.phase_label.y = px, top - 16
        self.target_label.x, self.target_label.y = px, top - 60
        # FC e zona passaram para os quadrados; as etiquetas antigas ficam fora do ecrã
        self.hr_label.x, self.hr_label.y = -2000, -2000
        self.hr_zone_label.anchor_x = "right"
        self.hr_zone_label.x, self.hr_zone_label.y = -2000, -2000
        tw = (pw - 40 - 3 * 8) / 4
        for i, (bg, cap, val) in enumerate(self.tiles):
            tx = px + i * (tw + 8)
            bg.x, bg.y, bg.width, bg.height = tx, top - 142, tw, 54
            cap.x, cap.y = tx + 8, top - 92
            val.x, val.y = tx + 8, top - 106
        seg_w = (pw - 40) / 5
        for i, r in enumerate(self.hr_segs):
            r.x, r.y, r.width, r.height = px + i * seg_w, top - 152, seg_w - 2, 10
        self.hr_marker.y = top - 156
        self.session_label.x, self.session_label.y = px, top - 172
        self.sets_title.x, self.sets_title.y = px, top - 204
        for i, lab in enumerate(self.set_lines):
            lab.x, lab.y = px, top - 228 - i * 22
        self.next_label.x = px
        self.next_label.y = max(140, top - 228 - self.SET_LINES * 22 - 10)
        self.next_label.width = max(200, pw - 40)
        self.clock.layout()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout_panel()

    # ------------------------------------------------------------- linhas

    def _action_label(self) -> str:
        s = self.session
        if s.phase == st.WORK:
            return t("str.end_set", n=s.set_no)
        if s.phase == st.DONE or (s.phase == st.REST and s.all_done):
            return t("str.all_done")
        n = s.set_no if s.remaining(s.item_idx) > 0 else 1
        if s.phase == st.REST:
            nxt = s.item_idx
            return t("str.next_set", n=s.done_sets(nxt) + 1, name=s.items[nxt].name)
        return t("str.start_set", n=n)

    def _shown(self) -> int:
        """No descanso mostra-se o exercício que acabou de ser feito (é a série
        dele que os campos corrigem); fora dele, o que vem a seguir."""
        s = self.session
        return s.sets[-1].item_idx if s.editing_last else s.item_idx

    def enter(self) -> None:
        s = self.session
        it = s.items[self._shown()]
        if self.confirming:
            items = [Item(t("str.confirm_no"), action=self._cancel_confirm),
                     Item(t("str.confirm_yes"), action=self._finish),
                     Item(tr("Terminar sem guardar", "Finish without saving"),
                          action=self._discard)]
            self.chrome.set(t("str.confirm_title"), t("str.confirm_sub",
                                                      n=len(s.sets)), self.footer())
            self.list.set_items(items)
            return
        editing = s.editing_last
        last = s.sets[-1] if editing else None
        measure = it.measure if not editing else s.items[last.item_idx].measure
        reps_label = t("str.seconds") if measure == "time" else t("str.reps")
        suffix = f" ({t('str.fix_set', n=last.set_no)})" if editing else ""
        reps = s.field_value("reps")
        items = [
            Item(self._action_label(), action=self._action, data="action"),
            Item(reps_label + suffix, value=_amount(reps or 0, measure), data="num:reps"),
            Item(t("str.load") + suffix, value=_kg(s.field_value("load_kg")),
                 data="num:load_kg"),
            Item("RPE" + suffix, value=_rpe(s.field_value("rpe")), data="num:rpe",
                 detail=t("str.rpe_hint") if not editing else ""),
            Item(t("str.exercise_next") if editing else t("str.exercise"),
                 value=f"{s.item_idx + 1}/{len(s.items)} · {s.item.name}", data="cyc:item"),
            Item(t("str.add_set"), action=self._add_set),
            Item(t("str.skip"), action=self._skip),
            Item(t("str.resume") if s.paused else t("str.pause"), action=self._pause),
            Item(t("str.finish"), action=self._ask_finish),
        ]
        shown = self._shown()
        if editing:
            head = t("str.set_done", n=last.set_no, total=s.planned_sets(shown))
        else:
            head = t("str.set_of", n=min(s.set_no, s.planned_sets(shown)),
                     total=s.planned_sets(shown))
        sub = f"{head} · {t('str.target')} {it.target_text()} · {t('str.rest')} {hms(it.rest_s)}"
        title = ((s.labels[shown] + " · ") if getattr(s, "labels", None) else "") + it.name
        # o relógio está ao centro, em cima: título e subtítulo param antes dele
        room = self.app.window.width / 2 - 115 - 48 - 12
        self.chrome.set(_fit_text(title, room, 18), _fit_text(sub, room, 13), self.footer())
        self.list.set_items(items, keep_index=True)
        self._sig = self._signature()

    def _signature(self):
        s = self.session
        return (s.phase, s.item_idx, len(s.sets), s.paused, self.confirming,
                s.field_value("reps"), s.field_value("load_kg"), s.field_value("rpe"))

    def footer(self) -> str:
        return t("str.footer")

    # -------------------------------------------------------------- ações

    def _action(self) -> None:
        self.session.action()
        self.enter()

    def _add_set(self) -> None:
        self.session.add_set()
        self.app.message(t("str.set_added", name=self.session.item.name))
        self.enter()

    def _skip(self) -> None:
        self.session.skip_item()
        self.enter()

    def _pause(self) -> None:
        self.session.toggle_pause()
        self.enter()

    def _ask_finish(self) -> None:
        self.confirming = True
        self.list.index = 0
        self.enter()

    def _cancel_confirm(self) -> None:
        self.confirming = False
        self.enter()

    def _finish(self) -> None:
        result = self.session.finish()
        self.app.replace(StrengthSummaryScreen(self.app, result))

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        mult = {"reps": 5, "load_kg": 4, "rpe": 2}.get(field, 1) if big else 1
        self.session.adjust(field, steps * mult)

    def num_set(self, field: str, value: float | None) -> None:
        self.session.set_field(field, value)

    def cycle(self, field: str, step: int) -> None:
        if field == "item":
            self.session.goto_item(step)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.confirming:
            if symbol == key.ESCAPE:
                self._cancel_confirm()
                return True
            return super().on_key(symbol, modifiers)
        if symbol == key.SPACE:
            self._action()
            return True
        if symbol == key.P:
            self._pause()
            return True
        if symbol in (key.ESCAPE, key.F10):
            self._ask_finish()
            return True
        return super().on_key(symbol, modifiers)

    def on_text(self, text: str) -> bool:
        if self.confirming:
            return True
        return super().on_text(text) or True

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self._ask_finish()               # «voltar» a meio pergunta primeiro
            return True
        return self.list.on_mouse_press(x, y)

    def leave(self) -> None:
        if not self.session.finished:
            self.session.suspend()

    # ------------------------------------------------------------- ciclo

    def update(self, dt: float) -> None:
        a = self.app
        a.hub.tick(dt)
        s = self.session
        s.update(dt)
        for kind, data in s.drain_events():
            if kind == "rest_done":
                a.message(t("str.rest_over"))
            elif kind == "recovered":
                a.message(t("recover.toast"))
            elif kind == "fit_error":
                a.message(f"{t('common.error')}: {data.get('message', '')}")
        if self._signature() != self._sig:
            self.enter()
        self._update_panel()
        sub = ""
        if s.phase == st.WORK:
            sub = tr("série {t}", "set {t}", t=hms(s.t - s.set_start_t))
        elif s.phase == st.REST:
            sub = tr("descanso {t}", "rest {t}", t=hms(max(0.0, s.rest_until - s.t)))
        elif not s.started:
            sub = tr("começa com a 1.ª série", "starts with the 1st set")
        self.clock.set(s.t, sub)

    def _discard(self) -> None:
        s = self.session
        try:
            s.abort()
            s.db.conn.execute("DELETE FROM strength_sessions WHERE id = ?", (s.session_id,))
            s.db.conn.commit()
        except Exception:
            pass
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

    def _update_panel(self) -> None:
        from velo.gfx.hud import zone_color
        s = self.session
        shown = self._shown()
        it = s.items[shown]
        secs = s.phase_seconds
        if s.paused:
            self.phase_label.text, self.phase_label.color = t("str.paused"), DIM
        elif s.phase == st.WORK:
            self.phase_label.text = f"{t('str.in_set', n=s.set_no)} · {hms(secs)}"
            self.phase_label.color = GOOD
        elif s.phase == st.REST:
            over = secs < 0
            self.phase_label.text = (f"{t('str.resting')} · "
                                     + (f"+{hms(-secs)}" if over else hms(secs)))
            self.phase_label.color = BAD if over else ACCENT
        elif s.phase == st.DONE:
            self.phase_label.text, self.phase_label.color = t("str.complete"), GOOD
        else:
            self.phase_label.text, self.phase_label.color = t("str.ready"), TEXT
        lab = (s.labels[shown] + " · ") if getattr(s, "labels", None) else ""
        tg = s.target(shown, s.done_sets(shown)) if hasattr(s, "target") else None
        if tg is not None and s.phase != st.DONE:
            unit = "s" if it.measure == "time" else ""
            tgt = f"{tg.get('reps') or it.reps}{unit}" + (
                f" @ {tg['load_kg']:g} kg" if tg.get("load_kg") else "") + (
                f" · RPE {tg['rpe']:g}" if tg.get("rpe") else "")
            self.target_label.text = (f"{lab}{it.name} · {t('str.target')} "
                                      f"{tr('série', 'set')} {s.set_no}: {tgt}")
        else:
            self.target_label.text = f"{lab}{it.name} · {t('str.target')} {it.target_text()}"
        self.target_label.text = _fit_text(self.target_label.text,
                                           max(200, self.panel.width - 40), 14)
        hr = s.hr_bpm
        zone = s.hr_zone
        if hr:
            self.hr_label.text = f"{hr} bpm"
            self.hr_label.color = _theme.ink(zone_color(zone or 1, "hr"))
            self.hr_zone_label.text = zone_text(zone, "hr") if zone else ""
        else:
            self.hr_label.text, self.hr_label.color = "— bpm", DIM
            self.hr_zone_label.text = t("str.no_hr")
        self._update_tiles()
        for i, r in enumerate(self.hr_segs):
            r.color = zone_color(i + 1, "hr")[:3]
            r.opacity = 255 if zone == i + 1 else 90
        if hr and s.lthr:
            lo, hi = 0.5 * s.lthr, 1.15 * s.lthr
            frac = max(0.0, min(1.0, (hr - lo) / (hi - lo)))
            seg0 = self.hr_segs[0]
            total_w = self.hr_segs[-1].x + self.hr_segs[-1].width - seg0.x
            self.hr_marker.x = seg0.x + frac * total_w
            self.hr_marker.opacity = 255
        else:
            self.hr_marker.opacity = 0
        summ_vol = sum(st.set_volume(x.load_kg, x.reps, s.items[x.item_idx].bodyweight,
                                     s.athlete.weight_kg, s.items[x.item_idx].measure)
                       for x in s.sets)
        planned = sum(s.planned_sets(i) for i in range(len(s.items))
                      if i not in s.skipped)
        self.session_label.text = t("str.session_line", time=hms(s.t), sets=len(s.sets),
                                    planned=planned, vol=f"{summ_vol:,.0f}".replace(",", " "),
                                    hr=f"{s.avg_hr:.0f}" if s.avg_hr else "—")
        mine = [x for x in s.sets if x.item_idx == shown]
        self.sets_title.text = t("str.sets_of", name=it.name) if mine else t("str.no_sets_yet")
        for i, lab in enumerate(self.set_lines):
            k = len(mine) - len(self.set_lines) + i if len(mine) > len(self.set_lines) else i
            if 0 <= k < len(mine):
                x = mine[k]
                lab.text = (f"{x.set_no}.  {_amount(x.reps, it.measure)}"
                            + (f" × {_kg(x.load_kg)}" if x.load_kg else "")
                            + (f" · RPE {_rpe(x.rpe)}" if x.rpe else "")
                            + (f" · {x.avg_hr:.0f} bpm" if x.avg_hr else "")
                            + f" · {hms(x.end_t - x.start_t)}")
                lab.color = TEXT
            else:
                lab.text = ""
        nxt = s.item_idx if shown != s.item_idx else s.next_item()
        goal = self._exercise_goal(s.item_idx)
        lines = [tr("Objetivo: ", "Goal: ") + goal] if goal else []
        if nxt is not None and nxt != shown and s.remaining(nxt) > 0:
            n_it = s.items[nxt]
            lines.append(f"{t('str.up_next')}: {n_it.name} — {n_it.target_text()}")
        self.next_label.text = "\n".join(lines)

    def tile_value(self, k: str) -> str:
        s = self.session
        if k == "hr":
            return f"{s.hr_bpm} bpm" if s.hr_bpm else "—"
        if k == "hr_zone":
            return f"Z{s.hr_zone}" if s.hr_zone else "—"
        if k == "avg_hr":
            return f"{s.avg_hr:.0f}" if s.avg_hr else "—"
        if k == "sets":
            total = sum(s.planned_sets(i) for i in range(len(s.items)))
            return f"{len(s.sets)}/{total}"
        if k == "reps":
            return str(sum(x.reps for x in s.sets))
        if k == "volume":
            v = sum((x.load_kg or 0) * x.reps for x in s.sets)
            return f"{v:,.0f} kg".replace(",", " ")
        if k == "exercise":
            return f"{s.item_idx + 1}/{len(s.items)}"
        if k == "session_time":
            return hms(s.t)
        if k == "phase_time":
            return hms(abs(s.phase_seconds))
        return "—"

    def _update_tiles(self) -> None:
        from velo.core import layouts
        for (bg, cap, val), k in zip(self.tiles, self.tile_keys + [None] * 4):
            if k is None:
                bg.opacity = 0
                cap.text = val.text = ""
                continue
            bg.opacity = 255
            cap.text = layouts.label("gym", k).upper()
            v = self.tile_value(k)
            val.text = v
            size = 20
            while size > 11 and len(v) * size * 0.66 > bg.width - 14:
                size -= 1
            val.font_size = size
            if k in ("hr", "hr_zone") and s_zone(self.session):
                val.color = _theme.ink(_hr_color(s_zone(self.session)))
            else:
                val.color = TEXT

    def _exercise_goal(self, idx: int) -> str:
        """O objetivo do exercício em curso (escrito no plano, ou a nota)."""
        if getattr(self, "_gym_brief", None) is None:
            self._gym_brief = False
            wid = getattr(self.session, "workout_id", None)
            if wid:
                try:
                    from velo.core import objectives as ob
                    wk = st.workout(self.app.db, wid) or {}
                    self._gym_brief = ob.gym_brief(self.app.db, wid, wk.get("name", ""),
                                                   self.session.items)
                except Exception:
                    self._gym_brief = False
        b = self._gym_brief
        if not b or not (0 <= idx < len(b.raw_blocks)):
            return ""
        return b.raw_blocks[idx].goal

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


class StrengthSummaryScreen(Screen):
    def __init__(self, app, result: dict):
        super().__init__(app)
        self.result = result

    def enter(self) -> None:
        a = self.app
        r = self.result
        if not r:
            a.reset_to_menu(_gym_hub())
            return
        items = [Item(t("summary.close"), action=lambda: a.reset_to_menu(_gym_hub()))]

        def add(label: str, value: str) -> None:
            items.append(Item(label, value=value, enabled=False))

        add(t("metric.elapsed"), hms(r["elapsed_s"]))
        add(t("str.sets"), f"{r['total_sets']} · {r['total_reps']} {t('str.reps').lower()}")
        add(t("str.volume"), f"{r['volume_kg']:,.0f} kg".replace(",", " "))
        if r.get("avg_rpe"):
            add(t("str.avg_rpe"), f"{r['avg_rpe']:.1f}")
        if r.get("avg_hr"):
            add(t("metric.avg_hr"), f"{r['avg_hr']:.0f} bpm · máx {r.get('max_hr') or '—'}")
        if r.get("load"):
            add(t("str.load_total"), f"{r['load']:.0f} · "
                + t("str.load_src_hr" if r.get("load_source") == "hr" else "str.load_src_rpe"))
        tz = r.get("hr_zone_s") or []
        if sum(tz):
            total = sum(tz)
            add(t("tiz.hr"), "  ".join(f"Z{i + 1} {v / total * 100:.0f}%"
                                       for i, v in enumerate(tz) if v))
        for ex in r.get("exercises", []):
            est = f" · 1RM {t('str.est')} {ex['best_e1rm']:.0f} kg" if ex.get("best_e1rm") else ""
            vol = f" · {ex['volume']:,.0f} kg".replace(",", " ") if ex["volume"] else ""
            items.append(Item(f"  {ex['name']}", value=f"{ex['sets']} × · {ex['reps']}"
                              + (" s" if ex.get("measure") == "time" else ""),
                              detail=(" · ".join(
                                  _amount(x.reps, ex.get("measure", "reps"))
                                  + (f"×{x.load_kg:g}" if x.load_kg else "")
                                  for x in ex["lines"])) + vol + est, enabled=False))
        sub = (t("summary.saved_fit", path=r["fit_path"]) if r.get("fit_path")
               else f"{t('common.error')}: o .fit não foi escrito")
        self.chrome.set(t("summary.title"), f"{r.get('name', '')} · {sub}", self.footer())
        fb_item = _feedback().summary_item(self.app, "strength", self.result.get("session_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        _sid = self.result.get("session_id")
        if _sid:
            items.insert(1 if fb_item is not None else 0, Item(
                tr("Análise pós-treino", "Post-workout analysis"),
                detail=tr("Cumprimento, repetições, volume e 1RM de cada exercício",
                          "Compliance, reps, volume and 1RM per exercise"),
                action=lambda: self.app.push(_analysis_screen(self.app, _sid))))
        self.list.set_items(items)
        _feedback().maybe_ask(self, "strength", self.result.get("session_id"))


class StrengthHistory(Screen):
    def enter(self) -> None:
        a = self.app
        items = []
        for s in st.sessions(a.db, 200):
            items.append(Item(f"{str(s['started_at'])[:10]}  {s['plan_name'] or s['name'] or ''}",
                              value=hms(s["elapsed_s"] or 0),
                              detail=f"{s['total_sets'] or 0} {t('str.sets').lower()} · "
                                     f"{(s['volume_kg'] or 0):,.0f} kg".replace(",", " ")
                                     + (f" · {s['avg_hr']:.0f} bpm" if s["avg_hr"] else "")
                                     + (f" · {t('str.load_total')} {s['load']:.0f}"
                                        if s["load"] else ""),
                              action=lambda sid=s["id"]: a.push(StrengthSessionDetail(a, sid))))
        if not items:
            items = [Item(t("str.no_history"), enabled=False)]
        self.chrome.set(t("str.history"), f"{len(items)}", self.footer())
        self.list.set_items(items, keep_index=True)


class StrengthSessionDetail(Screen):
    def __init__(self, app, session_id: str):
        super().__init__(app)
        self.session_id = session_id

    def enter(self) -> None:
        a = self.app
        row = a.db.conn.execute("SELECT * FROM strength_sessions WHERE id = ?",
                                (self.session_id,)).fetchone()
        items = []
        for s in st.session_sets(a.db, self.session_id):
            items.append(Item(f"{s['name']} · {s['set_no']}",
                              value=f"{s['reps']}" + (f" × {_kg(s['load_kg'])}" if s["load_kg"]
                                                      else ""),
                              detail=(f"RPE {_rpe(s['rpe'])} · " if s["rpe"] else "")
                              + (f"{s['avg_hr']:.0f} bpm · " if s["avg_hr"] else "")
                              + hms((s["end_t_s"] or 0) - (s["start_t_s"] or 0)),
                              enabled=False))
        plan = st.workout(a.db, row["workout_id"]) if row and row["workout_id"] else None
        title = (plan or {}).get("name") or (row["name"] if row else "")
        sub = str(row["started_at"])[:16].replace("T", " ") if row else ""
        if row and row["fit_path"]:
            sub += f" · {row['fit_path']}"
        self.chrome.set(title, sub, self.footer())
        fb_item = _feedback().summary_item(self.app, "strength", self.session_id)
        if fb_item is not None:
            items.insert(0, fb_item)
        _sid = self.session_id
        if _sid:
            items.insert(1 if fb_item is not None else 0, Item(
                tr("Análise pós-treino", "Post-workout analysis"),
                detail=tr("Cumprimento, repetições, volume e 1RM de cada exercício",
                          "Compliance, reps, volume and 1RM per exercise"),
                action=lambda: self.app.push(_analysis_screen(self.app, _sid))))
        self.list.set_items(items or [Item("—", enabled=False)])


# ------------------------------------------------------------ construtor


class StrengthBuilder(Screen):
    """Lista de planos de força. Del apaga (carregando duas vezes)."""

    def enter(self) -> None:
        a = self.app
        items = [Item(t("str.new_workout"), action=lambda: a.push(
            StrengthWorkoutEditor(a, None)))]
        for w in st.workouts(a.db):
            plan = st.workout_items(a.db, w["id"])
            items.append(Item(w["name"], value=f"≈ {hms(st.plan_seconds(plan))}",
                              detail=f"{w['n_items']} {t('str.exercises')} · "
                                     f"{w['n_sets']} {t('str.sets').lower()}"
                                     + (f" · {w['description']}" if w.get("description")
                                        else ""),
                              action=lambda wid=w["id"]: a.push(
                                  StrengthWorkoutEditor(a, wid)),
                              data=("sworkout", w["id"])))
        self.chrome.set(t("menu.builder"), t("home.strength"), t("str.builder_footer"))
        self.list.set_items(items, keep_index=True)
        self._armed = None

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.DELETE and item is not None and isinstance(item.data, tuple):
            wid = item.data[1]
            if getattr(self, "_armed", None) == wid:
                st.delete_workout(self.app.db, wid)
                self.app.message(t("str.deleted", name=item.label))
                self.enter()
            else:
                self._armed = wid
                self.app.message(t("str.delete_again"))
            return True
        return super().on_key(symbol, modifiers)


class StrengthWorkoutEditor(EditScreen):
    """Editar um plano: nome, descrição e a lista de exercícios. ←/→ num
    exercício muda-o de lugar; Enter abre-o."""

    def __init__(self, app, workout_id: str | None):
        super().__init__(app)
        self.workout_id = workout_id
        self.dirty = workout_id is None
        db = app.db
        wk = st.workout(db, workout_id) if workout_id else None
        self.name = wk["name"] if wk else t("str.new_name")
        self.description = (wk or {}).get("description") or ""
        self.items: list[dict] = []
        if workout_id:
            for it in st.workout_items(db, workout_id):
                d = it.as_dict()
                d.update(name=it.name, measure=it.measure, bodyweight=it.bodyweight)
                self.items.append(d)
        self._esc_armed = False

    def enter(self) -> None:
        rows = [Item(t("str.name"), value=self.name, data="text:name"),
                Item(t("str.description"), value=self.description or "—",
                     data="text:description")]
        for i, it in enumerate(self.items):
            rows.append(Item(f"{i + 1}. {it['name']}", value=self._target(it),
                             detail=f"{t('str.rest')} {hms(it['rest_s'])}"
                                    + (f" · {it['notes']}" if it.get("notes") else ""),
                             action=lambda k=i: self.app.push(StrengthItemEditor(self, k)),
                             data=f"item:{i}"))
        rows += [
            Item(t("str.add_exercise"), action=lambda: self.app.push(
                ExercisePicker(self.app, self._add_exercise))),
            Item(t("str.save"), action=self._save),
            Item(t("str.save_train"), action=self._save_and_train,
                 enabled=bool(self.items)),
        ]
        plan = [st.PlanItem(exercise_id=it["exercise_id"], name=it["name"], sets=it["sets"],
                            reps=it["reps"], rest_s=it["rest_s"],
                            measure=it.get("measure", "reps")) for it in self.items]
        sets = sum(it["sets"] for it in self.items)
        self.chrome.set(t("menu.builder") + (" *" if self.dirty else ""),
                        f"{len(self.items)} {t('str.exercises')} · {sets} {t('str.sets').lower()} · "
                        f"≈ {hms(st.plan_seconds(plan))}", t("str.editor_footer"))
        self.list.set_items(rows, keep_index=True)

    @staticmethod
    def _target(it: dict) -> str:
        unit = " s" if it.get("measure") == "time" else ""
        load = f" @ {it['load_kg']:g} kg" if it.get("load_kg") else ""
        rpe = f" · RPE {it['rpe']:g}" if it.get("rpe") else ""
        return f"{it['sets']} × {it['reps']}{unit}{load}{rpe}"

    def text_input(self, field: str, text: str) -> None:
        setattr(self, field, (getattr(self, field) or "") + text)
        self.dirty = True
        self.enter()

    def text_backspace(self, field: str) -> None:
        setattr(self, field, (getattr(self, field) or "")[:-1])
        self.dirty = True
        self.enter()

    def _add_exercise(self, ex: dict) -> None:
        measure = ex.get("measure") or "reps"
        self.items.append({"exercise_id": ex["id"], "name": ex["name"], "sets": 3,
                           "reps": 30 if measure == "time" else 10, "load_kg": None,
                           "rpe": 7.0, "rest_s": 90, "notes": None, "measure": measure,
                           "bodyweight": ex.get("bodyweight") or 0.0})
        self.dirty = True
        self.list.index = 2 + len(self.items) - 1

    def move(self, idx: int, step: int) -> None:
        j = idx + step
        if 0 <= j < len(self.items):
            self.items[idx], self.items[j] = self.items[j], self.items[idx]
            self.list.index = 2 + j
            self.dirty = True

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        data = item.data if item is not None else None
        if isinstance(data, str) and data.startswith("item:"):
            idx = int(data[5:])
            if symbol in (key.LEFT, key.RIGHT):
                self.move(idx, 1 if symbol == key.RIGHT else -1)
                self.enter()
                return True
            if symbol == key.DELETE:
                del self.items[idx]
                self.dirty = True
                self.enter()
                return True
        if symbol == key.ESCAPE and self.dirty and not self._esc_armed:
            self._esc_armed = True
            self.app.message(t("str.unsaved"))
            return True
        return super().on_key(symbol, modifiers)

    def _save(self) -> str | None:
        if not self.items:
            self.app.message(t("str.empty_plan"))
            return None
        self.workout_id = st.save_workout(self.app.db, self.workout_id, self.name,
                                          self.description or None, self.items)
        self.dirty = False
        self._esc_armed = False
        self.app.message(t("str.saved", name=self.name))
        self.enter()
        return self.workout_id

    def _save_and_train(self) -> None:
        wid = self._save()
        if wid:
            self.app.replace(StrengthPreview(self.app, wid))


class StrengthItemEditor(EditScreen):
    """Um exercício do plano: séries, repetições (ou segundos), carga, RPE
    alvo e descanso."""

    def __init__(self, editor: StrengthWorkoutEditor, idx: int):
        super().__init__(editor.app)
        self.editor = editor
        self.idx = idx

    @property
    def it(self) -> dict:
        return self.editor.items[self.idx]

    def enter(self) -> None:
        if self.idx >= len(self.editor.items):
            self.app.pop()
            return
        it = self.it
        timed = it.get("measure") == "time"
        rows = [
            Item(t("str.exercise"), value=it["name"], action=lambda: self.app.push(
                ExercisePicker(self.app, self._replace))),
            Item(t("str.sets"), value=str(it["sets"]), data="num:sets"),
            Item(t("str.seconds") if timed else t("str.reps"),
                 value=_amount(it["reps"], it.get("measure", "reps")), data="num:reps"),
            Item(t("str.load"), value=_kg(it.get("load_kg")), data="num:load_kg",
                 detail=t("str.load_hint")),
            Item(t("str.target_rpe"), value=_rpe(it.get("rpe")), data="num:rpe",
                 detail=t("str.rpe_hint")),
            Item(t("str.rest"), value=hms(it["rest_s"]), data="num:rest_s"),
            Item(t("str.notes"), value=it.get("notes") or "—", data="text:notes"),
            Item(t("str.duplicate"), action=self._duplicate),
            Item(t("str.remove"), action=self._remove),
            Item(t("str.done"), action=self.app.pop),
        ]
        self.chrome.set(f"{self.idx + 1}. {it['name']}",
                        StrengthWorkoutEditor._target(it), t("str.item_footer"))
        self.list.set_items(rows, keep_index=True)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        it = self.it
        if field == "sets":
            it["sets"] = max(1, it["sets"] + steps)
        elif field == "reps":
            step = (15 if big else 5) if it.get("measure") == "time" else (5 if big else 1)
            it["reps"] = max(1, it["reps"] + steps * step)
        elif field == "load_kg":
            v = (it.get("load_kg") or 0.0) + steps * (10.0 if big else 2.5)
            it["load_kg"] = round(v, 2) if v > 0 else None
        elif field == "rpe":
            v = (it.get("rpe") or 6.5) + steps * 0.5
            it["rpe"] = None if v < 1 else min(10.0, v)
        elif field == "rest_s":
            it["rest_s"] = max(0, it["rest_s"] + steps * (60 if big else 15))
        self.editor.dirty = True

    def num_set(self, field: str, value: float | None) -> None:
        it = self.it
        if field in ("sets", "reps"):
            it[field] = max(1, int(value or 1))
        elif field == "load_kg":
            it["load_kg"] = round(value, 2) if value else None
        elif field == "rpe":
            it["rpe"] = max(1.0, min(10.0, value)) if value else None
        elif field == "rest_s":
            it["rest_s"] = int(round((value or 0) * 60)) if value is not None and value < 15 \
                else int(value or 0)          # «2» = 2 minutos; «90» = 90 segundos
        self.editor.dirty = True

    def text_input(self, field: str, text: str) -> None:
        self.it[field] = (self.it.get(field) or "") + text
        self.editor.dirty = True
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.it[field] = (self.it.get(field) or "")[:-1] or None
        self.editor.dirty = True
        self.enter()

    def _replace(self, ex: dict) -> None:
        self.it.update(exercise_id=ex["id"], name=ex["name"],
                       measure=ex.get("measure") or "reps",
                       bodyweight=ex.get("bodyweight") or 0.0)
        self.editor.dirty = True

    def _duplicate(self) -> None:
        self.editor.items.insert(self.idx + 1, dict(self.it))
        self.editor.dirty = True
        self.app.message(t("str.duplicated"))

    def _remove(self) -> None:
        del self.editor.items[self.idx]
        self.editor.dirty = True
        self.app.pop()


class ExercisePicker(EditScreen):
    """Escolher um exercício, filtrado por grupo, ou criar um novo."""

    def __init__(self, app, on_pick):
        super().__init__(app)
        self.on_pick = on_pick
        self.group: str | None = None

    def enter(self) -> None:
        a = self.app
        rows = [Item(t("str.group"), value=t(f"str.group.{self.group or 'all'}"),
                     data="cyc:group"),
                Item(t("str.new_exercise"), action=lambda: a.push(
                    ExerciseCreate(a, self._created)))]
        for ex in st.exercises(a.db, self.group):
            rows.append(Item(ex["name"], value=t(f"str.group.{ex['category']}"),
                             detail=(t("str.timed") if ex.get("measure") == "time" else "")
                             + (" · " + t("str.custom") if ex["custom"] else ""),
                             action=lambda e=ex: self._pick(e)))
        self.chrome.set(t("str.pick_exercise"), f"{len(rows) - 2}", self.footer())
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        opts = [None] + list(st.GROUPS)
        i = opts.index(self.group) if self.group in opts else 0
        self.group = opts[(i + step) % len(opts)]
        self.list.index = 0

    def _pick(self, ex: dict) -> None:
        self.on_pick(ex)
        self.app.pop()

    def _created(self, ex_id: int) -> None:
        ex = st.exercise(self.app.db, ex_id)
        if ex:
            self.on_pick(ex)
            self.app.pop()               # sai também do seletor


class ExerciseCreate(EditScreen):
    BW = (0.0, 0.5, 0.65, 1.0)

    def __init__(self, app, on_created):
        super().__init__(app)
        self.on_created = on_created
        self.name = ""
        self.group = "full"
        self.measure = "reps"
        self.bw = 0.0

    def enter(self) -> None:
        rows = [Item(t("str.name"), value=self.name or "—", data="text:name"),
                Item(t("str.group"), value=t(f"str.group.{self.group}"), data="cyc:group"),
                Item(t("str.measure"), value=t(f"str.measure.{self.measure}"),
                     data="cyc:measure"),
                Item(t("str.bodyweight"), value=f"{self.bw * 100:.0f} %", data="cyc:bw",
                     detail=t("str.bodyweight_hint")),
                Item(t("str.create"), action=self._create)]
        self.chrome.set(t("str.new_exercise"), "", self.footer())
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        if field == "group":
            gs = list(st.GROUPS)
            self.group = gs[(gs.index(self.group) + step) % len(gs)]
        elif field == "measure":
            self.measure = "time" if self.measure == "reps" else "reps"
        elif field == "bw":
            self.bw = self.BW[(self.BW.index(self.bw) + step) % len(self.BW)]

    def text_input(self, field: str, text: str) -> None:
        self.name += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.name = self.name[:-1]
        self.enter()

    def _create(self) -> None:
        if not self.name.strip():
            self.app.message(t("str.need_name"))
            return
        ex_id = st.add_exercise(self.app.db, self.name, self.group, self.bw, self.measure)
        self.app.pop()
        self.on_created(ex_id)


# ============================================================ estatísticas


class StrengthStatsScreen(StatsScreen):
    """Estatísticas da força: evolução por período, progressão de cada
    exercício (1RM estimada, carga máxima, volume), tempo em zona de FC e a
    carga (fitness, fadiga e forma) só da força."""

    VIEWS = ("evolution", "exercise", "hr_zones", "load")
    VIEW_KEY = "str.view."
    RECORD_ROWS = 5
    STATS_SPORT = "gym"
    SPORTS = ("strength",)
    MEASURES = ("best_e1rm", "max_load", "volume")

    def __init__(self, app):
        super().__init__(app)
        self.metric = "volume"
        self.measure = "best_e1rm"
        self.exercise_idx = 0

    def _exercises(self) -> list[dict]:
        return st.exercises_with_history(self.app.db)

    def enter(self) -> None:
        a = self.app
        sess = st.sessions(a.db, 100000)
        vol = sum(s["volume_kg"] or 0 for s in sess)
        hours = sum(s["elapsed_s"] or 0 for s in sess) / 3600.0
        self.chrome.set(f"{t('menu.statistics')} · {t('home.strength')}",
                        t("str.stats_sub", n=len(sess), h=f"{hours:.1f}",
                          vol=f"{vol:,.0f}".replace(",", " ")),
                        "←/→ mudar · ↑↓ escolher a linha · clica no gráfico para ver um ponto")
        view = self.VIEWS[self.view]
        rows = [self.sport_row()]
        if view == "evolution":
            rows.append(Item(t("stats.row.metric"), value=t(f"str.metric.{self.metric}"),
                             data="smetric"))
        elif view == "exercise":
            exs = self._exercises()
            name = exs[self.exercise_idx % len(exs)]["name"] if exs else "—"
            rows.append(Item(t("str.exercise"), value=name, data="exercise"))
        else:
            rows.append(Item(t("stats.row.metric"), value="—", enabled=False))
        if view == "exercise":
            rows.append(Item(t("stats.row.metric"), value=t(f"str.measure_{self.measure}"),
                             data="measure"))
            rows.append(Item(t("stats.row.range"), value="—", enabled=False))
        else:
            rows.append(Item(t("stats.row.group"), value=t(f"stats.group.{self.grouping}"),
                             data="group"))
            rows.append(Item(t("stats.row.range"),
                             value=t("stats.range", n=self.count,
                                     unit=t(f"stats.unit.{self.grouping}")), data="range"))
        rows.append(Item(tr("Por exercício: carga, RPE e tempo", "Per exercise: load, RPE, time"),
                         value="›", action=lambda: a.push(_exercise_stats_screen(a))))
        self.list.set_items(rows, keep_index=True)
        self.list.y = self.content_top(self.app.window.height)
        self.list.set_visible_rows(self.RECORD_ROWS)
        self._refresh_chart()

    def _cycle(self, which: str, step: int) -> None:
        if which == "smetric":
            ms = stats.STRENGTH_METRICS
            self.metric = ms[(ms.index(self.metric) + step) % len(ms)]
            self.enter()
            return
        if which == "exercise":
            n = max(1, len(self._exercises()))
            self.exercise_idx = (self.exercise_idx + step) % n
            self.enter()
            return
        if which == "measure":
            self.measure = self.MEASURES[(self.MEASURES.index(self.measure) + step)
                                         % len(self.MEASURES)]
            self.enter()
            return
        super()._cycle(which, step)

    def _fmt(self, v: float, metric: str | None = None) -> str:
        m = metric or self.metric
        if m in ("volume", "best_e1rm", "max_load"):
            return f"{v:,.0f} kg".replace(",", " ")
        if m == "time":
            return f"{v:.1f} h"
        if m in ("avg_rpe",):
            return f"{v:.1f}"
        if m == "avg_hr":
            return f"{v:.0f} bpm"
        return f"{v:.0f}"

    def _bar_tip(self, idx: int) -> str:
        view = self.VIEWS[self.view]
        data = getattr(self, "_series", [])
        if not data or idx >= len(data):
            return ""
        if view == "exercise":
            label, value = data[idx]
            return f"{label}: {self._fmt(value, self.measure)}"
        if view == "evolution":
            label, value = data[idx]
            return f"{label}: {self._fmt(value)}"
        return super()._bar_tip(idx)

    def on_mouse(self, x: int, y: int) -> bool:
        idx = self.chart.hit(x, y)
        if idx is not None:
            self.chart.select(idx, self._bar_tip(idx))
            return True
        return Screen.on_mouse(self, x, y)

    def _refresh_chart(self) -> None:
        from velo.gfx.hud import zone_color
        a = self.app
        view = self.VIEWS[self.view]
        empty = t("str.no_history")
        self.bars.set_rows([])
        self.summary[0].text = self.summary[1].text = ""
        self._series = []
        if view == "evolution":
            self._series = stats.strength_series(a.db, self.metric, self.grouping, self.count)
            self.chart.show_bars(
                f"{t(f'str.metric.{self.metric}')} · {t(f'stats.group.{self.grouping}')}",
                [v for _, v in self._series], [lab for lab, _ in self._series], empty,
                fmt=lambda v: self._fmt(v))
            if self.chart.points:
                self.chart.select(len(self._series) - 1, self._bar_tip(len(self._series) - 1))
            tot = stats.strength_series(a.db, "sessions", self.grouping, self.count)
            self.summary[0].text = t("str.period", n=self.count,
                                     unit=t(f"stats.unit.{self.grouping}"),
                                     sessions=f"{sum(v for _, v in tot):.0f}")
        elif view == "exercise":
            exs = self._exercises()
            if not exs:
                self.chart.show_line(t("str.view.exercise"), [], [], empty)
                return
            ex = exs[self.exercise_idx % len(exs)]
            prog = st.exercise_progress(a.db, ex["id"])
            vals = [p[self.measure] or 0.0 for p in prog]
            self._series = [(p["date"][5:], v) for p, v in zip(prog, vals)]
            title = f"{ex['name']} · {t(f'str.measure_{self.measure}')}"
            if len(vals) >= 2:
                self.chart.show_line(title, vals, [lab for lab, _ in self._series], empty,
                                     fmt=lambda v: self._fmt(v, self.measure))
            else:
                self.chart.show_bars(title, vals, [lab for lab, _ in self._series], empty,
                                     fmt=lambda v: self._fmt(v, self.measure))
            if self.chart.points:
                self.chart.select(len(vals) - 1, self._bar_tip(len(vals) - 1))
            best = max((p["best_e1rm"] or 0 for p in prog), default=0)
            if best:
                self.summary[0].text = t("str.best_e1rm", kg=f"{best:.0f}",
                                         n=len(prog))
            self.summary[1].text = t("str.e1rm_hint")
        elif view == "hr_zones":
            self._series = stats.zones_series(a.db, "hr", self.grouping, self.count,
                                              self.SPORTS)
            n = len(self._series[0][1]) if self._series else 0
            self.chart.show_stacked(
                f"{t('tiz.hr')} · {t(f'stats.group.{self.grouping}')}",
                [[v / 3600.0 for v in z] for _, z in self._series],
                [zone_color(i + 1, "hr") for i in range(n)],
                [lab for lab, _ in self._series], empty, fmt=lambda v: f"{v:.1f} h")
            self.view_hint_zones()
        else:
            super()._refresh_chart()

    def view_hint_zones(self) -> None:
        total = [0.0] * 5
        for _, z in self._series:
            for i, v in enumerate(z[:5]):
                total[i] += v
        s = sum(total)
        if s:
            self.summary[0].text = "  ".join(f"Z{i + 1} {v / s * 100:.0f}%"
                                             for i, v in enumerate(total))


class GeneralStatsScreen(StatsScreen):
    """Estatísticas de todos os desportos: carga total (fitness, fadiga e
    forma), tempo/sessões/carga por desporto e tempo em zona de FC."""

    VIEWS = ("load", "sports", "hr_zones")
    VIEW_KEY = "gen.view."
    RECORD_ROWS = 5
    STATS_SPORT = None
    SPORTS = stats.SPORTS
    SPORT_COLORS = {"cycling": (108, 170, 220), "strength": (236, 128, 160),
                    "rowing": (120, 200, 150), "running": (240, 180, 90),
                    "swimming": (90, 200, 230)}

    def __init__(self, app):
        super().__init__(app)
        self.smetric = "time"

    def enter(self) -> None:
        a = self.app
        stk = stats.streaks(a.db)
        self.chrome.set(t("home.stats"),
                        t("home.streak_days", n=stk["days"]) + " · "
                        + t("home.streak_weeks", n=stk["weeks"]),
                        "←/→ mudar · ↑↓ escolher a linha · clica no gráfico para ver um ponto")
        view = self.VIEWS[self.view]
        rows = [self.sport_row()]
        if view == "sports":
            rows.append(Item(t("stats.row.metric"), value=t(f"gen.metric.{self.smetric}"),
                             data="smetric"))
        else:
            rows.append(Item(t("stats.row.metric"), value="—", enabled=False))
        rows.append(Item(t("stats.row.group"), value=t(f"stats.group.{self.grouping}"),
                         data="group"))
        rows.append(Item(t("stats.row.range"),
                         value=t("stats.range", n=self.count,
                                 unit=t(f"stats.unit.{self.grouping}")), data="range"))
        rows.append(Item(tr("Carga e prontidão", "Load and readiness"),
                         value="›", detail=tr("Fitness, fadiga, forma, prontidão e ramp",
                                              "Fitness, fatigue, form, readiness and ramp"),
                         action=lambda: a.push(_load_screens().LoadReadinessScreen(a))))
        self.list.set_items(rows, keep_index=True)
        self.list.y = self.content_top(self.app.window.height)
        self.list.set_visible_rows(self.RECORD_ROWS)
        self._refresh_chart()

    def _cycle(self, which: str, step: int) -> None:
        if which == "smetric":
            ms = stats.GENERAL_METRICS
            self.smetric = ms[(ms.index(self.smetric) + step) % len(ms)]
            self.enter()
            return
        super()._cycle(which, step)

    def on_mouse(self, x: int, y: int) -> bool:
        idx = self.chart.hit(x, y)
        if idx is not None:
            self.chart.select(idx, self._bar_tip(idx))
            return True
        return Screen.on_mouse(self, x, y)

    def _fmt_general(self, v: float) -> str:
        return {"time": f"{v:.1f} h", "sessions": f"{v:.0f}", "load": f"{v:.0f}"}[self.smetric]

    def _bar_tip(self, idx: int) -> str:
        view = self.VIEWS[self.view]
        data = getattr(self, "_series", [])
        if view == "sports" and data and idx < len(data):
            label, by = data[idx]
            return f"{label}: " + " · ".join(
                f"{t(f'gen.sport.{s}')} {self._fmt_general(by[s])}" for s in self.SPORTS)
        if view == "hr_zones":
            label, value = data[idx] if data and idx < len(data) else ("", [0])
            return f"{label}: {sum(value) / 3600.0:.1f} h"
        return super()._bar_tip(idx)

    def _refresh_chart(self) -> None:
        from velo.gfx.hud import zone_color
        a = self.app
        view = self.VIEWS[self.view]
        empty = t("stats.no_data")
        self.bars.set_rows([])
        self.summary[0].text = self.summary[1].text = ""
        self._series = []
        if view == "sports":
            self._series = stats.sport_series(a.db, self.smetric, self.grouping, self.count)
            self.chart.show_stacked(
                f"{t(f'gen.metric.{self.smetric}')} · {t(f'stats.group.{self.grouping}')}",
                [[by[s] for s in self.SPORTS] for _, by in self._series],
                [self.SPORT_COLORS[s] for s in self.SPORTS],
                [lab for lab, _ in self._series], empty, fmt=self._fmt_general,
                legend=[t(f"gen.sport.{s}") for s in self.SPORTS])
            if self.chart.points:
                self.chart.select(len(self._series) - 1, self._bar_tip(len(self._series) - 1))
            tot = stats.sport_totals(a.db, self.grouping, self.count)
            self.summary[0].text = " · ".join(
                f"{t(f'gen.sport.{s}')}: {tot[s]['sessions']:.0f} · {tot[s]['time']:.1f} h · "
                f"{t('gen.metric.load').lower()} {tot[s]['load']:.0f}" for s in self.SPORTS)
        elif view == "hr_zones":
            self._series = stats.zones_series(a.db, "hr", self.grouping, self.count,
                                              self.SPORTS)
            n = len(self._series[0][1]) if self._series else 0
            self.chart.show_stacked(
                f"{t('tiz.hr')} · {t('gen.all_sports')} · {t(f'stats.group.{self.grouping}')}",
                [[v / 3600.0 for v in z] for _, z in self._series],
                [zone_color(i + 1, "hr") for i in range(n)],
                [lab for lab, _ in self._series], empty, fmt=lambda v: f"{v:.1f} h")
            StrengthStatsScreen.view_hint_zones(self)
        else:
            super()._refresh_chart()
            if self.summary[1].text:
                self.summary[1].text = t("gen.load_hint")


# ======================================================= construtor ciclismo


class CyclingBuilder(Screen):
    """Lista de treinos de ciclismo para editar, criar e exportar."""

    HAS_BOARD = False

    def enter(self) -> None:
        a = self.app
        ftp = a.db.athlete().ftp_w
        items = [Item(t("bld.new"), action=lambda: a.push(WorkoutEditor(a, None)))]
        for w in a.db.workouts():
            tss = f" · TSS ≈ {w['est_tss']:.0f}" if w["est_tss"] else ""
            items.append(Item(w["name"], value=hms(w["total_seconds"] or 0),
                              detail=(w["description"] or w["source_format"] or "") + tss,
                              action=lambda wid=w["id"]: a.push(WorkoutEditor(a, wid)),
                              data=("workout", w["id"])))
        self.chrome.set(t("menu.builder"), f"{t('home.cycling')} · FTP {ftp} W",
                        t("bld.list_footer"))
        self.list.set_items(items, keep_index=True)
        self._armed = None

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and isinstance(item.data, tuple):
            wid = item.data[1]
            if symbol == key.E:
                self.app.push(ExportScreen(self.app, wid))
                return True
            if symbol == key.DELETE:
                if getattr(self, "_armed", None) == wid:
                    self.app.db.delete_workout(wid)
                    self.app.message(t("str.deleted", name=item.label))
                    self.enter()
                else:
                    self._armed = wid
                    self.app.message(t("str.delete_again"))
                return True
        return super().on_key(symbol, modifiers)


def _steps_from_db(db, workout_id: str) -> list[workouts.Step]:
    return [workouts.Step(kind=r["kind"], duration_s=r["duration_s"] or 0,
                          target_type=r["target_type"], target_lo=r["target_lo"],
                          target_hi=r["target_hi"], cadence_lo=r["cadence_lo"],
                          cadence_hi=r["cadence_hi"], text_cue=r["text_cue"])
            for r in db.workout_steps(workout_id)]


def step_text(s: workouts.Step, ftp: int) -> str:
    unit = "%" if s.target_type == "pct_ftp" else " W"
    if s.kind == "freeride" or s.target_type == "none":
        what = t("bld.free")
    elif s.kind == "ramp":
        what = f"{t('bld.ramp')} {s.target_lo:.0f}→{(s.target_hi or s.target_lo):.0f}{unit}"
    else:
        what = f"{s.target_lo:.0f}{unit}"
        if s.target_type == "pct_ftp":
            what += f" ({s.target_lo / 100 * ftp:.0f} W)"
    cad = f" · {s.cadence_lo} rpm" if s.cadence_lo else ""
    return f"{wx.duration_text(s.duration_s)} · {what}{cad}"


class WorkoutEditor(EditScreen):
    """Construtor de treinos de ciclismo: passos, rampas, livres e blocos de
    repetição. ←/→ num passo muda-o de lugar; Enter abre-o; Del apaga."""

    def __init__(self, app, workout_id: str | None):
        super().__init__(app)
        self.workout_id = workout_id
        row = app.db.workout(workout_id) if workout_id else None
        self.name = row["name"] if row else t("bld.new_name")
        self.description = (row["description"] if row else "") or ""
        self.steps: list[workouts.Step] = _steps_from_db(app.db, workout_id) \
            if workout_id else [
            workouts.Step("ramp", 600, "pct_ftp", 50, 75, text_cue="Aquecimento"),
            workouts.Step("steady", 1200, "pct_ftp", 88, 88, cadence_lo=90,
                          cadence_hi=90, text_cue="Sweet spot"),
            workouts.Step("ramp", 300, "pct_ftp", 65, 45, text_cue="Retorno à calma")]
        self.dirty = workout_id is None
        self._esc_armed = False

    @property
    def ftp(self) -> int:
        return self.app.db.athlete().ftp_w

    def workout(self) -> workouts.Workout:
        return workouts.Workout(self.name, self.steps, self.description or None, "builder")

    def enter(self) -> None:
        ftp = self.ftp
        rows = [Item(t("str.name"), value=self.name, data="text:name"),
                Item(t("str.description"), value=self.description or "—",
                     data="text:description")]
        for i, s in enumerate(self.steps):
            rows.append(Item(f"{i + 1}. {step_text(s, ftp)}", value=s.text_cue or "",
                             action=lambda k=i: self.app.push(StepEditor(self, k)),
                             data=f"step:{i}"))
        rows += [
            Item(t("bld.add_steady"), action=lambda: self._add("steady")),
            Item(t("bld.add_ramp"), action=lambda: self._add("ramp")),
            Item(t("bld.add_free"), action=lambda: self._add("freeride")),
            Item(t("bld.add_repeat"), action=lambda: self.app.push(RepeatEditor(self))),
            Item(t("str.save"), action=self._save),
            Item(t("bld.save_ride"), action=self._save_and_ride),
            Item(t("bld.export"), action=self._export),
        ]
        wk = self.workout()
        tss = wk.estimated_tss(ftp)
        hours = max(wk.total_seconds / 3600.0, 1e-6)
        if_ = (tss / 100.0 / hours) ** 0.5 if tss else 0
        self.chrome.set(t("menu.builder") + (" *" if self.dirty else ""),
                        t("bld.summary", n=len(self.steps), time=hms(wk.total_seconds),
                          tss=f"{tss:.0f}", if_=f"{if_:.2f}", ftp=ftp),
                        t("bld.editor_footer"))
        self.list.set_items(rows, keep_index=True)

    def _add(self, kind: str) -> None:
        if kind == "steady":
            s = workouts.Step("steady", 300, "pct_ftp", 75, 75)
        elif kind == "ramp":
            s = workouts.Step("ramp", 300, "pct_ftp", 60, 90)
        else:
            s = workouts.Step("freeride", 300, "none")
        self.steps.append(s)
        self.dirty = True
        self.app.push(StepEditor(self, len(self.steps) - 1))

    def text_input(self, field: str, text: str) -> None:
        setattr(self, field, (getattr(self, field) or "") + text)
        self.dirty = True
        self.enter()

    def text_backspace(self, field: str) -> None:
        setattr(self, field, (getattr(self, field) or "")[:-1])
        self.dirty = True
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        data = item.data if item is not None else None
        if isinstance(data, str) and data.startswith("step:"):
            idx = int(data[5:])
            if symbol in (key.LEFT, key.RIGHT):
                j = idx + (1 if symbol == key.RIGHT else -1)
                if 0 <= j < len(self.steps):
                    self.steps[idx], self.steps[j] = self.steps[j], self.steps[idx]
                    self.list.index = 2 + j
                    self.dirty = True
                self.enter()
                return True
            if symbol == key.DELETE:
                del self.steps[idx]
                self.dirty = True
                self.enter()
                return True
        if symbol == key.ESCAPE and self.dirty and not self._esc_armed:
            self._esc_armed = True
            self.app.message(t("str.unsaved"))
            return True
        return super().on_key(symbol, modifiers)

    def _save(self) -> str | None:
        if not self.steps:
            self.app.message(t("bld.empty"))
            return None
        db = self.app.db
        wk = self.workout()
        tss = wk.estimated_tss(self.ftp)
        steps = [s.as_dict() for s in self.steps]
        if self.workout_id:
            db.update_workout(self.workout_id, self.name, steps, self.description or None, tss)
        else:
            self.workout_id = db.insert_workout(self.name, steps, "builder",
                                                self.description or None, tss)
        self.dirty = False
        self._esc_armed = False
        self.app.message(t("str.saved", name=self.name))
        self.enter()
        return self.workout_id

    def _save_and_ride(self) -> None:
        wid = self._save()
        if wid:
            self.app.push(WorkoutRouteChoice(self.app, wid))

    def _export(self) -> None:
        wid = self._save()
        if wid:
            self.app.push(ExportScreen(self.app, wid))


class StepEditor(EditScreen):
    KINDS = ("steady", "ramp", "freeride")

    def __init__(self, editor: WorkoutEditor, idx: int):
        super().__init__(editor.app)
        self.editor = editor
        self.idx = idx

    @property
    def s(self) -> workouts.Step:
        return self.editor.steps[self.idx]

    def enter(self) -> None:
        if self.idx >= len(self.editor.steps):
            self.app.pop()
            return
        s = self.s
        ftp = self.editor.ftp
        pct = s.target_type == "pct_ftp"
        unit = "%" if pct else " W"
        rows = [Item(t("bld.kind"), value=t(f"bld.kind.{s.kind}"), data="cyc:kind"),
                Item(t("bld.duration"), value=wx.duration_text(s.duration_s),
                     data="num:duration", detail=t("bld.duration_hint"))]
        if s.kind != "freeride":
            lo = s.target_lo or 0
            watts = lo / 100 * ftp if pct else lo
            rows.append(Item(t("bld.target_start") if s.kind == "ramp" else t("bld.target"),
                             value=f"{lo:.0f}{unit}" + (f" · {watts:.0f} W" if pct else ""),
                             data="num:lo"))
            if s.kind == "ramp":
                hi = s.target_hi if s.target_hi is not None else lo
                rows.append(Item(t("bld.target_end"),
                                 value=f"{hi:.0f}{unit}"
                                 + (f" · {hi / 100 * ftp:.0f} W" if pct else ""),
                                 data="num:hi"))
            rows.append(Item(t("bld.unit"), value=t("bld.unit.pct") if pct
                             else t("bld.unit.watts"), data="cyc:unit"))
        rows += [
            Item(t("bld.cadence"), value=f"{s.cadence_lo} rpm" if s.cadence_lo else "—",
                 data="num:cad"),
            Item(t("bld.cue"), value=s.text_cue or "—", data="text:cue"),
            Item(t("str.duplicate"), action=self._duplicate),
            Item(t("str.remove"), action=self._remove),
            Item(t("str.done"), action=self.app.pop),
        ]
        self.chrome.set(f"{t('bld.step')} {self.idx + 1}", step_text(s, ftp),
                        t("str.item_footer"))
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        s = self.s
        ftp = max(1, self.editor.ftp)
        if field == "kind":
            k = self.KINDS[(self.KINDS.index(s.kind) + step) % len(self.KINDS)]
            s.kind = k
            if k == "freeride":
                s.target_type, s.target_lo, s.target_hi = "none", None, None
            elif s.target_type == "none":
                s.target_type, s.target_lo, s.target_hi = "pct_ftp", 75.0, 75.0
            if k == "steady":
                s.target_hi = s.target_lo
        elif field == "unit":
            if s.target_type == "pct_ftp":
                s.target_type = "watts"
                s.target_lo = round((s.target_lo or 0) / 100 * ftp)
                s.target_hi = round((s.target_hi or 0) / 100 * ftp) if s.target_hi else None
            else:
                s.target_type = "pct_ftp"
                s.target_lo = round((s.target_lo or 0) / ftp * 100)
                s.target_hi = round((s.target_hi or 0) / ftp * 100) if s.target_hi else None
        self.editor.dirty = True

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        s = self.s
        pct = s.target_type == "pct_ftp"
        if field == "duration":
            s.duration_s = max(5, s.duration_s + steps * (60 if big else 15))
        elif field in ("lo", "hi"):
            step = (5 if big else 1) if pct else (25 if big else 5)
            cur = s.target_lo if field == "lo" else (s.target_hi if s.target_hi is not None
                                                     else s.target_lo)
            v = max(0.0, (cur or 0) + steps * step)
            if field == "lo":
                s.target_lo = v
                if s.kind == "steady":
                    s.target_hi = v
            else:
                s.target_hi = v
        elif field == "cad":
            v = (s.cadence_lo or 85) + steps * (10 if big else 5) if s.cadence_lo or steps > 0 \
                else 0
            s.cadence_lo = s.cadence_hi = int(v) if v >= 40 else None
        self.editor.dirty = True

    def num_set(self, field: str, value: float | None) -> None:
        s = self.s
        if field == "duration":
            s.duration_s = max(5, int(round((value or 0) * 60)))   # em minutos: «2,5» = 2:30
        elif field == "lo":
            s.target_lo = value or 0.0
            if s.kind == "steady":
                s.target_hi = s.target_lo
        elif field == "hi":
            s.target_hi = value or 0.0
        elif field == "cad":
            s.cadence_lo = s.cadence_hi = int(value) if value and value >= 40 else None
        self.editor.dirty = True

    def text_input(self, field: str, text: str) -> None:
        self.s.text_cue = (self.s.text_cue or "") + text
        self.editor.dirty = True
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.s.text_cue = (self.s.text_cue or "")[:-1] or None
        self.editor.dirty = True
        self.enter()

    def _duplicate(self) -> None:
        self.editor.steps.insert(self.idx + 1, workouts.Step(**self.s.as_dict()))
        self.editor.dirty = True
        self.app.message(t("str.duplicated"))

    def _remove(self) -> None:
        del self.editor.steps[self.idx]
        self.editor.dirty = True
        self.app.pop()


class RepeatEditor(EditScreen):
    """Bloco de repetição: N × (esforço + recuperação), expandido em passos."""

    def __init__(self, editor: WorkoutEditor):
        super().__init__(editor.app)
        self.editor = editor
        self.v = {"times": 5, "on_s": 180, "on_pct": 110.0, "off_s": 120, "off_pct": 55.0,
                  "cad": 0}

    def enter(self) -> None:
        v = self.v
        ftp = self.editor.ftp
        rows = [
            Item(t("bld.rep.times"), value=f"{v['times']} ×", data="num:times"),
            Item(t("bld.rep.on"), value=wx.duration_text(v["on_s"]), data="num:on_s"),
            Item(t("bld.rep.on_pct"), value=f"{v['on_pct']:.0f}% · {v['on_pct'] / 100 * ftp:.0f} W",
                 data="num:on_pct"),
            Item(t("bld.rep.off"), value=wx.duration_text(v["off_s"]), data="num:off_s"),
            Item(t("bld.rep.off_pct"),
                 value=f"{v['off_pct']:.0f}% · {v['off_pct'] / 100 * ftp:.0f} W",
                 data="num:off_pct"),
            Item(t("bld.cadence"), value=f"{v['cad']} rpm" if v["cad"] else "—",
                 data="num:cad"),
            Item(t("bld.rep.add"), action=self._add),
        ]
        total = v["times"] * (v["on_s"] + v["off_s"])
        self.chrome.set(t("bld.add_repeat"),
                        f"{v['times']} × ({wx.duration_text(v['on_s'])} @ {v['on_pct']:.0f}% + "
                        f"{wx.duration_text(v['off_s'])} @ {v['off_pct']:.0f}%) = {hms(total)}",
                        t("str.item_footer"))
        self.list.set_items(rows, keep_index=True)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        v = self.v
        if field == "times":
            v["times"] = max(1, v["times"] + steps)
        elif field in ("on_s", "off_s"):
            v[field] = max(5, v[field] + steps * (60 if big else 15))
        elif field in ("on_pct", "off_pct"):
            v[field] = max(0.0, v[field] + steps * (5 if big else 1))
        elif field == "cad":
            v["cad"] = 0 if v["cad"] + steps * 5 < 40 and steps < 0 else max(
                40, (v["cad"] or 85) + steps * 5)

    def num_set(self, field: str, value: float | None) -> None:
        v = self.v
        if field == "times":
            v["times"] = max(1, int(value or 1))
        elif field in ("on_s", "off_s"):
            v[field] = max(5, int(round((value or 0) * 60)))
        elif field in ("on_pct", "off_pct"):
            v[field] = value or 0.0
        elif field == "cad":
            v["cad"] = int(value) if value and value >= 40 else 0

    def _add(self) -> None:
        v = self.v
        cad = v["cad"] or None
        on = workouts.Step("steady", v["on_s"], "pct_ftp", v["on_pct"], v["on_pct"], cad, cad,
                           text_cue=f"Esforço ({v['on_pct']:.0f}%)")
        off = workouts.Step("steady", v["off_s"], "pct_ftp", v["off_pct"], v["off_pct"],
                            text_cue="Recuperação")
        steps = wx.expand_repeat(v["times"], [on, off])
        for i in range(v["times"]):
            steps[2 * i].text_cue = f"{i + 1}/{v['times']} · esforço {v['on_pct']:.0f}%"
        # inserir antes do retorno à calma, se o último passo for uma rampa a descer
        last = self.editor.steps[-1] if self.editor.steps else None
        at = len(self.editor.steps)
        if last is not None and last.kind == "ramp" and (last.target_hi or 0) < (
                last.target_lo or 0):
            at -= 1
        self.editor.steps[at:at] = steps
        self.editor.dirty = True
        self.app.message(t("bld.rep.added", n=len(steps)))
        self.app.pop()


class ExportScreen(Screen):
    """Exportar um treino para .zwo, .erg, .mrc ou .fit (ou todos)."""

    def __init__(self, app, workout_id: str):
        super().__init__(app)
        self.workout_id = workout_id

    def folder(self) -> Path:
        return self.app.data_dir / "exports"

    def enter(self) -> None:
        a = self.app
        row = a.db.workout(self.workout_id)
        if row is None:
            a.pop()
            return
        items = [Item(wx.FORMAT_LABELS[f], action=lambda f=f: self._export([f]))
                 for f in wx.FORMATS]
        items.append(Item(t("bld.export_all"), action=lambda: self._export(list(wx.FORMATS))))
        self.chrome.set(f"{t('bld.export')} · {row['name']}",
                        t("bld.export_where", path=str(self.folder())), self.footer())
        self.list.set_items(items, keep_index=True)

    def _export(self, fmts: list[str]) -> list[Path]:
        a = self.app
        row = a.db.workout(self.workout_id)
        wk = workouts.Workout(row["name"], _steps_from_db(a.db, self.workout_id),
                              row["description"], row["source_format"])
        ftp = a.db.athlete().ftp_w
        out = []
        for f in fmts:
            try:
                out.append(wx.export(wk, f, self.folder(), ftp))
            except Exception as e:
                a.message(f"{t('common.error')}: {e}")
                return out
        a.message(t("bld.exported", files=", ".join(p.name for p in out)))
        self.last_exported = out
        return out


# ============================================================ recuperação


class RecoveryScreen(Screen):
    """A aplicação fechou a meio de uma sessão: retomar, guardar ou descartar."""

    AGENT = False
    def enter(self) -> None:
        a = self.app
        cps = a.db.checkpoints()
        if not cps:
            a.pop()
            return
        items = []
        for cp in cps:
            sid = cp["session_id"]
            items.append(Item(self._describe(cp), enabled=False))
            items.append(Item(t("recover.resume"), action=lambda c=cp: self._resume(c),
                              data=("resume", sid)))
            items.append(Item(t("recover.save"), action=lambda c=cp: self._save(c),
                              data=("save", sid)))
            items.append(Item(t("recover.discard"), action=lambda c=cp: self._discard(c),
                              data=("discard", sid)))
        self.chrome.set(t("recover.title"), t("recover.sub"), self.footer())
        self.list.set_items(items)
        self.list.index = 1
        self.list._sync()

    def _describe(self, cp: dict) -> str:
        db = self.app.db
        sid = cp["session_id"]
        state = cp["state"]
        when = time.strftime("%Y-%m-%d %H:%M",
                             time.localtime(float(cp["config"].get("start_unix") or 0)))
        if cp["sport"] == "rowing":
            return (f"{t('home.rowing')} · {cp['config'].get('name', '')} · {when} · "
                    f"{hms(state.get('t', 0))} · {state.get('distance_m', 0):.0f} m")
        if cp["sport"] == "endurance":
            from velo.core import sports as sp
            return (f"{sp.name(cp['config'].get('sport', 'running'))} · "
                    f"{cp['config'].get('name', '')} · {when} · {hms(state.get('t', 0))} · "
                    f"{state.get('distance_m', 0):.0f} m")
        if cp["sport"] == "strength_laps":
            n = db.conn.execute("SELECT COUNT(*) AS n FROM strength_laps WHERE session_id = ?",
                                (sid,)).fetchone()["n"]
            return (f"{t('home.strength')} · {cp['config'].get('name', '')} · {when} · "
                    f"{hms(state.get('t', 0))} · {n} {t('laps.laps')}")
        if cp["sport"] == "strength":
            n = db.conn.execute("SELECT COUNT(*) AS n FROM strength_sets WHERE session_id = ?",
                                (sid,)).fetchone()["n"]
            return (f"{t('home.strength')} · {cp['config'].get('name', '')} · {when} · "
                    f"{hms(state.get('t', 0))} · {n} {t('str.sets').lower()}")
        dv, du = km(state.get("dist_m", 0.0), self.app.units)
        return (f"{t('home.cycling')} · {when} · {hms(state.get('t', 0))} · "
                f"{dv:.2f} {du}")

    def _resume(self, cp: dict) -> None:
        a = self.app
        if cp["sport"] == "endurance":
            from velo.ui import endurance_screens as es
            a.replace(es.EnduranceSession(a, cp["config"].get("sport", "running"), resume=cp))
        elif cp["sport"] == "rowing":
            from velo.ui import rowing_screens as rs
            if a.rower is None:
                rs.start_session(a, replace=True, resume=cp)
            else:
                a.replace(rs.RowingSessionScreen(a, resume=cp))
        elif cp["sport"] == "strength_laps":
            a.replace(LapSessionScreen(a, cp["config"].get("mode", "free"), resume=cp))
        elif cp["sport"] == "strength":
            a.replace(StrengthSessionScreen(a, resume=cp))
        else:
            a.replace(RideScreen.from_checkpoint(a, cp))

    def _save(self, cp: dict) -> None:
        """Terminar com o que ficou gravado: .fit, resumo e estatísticas."""
        a = self.app
        if cp["sport"] == "endurance":
            from velo.core import endurance as en
            from velo.ui import endurance_screens as es
            eng = en.EnduranceEngine(a.db, a.db.athlete(), cp["config"].get("sport", "running"),
                                     workout_id=cp["config"].get("workout_id"),
                                     out_dir=a.data_dir / "endurance", resume=cp)
            a.replace(es.EnduranceSummary(a, eng.finish()))
        elif cp["sport"] == "rowing":
            from velo.core import rowing as rw
            from velo.ui import rowing_screens as rs
            cfg = cp["config"]
            eng = rw.RowEngine(a.db, a.db.athlete(), None, workout_id=cfg.get("workout_id"),
                               protocol=cfg.get("protocol"), game_spec=cfg.get("game"),
                               out_dir=a.data_dir / "rowing", resume=cp)
            a.replace(rs.RowSummaryScreen(a, eng.finish()))
        elif cp["sport"] == "strength_laps":
            from velo.core import laps_session as ls
            ses = ls.LapSession(a.db, a.db.athlete(), cp["config"].get("mode", "free"),
                                out_dir=a.data_dir / "strength", resume=cp)
            a.replace(LapSummaryScreen(a, ses.finish()))
        elif cp["sport"] == "strength":
            ses = st.StrengthSession(a.db, a.db.athlete(), cp["config"].get("workout_id"),
                                     out_dir=a.data_dir / "strength", resume=cp)
            result = ses.finish()
            a.replace(StrengthSummaryScreen(a, result))
        else:
            screen = RideScreen.from_checkpoint(a, cp)
            engine = screen.build_engine()
            result = engine.finish()
            a.replace(SummaryScreen(a, result, None))

    def _discard(self, cp: dict) -> None:
        a = self.app
        sid = cp["session_id"]
        if cp["sport"] in ("strength", "strength_laps"):
            a.db.conn.execute("UPDATE strength_sessions SET status='aborted' WHERE id = ?",
                              (sid,))
            a.db.conn.commit()
        elif cp["sport"] == "rowing":
            a.db.conn.execute("UPDATE row_sessions SET status='aborted' WHERE id = ?", (sid,))
            a.db.conn.commit()
        elif cp["sport"] == "endurance":
            a.db.conn.execute("UPDATE endurance_sessions SET status='aborted' WHERE id = ?",
                              (sid,))
            a.db.conn.commit()
        else:
            a.db.abort_ride(sid)
        a.db.delete_checkpoint(sid)
        a.message(t("recover.discarded"))
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.ESCAPE:
            return True                       # decidir primeiro
        return super().on_key(symbol, modifiers)

    def on_mouse(self, x: int, y: int) -> bool:
        return self.list.on_mouse_press(x, y)


# ================================================================ Challenge


class ChallengeMenu(Screen):
    """Modo Challenge do ciclismo: fuga, desafio adaptativo e mini-jogos."""

    HAS_BOARD = True

    def side_board(self):
        from velo.core import boards as boards_mod
        from velo.core import games as games_mod
        item = self.list.selected
        data = item.data if item is not None else None
        if data == "chase":
            return boards_mod.chase_board(self.app.db, self.app.db.get("chase_level", "normal"))
        if data in games_mod.CLASSES:
            return games_mod.leaderboard(self.app.db, data)
        return boards_mod.Board(t("menu.challenge"), empty=t("board.empty"))

    def enter(self) -> None:
        from velo.core import games as games_mod
        from velo.core.i18n import tr
        from velo.ui.app import ChaseScreen
        a = self.app
        lvl = a.db.get("adaptive_level", 0.9)
        items = [
            Item(t("menu.chase"), detail=tr("foge ao pelotão que acelera a cada minuto",
                                            "escape a bunch that speeds up every minute"),
                 action=lambda: a.push(ChaseScreen(a)), data="chase"),
            Item(t("game.adaptive"), value=tr("nível {l}", "level {l}", l=f"{lvl:.2f}"),
                 detail=t("game.adaptive.desc"),
                 action=lambda: a.push(GameSetup(a, "adaptive")), data="adaptive"),
            Item(tr("— Jogos —", "— Games —"), enabled=False),
        ]
        for key_ in games_mod.GAMES[1:]:
            items.append(Item(t(f"game.{key_}"), detail=t(f"game.{key_}.desc"),
                              action=lambda k=key_: a.push(GameSetup(a, k)), data=key_))
        self.chrome.set(t("menu.challenge"),
                        tr("Tudo à medida da tua FTP e da tua curva de potência",
                           "All scaled to your FTP and power curve"), self.footer())
        self.list.set_items(items, keep_index=True)


from velo.ui.app import AutoLapOptions  # noqa: E402


class GameSetup(AutoLapOptions, EditScreen):
    """Escolhas antes do jogo: duração, adversários, ERG, rota e auto lap."""

    HAS_BOARD = True
    BOT_OPTIONS = (0, 1, 3, 5, 7)

    def __init__(self, app, game_key: str):
        super().__init__(app)
        from velo.core import games as games_mod
        self.key = game_key
        self.cls = games_mod.CLASSES[game_key]
        self.minutes = self.cls.default_minutes
        self.bots = 1 if game_key == "tug" else (5 if game_key == "elimination" else 4)
        self.erg = self.cls.erg_default
        self.route_idx = 0

    def side_board(self):
        from velo.core import games as games_mod
        return games_mod.leaderboard(self.app.db, self.key)

    def routes(self) -> list:
        return [None] + list(self.app.db.routes())

    def enter(self) -> None:
        from velo.core.i18n import tr
        cls = self.cls
        rs = self.routes()
        route = rs[self.route_idx % len(rs)]
        rows = [Item(t("mode.start"), action=self._start)]
        if cls.has_duration:
            rows.append(Item(tr("Duração", "Duration"), value=f"{self.minutes} min",
                             data="cyc:minutes"))
        if cls.has_bots and self.key != "tug":
            rows.append(Item(tr("Adversários (bots)", "Opponents (bots)"), value=str(self.bots),
                             data="cyc:bots"))
        if self.key in ("adaptive", "ladder"):
            rows.append(Item(t("mode.erg"), value=t("common.on") if self.erg else t("common.off"),
                             detail=tr("com ERG o rolo põe os watts; aguentar é manter a cadência",
                                       "with ERG the trainer sets the watts; hold your cadence"),
                             data="cyc:erg"))
        rows.append(Item(tr("Rota", "Route"), value=route["name"] if route else t("board.no_route"),
                         detail=tr("a estrada é só paisagem; o jogo é igual",
                                   "the road is scenery; the game is the same"),
                         data="cyc:route"))
        rows += self.autolap_items()
        rows.append(Item(tr("Como se joga", "How it works"), detail=t(f"game.{self.key}.desc"),
                         enabled=False))
        self.chrome.set(t(f"game.{self.key}"), f"FTP {self.app.db.athlete().ftp_w} W",
                        self.footer())
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        if field == "minutes":
            ds = list(self.cls.durations)
            i = ds.index(self.minutes) if self.minutes in ds else 0
            self.minutes = ds[(i + step) % len(ds)]
        elif field == "bots":
            bs = list(self.BOT_OPTIONS)
            i = bs.index(self.bots) if self.bots in bs else 0
            self.bots = bs[(i + step) % len(bs)]
        elif field == "erg":
            self.erg = not self.erg
        elif field == "route":
            self.route_idx += step

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.autolap_key(symbol):
            return True
        return super().on_key(symbol, modifiers)

    def spec(self) -> dict:
        return {"key": self.key, "minutes": self.minutes, "bots": self.bots, "erg": self.erg,
                "seed": int(time.time()) % 100000}

    def _start(self) -> None:
        rs = self.routes()
        route = rs[self.route_idx % len(rs)]
        self.app.replace(RideScreen(self.app, route_id=route["id"] if route else None,
                                    workout_id=None, kind="game", ghosts=[], erg=self.erg,
                                    game_spec=self.spec(),
                                    autolap=dict(self.autolap_cfg())))


# ======================================================= treino livre / conditioning


class LapSessionScreen(EditScreen):
    """Sessão por voltas. À esquerda: abrir voltas e os campos da volta atual;
    à direita: a volta a contar, a FC e as voltas já feitas."""

    AGENT = False
    IN_SESSION = True
    LAP_LINES = 10

    def __init__(self, app, mode: str = "free", resume: dict | None = None,
                 plan: list | None = None, autolap: dict | None = None):
        super().__init__(app)
        from velo.core import laps_session as ls
        self.ls = ls
        self.session = ls.LapSession(app.db, app.db.athlete(), mode, sensors=app.hub,
                                     out_dir=app.data_dir / "strength", resume=resume,
                                     rower=getattr(app, "rower", None), plan=plan,
                                     autolap=autolap)
        self.chrome.title.font_size = 18
        self.confirming = False
        self._sig = None
        b = self.batch = pyglet.graphics.Batch()
        self.panel = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
        self.phase_label = make_label("", font_size=26, bold=True, color=ACCENT,
                                      anchor_y="top", batch=b)
        self.hr_label = make_label("", font_size=32, bold=True, color=TEXT, anchor_y="top",
                                   batch=b)
        self.hr_zone_label = make_label("", font_size=13, color=DIM, anchor_y="top",
                                        anchor_x="right", batch=b)
        self.session_label = make_label("", font_size=13, color=DIM, anchor_y="top", batch=b)
        self.lap_lines = [make_label("", font_size=12, color=TEXT, anchor_y="top", batch=b)
                          for _ in range(self.LAP_LINES)]
        from velo.ui.widgets import SessionClock
        self.clock = SessionClock(app.window, batch=b)
        self._layout_panel()

    def _list_width(self, w: int) -> int:
        return int(w * 0.44) - 48

    def _layout_panel(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        x = int(w * 0.44) + 24
        top = h - 120
        pw = w - 48 - x
        self.panel.x, self.panel.y, self.panel.width, self.panel.height = x, 96, pw, top - 96
        self.phase_label.x, self.phase_label.y = x + 20, top - 16
        self.hr_label.x, self.hr_label.y = x + 20, top - 60
        self.hr_zone_label.x, self.hr_zone_label.y = x + pw - 20, top - 78
        self.session_label.x, self.session_label.y = x + 20, top - 112
        for i, lab in enumerate(self.lap_lines):
            lab.x, lab.y = x + 20, top - 144 - i * 22
        self.clock.layout()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout_panel()

    def footer(self) -> str:
        from velo.core.i18n import tr
        return tr("Espaço trabalho ↔ descanso · ←/→ ajustar · escreve números · P pausa · "
                  "Esc terminar", "Space work ↔ rest · ←/→ adjust · type numbers · P pause · "
                  "Esc finish")

    def kind_name(self, k: str) -> str:
        return t(f"laps.kind.{k}")

    def enter(self) -> None:
        from velo.core.i18n import tr
        s = self.session
        if self.confirming:
            self.chrome.set(t("str.confirm_title"), tr("{n} voltas registadas.",
                                                       "{n} laps logged.", n=len(s.laps)),
                            self.footer())
            self.list.set_items([Item(t("str.confirm_no"), action=self._cancel_confirm),
                                 Item(t("str.confirm_yes"), action=self._finish),
                                 Item(tr("Terminar sem guardar", "Finish without saving"),
                                      action=self._discard)])
            return
        order = ("treadmill", "rowing", "strength", "rest", "cardio") \
            if s.mode == "conditioning" else ("strength", "rest", "treadmill", "rowing", "cardio")
        rows = []
        nxt = s.next_planned
        if not s.started and nxt is None:
            rows.append(Item(tr("▶ Começar", "▶ Start"), action=self._start_clock,
                             detail=tr("o relógio só arranca agora", "the clock starts now")))
        if nxt is not None:
            rows.append(Item(tr("▶ Volta do plano: {k}", "▶ Planned lap: {k}",
                                k=self.ls_text(nxt)),
                             detail=tr("{i} de {n} · Espaço", "{i} of {n} · Space",
                                       i=s.plan_idx + 1, n=len(s.plan)),
                             action=self._next_planned, data="planned"))
        rows += [Item(tr("▶ Nova volta: {k}", "▶ New lap: {k}", k=self.kind_name(k)),
                      action=lambda kk=k: self._new(kk), data=f"new:{k}") for k in order]
        lap = s.editable()
        if lap is not None:
            state = tr("a decorrer", "running") if lap.open else tr("fechada", "closed")
            rows.append(Item(tr("— Volta {n} · {k} · {s} —", "— Lap {n} · {k} · {s} —",
                                n=lap.no, k=self.kind_name(lap.kind), s=state), enabled=False))
            if lap.kind == "strength":
                rows.append(Item(t("str.exercise"), value=lap.name or "—",
                                 action=self._pick_exercise))
                unit = " s" if lap.measure == "time" else ""
                rows.append(Item(t("str.seconds") if lap.measure == "time" else t("str.reps"),
                                 value=f"{lap.reps}{unit}" if lap.reps is not None else "—",
                                 data="num:reps"))
                rows.append(Item(t("str.load"), value=_kg(lap.load_kg), data="num:load_kg"))
                rows.append(Item("RPE", value=_rpe(lap.rpe), data="num:rpe",
                                 detail=t("str.rpe_hint")))
            elif lap.kind == "treadmill":
                rows.append(Item(tr("Total no visor (km)", "Total on the display (km)"),
                                 value=f"{lap.odometer_km:.2f} km" if lap.odometer_km is not None
                                 else "—", data="num:odometer_km",
                                 detail=tr("a distância da volta calcula-se: {d}",
                                           "the lap distance is worked out: {d}",
                                           d=f"{lap.distance_km:.2f} km" if lap.distance_km
                                           is not None else "—")))
                rows.append(Item(tr("Velocidade", "Speed"), value=f"{lap.speed_kmh:.1f} km/h"
                                 if lap.speed_kmh is not None else "—", data="num:speed_kmh"))
                rows.append(Item(tr("Inclinação", "Incline"), value=f"{lap.incline_pct:.1f} %"
                                 if lap.incline_pct is not None else "—", data="num:incline_pct"))
            elif lap.kind == "rowing":
                from velo.io.rower import pace_text
                auto = lap.row.get("auto")
                rows.append(Item(tr("Distância (km)", "Distance (km)"),
                                 value=f"{lap.distance_km:.3f} km" if lap.distance_km else "—",
                                 data="num:distance_km",
                                 detail=(tr("da máquina de remo", "from the rowing machine")
                                         if auto else tr("o que o visor da máquina mostra",
                                                         "what the machine display shows"))
                                 + (f" · {pace_text(lap.pace_s)} /500 m" if lap.pace_s else "")))
                rows.append(Item(tr("Resistência (1–15)", "Resistance (1–15)"),
                                 value=str(lap.resistance or "—"), data="num:resistance"))
                rows.append(Item(tr("Voga (remadas/min)", "Stroke rate (spm)"),
                                 value=f"{lap.spm:.0f}" if lap.spm else "—", data="num:spm"))
            elif lap.kind == "cardio":
                rows.append(Item(tr("Distância (km, opcional)", "Distance (km, optional)"),
                                 value=f"{lap.distance_km:.2f} km" if lap.distance_km else "—",
                                 data="num:distance_km"))
            rows.append(Item(tr("Notas", "Notes"), value=lap.notes or "—", data="text:notes"))
            if lap.open:
                rows.append(Item(tr("Fechar a volta", "Close the lap"), action=self._close))
            rows.append(Item(tr("Apagar a última volta", "Delete the last lap"),
                             action=self._delete_last))
        rows += [Item(t("str.resume") if s.paused else t("str.pause"), action=self._pause),
                 Item(t("str.finish"), action=self._ask_finish)]
        self.chrome.set(s.title, tr("{n} voltas · {t}", "{n} laps · {t}", n=len(s.laps),
                                    t=hms(s.t)), self.footer())
        self.list.set_items(rows, keep_index=True)
        self._sig = self._signature()

    def ls_text(self, it: dict) -> str:
        bits = [self.kind_name(it["kind"])]
        if it.get("name"):
            bits.append(it["name"])
        if it.get("seconds"):
            bits.append(hms(it["seconds"]))
        if it.get("km"):
            bits.append(f"{it['km']:g} km")
        if it.get("reps") and it.get("kind") == "strength":
            bits.append(f"{it['reps']}" + (" s" if it.get("measure") == "time" else ""))
        return " · ".join(bits)

    def _start_clock(self) -> None:
        self.session.start()
        self.enter()

    def _next_planned(self) -> None:
        self.session.start_planned()
        self.enter()

    def _discard(self) -> None:
        s = self.session
        s.abort()
        try:
            s.db.conn.execute("DELETE FROM strength_sessions WHERE id = ?", (s.session_id,))
            s.db.conn.commit()
        except Exception:
            pass
        from velo.core.i18n import tr
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

    def _signature(self):
        s = self.session
        lap = s.editable()
        live = None
        if lap is not None and lap.kind == "rowing" and lap.row.get("auto"):
            live = (round(lap.distance_km or 0, 2), lap.resistance, round(lap.spm or 0))
        return (len(s.laps), s.paused, self.confirming, lap.open if lap else None,
                lap.kind if lap else None, live, s.started, s.plan_idx)

    # ações
    def _new(self, kind: str) -> None:
        self.session.start_lap(kind)
        if kind == "strength" and self.session.current.exercise_id is None:
            self._pick_exercise()
            return
        self._focus_fields()
        self.enter()

    def _focus_fields(self) -> None:
        self.list.index = 5            # o primeiro campo da volta, logo a seguir ao título

    def _pick_exercise(self) -> None:
        def picked(ex):
            self.session.set_exercise(ex)
        self.app.push(ExercisePicker(self.app, picked))

    def _close(self) -> None:
        self.session.close_lap()
        self.enter()

    def _delete_last(self) -> None:
        self.session.delete_last()
        self.enter()

    def _pause(self) -> None:
        self.session.toggle_pause()
        self.enter()

    def _ask_finish(self) -> None:
        self.confirming = True
        self.list.index = 0
        self.enter()

    def _cancel_confirm(self) -> None:
        self.confirming = False
        self.enter()

    def _finish(self) -> None:
        result = self.session.finish()
        self.app.replace(LapSummaryScreen(self.app, result))

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        self.session.adjust(field, steps, big)

    def num_set(self, field: str, value) -> None:
        self.session.set_field(field, value)

    def text_input(self, field: str, text: str) -> None:
        lap = self.session.editable()
        if lap is not None:
            self.session.set_field("notes", (lap.notes or "") + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        lap = self.session.editable()
        if lap is not None:
            self.session.set_field("notes", (lap.notes or "")[:-1] or None)
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.confirming:
            if symbol == key.ESCAPE:
                self._cancel_confirm()
                return True
            return super().on_key(symbol, modifiers)
        if self._field("text:") is None:
            if symbol == key.SPACE:
                lap = self.session.toggle()
                if lap.kind == "strength" and lap.exercise_id is None:
                    self._pick_exercise()
                    return True
                self.enter()
                return True
            if symbol == key.P:
                self._pause()
                return True
        if symbol in (key.ESCAPE, key.F10):
            self._ask_finish()
            return True
        return super().on_key(symbol, modifiers)

    def on_text(self, text: str) -> bool:
        if self.confirming:
            return True
        return super().on_text(text) or True

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self._ask_finish()
            return True
        return self.list.on_mouse_press(x, y)

    def leave(self) -> None:
        if not self.session.finished:
            self.session.suspend()

    def update(self, dt: float) -> None:
        a = self.app
        a.hub.tick(dt)
        s = self.session
        s.update(dt)
        for kind, data in s.drain_events():
            if kind == "recovered":
                a.message(t("recover.toast"))
            elif kind == "plan_next":
                a.message(tr("Volta seguinte do plano: {k}", "Next planned lap: {k}",
                             k=self.kind_name(data["kind"])))
            elif kind == "plan_done":
                a.message(tr("Plano cumprido!", "Plan done!"))
        if self._signature() != self._sig:
            self.enter()
        self._update_panel()
        cur = s.current
        lap_t = (s.t - cur.start_t) if cur is not None else 0.0
        self.clock.set(s.t, (tr("volta {t}", "lap {t}", t=hms(lap_t)) if cur is not None
                             else (tr("à espera de começar", "waiting to start")
                                   if not s.started else "")))

    def _update_panel(self) -> None:
        from velo.core.i18n import tr
        from velo.gfx.hud import zone_color
        s = self.session
        cur = s.current
        if s.paused:
            self.phase_label.text, self.phase_label.color = t("str.paused"), DIM
        elif cur is None:
            self.phase_label.text = tr("SEM VOLTA ABERTA", "NO LAP RUNNING")
            self.phase_label.color = TEXT
        else:
            self.phase_label.text = (f"{tr('VOLTA', 'LAP')} {cur.no} · "
                                     f"{self.kind_name(cur.kind).upper()} · "
                                     f"{hms(s.t - cur.start_t)}")
            self.phase_label.color = ACCENT if cur.kind == "rest" else GOOD
        hr, zone = s.hr_bpm, s.hr_zone
        if hr:
            self.hr_label.text = f"{hr} bpm"
            self.hr_label.color = _theme.ink(zone_color(zone or 1, "hr"))
            self.hr_zone_label.text = zone_text(zone, "hr") if zone else ""
        else:
            self.hr_label.text, self.hr_label.color = "— bpm", DIM
            self.hr_zone_label.text = t("str.no_hr")
        summ = s.summary()
        self.session_label.text = tr(
            "Tempo {t} · força {sets} séries, {vol} kg · passadeira {km} km · FC média {hr}",
            "Time {t} · strength {sets} sets, {vol} kg · treadmill {km} km · avg HR {hr}",
            t=hms(s.t), sets=summ["total_sets"], vol=f"{summ['volume_kg']:,.0f}".replace(",", " "),
            km=f"{summ['distance_km']:.2f}", hr=f"{s.avg_hr:.0f}" if s.avg_hr else "—")
        laps = s.laps[-self.LAP_LINES:]
        for i, lab in enumerate(self.lap_lines):
            if i < len(laps):
                lap = laps[len(laps) - 1 - i]
                lab.text = f"{lap.no}. {self.kind_name(lap.kind)} · {hms(lap.seconds)} · " + \
                    lap_text(lap)
                lab.color = TEXT if i else ACCENT
            else:
                lab.text = ""

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


def lap_text(lap) -> str:
    parts = []
    if lap.kind == "strength":
        if lap.name:
            parts.append(lap.name)
        if lap.reps is not None:
            parts.append(_amount(lap.reps, lap.measure)
                         + (f" × {_kg(lap.load_kg)}" if lap.load_kg else ""))
        if lap.rpe:
            parts.append(f"RPE {_rpe(lap.rpe)}")
    elif lap.kind == "treadmill":
        if lap.distance_km is not None:
            parts.append(f"{lap.distance_km:.2f} km")
        if lap.speed_kmh:
            parts.append(f"{lap.speed_kmh:.1f} km/h")
        if lap.incline_pct:
            parts.append(f"{lap.incline_pct:.1f} %")
    elif lap.kind == "cardio" and lap.distance_km:
        parts.append(f"{lap.distance_km:.2f} km")
    elif lap.kind == "rowing":
        from velo.io.rower import pace_text
        if lap.distance_km:
            parts.append(f"{lap.distance_km * 1000:.0f} m")
        if getattr(lap, "pace_s", None):
            parts.append(f"{pace_text(lap.pace_s)} /500 m")
        if getattr(lap, "spm", None):
            parts.append(f"{lap.spm:.0f} spm")
        if getattr(lap, "resistance", None):
            parts.append(f"nível {lap.resistance}")
    if lap.avg_hr:
        parts.append(f"{lap.avg_hr:.0f} bpm")
    return " · ".join(parts)


class LapSummaryScreen(Screen):
    def __init__(self, app, result: dict):
        super().__init__(app)
        self.result = result

    def enter(self) -> None:
        from velo.core.i18n import tr
        a = self.app
        r = self.result
        if not r:
            a.reset_to_menu(_gym_hub())
            return
        items = [Item(t("summary.close"), action=lambda: a.reset_to_menu(_gym_hub()))]

        def add(label, value):
            items.append(Item(label, value=value, enabled=False))
        add(t("metric.elapsed"), hms(r["elapsed_s"]))
        for k, secs in r["time_by_kind"].items():
            if secs:
                add(f"  {t(f'laps.kind.{k}')}", hms(secs))
        if r["total_sets"]:
            add(t("str.sets"), f"{r['total_sets']} · {r['volume_kg']:,.0f} kg".replace(",", " "))
        if r["distance_km"]:
            add(tr("Distância", "Distance"), f"{r['distance_km']:.2f} km")
        if r.get("avg_hr"):
            add(t("metric.avg_hr"), f"{r['avg_hr']:.0f} bpm · máx {r.get('max_hr') or '—'}")
        if r.get("load"):
            add(t("str.load_total"), f"{r['load']:.0f} · " + t(
                "str.load_src_hr" if r.get("load_source") == "hr" else "str.load_src_rpe"))
        for lap in r["laps"]:
            items.append(Item(f"  {lap.no}. {t(f'laps.kind.{lap.kind}')}",
                              value=hms(lap.seconds), detail=lap_text(lap), enabled=False))
        sub = (t("summary.saved_fit", path=r["fit_path"]) if r.get("fit_path")
               else f"{t('common.error')}: o .fit não foi escrito")
        self.chrome.set(t("summary.title"), f"{r.get('title', '')} · {sub}", self.footer())
        fb_item = _feedback().summary_item(self.app, "strength", self.result.get("session_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        self.list.set_items(items)
        _feedback().maybe_ask(self, "strength", self.result.get("session_id"))


def _feedback():
    from velo.ui import feedback_screens
    return feedback_screens


def s_zone(session) -> int | None:
    try:
        return session.hr_zone
    except Exception:
        return None


def _hr_color(zone: int):
    from velo.gfx.hud import zone_color
    return zone_color(zone or 1, "hr")


def _load_screens():
    from velo.ui import load_screens
    return load_screens


def _analysis_screen(app, sid: str):
    from velo.ui.strength_analysis_screens import StrengthAnalysisScreen
    return StrengthAnalysisScreen(app, sid)


def _exercise_stats_screen(app, eid: int | None = None):
    from velo.ui.exercise_stats_screens import ExerciseStatsScreen
    return ExerciseStatsScreen(app, eid)


def _fit_text(text: str, width_px: float, size: float) -> str:
    n = max(6, int(width_px / (size * 0.62)))
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"
