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
from velo.ui import app as app_mod  # noqa: E402
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


# =============================== treino de cada sessão e treinos apagados


class TestSessionWorkoutCopy(Base):
    def _ride_with(self, wid):
        rows = self.db.workout_steps(wid)
        wk = Workout("t", [Step(r["kind"], r["duration_s"], r["target_type"], r["target_lo"],
                                r["target_hi"]) for r in rows])
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=200), role="trainer", is_trainer=True)
        return RideEngine(self.db, self.db.athlete(), sensors=hub, trainer=hub,
                          workout_runner=WorkoutRunner(wk, 250, True), workout_id=wid,
                          kind="workout", rides_dir=self.tmp)

    def _wid(self):
        return self.db.insert_workout("Limiar", [Step("steady", 600, "pct_ftp", 95, 95)
                                                 .as_dict()], "zwo")

    def test_session_keeps_its_own_copy(self):
        from velo.core import feedback as fbm
        from velo.core import session_workouts as sw
        wid = self._wid()
        e = self._ride_with(wid)
        link = sw.of_session(self.db, "ride", e.ride_id)
        self.assertEqual(link["workout_id"], wid)
        copy = link["copy_id"]
        self.assertNotEqual(copy, wid)
        self.assertEqual(sw.status(self.db, "cycling", copy), "session")
        self.assertNotIn(copy, [w["id"] for w in self.db.workouts()])   # fora da lista
        # o original muda e depois é apagado: a sessão vê o treino como foi feito
        self.db.update_workout(wid, "Limiar", [Step("steady", 60, "pct_ftp", 50, 50)
                                               .as_dict()])
        self.db.delete_workout(wid)
        self.assertNotIn(wid, [w["id"] for w in self.db.workouts()])
        self.assertEqual(sw.status(self.db, "cycling", wid), "deleted")
        self.assertTrue(self.db.workout_steps(wid))                       # não se perdeu
        sess = fbm.load_session(self.db, "ride", e.ride_id)
        self.assertEqual(sess.workout_id, copy)
        self.assertEqual(sess.origin_workout_id, wid)
        self.assertEqual(fbm.prescribed(self.db, sess).raw_blocks[0].seconds, 600)
        self.assertEqual(sw.state(self.db, "ride", e.ride_id, "cycling", wid), "deleted")
        self.assertIn("Apagado", sw.state_text("deleted"))

    def test_discarded_session_takes_the_copy_with_it(self):
        from velo.core import session_workouts as sw
        wid = self._wid()
        e = self._ride_with(wid)
        copy = sw.of_session(self.db, "ride", e.ride_id)["copy_id"]
        e.discard()
        self.assertIsNone(sw.of_session(self.db, "ride", e.ride_id))
        self.assertIsNone(sw.status(self.db, "cycling", copy))
        self.assertEqual(sw.status(self.db, "cycling", wid), "active")

    def test_run_and_row_sessions_copy_too_and_purge_cleans_orphans(self):
        from velo.core import session_workouts as sw
        wid = en.save_workout(self.db, None, "running", "T", "",
                              [en.Step("active", "time", 120, 80, 85)])
        e = en.EnduranceEngine(self.db, self.db.athlete(), "running", workout_id=wid,
                               out_dir=self.tmp)
        self.assertIsNotNone(sw.of_session(self.db, "endurance", e.session_id))
        rwid = rw.save_workout(self.db, None, "R", "",
                               [rw.Step("active", "time", 120, "power", 90, 100)])
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, source="t"))
        row = rw.RowEngine(self.db, self.db.athlete(), r, workout_id=rwid, out_dir=self.tmp)
        self.assertIsNotNone(sw.of_session(self.db, "row", row.session_id))
        # uma sessão que desaparece sem passar por «descartar»
        self.db.conn.execute("DELETE FROM endurance_sessions WHERE id = ?", (e.session_id,))
        self.db.conn.commit()
        self.assertEqual(sw.purge(self.db), 1)
        self.assertIsNone(sw.of_session(self.db, "endurance", e.session_id))
        self.assertIsNotNone(sw.of_session(self.db, "row", row.session_id))


