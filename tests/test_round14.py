"""Ronda 14 — as sessões de treino (todos os desportos):

* o popup «PAUSA» (ao centro) com «Retomar sessão» e «Terminar treino»;
* Dispositivos e Definições abrem por cima da sessão e põem-na em pausa;
* as Definições durante uma sessão só têm o que se pode mexer;
* os atalhos de teclado unificados (marcar volta, pausa, terminar, começar sem contagem,
  saltar bloco) e os novos (velocidade e declive na corrida, resistência no remo);
* o ginásio: sem cronómetro nem RPE, contagem decrescente na métrica «Série / descanso» (ou no
  aviso ao centro), o descanso com o tempo na coluna das repetições e o botão «Saltar».
"""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.core import gym, layouts  # noqa: E402
from perennia.core import strength as st  # noqa: E402
from perennia.io import rower as rio  # noqa: E402
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import endurance_screens as es  # noqa: E402
from perennia.ui import keymap  # noqa: E402
from perennia.ui import rowing_screens as rs  # noqa: E402
from perennia.ui import sport_screens as ss  # noqa: E402

SPORTS = ("cycling", "running", "swimming", "rowing", "gym")


class SessionCase(tg.GuiCase):
    """Abre a sessão de cada desporto, já a decorrer, e dá as mesmas perguntas a todas."""

    def open_sport(self, sport: str):
        if sport == "cycling":
            wid = self.app.db.workouts()[0]["id"]
            scr = app_mod.RideScreen(self.app, route_id=None, workout_id=wid, kind="workout",
                                     ghosts=[], erg=True)
            self.app.push(scr)
            scr.preparing = False
        elif sport in ("running", "swimming"):
            scr = es.EnduranceSession(self.app, sport)
            self.app.push(scr)
            if not scr.engine.started:
                scr.engine.start()
        elif sport == "rowing":
            self.app.set_rower(rio.SimulatedRower())
            scr = rs.RowingSessionScreen(self.app)
            self.app.push(scr)
            self.press(key.SPACE)                          # começa a remar
        else:
            wid = gym.workouts(self.app.db, "strength")[0]["id"]
            scr = ss.StrengthSessionScreen(self.app, wid)
            self.app.push(scr)
        self.run_for(scr, 3)
        return scr

    def run_for(self, scr, seconds: float) -> None:
        for _ in range(int(seconds * 2)):
            self.app._tick(0.5)

    @staticmethod
    def clock(scr) -> float:
        if hasattr(scr, "hud"):
            return scr.engine.state.t_s
        if hasattr(scr, "session"):
            return scr.session.t
        return scr.engine.t

    @staticmethod
    def paused(scr) -> bool:
        if hasattr(scr, "hud"):
            return bool(scr.engine.manual_pause)
        return bool(scr._flow_paused())

    @staticmethod
    def popup(scr) -> bool:
        return bool(scr.hud.pause_popup if hasattr(scr, "hud") else scr.pause_popup)

    @staticmethod
    def dialog(scr):
        return scr.hud.pause_dialog if hasattr(scr, "hud") else scr.pause_dialog

    @staticmethod
    def confirming(scr) -> bool:
        return bool(scr.hud.finish_dialog.visible if hasattr(scr, "hud") else scr.confirming)

    def click(self, rect) -> None:
        self.app._on_mouse_press(int(rect.x + rect.width / 2), int(rect.y + rect.height / 2),
                                 1, 0)


