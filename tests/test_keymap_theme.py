"""Atalhos de teclado personalizáveis, Sincronização por separadores e a
pré-visualização do tema."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.gfx import theme as theme_mod  # noqa: E402
from velo.ui import keymap  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402


class TestKeymapCore(tg.GuiCase):
    def test_translate_new_key_to_the_original(self):
        raw = {"lap": ["H", []]}
        self.assertEqual(keymap.translate(raw, "ride", key.H, 0), (key.L, 0))
        self.assertIsNone(keymap.translate(raw, "ride", key.L, 0))   # a antiga deixa de marcar
        # é uma só definição: vale em todos os desportos
        for scope in ("rowing", "endurance", "gym"):
            self.assertEqual(keymap.translate(raw, scope, key.H, 0), (key.L, 0), scope)
            self.assertIsNone(keymap.translate(raw, scope, key.L, 0), scope)
        # noutro âmbito nada muda
        self.assertEqual(keymap.translate(raw, None, key.H, 0), (key.H, 0))
        self.assertEqual(keymap.translate(raw, None, key.L, 0), (key.L, 0))

    def test_old_per_sport_shortcuts_become_the_single_one(self):
        old = {"ride_lap": ["K", []], "row_lap": ["M", []], "gym_pause": ["O", []],
               "run_start": ["B", []], "ride_finish": ["F9", []]}
        got = keymap.custom_map(old)
        self.assertEqual(got["lap"], ["K", []])                 # a primeira que encontra
        self.assertEqual(got["pause"], ["O", []])
        self.assertEqual(got["start_now"], ["B", []])
        self.assertEqual(got["finish"], ["F9", []])
        self.assertNotIn("ride_lap", got)
        self.assertEqual(keymap.binding(old, "lap"), ("K", ()))
        # a definição nova ganha à antiga
        self.assertEqual(keymap.custom_map({"ride_lap": ["K", []], "lap": ["H", []]})["lap"],
                         ["H", []])
        # lixo antigo ou desconhecido não rebenta
        self.assertEqual(keymap.custom_map({"ride_pause": ["ZZ", []], "xx": ["A", []]}), {})

    def test_every_sport_hears_the_five_common_actions(self):
        common = ("lap", "pause", "finish", "start_now", "skip_block")
        self.assertEqual(list(keymap.actions_in("session")), list(common))
        for scope in keymap.SESSION_SCOPES:
            live = [a[0] for a in keymap._live(scope)]
            for a in common:
                self.assertIn(a, live, (scope, a))
        self.assertNotIn("lap", [a[0] for a in keymap._live("builder")])

    def test_new_shortcuts_exist_with_their_defaults(self):
        self.assertEqual(keymap.default("skip_block"), ("N", ()))
        self.assertEqual(keymap.default("speed_up"), ("PLUS", ()))
        self.assertEqual(keymap.default("incline_up"), ("UP", ()))
        self.assertEqual(keymap.default("row_res_up"), ("PLUS", ()))
        self.assertEqual(keymap.default("ride_res_down"), ("MINUS", ()))
        for a in ("speed_up", "speed_down", "incline_up", "incline_down",
                  "row_res_up", "row_res_down", "ride_res_up", "ride_res_down"):
            self.assertTrue(keymap.label(a))
        self.assertIsNone(keymap.problem({}, "incline_up", ("PAGEUP", ())))
        self.assertIsNotNone(keymap.problem({}, "skip_block", ("PLUS", ())))

    def test_conflicts_and_reserved_keys(self):
        self.assertIsNotNone(keymap.problem({}, "lap", ("P", ())))       # é a pausa
        self.assertIsNotNone(keymap.problem({}, "lap", ("N", ())))       # é saltar bloco
        self.assertIsNotNone(keymap.problem({}, "devices", ("J", ())))   # navega
        self.assertIsNotNone(keymap.problem({}, "lap", ("J", ())))       # muda de linha no ginásio
        self.assertIsNone(keymap.problem({}, "devices", ("J", ("ctrl",))))
        self.assertIsNone(keymap.problem({}, "lap", ("K", ("ctrl",))))
        self.assertIsNone(keymap.problem({}, "lap", ("H", ())))
        self.assertIsNone(keymap.problem({}, "row_res_up", ("PLUS", ())))
        self.assertIsNotNone(keymap.problem({}, "incline_up", ("PLUS", ())))


class TestShortcutsSettings(tg.GuiCase):
    def _open(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Atalhos")
        return scr

    def test_change_a_key_with_save(self):
        scr = self._open()
        self.select("Dispositivos")
        self.press(key.ENTER)
        self.assertEqual(scr.capturing, "devices")
        self.app._on_key_press(key.F4, 0)      # durante a captura não abre nada
        self.assertIs(self.screen(), scr)
        self.assertEqual(scr.capturing, None)  # F4 é a de origem: fica igual
        self.press(key.ENTER)
        self.app._on_key_press(key.F6, 0)
        self.assertTrue(scr.dirty)
        self.assertEqual(scr.list.selected.value, "F6")
        self.save()
        self.assertEqual(self.app.db.get("keymap"), {"devices": ["F6", []]})
        self.press(key.ESCAPE)                   # sai das Definições
        self.app._on_key_press(key.F6, 0)
        self.assertIsInstance(self.screen(), app_mod.DeviceScreen)

    def test_conflict_is_refused(self):
        scr = self._open()
        self.select("Dispositivos")
        self.press(key.ENTER)
        self.app._on_key_press(key.F8, 0)        # já é «Definições»
        self.assertEqual(scr.capturing, "devices")
        self.assertIn("já é", self.app._message)
        self.press(key.ESCAPE)                   # desiste
        self.assertIsNone(scr.capturing)
        self.assertFalse(scr.dirty)

    def test_cancel_and_restore(self):
        scr = self._open()
        self.select("Dispositivos")
        self.press(key.ENTER)
        self.app._on_key_press(key.F6, 0)
        self.pick("Cancelar")
        self.assertFalse(scr.dirty)
        self.app.db.set("keymap", {"devices": ["F6", []]})
        scr.enter()
        self.pick("Repor as teclas de origem")
        self.save()
        self.assertEqual(self.app.db.get("keymap"), {})


class TestSyncTabs(tg.GuiCase):
    def test_sync_has_a_tab_per_source(self):
        scr = self.open_sync()
        self.assertEqual(scr.sync.source_labels(), ["GarminDB", "HRV4Training", "Análises",
                                                    "TrainingPeaks", "Upload manual", "CSV", "Saúde"])
        self.assertEqual(scr.sync_tabs.current, "GarminDB")
        self.assertNotIn("Fonte", [i.label for i in scr.list.items])
        self.app._on_draw()


class TestThemePreview(tg.GuiCase):
    def _theme_row(self):
        self.pick("Definições")
        self.screen().tab_named("Ecrã e idioma")
        self.select("Tema")

    def test_changing_the_theme_shows_it_before_saving(self):
        before = theme_mod.P
        saved = self.app.db.get("theme", None)
        self._theme_row()
        self.press(key.RIGHT)
        scr = self.screen()
        self.assertIsInstance(scr, app_mod.SettingsScreen)
        self.assertIsNot(theme_mod.P, before)                 # já se vê
        self.assertEqual(self.app.db.get("theme", None), saved)  # mas não está gravado
        self.assertTrue(scr.dirty)
        self.assertEqual(scr.list.selected.label, "Tema")
        self.save()
        self.assertNotEqual(self.app.db.get("theme", None), saved)

    def test_cancel_puts_the_saved_theme_back(self):
        before = theme_mod.P
        self._theme_row()
        self.press(key.RIGHT)
        self.pick("Cancelar")
        self.assertIs(theme_mod.P, before)
        self.assertFalse(self.screen().dirty)

    def test_leaving_without_saving_puts_it_back(self):
        before = theme_mod.P
        self._theme_row()
        self.press(key.RIGHT)
        self.press(key.ESCAPE)
        self.pick("Sair sem guardar")
        self.assertIs(theme_mod.P, before)
        self.assertIsInstance(self.screen(), app_mod.HomeScreen)

    def tearDown(self):
        theme_mod.apply(theme_mod.DEFAULT)
        super().tearDown()


if __name__ == "__main__":
    import unittest
    unittest.main()
