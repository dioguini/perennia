"""Ronda 38: as notas do treinador (pré-treino) em todos os construtores, à parte do objetivo,
como no TrainingPeaks. Guardam-se com o treino, vão com a cópia da sessão e aparecem na ficha."""
from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import objectives as ob  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")

NOTES = "Come 2 h antes.\nAquece bem: o 1.º bloco custa.\nSe as pernas pesarem, corta 1 série."


class TestCore(tg.GuiCase):
    def test_notes_apart_from_the_goal(self):
        db = self.app.db
        ob.save(db, "cycling", "w1", "Melhorar o limiar", [])
        ob.save_notes(db, "cycling", "w1", NOTES)
        self.assertEqual(ob.notes(db, "cycling", "w1"), NOTES)
        self.assertEqual(ob.stored(db, "cycling", "w1")["goal"], "Melhorar o limiar")
        ob.save(db, "cycling", "w1", "Outro objetivo", [])          # não apaga as notas
        self.assertEqual(ob.notes(db, "cycling", "w1"), NOTES)
        ob.save_notes(db, "cycling", "w1", "  ")
        self.assertEqual(ob.notes(db, "cycling", "w1"), "")

    def test_session_copy_keeps_the_notes(self):
        from perennia.core import session_workouts as sw
        db = self.app.db
        wid = db.conn.execute("SELECT id FROM workouts LIMIT 1").fetchone()[0]
        ob.save_notes(db, "cycling", wid, NOTES)
        copy = sw.copy_workout(db, "cycling", wid) if hasattr(sw, "copy_workout") else None
        if copy is None:
            sw._copy_extras(db, "cycling", wid, "copia")
            copy = "copia"
        self.assertEqual(ob.notes(db, "cycling", copy), NOTES)


class TestBuilders(tg.GuiCase):
    def test_block_builder_has_coach_notes_and_saves_them(self):
        from perennia.ui.builder_screens import BlockBuilder
        from perennia.ui.goal_popup import GoalPopup
        wid = self.app.db.conn.execute("SELECT id FROM workouts LIMIT 1").fetchone()[0]
        b = BlockBuilder(self.app, "cycling", wid)
        self.app.push(b)
        labels = [i.label for i in b.list.items if i.head]
        self.assertEqual(labels[:3], ["Nome do treino", "Objetivo do treino",
                                      "Notas do treinador"])
        self.pick("Notas do treinador")
        pop = self.screen()
        self.assertIsInstance(pop, GoalPopup)
        self.assertTrue(pop.multiline)
        pop.on_text(NOTES)
        pop.save()
        self.assertEqual(b.wnotes, NOTES)
        self.assertTrue(b.dirty)
        b._save()
        self.assertEqual(ob.notes(self.app.db, "cycling", b.wid), NOTES)

    def test_brief_shows_the_notes_and_opens_them_whole(self):
        from perennia.ui import brief as br
        from perennia.ui.imported_screens import TextViewPopup
        wid = self.app.db.conn.execute("SELECT id FROM workouts LIMIT 1").fetchone()[0]
        ob.save_notes(self.app.db, "cycling", wid, NOTES)
        scr = br.CyclingBrief(self.app, wid)
        self.app.push(scr)
        self.assertEqual(scr.panel.notes_title.text, "Notas do treinador")
        self.assertIn("Come 2 h antes.", scr.panel.notes.text)
        self.pick("Notas do treinador")
        self.assertIsInstance(self.screen(), TextViewPopup)
        lines = [i.label for i in self.screen().list.items]
        self.assertIn("Aquece bem: o 1.º bloco custa.", lines)

    def test_brief_without_notes_shows_nothing(self):
        from perennia.ui import brief as br
        wid = self.app.db.conn.execute("SELECT id FROM workouts LIMIT 1").fetchone()[0]
        scr = br.CyclingBrief(self.app, wid)
        self.app.push(scr)
        self.assertEqual(scr.panel.notes_title.text, "")
        self.assertNotIn("Notas do treinador", [i.label for i in scr.list.items])

    def test_gym_editor(self):
        from perennia.core import strength as st
        from perennia.ui.sport_screens import StrengthWorkoutEditor
        wid = st.workouts(self.app.db)[0]["id"]
        ed = StrengthWorkoutEditor(self.app, wid)
        self.app.push(ed)
        self.assertIn("Notas do treinador (pré-treino)", [i.label for i in ed.list.items])
        ed.wnotes = NOTES
        ed._save(popup=False)
        self.assertEqual(ob.notes(self.app.db, "gym", wid), NOTES)
        self.assertEqual(ob.workout_brief(self.app.db, "gym", wid).notes, NOTES)

    def test_conditioning_builder(self):
        from perennia.ui.conditioning_builder import ConditioningBuilder
        cb = ConditioningBuilder(self.app, None, items=[])
        self.app.push(cb)
        self.assertIn("Notas do treinador (pré-treino)", [i.label for i in cb.list.items])
        cb.wnotes = NOTES
        self.assertTrue(cb.has_unsaved() or cb.draft is False)


if __name__ == "__main__":
    unittest.main()