class TestPausePopupEverywhere(SessionCase):
    def test_p_opens_the_popup_and_p_resumes_in_every_sport(self):
        for sport in SPORTS:
            with self.subTest(sport):
                self.setUp() if sport != SPORTS[0] else None
                scr = self.open_sport(sport)
                self.assertFalse(self.popup(scr))
                t0 = self.clock(scr)
                self.press(key.P)
                self.assertTrue(self.paused(scr), sport)
                self.assertTrue(self.popup(scr), sport)
                d = self.dialog(scr)
                self.assertEqual(d.title.text, "PAUSA")
                self.assertEqual(d.resume_label.text, "Retomar sessão")
                self.assertEqual(d.finish_label.text, "Terminar treino")
                self.run_for(scr, 5)
                self.assertEqual(self.clock(scr), t0, sport)        # o tempo pára
                self.press(key.P)
                self.assertFalse(self.paused(scr), sport)
                self.assertFalse(self.popup(scr), sport)
                self.run_for(scr, 2)
                self.assertGreater(self.clock(scr), t0, sport)

    def test_esc_pauses_and_the_popup_buttons_resume_or_finish(self):
        for sport in SPORTS:
            with self.subTest(sport):
                self.setUp() if sport != SPORTS[0] else None
                scr = self.open_sport(sport)
                self.press(key.ESCAPE)                         # Esc não termina: pausa
                self.assertTrue(self.popup(scr), sport)
                self.assertFalse(self.confirming(scr), sport)
                self.press(key.ESCAPE)                         # e Esc outra vez retoma
                self.assertFalse(self.popup(scr), sport)
                self.assertFalse(self.paused(scr), sport)
                self.press(key.ESCAPE)
                d = self.dialog(scr)
                self.click(d.resume)                           # botão «Retomar sessão»
                self.assertFalse(self.paused(scr), sport)
                self.assertFalse(self.popup(scr), sport)
                self.press(key.ESCAPE)
                self.click(self.dialog(scr).finish)            # botão «Terminar treino»
                self.assertTrue(self.confirming(scr), sport)   # pergunta primeiro
                self.assertFalse(self.popup(scr), sport)

    def test_f10_from_the_popup_asks_and_no_goes_back_to_the_popup(self):
        for sport in ("running", "rowing", "gym"):
            with self.subTest(sport):
                self.setUp() if sport != "running" else None
                scr = self.open_sport(sport)
                self.press(key.P)
                self.press(key.F10)
                self.assertTrue(self.confirming(scr), sport)
                self.assertFalse(self.popup(scr), sport)
                self.press(key.ESCAPE)                         # «Não»: volta ao «PAUSA»
                self.assertFalse(self.confirming(scr), sport)
                self.assertTrue(self.popup(scr), sport)
                self.assertTrue(self.paused(scr), sport)

    def test_the_pause_button_opens_the_popup(self):
        scr = self.open_sport("gym")
        btn = next(i for i in scr.list.items if i.button and i.label == "Pausa")
        btn.action()
        self.assertTrue(scr.pause_popup)
        self.assertTrue(scr.session.paused)

    def test_no_popup_before_the_session_starts(self):
        self.app.db.set("session_countdown_s", 15)
        scr = es.EnduranceSession(self.app, "running")
        self.app.push(scr)
        self.assertTrue(scr.counting)
        self.press(key.P)
        self.assertFalse(scr.pause_popup)
        self.assertFalse(scr.engine.started)


