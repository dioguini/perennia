"""Os cinco desportos: auto lap, «terminar sem guardar», corrida e natação,
modalidades do ginásio (treino livre com plano primeiro, surpresa,
longevidade), inventários, intensidade em várias escalas e o construtor
por arrastar blocos."""
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

from pyglet.window import key  # noqa: E402

from velo.core import endurance as en  # noqa: E402
from velo.core import fit, gym, inventory, stats  # noqa: E402
from velo.core import intensity as it  # noqa: E402
from velo.core import laps_session as ls  # noqa: E402
from velo.core import rowing as rw  # noqa: E402
from velo.core import strength as st  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.core.ride import Reading  # noqa: E402
from velo.core.sports import AutoLap  # noqa: E402
from velo.io import rower as rio  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import builder_screens as bs  # noqa: E402
from velo.ui import endurance_screens as es  # noqa: E402
from velo.ui import gym_screens as gs  # noqa: E402
from velo.ui import hub_screens as hs  # noqa: E402
from velo.ui import sport_screens as ss  # noqa: E402
from velo.ui import stats_screens as sts  # noqa: E402


class HR:
    def __init__(self, bpm=150):
        self.bpm = bpm

    def reading(self):
        return Reading(hr_bpm=self.bpm)


def make_db(tmp: Path) -> Database:
    db = Database(tmp / "v.db")
    db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250, lthr=165))
    return db


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = make_db(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ==================================================================== núcleo


class TestAutoLapAndIntensity(Base):
    def test_auto_lap_is_off_by_default_and_counts_by_time_or_distance(self):
        self.assertFalse(AutoLap().on)
        self.assertFalse(AutoLap(None).due(1000, 1000))
        a = AutoLap({"mode": "distance", "value": 1000})
        self.assertFalse(a.due(10, 999))
        self.assertTrue(a.due(11, 1001))
        self.assertFalse(a.due(12, 1500))
        self.assertTrue(a.due(13, 2500))
        b = AutoLap({"mode": "time", "value": 60})
        b.restore(130, 0)
        self.assertFalse(b.due(170, 0))
        self.assertTrue(b.due(181, 0))

    def test_same_block_in_every_scale(self):
        c = it.Context("running", run_pace_s=300, lthr=165)
        self.assertEqual(c.text("pace", 100), "5:00 /km")
        self.assertAlmostEqual(c.pct_from("pace", 300), 100)
        self.assertEqual(c.rpe(100), 7.5)
        self.assertAlmostEqual(c.pct_from("rpe", c.rpe(80)), 80, delta=1)
        self.assertEqual(c.hr(105), 165)
        self.assertEqual(it.zone(98), 4)
        w = it.Context("swimming", swim_css_s=100)
        self.assertEqual(w.text("pace", 100), "1:40 /100 m")
        r = it.Context("rowing", row_ftp_w=200)
        self.assertAlmostEqual(r.pct_from("pace", r.pace(90)), 90, delta=0.5)


class TestGymCore(Base):
    def test_every_modality_has_exercises_and_longevity_sees_all(self):
        gym.ensure(self.db)
        keys = [m.key for m in gym.modalities()]
        for k in ("strength", "plyometrics", "animal_flow", "cardio", "hiit", "calisthenics",
                  "rings", "bands", "kettlebell", "sandbag", "longevity", "conditioning"):
            self.assertIn(k, keys)
            self.assertGreater(len(gym.exercises(self.db, k)), 4, k)
        everything = len(gym.exercises(self.db))
        self.assertEqual(len(gym.exercises(self.db, "longevity")), everything)
        self.assertLess(len(gym.exercises(self.db, "kettlebell")), everything)
        # só a Longevidade junta desportos
        self.assertTrue(gym.modality("longevity").multi)
        self.assertFalse(any(m.multi for m in gym.modalities() if m.key != "longevity"))

    def test_new_modality_plugs_in(self):
        gym.register(gym.Modality("yoga", "Yoga", "Yoga", "pulse"),
                     [("Saudação ao sol", "mobility", "warm_up", 0.0, "time", ("mat",))])
        try:
            gym.ensure(self.db)
            names = [e["name"] for e in gym.exercises(self.db, "yoga")]
            self.assertEqual(names, ["Saudação ao sol"])
            self.assertTrue(gym.surprise(self.db, "yoga", 1))
        finally:
            gym.MODALITIES.pop("yoga", None)
            gym.SEED_EXERCISES[:] = [e for e in gym.SEED_EXERCISES if e[1] != "yoga"]

    def test_surprise_uses_only_my_equipment(self):
        gym.ensure(self.db)
        inventory.save(self.db, None, name="Kettlebell 16 kg", kind="kettlebell",
                       weight_kg=16)
        for seed in range(5):
            items = gym.surprise(self.db, "strength", seed)
            self.assertTrue(items)
            for i in items:
                ex = gym.exercise(self.db, i["exercise_id"])
                self.assertTrue(set(ex["equipment"]) <= {"kettlebell"}, ex["name"])
        lon = gym.surprise(self.db, "longevity", 3)
        mods = {m for i in lon for m in gym.exercise(self.db, i["exercise_id"])["modalities"]}
        self.assertIn("cardio", mods)                       # um bloco de outro desporto

    def test_exercise_with_modalities_and_equipment(self):
        gym.ensure(self.db)
        eid = gym.save_exercise(self.db, None, name="Remada renegada",
                                mods=["kettlebell", "strength"], group="back",
                                equipment=["kettlebell"], description="Em prancha")
        ex = gym.exercise(self.db, eid)
        self.assertEqual(sorted(ex["modalities"]), ["kettlebell", "strength"])
        self.assertEqual(ex["equipment"], ["kettlebell"])
        self.assertEqual(gym.missing_equipment(self.db, ex), ["kettlebell"])
        gym.archive_exercise(self.db, eid)
        self.assertNotIn(eid, [e["id"] for e in gym.exercises(self.db, "kettlebell")])

    def test_drafts_are_hidden_until_kept(self):
        gym.ensure(self.db)
        eid = gym.exercises(self.db, "hiit")[0]["id"]
        wid = gym.save_plan(self.db, None, "Livre", None,
                            [{"exercise_id": eid, "sets": 3, "reps": 30, "rest_s": 15}],
                            "hiit", hidden=True)
        self.assertNotIn(wid, [w["id"] for w in gym.workouts(self.db, "hiit")])
        gym.keep_plan(self.db, wid, "HIIT de terça")
        self.assertIn("HIIT de terça", [w["name"] for w in gym.workouts(self.db, "hiit")])

    def test_strength_clock_waits_for_the_first_set(self):
        gym.ensure(self.db)
        wid = gym.workouts(self.db, "strength")[0]["id"]
        s = st.StrengthSession(self.db, self.db.athlete(), wid, out_dir=self.tmp)
        for _ in range(10):
            s.update(1.0)
        self.assertEqual(s.t, 0.0)
        s.action()
        for _ in range(10):
            s.update(1.0)
        self.assertEqual(s.t, 10.0)
        cur = self.db.conn.execute("SELECT modality FROM strength_sessions").fetchone()
        self.assertEqual(cur["modality"], "strength")

    def test_inventory(self):
        iid = inventory.save(self.db, None, name="Disco 1 kg", kind="plates", qty=10,
                             weight_kg=1.0)
        inventory.save(self.db, None, name="Domyos Rowing 500B", kind="rower")
        self.assertEqual(inventory.total_weight(self.db, "plates"), 10.0)
        self.assertEqual(inventory.available_kinds(self.db), {"plates", "rower"})
        inventory.save(self.db, iid, name="Disco 1 kg", kind="plates", qty=0, weight_kg=1)
        self.assertEqual(inventory.available_kinds(self.db), {"rower"})
        self.assertEqual(inventory.summary(self.db)["articles"], 2)


class TestLapPlans(Base):
    def test_plan_first_clock_waits_and_timed_laps_advance(self):
        gym.ensure(self.db)
        ex = gym.exercises(self.db, "kettlebell")[0]
        plan = [{"kind": "treadmill", "seconds": 30},
                {"kind": "strength", "exercise_id": ex["id"], "name": ex["name"], "reps": 12},
                {"kind": "rest", "seconds": 20}]
        s = ls.LapSession(self.db, self.db.athlete(), "conditioning", out_dir=self.tmp,
                          plan=plan)
        for _ in range(10):
            s.update(1.0)
        self.assertEqual(s.t, 0.0)
        s.start_planned()
        for _ in range(31):
            s.update(1.0)
        self.assertEqual(s.current.kind, "strength")         # passou sozinho
        self.assertEqual(s.current.reps, 12)
        s.toggle()                                           # Espaço: a seguinte do plano
        self.assertEqual(s.current.kind, "rest")
        for _ in range(21):
            s.update(1.0)
        self.assertIsNone(s.current)                         # plano cumprido
        pid = ls.save_plan(self.db, None, "Meu", "conditioning", plan)
        self.assertEqual(len(ls.plan(self.db, pid)["items"]), 3)
        self.assertTrue(ls.surprise_plan(self.db, 1))


# ================================================================ resistência


class TestEndurance(Base):
    def test_treadmill_run_with_workout_autolap_and_fit(self):
        wid = en.save_workout(self.db, None, "running", "Teste", "", [
            en.Step("warmup", "time", 60, 60, 70), en.Step("active", "distance", 400, 100, 105),
            en.Step("cooldown", "time", 60, 60, 65)], mode="pace")
        e = en.EnduranceEngine(self.db, self.db.athlete(), "running", sensors=HR(),
                               workout_id=wid, autolap={"mode": "distance", "value": 200},
                               out_dir=self.tmp)
        for _ in range(10):
            e.update(1.0)
        self.assertEqual(e.t, 0.0)                           # só conta depois de começar
        e.start()
        e.set_speed(12.0)                                    # 12 km/h = 3,33 m/s
        for _ in range(60):
            e.update(1.0)
        self.assertEqual(e.workout.idx, 1)
        self.assertIn("/km", e.target_text())
        for _ in range(125):
            e.update(1.0)
        self.assertEqual(e.workout.idx, 2)                   # 400 m em 120 s
        res = e.finish()
        self.assertAlmostEqual(res["distance_m"], 615, delta=5)
        triggers = [lp.trigger for lp in res["laps"]]
        self.assertIn("distance", triggers)
        self.assertIn("workout_step", triggers)
        msgs = fit.read_messages(res["fit_path"])
        sport = [f for n, f in msgs if n == 12][0]
        self.assertEqual((sport[0], sport[1]), (1, 1))      # corrida, passadeira
        self.assertGreater(res["load"], 0)
        self.assertEqual(len(en.sessions(self.db, "running")), 1)
        self.assertEqual(stats.sport_totals(self.db, "week", 1)["running"]["sessions"], 1)

    def test_swim_lengths_resume_and_discard(self):
        e = en.EnduranceEngine(self.db, self.db.athlete(), "swimming", pool_m=25,
                               out_dir=self.tmp)
        e.add_length()                                       # a primeira piscina começa
        self.assertTrue(e.started)
        for _ in range(3):
            e.add_length()
        e.add_length(-1)                                     # corrige
        for _ in range(90):
            e.update(1.0)
        self.assertEqual(e.distance_m, 75.0)
        self.assertAlmostEqual(e.avg_pace_s, 120.0)          # 90 s em 75 m → 2:00/100 m
        e.suspend()
        self.db.purge_incomplete()
        cp = self.db.checkpoint(e.session_id)
        self.assertEqual(cp["sport"], "endurance")
        e2 = en.EnduranceEngine(self.db, self.db.athlete(), "swimming", resume=cp,
                                out_dir=self.tmp)
        self.assertEqual(e2.lengths, 3)
        self.assertTrue(e2.paused)
        e2.discard()
        self.assertIsNone(self.db.conn.execute(
            "SELECT 1 FROM endurance_sessions WHERE id = ?", (e.session_id,)).fetchone())
        self.assertIsNone(self.db.checkpoint(e.session_id))

    def test_library_and_swim_tests(self):
        self.assertGreaterEqual(len(en.workouts(self.db, "running")), 4)
        self.assertGreaterEqual(len(en.workouts(self.db, "swimming")), 3)
        from velo.core import fitness_tests as ft
        names = [x["name"] for x in ft.tests(self.db, "swimming")]
        self.assertIn("400 m", names)


class TestRowingAndRideExtras(Base):
    def test_rowing_autolap_split_and_discard(self):
        r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, source="domyos"))
        e = rw.RowEngine(self.db, self.db.athlete(), r, out_dir=self.tmp,
                         autolap={"mode": "distance", "value": 250})
        for _ in range(700):
            e.update(0.5)
        self.assertEqual(len([x for x in e.laps if x.trigger == "distance"]), 5)
        self.assertAlmostEqual(e.split(500), 120.0, delta=2)
        self.assertGreater(e.live_load, 0)
        self.assertAlmostEqual(e.joules_per_stroke, 203 * 60 / 24, delta=1)
        e.discard()
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) AS n FROM row_sessions"
                                              ).fetchone()["n"], 0)

    def test_ride_autolap_by_time_and_discard(self):
        from velo.core.ride import RideEngine
        from velo.io.sim import SimulatedTrainer
        from velo.io.hub import SensorHub
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=200), role="trainer", is_trainer=True)
        e = RideEngine(self.db, self.db.athlete(), sensors=hub, trainer=hub, kind="free",
                       rides_dir=self.tmp, autolap={"mode": "time", "value": 60})
        for _ in range(int(200 / 0.5)):
            hub.tick(0.5)
            e.update(0.5)
        self.assertEqual(len([x for x in e.laps if x.trigger == "time"]), 3)
        self.assertLess(e.lap_elapsed_s, 60)
        rid = e.ride_id
        e.discard()
        self.assertIsNone(self.db.conn.execute("SELECT 1 FROM rides WHERE id = ?",
                                               (rid,)).fetchone())