class TestWorkoutFiles(Base):
    def test_fit_and_zwo_for_every_sport(self):
        from velo.core import fit
        from velo.core import session_workouts as sw
        from velo.core import workout_files as wf
        p = fit.write_row_workout(self.tmp / "r.fit", "Remo X", [
            {"name": "aq", "seconds": 300, "lo_w": 100, "hi_w": 120, "intensity": "warmup"},
            {"name": "forte", "meters": 500, "lo_w": 200, "intensity": "active"}])
        loaded = wf.read(p, "rowing", *wf.context(self.db, "rowing"))
        self.assertEqual([s.dur_type for s in loaded.steps], ["time", "distance"])
        self.assertEqual(loaded.steps[0].kind, "warmup")
        wid = wf.save(self.db, "rowing", loaded, keep=False)
        self.assertEqual(sw.status(self.db, "rowing", wid), "session")
        self.assertNotIn(wid, [w["id"] for w in rw.workouts(self.db)])
        zwo = self.tmp / "run.zwo"
        zwo.write_text('<workout_file><name>Run Z</name><workout>'
                       '<Warmup Duration="600" PowerLow="0.6" PowerHigh="0.8"/>'
                       '<SteadyState Duration="300" Power="1.0"/>'
                       '<Cooldown Duration="300" PowerLow="0.8" PowerHigh="0.6"/>'
                       '</workout></workout_file>')
        run = wf.read(zwo, "running", *wf.context(self.db, "running"))
        self.assertEqual([s.kind for s in run.steps], ["warmup", "active", "cooldown"])
        rid = wf.save(self.db, "running", run, keep=True)
        self.assertEqual(wf.same_in_list(self.db, "running", run), rid)   # sem duplicar
        self.assertEqual(sorted(p.name for p in wf.scan("running", [str(self.tmp)])),
                         ["r.fit", "run.zwo"])
        with self.assertRaises(wf.FileError):
            wf.read(self.tmp / "x.mrc", "running")


class TestLoadFromComputer(tg.GuiCase):
    def _zwo(self, name="Do PC"):
        zwo = Path(self.tmp) / "pc.zwo"
        zwo.write_text(f'<workout_file><name>{name}</name><workout>'
                       '<SteadyState Duration="300" Power="0.9"/>'
                       '</workout></workout_file>')
        return zwo

    def test_start_from_the_computer_just_for_this_session(self):
        from velo.core import session_workouts as sw
        from velo.ui import session_setup
        from velo.ui.workout_import import WorkoutFilePopup
        zwo = self._zwo()
        self.pick("Sessão de treino")
        self.pick("Do computador")
        pop = self.screen()
        self.assertIsInstance(pop, WorkoutFilePopup)
        n0 = len(self.app.db.workouts())
        pop.pick(zwo)
        self.assertIn("Guardar «Do PC» na lista de treinos?", self.screen().title_text)
        self.pick("Só para esta sessão")
        setup = self.screen()
        self.assertIsInstance(setup, session_setup.SessionSetup)
        self.assertEqual(sw.status(self.app.db, "cycling", setup.workout_id), "session")
        self.assertEqual(len(self.app.db.workouts()), n0)          # a lista não encheu
        self.assertEqual(setup.title(), "Do PC")

    def test_keep_in_the_list_from_a_running_session(self):
        from velo.core import session_workouts as sw
        from velo.ui import session_setup
        zwo = self._zwo("Corrida PC")
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Do computador")
        self.screen().pick(zwo)
        self.pick("Guardar na lista")
        setup = self.screen()
        self.assertIsInstance(setup, session_setup.SessionSetup)
        self.assertEqual(sw.status(self.app.db, "running", setup.workout_id), "active")
        self.assertIn("Corrida PC", [w["name"] for w in en.workouts(self.app.db, "running")])

    def test_delete_from_any_builder_list_keeps_the_steps(self):
        from velo.core import session_workouts as sw
        self.press(key.ESCAPE)
        self.pick("Remo")
        hub = self.screen()
        hub.tab_named("Lista de treinos")
        first = next(i for i in hub.list.items if isinstance(i.data, tuple))
        hub.list.index = hub.list.items.index(first)
        hub.list._sync()
        self.press(key.DELETE)
        self.assertIn("Sai da lista de treinos", self.screen().sub_text)
        self.pick("Apagar")
        wid = first.data[1]
        self.assertEqual(sw.status(self.app.db, "rowing", wid), "deleted")
        self.assertTrue(rw.steps_of(self.app.db, wid))


# ======================================================= FC simulada