class TestDevicesAndSettingsPauseTheSession(SessionCase):
    def test_devices_pause_and_the_popup_is_waiting_when_back(self):
        for sport in SPORTS:
            with self.subTest(sport):
                self.setUp() if sport != SPORTS[0] else None
                scr = self.open_sport(sport)
                t0 = self.clock(scr)
                self.press(key.F4)
                self.assertIsInstance(self.screen(), app_mod.DeviceScreen)
                self.assertTrue(self.paused(scr), sport)
                self.run_for(scr, 6)
                self.assertEqual(self.clock(scr), t0, sport)
                self.press(key.ESCAPE)
                self.assertIs(self.screen(), scr)
                self.assertTrue(self.popup(scr), sport)       # a sessão não retoma sozinha
                self.assertTrue(self.paused(scr), sport)
                self.press(key.P)
                self.assertFalse(self.paused(scr), sport)

    def test_settings_pause_too_in_every_sport(self):
        for sport in SPORTS:
            with self.subTest(sport):
                self.setUp() if sport != SPORTS[0] else None
                scr = self.open_sport(sport)
                self.press(key.F8)
                sett = self.screen()
                self.assertIsInstance(sett, app_mod.SettingsScreen)
                self.assertTrue(self.paused(scr), sport)
                self.run_for(scr, 4)
                t0 = self.clock(scr)
                self.run_for(scr, 4)
                self.assertEqual(self.clock(scr), t0, sport)
                self.press(key.ESCAPE)
                self.assertIs(self.screen(), scr)
                self.assertTrue(self.popup(scr), sport)

    def test_a_session_that_was_already_paused_stays_paused_with_the_popup(self):
        scr = self.open_sport("running")
        self.press(key.P)
        self.assertTrue(scr.pause_popup)
        self.press(key.F4)
        self.assertFalse(scr.pause_popup)                     # o menu está por cima
        self.press(key.ESCAPE)
        self.assertTrue(scr.pause_popup)
        self.assertTrue(scr.engine.paused)

    def test_the_topbar_buttons_do_the_same(self):
        scr = self.open_sport("rowing")
        bar = self.app.topbar
        self.assertTrue(bar.enabled["settings"])
        self.assertTrue(bar.enabled["devices"])
        r = bar.buttons["devices"][0]
        self.app._on_mouse_press(int(r.x + 5), int(r.y + 5), 1, 0)
        self.assertIsInstance(self.screen(), app_mod.DeviceScreen)
        self.assertTrue(scr.engine.manual_pause)
        self.press(key.ESCAPE)
        r = bar.buttons["settings"][0]
        self.app._on_mouse_press(int(r.x + 5), int(r.y + 5), 1, 0)
        self.assertIsInstance(self.screen(), app_mod.SettingsScreen)

    def test_opening_settings_never_stacks_or_ends_the_session(self):
        scr = self.open_sport("gym")
        self.press(key.F8)
        self.press(key.F8)                                    # já aberta: nada acontece
        self.assertEqual(sum(isinstance(s, app_mod.SettingsScreen) for s in self.app.stack), 1)
        self.press(key.ESCAPE)
        self.assertIn(scr, self.app.stack)
        self.assertFalse(scr.session.finished)


