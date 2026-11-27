"""Ronda 29: tudo numa pasta `data/` na raiz do projeto.

* `data/in/<categoria>` para importar e `data/out/<categoria>` para o que a Perennia grava; as
  listas de importação só procuram na pasta `data/in` certa (nada de Transferências);
* os backups também: exportar → `data/out/backups`, repor → `data/in/backups`;
* a primeira vez, os dados da pasta antiga do sistema são copiados (com os caminhos dos .fit
  corrigidos) e o GarminDB passa para `data/garmin` sem palavra-passe;
* a palavra-passe do Garmin é pedida a cada sincronização e não fica em lado nenhum;
* `main.py --setup` (o que o `perennia_setup` corre) prepara tudo num computador novo.
"""
from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia import datadir, install, paths  # noqa: E402
from perennia.core import backup as bk  # noqa: E402
from perennia.core import folders  # noqa: E402
from perennia.core import garmin_sync as gs  # noqa: E402
from perennia.core import importers  # noqa: E402
from perennia.core.db import Database  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")

ROOT = Path(__file__).resolve().parents[1]
SECRET = "p4lavra-PASSE-garmin"


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._root = folders._ROOT
        self.addCleanup(setattr, folders, "_ROOT", self._root)
        self.data = self.tmp / "data"


# ===================================================================== as pastas


class TestTree(Tmp):
    def test_the_tree_and_the_templates(self):
        copied = folders.ensure_tree(self.data)
        for k, name in folders.IN.items():
            self.assertTrue((self.data / "in" / name).is_dir(), k)
        for k, name in folders.OUT.items():
            self.assertTrue((self.data / "out" / name).is_dir(), k)
        for sport in ("ciclismo", "remo", "corrida", "natacao", "ginasio"):
            self.assertTrue((self.data / "out" / "sessoes" / sport).is_dir(), sport)
        self.assertTrue((self.data / "garmin" / "config").is_dir())
        self.assertTrue((self.data / "garmin" / "bases").is_dir())
        # os modelos de modelos/ vão para data/in, um por um
        self.assertTrue((self.data / "in" / "gpx" / "exemplo-serra.gpx").exists())
        self.assertTrue((self.data / "in" / "treinos" / "exemplo-intervalos.zwo").exists())
        self.assertTrue((self.data / "in" / "planos" / "plano-modelo.perennia-plan.json")
                        .exists())
        self.assertTrue(all((self.data / "in" / n / "LEIA-ME.txt").exists()
                            for n in folders.IN.values()))
        self.assertGreater(len(copied), 10)
        # a segunda vez não copia nada (e nunca escreve por cima do que mudaste)
        mine = self.data / "in" / "gpx" / "LEIA-ME.txt"
        mine.write_text("o meu", encoding="utf-8")
        self.assertEqual(folders.ensure_tree(self.data), [])
        self.assertEqual(mine.read_text(encoding="utf-8"), "o meu")

    def test_every_template_is_tracked_and_not_ignored(self):
        out = subprocess.run(["git", "check-ignore", "--no-index", "-v",
                              "modelos/in/backups/LEIA-ME.txt", "data/perennia.db",
                              "data/in/gpx/x.gpx"], cwd=ROOT, capture_output=True, text=True)
        if out.returncode not in (0, 1):
            self.skipTest("sem git")
        ignored = out.stdout
        self.assertNotIn("modelos/in/backups", ignored)
        self.assertIn("data/perennia.db", ignored)            # os teus dados: nunca no git
        self.assertIn("data/in/gpx/x.gpx", ignored)

    def test_shown_and_names(self):
        p = folders.in_dir("gpx", self.data)
        self.assertEqual(folders.shown(p, self.data), "data/in/gpx")
        self.assertEqual(folders.shown(Path("/noutro/sitio"), self.data), "/noutro/sitio")
        self.assertEqual(folders.session_dir("swimming", self.data),
                         self.data / "out" / "sessoes" / "natacao")
        self.assertEqual(folders.session_dir("strength", self.data),
                         self.data / "out" / "sessoes" / "ginasio")

    def test_relocate_old_paths(self):
        cases = {"rides/a.fit": "out/sessoes/ciclismo/a.fit",
                 "rowing/b.fit": "out/sessoes/remo/b.fit",
                 "strength/c.fit": "out/sessoes/ginasio/c.fit",
                 "endurance/perennia_x_corrida.fit": "out/sessoes/corrida/"
                                                     "perennia_x_corrida.fit",
                 "endurance/natacao-y.fit": "out/sessoes/natacao/natacao-y.fit",
                 "exports/w.zwo": "out/treinos/w.zwo",
                 "backups/k.zip": "out/backups/k.zip",
                 "workouts/w.erg": "in/treinos/w.erg",
                 "gpx/r.gpx": "in/gpx/r.gpx",
                 "imports/act.fit": "in/atividades/act.fit",
                 "imports/labs.xlsx": "in/analises/labs.xlsx",
                 "imports/My_Measurements.csv": "in/hrv4training/My_Measurements.csv",
                 "imports/artigos.csv": "in/csv/artigos.csv",
                 "out/sessoes/remo/z.fit": "out/sessoes/remo/z.fit"}
        for old, new in cases.items():
            self.assertEqual(folders.relocate(old), new, old)

    def test_no_configurable_folders_left(self):
        from perennia.core import options
        for k in ("path_exports", "path_imports", "path_backups", "path_workouts", "path_gpx",
                  "etl_rules_file", "adhoc_export_dir"):
            self.assertNotIn(k, options.BY_KEY)
        self.assertFalse(hasattr(paths, "user_folder"))

    def test_no_search_in_downloads_documents_or_desktop(self):
        """Ninguém procura ficheiros fora de data/in (o pedido: «Apenas na diretoria
        data/in»)."""
        bad = []
        for p in (ROOT / "perennia").rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            for needle in ('"~/Downloads"', '"~/Documents"', '"~/Transferências"',
                           '"~/Desktop"', "expanduser(\"~/"):
                if needle in text:
                    bad.append(f"{p.name}: {needle}")
        self.assertEqual(bad, [])


