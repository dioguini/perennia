"""O ecrã da sessão 100% personalizável: a disposição dos painéis (grelha),
o editor que os arrasta e redimensiona, e as sessões que a seguem."""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia.core import screen_layout as sl  # noqa: E402
from perennia.core.db import Database  # noqa: E402
from perennia.io import rower as rio  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import arrangement_screens as ars  # noqa: E402
from perennia.ui import endurance_screens as es  # noqa: E402


class TestModel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = Database(Path(self.tmp) / "t.db")

    def test_defaults_do_not_overlap(self):
        for sport in sl.SPORTS:
            panels = sl.defaults(sport)
            on = [(k, r) for k, r in panels.items() if r]
            for i, (k, r) in enumerate(on):
                self.assertTrue(sl.fits(panels, k, r), (sport, k))
                for k2, r2 in on[i + 1:]:
                    self.assertFalse(sl.overlaps(r, r2), (sport, k, k2))

    def test_save_load_and_clean(self):
        p = sl.defaults("running")
        p["chart"] = (0, 8, 10, 8)
        p["status"] = None
        sl.save(self.db, "running", p)
        self.assertTrue(sl.is_custom(self.db, "running"))
        got = sl.load(self.db, "running")
        self.assertEqual(got["chart"], (0, 8, 10, 8))
        self.assertIsNone(got["status"])
        # tudo de origem: não guarda nada
        sl.save(self.db, "running", sl.defaults("running"))
        self.assertFalse(sl.is_custom(self.db, "running"))
        # valores fora da grelha ficam dentro
        self.db.set("screen_layout_running", {"laps": [30, 30, 99, 2]})
        x, y, w, h = sl.load(self.db, "running")["laps"]
        self.assertLessEqual(x + w, sl.COLS)
        self.assertLessEqual(y + h, sl.ROWS)
        self.assertGreaterEqual(h, sl.min_size("running", "laps")[1])

    def test_to_px_maps_the_grid(self):
        x, y, w, h = sl.to_px((0, 0, 24, 16), (0, 0, 2400, 1600), gap=0)
        self.assertEqual((x, y, w, h), (0, 0, 2400, 1600))
        x, y, w, h = sl.to_px((12, 0, 12, 8), (0, 0, 2400, 1600), gap=0)
        self.assertEqual((x, y, w, h), (1200, 800, 1200, 800))     # canto de cima, à direita


class TestEditor(tg.GuiCase):
    def _open(self, sport="running"):
        self.pick("Definições")
        self.screen().tab_named("Desportos")
        self.screen().set_sport({"cycling": 0, "rowing": 1, "running": 2}[sport])
        self.screen().set_section(1)                    # Disposição do ecrã de sessão
        self.pick("Disposição dos painéis")
        ed = self.screen()
        self.assertIsInstance(ed, ars.ArrangementEditor)
        self.assertEqual(ed.sport, sport)               # só o separador do desporto de onde se veio
        self.assertEqual(ed.tab_labels(), [{"cycling": "Ciclismo", "rowing": "Remo",
                                            "running": "Corrida"}[sport]])
        return ed

    def test_keys_move_resize_remove_and_add(self):
        ed = self._open()
        ed.sel = "laps"
        x0 = ed.panels["laps"][0]
        self.press(key.LEFT)                      # pisaria os quadrados: não mexe
        self.assertEqual(ed.panels["laps"][0], x0)
        self.press(key.DELETE)                    # tira as voltas do ecrã
        self.assertIsNone(ed.panels["laps"])
        self.assertIn("laps", ed.hidden())
        self.assertTrue(ed.dirty)
        ed.sel = "metrics"
        self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)       # mais larga
        self.assertEqual(ed.panels["metrics"][2], 18)
        self.press(key.RIGHT)                                  # e para a direita
        self.assertEqual(ed.panels["metrics"][0], 1)
        self.assertTrue(ed.add("chart"))
        self.assertIsNotNone(ed.panels["chart"])
        self.save()
        got = sl.load(self.app.db, "running")
        self.assertIsNone(got["laps"])
        self.assertIsNotNone(got["chart"])

    def test_mouse_drag_moves_a_panel(self):
        ed = self._open()
        ed.remove("status")
        gx, gy, gw, gh = ed.grid_area()
        px, py, pw, ph = sl.to_px(ed.panels["metrics"], (gx, gy, gw, gh), gap=4)
        self.app._on_mouse_press(int(px + 20), int(py + ph - 20), 1, 0)
        self.assertEqual(ed.drag["what"], "move")
        cell_h = gh / sl.ROWS
        self.app._on_mouse_drag(int(px + 20), int(py + ph - 20 - 4 * cell_h), 0, -4, 1, 0)
        self.app._on_mouse_release(int(px + 20), int(py + ph - 20 - 4 * cell_h), 1, 0)
        self.assertEqual(ed.panels["metrics"][1], 4)          # 4 linhas para baixo

    def test_resize_from_the_corner(self):
        ed = self._open()
        ed.remove("status")
        gx, gy, gw, gh = ed.grid_area()
        px, py, pw, ph = sl.to_px(ed.panels["metrics"], (gx, gy, gw, gh), gap=4)
        self.app._on_mouse_press(int(px + pw - 4), int(py + 4), 1, 0)
        self.assertEqual(ed.drag["what"], "resize")
        cell_h = gh / sl.ROWS
        self.app._on_mouse_drag(int(px + pw - 4), int(py + 4 - 3 * cell_h), 0, -3, 1, 0)
        self.app._on_mouse_release(int(px + pw - 4), int(py + 4 - 3 * cell_h), 1, 0)
        self.assertEqual(ed.panels["metrics"][3], 11)          # 8 + 3

    def test_click_a_chip_adds_the_panel(self):
        ed = self._open()
        self.app._on_draw()
        k, x, y, w, h = ed._chip_rects[0]
        self.app._on_mouse_press(int(x + 5), int(y + 5), 1, 0)
        self.app._on_mouse_release(int(x + 5), int(y + 5), 1, 0)
        self.assertIsNotNone(ed.panels[k])

    def test_cancel_and_reset(self):
        ed = self._open()
        ed.remove("laps")
        self.pick("Cancelar")
        self.assertIsNotNone(ed.panels["laps"])
        self.assertFalse(ed.dirty)
        ed.remove("laps")
        self.pick("Repor a de origem")
        self.assertEqual(ed.panels, sl.defaults("running"))

    def test_layout_editor_links_to_the_arrangement(self):
        self.pick("Definições")
        self.screen().tab_named("Desportos")
        self.screen().set_section(1)
        self.pick("Escolher as métricas do ecrã")
        self.pick("Disposição do ecrã")
        self.assertIsInstance(self.screen(), ars.ArrangementEditor)
        self.assertEqual(self.screen().sport, "cycling")


