"""Ronda 24: as tags (sempre em inglês) — o tipo de sessão (`Free Session`, `Workout`,
`Challenge` + jogo, `Test`) em todos os desportos, as tags dos treinos que as sessões herdam,
o preenchimento das sessões antigas e a consulta por uma ou mais tags (Análise AdHoc)."""
from __future__ import annotations

import csv
import importlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import adhoc, backup, games, gym, i18n, tags  # noqa: E402
from perennia.core import rowing as rw  # noqa: E402
from perennia.core import strength as st  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402
from perennia.core.ride import RideEngine  # noqa: E402
from perennia.io import rower as rio  # noqa: E402
from perennia.io.hub import SensorHub  # noqa: E402
from perennia.io.sim import SimulatedTrainer  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
DT = 0.25


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250,
                                     lthr=165))
        i18n.set_language("pt")

    def tearDown(self):
        i18n.set_language("pt")
        try:
            self.db.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ride(self, **kw) -> dict:
        """Uma sessão de ciclismo curta, do princípio ao fim; devolve o resultado."""
        athlete = self.db.athlete()
        trainer = SimulatedTrainer(base_power=200, with_hr=True)
        hub = SensorHub()
        hub.add_source(trainer, role="trainer", is_trainer=True)
        e = RideEngine(self.db, athlete, sensors=hub, trainer=hub, rides_dir=self.tmp / "rides",
                       **kw)
        for _ in range(int(20 / DT)):
            hub.tick(DT)
            e.update(DT)
        return e.finish()


class TestKindTags(Tmp):
    def test_every_kind_of_session_has_its_tags_in_english(self):
        K = tags.kind_tags
        self.assertEqual(K(*tags.kind_of()), ["Free Session"])
        self.assertEqual(K(*tags.kind_of(kind="route")), ["Free Session"])
        self.assertEqual(K(*tags.kind_of(workout_id="w1")), ["Workout"])
        self.assertEqual(K(*tags.kind_of(game_key="zone_hero")), ["Challenge", "Zone Hero"])
        self.assertEqual(K(*tags.kind_of(game_key="regatta")), ["Challenge", "Regatta"])
        self.assertEqual(K(*tags.kind_of(game_key="seg_pace")), ["Challenge", "Segment Pace"])
        self.assertEqual(K(*tags.kind_of(kind="chase")), ["Challenge", "Chase"])
        self.assertEqual(K(*tags.kind_of(kind="ftp_test", test="ramp")), ["Test", "FTP Ramp"])
        self.assertEqual(K(*tags.kind_of(test="row_2000")), ["Test", "Row 2000 m"])
        # um jogo ganha a um treino (um jogo de cabo de guerra também leva um treino por baixo)
        self.assertEqual(K(*tags.kind_of(workout_id="w", game_key="tug"))[0], "Challenge")

    def test_a_known_game_name_is_english_in_every_language(self):
        for key in games.GAMES + rw.ROW_GAMES:
            i18n.set_language("pt")
            pt = tags.kind_tags("game", key)
            i18n.set_language("en")
            en = tags.kind_tags("game", key)
            self.assertEqual(pt, en, key)
            self.assertTrue(all(t.isascii() for t in pt), pt)

    def test_workout_type_labels_are_english_even_in_portuguese(self):
        i18n.set_language("pt")
        self.assertEqual(tags.type_label("threshold"), "Threshold")
        self.assertEqual(tags.type_label("endurance"), "Aerobic endurance")
        self.assertEqual(tags.type_labels()[0], "Recovery")
        self.assertEqual(tags.labels({"workout_type": "vo2max", "activity": ["Free Session"]}),
                         ["Free Session", "VO2max"])
        self.assertEqual(tags.type_key("Limiar"), "threshold")       # as regras ainda aceitam PT

    def test_fit_text_keeps_whole_tags_and_the_session_type_first(self):
        info = {"activity": ["Challenge", "Zone Hero"], "workout_type": "threshold",
                "session": ["Perennia", "Indoor Cycling"], "custom": ["A" * 30, "Etiqueta"]}
        text = tags.fit_text(info)
        self.assertLessEqual(len(text), 63)
        self.assertTrue(text.startswith("Challenge · Zone Hero · Threshold"))
        self.assertNotIn("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA ·", text[:0])
        for part in text.split(" · "):
            self.assertIn(part, tags.labels(info))                  # nada cortado a meio


