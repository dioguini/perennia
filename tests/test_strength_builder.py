"""Construtor de treinos de força por blocos (à maneira do TrainingPeaks),
a sessão que segue a estrutura (supersets, circuitos, alvo por série), a
análise pós-treino e as estatísticas por exercício."""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import gym  # noqa: E402
from velo.core import strength as st  # noqa: E402
from velo.core import strength_analysis as sa  # noqa: E402
from velo.core import strength_builder as sb  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import exercise_stats_screens as ess  # noqa: E402
from velo.ui import strength_analysis_screens as sas  # noqa: E402
from velo.ui import strength_builder_screens as sbs  # noqa: E402


class _Db(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "perennia.db")
        st.seed(self.db)
        gym.ensure(self.db)
        self.exs = {e["name"]: e for e in gym.exercises(self.db, "strength")}

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ex(self, part: str) -> dict:
        return next(e for k, e in self.exs.items() if part.lower() in k.lower())

    def plan(self) -> dict:
        s = sb.empty()
        a = sb.new_exercise(self.ex("agachamento com barra"))
        sb.add_block(s, "single", [a])
        for i, (r, ld) in enumerate([(5, 100), (5, 105), (3, 110)]):
            sb.set_value(s, 0, 0, i, "reps", r)
            sb.set_value(s, 0, 0, i, "load", ld)
            sb.set_value(s, 0, 0, i, "rest", 120)
        sb.add_block(s, "single", [sb.new_exercise(self.ex("supino com barra"))])
        sb.add_block(s, "single", [sb.new_exercise(self.ex("remada"))])
        sb.combine(s, 2, 1)                              # remada em cima do supino
        for i in range(3):
            sb.set_value(s, 1, 0, i, "reps", 8)
            sb.set_value(s, 1, 0, i, "load", 60)
            sb.set_value(s, 1, 1, i, "reps", 10)
            sb.set_value(s, 1, 1, i, "load", 24)
        return s


class TestModel(_Db):
    def test_blocks_combine_unlink_move_convert(self):
        s = self.plan()
        self.assertEqual([b["kind"] for b in s["blocks"]], ["single", "superset"])
        self.assertEqual(sb.label(1, 1, s["blocks"][1]), "B2")
        self.assertEqual(sb.label(0, 0, s["blocks"][0]), "A")
        nb = sb.unlink(s, 1, 1)
        self.assertEqual(nb, 2)
        self.assertEqual(s["blocks"][1]["kind"], "single")
        sb.move_block(s, 2, 0)
        self.assertIn("Remada", s["blocks"][0]["exercises"][0]["name"])
        sb.convert(s, 1, "circuit")
        self.assertEqual(s["blocks"][1]["rounds"], 3)

    def test_parameters_add_replace_remove(self):
        s = self.plan()
        sb.add_param(s, 0, 0, "rpe")
        self.assertIn("rpe", s["blocks"][0]["exercises"][0]["params"])
        sb.set_value(s, 0, 0, 0, "rpe", 8)
        sb.replace_param(s, 0, 0, "rpe", "rir")          # RPE 8 ≈ RIR 2
        self.assertEqual(s["blocks"][0]["exercises"][0]["sets"][0]["rir"], 2)
        sb.add_param(s, 0, 0, "rpe")                     # RPE e RIR não ficam os dois
        self.assertNotIn("rir", s["blocks"][0]["exercises"][0]["params"])
        sb.remove_param(s, 0, 0, "rest")
        self.assertNotIn("rest", s["blocks"][0]["exercises"][0]["params"])
        sb.set_value(s, 0, 0, 0, "reps", 999)
        self.assertEqual(s["blocks"][0]["exercises"][0]["sets"][0]["reps"], 500)

    def test_prescription_and_summary(self):
        s = self.plan()
        lines = sb.summary_lines(s)
        self.assertEqual(lines[0][:2], ("A", "Exercício único"))
        self.assertEqual(lines[1][2], "5/5/3 reps @ 100/105/110 kg · 120 s")
        self.assertIn("3 × 8 @ 60 kg", lines[3][2])

    def test_sequence_superset_alternates_and_circuit_repeats(self):
        s = self.plan()
        seq = sb.sequence(s)
        self.assertEqual(seq[:3], [(0, 0), (0, 1), (0, 2)])
        self.assertEqual(seq[3:7], [(1, 0), (2, 0), (1, 1), (2, 1)])
        sb.convert(s, 1, "circuit")
        s["blocks"][1]["rounds"] = 2
        seq = sb.sequence(s)
        self.assertEqual(len(seq), 3 + 2 * (3 + 3))
        self.assertEqual(seq[3:10], [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2), (1, 3)])
        # descanso: só no fim da volta do superset
        sb.convert(s, 1, "superset")
        self.assertEqual(sb.set_rest(s, 1, 0), 0)
        self.assertEqual(sb.set_rest(s, 2, 0), 90)
        self.assertEqual(sb.set_rest(s, 0, 0), 120)

    def test_save_load_and_simple_editor_drops_the_structure(self):
        s = self.plan()
        wid = sb.save(self.db, None, "Blocos", s)
        self.assertIsNotNone(sb.stored(self.db, wid))
        items = st.workout_items(self.db, wid)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].sets, 3)
        st.save_workout(self.db, wid, "Blocos", None, [it.as_dict() for it in items])
        self.assertIsNone(sb.stored(self.db, wid))
        again = sb.load(self.db, wid)                   # volta como lista simples
        self.assertEqual(len(again["blocks"]), 3)

    def test_percent_of_1rm_uses_history(self):
        s = sb.empty()
        e = sb.new_exercise(self.ex("agachamento com barra"))
        e["params"] = ["reps", "pct1rm"]
        e["sets"] = [{"reps": 5, "pct1rm": 80}]
        sb.add_block(s, "single", [e])
        tgt = sb.set_targets(s, {e["exercise_id"]: 125.0})
        self.assertEqual(tgt[0][0]["load_kg"], 100.0)


