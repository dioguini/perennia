"""Ronda 30: o impacto de um treino por potência.

* no construtor, logo ao criar: o IF, a TSS, o efeito em cada sistema do desporto (Resistência,
  Tempo, Limiar, VO2máx, Anaeróbio, Sprint), a ligação ao perfil e o impacto no índice de
  longevidade;
* no fim da sessão desse treino: o IF feito contra o IF alvo, e o impacto (sistemas e
  longevidade) do plano sobreposto ao do que se fez.
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import longevity as lg  # noqa: E402
from perennia.core import rowing as rw  # noqa: E402
from perennia.core import workout_impact as wi  # noqa: E402
from perennia.core import workouts  # noqa: E402
from perennia.core.blocks import Block, effective_pct, estimate  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402
from perennia.core.intensity import Context  # noqa: E402
from perennia.core.ride import RideEngine  # noqa: E402
from perennia.core.workouts import WorkoutRunner  # noqa: E402
from perennia.io.hub import SensorHub  # noqa: E402
from perennia.io.sim import SimulatedTrainer  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import builder_screens as bs  # noqa: E402
from perennia.ui.sport_screens import _steps_from_db  # noqa: E402

VO2 = [{"kind": "steady", "duration_s": 120, "target_type": "pct_ftp", "target_lo": 60,
        "target_hi": 60}] + [
    {"kind": "steady", "duration_s": 120, "target_type": "pct_ftp", "target_lo": 115,
     "target_hi": 115},
    {"kind": "steady", "duration_s": 60, "target_type": "pct_ftp", "target_lo": 50,
     "target_hi": 50}] * 3


def vo2_blocks() -> list[Block]:
    return [Block("warmup", "time", 600, 55)] + \
        [Block("active", "time", 240, 115), Block("rest", "time", 180, 50)] * 5 + \
        [Block("cooldown", "time", 600, 50)]


def ride_workout(db, wid: str, data_dir: Path, base_power: int = 200) -> dict:
    """Faz a sessão do treino inteiro (trainer simulado em ERG) e devolve o resultado."""
    w = db.workout(wid)
    wk = workouts.Workout(w["name"], _steps_from_db(db, wid))
    hub = SensorHub()
    hub.add_source(SimulatedTrainer(base_power=base_power), role="trainer", is_trainer=True)
    runner = WorkoutRunner(wk, db.athlete().ftp_w, True)
    e = RideEngine(db, db.athlete(), sensors=hub, trainer=hub, workout_runner=runner,
                   workout_id=wid, kind="workout", rides_dir=data_dir / "out" / "sessoes")
    for _ in range(int(runner.total_s) + 3):
        hub.tick(1.0)
        e.update(1.0)
        e.drain_events()
    return e.finish()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.addCleanup(self.db.close)
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))


# =================================================================== o núcleo


class TestEffects(Base):
    def test_effects_saturate_and_go_to_the_right_system(self):
        self.assertEqual(wi.effects([0] * 7), {s: 0.0 for s in wi.SYSTEMS})
        z2 = wi.effects([0, 2 * 3600, 0, 0, 0, 0, 0])
        self.assertGreater(z2["endurance"], 3.5)
        self.assertEqual(z2["vo2max"], 0.0)
        sprint = wi.effects([0, 0, 0, 0, 0, 0, 120])
        self.assertGreater(sprint["sprint"], sprint["anaerobic"])
        big = wi.effects([0, 0, 0, 0, 3 * 3600, 0, 0])
        self.assertLessEqual(big["vo2max"], wi.EFFECT_MAX)
        self.assertEqual(wi.effect_level(0.5), "sem efeito")
        self.assertEqual(wi.effect_level(3.2), "melhora")
        self.assertEqual(wi.effect_level(4.5), "melhora muito")

    def test_free_sprint_blocks_count_as_all_out(self):
        self.assertEqual(effective_pct(Block("active", "time", 15, None, cue="SPRINT!")), 200.0)
        self.assertEqual(effective_pct(Block("active", "time", 20, None)), 200.0)
        self.assertEqual(effective_pct(Block("active", "time", 60, None, cue="a fundo")), 130.0)
        self.assertEqual(effective_pct(Block("active", "time", 600, None)), 50.0)
        self.assertEqual(effective_pct(Block("rest", "time", 20, None)), 50.0)
        self.assertEqual(effective_pct(Block("active", "time", 300, 90)), 90.0)
        est = estimate([Block("active", "time", 15, None)], Context())
        self.assertEqual(est["zones"][6], 15.0)                         # Z7

    def test_planned_if_is_the_np_of_the_profile(self):
        from perennia.core.blocks import profile_if
        steady = [Block("active", "time", 3600, 100)]
        self.assertAlmostEqual(profile_if(steady, Context()), 1.0, places=3)
        est = estimate(steady, Context())
        self.assertAlmostEqual((est["if"], est["tss"])[1], 100.0, places=1)
        # intervalos: a NP pesa os esforços, o IF fica acima da média por blocos
        bl = vo2_blocks()
        mean_if = (sum(b.dur * (b.mid() / 100) ** 2 for b in bl) / sum(b.dur for b in bl)) ** .5
        self.assertGreater(profile_if(bl, Context()), mean_if)

    def test_planned_vo2_workout(self):
        imp = wi.planned(self.db, "cycling", vo2_blocks())
        self.assertAlmostEqual(imp.if_, 0.90, delta=0.02)          # pela NP do perfil
        self.assertGreater(imp.tss, 50)
        self.assertEqual(imp.focus, "vo2max")
        self.assertGreater(imp.systems["vo2max"], 3.5)
        self.assertEqual(imp.systems["sprint"], 0.0)
        d = imp.longevity["deltas"]
        self.assertGreater(d["1m"], 0)
        self.assertIn("vo2max", [a for a, _v in imp.longevity["top"]])
        self.assertIn("foco VO2máx", wi.summary_text(imp))

    def test_if_verdict_and_compare(self):
        self.assertEqual(wi.if_verdict(0.80, 0.81)[0], "on")
        self.assertEqual(wi.if_verdict(0.80, 0.86)[0], "above")
        self.assertEqual(wi.if_verdict(0.80, 0.70)[0], "below")
        self.assertEqual(wi.if_verdict(None, 0.70)[0], "none")
        plan = wi.planned(self.db, "cycling", vo2_blocks())
        act = wi.Impact(if_=0.70, tss=40, systems={"vo2max": 2.0}, source="actual")
        c = wi.compare(plan, act)
        self.assertEqual(c["if_key"], "below")
        self.assertAlmostEqual(c["if_pct"], 0.70 / plan.if_ * 100)
        self.assertEqual(c["systems"]["vo2max"], (plan.systems["vo2max"], 2.0))
        self.assertEqual(set(c["longevity"]), {"1w", "1m", "3m"})

    def test_profile_links_mark_the_weakest(self):
        from perennia.core import profile as pf
        orig = pf.cycling

        def fake(db, today=None):
            rows = [{"key": k, "name": pf.duration_name(k), "score": sc, "level": "x"}
                    for k, sc in ((5, 80), (60, 70), (300, 20), ("ft", 60))]
            return {"rows": rows, "weakest": rows[2]}
        pf.cycling = fake
        try:
            links = wi.profile_links(self.db, "cycling", {"vo2max": 3.8})
        finally:
            pf.cycling = orig
        self.assertTrue(links["vo2max"]["weakest"])
        self.assertFalse(links["threshold"]["weakest"])
        self.assertEqual(wi.profile_links(self.db, "running", {}), {})


class TestSession(Base):
    def test_ride_with_a_workout_compares_plan_and_done(self):
        wid = self.db.insert_workout("VO2 curto", VO2)
        res = ride_workout(self.db, wid, self.tmp)
        cmp = wi.for_session(self.db, "cycling", res["ride_id"])
        self.assertIsNotNone(cmp)
        plan, act = cmp["planned"], cmp["actual"]
        self.assertAlmostEqual(plan.if_, 0.99, delta=0.03)
        self.assertIsNotNone(act.if_)
        self.assertAlmostEqual(act.if_, plan.if_, delta=0.08)       # ERG segue o alvo
        self.assertGreater(act.systems["vo2max"], 0.5)
        self.assertGreater(sum(act.zones), 600)                     # as amostras da sessão
        comp = cmp["compare"]
        self.assertIn(comp["if_key"], ("on", "above", "below"))
        self.assertIsNotNone(comp["longevity"]["1m"][0])
        self.assertIsNotNone(comp["longevity"]["1m"][1])
        # o plano mede-se contra a mesma base que a sessão: valores da mesma ordem
        self.assertAlmostEqual(comp["longevity"]["1m"][0], comp["longevity"]["1m"][1],
                               delta=abs(comp["longevity"]["1m"][1]) + 2)

    def test_free_ride_and_other_sports_have_no_comparison(self):
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=180), role="trainer", is_trainer=True)
        e = RideEngine(self.db, self.db.athlete(), sensors=hub, trainer=hub, kind="free",
                       rides_dir=self.tmp)
        for _ in range(120):
            hub.tick(1.0)
            e.update(1.0)
        res = e.finish()
        self.assertIsNone(wi.for_session(self.db, "cycling", res["ride_id"]))
        self.assertIsNone(wi.for_session(self.db, "running", "x"))
        self.assertIsNone(wi.for_session(self.db, "cycling", "nao-existe"))

    def test_rowing_actual_from_power_samples(self):
        rw.ensure(self.db)
        self.db.conn.execute(
            "INSERT INTO row_sessions(id, kind, status, started_at, elapsed_s, moving_s, np_w,"
            " ftp_w) VALUES ('r1', 'workout', 'completed', ?, 600, 600, 220, 200)",
            (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),))
        self.db.conn.executemany(
            "INSERT INTO row_samples(session_id, t_s, power_w) VALUES ('r1', ?, ?)",
            [(t, 230 if t < 300 else 120) for t in range(600)])
        self.db.conn.commit()
        act = wi.actual(self.db, "rowing", "r1")
        self.assertAlmostEqual(act.if_, 1.1)
        self.assertEqual(act.zones[4], 300.0)          # 115 % → Z5
        self.assertGreater(act.systems["vo2max"], 1.5)             # 5 min em Z5
        self.assertEqual(act.focus, "vo2max")


# ================================================================== o construtor


class TestBuilderPanel(tg.GuiCase):
    def builder(self, blocks=None) -> bs.BlockBuilder:
        scr = bs.BlockBuilder(self.app, "cycling", None)
        if blocks is not None:
            scr.blocks = blocks
            scr.sel = 0
            scr.changed()
        self.app.push(scr)
        return scr

    def test_the_panel_shows_if_systems_and_longevity_right_away(self):
        scr = self.builder(vo2_blocks())
        self.assertTrue(scr.impact_visible())
        tx = scr.impact_texts()
        self.assertTrue(tx["if"].startswith("IF 0.9"))
        self.assertIn("TSS", tx["sub"])
        self.assertEqual(set(tx["rows"]), set(wi.SYSTEMS))
        self.assertTrue(tx["rows"]["vo2max"].startswith(("3.", "4.")))
        self.assertIn("Longevidade", tx["longevity"])
        self.assertEqual(tx["focus"], "vo2max")
        self.assertEqual(scr.imp_if.text, tx["if"])                 # desenhado no painel
        self.assertLess(scr.cx1, self.app.window.width - 48 - scr.IMPACT_W)   # gráfico ao lado

    def test_the_panel_follows_the_blocks(self):
        scr = self.builder([Block("active", "time", 3600, 65)])
        before = scr.impact_texts()
        self.assertEqual(before["focus"], "endurance")
        scr.blocks.append(Block("active", "time", 1200, 100))
        scr.changed()
        after = scr.impact_texts()
        self.assertGreater(float(after["if"].split()[1]), float(before["if"].split()[1]))
        self.assertNotEqual(after["rows"]["threshold"], before["rows"]["threshold"])

    def test_narrow_window_keeps_the_subtitle(self):
        self.app.window.width = 1000
        scr = self.builder(vo2_blocks())
        scr.on_resize(1000, self.app.window.height)
        scr.redraw()
        self.assertFalse(scr.impact_visible())
        self.assertIn("Long", scr.chrome.subtitle.text)             # a longevidade, no subtítulo
        self.assertEqual(scr.imp_if.text, "")

    def test_head_rows_are_a_two_by_two_grid_above_the_palette(self):
        scr = self.builder()
        lv = scr.list
        self.assertEqual(lv.head_cols, 2)
        heads = [c for c in lv._cells if lv.items[c[0]].head]
        ys = sorted({round(c[2]) for c in heads}, reverse=True)
        self.assertEqual(len(ys), 2)                                # duas linhas
        lowest_head = min(ys) - lv.row_h / 2
        pal_top = max(r.y + r.height for _n, _p, r, _l in scr.pal)
        self.assertLessEqual(pal_top, lowest_head)                  # sem sobreposição


# =============================================================== o fim da sessão


class TestSessionEnd(tg.GuiCase):
    def finished(self) -> dict:
        wid = self.app.db.insert_workout("VO2 curto", VO2)
        return ride_workout(self.app.db, wid, Path(self.tmp))

    def test_summary_shows_if_against_target_and_the_overlay(self):
        res = self.finished()
        scr = app_mod.SummaryScreen(self.app, res)
        self.app.push(scr)
        labels = [i.label for i in scr.list.items]
        self.assertIn("IF feito · alvo", labels)
        self.assertIn("Foco do treino", labels)
        row = next(i for i in scr.list.items if i.label == "IF feito · alvo")
        done, target = row.value.split(" · ")
        self.assertAlmostEqual(float(target), 0.99, delta=0.03)
        self.assertTrue(float(done) > 0)
        self.assertIsNotNone(scr._impact_panel)
        tx = scr._impact_panel.texts()
        self.assertTrue(tx["if"].startswith("IF "))
        self.assertIn("alvo", tx["if_note"])
        self.assertEqual(len(tx["rows"]), len(wi.SYSTEMS))
        self.assertIn("feito", tx["longevity"])
        self.assertIsNone(scr.board_panel)                          # o painel no lugar dele
        self.assertEqual(len(scr._radar.overlay), len(lg.AXES))     # o plano sobreposto
        self.assertIn("laranja = plano", scr._radar.legend.text)
        lon = next(i for i in scr.list.items if i.label == "Longevidade")
        self.assertTrue(lon.detail.startswith("plano "))
        scr.draw()

    def test_analysis_general_tab_has_the_same_comparison(self):
        from perennia.ui.session_analysis import SessionAnalysis
        res = self.finished()
        scr = SessionAnalysis(self.app, "ride", res["ride_id"])
        self.app.push(scr)
        self.assertIn("IF feito · alvo", [i.label for i in scr.list.items])
        self.assertIsNotNone(scr._cmp)
        x, y, w, h = scr._impact_panel.box
        self.assertGreater(w, 200)
        scr.draw()

    def test_free_ride_summary_has_no_comparison_and_keeps_the_board(self):
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=180), role="trainer", is_trainer=True)
        e = RideEngine(self.app.db, self.app.db.athlete(), sensors=hub, trainer=hub,
                       kind="free", rides_dir=Path(self.tmp))
        for _ in range(120):
            hub.tick(1.0)
            e.update(1.0)
        scr = app_mod.SummaryScreen(self.app, e.finish())
        self.app.push(scr)
        self.assertNotIn("IF feito · alvo", [i.label for i in scr.list.items])
        self.assertIsNotNone(scr.board_panel)
        self.assertIsNone(scr._radar.overlay)


if __name__ == "__main__":
    unittest.main()