class TestSessionsGetTheirTags(Tmp):
    def stored(self, sport, sid) -> dict:
        return tags.load(self.db, sport, sid)

    def test_cycling_free_session(self):
        res = self.ride(kind="route")
        self.assertEqual(res["tags"]["activity"], ["Free Session"])
        info = self.stored("cycling", res["ride_id"])
        self.assertEqual(info["activity"], ["Free Session"])
        self.assertIn("Indoor Cycling", info["session"])

    def test_cycling_game_gets_challenge_and_the_game(self):
        spec = {"key": "zone_hero", "minutes": 1, "bots": 0, "seed": 3}
        game = games.create(spec, self.db.athlete(), self.db)
        res = self.ride(kind="game", game=game)
        self.assertEqual(self.stored("cycling", res["ride_id"])["activity"],
                         ["Challenge", "Zone Hero"])

    def test_cycling_chase_and_ftp_test(self):
        res = self.ride(kind="chase", chase_level="easy")
        self.assertEqual(self.stored("cycling", res["ride_id"])["activity"],
                         ["Challenge", "Chase"])
        res = self.ride(kind="ftp_test", meta={"ftp_protocol": "ramp"})
        self.assertEqual(self.stored("cycling", res["ride_id"])["activity"],
                         ["Test", "FTP Ramp"])

    def test_rowing_free_workout_game_and_test(self):
        def row(**kw):
            r = rio.ScriptedRower(rio.RowerData(strokes=0, spm=24, pace_s=120.0, resistance=6,
                                                hr_bpm=150, source="domyos"))
            e = rw.RowEngine(self.db, self.db.athlete(), r, out_dir=self.tmp, **kw)
            for i in range(60):
                r.current.strokes = i // 5
                e.update(0.5)
            return e, e.finish()
        e, res = row()
        self.assertEqual(self.stored("rowing", e.session_id)["activity"], ["Free Session"])
        e, res = row(game_spec={"key": "regatta", "distance": 500, "bots": 1, "seed": 1})
        self.assertEqual(self.stored("rowing", e.session_id)["activity"],
                         ["Challenge", "Regatta"])
        e, res = row(protocol="row_500")
        self.assertEqual(self.stored("rowing", e.session_id)["activity"],
                         ["Test", "Row 500 m"])
        wid = rw.save_workout(self.db, None, "Remo teste", "", [
            rw.Step("active", "time", 30, "none")])
        e, res = row(workout_id=wid)
        self.assertEqual(self.stored("rowing", e.session_id)["activity"], ["Workout"])

    def test_gym_free_workout_surprise_and_laps(self):
        gym.ensure(self.db)
        ex = self.db.conn.execute("SELECT id FROM exercises LIMIT 1").fetchone()["id"]
        item = {"exercise_id": ex, "sets": 1, "reps": 5, "load_kg": None, "rpe": None,
                "rest_s": 10}
        saved = gym.save_plan(self.db, None, "Guardado", "", [item])
        hidden = gym.save_plan(self.db, None, "Montado", "", [item], hidden=True)

        def session(wid, **kw):
            s = st.StrengthSession(self.db, self.db.athlete(), str(wid),
                                   out_dir=self.tmp / "strength", **kw)
            s.action()
            for _ in range(10):
                s.update(1.0)
            s.action()
            for _ in range(3):
                s.update(1.0)
            s.finish()
            return s
        self.assertEqual(self.stored("strength", session(saved).session_id)["activity"],
                         ["Workout"])
        self.assertEqual(self.stored("strength", session(hidden).session_id)["activity"],
                         ["Free Session"])
        self.assertEqual(self.stored("strength", session(hidden, free=True).session_id)["activity"],
                         ["Free Session"])
        self.assertEqual(self.stored("strength", session(
            hidden, challenge="surprise").session_id)["activity"], ["Challenge", "Surprise"])

    def test_lap_sessions(self):
        from perennia.core import laps_session as ls

        def laps(**kw):
            s = ls.LapSession(self.db, self.db.athlete(), "conditioning",
                              out_dir=self.tmp / "strength", **kw)
            for _ in range(5):
                s.update(1.0)
            s.lap("manual") if hasattr(s, "lap") else None
            s.finish()
            return s
        free = laps()
        self.assertEqual(self.stored("strength", free.session_id)["activity"], ["Free Session"])
        plan = [{"kind": "cardio", "seconds": 30}, {"kind": "rest", "seconds": 10}]
        self.assertEqual(self.stored("strength", laps(plan=plan).session_id)["activity"],
                         ["Workout"])
        self.assertEqual(self.stored("strength", laps(plan=plan, challenge="tabata").session_id
                                     )["activity"], ["Challenge", "Tabata x3"])


