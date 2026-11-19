"""Ronda 25: o Conditioning como agregador de remo, passadeira e ginásio — tags
(`Conditioning` + uma por desporto), um .fit total e um por desporto, as partes por desporto
na base de dados e a contagem por desporto sem perder a noção do Conditioning."""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import adhoc, backup, fit, i18n, tags  # noqa: E402
from perennia.core import laps_session as ls  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")

# o exemplo do pedido: 5 remo, 10 passadeira, 15 ginásio, 5 passadeira, 10 ginásio,
# 3 passadeira, 10 ginásio (minutos)
EXAMPLE = [("rowing", 5), ("treadmill", 10), ("strength", 15), ("treadmill", 5),
           ("strength", 10), ("treadmill", 3), ("strength", 10)]


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))
        i18n.set_language("pt")

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def session(self, blocks=EXAMPLE, mode="conditioning", plan=None, hr=140) -> dict:
        class HR:
            def reading(self_):
                return type("R", (), {"hr_bpm": hr})()
        s = ls.LapSession(self.db, self.db.athlete(), mode, sensors=HR(),
                          out_dir=self.tmp / "strength", plan=plan)
        s.start()
        for kind, minutes in blocks:
            s.start_lap(kind)
            if kind == "treadmill":
                s.set_field("distance_km", round(minutes * 0.18, 2))
            if kind == "rowing":
                s.set_field("distance_km", round(minutes * 0.25, 2))
            for _ in range(int(minutes * 60)):
                s.update(1.0)
        self.engine = s
        return s.finish()


class TestPartsAndFits(Tmp):
    def test_the_example_gives_four_fits_total_rowing_running_gym(self):
        res = self.session()
        files = sorted(p.name for p in (self.tmp / "strength").glob("*.fit"))
        self.assertEqual(len(files), 4, files)
        self.assertTrue(any(f.endswith("_rowing.fit") for f in files))
        self.assertTrue(any(f.endswith("_running.fit") for f in files))
        self.assertTrue(any(f.endswith("_gym.fit") for f in files))
        by = {p["sport"]: p for p in res["parts"]}
        self.assertEqual(list(by), ["rowing", "running", "gym"])         # pela ordem feita
        self.assertEqual(by["rowing"]["timer_s"], 5 * 60)
        self.assertEqual(by["running"]["timer_s"], 18 * 60)               # 10 + 5 + 3
        self.assertEqual(by["gym"]["timer_s"], 35 * 60)                   # 15 + 10 + 10
        self.assertEqual((by["rowing"]["blocks"], by["running"]["blocks"],
                          by["gym"]["blocks"]), (1, 3, 3))
        self.assertAlmostEqual(by["running"]["distance_km"], 1.8 + 0.9 + 0.54, places=2)
        # a carga das partes soma a da sessão (nada contado duas vezes)
        self.assertAlmostEqual(sum(p["load"] for p in res["parts"]), res["load"], places=3)

    def test_each_part_fit_has_its_sport_and_only_its_time(self):
        res = self.session()
        by = {p["sport"]: p for p in res["parts"]}
        for sport, (fsport, fsub) in ls.PART_FIT.items():
            msgs = fit.read_messages(by[sport]["fit_path"])
            sess = [f for m, f in msgs if m == 18][0]
            self.assertEqual((sess[5], sess[6]), (fsport, fsub), sport)      # sport, sub_sport
            self.assertAlmostEqual(sess[8] / 1000.0, by[sport]["timer_s"], delta=1)  # timer
            laps = [f for m, f in msgs if m == 19]
            self.assertEqual(len(laps), by[sport]["laps"], sport)
        # a passadeira esteve parada entre blocos: há eventos de stop/start no meio
        msgs = fit.read_messages(by["running"]["fit_path"])
        ev = Counter(f.get(1) for m, f in msgs if m == 21)
        self.assertGreaterEqual(ev[0], 3)                                     # 3 arranques
        # o total: treino cardio, com as voltas todas
        tot = fit.read_messages(res["fit_path"])
        sess = [f for m, f in tot if m == 18][0]
        self.assertEqual((sess[5], sess[6]), (fit.SPORT_TRAINING,
                                              fit.SUB_SPORT_CARDIO_TRAINING))
        self.assertEqual(len([1 for m, _ in tot if m == 19]), len(EXAMPLE))

    def test_parts_are_saved_and_rest_goes_with_the_block_before(self):
        res = self.session([("rest", 1), ("treadmill", 2), ("rest", 1), ("strength", 3),
                            ("rest", 2)])
        got = {p["sport"]: p["timer_s"] for p in ls.parts(self.db, res["session_id"])}
        self.assertEqual(got, {"running": 4 * 60, "gym": 5 * 60})        # 1.º descanso → a seguir
        self.assertEqual(ls.lap_sports([type("L", (), {"kind": k})() for k in
                                        ("rest", "cardio", "rowing", "rest")]),
                         ["gym", "gym", "rowing", "rowing"])

    def test_free_training_mode_is_not_split(self):
        res = self.session([("strength", 2), ("treadmill", 2)], mode="free")
        self.assertEqual(res["parts"], [])
        self.assertEqual(len(list((self.tmp / "strength").glob("*.fit"))), 1)
        self.assertEqual(tags.load(self.db, "strength", res["session_id"])["sport"], ["Gym"])


