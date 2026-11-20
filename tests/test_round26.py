"""Ronda 26: tags na construção de treinos (todos os desportos) e o construtor de Conditioning
por blocos de vários desportos (Manual/ERG, o construtor do desporto noutra página com
«Adicionar bloco a treino de Conditioning», duplicar e arrastar)."""
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

from perennia.core import conditioning as cnd  # noqa: E402
from perennia.core import laps_session as ls  # noqa: E402
from perennia.core import options, tags  # noqa: E402
from perennia.core.blocks import Block  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")


def bike(erg: bool = True, watts=(60, 100)) -> dict:
    b = cnd.new_block("cycling", "erg" if erg else "manual")
    b.update(cnd.endurance_payload([Block("active", "time", 60, w) for w in watts], "power"))
    return b


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))
        options.apply(self.db)

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestAutoTags(Tmp):
    def test_builder_auto_tags_per_sport(self):
        self.assertEqual(tags.builder_auto_tags("cycling"),
                         ["Workout", "Cycling", "Indoor Cycling", "Perennia"])
        self.assertEqual(tags.builder_auto_tags("running")[:2], ["Workout", "Running"])
        self.assertEqual(tags.builder_auto_tags("strength", modality="mobility"),
                         ["Workout", "Gym", "Mobility", "Indoor Strength", "Perennia"])
        self.assertEqual(tags.builder_auto_tags("conditioning", sports=["cycling", "gym"]),
                         ["Conditioning", "Workout", "Cycling", "Gym", "Perennia"])

    def test_auto_tags_match_what_the_session_gets(self):
        """O que o construtor mostra é o que a sessão desse treino recebe."""
        info = tags.defaults(self.db, "cycling", workout_id="w1")
        self.assertTrue(set(tags.builder_auto_tags("cycling")) <=
                        set(info["activity"] + info["sport"] + info["session"]))

    def test_gym_sessions_get_the_modality_tag(self):
        from perennia.core import gym
        from perennia.core import strength as st
        gym.ensure(self.db)
        ex = self.db.conn.execute("SELECT id FROM exercises LIMIT 1").fetchone()["id"]
        wid = gym.save_plan(self.db, None, "Mob", "", [{"exercise_id": ex, "sets": 1, "reps": 5,
                                                        "load_kg": None, "rpe": None,
                                                        "rest_s": 10}])
        self.db.conn.execute("UPDATE strength_workouts SET modality = 'mobility' WHERE id = ?",
                             (wid,))
        s = st.StrengthSession(self.db, self.db.athlete(), wid, out_dir=self.tmp / "s")
        self.assertEqual(s.tag_sports(), ["Gym", "Mobility"])
        s.action()
        for _ in range(5):
            s.update(1.0)
        s.action()
        s.finish()
        self.assertEqual(tags.load(self.db, "strength", s.session_id)["sport"],
                         ["Gym", "Mobility"])


class TestConditioningModel(Tmp):
    def test_blocks_round_trip_and_items(self):
        blocks = [bike(), cnd.new_block("rest"), cnd.new_block("gym", modality="hiit")]
        items = cnd.to_items(self.db, blocks)
        self.assertEqual([i["kind"] for i in items], ["bike", "rest", "strength"])
        self.assertEqual(items[0]["control"], "erg")
        self.assertEqual(items[0]["seconds"], 120)
        self.assertEqual(items[1]["seconds"], cnd.REST_DEFAULT_S)
        self.assertEqual(items[2]["seconds"], cnd.GYM_DEFAULT_S)
        pid = ls.save_plan(self.db, None, "C", "conditioning", items)
        self.assertEqual(cnd.from_items(ls.plan(self.db, pid)["items"]), blocks)

    def test_old_plans_still_open_as_blocks(self):
        old = [{"kind": "treadmill", "seconds": 300}, {"kind": "rest", "seconds": 60},
               {"kind": "strength", "exercise_id": 3, "reps": 10, "name": "Agachamento"},
               {"kind": "rowing", "seconds": 240}]
        blocks = cnd.from_items(old)
        self.assertEqual([b["sport"] for b in blocks], ["running", "rest", "gym", "rowing"])
        self.assertEqual(cnd.seconds(self.db, blocks[0]), 300)
        back = cnd.to_items(self.db, blocks)
        self.assertEqual(back[2]["exercise_id"], 3)                 # o exercício não se perde
        self.assertEqual(back[2]["reps"], 10)

    def test_duplicate_move_and_totals(self):
        blocks = [bike(), cnd.new_block("rest", seconds=60), cnd.new_block("gym")]
        self.assertEqual(cnd.duplicate(blocks, 0), 1)
        self.assertEqual([b["sport"] for b in blocks], ["cycling", "cycling", "rest", "gym"])
        self.assertEqual(cnd.move(blocks, 3, 0), 0)
        self.assertEqual([b["sport"] for b in blocks], ["gym", "cycling", "cycling", "rest"])
        by = cnd.total_by_sport(self.db, blocks)
        self.assertEqual(by["cycling"], 240 + 60)                    # o descanso vai com o de antes
        self.assertEqual(cnd.sports_used(blocks), ["gym", "cycling"])

    def test_the_options_change_the_defaults(self):
        self.db.set("cond_rest_default_s", 45)
        self.db.set("cond_gym_block_default_s", 600)
        options.apply(self.db)
        try:
            self.assertEqual(cnd.new_block("rest")["seconds"], 45)
            self.assertEqual(cnd.seconds(self.db, cnd.new_block("gym")), 600)
        finally:
            self.db.set("cond_rest_default_s", 120)
            self.db.set("cond_gym_block_default_s", 900)
            options.apply(self.db)