class TestWorkoutTags(Tmp):
    def test_set_get_clean_and_catalog(self):
        got = tags.set_workout_tags(self.db, "cycling", "w1",
                                    ["  Base  ", "base", "Z2", "", "Long   ride"])
        self.assertEqual(got, ["Base", "Z2", "Long ride"])
        self.assertEqual(tags.workout_tags(self.db, "cycling", "w1"), got)
        self.assertEqual(tags.workout_tags(self.db, "rowing", "w1"), [])       # por desporto
        tags.set_workout_tags(self.db, "cycling", "w1", ["Z2"])
        self.assertEqual(tags.workout_tags(self.db, "cycling", "w1"), ["Z2"])
        self.assertIn("Base", tags.known_tags(self.db))                         # sugere-se

    def test_a_session_inherits_the_workout_tags_and_can_drop_them(self):
        tags.set_workout_tags(self.db, "cycling", "w1", ["Base", "Winter"])
        info = tags.defaults(self.db, "cycling", workout_id="w1")
        self.assertEqual(info["custom"], ["Base", "Winter"])
        self.assertEqual(info["activity"], ["Workout"])
        res = tags.resolve(self.db, "cycling", "s1", {"custom": ["Base"]}, workout_id="w1")
        self.assertEqual(tags.load(self.db, "cycling", "s1")["custom"], ["Base"])
        self.assertEqual(res["activity"], ["Workout"])                          # esse fica sempre
        # mudar o treino depois não mexe nas sessões que já foram feitas
        tags.set_workout_tags(self.db, "cycling", "w1", ["Other"])
        self.assertEqual(tags.load(self.db, "cycling", "s1")["custom"], ["Base"])

    def test_the_automatic_tags_cannot_be_removed_by_the_popup(self):
        res = tags.resolve(self.db, "cycling", "s2",
                           {"activity": [], "session": [], "custom": ["Free Session", "Mine"]})
        self.assertEqual(res["activity"], ["Free Session"])
        self.assertEqual(res["custom"], ["Mine"])

    def test_workouts_with_tags(self):
        tags.set_workout_tags(self.db, "cycling", "a", ["Base", "Winter"])
        tags.set_workout_tags(self.db, "rowing", "b", ["Base"])
        tags.set_workout_type(self.db, "rowing", "b", "threshold")
        both = {(w["sport"], w["id"]) for w in tags.workouts_with(self.db, "Base")}
        self.assertEqual(both, {("cycling", "a"), ("rowing", "b")})
        self.assertEqual({w["id"] for w in tags.workouts_with(self.db, "base, threshold")}, {"b"})
        self.assertEqual({w["id"] for w in tags.workouts_with(self.db, "Winter, Threshold",
                                                              "any")}, {"a", "b"})


