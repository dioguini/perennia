"""Remo: protocolos (Domyos e FTMS), motor da sessão, treinos, testes, jogos,
voltas de remo no Conditioning, recuperação e os ecrãs."""
from __future__ import annotations

import importlib
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import fit, fitness_tests as ft, rowing as rw, stats  # noqa: E402
from velo.core import laps_session as ls  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.io import rower as rio  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import rowing_screens as rs  # noqa: E402
from velo.ui import sport_screens as ss  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ================================================================ protocolos


class TestProtocols(unittest.TestCase):
    def test_concept2_formula(self):
        self.assertEqual(rio.watts_from_pace(120.0), 203)          # 2:00 /500 m ≈ 203 W
        self.assertAlmostEqual(rio.pace_from_watts(203), 120.0, delta=0.3)
        self.assertIsNone(rio.watts_from_pace(0))
        self.assertEqual(rio.pace_text(112.34), "1:52.3")
        self.assertEqual(rio.pace_text(None), "—")

    def test_domyos_frames(self):
        self.assertEqual(rio.DOMYOS_POLL.hex(), "f0ac9c")
        self.assertEqual([f.hex() for f in rio.DOMYOS_INIT],
                         ["f0c801b9", "f0c9b9", "f0a393", "f0a494", "f0a595", "f0ab9b",
                          "f0c403b7"])
        cmd = rio.encode_domyos_resistance(9)
        self.assertEqual(len(cmd), 23)
        self.assertEqual(cmd[:2], b"\xf0\xad")
        self.assertEqual(cmd[10], 9)
        self.assertEqual((cmd[17], cmd[18]), (0x00, 0x01))
        self.assertTrue(rio.valid(cmd))
        self.assertEqual([len(c) for c in rio.chunks(cmd)], [20, 3])
        self.assertEqual(rio.encode_domyos_resistance(40)[10], 15)   # limitado a 1–15
        self.assertEqual(rio.encode_domyos_resistance(0)[10], 1)

    def test_domyos_status_packet(self):
        pkt = rio.build_domyos_packet(strokes=321, pace_s=118, spm=24, kcal=55,
                                      distance_raw=7650, resistance=7, hr=142)
        self.assertEqual(len(pkt), 26)
        d = rio.parse_domyos(pkt)
        self.assertEqual((d.strokes, d.spm, d.pace_s, d.resistance, d.hr_bpm, d.kcal),
                         (321, 24.0, 118.0, 7, 142, 55.0))
        self.assertEqual(d.watts, rio.watts_from_pace(118))
        idle = rio.parse_domyos(rio.build_domyos_packet(strokes=321, pace_s=118, spm=0))
        self.assertIsNone(idle.pace_s)                 # parado: sem ritmo
        self.assertIsNone(rio.parse_domyos(b"\xf0\xac\x9c"))

    def test_ftms_rower_data(self):
        # flags: total distance (bit2), pace (bit3), power (bit5), resistance (bit7),
        # energy (bit8), HR (bit9), elapsed (bit11); bit0 = 0 → spm e remadas
        flags = (1 << 2) | (1 << 3) | (1 << 5) | (1 << 7) | (1 << 8) | (1 << 9) | (1 << 11)
        data = struct.pack("<HBH", flags, 48, 150) + (1234).to_bytes(3, "little") + \
            struct.pack("<Hhh", 115, 210, 6) + struct.pack("<HHB", 80, 600, 10) + \
            struct.pack("<BH", 151, 420)
        d = rio.parse_ftms_rower(data)
        self.assertEqual((d.spm, d.strokes, d.distance_m, d.pace_s, d.power_w, d.resistance,
                          d.kcal, d.hr_bpm, d.elapsed_s),
                         (24.0, 150, 1234, 115.0, 210, 6, 80, 151, 420))
        self.assertEqual(rio.encode_ftms_resistance(8), bytes([0x04, 80]))

    def test_detection_by_advertisement(self):
        self.assertEqual(rio.is_rower("DOMYOS-ROW-1234", []), "domyos")
        self.assertEqual(rio.is_rower("", [rio.SVC_DOMYOS]), "domyos")
        self.assertEqual(rio.is_rower("PM5 430000000", []), "ftms")
        self.assertIsNone(rio.is_rower("KICKR CORE", []))

    def test_sensor_feed_goes_stale(self):
        clock = Clock()
        s = rio.RowerSensor("AA", "DOMYOS-ROW", "domyos", clock=clock)
        s.feed(rio.build_domyos_packet(strokes=10, pace_s=130, spm=22, resistance=4))
        self.assertEqual(s.data().strokes, 10)
        clock.t = 6.0
        self.assertIsNone(s.data())