class TestSimulatedHeartStrap(unittest.TestCase):
    def test_hr_follows_the_effort(self):
        from velo.io.sim import SimulatedHeartStrap
        effort = {"v": None}
        strap = SimulatedHeartStrap(effort=lambda: effort["v"])
        for _ in range(120):
            strap.tick(1.0)
        rest = strap.reading().hr_bpm
        self.assertLess(rest, 80)
        effort["v"] = 1.0                                   # no limiar
        for _ in range(300):
            strap.tick(1.0)
        hard = strap.reading().hr_bpm
        self.assertGreater(hard, 160)
        effort["v"] = 0.5
        for _ in range(300):
            strap.tick(1.0)
        self.assertLess(strap.reading().hr_bpm, hard - 15)

    def test_strap_wins_over_the_trainer_hr(self):
        from velo.io.sim import SimulatedHeartStrap
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=200), role="simulated", is_trainer=True)
        hub.add_source(SimulatedHeartStrap(effort=lambda: 1.2), role="hr_monitor")
        for _ in range(10):
            hub.tick(1.0)
        self.assertEqual(hub.source_of("hr"), "SEM HARDWARE - Banda cardíaca")


class TestHeartStrapInDevices(tg.GuiCase):
    def test_add_from_devices_and_run_with_it(self):
        self.app.push(app_mod.DeviceScreen(self.app))
        self.pick("SEM HARDWARE - Banda cardíaca")
        self.assertIn("sim:hr", [getattr(s, "device_id", "") for s in self.app.hub.sources])
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("✓ SEM HARDWARE - Banda cardíaca", labels)
        self.assertNotIn("SEM HARDWARE - Banda cardíaca", labels)   # não se liga duas vezes
        self.press(key.ESCAPE)
        self.app.reset_to_menu()
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        run = self.screen()
        self.assertIsInstance(run, es.EnduranceSession)
        run.engine.start()
        for _ in range(60):
            run.update(1.0)
        self.assertIsNotNone(run.engine.hr_bpm)
        self.assertIsNotNone(self.app.effort_now())


# ===================================================== rotas e segmentos


class TestRoutesAndSegmentsCore(tg.GuiCase):
    def test_times_done_profile_and_perennia_segments(self):
        from velo.core import routes as routes_mod
        from velo.core import segments as seg_mod
        db = self.app.db
        prof = routes_mod.profile(db, self.route_id)
        self.assertEqual(len(prof), 160)
        self.assertAlmostEqual(prof[-1][0], self.points[-1].dist_m, delta=1)
        self.assertEqual(routes_mod.times_done(db, self.route_id)["total"], 0)
        sid = seg_mod.save_perennia(db, None, self.route_id, "Rampa", 1000, 2500)
        segs = seg_mod.load(db, self.route_id)
        mine = [s for s in segs if s.source == "perennia"]
        self.assertEqual([s.name for s in mine], ["Rampa"])
        self.assertEqual(mine[0].key, f"perennia:{sid}")
        self.assertAlmostEqual(mine[0].length_m, 1500)
        self.assertIsNotNone(mine[0].avg_grade)
        with self.assertRaises(ValueError):
            seg_mod.save_perennia(db, None, self.route_id, "Curto", 1000, 1020)
        # um tempo numa sessão de corrida
        seg_mod.save_effort(db, "s1", sid, 400, source="perennia", kind="endurance",
                            sport="running")
        self.assertEqual(seg_mod.efforts(db, "perennia", sid)[0]["elapsed_s"], 400)
        self.assertEqual(seg_mod.load(db, self.route_id, ("perennia",))[0].local_best_s, 400)
        self.assertEqual(seg_mod.purge(db), 1)                # «s1» não existe
        seg_mod.delete_perennia(db, sid)
        self.assertEqual(seg_mod.load(db, self.route_id, ("perennia",)), [])

    def test_tracker_keeps_strava_and_perennia_apart(self):
        from velo.core import segments as seg_mod
        a = seg_mod.Segment(7, "S", 100, 400, source="strava")
        b = seg_mod.Segment(7, "P", 100, 300, source="perennia")
        tr_ = seg_mod.SegmentTracker([a, b])
        ev = tr_.observe(110, 0)
        self.assertEqual(len([k for k, _ in ev if k == "strava_start"]), 2)
        ev = tr_.observe(310, 30)
        self.assertEqual([(k, d["source"]) for k, d in ev], [("strava_end", "perennia")])


