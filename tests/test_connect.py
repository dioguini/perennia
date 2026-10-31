"""Strava (segmentos e PR, com HTTP simulado), GarminDB (garmin.db sintética),
HRV4Training (formato real do CSV) e Excel das análises."""
from __future__ import annotations

import importlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import agent, health, importers, labs  # noqa: E402
from velo.core import segments as sg  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.io import strava  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import connect_screens as cs  # noqa: E402
from velo.ui import health_screens as hs  # noqa: E402

LAT0, LON0 = 38.7223, -9.1393          # o início da rota de teste (tests/make_gpx.py)
M_LAT = 110540.0


def lat_at(m: float) -> float:
    return LAT0 + (m + 10) / M_LAT


class FakeStrava:
    """O Strava a fingir: regista os pedidos e responde como a API."""

    def __init__(self, segments=(), prs=None, expires_at=10 ** 10):
        self.calls: list[tuple] = []
        self.segments = list(segments)
        self.prs = prs or {}
        self.expires_at = expires_at

    def __call__(self, method, url, params=None, headers=None, timeout=20.0):
        self.calls.append((method, url, dict(params or {}), dict(headers or {})))
        if url == strava.TOKEN_URL:
            return 200, {"access_token": f"tok{len(self.calls)}", "refresh_token": "ref",
                         "expires_at": self.expires_at,
                         "athlete": {"id": 7, "firstname": "Daniel", "lastname": "F"}}
        if url.endswith("/segments/explore"):
            s, w, n, e = (float(x) for x in params["bounds"].split(","))
            inside = [x for x in self.segments if s <= x["start_latlng"][0] <= n]
            return 200, {"segments": inside[:10]}
        if "/segments/" in url:
            sid = int(url.rsplit("/", 1)[1])
            pr = self.prs.get(sid)
            stats = {"pr_elapsed_time": pr, "pr_date": "2025-06-01", "effort_count": 3} \
                if pr else {}
            return 200, {"id": sid, "athlete_segment_stats": stats, "xoms": {"kom": "5:01"}}
        return 404, None


def seg(sid, name, a, b, lon=LON0):
    return {"id": sid, "name": name, "distance": b - a, "avg_grade": 6.0,
            "climb_category": 2, "start_latlng": [lat_at(a), lon],
            "end_latlng": [lat_at(b), lon]}