class TestConditioningSession(Tmp):
    def test_erg_block_sets_the_power_of_each_step_and_parts_include_cycling(self):
        class Hub:
            def __init__(self):
                self.watts = []

            def reading(self):
                return None

            def set_target_power(self, w):
                self.watts.append(w)
        hub = Hub()
        items = cnd.to_items(self.db, [bike(True, (60, 100)), cnd.new_block("rest", seconds=30),
                                       bike(False, (80,))])
        s = ls.LapSession(self.db, self.db.athlete(), "conditioning", sensors=hub,
                          out_dir=self.tmp / "s", plan=items)
        s.start_planned()
        step = s.current_step()
        self.assertEqual(step[0], 0)
        for _ in range(125):
            s.update(1.0)
        self.assertEqual(hub.watts, [150, 250])                       # 60 % e 100 % de 250 W
        self.assertEqual(s.current.kind, "rest")
        for _ in range(100):
            s.update(1.0)
        self.assertEqual(hub.watts, [150, 250])                       # o manual não mexe no rolo
        res = s.finish()
        self.assertEqual([p["sport"] for p in res["parts"]], ["cycling"])
        self.assertTrue(res["parts"][0]["fit_path"].endswith("_cycling.fit"))
        self.assertIn("Cycling", tags.load(self.db, "strength", res["session_id"])["sport"])


class TestBuilderUI(tg.GuiCase):
    def open(self):
        from perennia.ui.conditioning_builder import ConditioningBuilder
        scr = ConditioningBuilder(self.app, None)
        self.app.push(scr)
        scr.enter()
        return scr

    def test_add_a_cycling_block_through_its_own_builder(self):
        from perennia.ui.builder_screens import BlockBuilder
        scr = self.open()
        scr._add()
        self.pick("Ciclismo")                                      # a lista dos desportos
        self.pick("ERG")                                            # Manual ou ERG
        bb = self.screen()
        self.assertIsInstance(bb, BlockBuilder)
        self.assertEqual(bb.control, "erg")
        labels = [i.label for i in bb.list.items]
        self.assertIn("Adicionar bloco a treino de Conditioning", labels)
        self.assertNotIn("Guardar", labels)
        n = len(bb.blocks)
        self.pick("Adicionar bloco a treino de Conditioning")
        self.assertIs(self.screen(), scr)
        self.assertEqual(len(scr.blocks), 1)
        self.assertEqual(scr.blocks[0]["sport"], "cycling")
        self.assertEqual(scr.blocks[0]["control"], "erg")
        self.assertEqual(len(scr.blocks[0]["blocks"]), n)
        # editar: abre o mesmo construtor com «Atualizar bloco…»
        scr._edit(0)
        self.assertIn("Atualizar bloco no treino de Conditioning",
                      [i.label for i in self.screen().list.items])
        self.screen()._cond_cancel()

    def test_gym_block_asks_the_modality_and_opens_the_strength_builder(self):
        from perennia.ui.strength_builder_screens import StrengthBuilder
        scr = self.open()
        scr._add()
        self.pick("Ginásio")
        self.pick("Mobilidade")
        sb = self.screen()
        self.assertIsInstance(sb, StrengthBuilder)
        self.assertEqual(sb.mod, "mobility")
        self.assertEqual(sb._focusables()[1], ("cond_add",))
        sb.activate(("cond_add",))
        self.assertIs(self.screen(), scr)
        self.assertEqual(scr.blocks[0]["modality"], "mobility")
        self.assertIn("Mobility", scr._auto_tags() + ["Mobility"])

    def test_rest_duplicate_move_remove_and_save(self):
        scr = self.open()
        scr._add_sport("rest")
        scr.blocks.append(bike())
        scr.enter()
        scr._select(0)
        self.press(key.D)                                          # duplica o descanso
        self.assertEqual([b["sport"] for b in scr.blocks], ["rest", "rest", "cycling"])
        scr._select(2)
        scr.on_key(key.UP, key.MOD_ALT)
        self.assertEqual(scr.blocks[1]["sport"], "cycling")
        self.assertEqual(scr.sel, 1)
        scr.name = "Misto"
        scr._save()
        self.assertIsNotNone(scr.pid)
        got = ls.plan(self.app.db, scr.pid)
        self.assertEqual([i["kind"] for i in got["items"]], ["rest", "bike", "rest"])
        self.assertFalse(scr.has_unsaved())

    def test_drag_on_the_strip_moves_a_block(self):
        scr = self.open()
        scr.blocks = [cnd.new_block("rest", seconds=60), bike(), cnd.new_block("gym")]
        scr.enter()
        a0, a1 = scr._geo[0]
        z0, z1 = scr._geo[2]
        y = scr.sy0 + 20
        self.assertTrue(scr.on_mouse((a0 + a1) / 2, y))
        scr.on_drag(z1 - 2, y, 10, 0)
        scr.on_release(z1 - 2, y)
        self.assertEqual([b["sport"] for b in scr.blocks], ["cycling", "gym", "rest"])

    def test_tags_row_shows_automatic_tags_from_the_blocks(self):
        scr = self.open()
        scr.blocks = [bike(), cnd.new_block("gym", modality="strength")]
        scr.enter()
        row = next(i for i in scr.list.items if i.label == "Tags")
        self.assertTrue(row.value.startswith("Conditioning · Workout · Cycling · Gym"))

    def test_every_builder_has_tags_with_automatic_ones(self):
        from perennia.ui.builder_screens import BlockBuilder
        from perennia.ui.strength_builder_screens import StrengthBuilder
        for sport in ("cycling", "running", "rowing", "swimming"):
            b = BlockBuilder(self.app, sport, None, control="manual")
            b.enter()
            row = next(i for i in b.list.items if i.label == "Tags do treino")
            self.assertIn(tags.SPORT_TAGS[sport], row.value, sport)
        s = StrengthBuilder(self.app, "hiit", None)
        self.assertIn("HIIT", s._auto_tags())

    def test_simple_editor_is_no_longer_offered(self):
        from perennia.ui import gym_screens as gs
        src = Path(gs.__file__).read_text(encoding="utf-8")
        self.assertNotIn("GymPlanEditor(a,", src)
        from perennia.ui import sport_screens as ss
        self.assertNotIn("StrengthWorkoutEditor(a, None)", Path(ss.__file__).read_text(
            encoding="utf-8"))

    def test_conditioning_menus_open_the_new_builder(self):
        from perennia.ui import gym_screens as gs
        from perennia.ui.conditioning_builder import ConditioningBuilder
        self.assertIsInstance(gs.LapPlanEditor(self.app, None), ConditioningBuilder)