class TestRoutesMenu(tg.GuiCase):
    def setUp(self):
        super().setUp()
        win = self.app.window
        win.width, win.height = 1920, 1080
        self.app._on_resize(1920, 1080)

    def test_home_tile_opens_routes_with_times_done(self):
        from velo.ui import route_screens
        self.press(key.ESCAPE)
        self.pick("Rotas")
        scr = self.screen()
        self.assertIsInstance(scr, route_screens.RoutesScreen)
        row = next(i for i in scr.list.items if i.label == "Serra de Teste")
        self.assertIn("ainda não feita", row.detail)
        self.assertIn("+ Carregar .gpx", [i.label for i in scr.list.items])
        self.pick("Serra de Teste")
        ov = self.screen()
        self.assertIsInstance(ov, route_screens.RouteOverview)
        labels = [i.label for i in ov.list.items]
        for want in ("Distância", "Altitude", "Vezes feita", "Segmentos",
                     "Começar no ciclismo", "Começar na corrida"):
            self.assertIn(want, labels)
        self.app._on_draw()
        self.assertTrue(any(b.opacity for b in ov.chart.bars))

    def test_new_segment_from_the_route_and_the_overview(self):
        from velo.core import segments as seg_mod
        from velo.ui import route_screens, segment_screens
        self.app.push(route_screens.RouteOverview(self.app, self.route_id))
        self.pick("+ Novo segmento")
        ed = self.screen()
        self.assertIsInstance(ed, segment_screens.SegmentEditor)
        self.select("Nome")
        self.type("Muro")
        self.select("Início")
        self.press(key.RIGHT)                               # km 0,1
        self.select("Fim por")
        self.press(key.RIGHT)                               # pela distância
        self.select("Distância")
        self.press(key.RIGHT, key.RIGHT)
        self.assertAlmostEqual(ed.v["end_km"] - ed.v["start_km"], 1.1, places=2)
        self.pick("Guardar e sair")
        segs = seg_mod.load(self.app.db, self.route_id, ("perennia",))
        self.assertEqual([s.name for s in segs], ["Muro"])
        self.assertAlmostEqual(segs[0].start_m, 100, delta=1)
        # na visão geral (menu Segmentos), com o tempo e a rota
        self.app.push(segment_screens.SegmentsScreen(self.app))
        scr = self.screen()
        labels = [i.label for i in scr.list.items]
        self.assertIn("Serra de Teste", labels)                 # o título da rota
        self.assertIn("Muro", labels)
        self.select("Muro")
        self.app._on_draw()
        self.assertIn("Muro", scr.info[0].text)
        self.pick("Muro")
        self.assertIsInstance(self.screen(), segment_screens.SegmentDetail)
        self.assertIn("Ainda sem tempos", [i.label for i in self.screen().list.items])
        self.press(key.ESCAPE)
        self.select("Muro")
        self.press(key.DELETE)
        self.assertIn("Apagar o segmento", self.screen().title_text)
        self.pick("Apagar")
        self.assertEqual(seg_mod.load(self.app.db, self.route_id, ("perennia",)), [])

    def test_running_on_a_route_times_the_segment(self):
        from velo.core import routes as routes_mod
        from velo.core import segments as seg_mod
        from velo.ui import route_screens
        sid = seg_mod.save_perennia(self.app.db, None, self.route_id, "Reta", 50, 400)
        self.app.push(route_screens.RouteOverview(self.app, self.route_id))
        self.pick("Começar na corrida")
        setup = self.screen()
        self.assertEqual((setup.sport, setup.route_id), ("running", self.route_id))
        self.assertIn("Segmentos da Perennia", [i.label for i in setup.list.items])
        self.pick("Começar")
        run = self.screen()
        self.assertIsInstance(run, es.EnduranceSession)
        run.engine.start()
        run.engine.set_speed(18.0)                          # 5 m/s
        for _ in range(100):
            run.update(1.0)
        ef = seg_mod.efforts(self.app.db, "perennia", sid)
        self.assertEqual(len(ef), 1)
        self.assertAlmostEqual(ef[0]["elapsed_s"], 70, delta=4)
        res = run.engine.finish()
        self.assertEqual(routes_mod.times_done(self.app.db, self.route_id)["running"], 1)
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