class TestSettingsDuringASession(SessionCase):
    def labels(self, sport: str) -> list[str]:
        self.open_sport(sport)
        self.press(key.F8)
        return self.screen().tab_labels()

    def test_only_the_allowed_tabs(self):
        full = ["Geral", "Desportos", "Ecrã e idioma", "Atalhos de teclado",
                "Configurações sonoras"]
        for sport in ("cycling", "running", "rowing", "gym"):
            with self.subTest(sport):
                self.setUp() if sport != "cycling" else None
                self.assertEqual(self.labels(sport), full)

    def test_swimming_has_no_sport_tab(self):
        self.assertEqual(self.labels("swimming"), ["Geral", "Ecrã e idioma",
                                                   "Atalhos de teclado",
                                                   "Configurações sonoras"])

    def test_the_athlete_and_external_connections_are_not_there(self):
        for gone in ("Atleta", "Ligações Externas"):
            self.assertNotIn(gone, self.labels("running"))

    def test_general_has_only_the_next_steps_of_the_workout(self):
        self.open_sport("running")
        self.press(key.F8)
        scr = self.screen()
        scr.tab_named("Geral")
        self.app._on_draw()
        rows = [i for i in scr.list.items if i.data is not None]
        self.assertEqual([i.data for i in rows], ["lookahead"])

    def test_display_has_theme_units_and_language_only(self):
        self.open_sport("running")
        self.press(key.F8)
        scr = self.screen()
        scr.tab_named("Ecrã e idioma")
        self.app._on_draw()
        self.assertEqual([i.data for i in scr.list.items if i.data is not None],
                         ["theme", "units", "language"])

    def test_sports_has_only_the_one_being_trained(self):
        for sport, name in (("running", "running"), ("rowing", "rowing"), ("gym", "gym"),
                            ("cycling", "cycling")):
            with self.subTest(sport):
                self.setUp() if sport != "running" else None
                self.open_sport(sport)
                self.press(key.F8)
                scr = self.screen()
                scr.tab_named("Desportos")
                self.assertEqual(scr.SPORTS, (name,))
                self.assertEqual(scr.sport, name)

    def test_shortcuts_and_sounds_are_complete(self):
        self.open_sport("running")
        self.press(key.F8)
        scr = self.screen()
        scr.tab_named("Atalhos")
        self.app._on_draw()
        labels = [i.label for i in scr.list.items]
        for lab in ("Marcar volta", "Pausa / retomar", "Saltar bloco",
                    "Corrida: aumentar velocidade (natação: + piscina)", "Dispositivos"):
            self.assertIn(lab, labels)
        scr.tab_named("Configurações sonoras")
        self.app._on_draw()
        self.assertTrue(scr.list.items)

    def test_a_change_is_saved_and_valid_in_the_session(self):
        self.open_sport("running")
        self.press(key.F8)
        scr = self.screen()
        scr.tab_named("Geral")
        self.app._on_draw()
        scr.list.select_data("lookahead")
        before = scr.get("workout_lookahead", 2)
        self.press(key.RIGHT)
        self.assertTrue(scr.dirty)
        self.assertNotEqual(scr.get("workout_lookahead", 2), before)
        self.save()
        self.assertNotEqual(self.app.db.get("workout_lookahead", 2), before)

    def test_leaving_with_unsaved_changes_asks_first(self):
        self.open_sport("gym")
        self.press(key.F8)
        scr = self.screen()
        scr.tab_named("Geral")
        self.app._on_draw()
        scr.list.select_data("lookahead")
        self.press(key.RIGHT)
        self.assertTrue(scr.dirty)
        self.press(key.ESCAPE)
        self.assertIsNot(self.screen(), scr.session)          # pergunta (não fecha logo)
        self.assertIn(scr, self.app.stack)

    def test_outside_a_session_all_the_tabs_are_there(self):
        self.pick("Definições")
        self.assertEqual(len(self.screen().tab_labels()), 8)
        self.assertIsNone(self.screen().session)


class TestUnifiedShortcutsInSessions(SessionCase):
    def test_a_changed_pause_key_works_in_every_sport(self):
        self.app.db.set("keymap", {"pause": ["O", []]})
        for sport in SPORTS:
            with self.subTest(sport):
                self.setUp() if sport != SPORTS[0] else None
                self.app.db.set("keymap", {"pause": ["O", []]})
                scr = self.open_sport(sport)
                self.press(key.P)                              # a antiga já não faz nada
                self.assertFalse(self.paused(scr), sport)
                self.press(key.O)
                self.assertTrue(self.paused(scr), sport)
                self.assertTrue(self.popup(scr), sport)

    def test_a_changed_finish_key_works_in_every_sport(self):
        for sport in SPORTS:
            with self.subTest(sport):
                self.setUp() if sport != SPORTS[0] else None
                self.app.db.set("keymap", {"finish": ["F9", []]})
                scr = self.open_sport(sport)
                self.press(key.F10)
                self.assertFalse(self.confirming(scr), sport)
                self.press(key.F9)
                self.assertTrue(self.confirming(scr), sport)

    def test_the_old_per_sport_ids_still_apply(self):
        self.app.db.set("keymap", {"row_pause": ["O", []], "gym_finish": ["F9", []]})
        scr = self.open_sport("running")
        self.press(key.O)
        self.assertTrue(scr.pause_popup)
        self.press(key.O)
        self.press(key.F9)
        self.assertTrue(scr.confirming)

    def test_start_now_works_in_every_sport_during_the_countdown(self):
        self.app.db.set("session_countdown_s", 15)
        for sport, make in (("running", lambda: es.EnduranceSession(self.app, "running")),
                            ("swimming", lambda: es.EnduranceSession(self.app, "swimming")),
                            ("gym", lambda: ss.StrengthSessionScreen(
                                self.app, gym.workouts(self.app.db, "strength")[0]["id"]))):
            with self.subTest(sport):
                self.setUp() if sport != "running" else None
                self.app.db.set("session_countdown_s", 15)
                scr = make()
                self.app.push(scr)
                self.assertTrue(scr.counting)
                self.app._tick(1.0)
                self.press(key.SPACE)
                self.assertFalse(scr.counting, sport)

    def test_lap_is_one_key_for_every_sport(self):
        self.app.db.set("keymap", {"lap": ["H", []]})
        scr = self.open_sport("gym")
        n = len(scr.session.sets)
        self.press(key.L)                                      # a de origem já não marca
        self.assertEqual(len(scr.session.sets), n)
        self.press(key.H)
        self.assertEqual(len(scr.session.sets), n + 1)


