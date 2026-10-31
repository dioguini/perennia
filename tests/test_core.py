"""Testes do núcleo. Correm sem hardware e sem dependências externas:

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from velo.core import climbs as climbs_mod
from velo.core import fit, gpx, metrics, physics, units
from velo.core.db import Athlete, Database, Lap, RideSummary, RoutePoint, Sample
from velo.core.i18n import EN, PT, missing_keys, set_language, t
from velo.core.route_index import RouteIndex

GPX = Path(__file__).parent / "teste.gpx"


class TestGpx(unittest.TestCase):
    def test_parse_and_resample(self):
        name, raw = gpx.parse_gpx(GPX)
        self.assertEqual(name, "Serra de Teste")
        self.assertEqual(len(raw), 600)

        pts = gpx.resample(raw)
        # 6 km a passo de 5 m
        self.assertAlmostEqual(pts[-1].dist_m, 6000.0, delta=15.0)
        self.assertAlmostEqual(pts[1].dist_m - pts[0].dist_m, 5.0, places=6)
        # Primeiro km plano
        self.assertAlmostEqual(pts[100].grade_pct, 0.0, delta=0.3)
        # A subida de 6 % reconhecida a meio
        self.assertAlmostEqual(pts[500].grade_pct, 6.0, delta=0.4)
        # A descida de 4 %
        self.assertAlmostEqual(pts[1000].grade_pct, -4.0, delta=0.4)
        # Elevação: 50 + 180 - 80
        self.assertAlmostEqual(pts[-1].ele_m, 150.0, delta=3.0)

    def test_rejects_garbage(self):
        with tempfile.NamedTemporaryFile("w", suffix=".gpx", delete=False) as f:
            f.write("isto não é xml")
            bad = f.name
        with self.assertRaises(gpx.GpxError):
            gpx.parse_gpx(bad)

    def test_rejects_too_few_points(self):
        with tempfile.NamedTemporaryFile("w", suffix=".gpx", delete=False) as f:
            f.write('<?xml version="1.0"?><gpx><trk><trkseg>'
                    '<trkpt lat="1" lon="1"><ele>0</ele></trkpt>'
                    '</trkseg></trk></gpx>')
            bad = f.name
        with self.assertRaises(gpx.GpxError):
            gpx.parse_gpx(bad)


class TestClimbs(unittest.TestCase):
    def setUp(self):
        _, raw = gpx.parse_gpx(GPX)
        self.pts = gpx.resample(raw)

    def test_detects_the_single_climb(self):
        found = climbs_mod.detect(self.pts)
        self.assertEqual(len(found), 1, f"esperava 1 subida, obtive {len(found)}")
        c = found[0]
        self.assertAlmostEqual(c.start_m, 1000.0, delta=60.0)
        self.assertAlmostEqual(c.end_m, 4000.0, delta=60.0)
        self.assertAlmostEqual(c.avg_grade_pct, 6.0, delta=0.4)
        self.assertAlmostEqual(c.gain_m, 180.0, delta=10.0)
        self.assertIn(c.category, ("1", "2", "3"))

    def test_flat_route_has_no_climbs(self):
        flat = [p for p in self.pts[:200]]
        self.assertEqual(climbs_mod.detect(flat), [])

    def test_sign_marks_count_down_from_the_top(self):
        c = climbs_mod.detect(self.pts)[0]
        marks = climbs_mod.signs_for(c, every_m=500.0)
        self.assertTrue(marks)
        self.assertTrue(all(c.start_m < m < c.end_m for m in marks))
        # a placa mais alta está a 500 m do topo
        self.assertAlmostEqual(c.end_m - marks[-1], 500.0, delta=1.0)

    def test_category_thresholds(self):
        self.assertEqual(climbs_mod.categorize(10_000, 9.0), "HC")
        self.assertEqual(climbs_mod.categorize(2_000, 5.0), "4")


class TestPhysics(unittest.TestCase):
    def test_200w_on_the_flat(self):
        v = 0.0
        for _ in range(4000):
            v = physics.step_velocity(83.0, 0.32, 0.004, v, 200.0, 0.0, 0.05)
        self.assertAlmostEqual(v * 3.6, 34.0, delta=2.5)

    def test_climbing_is_slower(self):
        flat = physics.speed_from_power(83.0, 0.32, 0.004, 250.0, 0.0)
        steep = physics.speed_from_power(83.0, 0.32, 0.004, 250.0, 0.08)
        self.assertGreater(flat, steep * 2.5)

    def test_equilibrium_matches_integration(self):
        target = physics.speed_from_power(83.0, 0.32, 0.004, 200.0, 0.03)
        v = 0.0
        for _ in range(6000):
            v = physics.step_velocity(83.0, 0.32, 0.004, v, 200.0, 0.03, 0.05)
        self.assertAlmostEqual(v, target, delta=0.2)

    def test_trainer_grade_scaling_and_clamping(self):
        self.assertAlmostEqual(physics.trainer_grade(8.0, 0.5, 0.0), 4.0)
        self.assertAlmostEqual(physics.trainer_grade(0.0, 1.0, 3.0), 3.0)
        self.assertAlmostEqual(physics.trainer_grade(-20.0, 1.0, 0.0), -5.0)
        self.assertAlmostEqual(physics.trainer_grade(40.0, 1.5, 0.0), 25.0)

    def test_torque(self):
        self.assertAlmostEqual(physics.torque_nm(200, 90), 21.22, delta=0.05)
        self.assertIsNone(physics.torque_nm(200, 0))
        self.assertIsNone(physics.torque_nm(None, 90))

    def test_normalized_power_of_constant_effort(self):
        self.assertAlmostEqual(physics.normalized_power([200.0] * 600), 200.0, delta=0.5)
        self.assertIsNone(physics.normalized_power([200.0] * 10))

    def test_np_exceeds_average_when_variable(self):
        series = ([100.0] * 30 + [300.0] * 30) * 20
        np_w = physics.normalized_power(series)
        self.assertGreater(np_w, 200.0)

    def test_power_curve_is_monotonic(self):
        series = [float(100 + (i % 50)) for i in range(1200)]
        curve = dict(physics.power_curve(series))
        self.assertGreaterEqual(curve[1], curve[60])
        self.assertGreaterEqual(curve[60], curve[600])
        self.assertNotIn(3600, curve)

    def test_tss_of_one_hour_at_ftp_is_100(self):
        tss = physics.training_stress_score(250.0, 250, 3600)
        self.assertAlmostEqual(tss, 100.0, delta=0.5)

    def test_zones(self):
        bounds = [55, 75, 90, 105, 120, 150]
        self.assertEqual(physics.zone_of(100, bounds, 250), 1)   # 40 %
        self.assertEqual(physics.zone_of(250, bounds, 250), 4)   # 100 %
        self.assertEqual(physics.zone_of(500, bounds, 250), 7)   # 200 %


class TestRouteIndex(unittest.TestCase):
    def setUp(self):
        _, raw = gpx.parse_gpx(GPX)
        self.idx = RouteIndex(gpx.resample(raw))

    def test_avg_grade_ahead(self):
        # a partir de 1,5 km, o próximo 1 km é todo a 6 %
        self.assertAlmostEqual(self.idx.avg_grade_ahead(1500.0, 1000.0), 6.0, delta=0.3)
        # o primeiro meio km é plano
        self.assertAlmostEqual(self.idx.avg_grade_ahead(0.0, 500.0), 0.0, delta=0.3)

    def test_none_when_route_ends_first(self):
        self.assertIsNone(self.idx.avg_grade_ahead(5500.0, 1000.0))
        self.assertIsNone(self.idx.avg_grade_ahead(0.0, 10_000.0))

    def test_point_interpolation(self):
        p = self.idx.point_at(2502.5)
        self.assertAlmostEqual(p.dist_m, 2502.5)
        self.assertTrue(self.idx.ele_at(2500.0) < p.ele_m < self.idx.ele_at(2505.0))

    def test_clamps_outside_the_route(self):
        self.assertAlmostEqual(self.idx.ele_at(-100.0), self.idx.points[0].ele_m)
        self.assertAlmostEqual(self.idx.ele_at(99_999.0), self.idx.points[-1].ele_m)

    def test_ascent_between(self):
        self.assertAlmostEqual(self.idx.ascent_between(1000.0, 4000.0), 180.0, delta=8.0)

    def test_profile_is_normalized(self):
        pts, lo, hi = self.idx.profile_normalized(1000.0, 2000.0, 32)
        self.assertEqual(len(pts), 32)
        self.assertTrue(all(0.0 <= y <= 1.0 for _, y in pts))
        self.assertLess(lo, hi)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "perennia.db")
        _, raw = gpx.parse_gpx(GPX)
        self.pts = gpx.resample(raw)
        self.climbs = climbs_mod.detect(self.pts)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_defaults_are_seeded(self):
        self.assertEqual(self.db.get("units"), "metric")
        self.assertEqual(self.db.get("language"), "pt_PT")
        self.assertEqual(len(self.db.challenges()), 4)
        self.assertEqual(self.db.athlete().ftp_w, 200)

    def test_settings_roundtrip(self):
        self.db.set("trainer_difficulty", 0.75)
        self.assertEqual(self.db.get("trainer_difficulty"), 0.75)
        self.db.set("hud_metrics", ["power", "hr"])
        self.assertEqual(self.db.get("hud_metrics"), ["power", "hr"])

    def test_athlete_roundtrip(self):
        a = Athlete(name="Daniel", birth_year=1993, weight_kg=72.5, ftp_w=265, lthr=168)
        self.db.save_athlete(a)
        b = self.db.athlete()
        self.assertEqual(b.name, "Daniel")
        self.assertEqual(b.ftp_w, 265)
        self.assertEqual(b.age, time.localtime().tm_year - 1993)

    def test_route_roundtrip(self):
        rid = self.db.insert_route("Serra", self.pts, self.climbs, "teste.gpx")
        row = self.db.route(rid)
        self.assertAlmostEqual(row["distance_m"], 6000.0, delta=15.0)
        self.assertAlmostEqual(row["ascent_m"], 180.0, delta=8.0)
        self.assertEqual(row["point_count"], len(self.pts))
        back = self.db.route_points(rid)
        self.assertEqual(len(back), len(self.pts))
        self.assertAlmostEqual(back[500].grade_pct, self.pts[500].grade_pct, places=5)
        self.assertEqual(len(self.db.climbs(rid)), 1)

    def test_duplicate_uploads_are_separate_routes(self):
        a = self.db.insert_route("Serra", self.pts, self.climbs)
        b = self.db.insert_route("Serra", self.pts, self.climbs)
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.db.routes()), 2)

    def test_delete_cascades(self):
        rid = self.db.insert_route("Serra", self.pts, self.climbs)
        self.db.delete_route(rid)
        self.assertEqual(self.db.route_points(rid), [])
        self.assertEqual(self.db.climbs(rid), [])

    def test_ride_lifecycle_and_leaderboard(self):
        rid = self.db.insert_route("Serra", self.pts, self.climbs)
        athlete = self.db.athlete()
        ride = self.db.begin_ride(route_id=rid, workout_id=None, kind="route", mode="alone",
                                  erg=False, athlete=athlete, difficulty=1.0, extra=0.0,
                                  preset="low")
        samples = [Sample(t_s=i, dist_m=i * 8.0, speed_mps=8.0, power_w=200,
                          cadence_rpm=85, hr_bpm=140) for i in range(60)]
        self.db.append_samples(ride, samples)
        self.assertEqual(len(self.db.samples(ride)), 60)

        self.db.save_lap(ride, Lap(lap_no=1, trigger="manual", start_t_s=0, end_t_s=30,
                                   start_dist_m=0.0, end_dist_m=240.0, avg_power_w=200.0))
        self.assertEqual(len(self.db.laps(ride)), 1)

        s = RideSummary(elapsed_s=60, moving_s=60, distance_m=480.0, ascent_m=10.0,
                        avg_power_w=200.0, completed_route=True, avg_speed_mps=8.0,
                        power_curve=[(1, 210.0), (60, 200.0)])
        self.db.finish_ride(ride, s, "rides/x.fit")
        self.assertEqual(self.db.route(rid)["times_ridden"], 1)
        board = self.db.route_leaderboard(rid)
        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["elapsed_s"], 60)

    def test_incomplete_ride_stays_off_the_leaderboard(self):
        rid = self.db.insert_route("Serra", self.pts, self.climbs)
        ride = self.db.begin_ride(route_id=rid, workout_id=None, kind="route", mode="alone",
                                  erg=False, athlete=self.db.athlete(), difficulty=1.0,
                                  extra=0.0, preset="low")
        self.db.finish_ride(ride, RideSummary(elapsed_s=30, completed_route=False), None)
        self.assertEqual(self.db.route_leaderboard(rid), [])

    def test_climb_leaderboard_ranks_and_flags_pr(self):
        rid = self.db.insert_route("Serra", self.pts, self.climbs)
        climb_id = self.db.climbs(rid)[0].id
        a = self.db.athlete()
        r1 = self.db.begin_ride(route_id=rid, workout_id=None, kind="route", mode="alone",
                                erg=False, athlete=a, difficulty=1.0, extra=0.0, preset="low")
        rank, total, pr = self.db.save_climb_effort(climb_id, r1, 0, 900, 240.0, 155.0,
                                                    80.0, 180.0)
        self.assertEqual((rank, total, pr), (1, 1, False))  # primeiro esforço não é "recorde"

        r2 = self.db.begin_ride(route_id=rid, workout_id=None, kind="route", mode="alone",
                                erg=False, athlete=a, difficulty=1.0, extra=0.0, preset="low")
        rank, total, pr = self.db.save_climb_effort(climb_id, r2, 0, 840, 260.0, 158.0,
                                                    82.0, 180.0)
        self.assertEqual((rank, total, pr), (1, 2, True))   # bateu o anterior

        r3 = self.db.begin_ride(route_id=rid, workout_id=None, kind="route", mode="alone",
                                erg=False, athlete=a, difficulty=1.0, extra=0.0, preset="low")
        rank, total, pr = self.db.save_climb_effort(climb_id, r3, 0, 1000, 220.0, 150.0,
                                                    78.0, 180.0)
        self.assertEqual((rank, total, pr), (3, 3, False))
        board = self.db.climb_leaderboard(climb_id)
        self.assertEqual([r["elapsed_s"] for r in board], [840, 900, 1000])

    def test_challenges_progress_reset_and_leaderboard(self):
        ch = self.db.challenges()[0]          # Pedalar 500 km
        attempt = self.db.ensure_attempt(ch["id"])
        self.assertFalse(self.db.bump_attempt(attempt["id"], 100_000.0, ch["target"], None))
        self.assertFalse(self.db.bump_attempt(attempt["id"], 399_000.0, ch["target"], None))
        self.assertTrue(self.db.bump_attempt(attempt["id"], 2_000.0, ch["target"], None))
        board = self.db.challenge_leaderboard(ch["id"])
        self.assertEqual(len(board), 1)
        self.assertIsNotNone(board[0]["elapsed_s"])
        # reiniciar abre nova tentativa a zero
        new_id = self.db.reset_attempt(ch["id"])
        fresh = self.db.active_attempt(ch["id"])
        self.assertEqual(fresh["id"], new_id)
        self.assertEqual(fresh["progress"], 0.0)

    def test_custom_challenge(self):
        cid = self.db.create_challenge("Subir o Everest", "ascent_m", 8848.0)
        self.assertTrue(any(c["id"] == cid for c in self.db.challenges()))
        self.db.delete_challenge(cid)
        self.assertFalse(any(c["id"] == cid for c in self.db.challenges()))

    def test_default_challenge_cannot_be_deleted(self):
        ch = self.db.challenges()[0]
        self.db.delete_challenge(ch["id"])
        self.assertTrue(any(c["id"] == ch["id"] for c in self.db.challenges()))

    def test_workout_roundtrip(self):
        steps = [
            {"kind": "steady", "duration_s": 600, "target_type": "pct_ftp",
             "target_lo": 55, "target_hi": 55},
            {"kind": "steady", "duration_s": 300, "target_type": "pct_ftp",
             "target_lo": 105, "target_hi": 105},
        ]
        wid = self.db.insert_workout("Teste", steps, "zwo")
        self.assertEqual(len(self.db.workout_steps(wid)), 2)
        self.assertEqual(self.db.workouts()[0]["total_seconds"], 900)

    def test_ftp_test_updates_athlete(self):
        self.db.save_ftp_test("20min", 280.0, 266, None, accepted=True)
        self.assertEqual(self.db.athlete().ftp_w, 266)
        self.db.save_ftp_test("ramp", 300.0, 225, None, accepted=False)
        self.assertEqual(self.db.athlete().ftp_w, 266)
        self.assertEqual(len(self.db.ftp_history()), 1)

    def test_device_memory_and_calibration(self):
        self.db.remember_device("ble:aa", "ble", "KICKR", ["ftms", "cps"], 0b1010011)
        self.assertEqual(len(self.db.known_devices()), 1)
        self.db.save_calibration("ble:aa", "spindown_ftms", True, "12.4 s")
        self.assertEqual(self.db.last_calibration("ble:aa")["success"], 1)

    def test_portability_reopen(self):
        rid = self.db.insert_route("Serra", self.pts, self.climbs)
        path = self.db.path
        self.db.close()
        again = Database(path)
        self.assertEqual(len(again.route_points(rid)), len(self.pts))
        again.close()
        self.db = Database(path)   # para o tearDown


class TestMetrics(unittest.TestCase):
    def _state(self, **over):
        _, raw = gpx.parse_gpx(GPX)
        base = dict(
            t_s=600, dist_m=1500.0, pos_m=1500.0, loops=0, speed_mps=6.5, grade_pct=6.0,
            power_w=240, power_3s=235, avg_power=230.0, np_w=238.0,
            balance_left=51.0, cadence_rpm=84, avg_cadence=82.0,
            hr_bpm=158, avg_hr=152.0, avg_speed=6.2, ascent_m=90.0,
            joules=140_000.0, tss=45.0, ftp_w=250, lthr=165,
            power_zone_bounds=[55, 75, 90, 105, 120, 150],
            hr_zone_bounds=[68, 83, 94, 105],
            target_power_w=None, route=RouteIndex(gpx.resample(raw)),
        )
        base.update(over)
        return SimpleNamespace(**base)

    def test_registry_covers_every_required_metric(self):
        required = {
            "dist_done", "dist_left", "avg_grade_500m", "avg_grade_1km", "avg_grade_3km",
            "avg_grade_5km", "avg_grade_10km", "hr", "power", "power_balance",
            "power_zone", "hr_zone", "torque", "cadence", "tss_accum", "avg_cadence",
            "avg_hr", "speed", "avg_speed",
        }
        self.assertTrue(required.issubset(set(metrics.REGISTRY)),
                        f"faltam: {required - set(metrics.REGISTRY)}")

    def test_values(self):
        s = self._state()
        self.assertAlmostEqual(metrics.value("dist_done", s), 1500.0)
        self.assertAlmostEqual(metrics.value("dist_left", s), 4500.0, delta=20.0)
        self.assertAlmostEqual(metrics.value("avg_grade_1km", s), 6.0, delta=0.3)
        self.assertIsNone(metrics.value("avg_grade_10km", s))   # rota acaba antes
        self.assertEqual(metrics.value("power_zone", s), 4)     # 235/250 = 94 %
        self.assertEqual(metrics.value("hr_zone", s), 4)        # 158/165 = 96 %
        self.assertAlmostEqual(metrics.value("torque", s), 27.28, delta=0.1)
        self.assertAlmostEqual(metrics.value("work_kj", s), 140.0)

    def test_missing_sensors_give_none_not_crash(self):
        s = self._state(power_w=None, power_3s=None, cadence_rpm=None, hr_bpm=None)
        for mid in metrics.available():
            metrics.value(mid, s)   # nenhuma destas pode rebentar
        self.assertIsNone(metrics.value("power", s))
        self.assertIsNone(metrics.value("torque", s))
        self.assertIsNone(metrics.value("hr_zone", s))

    def test_formatting_respects_units(self):
        s = self._state()
        set_language(PT)
        label, text = metrics.formatted("speed", s, "metric")
        self.assertEqual(label, "Velocidade")
        self.assertIn("km/h", text)
        _, text_i = metrics.formatted("speed", s, "imperial")
        self.assertIn("mph", text_i)
        _, dist = metrics.formatted("dist_done", s, "imperial")
        self.assertIn("mi", dist)

    def test_unknown_metric_is_graceful(self):
        self.assertIsNone(metrics.value("nao_existe", self._state()))
        self.assertEqual(metrics.formatted("nao_existe", self._state())[1], "—")


class TestUnitsAndI18n(unittest.TestCase):
    def test_conversions(self):
        self.assertAlmostEqual(units.km(5000.0)[0], 5.0)
        self.assertAlmostEqual(units.km(5000.0, "imperial")[0], 3.107, places=3)
        self.assertAlmostEqual(units.speed(10.0)[0], 36.0)
        self.assertAlmostEqual(units.elevation(100.0, "imperial")[0], 328.084, places=2)
        self.assertAlmostEqual(units.weight(70.0, "imperial")[0], 154.32, places=1)

    def test_time_formatting(self):
        self.assertEqual(units.hms(59), "0:59")
        self.assertEqual(units.hms(615), "10:15")
        self.assertEqual(units.hms(3661), "1:01:01")
        self.assertEqual(units.delta(-12), "-0:12")
        self.assertEqual(units.delta(65), "+1:05")

    def test_none_renders_as_dash(self):
        self.assertEqual(units.format_metric(None, "W"), "—")

    def test_both_languages_have_the_same_keys(self):
        miss = missing_keys()
        self.assertEqual(miss["only_pt"], [], f"sem tradução EN: {miss['only_pt']}")
        self.assertEqual(miss["only_en"], [], f"sem tradução PT: {miss['only_en']}")

    def test_translation_and_fallback(self):
        set_language(PT)
        self.assertEqual(t("menu.ride"), "Pedalar")
        set_language(EN)
        self.assertEqual(t("menu.ride"), "Ride")
        self.assertEqual(t("chave.que.nao.existe"), "chave.que.nao.existe")
        self.assertEqual(t("toast.lap", n=3), "Lap 3")
        set_language(PT)


class TestFit(unittest.TestCase):
    def test_crc_known_value(self):
        self.assertEqual(fit.crc16(b""), 0)
        self.assertEqual(fit.crc16(b"\x00" * 10), 0)
        self.assertNotEqual(fit.crc16(b"123456789"), 0)

    def test_epoch_and_semicircles(self):
        self.assertEqual(fit.to_fit_time(fit.FIT_EPOCH), 0)
        self.assertEqual(fit.to_fit_time(fit.FIT_EPOCH + 100), 100)
        self.assertEqual(fit.to_semicircles(0.0), 0)
        self.assertEqual(fit.to_semicircles(180.0), 2 ** 31)

    def test_field_encodes_invalid_for_none(self):
        f = fit.Field("power", 7, "uint16")
        self.assertEqual(f.encode(None), b"\xff\xff")
        self.assertEqual(f.encode(250), b"\xfa\x00")

    def test_field_rejects_out_of_range(self):
        f = fit.Field("heart_rate", 3, "uint8")
        self.assertEqual(f.encode(400), b"\xff")      # fora de alcance → inválido
        self.assertEqual(f.encode(150), b"\x96")

    def test_altitude_scaling(self):
        f = fit.Field("altitude", 2, "uint16", scale=5, offset=500)
        self.assertEqual(f.encode(0.0), b"\xc4\x09")    # (0+500)*5   = 2500 = 0x09C4
        self.assertEqual(f.encode(100.0), b"\xb8\x0b")  # (100+500)*5 = 3000 = 0x0BB8
        self.assertEqual(f.encode(-600.0), b"\xff\xff")  # abaixo do alcance → inválido

    def test_write_and_verify_activity(self):
        _, raw = gpx.parse_gpx(GPX)
        idx = RouteIndex(gpx.resample(raw))
        athlete = Athlete(name="Teste", birth_year=1990, weight_kg=72.0, ftp_w=250)
        samples = [
            Sample(t_s=i, dist_m=i * 7.0, speed_mps=7.0, power_w=220 + (i % 11),
                   cadence_rpm=85, hr_bpm=150, balance_left=51.0,
                   grade_pct=idx.grade_at(i * 7.0), ele_m=idx.ele_at(i * 7.0), lap_no=1)
            for i in range(300)
        ]
        laps = [Lap(lap_no=1, trigger="manual", start_t_s=0, end_t_s=150,
                    start_dist_m=0.0, end_dist_m=1050.0, avg_power_w=225.0, max_power_w=240,
                    avg_hr=150.0, max_hr=160, avg_cadence=85.0, avg_speed_mps=7.0,
                    ascent_m=30.0),
                Lap(lap_no=2, trigger="end", start_t_s=150, end_t_s=299,
                    start_dist_m=1050.0, end_dist_m=2093.0, avg_power_w=225.0,
                    max_power_w=240, avg_hr=151.0, max_hr=162, avg_cadence=84.0,
                    avg_speed_mps=7.0, ascent_m=60.0)]
        power = [float(s.power_w) for s in samples]
        np_w = physics.normalized_power(power)
        summary = RideSummary(
            elapsed_s=300, moving_s=300, distance_m=2093.0, ascent_m=90.0,
            avg_power_w=sum(power) / len(power), max_power_w=max(int(p) for p in power),
            np_w=np_w, intensity_factor=np_w / 250.0,
            tss=physics.training_stress_score(np_w, 250, 300),
            work_kj=sum(power) / 1000.0, avg_hr=150.0, max_hr=162, avg_cadence=85.0,
            avg_speed_mps=7.0, avg_balance_left=51.0, completed_route=False,
        )
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "ride.fit"
            fit.write_activity(out, athlete, samples, laps, summary,
                               start_unix=time.time(), include_coords=True,
                               coord_at=lambda m: (idx.point_at(m).lat,
                                                   idx.point_at(m).lon,
                                                   idx.ele_at(m)))
            info = fit.verify(out)
            self.assertEqual(info["messages"][fit.MSG_RECORD], 300)
            self.assertEqual(info["messages"][fit.MSG_LAP], 2)
            self.assertEqual(info["messages"][fit.MSG_SESSION], 1)
            self.assertEqual(info["messages"][fit.MSG_ACTIVITY], 1)
            self.assertEqual(info["messages"][fit.MSG_EVENT], 2)
            self.assertEqual(info["messages"][fit.MSG_FILE_ID], 1)
            self.assertGreater(info["bytes"], 300 * 20)

    def test_verify_detects_corruption(self):
        athlete = Athlete(ftp_w=250)
        samples = [Sample(t_s=i, dist_m=i * 7.0, speed_mps=7.0, power_w=200)
                   for i in range(10)]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "ride.fit"
            fit.write_activity(out, athlete, samples, [], RideSummary(elapsed_s=10),
                               start_unix=time.time(), include_coords=False)
            data = bytearray(out.read_bytes())
            data[40] ^= 0xFF
            out.write_bytes(bytes(data))
            with self.assertRaises(ValueError):
                fit.verify(out)

    def test_works_without_coordinates(self):
        athlete = Athlete(ftp_w=250)
        samples = [Sample(t_s=i, dist_m=i * 7.0, speed_mps=7.0, power_w=200)
                   for i in range(10)]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "indoor.fit"
            fit.write_activity(out, athlete, samples, [], RideSummary(elapsed_s=10),
                               start_unix=time.time(), include_coords=False)
            self.assertEqual(fit.verify(out)["messages"][fit.MSG_RECORD], 10)


class TestNumberInput(unittest.TestCase):
    def test_both_decimal_styles(self):
        for text in ("5000.34", "5000,34", "5,000.34", "5.000,34", "5 000,34"):
            self.assertAlmostEqual(units.parse_number(text), 5000.34, places=6, msg=text)
        self.assertEqual(units.parse_number("23,5"), 23.5)
        self.assertEqual(units.parse_number("23.5"), 23.5)
        self.assertEqual(units.parse_number("1.000.000"), 1_000_000.0)

    def test_rejects_garbage(self):
        for text in ("", "   ", "abc", "5km", "-5", "1,2,3.4.5x"):
            self.assertIsNone(units.parse_number(text), text)


class TestChallengeText(unittest.TestCase):
    def test_targets_keep_the_unit_the_rider_typed(self):
        from velo.core import boards
        self.assertEqual(boards.challenge_target_text("distance_m", 5_000_340.0, "km"),
                         "5000.34 km")
        self.assertEqual(boards.challenge_target_text("ascent_m", 23_500.0, "km"),
                         "23.5 km")
        self.assertEqual(boards.challenge_target_text("ascent_m", 500.0, None), "500 m")
        self.assertEqual(boards.challenge_progress_text("ascent_m", 1234.0, 23_500.0, "km"),
                         "1.2 / 23.5 km")

    def test_long_durations_use_days(self):
        from velo.core import boards
        self.assertEqual(boards.long_duration(3600 * 5), "5:00:00")
        self.assertEqual(boards.long_duration(86400 * 12 + 3600 * 4), "12 d 4 h")

    def test_database_keeps_the_display_unit_and_rejects_zero(self):
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "v.db")
            cid = db.create_challenge("Subir 23.5 km", "ascent_m", 23_500.0, "km")
            row = next(c for c in db.challenges() if c["id"] == cid)
            self.assertEqual(row["display_unit"], "km")
            with self.assertRaises(ValueError):
                db.create_challenge("nada", "distance_m", 0.0)
            db.close()


class TestRankedWithMe(unittest.TestCase):
    def setUp(self):
        from velo.core import boards
        self.rank = boards.ranked_with_me
        self.fmt = lambda v: f"{v:.0f}"

    def test_inserts_me_in_order(self):
        rows, rank = self.rank([(10, "a"), (30, "c"), (20, "b")], 25, False,
                               self.fmt, "Tu")
        self.assertEqual(rank, 3)
        self.assertEqual([r.label for r in rows], ["a", "b", "Tu", "c"])
        self.assertEqual([r.rank for r in rows], [1, 2, 3, 4])

    def test_higher_is_better(self):
        rows, rank = self.rank([(60, "a"), (600, "b")], 100, True, self.fmt, "Tu")
        self.assertEqual(rank, 2)
        self.assertTrue(rows[1].me)

    def test_me_stays_visible_outside_the_top(self):
        entries = [(i, f"r{i}") for i in range(1, 21)]
        rows, rank = self.rank(entries, 99, False, self.fmt, "Tu", max_rows=6)
        self.assertEqual(len(rows), 6)
        self.assertEqual(rank, 21)
        self.assertTrue(rows[-1].me)
        self.assertEqual(rows[-1].rank, 21)

    def test_without_a_value_yet(self):
        rows, rank = self.rank([(10, "a")], None, False, self.fmt, "Tu")
        self.assertIsNone(rank)
        self.assertTrue(rows[-1].me)
        self.assertEqual(rows[-1].value, "—")


class TestChaseLevels(unittest.TestCase):
    def test_waves_raise_the_power_every_minute(self):
        from velo.core.chase import Chase, minutes_to_ftp, LEVELS
        c = Chase("normal", 250, 80.0, 0.32, 0.004)
        self.assertEqual(c.watts_at(0), 150)
        self.assertEqual(c.watts_at(59.9), 150)
        self.assertEqual(c.watts_at(60), 160)
        self.assertEqual(c.watts_at(600), 250)
        self.assertAlmostEqual(minutes_to_ftp(LEVELS["normal"]), 10.0)
        self.assertLess(minutes_to_ftp(LEVELS["hard"]), minutes_to_ftp(LEVELS["easy"]))

    def test_stationary_rider_is_caught_quickly(self):
        from velo.core.chase import Chase
        c = Chase("easy", 250, 80.0, 0.32, 0.004)
        kinds = []
        for _ in range(int(120 / 0.05)):
            kinds += [k for k, _ in c.step(0.05, 0.0)]
            if c.caught:
                break
        self.assertTrue(c.caught)
        self.assertIn("chase_caught", kinds)
        self.assertLess(c.t_s, 60)


class TestLeftRightBalance(unittest.TestCase):
    def test_text_always_sums_to_100(self):
        self.assertEqual(units.balance_text(49.0), "49 / 51")
        self.assertEqual(units.balance_text(49.6), "50 / 50")
        self.assertEqual(units.balance_text(52.4), "52 / 48")
        self.assertEqual(units.balance_text(None), "—")
        self.assertEqual(units.format_metric(48.0, "balance"), "48 / 52")

    def test_hud_metric_uses_the_3s_average(self):
        state = SimpleNamespace(balance_left=60.0, balance_3s=51.0, avg_balance=50.5)
        self.assertEqual(metrics.formatted("power_balance", state)[1], "51 / 49")
        self.assertEqual(metrics.formatted("avg_balance", state)[1], "50 / 50")

    def test_fit_encoding_marks_the_right_leg(self):
        # 48 % esquerda = 52 % direita, com o bit da direita ligado
        self.assertEqual(fit.balance_8(48.0), 0x80 | 52)
        self.assertEqual(fit.balance_left_from_8(fit.balance_8(48.0)), 48.0)
        self.assertEqual(fit.balance_100(49.5), 0x8000 | 5050)
        self.assertIsNone(fit.balance_8(None))
        self.assertIsNone(fit.balance_100(None))

    def test_existing_hud_lists_get_the_metric_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "v.db"
            db = Database(path)
            db.set("hud_metrics", ["power", "hr"])
            db.conn.execute("DELETE FROM settings WHERE key = 'migr_balance_hud'")
            db.conn.commit()
            db.close()
            db = Database(path)                       # abrir de novo migra
            self.assertEqual(db.get("hud_metrics"), ["power", "hr", "power_balance"])
            db.set("hud_metrics", ["power"])          # o atleta tirou-a
            db.close()
            db = Database(path)
            self.assertEqual(db.get("hud_metrics"), ["power"])   # não volta a pôr
            db.close()


class TestActivityNaming(unittest.TestCase):
    def setUp(self):
        from velo.core import naming
        self.n = naming
        self.when = time.mktime((2026, 10, 26, 9, 30, 0, 0, 0, -1))

    def test_name_uses_the_gpx_file(self):
        self.assertEqual(self.n.activity_name(self.when, source_filename="Serra da Estrela.gpx"),
                         "perennia_2026-10-26_Serra-da-Estrela")
        self.assertEqual(self.n.activity_name(self.when, source_filename="C:/x/sintra.GPX"),
                         "perennia_2026-10-26_sintra")

    def test_falls_back_without_a_route(self):
        self.assertEqual(self.n.activity_name(self.when, kind="chase"),
                         "perennia_2026-10-26_fuga")
        self.assertEqual(self.n.activity_name(self.when, kind="workout",
                                              workout_name="Sweet spot 3x15"),
                         "perennia_2026-10-26_Sweet-spot-3x15")
        self.assertEqual(self.n.activity_name(self.when), "perennia_2026-10-26_livre")

    def test_strips_characters_windows_refuses(self):
        self.assertEqual(self.n.clean('a<b>:c"d/e\\f|g?h*'), "abcdefgh")
        self.assertEqual(self.n.clean("Volta à Ribeira. "), "Volta-à-Ribeira")

    def test_same_day_same_route_gets_a_suffix(self):
        with tempfile.TemporaryDirectory() as d:
            p1, n1 = self.n.unique_path(Path(d), "perennia_2026-10-26_serra")
            p1.write_bytes(b"x")
            p2, n2 = self.n.unique_path(Path(d), "perennia_2026-10-26_serra")
            self.assertEqual(n1, "perennia_2026-10-26_serra")
            self.assertEqual(n2, "perennia_2026-10-26_serra_2")
            self.assertEqual(p2.name, "perennia_2026-10-26_serra_2.fit")


class TestFitContents(unittest.TestCase):
    """Lê o .fit de volta, campo a campo."""

    def _write(self, d, **kw):
        samples = [Sample(t_s=i, dist_m=i * 8.0, speed_mps=8.0, power_w=220,
                          cadence_rpm=88, balance_left=49.0, te_left=78.0,
                          te_right=80.5, ps_left=22.0, ps_right=24.5) for i in range(30)]
        lap = Lap(lap_no=1, trigger="end", start_t_s=0, end_t_s=29, start_dist_m=0,
                  end_dist_m=232, avg_power_w=220,
                  pedal={"te_left": 78.0, "te_right": 80.5, "ps_left": 22.0,
                         "ps_right": 24.5, "ps_combined": None})
        summary = RideSummary(elapsed_s=29, moving_s=29, distance_m=232,
                              avg_power_w=220, pedal=lap.pedal)
        out = Path(d) / "a.fit"
        fit.write_activity(out, Athlete(name="x"), samples, [lap], summary,
                           start_unix=time.time(), **kw)
        return fit.read_messages(out)

    def _first(self, msgs, num):
        return next(v for g, v in msgs if g == num)

    def test_virtual_ride_and_name(self):
        with tempfile.TemporaryDirectory() as d:
            msgs = self._write(d, name="perennia_2026-10-26_serra")
            sport = self._first(msgs, fit.MSG_SPORT)
            self.assertEqual(sport[1], fit.SUB_SPORT_VIRTUAL)
            self.assertEqual(sport[3], "perennia_2026-10-26_serra")
            session = self._first(msgs, fit.MSG_SESSION)
            self.assertEqual(session[5], fit.SPORT_CYCLING)
            self.assertEqual(session[6], 58)
            self.assertEqual(session[110], "perennia_2026-10-26_serra")
            self.assertEqual(self._first(msgs, fit.MSG_LAP)[39], 58)

    def test_torque_effectiveness_and_smoothness(self):
        with tempfile.TemporaryDirectory() as d:
            msgs = self._write(d)
            rec = self._first(msgs, fit.MSG_RECORD)
            self.assertEqual((rec[43], rec[44], rec[45], rec[46]), (156, 161, 44, 49))
            self.assertNotIn(47, rec)                     # combinada: não há
            self.assertEqual(rec[30], 0x80 | 51)          # balanço: 51 % direita
            session = self._first(msgs, fit.MSG_SESSION)
            self.assertEqual((session[101], session[102], session[103], session[104]),
                             (156, 161, 44, 49))
            lap = self._first(msgs, fit.MSG_LAP)
            self.assertEqual((lap[91], lap[92]), (156, 161))

    def test_long_names_are_cut_without_breaking_characters(self):
        raw = fit.encode_string("á" * 100, 64)
        self.assertEqual(len(raw), 64)
        self.assertEqual(raw[-1], 0)
        raw.split(b"\x00")[0].decode("utf-8")           # não rebenta

    def test_pedal_metrics_text(self):
        state = SimpleNamespace(pedal={"te_left": 78.0, "te_right": 80.5},
                                avg_pedal={"ps_combined": 24.0})
        self.assertEqual(metrics.formatted("torque_eff", state)[1], "78 / 80 %")
        self.assertEqual(metrics.formatted("avg_pedal_smooth", state)[1], "24 %")
        self.assertEqual(metrics.formatted("pedal_smooth", state)[1], "—")


class TestFrozenPaths(unittest.TestCase):
    """Como executável do PyInstaller: pastas ao lado do .exe, recursos embutidos."""

    def _frozen(self, exe, meipass=None):
        from unittest import mock
        patches = [mock.patch.object(sys, "frozen", True, create=True),
                   mock.patch.object(sys, "executable", exe)]
        if meipass:
            patches.append(mock.patch.object(sys, "_MEIPASS", meipass, create=True))
        return patches

    def test_windows_exe(self):
        from velo import paths
        with tempfile.TemporaryDirectory() as d:
            exe = str(Path(d) / "Perennia" / "Perennia.exe")
            internal = str(Path(d) / "Perennia" / "_internal")
            ps = self._frozen(exe, internal)
            for p in ps:
                p.start()
            try:
                self.assertTrue(paths.frozen())
                self.assertEqual(paths.app_dir(), Path(exe).resolve().parent)
                self.assertEqual(paths.user_folder("gpx")[0],
                                 Path(exe).resolve().parent / "gpx")
                self.assertEqual(paths.resource("tests", "teste.gpx"),
                                 Path(internal) / "tests" / "teste.gpx")
            finally:
                for p in ps:
                    p.stop()

    def test_mac_app_bundle_points_next_to_the_app(self):
        from velo import paths
        with tempfile.TemporaryDirectory() as d:
            exe = str(Path(d) / "Perennia.app" / "Contents" / "MacOS" / "Perennia")
            ps = self._frozen(exe)
            for p in ps:
                p.start()
            try:
                self.assertEqual(paths.app_dir(), Path(d).resolve())
            finally:
                for p in ps:
                    p.stop()

    def test_crash_report_is_written(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "velo_main", Path(__file__).resolve().parents[1] / "main.py")
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        with tempfile.TemporaryDirectory() as d:
            try:
                raise RuntimeError("falha de teste")
            except RuntimeError:
                import io, contextlib
                with contextlib.redirect_stderr(io.StringIO()):
                    main.report_crash(Path(d))
            text = (Path(d) / "perennia-erro.log").read_text(encoding="utf-8")
            self.assertIn("falha de teste", text)


class TestSmoothDrawing(unittest.TestCase):
    def test_monotone_cubic_passes_through_points_without_overshoot(self):
        from velo.core.curves import monotone_cubic
        xs = [0.0, 0.2, 0.5, 1.0]
        ys = [900.0, 600.0, 350.0, 250.0]           # curva de potência: sempre a descer
        sx, sy = monotone_cubic(xs, ys, 101)
        self.assertEqual(len(sx), 101)
        self.assertAlmostEqual(sy[0], 900.0)
        self.assertAlmostEqual(sy[-1], 250.0)
        self.assertAlmostEqual(sy[50], 350.0, places=6)   # x = 0.5
        for a, b in zip(sy, sy[1:]):
            self.assertLessEqual(b, a + 1e-9)       # nunca sobe entre pontos medidos

    def test_log_positions_spread_durations(self):
        from velo.core.curves import log_positions
        pos = log_positions([1, 10, 100, 1000])
        for got, want in zip(pos, (0.0, 1 / 3, 2 / 3, 1.0)):
            self.assertAlmostEqual(got, want)

    def test_flat_profile_is_not_stretched_into_a_saw(self):
        pts = [RoutePoint(dist_m=i * 5.0, lat=0, lon=0, x_m=i * 5.0, y_m=0,
                          ele_m=100.0 + (0.5 if i % 2 else 0.0), grade_pct=0.0,
                          heading_deg=0.0)
               for i in range(400)]
        idx = RouteIndex(pts)
        prof, lo, hi = idx.profile_normalized(0.0, 1500.0, 200)
        ys = [y for _, y in prof]
        self.assertLess(max(ys) - min(ys), 0.03)    # 0,5 m em 30 m de escala
        self.assertLess(max(ys), 0.5)               # fica em baixo, não a meio

    def test_real_climb_still_fills_the_height(self):
        pts = [RoutePoint(dist_m=i * 5.0, lat=0, lon=0, x_m=i * 5.0, y_m=0,
                          ele_m=100.0 + i * 0.3, grade_pct=6.0, heading_deg=0.0)
               for i in range(400)]
        prof, lo, hi = RouteIndex(pts).profile_normalized(0.0, 1500.0, 200)
        ys = [y for _, y in prof]
        self.assertAlmostEqual(min(ys), 0.0, places=6)
        self.assertAlmostEqual(max(ys), 1.0, places=2)


class TestMetricCatalog(unittest.TestCase):
    def test_new_metrics_exist_and_format(self):
        state = SimpleNamespace(power_3s=250, power_w=250, avg_power=200, weight_kg=72.0,
                                avg_torque=27.4, ftp_w=250,
                                power_zone_bounds=[55, 75, 90, 105, 120, 150])
        self.assertEqual(metrics.formatted("wkg", state)[1], "3.47 W/kg")
        self.assertEqual(metrics.formatted("avg_wkg", state)[1], "2.78 W/kg")
        self.assertEqual(metrics.formatted("avg_torque", state)[1], "27.4 Nm")
        self.assertEqual(metrics.formatted("power_zone_range", state)[1],
                         "225–262 W · 3.1–3.6 W/kg")
        for mid in ("avg_speed", "avg_cadence", "torque", "avg_torque", "wkg"):
            self.assertIn(mid, metrics.REGISTRY)

    def test_disabled_metrics_are_hidden(self):
        from velo.core import boxes
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "v.db")
            allm = metrics.available()
            self.assertEqual(boxes.enabled_metrics(db, allm), allm)
            boxes.set_enabled(db, "np", False)
            self.assertNotIn("np", boxes.enabled_metrics(db, allm))
            boxes.set_enabled(db, "np", True)
            self.assertIn("np", boxes.enabled_metrics(db, allm))
            db.close()


class TestZoneRanges(unittest.TestCase):
    def test_power_zones_in_watts_and_wkg(self):
        from velo.core import zones
        set_language(PT)
        zs = zones.power_zones(250, 72.0)
        self.assertEqual(len(zs), 7)
        self.assertEqual(zs[2].range_text(), "188–225 W · 2.6–3.1 W/kg")
        self.assertEqual(zs[0].range_text(), "< 138 W · < 1.9 W/kg")
        self.assertEqual(zs[6].range_text(), "> 375 W · > 5.2 W/kg")
        self.assertEqual(zs[3].name, "Limiar")

    def test_gauge_position_and_fill_within_zone(self):
        from velo.core import zones
        zs = zones.power_zones(250, 72.0)
        g = zones.gauge(206.25, zs)               # a meio da Z3 (188–225)
        self.assertEqual(g.zone.n, 3)
        self.assertAlmostEqual(g.in_zone, 0.5, places=3)
        self.assertAlmostEqual(g.position, 206.25 / (375 * 1.2), places=4)
        top = zones.gauge(2000, zs)
        self.assertEqual((top.zone.n, top.position, top.in_zone), (7, 1.0, 1.0))
        segs = zones.segments(zs)
        self.assertEqual(segs[0][0], 0.0)
        self.assertAlmostEqual(segs[-1][1], 1.0)
        for (a0, a1), (b0, _) in zip(segs, segs[1:]):
            self.assertAlmostEqual(a1, b0)        # contíguos

    def test_hr_zone_range(self):
        from velo.core import zones
        z = zones.zone_for(150, zones.hr_zones(165))
        self.assertEqual((z.n, z.range_text()), (3, "137–155 bpm"))


class TestWorkoutLibrary(unittest.TestCase):
    def test_every_builtin_workout_is_sound(self):
        from velo.core import workout_library as wl
        from velo.core.workouts import Workout
        names = [n for n, _, _, _ in wl.WORKOUTS]
        self.assertEqual(len(names), len(set(names)))
        for name, category, description, steps in wl.WORKOUTS:
            wk = Workout(name, steps)
            self.assertGreater(wk.total_seconds, 20 * 60, name)
            self.assertLess(wk.total_seconds, 2 * 3600, name)
            for st in steps:
                self.assertGreater(st.duration_s, 0, name)
                if st.target_type == "pct_ftp":
                    self.assertLessEqual(st.target_lo, 200, name)
            self.assertTrue(any(st.text_cue for st in steps), name)

    def test_seed_adds_once_and_respects_deletions(self):
        from velo.core import workout_library as wl
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "v.db")
            self.assertEqual(wl.seed(db), len(wl.WORKOUTS))
            self.assertEqual(wl.seed(db), 0)
            victim = db.workouts()[0]
            db.delete_workout(victim["id"])
            self.assertEqual(wl.seed(db), 0)              # apagado não volta
            self.assertEqual(len(db.workouts()), len(wl.WORKOUTS) - 1)
            db.close()

    def test_plan_shows_current_and_next_steps(self):
        from velo.core.workouts import Step, Workout, WorkoutRunner
        wk = Workout("t", [Step("steady", 300, "pct_ftp", 50, 50),
                           Step("steady", 600, "pct_ftp", 106, 106, 90, 90, "Força"),
                           Step("ramp", 180, "pct_ftp", 60, 40),
                           Step("steady", 60, "pct_ftp", 120, 120)])
        runner = WorkoutRunner(wk, 250, True)
        plan = runner.plan(420, ahead=2)           # 2 min dentro do 2.º passo
        self.assertEqual([p["idx"] for p in plan], [1, 2, 3])
        self.assertTrue(plan[0]["current"])
        self.assertAlmostEqual(plan[0]["remaining_s"], 480)
        self.assertEqual(plan[0]["watts"], (265, 265))
        self.assertEqual(plan[0]["cadence"], 90)
        self.assertEqual(plan[1]["watts"], (150, 100))   # rampa a descer
        runner.intensity = 0.9
        self.assertEqual(runner.plan(420, ahead=0)[0]["watts"], (238, 238))
        self.assertEqual(runner.target_watts(420), 238)


class TestZonesAndBoxes(unittest.TestCase):
    def test_zone_text_has_names(self):
        set_language(PT)
        self.assertEqual(units.format_metric(3, "pzone"), "Z3 · Tempo")
        self.assertEqual(units.format_metric(5, "hzone"), "Z5 · Máximo")

    def test_power_and_hr_zone_metrics(self):
        state = SimpleNamespace(power_3s=260, power_w=255, ftp_w=250, avg_power=180,
                                power_zone_bounds=[55, 75, 90, 105, 120, 150],
                                hr_bpm=150, avg_hr=140, lthr=165,
                                hr_zone_bounds=[68, 83, 94, 105])
        self.assertEqual(metrics.value("power_zone", state), 4)       # 104 % FTP
        self.assertEqual(metrics.value("avg_power_zone", state), 2)   # 72 % FTP
        self.assertEqual(metrics.value("hr_zone", state), 3)          # 91 % LTHR
        self.assertEqual(metrics.value("avg_hr_zone", state), 3)

    def test_lthr_is_estimated_when_missing(self):
        from velo.core.ride import estimate_lthr
        self.assertEqual(estimate_lthr(Athlete(lthr=168)), 168)
        self.assertEqual(estimate_lthr(Athlete(max_hr=190)), 171)
        self.assertEqual(estimate_lthr(Athlete(birth_year=time.localtime().tm_year - 40)),
                         162)
        self.assertIsNone(estimate_lthr(Athlete()))

    def test_left_right_watts(self):
        state = SimpleNamespace(power_3s=240, power_w=240, balance_3s=48.0,
                                balance_left=47.0)
        self.assertEqual(metrics.formatted("power_lr", state)[1], "115 / 125 W")

    def test_boxes_load_repairs_bad_settings(self):
        from velo.core import boxes
        with tempfile.TemporaryDirectory() as d:
            db = Database(Path(d) / "v.db")
            self.assertEqual(len(boxes.load(db, metrics.REGISTRY)), 6)   # por omissão
            db.set("hud_boxes", [{"name": "X", "metrics": ["power", "power", "nope",
                                                            "hr", "cadence", "speed",
                                                            "np", "wkg", "torque",
                                                            "avg_torque", "ascent"]},
                                 "lixo"])
            bx = boxes.load(db, metrics.REGISTRY)
            self.assertEqual(len(bx), 6)
            # sem repetidas, sem desconhecidas, no máximo 7
            self.assertEqual(bx[0]["metrics"], ["power", "hr", "cadence", "speed", "np",
                                                "wkg", "torque"])
            self.assertEqual(bx[1]["metrics"], boxes.DEFAULT_BOXES[1])
            for box in boxes.DEFAULT_BOXES:
                for mid in box:
                    self.assertIn(mid, metrics.REGISTRY, mid)
            db.close()


class TestStatsPeriods(unittest.TestCase):
    """Histórico sintético: sessões em datas escolhidas."""

    def setUp(self):
        from datetime import date
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "v.db")
        self.today = date(2026, 10, 28)          # uma quarta-feira

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def ride(self, day, km=30.0, minutes=60, up=300.0, tss=60.0, watts=200.0,
             curve=None):
        from datetime import datetime, timezone
        rid = self.db.begin_ride(route_id=None, workout_id=None, kind="route",
                                 mode="alone", erg=False, athlete=self.db.athlete(),
                                 difficulty=1.0, extra=0.0, preset="low")
        s = RideSummary(elapsed_s=minutes * 60, moving_s=minutes * 60,
                        distance_m=km * 1000.0, ascent_m=up, tss=tss, avg_power_w=watts,
                        power_curve=curve or [])
        self.db.finish_ride(rid, s, None)
        when = datetime(day.year, day.month, day.day, 12, 0, tzinfo=timezone.utc)
        self.db.conn.execute("UPDATE rides SET started_at = ? WHERE id = ?",
                             (when.strftime("%Y-%m-%dT%H:%M:%S.000Z"), rid))
        self.db.conn.commit()
        return rid

    def test_streaks_in_days_and_weeks(self):
        from datetime import timedelta
        from velo.core import stats
        t = self.today
        for back in (0, 1, 2, 5, 6, 7, 8):          # hoje, ontem, anteontem; e uma série antiga
            self.ride(t - timedelta(days=back))
        st = stats.streaks(self.db, today=t)
        self.assertEqual(st["days"], 3)
        self.assertEqual(st["best_days"], 4)          # dias 5–8
        self.assertEqual(st["weeks"], 2)              # esta semana e a anterior
        self.assertEqual(st["rides_this_week"], 3)    # segunda, terça, quarta
        st2 = stats.streaks(self.db, today=t + timedelta(days=1))   # amanhã, sem treinar ainda
        self.assertEqual(st2["days"], 3)              # não se perde a meio do dia

    def test_heatmap_grid(self):
        from velo.core import stats
        self.ride(self.today, minutes=75)
        grid = stats.heatmap(self.db, 16, today=self.today)
        self.assertEqual((len(grid), len(grid[0])), (16, 7))
        self.assertEqual(grid[-1][2], 75.0)           # quarta-feira desta semana
        self.assertEqual(grid[-1][3], -1.0)           # quinta ainda não chegou

    def test_series_by_week_and_month_with_empty_buckets(self):
        from datetime import timedelta
        from velo.core import stats
        self.ride(self.today, km=40)
        self.ride(self.today - timedelta(days=1), km=20)
        self.ride(self.today - timedelta(days=14), km=50)
        weeks = stats.series(self.db, "distance", "week", 4, today=self.today)
        self.assertEqual([v for _, v in weeks], [0.0, 50.0, 0.0, 60.0])
        self.assertEqual(weeks[-1][0], "S44")
        months = stats.series(self.db, "rides", "month", 2, today=self.today)
        self.assertEqual(months, [("set 26", 0.0), ("out 26", 3.0)])
        tot = stats.period_totals(self.db, "week", 4, today=self.today)
        self.assertEqual(tot["distance"], 110.0)
        self.assertEqual(tot["rides"], 3)

    def test_percentile_of_the_current_week(self):
        from datetime import timedelta
        from velo.core import stats
        for w, km in enumerate((10, 20, 30, 40, 80)):    # 5 semanas, a atual a 80 km
            self.ride(self.today - timedelta(days=7 * (4 - w)), km=km)
        pct = stats.percentile_now(self.db, "distance", "week", today=self.today)
        self.assertEqual(pct["value"], 80.0)
        self.assertEqual(pct["n"], 5)
        self.assertEqual(pct["percentile"], 90.0)      # 4 abaixo + meio empate de 5
        self.assertEqual(pct["best"], 80.0)

    def test_power_curve_keeps_the_date_of_each_best(self):
        from datetime import timedelta
        from velo.core import stats
        self.ride(self.today - timedelta(days=30), curve=[(60, 500.0), (1200, 270.0)])
        self.ride(self.today, curve=[(60, 450.0), (1200, 285.0)])
        detail = {p["duration_s"]: p for p in stats.power_curve_detail(self.db)}
        self.assertEqual(detail[60]["watts"], 500.0)
        self.assertEqual(detail[60]["date"], "2026-09-28")
        self.assertEqual(detail[1200]["watts"], 285.0)
        self.assertEqual(detail[1200]["date"], "2026-10-28")

    def test_power_profile_position(self):
        from velo.core import stats
        self.ride(self.today, curve=[(5, 1000.0), (60, 600.0), (300, 350.0), (1200, 300.0)])
        prof = {p["duration_s"]: p for p in stats.power_profile(self.db, "male", 75.0)}
        self.assertAlmostEqual(prof[3600]["wkg"], 300 * 0.95 / 75)    # limiar = 95 % de 20 min
        lo, hi = stats.COGGAN["male"][300]
        self.assertAlmostEqual(prof[300]["position"], (350 / 75 - lo) / (hi - lo) * 100)
        self.assertIn(prof[60]["level"], stats.COGGAN_LEVELS)
        women = {p["duration_s"]: p for p in stats.power_profile(self.db, "female", 75.0)}
        self.assertGreater(women[300]["position"], prof[300]["position"])

    def test_time_in_zones_from_samples(self):
        from velo.core import stats
        rid = self.ride(self.today)
        self.db.append_samples(rid, [Sample(t_s=i, dist_m=i * 8.0, power_w=100 if i < 30
                                            else 250, hr_bpm=150) for i in range(60)])
        self.db.save_athlete(Athlete(ftp_w=200, lthr=165))
        self.db.conn.execute("UPDATE rides SET ftp_at_ride_w = 200")
        tiz = stats.time_in_zones(self.db)
        self.assertEqual(tiz["power"][0], 30)         # 100 W = 50 % FTP → Z1
        self.assertEqual(tiz["power"][5], 30)         # 250 W = 125 % FTP → Z6
        self.assertEqual(tiz["hr"][2], 60)            # 150 bpm = 91 % LTHR → Z3


if __name__ == "__main__":
    unittest.main(verbosity=2)
