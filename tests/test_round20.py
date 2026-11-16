"""Ronda 20: métricas de saúde (catálogo, perguntas dependentes, descontinuar/apagar,
CSV «metricas») e o feedback do treino do dia anterior."""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import (backup, csv_sync as cs, day_feedback, health,  # noqa: E402
                           health_catalog as hc, options)
from perennia.ui import health_screens as hs  # noqa: E402
from tests.test_gui import GuiCase  # noqa: E402
from tests.test_round19 import Tmp  # noqa: E402


def names(db, **kw):
    return [m["name"] for m in health.metrics(db, **kw)]


class TestCatalog(Tmp):
    def test_seed_adds_catalog_once_without_duplicates(self):
        health.seed(self.db)
        ms = health.metrics(self.db, include_inactive=True)
        self.assertEqual(len(ms), len({m["key"] for m in ms}))
        self.assertEqual(len(ms), len({m["name"].casefold() for m in ms}))
        for key in ("lunch_diet", "stool_type", "nasal_strips", "myofascial", "away_where",
                    "long_in_bed", "lunch_out_where", "decaf_dinner", "heavy_snack"):
            self.assertIsNotNone(health.metric_by_key(self.db, key), key)
        self.assertEqual(health_seeded(self.db), set(hc.keys()))
        self.assertEqual(hc.seed(self.db), 0)

    def test_existing_metrics_are_not_duplicated(self):
        health.ensure(self.db)
        self.db.set("health_seeded", True)           # já havia métricas de origem
        health.save_metric(self.db, None, name="Fiz cocó?", kind="bool", key="meu_coco")
        hc.seed(self.db)
        self.assertEqual(sum(1 for n in names(self.db, include_inactive=True)
                             if n == "Fiz cocó?"), 1)
        self.assertIsNone(health.metric_by_key(self.db, "pooped"))

    def test_deleted_and_discontinued_do_not_come_back(self):
        health.seed(self.db)
        a, b = health.metric_by_key(self.db, "insomnia"), health.metric_by_key(self.db, "stretching")
        health.delete_metric(self.db, a["id"])
        health.discontinue(self.db, b["id"])
        hc.seed(self.db)
        self.assertIsNone(health.metric_by_key(self.db, "insomnia"))
        self.assertFalse(health.metric_by_key(self.db, "stretching")["active"])

    def test_option_can_turn_the_catalog_off(self):
        self.db.set("health_catalog_seed", False)
        health.seed(self.db)
        self.assertIsNone(health.metric_by_key(self.db, "stool_type"))

    def test_choices_and_parents_are_valid(self):
        health.seed(self.db)
        keys = {m["key"] for m in health.metrics(self.db, include_inactive=True)}
        for m in health.metrics(self.db, include_inactive=True):
            if m["kind"] == "choice":
                self.assertTrue(m["choices"], m["key"])
            for p in str(m.get("parent_key") or "").split("|"):
                if p:
                    self.assertIn(p, keys, m["key"])


def health_seeded(db):
    return set(db.get("health_catalog_seeded", []))


