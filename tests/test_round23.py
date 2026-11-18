"""Ronda 23: o fim automático das sessões que não são livres e os textos dentro das caixas.

1. Treino, challenge, teste, fuga ou plano de voltas que acabam sozinhos: o tempo pára e abre-se o
   ecrã «… concluído» com o menu de guardar (como em «Terminar»). Numa sessão livre, nunca.
2. Nenhum texto sai da caixa onde está (medido com uma letra real, ver `tests/textfit.py`).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia.core import gym  # noqa: E402
from perennia.io import rower as rio  # noqa: E402
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import endurance_screens as es  # noqa: E402
from perennia.ui import rowing_screens as rs  # noqa: E402
from perennia.ui import sport_screens as ss  # noqa: E402
from tests import test_gui as tg  # noqa: E402
from tests import textfit  # noqa: E402


def overflow(app) -> list[dict]:
    """O que, no que se desenha agora, não cabe (sem o que está fora do ecrã de propósito)."""
    app._on_draw()
    w, h = app.window.width, app.window.height
    out = []
    for it in textfit.scan_frame(list(pyglet_stub.frame), w, h):
        if it["kind"] == "janela" and it["x0"] < -3000:
            continue                                   # escondido de propósito, fora do ecrã
        out.append(it)
    return out


def resize(app, w: int, h: int) -> None:
    app.window.set_size(w, h)
    app._on_resize(w, h)


# ======================================================= o fim automático


class TestAutoFinishCycling(tg.GuiCase):
    def ride(self, **kw):
        wid = kw.pop("workout_id", None)
        r = app_mod.RideScreen(self.app, route_id=None, workout_id=wid,
                               kind=kw.pop("kind", "workout" if wid else "free"),
                               ghosts=[], erg=True, **kw)
        self.app.push(r)
        r.preparing = False
        r.update(0.5)
        return r

    def test_workout_done_stops_the_clock_and_asks(self):
        r = self.ride(workout_id=self.app.db.workouts()[0]["id"])
        r.engine._emit("workout_done")
        r.update(0.5)
        self.assertTrue(r.hud.finish_dialog.visible)
        self.assertEqual(r.hud.finish_dialog.title.text, "Treino concluído")
        self.assertIn("O tempo parou", r.hud.finish_dialog.sub.text)
        self.assertTrue(r.engine.manual_pause)                 # o tempo pára

    def test_ftp_test_is_called_a_test(self):
        r = self.ride(workout_id=self.app.db.workouts()[0]["id"])
        r.ftp_protocol = "ramp"
        r.engine._emit("workout_done")
        r.update(0.5)
        self.assertEqual(r.hud.finish_dialog.title.text, "Teste concluído")

    def test_game_over_asks_with_the_result(self):
        r = self.ride(kind="game", game_spec={"key": "adaptive", "minutes": 1})
        r.engine._emit("game_over", summary="3.º em 5 · 12:34")
        r.update(0.5)
        d = r.hud.finish_dialog
        self.assertTrue(d.visible)
        self.assertEqual(d.title.text, "Challenge concluído")
        self.assertEqual(d.detail.text, "3.º em 5 · 12:34")

    def test_chase_caught_asks(self):
        r = self.ride()
        r.engine._emit("chase_caught", survived_s=95.0, watts=300, distance_m=900.0)
        r.update(0.5)
        self.assertTrue(r.hud.finish_dialog.visible)
        self.assertEqual(r.hud.finish_dialog.title.text, "Fuga terminada")

    def test_a_free_ride_never_asks(self):
        r = self.ride()
        for _ in range(80):
            r.update(0.5)
        self.assertFalse(r.hud.finish_dialog.visible)

    def test_a_real_short_game_ends_by_itself(self):
        r = self.ride(kind="game", game_spec={"key": "adaptive", "minutes": 1})
        for _ in range(200):                                    # 100 s de sessão simulada
            r.update(0.5)
            if r.hud.finish_dialog.visible:
                break
        self.assertTrue(r.hud.finish_dialog.visible)
        self.assertEqual(r.hud.finish_dialog.title.text, "Challenge concluído")
        self.assertTrue(r.engine.game.finished)

    def test_no_keeps_the_ride_going_and_does_not_ask_again(self):
        r = self.ride(workout_id=self.app.db.workouts()[0]["id"])
        r.engine._emit("workout_done")
        r.update(0.5)
        self.press(key.ESCAPE)                                  # «Não»
        self.assertFalse(r.hud.finish_dialog.visible)
        for _ in range(10):
            r.update(0.5)
        self.assertFalse(r.hud.finish_dialog.visible)


class TestAutoFinishOthers(tg.GuiCase):
    def test_rowing_test_done(self):
        self.app.set_rower(rio.SimulatedRower())
        scr = rs.RowingSessionScreen(self.app)
        self.app.push(scr)
        self.press(key.SPACE)
        self.app._tick(0.5)
        scr._event("test_done", {"value": 450, "unit": "s"})
        self.assertTrue(scr.confirming)
        self.assertEqual(scr.finish_dialog.title.text, "Teste concluído")
        self.assertIn("7:30", scr.finish_dialog.detail.text)
        self.assertTrue(scr._flow_paused())

    def test_rowing_game_over(self):
        self.app.set_rower(rio.SimulatedRower())
        scr = rs.RowingSessionScreen(self.app)
        self.app.push(scr)
        self.press(key.SPACE)
        scr._event("game_over", {"summary": "1.º em 4 · 1:25"})
        self.assertTrue(scr.confirming)
        self.assertEqual(scr.finish_dialog.title.text, "Challenge concluído")
        self.assertEqual(scr.finish_dialog.detail.text, "1.º em 4 · 1:25")

    def test_rowing_free_never_asks(self):
        self.app.set_rower(rio.SimulatedRower())
        scr = rs.RowingSessionScreen(self.app)
        self.app.push(scr)
        self.press(key.SPACE)
        for _ in range(60):
            self.app._tick(0.5)
        self.assertFalse(scr.confirming)

    def test_running_workout_done_title(self):
        scr = es.EnduranceSession(self.app, "running")
        self.app.push(scr)
        scr.engine.start()
        scr._event("workout_done", {})
        self.assertTrue(scr.confirming)
        self.assertEqual(scr.finish_dialog.title.text, "Treino concluído")

    def test_lap_plan_done_asks(self):
        plan = [{"kind": "treadmill", "seconds": 2}]
        scr = ss.LapSessionScreen(self.app, "free", plan=plan)
        self.app.push(scr)
        for _ in range(12):
            self.app._tick(0.5)
        self.assertTrue(scr.confirming)
        self.assertEqual(scr.finish_dialog.title.text, "Plano concluído")
        self.assertTrue(scr._flow_paused())

    def test_lap_session_without_plan_never_asks(self):
        scr = ss.LapSessionScreen(self.app, "free")
        self.app.push(scr)
        for _ in range(30):
            self.app._tick(0.5)
        self.assertFalse(scr.confirming)

    def test_strength_plan_done_title(self):
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = ss.StrengthSessionScreen(self.app, wid)
        self.app.push(scr)
        scr.plan_complete()
        self.assertEqual(scr.finish_dialog.title.text, "Treino concluído")


class TestAutoFinishOption(tg.GuiCase):
    def test_the_option_turns_the_automatic_stop_off(self):
        from perennia.core import options
        from perennia.ui import session_flow as sf
        self.assertTrue(sf.AUTO_FINISH)
        self.app.db.set("session_auto_finish", False)
        options.apply(self.app.db)
        try:
            self.assertFalse(sf.AUTO_FINISH)
            scr = es.EnduranceSession(self.app, "running")
            self.app.push(scr)
            scr.engine.start()
            scr._event("workout_done", {})
            self.assertFalse(scr.confirming)             # continua à vontade
        finally:
            self.app.db.set("session_auto_finish", True)
            options.apply(self.app.db)
        self.assertTrue(sf.AUTO_FINISH)


class TestOptionInBackup(tg.GuiCase):
    def test_the_option_travels_with_the_settings_component(self):
        from perennia.core import backup
        c = next(c for c in backup.COMPONENTS if c.key == "definicoes")
        self.assertTrue(c.settings("session_auto_finish"))
        self.app.db.set("session_auto_finish", False)
        self.assertIn("session_auto_finish", backup._setting_keys(self.app.db, c))


# ================================================ os textos dentro das caixas


@unittest.skipUnless(textfit.available(), "sem a Pillow/letra não há medição")
class TestTextFits(tg.GuiCase):
    LONG = ("Texto muito comprido que não cabe numa linha da caixa onde foi posto e que por isso "
            "tem de ser cortado ou partido em várias linhas sem sair para fora")

    def assertFits(self, where: str):
        bad = overflow(self.app)
        self.assertEqual(bad, [], f"{where}: {bad[:3]}")

    def test_finish_dialog_with_long_texts_at_every_size(self):
        for w, h in ((1024, 640), (1280, 760), (1920, 1080)):
            resize(self.app, w, h)
            r = app_mod.RideScreen(self.app, route_id=None, workout_id=None, kind="free",
                                   ghosts=[], erg=True)
            self.app.push(r)
            r.preparing = False
            r.update(0.5)
            r._ask_finish("Challenge concluído", self.LONG, self.LONG)
            self.assertFits(f"{w}x{h}")
            self.app.pop()

    def test_hud_messages_stay_inside(self):
        resize(self.app, 1024, 640)
        r = app_mod.RideScreen(self.app, route_id=None, workout_id=None, kind="free",
                               ghosts=[], erg=True)
        self.app.push(r)
        r.preparing = False
        r.update(0.5)
        from perennia.gfx.hud import Sign
        import time
        r.hud.sign = Sign("Título " + self.LONG, self.LONG, time.monotonic(), 30.0)
        r.hud.toast(self.LONG)
        r.hud.toast(self.LONG, emphasis=True)
        r.update(0.5)
        self.assertFits("HUD")

    def test_long_item_values_are_cut_not_overflowing(self):
        from perennia.ui.widgets import Item
        scr = self.screen()
        scr.list.set_items([Item("Material", value=self.LONG, enabled=False),
                            Item("Um rótulo comprido " * 4, value=self.LONG, enabled=False),
                            Item("Curto", value="x", detail=self.LONG, enabled=False)])
        self.assertFits("lista")

    def test_builder_subtitle_fits_the_window(self):
        from perennia.ui import builder_screens as bs
        resize(self.app, 1024, 640)
        wid = self.app.db.workouts()[0]["id"]
        scr = bs.BlockBuilder(self.app, "cycling", wid) if hasattr(bs, "BlockBuilder") else None
        if scr is None:
            self.skipTest("sem BlockBuilder")
        self.app.push(scr)
        self.assertFits("construtor")

    def test_tabs_fit_their_boxes(self):
        from perennia.ui.widgets import TabBar, text_px
        bar = TabBar(["Treinar", "Lista de treinos", "Histórico", "Perfil",
                      "Estatísticas e muito mais coisas"], 48, 600, 700)
        for lab, bg in zip(bar.labs, bar.bgs):
            self.assertLessEqual(text_px(lab.text, lab.font_size, True), bg.width)

    def test_pace_setup_and_picker_with_long_names(self):
        from perennia.core import segments as sg
        from perennia.ui import pace_screens as pace
        sg.save_perennia(self.app.db, None, self.route_id, "Subida " + self.LONG, 500, 3000)
        self.app.push(pace.PaceSetup(self.app, "seg_pace"))
        self.assertFits("preparação do Segment Pace")
        scr = self.screen()
        scr.list.index = next(i for i, it in enumerate(scr.list.items)
                              if it.label.startswith("Segmento"))
        scr.list.activate()
        self.assertFits("janela dos segmentos")

    def test_menus_at_the_smallest_window(self):
        """O robô percorre os menus no tamanho mínimo e nada passa do ecrã."""
        self.assertEqual(walk_menus(self, 1024, 640), {})

    def test_menus_at_the_usual_window(self):
        self.assertEqual(walk_menus(self, 1280, 760), {})


def walk_menus(self, w_: int, h_: int) -> dict:
    """O robô percorre os menus num tamanho de janela e junta o texto que não cabe."""
    from tests import test_ui_walk as w
    resize(self.app, w_, h_)
    bad: dict = {}
    walker = w.Walker(self)
    orig = walker.draw

    def draw(where):
        orig(where)
        for it in textfit.scan_frame(list(pyglet_stub.frame), w_, h_):
            if it["kind"] == "janela" and it["x0"] < -3000:
                continue
            if it["text"] in KNOWN_FALSE_ALARMS or it["text"].replace(":", "").isdigit():
                continue
            bad.setdefault((it["text"][:50], it["kind"]), where)

    walker.draw = draw
    self.app.reset_to_menu()
    self.app.stack[0].enter()
    for sport in ("Ciclismo", "Remo", "Corrida", "Natação", "Ginásio"):
        self.app.stack[:] = self.app.stack[:1]
        self.app.stack[0].enter()
        walker.safe(f"abrir {sport}", lambda s=sport: self.pick(s))
        walker.explore(sport)
    self.assertEqual(walker.errors, [])
    return {k: v[-60:] for k, v in bad.items()}



@unittest.skipUnless(textfit.available(), "sem a Pillow/letra não há medição")
class TestTextFitsLargeFont(tg.GuiCase):
    """Com a letra a 125 % (Definições → Aspeto) o texto também fica dentro das caixas."""

    def setUp(self):
        from perennia.gfx import compat
        compat.FONT_PCT = 125                 # antes de a aplicação criar as etiquetas
        super().setUp()

    def tearDown(self):
        from perennia.gfx import compat
        super().tearDown()
        compat.FONT_PCT = 100

    def test_menus_with_a_bigger_font(self):
        self.assertEqual(walk_menus(self, 1280, 760), {})


# o que a medição acusa mas está bem (etiquetas escondidas de propósito ou sobre caixas decorativas)
KNOWN_FALSE_ALARMS = {"Recordes", "POTÊNCIA MÉDIA", "112 bpm", "−", "Pesquisar · Ctrl+F"}


if __name__ == "__main__":
    unittest.main()
