"""Testes de integração do motor da sessão, com o trainer simulado.

Percorrem uma rota inteira em tempo acelerado e verificam o que o atleta
vê: distância, subidas cronometradas, voltas, classificações, fantasmas,
ERG, e o .fit no fim.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from velo.core import climbs as climbs_mod
from velo.core import fit, ftp, gpx, physics
from velo.core.db import Athlete, Database
from velo.core.ride import Ghost, RideEngine, load_ghosts
from velo.core.workouts import Step, Workout, WorkoutRunner
from velo.io.hub import SensorHub
from velo.io.sim import SimulatedTrainer

GPX = Path(__file__).parent / "teste.gpx"
DT = 0.25     # passo de simulação: 4 "frames" por segundo
MAX_STEPS = 40_000


class RideHarness:
    """Monta base de dados, rota, sensores e motor para um teste."""

    def __init__(self, tmp: Path, *, base_power: int = 200, workout=None,
                 erg: bool = False, ghosts=(), with_hr: bool = True,
                 difficulty: float = 1.0, extra: float = 0.0,
                 chase_level: str | None = None, auto_pause: bool = True,
                 with_route: bool = True):
        self.db = Database(tmp / "perennia.db")
        self.db.set("trainer_difficulty", difficulty)
        self.db.set("extra_resistance_pct", extra)
        self.db.set("auto_pause", auto_pause)
        self.db.save_athlete(Athlete(name="Teste", birth_year=1990, weight_kg=72.0,
                                     ftp_w=250, lthr=165))
        self.athlete = self.db.athlete()

        _, raw = gpx.parse_gpx(GPX)
        self.points = gpx.resample(raw)
        self.climbs = climbs_mod.detect(self.points)
        self.route_id = self.db.insert_route("Serra de Teste", self.points, self.climbs,
                                             GPX.name)

        self.trainer = SimulatedTrainer(base_power=base_power, with_hr=with_hr)
        self.hub = SensorHub()
        self.hub.add_source(self.trainer, role="trainer", is_trainer=True)

        runner = None
        if workout is not None:
            runner = WorkoutRunner(workout, self.athlete.ftp_w, erg)

        rid = self.route_id if with_route else None
        self.engine = RideEngine(
            self.db, self.athlete, route_id=rid,
            points=self.db.route_points(rid) if rid else None,
            climbs=self.db.climbs(rid) if rid else (),
            workout_runner=runner, ghosts=ghosts,
            kind="chase" if chase_level else "route", chase_level=chase_level,
            sensors=self.hub, trainer=self.hub, rides_dir=tmp / "rides",
        )
        self.events: list = []

    def run(self, until_finished: bool = True, seconds: float | None = None) -> None:
        """Corre até completar mais uma volta à rota (ou até `seconds`)."""
        steps = 0
        loops_before = self.engine.state.loops
        target = seconds / DT if seconds else MAX_STEPS
        while steps < min(MAX_STEPS, target):
            self.hub.tick(DT)
            self.engine.update(DT)
            self.events.extend(self.engine.drain_events())
            steps += 1
            if until_finished and self.engine.state.loops > loops_before:
                break

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]

    def of(self, kind: str) -> list:
        return [e for e in self.events if e.kind == kind]

    def close(self) -> None:
        self.db.close()


class TestFullRide(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = RideHarness(Path(self.tmp.name))

    def tearDown(self):
        self.h.close()
        self.tmp.cleanup()

    def test_completes_a_loop_and_keeps_going(self):
        """Chegar ao fim da rota marca uma volta e a sessão continua."""
        self.h.run()
        total = self.h.points[-1].dist_m
        self.assertTrue(self.h.engine.route_finished)
        self.assertEqual(self.h.engine.state.loops, 1)
        self.assertGreaterEqual(self.h.engine.state.dist_m, total)
        self.assertLess(self.h.engine.state.pos_m, 50.0)        # deu a volta
        self.assertIn("route_loop", self.h.kinds())
        loop = self.h.of("route_loop")[0].data
        self.assertEqual(loop["loops"], 1)
        self.assertGreater(loop["loop_time_s"], 60)
        # … e não terminou: continua a andar
        self.h.run(until_finished=False, seconds=60)
        self.assertFalse(self.h.engine.finished)
        self.assertGreater(self.h.engine.state.pos_m, 100.0)

    def test_stopping_pedalling_auto_pauses_and_pedalling_resumes(self):
        self.h.run(seconds=60)
        self.h.trainer.base_power = 0            # deixa de pedalar
        t0 = self.h.engine.state.t_s
        self.h.run(until_finished=False, seconds=120)
        e = self.h.engine
        self.assertFalse(e.finished)                       # a sessão continua aberta
        self.assertTrue(e.auto_pause)
        self.assertEqual(e.state.status, "auto_paused")
        # o relógio parou poucos segundos depois de deixar de pedalar
        self.assertLess(e.state.t_s, t0 + 8)
        self.assertGreater(e.state.paused_s, 100)
        self.assertIn("auto_pause", self.h.kinds())
        d0 = e.state.dist_m
        self.h.trainer.base_power = 200          # volta a pedalar
        self.h.run(until_finished=False, seconds=30)
        self.assertFalse(e.paused)
        self.assertIn("auto_resume", self.h.kinds())
        self.assertGreater(e.state.t_s, t0 + 20)
        self.assertGreater(e.state.dist_m, d0)
        s = e.finish()["summary"]
        self.assertGreaterEqual(s.paused_s, 100)
        row = self.h.db.conn.execute("SELECT paused_s FROM rides WHERE id = ?",
                                     (e.ride_id,)).fetchone()
        self.assertEqual(row["paused_s"], s.paused_s)

    def test_left_right_balance_everywhere(self):
        self.h.run()                                  # uma volta, com a subida
        e = self.h.engine
        self.assertIsNotNone(e.state.balance_3s)
        # o simulador tem a perna esquerda um pouco mais fraca, como é comum
        self.assertAlmostEqual(e.state.balance_3s, 47.5, delta=3.0)
        self.assertAlmostEqual(e.state.avg_balance, 47.5, delta=2.0)
        climb = e.climb_results[0]
        self.assertIsNotNone(climb["avg_balance_left"])
        row = self.h.db.conn.execute(
            "SELECT avg_balance_left FROM climb_efforts").fetchone()
        self.assertAlmostEqual(row["avg_balance_left"], climb["avg_balance_left"])
        result = e.finish()
        self.assertAlmostEqual(result["summary"].avg_balance_left, 47.5, delta=2.0)
        laps = self.h.db.laps(e.ride_id)
        self.assertTrue(all(r["avg_balance_left"] is not None for r in laps))
        from velo.core import stats
        hist = stats.balance_history(self.h.db)
        self.assertEqual(len(hist), 1)
        self.assertIsNotNone(stats.avg_balance(self.h.db))
        self.assertGreater(fit.verify(result["fit_path"])["messages"][fit.MSG_RECORD], 50)

    def test_torque_effectiveness_and_smoothness_flow_to_the_fit(self):
        self.h.run(seconds=120)
        e = self.h.engine
        self.assertIsNotNone(e.state.pedal["te_left"])
        self.assertAlmostEqual(e.state.avg_pedal["te_right"], 79.0, delta=2.5)
        result = e.finish()
        s = result["summary"]
        self.assertAlmostEqual(s.pedal["ps_left"], 22.0, delta=2.0)
        row = self.h.db.conn.execute(
            "SELECT avg_te_left, avg_ps_right FROM rides WHERE id = ?",
            (e.ride_id,)).fetchone()
        self.assertAlmostEqual(row["avg_te_left"], s.pedal["te_left"])
        lap = self.h.db.conn.execute(
            "SELECT avg_te_left FROM laps WHERE ride_id = ?", (e.ride_id,)).fetchone()
        self.assertIsNotNone(lap["avg_te_left"])
        self.assertIsNotNone(self.h.db.samples(e.ride_id)[5].te_left)
        msgs = fit.read_messages(result["fit_path"])
        rec = next(v for g, v in msgs if g == fit.MSG_RECORD and 43 in v)
        self.assertGreater(rec[43], 140)                    # > 70 %, em meios por cento

    def test_fit_is_named_after_the_gpx_and_marked_virtual(self):
        import time as _time
        self.h.run(seconds=30)
        result = self.h.engine.finish()
        today = _time.strftime("%Y-%m-%d")
        self.assertEqual(result["name"], f"perennia_{today}_teste")
        self.assertEqual(Path(result["fit_path"]).name, f"perennia_{today}_teste.fit")
        row = self.h.db.conn.execute("SELECT name FROM rides WHERE id = ?",
                                     (self.h.engine.ride_id,)).fetchone()
        self.assertEqual(row["name"], result["name"])
        session = next(v for g, v in fit.read_messages(result["fit_path"])
                       if g == fit.MSG_SESSION)
        self.assertEqual(session[6], fit.SUB_SPORT_VIRTUAL)
        self.assertEqual(session[110], result["name"])

    def test_pedals_that_keep_repeating_still_pause_the_ride(self):
        """O caso real da Assioma: parada, continua a repetir a última página."""
        from velo.io import ant
        from velo.io.hub import SensorHub
        now = [0.0]
        hub = SensorHub(clock=lambda: now[0])
        pedals = ant.AntSensor(ant.AntStick(), 3,
                               ant.AntDiscovered(4321, ant.DEVICE_POWER, "assioma"), hub)
        pedals._stall.clock = lambda: now[0]
        hub.add_source(pedals, role="power_meter")
        e = RideEngine(self.h.db, self.h.athlete, route_id=self.h.route_id,
                       points=self.h.db.route_points(self.h.route_id),
                       climbs=self.h.db.climbs(self.h.route_id), sensors=hub,
                       trainer=None, rides_dir=Path(self.tmp.name) / "r2")
        event = 0

        def tick(pedalling: bool):
            nonlocal event
            now[0] += 0.25
            if pedalling:
                event = (event + 1) % 256
            pedals._on_page(3, bytes((0x10, event, 0x80 | 52, 88, 0, 0, 230, 0)))
            e.update(0.25)

        for _ in range(120):                      # 30 s a pedalar
            tick(True)
        t0 = e.state.t_s
        for _ in range(240):                      # 60 s parado (casa de banho)
            tick(False)
        self.assertTrue(e.auto_pause)
        self.assertLess(e.state.t_s, t0 + 7)      # 3 s até zerar + 3 s até pausar
        self.assertEqual(e.state.power_w, 0)      # e o ecrã mostra 0, não 230
        for _ in range(40):                       # volta a pedalar
            tick(True)
        self.assertFalse(e.paused)
        self.assertGreater(e.state.t_s, t0 + 8)

    def test_time_in_zones_trace_and_live_lap(self):
        self.h.run(until_finished=False, seconds=120)
        e = self.h.engine
        st = e.state
        self.assertAlmostEqual(sum(st.power_zone_s), 120, delta=2)
        self.assertAlmostEqual(sum(st.hr_zone_s), 120, delta=2)
        self.assertEqual(len(st.power_zone_s), 7)
        self.assertGreater(len(e.trace), 100)
        pos, p, hr = e.trace[-1]
        self.assertAlmostEqual(pos, st.pos_m, delta=15)
        lap = e.current_lap()
        self.assertEqual(lap["lap_no"], 1)
        self.assertAlmostEqual(lap["elapsed_s"], 120, delta=1)
        self.assertGreater(lap["avg_power_w"], 100)
        self.assertIsNotNone(lap["avg_power_zone"])
        self.assertIsNotNone(st.avg_torque)
        self.assertEqual(st.weight_kg, 72.0)

    def test_resistance_feel_changes_what_the_trainer_gets(self):
        e = self.h.engine
        self.h.run(until_finished=False, seconds=5)
        self.assertEqual(e.adjust_resistance(-3), "sim")
        self.assertAlmostEqual(e.difficulty, 0.7)
        self.h.run(until_finished=False, seconds=2)
        self.assertAlmostEqual(self.h.trainer.last_grade,
                               physics.trainer_grade(e.state.grade_pct, 0.7, 0.0), delta=0.25)
        for _ in range(20):
            e.adjust_resistance(+1)
        self.assertEqual(e.difficulty, 1.5)              # limite
        kinds = [x.kind for x in e.drain_events()]
        self.assertIn("resistance", kinds)

    def test_cancelled_finish_resumes_when_pedalling(self):
        e = self.h.engine
        self.h.run(until_finished=False, seconds=10)
        e.pause(confirming=True)
        t0 = e.state.t_s
        self.h.run(until_finished=False, seconds=5)
        self.assertEqual(e.state.t_s, t0)
        e.resume_on_pedal()
        self.assertTrue(e.auto_pause)
        self.h.run(until_finished=False, seconds=5)
        self.assertFalse(e.paused)
        self.assertGreater(e.state.t_s, t0 + 3)

    def test_manual_pause_is_not_undone_by_pedalling(self):
        self.h.run(seconds=20)
        e = self.h.engine
        e.pause()
        t0, d0 = e.state.t_s, e.state.dist_m
        self.h.run(until_finished=False, seconds=30)       # continua a pedalar
        self.assertTrue(e.manual_pause)
        self.assertEqual(e.state.status, "paused")
        self.assertEqual(e.state.t_s, t0)
        self.assertAlmostEqual(e.state.dist_m, d0, delta=0.01)
        e.resume()
        self.h.run(until_finished=False, seconds=10)
        self.assertGreater(e.state.t_s, t0 + 8)

    def test_auto_pause_can_be_turned_off(self):
        self.h.close()
        self.h = RideHarness(Path(self.tmp.name) / "off", auto_pause=False)
        self.h.run(seconds=30)
        self.h.trainer.base_power = 0
        t0 = self.h.engine.state.t_s
        self.h.run(until_finished=False, seconds=60)
        self.assertFalse(self.h.engine.paused)
        self.assertGreater(self.h.engine.state.t_s, t0 + 55)

    def test_coasting_downhill_does_not_pause(self):
        e = self.h.engine
        # chega à descida (a rota de teste desce a partir dos 4 km)
        steps = 0
        while e.state.pos_m < 4300 and steps < MAX_STEPS:
            self.h.hub.tick(DT)
            e.update(DT)
            steps += 1
        self.assertLess(e.state.grade_pct, -2.0)
        self.h.trainer.base_power = 0
        t0 = e.state.t_s
        self.h.run(until_finished=False, seconds=15)
        self.assertFalse(e.auto_pause)                     # a rolar na descida
        self.assertGreater(e.state.t_s, t0 + 14)
        self.assertGreater(e.state.speed_mps, 2.0)

    def test_two_loops_record_best_loop_and_lap_rows(self):
        self.h.run()                              # 1.ª volta
        self.h.run()                              # 2.ª volta
        self.assertEqual(self.h.engine.state.loops, 2)
        result = self.h.engine.finish()
        s = result["summary"]
        self.assertEqual(s.route_loops, 2)
        self.assertIsNotNone(s.best_loop_s)
        self.assertLess(s.best_loop_s, s.elapsed_s)
        triggers = [r["trigger"] for r in self.h.db.laps(self.h.engine.ride_id)]
        self.assertEqual(triggers.count("route_loop"), 2)
        # a classificação usa a melhor volta, não a sessão inteira
        board = self.h.db.route_leaderboard(self.h.route_id)
        self.assertEqual(board[0]["elapsed_s"], s.best_loop_s)
        row = self.h.db.conn.execute("SELECT route_loops FROM rides WHERE id = ?",
                                     (self.h.engine.ride_id,)).fetchone()
        self.assertEqual(row["route_loops"], 2)
        # as subidas contaram nas duas voltas
        climb_id = self.h.db.climbs(self.h.route_id)[0].id
        self.assertEqual(len(self.h.db.climb_leaderboard(climb_id)), 2)

    def test_speed_responds_to_gradient(self):
        """Na subida de 6 % tem de andar bem mais devagar do que no plano."""
        flat_speeds, climb_speeds = [], []
        steps = 0
        while steps < MAX_STEPS and not self.h.engine.route_finished:
            self.h.hub.tick(DT)
            self.h.engine.update(DT)
            self.h.engine.drain_events()
            d = self.h.engine.state.dist_m
            if 300 < d < 900:
                flat_speeds.append(self.h.engine.state.speed_mps)
            elif 2000 < d < 3500:
                climb_speeds.append(self.h.engine.state.speed_mps)
            steps += 1
        flat = sum(flat_speeds) / len(flat_speeds)
        climb = sum(climb_speeds) / len(climb_speeds)
        self.assertGreater(flat, climb * 2.0, f"plano {flat:.1f} vs subida {climb:.1f} m/s")

    def test_climb_is_signposted_timed_and_recorded(self):
        self.h.run()
        starts = self.h.of("section_start")
        signs = self.h.of("section_sign")
        finishes = self.h.of("section_finish")
        self.assertEqual(len(starts), 1)
        self.assertEqual(len(finishes), 1)
        self.assertGreaterEqual(len(signs), 4)          # placas a cada 500 m numa subida de 3 km
        # as placas contam para baixo
        lefts = [s.data["left_m"] for s in signs]
        self.assertEqual(lefts, sorted(lefts, reverse=True))

        fin = finishes[0].data
        self.assertGreater(fin["elapsed_s"], 60)
        self.assertIsNotNone(fin["avg_power_w"])
        self.assertIsNotNone(fin["avg_hr"])
        self.assertIsNotNone(fin["avg_cadence"])
        self.assertEqual(fin["rank"], 1)
        self.assertGreater(fin["vam_mh"], 100)

        climb_id = self.h.db.climbs(self.h.route_id)[0].id
        board = self.h.db.climb_leaderboard(climb_id)
        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["elapsed_s"], fin["elapsed_s"])

    def test_manual_lap_splits_and_records(self):
        self.h.run(seconds=120)
        lap = self.h.engine.lap("manual")
        self.assertEqual(lap.lap_no, 1)
        self.assertEqual(lap.trigger, "manual")
        self.assertGreater(lap.end_dist_m, 0)
        self.assertIsNotNone(lap.avg_power_w)
        self.assertEqual(self.h.engine.lap_no, 2)
        self.assertIn("lap", [e.kind for e in self.h.engine.drain_events()])
        self.assertEqual(len(self.h.db.laps(self.h.engine.ride_id)), 1)

    def test_climb_end_creates_its_own_lap(self):
        self.h.run()
        triggers = [r["trigger"] for r in self.h.db.laps(self.h.engine.ride_id)]
        self.assertIn("climb", triggers)

    def test_trainer_receives_scaled_gradient(self):
        self.h.run(seconds=400)
        sims = [v for name, v in self.h.trainer.commands if name == "set_sim"]
        self.assertTrue(sims)
        self.assertTrue(self.h.trainer.controlled)
        # a meio da subida o declive pedido anda pelos 6 %
        self.assertGreater(max(sims), 5.0)
        self.assertLessEqual(max(sims), 7.0)

    def test_samples_are_persisted_at_1hz(self):
        self.h.run(seconds=60)
        self.h.engine.flush()
        samples = self.h.db.samples(self.h.engine.ride_id)
        self.assertGreaterEqual(len(samples), 55)
        self.assertLessEqual(len(samples), 62)
        self.assertTrue(all(s.power_w is not None for s in samples))
        self.assertTrue(all(s.hr_bpm is not None for s in samples))
        # distância estritamente crescente
        dists = [s.dist_m for s in samples]
        self.assertEqual(dists, sorted(dists))

    def test_finish_writes_valid_fit_and_summary(self):
        self.h.run()
        result = self.h.engine.finish()
        self.assertIsNotNone(result["fit_path"])
        info = fit.verify(result["fit_path"])
        self.assertGreater(info["messages"][fit.MSG_RECORD], 500)
        self.assertGreaterEqual(info["messages"][fit.MSG_LAP], 2)

        s = result["summary"]
        # passa o fim da rota no máximo um passo de simulação (0,25 s a descer)
        self.assertAlmostEqual(s.distance_m, self.h.points[-1].dist_m, delta=4.0)
        self.assertAlmostEqual(s.ascent_m, 180.0, delta=12.0)
        self.assertTrue(s.completed_route)
        self.assertGreater(s.avg_power_w, 150)
        self.assertIsNotNone(s.np_w)
        self.assertIsNotNone(s.tss)
        self.assertGreater(s.work_kj, 50)
        self.assertTrue(s.power_curve)

        row = self.h.db.route(self.h.route_id)
        self.assertEqual(row["times_ridden"], 1)
        self.assertEqual(len(self.h.db.route_leaderboard(self.h.route_id)), 1)

    def test_pause_freezes_progress(self):
        self.h.run(seconds=30)
        d0 = self.h.engine.state.dist_m
        self.h.engine.pause()
        for _ in range(100):
            self.h.hub.tick(DT)
            self.h.engine.update(DT)
        self.assertAlmostEqual(self.h.engine.state.dist_m, d0, delta=0.01)
        self.h.engine.resume()
        self.h.run(seconds=30)
        self.assertGreater(self.h.engine.state.dist_m, d0)

    def test_challenges_accumulate_and_complete(self):
        ch = [c for c in self.h.db.challenges() if c["metric"] == "ascent_m"][0]
        # alvo baixo de propósito, para fechar dentro desta rota
        small = self.h.db.create_challenge("Subir 50 m", "ascent_m", 50.0)
        self.h.engine._attempts.append(
            (self.h.db.ensure_attempt(small)["id"], small, "ascent_m", 50.0))
        self.h.engine._challenge_names[small] = "Subir 50 m"
        self.h.run()
        done = [e.data["name"] for e in self.h.of("challenge_done")]
        self.assertIn("Subir 50 m", done)
        board = self.h.db.challenge_leaderboard(small)
        self.assertEqual(len(board), 1)
        # e o desafio grande ficou com progresso mas incompleto
        attempt = self.h.db.active_attempt(ch["id"])
        self.assertGreater(attempt["progress"], 100.0)
        self.assertIsNone(attempt["completed_at"])

    def test_abort_leaves_no_leaderboard_entry(self):
        self.h.run(seconds=60)
        self.h.engine.abort()
        self.assertEqual(self.h.db.route_leaderboard(self.h.route_id), [])
        row = self.h.db.conn.execute(
            "SELECT status FROM rides WHERE id = ?", (self.h.engine.ride_id,)).fetchone()
        self.assertEqual(row["status"], "aborted")


class TestErgIntensity(unittest.TestCase):
    def test_intensity_scales_the_erg_target(self):
        with tempfile.TemporaryDirectory() as d:
            wk = Workout("t", [Step("steady", 600, "pct_ftp", 100, 100)])
            h = RideHarness(Path(d), workout=wk, erg=True)
            h.run(until_finished=False, seconds=5)
            self.assertEqual(h.engine.state.target_power_w, 250)
            self.assertEqual(h.engine.adjust_resistance(-2), "erg")
            h.run(until_finished=False, seconds=2)
            self.assertEqual(h.engine.state.target_power_w, 225)
            self.assertEqual(h.trainer.last_target, 225)
            h.close()


class TestClockStartsWithPedalling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = RideHarness(Path(self.tmp.name), base_power=0)

    def tearDown(self):
        self.h.close()
        self.tmp.cleanup()

    def test_waits_for_the_first_pedal_stroke(self):
        e = self.h.engine
        self.h.run(until_finished=False, seconds=30)
        self.assertFalse(e.started)
        self.assertEqual(e.state.status, "waiting")
        self.assertEqual(e.state.t_s, 0.0)
        self.assertEqual(e.state.dist_m, 0.0)
        self.assertNotIn("auto_pause", self.h.kinds())
        # o trainer já recebeu o declive do início, antes de arrancar
        self.assertTrue(any(c[0] == "set_sim" for c in self.h.trainer.commands))
        self.h.trainer.base_power = 200
        self.h.run(until_finished=False, seconds=20)
        self.assertTrue(e.started)
        self.assertIn("ride_started", self.h.kinds())
        self.assertGreater(e.state.t_s, 15)
        self.assertLessEqual(e.state.t_s, 20)

    def test_finishing_without_pedalling_still_writes_a_fit(self):
        self.h.run(until_finished=False, seconds=10)
        result = self.h.engine.finish()
        self.assertEqual(result["summary"].elapsed_s, 0)
        self.assertIsNotNone(result["fit_path"])


class TestChaseMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _run_until(self, h, cond, seconds=3600):
        for _ in range(int(seconds / DT)):
            h.hub.tick(DT)
            h.engine.update(DT)
            h.events.extend(h.engine.drain_events())
            if cond():
                return True
        return False

    def test_peloton_ramps_up_and_catches_the_rider(self):
        h = RideHarness(Path(self.tmp.name), base_power=220, chase_level="hard",
                        with_route=False)
        e = h.engine
        self.assertTrue(self._run_until(h, lambda: e.chase_result is not None))
        res = e.chase_result
        self.assertTrue(res["caught"])
        self.assertTrue(res["clean"])
        self.assertEqual(res["rank"], 1)
        # 70 % de 250 W a subir 5 % por minuto: passa os 220 W ao fim de 3 min
        self.assertGreater(res["survived_s"], 180)
        self.assertGreater(res["final_chaser_w"], 220)
        kinds = h.kinds()
        self.assertGreaterEqual(kinds.count("chase_wave"), 3)
        self.assertEqual(kinds.count("chase_close"), 3)    # 100, 50 e 20 m
        self.assertIn("chase_caught", kinds)
        # gravado na classificação do nível, no plano
        board = h.db.chase_leaderboard("hard", None)
        self.assertEqual(len(board), 1)
        self.assertAlmostEqual(board[0]["survived_s"], res["survived_s"], delta=0.01)
        # depois de apanhado, a sessão continua até o atleta a terminar
        self.assertFalse(e.finished)
        h.run(until_finished=False, seconds=20)
        self.assertFalse(e.finished)
        result = e.finish()
        self.assertEqual(len(h.db.chase_leaderboard("hard", None)), 1)   # não duplica
        self.assertTrue(result["chase"]["caught"])
        h.close()

    def test_equal_power_keeps_the_gap(self):
        from velo.core.chase import Chase
        c = Chase("normal", 250, 80.0, 0.32, 0.004)
        rider_v, rider_m = 0.0, 0.0
        for _ in range(int(240 / 0.05)):
            watts = c.watts
            rider_v = physics.step_velocity(80.0, 0.32, 0.004, rider_v, watts, 0.0, 0.05)
            rider_m += rider_v * 0.05
            c.step(0.05, rider_m)
        self.assertAlmostEqual(c.gap_m(rider_m), 150.0, delta=1.0)
        self.assertFalse(c.caught)

    def test_no_auto_pause_during_the_chase(self):
        h = RideHarness(Path(self.tmp.name), base_power=220, chase_level="normal",
                        with_route=False)
        e = h.engine
        h.run(until_finished=False, seconds=20)
        h.trainer.base_power = 0                           # parar não esconde ninguém
        self.assertTrue(self._run_until(h, lambda: e.chase.caught, seconds=600))
        self.assertNotIn("auto_pause", h.kinds())
        self.assertLess(e.chase.t_s, 120)
        # depois de apanhado, a pausa automática volta
        self.assertTrue(self._run_until(h, lambda: e.auto_pause, seconds=30))
        h.close()

    def test_manual_pause_takes_the_attempt_out_of_the_ranking(self):
        h = RideHarness(Path(self.tmp.name), base_power=220, chase_level="hard",
                        with_route=False)
        e = h.engine
        h.run(until_finished=False, seconds=30)
        e.pause()
        h.events.extend(e.drain_events())
        self.assertIn("chase_unranked", h.kinds())
        e.resume()
        self.assertTrue(self._run_until(h, lambda: e.chase_result is not None))
        self.assertFalse(e.chase_result["clean"])
        self.assertEqual(h.db.chase_leaderboard("hard", None), [])
        h.close()

    def test_stopping_before_being_caught_saves_the_time(self):
        h = RideHarness(Path(self.tmp.name), base_power=220, chase_level="easy")
        e = h.engine
        h.run(until_finished=False, seconds=90)
        result = e.finish()
        res = result["chase"]
        self.assertFalse(res["caught"])
        self.assertAlmostEqual(res["survived_s"], 90, delta=2)
        board = h.db.chase_leaderboard("easy", h.route_id)
        self.assertEqual(len(board), 1)
        self.assertEqual(h.db.chase_leaderboard("easy", None), [])   # outra rota
        h.close()

    def test_live_board_ranks_the_rider_against_past_escapes(self):
        h = RideHarness(Path(self.tmp.name), base_power=220, chase_level="normal",
                        with_route=False)
        for secs in (60.0, 600.0):           # duas fugas antigas, de outras sessões
            old = h.db.begin_ride(route_id=None, workout_id=None, kind="chase",
                                  mode="alone", erg=False, athlete=h.athlete,
                                  difficulty=1.0, extra=0.0, preset="low")
            h.db.save_chase_effort(old, None, "normal", secs, 1000.0, 200.0, 250,
                                   True, True)
        e = h.engine
        h.run(until_finished=False, seconds=5)
        board = e.live_board()
        self.assertEqual(board.title, "Fuga")
        me = [r for r in board.rows if r.me]
        self.assertEqual(len(me), 1)
        self.assertEqual(me[0].rank, 3)
        h.run(until_finished=False, seconds=70)
        e.boards._cache.clear()
        self.assertEqual(e.live_board().my_rank, 2)
        h.close()


class TestGradientFeel(unittest.TestCase):
    """A sensação de declive escala a resistência mas não a velocidade (req. 23, 24)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_difficulty_halves_the_requested_gradient(self):
        h = RideHarness(Path(self.tmp.name) / "a", difficulty=0.5)
        h.run(seconds=400)
        sims = [v for name, v in h.trainer.commands if name == "set_sim"]
        self.assertLessEqual(max(sims), 3.5)     # 6 % reais → ~3 % pedidos
        self.assertGreater(max(sims), 2.0)
        h.close()

    def test_extra_resistance_adds_a_floor(self):
        h = RideHarness(Path(self.tmp.name) / "b", extra=3.0)
        h.run(seconds=60)                        # ainda no plano
        sims = [v for name, v in h.trainer.commands if name == "set_sim"]
        self.assertTrue(all(v >= 2.5 for v in sims), f"obtive {sims[:5]}")
        h.close()

    def test_world_speed_uses_the_real_gradient_not_the_scaled_one(self):
        """Com a MESMA potência entregue, a dificuldade não altera a velocidade.

        A dificuldade só muda o que o trainer pede aos músculos; a velocidade
        no mundo continua a sair do declive real da estrada. Para isolar isto
        de um ciclista que reage à resistência, injeta-se potência constante.
        """
        from velo.core.ride import Reading
        from velo.io.sim import ScriptedSource

        def distance_after(difficulty: float, tag: str) -> float:
            db = Database(Path(self.tmp.name) / f"{tag}.db")
            db.set("trainer_difficulty", difficulty)
            db.save_athlete(Athlete(weight_kg=72.0, ftp_w=250))
            _, raw = gpx.parse_gpx(GPX)
            pts = gpx.resample(raw)
            rid = db.insert_route("Serra", pts, climbs_mod.detect(pts))
            hub = SensorHub()
            # potência fixa de 220 W, com prioridade de medidor dedicado
            hub.add_source(ScriptedSource([Reading(power_w=220, cadence_rpm=85)]),
                           role="power_meter")
            trainer = SimulatedTrainer()
            hub.add_source(trainer, role="trainer", is_trainer=True)
            engine = RideEngine(db, db.athlete(), route_id=rid,
                                points=db.route_points(rid), climbs=db.climbs(rid),
                                sensors=hub, trainer=hub,
                                rides_dir=Path(self.tmp.name) / "rides")
            for _ in range(int(600 / DT)):
                hub.tick(DT)
                engine.update(DT)
            sims = [v for n, v in trainer.commands if n == "set_sim"]
            db.close()
            return engine.state.dist_m, max(sims)

        full_dist, full_grade = distance_after(1.0, "c")
        half_dist, half_grade = distance_after(0.5, "d")
        # mesma distância percorrida…
        self.assertAlmostEqual(full_dist, half_dist, delta=1.0)
        # …mas o trainer recebeu metade do declive
        self.assertAlmostEqual(half_grade, full_grade / 2.0, delta=0.4)


class TestComparisonMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_second_ride_races_the_first(self):
        root = Path(self.tmp.name)
        first = RideHarness(root, base_power=180)
        first.run()
        first_result = first.engine.finish()
        first_ride_id = first.engine.ride_id
        first_elapsed = first_result["summary"].elapsed_s
        db_path = first.db.path
        first.db.close()

        # Segunda sessão, mais forte, a comparar com a primeira.
        db = Database(db_path)
        athlete = db.athlete()
        route_id = db.routes()[0]["id"]
        ghosts = load_ghosts(db, [first_ride_id])
        self.assertEqual(len(ghosts), 1)
        self.assertGreater(ghosts[0].total_m, 5000.0)

        trainer = SimulatedTrainer(base_power=260)
        hub = SensorHub()
        hub.add_source(trainer, role="trainer", is_trainer=True)
        engine = RideEngine(db, athlete, route_id=route_id,
                            points=db.route_points(route_id), climbs=db.climbs(route_id),
                            ghosts=ghosts, sensors=hub, trainer=hub,
                            rides_dir=root / "rides")
        deltas = []
        steps = 0
        while steps < MAX_STEPS and not engine.route_finished:
            hub.tick(DT)
            engine.update(DT)
            for e in engine.drain_events():
                if e.kind == "ghost" and engine.state.loops == 0:
                    deltas.append(e.data["delta_s"])
            steps += 1
        result = engine.finish()

        self.assertTrue(deltas, "nenhuma diferença de fantasma emitida")
        # mais potência → chega mais cedo → diferença final negativa
        self.assertLess(deltas[-1], 0.0)
        self.assertLess(result["summary"].elapsed_s, first_elapsed)

        board = db.route_leaderboard(route_id)
        self.assertEqual(len(board), 2)
        self.assertEqual(board[0]["ride_id"], engine.ride_id)   # o mais rápido à frente

        rows = db.conn.execute(
            "SELECT * FROM ride_comparisons WHERE ride_id = ?", (engine.ride_id,)).fetchall()
        self.assertEqual(len(rows), 1)
        db.close()

    def test_alone_mode_has_no_ghosts(self):
        h = RideHarness(Path(self.tmp.name))
        h.run(seconds=60)
        self.assertEqual(h.of("ghost"), [])
        self.assertEqual(
            h.db.conn.execute("SELECT mode FROM rides WHERE id = ?",
                              (h.engine.ride_id,)).fetchone()["mode"], "alone")
        h.close()

    def test_ghost_interpolates_between_samples(self):
        from velo.core.db import Sample
        g = Ghost("x", "teste", [Sample(t_s=0, dist_m=0.0), Sample(t_s=10, dist_m=100.0)])
        self.assertAlmostEqual(g.time_at(50.0), 5.0)
        self.assertAlmostEqual(g.dist_at(5.0), 50.0)
        self.assertIsNone(g.time_at(200.0))      # além do fim do esforço