# ===================================================================== motor


def make_db(tmp: Path) -> Database:
    db = Database(tmp / "v.db")
    db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=75, ftp_w=250, lthr=165))
    return db


class TestRowEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_for(self, e, seconds, dt=0.5):
        for _ in range(int(seconds / dt)):
            e.update(dt)

    def test_free_session_distance_pace_and_fit(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, resistance=6,
                                            hr_bpm=150, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, out_dir=self.tmp)
        self.assertEqual(e.status, "waiting")
        e.update(0.5)
        self.assertEqual(e.status, "running")         # há ritmo: arranca
        for i in range(239):
            r.current.strokes = i // 5
            e.update(0.5)
        self.assertAlmostEqual(e.distance_m, 500.0, delta=5)       # 2 min a 2:00/500 m
        self.assertAlmostEqual(e.avg_pace_s, 120.0, delta=1)
        self.assertEqual(e.power_w, 203)
        e.lap("manual")
        res = e.finish()
        self.assertEqual(len(res["laps"]), 2)
        self.assertAlmostEqual(res["avg_power_w"], 203, delta=1)
        info = fit.verify(res["fit_path"])
        self.assertGreaterEqual(info["messages"][20], 100)        # registos
        msgs = fit.read_messages(res["fit_path"])
        sport = [f for n, f in msgs if n == 12][0]
        self.assertEqual((sport[0], sport[1]), (15, 14))           # remo indoor
        row = self.db.conn.execute("SELECT * FROM row_sessions").fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertAlmostEqual(row["distance_m"], 500, delta=5)

    def test_auto_pause_and_resume(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=22, pace_s=125.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, out_dir=self.tmp)
        self.run_for(e, 30)
        r.current = rio.RowerData(strokes=60, spm=0, pace_s=None, source="domyos")
        self.run_for(e, 20)
        self.assertEqual(e.status, "auto_paused")
        t_paused = e.t
        self.run_for(e, 20)
        self.assertLess(e.t - t_paused, 1.0)
        r.current = rio.RowerData(strokes=61, spm=22, pace_s=125.0, source="domyos")
        self.run_for(e, 2)
        self.assertEqual(e.status, "running")

    def test_workout_steps_by_time_and_distance_set_resistance(self):
        wid = rw.save_workout(self.db, None, "Teste", "", [
            rw.Step("warmup", "time", 3, "none", resistance=3),        # sobe para 10 s
            rw.Step("active", "distance", 100, "power", 90, 100, 9),
            rw.Step("rest", "time", 20, "none")])
        steps = rw.workout(self.db, wid)["steps"]
        self.assertEqual(steps[0].dur_value, 10)
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=100.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, workout_id=wid, out_dir=self.tmp)
        self.assertEqual(r.commands[0], ("resistance", 3))
        self.run_for(e, 10.5)
        self.assertEqual(e.workout.idx, 1)
        self.assertIn(("resistance", 9), r.commands)
        self.run_for(e, 20.5)                    # 100 m a 5 m/s = 20 s
        self.assertEqual(e.workout.idx, 2)
        self.run_for(e, 21)
        self.assertTrue(e.workout.done)
        res = e.finish()
        self.assertEqual(len(res["workout_results"]), 3)
        self.assertEqual([lp.trigger for lp in res["laps"]][:3],
                         ["workout_step", "workout_step", "workout_step"])

    def test_power_target_in_watts_and_pace(self):
        s = rw.Step("active", "time", 60, "power", 100, 100)
        self.assertEqual(s.watts_range(200), (200, 200))
        slow, fast = s.pace_range(200)
        self.assertAlmostEqual(slow, rio.pace_from_watts(200))
        self.assertIn("200–200 W", s.target_text(200))
        p = rw.Step("active", "time", 60, "pace", 125, 120)
        self.assertEqual(p.target_text(), "2:05.0–2:00.0 /500 m")

    def test_test_2000m_records_result_and_rowing_ftp(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=30, pace_s=100.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, protocol="row_500", out_dir=self.tmp)
        self.run_for(e, 120)
        self.assertEqual(e.distance_m, 500.0)
        self.assertEqual(e.result_value, 100.0)
        e.finish()
        t_ = next(x for x in ft.tests(self.db, "rowing") if x["name"] == "500 m")
        self.assertEqual(t_["protocol"], "row_500")
        self.assertEqual(t_["last"], 100.0)
        e2 = rw.RowEngine(self.db, self.db.athlete(), r, protocol="row_2000", out_dir=self.tmp)
        self.run_for(e2, 420)
        e2.finish()
        self.assertEqual(self.db.get("row_ftp_w"), int(round(rio.watts_from_pace(100) * 0.85)))

    def test_regatta_vs_bots(self):
        self.db.set("row_ftp_w", 200)
        fast = rio.ScriptedRower(rio.RowerData(strokes=0, spm=34, pace_s=85.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), fast, out_dir=self.tmp,
                         game_spec={"key": "regatta", "distance": 500, "bots": 3, "seed": 2})
        self.run_for(e, 100)
        self.assertTrue(e.game.finished)
        self.assertEqual(e.game.rank, 1)                     # 1:25 a 200 W de FTP ganha
        b = e.game.board()
        self.assertTrue(any(r.me for r in b.rows))
        res = e.finish()
        self.assertEqual(res["game"]["rank"], 1)
        self.assertAlmostEqual(rw.game_history(self.db, e.game)[0], 85, delta=1)

    def test_cycling_games_use_rowing_ftp(self):
        self.db.set("row_ftp_w", 180)
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, out_dir=self.tmp,
                         game_spec={"key": "adaptive", "minutes": 10})
        self.assertEqual(e.game.ftp, 180)
        self.assertFalse(e.game.erg)
        self.run_for(e, 60)
        self.assertIsNotNone(e.game.target_w)
        res = e.finish()
        self.assertIsNotNone(res["game"])
        self.assertEqual(self.db.get("adaptive_level"), None)   # o nível do ciclismo fica
        self.assertIsNotNone(self.db.get("row_adaptive_level"))

    def test_checkpoint_and_resume(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, source="domyos"))
        wid = rw.workouts(self.db)[0]["id"]
        e = rw.RowEngine(self.db, self.db.athlete(), r, workout_id=wid, out_dir=self.tmp)
        self.run_for(e, 61)
        e.suspend()
        self.db.purge_incomplete()
        cp = self.db.checkpoint(e.session_id)
        self.assertIsNotNone(cp)
        self.assertEqual(cp["sport"], "rowing")
        e2 = rw.RowEngine(self.db, self.db.athlete(), r, resume=cp, workout_id=wid,
                          out_dir=self.tmp)
        self.assertAlmostEqual(e2.distance_m, e.distance_m, delta=3)
        self.assertEqual(e2.workout.idx, e.workout.idx)
        self.assertEqual(e2.status, "paused")
        e2.toggle_pause()
        self.run_for(e2, 10)
        self.assertGreater(e2.distance_m, e.distance_m + 30)
        e2.finish()
        self.assertIsNone(self.db.checkpoint(e.session_id))

    def test_rowing_counts_in_load_and_streaks(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=110.0, hr_bpm=160,
                                            source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, out_dir=self.tmp)
        self.run_for(e, 600)
        res = e.finish()
        self.assertGreater(res["load"], 5)
        self.assertIn("rowing", stats.SPORTS)
        now = stats.fitness_now(self.db)
        self.assertGreater(now["atl"], 0)
        self.assertGreaterEqual(stats.streaks(self.db)["days"], 1)
        tot = stats.sport_totals(self.db, "week", 1)
        self.assertEqual(tot["rowing"]["sessions"], 1)

    def test_workout_export_fit(self):
        path = self.tmp / "w.fit"
        fit.write_row_workout(path, "8x500", [
            {"name": "Trabalho", "meters": 500, "lo_w": 200, "hi_w": 220},
            {"name": "Descanso", "seconds": 90}])
        info = fit.verify(path)
        self.assertEqual(info["messages"][27], 2)