class TestChildQuestions(Tmp):
    def setUp(self):
        super().setUp()
        health.seed(self.db)
        self.day = date.today()

    def shown(self):
        return {m["key"] for m in health.day_metrics(self.db, self.day)}

    def test_child_hidden_until_parent_answered_yes(self):
        self.assertNotIn("stool_type", self.shown())
        pooped = health.metric_by_key(self.db, "pooped")
        health.set_value(self.db, self.day, pooped["id"], 0.0)
        self.assertNotIn("stool_type", self.shown())
        health.set_value(self.db, self.day, pooped["id"], 1.0)
        self.assertIn("stool_type", self.shown())

    def test_not_home_question_shows_on_no(self):
        home = health.metric_by_key(self.db, "home_all_day")
        health.set_value(self.db, self.day, home["id"], 1.0)
        self.assertNotIn("away_where", self.shown())
        health.set_value(self.db, self.day, home["id"], 0.0)
        self.assertIn("away_where", self.shown())

    def test_any_of_several_parents(self):
        self.assertNotIn("meat_which_lunch", self.shown())
        red = health.metric_by_key(self.db, "red_meat_lunch")
        health.set_value(self.db, self.day, red["id"], 1.0)
        self.assertIn("meat_which_lunch", self.shown())

    def test_choice_parent_value(self):
        c = health.save_metric(self.db, None, name="Local", kind="choice", choices=["a", "b"])
        k = health.save_metric(self.db, None, name="Detalhe", kind="text",
                               parent=health.metric(self.db, c)["key"], parent_value="b")
        health.set_value(self.db, self.day, c, "a")
        self.assertNotIn(health.metric(self.db, k)["key"], self.shown())
        health.set_value(self.db, self.day, c, "b")
        self.assertIn(health.metric(self.db, k)["key"], self.shown())

    def test_answered_child_stays_visible(self):
        pooped = health.metric_by_key(self.db, "pooped")
        st = health.metric_by_key(self.db, "stool_type")
        health.set_value(self.db, self.day, pooped["id"], 1.0)
        health.set_value(self.db, self.day, st["id"], "moles")
        health.set_value(self.db, self.day, pooped["id"], 0.0)
        self.assertIn("stool_type", self.shown())       # tem valor: não se esconde

    def test_self_and_unknown_parents_are_dropped(self):
        mid = health.save_metric(self.db, None, name="X", kind="bool", parent="inexistente")
        self.assertIsNone(health.metric(self.db, mid)["parent_key"])
        key = health.metric(self.db, mid)["key"]
        health.save_metric(self.db, mid, name="X", kind="bool", parent=key)
        self.assertIsNone(health.metric(self.db, mid)["parent_key"])

    def test_completeness_counts_only_applicable_active(self):
        d0, t0 = health.completeness(self.db, self.day)
        pooped = health.metric_by_key(self.db, "pooped")
        health.set_value(self.db, self.day, pooped["id"], 1.0)
        d1, t1 = health.completeness(self.db, self.day)
        self.assertEqual(d1, d0 + 1)
        self.assertEqual(t1, t0 + 3)                     # fezes, dificuldade, cor


class TestDiscontinueDelete(Tmp):
    def setUp(self):
        super().setUp()
        health.seed(self.db)
        self.m = health.metric_by_key(self.db, "stretching")
        self.yesterday = date.today() - timedelta(days=1)

    def test_discontinue_keeps_history_and_hides_when_empty(self):
        health.set_value(self.db, self.yesterday, self.m["id"], 1.0)
        health.discontinue(self.db, self.m["id"])
        m = health.metric(self.db, self.m["id"])
        self.assertFalse(m["active"])
        self.assertEqual(m["discontinued_on"], date.today().isoformat())
        self.assertIn("stretching", {x["key"] for x in health.day_metrics(self.db, self.yesterday)})
        self.assertNotIn("stretching", {x["key"] for x in health.day_metrics(self.db, date.today())})
        self.assertEqual(health.values_for(self.db, self.yesterday)[m["id"]]["value"], 1.0)

    def test_reactivate_clears_date(self):
        health.discontinue(self.db, self.m["id"])
        health.reactivate(self.db, self.m["id"])
        m = health.metric(self.db, self.m["id"])
        self.assertTrue(m["active"])
        self.assertIsNone(m["discontinued_on"])

    def test_delete_removes_values_and_unlinks_children(self):
        pooped = health.metric_by_key(self.db, "pooped")
        health.set_value(self.db, self.yesterday, pooped["id"], 1.0)
        n = health.delete_metric(self.db, pooped["id"])
        self.assertEqual(n, 1)
        self.assertIsNone(health.metric_by_key(self.db, "pooped"))
        self.assertIsNone(health.metric_by_key(self.db, "stool_type")["parent_key"])
        self.assertEqual(health.delete_metric(self.db, 99999), 0)


