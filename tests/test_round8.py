"""Ronda 8: PMC como o TrainingPeaks, rTSS/sTSS, métricas de evolução,
importações (TrainingPeaks, análises), inventário com compra, limites do
construtor, pesquisa nas listas, seletores e o calendário no ecrã inicial."""
from __future__ import annotations

import importlib
import math
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import endurance as en  # noqa: E402
from velo.core import evolution as ev  # noqa: E402
from velo.core import health  # noqa: E402
from velo.core import inventory as inv  # noqa: E402
from velo.core import labs  # noqa: E402
from velo.core import stats  # noqa: E402
from velo.core import tp_import  # noqa: E402
from velo.core import tss  # noqa: E402
from velo.core import workout_meta as wm  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.core.i18n import PT, set_language  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import pickers  # noqa: E402
from velo.ui.widgets import Item  # noqa: E402

TODAY = date(2026, 6, 30)


class DbCase(unittest.TestCase):
    def setUp(self):
        set_language(PT)
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))
        en.ensure(self.db)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_(self, day: date, km: float, minutes: float, hr_drift: float = 0.0,
             samples: bool = True) -> str:
        sid = f"r{day.isoformat()}{km}"
        secs = int(minutes * 60)
        v = km * 1000 / secs
        self.db.conn.execute(
            "INSERT INTO endurance_sessions(id, sport, name, status, started_at, moving_s,"
            " distance_m, avg_hr) VALUES (?,?,?,?,?,?,?,?)",
            (sid, "running", "Corrida", "completed", f"{day.isoformat()}T09:00:00Z", secs,
             km * 1000, 150))
        if samples:
            rows = [(sid, t, v * t, v, int(150 + hr_drift * t / secs)) for t in range(secs)]
            self.db.conn.executemany(
                "INSERT INTO endurance_samples(session_id, t_s, dist_m, speed_mps, hr_bpm)"
                " VALUES (?,?,?,?,?)", rows)
        self.db.conn.commit()
        return sid


# ============================================================ PMC e TSS


class TestPmc(DbCase):
    def test_constants_like_trainingpeaks(self):
        out = stats.pmc({TODAY: 100.0}, TODAY + timedelta(days=1), None)
        first, nxt = out[0], out[1]
        self.assertAlmostEqual(first["ctl"], 100 * (1 - math.exp(-1 / 42)), places=3)
        self.assertAlmostEqual(first["atl"], 100 * (1 - math.exp(-1 / 7)), places=3)
        # a forma de amanhã é o fitness menos a fadiga de hoje
        self.assertAlmostEqual(nxt["tsb"], first["ctl"] - first["atl"], places=3)
        self.assertAlmostEqual(first["tsb"], 0.0, places=6)

    def test_starting_values_from_settings(self):
        self.db.set("pmc_ctl0", 50.0)
        self.db.set("pmc_atl0", 60.0)
        out = stats.pmc({TODAY: 0.0}, TODAY, self.db)
        self.assertAlmostEqual(out[0]["tsb"], -10.0, places=3)
        self.assertLess(out[0]["ctl"], 50.0)

    def test_rtss_one_hour_at_threshold_is_100(self):
        self.assertAlmostEqual(tss.rtss([4.0] * 3600, 3600, 4.0), 100.0, places=3)
        self.assertLess(tss.rtss([3.0] * 3600, 3600, 4.0), 100.0)

    def test_stss_cubes_intensity(self):
        # 100 m em 100 s com CSS de 100 s/100 m durante 1 h = 100
        self.assertAlmostEqual(tss.stss(3600, 3600, 100), 100.0, places=3)
        self.assertAlmostEqual(tss.stss(3600, 3600, 50), 12.5, places=3)   # IF 0,5

    def test_grade_factor_uphill_costs_more(self):
        self.assertGreater(tss.grade_factor(5), 1.0)
        self.assertAlmostEqual(tss.grade_factor(0), 1.0, places=6)


# ================================================== métricas de evolução