class TestConditioningRowingLap(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rowing_lap_filled_from_machine(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=26, pace_s=125.0, resistance=8,
                                            source="domyos"))
        s = ls.LapSession(self.db, self.db.athlete(), "conditioning", out_dir=self.tmp, rower=r)
        s.start_lap("treadmill")
        for _ in range(60):
            s.update(1.0)
        lap = s.start_lap("rowing")
        self.assertEqual(lap.kind, "rowing")
        for _ in range(250):
            s.update(1.0)
        self.assertAlmostEqual(lap.distance_km, 1.0, delta=0.01)
        self.assertEqual(lap.resistance, 8)
        self.assertEqual(lap.spm, 26)
        self.assertAlmostEqual(lap.pace_s, 125.0, delta=1)
        s.set_field("resistance", 11)
        self.assertIn(("resistance", 11), r.commands)
        res = s.finish()
        self.assertAlmostEqual(res["distance_km"], 1.0, delta=0.01)
        row = self.db.conn.execute("SELECT * FROM strength_laps WHERE kind='rowing'").fetchone()
        self.assertEqual(row["row_resistance"], 11)
        self.assertIsNotNone(row["row_pace_s"])

    def test_rowing_lap_by_hand(self):
        s = ls.LapSession(self.db, self.db.athlete(), "conditioning", out_dir=self.tmp)
        lap = s.start_lap("rowing")
        for _ in range(240):
            s.update(1.0)
        s.set_field("distance_km", 1.0)
        self.assertAlmostEqual(lap.pace_s, 120.0, delta=0.5)
        s.adjust("resistance", 1)
        self.assertEqual(lap.resistance, 6)