class TestSessionFollowsBlocks(_Db):
    def test_superset_order_and_per_set_targets(self):
        wid = sb.save(self.db, None, "Blocos", self.plan())
        now = [0.0]
        ses = st.StrengthSession(self.db, Athlete(), wid, clock=lambda: now[0])
        done = []
        while not ses.all_done and len(done) < 20:
            ses.start_set()
            done.append((ses.item_idx, ses.entry["reps"], ses.entry["load_kg"]))
            ses.update(20)
            ses.end_set()
            ses.update(300)
        self.assertEqual(done[:3], [(0, 5, 100), (0, 5, 105), (0, 3, 110)])
        self.assertEqual([d[0] for d in done[3:]], [1, 2, 1, 2, 1, 2])
        self.assertEqual(ses.labels, ["A", "B1", "B2"])
        planned = [r["planned_load_kg"] for r in self.db.conn.execute(
            "SELECT planned_load_kg FROM strength_sets WHERE session_id=? ORDER BY id",
            (ses.session_id,))]
        self.assertEqual(planned[:3], [100, 105, 110])

    def test_analysis_and_exercise_history(self):
        wid = sb.save(self.db, None, "Blocos", self.plan())
        for load_bump in (0, 5):
            now = [0.0]
            ses = st.StrengthSession(self.db, Athlete(), wid, clock=lambda: now[0])
            for _ in range(4):                          # só o agachamento e 1 do superset
                ses.start_set()
                ses.set_field("load_kg", (ses.entry["load_kg"] or 0) + load_bump)
                ses.update(30)
                ses.end_set()
                ses.update(200)
            res = ses.finish()
        an = sa.session(self.db, res["session_id"])
        self.assertEqual(an["done_sets"], 4)
        self.assertEqual(an["planned_sets"], 9)
        squat = an["exercises"][0]
        self.assertEqual(squat["label"], "A")
        self.assertEqual(squat["done_sets"], 3)
        self.assertGreater(squat["compliance"], 1.0)        # carga acima do prescrito
        self.assertIsNotNone(squat["prev_e1rm"])
        self.assertGreater(squat["best_e1rm"], squat["prev_e1rm"])
        self.assertEqual(squat["sets"][0]["plan_load"], 100)
        self.assertEqual(squat["sets"][0]["load"], 105)
        self.assertEqual(sa.compliance_tone(an["exercises"][2]["compliance"]), "bad")
        hist = sa.history(self.db, squat["exercise_id"])
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[1]["max_load"], 115)
        self.assertGreater(hist[1]["time_s"], 0)
        self.assertEqual(hist[1]["work_s"], 90)
        self.assertGreater(sa.trend([v for _, v in sa.series(hist, "max_load")]), 0)