class TestWorkoutAndErg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workout = Workout("Intervalos", [
            Step("steady", 60, "pct_ftp", 50, 50, text_cue="Aquecimento"),
            Step("steady", 120, "pct_ftp", 110, 110, text_cue="Bloco 1"),
            Step("steady", 60, "pct_ftp", 50, 50, text_cue="Recuperação"),
            Step("ramp", 120, "pct_ftp", 70, 110, text_cue="Rampa"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_erg_on_sends_target_power(self):
        h = RideHarness(Path(self.tmp.name) / "erg", workout=self.workout, erg=True)
        h.run(seconds=200)
        targets = [v for name, v in h.trainer.commands if name == "set_target_power"]
        self.assertTrue(targets)
        self.assertIn(125.0, targets)        # 50 % de 250
        self.assertIn(275.0, targets)        # 110 % de 250
        # em ERG não se mandam declives depois do arranque
        self.assertLessEqual(len([v for n, v in h.trainer.commands if n == "set_sim"]), 1)
        h.close()

    def test_erg_off_shows_target_but_sends_gradient(self):
        h = RideHarness(Path(self.tmp.name) / "noerg", workout=self.workout, erg=False)
        h.run(seconds=200)
        self.assertEqual([v for n, v in h.trainer.commands if n == "set_target_power"], [])
        self.assertTrue([v for n, v in h.trainer.commands if n == "set_sim"])
        self.assertIsNotNone(h.engine.state.target_power_w)   # mostrado, não imposto
        h.close()

    def test_step_changes_are_announced(self):
        h = RideHarness(Path(self.tmp.name) / "steps", workout=self.workout, erg=True)
        h.run(seconds=300)
        cues = [e.data["cue"] for e in h.of("workout_step")]
        self.assertIn("Aquecimento", cues)
        self.assertIn("Bloco 1", cues)
        self.assertIn("Recuperação", cues)
        h.close()

    def test_compliance_is_scored_per_step(self):
        h = RideHarness(Path(self.tmp.name) / "score", workout=self.workout, erg=True)
        h.run(seconds=300)
        h.engine.finish()
        rows = h.db.conn.execute(
            "SELECT * FROM workout_step_results WHERE ride_id = ? ORDER BY step_idx",
            (h.engine.ride_id,)).fetchall()
        self.assertGreaterEqual(len(rows), 3)
        # o simulado segue o alvo, logo cumpre a maior parte do tempo
        self.assertGreater(rows[1]["pct_in_target"], 50.0)
        h.close()

    def test_ramp_target_interpolates(self):
        runner = WorkoutRunner(self.workout, 250, True)
        self.assertEqual(runner.target_watts(0), 125)        # 50 %
        self.assertEqual(runner.target_watts(70), 275)       # 110 %
        start_ramp = 60 + 120 + 60
        self.assertEqual(runner.target_watts(start_ramp), 175)             # 70 %
        self.assertEqual(runner.target_watts(start_ramp + 60), 225)        # 90 %
        self.assertIsNone(runner.target_watts(10_000))       # acabou

    def test_compliance_window(self):
        runner = WorkoutRunner(self.workout, 250, True)
        self.assertEqual(runner.compliance(200, 200), 0)
        self.assertEqual(runner.compliance(205, 200), 0)     # dentro de ±5 %
        self.assertEqual(runner.compliance(180, 200), -1)
        self.assertEqual(runner.compliance(230, 200), 1)


class TestFtpMode(unittest.TestCase):
    def test_protocols_build_sensible_workouts(self):
        for proto in ftp.PROTOCOLS:
            w = ftp.build(proto, 250)
            self.assertGreater(w.total_seconds, 600)
            self.assertTrue(w.steps)

    def test_20min_estimate(self):
        series = [150.0] * 600 + [280.0] * 1200 + [120.0] * 300
        raw, est = ftp.estimate("20min", series)
        self.assertAlmostEqual(raw, 280.0, delta=1.0)
        self.assertEqual(est, 266)                 # 95 %

    def test_ramp_estimate(self):
        series = [100.0 + i * 0.3 for i in range(1200)]
        raw, est = ftp.estimate("ramp", series)
        self.assertAlmostEqual(est, raw * 0.75, delta=1.0)

    def test_8x8_estimate(self):
        series = [140.0] * 300 + [300.0] * 480 + [140.0] * 300 + [290.0] * 480
        raw, est = ftp.estimate("8x8", series)
        self.assertAlmostEqual(raw, 300.0, delta=2.0)
        self.assertEqual(est, round(raw * 0.90))

    def test_short_series_returns_none(self):
        self.assertIsNone(ftp.estimate("20min", [200.0] * 100))

    def test_zones_cover_the_range(self):
        zones = ftp.zones_from_ftp(250, [55, 75, 90, 105, 120, 150])
        self.assertEqual(len(zones), 7)
        self.assertEqual(zones[0][1], 138)         # 55 % de 250 = 137,5

    def test_ftp_test_ride_updates_athlete(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "v.db")
            db.save_athlete(Athlete(ftp_w=200))
            db.save_ftp_test("20min", 280.0, 266, None, accepted=True)
            self.assertEqual(db.athlete().ftp_w, 266)
            db.close()


class TestSensorHub(unittest.TestCase):
    """Vários sensores ao mesmo tempo, com prioridades (req. 27)."""

    def test_power_meter_beats_trainer_but_cadence_can_differ(self):
        from velo.core.ride import Reading
        hub = SensorHub()
        trainer = SimulatedTrainer(base_power=200, with_hr=True)
        hub.add_source(trainer, role="trainer", is_trainer=True)
        hub.tick(1.0)
        hub.push("ble:pedals", "power", 333, priority=20)
        hub.push("ble:strap", "hr", 142, priority=20)
        r = hub.reading()
        self.assertEqual(r.power_w, 333)            # pedais ganham
        self.assertEqual(r.hr_bpm, 142)             # cinta ganha ao trainer
        self.assertIsNotNone(r.cadence_rpm)         # cadência ainda vem do trainer

    def test_stale_values_are_dropped(self):
        now = [1000.0]
        hub = SensorHub(stale_after_s=3.0, clock=lambda: now[0])
        hub.push("ble:strap", "hr", 150, priority=20)
        self.assertEqual(hub.reading().hr_bpm, 150)
        now[0] += 10.0
        self.assertIsNone(hub.reading().hr_bpm)

    def test_lost_sensors_are_reported(self):
        now = [0.0]
        hub = SensorHub(stale_after_s=2.0, clock=lambda: now[0])
        hub.names["ble:strap"] = "Cinta"
        hub.push("ble:strap", "hr", 150)
        now[0] += 5.0
        hub.tick(0.1)
        self.assertIn("Cinta", hub.drain_lost())
        self.assertEqual(hub.drain_lost(), [])      # só avisa uma vez

    def test_source_of_names_the_provider(self):
        hub = SensorHub()
        hub.names["ble:pedals"] = "Assioma"
        hub.push("ble:pedals", "power", 250, priority=20)
        self.assertEqual(hub.source_of("power"), "Assioma")

    def test_trainer_passthrough(self):
        trainer = SimulatedTrainer()
        hub = SensorHub()
        hub.add_source(trainer, role="trainer", is_trainer=True)
        self.assertTrue(hub.can_control)
        hub.set_sim(5.0)
        hub.set_target_power(220)
        hub.start_spindown()
        names = [n for n, _ in trainer.commands]
        self.assertIn("set_sim", names)
        self.assertIn("set_target_power", names)
        self.assertIn("start_spindown", names)

    def test_works_with_no_trainer_at_all(self):
        hub = SensorHub()
        hub.push("ble:strap", "hr", 150)
        self.assertFalse(hub.can_control)
        hub.set_sim(5.0)                            # não pode rebentar
        self.assertEqual(hub.reading().hr_bpm, 150)


class TestRideWithoutHardware(unittest.TestCase):
    """Uma sessão sem qualquer sensor não deve rebentar — só não avança."""

    def test_no_sensors(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "v.db")
            _, raw = gpx.parse_gpx(GPX)
            pts = gpx.resample(raw)
            rid = db.insert_route("Serra", pts, climbs_mod.detect(pts))
            hub = SensorHub()
            engine = RideEngine(db, db.athlete(), route_id=rid,
                                points=db.route_points(rid), climbs=db.climbs(rid),
                                sensors=hub, trainer=hub, rides_dir=Path(d) / "rides")
            for _ in range(200):
                hub.tick(DT)
                engine.update(DT)
            self.assertAlmostEqual(engine.state.dist_m, 0.0, delta=0.5)
            result = engine.finish()
            self.assertIsNotNone(result["fit_path"])
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