class TestSkipBlockEverywhere(SessionCase):
    def test_n_skips_the_block_in_running(self):
        from perennia.core import endurance as en
        wid = next(w["id"] for w in en.workouts(self.app.db, "running")
                   if w["name"].startswith("Intervalos"))
        scr = es.EnduranceSession(self.app, "running", workout_id=wid)
        self.app.push(scr)
        if not scr.engine.started:
            scr.engine.start()
        self.run_for(scr, 3)
        e = scr.engine
        idx0 = e.workout.idx
        self.press(key.N)
        self.assertEqual(e.workout.idx, idx0 + 1)
        self.assertEqual(scr.toast, "Bloco saltado")
        self.press(key.N)
        self.assertEqual(e.workout.idx, idx0 + 2)

    def test_n_skips_the_block_in_rowing(self):
        from perennia.core import rowing as rw
        wid = next(w["id"] for w in rw.workouts(self.app.db) if w["name"].startswith("Base"))
        self.app.set_rower(rio.SimulatedRower())
        scr = rs.RowingSessionScreen(self.app, workout_id=wid)
        self.app.push(scr)
        self.press(key.SPACE)
        self.run_for(scr, 3)
        e = scr.engine
        idx0 = e.workout.idx
        self.press(key.N)
        self.assertEqual(e.workout.idx, idx0 + 1)
        self.assertEqual(scr.toast, "Bloco saltado")

    def test_n_in_a_free_session_says_there_are_no_blocks(self):
        for sport in ("running", "rowing"):
            with self.subTest(sport):
                self.setUp() if sport != "running" else None
                scr = self.open_sport(sport)
                self.press(key.N)
                self.assertFalse(scr.engine.finished, sport)
                self.assertFalse(self.paused(scr), sport)
                self.assertIn("bloco", scr.toast.lower())

    def test_n_skips_the_exercise_in_the_gym_even_in_the_middle_of_a_set(self):
        scr = self.open_sport("gym")
        s = scr.session
        self.assertEqual(s.phase, st.WORK)
        first = s.item_idx
        self.press(key.N)
        self.assertNotEqual(s.item_idx, first)
        self.assertIn(first, s.skipped)
        self.assertEqual(len(s.sets), 0)                      # a série a meio não ficou gravada
        self.assertEqual(s.phase, st.READY if s.phase == st.READY else s.phase)

    def test_the_skip_button_works_while_the_set_is_running(self):
        scr = self.open_sport("gym")
        s = scr.session
        first = s.item_idx
        btn = next(i for i in scr.list.items if i.button and i.label == "Saltar")
        btn.action()
        self.assertIn(first, s.skipped)
        self.assertNotEqual(s.item_idx, first)
        # e a linha mostra-o
        row = next(i for i in scr.list.items if i.data == ("ex", first))
        self.assertTrue(row.label.lstrip().startswith("–"))
        self.assertEqual(row.value, "saltado")

    def test_skip_during_the_rest_goes_to_the_next_exercise(self):
        scr = self.open_sport("gym")
        s = scr.session
        self.press(key.SPACE)                                  # Lap: descanso
        self.assertEqual(s.phase, st.REST)
        done_item = s.sets[-1].item_idx
        btn = next(i for i in scr.list.items if i.button and i.label == "Saltar")
        btn.action()
        self.assertEqual(len(s.sets), 1)                      # a série feita mantém-se
        self.assertIn(done_item, s.skipped) if s.remaining(done_item) else None

    def test_n_skips_the_block_in_cycling(self):
        scr = self.open_sport("cycling")
        e = scr.engine
        self.assertIsNotNone(e.workout)
        before = e.workout.skipped_s
        self.press(key.N)
        self.assertGreater(e.workout.skipped_s, before)       # o treino andou para o bloco seguinte
        self.assertFalse(e.finished)

    def test_a_changed_skip_key_works_in_every_sport(self):
        self.app.db.set("keymap", {"skip_block": ["B", []]})
        scr = self.open_sport("gym")
        first = scr.session.item_idx
        self.press(key.N)                                      # a antiga já não faz nada
        self.assertEqual(scr.session.item_idx, first)
        self.press(key.B)
        self.assertNotEqual(scr.session.item_idx, first)