# ===================================================================== a migração


class TestMigration(Tmp):
    def old_place(self) -> Path:
        old = self.tmp / "sistema"
        (old / "rides").mkdir(parents=True)
        (old / "endurance").mkdir()
        (old / "backups").mkdir()
        (old / "exports").mkdir()
        (old / "rides" / "volta.fit").write_bytes(b"fit-volta")
        (old / "endurance" / "perennia_2026_natacao.fit").write_bytes(b"fit-nado")
        (old / "backups" / "b.zip").write_bytes(b"zip")
        (old / "exports" / "w.zwo").write_text("<x/>", encoding="utf-8")
        (old / "route_cache").mkdir()
        (old / "route_cache" / "x.bin").write_bytes(b"cache")         # não vale a pena copiar
        db = Database(old / datadir.DB_NAME)
        db.conn.execute(
            "INSERT INTO rides(id, status, started_at, ftp_at_ride_w, weight_at_ride_kg,"
            " fit_path) VALUES ('r1', 'done', '2026-01-01T00:00:00Z', 200, 70, ?)",
            (str(old / "rides" / "volta.fit"),))
        db.conn.commit()
        db.close()
        return old

    def garmin_home(self) -> Path:
        home = self.tmp / "casa"
        cfg_dir = home / ".GarminDb"
        cfg_dir.mkdir(parents=True)
        cfg = gs.new_config()
        cfg["credentials"].update(user="eu@exemplo.pt", password=SECRET)
        cfg["directories"].update(relative_to_home=True, base_dir="HealthData")
        (cfg_dir / gs.CONFIG_NAME).write_text(json.dumps(cfg), encoding="utf-8")
        (cfg_dir / "garmin_tokens.json").write_text('{"token": "t"}', encoding="utf-8")
        (home / "HealthData" / "DBs").mkdir(parents=True)
        (home / "HealthData" / "DBs" / "garmin.db").write_bytes(b"sqlite")
        return home

    def test_copy_once_with_paths_fixed_and_originals_kept(self):
        old = self.old_place()
        home = self.garmin_home()
        folders.set_root(self.data)
        rep = datadir.migrate_from(old, self.data, home=home)
        self.assertEqual(rep["files"], 4)                      # sem as caches
        self.assertTrue(rep["garmin"])
        self.assertEqual((self.data / "out" / "sessoes" / "ciclismo" / "volta.fit")
                         .read_bytes(), b"fit-volta")
        self.assertTrue((self.data / "out" / "sessoes" / "natacao" /
                         "perennia_2026_natacao.fit").exists())
        self.assertTrue((self.data / "out" / "backups" / "b.zip").exists())
        self.assertTrue((self.data / "out" / "treinos" / "w.zwo").exists())
        self.assertFalse((self.data / "route_cache").exists())
        self.assertTrue((self.data / datadir.MIGRATED_NOTE).exists())
        # os originais ficam onde estavam
        self.assertTrue((old / "rides" / "volta.fit").exists())
        self.assertTrue((old / datadir.DB_NAME).exists())
        con = sqlite3.connect(self.data / datadir.DB_NAME)
        fit = con.execute("SELECT fit_path FROM rides").fetchone()[0]
        con.close()
        self.assertEqual(fit, str(self.data / "out" / "sessoes" / "ciclismo" / "volta.fit"))
        # o GarminDB: as bases e o token copiados, a configuração sem palavra-passe
        self.assertTrue((self.data / "garmin" / "bases" / "DBs" / "garmin.db").exists())
        self.assertTrue((self.data / "garmin" / "config" / "garmin_tokens.json").exists())
        cfg = json.loads((self.data / "garmin" / "config" / gs.CONFIG_NAME).read_text("utf-8"))
        self.assertEqual(cfg["credentials"]["user"], "eu@exemplo.pt")
        self.assertEqual(cfg["credentials"]["password"], "")
        self.assertEqual(Path(cfg["directories"]["base_dir"]),
                         (self.data / "garmin" / "bases").resolve())
        self.assertFalse(cfg["directories"]["relative_to_home"])
        every = "".join(p.read_text("utf-8", errors="ignore")
                        for p in self.data.rglob("*") if p.is_file())
        self.assertNotIn(SECRET, every)                         # a palavra-passe não veio
        # só uma vez: com a base em data/, nada se repete
        self.assertIsNone(datadir.migrate_from(old, self.data, home=home))

    def test_nothing_to_copy(self):
        self.assertIsNone(datadir.migrate_from(self.tmp / "nada", self.data))
        report = datadir.prepare(self.data, migrate=False)
        self.assertIsNone(report)
        self.assertTrue((self.data / "in" / "gpx").is_dir())

    def test_tests_and_cli_never_touch_the_project_data_folder(self):
        self.assertTrue(os.environ.get("PERENNIA_DATA_DIR"))
        self.assertNotEqual(datadir.default_data_dir(), datadir.project_data_dir())
        self.assertEqual(datadir.project_data_dir(), paths.app_dir() / "data")


