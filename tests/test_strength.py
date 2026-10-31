"""Força, recuperação de sessões, exportação de treinos e métricas de forma.

Núcleo primeiro (sem janela), depois a interface contra a pyglet falsa.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import climbs as climbs_mod  # noqa: E402
from velo.core import fit, gpx, stats  # noqa: E402
from velo.core import strength as st  # noqa: E402
from velo.core import workout_export as wx  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.core.ride import AUTO_PAUSED, Reading, RideEngine  # noqa: E402
from velo.core.workouts import Step, Workout, WorkoutRunner, parse_mrc, parse_zwo  # noqa: E402
from velo.io.hub import SensorHub  # noqa: E402
from velo.io.sim import SimulatedTrainer  # noqa: E402

GPX = Path(__file__).parent / "teste.gpx"


class FakeHR:
    """Sensor de FC: sobe devagar durante as séries."""

    def __init__(self, bpm: int | None = 120):
        self.bpm = bpm

    def reading(self):
        return Reading(hr_bpm=self.bpm)


def make_db(tmp: Path) -> Database:
    db = Database(tmp / "perennia.db")
    db.save_athlete(Athlete(name="Teste", birth_year=1990, weight_kg=72.0, ftp_w=250,
                            lthr=165))
    st.seed(db)
    return db


def run(ses, seconds: float, step: float = 0.5) -> None:
    for _ in range(int(seconds / step)):
        ses.update(step)


def template(db, name_part: str) -> str:
    return next(w["id"] for w in st.workouts(db) if name_part in w["name"])


# ======================================================================= força


class TestStrengthCore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seed_is_once_and_deleted_plans_stay_deleted(self):
        n_ex = len(st.exercises(self.db))
        self.assertGreaterEqual(n_ex, 40)
        names = [w["name"] for w in st.workouts(self.db)]
        self.assertEqual(len(names), 3)
        st.delete_workout(self.db, template(self.db, "Força A"))
        st.seed(self.db)
        self.assertEqual(len(st.workouts(self.db)), 2)
        self.assertEqual(len(st.exercises(self.db)), n_ex)

    def test_e1rm_and_volume(self):
        self.assertAlmostEqual(st.e1rm(100, 5), 100 * (1 + 5 / 30))
        self.assertAlmostEqual(st.e1rm(100, 5, rpe=8), 100 * (1 + 7 / 30))   # 2 em reserva
        self.assertEqual(st.e1rm(100, 1), 100.0)
        self.assertIsNone(st.e1rm(40, 20))                 # demasiadas repetições
        self.assertIsNone(st.e1rm(None, 5))
        self.assertEqual(st.set_volume(60, 10, 0.0, 72), 600)
        self.assertEqual(st.set_volume(None, 10, 1.0, 72), 720)   # elevações
        self.assertEqual(st.set_volume(10, 30, 0.0, 72, "time"), 0.0)

    def test_load_from_hr_or_rpe(self):
        self.assertAlmostEqual(st.hr_load([165] * 3600, 165), 100.0)
        self.assertIsNone(st.hr_load([None] * 10, 165))
        self.assertAlmostEqual(st.rpe_load(3600, 10), 100.0)
        self.assertAlmostEqual(st.rpe_load(3600, 8), 64.0)

    def test_full_session_logs_sets_and_writes_fit(self):
        wid = template(self.db, "Força A")
        hr = FakeHR(120)
        ses = st.StrengthSession(self.db, self.db.athlete(), wid, sensors=hr,
                                 out_dir=self.tmp / "strength")
        plan_sets = sum(it.sets for it in ses.items)
        guard = 0
        while not ses.all_done and guard < 100:
            ses.action()                         # começar
            self.assertEqual(ses.phase, st.WORK)
            hr.bpm = 150
            run(ses, 20)
            ses.action()                         # terminar
            hr.bpm = 120
            run(ses, 10)
            guard += 1
        self.assertEqual(len(ses.sets), plan_sets)
        ses.action()
        self.assertEqual(ses.phase, st.DONE)
        result = ses.finish()
        self.assertEqual(result["total_sets"], plan_sets)
        self.assertGreater(result["volume_kg"], 1000)
        self.assertEqual(result["load_source"], "hr")
        self.assertGreater(result["load"], 0)
        self.assertGreater(sum(result["hr_zone_s"]), 0)
        squat = next(e for e in result["exercises"] if e["name"].startswith("Agachamento"))
        self.assertAlmostEqual(squat["best_e1rm"], 60 * (1 + (6 + 2.5) / 30), places=3)
        # na base: sessão concluída, ponto de recuperação apagado
        row = self.db.conn.execute("SELECT * FROM strength_sessions").fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(self.db.checkpoints(), [])
        # o .fit: força (training / strength_training), séries e descansos
        info = fit.verify(result["fit_path"])
        msgs = fit.read_messages(result["fit_path"])
        sport = next(v for g, v in msgs if g == fit.MSG_SPORT)
        self.assertEqual((sport[0], sport[1]), (fit.SPORT_TRAINING, fit.SUB_SPORT_STRENGTH))
        active = [v for g, v in msgs if g == fit.MSG_SET and v.get(5) == 1]
        rest = [v for g, v in msgs if g == fit.MSG_SET and v.get(5) == 0]
        self.assertEqual(len(active), plan_sets)
        self.assertGreater(len(rest), 0)
        bench = next(v for v in active if v.get(7) == st.FIT_CATEGORY["bench_press"])
        self.assertEqual(bench[3], 6)                         # repetições
        self.assertEqual(bench[4], 50 * 16)                   # carga, escala 16
        self.assertGreater(info["messages"][fit.MSG_RECORD], 100)
        self.assertTrue(Path(result["fit_path"]).name.startswith("perennia_"))

    def test_fields_edit_the_last_set_during_rest(self):
        ses = st.StrengthSession(self.db, self.db.athlete(), template(self.db, "Força A"),
                                 sensors=FakeHR(), out_dir=self.tmp / "s")
        ses.goto_item(1)                              # agachamento
        ses.action()
        run(ses, 5)
        ses.action()
        self.assertTrue(ses.editing_last)
        ses.adjust("reps", -1)                        # saíram 5, não 6
        ses.adjust("load_kg", +2)                     # +5 kg
        ses.set_field("rpe", 9)
        row = self.db.conn.execute("SELECT reps, load_kg, rpe FROM strength_sets").fetchone()
        self.assertEqual((row["reps"], row["load_kg"], row["rpe"]), (5, 65.0, 9.0))
        ses.action()                                  # próxima série leva a carga nova
        self.assertEqual(ses.entry["load_kg"], 65.0)
        self.assertEqual(ses.entry["reps"], 6)

    def test_no_hr_uses_rpe_for_the_load(self):
        ses = st.StrengthSession(self.db, self.db.athlete(), template(self.db, "Força A"),
                                 sensors=FakeHR(None), out_dir=self.tmp / "s")
        for _ in range(3):
            ses.action()
            run(ses, 30)
            ses.action()
            run(ses, 30)
        r = ses.finish()
        self.assertEqual(r["load_source"], "rpe")
        self.assertGreater(r["load"], 0)

    def test_crash_and_resume(self):
        wid = template(self.db, "Força B")
        ses = st.StrengthSession(self.db, self.db.athlete(), wid, sensors=FakeHR(130),
                                 out_dir=self.tmp / "s")
        for _ in range(3):
            ses.action()
            run(ses, 12)
            ses.action()
            run(ses, 12)
        ses.add_set()
        t_before, n_before, idx = ses.t, len(ses.sets), ses.item_idx
        ses.suspend()                                  # a aplicação vai abaixo aqui
        del ses
        self.assertEqual(self.db.purge_incomplete(), 0)    # tem ponto: não se fecha
        cps = self.db.checkpoints()
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0]["sport"], "strength")
        again = st.StrengthSession(self.db, self.db.athlete(), wid, sensors=FakeHR(130),
                                   out_dir=self.tmp / "s", resume=cps[0])
        self.assertEqual(len(again.sets), n_before)
        self.assertAlmostEqual(again.t, t_before, delta=5)
        self.assertEqual(again.item_idx, idx)
        self.assertTrue(again.paused)                  # retoma em pausa
        self.assertEqual(again.extra, ses_extra(cps[0]))
        again.toggle_pause()
        again.action()
        run(again, 10)
        again.action()
        r = again.finish()
        self.assertEqual(r["total_sets"], n_before + 1)
        self.assertEqual(self.db.checkpoints(), [])

    def test_purge_closes_sessions_without_checkpoint(self):
        ses = st.StrengthSession(self.db, self.db.athlete(), template(self.db, "Força A"),
                                 out_dir=self.tmp / "s")
        self.db.delete_checkpoint(ses.session_id)
        self.assertEqual(self.db.purge_incomplete(), 1)
        row = self.db.conn.execute("SELECT status FROM strength_sessions").fetchone()
        self.assertEqual(row["status"], "aborted")

    def test_builder_save_and_reload(self):
        ex = {e["name"]: e for e in st.exercises(self.db)}
        new_id = st.add_exercise(self.db, "Remada Pendlay", "back", 0.0, "reps")
        wid = st.save_workout(self.db, None, "Teste", "desc", [
            {"exercise_id": ex["Supino com barra"]["id"], "sets": 5, "reps": 5,
             "load_kg": 80.0, "rpe": 8, "rest_s": 180},
            {"exercise_id": new_id, "sets": 3, "reps": 8, "load_kg": 60, "rpe": None,
             "rest_s": 120}])
        items = st.workout_items(self.db, wid)
        self.assertEqual([i.name for i in items], ["Supino com barra", "Remada Pendlay"])
        self.assertEqual(items[0].target_text(), "5 × 5 @ 80 kg · RPE 8")
        st.save_workout(self.db, wid, "Teste 2", None, [items[1].as_dict()])
        self.assertEqual(len(st.workout_items(self.db, wid)), 1)
        self.assertEqual(st.workout(self.db, wid)["name"], "Teste 2")

    def test_progress_and_period_stats(self):
        wid = template(self.db, "Força A")
        for _ in range(2):
            ses = st.StrengthSession(self.db, self.db.athlete(), wid, sensors=FakeHR(140),
                                     out_dir=self.tmp / "s")
            ses.goto_item(1)
            for _ in range(2):
                ses.action()
                run(ses, 10)
                ses.action()
            ses.finish()
        squat = next(e for e in st.exercises_with_history(self.db)
                     if e["name"].startswith("Agachamento"))
        prog = st.exercise_progress(self.db, squat["id"])
        self.assertEqual(len(prog), 2)
        self.assertEqual(prog[0]["sets"], 2)
        self.assertAlmostEqual(prog[0]["volume"], 2 * 6 * 60)
        series = stats.strength_series(self.db, "sessions", "week", 4)
        self.assertEqual(series[-1][1], 2)
        self.assertEqual(stats.strength_series(self.db, "sets", "week", 4)[-1][1], 4)
        # entra na sequência de dias de treino
        self.assertIn(date.today(), stats.ride_days(self.db))


def ses_extra(cp: dict) -> dict:
    return {int(k): v for k, v in cp["state"]["extra"].items()}


# ================================================================ recuperação


class TestRideRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)
        _, raw = gpx.parse_gpx(GPX)
        self.points = gpx.resample(raw)
        self.climbs = climbs_mod.detect(self.points)
        self.route_id = self.db.insert_route("Serra", self.points, self.climbs, GPX.name)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self, resume=None, workout=None):
        trainer = SimulatedTrainer(base_power=220)
        hub = SensorHub()
        hub.add_source(trainer, role="trainer", is_trainer=True)
        runner = WorkoutRunner(workout, 250, erg_enabled=True) if workout else None
        e = RideEngine(self.db, self.db.athlete(), route_id=self.route_id,
                       points=self.points, climbs=self.db.climbs(self.route_id),
                       workout_runner=runner, sensors=hub, trainer=hub,
                       rides_dir=self.tmp / "rides", meta={"ghosts": [], "erg": True},
                       resume=resume)
        return e, hub

    def ride(self, e, hub, seconds):
        for _ in range(int(seconds / 0.25)):
            hub.tick(0.25)
            e.update(0.25)
            e.drain_events()

    def test_resume_carries_on_where_it_stopped(self):
        e, hub = self.engine()
        self.ride(e, hub, 120)
        e.lap("manual")
        self.ride(e, hub, 61)
        before = (e.state.t_s, e.state.dist_m, e.lap_no, e.state.avg_power,
                  sum(e.state.power_zone_s))
        e.suspend()                                     # falha: nada de finish()
        rid = e.ride_id
        self.assertEqual(self.db.purge_incomplete(), 0)
        cp = self.db.checkpoint(rid)
        self.assertIsNotNone(cp)
        self.assertEqual(cp["sport"], "cycling")

        e2, hub2 = self.engine(resume=cp)
        self.assertEqual(e2.ride_id, rid)
        self.assertTrue(e2.recovered)
        self.assertEqual(e2.state.status, AUTO_PAUSED)
        self.assertAlmostEqual(e2.state.t_s, before[0], delta=1.0)
        self.assertAlmostEqual(e2.state.dist_m, before[1], delta=1.0)
        self.assertEqual(e2.lap_no, before[2])
        self.assertEqual(len(e2.laps), 1)
        self.assertAlmostEqual(e2.state.avg_power, before[3], delta=3)
        self.assertAlmostEqual(sum(e2.state.power_zone_s), before[4], delta=2)
        self.assertTrue(any(ev.kind == "recovered" for ev in e2.drain_events()))
        self.assertTrue(e2.trace)                      # o traço da volta reaparece
        self.ride(e2, hub2, 60)
        self.assertGreater(e2.state.t_s, before[0] + 50)
        result = e2.finish()
        s = result["summary"]
        self.assertGreaterEqual(s.elapsed_s, int(before[0]) + 50)
        laps = result["laps"]
        self.assertEqual(laps[0].trigger, "manual")       # a de antes da falha
        self.assertEqual(laps[-1].trigger, "end")
        self.assertEqual([lp.lap_no for lp in laps], list(range(1, len(laps) + 1)))
        fit.verify(result["fit_path"])
        row = self.db.conn.execute("SELECT status FROM rides WHERE id = ?",
                                   (rid,)).fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertIsNone(self.db.checkpoint(rid))
        # amostras sem buracos nem repetições
        ts = [x.t_s for x in self.db.samples(rid)]
        self.assertEqual(len(ts), len(set(ts)))

    def test_workout_resumes_on_the_same_step(self):
        wk = Workout("Teste", [Step("steady", 120, "pct_ftp", 60, 60),
                               Step("steady", 300, "pct_ftp", 100, 100),
                               Step("steady", 120, "pct_ftp", 50, 50)])
        e, hub = self.engine(workout=wk)
        self.ride(e, hub, 200)
        e.adjust_resistance(+2)                          # ERG: +10 %
        self.ride(e, hub, 5)
        e.suspend()
        cp = self.db.checkpoint(e.ride_id)
        e2, hub2 = self.engine(resume=cp, workout=wk)
        self.assertAlmostEqual(e2.state.intensity, 1.10)
        self.ride(e2, hub2, 2)
        self.assertEqual(e2.state.target_power_w, round(250 * 1.10))

    def test_aborted_and_finished_rides_leave_no_checkpoint(self):
        e, hub = self.engine()
        self.ride(e, hub, 30)
        self.assertIsNotNone(self.db.checkpoint(e.ride_id))
        e.abort()
        self.assertIsNone(self.db.checkpoint(e.ride_id))


# ================================================================ exportação


class TestWorkoutExport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.wk = Workout("Sweet spot 3×10", [
            Step("ramp", 600, "pct_ftp", 50, 75, text_cue="Aquecimento"),
            Step("steady", 600, "pct_ftp", 90, 90, 90, 90, "Bloco 1"),
            Step("steady", 300, "watts", 125, 125),
            Step("freeride", 120, "none"),
            Step("ramp", 300, "pct_ftp", 65, 45)], "Descrição")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_zwo_round_trip(self):
        path = wx.export(self.wk, "zwo", self.tmp, 250)
        back = parse_zwo(path)
        self.assertEqual(back.name, self.wk.name)
        self.assertEqual(len(back.steps), 5)
        self.assertEqual(back.total_seconds, self.wk.total_seconds)
        self.assertEqual(back.steps[0].kind, "ramp")
        self.assertAlmostEqual(back.steps[1].target_lo, 90.0)
        self.assertEqual(back.steps[1].cadence_lo, 90)
        self.assertAlmostEqual(back.steps[2].target_lo, 50.0)       # 125 W de 250
        self.assertEqual(back.steps[3].kind, "freeride")
        self.assertIn("<Warmup", path.read_text())
        self.assertIn("<Cooldown", path.read_text())
        self.assertIn("Aquecimento", path.read_text())

    def test_mrc_and_erg_round_trip(self):
        mrc = parse_mrc(wx.export(self.wk, "mrc", self.tmp, 250))
        erg = parse_mrc(wx.export(self.wk, "erg", self.tmp, 250))
        self.assertEqual(mrc.total_seconds, self.wk.total_seconds)
        self.assertEqual(erg.total_seconds, self.wk.total_seconds)
        self.assertEqual(mrc.steps[1].target_type, "pct_ftp")
        self.assertAlmostEqual(mrc.steps[1].target_lo, 90.0)
        self.assertEqual(erg.steps[1].target_type, "watts")
        self.assertAlmostEqual(erg.steps[1].target_lo, 225.0)
        self.assertAlmostEqual(erg.steps[0].target_hi, 187.5, delta=0.6)

    def test_fit_workout(self):
        path = wx.export(self.wk, "fit", self.tmp, 250)
        msgs = fit.read_messages(path)
        self.assertEqual(next(v for g, v in msgs if g == 0)[0], fit.FILE_TYPE_WORKOUT)
        steps = [v for g, v in msgs if g == fit.MSG_WORKOUT_STEP]
        wkt = next(v for g, v in msgs if g == fit.MSG_WORKOUT)
        self.assertEqual(wkt[6], len(steps))
        self.assertEqual(wkt[8], self.wk.name)
        total_ms = sum(s[2] for s in steps)
        self.assertEqual(total_ms, self.wk.total_seconds * 1000)
        self.assertEqual(len(steps), 10 + 1 + 1 + 1 + 5)       # rampas partidas por minuto
        first = steps[0]
        self.assertEqual(first[7], fit.INTENSITY["warmup"])
        steady = steps[10]
        self.assertEqual((steady[5], steady[6]), (88, 92))     # 90 % ± 2,5
        free = steps[12]
        self.assertEqual(free[3], fit.WKT_TARGET_OPEN)

    def test_unique_names(self):
        a = wx.export(self.wk, "zwo", self.tmp, 250)
        b = wx.export(self.wk, "zwo", self.tmp, 250)
        self.assertNotEqual(a, b)

    def test_repeat_block(self):
        block = [Step("steady", 60, "pct_ftp", 120, 120), Step("steady", 60, "pct_ftp", 50, 50)]
        steps = wx.expand_repeat(4, block)
        self.assertEqual(len(steps), 8)
        steps[0].target_lo = 1
        self.assertEqual(block[0].target_lo, 120)               # cópias, não o original


# ================================================================ forma e eFTP


def _iso(day: date) -> str:
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


class TestFitnessAndFtp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add_ride(self, day: date, tss: float, curve: dict | None = None) -> str:
        rid = self.db.begin_ride(route_id=None, workout_id=None, kind="free", mode="alone",
                                 erg=False, athlete=self.db.athlete(), difficulty=1.0,
                                 extra=0.0, preset="low")
        self.db.conn.execute(
            "UPDATE rides SET status='completed', started_at=?, tss=?, moving_s=3600,"
            " elapsed_s=3600 WHERE id = ?", (_iso(day), tss, rid))
        for d, w in (curve or {}).items():
            self.db.conn.execute("INSERT INTO ride_power_curve VALUES (?,?,?)", (rid, d, w))
        self.db.conn.commit()
        return rid

    def test_ctl_atl_tsb(self):
        today = date.today()
        for k in range(30):
            self.add_ride(today - timedelta(days=k), 100)
        cur = stats.fitness_now(self.db, today=today)
        # 30 dias seguidos de 100: a fadiga já quase lá chegou, a fitness não
        self.assertGreater(cur["atl"], 95)
        self.assertLess(cur["ctl"], 60)
        self.assertLess(cur["tsb"], -30)
        self.assertEqual(cur["state"], "overload")
        series_ = stats.fitness(self.db, 10, today=today)
        self.assertEqual(len(series_), 10)
        self.assertEqual(series_[-1]["date"], today)

    def test_form_states(self):
        self.assertEqual(stats.form_state(30), "transition")
        self.assertEqual(stats.form_state(10), "fresh")
        self.assertEqual(stats.form_state(0), "neutral")
        self.assertEqual(stats.form_state(-20), "optimal")
        self.assertEqual(stats.form_state(-40), "overload")

    def test_strength_load_counts_in_total(self):
        today = date.today()
        self.add_ride(today, 50)
        self.db.conn.execute(
            "INSERT INTO strength_sessions(id, name, status, started_at, elapsed_s, load)"
            " VALUES ('s1', 'x', 'completed', ?, 3600, 40)", (_iso(today),))
        self.db.conn.commit()
        self.assertEqual(stats.daily_load(self.db)[today], 90)
        self.assertEqual(stats.daily_load(self.db, ("cycling",))[today], 50)

    def test_ftp_estimate_methods(self):
        self.assertEqual(stats.estimate_ftp_from({1200: 300})["ftp"], 285)
        self.assertEqual(stats.estimate_ftp_from({1200: 300, 3600: 290})["ftp"], 290)
        # potência crítica: CP 260 W, W′ 20 kJ
        best = {t: 260 + 20000 / t for t in (180, 300, 600)}
        est = stats.estimate_ftp_from(best)
        self.assertEqual(est["method"], "cp")
        self.assertEqual(est["cp"], 260)
        self.assertAlmostEqual(est["w_prime_kj"], 20.0, delta=0.1)
        self.assertEqual(est["ftp"], round(260 * 0.97))
        self.assertIsNone(stats.estimate_ftp_from({5: 900, 60: 500}))

    def test_estimated_ftp_window(self):
        today = date.today()
        self.add_ride(today - timedelta(days=200), 80, {1200: 400})   # fora da janela
        self.add_ride(today - timedelta(days=10), 80, {1200: 300})
        self.assertEqual(stats.estimated_ftp(self.db, today=today)["ftp"], 285)
        series_ = stats.eftp_series(self.db, "month", 12, today=today)
        self.assertEqual(len(series_), 12)
        self.assertEqual(series_[-1][1], 285)

    def test_zones_by_period_and_sport(self):
        rid = self.add_ride(date.today(), 60)
        self.db.append_samples(rid, [
            __import__("velo.core.db", fromlist=["Sample"]).Sample(
                t_s=i, dist_m=i * 8.0, power_w=240 if i < 60 else 100, hr_bpm=150)
            for i in range(120)])
        z = stats.zones_series(self.db, "power", "week", 4)
        self.assertEqual(sum(z[-1][1]), 120)
        self.assertEqual(z[-1][1][3], 60)                      # 96 % FTP = Z4
        z2 = stats.zones_series(self.db, "power", "week", 4)   # da cache
        self.assertEqual(z, z2)
        by = stats.sport_series(self.db, "sessions", "week", 2)
        self.assertEqual(by[-1][1]["cycling"], 1)
        self.assertEqual(by[-1][1]["strength"], 0)


# ================================================================= interface

from tests import test_gui as tg  # noqa: E402
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import sport_screens as ss  # noqa: E402


class TestStrengthGui(tg.GuiCase):
    def go_strength(self):
        from velo.ui import gym_screens as gs
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.assertIsInstance(self.screen(), gs.GymHub)
        self.pick("Sessão de treino")
        self.pick("Força")
        self.assertIsInstance(self.screen(), gs.ModalityScreen)

    def test_train_a_plan_and_finish(self):
        from velo.ui import gym_screens as gs
        self.go_strength()
        self.pick("Força A")
        self.assertIsInstance(self.screen(), ss.StrengthPreview)
        self.assertTrue(any("Agachamento" in b.name for b in self.screen().brief_data.blocks))
        self.pick("Começar")
        scr = self.screen()
        self.assertIsInstance(scr, ss.StrengthSessionScreen)
        for _ in range(10):
            self.app._tick(0.5)
        self.assertEqual(scr.session.t, 0.0)          # o relógio espera pela 1.ª série
        self.app._on_draw()
        self.press(key.SPACE)                             # começar a série
        for _ in range(20):
            self.app._tick(0.5)
        self.assertEqual(scr.clock.value.text, "0:10")   # tempo total ao centro
        self.assertIn("série", scr.clock.sub.text)
        self.press(key.SPACE)                             # terminar
        self.assertEqual(len(scr.session.sets), 1)
        self.select("Segundos")                            # corrige: foram 280 s
        self.app._on_text("280")
        self.assertEqual(scr.session.sets[-1].reps, 280)
        self.select("RPE")
        self.press(key.RIGHT, key.RIGHT)
        self.app._on_draw()
        self.press(key.SPACE)                             # série seguinte
        self.assertEqual(scr.session.phase, "work")
        self.press(key.ESCAPE)                            # pergunta
        self.assertTrue(scr.confirming)
        self.assertTrue(any("sem guardar" in i.label for i in scr.list.items))
        self.pick("Sim, terminar")
        summ = self.screen()
        self.assertIsInstance(summ, ss.StrengthSummaryScreen)
        self.assertEqual(summ.result["total_sets"], 2)
        self.assertTrue(Path(summ.result["fit_path"]).exists())
        self.app._on_draw()
        self.pick("Fechar")
        self.assertIsInstance(self.screen(), gs.GymHub)
        self.pick("Histórico")
        self.assertIn("Força A", self.screen().list.items[0].label)
        self.assertIn("Força", self.screen().list.items[0].detail)
        self.pick("Força A")
        from velo.ui import strength_analysis_screens as sas
        an = self.screen()                                 # a análise pós-treino
        self.assertIsInstance(an, sas.StrengthAnalysisScreen)
        self.assertEqual(an.data["done_sets"], 2)
        self.press(key.S)                                  # as séries, em lista
        items = self.screen().list.items                   # feedback + análise + 2 séries
        self.assertEqual(items[0].label, "Como correu esta sessão?")
        self.assertEqual(items[1].label, "Análise pós-treino")
        self.assertEqual(len(items), 4)

    def test_discard_session(self):
        self.go_strength()
        self.pick("Força A")
        self.pick("Começar")
        scr = self.screen()
        sid = scr.session.session_id
        self.press(key.SPACE)
        self.app._tick(1.0)
        self.press(key.ESCAPE)
        self.pick("sem guardar")
        self.assertIsNone(self.app.db.conn.execute(
            "SELECT 1 FROM strength_sessions WHERE id = ?", (sid,)).fetchone())

    def test_back_arrow_in_session_asks_first(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Sessão de treino")
        self.pick("Longevidade")
        self.pick("Longevidade ·")
        self.pick("Começar")
        scr = self.screen()
        b = scr.back_button.bg
        self.app._on_mouse_press(int(b.x + 5), int(b.y + 5), 1, 0)
        self.assertIs(self.screen(), scr)
        self.assertTrue(scr.confirming)
        self.pick("Não")
        self.assertFalse(scr.confirming)

    def test_builder_creates_a_plan(self):
        from velo.ui import hub_screens as hs_
        self.go_strength()
        self.pick("editor simples")
        ed = self.screen()
        self.assertIsInstance(ed, ss.StrengthWorkoutEditor)
        self.select("Nome")
        for _ in range(40):
            self.press(key.BACKSPACE)
        self.type("Pernas")
        self.pick("Adicionar exercício")
        self.assertIsInstance(self.screen(), hs_.ExerciseInventory)
        self.assertEqual(self.screen().modality(), "strength")
        self.pick("Prensa de pernas")
        self.assertEqual(ed.items[-1]["name"], "Prensa de pernas")
        self.pick("Prensa de pernas")                           # abrir o exercício
        item = self.screen()
        self.assertIsInstance(item, ss.StrengthItemEditor)
        self.select("Séries")
        self.press(key.RIGHT)
        self.select("Carga")
        self.app._on_text("100")
        self.pick("Feito")
        self.assertEqual(ed.items[-1]["sets"], 4)
        self.assertEqual(ed.items[-1]["load_kg"], 100.0)
        self.pick("Adicionar exercício")
        self.pick("Novo exercício")
        self.select("Nome")
        self.type("Nordic curl")
        self.pick("Guardar")
        self.pick("Nordic curl")
        self.assertEqual(ed.items[-1]["name"], "Nordic curl")
        self.pick("Guardar e treinar")
        self.assertIsInstance(self.screen(), ss.StrengthPreview)
        from velo.core import gym
        names = [w["name"] for w in gym.workouts(self.app.db, "strength")]
        self.assertIn("Pernas", names)

    def test_strength_and_general_stats_views(self):
        self.go_strength()
        self.pick("Força A")
        self.pick("Começar")
        for _ in range(2):
            self.press(key.SPACE)
            for _ in range(10):
                self.app._tick(0.5)
            self.press(key.SPACE)
        self.press(key.ESCAPE)
        self.pick("Sim")
        self.pick("Fechar")
        self.pick("Gráficos e análise")
        scr = self.screen()
        self.assertIsInstance(scr, ss.StrengthStatsScreen)
        titles = set()
        for _ in range(len(scr.VIEWS)):
            self.app._on_draw()
            titles.add(scr.chart.title.text)
            self.press(key.TAB)
        self.assertEqual(len(titles), len(scr.VIEWS))
        self.select("Desporto")
        self.press(key.RIGHT)                                      # ginásio → todos
        gen = self.screen()
        self.assertIsInstance(gen, ss.GeneralStatsScreen)
        for _ in range(len(gen.VIEWS)):
            self.app._on_draw()
            self.press(key.TAB)
        self.assertGreater(len(stats.ride_days(self.app.db)), 0)


class TestCyclingBuilderGui(tg.GuiCase):
    def test_build_save_and_export(self):
        self.app.push(ss.WorkoutEditor(self.app, None))           # o editor por passos (P)
        ed = self.screen()
        self.assertIsInstance(ed, ss.WorkoutEditor)
        self.assertEqual(len(ed.steps), 3)
        self.pick("Bloco de repetições")
        rep = self.screen()
        self.select("Repetições")
        self.press(key.LEFT)                                       # 4 ×
        self.pick("Juntar")
        self.assertEqual(len(ed.steps), 3 + 8)
        self.assertEqual(ed.steps[-1].kind, "ramp")               # retorno à calma no fim
        self.pick("Passo constante")
        step = self.screen()
        self.assertIsInstance(step, ss.StepEditor)
        self.select("Duração")
        self.app._on_text("2,5")
        self.assertEqual(ed.steps[-1].duration_s, 150)
        self.select("Unidade")
        self.press(key.ENTER)                                      # watts
        self.assertEqual(ed.steps[-1].target_type, "watts")
        self.pick("Feito")
        self.pick("Exportar")
        exp = self.screen()
        self.assertIsInstance(exp, ss.ExportScreen)
        self.pick("Todos")
        files = sorted(p.suffix for p in exp.folder().iterdir())
        self.assertEqual(files, [".erg", ".fit", ".mrc", ".zwo"])
        back = parse_zwo(next(exp.folder().glob("*.zwo")))
        self.assertEqual(len(back.steps), len(ed.steps))

    def test_edit_existing_workout_by_steps(self):
        self.pick("Construtor de treinos")
        first = self.screen().list.items[1]
        self.select(first.label)
        self.press(key.P)                                          # P: editor por passos
        ed = self.screen()
        self.assertIsInstance(ed, ss.WorkoutEditor)
        n = len(ed.steps)
        self.select("2.")
        self.press(key.DELETE)
        self.pick("Guardar")
        self.assertEqual(len(self.app.db.workout_steps(ed.workout_id)), n - 1)


class TestStatsNewViews(tg.GuiCase):
    def test_fitness_zones_and_eftp(self):
        tg.TestStatsExplorer._ride(self)
        self.pick("Gráficos e análise")
        scr = self.screen()
        for view in ("zones_period", "load", "eftp"):
            scr.view = scr.VIEWS.index(view)
            scr.enter()
            self.app._on_draw()
        scr.view = scr.VIEWS.index("load")
        scr.enter()
        self.assertIn("fitness", scr.summary[0].text)
        scr.view = scr.VIEWS.index("zones_period")
        scr.enter()
        self.assertTrue(scr.chart.points)


class TestRecoveryGui(tg.GuiCase):
    def test_crash_mid_ride_then_resume(self):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(240):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        t_before = ride.engine.state.t_s
        rid = ride.engine.ride_id
        self.app.shutdown(crashed=True)                 # cai aqui

        app2 = app_mod.App(data_dir=Path(self.tmp), width=1280, height=760)
        try:
            rec = app2.current
            self.assertIsInstance(rec, ss.RecoveryScreen)
            self.assertIn("Ciclismo", rec.list.items[0].label)
            app2.hub.add_source(SimulatedTrainer(base_power=200), role="trainer",
                                is_trainer=True)
            rec.list.index = 1                          # Retomar
            rec.list.activate()
            ride2 = app2.current
            self.assertIsInstance(ride2, app_mod.RideScreen)
            self.assertEqual(ride2.engine.ride_id, rid)
            self.assertAlmostEqual(ride2.engine.state.t_s, t_before, delta=6)
            ride2.world.build_all()
            ride2.preparing = False
            for _ in range(40):
                app2.hub.tick(0.5)
                ride2.update(0.5)
            self.assertGreater(ride2.engine.state.t_s, t_before)
            app2._on_key_press(key.F10, 0)
            app2._on_key_press(key.ENTER, 0)
            self.assertIsInstance(app2.current, app_mod.SummaryScreen)
        finally:
            app2.shutdown()

    def test_crash_mid_strength_then_save_as_is(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Sessão de treino")
        self.pick("Força")
        self.pick("Força A")
        self.pick("Começar")
        scr = self.screen()
        for _ in range(2):
            self.press(key.SPACE)
            for _ in range(8):
                self.app._tick(0.5)
            self.press(key.SPACE)
        self.app.shutdown(crashed=True)
        app2 = app_mod.App(data_dir=Path(self.tmp), width=1280, height=760)
        try:
            rec = app2.current
            self.assertIsInstance(rec, ss.RecoveryScreen)
            self.assertIn("Força", rec.list.items[0].label)
            rec.list.index = 2                          # Guardar como está
            rec.list.activate()
            summ = app2.current
            self.assertIsInstance(summ, ss.StrengthSummaryScreen)
            self.assertEqual(summ.result["total_sets"], 2)
            self.assertEqual(app2.db.checkpoints(), [])
        finally:
            app2.shutdown()

    def test_discard(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Sessão de treino")
        self.pick("Força")
        self.pick("Força A")
        self.pick("Começar")
        self.app.shutdown(crashed=True)
        app2 = app_mod.App(data_dir=Path(self.tmp), width=1280, height=760)
        try:
            rec = app2.current
            rec.list.index = 3
            rec.list.activate()
            self.assertIsInstance(app2.current, app_mod.HomeScreen)
            self.assertEqual(app2.db.checkpoints(), [])
        finally:
            app2.shutdown()

    def test_closing_the_window_saves_strength(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Sessão de treino")
        self.pick("Força")
        self.pick("Força A")
        self.pick("Começar")
        self.press(key.SPACE)
        self.app._tick(0.5)
        self.press(key.SPACE)
        self.app.shutdown()
        db = Database(Path(self.tmp) / "perennia.db")
        try:
            row = db.conn.execute("SELECT status FROM strength_sessions").fetchone()
            self.assertEqual(row["status"], "completed")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
