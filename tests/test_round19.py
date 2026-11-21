"""Ronda 19: blocos alterados/saltados com o original, séries corrigidas, complexos de
kettlebell, pastas, planos em CSV, regras do histórico e a sincronização por Wi-Fi."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402,F401

from perennia.core import block_log  # noqa: E402
from perennia.core import endurance as en  # noqa: E402
from perennia.core import rowing as rw  # noqa: E402
from perennia.core import strength as st  # noqa: E402
from perennia.core import workout_meta as wm  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402
from perennia.core.workouts import Step, Workout  # noqa: E402
from perennia.io import rower as rio  # noqa: E402
from tests.test_ride import RideHarness  # noqa: E402
from tests.test_strength import FakeHR, template  # noqa: E402


def make_db(tmp: Path) -> Database:
    db = Database(tmp / "r19.db")
    db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=75, ftp_w=250, lthr=165))
    return db


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)


# ============================================================ registo de blocos


class TestBlockLog(Tmp):
    def test_change_keeps_the_first_original_and_counts(self):
        bl = block_log
        bl.record_change(self.db, "cycling", "s1", 2, "target_w", 200.0, 190.0, 10.0)
        bl.record_change(self.db, "cycling", "s1", 2, "target_w", 200.0, 170.0, 20.0)
        (e,) = bl.events(self.db, "s1")
        self.assertEqual((e["original"], e["value"], e["changes"]), (200.0, 170.0, 2))
        self.assertIn("Bloco 3", bl.describe(e))
        self.assertIn("200", bl.describe(e))
        self.assertIn("170", bl.describe(e))

    def test_skip_keeps_what_was_done(self):
        block_log.record_skip(self.db, "rowing", "s2", 1, 300.0, 130.0, "s", 99.0)
        (e,) = block_log.events(self.db, "s2")
        self.assertAlmostEqual(block_log.completion(e), 130 / 300)
        self.assertIn("2:10", block_log.describe(e))
        self.assertIn("5:00", block_log.describe(e))

    def test_purge_and_by_step(self):
        block_log.record_skip(self.db, "rowing", "s3", 0, 60.0, 0.0, "s")
        block_log.record_change(self.db, "rowing", "s3", 1, "resistance", 5.0, 7.0)
        self.assertEqual(sorted(block_log.by_step(self.db, "s3")), [0, 1])
        block_log.purge(self.db, "s3")
        self.assertEqual(block_log.events(self.db, "s3"), [])

    def test_option_defaults(self):
        self.assertTrue(block_log.can_edit(self.db))
        self.assertEqual(block_log.scope(self.db), "block")
        self.db.set("block_change_scope", "session")
        self.assertEqual(block_log.scope(self.db), "session")


class TestBlockLogCycling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workout = Workout("Intervalos", [
            Step("steady", 60, "pct_ftp", 50, 50, text_cue="Aquecimento"),
            Step("steady", 120, "pct_ftp", 100, 100, text_cue="Bloco 1"),
            Step("steady", 60, "pct_ftp", 50, 50, text_cue="Recuperação"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_erg_change_is_recorded_and_does_not_skip(self):
        h = RideHarness(Path(self.tmp.name), workout=self.workout, erg=True)
        h.run(seconds=70)                                  # já no bloco 2
        idx = h.engine.workout.current_idx
        self.assertEqual(idx, 1)
        h.engine.adjust_resistance(-2)                      # −10 %
        self.assertEqual(h.engine.workout.current_idx, 1)   # não saltou
        (e,) = block_log.events(h.db, h.engine.ride_id)
        self.assertEqual((e["step_idx"], e["field"]), (1, "target_w"))
        self.assertEqual(e["original"], 250.0)
        self.assertEqual(e["value"], 225.0)
        h.close()

    def test_change_lasts_only_for_the_block_by_default(self):
        h = RideHarness(Path(self.tmp.name), workout=self.workout, erg=True)
        h.run(seconds=70)
        h.engine.adjust_resistance(-2)
        self.assertLess(h.engine.state.intensity, 1.0)
        h.run(seconds=120, until_finished=False)            # entra no bloco seguinte
        self.assertEqual(h.engine.state.intensity, 1.0)
        h.close()

    def test_change_can_last_for_the_session(self):
        h = RideHarness(Path(self.tmp.name), workout=self.workout, erg=True)
        h.db.set("block_change_scope", "session")
        h.run(seconds=70)
        h.engine.adjust_resistance(-2)
        h.run(seconds=120, until_finished=False)
        self.assertLess(h.engine.state.intensity, 1.0)
        h.close()

    def test_skip_records_how_much_was_done(self):
        h = RideHarness(Path(self.tmp.name), workout=self.workout, erg=True)
        h.run(seconds=90)                                   # 30 s dentro do bloco 2 (120 s)
        self.assertTrue(h.engine.skip_block())
        sk = [e for e in block_log.events(h.db, h.engine.ride_id) if e["kind"] == "skip"]
        self.assertEqual(len(sk), 1)
        self.assertEqual(sk[0]["step_idx"], 1)
        self.assertEqual(sk[0]["planned"], 120.0)
        self.assertGreater(sk[0]["done"], 20)
        self.assertLess(sk[0]["done"], 40)
        h.close()


class TestBlockLogRowingAndRunning(Tmp):
    def run_for(self, e, seconds, dt=0.5):
        for _ in range(int(seconds / dt)):
            e.update(dt)

    def test_rowing_resistance_change_and_skip(self):
        wid = rw.save_workout(self.db, None, "Teste", "", [
            rw.Step("active", "time", 60, "none", resistance=5),
            rw.Step("active", "time", 60, "none", resistance=7)])
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=100.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, workout_id=wid, out_dir=self.tmp)
        self.run_for(e, 20)
        e.adjust_resistance(2)                              # 5 → 7 dentro do 1.º bloco
        self.assertEqual(e.workout.idx, 0)
        ev = {x["kind"]: x for x in block_log.events(self.db, e.session_id)}
        self.assertEqual((ev["change"]["original"], ev["change"]["value"]), (5.0, 7.0))
        self.assertTrue(e.skip_step())
        ev = {x["kind"]: x for x in block_log.events(self.db, e.session_id)}
        self.assertEqual(ev["skip"]["planned"], 60.0)
        self.assertAlmostEqual(ev["skip"]["done"], 20.0, delta=1.5)
        self.assertEqual(e.workout.idx, 1)

    def test_running_speed_and_incline_change_keep_the_plan(self):
        wid = en.save_workout(self.db, None, "running", "Passadeira", "", [
            en.Step("warmup", "time", 600, 60, 70), en.Step("active", "time", 300, 100, 105)])
        wm.save(self.db, "running", wid, "manual", "pace",
                [{"speed_kmh": 9.0, "incline_pct": 1.0}, {"speed_kmh": 12.0}])
        e = en.EnduranceEngine(self.db, self.db.athlete(), "running", workout_id=wid,
                               out_dir=self.tmp)
        e.start()
        self.assertFalse(e.speed_locked)                    # já se pode alterar o bloco
        self.assertEqual(e.speed_kmh, 9.0)
        self.assertEqual(block_log.events(self.db, e.session_id), [])   # o plano não é alteração
        for _ in range(30):
            e.update(1.0)
        e.set_speed(8.0)
        e.set_speed(8.5)
        e.set_incline(2.0)
        self.assertEqual(e.workout.idx, 0)
        ev = {x["field"]: x for x in block_log.events(self.db, e.session_id)}
        self.assertEqual((ev["speed_kmh"]["original"], ev["speed_kmh"]["value"],
                          ev["speed_kmh"]["changes"]), (9.0, 8.5, 2))
        self.assertEqual((ev["incline_pct"]["original"], ev["incline_pct"]["value"]), (1.0, 2.0))
        self.assertTrue(e.skip_step())
        sk = [x for x in block_log.events(self.db, e.session_id) if x["kind"] == "skip"][0]
        self.assertEqual(sk["planned"], 600.0)
        self.assertAlmostEqual(sk["done"], 30.0, delta=1.5)
        self.assertEqual(e.speed_kmh, 12.0)                 # o bloco seguinte volta ao plano

    def test_locking_can_be_turned_back_on(self):
        self.db.set("block_edit_enabled", False)
        wid = en.save_workout(self.db, None, "running", "P", "", [
            en.Step("active", "time", 300, 100, 105)])
        wm.save(self.db, "running", wid, "manual", "pace", [{"speed_kmh": 10.0}])
        e = en.EnduranceEngine(self.db, self.db.athlete(), "running", workout_id=wid,
                               out_dir=self.tmp)
        e.start()
        self.assertTrue(e.speed_locked)


# ============================================================ séries corrigidas


def run(ses, seconds, dt=0.5):
    for _ in range(int(seconds / dt)):
        ses.update(dt)


class TestSetEditing(Tmp):
    def _session(self):
        st.seed(self.db)
        wid = template(self.db, "Força A")
        ses = st.StrengthSession(self.db, self.db.athlete(), wid, sensors=FakeHR(120),
                                 out_dir=self.tmp / "strength")
        return ses

    def _do(self, ses, n):
        for _ in range(n):
            ses.action()
            run(ses, 10)
            ses.action()
            run(ses, 5)

    def test_edit_any_set_of_a_planned_session_keeps_plan_and_original(self):
        ses = self._session()
        self._do(ses, 3)
        first = ses.sets[0]
        planned = self.db.conn.execute("SELECT planned_reps, planned_load_kg FROM strength_sets"
                                       " WHERE id = ?", (first.id,)).fetchone()
        was = first.reps
        self.assertTrue(ses.edit_done_set(first.id, reps=was - 2, load_kg=first.load_kg, rpe=8))
        row = self.db.conn.execute("SELECT * FROM strength_sets WHERE id = ?",
                                   (first.id,)).fetchone()
        self.assertEqual(row["reps"], was - 2)
        self.assertEqual(row["logged_reps"], was)                    # o registado na hora
        self.assertEqual(row["planned_reps"], planned["planned_reps"])  # o plano não muda
        self.assertIsNotNone(row["edited_at"])
        self.assertEqual(first.reps, was - 2)                        # a sessão a correr vê
        # uma segunda correção não perde o original
        ses.edit_done_set(first.id, reps=was - 1, load_kg=first.load_kg, rpe=8)
        row = self.db.conn.execute("SELECT * FROM strength_sets WHERE id = ?",
                                   (first.id,)).fetchone()
        self.assertEqual(row["logged_reps"], was)
        # os totais da sessão seguem as correções
        res = ses.finish()
        total = self.db.conn.execute("SELECT SUM(reps) AS n FROM strength_sets WHERE session_id"
                                     " = ?", (ses.session_id,)).fetchone()["n"]
        self.assertEqual(res["total_reps"], total)

    def test_set_original_and_edit_after_the_session(self):
        ses = self._session()
        self._do(ses, 2)
        ses.finish()
        sid = ses.sets[0].id
        self.assertTrue(st.edit_set(self.db, sid, reps=3, load_kg=40.0, rpe=None))
        o = st.set_original(self.db, sid)
        self.assertTrue(o["edited"])
        self.assertEqual(o["reps"], 3)
        self.assertEqual(o["logged_reps"], ses.sets[0].reps or o["logged_reps"])
        self.assertFalse(st.edit_set(self.db, 999999, reps=1))

    def test_edit_free_set_still_works_on_free_sessions(self):
        ses = self._session()
        self._do(ses, 1)
        self.assertTrue(st.edit_free_set(self.db, ses.sets[0].id, reps=4, load_kg=None, rpe=None))

    def test_skipping_a_gym_exercise_records_sets_done(self):
        ses = self._session()
        self._do(ses, 2)                                    # 2 séries do 1.º exercício
        idx = ses.item_idx
        done, planned = ses.done_sets(idx), ses.planned_sets(idx)
        ses.skip_item()
        (e,) = [x for x in block_log.events(self.db, ses.session_id) if x["kind"] == "skip"]
        self.assertEqual((e["step_idx"], e["done"], e["planned"], e["unit"]),
                         (idx, float(done), float(planned), "sets"))
        self.assertIn("séries", block_log.describe(e))


if __name__ == "__main__":
    unittest.main()