# ================================================================ a palavra-passe


class TestPasswordNeverKept(Tmp):
    def setUp(self):
        super().setUp()
        folders.set_root(self.data)
        self.db = Database(self.tmp / "p.db")
        self.addCleanup(self.db.close)

    def test_settings_have_no_password_field_to_save(self):
        gs.write_credentials(gs.config_path(self.db), "eu@exemplo.pt")
        for k, v in self.db.conn.execute("SELECT key, value FROM settings").fetchall():
            self.assertNotIn("password", k.lower())
        text = gs.config_path(self.db).read_text(encoding="utf-8")
        self.assertIn('"password": ""', text)

    def test_needs_password_only_to_download(self):
        o = gs.Options()
        o.download = False
        self.assertFalse(gs.needs_password(o))
        o.download = True
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli"
        try:
            self.assertTrue(gs.needs_password(o))
        finally:
            importers.garmindb_cli = orig

    def test_a_leftover_run_folder_is_cleaned_before_the_next_run(self):
        gs.write_credentials(gs.config_path(self.db), "eu@exemplo.pt")
        # uma execução que acabou à força (a aplicação morreu a meio) deixou o ficheiro
        left = gs.config_dir(self.db) / (gs._RUN_PREFIX + "abc")
        left.mkdir()
        (left / "gp").write_text(SECRET, encoding="utf-8")
        cfg = json.loads(gs.config_path(self.db).read_text("utf-8"))
        cfg["credentials"]["password_file"] = str(left / "gp")
        gs.config_path(self.db).write_text(json.dumps(cfg), encoding="utf-8")
        gs.scrub_config(gs.config_path(self.db))
        self.assertFalse(left.exists())
        self.assertIsNone(json.loads(gs.config_path(self.db).read_text("utf-8"))
                          ["credentials"]["password_file"])


