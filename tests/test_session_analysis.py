"""A análise de uma sessão do histórico em separadores: Geral (com o tipo),
Feedback (o próprio ecrã), Análise do treino (cada bloco cumprido ou não) e
Infográficos (com os blocos por baixo)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import feedback as fbm  # noqa: E402
from velo.core import session_review as rv  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import session_analysis as sa  # noqa: E402


class Base(tg.GuiCase):
    def _workout(self):
        steps = [{"kind": "steady", "duration_s": 60, "target_type": "pct_ftp",
                  "target_lo": 84.0},
                 {"kind": "steady", "duration_s": 60, "target_type": "pct_ftp",
                  "target_lo": 120.0}]
        return self.app.db.insert_workout("Dois blocos", steps, "builder", None, 5)

    def _ride(self, wid=None, seconds=150):
        from velo.ui.session_setup import SessionSetup
        setup = SessionSetup(self.app, "cycling", kind="workout" if wid else "free",
                             workout_id=wid, route_id=None if wid else self.route_id)
        self.app.push(setup)
        if wid:
            setup.erg = False                     # a potência é a do ciclista simulado
        setup._start()
        ride = self.screen()
        ride.preparing = False
        for _ in range(int(seconds / 0.5)):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.press(key.F10, key.ENTER)
        return ride.engine.ride_id


class TestTabsAndGeneral(Base):
    def test_four_tabs_and_session_kind(self):
        rid = self._ride(self._workout())
        an = sa.SessionAnalysis(self.app, "ride", rid)
        self.app.push(an)
        self.assertEqual(an.tab_labels(), ["Geral", "Feedback", "Análise do treino",
                                           "Infográficos"])
        kind = next(i for i in an.list.items if i.label == "Tipo de sessão")
        self.assertTrue(kind.value.startswith("Treino: Dois blocos"))
        self.assertIn("ERG", kind.value)              # o tipo do treino
        self.app._on_draw()

    def test_free_session_kind(self):
        rid = self._ride()
        an = sa.SessionAnalysis(self.app, "ride", rid)
        self.app.push(an)
        kind = next(i for i in an.list.items if i.label == "Tipo de sessão")
        self.assertTrue(kind.value.startswith("Sessão livre"))
        an.tab_named("Análise do treino")
        self.app._on_draw()
        sess = fbm.load_session(self.app.db, "ride", rid)
        self.assertEqual(rv.block_compliance(self.app.db, sess), [])   # sem blocos
        texts = [lab.text for lab in pyglet_stub.created["labels"] if lab.text]
        self.assertTrue(any("sem blocos de treino" in x for x in texts))

    def test_history_opens_the_analysis(self):
        rid = self._ride(self._workout())
        self.press(key.ESCAPE)                         # do resumo para o menu
        self.pick("Histórico")
        self.pick("Dois blocos" if any("Dois blocos" in i.label
                                       for i in self.screen().list.items) else "20")
        self.assertIsInstance(self.screen(), sa.SessionAnalysis)
        _ = rid


class TestBlocks(Base):
    def test_each_block_has_a_verdict(self):
        rid = self._ride(self._workout())
        sess = fbm.load_session(self.app.db, "ride", rid)
        rows = rv.block_compliance(self.app.db, sess)
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertIn(r["verdict"], ("ok", "partial", "miss", "short", "skipped"))
            self.assertTrue(r["avg_text"].endswith(" W"))
        # o 1.º bloco (84 % da FTP = 210 W, a potência do ciclista) foi cumprido;
        # o 2.º (120 %) não
        self.assertEqual(rows[0]["verdict"], "ok")
        self.assertIn(rows[1]["verdict"], ("miss", "partial"))
        an = sa.SessionAnalysis(self.app, "ride", rid)
        self.app.push(an)
        an.tab_named("Análise do treino")
        self.app._on_draw()
        cells = [m.text for row in an.table.cells for m, _n in row if m.text]
        self.assertTrue(any("cumprido" in c for c in cells), cells)
        self.assertIn("1 de 2 blocos cumpridos", an.chrome.subtitle.text)

    def test_windows_follow_the_block_laps(self):
        rid = self._ride(self._workout())
        sess = fbm.load_session(self.app.db, "ride", rid)
        brief = fbm.prescribed(self.app.db, sess)
        wins = rv.block_windows(self.app.db, sess, brief)
        self.assertEqual(len(wins), 2)
        self.assertAlmostEqual(wins[0][1], 60, delta=2)

    def test_chart_has_the_blocks_and_the_target(self):
        rid = self._ride(self._workout())
        an = sa.SessionAnalysis(self.app, "ride", rid)
        self.app.push(an)
        an.tab_named("Infográficos")
        self.app._on_draw()
        self.assertEqual(len(an.bands), 2)                  # um retângulo por bloco
        self.assertIsNotNone(an.target)
        labels = [i.label for i in an.list.items]
        self.assertTrue(any("Blocos e alvo" in x for x in labels))
        self.select("Blocos e alvo")
        self.press(key.RIGHT)                               # desliga os blocos
        self.assertEqual(len(an.bands), 0)
        self.press(key.BRACKETRIGHT)                        # Relatório (ciclismo)
        self.app._on_draw()
        self.assertEqual(an.sub, 1)


class TestFeedbackTab(Base):
    def test_feedback_lives_in_the_tab(self):
        rid = self._ride(self._workout())
        an = sa.SessionAnalysis(self.app, "ride", rid)
        self.app.push(an)
        an.tab_named("Feedback")
        self.app._on_draw()
        self.app._on_text("7")                              # RPE 7 (a 1.ª linha)
        self.assertEqual(an.fb.v["rpe"], 7)
        self.assertTrue(an.has_unsaved())
        self.press(key.TAB)                                 # Tab muda de separador
        self.assertEqual(an.view, "analysis")
        self.press(key.ESCAPE)                              # pergunta: há alterações
        pop = self.screen()
        self.assertIsInstance(pop, app_mod.ConfirmScreen)
        self.pick("Sair e guardar")
        self.assertEqual(fbm.get(self.app.db, "ride", rid)["rpe"], 7)
        self.assertNotIn(an, self.app.stack)


class TestOtherSports(tg.GuiCase):
    def test_running_and_gym_open_with_tabs(self):
        from velo.ui import endurance_screens as es
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        ses = self.screen()
        self.assertIsInstance(ses, es.EnduranceSession)
        self.press(key.SPACE)
        for _ in range(60):
            self.app._tick(0.5)
        sid = ses.engine.session_id
        self.press(key.ESCAPE)
        self.pick("Sim, terminar")
        an = sa.open_session(self.app, "running", sid)
        self.app.push(an)
        kind = next(i for i in an.list.items if i.label == "Tipo de sessão")
        self.assertEqual(kind.value, "Sessão livre")
        for name in ("Feedback", "Análise do treino", "Infográficos"):
            an.tab_named(name)
            self.app._on_draw()


if __name__ == "__main__":
    import unittest
    unittest.main()
