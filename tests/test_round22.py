"""Ronda 22: Segment Pace e Segment KOM no Challenge do ciclismo (plano de watts por secções,
guia com a diferença ao vivo, ERG, viabilidade, tabela por secção e histórico por segmento)."""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import climbs, games, gpx, options, physics  # noqa: E402
from perennia.core import segment_pace as sp  # noqa: E402
from perennia.core import segments as sg  # noqa: E402
from perennia.core.db import Athlete, Database, RoutePoint  # noqa: E402
from perennia.core.ride import RideEngine  # noqa: E402
from perennia.core.route_index import RouteIndex  # noqa: E402
from perennia.io.hub import SensorHub  # noqa: E402
from perennia.io.sim import SimulatedTrainer  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
GPX = Path(__file__).parent / "teste.gpx"
DT = 0.25


def synthetic(profile, step=5.0) -> RouteIndex:
    """Uma rota por troços (comprimento m, inclinação %): para testar a física."""
    pts, d, ele = [], 0.0, 100.0
    pts.append(RoutePoint(0, 0, 0, 0, 0, ele, profile[0][1], 0))
    for length, grade in profile:
        for _ in range(int(length / step)):
            d += step
            ele += step * grade / 100
            pts.append(RoutePoint(d, 0, 0, d, 0, ele, grade, 0))
    return RouteIndex(pts)


MIXED = [(1000, 0), (600, 4), (900, 8), (500, 5), (800, 10), (400, -3), (1000, 0)]


def planner(route=None, lead=500.0, a=1000.0, b=4200.0, ftp=250) -> sp.Planner:
    return sp.Planner(route or synthetic(MIXED), a, b, 84.0, 0.32, 0.005, ftp, lead_in_m=lead)


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))
        _, raw = gpx.parse_gpx(GPX)
        self.points = gpx.resample(raw)
        self.route_id = self.db.insert_route("Serra", self.points, climbs.detect(self.points))

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        options.apply(Database(self.tmp / "x.db")) if False else None

    def seg(self, a=1000, b=3000, name="Subida"):
        sid = sg.save_perennia(self.db, None, self.route_id, name, a, b)
        return next(s for s in sg.load(self.db, self.route_id) if s.id == sid)


# ================================================================== tempos


