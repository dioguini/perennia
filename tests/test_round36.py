"""Ronda 36: o calendário mostra todas as atividades, feitas na Perennia ou importadas
(Garmin, TrainingPeaks, histórico do Strava/Garmin Connect, upload manual). As do Garmin
ganham a potência, a TSS e o IF lidos dos .fit que o GarminDB já descarrega."""
from __future__ import annotations

import importlib
import shutil
import sqlite3
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import calendar_view as cv  # noqa: E402
from perennia.core import garmin_sync as gs  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
t9 = sys.modules.get("test_round9") or importlib.import_module("tests.test_round9")


def garmin_activities(folder: Path, rows: list[tuple]) -> None:
    """Uma garmin_activities.db como a do GarminDB (só as colunas que a Perennia lê)."""
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(folder / "garmin_activities.db")
    con.execute("CREATE TABLE activities (activity_id TEXT, name TEXT, sport TEXT,"
                " sub_sport TEXT, start_time TEXT, elapsed_time TEXT, moving_time TEXT,"
                " distance REAL, ascent REAL, avg_hr REAL, max_hr REAL, calories REAL,"
                " training_load REAL)")
    con.executemany("INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


class TestCalendarShowsEverything(tg.GuiCase):
    def add_imported(self, aid="garmin:1", sport="running", when=None, secs=2700.0,
                     source="garmindb", **kw):
        gs.ensure(self.app.db)
        when = when or datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
        self.app.db.conn.execute(
            "INSERT INTO synced_activities(id, source, sport, name, started_at, elapsed_s,"
            " moving_s, distance_m, avg_hr, tss) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, source, sport, kw.get("name", "Corrida da manhã"),
             when.isoformat(timespec="seconds"), secs, secs, kw.get("dist", 8000.0),
             kw.get("hr", 150.0), kw.get("tss")))
        self.app.db.conn.commit()
        return when.date()

    def test_imported_activity_appears_on_its_day(self):
        day = self.add_imported()
        es = cv.sessions_between(self.app.db, day, day)
        self.assertEqual([(e.kind, e.sport, e.title) for e in es],
                         [("imported", "running", "Corrida da manhã")])
        self.assertTrue(es[0].load)                     # a carga pela FC (sem TSS)
        data = cv.month_data(self.app.db, day.year, day.month)
        self.assertIn(es[0].id, [e.id for e in data["by_day"][day]])

    def test_every_source_counts(self):
        day = date.today()
        for i, src in enumerate(("garmindb", "trainingpeaks", "strava", "garmin", "upload")):
            self.add_imported(f"x:{i}", sport=("cycling", "running", "swimming", "gym",
                                               "rowing")[i], source=src, secs=600.0 * (i + 1))
        es = cv.sessions_between(self.app.db, day, day)
        self.assertEqual(len(es), 5)
        self.assertEqual({cv.imported_source({"source": s}) for s in
                          ("garmindb", "trainingpeaks", "strava", "garmin")},
                         {"Garmin", "TrainingPeaks", "Strava", "Garmin Connect"})

    def test_same_activity_done_in_perennia_is_not_doubled(self):
        from perennia.core.db import RideSummary
        when = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
        rid = self.app.db.begin_ride(route_id=self.route_id, workout_id=None, kind="free",
                                     mode="sim", erg=False, athlete=self.app.db.athlete(),
                                     difficulty=1.0, extra=0.0, preset="medium")
        self.app.db.conn.execute("UPDATE rides SET status='completed', started_at=?,"
                                 " moving_s=3600, elapsed_s=3600 WHERE id=?",
                                 (when.astimezone(timezone.utc).strftime(
                                     "%Y-%m-%dT%H:%M:%SZ"), rid))
        self.app.db.conn.commit()
        self.add_imported("garmin:9", sport="cycling", when=when, secs=3500.0)
        es = cv.sessions_between(self.app.db, when.date(), when.date())
        self.assertEqual([e.kind for e in es], ["ride"])
        _ = RideSummary

    def test_day_popup_opens_the_imported_details(self):
        from perennia.ui.calendar_screens import DayScreen
        from perennia.ui.imported_screens import ImportedActivityScreen
        day = self.add_imported(tss=55.0)
        scr = DayScreen(self.app, day)
        self.app.push(scr)
        item = next(i for i in scr.list.items if "Corrida da manhã" in i.label)
        self.assertIn("importada de Garmin", item.detail)
        item.action()
        det = self.screen()
        self.assertIsInstance(det, ImportedActivityScreen)
        labels = {i.label: i.value for i in det.list.items}
        self.assertEqual(labels["Origem"], "Garmin")
        self.assertEqual(labels["TSS"], "55")
        self.assertEqual(labels["Distância"], "8.00 km")

    def test_history_rows_open_the_details_too(self):
        from perennia.ui.imported_screens import ImportedActivityScreen
        from perennia.ui.sync_screens import history_items
        self.add_imported()
        rows = [i for i in history_items(self.app, "running") if i.data]
        self.assertTrue(rows and rows[0].enabled)
        rows[0].action()
        self.assertIsInstance(self.screen(), ImportedActivityScreen)


class TestGarminFitDetails(tg.GuiCase):
    def test_power_tss_and_if_from_the_fit(self):
        db = self.app.db
        dbs = gs.db_dir(db)                               # data/garmin/bases/DBs
        garmin_activities(dbs, [("123456", "Volta ao vale", "cycling", "road",
                                 "2026-11-20 08:00:00", "00:30:00", "00:30:00", 15.0, 120,
                                 140, 165, 500, 80)])
        fit_dir = dbs.parent / "FitFiles" / "Activities"
        fit_dir.mkdir(parents=True, exist_ok=True)
        src = t9._write_fit(Path(self.tmp) / "ride.fit", minutes=30)
        shutil.copy(src, fit_dir / "123456_ACTIVITY.fit")
        rep = gs.import_activities(db, dbs)
        self.assertEqual(rep["activities"], 1)
        self.assertEqual(rep["detailed"], 1)
        r = dict(db.conn.execute("SELECT * FROM synced_activities WHERE id='garmin:123456'")
                 .fetchone())
        self.assertTrue(r["fit_file"].endswith("123456_ACTIVITY.fit"))
        self.assertGreater(r["avg_power_w"] or 0, 0)
        self.assertGreater(r["np_w"] or 0, 0)
        self.assertGreater(r["tss"] or 0, 0)               # pelo FTP (250 W) se o .fit não a tem
        self.assertGreater(r["if_value"] or 0, 0)
        # a segunda vez não volta a ler
        self.assertEqual(gs.fit_details(db, dbs), 0)

    def test_without_fit_files_nothing_breaks(self):
        db = self.app.db
        dbs = gs.db_dir(db)
        garmin_activities(dbs, [("777777", "Corrida", "running", "generic",
                                 "2026-11-21 08:00:00", "00:40:00", "00:40:00", 8.0, 30, 150,
                                 170, 500, 60)])
        rep = gs.import_activities(db, dbs)
        self.assertEqual((rep["activities"], rep["detailed"]), (1, 0))
        r = db.conn.execute("SELECT fit_file, tss FROM synced_activities").fetchone()
        self.assertIsNone(r["fit_file"])                   # tenta-se outra vez na próxima


if __name__ == "__main__":
    unittest.main()