class TestEvolution(DbCase):
    def test_efficiency_and_decoupling(self):
        steady = ev.decoupling([3.0] * 3600, [150] * 3600)
        self.assertAlmostEqual(steady, 0.0, places=3)
        drift = ev.decoupling([3.0] * 3600, [140] * 1800 + [160] * 1800)
        self.assertGreater(drift, 5.0)
        self.assertAlmostEqual(ev.efficiency([3.0] * 100, [150] * 100), 1.2, places=3)

    def test_durability_needs_long_run(self):
        self.assertIsNone(ev.durability([3.0] * 1200, [150] * 1200))
        n = ev.LONG_RUN_S + 600
        self.assertIsNotNone(ev.durability([3.0] * n, [150] * n))

    def test_running_trends_from_db(self):
        self.run_(TODAY - timedelta(days=3), 12, 80, hr_drift=12)
        t = ev.running_trends(self.db, TODAY)
        self.assertEqual(len(t["ef"]), 1)
        self.assertGreater(t["decoupling"][0][1], 0)
        self.assertEqual(len(t["durability"]), 1)

    def test_long_run_warning(self):
        self.run_(TODAY - timedelta(days=20), 10, 60, samples=False)
        self.run_(TODAY - timedelta(days=2), 12, 72, samples=False)
        w = ev.load_warnings(self.db, TODAY)
        self.assertTrue(any("12.0 km" in x for x in w), w)

    def test_weekly_volume_warning(self):
        self.run_(TODAY - timedelta(days=9), 20, 120, samples=False)
        self.run_(TODAY - timedelta(days=1), 15, 90, samples=False)
        self.run_(TODAY, 10, 60, samples=False)
        w = ev.load_warnings(self.db, TODAY)
        self.assertTrue(any("Volume" in x for x in w), w)

    def test_riegel_and_predictions(self):
        self.assertAlmostEqual(ev.riegel(1200, 5000, 5000), 1200)
        self.assertAlmostEqual(ev.riegel(1200, 5000, 10000), 1200 * 2 ** 1.06, places=3)
        self.run_(TODAY - timedelta(days=5), 10, 45, samples=False)
        p = ev.predictions(self.db, TODAY)
        self.assertEqual(p["basis"].distance_m, 10000)
        names = [n for n, _d, _s in p["races"]]
        self.assertIn("Maratona", names)
        self.assertIsNotNone(p["tanda"])

    def test_daniels_vdot_reference(self):
        # 5 km em 20:00 ≈ VDOT 49,8 (tabelas de Daniels)
        self.assertAlmostEqual(ev.daniels_vdot(5000, 1200), 49.8, delta=0.5)
        v = ev.daniels_vdot(5000, 1200)
        z = ev.pace_zones(270, v)
        self.assertEqual(set(z), {"80/20", "Friel", "Daniels"})
        e_lo, e_hi = z["Daniels"][0][1], z["Daniels"][0][2]
        self.assertGreater(e_lo, e_hi)                       # o mais lento primeiro
        self.assertIn("/km", ev.zone_text(e_lo, e_hi))
        easy = z["80/20"][0]
        self.assertTrue(ev.zone_text(easy[1], easy[2]).startswith("mais lento"))
        self.assertTrue(ev.zone_text(*z["Friel"][-1][1:]).startswith("mais rápido"))

    def test_readiness(self):
        health.ensure(self.db)
        health.seed(self.db)
        mid = health.metric_by_key(self.db, "hrv_rmssd")["id"]
        rid = health.metric_by_key(self.db, "rhr")["id"]
        for k in range(30):
            d = TODAY - timedelta(days=k)
            health.set_value(self.db, d, mid, 62 - (k % 3))
            health.set_value(self.db, d, rid, 50)
        r = ev.readiness(self.db, TODAY)
        self.assertEqual(r["state"], "ready")
        health.set_value(self.db, TODAY, rid, 60)
        for k in range(7):
            health.set_value(self.db, TODAY - timedelta(days=k), mid, 35)
        self.assertEqual(ev.readiness(self.db, TODAY)["state"], "rest")
        self.assertIsNone(ev.readiness(self.db, TODAY + timedelta(days=5))["state"])


# ============================================================ importações


class TestImports(DbCase):
    def test_trainingpeaks_csv(self):
        p = self.tmp / "tp.csv"
        p.write_text("Title,WorkoutType,WorkoutDay,TimeTotalInHours,DistanceInMeters,TSS,IF,"
                     "HeartRateAverage\n"
                     "Longo,Run,2026-06-20,1.5,15000,95,0.8,148\n"
                     "Planeado,Bike,2026-06-21,,,,,\n", encoding="utf-8")
        self.assertTrue(tp_import.looks_like_tp(p))
        r = tp_import.import_csv(self.db, p)
        self.assertEqual(r, {"activities": 1, "skipped": 1})
        row = self.db.conn.execute("SELECT * FROM synced_activities").fetchone()
        self.assertEqual(row["sport"], "running")
        self.assertEqual(row["tss"], 95)
        tp_import.import_csv(self.db, p)                  # outra vez: sem duplicar
        self.assertEqual(self.db.conn.execute(
            "SELECT COUNT(*) FROM synced_activities").fetchone()[0], 1)
        # entra na carga quando está ligado nas Definições
        self.db.set("pmc_synced", True)
        daily = stats.daily_load(self.db)
        self.assertIn(95.0, list(daily.values()))

    def test_labs_csv_and_doctor_comment(self):
        p = self.tmp / "a.csv"
        p.write_text("data;analise;valor;unidade\n01/03/2026;Glicose;92;mg/dL\n"
                     "01/03/2026;Colesterol total;180;mg/dL\n2026-05-01;Glicose;88;mg/dL\n",
                     encoding="utf-8")
        r = labs.import_csv(self.db, p)
        self.assertEqual((r["reports"], r["results"]), (2, 3))
        prev = labs.previous_values(self.db, "Glicose", "2026-05-01")
        self.assertEqual(len(prev), 1)
        res = self.db.conn.execute("SELECT id FROM lab_results LIMIT 1").fetchone()[0]
        labs.set_doctor_comment(self.db, res, "Normal")
        self.assertEqual(self.db.conn.execute(
            "SELECT doctor_comment FROM lab_results WHERE id = ?", (res,)).fetchone()[0],
            "Normal")