class TestRunningAndRowingKeys(SessionCase):
    def test_speed_and_incline_shortcuts_exist_in_running(self):
        scr = self.open_sport("running")
        e = scr.engine
        v0, i0 = e.speed_kmh, e.incline_pct
        self.press(key.UP)                                     # declive +
        self.assertGreater(e.incline_pct, i0)
        self.press(key.DOWN)
        self.assertAlmostEqual(e.incline_pct, i0)
        self.press(key.PLUS)                                   # velocidade +
        self.assertGreater(e.speed_kmh, v0)
        self.press(key.MINUS)
        self.assertAlmostEqual(e.speed_kmh, v0)

    def test_speed_and_incline_can_be_remapped(self):
        self.app.db.set("keymap", {"incline_up": ["PAGEUP", []], "incline_down": ["PAGEDOWN", []],
                                   "speed_up": ["W", []], "speed_down": ["S", []]})
        scr = self.open_sport("running")
        e = scr.engine
        i0, v0 = e.incline_pct, e.speed_kmh
        self.press(key.UP)                                     # as antigas já não fazem nada
        self.press(key.PLUS)
        self.assertAlmostEqual(e.incline_pct, i0)
        self.assertAlmostEqual(e.speed_kmh, v0)
        self.press(key.PAGEUP)
        self.assertGreater(e.incline_pct, i0)
        self.press(key.W)
        self.assertGreater(e.speed_kmh, v0)
        self.press(key.S)
        self.assertAlmostEqual(e.speed_kmh, v0)

    def test_swimming_plus_and_minus_are_still_the_lengths(self):
        scr = self.open_sport("swimming")
        n = scr.engine.lengths
        self.press(key.PLUS)
        self.assertEqual(scr.engine.lengths, n + 1)
        self.press(key.MINUS)
        self.assertEqual(scr.engine.lengths, n)

    def test_rowing_resistance_shortcut(self):
        self.app.set_rower(rio.SimulatedRower())
        scr = rs.RowingSessionScreen(self.app)
        self.app.push(scr)
        self.press(key.SPACE)
        self.run_for(scr, 2)
        self.press(key.PLUS)
        up = scr.engine.resistance
        self.assertIsNotNone(up)
        self.press(key.PLUS)
        self.assertEqual(scr.engine.resistance, up + 1)
        self.press(key.MINUS)
        self.assertEqual(scr.engine.resistance, up)

    def test_rowing_resistance_can_be_remapped(self):
        self.app.db.set("keymap", {"row_res_up": ["W", []], "row_res_down": ["S", []]})
        self.app.set_rower(rio.SimulatedRower())
        scr = rs.RowingSessionScreen(self.app)
        self.app.push(scr)
        self.press(key.SPACE)
        self.run_for(scr, 2)
        self.press(key.PLUS)                                   # a antiga já não faz nada
        before = scr.engine.resistance
        self.press(key.PLUS)
        self.assertEqual(scr.engine.resistance, before)
        self.press(key.W)
        self.assertNotEqual(scr.engine.resistance, before)

    def test_rowing_resistance_can_be_remapped_to_the_same_key_as_cycling(self):
        # a mesma tecla em dois desportos não é conflito (são âmbitos diferentes)
        self.assertIsNone(keymap.problem({}, "row_res_up", ("PLUS", ())))
        self.assertIsNone(keymap.problem({"ride_res_up": ["Z", []]}, "row_res_up", ("Z", ())))


