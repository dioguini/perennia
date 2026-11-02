"""A janela «preparar a sessão» (ciclismo, corrida, remo), a ficha do treino
com «Configurar sessão de treino», o Challenge e os Testes em janela, o
aviso do Strava sem internet e os níveis do rolo nas Definições."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import fitness_tests as ft  # noqa: E402
from velo.core import rowing as rw  # noqa: E402
from velo.core import workout_meta as wm  # noqa: E402
from velo.io import rower as rio  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import brief as br  # noqa: E402
from velo.ui import endurance_screens as es  # noqa: E402
from velo.ui import session_setup as ss  # noqa: E402


class FakeStrava:
    """Um Strava «ligado» cujo pedido falha (sem internet) ou responde."""

    def __init__(self, fail: bool):
        self.fail = fail
        self.connected = True

    def explore(self, box):
        if self.fail:
            raise OSError("Network is unreachable")
        return []

    def segment(self, sid):
        return {}


class TestStartChoice(tg.GuiCase):
    def test_session_asks_free_or_load_workout(self):
        self.pick("Sessão de treino")
        labels = [i.label for i in self.screen().list.items]
        self.assertEqual(labels, ["Cancelar", "Carregar treino", "Livre"])
        self.pick("Carregar treino")
        hub = self.screen()
        self.assertIsInstance(hub, app_mod.MainMenu)
        self.assertEqual(hub.tab_labels()[hub.tab], "Lista de treinos")

    def test_free_cycling_needs_a_route(self):
        self.app.db.delete_route(self.route_id)
        self.pick("Sessão de treino")
        self.pick("Livre")
        setup = self.screen()
        self.assertIsInstance(setup, ss.SessionSetup)
        self.assertIsNone(setup.route_id)
        start = next(i for i in setup.list.items if i.label == "Começar")
        self.assertFalse(start.enabled)
        # carregar um .gpx novo: a janela do seletor e, depois, a rota escolhida
        self.pick("Carregar um .gpx novo")
        picker = self.screen()
        self.assertIsInstance(picker, ss.GpxPickerPopup)
        self.assertTrue(picker.MODAL)
        picker._import(tg.GPX)
        self.assertIs(self.screen(), setup)
        self.assertIsNotNone(setup.route_id)
        self.assertEqual(setup.new_route, setup.route_id)
        start = next(i for i in setup.list.items if i.label == "Começar")
        self.assertTrue(start.enabled)

    def test_free_cycling_starts_on_the_route(self):
        self.pick("Sessão de treino")
        self.pick("Livre")
        setup = self.screen()
        self.assertEqual(setup.route_id, self.route_id)        # a primeira rota
        self.select("Rota (.gpx)")
        self.press(key.ENTER)                                  # Enter não muda valores
        self.assertEqual(setup.route_id, self.route_id)
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        self.assertEqual(ride.route_id, self.route_id)

    def test_devices_row_opens_pairing(self):
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Aparelhos")
        self.assertIsInstance(self.screen(), app_mod.DeviceScreen)


class TestStravaOffline(tg.GuiCase):
    def _setup(self, fail: bool) -> ss.SessionSetup:
        self.pick("Sessão de treino")
        self.pick("Livre")
        setup = self.screen()
        setup.strava_client = lambda: FakeStrava(fail)
        setup.enter()
        return setup

    def _fetch(self, setup) -> None:
        self.pick("Segmentos do Strava")
        self.assertIsNotNone(setup.job)
        setup.job.thread.join(5)
        setup.update(0.1)

    def test_offline_warns_and_lets_you_go_on(self):
        setup = self._setup(fail=True)
        self._fetch(setup)
        warn = self.screen()
        self.assertIsInstance(warn, app_mod.ConfirmScreen)
        self.assertIn("Strava", warn.title_text)
        self.assertEqual([i.label for i in warn.list.items],
                         ["Cancelar a sessão", "Prosseguir sem Strava"])
        self.pick("Prosseguir sem Strava")
        self.assertIs(self.screen(), setup)
        self.assertTrue(setup.strava_skipped)
        self.pick("Começar")                                   # e a sessão começa na mesma
        self.assertIsInstance(self.screen(), app_mod.RideScreen)

    def test_offline_cancel_closes_the_setup(self):
        setup = self._setup(fail=True)
        self._fetch(setup)
        self.pick("Cancelar a sessão")
        self.assertIsInstance(self.screen(), app_mod.MainMenu)
        self.assertNotIn(setup, self.app.stack)

    def test_online_fetch_has_no_warning(self):
        setup = self._setup(fail=False)
        self._fetch(setup)
        self.assertIs(self.screen(), setup)
        self.assertFalse(setup.strava_skipped)


class TestWorkoutBriefAndSetup(tg.GuiCase):
    def test_brief_has_bottom_right_actions_and_enter_sets_up(self):
        self.pick("Lista de treinos")
        self.pick("VO2máx 5×4")
        brief = self.screen()
        self.assertIsInstance(brief, br.CyclingBrief)
        buttons = [i for i in brief.list.items if i.button]
        self.assertEqual(len(buttons), len(brief.list.items))   # só botões, em baixo
        self.assertEqual(buttons[-1].label, "Configurar sessão de treino")
        self.assertTrue(buttons[-1].primary)
        self.press(key.ENTER)                                   # a principal já está escolhida
        setup = self.screen()
        self.assertIsInstance(setup, ss.SessionSetup)
        self.assertEqual(setup.kind, "workout")
        self.assertIsNone(setup.route_id)                       # rota opcional

    def test_manual_workout_has_no_erg_row(self):
        wid = self.app.db.workouts()[0]["id"]
        wm.save(self.app.db, "cycling", wid, "manual", "level", [])
        setup = ss.SessionSetup(self.app, "cycling", kind="workout", workout_id=wid)
        self.app.push(setup)
        labels = [i.label for i in setup.list.items]
        self.assertNotIn("Modo ERG", labels)
        self.assertIn("Tipo do treino", labels)
        self.assertFalse(setup.erg)


class TestChallengeAndTestsPopups(tg.GuiCase):
    def test_game_popup_has_how_to_play_and_no_erg(self):
        self.pick("Challenge")
        self.pick("Desafio adaptativo")
        setup = self.screen()
        self.assertIsInstance(setup, ss.GameSetup)
        self.assertTrue(setup.MODAL)
        self.assertTrue(setup.chrome.subtitle.text.startswith("Como se joga"))
        labels = [i.label for i in setup.list.items]
        self.assertNotIn("Modo ERG", labels)
        for want in ("Duração", "Rota (.gpx)", "Carregar um .gpx novo", "Segmentos do Strava",
                     "Auto lap"):
            self.assertIn(want, labels)

    def test_cycling_test_has_configure_button_and_no_log_result(self):
        self.pick("Testes")
        self.pick("5 minutos")
        det = self.screen()
        labels = [i.label for i in det.list.items]
        self.assertNotIn("Registar um resultado", labels)
        buttons = [i.label for i in det.list.items if i.button]
        self.assertEqual(buttons, ["Editar o teste", "Configurar sessão"])
        # Enter numa linha sem ação configura a sessão
        det._configure()
        self.assertIsInstance(self.screen(), ss.SessionSetup)
        self.assertEqual(self.screen().kind, "ftp_test")

    def test_adding_a_test_is_a_bottom_right_button(self):
        self.pick("Testes")
        menu = self.screen()
        add = [i for i in menu.list.items if i.button and "Adicionar teste" in i.label]
        self.assertTrue(add)


class TestRunningAndRowing(tg.GuiCase):
    def test_running_with_a_gpx_shows_the_incline(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        setup = self.screen()
        self.select("Rota (.gpx)")
        self.press(key.RIGHT)
        self.assertEqual(setup.route_id, self.route_id)
        self.pick("Começar")
        ses = self.screen()
        self.assertIsInstance(ses, es.EnduranceSession)
        self.press(key.SPACE)
        for _ in range(20):
            self.app._tick(0.5)
        self.assertIn("Serra de Teste", ses.route_line())
        self.assertIn("põe", ses.route_line())
        self.assertIn("Rota", ses.plan.text)

    def test_manual_rowing_workout_only_shows_the_resistance(self):
        rower = rio.SimulatedRower()
        self.app.set_rower(rower)
        wid = rw.workouts(self.app.db)[0]["id"]
        wm.save(self.app.db, "rowing", wid, "manual", "power", [])
        eng = rw.RowEngine(self.app.db, self.app.db.athlete(), rower, workout_id=wid,
                           out_dir=Path(self.tmp) / "row")
        self.assertFalse(eng.erg)
        rower.commands.clear()
        eng._apply_step()
        self.assertFalse([c for c in rower.commands if c[0] == "resistance"])


class TestTrainerLevelsSetting(tg.GuiCase):
    def test_levels_are_set_in_sessions_tab(self):
        self.pick("Definições")
        scr = self.screen()
        self.select("número de níveis")
        self.press(key.RIGHT)
        self.assertTrue(scr.dirty)
        self.select("watts no nível máximo")
        self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)        # +50 W
        self.save()
        lv = wm.levels(self.app.db)
        self.assertEqual(lv["n"], 11)
        self.assertEqual(lv["w_max"], 450.0)

    def test_back_to_the_same_value_is_not_a_change(self):
        self.pick("Definições")
        scr = self.screen()
        self.select("número de níveis")
        self.press(key.RIGHT, key.LEFT)
        self.assertFalse(scr.dirty)


if __name__ == "__main__":
    import unittest
    unittest.main()
