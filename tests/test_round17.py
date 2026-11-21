"""Ronda 17: planos de treino de X semanas (formato Perennia, biblioteca, calendário,
importação e ficheiro modelo) e o perfil por desporto (tipo de ciclista, perfil de força)."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia.core import backup, gym, inventory, options, profile
from perennia.core import program_library as pl
from perennia.core import programs as pg
from perennia.core import strength as st
from perennia.core import strength_builder as sb
from perennia.core.db import Athlete, Database
from perennia.core.i18n import PT, set_language
from tests import test_gui as tg

MONDAY = date(2026, 11, 16)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def log_session(db, sets, days_ago: int = 1, workout_id=None, sid: str | None = None) -> str:
    """Uma sessão de força acabada: `sets` = [(nome do exercício, repetições, carga, rpe)]."""
    gym.ensure(db)
    when = datetime.now(timezone.utc).replace(hour=12) - timedelta(days=days_ago)
    sid = sid or f"s{days_ago}_{len(sets)}_{abs(hash(str(sets))) % 10 ** 6}"
    db.conn.execute(
        "INSERT INTO strength_sessions (id, workout_id, name, status, started_at, elapsed_s,"
        " weight_at_session_kg) VALUES (?,?,?,?,?,?,?)",
        (sid, workout_id, "Sessão", "completed", _iso(when), 3600, 72.0))
    ids = {e["name"]: e["id"] for e in gym.exercises(db, include_archived=True)}
    for n, (name, reps, load, rpe) in enumerate(sets, 1):
        db.conn.execute(
            "INSERT INTO strength_sets (session_id, item_idx, exercise_id, set_no, reps,"
            " load_kg, rpe) VALUES (?,?,?,?,?,?,?)", (sid, 0, ids[name], n, reps, load, rpe))
    db.conn.commit()
    return sid


class CoreCase(unittest.TestCase):
    def setUp(self):
        set_language(PT)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = Database(self.tmp / "perennia.db")
        self.addCleanup(self.db.close)
        self.db.save_athlete(Athlete(name="D", birth_year=1993, weight_kg=72.0, ftp_w=250,
                                     lthr=165))

    def plan_count(self) -> int:
        return self.db.conn.execute("SELECT COUNT(*) FROM training_plan").fetchone()[0]


# =========================================================================== o formato


class TestFormat(CoreCase):
    def minimal(self, **over) -> dict:
        p = {"format": "perennia-plan", "name": "Mini", "weeks": 2, "days_per_week": 2,
             "exercises": {"sq": {"name": "Agachamento com barra", "group": "legs"}},
             "sessions": {"A": {"blocks": [{"exercise": "sq", "sets": 3, "reps": 5}]}},
             "rotation": ["A"]}
        p.update(over)
        return p

    def test_every_builtin_plan_is_valid_and_round_trips(self):
        plans = pl.plans()
        self.assertGreaterEqual(len(plans), 30)
        for k, p in plans.items():
            again = pg.validate(json.loads(pg.export_text(p)))
            self.assertEqual(again, p, k)
            self.assertEqual(pg.total_sessions(p), sum(len(w) for w in pg.outline(p)))
            self.assertEqual(len(pg.outline(p)), p["weeks"])
            self.assertEqual(len(p["weekdays"]), p["days_per_week"])
            self.assertTrue(p["description"], k)
            for s in p["sessions"]:
                for e in pg.entries(p, s):
                    self.assertTrue(pg.entry_text(p, e, 1), (k, s))
        for name in ("stronglifts_5x5", "starting_strength", "wendler_531", "gzclp",
                     "grip_block", "sandbag_strength", "simple_sinister"):
            self.assertIn(name, plans)
        self.assertEqual({p["category"] for p in plans.values()} - set(pg.CATEGORIES), set())

    def test_the_template_is_valid_and_matches_the_packaged_file(self):
        t = pg.validate(pl.template_plan())
        self.assertEqual(t["weeks"], 4)
        root = Path(__file__).resolve().parents[1] / "packaging" / "planos"
        on_disk = json.loads((root / "plano-modelo.perennia-plan.json").read_text("utf-8"))
        self.assertEqual(pg.validate(on_disk), t)
        self.assertEqual((root / "FORMATO-DO-PLANO.md").read_text("utf-8"), pl.FORMAT_DOC)

    def test_rotation_and_schedule(self):
        p = pg.validate(self.minimal(
            sessions={"A": {"blocks": [{"exercise": "sq", "sets": 1, "reps": 5}]},
                      "B": {"blocks": [{"exercise": "sq", "sets": 1, "reps": 3}]}},
            rotation=["A", "B"], days_per_week=3))
        self.assertEqual(pg.outline(p), [["A", "B", "A"], ["B", "A", "B"]])
        self.assertEqual(p["weekdays"], [1, 3, 5])
        q = dict(self.minimal(weeks=3))
        del q["rotation"]
        del q["days_per_week"]
        q["schedule"] = [["A"], ["A", "A"]]
        q = pg.validate(q)
        self.assertEqual(pg.outline(q), [["A"], ["A", "A"], ["A"]])       # repete-se
        self.assertEqual(q["days_per_week"], 2)

    def test_per_week_values_and_reps_forms(self):
        self.assertEqual(pg.at([70, 75, 80], 2), 75)
        self.assertEqual(pg.at([70, 75, 80], 9), 80)                      # o último repete
        self.assertEqual(pg.at(60, 3), 60)
        p = pg.validate(self.minimal(sessions={"A": {"blocks": [
            {"exercise": "sq", "sets": [3, 4], "reps": "8-12", "pct1rm": [60, 65]},
            {"exercise": "sq", "sets": [{"reps": 5, "pct1rm": 65}, {"reps": "5+", "pct1rm": 85}]},
            {"exercise": "sq", "sets": 2, "reps": "MAX"}]}}))
        e = pg.entries(p, "A")
        self.assertEqual(e[0]["reps"], "8-12")
        self.assertEqual(e[1]["sets"][1]["reps"], "5+")
        self.assertEqual(e[2]["reps"], "max")
        self.assertEqual(pg.entry_text(p, e[0], 2), "4 × 8-12 · 65 % 1RM")
        self.assertEqual(pg.entry_text(p, e[1], 1), "5@65 % · 5+@85 %")

    def test_bad_plans_say_where(self):
        cases = [
            ({"format": "outro"}, "format"),
            (self.minimal(version=9), "versão"),
            (self.minimal(name=""), "name"),
            (self.minimal(weeks=0), "weeks"),
            (self.minimal(weeks=500), "weeks"),
            (self.minimal(exercises={}), "exercises"),
            (self.minimal(exercises={"a b": {"name": "x"}}), "chave"),
            (self.minimal(sessions={"A": {"blocks": []}}), "blocks"),
            (self.minimal(sessions={"A": {"blocks": [{"exercise": "nope", "sets": 1}]}}),
             "nope"),
            (self.minimal(sessions={"A": {"blocks": [{"exercise": "sq", "sets": 99}]}}), "sets"),
            (self.minimal(sessions={"A": {"blocks": [{"exercise": "sq", "sets": 1,
                                                      "reps": "muitas"}]}}), "repetições"),
            (self.minimal(sessions={"A": {"blocks": [{"exercise": "sq", "sets": 1,
                                                      "pct1rm": 900}]}}), "pct1rm"),
            (self.minimal(sessions={"A": {"blocks": [{"exercise": "sq", "sets": 1,
                                                      "surpresa": 1}]}}), "surpresa"),
            (self.minimal(sessions={"A": {"blocks": [{"kind": "dança", "exercises": []}]}}),
             "kind"),
            (self.minimal(rotation=["Z"]), "Z"),
            (self.minimal(days_per_week=9), "days_per_week"),
            (self.minimal(weekdays=[1, 1]), "weekdays"),
            (self.minimal(weekdays=[1, 9]), "weekdays"),
            ([1, 2], "objeto"),
        ]
        for data, word in cases:
            with self.assertRaises(pg.PlanError) as cm:
                pg.validate(data)
            self.assertIn(word, str(cm.exception), data)
        no_order = self.minimal()
        del no_order["rotation"]
        with self.assertRaises(pg.PlanError):
            pg.validate(no_order)

    def test_unknown_equipment_and_modality_are_dropped_not_trusted(self):
        p = pg.validate(self.minimal(exercises={"sq": {
            "name": "X", "equipment": ["barbell", "<script>", 7], "modality": "inventada",
            "group": "nariz", "measure": "anos"}}))
        e = p["exercises"]["sq"]
        self.assertEqual(e["equipment"], ["barbell"])
        self.assertEqual((e["modality"], e["group"], e["measure"]), ("strength", "full", "reps"))


# =========================================================================== ficheiros


class TestFiles(CoreCase):
    def test_template_export_import_round_trip(self):
        out = pg.write_template(self.tmp / "planos")
        self.assertTrue(out[0].name.endswith(pg.EXT))
        self.assertEqual(out[1].name, "FORMATO-DO-PLANO.md")
        again = pg.write_template(self.tmp / "planos")
        self.assertNotEqual(again[0], out[0])                     # nunca substitui
        key = pg.import_file(self.db, out[0])
        p = pg.get(self.db, key)
        self.assertEqual((p["origin"], p["name"]), ("imported", "O meu plano (modelo)"))
        self.assertEqual(pg.import_file(self.db, out[0]), key)    # o mesmo nome substitui
        self.assertEqual(len([q for q in pg.library(self.db) if q["origin"] == "imported"]), 1)
        path = pg.export_file(pg.get(self.db, "stronglifts_5x5"), self.tmp / "exp")
        self.assertEqual(pg.read_file(path)["name"], "StrongLifts 5×5")
        pg.delete_plan(self.db, key)
        self.assertIsNone(pg.get(self.db, key))
        self.assertIsNotNone(pg.get(self.db, "stronglifts_5x5"))  # os de origem não se apagam

    def test_an_imported_plan_never_replaces_a_builtin(self):
        data = json.loads(pg.export_text(pl.plans()["stronglifts_5x5"]))
        data["weeks"] = 2
        key = pg.save_plan(self.db, data, key="stronglifts_5x5")
        self.assertNotEqual(key, "stronglifts_5x5")
        self.assertEqual(pg.get(self.db, "stronglifts_5x5")["weeks"], 12)

    def test_bad_files_are_refused(self):
        f = self.tmp / ("x" + pg.EXT)
        f.write_text("isto não é json", "utf-8")
        with self.assertRaises(pg.PlanError):
            pg.import_file(self.db, f)
        f.write_text('{"format": "perennia-plan", "name": "x", "weeks": 1}', "utf-8")
        with self.assertRaises(pg.PlanError):
            pg.import_file(self.db, f)
        with self.assertRaises(pg.PlanError):
            pg.import_file(self.db, self.tmp / "nao-existe.json")
        big = dict(pl.template_plan(), description="x" * 3000)
        f.write_text(json.dumps(big) + " " * (40 * 1024), "utf-8")
        self.db.set("plan_import_max_kb", 16)
        with self.assertRaises(pg.PlanError) as cm:
            pg.import_file(self.db, f)
        self.assertIn("kB", str(cm.exception))
        self.assertEqual([p for p in pg.library(self.db) if p["origin"] == "imported"], [])

    def test_scan_finds_plans_and_the_workout_import_ignores_them(self):
        from perennia.core import strength_import as si
        folder = self.tmp / "w"
        pg.write_template(folder)
        (folder / "treino.json").write_text("{}", "utf-8")
        self.assertEqual([p.name for p in pg.scan([str(folder)])],
                         ["plano-modelo.perennia-plan.csv", "plano-modelo.perennia-plan.json"])
        self.assertEqual([p.name for p in si.scan([str(folder)])], ["treino.json"])

    def test_command_line(self):
        import main as main_mod

        def ns(**kw):
            base = dict(data_dir=str(self.tmp / "d"), plano_modelo=None, plano_importar=None,
                        plano_exportar=None, destino=None)
            base.update(kw)
            return argparse.Namespace(**base)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(main_mod.plan_cli(ns(plano_modelo=str(self.tmp / "m"))), 0)
            model = self.tmp / "m" / "plano-modelo.perennia-plan.json"
            self.assertTrue(model.exists())
            self.assertEqual(main_mod.plan_cli(ns(plano_importar=str(model))), 0)
            self.assertEqual(main_mod.plan_cli(ns(plano_exportar="lista")), 0)
            self.assertEqual(main_mod.plan_cli(ns(plano_exportar="gzclp",
                                                  destino=str(self.tmp / "e"))), 0)
            self.assertEqual(main_mod.plan_cli(ns(plano_exportar="nao-existe")), 2)
            model.write_text("{}", "utf-8")
            self.assertEqual(main_mod.plan_cli(ns(plano_importar=str(model))), 2)
        self.assertIn("u_o_meu_plano_modelo", out.getvalue())
        self.assertTrue((self.tmp / "e" / "gzclp-progressao-linear.perennia-plan.json").exists())


# =========================================================================== começar um plano


class TestRun(CoreCase):
    LOADS = {"squat": 60.0, "bench": 40.0, "row": 40.0, "press": 30.0, "deadlift": 80.0}

    def start(self, key="stronglifts_5x5", day=MONDAY, weekdays=None, loads=None):
        return pg.start(self.db, key, day, weekdays, self.LOADS if loads is None else loads)

    def sets(self, wid, i=0):
        s = sb.load(self.db, wid)
        e = s["blocks"][i]["exercises"][0]
        return e["name"], [x.get("load") for x in e["sets"]], [x.get("reps") for x in e["sets"]]

    def test_every_session_goes_to_the_calendar_on_the_chosen_days(self):
        rid = self.start()
        ds = pg.days(self.db, rid)
        self.assertEqual(len(ds), 36)
        self.assertEqual(self.plan_count(), 36)
        self.assertEqual([d["date"].isoweekday() for d in ds[:6]], [1, 3, 5, 1, 3, 5])
        self.assertEqual(ds[0]["date"], MONDAY)
        self.assertEqual(ds[-1]["date"], MONDAY + timedelta(weeks=11, days=4))
        self.assertEqual(ds[0]["title"], "StrongLifts 5×5 · S1 · Treino A")
        self.assertEqual([d["session_key"] for d in ds[:6]], ["A", "B", "A", "B", "A", "B"])
        rows = self.db.conn.execute("SELECT sport, workout_id, title FROM training_plan"
                                    " ORDER BY day").fetchall()
        self.assertTrue(all(r["sport"] == "gym" and r["workout_id"] for r in rows))
        # os treinos do plano não enchem a lista de treinos, nem são limpos como rascunhos
        self.assertEqual([w for w in gym.workouts(self.db) if "StrongLifts" in w["name"]], [])
        gym.purge_drafts(self.db)
        self.assertIsNotNone(st.workout(self.db, ds[0]["workout_id"]))

    def test_linear_progression_adds_each_time_the_lift_comes_back(self):
        ds = pg.days(self.db, self.start())
        self.assertEqual(self.sets(ds[0]["workout_id"]), ("Agachamento com barra", [60.0] * 5,
                                                          [5] * 5))
        self.assertEqual(self.sets(ds[1]["workout_id"])[1], [62.5] * 5)     # volta: +2,5
        self.assertEqual(self.sets(ds[2]["workout_id"])[1], [65.0] * 5)
        self.assertEqual(self.sets(ds[2]["workout_id"], 1)[1], [42.5] * 5)  # supino: 2.ª vez
        self.assertEqual(self.sets(ds[1]["workout_id"], 2), ("Peso morto", [80.0], [5]))
        self.assertEqual(self.sets(ds[3]["workout_id"], 2)[1], [85.0])      # peso morto: +5
        self.assertEqual(self.sets(ds[35]["workout_id"])[1], [147.5] * 5)

    def test_starting_midweek_moves_sessions_forward_without_skipping(self):
        ds = pg.days(self.db, self.start(day=MONDAY + timedelta(days=3)))    # quinta
        self.assertEqual(ds[0]["date"], MONDAY + timedelta(days=4))          # sexta
        self.assertEqual(ds[1]["date"], MONDAY + timedelta(days=7))
        self.assertEqual(len(ds), 36)
        self.assertEqual(ds[0]["session_key"], "A")

    def test_other_weekdays_and_bad_ones(self):
        ds = pg.days(self.db, self.start(weekdays=[2, 4, 6]))
        self.assertEqual([d["date"].isoweekday() for d in ds[:3]], [2, 4, 6])
        for bad in ([1, 2], [1, 1, 3], [0, 3, 5], [1, 3, 8]):
            with self.assertRaises(pg.PlanError):
                self.start(weekdays=bad)
        with self.assertRaises(pg.PlanError):
            pg.start(self.db, "nao-existe", MONDAY)

    def test_percent_plans_keep_percentages_by_week(self):
        ds = pg.days(self.db, pg.start(self.db, "wendler_531", MONDAY))
        self.assertEqual(len(ds), 16)
        for week, pcts, reps in ((0, [58.5, 67.5, 76.5], [5, 5, 5]),
                                 (1, [63, 72, 81], [3, 3, 3]),
                                 (2, [67.5, 76.5, 85.5], [5, 3, 1]),
                                 (3, [36, 45, 54], [5, 5, 5])):
            e = sb.load(self.db, ds[week * 4]["workout_id"])["blocks"][0]["exercises"][0]
            self.assertEqual([s["pct1rm"] for s in e["sets"]], pcts)
            self.assertEqual([s["reps"] for s in e["sets"]], reps)
        rs = pg.days(self.db, pg.start(self.db, "russian_squat", MONDAY))
        e = sb.load(self.db, rs[17]["workout_id"])["blocks"][0]["exercises"][0]
        self.assertEqual((len(e["sets"]), e["sets"][0]["reps"], e["sets"][0]["pct1rm"]),
                         (1, 1, 105))

    def test_ramps_circuits_supersets_and_timed_sets(self):
        ds = pg.days(self.db, pg.start(self.db, "madcow_5x5", MONDAY, None,
                                       {"squat": 100.0, "bench": 80.0, "row": 70.0,
                                        "press": 50.0, "deadlift": 120.0}))
        self.assertEqual(self.sets(ds[0]["workout_id"])[1], [50.0, 62.5, 75.0, 87.5, 100.0])
        self.assertEqual(self.sets(ds[2]["workout_id"])[1],
                         [50.0, 62.5, 75.0, 87.5, 102.5, 75.0])
        self.assertEqual(self.sets(ds[3]["workout_id"])[1][-1], 102.5)       # semana 2: +2,5
        g = pg.days(self.db, pg.start(self.db, "gvt_10x10", MONDAY))
        b = sb.load(self.db, g[0]["workout_id"])["blocks"][0]
        self.assertEqual((b["kind"], len(b["exercises"]), len(b["exercises"][0]["sets"])),
                         ("superset", 2, 10))
        s = pg.days(self.db, pg.start(self.db, "sandbag_strength", MONDAY))
        c = sb.load(self.db, s[2]["workout_id"])["blocks"][0]
        self.assertEqual((c["kind"], c["rounds"]), ("circuit", 4))
        carry = c["exercises"][-1]
        self.assertIn("time", carry["params"])
        self.assertEqual(carry["sets"][0]["time"], 30)

    def test_gzclp_keeps_two_progressions_per_lift(self):
        p = pg.get(self.db, "gzclp")
        self.assertEqual(len(pg.tracks(p)), 8)
        loads = {t["track"]: (100.0 if t["track"].endswith("t1") else 60.0)
                 for t in pg.tracks(p)}
        ds = pg.days(self.db, pg.start(self.db, "gzclp", MONDAY, None, loads))
        self.assertEqual(self.sets(ds[0]["workout_id"])[1], [100.0] * 5)     # agach. T1
        self.assertEqual(self.sets(ds[2]["workout_id"], 1)[1], [60.0] * 3)   # agach. T2
        self.assertEqual(self.sets(ds[4]["workout_id"])[1], [102.5] * 5)

    def test_new_exercises_and_equipment_are_created_on_start(self):
        before = {e["name"] for e in gym.exercises(self.db)}
        p = pg.get(self.db, "grip_block")
        new = pg.new_exercises(self.db, p)
        self.assertIn("Gripper (fechos)", new)
        self.assertNotIn("Gripper (fechos)", before)
        self.assertIn("gripper", pg.missing_equipment(self.db, p))
        for k in ("gripper", "fat_grips", "wrist_roller", "leg_press", "sled", "ab_wheel",
                  "trap_bar"):
            self.assertIn(k, inventory.KINDS)
        pg.start(self.db, "grip_block", MONDAY)
        ex = {e["name"]: e for e in gym.exercises(self.db)}
        self.assertEqual(ex["Gripper (fechos)"]["equipment"], ["gripper"])
        self.assertEqual(ex["Pinça de discos"]["measure"], "time")
        self.assertEqual(pg.new_exercises(self.db, p), [])
        n = len(gym.exercises(self.db))
        pg.start(self.db, "grip_block", MONDAY)                    # outra vez: não duplica
        self.assertEqual(len(gym.exercises(self.db)), n)
        inventory.save(self.db, None, name="CoC 1", kind="gripper")
        self.assertNotIn("gripper", pg.missing_equipment(self.db, p))

    def test_suggested_loads_use_your_e1rm(self):
        p = pg.get(self.db, "stronglifts_5x5")
        self.assertEqual(pg.suggest_loads(self.db, p)["squat"], 20.0)       # sem histórico
        self.db.set("plan_default_start_kg", 30.0)
        self.assertEqual(pg.suggest_loads(self.db, p)["squat"], 30.0)
        log_session(self.db, [("Agachamento com barra", 1, 100.0, 10.0)])
        self.assertEqual(pg.suggest_loads(self.db, p)["squat"], 50.0)       # 50 % de 100
        self.db.set("plan_round_kg", 5.0)
        self.assertEqual(pg.round_load(self.db, 52.4), 50.0)

    def test_progress_done_next_and_finish(self):
        rid = self.start(key="minimalist_2x", loads={})
        ds = pg.days(self.db, rid)
        p = pg.progress(self.db, rid)
        self.assertEqual((p["total"], p["done"], p["next"]["idx"]), (16, 0, 0))
        log_session(self.db, [("Agachamento com barra", 5, 60.0, 7.0)], days_ago=0,
                    workout_id=ds[0]["workout_id"], sid="feita0")
        p = pg.progress(self.db, rid)
        self.assertEqual((p["done"], p["next"]["idx"]), (1, 1))
        self.assertTrue(pg.days(self.db, rid)[0]["done"])
        run, nxt = pg.next_session(self.db)
        self.assertEqual((run["id"], nxt["idx"]), (rid, 1))
        for i, d in enumerate(ds[1:], 1):
            log_session(self.db, [("Peso morto", 5, 80.0, 7.0)], days_ago=0,
                        workout_id=d["workout_id"], sid=f"feita{i}")
        self.assertEqual(pg.finish_if_done(self.db), ["Manutenção minimalista (2× por semana)"])
        self.assertEqual(pg.run(self.db, rid)["status"], "ended")
        self.assertIsNone(pg.next_session(self.db))

    def test_rebase_rebuilds_only_what_is_left(self):
        rid = self.start()
        ds = pg.days(self.db, rid)
        log_session(self.db, [("Agachamento com barra", 5, 60.0, 8.0)], days_ago=0,
                    workout_id=ds[0]["workout_id"], sid="d0")
        cur = pg.current_loads(self.db, rid)
        self.assertEqual((cur["squat"], cur["bench"], cur["press"]), (62.5, 42.5, 30.0))
        n = pg.rebase(self.db, rid, {"squat": 50.0, "nao-existe": 1.0})
        self.assertEqual(n, 35)
        after = pg.days(self.db, rid)
        self.assertEqual(len(after), 36)
        self.assertEqual(self.plan_count(), 36)
        self.assertEqual(after[0]["workout_id"], ds[0]["workout_id"])       # a feita fica
        self.assertTrue(after[0]["done"])
        self.assertEqual(self.sets(after[1]["workout_id"])[1], [50.0] * 5)
        self.assertEqual(self.sets(after[2]["workout_id"])[1], [52.5] * 5)
        self.assertEqual(self.sets(after[2]["workout_id"], 1)[1], [42.5] * 5)   # supino igual
        self.assertEqual([d["date"] for d in after], [d["date"] for d in ds])
        self.assertEqual(pg.current_loads(self.db, rid)["squat"], 50.0)
        self.assertIsNone(st.workout(self.db, ds[1]["workout_id"]))         # o antigo saiu

    def test_shift_moves_the_calendar_too(self):
        rid = self.start()
        ds = pg.days(self.db, rid)
        log_session(self.db, [("Agachamento com barra", 5, 60.0, 8.0)], days_ago=0,
                    workout_id=ds[0]["workout_id"], sid="d0")
        self.assertEqual(pg.shift(self.db, rid, 7), 35)
        after = pg.days(self.db, rid)
        self.assertEqual(after[0]["date"], ds[0]["date"])
        self.assertEqual(after[1]["date"], ds[1]["date"] + timedelta(days=7))
        row = self.db.conn.execute("SELECT day FROM training_plan WHERE id = ?",
                                   (after[1]["plan_id"],)).fetchone()
        self.assertEqual(row["day"], after[1]["date"].isoformat())

    def test_ending_clears_the_future_and_keeps_the_history(self):
        rid = self.start()
        ds = pg.days(self.db, rid)
        sid = log_session(self.db, [("Agachamento com barra", 5, 60.0, 8.0)], days_ago=0,
                          workout_id=ds[0]["workout_id"], sid="d0")
        from perennia.core import calendar_view as cal
        mine = cal.plan_add(self.db, MONDAY, "gym", None, "meu")
        pg.end(self.db, rid)
        self.assertEqual(self.plan_count(), 1)                              # só o teu
        self.assertEqual(pg.run(self.db, rid)["status"], "ended")
        self.assertIsNotNone(st.workout(self.db, ds[0]["workout_id"]))
        self.assertIsNone(st.workout(self.db, ds[5]["workout_id"]))
        self.assertIsNotNone(self.db.conn.execute(
            "SELECT 1 FROM strength_sessions WHERE id = ?", (sid,)).fetchone())
        self.assertEqual(len(pg.days(self.db, rid)), 1)
        pg.end(self.db, rid, delete=True)
        self.assertIsNone(pg.run(self.db, rid))
        self.assertTrue(mine)

    def test_a_run_survives_deleting_the_imported_plan(self):
        key = pg.import_file(self.db, pg.write_template(self.tmp / "p")[0])
        rid = pg.start(self.db, key, MONDAY)
        pg.delete_plan(self.db, key)
        self.assertEqual(pg.rebase(self.db, rid, {"squat": 40.0}), 12)
        self.assertEqual(len(pg.days(self.db, rid)), 12)

    def test_editing_a_plan_workout_keeps_it_out_of_the_list(self):
        ds = pg.days(self.db, self.start())
        wid = ds[0]["workout_id"]
        sb.save(self.db, wid, "Editado", sb.load(self.db, wid), "strength")
        self.assertEqual([w for w in gym.workouts(self.db) if w["id"] == wid], [])

    def test_backup_takes_plans_and_runs(self):
        key = pg.import_file(self.db, pg.write_template(self.tmp / "p")[0])
        rid = self.start()
        info = backup.export(self.db, self.tmp, self.tmp / "b.zip")
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, True)
        db = Database(other / "perennia.db")
        self.addCleanup(db.close)
        backup.restore(db, other, info["path"], mode="replace", safety=False)
        self.assertIsNotNone(pg.get(db, key))
        self.assertEqual(len(pg.days(db, rid)), 36)
        self.assertEqual(pg.progress(db, rid)["next"]["idx"], 0)
        self.assertIsNotNone(st.workout(db, pg.days(db, rid)[0]["workout_id"]))
        tables = {t for c in backup.COMPONENTS for t in c.tables}
        for t in ("programs", "program_runs", "program_days"):
            self.assertIn(t, tables)


# =========================================================================== perfil


class TestCyclingProfile(CoreCase):
    def peaks(self, values: dict[int, float]) -> None:
        from perennia.core import peaks
        peaks.ensure(self.db)
        when = _iso(datetime.now(timezone.utc) - timedelta(days=3))
        self.db.conn.execute(
            "INSERT OR REPLACE INTO rides(id, name, status, started_at, ftp_at_ride_w,"
            " weight_at_ride_kg, elapsed_s, moving_s, distance_m) VALUES (?,?,?,?,?,?,?,?,?)",
            ("p1", "Teste", "completed", when, 250, 72.0, 3600, 3600, 30000))
        self.db.conn.execute("DELETE FROM ride_peaks WHERE ride_id = 'p1'")
        for d, v in values.items():
            self.db.conn.execute("INSERT INTO ride_peaks VALUES ('p1', 'power_w', ?, ?, ?)",
                                 (d, v, peaks.VERSION))
        self.db.conn.execute("INSERT INTO ride_peaks VALUES ('p1', '_done', -1, 0, ?)",
                             (peaks.VERSION,))
        self.db.conn.commit()

    def test_without_efforts_it_says_what_is_missing(self):
        p = profile.cycling(self.db)
        self.assertIsNone(p["type"])
        self.assertFalse(p["enough"])
        self.assertEqual(len(p["missing"]), 3)
        self.assertIsNotNone(p["rows"][3]["score"])                 # o limiar vem da FTP

    def test_puncheur(self):
        self.peaks({5: 900, 60: 640, 300: 400, 1200: 255})
        p = profile.cycling(self.db)
        self.assertEqual(p["type"], "puncheur")
        self.assertEqual(p["type_name"], "Puncheur")
        self.assertTrue(p["advice"])
        self.assertAlmostEqual(p["rows"][1]["wkg"], 640 / 72.0)
        self.assertEqual(p["missing"], [])

    def test_sprinter_climber_rouleur_and_allrounder(self):
        self.peaks({5: 1500, 60: 500, 300: 300, 1200: 250})
        self.assertEqual(profile.cycling(self.db)["type"], "sprinter")
        self.peaks({5: 800, 60: 420, 300: 330, 1200: 330})
        self.db.save_athlete(Athlete(name="D", weight_kg=62.0, ftp_w=300))
        self.assertEqual(profile.cycling(self.db)["type"], "climber")
        self.db.save_athlete(Athlete(name="D", weight_kg=82.0, ftp_w=400))
        self.peaks({5: 1000, 60: 520, 300: 400, 1200: 420})
        self.assertEqual(profile.cycling(self.db)["type"], "rouleur")
        self.db.set("profile_climber_max_kg", 85.0)
        self.assertEqual(profile.cycling(self.db)["type"], "climber")
        # as quatro durações a meio da escala: nenhuma se destaca
        self.db.save_athlete(Athlete(name="D", weight_kg=82.0, ftp_w=340))
        self.peaks({5: 1402, 60: 701, 300: 406, 1200: 300})
        p = profile.cycling(self.db)
        self.assertEqual(p["type"], "allrounder")
        self.assertEqual(p["advice"], "")
        self.db.set("profile_flat_spread", 2.0)
        self.peaks({5: 1402, 60: 800, 300: 460, 1200: 300})
        self.assertEqual(profile.cycling(self.db)["type"], "puncheur")

    def test_reference_table_and_window_are_options(self):
        self.peaks({5: 900, 60: 500, 300: 330, 1200: 260})
        m = profile.cycling(self.db)["rows"][0]["score"]
        self.db.set("profile_reference", "female")
        self.assertGreater(profile.cycling(self.db)["rows"][0]["score"], m)
        self.db.conn.execute("UPDATE rides SET started_at = ? WHERE id = 'p1'",
                             (_iso(datetime.now(timezone.utc) - timedelta(days=400)),))
        self.db.conn.commit()
        self.assertEqual(len(profile.cycling(self.db)["missing"]), 3)
        self.db.set("profile_days", 500)
        self.assertEqual(profile.cycling(self.db)["missing"], [])

    def test_scores_are_clamped(self):
        self.peaks({5: 5000, 60: 10, 300: 400, 1200: 250})
        rows = profile.cycling(self.db)["rows"]
        self.assertEqual((rows[0]["score"], rows[1]["score"]), (100.0, 0.0))
        self.assertEqual(profile.bar(100.0), "█" * 10)
        self.assertEqual(profile.bar(None), "·" * 10)
        self.assertEqual(profile.level(None), "sem dados")


class TestGymProfile(CoreCase):
    def test_no_sessions_means_no_data_not_weak(self):
        p = profile.gym(self.db)
        self.assertFalse(p["enough"])
        self.assertTrue(all(d["score"] is None for d in p["dims"]))
        self.assertEqual(p["weak"], [])

    def strong_but_narrow(self):
        """Forte nos básicos, sem mãos, tendões, saltos nem mobilidade."""
        for week in range(6):
            for k in range(2):
                log_session(self.db, [("Agachamento com barra", 5, 120.0, 9.0)] * 4
                            + [("Supino com barra", 5, 95.0, 9.0)] * 4
                            + [("Peso morto", 5, 150.0, 9.0)] * 2
                            + [("Press militar", 5, 55.0, 9.0)] * 3,
                            days_ago=1 + week * 7 + k * 3, sid=f"w{week}k{k}")

    def test_strong_lifter_with_gaps(self):
        self.strong_but_narrow()
        p = profile.gym(self.db)
        d = {x["key"]: x for x in p["dims"]}
        self.assertGreater(d["max_strength"]["score"], 80)
        self.assertTrue(d["max_strength"]["measured"])
        for k in ("grip", "tendons", "power", "mobility"):
            self.assertEqual(d[k]["score"], 0.0, k)                 # com sessões: é deficiência
        weak = [x["key"] for x in p["weak"]]
        for k in ("grip", "tendons", "power", "mobility"):
            self.assertIn(k, weak)
        self.assertNotIn("max_strength", weak)
        self.assertIn("força máxima", p["summary"])
        self.assertEqual(len(p["advice"]), 3)
        self.assertTrue(any("puxas pouco" in b for b in p["balance"]))
        plans = {a["plan"] for a in p["advice"] if a["plan"]}
        self.assertTrue(plans <= set(pl.plans()))

    def test_grip_tendons_and_power_count_what_you_do(self):
        self.strong_but_narrow()
        base = {x["key"]: x["score"] for x in profile.gym(self.db)["dims"]}
        for k in range(8):
            log_session(self.db, [("Suspensão na barra", 60, None, None)] * 3
                        + [("Elevação de gémeos lenta (3-0-3)", 10, None, None)] * 4
                        + [("Saltos para caixa", 5, None, None)] * 4
                        + [("Farmer's carry", 40, 36.0, None)] * 2,
                        days_ago=2 + k * 5, sid=f"x{k}")
        d = {x["key"]: x for x in profile.gym(self.db)["dims"]}
        for k in ("grip", "tendons", "power"):
            self.assertGreater(d[k]["score"], base[k] + 20, k)
        self.assertIn("suspensão 60 s", " ".join(d["grip"]["measured"]))
        self.assertIn("farmer's carry 36 kg", " ".join(d["grip"]["measured"]))

    def test_levels_are_options(self):
        self.strong_but_narrow()
        a = {x["key"]: x["score"] for x in profile.gym(self.db)["dims"]}["max_strength"]
        for k in ("profile_squat_bw", "profile_deadlift_bw", "profile_bench_bw",
                  "profile_press_bw"):
            self.db.set(k, options.BY_KEY[k].hi)
        b = {x["key"]: x["score"] for x in profile.gym(self.db)["dims"]}["max_strength"]
        self.assertLess(b, a)
        self.db.set("profile_weak_score", 10.0)
        self.assertNotIn("relative", [x["key"] for x in profile.gym(self.db)["weak"]
                                      if x["score"] >= 10])

    def test_bodyweight_reps_and_plank(self):
        log_session(self.db, [("Elevações (pull-ups)", 12, None, None),
                              ("Flexões", 20, None, None), ("Prancha", 120, None, None)])
        d = {x["key"]: x for x in profile.gym(self.db)["dims"]}
        self.assertEqual(d["relative"]["perf"], (100.0 + 50.0) / 2)
        self.assertEqual(d["core"]["perf"], 100.0)

    def test_facts_and_dispatch(self):
        self.assertEqual(profile.of(self.db, "gym")["sport"], "gym")
        self.assertEqual(profile.of(self.db, "cycling")["sport"], "cycling")
        self.assertEqual(profile.of(self.db, "running")["sport"], "running")
        for s in ("gym", "cycling", "rowing"):
            self.assertTrue(json.dumps(profile.facts(profile.of(self.db, s))))


class TestEnduranceProfile(CoreCase):
    def run_(self, i, km, minutes):
        from perennia.core import endurance
        endurance.ensure(self.db)
        when = _iso(datetime.now(timezone.utc) - timedelta(days=i + 1))
        cols = {r["name"] for r in self.db.conn.execute("PRAGMA table_info(endurance_sessions)")}
        row = {"id": f"e{i}", "sport": "running", "status": "completed", "started_at": when,
               "elapsed_s": minutes * 60, "moving_s": minutes * 60, "distance_m": km * 1000.0}
        row = {k: v for k, v in row.items() if k in cols}
        self.db.conn.execute(
            f"INSERT INTO endurance_sessions ({', '.join(row)}) VALUES"
            f" ({', '.join('?' * len(row))})", list(row.values()))
        self.db.conn.commit()

    def test_speed_vs_endurance(self):
        self.assertIsNone(profile.endurance(self.db, "running")["type"])
        self.run_(0, 3.0, 12)            # 15 km/h
        self.run_(1, 21.0, 100)          # 12,6 km/h → 84 %
        p = profile.endurance(self.db, "running")
        self.assertEqual(p["type"], "balanced")
        self.run_(2, 24.0, 100)          # 14,4 km/h → 96 %
        self.assertEqual(profile.endurance(self.db, "running")["type"], "endurance")


# =========================================================================== opções


class TestOptions(CoreCase):
    def test_new_options_are_sane(self):
        keys = [o.key for o in options.OPTIONS]
        self.assertEqual(len(keys), len(set(keys)))
        for o in options.OPTIONS:
            self.assertEqual(options.coerce(o, o.default), o.default, o.key)
            self.assertIn(o.group, options.GROUPS)
        for k in ("plan_round_kg", "plan_default_start_kg", "plan_import_max_kb",
                  "plan_deload_pct", "profile_days", "profile_reference", "profile_hang_s"):
            self.assertIn(k, options.BY_KEY)


# =========================================================================== interface


class TestPlansUI(tg.GuiCase):
    def hub(self, tab: str):
        from perennia.ui import gym_screens as gs
        self.app.push(gs.GymHub(self.app))
        h = self.screen()
        self.assertTrue(h.tab_named(tab))
        return h

    def test_library_start_and_follow(self):
        from perennia.ui import program_screens as ps
        from perennia.ui.sport_screens import StrengthPreview
        hub = self.hub("Lista")
        self.assertEqual(hub.list.items[0].label, "Planos de X semanas")
        self.pick("Planos de X semanas")
        lib = self.screen()
        self.assertIsInstance(lib, ps.ProgramsScreen)
        self.assertIn("Força de mãos", [i.label for i in lib.list.items if i.header])
        lib.list.select_data(("plan", "stronglifts_5x5"))
        self.press(key.ENTER)
        det = self.screen()
        self.assertIsInstance(det, ps.ProgramDetail)
        labels = [i.label for i in det.list.items]
        for word in ("Material", "Progressão linear", "Semana 1", "Treino A", "Treino B"):
            self.assertIn(word, labels)
        self.pick("Começar este plano")
        st_ = self.screen()
        self.assertIsInstance(st_, ps.ProgramStart)
        st_.list.select_data("num:squat")
        for ch in "60":
            self.app._on_text(ch)
        self.assertEqual(st_.v["loads"]["squat"], 60.0)
        self.pick("Começar e pôr no calendário")
        run = self.screen()
        self.assertIsInstance(run, ps.RunScreen)
        self.assertEqual(self.app.db.conn.execute("SELECT COUNT(*) FROM training_plan"
                                                  ).fetchone()[0], 36)
        self.assertEqual(run.list.selected.data, ("day", 0))
        self.pick("Fazer a próxima sessão")
        self.assertIsInstance(self.screen(), StrengthPreview)
        self.press(key.ESCAPE, key.ESCAPE)
        self.assertIs(self.screen(), det)
        self.press(key.ESCAPE)
        self.assertIn("Em curso", [i.label for i in lib.list.items if i.header])
        self.press(key.ESCAPE)
        self.assertIn("em curso: StrongLifts 5×5", hub.list.items[0].detail)
        hub.tab_named("Treinar")
        self.assertEqual(hub.list.items[0].label, "Plano em curso: próxima sessão")
        self.pick("Plano em curso: próxima sessão")
        self.assertIsInstance(self.screen(), StrengthPreview)

    def test_weekdays_come_from_a_list_and_custom_days_need_the_right_count(self):
        from perennia.ui import pickers
        from perennia.ui import program_screens as ps
        self.app.push(ps.ProgramStart(self.app, "stronglifts_5x5"))
        st_ = self.screen()
        st_.list.select_data("cyc:weekdays")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), pickers.ChoicePopup)
        self.pick("Ter, Qui, Sáb")
        self.assertEqual(st_.v["weekdays"], [2, 4, 6])
        self.pick("Outros dias…")
        pop = self.screen()
        self.assertIsInstance(pop, pickers.MultiChoicePopup)
        pop.selected = ["1", "2"]
        pop._ok()
        self.assertEqual(st_.v["weekdays"], [2, 4, 6])              # 2 dias: recusado
        self.pick("Outros dias…")
        pop = self.screen()
        pop.selected = ["1", "2", "7"]
        pop._ok()
        self.assertEqual(st_.v["weekdays"], [1, 2, 7])
        self.assertIn("Seg, Ter, Dom", [i.value for i in st_.list.items])

    def test_run_screen_actions(self):
        from perennia.ui import program_screens as ps
        rid = pg.start(self.app.db, "stronglifts_5x5", date.today(), None,
                       {"squat": 60.0, "bench": 40.0, "row": 40.0, "press": 30.0,
                        "deadlift": 80.0})
        self.app.push(ps.RunScreen(self.app, rid))
        run = self.screen()
        first = pg.days(self.app.db, rid)[0]["date"]
        self.pick("Adiar o que falta (7 dias)")
        self.pick("Adiar")
        self.assertEqual(pg.days(self.app.db, rid)[0]["date"], first + timedelta(days=7))
        self.pick("Recalcular cargas")
        rb = self.screen()
        self.assertIsInstance(rb, ps.RebasePopup)
        self.assertEqual(rb.v["squat"], 60.0)
        self.pick("Baixar tudo 10 %")
        self.assertEqual(rb.v["squat"], 55.0)
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), run)
        self.assertEqual(pg.current_loads(self.app.db, rid)["squat"], 55.0)
        self.pick("Terminar plano")
        self.pick("Terminar")
        self.assertEqual(pg.run(self.app.db, rid)["status"], "ended")
        self.assertEqual(self.app.db.conn.execute("SELECT COUNT(*) FROM training_plan"
                                                  ).fetchone()[0], 0)
        self.pick("Apagar do registo")
        self.pick("Apagar")
        self.assertIsNone(pg.run(self.app.db, rid))

    def test_import_from_a_file_and_refuse_a_bad_one(self):
        from perennia.ui import program_screens as ps
        folder = Path(self.tmp) / "planos-teste"
        good = pg.write_template(folder)[0]
        bad = folder / ("mau" + pg.EXT)
        bad.write_text('{"format": "perennia-plan"}', "utf-8")
        self.app.push(ps.ProgramFilePopup(self.app, folders=[str(folder)]))
        pop = self.screen()
        self.assertEqual(len(pop.files), 3)                         # + o modelo em CSV
        pop.pick(bad)
        self.assertIs(self.screen(), pop)                           # recusado: fica na lista
        self.assertEqual([p for p in pg.library(self.app.db) if p["origin"] == "imported"], [])
        pop.pick(good)
        det = self.screen()
        self.assertIsInstance(det, ps.ProgramDetail)
        self.assertIn("Apagar", [i.label for i in det.list.items if i.button])
        self.pick("Apagar")
        self.pick("Apagar")
        self.assertEqual([p for p in pg.library(self.app.db) if p["origin"] == "imported"], [])

    def test_template_and_export_buttons_write_to_the_data_folder(self):
        from perennia.ui import program_screens as ps
        self.app.push(ps.ProgramsScreen(self.app))
        self.pick("Ficheiro modelo")
        folder = Path(self.app.data_dir) / "planos"
        self.assertTrue((folder / "plano-modelo.perennia-plan.json").exists())
        self.assertTrue((folder / "FORMATO-DO-PLANO.md").exists())
        self.app.push(ps.ProgramDetail(self.app, "gzclp"))
        self.pick("Exportar (.json)")
        self.assertTrue((folder / "gzclp-progressao-linear.perennia-plan.json").exists())

    def test_calendar_shows_the_plan_sessions(self):
        from perennia.core import calendar_view as cal
        rid = pg.start(self.app.db, "minimalist_2x", date.today())
        d = pg.days(self.app.db, rid)[0]
        entries = cal.planned_for(self.app.db, d["date"])
        self.assertEqual([(e.sport, e.workout_id, e.title) for e in entries],
                         [("gym", d["workout_id"], d["title"])])


class TestProfileUI(tg.GuiCase):
    def test_every_sport_has_a_profile_tab(self):
        from perennia.ui import app as app_mod
        from perennia.ui import gym_screens as gs
        for cls in (app_mod.MainMenu, gs.GymHub):
            self.app.push(cls(self.app))
            hub = self.screen()
            self.assertEqual(hub.tab_labels(), ["Treinar", "Lista de treinos", "Histórico",
                                                "Perfil", "Estatísticas"])
            self.assertTrue(hub.tab_named("Perfil"))
            self.assertTrue(hub.list.detail_below)
            self.assertIn("Capacidades para a vida → Longevidade",
                          [i.label for i in hub.list.items])
            hub.tab_named("Treinar")
            self.assertFalse(hub.list.detail_below)
            self.press(key.ESCAPE)

    def test_cycling_profile_rows(self):
        from perennia.ui import app as app_mod
        self.app.push(app_mod.MainMenu(self.app))
        hub = self.screen()
        hub.tab_named("Perfil")
        labels = [i.label for i in hub.list.items]
        for word in ("Tipo de ciclista", "Sprint (5 s)", "Anaeróbio (1 min)", "VO2máx (5 min)",
                     "Limiar (FTP)"):
            self.assertIn(word, labels)
        self.pick("Capacidades para a vida → Longevidade")
        from perennia.ui import longevity_screens as ls
        self.assertIsInstance(self.screen(), ls.LongevityMenu)

    def test_gym_profile_links_a_gap_to_a_plan(self):
        from perennia.ui import gym_screens as gs
        from perennia.ui import program_screens as ps
        for k in range(6):
            log_session(self.app.db, [("Agachamento com barra", 5, 120.0, 9.0)] * 4,
                        days_ago=1 + k * 4, sid=f"u{k}")
        self.app.push(gs.GymHub(self.app))
        hub = self.screen()
        hub.tab_named("Perfil")
        labels = [i.label for i in hub.list.items]
        for word in ("Força máxima", "Força de mãos", "Tendões", "Explosividade", "Mobilidade"):
            self.assertIn(word, labels)
        hub.list.select_data(("advice", "grip"))
        self.press(key.ENTER)
        det = self.screen()
        self.assertIsInstance(det, ps.ProgramDetail)
        self.assertEqual(det.key, "grip_block")

    def test_other_sports_profile(self):
        from perennia.ui import app as app_mod
        from perennia.ui.endurance_screens import EnduranceHub
        from perennia.ui.rowing_screens import RowingMenu
        makers = [lambda: EnduranceHub(self.app, "running"),
                  lambda: EnduranceHub(self.app, "swimming"), lambda: RowingMenu(self.app)]
        for make in makers:
            self.app.push(make())
            hub = self.screen()
            self.assertTrue(hub.tab_named("Perfil"))
            self.assertIn("Perfil", [i.label for i in hub.list.items])
            self.press(key.ESCAPE)


class TestSettingsUI(tg.GuiCase):
    def test_advanced_tab_lists_the_new_groups(self):
        self.app.open_settings()
        scr = self.screen()
        self.assertTrue(scr.tab_named("Avançado"))
        labels = [i.label for i in scr.list.items]
        for name in ("Planos de treino (ginásio)", "Perfil por desporto",
                     "Arredondar as cargas a", "Tabela de referência"):
            self.assertIn(name, labels)

    def test_inventory_offers_the_new_equipment(self):
        for k in ("gripper", "sled", "leg_press"):
            self.assertTrue(inventory.kind_name(k))
            self.assertNotEqual(inventory.kind_name(k), k)


if __name__ == "__main__":
    unittest.main()
