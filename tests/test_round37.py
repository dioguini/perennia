"""Ronda 37: métricas como o TrainingPeaks (sem substitutos), o relatório .txt de cada
sincronização (sem o limite de 1 h), a análise automática das atividades importadas,
«Reavaliar todos os treinos» e o que o TrainingPeaks traz escrito."""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import feedback as fbm  # noqa: E402
from perennia.core import garmin_sync as gs  # noqa: E402
from perennia.core import longevity as lg  # noqa: E402
from perennia.core import stats, tp_import, tss  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")

TP_CSV = ("Title,WorkoutType,WorkoutDescription,WorkoutDay,CoachComments,TimeTotalInHours,"
          "DistanceInMeters,TSS,IF,HeartRateAverage,HRZone1Minutes,HRZone2Minutes,"
          "HRZone3Minutes,PWRZone2Minutes,Rpe,Feeling,AthleteComments\n"
          "Sweet spot,Bike,3x15 a 90 %,2026-11-20,Cadência alta,1.25,38000,80,0.8,140,"
          "10,40,25,60,7,8,Pernas pesadas no fim\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.db.save_athlete(Athlete(name="D", birth_year=1990, weight_kg=70, ftp_w=250,
                                     lthr=165))
        gs.ensure(self.db)

    def tearDown(self):
        self.db.close()

    def add(self, aid, sport="running", secs=3600.0, tss_=None, hr=150.0, when=None):
        when = when or "2026-11-21 08:00:00"
        self.db.conn.execute(
            "INSERT INTO synced_activities(id, source, sport, name, started_at, elapsed_s,"
            " moving_s, avg_hr, tss) VALUES (?,?,?,?,?,?,?,?,?)",
            (aid, "garmindb", sport, "Atividade", when, secs, secs, hr, tss_))
        self.db.conn.commit()


class TestMetrics(Base):
    def test_pmc_constants_are_options(self):
        old = stats.CTL_DAYS
        try:
            stats.CTL_DAYS = 28
            out = stats.pmc({date.today(): 100.0}, date.today())
            self.assertAlmostEqual(out[-1]["ctl"], 100 / 28)
        finally:
            stats.CTL_DAYS = old

    def test_no_substitutes(self):
        self.assertIsNone(stats.synced_load({"tss": None, "avg_hr": 160, "moving_s": 3600}))
        # corrida sem ritmo gravado: sem rTSS (não vale o ritmo médio nem a FC)
        self.assertEqual(tss.for_imported(self.db, "running", 3600, speeds=None),
                         (None, None, None))
        # ciclismo pela NP e o FTP: 1 h à FTP = 100
        t, if_, src = tss.for_imported(self.db, "cycling", 3600, np_w=250)
        self.assertAlmostEqual(t, 100.0)
        self.assertEqual((if_, src), (1.0, "power"))
        # corrida com ritmo (1 h ao ritmo de limiar = 100)
        t, _if, src = tss.for_imported(self.db, "running", 3600, speeds=[1000 / 300.0] * 3600)
        self.assertAlmostEqual(t, 100.0, places=3)
        self.assertEqual(src, "rtss")

    def test_clear_substitutes(self):
        from perennia.core import endurance as en
        en.ensure(self.db)
        self.db.conn.execute("INSERT INTO endurance_sessions(id, sport, status, started_at,"
                             " moving_s, load, load_source) VALUES ('e1','running','completed',"
                             "'2026-11-20T08:00:00Z',3600,55,'hr')")
        self.db.conn.commit()
        self.assertEqual(tss.clear_substitutes(self.db), 1)
        r = self.db.conn.execute("SELECT load FROM endurance_sessions").fetchone()
        self.assertIsNone(r["load"])


class TestReport(Base):
    def test_report_file_with_steps_and_lines(self):
        log = gs.SyncLog()
        log.step("A correr o GarminDB")
        log.line("Downloading activities: 3 of 9")
        log.line('{"password": "segredo"}')
        log.end(False, "o GarminDB parou")
        path = gs.save_report(log, False, "o GarminDB parou", {"activities": 0}, "GarminDB",
                              self.tmp)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.name, "sincronizacoes")
        text = path.read_text(encoding="utf-8")
        for want in ("Resultado: FALHOU", "✗ 1. A correr o GarminDB", "Downloading activities"):
            self.assertIn(want, text)
        self.assertNotIn("segredo", text)

    def test_no_time_limit_by_default(self):
        self.assertEqual(gs.SYNC_TIMEOUT_S, 0.0)
        log = gs.SyncLog()
        ok, out = gs._run_streaming([sys.executable, "-c", "print('ok')"], 0, None, log)
        self.assertTrue(ok)


class TestImportedAnalysis(Base):
    def test_trainingpeaks_text_feedback_zones_and_analysis(self):
        p = self.tmp / "tp.csv"
        p.write_text(TP_CSV, encoding="utf-8")
        rep = tp_import.import_csv(self.db, p)
        self.assertEqual(rep["activities"], 1)
        r = dict(self.db.conn.execute("SELECT * FROM synced_activities").fetchone())
        self.assertEqual(r["description"], "3x15 a 90 %")
        self.assertEqual(r["coach_comments"], "Cadência alta")
        self.assertEqual(r["athlete_comments"], "Pernas pesadas no fim")
        self.assertIn("2400", r["hr_zone_s"])                   # 40 min em Z2
        fb = fbm.get(self.db, "imported", r["id"])
        self.assertEqual((fb["rpe"], fb["feel"]), (7, 4))
        self.assertEqual(fb["comment"], "Pernas pesadas no fim")
        self.assertTrue(fb["verdict"])
        self.assertTrue(fb["analysis"]["sections"])

    def test_imported_count_for_longevity_without_doubling(self):
        self.add("g:1", "running", 3600)
        ids = [d.sid for d in lg.all_doses(self.db)]
        self.assertIn("g:1", ids)
        n = fbm.analyse_imported(self.db)
        self.assertEqual(n, 1)
        self.assertEqual(fbm.analyse_imported(self.db), 0)       # só as novas

    def test_auto_analysis_keeps_the_athlete_feedback(self):
        self.add("g:2", "cycling", 3600, tss_=70)
        fbm.save(self.db, "imported", "g:2", rpe=6, comment="bom")
        fbm.auto_analyse(self.db, "imported", "g:2")
        fb = fbm.get(self.db, "imported", "g:2")
        self.assertEqual((fb["rpe"], fb["comment"]), (6, "bom"))
        self.assertTrue(fbm.has_user_feedback(fb))

    def test_reevaluate_all(self):
        self.add("g:3", "running", 1800)
        rep = fbm.reevaluate_all(self.db)
        self.assertGreaterEqual(rep["sessions"], 1)
        self.assertIsNotNone(fbm.get(self.db, "imported", "g:3"))


class TestReevaluateButton(tg.GuiCase):
    def test_button_in_history_tab(self):
        scr = self.open_sync("Histórico")
        self.assertIn("Reavaliar todos os treinos", [i.label for i in scr.list.items])
        self.pick("Reavaliar todos os treinos")
        self.pick("Reavaliar")                             # a confirmação
        self.assertEqual(self.app.task.kind, "reevaluate")
        self.assertEqual(self.app.task.state(), "ok")
        self.assertIn("sessões reavaliadas", self.app._message)


if __name__ == "__main__":
    unittest.main()