class TestBackfillAndQueries(Tmp):
    def make_old_sessions(self):
        """Sessões gravadas antes das tags (sem tipo de atividade)."""
        c = self.db.conn
        base = ("INSERT INTO rides(id, kind, status, started_at, ftp_at_ride_w,"
                " weight_at_ride_kg, workout_id) VALUES (?, ?, 'completed', ?, 250, 72, ?)")
        c.execute(base, ("r-free", "route", "2026-01-01T08:00:00Z", None))
        c.execute(base, ("r-work", "workout", "2026-01-02T08:00:00Z", None))
        c.execute(base, ("r-game", "game", "2026-01-03T08:00:00Z", None))
        c.execute(base, ("r-chase", "chase", "2026-01-04T08:00:00Z", None))
        c.execute(base, ("r-test", "ftp_test", "2026-01-05T08:00:00Z", None))
        c.execute(base, ("r-run", "route", "2026-01-06T08:00:00Z", None))
        games.ensure_table(self.db)
        c.execute("INSERT INTO game_results(ride_id, game, score, created_at) VALUES"
                  " ('r-game', 'ladder', 10, '2026-01-03T09:00:00Z')")
        c.execute("INSERT INTO ftp_tests(ride_id, protocol, tested_at, ftp_w) VALUES"
                  " ('r-test', '20min', '2026-01-05', 250)")
        rw.ensure(self.db) if hasattr(rw, "ensure") else None
        c.execute("INSERT INTO row_sessions(id, kind, status, started_at, game)"
                  " VALUES ('w-game', 'game', 'completed', '2026-01-07T08:00:00Z', 'tug')")
        c.commit()

    def test_backfill_tags_old_sessions_once_and_keeps_existing_ones(self):
        self.make_old_sessions()
        tags.save(self.db, "cycling", "r-run", {"activity": ["Workout"], "session": [],
                                                "custom": []})
        n = tags.backfill(self.db)
        self.assertGreaterEqual(n, 6)
        act = lambda sid, sp="cycling": tags.load(self.db, sp, sid)["activity"]    # noqa: E731
        self.assertEqual(act("r-free"), ["Free Session"])
        self.assertEqual(act("r-work"), ["Workout"])
        self.assertEqual(act("r-game"), ["Challenge", "Power Ladder"])
        self.assertEqual(act("r-chase"), ["Challenge", "Chase"])
        self.assertEqual(act("r-test"), ["Test", "FTP 20 min"])
        self.assertEqual(act("r-run"), ["Workout"])                     # o que já tinha fica
        self.assertEqual(act("w-game", "rowing"), ["Challenge", "Tug of War"])
        self.assertEqual(tags.backfill(self.db), 0)                      # só uma vez

    def test_query_by_one_or_more_tags_across_sports(self):
        self.make_old_sessions()
        tags.backfill(self.db)
        ids = lambda w, mode="all": sorted(s["id"] for s in tags.sessions_with(   # noqa: E731
            self.db, w, mode))
        self.assertEqual(ids("Challenge"), ["r-chase", "r-game", "w-game"])      # 2 desportos
        self.assertEqual(ids("challenge, power ladder"), ["r-game"])            # todas
        self.assertEqual(ids(["Chase", "Tug of War"], "any"), ["r-chase", "w-game"])
        self.assertEqual(ids("Free Session, Workout", "none").count("r-free"), 0)
        self.assertIn("r-free", ids("Free Session"))
        self.assertNotIn("r-game", ids("Challenge", "none"))
        counts = dict(tags.tag_counts(self.db))
        self.assertEqual(counts["Challenge"], 3)

    def test_adhoc_sessions_have_tag_fields_and_filters(self):
        self.make_old_sessions()
        spec = adhoc.Spec.from_dict({"source": "sessions", "mode": "dataset",
                                     "fields": ["date", "sport", "activity", "game", "tags"],
                                     "filters": [{"field": "tags", "op": "has_all",
                                                  "value": "Challenge"}]})
        cols, rows = adhoc.dataset(self.db, spec)
        self.assertEqual([c.key for c in cols], ["date", "sport", "activity", "game", "tags"])
        self.assertEqual(sorted(r["game"] for r in rows),
                         ["Chase", "Power Ladder", "Tug of War"])
        self.assertTrue(all(r["activity"] == "Challenge" for r in rows))
        spec.filters = [adhoc.Filter("tags", "has_any", "Chase, Tug of War")]
        self.assertEqual(len(adhoc.apply_filters(adhoc.load(self.db, "sessions"), spec)), 2)
        spec.filters = [adhoc.Filter("tags", "has_none", "Challenge")]
        rest = adhoc.apply_filters(adhoc.load(self.db, "sessions"), spec)
        self.assertEqual(len(rest), 4)
        self.assertTrue(all("Challenge" not in r["tags"] for r in rest))
        # e sai em .csv, as tags numa só coluna
        text = adhoc.csv_text(cols, rows, ";", ".")
        got = list(csv.reader(io.StringIO(text), delimiter=";"))
        self.assertIn("Challenge | Chase", [r[-1] for r in got[1:]][0:3] + [x[-1] for x in got])

    def test_tags_are_not_an_axis_and_old_views_stay_valid(self):
        src = adhoc.source_of("sessions")
        self.assertNotIn("tags", [f.key for f in adhoc.x_fields(src)])
        spec = adhoc.Spec.from_dict({"source": "sessions", "x": "tags", "y": "duration_min"})
        self.assertNotEqual(spec.x, "tags")
        old = adhoc.Spec.from_dict({"source": "sessions", "filters": [
            {"field": "name", "op": "contains", "value": "x"}]})
        self.assertEqual(len(old.filters), 1)

    def test_tags_are_in_the_session_history_backup(self):
        comp = backup.BY_KEY["sessoes"]
        for t in ("session_tags", "tag_catalog"):
            self.assertIn(t, comp.tables)
        self.assertIn("workout_tags", backup.BY_KEY["treinos"].tables)
        self.assertEqual(backup.unknown_tables(self.db) if backup.prepare(self.db) is None
                         else [], [])