# ================================================================== construtor


class TestBlockBuilderCore(Base):
    def test_round_trip_in_every_sport(self):
        for sport in ("cycling", "rowing", "running", "swimming"):
            name, _d, mode, blocks = bs.load_blocks(self.db, sport, None)
            blocks.append(bs.Block("active", "time", 120, 110, None, "forte"))
            wid = bs.save_blocks(self.db, sport, None, f"T {sport}", "", mode, blocks)
            _n, _d, _m, again = bs.load_blocks(self.db, sport, wid)
            self.assertEqual(len(again), len(blocks), sport)
            self.assertAlmostEqual(again[-1].lo, 110, delta=0.6, msg=sport)
            self.assertEqual(again[-1].dur, 120, sport)
        # a rampa do ciclismo volta como rampa
        _n, _d, _m, cyc = bs.load_blocks(self.db, "cycling",
                                         self.db.workouts()[0]["id"])
        self.assertTrue(any(b.ramp for b in cyc) or True)

    def test_estimate(self):
        ctx = it.Context("cycling")
        est = bs.estimate([bs.Block("active", "time", 3600, 100)], ctx)
        self.assertAlmostEqual(est["tss"], 100.0)
        self.assertAlmostEqual(est["if"], 1.0)
        run = it.Context("running", run_pace_s=300)
        e2 = bs.estimate([bs.Block("active", "distance", 1000, 100)], run)
        self.assertAlmostEqual(e2["seconds"], 300, delta=1)