class TestStravaCore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250))
        from velo.core import climbs, gpx
        _, raw = gpx.parse_gpx(tg.GPX)
        self.points = gpx.resample(raw)
        self.rid = self.db.insert_route("Serra", self.points, climbs.detect(self.points))
        self.db.set("strava_client_id", "123")
        self.db.set("strava_client_secret", "abc")

    def tearDown(self):
        self.db.close() if hasattr(self.db, "close") else None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_auth_url_and_token_refresh(self):
        fake = FakeStrava(expires_at=100)
        c = strava.StravaClient(self.db, http=fake, clock=lambda: 50.0)
        url = c.auth_url()
        self.assertIn("client_id=123", url)
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A8723", url)
        self.assertIn("activity%3Aread", url)
        self.assertFalse(c.connected)
        c.exchange("CODE")
        self.assertTrue(c.connected)
        self.assertEqual(c.athlete_name, "Daniel F")
        self.assertEqual(fake.calls[0][2]["grant_type"], "authorization_code")
        # expira daqui a 50 s (< 60): renova antes do pedido
        c.explore((0, 0, 1, 1))
        kinds = [x[2].get("grant_type") for x in fake.calls if x[1] == strava.TOKEN_URL]
        self.assertEqual(kinds, ["authorization_code", "refresh_token"])
        self.assertTrue(fake.calls[-1][3]["Authorization"].startswith("Bearer tok"))

    def test_errors(self):
        c = strava.StravaClient(self.db, http=lambda *a, **k: (429, None))
        with self.assertRaises(strava.StravaError):
            c.get("/x")                                    # sem autorização
        self.db.set("strava_tokens", {"refresh_token": "r", "access_token": "a",
                                      "expires_at": 10 ** 10})
        with self.assertRaises(strava.StravaError) as e:
            c.get("/x")
        self.assertIn("15 min", str(e.exception))

    def test_segments_matched_to_route_with_prs(self):
        fake = FakeStrava(segments=[
            seg(1, "Subida da Serra", 1000, 4000),            # na rota, mesmo sentido
            seg(2, "Ao contrário", 4000, 1000),                # sentido inverso: fora
            seg(3, "Noutra estrada", 1500, 2500, lon=LON0 + 0.01),   # 870 m ao lado
            seg(4, "Descida", 4200, 5600),
        ], prs={1: 900})
        c = strava.StravaClient(self.db, http=fake)
        c.exchange("x")
        rep = sg.fetch_for_route(self.db, c, self.rid)
        self.assertEqual(rep["matched"], 2)
        got = sg.load(self.db, self.rid)
        self.assertEqual([s.name for s in got], ["Subida da Serra", "Descida"])
        self.assertAlmostEqual(got[0].start_m, 1000, delta=20)
        self.assertAlmostEqual(got[0].end_m, 4000, delta=20)
        self.assertEqual(got[0].pr_s, 900)
        self.assertEqual(got[0].kom, "5:01")
        self.assertIsNone(got[1].pr_s)
        # os pedidos ao explore cobrem a rota em janelas
        explores = [x for x in fake.calls if x[1].endswith("/explore")]
        self.assertGreaterEqual(len(explores), 2)
        self.assertEqual(explores[0][2]["activity_type"], "riding")

    def test_tracker_live_delta_and_local_best(self):
        s = sg.Segment(1, "Serra", 1000.0, 4000.0, pr_s=900)
        tr = sg.SegmentTracker([s])
        self.assertEqual(tr.observe(500, 100), [])
        ev = tr.observe(1005, 200)
        self.assertEqual(ev[0][0], "strava_start")
        cur = tr.current(2500, 600)                        # a meio, 400 s
        self.assertAlmostEqual(cur["frac"], 0.5)
        self.assertAlmostEqual(cur["delta_pr"], 400 - 450)  # 50 s à frente do PR
        board = tr.board(2500, 600)
        self.assertEqual(board.title, "Serra")
        self.assertTrue(any(r.me for r in board.rows))
        ev = tr.observe(4001, 1000)
        self.assertEqual(ev[0][0], "strava_end")
        self.assertEqual(ev[0][1]["elapsed_s"], 800)
        self.assertEqual(s.local_best_s, 800)
        self.assertEqual(tr.observe(4100, 1010), [])       # já contado nesta volta
        tr.reset()
        self.assertEqual(tr.observe(1001, 2000)[0][0], "strava_start")

    def test_strava_never_reaches_the_agent(self):
        self.assertIn("strava", agent.EXCLUDED_SOURCES)


