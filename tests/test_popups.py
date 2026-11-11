"""Janelas onde se justificam: voltar atrás com alterações pergunta, apagar
pergunta, e guardar um treino avisa."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import feedback_screens as fs  # noqa: E402
from perennia.ui import health_screens as hs  # noqa: E402


class TestBackWithChangesAsks(tg.GuiCase):
    def _is_unsaved_question(self):
        scr = self.screen()
        self.assertIsInstance(scr, app_mod.ConfirmScreen)
        self.assertEqual([i.label for i in scr.list.items],
                         ["Sair sem guardar", "Cancelar", "Sair e guardar"])

    def test_goal_popup(self):
        from perennia.ui.goal_popup import GoalPopup
        self.pick("Lista de treinos")
        self.pick("Tempo 3×15")
        self.pick("Editar")
        b = self.screen()
        self.pick("Objetivo do treino")
        pop = self.screen()
        self.assertIsInstance(pop, GoalPopup)
        self.press(key.ESCAPE)                       # sem alterações: sai logo
        self.assertIs(self.screen(), b)
        self.pick("Objetivo do treino")
        pop = self.screen()
        self.type("x")
        self.press(key.ESCAPE)
        self._is_unsaved_question()
        self.pick("Cancelar")
        self.assertIs(self.screen(), pop)

    def test_feedback_form(self):
        # uma sessão de ciclismo curta para ter onde dar feedback
        self.open_routes()
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.preparing = False
        for _ in range(40):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.press(key.F10, key.ENTER, key.ENTER)
        summ = self.screen()
        rid = summ.result["ride_id"]
        fb = fs.FeedbackScreen(self.app, "ride", rid)
        self.app.push(fb)
        fb.set_value("rpe", 7)
        self.press(key.ESCAPE)
        self._is_unsaved_question()
        self.pick("Sair e guardar")
        self.assertNotIn(fb, self.app.stack)

    def test_test_result_entry(self):
        self.press(key.ESCAPE)
        self.pick("Longevidade")
        self.pick("Testes de longevidade")
        self.pick("Flexões em 1 minuto")
        self.pick("Registar um resultado")
        run = self.screen()
        self.assertIsInstance(run, hs.ResultPopup)        # o registo é uma janela
        self.select("Resultado")
        self.app._on_text("30")
        self.press(key.ESCAPE)
        self._is_unsaved_question()
        self.pick("Sair sem guardar")
        self.assertNotIn(run, self.app.stack)


class TestDeleteAsks(tg.GuiCase):
    def test_route_delete_asks_and_cancel_keeps_it(self):
        self.open_routes()
        self.select("Serra de Teste")
        self.press(key.DELETE)
        pop = self.screen()
        self.assertIsInstance(pop, app_mod.ConfirmScreen)
        self.assertIn("Apagar a rota", pop.title_text)
        self.press(key.ESCAPE)                       # Esc = Cancelar
        self.assertEqual(len(self.app.db.routes()), 1)

    def test_workout_delete_asks(self):
        self.pick("Lista de treinos")
        n = len(self.app.db.workouts())
        self.select("Tempo 3×15")
        self.press(key.DELETE)
        self.assertIn("Apagar o treino", self.screen().title_text)
        self.pick("Apagar")
        self.assertEqual(len(self.app.db.workouts()), n - 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