# ==================================================================== ecrãs


class TestRowingGui(tg.GuiCase):
    def go_rowing(self):
        self.press(key.ESCAPE)
        self.pick("Remo")
        self.assertIsInstance(self.screen(), rs.RowingMenu)

    def test_free_row_with_simulated_machine(self):
        self.go_rowing()
        self.pick("Sessão de treino")
        dev = self.screen()
        self.assertIsInstance(dev, rs.RowerDeviceScreen)          # pede a máquina
        self.pick("simulada")
        self.assertIsInstance(self.app.rower, rio.SimulatedRower)
        self.pick("Continuar")
        self.assertEqual(self.screen().list.items[1].value, "desligado")   # auto lap
        self.pick("Começar")
        ses = self.screen()
        self.assertIsInstance(ses, rs.RowingSessionScreen)
        for _ in range(120):
            ses.update(0.5)
        self.app._on_draw()
        values = [v.text for _, _, v in ses.cells]
        self.assertEqual(len(values), 12)                       # 12 campos por página
        self.assertTrue(any("/15" in v for v in values))
        self.assertTrue(any(v.endswith(" m") for v in values))
        self.assertIn("TEMPO TOTAL", ses.clock.cap.text)
        self.assertNotEqual(ses.clock.value.text, "0:00")
        self.press(key.V)                                       # segunda página de campos
        ses.update(0.5)
        caps = [c.text for _, c, _ in ses.cells]
        self.assertIn("VOGA MÉDIA", caps)
        self.assertIn("ENERGIA POR REMADA", caps)
        self.press(key.PLUS)
        self.assertEqual(self.app.rower.level, 7)
        self.press(key.L)
        self.press(key.ESCAPE)
        self.pick("Sim")
        summ = self.screen()
        self.assertIsInstance(summ, rs.RowSummaryScreen)
        self.assertTrue(any("Volta 1" in i.label for i in summ.list.items))
        self.assertEqual(len(rw.sessions(self.app.db)), 1)

    def test_workout_builder_and_run(self):
        self.app.set_rower(rio.SimulatedRower())
        self.go_rowing()
        self.app.push(rs.RowWorkoutEditor(self.app, None))      # o editor por passos (P)
        ed = self.screen()
        self.assertIsInstance(ed, rs.RowWorkoutEditor)
        self.pick("2. Trabalho")
        step = self.screen()
        self.select("Duração por")
        self.press(key.RIGHT)
        self.assertEqual(step.s.dur_type, "distance")
        self.select("Resistência")
        self.press(key.RIGHT, key.RIGHT)
        self.assertEqual(step.s.resistance, 8)
        self.press(key.ESCAPE)
        self.select("Repetir")
        self.press(key.RIGHT)                                   # × 5
        self.press(key.ENTER)
        self.assertEqual(len(ed.steps), 3 + 2 * 4)
        self.pick("Exportar")
        self.assertTrue(ed.export_path.exists())
        self.pick("Guardar")
        names = [w["name"] for w in rw.workouts(self.app.db)]
        self.assertIn("Novo treino", names)
        self.assertIsInstance(self.screen(), rs.RowingMenu)
        self.screen().enter()
        self.pick("Lista de treinos")
        self.pick("8 × 500 m")
        self.pick("Começar")
        self.pick("Começar")                                    # depois das opções
        ses = self.screen()
        self.assertIsInstance(ses, rs.RowingSessionScreen)
        for _ in range(30):
            ses.update(0.5)
        self.assertIn("PASSO 1/18", ses.status.text)
        self.assertIn("A seguir", ses.plan.text)

    def test_regatta_from_challenge(self):
        self.app.set_rower(rio.SimulatedRower(watts=260))
        self.go_rowing()
        self.pick("Challenge")
        self.pick("Regata")
        setup = self.screen()
        self.select("Distância")
        self.press(key.LEFT, key.LEFT)
        self.assertEqual(setup.amount, 500)
        self.pick("Começar")
        self.pick("Começar")
        ses = self.screen()
        self.assertIsNotNone(ses.engine.game)
        for _ in range(400):
            ses.update(0.5)
            if ses.engine.game.finished:
                break
        self.assertTrue(ses.engine.game.finished)
        self.assertTrue(ses.board_panel.board.title.startswith("Regata"))

    def test_rowing_test_from_tests_menu(self):
        self.app.set_rower(rio.SimulatedRower())
        self.go_rowing()
        self.pick("Testes")
        self.pick("500 m")
        self.pick("máquina de remo")
        self.pick("Começar")
        ses = self.screen()
        self.assertEqual(ses.engine.protocol, "row_500")

    def test_fields_and_ftp(self):
        # a FTP do remo está nas Definições (Atleta); a máquina, nos Dispositivos
        self.go_rowing()
        labels = [i.label for i in self.screen().list.items]
        self.assertEqual(labels[:3], ["Sessão de treino", "Challenge", "Desafios"])
        self.assertFalse(any("Máquina de remo" in x or "FTP" in x for x in labels))
        self.pick("Definições")
        self.select("FTP do remo")
        before = rw.row_ftp(self.app.db)
        self.press(key.RIGHT)
        self.assertEqual(rw.row_ftp(self.app.db), before + 1)
        self.press(key.ESCAPE)
        self.pick("Campos")
        self.select("Campo 1")
        self.press(key.RIGHT)
        self.assertEqual(rs.field_names(self.app.db)[0], "avg_pace")

    def test_crash_recovery(self):
        self.app.set_rower(rio.SimulatedRower())
        self.go_rowing()
        self.pick("Sessão de treino")
        self.pick("Começar")
        ses = self.screen()
        for _ in range(60):
            ses.update(0.5)
        self.app.shutdown(crashed=True)
        app2 = app_mod.App(data_dir=Path(self.tmp), width=1280, height=760)
        try:
            self.assertIsInstance(app2.current, ss.RecoveryScreen)
            labels = [i.label for i in app2.current.list.items]
            self.assertTrue(any("Remo" in x for x in labels))
            app2.set_rower(rio.SimulatedRower())
            view = app2.current.list
            view.index = next(i for i, it in enumerate(view.items)
                              if "Retomar" in it.label)
            view.activate()
            self.assertIsInstance(app2.current, rs.RowingSessionScreen)
            self.assertGreater(app2.current.engine.distance_m, 10)
        finally:
            app2.shutdown()

    def test_conditioning_offers_rowing_lap(self):
        self.app.set_rower(rio.SimulatedRower())
        scr = ss.LapSessionScreen(self.app, "conditioning")
        self.app.push(scr)
        self.pick("Nova volta: Remo")
        for _ in range(60):
            scr.update(1.0)
        lap = scr.session.current
        self.assertEqual(lap.kind, "rowing")
        self.assertGreater(lap.distance_km, 0.05)
        self.assertTrue(any("da máquina de remo" in (i.detail or "") for i in scr.list.items))


if __name__ == "__main__":
    unittest.main()