class TestPasswordPopup(tg.GuiCase):
    def test_sync_asks_for_the_password_and_forgets_it(self):
        gs.write_credentials(gs.config_path(self.app.db), "eu@exemplo.pt")
        scr = self.open_sync("GarminDB")
        panel = scr.sync
        got = {}
        orig_cli, orig_start = gs.importers.garmindb_cli, panel._start_sync
        gs.importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli"
        panel._start_sync = lambda o, pw: got.update(pw=pw)
        try:
            panel.opts.download = True
            panel.sync_now()
            pop = self.screen()
            from perennia.ui.goal_popup import PasswordPopup
            self.assertIsInstance(pop, PasswordPopup)
            pop.on_text(SECRET)
            shown = pop.body.text + " ".join(str(i.value) for i in pop.list.items)
            self.assertNotIn(SECRET, shown)                       # só bolinhas
            self.assertIn("•" * len(SECRET), pop.body.text)
            pop.save()
            self.assertEqual(pop.text, "")                         # esquecida no popup
        finally:
            gs.importers.garmindb_cli, panel._start_sync = orig_cli, orig_start
        self.assertEqual(got["pw"], SECRET)
        self.assertNotIn(SECRET, json.dumps(dict(self.app.db.conn.execute(
            "SELECT key, value FROM settings").fetchall())))

    def test_cancel_runs_nothing(self):
        gs.write_credentials(gs.config_path(self.app.db), "eu@exemplo.pt")
        scr = self.open_sync("GarminDB")
        panel = scr.sync
        called = []
        orig_cli, orig_start = gs.importers.garmindb_cli, panel._start_sync
        gs.importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli"
        panel._start_sync = lambda o, pw: called.append(pw)
        try:
            panel.opts.download = True
            panel.sync_now()
            pop = self.screen()
            pop.on_text("abc")
            self.press(key.ESCAPE)
        finally:
            gs.importers.garmindb_cli, panel._start_sync = orig_cli, orig_start
        self.assertEqual(called, [])


# ======================================================= listas só de data/in, e out


class TestOnlyDataIn(tg.GuiCase):
    def test_route_picker_lists_only_data_in_gpx(self):
        from perennia.ui.app import GpxPicker
        gpx_in = Path(self.app.data_dir) / "in" / "gpx"
        shutil.copy2(tg.GPX, gpx_in / "a-minha-serra.gpx")
        elsewhere = Path(self.tmp) / "fora.gpx"
        shutil.copy2(tg.GPX, elsewhere)
        self.app.push(GpxPicker(self.app))
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("a-minha-serra.gpx", labels)
        self.assertIn("exemplo-serra.gpx", labels)                     # o modelo
        self.assertNotIn("fora.gpx", labels)

    def test_workout_files_and_plans_come_from_data_in(self):
        from perennia.core import programs, workout_files
        found = [p.name for p in workout_files.scan("cycling")]
        self.assertIn("exemplo-intervalos.zwo", found)
        plans = [p.name for p in programs.scan()]
        self.assertIn("plano-modelo.perennia-plan.json", plans)
        self.assertTrue(all(Path(p).parent == Path(self.app.data_dir) / "in" / "planos"
                            for p in programs.scan()))

    def test_backups_out_for_export_and_in_for_restore(self):
        from perennia.ui import backup_screens as bs
        self.assertEqual(bs.backups_dir(self.app), Path(self.app.data_dir) / "out" / "backups")
        self.assertEqual(bs.search_folders(self.app),
                         [Path(self.app.data_dir) / "in" / "backups"])
        m = bk.export(self.app.db, self.app.data_dir, bs.backups_dir(self.app), ["atalhos"])
        found = bk.find(bs.search_folders(self.app))
        self.assertEqual(found, [])                                 # o que fazes não se repõe
        shutil.copy2(m["path"], Path(self.app.data_dir) / "in" / "backups")
        self.assertEqual(len(bk.find(bs.search_folders(self.app))), 1)

    def test_exports_land_in_data_out(self):
        from perennia.core import powerbi, workout_download as wd
        self.assertEqual(wd.export_dir(data_dir=self.app.data_dir),
                         Path(self.app.data_dir) / "out" / "treinos")
        self.assertEqual(powerbi.output_dir(self.app.db, self.app.data_dir),
                         Path(self.app.data_dir) / "out" / "powerbi")
        self.assertEqual(self.app.rides_dir,
                         Path(self.app.data_dir) / "out" / "sessoes" / "ciclismo")

    def test_a_session_fit_goes_to_its_sport_folder(self):
        from perennia.core import endurance as en
        from perennia.ui import endurance_screens as es
        scr = es.EnduranceSession(self.app, "running")
        self.assertEqual(scr.engine.out_dir,
                         Path(self.app.data_dir) / "out" / "sessoes" / "corrida")
        swim = en.EnduranceEngine(self.app.db, self.app.db.athlete(), "swimming",
                                  out_dir=es._session_dir(self.app, "swimming"))
        self.assertEqual(swim.out_dir, Path(self.app.data_dir) / "out" / "sessoes" / "natacao")