if __name__ == "__main__":
    unittest.main()


from tests import textfit  # noqa: E402


@unittest.skipUnless(textfit.available(), "sem a Pillow/letra não há medição")
class TestTextFits(tg.GuiCase):
    """O construtor de Conditioning, os construtores em modo «bloco» e as tags: nada sai das
    caixas, na janela mais pequena e na habitual."""

    def check(self, w, h):
        from tests.test_round23 import overflow, resize
        from perennia.ui.builder_screens import BlockBuilder
        from perennia.ui.conditioning_builder import ConditioningBuilder
        from perennia.ui.strength_builder_screens import StrengthBuilder
        from perennia.ui.tag_popup import WorkoutTagsPopup
        resize(self.app, w, h)
        bad = []
        scr = ConditioningBuilder(self.app, None)
        scr.name = "Um treino de Conditioning com um nome mesmo muito comprido para caber"
        scr.blocks = [bike(), cnd.new_block("rest", seconds=20), cnd.new_block("gym"),
                      bike(False, (50, 60, 70, 80)), cnd.new_block("rowing", "erg")]
        scr.blocks[0]["name"] = "Sweet spot com muitas palavras e um nome longuíssimo"
        self.app.push(scr)
        scr.enter()
        bad += [(w, "cond", x["text"]) for x in overflow(self.app)]
        self.app.push(BlockBuilder(self.app, "cycling", None, control="erg",
                                   cond_cb=lambda b: None))
        self.app.stack[-1].enter()
        bad += [(w, "bloco", x["text"]) for x in overflow(self.app)]
        self.app.pop()
        self.app.push(StrengthBuilder(self.app, "strength", None, cond_cb=lambda b: None))
        bad += [(w, "força", x["text"]) for x in overflow(self.app)]
        self.app.pop()
        self.app.push(WorkoutTagsPopup(self.app, scr.name, ["Uma tag", "Outra"], lambda t: None,
                                       auto=scr._auto_tags()))
        self.app.stack[-1].enter()
        bad += [(w, "tags", x["text"]) for x in overflow(self.app)]
        self.app.pop()
        self.app.pop()
        return bad

    def test_small_and_usual_windows(self):
        self.assertEqual(self.check(1024, 640) + self.check(1280, 760), [])