class TestMetricsCsv(Tmp):
    def test_export_import_round_trip_and_dependencies(self):
        health.seed(self.db)
        text = cs._render(cs.DATASETS["metricas"].columns, cs.DATASETS["metricas"].export(self.db))
        self.assertEqual(cs.detect(text), "metricas")
        rep = cs.import_csv(self.db, "metricas", text)
        self.assertEqual(rep["created"], 0)
        self.assertEqual(rep["skipped"], 0)
        self.assertEqual(health.metric_by_key(self.db, "stool_type")["parent_key"], "pooped")

    def test_bulk_add_with_forward_reference(self):
        health.seed(self.db)
        text = ("metrica;tipo;unidade;grupo;opcoes;depende_de;resposta;ativa\n"
                "Qual o local?;escolha;;Rotina;casa|trabalho;Fui ao ginásio?;sim;sim\n"
                "Fui ao ginásio?;sim/não;;Atividade;;;;sim\n"
                "Antiga;texto;;Outras;;;;não\n"
                "Sem tipo valido;escolha;;Outras;;;;sim\n")
        rep = cs.import_csv(self.db, "metricas", text)
        self.assertEqual(rep["created"], 3)
        self.assertEqual(rep["skipped"], 1)                 # escolha sem opções
        loc = health.metric_by_key(self.db, "qual_o_local")
        self.assertEqual(loc["choices"], ["casa", "trabalho"])
        self.assertEqual(loc["parent_value"], "1")
        self.assertEqual(loc["parent_key"], "fui_ao_gin_sio")
        self.assertFalse(health.metric_by_key(self.db, "antiga")["active"])
        cs.import_csv(self.db, "metricas", text)           # repetir não duplica
        self.assertEqual(sum(1 for n in names(self.db, include_inactive=True)
                             if n == "Antiga"), 1)

    def test_type_kept_when_metric_has_values(self):
        health.seed(self.db)
        m = health.metric_by_key(self.db, "pooped")
        health.set_value(self.db, date.today(), m["id"], 1.0)
        rep = cs.import_csv(self.db, "metricas", "metrica;tipo\nFiz cocó?;texto\n")
        self.assertEqual(health.metric(self.db, m["id"])["kind"], "bool")
        self.assertTrue(rep["errors"])


class TestCliImport(Tmp):
    def test_csv_kind_imports_metrics_file(self):
        import tempfile
        from perennia.core import file_import
        f = Path(tempfile.mkdtemp()) / "m.csv"
        f.write_text("metrica;tipo;grupo\nFiz yoga?;sim/não;Recuperação\n", encoding="utf-8")
        rep, text = file_import.import_file(self.db, "csv", f)
        self.assertEqual(rep["dataset"], "metricas")
        self.assertIn("1 criados", text)
        self.assertIsNotNone(health.metric_by_key(self.db, "fiz_yoga"))


class TestBackup(Tmp):
    def test_new_columns_exist_and_catalog_marks_travel_with_health(self):
        health.seed(self.db)
        cols = {r["name"] for r in self.db.conn.execute("PRAGMA table_info(metric_defs)")}
        self.assertTrue({"parent_key", "parent_value", "discontinued_on"} <= cols)
        saude = backup.BY_KEY["saude"]
        self.assertTrue(saude.settings("health_catalog_seeded"))
        self.assertTrue(saude.settings("health_seeded"))
        self.assertFalse(backup.BY_KEY["definicoes"].settings("health_catalog_seeded"))

    def test_restore_of_health_keeps_deleted_metrics_deleted(self):
        import tempfile
        from perennia.core.db import Database
        health.seed(self.db)
        health.delete_metric(self.db, health.metric_by_key(self.db, "insomnia")["id"])
        zp = Path(tempfile.mkdtemp()) / "b.zip"
        backup.export(self.db, None, zp, ["saude"])
        other = Database(Path(tempfile.mkdtemp()) / "o.db")
        backup.restore(other, None, zp, ["saude"])
        health.seed(other)
        self.assertIsNone(health.metric_by_key(other, "insomnia"))
        self.assertEqual(health.metric_by_key(other, "stool_type")["parent_key"], "pooped")