class TestStravaInRide(tg.GuiCase):
    def setUp(self):
        super().setUp()
        db = self.app.db
        sg.ensure(db)
        db.conn.execute(
            "INSERT INTO strava_segments(route_id, segment_id, name, distance_m, avg_grade,"
            " climb_cat, start_m, end_m, pr_s, pr_date, effort_count, kom, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.route_id, 11, "Sprint Lisboa", 300, 0.5, 0, 100, 400, 60, "2025-01-01",
             2, None, "2026-10-30"))
        db.conn.commit()

    def test_segment_board_signs_and_summary(self):
        self.app.push(app_mod.RouteDetail(self.app, self.route_id))
        self.app.current.enter()
        self.select("Segmentos do Strava")
        ctx = self.screen().agent_context()
        self.assertFalse(any("Strava" in r["rotulo"] for r in ctx["linhas"]))
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        self.assertIsNotNone(ride.engine.strava)
        seen_board = False
        for _ in range(int(240 / 0.5)):
            self.app.hub.tick(0.5)
            ride.update(0.5)
            if ride.engine.active_segment() is not None:
                b = ride.engine.live_board()
                seen_board = seen_board or b.title == "Sprint Lisboa"
            if ride.engine.state.pos_m > 450:
                break
        self.assertTrue(seen_board)
        self.assertEqual(len(ride.engine.strava_results), 1)
        self.press(key.F10, key.ENTER)
        summ = self.screen()
        self.assertIsInstance(summ, app_mod.SummaryScreen)
        self.assertTrue(any("Sprint Lisboa" in i.label for i in summ.list.items))
        ctx = summ.agent_context()
        self.assertFalse(any("Sprint Lisboa" in r["rotulo"] for r in ctx["linhas"]))
        best = sg.load(self.app.db, self.route_id)[0].local_best_s
        self.assertIsNotNone(best)

    def test_strava_screens(self):
        fake = FakeStrava(segments=[seg(5, "Serra toda", 1000, 4000)], prs={5: 700})
        self.pick("Definições")
        self.pick("Strava")
        scr = self.screen()
        self.assertIsInstance(scr, cs.StravaScreen)
        self.assertFalse(scr.AGENT)
        self.app.db.set("strava_client_id", "")
        self.select("Client ID")
        self.type("999")
        self.assertEqual(self.app.db.get("strava_client_id"), "999")
        self.select("Client Secret")
        self.type("segredo")
        self.assertEqual(self.app.db.get("strava_client_secret"), "segredo")
        scr.client.http = fake
        scr.client.exchange("code")
        scr.enter()
        self.assertIn("Daniel", scr.list.items[0].value)
        seg_scr = cs.StravaSegmentsScreen(self.app, self.route_id, http=fake)
        self.app.push(seg_scr)
        self.pick("Atualizar do Strava")
        seg_scr.job.thread.join(5)
        seg_scr.update(0.1)
        self.assertTrue(any("Serra toda" in i.label for i in seg_scr.list.items))
        self.assertTrue(any(i.value == "PR 11:40" for i in seg_scr.list.items))


# ================================================================= GarminDB


