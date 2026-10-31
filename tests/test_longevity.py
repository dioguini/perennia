"""Modo Challenge (jogos), testes de aptidão, saúde (diário, análises,
importação), treino livre / Conditioning e o agente (pré-visualização)."""
from __future__ import annotations

import importlib
import json
import random
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import agent, fit, fitness_tests as ft, games, health  # noqa: E402
from velo.core import laps_session as ls  # noqa: E402
from velo.core import strength as st  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.core.ride import Reading  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import health_screens as hs  # noqa: E402
from velo.ui import sport_screens as ss  # noqa: E402


def make_db(tmp: Path) -> Database:
    db = Database(tmp / "perennia.db")
    db.save_athlete(Athlete(name="Teste", birth_year=1990, weight_kg=72.0, ftp_w=250,
                            lthr=165))
    return db


class HR:
    def __init__(self, bpm=140):
        self.bpm = bpm

    def reading(self):
        return Reading(hr_bpm=self.bpm)


# ===================================================================== jogos


class TestGames(unittest.TestCase):
    def play(self, g, power_fn, limit=4000):
        evs = []
        while not g.finished and g.t < limit:
            evs += g.tick(1.0, power_fn(g))
        return evs

    def test_no_target_lasts_less_than_10_seconds(self):
        for key_ in ("adaptive", "zone_hero", "warmup"):
            for seed in range(5):
                g = games.CLASSES[key_](250, 72, minutes=20, seed=seed)
                blocks = g.blocks
                self.assertTrue(all(b.seconds >= games.MIN_BLOCK_S for b in blocks),
                                (key_, [b.seconds for b in blocks]))
        self.assertEqual(games.PowerLadder.STEP_S >= games.MIN_BLOCK_S, True)

    def test_adaptive_scales_to_ftp_and_history(self):
        weak = games.AdaptiveChallenge(150, 70, minutes=30, seed=2)
        strong = games.AdaptiveChallenge(350, 70, minutes=30, seed=2)
        w = [b.pct for b in weak.blocks if b.kind == "effort"]
        s = [b.pct for b in strong.blocks if b.kind == "effort"]
        self.assertEqual(w, s)                               # o mesmo desafio relativo
        # quem tem um sprint forte no histórico recebe alvos de sprint mais altos
        sprinter = games.capacity_curve(250, {10: 900.0})
        self.assertGreater(sprinter[10], games.capacity_curve(250, None)[10])
        # o histórico curto nunca faz o desafio ficar trivial
        low = games.capacity_curve(250, {300: 100.0})
        self.assertGreaterEqual(low[300], 250 * 1.06 * 0.85)

    def test_adaptive_level_goes_up_when_you_succeed(self):
        g = games.AdaptiveChallenge(250, 72, minutes=20, seed=3, level=0.9)
        evs = self.play(g, lambda g: (g.target_w or 100) * 1.05)
        self.assertTrue(g.finished)
        self.assertGreater(g.level, 0.9)
        self.assertEqual(g.passed, g.done)
        judged = [d for k, d in evs if k == "game_judge"]
        self.assertTrue(all(d["ok"] for d in judged))
        cues = [d["text"] for k, d in evs if k == "game_cue"]
        self.assertTrue(any("Aguenta" in c for c in cues))
        self.assertTrue(any("Descansa" in c for c in cues))
        g2 = games.AdaptiveChallenge(250, 72, minutes=20, seed=3, level=0.9)
        self.play(g2, lambda g: (g.target_w or 100) * 0.7)
        self.assertLess(g2.level, 0.9)
        self.assertEqual(g2.passed, 0)

    def test_zone_hero_scores_combos_and_rings(self):
        g = games.ZoneHero(250, 72, minutes=10, bots=3, seed=1)
        self.play(g, lambda g: g.target_w or 0)
        self.assertGreater(g.score, 0)
        self.assertGreater(g.best_combo, 20)
        self.assertGreater(g.rings, 0)
        self.assertIsNotNone(g.rank)
        lazy = games.ZoneHero(250, 72, minutes=10, bots=3, seed=1)
        self.play(lazy, lambda g: 0)
        self.assertEqual(lazy.score, 0)
        self.assertEqual(lazy.rank, 4)

    def test_ladder_ends_when_you_drop(self):
        g = games.PowerLadder(250, 72, bots=4, seed=5)
        evs = self.play(g, lambda g: 330)                    # aguenta até ~130 %
        self.assertTrue(g.finished)
        self.assertTrue(any(k == "game_over" for k, _ in evs))
        self.assertGreater(g.step, 10)
        self.assertIsNotNone(g.rank)

    def test_elimination_tactics_matter(self):
        def smart(g):
            alive = g._alive()
            lead = max([g.dist] + [b.dist for b in alive])
            danger = all(b.dist > g.dist - 5 for b in alive)
            return 480 if g.next_cut - lead < 150 and danger else 230
        wins = 0
        for seed in range(6):
            g = games.Elimination(250, 72, bots=5, seed=seed)
            self.play(g, smart)
            wins += g.won is True
        self.assertGreaterEqual(wins, 3)
        g = games.Elimination(250, 72, bots=5, seed=1)
        self.play(g, lambda g: 120)                          # a passear: sai logo
        self.assertEqual(g.rank, 6)

    def test_tug_of_war(self):
        g = games.TugOfWar(250, 72, minutes=10, seed=1)
        self.play(g, lambda g: 450)
        self.assertTrue(g.won)
        g2 = games.TugOfWar(250, 72, minutes=10, seed=1)
        self.play(g2, lambda g: 50)
        self.assertFalse(g2.won)

    def test_snapshot_restore(self):
        g = games.AdaptiveChallenge(250, 72, minutes=20, seed=7)
        for _ in range(400):
            g.tick(1.0, 260)
        snap = json.loads(json.dumps(g.snapshot()))
        h = games.AdaptiveChallenge(250, 72, minutes=20, seed=7)
        h.restore(snap)
        self.assertEqual((h.idx, h.passed, h.t, len(h.blocks)), (g.idx, g.passed, g.t,
                                                                 len(g.blocks)))
        e = games.Elimination(250, 72, bots=3, seed=1)
        for _ in range(30):
            e.tick(1.0, 250)
        e2 = games.Elimination(250, 72, bots=3, seed=1)
        e2.restore(json.loads(json.dumps(e.snapshot())))
        self.assertAlmostEqual(e2.bots[0].dist, e.bots[0].dist)