class TestInventory(DbCase):
    def test_purchase_fields(self):
        iid = inv.save(self.db, None, name="Sapatilhas", kind="shoes",
                       purchase_date="2026-01-15", purchase_price=129.9)
        row = self.db.conn.execute("SELECT purchase_date, purchase_price FROM equipment_items"
                                   " WHERE id = ?", (iid,)).fetchone()
        self.assertEqual(tuple(row), ("2026-01-15", 129.9))


class TestLimits(DbCase):
    def test_device_limits_defaults_and_settings(self):
        lim = wm.device_limits(self.db)
        self.assertEqual(lim["rower_levels"], 10)
        self.assertEqual(lim["treadmill_max_kmh"], 20.0)
        self.db.set("treadmill_max_kmh", 16.0)
        self.assertEqual(wm.device_limits(self.db)["treadmill_max_kmh"], 16.0)


class TestBackupAndCli(DbCase):
    def test_new_settings_go_to_the_right_component(self):
        from velo.core import backup
        self.assertTrue(backup.BY_KEY["ecra"].settings("metrics_disabled_running"))
        for k in ("pmc_ctl0", "pmc_atl0", "pmc_synced", "rower_levels", "treadmill_max_kmh"):
            self.assertTrue(backup.BY_KEY["definicoes"].settings(k), k)
        backup.prepare(self.db)
        self.assertEqual(backup.unknown_tables(self.db), [])

    def test_import_cli(self):
        import main
        p = self.tmp / "tp.csv"
        p.write_text("Title,WorkoutType,WorkoutDay,TimeTotalInHours,TSS\nX,Run,2026-06-20,1,70\n",
                     encoding="utf-8")

        class A:
            data_dir = str(self.tmp / "d")
            importar = ("trainingpeaks", str(p))
        self.assertEqual(main.import_cli(A), 0)
        A.importar = ("xpto", str(p))
        self.assertEqual(main.import_cli(A), 2)


# =================================================================== UI


class TestUi(tg.GuiCase):
    def test_list_search_filters_as_you_type(self):
        lst = self.screen().list
        lst.set_items([Item("Alpha"), Item("Beta"), Item("Árvore")])
        lst.set_query("ar")
        self.assertEqual([i.label for i in lst.items], ["Árvore"])
        lst.set_query("")
        self.assertEqual(len(lst.items), 3)

    def test_date_picker_keys_and_typing(self):
        got = []
        pickers.pick_date(self.app, "Data", "2026-03-15", got.append)
        p = self.screen()
        self.assertIsInstance(p, pickers.DatePickerPopup)
        self.press(key.RIGHT, key.DOWN)                 # +1 dia, +1 semana
        self.assertEqual(p.sel, date(2026, 3, 23))
        self.press(key.PAGEDOWN)
        self.assertEqual(p.sel, date(2026, 4, 23))
        p.on_text("01/02/2026")
        self.press(key.ENTER)
        self.assertEqual(got, ["2026-02-01"])
        self.assertEqual(pickers.parse_date("31-12-2025"), date(2025, 12, 31))

    def test_choice_popup_picks_filtered(self):
        got = []
        self.app.push(pickers.ChoicePopup(self.app, "Tema", ["Claro", "Escuro", "Sistema"], 0,
                                          got.append))
        p = self.screen()
        self.assertTrue(p.search_active)
        p.search_set("esc")
        self.press(key.ENTER)
        self.assertEqual(got, [1])

    def test_home_has_calendar(self):
        while len(self.app.stack) > 1:
            self.app.pop()
        home = self.app.stack[0]
        self.assertIsNotNone(getattr(home, "cal", None))
        labels = [t.title_text for t in home.tiles] if hasattr(home, "tiles") else []
        self.assertNotIn("Calendário", labels)

    def test_evolution_screen_tabs(self):
        from velo.ui.evolution_screens import EvolutionScreen
        self.app.push(EvolutionScreen(self.app))
        s = self.screen()
        for tab in range(3):
            s.set_tab(tab) if hasattr(s, "set_tab") else None
            s.tab = tab
            s.enter()
            self.assertTrue(s.list.all_items)
        labels = " ".join(i.label for i in s.list.all_items)
        self.assertIn("HRV", labels)


if __name__ == "__main__":
    unittest.main()