class TestClock(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(sp.parse_clock("5:01"), 301)
        self.assertEqual(sp.parse_clock("1:02:03"), 3723)
        self.assertEqual(sp.parse_clock("47s"), 47)
        self.assertEqual(sp.parse_clock("1m 5s"), 65)
        self.assertEqual(sp.parse_clock("12 min"), 720)
        self.assertEqual(sp.parse_clock("12", bare="min"), 720)
        self.assertEqual(sp.parse_clock("90"), 90)
        self.assertEqual(sp.parse_clock("5,5", bare="min"), 330)
        for bad in ("", None, "abc", "5:", "::"):
            self.assertIsNone(sp.parse_clock(bad))

    def test_kom_and_best(self):
        self.assertEqual(sp.kom_seconds("5:01"), 301)
        self.assertIsNone(sp.kom_seconds(None))

        class S:
            pr_s, local_best_s = 600, 580
        self.assertEqual(sp.my_best(S), 580)
        S.local_best_s = None
        self.assertEqual(sp.my_best(S), 600)
        S.pr_s = None
        self.assertIsNone(sp.my_best(S))

    def test_parse_target(self):
        self.assertEqual(sp.parse_target("seg_pace", "time", "12:30"), 750)
        self.assertEqual(sp.parse_target("seg_pace", "time", "12"), 720)
        self.assertEqual(sp.parse_target("seg_pace", "pr_pct", "-2,5 %"), -2.5)
        self.assertEqual(sp.parse_target("seg_pace", "pr_pct", "+3"), 3.0)
        self.assertEqual(sp.parse_target("seg_pace", "power", "230 W"), 230.0)
        self.assertIsNone(sp.parse_target("seg_pace", "power", "muito"))


# ================================================================ secções


class TestSections(unittest.TestCase):
    def test_sections_cover_the_segment_and_respect_the_limits(self):
        r = synthetic(MIXED)
        secs = sp.build_sections(r, 1000, 4200, min_m=250, max_m=1000, tol=1.5)
        self.assertEqual(secs[0].start_m, 1000)
        self.assertEqual(secs[-1].end_m, 4200)
        for a, b in zip(secs, secs[1:]):
            self.assertAlmostEqual(a.end_m, b.start_m)
        for s in secs:
            self.assertGreaterEqual(s.length_m, 250 - 1e-6)
            self.assertLessEqual(s.length_m, 1000 + 250)      # o restinho junta-se
        self.assertGreater(len(secs), 3)

    def test_any_end_keeps_the_sections_contiguous(self):
        r = synthetic(MIXED)
        for end in range(1400, 4200, 37):
            secs = sp.build_sections(r, 1000, end)
            self.assertEqual(secs[0].start_m, 1000)
            self.assertEqual(secs[-1].end_m, end)
            for a, b in zip(secs, secs[1:]):
                self.assertAlmostEqual(a.end_m, b.start_m)

    def test_flat_segment_is_split_by_length_only(self):
        r = synthetic([(5000, 0)])
        secs = sp.build_sections(r, 0, 4500, min_m=250, max_m=1000, tol=1.5)
        self.assertGreaterEqual(len(secs), 4)
        self.assertTrue(all(abs(s.grade) < 0.01 for s in secs))

    def test_shape_follows_the_gradient_within_limits(self):
        secs = sp.build_sections(synthetic(MIXED), 1000, 4200)
        f = sp.shape_factors(secs, var_pct=20, floor_pct=50, ref_pct=4)
        self.assertTrue(all(0.8 - 1e-9 <= x <= 1.2 + 1e-9 for x in f))
        steepest = max(range(len(secs)), key=lambda i: secs[i].grade)
        easiest = min(range(len(secs)), key=lambda i: secs[i].grade)
        self.assertEqual(f.index(max(f)), steepest)
        self.assertEqual(f.index(min(f)), easiest)

    def test_floor_binds_when_variation_is_large(self):
        secs = sp.build_sections(synthetic(MIXED), 1000, 4200)
        f = sp.shape_factors(secs, var_pct=80, floor_pct=50, ref_pct=2)
        self.assertGreaterEqual(min(f), 0.5 - 1e-9)
        self.assertLessEqual(max(f), 1.8 + 1e-9)

    def test_zero_variation_is_even_power(self):
        secs = sp.build_sections(synthetic(MIXED), 1000, 4200)
        self.assertEqual(set(sp.shape_factors(secs, var_pct=0)), {1.0})


# ================================================================== plano


class TestPlan(unittest.TestCase):
    def test_hits_the_target_time(self):
        pl = planner()
        for target in (900, 1100, 1500):
            p = pl.plan_time(target)
            self.assertAlmostEqual(p.total_s, target, delta=1.0)
            self.assertTrue(p.reachable)
            self.assertAlmostEqual(sum(s.plan_s for s in p.sections), p.total_s, delta=0.5)

    def test_more_watts_where_it_is_steeper_and_less_downhill(self):
        p = planner().plan_time(1100)
        steep = max(p.sections, key=lambda s: s.grade)
        easy = min(p.sections, key=lambda s: s.grade)
        self.assertGreater(steep.watts, easy.watts)
        self.assertLessEqual(max(p.watts) / min(p.watts), 1.2 / 0.8 + 1e-6)
        self.assertGreaterEqual(min(p.watts), 0.5 * p.avg_w)

    def test_a_faster_target_needs_more_power(self):
        pl = planner()
        self.assertGreater(pl.plan_time(900).avg_w, pl.plan_time(1100).avg_w)

    def test_time_matches_a_fine_step_ride(self):
        """O plano (passo de 0,5 s) dá o mesmo tempo que um passo de 0,05 s, como o motor."""
        pl = planner()
        p = pl.plan_time(1100)
        r = pl.route
        v = physics.speed_from_power(84, 0.32, 0.005, p.sections[0].watts,
                                     p.sections[0].grade / 100)
        pos, t, i = 1000.0, 0.0, 0
        while pos < 4200:
            while i < len(p.sections) - 1 and pos >= p.sections[i].end_m:
                i += 1
            v = physics.step_velocity(84, 0.32, 0.005, v, p.sections[i].watts,
                                      r.grade_at(pos) / 100, 0.05)
            pos += v * 0.05
            t += 0.05
        self.assertAlmostEqual(t, 1100, delta=11)          # 1 %

    def test_power_target_gives_that_average(self):
        p = planner().plan_power(230)
        self.assertAlmostEqual(p.avg_w, 230, delta=1.0)
        self.assertGreater(p.total_s, 0)

    def test_unreachable_target_is_flagged(self):
        p = planner().plan_time(60)             # 3,2 km em 1 min: impossível
        self.assertFalse(p.reachable)

    def test_no_section_shorter_than_a_block(self):
        pl = planner()
        p = pl.plan_time(700)
        self.assertTrue(all(s.plan_s >= games.MIN_BLOCK_S - 0.5 for s in p.sections))

    def test_track_is_monotonic_and_covers_the_segment(self):
        p = planner().plan_time(1100)
        self.assertAlmostEqual(p.track.total_m, 3200, delta=2)
        self.assertEqual(p.track.dist, sorted(p.track.dist))
        self.assertAlmostEqual(p.track.time_at(p.track.dist_at(500.0)), 500.0, delta=0.6)

    def test_lead_in_zero_starts_standing(self):
        slow = planner(lead=0).plan_time(1100)
        fast = planner(lead=500).plan_time(1100)
        self.assertAlmostEqual(slow.total_s, 1100, delta=1)
        self.assertGreater(slow.avg_w, fast.avg_w - 1)         # parte parado: pede ≥ à entrada

    def test_replan_asks_for_more_when_behind_and_is_capped(self):
        pl = planner()
        p = pl.plan_time(1100)
        i = 2
        left = sum(s.plan_s for s in p.sections[i:])
        v = 4.0
        base, ok1 = pl.replan(i, v, left, 50.0, 1000.0)
        late, ok2 = pl.replan(i, v, left - 60, 50.0, 1000.0)
        self.assertGreater(sum(late), sum(base))
        capped, ok3 = pl.replan(i, v, left - 200, 50.0, 150.0)
        self.assertFalse(ok3)
        self.assertLessEqual(max(capped), 150.0 * 1.25 + 1)     # a forma ainda varia ±20 %

    def test_options_drive_the_module(self):
        db = Database(Path(tempfile.mkdtemp()) / "o.db")
        try:
            db.set("seg_pace_variation_pct", 35.0)
            db.set("seg_lead_in_m", 800)
            options.apply(db)
            self.assertEqual(sp.VARIATION_PCT, 35.0)
            self.assertEqual(sp.LEAD_IN_M, 800)
        finally:
            db.set("seg_pace_variation_pct", options.BY_KEY["seg_pace_variation_pct"].default)
            db.set("seg_lead_in_m", options.BY_KEY["seg_lead_in_m"].default)
            options.apply(db)
            db.close()
        self.assertEqual(sp.VARIATION_PCT, 20.0)
        self.assertEqual(sp.LEAD_IN_M, 500)


class TestFeasibility(unittest.TestCase):
    def test_levels_and_message(self):
        curve = games.capacity_curve(250, None)
        cap = games.capacity_at(curve, 600)
        ok = sp.feasibility(cap * 0.8, 600, 250, curve)
        hard = sp.feasibility(cap * 0.97, 600, 250, curve)
        over = sp.feasibility(cap * 1.1, 600, 250, curve)
        self.assertEqual((ok["level"], hard["level"], over["level"]), ("ok", "hard", "over"))
        self.assertIn("W", over["text"])
        self.assertIn("% da FTP", over["text"])
        self.assertIn(str(round(cap)), over["text"])

    def test_prepare_pace_and_kom(self):
        pl = planner()

        class S:
            id, name, source, key = 1, "S", "strava", "strava:1"
            start_m, end_m, length_m = 1000, 4200, 3200
            pr_s, local_best_s, kom = 1100, 1090, "15:00"
            avg_grade = 4.0
        s = S()
        a = sp.prepare(pl, s, sp.PACE, "pr_pct", 2.0)
        self.assertAlmostEqual(a.plan.total_s, 1090 * 1.02, delta=1)
        self.assertEqual(len(a.guides), 1)
        b = sp.prepare(pl, s, sp.KOM, "kom")
        self.assertAlmostEqual(b.plan.total_s, 900, delta=1)
        self.assertEqual([g[0] for g in b.guides], ["O meu KOM", "KOM"])
        self.assertTrue(b.note)                                   # o aviso do rolo
        with self.assertRaises(ValueError):
            sp.prepare(pl, s, sp.PACE, "time", None)
        s.pr_s = s.local_best_s = None
        s.kom = None
        with self.assertRaises(ValueError):
            sp.prepare(pl, s, sp.KOM, "my_kom")
        with self.assertRaises(ValueError):
            sp.prepare(pl, s, sp.PACE, "pr_pct", 0)
        self.assertEqual([k for k, _ in sp.target_choices(sp.KOM, s)], [])


# ================================================================== sessão


class Ride:
    """O motor com um jogo de segmento e o trainer simulado."""

    def __init__(self, case: Tmp, spec: dict, base_power: int = 200):
        self.case = case
        self.athlete = case.db.athlete()
        self.game = games.create(spec, self.athlete, case.db)
        self.trainer = SimulatedTrainer(base_power=base_power, with_hr=True)
        self.hub = SensorHub()
        self.hub.add_source(self.trainer, role="trainer", is_trainer=True)
        self.engine = RideEngine(
            case.db, self.athlete, route_id=case.route_id,
            points=case.db.route_points(case.route_id), climbs=case.db.climbs(case.route_id),
            kind="game", sensors=self.hub, trainer=self.hub, rides_dir=case.tmp / "rides",
            game=self.game)
        self.events = []

    def run(self, seconds: float = 1500.0) -> None:
        steps = 0
        while steps < seconds / DT and not self.game.finished:
            self.hub.tick(DT)
            self.engine.update(DT)
            self.events.extend(self.engine.drain_events())
            steps += 1

    def kinds(self):
        return [e.kind for e in self.events]


class TestSession(Tmp):
    def spec(self, seg, key="seg_pace", **kw):
        d = {"key": key, "route_id": self.route_id, "segment": seg.key, "seed": 3,
             "erg": key == "seg_pace", "lead_in_m": 500}
        d.update(kw)
        return d

    def test_starts_on_the_lead_in_and_clocks_the_segment(self):
        seg = self.seg(1500, 3500)
        r = Ride(self, self.spec(seg, kind="time", value=480))
        self.assertAlmostEqual(r.engine.state.pos_m, 1000.0, delta=0.01)
        self.assertEqual(r.game.start_m, 1000.0)
        r.run()
        self.assertTrue(r.game.finished)
        self.assertIn("game_over", r.kinds())
        res = r.engine.game_result
        self.assertTrue(res["completed"])
        self.assertAlmostEqual(res["elapsed_s"], 480, delta=480 * 0.05)
        self.assertEqual(len(res["sections"]), len(r.game.sections))
        # com o ERG, a potência real acompanha a do plano
        for row in res["sections"][1:-1]:
            self.assertAlmostEqual(row["real_w"], row["plan_w"], delta=25)
        # o motor cronometrou o mesmo segmento (PR local) e a guia foi posta no HUD
        self.assertIn("strava_end", r.kinds())
        self.assertIn("game_cue", r.kinds())

    def test_erg_commands_follow_the_sign(self):
        seg = self.seg(3000, 5400)                  # sobe a 6 % e depois desce: secções distintas
        r = Ride(self, self.spec(seg, kind="time", value=420))
        self.assertGreater(len(set(round(w) for w in r.game.watts)), 2)
        r.run()
        sent = [w for c, w in r.trainer.commands if c == "set_target_power"]
        self.assertTrue(sent)
        self.assertTrue(all(w > 0 for w in sent))
        self.assertGreater(len(set(sent)), 1)               # watts diferentes por secção

    def test_erg_off_shows_the_sign_but_does_not_command_the_trainer(self):
        seg = self.seg(1500, 3500)
        r = Ride(self, self.spec(seg, kind="time", value=480, erg=False))
        r.run(seconds=200)
        self.assertFalse(r.game.erg)
        self.assertFalse([1 for c, _ in r.trainer.commands if c == "set_target_power"])
        self.assertIsNotNone(r.engine.state.target_power_w)
        self.assertIn("▶", r.game.headline)

    def test_lead_in_has_no_target_and_no_erg(self):
        seg = self.seg(1500, 3500)
        r = Ride(self, self.spec(seg, kind="time", value=480))
        r.run(seconds=10)
        self.assertEqual(r.game.phase, "lead")
        self.assertIsNone(r.game.target_w)
        self.assertIn("segmento", r.game.headline.lower())

    def test_kom_my_best_with_ghost_and_table(self):
        seg = self.seg(1500, 3500)
        sg.save_effort(self.db, None, seg.id, 420, source="perennia", kind="ride")
        seg = next(s for s in sg.load(self.db, self.route_id) if s.id == seg.id)
        self.assertEqual(seg.local_best_s, 420)
        r = Ride(self, self.spec(seg, key="seg_kom", kind="my_kom"), base_power=230)
        self.assertFalse(r.game.erg)
        r.run(seconds=100)
        labels = [g[0] for g in r.engine.ghost_positions()]
        self.assertIn("O meu KOM", labels)
        r.run()
        res = r.engine.game_result
        self.assertEqual(res["mode"], "seg_kom")
        self.assertEqual(res["target"]["s"], 420)
        self.assertEqual(res["others"][0]["label"], "O meu KOM")
        d = res["others"][0]["delta_s"]
        self.assertAlmostEqual(d, res["elapsed_s"] - 420, delta=0.2)
        self.assertEqual(res["won"], res["elapsed_s"] < 420)
        self.assertTrue(res["sections"])

    def test_history_per_segment_and_board(self):
        seg = self.seg(1500, 3500)
        other = self.seg(3600, 5000, "Outra")
        r = Ride(self, self.spec(seg, kind="time", value=480))
        r.run()
        h = sp.segment_history(self.db, seg.key, sp.PACE)
        self.assertEqual(len(h), 1)
        self.assertTrue(h[0]["completed"])
        self.assertEqual(sp.segment_history(self.db, other.key), [])
        self.assertEqual(sp.segment_history(self.db, seg.key, sp.KOM), [])
        b = sp.history_board(self.db, seg.key, sp.PACE, "x")
        self.assertEqual(len(b.rows), 1)
        lb = games.leaderboard(self.db, "seg_pace")
        self.assertIn("Subida", lb.rows[0].label)
        self.assertEqual(games.history(self.db, "seg_pace", 1)[0], -round(h[0]["elapsed_s"]))

    def test_unfinished_session_is_saved_as_not_completed(self):
        seg = self.seg(1500, 3500)
        r = Ride(self, self.spec(seg, kind="time", value=480))
        r.run(seconds=60)
        r.game.end()
        res = r.game.result()
        self.assertFalse(res["completed"])
        self.assertIsNone(res["score"])
        self.assertFalse(res["won"])
        self.assertIn("não concluído", res["summary"].lower())

    def test_replan_when_behind(self):
        seg = self.seg(1500, 3500)
        r = Ride(self, self.spec(seg, kind="time", value=420, erg=False), base_power=120)
        r.run()
        self.assertGreater(r.game.replans, 0)
        # atrasado: os watts do sinal subiram acima do plano original nas últimas secções
        res = r.engine.game_result
        self.assertGreater(res["sections"][-1]["sign_w"], res["sections"][-1]["plan_w"] - 1)

    def test_missing_segment_is_a_clear_error(self):
        with self.assertRaises(ValueError):
            games.create({"key": "seg_pace", "route_id": self.route_id,
                          "segment": "perennia:999", "kind": "time", "value": 300},
                         self.db.athlete(), self.db)

    def test_snapshot_survives_json(self):
        import json
        seg = self.seg(1500, 3500)
        r = Ride(self, self.spec(seg, kind="time", value=480))
        r.run(seconds=150)
        snap = r.game.snapshot()
        json.dumps(snap)
        g2 = games.create(self.spec(seg, kind="time", value=480), self.db.athlete(), self.db)
        g2.restore(snap)
        self.assertEqual(g2.phase, r.game.phase)
        self.assertEqual(g2.watts, r.game.watts)


# ================================================================ ecrãs


class TestScreens(tg.GuiCase):
    def seg(self, a=1500, b=3500, name="Subida"):
        sid = sg.save_perennia(self.app.db, None, self.route_id, name, a, b)
        return next(s for s in sg.load(self.app.db, self.route_id) if s.id == sid)

    def open_pace(self, which="Segment Pace"):
        self.pick_mode("Challenge")
        self.pick(which)
        return self.screen()

    def labels_of(self):
        return [i.label for i in self.screen().list.items]

    def test_menu_lists_both_games(self):
        self.pick_mode("Challenge")
        labels = self.labels_of()
        self.assertIn("Segment Pace", labels)
        self.assertIn("Segment KOM", labels)
        from perennia.ui.sport_screens import ChallengeMenu
        menu = ChallengeMenu(self.app)
        menu.enter()
        menu.list.index = [i.label for i in menu.list.items].index("Segment KOM")
        self.assertEqual(menu.side_board().title, "Segment KOM")

    def test_no_segments_explains_and_blocks_start(self):
        scr = self.open_pace()
        self.assertFalse(scr.can_start)
        self.assertTrue(any("não tem segmentos" in (i.detail or "") for i in scr.list.items))

    def test_pace_setup_rows_defaults_and_start(self):
        seg = self.seg()
        scr = self.open_pace()
        labels = self.labels_of()
        for want in ("Segmento", "Alvo", "ERG", "Entrada"):
            self.assertTrue(any(want in x for x in labels), want)
        self.assertTrue(scr.erg)                               # ERG ligado por omissão
        self.assertEqual(scr.lead_in, 500)
        self.assertEqual(scr.kind, "time")                     # sem melhor tempo: pede o tempo
        self.assertFalse(scr.can_start)
        self.assertFalse(scr._set_value("lixo"))
        self.assertTrue(scr._set_value("8:00"))
        scr.enter()
        self.assertTrue(scr.can_start)
        text = " ".join(f"{i.label} {i.value} {i.detail}" for i in scr.list.items)
        for want in ("Tempo previsto", "Potência média", "Cabe em ti", "Secções", "% da FTP"):
            self.assertIn(want, text)
        seg_item = next(i for i in scr.list.items if i.data == "seg")
        self.assertIsNotNone(seg_item.dropdown)
        self.assertEqual(scr.game()["segment"], seg.key)
        scr._start()
        rs = self.screen()
        self.assertEqual(rs.game_spec["kind"], "time")
        self.assertEqual(rs.game_spec["route_id"], self.route_id)
        self.assertIsInstance(rs.engine.game, sp.SegmentPace)
        self.assertAlmostEqual(rs.engine.state.pos_m, 1000.0, delta=0.01)

    def test_pace_with_pr_uses_percent_and_dropdown_of_kinds(self):
        seg = self.seg()
        sg.save_effort(self.app.db, None, seg.id, 500, source="perennia", kind="ride")
        scr = self.open_pace()
        self.assertEqual(scr.kind, "pr_pct")
        item = next(i for i in scr.list.items if i.data == "tgt")
        self.assertEqual(len(item.dropdown.labels()), 3)
        item.dropdown.on_pick(2)                               # potência média
        self.assertEqual(scr.kind, "power")
        self.assertTrue(scr._set_value("200"))
        scr.enter()
        self.assertTrue(scr.can_start)
        self.assertTrue(any("W" in (i.value or "") for i in scr.list.items
                            if i.data == "plan_w"))

    def test_feasibility_warns_when_out_of_reach(self):
        self.seg()
        scr = self.open_pace()
        scr._set_value("2:00")                                  # 2 km em 2 min
        scr.enter()
        feas = next(i for i in scr.list.items if i.data == "feas")
        self.assertEqual(feas.value, "✗")
        self.assertIn("W", feas.detail)

    def test_kom_needs_a_time_then_offers_my_kom(self):
        seg = self.seg()
        scr = self.open_pace("Segment KOM")
        self.assertFalse(scr.can_start)
        why = next(i for i in scr.list.items if i.data == "why")
        self.assertIn("tempos teus", why.detail)
        sg.save_effort(self.app.db, None, seg.id, 420, source="perennia", kind="ride")
        scr.enter()
        scr._ensure_choices()
        self.assertEqual(scr.kind, "my_kom")
        self.assertTrue(scr.can_start)
        self.assertFalse(any(i.data == "erg" for i in scr.list.items))   # KOM: sem ERG
        scr._start()
        self.assertIsInstance(self.screen().engine.game, sp.SegmentKom)
        self.assertFalse(self.screen().engine.game.erg)

    def test_kom_with_strava_segment_offers_both_targets(self):
        db = self.app.db
        db.conn.execute(
            "INSERT INTO strava_segments(route_id, segment_id, name, distance_m, avg_grade,"
            " climb_cat, start_m, end_m, pr_s, pr_date, effort_count, kom, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.route_id, 77, "Strava Climb", 2000, 4.0, 3, 1500, 3500, 540, "2025-01-01", 5,
             "5:01", "2025-01-01T00:00:00Z"))
        db.conn.commit()
        scr = self.open_pace("Segment KOM")
        item = next(i for i in scr.list.items if i.data == "tgt")
        self.assertEqual(item.dropdown.labels(), ["O meu KOM", "KOM do segmento"])
        item.dropdown.on_pick(1)
        scr.enter()
        self.assertEqual(scr.kind, "kom")
        setup, err = scr.prepared()
        self.assertIsNone(err)
        self.assertAlmostEqual(setup.plan.total_s, 301, delta=1)
        self.assertEqual(len(setup.guides), 2)
        self.assertTrue(any(i.data == "note" for i in scr.list.items))   # vento / aspiração

    def test_lead_in_dropdown_and_arrows(self):
        self.seg()
        scr = self.open_pace()
        item = next(i for i in scr.list.items if i.data == "lead")
        self.assertIn("500 m", item.dropdown.labels())
        item.dropdown.on_pick(item.dropdown.labels().index("0 m"))
        self.assertEqual(scr.lead_in, 0)
        scr.adjust("lead", 1)
        self.assertEqual(scr.lead_in, 250)

    def test_full_flow_menu_to_summary_with_the_table(self):
        from pyglet.window import key
        from perennia.ui import app as app_mod
        self.seg(3000, 5400)
        scr = self.open_pace()
        self.assertTrue(scr._set_value("7:00"))
        scr.enter()
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        seen_sign = seen_guide = False
        for i in range(int(900 / 0.25)):
            self.app.hub.tick(0.25)
            ride.update(0.25)
            if i % 40 == 0:
                self.app._on_draw()
            seen_sign = seen_sign or "▶" in ride.hud._chase_title.text
            seen_guide = seen_guide or any("Guia" in lab.text for lab in ride.hud._ghost_labels)
            if ride.engine.game.finished:
                break
        self.assertTrue(ride.engine.game.finished)
        self.assertTrue(seen_sign)
        self.assertTrue(seen_guide)
        self.press(key.F10, key.ENTER, key.ENTER)          # terminar → «Sim»
        self.assertIsInstance(self.screen(), app_mod.SummaryScreen)
        self.app._on_draw()
        texts = [i.label for i in self.screen().list.items]
        self.assertTrue(any("Segment Pace" in x for x in texts))
        self.assertTrue(any(". " in x and "%" in x and " m" in x for x in texts))   # as secções
        self.assertEqual(len(sp.segment_history(self.app.db, f"perennia:{self.seg_id()}")), 1)

    def seg_id(self) -> int:
        return sg.perennia_segments(self.app.db)[0].id

    def test_section_table_text(self):
        from perennia.ui.pace_screens import section_table
        rows = section_table({"sections": [
            {"idx": 0, "grade": 4.2, "length_m": 500, "plan_w": 210, "sign_w": 210,
             "real_w": 214, "plan_s": 120.0, "real_s": 116.0, "delta_s": -4.0},
            {"idx": 1, "grade": -2.0, "length_m": 300, "plan_w": 150, "sign_w": 150,
             "real_w": None, "plan_s": 40.0, "real_s": 44.0, "delta_s": 4.0}]})
        self.assertEqual(len(rows), 2)
        self.assertIn("214 / 210 W", rows[0].value)
        self.assertIn("ganhaste 4 s", rows[0].detail)
        self.assertIn("perdeste 4 s", rows[1].detail)
        self.assertEqual(rows[1].value, "— / 150 W")


if __name__ == "__main__":
    unittest.main()
