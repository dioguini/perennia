"""Ronda 6: voltas só no modo livre, distância calculada na passadeira,
cópia do treino por sessão, banda cardíaca simulada, rotas e segmentos."""
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

from velo.core import endurance as en  # noqa: E402
from velo.core import rowing as rw  # noqa: E402
from velo.core import workout_meta as wm  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.core.ride import RideEngine  # noqa: E402
from velo.core.workouts import Step, Workout, WorkoutRunner  # noqa: E402
from velo.io import rower as rio  # noqa: E402
from velo.io.hub import SensorHub  # noqa: E402
from velo.io.sim import SimulatedTrainer  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import builder_screens as bs  # noqa: E402
from velo.ui import endurance_screens as es  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ============================================== voltas: só no modo livre


class TestLapsOnlyInFreeMode(Base):
    def _ride(self, workout=None):
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=200), role="trainer", is_trainer=True)
        runner = WorkoutRunner(workout, 250, True) if workout else None
        e = RideEngine(self.db, self.db.athlete(), sensors=hub, trainer=hub,
                       workout_runner=runner, kind="workout" if workout else "free",
                       rides_dir=self.tmp)
        for _ in range(20):
            hub.tick(0.5)
            e.update(0.5)
        return e

    def test_ride_free_makes_laps_workout_does_not(self):
        free = self._ride()
        self.assertTrue(free.manual_laps)
        self.assertIsNotNone(free.lap())
        wk = Workout("t", [Step("steady", 600, "pct_ftp", 90, 90)])
        e = self._ride(wk)
        self.assertFalse(e.manual_laps)
        n = len(e.laps)
        self.assertIsNone(e.lap())                       # «L» não faz nada
        self.assertEqual(len(e.laps), n)

    def test_run_and_row_workouts_have_no_manual_laps(self):
        wid = en.save_workout(self.db, None, "running", "T", "",
                              [en.Step("active", "time", 120, 80, 85)])
        e = en.EnduranceEngine(self.db, self.db.athlete(), "running", workout_id=wid,
                               out_dir=self.tmp)
        e.start()
        e.update(5)
        self.assertFalse(e.manual_laps)
        self.assertIsNone(e.lap())
        free = en.EnduranceEngine(self.db, self.db.athlete(), "running", out_dir=self.tmp)
        self.assertTrue(free.manual_laps)

        rwid = rw.save_workout(self.db, None, "R", "",
                               [rw.Step("active", "time", 120, "power", 90, 100)])
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, source="t"))
        row = rw.RowEngine(self.db, self.db.athlete(), r, workout_id=rwid, out_dir=self.tmp)
        for _ in range(10):
            row.update(0.5)
        self.assertFalse(row.manual_laps)
        self.assertIsNone(row.lap())


# ============================================ corrida: distância calculada


class TestTreadmillDistance(Base):
    def _workout(self):
        wid = en.save_workout(self.db, None, "running", "Passadeira", "", [
            en.Step("warmup", "time", 600, 60, 70), en.Step("active", "time", 300, 100, 105)])
        wm.save(self.db, "running", wid, "manual", "pace",
                [{"speed_kmh": 9.0}, {"speed_kmh": 12.0}])
        return wid

    def test_planned_distance_comes_from_block_speeds(self):
        wid = self._workout()
        w = en.workout(self.db, wid)
        # 10 min a 9 km/h = 1,5 km; 5 min a 12 km/h = 1 km
        self.assertAlmostEqual(en.planned_m(self.db, "running", w), 2500, delta=1)

    def test_session_sets_and_locks_the_block_speed(self):
        wid = self._workout()
        e = en.EnduranceEngine(self.db, self.db.athlete(), "running", workout_id=wid,
                               out_dir=self.tmp)
        e.start()
        self.assertEqual(e.speed_kmh, 9.0)
        self.assertTrue(e.speed_locked)
        for _ in range(601):
            e.update(1.0)
        self.assertEqual(e.workout.idx, 1)
        self.assertEqual(e.speed_kmh, 12.0)
        self.assertAlmostEqual(e.distance_m, 1500 + 12 / 3.6, delta=5)


class TestTreadmillBuilder(tg.GuiCase):
    def setUp(self):
        super().setUp()
        win = self.app.window
        win.width, win.height = 1920, 1080
        self.app._on_resize(1920, 1080)

    def _open(self):
        b = bs.BlockBuilder(self.app, "running", None, control="manual")
        self.app.push(b)
        b.sel = 1
        b.enter()
        return b

    def _row(self, b, label):
        return next(i for i in b.list.items if i.label.startswith(label))

    def test_distance_row_is_computed_and_read_only(self):
        b = self._open()
        blk = b.block
        blk.dur_type, blk.dur = "distance", 1000.0
        b.num_set("speed", 10.0)                       # 1 km a 10 km/h = 6 min
        self.assertEqual(blk.dur_type, "time")
        self.assertAlmostEqual(blk.dur, 360, delta=1)
        b.enter()
        dist = self._row(b, "Distância (calculada)")
        self.assertFalse(dist.enabled)
        self.assertEqual(dist.value, "1.00 km")
        dur_by = self._row(b, "Duração por")
        self.assertFalse(dur_by.enabled)
        b.cycle("dur_type", 1)                         # não passa a distância
        self.assertEqual(blk.dur_type, "time")
        b.num_adjust("speed", 10, True)                # 20 km/h: a distância acompanha
        b.enter()
        self.assertEqual(self._row(b, "Distância (calculada)").value, "2.00 km")
        self.assertIn(f"{b._total_m() / 1000:.2f} km", b.summary.text)


if __name__ == "__main__":
    unittest.main()