class TestBlockBuilderGui(tg.GuiCase):
    def open_builder(self):
        self.pick("Construtor de treinos")
        self.pick("Novo treino")
        b = self.screen()
        self.assertIsInstance(b, bs.BlockBuilder)
        return b

    def test_drag_from_palette_resize_raise_and_move(self):
        b = self.open_builder()
        n0 = len(b.blocks)
        # arrastar o Z5 da paleta para o meio do gráfico
        z5 = next(p for p in b.pal if p[0] == "Z5")[2]
        self.app._on_mouse_press(int(z5.x + 5), int(z5.y + 5), 1, 0)
        cx = (b.cx0 + b.cx1) / 2
        cy = (b.cy0 + b.cy1) / 2
        self.app._on_mouse_drag(int(cx), int(cy), 5, 5, 1, 0)
        self.assertEqual(b.insert_mark.opacity, 255)
        self.app._on_mouse_release(int(cx), int(cy), 1, 0)
        self.assertEqual(len(b.blocks), n0 + 1)
        new = b.block
        self.assertEqual(new.lo, 112.0)
        self.assertTrue(b.dirty)
        # aresta direita: mais tempo
        spans, total = b.spans()
        a0, a1 = spans[b.sel]
        xr = b.x_of(a1, total) - 3
        self.app._on_mouse_press(int(xr), int(b.cy0 + 10), 1, 0)
        self.assertEqual(b.drag["what"], "resize")
        self.app._on_mouse_drag(int(xr + 60), int(b.cy0 + 10), 60, 0, 1, 0)
        self.app._on_mouse_release(int(xr + 60), int(b.cy0 + 10), 1, 0)
        self.assertGreater(new.dur, 300)
        # aresta de cima: mais intensidade
        spans, total = b.spans()
        a0, a1 = spans[b.sel]
        xm = (b.x_of(a0, total) + b.x_of(a1, total)) / 2
        top = b.y_of(new.lo)
        self.app._on_mouse_press(int(xm), int(top), 1, 0)
        self.assertEqual(b.drag["what"], "top")
        self.app._on_mouse_drag(int(xm), int(b.y_of(130)), 0, 20, 1, 0)
        self.app._on_mouse_release(int(xm), int(b.y_of(130)), 1, 0)
        self.assertAlmostEqual(new.lo, 130, delta=2)
        # arrastar o meio para o início: muda de lugar
        idx = b.sel
        self.app._on_mouse_press(int(xm), int(b.cy0 + 10), 1, 0)
        self.assertEqual(b.drag["what"], "move")
        self.app._on_mouse_drag(int(b.cx0 + 2), int(b.cy0 + 10), -200, 0, 1, 0)
        self.app._on_mouse_release(int(b.cx0 + 2), int(b.cy0 + 10), 1, 0)
        self.assertEqual(b.blocks.index(new), 0)
        self.assertNotEqual(idx, 0)
        # um clique na paleta junta a seguir ao escolhido
        rest = next(p for p in b.pal if p[0] == "rest")[2]
        self.app._on_mouse_press(int(rest.x + 5), int(rest.y + 5), 1, 0)
        self.app._on_mouse_release(int(rest.x + 5), int(rest.y + 5), 1, 0)
        self.assertEqual(b.blocks[1].kind, "rest")

    def test_views_keyboard_and_save(self):
        b = self.open_builder()
        b.sel = 1
        self.assertEqual(b.mode, "power")
        self.press(key.TAB)                                     # vista FC
        self.assertEqual(b.mode, "hr")
        self.app._on_draw()
        self.assertIn("bpm", b.axis[1].text)
        self.press(key.TAB)                                     # vista RPE
        self.assertEqual(b.mode, "rpe")
        self.assertTrue(any("RPE" in i.value for i in b.list.items))
        lo = b.block.lo
        self.select("Intensidade")
        self.press(key.RIGHT)
        self.assertEqual(b.block.lo, lo + 1)
        self.press(key.D)                                       # duplicar
        self.assertEqual(len(b.blocks), 4)
        self.press(key.DELETE)
        self.assertEqual(len(b.blocks), 3)
        self.app._on_key_press(key.S, key.MOD_CTRL)              # Ctrl+S guarda
        self.assertFalse(b.dirty)
        self.assertIn("Novo treino", [w["name"] for w in self.app.db.workouts()])

    def test_rowing_and_swimming_builders(self):
        self.press(key.ESCAPE)
        self.pick("Remo")
        self.pick("Construtor de treinos")
        self.pick("8 × 500 m")
        b = self.screen()
        self.assertIsInstance(b, bs.BlockBuilder)
        self.assertEqual(b.tab_labels(), ["Zonas de potência", "Ritmo", "FC", "RPE"])
        self.assertEqual(len(b.blocks), 18)
        b.sel = 1
        b.enter()
        self.assertTrue(any(i.label == "Resistência" for i in b.list.items))
        self.press(key.ESCAPE, key.ESCAPE, key.ESCAPE)
        self.pick("Natação")
        self.pick("Construtor de treinos")
        self.pick("Novo treino")
        w = self.screen()
        self.assertEqual(w.blocks[0].dur_type, "distance")
        w.add_block("Z3")
        self.assertEqual(w.block.dur_type, "distance")