class TestSessionsFollowTheLayout(tg.GuiCase):
    def test_running_with_laps_left_and_a_live_chart(self):
        p = sl.defaults("running")
        p["metrics"] = (7, 0, 17, 8)
        p["laps"] = (0, 0, 7, 16)
        p["status"] = (7, 8, 17, 4)
        p["chart"] = (7, 12, 17, 4)
        sl.save(self.app.db, "running", p)
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        ses = self.screen()
        self.assertIsInstance(ses, es.EnduranceSession)
        lx = ses.laps_panel.geometry[0]
        self.assertLess(lx, ses.cells[0][0].x)                 # as voltas à esquerda
        self.press(key.SPACE)
        for _ in range(12):
            self.app._tick(0.5)
        self.app._on_draw()
        self.assertTrue(ses.live_chart is not None)
        self.assertGreater(len(ses._series["a"]), 3)

    def test_hidden_panel_goes_off_screen(self):
        p = sl.defaults("running")
        p["laps"] = None
        sl.save(self.app.db, "running", p)
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        self.assertLess(self.screen().laps_panel.geometry[0], 0)

    def test_rowing_board_and_laps(self):
        self.app.set_rower(rio.SimulatedRower())
        p = sl.defaults("rowing")
        p["zones"] = None
        sl.save(self.app.db, "rowing", dict(p, metrics=(0, 0, 17, 8), status=(0, 8, 17, 8)))
        self.press(key.ESCAPE)
        self.pick("Remo")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        ses = self.screen()
        x, top, width, bottom = ses.laps_panel.geometry
        self.assertGreater(x, ses.cells[3][0].x + ses.cells[3][0].width)
        # sem jogo, as voltas ocupam também o lugar da classificação
        self.assertLess(bottom, 200)

    def test_cycling_hud_uses_the_rectangles(self):
        p = sl.defaults("cycling")
        p["laps"] = (0, 9, 6, 4)          # as voltas à esquerda…
        p["plan"] = (18, 9, 6, 4)         # …e o plano à direita
        p["strip"] = None
        sl.save(self.app.db, "cycling", p)
        self.open_routes()
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        hud = ride.hud
        self.assertIsNotNone(hud.arrangement)
        w = self.app.window.width
        self.assertLess(hud._laps_geometry[0], w / 2)
        self.assertGreater(hud._plan_bg.x, w / 2)
        self.assertLess(hud._strip_geometry[0], 0)              # fora do ecrã
        ride.world.build_all()
        ride.preparing = False
        for _ in range(8):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.app._on_draw()


if __name__ == "__main__":
    unittest.main()