class TestUI(tg.GuiCase):
    def test_finish_popup_shows_session_type_and_english_tags(self):
        from perennia.ui.tag_popup import SessionTagsPopup
        db = self.app.db
        tags.set_workout_tags(db, "cycling", "w1", ["Base"])
        info = tags.defaults(db, "cycling", workout_id="w1", activity=("game", "zone_hero"))
        pop = SessionTagsPopup(self.app, "cycling", info, None, lambda i: None, lambda: None)
        pop.enter()
        rows = {i.label: i for i in pop.list.items}
        self.assertEqual(rows["Tipo de sessão"].value, "Challenge · Zone Hero")
        self.assertIn("Base", rows)                                    # a do treino, removível
        fit = next(i for i in pop.list.items if i.label == "No .fit")
        self.assertTrue(fit.value.startswith("Challenge · Zone Hero"))

    def test_builder_edits_and_saves_workout_tags(self):
        from perennia.ui import builder_screens as bs
        from perennia.ui.tag_popup import WorkoutTagsPopup
        self.app.db.set("language", "pt")
        scr = bs.BlockBuilder(self.app, "cycling", None) if hasattr(bs, "BlockBuilder") else None
        self.assertIsNotNone(scr)
        scr.enter()
        labels = [i.label for i in scr.list.items]
        self.assertIn("Tags do treino", labels)
        wt = next(i for i in scr.list.items if i.label == "Tipo de treino")
        self.assertIsNotNone(wt.dropdown)                              # uma lista, não setas
        self.assertEqual(wt.dropdown.labels()[1], "Recovery")
        scr._edit_tags()
        pop = self.app.stack[-1]
        self.assertIsInstance(pop, WorkoutTagsPopup)
        pop._added("Base")
        pop._added("base")                                             # repetida: ignora
        pop._added("Z2")
        pop._done()
        self.assertEqual(scr.wtags, ["Base", "Z2"])
        self.assertTrue(scr.dirty)

    def test_lap_plan_editor_saves_tags_and_the_session_inherits_them(self):
        from perennia.ui import gym_screens as gs
        scr = gs.LapPlanEditor(self.app, None)
        scr.items = [{"kind": "cardio", "seconds": 30}]
        scr.enter()
        self.assertIn("Tags do plano", [i.label for i in scr.list.items])
        scr.wtags = ["Conditioning", "Friday"]
        self.assertNotEqual(scr._state(), scr._saved_state)           # conta como por guardar
        scr._save()
        self.assertEqual(tags.workout_tags(self.app.db, "strength", scr.pid),
                         ["Conditioning", "Friday"])
        info = tags.defaults(self.app.db, "strength", workout_id=scr.pid,
                             activity=tags.kind_of(workout_id="plan"))
        self.assertEqual(info["custom"], ["Conditioning", "Friday"])

    def test_strength_builder_has_a_tags_button(self):
        from perennia.ui.strength_builder_screens import StrengthBuilder
        scr = StrengthBuilder(self.app, "strength", None)
        self.assertIn(("tags",), scr._focusables())
        scr.wtags = ["Hypertrophy"]
        scr.refresh()


if __name__ == "__main__":
    unittest.main()