class TestGameInRide(tg.GuiCase):
    def test_adaptive_challenge_ride(self):
        self.pick("Challenge")
        self.assertIsInstance(self.screen(), ss.ChallengeMenu)
        self.pick("Desafio adaptativo")
        setup = self.screen()
        self.assertIsInstance(setup, ss.GameSetup)
        self.select("Duração")
        self.press(key.RIGHT)
        self.assertEqual(setup.minutes, 45)
        self.press(key.LEFT, key.LEFT)                         # volta a 20
        self.assertEqual(setup.minutes, 20)
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        game = ride.engine.game
        self.assertIsNotNone(game)
        self.assertTrue(game.erg)
        for _ in range(int(400 / 0.5)):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.assertEqual(ride.engine.state.target_power_w, game.target_w)
        self.assertTrue(ride.hud._chase_title.text)
        self.assertEqual(ride.hud.board_panel.title.text, "Desafio adaptativo")
        self.app._on_draw()
        self.press(key.F10, key.ENTER)
        summ = self.screen()
        self.assertIsInstance(summ, app_mod.SummaryScreen)
        self.assertTrue(any("Desafio adaptativo" in i.label for i in summ.list.items))
        board = games.leaderboard(self.app.db, "adaptive")
        self.assertEqual(len(board.rows), 1)
        self.assertNotEqual(self.app.db.get("adaptive_level"), None)

    def test_elimination_with_bots_on_the_board(self):
        self.pick("Challenge")
        self.pick("Eliminação")
        self.pick("Começar")
        ride = self.screen()
        for _ in range(60):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        names = [r.label for r in ride.engine.live_board().rows]
        self.assertEqual(len(names), 6)
        self.assertIn("Tu", names)


# ================================================================== testes


class TestFitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)
        ft.seed(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_catalog_for_each_sport(self):
        for sport in ft.SPORTS:
            self.assertGreaterEqual(len(ft.tests(self.db, sport)), 4, sport)
        names = [x["name"] for x in ft.tests(self.db, "longevity")]
        self.assertTrue(any("preensão" in n for n in names))
        self.assertTrue(any("Elevações em 1 minuto" == n for n in names))
        ft.seed(self.db)                                       # uma vez só
        self.assertEqual(len(ft.tests(self.db, "longevity")), len(names))

    def test_results_best_and_trend(self):
        push = next(x for x in ft.tests(self.db, "longevity") if x["name"] == "Flexões máximas")
        ft.add_result(self.db, push["id"], 30, done_on="2026-09-01")
        ft.add_result(self.db, push["id"], 36, done_on="2026-10-01", notes="boa técnica")
        x = next(x for x in ft.tests(self.db, "longevity") if x["id"] == push["id"])
        self.assertEqual((x["last"], x["best"], x["trend"], x["n"]), (36, 36, "up", 2))
        run = next(x for x in ft.tests(self.db, "running") if x["name"] == "5 km")
        ft.add_result(self.db, run["id"], 1500, done_on="2026-09-01")
        ft.add_result(self.db, run["id"], 1450, done_on="2026-10-01")
        r = next(x for x in ft.tests(self.db, "running") if x["id"] == run["id"])
        self.assertEqual((r["best"], r["trend"]), (1450, "up"))      # mais baixo é melhor
        self.assertEqual(ft.fmt_value(1450, "s"), "24:10")

    def test_custom_and_edit(self):
        tid = ft.save_test(self.db, None, sport="longevity", name="Burpees em 2 min",
                           unit="reps", duration_s=120)
        self.assertIn("Burpees em 2 min", [x["name"] for x in ft.tests(self.db, "longevity")])
        ft.save_test(self.db, tid, sport="longevity", name="Burpees em 3 min", unit="reps",
                     duration_s=180)
        self.assertEqual(ft.test(self.db, tid)["duration_s"], 180)
        ft.set_active(self.db, tid, False)
        self.assertNotIn(tid, [x["id"] for x in ft.tests(self.db, "longevity")])

    def test_cycling_protocols(self):
        from velo.core import ftp
        for proto in ftp.TEST_PROTOCOLS:
            wk = ftp.build(proto, 250)
            self.assertTrue(wk.steps)
            self.assertIsNotNone(ft.by_protocol(self.db, proto))
        series = [150.0] * 600 + [900.0] * 6 + [150.0] * 300
        self.assertEqual(ftp.estimate("sprint", series)[1], 900)
        self.assertAlmostEqual(ft.vo2max_from_5min(300, 72), 10.8 * 300 / 72 + 7)
        ft.record_protocol(self.db, "sprint", 900, None)
        t_ = ft.by_protocol(self.db, "sprint")
        self.assertEqual(ft.results(self.db, t_["id"])[0]["value"], 900)


class TestTestsGui(tg.GuiCase):
    def test_longevity_test_with_timer(self):
        self.press(key.ESCAPE)
        self.pick("Saúde")
        self.pick("Testes de longevidade")
        self.pick("Flexões em 1 minuto")
        self.assertIsInstance(self.screen(), hs.TestDetail)
        self.pick("Fazer o teste")
        run = self.screen()
        self.assertIsInstance(run, hs.TestRunScreen)
        self.press(key.SPACE)
        for _ in range(130):
            self.app._tick(0.5)
        self.assertFalse(run.running)                      # o minuto acabou
        self.select("Resultado")
        self.app._on_text("42")
        self.pick("Guardar")
        self.assertIsInstance(self.screen(), hs.TestDetail)
        self.assertTrue(any(i.value == "42 reps" for i in self.screen().list.items))

    def test_stopwatch_gives_the_time(self):
        self.press(key.ESCAPE)
        self.pick("Saúde")
        self.pick("Testes de longevidade")
        self.pick("Suspensão na barra")
        self.pick("Fazer o teste")
        run = self.screen()
        self.press(key.SPACE)
        for _ in range(91):
            self.app._tick(0.5)
        self.press(key.SPACE)
        self.assertAlmostEqual(run.value, 45.5, delta=0.6)

    def test_rowing_tests_from_coming_soon(self):
        self.press(key.ESCAPE)
        self.pick("Remo")
        self.pick("Testes")
        self.assertIsInstance(self.screen(), hs.TestsMenu)
        self.assertTrue(any("2000 m" in i.label for i in self.screen().list.items))
        self.pick("Novo teste")
        ed = self.screen()
        self.type("Remo 10 min")
        self.pick("Guardar")
        self.assertTrue(any("Remo 10 min" in i.label for i in self.screen().list.items))

    def test_cycling_5min_test_records_vo2max(self):
        self.pick("Testes")
        self.pick("5 minutos")
        self.pick("Fazer o teste")
        self.pick("Sem rota")
        self.pick("Começar")
        ride = self.screen()
        for _ in range(int(1500 / 1.0)):
            self.app.hub.tick(1.0)
            ride.update(1.0)
        self.press(key.F10, key.ENTER)
        summ = self.screen()
        self.assertTrue(any("VO2máx" in (i.value or "") for i in summ.list.items))
        t_ = ft.by_protocol(self.app.db, "5min")
        res = ft.results(self.app.db, t_["id"])
        self.assertEqual(len(res), 1)
        self.assertIn("vo2max", json.loads(res[0]["extra"]))


# ================================================================== saúde


class TestHealthCore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)
        health.seed(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def m(self, key_):
        return health.metric_by_key(self.db, key_)

    def test_values_notes_and_kinds(self):
        d = date(2026, 10, 29)
        health.set_value(self.db, d, self.m("sweets_lunch")["id"], True)
        health.set_value(self.db, d, self.m("lunch")["id"], "bacalhau com grão")
        health.set_value(self.db, d, self.m("weight")["id"], 71.8)
        health.set_note(self.db, d, self.m("weight")["id"], "depois do treino")
        health.set_value(self.db, d, self.m("weight")["id"], 71.6)       # a nota fica
        v = health.values_for(self.db, d)
        self.assertEqual(v[self.m("sweets_lunch")["id"]]["value"], 1.0)
        self.assertEqual(v[self.m("lunch")["id"]]["value"], "bacalhau com grão")
        self.assertEqual(v[self.m("weight")["id"]]["notes"], "depois do treino")
        self.assertEqual(health.fmt(self.m("weight"), 71.6), "71.6 kg")
        self.assertEqual(health.fmt(self.m("sweets_lunch"), 1.0), "sim")
        done, total = health.completeness(self.db, d)
        self.assertEqual(done, 3)
        self.assertGreater(total, 20)

    def test_custom_metric(self):
        mid = health.save_metric(self.db, None, name="Comi sobremesa?", kind="bool",
                                 group="food")
        self.assertEqual(health.metric(self.db, mid)["key"], "comi_sobremesa")
        cid = health.save_metric(self.db, None, name="Pequeno-almoço", kind="choice",
                                 choices=["aveia", "ovos", "pão"])
        self.assertEqual(health.metric(self.db, cid)["choices"], ["aveia", "ovos", "pão"])

    def test_labs(self):
        rid = health.save_lab_report(self.db, None, done_on="2026-05-10", lab="Lab X")
        health.save_lab_result(self.db, None, rid, marker="Colesterol LDL", value=128,
                               unit="mg/dL", ref_high=115)
        health.save_lab_result(self.db, None, rid, marker="Vitamina D (25-OH)", value=34,
                               unit="ng/mL", ref_low=30)
        health.save_lab_report(self.db, rid, done_on="2026-05-10", lab="Lab X",
                               doctor_feedback="Repetir o perfil lipídico em 6 meses.")
        reps = health.lab_reports(self.db)
        self.assertEqual(reps[0]["out_of_range"], 1)
        self.assertIn("6 meses", reps[0]["doctor_feedback"])
        res = health.lab_results(self.db, rid)
        self.assertEqual([health.flag(x) for x in res], ["high", ""])
        rid2 = health.save_lab_report(self.db, None, done_on="2026-10-10")
        health.save_lab_result(self.db, None, rid2, marker="Colesterol LDL", value=110,
                               unit="mg/dL", ref_high=115)
        self.assertEqual([x["value"] for x in health.marker_history(self.db, "Colesterol LDL")],
                         [128, 110])

    def test_import_hrv4training_and_garmin(self):
        csv_ = self.tmp / "My_Measurements_Android.csv"
        csv_.write_text("date,HR,rMSSD,HRV4T_Recovery_Points,extra\n"
                        "2026-10-27,52,68.5,7.2,1\n2026-10-28,50,72,8,2\n")
        rep = health.import_file(self.db, csv_)
        self.assertEqual(rep["days"], 2)
        self.assertEqual(rep["ignored"], ["extra"])
        v = health.values_for(self.db, "2026-10-28")
        self.assertEqual(v[self.m("hrv_rmssd")["id"]]["value"], 72)
        self.assertEqual(v[self.m("rhr")["id"]]["source"], "hrv4training")
        js = self.tmp / "UDSFile_2026.json"
        js.write_text(json.dumps([{"calendarDate": "2026-10-28", "totalSteps": 9876,
                                   "restingHeartRate": 49, "sleepTimeSeconds": 27000}]))
        rep = health.import_file(self.db, js)
        v = health.values_for(self.db, "2026-10-28")
        self.assertEqual(v[self.m("steps")["id"]]["value"], 9876)
        self.assertEqual(v[self.m("sleep_hours")["id"]]["value"], 7.5)
        self.assertEqual(v[self.m("rhr")["id"]]["value"], 49)      # o Garmin por cima
        rep = health.import_file(self.db, csv_, create_unknown=True)
        self.assertEqual(rep["created"], ["extra"])


class TestHealthGui(tg.GuiCase):
    def go(self):
        self.press(key.ESCAPE)
        self.pick("Saúde")
        self.assertIsInstance(self.screen(), hs.HealthMenu)

    def test_daily_log(self):
        self.go()
        self.pick("Diário de hoje")
        log = self.screen()
        self.assertIsInstance(log, hs.DailyLogScreen)
        db = self.app.db
        today = date.today()
        self.select("Comi doces ao almoço")
        self.press(key.RIGHT)                                 # sim
        self.select("Energia")
        self.press(key.RIGHT)                                 # 3
        self.press(key.RIGHT)                                 # 4
        self.select("Peso")
        self.app._on_text("71,8")
        self.press(key.N)
        note = self.screen()
        self.assertIsInstance(note, hs.TextEditScreen)
        self.app._on_text("em jejum")
        self.press(key.ENTER)
        self.app._on_text("balança nova")
        self.press(key.ESCAPE)
        self.assertIs(self.screen(), log)
        self.select("O que almocei")
        self.type("sopa e frango")
        self.select("Confeção do almoço")
        self.press(key.RIGHT)
        vals = {health.metric(db, k)["key"]: v for k, v in health.values_for(db, today).items()}
        self.assertEqual(vals["sweets_lunch"]["value"], 1.0)
        self.assertEqual(vals["energy"]["value"], 4)
        self.assertEqual(vals["weight"]["value"], 71.8)
        self.assertEqual(vals["weight"]["notes"], "em jejum\nbalança nova")
        self.assertEqual(vals["lunch"]["value"], "sopa e frango")
        self.assertEqual(vals["lunch_cooking"]["value"], "grelhado")
        self.select("Dia")
        self.press(key.LEFT)
        self.assertEqual(log.day, today - timedelta(days=1))
        self.press(key.RIGHT, key.RIGHT)                     # não passa de hoje
        self.assertEqual(log.day, today)

    def test_labs_flow_with_doctor_feedback(self):
        self.go()
        self.pick("Análises clínicas")
        self.pick("Nova análise")
        ed = self.screen()
        self.assertIsInstance(ed, hs.LabReportEditor)
        self.select("Data das análises")
        self.app._on_text("2026-10-15")
        self.assertEqual(ed.done_on, "2026-10-15")
        self.pick("Adicionar resultado")
        self.pick("Colesterol LDL")
        res = self.screen()
        self.assertIsInstance(res, hs.LabResultEditor)
        self.select("Valor")
        self.app._on_text("131")
        self.pick("Guardar")
        self.assertIs(self.screen(), ed)
        self.assertTrue(any("LDL ▲" in i.label for i in ed.list.items))
        self.pick("Comentário do médico")
        self.app._on_text("Repetir em 3 meses.")
        self.press(key.ESCAPE)
        self.pick("Guardar")
        reps = health.lab_reports(self.app.db)
        self.assertEqual(reps[0]["done_on"], "2026-10-15")
        self.assertEqual(reps[0]["doctor_feedback"], "Repetir em 3 meses.")

    def test_metrics_manager_and_trend(self):
        self.go()
        self.pick("Métricas do diário")
        self.pick("Nova métrica")
        self.type("Comi fruta")
        self.pick("Guardar")
        self.assertTrue(any("Comi fruta" in i.label for i in self.screen().list.items))
        self.select("Passos")
        self.press(key.A)                                       # desligar
        self.assertFalse(health.metric_by_key(self.app.db, "steps")["active"])
        self.press(key.ESCAPE)
        db = self.app.db
        mid = health.metric_by_key(db, "sleep_hours")["id"]
        for k in range(10):
            health.set_value(db, date.today() - timedelta(days=k), mid, 7 + k % 3 * 0.5)
        self.pick("Tendências")
        trend = self.screen()
        self.assertTrue(trend.chart.points)
        self.assertIn("média", trend.summary.text)

    def test_import_screen(self):
        imports = Path(self.tmp) / "imports"
        imports.mkdir(exist_ok=True)
        (imports / "My_Measurements.csv").write_text("date,rMSSD\n2026-10-28,70\n")
        self.go()
        self.pick("Importar dados")
        self.pick("My_Measurements.csv")
        self.assertEqual(self.screen().last_report["values"], 1)


# ===================================================== treino livre / conditioning


class TestLapSession(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)
        st.seed(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_conditioning_distances_and_fit(self):
        s = ls.LapSession(self.db, self.db.athlete(), "conditioning", sensors=HR(),
                          out_dir=self.tmp)
        s.start_lap("treadmill")
        s.set_field("speed_kmh", 12)
        s.set_field("incline_pct", 1)
        for _ in range(300):
            s.update(1)
        s.set_field("odometer_km", 1.0)
        s.start_lap("rest")
        for _ in range(60):
            s.update(1)
        ex = next(e for e in st.exercises(self.db) if e["name"] == "Kettlebell swing")
        s.start_lap("strength", ex)
        s.set_field("reps", 20)
        s.set_field("load_kg", 24)
        s.set_field("rpe", 8)
        for _ in range(45):
            s.update(1)
        s.start_lap("treadmill")
        self.assertEqual(s.current.speed_kmh, 12)            # copia a última volta
        for _ in range(300):
            s.update(1)
        s.set_field("odometer_km", 2.1)
        self.assertEqual([lp.distance_km for lp in s.laps if lp.kind == "treadmill"],
                         [1.0, 1.1])
        r = s.finish()
        self.assertAlmostEqual(r["distance_km"], 2.1)
        self.assertEqual(r["total_sets"], 1)
        self.assertEqual(r["volume_kg"], 480)
        msgs = fit.read_messages(r["fit_path"])
        laps = [v for g, v in msgs if g == fit.MSG_LAP]
        self.assertEqual(len(laps), 4)
        self.assertEqual(laps[0][9], 100000)                  # 1 km, escala 100
        sets = [v for g, v in msgs if g == fit.MSG_SET]
        self.assertEqual(sum(1 for v in sets if v.get(5) == 1), 1)
        # a série conta para as estatísticas da força
        prog = st.exercise_progress(self.db, ex["id"])
        self.assertEqual(prog[0]["reps"], 20)

    def test_toggle_free_session_and_recovery(self):
        s = ls.LapSession(self.db, self.db.athlete(), "free", sensors=HR())
        ex = next(e for e in st.exercises(self.db) if e["name"] == "Supino com barra")
        s.start_lap("strength", ex)
        s.set_field("reps", 8)
        s.set_field("load_kg", 60)
        for _ in range(30):
            s.update(1)
        s.toggle()                                           # → descanso
        self.assertEqual(s.current.kind, "rest")
        for _ in range(60):
            s.update(1)
        s.toggle()                                           # → supino outra vez
        self.assertEqual((s.current.kind, s.current.name, s.current.load_kg),
                         ("strength", "Supino com barra", 60))
        for _ in range(20):
            s.update(1)
        s.suspend()
        cp = self.db.checkpoint(s.session_id)
        self.assertEqual(cp["sport"], "strength_laps")
        again = ls.LapSession(self.db, self.db.athlete(), "free", resume=cp)
        self.assertEqual(len(again.laps), 3)
        self.assertTrue(again.paused)
        self.assertIsNone(again.current)                     # a aberta fechou-se
        r = again.finish()
        self.assertEqual(r["total_sets"], 2)
        self.assertEqual(self.db.checkpoints(), [])


class TestLapSessionGui(tg.GuiCase):
    def test_conditioning_plan_first_then_start(self):
        from velo.ui import gym_screens as gs
        from velo.ui import hub_screens as hs_
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Conditioning")
        self.assertIsInstance(self.screen(), gs.ModalityScreen)
        self.pick("Treino livre")
        plan = self.screen()
        self.assertIsInstance(plan, gs.LapPlanEditor)
        self.pick("+ Volta: Passadeira")
        self.pick("+ Volta: Força")
        self.assertIsInstance(self.screen(), hs_.ExerciseInventory)
        self.pick("Kettlebell swing")
        self.assertIs(self.screen(), plan)
        self.pick("+ Volta: Descanso")
        self.assertEqual([i["kind"] for i in plan.items], ["treadmill", "strength", "rest"])
        self.pick("Começar")                                   # → opções (auto lap)
        opts = self.screen()
        self.assertEqual(opts.list.items[1].value, "desligado")  # auto lap desligado
        self.pick("Começar")
        scr = self.screen()
        self.assertIsInstance(scr, ss.LapSessionScreen)
        for _ in range(20):
            self.app._tick(0.5)
        self.assertEqual(scr.session.t, 0.0)                    # nada conta antes de começar
        self.pick("Volta do plano")
        self.assertEqual(scr.session.current.kind, "treadmill")
        self.select("Velocidade")
        self.app._on_text("11,5")
        for _ in range(60):
            self.app._tick(0.5)
        self.assertAlmostEqual(scr.session.t, 30.0, delta=1)
        self.select("Total no visor")
        self.app._on_text("0,48")
        self.assertAlmostEqual(scr.session.current.distance_km, 0.48)
        self.press(key.SPACE)                                   # volta seguinte do plano
        self.assertEqual(scr.session.current.kind, "strength")
        self.assertEqual(scr.session.current.name, "Kettlebell swing")
        self.press(key.SPACE)
        self.assertEqual(scr.session.current.kind, "rest")
        self.app._on_draw()
        self.press(key.ESCAPE)
        self.assertTrue(any("sem guardar" in i.label for i in scr.list.items))
        self.pick("Sim")
        summ = self.screen()
        self.assertIsInstance(summ, ss.LapSummaryScreen)
        self.assertTrue(Path(summ.result["fit_path"]).exists())
        self.pick("Fechar")
        self.assertIsInstance(self.screen(), gs.GymHub)

    def test_free_laps_discard_leaves_nothing(self):
        scr = ss.LapSessionScreen(self.app, "free")
        self.app.push(scr)
        self.pick("Nova volta: Descanso")
        for _ in range(10):
            self.app._tick(0.5)
        sid = scr.session.session_id
        self.press(key.ESCAPE)
        self.pick("sem guardar")
        row = self.app.db.conn.execute("SELECT * FROM strength_sessions WHERE id = ?",
                                       (sid,)).fetchone()
        self.assertIsNone(row)


# ================================================================== agente


class TestAgent(tg.GuiCase):
    def test_f1_and_f2_show_what_would_be_sent(self):
        self.pick("Gráficos e análise")
        stats_screen = self.screen()
        self.press(key.F1)
        ag = self.screen()
        self.assertIsInstance(ag, hs.AgentScreen)
        self.assertEqual(ag.request["content"]["pagina"]["ecra"], "StatsScreen")
        self.assertIn("não está ligado", ag.list.items[0].label)
        self.press(key.ESCAPE)
        self.assertIs(self.screen(), stats_screen)
        self.press(key.F2)
        ctx = self.screen().request["content"]["contexto"]
        self.assertIn("atleta", ctx)
        self.assertEqual(ctx["atleta"]["ftp_w"], 250)

    def test_sharing_categories_are_respected(self):
        db = self.app.db
        health.seed(db)
        health.set_value(db, date.today(), health.metric_by_key(db, "lunch")["id"], "pizza")
        db.set("agent_share", ["training"])
        ctx = agent.athlete_context(db)
        self.assertNotIn("diario", ctx)
        db.set("agent_share", list(agent.CATEGORIES))
        ctx = agent.athlete_context(db)
        self.assertIn("O que almocei", ctx["diario"])

    def test_no_agent_during_a_ride(self):
        self.pick("Pedalar")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        self.press(key.F1)
        self.assertIs(self.screen(), ride)


if __name__ == "__main__":
    unittest.main()