class TestTags(Tmp):
    def test_conditioning_is_mandatory_and_one_tag_per_sport(self):
        res = self.session()
        info = tags.load(self.db, "strength", res["session_id"])
        self.assertEqual(info["activity"], ["Conditioning", "Free Session"])
        self.assertEqual(info["sport"], ["Rowing", "Running", "Gym"])
        self.assertNotIn("Indoor Strength", info["session"])
        text = tags.fit_text(res["tags"])
        self.assertTrue(text.startswith("Conditioning · Free Session · Rowing · Running · Gym"),
                        text)

    def test_a_plan_is_a_workout_and_only_the_sports_used_are_tagged(self):
        plan = [{"kind": "treadmill", "seconds": 60}, {"kind": "strength", "seconds": 120}]
        res = self.session([("treadmill", 1), ("strength", 2)], plan=plan)
        info = tags.load(self.db, "strength", res["session_id"])
        self.assertEqual(info["activity"], ["Conditioning", "Workout"])
        self.assertEqual(info["sport"], ["Running", "Gym"])

    def test_the_popup_cannot_drop_the_automatic_tags(self):
        info = tags.resolve(self.db, "strength", "x", {"activity": [], "sport": [],
                                                       "custom": ["Running", "Mine"]},
                            activity=("free", None, "conditioning"), sports=["Running"])
        self.assertEqual(info["activity"], ["Conditioning", "Free Session"])
        self.assertEqual(info["sport"], ["Running"])
        self.assertEqual(info["custom"], ["Mine"])

    def test_every_other_session_gets_its_sport_tag(self):
        d = tags.defaults(self.db, "cycling")
        self.assertEqual(d["sport"], ["Cycling"])
        self.assertEqual(tags.defaults(self.db, "running")["sport"], ["Running"])
        self.assertEqual(tags.defaults(self.db, "strength")["sport"], ["Gym"])


class TestCounting(Tmp):
    def make_history(self):
        """1 Conditioning (remo + passadeira + ginásio), 1 corrida sozinha, 1 ginásio sozinho."""
        self.session()
        self.cond_id = self.engine.session_id
        c = self.db.conn
        c.execute("INSERT INTO endurance_sessions(id, sport, name, status, started_at,"
                  " elapsed_s, moving_s, distance_m) VALUES ('run1', 'running', 'Corrida',"
                  " 'completed', '2026-11-01T08:00:00Z', 1800, 1800, 5000)") \
            if self._has("endurance_sessions") else None
        c.execute("INSERT INTO strength_sessions(id, name, status, started_at, elapsed_s,"
                  " mode) VALUES ('gym1', 'Força', 'completed', '2026-11-02T08:00:00Z',"
                  " 2400, 'plan')")
        c.commit()

    def _has(self, table: str) -> bool:
        if table == "endurance_sessions":
            from perennia.core import endurance as en
            en.ensure(self.db)
        return bool(self.db.conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?",
                                         (table,)).fetchone())

    def test_by_sport_source_counts_each_sport_and_keeps_the_conditioning_flag(self):
        self.make_history()
        rows = adhoc.load(self.db, "by_sport")
        count = Counter((r["sport"], r["in_conditioning"]) for r in rows)
        self.assertEqual(count[("Corrida", "Sim")], 1)
        self.assertEqual(count[("Corrida", "Não")], 1)
        self.assertEqual(count[("Remo", "Sim")], 1)
        self.assertEqual(count[("Ginásio", "Sim")], 1)
        self.assertEqual(count[("Ginásio", "Não")], 1)
        run_in = next(r for r in rows if r["sport"] == "Corrida" and r["in_conditioning"] == "Sim")
        self.assertEqual(run_in["duration_min"], 18.0)
        self.assertEqual(run_in["blocks"], 3)
        # o tempo total não se repete: as partes somam a sessão de Conditioning
        sessions = adhoc.load(self.db, "sessions")
        cond = [r for r in sessions if r["sport"] == "Conditioning"]
        self.assertEqual(len(cond), 1)
        self.assertEqual(cond[0]["sports"], "Rowing + Running + Gym")
        parts_min = sum(r["duration_min"] for r in rows if r["in_conditioning"] == "Sim")
        self.assertAlmostEqual(parts_min, cond[0]["duration_min"], delta=0.1)

    def test_tag_queries_count_conditioning_and_each_sport(self):
        self.make_history()
        tags.backfill(self.db)
        n = lambda w, mode="all": len(tags.sessions_with(self.db, w, mode))   # noqa: E731
        self.assertEqual(n("Conditioning"), 1)
        self.assertEqual(n("Running"), 2)                       # a corrida + o Conditioning
        self.assertEqual(n("Running, Conditioning"), 1)
        self.assertEqual(n("Gym"), 2)

    def test_old_conditioning_sessions_get_parts_and_tags(self):
        res = self.session([("treadmill", 2), ("strength", 3)])
        sid = res["session_id"]
        c = self.db.conn
        c.execute("DELETE FROM conditioning_parts WHERE session_id = ?", (sid,))
        c.execute("DELETE FROM session_tags WHERE session_id = ? AND (kind = 'sport' OR tag ="
                  " 'Conditioning')", (sid,))
        c.commit()
        tags.backfill(self.db)
        self.assertEqual([p["sport"] for p in ls.parts(self.db, sid)], ["running", "gym"])
        info = tags.load(self.db, "strength", sid)
        self.assertIn("Conditioning", info["activity"])
        self.assertEqual(info["sport"], ["Running", "Gym"])
        self.assertEqual(tags.backfill(self.db), 0)

    def test_parts_are_in_the_backup(self):
        self.assertIn("conditioning_parts", backup.BY_KEY["sessoes"].tables)