class TestOldBackupsRestoreIntoTheNewTree(Tmp):
    def test_files_and_fit_paths_are_relocated(self):
        src = self.tmp / "antiga"
        (src / "out" / "sessoes" / "ciclismo").mkdir(parents=True)
        (src / "out" / "sessoes" / "ciclismo" / "v.fit").write_bytes(b"fit")
        db = Database(src / "perennia.db")
        db.conn.execute(
            "INSERT INTO rides(id, status, started_at, ftp_at_ride_w, weight_at_ride_kg,"
            " fit_path) VALUES ('r1', 'done', '2026-01-01T00:00:00Z', 200, 70, ?)",
            (str(src / "rides" / "v.fit"),))
        db.conn.commit()
        # um backup como os da versão anterior: o .fit em «rides/…» (e o caminho na base também)
        m = bk.export(db, src, self.tmp / "bk", ["sessoes"])
        db.close()
        old_zip = self.tmp / "velho.zip"
        with zipfile.ZipFile(m["path"]) as zin, zipfile.ZipFile(old_zip, "w") as zout:
            for n in zin.namelist():
                data = zin.read(n)
                if n == "manifest.json":
                    man = json.loads(data)
                    for c in man["components"]:
                        c["files"] = [dict(f, path="rides/v.fit") for f in c["files"]]
                    data = json.dumps(man).encode()
                zout.writestr(n.replace("ficheiros/out/sessoes/ciclismo/", "ficheiros/rides/"),
                              data)
        self.data.mkdir(parents=True)
        dst = Database(self.data / "perennia.db")
        rep = bk.restore(dst, self.data, old_zip, safety=False)
        self.assertEqual(rep["files"], 1)
        want = self.data / "out" / "sessoes" / "ciclismo" / "v.fit"
        self.assertTrue(want.exists())
        self.assertFalse((self.data / "rides").exists())
        fit = dst.conn.execute("SELECT fit_path FROM rides").fetchone()[0]
        self.assertEqual(fit, str(want))
        dst.close()

    def test_new_backups_keep_the_new_paths_and_skip_garmin(self):
        self.data.mkdir(parents=True)
        folders.ensure_tree(self.data, copy_templates=False)
        (self.data / "in" / "treinos" / "meu.zwo").write_text("<x/>", encoding="utf-8")
        (self.data / "out" / "powerbi" / "x.csv").write_text("a", encoding="utf-8")
        (self.data / "garmin" / "config" / "garmin_tokens.json").write_text("t", "utf-8")
        db = Database(self.data / "perennia.db")
        m = bk.export(db, self.data, self.data / "out" / "backups")
        db.close()
        with zipfile.ZipFile(m["path"]) as z:
            names = z.namelist()
        self.assertTrue(any(n.endswith("ficheiros/in/treinos/meu.zwo") for n in names))
        self.assertFalse(any("powerbi" in n for n in names))
        self.assertFalse(any("garmin_tokens" in n for n in names))
        self.assertFalse(any("/out/backups/" in n for n in names))