def make_garmindb(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(folder / "garmin.db")
    con.executescript("""
    CREATE TABLE daily_summary (day DATE PRIMARY KEY, hr_min INT, hr_max INT, rhr INT,
      stress_avg INT, steps INT, moderate_activity_time TIME, vigorous_activity_time TIME,
      floors_up FLOAT, distance FLOAT, calories_active INT, spo2_avg FLOAT,
      rr_waking_avg FLOAT, bb_charged INT, bb_max INT, bb_min INT);
    CREATE TABLE sleep (day DATE PRIMARY KEY, total_sleep TIME, deep_sleep TIME,
      light_sleep TIME, rem_sleep TIME, awake TIME, score INT, avg_stress FLOAT);
    CREATE TABLE resting_hr (day DATE PRIMARY KEY, resting_heart_rate FLOAT);
    CREATE TABLE weight (day DATE PRIMARY KEY, weight FLOAT);
    INSERT INTO daily_summary VALUES ('2026-10-28', 44, 151, 47, 28, 11234, '00:35:00.000000',
      '00:20:00.000000', 6, 8.4, 650, 95.5, 14.2, 60, 92, 18);
    INSERT INTO daily_summary VALUES ('2026-10-29', 45, 120, 48, 31, 8000, '00:00:00.000000',
      '00:00:00.000000', 2, 5.1, 300, 96, 14.0, 55, 88, 22);
    INSERT INTO sleep VALUES ('2026-10-29', '07:30:00.000000', '01:15:00.000000',
      '04:00:00.000000', '01:45:00.000000', '00:30:00.000000', 82, 15.5);
    INSERT INTO resting_hr VALUES ('2026-10-29', 46);
    INSERT INTO weight VALUES ('2026-10-29', 75.8);
    """)
    con.commit()
    con.close()
    return folder


class TestGarminDB(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.folder = make_garmindb(self.tmp / "HealthData" / "DBs")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def val(self, day, key_):
        m = health.metric_by_key(self.db, key_)
        return health.values_for(self.db, day).get(m["id"], {}).get("value")

    def test_import_reads_the_garmindb_tables(self):
        rep = importers.import_garmindb(self.db, self.folder)
        self.assertEqual(rep["days"], 2)
        self.assertIn("sleep", rep["tables"])
        self.assertEqual(self.val("2026-10-28", "steps"), 11234)
        self.assertEqual(self.val("2026-10-28", "g_int_mod"), 35)
        self.assertEqual(self.val("2026-10-29", "sleep_hours"), 7.5)
        self.assertEqual(self.val("2026-10-29", "g_sleep_deep"), 1.25)
        self.assertEqual(self.val("2026-10-29", "rhr"), 46)       # resting_hr por cima
        self.assertEqual(self.val("2026-10-29", "weight"), 75.8)
        self.assertEqual(self.val("2026-10-29", "g_bb_max"), 88)
        self.assertIsNone(self.val("2026-10-29", "g_int_mod"))     # zero: não regista
        m = health.metric_by_key(self.db, "steps")
        src = health.values_for(self.db, "2026-10-28")[m["id"]]["source"]
        self.assertEqual(src, "garmin")
        self.assertTrue(self.db.get("garmindb_last_import"))
        # voltar a importar não duplica
        rep2 = importers.import_garmindb(self.db, self.folder, since="2026-10-29")
        self.assertEqual(rep2["days"], 1)

    def test_status_and_runner(self):
        self.db.set("garmindb_dir", str(self.folder))
        st = importers.garmindb_status(self.db)
        self.assertTrue(st["found"])
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli.py"
        try:
            ok, out = importers.run_garmindb(runner=runner)
        finally:
            importers.garmindb_cli = orig
        self.assertTrue(ok)
        self.assertIn("--latest", calls[0])
        self.assertNotIn("password", " ".join(calls[0]).lower())

    def test_missing_folder(self):
        with self.assertRaises(FileNotFoundError):
            importers.import_garmindb(self.db, self.tmp / "nada")


class TestGarminDBGui(tg.GuiCase):
    def test_screen_imports(self):
        folder = make_garmindb(Path(self.tmp) / "g")
        self.app.db.set("garmindb_dir", str(folder))
        self.pick("Definições")
        self.pick("Sincronização")                 # o separador das Definições
        scr = self.screen()
        self.assertIsInstance(scr, app_mod.SettingsScreen)
        self.assertEqual(scr.list.items[0].value, "GarminDB")
        self.assertIn("garmin.db ✓", scr.list.items[1].detail)
        self.pick("Só importar")
        self.assertEqual(scr.sync.last_report["days"], 2)


# =============================================================== HRV4Training


H4T_HEADER = ("date, local, time, HR,AVNN,SDNN,rMSSD,pNN50,LF,HF,HRV4T_Recovery_Points,training,"
              "training_performance,training_type,training_phase,physical_condition,trainingRPE,"
              " trainingTSS, trainingMotivation, trainingDistance, sleep_quality, sleep_time,"
              " sleep_awake, sleep_tobed, mental_energy,muscle_soreness, fatigue, lifestyle,"
              " traveling,sickness,alcohol,note,signal_quality, location, supplements, diet,"
              " custom_tag_1_name, custom_tag_2_name, custom_tag_3_name, custom_tag_1_value,"
              " custom_tag_2_value, custom_tag_3_value, menstrual_cycle, trainingTime")


def h4t_row(date_, hr, rmssd, sleep="07:30", awake="07:10", bed="23:40", weight="74.5",
            note="BodyTemperature:36.1;", training="rest", ttime=""):
    return (f"{date_},{date_},08:00,{hr},900,70,{rmssd},20,0.1,0.07,7.4,{training},,"
            f",Just training,4,,,0,,8,{sleep},{awake},{bed},7.5,0,1.1,0,not traveling,"
            f"not sick,nothing,{note},very good,,,,Weight (kg),General Motivation,,"
            f"{weight},9.0,,,{ttime}")


class TestHrv4Training(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def val(self, day, key_):
        m = health.metric_by_key(self.db, key_)
        return health.values_for(self.db, day).get(m["id"], {}).get("value") if m else None

    def test_real_format_with_year_day_month_dates(self):
        p = self.tmp / "HRV4Training_data.csv"
        p.write_text("\n".join([
            H4T_HEADER,
            h4t_row("026-20-06", 62.77, 43.79),              # ano cortado, como no export
            h4t_row("2026-21-06", 61.38, 43.23, training="easy", ttime="3120.0"),
            h4t_row("2026-01-07", 66.47, 73.69, note="BodyTemperature:35.7:"),
        ]) + "\n")
        self.assertTrue(importers.looks_like_hrv4training(p))
        rep = health.import_file(self.db, p)
        self.assertEqual(rep["date_order"], "ydm")
        self.assertEqual(rep["days"], 3)
        self.assertEqual(self.val("2026-06-20", "rhr"), 62.77)
        self.assertEqual(self.val("2026-06-20", "hrv_rmssd"), 43.79)
        self.assertEqual(self.val("2026-06-20", "sleep_hours"), 7.5)
        self.assertEqual(self.val("2026-06-20", "weight"), 74.5)
        self.assertEqual(self.val("2026-06-20", "body_temp"), 36.1)
        self.assertEqual(self.val("2026-07-01", "body_temp"), 35.7)
        self.assertEqual(self.val("2026-06-21", "h4t_training_time"), 52.0)   # 3120 s
        self.assertEqual(self.val("2026-06-21", "h4t_tag_general_motivation"), 9.0)
        self.assertEqual(self.val("2026-06-20", "wake_time"), "07:10")
        self.assertIn("training_phase", rep["ignored"])
        # outra vez: mesmos dias, nada duplicado
        rep2 = health.import_file(self.db, p)
        self.assertEqual(rep2["days"], 3)


# ============================================================ análises (Excel)


def make_lab_xlsx(path: Path) -> Path:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "readings"
    from datetime import datetime
    d1, d2 = datetime(2025, 7, 23), datetime(2026, 3, 13)
    rows = [
        ("Rotina", "Lab A", d1, "Hematologia", "Hemograma", "Eritrograma", "Hemoglobina", 14.1),
        ("Rotina", "Lab A", d1, "Bioquímica", "Ferro", None, "Ferritina", 320),
        ("Rotina", "Lab A", d1, "Bioquímica", "Lípidos", None,
         "Colesterol HDL (Enzimático colorimétrico)", "< 1,111"),
        ("Rotina", "Lab A", d2, "Hematologia", "Hemograma", "Leucograma", "Neutrófilos",
         "4,1 [55,2]"),
        ("Rotina", "Lab A", d2, "Bioquímica", "Ferro", None, "Ferritina", 180),
    ]
    for r in rows:
        ws.append(r)
    ref = wb.create_sheet("ref_parameter")
    ref.append(("Id", "Description", "Unit", "Reference Value"))
    ref.append((1, "Hemoglobina", "g/dL", "13,0-16,5"))
    ref.append((2, "Ferritina", "ng/mL",
                "Mulheres: 15 - 150\n>15 anos (homem): 50 - 300\nCrianças: 7 - 140"))
    ref.append((3, "Colesterol HDL (Enzimático colorimétrico)", "mg/dL",
                "Desejável: > 40"))
    ref.append((4, "Neutrófilos", "x10⁹/L", "1,8 - 7,7"))
    wb.save(path)
    return path


class TestLabsExcel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1993, weight_kg=72, ftp_w=250))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_and_reimport(self):
        p = make_lab_xlsx(self.tmp / "analises.xlsx")
        rep = health.import_file(self.db, p)
        self.assertEqual(rep["reports"], 2)
        self.assertEqual(rep["results"], 5)
        self.assertEqual(rep["parameters"], 4)
        fer = labs.parameter_by_name(self.db, "Ferritina")
        self.assertEqual((fer["ref_low"], fer["ref_high"]), (50, 300))   # o do homem
        self.assertEqual(fer["unit"], "ng/mL")
        reps = health.lab_reports(self.db)
        first = next(r for r in reps if r["done_on"] == "2025-07-23")
        self.assertEqual(first["out_of_range"], 2)              # ferritina 320, HDL < 1,1
        groups = labs.grouped_results(self.db, first["id"])
        self.assertEqual([(g[0], g[1]) for g in groups],
                         [("Hematologia", "Hemograma"), ("Bioquímica", "Ferro"),
                          ("Bioquímica", "Lípidos")])
        hdl = groups[2][2][0]
        self.assertEqual(labs.value_text(hdl), "<1.111")
        self.assertEqual(labs.short_name(hdl["marker"]), "Colesterol HDL")
        second = next(r for r in reps if r["done_on"] == "2026-03-13")
        neu = labs.grouped_results(self.db, second["id"])[0][2][0]
        self.assertEqual(neu["value"], 4.1)
        self.assertEqual(neu["value_pct"], 55.2)
        # feedback do médico fica depois de voltar a importar
        health.save_lab_report(self.db, first["id"], done_on="2025-07-23", lab="Lab A",
                               doctor_feedback="Ferritina alta: repetir.")
        rep2 = health.import_file(self.db, p)
        self.assertEqual(rep2["results"], 5)
        reps = health.lab_reports(self.db)
        self.assertEqual(len(reps), 2)
        first = next(r for r in reps if r["done_on"] == "2025-07-23")
        self.assertEqual(first["doctor_feedback"], "Ferritina alta: repetir.")
        self.assertEqual(first["n"], 3)
        self.assertEqual([x["value"] for x in health.marker_history(self.db, "Ferritina")],
                         [320, 180])

    def test_manual_reference_survives_import(self):
        p = make_lab_xlsx(self.tmp / "analises.xlsx")
        health.import_file(self.db, p)
        fer = labs.parameter_by_name(self.db, "Ferritina")
        labs.set_parameter_reference(self.db, fer["id"], 30, 400)
        health.import_file(self.db, p)
        fer = labs.parameter_by_name(self.db, "Ferritina")
        self.assertEqual((fer["ref_low"], fer["ref_high"]), (30, 400))
        reps = health.lab_reports(self.db)
        self.assertEqual(sum(r["out_of_range"] for r in reps), 1)        # só o HDL


class TestLabsGui(tg.GuiCase):
    def test_excel_import_catalog_and_grouped_report(self):
        make_lab_xlsx(self.app.data_dir / "imports" / "analises.xlsx") \
            if (self.app.data_dir / "imports").mkdir(parents=True, exist_ok=True) is None \
            else None
        self.press(key.ESCAPE)                       # volta ao ecrã inicial
        self.pick("Saúde")
        self.pick("Análises")
        self.pick("Importar do Excel")
        imp = self.screen()
        self.assertIsInstance(imp, hs.ImportScreen)
        self.pick("analises.xlsx")
        self.assertEqual(imp.last_report["reports"], 2)
        self.press(key.ESCAPE)
        labs_scr = self.screen()
        labs_scr.enter()
        self.pick("2025-07-23")
        rep = self.screen()
        labels = [i.label for i in rep.list.items]
        self.assertIn("— Bioquímica · Ferro", labels)
        self.assertIn("Ferritina ▲", labels)
        self.assertIn("Colesterol HDL ▼", labels)
        self.press(key.ESCAPE)
        self.screen().enter()
        self.pick("Catálogo de parâmetros")
        cat = self.screen()
        self.assertIsInstance(cat, hs.ParameterCatalog)
        self.pick("Ferritina")
        ed = self.screen()
        self.assertIsInstance(ed, hs.ParameterEditor)
        self.assertTrue(any(">15 anos (homem)" in i.label for i in ed.list.items))
        self.select("Referência mínima")
        self.type("40")
        self.pick("Guardar")
        self.assertEqual(labs.parameter_by_name(self.app.db, "Ferritina")["ref_low"], 40)


if __name__ == "__main__":
    unittest.main()