class TestDayFeedback(Tmp):
    def test_empty_without_sessions_and_off_by_option(self):
        self.assertEqual(day_feedback.for_day(self.db, date.today()), [])
        self.db.set("health_day_feedback", False)
        self.assertEqual(day_feedback.for_day(self.db, date.today()), [])

    def test_summarises_yesterdays_ride(self):
        y = date.today() - timedelta(days=1)
        self.db.conn.execute(
            "INSERT INTO rides(id, started_at, name, status, moving_s, elapsed_s, distance_m, tss,"
            " ftp_at_ride_w, weight_at_ride_kg) VALUES ('r1', ?, 'Sweet spot', 'completed', 3600, 3700, 30000, 80,"
            " 250, 75)",
            (y.isoformat() + "T12:00:00Z",))
        self.db.conn.commit()
        out = day_feedback.for_day(self.db, date.today())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["kind"], "ride")
        self.assertIn("60 minutos", out[0]["text"])
        self.assertEqual(day_feedback.for_day(self.db, y), [])   # o dia do próprio treino: nada

    def test_options_exist_with_defaults(self):
        self.assertTrue(options.get(self.db, "health_day_feedback"))
        self.assertEqual(options.get(self.db, "health_feedback_days"), 1)
        self.assertTrue(options.get(self.db, "health_catalog_seed"))


class TestScreens(GuiCase):
    def test_daily_log_group_filter_and_children(self):
        db = self.app.db
        health.seed(db)
        d = hs.DailyLogScreen(self.app, date.today())
        d.enter()
        total = len(d.list.items)
        d.group_filter = "digestion"
        d.enter()
        labels = [i.label for i in d.list.items]
        self.assertLess(len(d.list.items), total)
        self.assertIn("Fiz cocó?", labels)
        self.assertFalse(any("↳" in x for x in labels))          # filhos escondidos
        health.set_value(db, date.today(), health.metric_by_key(db, "pooped")["id"], 1.0)
        d.enter()
        self.assertTrue(any("↳" in i.label for i in d.list.items))

    def test_manager_lists_discontinued_separately(self):
        db = self.app.db
        health.seed(db)
        health.discontinue(db, health.metric_by_key(db, "stretching")["id"])
        m = hs.MetricsManager(self.app)
        m.enter()
        labels = [i.label for i in m.list.items]
        self.assertTrue(any("Descontinuadas (1)" in x for x in labels))
        m.group_filter = "digestion"
        m.enter()
        self.assertTrue(all("Descontinuadas" not in i.label for i in m.list.items))

    def test_editor_sets_parent_and_saves(self):
        db = self.app.db
        health.seed(db)
        e = hs.MetricEditor(self.app, None)
        e.enter()
        e.name = "Onde foi?"
        e.kind = "text"
        e._pick_parent(1 + [m["key"] for m in e._candidates()].index("pooped"))
        self.assertEqual(e.parent_value, "1")
        self.assertTrue(e.commit())
        m = health.metric(db, e.metric_id)
        self.assertEqual((m["parent_key"], m["parent_value"]), ("pooped", "1"))
        labels = [r.label for r in e.rows()]
        self.assertIn("Descontinuar", labels)
        self.assertIn("Apagar (com o histórico)", labels)

    def test_editor_rejects_choice_without_options(self):
        e = hs.MetricEditor(self.app, None)
        e.enter()
        e.name, e.kind, e.choices = "Z", "choice", ""
        self.assertFalse(e.commit())

    def test_manager_toggle_key(self):
        from pyglet.window import key
        db = self.app.db
        health.seed(db)
        m = hs.MetricsManager(self.app)
        m.enter()
        idx = next(i for i, it in enumerate(m.list.items)
                   if isinstance(it.data, tuple) and it.label == "Fiz alongamentos?")
        m.list.index = idx
        m.on_key(key.A, 0)
        self.assertFalse(health.metric_by_key(db, "stretching")["active"])


if __name__ == "__main__":
    unittest.main()