# ========================================================================= setup


class TestSetup(Tmp):
    def quiet(self, fn, *a, **kw):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fn(*a, **kw)
        return code, buf.getvalue()

    def test_headless_setup_creates_everything_and_can_run_again(self):
        code, out = self.quiet(install.run, self.data, interactive=False,
                               self_test=lambda: 0)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.data / "perennia.db").exists())
        self.assertTrue((self.data / "in" / "gpx" / "exemplo-serra.gpx").exists())
        db = Database(self.data / "perennia.db")
        try:
            n_workouts = db.conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
            n_ex = db.conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
        finally:
            db.close()
        self.assertGreater(n_workouts, 5)
        self.assertGreater(n_ex, 50)
        self.assertIn("Pronto.", out)
        code, out = self.quiet(install.run, self.data, interactive=False,
                               self_test=lambda: 0)
        self.assertEqual(code, 0)
        self.assertIn("Já existia", out)

    def test_garmin_step_saves_the_user_logs_in_and_keeps_no_password(self):
        answers = iter(["s", "eu@exemplo.pt", "s"])
        seen = {}
        folders.set_root(self.data)
        datadir.prepare(self.data)

        def call(cmd, **kw):
            pf = Path(json.loads(gs.config_path().read_text("utf-8"))
                      ["credentials"]["password_file"])
            seen["cmd"], seen["had"] = cmd, pf.read_text("utf-8") == SECRET
            return 0
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli"
        try:
            g = self.quiet(install.garmin, self.data, lambda _q: next(answers),
                           lambda _q: SECRET, call)[0]
        finally:
            importers.garmindb_cli = orig
        self.assertTrue(g["wanted"] and g["login"])
        self.assertEqual(g["user"], "eu@exemplo.pt")
        self.assertTrue(seen["had"])
        self.assertIn("--download", seen["cmd"])
        self.assertEqual(gs.credentials(gs.config_path()), ("eu@exemplo.pt", True))
        every = "".join(p.read_text("utf-8", errors="ignore")
                        for p in self.data.rglob("*") if p.is_file() and p.suffix != ".db")
        self.assertNotIn(SECRET, every)

    def test_garmin_step_installs_garmindb_when_missing(self):
        folders.set_root(self.data)
        datadir.prepare(self.data)
        calls = []
        state = {"installed": False}

        def call(cmd, **kw):
            calls.append(cmd)
            if "pip" in cmd:
                state["installed"] = True
            return 0
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/x/garmindb_cli" if state["installed"] else None
        answers = iter(["s", "eu@exemplo.pt", "n"])
        try:
            g = self.quiet(install.garmin, self.data, lambda _q: next(answers),
                           lambda _q: "", call)[0]
        finally:
            importers.garmindb_cli = orig
        self.assertTrue(g["installed"])
        self.assertEqual(calls[0][1:], ["-m", "pip", "install", "--upgrade", "garmindb>=4"])
        self.assertIsNone(g["login"])                     # disse que não ao login

    def test_scripts_exist_and_call_setup(self):
        sh = (ROOT / "perennia_setup.sh").read_text(encoding="utf-8")
        bat = (ROOT / "perennia_setup.bat").read_bytes().decode("ascii")
        for text in (sh, bat):
            self.assertIn("requirements.txt", text)
            self.assertIn("main.py --setup", text)
            self.assertIn(".venv", text)
        self.assertIn("\r\n", bat)                          # o cmd do Windows quer CRLF
        if os.name == "posix":
            self.assertTrue(os.access(ROOT / "perennia_setup.sh", os.X_OK))

    def test_main_setup_flag(self):
        out = subprocess.run([sys.executable, str(ROOT / "main.py"), "--setup",
                              "--sem-perguntas", "--data-dir", str(self.data)],
                             capture_output=True, text=True, timeout=300,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("núcleo OK", out.stdout)
        self.assertTrue((self.data / "perennia.db").exists())


if __name__ == "__main__":
    unittest.main()
