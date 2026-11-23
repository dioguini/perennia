"""Ronda 28: o guia da passadeira manual (uma passadeira sem ligação, como a NordicTrack T 7.0):
antes de cada bloco a sessão diz a velocidade e a inclinação que vêm aí e quantos toques dar."""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia.core import endurance as en  # noqa: E402
from perennia.core import treadmill_guide as tg  # noqa: E402

gui = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import endurance_screens as es  # noqa: E402


class TestCore(unittest.TestCase):
    def test_presses(self):
        self.assertEqual(tg.presses(10.0, 12.5, 0.1), 25)
        self.assertEqual(tg.presses(12.5, 10.0, 0.1), -25)
        self.assertEqual(tg.presses(1.0, 2.0, 0.5), 2)
        self.assertEqual(tg.presses(None, 2.0, 0.5), 0)
        self.assertEqual(tg.press_text(-3, "inclinação"), "▼ inclinação ×3")
        self.assertEqual(tg.press_text(0, "x"), "")

    def guide(self) -> tg.Guide:
        tgts = [tg.Target(8.0, 0.0), tg.Target(12.5, 2.0), tg.Target(12.5, 2.0),
                tg.Target(7.0, 0.0)]
        return tg.Guide(tgts, 0.1, 0.5, lead_s=10)

    def test_phases(self):
        g = self.guide()
        st = g.state(0, 300, 0, started=False)
        self.assertEqual(st["kind"], "start")
        self.assertEqual(st["line"], "8,0 km/h · 0,0 %")
        self.assertEqual(g.state(0, 100, 60)["kind"], "steady")
        soon = g.state(0, 8.2, 290)
        self.assertEqual(soon["kind"], "soon")
        self.assertEqual(soon["title"], "DAQUI A 8 s")
        self.assertEqual(soon["presses_text"], "▲ velocidade ×45 · ▲ inclinação ×4")
        self.assertTrue(soon["beep"])
        self.assertFalse(g.state(0, 5, 295)["beep"])              # o bip só uma vez por bloco
        self.assertIn("manter o botão", soon["hint"])             # 45 toques: manter carregado
        now = g.state(1, 200, 2)
        self.assertEqual(now["kind"], "now")
        self.assertEqual(now["speed_presses"], 45)
        self.assertEqual(g.state(1, 200, 30)["kind"], "steady")
        # entre dois blocos iguais não há nada a fazer: nem aviso nem «agora»
        self.assertEqual(g.state(1, 5, 200)["kind"], "steady")
        self.assertEqual(g.state(2, 200, 2)["kind"], "steady")
        down = g.state(2, 5, 200)
        self.assertEqual(down["presses_text"], "▼ velocidade ×55 · ▼ inclinação ×4")
        self.assertIn("manter o botão", down["hint"])
        self.assertEqual(g.state(4, None, 0)["kind"], "done")


class TestInTheSession(gui.GuiCase):
    def setUp(self):
        super().setUp()
        self.app.set_treadmill(None)                  # uma passadeira sem ligação
        self.wid = next(w["id"] for w in en.workouts(self.app.db, "running")
                        if w["name"].startswith("Intervalos"))

    def session(self) -> es.EnduranceSession:
        scr = es.EnduranceSession(self.app, "running", workout_id=self.wid)
        self.app.push(scr)
        return scr

    def test_targets_from_the_pace_rounded_to_the_step(self):
        scr = self.session()
        g = scr.guide
        self.assertIsNotNone(g)
        speeds = [t.speed for t in g.targets]
        self.assertTrue(all(s and abs(s * 10 - round(s * 10)) < 1e-6 for s in speeds))
        self.assertGreater(speeds[1], speeds[0])          # o esforço é mais rápido que o aquecimento

    def test_card_warns_before_the_change_with_one_beep(self):
        scr = self.session()
        scr.update(0.1)                                  # antes de começar: o 1.º bloco
        self.assertTrue(scr.guide_card.visible)
        self.assertEqual(scr.guide_card.kind, "start")
        scr.engine.start()
        scr.update(0.01)                                 # a sessão trata o «começou»
        first = scr.guide.targets[0].speed
        self.assertAlmostEqual(scr.engine.speed_kmh, first)   # a distância conta por esta
        before = self.app.beeper.count
        kinds = []
        while scr.engine.t < 905:
            scr.update(0.5)
            kinds.append(scr.guide_card.kind)
        self.assertIn("soon", kinds)
        self.assertIn("now", kinds)
        self.assertGreaterEqual(self.app.beeper.count - before, 1)     # o bip do aviso
        texts = scr.guide_card.texts()
        self.assertTrue(texts[2].startswith("▲ velocidade ×"))
        self.assertAlmostEqual(scr.engine.speed_kmh, scr.guide.targets[1].speed)

    def test_no_guide_with_a_treadmill_the_app_controls(self):
        from perennia.io.sim import SimulatedTreadmill
        self.app.set_treadmill(SimulatedTreadmill(20.0, 15.0))
        scr = self.session()
        self.assertIsNone(scr.guide)
        scr.update(0.5)
        self.assertFalse(scr.guide_card.visible)

    def test_no_guide_in_a_free_run(self):
        scr = es.EnduranceSession(self.app, "running")
        self.app.push(scr)
        self.assertIsNone(scr.guide)

    def test_settings_rows(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Desportos")
        scr.set_sport(scr.SPORTS.index("running"))
        scr.set_section(2)                                   # Sessões Não ERG
        self.select("Passo da velocidade")
        self.press(key.RIGHT)
        self.select("Aviso antes de cada mudança")
        self.press(key.RIGHT, key.RIGHT)
        self.save()
        self.assertEqual(self.app.db.get("treadmill_speed_step"), 0.2)
        self.assertEqual(self.app.db.get("treadmill_guide_lead_s"), 12)
        cfg = tg.settings(self.app.db)
        self.assertEqual((cfg["speed_step"], cfg["lead_s"]), (0.2, 12))


if __name__ == "__main__":
    unittest.main()
