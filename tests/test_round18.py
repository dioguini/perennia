"""Ronda 18: notas nas listas, glossário, remo (novas métricas), barra do bloco, gráfico ao vivo,
tamanho da letra, modos de sessão, calendário, rato, fonte das métricas e passos da sincronização."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

import os
import stat

from perennia.core import backup, garmin_sync as gs, glossary, glossary_data, health, health_csv
from perennia.core import options
from perennia.core.db import Athlete, Database
from perennia.core.i18n import PT, set_language
from tests import test_gui as tg


class CoreCase(unittest.TestCase):
    def setUp(self):
        set_language(PT)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = Database(self.tmp / "perennia.db")
        self.addCleanup(self.db.close)
        self.db.save_athlete(Athlete(name="D", birth_year=1993, weight_kg=72.0, ftp_w=250,
                                     lthr=165))
        from perennia.core import folders             # o GarminDB em <tmp>/data/garmin
        old = folders._ROOT
        folders.set_root(self.tmp / "data")
        self.addCleanup(setattr, folders, "_ROOT", old)


# ============================================================================ glossário

class TestGlossaryCore(CoreCase):
    def test_every_tab_has_terms_and_keys_are_unique(self):
        keys = [r[0] for rows in glossary_data.TERMS.values() for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(glossary_data.TERMS), set(glossary.tab_keys()))
        for tab in glossary.tab_keys():
            self.assertGreaterEqual(len(glossary.entries(self.db, tab)), 8, tab)

    def test_covers_the_terms_asked_for(self):
        terms = " ".join(e["term"].lower() for e in glossary.all_entries(self.db))
        for word in ("rota", "segmento", ".gpx", ".fit", "série", "repetição", "fadiga",
                     "forma", "ginásio" if False else "modalidade"):
            self.assertIn(word, terms)

    def test_both_languages_have_text(self):
        for rows in glossary_data.TERMS.values():
            for key_, tpt, ten, dpt, den in rows:
                self.assertTrue(tpt and ten and dpt and den, key_)

    def test_edit_delete_restore_builtin(self):
        glossary.save(self.db, "tr.ftp", "FTP", "texto meu", "training")
        e = glossary.get(self.db, "tr.ftp")
        self.assertTrue(e["edited"])
        self.assertEqual(e["definition"], "texto meu")
        glossary.delete(self.db, "tr.ftp")
        self.assertNotIn("tr.ftp", [x["ref"] for x in glossary.all_entries(self.db)])
        self.assertEqual([x["ref"] for x in glossary.deleted_builtins(self.db)], ["tr.ftp"])
        glossary.restore(self.db, "tr.ftp")
        e = glossary.get(self.db, "tr.ftp")
        self.assertFalse(e["edited"])
        self.assertNotEqual(e["definition"], "texto meu")

    def test_custom_terms(self):
        ref = glossary.save(self.db, None, "  Minha sigla ", "o que é", "gym")
        self.assertTrue(ref.startswith("c:"))
        self.assertEqual(glossary.get(self.db, ref)["term"], "Minha sigla")
        glossary.save(self.db, ref, "Minha sigla", "outra", "health")
        self.assertEqual(glossary.get(self.db, ref)["tab"], "health")
        self.assertIn(ref, [e["ref"] for e in glossary.entries(self.db, "health")])
        glossary.delete(self.db, ref)
        self.assertIsNone(glossary.get(self.db, ref))

    def test_validation(self):
        with self.assertRaises(ValueError):
            glossary.save(self.db, None, "  ", "x", "gym")
        with self.assertRaises(ValueError):
            glossary.save(self.db, None, "a", "x", "nao_existe")
        with self.assertRaises(ValueError):
            glossary.save(self.db, "nao.existe", "a", "x", "gym")

    def test_find_ignores_accents_and_case(self):
        self.assertTrue(any(e["ref"] == "tr.atl" for e in glossary.find(self.db, "FADIGA")))
        self.assertTrue(any(e["ref"] == "gym.set" for e in glossary.find(self.db, "serie")))

    def test_restore_all_keeps_custom(self):
        glossary.save(self.db, "tr.ftp", "FTP", "x", "training")
        glossary.delete(self.db, "tr.tss")
        ref = glossary.save(self.db, None, "Meu", "d", "gym")
        self.assertEqual(glossary.restore_all(self.db), 2)
        self.assertIsNotNone(glossary.get(self.db, ref))
        self.assertEqual(glossary.deleted_builtins(self.db), [])

    def test_english(self):
        from perennia.core.i18n import EN
        set_language(EN)
        try:
            self.assertEqual(glossary.get(self.db, "tr.atl")["term"], "Fatigue (ATL)")
            self.assertEqual(glossary.tab_name("health"), "Health")
        finally:
            set_language(PT)

    def test_backup_component_exists(self):
        c = backup.BY_KEY["glossario"]
        self.assertEqual(c.tables, ("glossary", "lab_glossary"))   # + o das análises (r27)
        self.assertIn("glossary", backup.ENSURE_MODULES)


# ======================================================================= Fonte dos indicadores

class TestMetricSource(CoreCase):
    def metric(self, key):
        health.seed(self.db)
        return health.metric_by_key(self.db, key)

    def test_every_metric_has_a_valid_source(self):
        health.seed(self.db)
        for m in health.metrics(self.db, include_inactive=True):
            self.assertIn(m["source"], health.source_keys(), m["key"])
        self.assertEqual(self.metric("steps")["source"], "garmin")
        self.assertEqual(self.metric("lunch")["source"], "manual")
        self.assertEqual(self.metric("rhr")["source"], "")

    def test_old_database_gets_the_column(self):
        self.db.conn.executescript("DROP TABLE IF EXISTS daily_values; DROP TABLE IF EXISTS metric_defs;"
                                   "CREATE TABLE metric_defs (id INTEGER PRIMARY KEY, key TEXT"
                                   " UNIQUE, name TEXT NOT NULL, kind TEXT NOT NULL, unit TEXT,"
                                   " grp TEXT NOT NULL DEFAULT 'other', choices TEXT, active"
                                   " INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0,"
                                   " custom INTEGER NOT NULL DEFAULT 0);"
                                   "INSERT INTO metric_defs(key,name,kind) VALUES"
                                   " ('steps','Passos','number'),('lunch','Almoço','text');")
        health.ensure(self.db)
        src = {r["key"]: r["source"] for r in self.db.conn.execute(
            "SELECT key, source FROM metric_defs")}
        self.assertEqual(src, {"steps": "garmin", "lunch": "manual"})

    def test_save_metric_source(self):
        mid = health.save_metric(self.db, None, name="Minha", kind="number", source="device")
        self.assertEqual(health.metric(self.db, mid)["source"], "device")
        health.save_metric(self.db, mid, name="Minha", kind="number")        # mantém
        self.assertEqual(health.metric(self.db, mid)["source"], "device")
        health.save_metric(self.db, mid, name="Minha", kind="number", source="")
        self.assertEqual(health.metric(self.db, mid)["source"], "")
        with self.assertRaises(ValueError):
            health.save_metric(self.db, mid, name="x", kind="number", source="xpto")
        self.assertEqual(health.metric(self.db, health.save_metric(
            self.db, None, name="Outra", kind="text"))["source"], "manual")

    def test_import_does_not_overwrite_other_source(self):
        m = self.metric("lunch")                                  # Fonte: manual
        health.set_value(self.db, "2026-11-10", m["id"], "arroz")
        rep = {}
        self.assertFalse(health.import_value(self.db, "2026-11-10", m["id"], "massa", "csv", rep))
        self.assertEqual(rep["kept"], 1)
        self.assertEqual(health.values_for(self.db, "2026-11-10")[m["id"]]["value"], "arroz")
        # num dia sem valor, preenche
        self.assertTrue(health.import_value(self.db, "2026-11-11", m["id"], "massa", "csv"))

    def test_designated_source_wins_and_any_overwrites(self):
        steps = self.metric("steps")                              # Fonte: garmin
        health.set_value(self.db, "2026-11-10", steps["id"], 100, source="manual")
        self.assertTrue(health.import_value(self.db, "2026-11-10", steps["id"], 9000, "garmin"))
        rhr = self.metric("rhr")                                  # qualquer
        health.set_value(self.db, "2026-11-10", rhr["id"], 50, source="manual")
        self.assertTrue(health.import_value(self.db, "2026-11-10", rhr["id"], 52, "hrv4training"))

    def test_option_turns_the_rule_off(self):
        m = self.metric("lunch")
        health.set_value(self.db, "2026-11-10", m["id"], "arroz")
        self.db.set("health_respect_source", False)
        self.assertTrue(health.import_value(self.db, "2026-11-10", m["id"], "massa", "csv"))

    def test_csv_has_a_source_column_and_uses_it(self):
        self.assertEqual(health_csv.columns(self.db)[-2:], ["nota", "fonte"])
        text = health_csv.template(self.db)
        self.assertTrue(text.splitlines()[0].endswith(";nota;fonte"))
        head = health_csv.columns(self.db)
        row = ["2026-11-12"] + [""] * (len(head) - 1)
        row[head.index("Passos")] = "8000"
        row[-1] = "garmin"
        csv_text = ";".join(head) + "\n" + ";".join(row) + "\n"
        rep = health_csv.import_csv(self.db, csv_text)
        self.assertEqual(rep["values"], 1)
        steps = self.metric("steps")
        self.assertEqual(health.values_for(self.db, "2026-11-12")[steps["id"]]["source"], "garmin")
        out = health_csv.export_csv(self.db).splitlines()
        self.assertTrue(out[1].endswith(";garmin"))

    def test_garmin_importer_reports_kept(self):
        import sqlite3
        d = self.tmp / "dbs"
        d.mkdir()
        c = sqlite3.connect(d / "garmin.db")
        c.execute("CREATE TABLE daily_summary (day TEXT PRIMARY KEY, steps INTEGER, rhr INTEGER)")
        c.execute("INSERT INTO daily_summary VALUES ('2026-11-10', 9000, 50)")
        c.commit()
        c.close()
        health.seed(self.db)
        mid = health.save_metric(self.db, None, name="Passos x", kind="number", key="steps_x")
        from perennia.core import importers
        # «rhr» (qualquer): grava; «steps» (garmin): grava
        rep = importers.import_garmindb(self.db, d)
        self.assertEqual(rep["values"], 2)
        self.assertEqual(rep["kept"], 0)
        # agora um valor à mão num indicador manual
        rhr = self.metric("rhr")
        health.save_metric(self.db, rhr["id"], name=rhr["name"], kind="number", source="manual")
        health.set_value(self.db, "2026-11-10", rhr["id"], 44, source="manual")
        rep = importers.import_garmindb(self.db, d)
        self.assertEqual(rep["kept"], 1)
        self.assertEqual(health.values_for(self.db, "2026-11-10")[rhr["id"]]["value"], 44)
        self.assertIsNotNone(mid)


# ======================================================== sincronização: passos e requisitos

class TestSyncSteps(CoreCase):
    def opts(self, **kw):
        o = gs.Options(**kw)
        return o.clean()

    def test_log_steps_and_lines(self):
        log = gs.SyncLog(keep=3)
        log.step("um")
        log.step("dois")
        for i in range(5):
            log.line(f"l{i}")
        log.detail("x")
        log.end(False, "falhou")
        steps, lines = log.snapshot()
        self.assertEqual([s["state"] for s in steps], ["ok", "fail"])
        self.assertEqual(steps[1]["detail"], "falhou")
        self.assertEqual(lines, ["l2", "l3", "l4"])                     # só as últimas
        self.assertTrue(log.failed)

    def test_phase_and_diagnosis(self):
        self.assertIn("descarregar", gs.phase_of("Downloading sleep"))
        self.assertIn("importar", gs.phase_of("Importing 2026-11-01"))
        self.assertIsNone(gs.phase_of("hello"))
        self.assertIn("dois passos", gs.diagnose("Enter MFA code"))
        self.assertIn("palavra-passe", gs.diagnose("HTTP 401 Unauthorized"))
        self.assertIn("30 minutos", gs.diagnose("429 Too Many Requests"))
        self.assertIsNone(gs.diagnose("tudo bem"))

    def test_preflight_lists_what_is_missing(self):
        checks = {c["key"]: c for c in gs.preflight(self.db, self.opts())}
        self.assertFalse(checks["config"]["ok"])
        self.assertIn("GarminConnectConfig.json", checks["config"]["fix"])
        self.assertIn(str(Path("garmin") / "config"), checks["config"]["fix"])
        # a palavra-passe nunca é um requisito guardado: é pedida ao sincronizar
        self.assertTrue(checks["password"]["ok"])
        self.assertFalse(checks["password"]["blocking"])
        self.assertTrue(checks["stats"]["ok"])
        gs.write_credentials(gs.config_path(self.db), "eu@exemplo.pt")
        checks = {c["key"]: c for c in gs.preflight(self.db, self.opts())}
        self.assertTrue(checks["config"]["ok"] and checks["user"]["ok"])
        self.assertEqual(gs.blocking_problems(list(checks.values())), [])
        bad = gs.preflight(self.db, self.opts(stats=[]))
        self.assertIn("stats", [c["key"] for c in gs.blocking_problems(bad)])

    def test_streaming_run_feeds_the_log(self):
        cli = self.tmp / "fake.sh"
        cli.write_text("#!/bin/sh\necho 'Downloading monitoring'\necho 'Importing sleep'\n"
                       "echo 'Analyzing'\nexit 0\n")
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
        log = gs.SyncLog()
        ok, out = gs._run([str(cli)], None, 20, self.tmp, log)
        self.assertTrue(ok)
        self.assertEqual(log.snapshot()[1], ["Downloading monitoring", "Importing sleep",
                                             "Analyzing"])

    def test_streaming_run_stops_on_timeout_and_failure(self):
        cli = self.tmp / "slow.sh"
        cli.write_text("#!/bin/sh\nsleep 5\n")
        cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
        ok, out = gs._run([str(cli)], None, 1, self.tmp, gs.SyncLog())
        self.assertFalse(ok)
        self.assertIn("demorou", out)
        cli.write_text("#!/bin/sh\necho 'HTTP 401 Unauthorized'\nexit 1\n")
        ok, out = gs._run([str(cli)], None, 10, self.tmp, gs.SyncLog())
        self.assertFalse(ok)
        self.assertIn("401", out)

    def test_sync_reports_each_step(self):
        import sqlite3
        d = gs.db_dir(self.db)                            # data/garmin/bases/DBs
        self.assertEqual(d, self.tmp / "data" / "garmin" / "bases" / "DBs")
        d.mkdir(parents=True)
        c = sqlite3.connect(d / "garmin.db")
        c.execute("CREATE TABLE daily_summary (day TEXT PRIMARY KEY, steps INTEGER)")
        c.execute("INSERT INTO daily_summary VALUES ('2026-11-10', 9000)")
        c.commit()
        c.close()
        log = gs.SyncLog()
        ok, msg, rep = gs.sync(self.db, self.opts(stats=["monitoring"]), run_source=False,
                               log=log)
        self.assertTrue(ok, msg)
        steps, _ = log.snapshot()
        self.assertEqual(steps[-1]["text"], "Concluído")
        self.assertTrue(all(s["state"] in ("ok", "skip") for s in steps))
        self.assertTrue(any("1 valores" in s["detail"] for s in steps))

    def test_failed_run_explains_in_words(self):
        class Res:
            returncode = 1
            stdout = ""
            stderr = "HTTP 401 Unauthorized"
        gs_cli = self.tmp / "garmindb_cli.py"
        gs_cli.write_text("#!/bin/sh\n")
        gs_cli.chmod(0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = str(self.tmp) + os.pathsep + old_path
        try:
            gs.write_credentials(gs.config_path(self.db), "a@b.pt")
            log = gs.SyncLog()
            ok, msg, rep = gs.sync(self.db, self.opts(), runner=lambda *a, **k: Res(), log=log,
                                   password="x-segredo")
            self.assertFalse(ok)
            self.assertIn("recusou", msg)
            self.assertTrue(log.failed)
            text = open(gs.config_path(self.db)).read()
            self.assertIn("a@b.pt", text)
            self.assertNotIn("x-segredo", text)                 # sem palavra-passe
        finally:
            os.environ["PATH"] = old_path


class TestSyncUI(tg.GuiCase):
    def test_garmin_tab_shows_requirements_and_guide(self):
        scr = self.open_sync("GarminDB")
        labels = [i.label for i in scr.list.items]
        self.assertTrue(any("Requisitos" in x for x in labels))
        self.assertTrue(any(x.startswith("✗") or x.startswith("✓") for x in labels))
        self.assertTrue(any("Passo a passo" in x for x in labels))
        self.pick("Passo a passo")
        self.assertTrue(any("não fica guardada" in t for t in self.labels()))
        self.assertTrue(any("data/garmin" in t for t in self.labels()))

    def test_sync_now_without_requirements_says_what_is_missing(self):
        scr = self.open_sync("GarminDB")                # sem configuração em data/garmin
        panel = scr.sync
        orig, orig_cli = gs.status, gs.importers.garmindb_cli
        try:
            gs.status = lambda db: {**orig(db), "cli": True}
            gs.importers.garmindb_cli = lambda: "garmindb_cli.py"
            panel.sync_now()
        finally:
            gs.status, gs.importers.garmindb_cli = orig, orig_cli
        self.assertIsNotNone(panel.log)
        self.assertTrue(panel.log.failed)
        self.assertIsNone(panel.job)                    # nem chegou a correr o GarminDB


class TestGlossaryUI(tg.GuiCase):
    def test_top_button_and_key_open_it(self):
        from perennia.ui.glossary_screens import GlossaryScreen
        self.app.open_glossary()
        self.assertIsInstance(self.screen(), GlossaryScreen)
        self.app.pop()
        self.app._on_key_press(key.F9, 0)
        self.assertIsInstance(self.screen(), GlossaryScreen)

    def test_tabs_before_devices_button_and_tab_switch(self):
        self.app.open_glossary()
        scr = self.screen()
        self.assertEqual(scr.tab_labels()[0], "Perennia")
        self.assertEqual(len(scr.tab_labels()), len(glossary.tab_keys()))
        keys = list(self.app.topbar.buttons)
        self.assertLess(keys.index("glossary"), keys.index("devices"))
        first = [i.label for i in scr.list.items if not i.button]
        scr.set_tab(2)
        self.assertNotEqual(first, [i.label for i in scr.list.items if not i.button])

    def test_new_edit_delete_term(self):
        self.app.open_glossary()
        scr = self.screen()
        scr.set_tab(3)                                    # Ginásio
        self.pick("Novo termo")
        ed = self.screen()
        ed.v["term"] = "Dropset"
        ed.v["definition"] = "Baixar o peso e continuar."
        ed.save_exit()
        self.assertIs(self.screen(), scr)
        self.assertIn("Dropset", [i.label for i in scr.list.items])
        ref = next(e["ref"] for e in glossary.entries(self.app.db, "gym") if e["term"] == "Dropset")
        from perennia.ui.glossary_screens import TermEditor, ask_delete, open_term
        open_term(self.app, ref)                          # a janela de leitura
        self.assertTrue(any("Baixar o peso" in t for t in self.labels()))
        self.app.pop()
        self.app.push(TermEditor(self.app, ref))
        self.screen().v["definition"] = "Outra."
        self.screen().save_exit()
        self.assertEqual(glossary.get(self.app.db, ref)["definition"], "Outra.")
        ask_delete(self.app, ref)
        self.screen().list.index = 1
        self.screen().list.activate()
        self.assertIsNone(glossary.get(self.app.db, ref))

    def test_empty_term_does_not_save(self):
        from perennia.ui.glossary_screens import TermEditor
        self.app.open_glossary()
        ed = TermEditor(self.app, None, "gym")
        self.app.push(ed)
        self.assertFalse(ed.commit())

    def test_search_filters_the_list(self):
        self.app.open_glossary()
        scr = self.screen()
        scr.search_set("fadiga")                       # está noutro separador
        labels = [i.label for i in scr.list.items if not i.button]
        self.assertIn("Fadiga (ATL)", labels)
        self.assertNotIn("Barra do bloco", labels)
        scr.search_set("")
        self.assertIn("Barra do bloco", [i.label for i in scr.list.items])

    def test_not_available_in_a_session(self):
        from perennia.ui.glossary_screens import GlossaryScreen
        self.app.stack[-1].IN_SESSION = True
        try:
            self.app.open_glossary()
            self.assertNotIsInstance(self.screen(), GlossaryScreen)
        finally:
            self.app.stack[-1].IN_SESSION = False


# ==================================================================== barra do bloco e cores

class TestBlockBar(unittest.TestCase):
    def test_stages_and_order(self):
        from perennia.core import block_bar as bb
        cfg = bb.Config.make(True, 25, 10, 3)
        self.assertEqual(bb.stage(0.9, cfg), bb.NORMAL)
        self.assertEqual(bb.stage(0.25, cfg), bb.YELLOW)
        self.assertEqual(bb.stage(0.10, cfg), bb.RED)
        self.assertEqual(bb.stage(0.03, cfg), bb.BLACK)
        self.assertEqual(bb.stage(0.0, cfg), bb.BLACK)

    def test_thresholds_are_kept_in_order_and_can_be_off(self):
        from perennia.core import block_bar as bb
        cfg = bb.Config.make(True, 10, 50, 80)
        self.assertGreaterEqual(cfg.yellow, cfg.red)
        self.assertGreaterEqual(cfg.red, cfg.black)
        off = bb.Config.make(False, 25, 10, 3)
        self.assertEqual(bb.stage(0.0, off), bb.NORMAL)
        self.assertEqual(bb.color(bb.NORMAL, (1, 2, 3)), (1, 2, 3))
        self.assertEqual(bb.color(bb.RED, (1, 2, 3)), bb.COLORS[bb.RED])

    def test_from_db_uses_the_options(self):
        from perennia.core import block_bar as bb
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        db = Database(tmp / "p.db")
        self.addCleanup(db.close)
        db.set("block_bar_yellow_pct", 40)
        self.assertAlmostEqual(bb.Config.from_db(db).yellow, 0.40)


class TestLiveChartMetrics(unittest.TestCase):
    def test_only_the_sports_own_metrics(self):
        from perennia.core import live_chart as lc
        self.assertIn("speed", lc.keys("rowing"))
        self.assertIn("pace", lc.keys("rowing"))
        self.assertNotIn("pace", lc.keys("cycling"))
        self.assertNotIn("spm", lc.keys("cycling"))
        self.assertEqual(lc.clean("cycling", ["pace", "power", "xpto"]), ["power"])

    def test_marks_and_plot(self):
        from perennia.core import live_chart as lc
        ls = lc.LiveSeries("cycling", ["power", "hr"], points=30)
        for i in range(10):
            ls.add({"power": 100 + i, "hr": 120})
        ls.mark()
        for i in range(10):
            ls.add({"power": 200, "hr": 130})
        curves, marks, total = ls.plot()
        self.assertEqual(total, 20)
        self.assertEqual(marks, [0.5])
        self.assertEqual(len(curves), 2)

    def test_choice_is_saved_in_the_db(self):
        from perennia.core import live_chart as lc
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        db = Database(tmp / "p.db")
        self.addCleanup(db.close)
        lc.save(db, "rowing", ["power", "pace"])
        self.assertEqual(lc.choice(db, "rowing"), ["power", "pace"])
        self.assertEqual(lc.choice(db, "cycling"), lc.DEFAULTS["cycling"])


class TestFontSize(unittest.TestCase):
    def tearDown(self):
        from perennia.gfx import compat
        compat.FONT_PCT = 100

    def test_scaled_label_reports_requested_size(self):
        from perennia.gfx import compat
        compat.FONT_PCT = 130
        self.assertEqual(compat.scaled(10), 13.0)
        self.assertAlmostEqual(compat.scale_factor(), 1.3)
        compat.FONT_PCT = 100
        self.assertEqual(compat.scaled(10), 10)

    def test_option_binds_the_module_constant_and_is_limited(self):
        from perennia.gfx import compat
        o = options.BY_KEY["ui_font_pct"]
        self.assertEqual(o.default, 100)
        self.assertEqual((o.lo, o.hi), (80, 150))
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        db = Database(tmp / "p.db")
        self.addCleanup(db.close)
        db.set("ui_font_pct", 120)
        options.apply(db)
        self.assertEqual(compat.FONT_PCT, 120)


class TestOptionsRound18(unittest.TestCase):
    def test_new_options_exist_with_sane_defaults(self):
        for k in ("ui_font_pct", "block_bar_colors", "block_bar_yellow_pct", "block_bar_red_pct",
                  "block_bar_black_pct", "live_chart_max_series", "live_chart_points",
                  "note_max_chars", "mouse_back_button", "mouse_forward_button",
                  "garmin_log_lines", "garmin_log_line_chars", "glossary_term_chars",
                  "health_respect_source"):
            self.assertIn(k, options.BY_KEY, k)
            self.assertTrue(options.BY_KEY[k].pt and options.BY_KEY[k].en, k)
        d = options.BY_KEY
        self.assertGreater(d["block_bar_yellow_pct"].default, d["block_bar_red_pct"].default)
        self.assertGreater(d["block_bar_red_pct"].default, d["block_bar_black_pct"].default)


# ==================================================== comparação, modos de sessão e calendário

class TestComparisonRule(tg.GuiCase):
    def setup(self, **kw):
        from perennia.ui import session_setup as ss
        scr = ss.SessionSetup(self.app, "cycling", **kw)
        self.app.push(scr)
        return scr

    def test_free_with_a_route_allows_comparison(self):
        scr = self.setup(kind="free", route_id=self.route_id)
        self.assertTrue(scr.comparison_allowed)
        self.assertTrue(any("omparação" in i.label or "Modo" in i.label
                            for i in scr.list.items))

    def test_free_without_a_route_does_not(self):
        scr = self.setup(kind="free")
        scr.route_id = None                      # (a sessão livre já traz a 1.ª rota por omissão)
        self.assertFalse(scr.comparison_allowed)
        self.assertEqual(scr.mode_items(), [])

    def test_a_loaded_workout_never_does(self):
        wid = self.app.db.workouts()[0]["id"]
        scr = self.setup(kind="workout", workout_id=wid, route_id=self.route_id)
        self.assertFalse(scr.comparison_allowed)
        self.assertEqual(scr.mode_items(), [])
        scr.comparison = True
        self.assertFalse(scr.comparison_allowed)


class TestCalendarRules(tg.GuiCase):
    def day_labels(self, day):
        from perennia.ui import calendar_screens as cs
        scr = cs.DayScreen(self.app, day)
        self.app.push(scr)
        return [i.label for i in scr.list.items]

    def test_future_day_has_no_health_log_but_has_an_event(self):
        from datetime import date, timedelta
        labels = self.day_labels(date.today() + timedelta(days=3))
        self.assertFalse(any("Diário de saúde" in x for x in labels))
        self.assertTrue(any("Planear um evento" in x for x in labels))

    def test_today_has_both_and_past_has_no_event(self):
        from datetime import date, timedelta
        labels = self.day_labels(date.today())
        self.assertTrue(any("Diário de saúde" in x for x in labels))
        self.assertTrue(any("Planear um evento" in x for x in labels))
        self.app.pop()
        labels = self.day_labels(date.today() - timedelta(days=3))
        self.assertTrue(any("Diário de saúde" in x for x in labels))
        self.assertFalse(any("Planear um evento" in x for x in labels))

    def test_future_planned_workout_cannot_be_started(self):
        from datetime import date, timedelta
        from perennia.ui.brief import CyclingBrief
        wid = self.app.db.workouts()[0]["id"]
        b = CyclingBrief(self.app, wid)
        b.planned_day = date.today() + timedelta(days=2)
        self.app.push(b)
        self.assertFalse(any("Configurar sessão" in i.label for i in b.list.items))
        b.planned_day = date.today()
        b.enter()
        self.assertTrue(any("Configurar sessão" in i.label for i in b.list.items))


class TestMouseAndQuit(tg.GuiCase):
    def test_side_button_goes_back(self):
        from pyglet.window import mouse
        self.open_routes()
        before = self.screen()
        self.app._on_mouse_press(10, 10, mouse.MOUSE4, 0)
        self.assertIsNot(self.screen(), before)

    def test_side_button_option_off(self):
        from pyglet.window import mouse
        self.app.db.set("mouse_back_button", False)
        self.open_routes()
        before = self.screen()
        self.app._on_mouse_press(10, 10, mouse.MOUSE4, 0)
        self.assertIs(self.screen(), before)

    def test_forward_button_only_when_enabled(self):
        from pyglet.window import mouse
        self.open_routes()
        before = self.screen()
        self.app._on_mouse_press(10, 10, mouse.MOUSE5, 0)
        self.assertIs(self.screen(), before)
        self.app.db.set("mouse_forward_button", True)
        self.app._on_mouse_press(10, 10, mouse.MOUSE5, 0)
        self.assertIsNot(self.screen(), before)

    def test_quit_dialog_is_side_by_side_without_back(self):
        from perennia.ui import app as app_mod
        self.app.ask_quit()
        conf = self.screen()
        self.assertIsInstance(conf, app_mod.ConfirmScreen)
        labels = [i.label for i in conf.list.items]
        self.assertEqual(labels, ["Não", "Sim, sair"])
        self.assertNotIn("Voltar", labels)


class TestNotes(CoreCase):
    def test_exercise_notes_are_saved_and_kept(self):
        from perennia.core import gym
        gym.ensure(self.db)
        eid = gym.save_exercise(self.db, None, name="Remada X", mods=["strength"],
                                notes="pega neutra\nsem balanço")
        ex = next(e for e in gym.exercises(self.db) if e["id"] == eid)
        self.assertEqual(ex["notes"], "pega neutra\nsem balanço")
        gym.save_exercise(self.db, eid, name="Remada X", mods=["strength"])      # mantém
        ex = next(e for e in gym.exercises(self.db) if e["id"] == eid)
        self.assertEqual(ex["notes"], "pega neutra\nsem balanço")
        gym.save_exercise(self.db, eid, name="Remada X", mods=["strength"], notes="")
        ex = next(e for e in gym.exercises(self.db) if e["id"] == eid)
        self.assertFalse(ex["notes"])


class TestCsvRound18(CoreCase):
    def test_glossary_dataset_roundtrip(self):
        from perennia.core import csv_sync as cs
        text = cs.export_csv(self.db, "glossario")
        self.assertTrue(text.startswith("separador;termo;definicao"))
        self.assertGreater(len(text.splitlines()), 100)
        f = self.tmp / "g.csv"
        f.write_text("separador;termo;definicao\nSaúde;HRV;a minha definição\n"
                     "Ginásio;Dropset;baixar o peso\nnada;X;y\n", encoding="utf-8")
        key, rep = cs.import_file(self.db, f)
        self.assertEqual(key, "glossario")
        self.assertEqual((rep["created"], rep["updated"], rep["skipped"]), (1, 1, 1))
        self.assertEqual(glossary.get(self.db, "he.hrv")["definition"], "a minha definição")
        self.assertTrue(any(e["term"] == "Dropset" for e in glossary.entries(self.db, "gym")))

    def test_exercise_notes_travel_in_the_csv(self):
        from perennia.core import csv_sync as cs, gym
        gym.ensure(self.db)
        eid = gym.save_exercise(self.db, None, name="Remada Y", mods=["strength"], notes="dica")
        text = cs.export_csv(self.db, "exercicios")
        self.assertTrue(text.splitlines()[0].endswith(";notas"))
        self.assertIn("dica", text)
        f = self.tmp / "e.csv"
        f.write_text("nome;notas\nRemada Y;outra dica\n", encoding="utf-8")
        cs.import_file(self.db, f, "exercicios")
        self.assertEqual(next(e for e in gym.exercises(self.db) if e["id"] == eid)["notes"],
                         "outra dica")
        f.write_text("nome\nRemada Y\n", encoding="utf-8")                # sem a coluna: mantém
        cs.import_file(self.db, f, "exercicios")
        self.assertEqual(next(e for e in gym.exercises(self.db) if e["id"] == eid)["notes"],
                         "outra dica")

    def test_backup_roundtrip_of_glossary_and_source(self):
        health.seed(self.db)
        glossary.save(self.db, None, "Meu termo", "def", "gym")
        glossary.delete(self.db, "tr.tss")
        m = health.metric_by_key(self.db, "lunch")
        health.save_metric(self.db, m["id"], name=m["name"], kind=m["kind"], source="device")
        out = self.tmp / "bk"
        out.mkdir()
        man = backup.export(self.db, self.tmp / "data", out, keys=["glossario", "saude"])
        path = man["path"]
        db2 = Database(self.tmp / "outro.db")
        self.addCleanup(db2.close)
        backup.restore(db2, self.tmp / "data2", path, keys=["glossario", "saude"], safety=False)
        self.assertTrue(any(e["term"] == "Meu termo" for e in glossary.all_entries(db2)))
        self.assertEqual([e["ref"] for e in glossary.deleted_builtins(db2)], ["tr.tss"])
        self.assertEqual(health.metric_by_key(db2, "lunch")["source"], "device")

    def test_live_chart_choice_goes_with_the_screen_component(self):
        self.assertTrue(backup._is_ecra("live_chart_rowing"))
        self.assertFalse(backup._is_ecra("live_chart_points"))      # essa é uma opção


class TestSecurity(CoreCase):
    def test_restore_ignores_tables_that_are_not_the_components_own(self):
        import json
        import zipfile
        health.seed(self.db)
        m = health.metric_by_key(self.db, "lunch")
        health.set_value(self.db, "2026-11-10", m["id"], "arroz")
        glossary.save(self.db, None, "Meu", "d", "gym")
        out = self.tmp / "bk"
        out.mkdir()
        path = Path(backup.export(self.db, self.tmp / "data", out, keys=["glossario"])["path"])
        forged = self.tmp / "forjado.zip"
        with zipfile.ZipFile(path) as zin, zipfile.ZipFile(forged, "w") as zout:
            for n in zin.namelist():
                data = zin.read(n)
                if n == "manifest.json":
                    mf = json.loads(data)
                    for c in mf["components"]:
                        if c["key"] == "glossario":
                            c["tables"] = ["glossary", "daily_values", 'x"; DROP TABLE settings;--']
                    data = json.dumps(mf).encode()
                zout.writestr(n, data)
        backup.restore(self.db, self.tmp / "data", forged, keys=["glossario"], safety=False)
        self.assertEqual(health.values_for(self.db, "2026-11-10")[m["id"]]["value"], "arroz")
        self.assertTrue(any(e["term"] == "Meu" for e in glossary.all_entries(self.db)))

    def test_the_password_never_reaches_the_childs_arguments_or_environment(self):
        cli = self.tmp / "garmindb_cli"
        cli.write_text('#!/bin/sh\necho "args=$*"\nenv\n')
        cli.chmod(0o755)
        gs.write_credentials(gs.config_path(self.db), "a@b.pt")
        from perennia.core import importers
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: str(cli)
        try:
            log = gs.SyncLog(keep=500, line_chars=4000)
            opts = gs.Options(stats=["sleep"])
            opts.download = True
            ok, out = gs.run_garmindb(self.db, opts.clean(), log=log, password="segredo-77")
        finally:
            importers.garmindb_cli = orig
        self.assertTrue(ok, out)
        lines = log.snapshot()[1]
        self.assertTrue(any(x.startswith("args=-f ") for x in lines))
        self.assertFalse(any("segredo-77" in x for x in lines))
        self.assertNotIn("segredo-77", out)

    def test_log_lines_are_cut_and_options_respected(self):
        log = gs.SyncLog(keep=2, line_chars=30)
        log.line("x" * 100)
        self.assertEqual(len(log.snapshot()[1][0]), 30)
        self.assertEqual(glossary.max_term(self.db), 80)
        self.db.set("glossary_term_chars", 20)
        ref = glossary.save(self.db, None, "t" * 50, "d", "gym")
        self.assertEqual(len(glossary.get(self.db, ref)["term"]), 20)
        self.db.set("note_max_chars", 200)
        ref = glossary.save(self.db, None, "t", "d" * 500, "gym")
        self.assertEqual(len(glossary.get(self.db, ref)["definition"]), 200)

    def test_gitignore_covers_secrets(self):
        text = (Path(__file__).resolve().parents[1] / ".gitignore").read_text()
        for needle in (".claude/", ".env", "*.db", "GarminConnectConfig.json*", "*.key", "*.pem"):
            self.assertIn(needle, text)


class TestRowingMetrics(unittest.TestCase):
    def test_new_fields_exist_in_the_row_layout(self):
        from perennia.core import layouts
        names = {f[0] if isinstance(f, (tuple, list)) else f for f in layouts.ROW_FIELDS}
        for k in ("strokes", "avg_pace", "pace", "speed", "avg_speed"):
            self.assertIn(k, names)

    def test_speed_text(self):
        from perennia.ui.rowing_screens import speed_text
        self.assertEqual(speed_text(None), "—")
        self.assertEqual(speed_text(5.0), "18.0 km/h")


if __name__ == "__main__":
    unittest.main()