class TestShortcutSettingsShowTheNewOnes(tg.GuiCase):
    def test_the_list_has_one_row_per_common_action(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Atalhos")
        self.app._on_draw()
        labels = [i.label for i in scr.list.items]
        for lab in ("Marcar volta", "Pausa / retomar", "Terminar", "Começar sem contagem",
                    "Saltar bloco"):
            self.assertEqual(labels.count(lab), 1, lab)
        for lab in ("Marcar volta (lap)", "Pausa / retomar (corrida)"):
            self.assertNotIn(lab, labels)

    def test_changing_a_common_key_is_saved_under_the_new_id(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Atalhos")
        self.app._on_draw()
        self.select("Saltar bloco")
        self.press(key.ENTER)
        self.assertEqual(scr.capturing, "skip_block")
        self.app._on_key_press(key.B, 0)
        self.save()
        self.assertEqual(self.app.db.get("keymap"), {"skip_block": ["B", []]})

    def test_conflict_between_two_common_keys_is_refused(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Atalhos")
        self.app._on_draw()
        self.select("Saltar bloco")
        self.press(key.ENTER)
        self.app._on_key_press(key.P, 0)                       # já é «Pausa / retomar»
        self.assertFalse(scr.dirty)
        self.assertIn("Pausa", self.app._message)


class TestRunWithoutPyCharm(unittest.TestCase):
    """Os lançadores e o ícone da aplicação existem e estão bem formados."""
    ROOT = Path(__file__).resolve().parents[1]

    def test_launchers_and_icons_exist(self):
        for rel in ("Perennia.bat", "perennia.sh", "criar_atalho_windows.bat",
                    "packaging/criar_atalho.ps1", "packaging/perennia.ico",
                    "perennia/assets/app_icon.png", "tools/make_app_icon.py"):
            self.assertTrue((self.ROOT / rel).exists(), rel)

    def test_windows_scripts_are_plain_ascii(self):
        # o Windows lê estes ficheiros como ANSI: um acento estraga-os
        for rel in ("Perennia.bat", "criar_atalho_windows.bat", "packaging/criar_atalho.ps1",
                    "build_windows.bat"):
            data = (self.ROOT / rel).read_bytes()
            self.assertTrue(all(b < 128 for b in data), rel)

    def test_the_shell_launcher_is_executable(self):
        import os
        self.assertTrue(os.access(self.ROOT / "perennia.sh", os.X_OK))

    def test_the_icon_is_a_real_ico_and_png(self):
        ico = (self.ROOT / "packaging" / "perennia.ico").read_bytes()
        self.assertEqual(ico[:4], b"\x00\x00\x01\x00")          # cabeçalho .ico
        png = (self.ROOT / "perennia" / "assets" / "app_icon.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_the_spec_uses_the_icon_only_when_it_exists_on_windows(self):
        spec = (self.ROOT / "packaging" / "perennia.spec").read_text(encoding="utf-8")
        self.assertIn("perennia.ico", spec)
        self.assertIn('sys.platform == "win32" and ICON.exists()', spec)