class TestPlans(Tmp):
    def test_plan_by_sport_and_gym_block(self):
        items = [{"kind": "rowing", "seconds": 300}, {"kind": "treadmill", "seconds": 600},
                 {"kind": "strength", "seconds": 900}, {"kind": "rest", "seconds": 60},
                 {"kind": "treadmill", "seconds": 300}]
        self.assertEqual(ls.plan_by_sport(items),
                         {"rowing": 300, "running": 900, "gym": 960})

    def test_a_timed_gym_block_keeps_counting_across_exercises(self):
        plan = [{"kind": "strength", "seconds": 120}, {"kind": "treadmill", "seconds": 60}]
        s = ls.LapSession(self.db, self.db.athlete(), "conditioning",
                          out_dir=self.tmp / "strength", plan=plan)
        s.start_planned()
        for _ in range(50):
            s.update(1.0)
        s.start_lap("rest")                         # um descanso dentro do bloco
        for _ in range(20):
            s.update(1.0)
        s.start_lap("strength")                     # outro exercício
        for _ in range(49):
            s.update(1.0)
        self.assertEqual(s.current.kind, "strength")
        for _ in range(3):
            s.update(1.0)
        self.assertEqual(s.current.kind, "treadmill")  # os 2 min do bloco acabaram
        s.start_lap("rowing")                       # outro desporto: o plano fica à espera
        self.assertIsNone(s._lap_plan)


class TestUI(tg.GuiCase):
    def test_summary_lists_parts_with_their_fit(self):
        from perennia.ui.sport_screens import LapSummaryScreen
        tmp = Path(tempfile.mkdtemp())
        try:
            s = ls.LapSession(self.app.db, self.app.db.athlete(), "conditioning",
                              out_dir=tmp)
            s.start()
            for kind in ("rowing", "treadmill", "strength"):
                s.start_lap(kind)
                for _ in range(30):
                    s.update(1.0)
            res = s.finish()
            scr = LapSummaryScreen(self.app, res)
            self.app.push(scr)
            labels = [i.label for i in scr.list.items]
            self.assertIn("Por desporto · um .fit cada", labels)
            details = " ".join(i.detail or "" for i in scr.list.items)
            for sport in ("rowing", "running", "gym"):
                self.assertIn(f"_{sport}.fit", details)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_running_history_shows_conditioning_parts(self):
        from perennia.ui.gym_screens import conditioning_history_items
        tmp = Path(tempfile.mkdtemp())
        try:
            s = ls.LapSession(self.app.db, self.app.db.athlete(), "conditioning", out_dir=tmp)
            s.start()
            s.start_lap("treadmill")
            for _ in range(60):
                s.update(1.0)
            s.finish()
            items = conditioning_history_items(self.app, "running")
            self.assertEqual(items[0].label, "Dentro de um Conditioning")
            self.assertEqual(len(items), 2)
            self.assertEqual(conditioning_history_items(self.app, "rowing"), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_plan_editor_shows_time_per_sport_and_gym_block(self):
        from perennia.ui import gym_screens as gs
        scr = gs.LapPlanEditor(self.app, None, draft=True)
        self.app.push(scr)
        scr._add("rowing")
        scr._add("gym_block")
        self.assertIn("Remo 5:00", scr.chrome.subtitle.text)
        self.assertIn("Ginásio 15:00", scr.chrome.subtitle.text)
        self.assertIn("+ Bloco de ginásio (tempo)", [i.label for i in scr.list.items])
        self.assertEqual(scr.value_of(scr.items[-1]), "15:00")

    def test_conditioning_menu_has_a_free_session_without_plan(self):
        from perennia.ui import session_setup as ss
        src = Path(ss.__file__).read_text(encoding="utf-8")
        self.assertIn('gs.start_laps(a, "conditioning", None)', src)


if __name__ == "__main__":
    unittest.main()
