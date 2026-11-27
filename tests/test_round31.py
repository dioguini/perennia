"""Ronda 31: o impacto do treino (IF, sistemas do desporto, longevidade) também na ficha do
treino — o ecrã dos detalhes que se abre ao escolher um treino da lista — e não só no
construtor. O painel é o mesmo (perennia.ui.impact_panel)."""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import endurance as en  # noqa: E402
from perennia.core import rowing as rw  # noqa: E402
from perennia.core import workout_impact as wi  # noqa: E402
from perennia.core.blocks import Block, load_blocks, save_blocks  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import brief as br  # noqa: E402
from perennia.ui import builder_screens as bs  # noqa: E402
from perennia.ui.impact_panel import ImpactPanel, texts_for  # noqa: E402


class TestBriefImpact(tg.GuiCase):
    def cycling_wid(self, prefix="VO2máx 5") -> str:
        return next(w["id"] for w in self.app.db.workouts() if w["name"].startswith(prefix))

    def open(self, scr):
        self.app.push(scr)
        return scr

    def test_cycling_brief_shows_the_same_impact_as_the_builder(self):
        wid = self.cycling_wid()
        scr = self.open(br.CyclingBrief(self.app, wid))
        panel = scr.panel.impact
        self.assertTrue(panel.visible)
        tx = panel.texts()
        self.assertEqual(tx["focus"], "vo2max")
        self.assertTrue(tx["if"].startswith("IF 0.8") or tx["if"].startswith("IF 0.9"))
        self.assertIn("Longevidade", tx["longevity"])
        self.assertEqual(panel.if_label.text, tx["if"])                   # desenhado
        self.assertEqual(panel.title.text, "Impacto do treino")
        # o construtor do mesmo treino diz o mesmo
        b = bs.BlockBuilder(self.app, "cycling", wid)
        self.assertEqual(b.impact_texts()["if"], tx["if"])
        self.assertEqual(b.impact_texts()["rows"], tx["rows"])
        # e a TSS da ficha é a do painel
        imp = panel.impact
        self.assertIn(f"TSS ≈ {imp.tss:.0f}", scr.panel.meta.text)
        scr.draw()

    def test_the_text_moves_left_and_the_chart_goes_below_the_panel(self):
        scr = self.open(br.CyclingBrief(self.app, self.cycling_wid()))
        x0, x1, y0, y1 = scr.panel.impact.box
        self.assertGreater(x0, scr.panel.title.x + 300)
        self.assertLessEqual(scr.panel.chart_bg.y + scr.panel.chart_bg.height, y0)

    def test_rowing_running_and_swimming_briefs(self):
        rw.seed(self.app.db)
        en.seed(self.app.db)
        from perennia.ui import endurance_screens as es
        from perennia.ui import rowing_screens as rs
        rscr = self.open(rs.RowWorkoutPreview(self.app, rw.workouts(self.app.db)[0]["id"]))
        self.assertTrue(rscr.panel.impact.visible)
        self.assertEqual(rscr.panel.impact.texts()["focus"], "endurance")
        run_wid = next(w["id"] for w in en.workouts(self.app.db, "running")
                       if w["name"].startswith("Intervalos"))
        escr = self.open(es.EndurancePreview(self.app, "running", run_wid))
        self.assertTrue(escr.panel.impact.visible)
        self.assertEqual(escr.panel.impact.texts()["focus"], "threshold")
        swims = en.workouts(self.app.db, "swimming")
        if swims:
            sscr = self.open(es.EndurancePreview(self.app, "swimming", swims[0]["id"]))
            self.assertIsNotNone(sscr.panel.impact.impact)

    def test_gym_brief_has_no_impact_panel(self):
        from perennia.core import gym
        from perennia.ui.brief import GymBrief
        gym.seed(self.app.db)
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = self.open(GymBrief(self.app, wid))
        self.assertFalse(scr.panel.impact.visible)
        self.assertEqual(scr.panel.impact.if_label.text, "")

    def test_narrow_window_hides_the_panel(self):
        self.app.window.width = 900
        scr = self.open(br.CyclingBrief(self.app, self.cycling_wid()))
        scr.on_resize(900, self.app.window.height)
        self.assertFalse(scr.panel.impact.visible)
        self.assertEqual(scr.panel.impact.if_label.text, "")

    def test_editing_the_workout_updates_the_brief(self):
        wid = self.cycling_wid("Resistência Z2 60")
        scr = self.open(br.CyclingBrief(self.app, wid))
        before = scr.panel.impact.texts()
        self.assertEqual(before["focus"], "endurance")
        name, desc, mode, blocks = load_blocks(self.app.db, "cycling", wid)
        blocks.append(Block("active", "time", 1200, 100))       # 20 min ao limiar
        save_blocks(self.app.db, "cycling", wid, name, desc, mode, blocks)
        scr.enter()                                             # de volta à ficha
        after = scr.panel.impact.texts()
        self.assertGreater(float(after["if"].split()[1]), float(before["if"].split()[1]))
        self.assertNotEqual(after["rows"]["threshold"], before["rows"]["threshold"])


class TestPanelWidget(tg.GuiCase):
    def test_hidden_without_impact_or_room(self):
        p = ImpactPanel()
        p.layout(0, 300, 0, 200)
        self.assertFalse(p.visible)                    # sem impacto
        imp = wi.planned(self.app.db, "cycling", [Block("active", "time", 1800, 95)])
        p.set(imp, {})
        self.assertTrue(p.visible)
        self.assertEqual(p.if_label.text, texts_for(imp, {})["if"])
        p.layout(0, 0, 0, 0)                           # sem espaço
        self.assertFalse(p.visible)
        self.assertEqual(p.if_label.text, "")
        self.assertEqual(texts_for(None, None), {})


if __name__ == "__main__":
    unittest.main()