class TestBuilderGui(tg.GuiCase):
    def go(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Força")
        self.pick("construtor por blocos")
        b = self.screen()
        self.assertIsInstance(b, sbs.StrengthBuilder)
        return b

    def add_block(self, kind_label: str, exercise: str):
        b = self.screen()
        b.set_focus(("addblock",))
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), sbs.MenuPopup)
        self.pick(kind_label)
        self.pick(exercise)
        self.assertIs(self.screen(), b)

    def test_build_type_combine_save_and_start(self):
        b = self.go()
        b.name = "Pernas e peito"
        self.add_block("Exercício único", "Agachamento com barra")
        self.assertEqual(b.focus, ("cell", 0, 0, 0, 0))
        self.app._on_text("5")
        self.press(key.RIGHT)
        self.app._on_text("100")
        self.press(key.ENTER)                           # desce para a série 2 da carga
        self.assertEqual(b.focus, ("cell", 0, 0, 1, 1))
        self.app._on_text("1")
        self.app._on_text("0")
        self.app._on_text("5")
        self.press(key.DOWN)
        e = b.struct["blocks"][0]["exercises"][0]
        self.assertEqual(e["sets"][0]["reps"], 5)
        self.assertEqual(e["sets"][0]["load"], 100)
        self.assertEqual(e["sets"][1]["load"], 105)
        # ⋮ do exercício › Adicionar parâmetro › RPE
        b.set_focus(("exmenu", 0, 0))
        self.press(key.ENTER)
        self.pick("Adicionar parâmetro")
        self.pick("RPE")
        self.assertIn("rpe", e["params"])
        # dois blocos e arrastar um para cima do outro: superset
        self.add_block("Exercício único", "Supino com barra")
        self.add_block("Exercício único", "Remada com barra")
        self.app._on_draw()
        b.refresh()
        hx = next(g for g in b.cell_geo if g[0] == ("handle", 2))
        y0, y1 = b.block_geo[1]
        self.app._on_mouse_press(int(hx[1] + 5), int(hx[2] + 5), 1, 0)
        self.app._on_mouse_drag(int(hx[1] + 60), int((y0 + y1) / 2), 0, -40)
        self.app._on_mouse_release(int(hx[1] + 60), int((y0 + y1) / 2))
        self.assertEqual(len(b.struct["blocks"]), 2)
        self.assertEqual(b.struct["blocks"][1]["kind"], "superset")
        # gravar (Ctrl+S) e começar
        self.app._on_key_press(key.S, key.MOD_CTRL)
        self.assertFalse(b.dirty)
        stored = sb.stored(self.app.db, b.wid)
        self.assertEqual([x["kind"] for x in stored["blocks"]], ["single", "superset"])
        names = [w["name"] for w in gym.workouts(self.app.db, "strength")]
        self.assertIn("Pernas e peito", names)
        b.set_focus(("start_session",))
        self.press(key.ENTER)
        from velo.ui import sport_screens as ss
        scr = self.screen()
        self.assertIsInstance(scr, ss.StrengthSessionScreen)
        self.assertEqual(scr.session.labels, ["A", "B1", "B2"])

    def test_reorder_by_dragging_and_block_menu(self):
        b = self.go()
        self.add_block("Aquecimento", "Mobilidade")
        self.add_block("Exercício único", "Agachamento com barra")
        b.refresh()
        hx = next(g for g in b.cell_geo if g[0] == ("handle", 1))
        y0, y1 = b.block_geo[0]
        self.app._on_mouse_press(int(hx[1] + 5), int(hx[2] + 5), 1, 0)
        self.app._on_mouse_drag(int(hx[1] + 60), int(y1 - 3), 0, 40)   # parte de cima
        self.app._on_mouse_release(int(hx[1] + 60), int(y1 - 3))
        self.assertIn("Agachamento", b.struct["blocks"][0]["exercises"][0]["name"])
        b.set_focus(("bmenu", 0))
        self.press(key.ENTER)
        self.pick("Converter em Circuito")
        self.assertEqual(b.struct["blocks"][0]["kind"], "circuit")
        b.set_focus(("rounds", 0))
        self.app._on_text("4")
        self.press(key.ENTER)
        self.assertEqual(b.struct["blocks"][0]["rounds"], 4)
        b.set_focus(("bmenu", 1))
        self.press(key.ENTER)
        self.pick("Remover o bloco")
        self.assertEqual(len(b.struct["blocks"]), 1)

    def test_text_fields_plan_day_and_unsaved_warning(self):
        b = self.go()
        self.add_block("Exercício único", "Agachamento com barra")
        b.set_focus(("instr",))
        self.type("Aquece bem")
        self.assertEqual(b.struct["instructions"], "Aquece bem")
        b.set_focus(("start",))
        self.app._on_text("0730")
        self.assertEqual(b.struct["start_time"], "07:30")
        b.set_focus(("notes", 0, 0))
        self.type("Costas direitas")
        self.assertEqual(b.struct["blocks"][0]["exercises"][0]["notes"], "Costas direitas")
        b.set_focus(("plan",))
        self.press(key.ENTER)
        self.pick("Amanhã")
        self.press(key.ESCAPE)                          # avisa que há alterações
        self.assertIs(self.screen(), b)
        self.app._on_key_press(key.S, key.MOD_CTRL)
        from datetime import date, timedelta
        from velo.core import calendar_view as cv
        plan = cv.planned_for(self.app.db, date.today() + timedelta(days=1))
        self.assertEqual([p.workout_id for p in plan], [b.wid])
        self.press(key.ESCAPE)
        self.assertIsNot(self.screen(), b)

    def test_history_opens_the_analysis_and_exercise_stats(self):
        db = self.app.db
        s = sb.empty()
        sb.add_block(s, "single", [sb.new_exercise(
            next(e for e in gym.exercises(db, "strength") if "Agachamento com barra" in e["name"]))])
        for i in range(3):
            sb.set_value(s, 0, 0, i, "reps", 5)
            sb.set_value(s, 0, 0, i, "load", 100)
        wid = sb.save(db, None, "Só agachamento", s)
        ses = st.StrengthSession(db, Athlete(), wid, clock=lambda: 0.0)
        while not ses.all_done:
            ses.start_set()
            ses.update(20)
            ses.end_set()
            ses.update(200)
        ses.finish()
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Histórico")
        self.pick("agachamento")
        an = self.screen()
        self.assertIsInstance(an, sas.StrengthAnalysisScreen)
        self.assertAlmostEqual(an.data["compliance"], 1.0)
        self.app._on_draw()
        self.press(key.ENTER)
        stats = self.screen()
        self.assertIsInstance(stats, ess.ExerciseStatsScreen)
        self.assertEqual(len(stats.hist), 1)
        stats.set_tab(2)                                 # 1RM estimada
        self.assertEqual(stats.metric, "best_e1rm")
        self.app._on_draw()
        self.press(key.ESCAPE)
        self.press(key.F)
        from velo.ui.feedback_screens import FeedbackScreen
        self.assertIsInstance(self.screen(), FeedbackScreen)

    def test_gym_stats_reach_exercise_statistics(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Estatísticas por exercício")
        self.assertIsInstance(self.screen(), ess.ExerciseStatsScreen)
        self.app._on_draw()


if __name__ == "__main__":
    unittest.main()