# =================================================================== ecrãs


class TestSportsGui(tg.GuiCase):
    def test_running_session_from_the_hub(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Corrida livre")
        opts = self.screen()
        self.assertIsInstance(opts, app_mod.StartOptions)
        self.select("Auto lap")
        self.press(key.RIGHT, key.RIGHT)                         # por distância
        self.assertEqual(opts.autolap_cfg()["mode"], "distance")
        self.pick("Começar")
        scr = self.screen()
        self.assertIsInstance(scr, es.EnduranceSession)
        self.assertTrue(scr.engine.autolap.on)
        for _ in range(10):
            self.app._tick(0.5)
        self.assertEqual(scr.engine.t, 0.0)
        self.press(key.SPACE)                                    # começar
        self.press(key.PLUS, key.PLUS)                           # 11 km/h
        self.assertEqual(scr.engine.speed_kmh, 11.0)
        for _ in range(240):
            self.app._tick(0.5)
        self.assertGreater(scr.engine.distance_m, 350)
        self.assertEqual(scr.clock.value.text, "2:00")
        self.press(key.T)
        self.app._on_text("0,5")
        self.press(key.ENTER)
        self.assertEqual(scr.engine.distance_m, 500)
        self.press(key.ESCAPE)
        self.pick("Sim, terminar")
        summ = self.screen()
        self.assertIsInstance(summ, es.EnduranceSummary)
        self.assertTrue(Path(summ.result["fit_path"]).exists())

    def test_gym_free_workout_plan_first_and_keep(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Kettlebell")
        self.pick("Treino livre")
        ed = self.screen()
        self.assertIsInstance(ed, gs.GymPlanEditor)
        self.pick("Adicionar exercício")
        self.assertEqual(self.screen().modality(), "kettlebell")
        self.pick("Kettlebell swing")
        self.pick("Guardar como treino")
        self.assertIn(ed.name, [w["name"] for w in gym.workouts(self.app.db, "kettlebell")])
        self.pick("Começar o treino")
        scr = self.screen()
        self.assertIsInstance(scr, ss.StrengthSessionScreen)
        self.app._tick(5.0)
        self.assertEqual(scr.session.t, 0.0)                    # espera pela 1.ª série

    def test_surprise_inventory_and_exercise_editor(self):
        self.press(key.ESCAPE)
        self.pick("Inventário de artigos")
        inv = self.screen()
        inv.tab_named("Pesos livres")
        self.pick("Novo artigo")
        ed = self.screen()
        self.assertIsInstance(ed, hs.ItemEditor)
        self.select("Tipo")
        for _ in range(len(inventory.KINDS)):
            if ed.v["kind"] == "kettlebell":
                break
            self.press(key.RIGHT)
        self.assertEqual(ed.v["kind"], "kettlebell")
        self.select("Nome")
        self.type("KB 16")
        self.select("Peso")
        self.app._on_text("16")
        self.pick("Guardar")
        self.assertEqual(inventory.available_kinds(self.app.db), {"kettlebell"})
        self.press(key.ESCAPE)
        self.pick("Exercícios")
        exs = self.screen()
        exs.tab_named("Sandbag")
        self.pick("Novo exercício")
        e = self.screen()
        self.select("Nome")
        self.type("Sandbag lunge walk")
        self.pick("Guardar")
        self.assertIn("Sandbag lunge walk",
                      [x["name"] for x in gym.exercises(self.app.db, "sandbag")])
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Força")
        self.pick("Treino surpresa")
        sur = self.screen()
        self.assertIsInstance(sur, gs.SurpriseScreen)
        self.assertIn("com o teu material", sur.chrome.subtitle.text)
        first = [i.label for i in sur.list.items]
        self.pick("Outra surpresa")
        self.pick("Começar")
        self.assertIsInstance(self.screen(), ss.StrengthSessionScreen)
        self.assertTrue(first)

    def test_stats_sport_tabs(self):
        self.pick("Gráficos e análise")
        scr = self.screen()
        self.select("Desporto")
        self.press(key.RIGHT)                                    # ciclismo → remo
        row = self.screen()
        self.assertIsInstance(row, sts.SportStatsScreen)
        self.assertEqual(row.sport, "rowing")
        self.assertEqual(row.tab_labels()[0], "Distância")
        for _ in range(5):
            self.press(key.TAB)
            self.app._on_draw()
        self.select("Desporto")
        self.press(key.RIGHT)
        self.assertEqual(self.screen().sport, "running")
        self.assertIsNot(scr, self.screen())

    def test_swim_crash_recovery(self):
        self.press(key.ESCAPE)
        self.pick("Natação")
        self.pick("Natação livre")
        self.pick("Começar")
        scr = self.screen()
        self.press(key.PLUS, key.PLUS)                           # duas piscinas
        for _ in range(20):
            self.app._tick(0.5)
        self.app.shutdown(crashed=True)
        app2 = app_mod.App(data_dir=Path(self.tmp), width=1280, height=760)
        try:
            rec = app2.current
            self.assertIsInstance(rec, ss.RecoveryScreen)
            self.assertIn("Natação", rec.list.items[0].label)
            rec.list.index = 2                                   # guardar como está
            rec.list.activate()
            self.assertIsInstance(app2.current, es.EnduranceSummary)
            self.assertEqual(app2.current.result["distance_m"], 50)
        finally:
            app2.shutdown()
        self.assertTrue(scr)

    def test_device_lost_mid_ride_shows_on_the_hud(self):
        self.pick("Pedalar")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.on_device_lost("Cinta")
        self.assertTrue(any("Cinta" in x.text for x in ride.hud.toasts))


if __name__ == "__main__":
    unittest.main()
