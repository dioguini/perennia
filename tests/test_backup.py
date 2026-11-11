"""Ronda 7: backups e reposição — tudo, ou por componentes, e a reposição
(substituir ou juntar), pela janela, por arrastar o ficheiro e pela linha
de comandos."""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import backup as bk  # noqa: E402
from velo.core import climbs as climbs_mod  # noqa: E402
from velo.core import gpx  # noqa: E402
from velo.core import segments as seg  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402
from velo.core.ride import RideEngine  # noqa: E402
from velo.io.hub import SensorHub  # noqa: E402
from velo.io.sim import SimulatedTrainer  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
GPX = Path(__file__).parent / "teste.gpx"


def counts(db) -> dict:
    return {t: db.conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in bk.tables_in(db) if t not in bk.SKIP_TABLES}


class Base(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def place(self) -> tuple[Path, Database]:
        d = Path(tempfile.mkdtemp())
        self.dirs.append(d)
        db = Database(d / "perennia.db")
        db.save_athlete(Athlete(name="A", birth_year=1990, weight_kg=70, ftp_w=250, lthr=165))
        bk.prepare(db)
        return d, db

    def with_a_ride(self):
        d, db = self.place()
        _, raw = gpx.parse_gpx(GPX)
        pts = gpx.resample(raw)
        rid = db.insert_route("Serra", pts, climbs_mod.detect(pts))
        seg.save_perennia(db, None, rid, "Muro", 1000, 2000)
        db.set("keymap", {"pause": ["Q", []]})
        db.set("strava_client_secret", "segredo")
        hub = SensorHub()
        hub.add_source(SimulatedTrainer(base_power=230), role="trainer", is_trainer=True)
        e = RideEngine(db, db.athlete(), route_id=rid, points=db.route_points(rid),
                       climbs=db.climbs(rid), sensors=hub, trainer=hub, rides_dir=d / "rides")
        for _ in range(600):
            hub.tick(0.5)
            e.update(0.5)
        e.finish()
        return d, db, rid


class TestComponents(Base):
    def test_every_table_is_in_one_component(self):
        _d, db = self.place()
        self.assertEqual(bk.unknown_tables(db), [])
        seen = [t for c in bk.COMPONENTS for t in c.tables]
        self.assertEqual(len(seen), len(set(seen)))              # nenhuma em duas
        # as definições dividem-se sem sobrar nenhuma chave
        for k in ("keymap", "screen_layout_cycling", "strava_tokens", "theme", "units"):
            owners = [c.key for c in bk.COMPONENTS if c.settings and c.settings(k)]
            self.assertEqual(len(owners), 1, (k, owners))


    def test_the_session_settings_of_round_14_belong_to_one_component(self):
        # a contagem, os bips, os passos seguintes e o fim automático das séries por tempo
        for k in ("session_countdown_s", "sound_rules", "sound_on", "sound_end",
                  "workout_lookahead", "gym_auto_end_timed", "keymap"):
            owners = [c.key for c in bk.COMPONENTS if c.settings and c.settings(k)]
            self.assertEqual(len(owners), 1, (k, owners))
        self.assertEqual([c.key for c in bk.COMPONENTS if c.settings and c.settings("keymap")],
                         ["atalhos"])
        for k in ("session_countdown_s", "sound_rules", "gym_auto_end_timed"):
            self.assertEqual([c.key for c in bk.COMPONENTS if c.settings and c.settings(k)],
                             ["definicoes"], k)

    def test_every_module_that_creates_tables_is_prepared(self):
        core = Path(bk.__file__).parent
        have = sorted(p.stem for p in core.glob("*.py")
                      if any(f"\ndef {fn}(" in p.read_text(encoding="utf-8")
                             for fn in ("ensure", "ensure_table")))
        self.assertEqual(sorted(bk.ENSURE_MODULES), have)
        _d, db = self.place()
        self.assertIn("game_results", bk.tables_in(db))          # nasce no prepare


class TestExportAndRestore(Base):
    def test_full_export_is_segmented_and_restores_exactly(self):
        d, db, _rid = self.with_a_ride()
        m = bk.export(db, d, d / "backups")
        path = Path(m["path"])
        self.assertTrue(path.name.startswith("perennia-backup_"))
        self.assertTrue(path.name.endswith("_completo.zip"))
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            man = json.loads(z.read("manifest.json"))
        self.assertIn("LEIA-ME.txt", names)
        self.assertIn("06-rotas/routes.jsonl", names)
        self.assertIn("11-sessoes/rides.jsonl", names)
        self.assertTrue(any(n.startswith("11-sessoes/ficheiros/rides/") and n.endswith(".fit")
                            for n in names))
        self.assertIn("03-atalhos/settings.jsonl", names)
        self.assertFalse(man["secrets"])                         # credenciais: só se pedir
        self.assertFalse(any(n.startswith("18-ligacoes") for n in names))
        # noutro computador (outra pasta), substituir dá uma cópia exata
        d2, db2 = self.place()
        rep = bk.restore(db2, d2, path)
        self.assertEqual(rep["mode"], "replace")
        self.assertTrue(Path(rep["safety"]).exists())             # o que havia, guardado
        a, b = counts(db), counts(db2)
        self.assertEqual({t: a[t] for t in a if a[t] != b.get(t) and t != "settings"}, {})
        mine = {r[0] for r in db.conn.execute("SELECT key FROM settings")}
        theirs = {r[0] for r in db2.conn.execute("SELECT key FROM settings")}
        self.assertEqual(mine - theirs, {"strava_client_secret"})   # só as credenciais
        fit_path = db2.conn.execute("SELECT fit_path FROM rides").fetchone()[0]
        self.assertTrue(fit_path.startswith(str(d2)))             # o caminho acompanha
        self.assertTrue(Path(fit_path).exists())
        self.assertEqual(db2.get("keymap"), {"pause": ["Q", []]})
        self.assertIsNone(db2.get("strava_client_secret"))
        self.assertEqual(db2.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_an_old_backup_with_one_shortcut_per_sport_comes_back_unified(self):
        d, db, _rid = self.with_a_ride()
        # como estava numa versão anterior: um atalho por desporto
        db.set("keymap", {"ride_lap": ["K", []], "row_lap": ["M", []], "gym_pause": ["O", []],
                          "run_start": ["B", []], "devices": ["F6", []]})
        m = bk.export(db, d, d / "backups", ["atalhos"])
        d2, db2 = self.place()
        bk.restore(db2, d2, m["path"], ["atalhos"])
        self.assertEqual(db2.get("keymap"), {"devices": ["F6", []], "lap": ["K", []],
                                             "pause": ["O", []], "start_now": ["B", []]})

    def test_a_backup_with_the_new_shortcuts_is_restored_as_it_is(self):
        d, db, _rid = self.with_a_ride()
        keys = {"lap": ["H", []], "skip_block": ["B", []], "speed_up": ["W", []],
                "incline_down": ["PAGEDOWN", []], "row_res_up": ["Z", ["ctrl"]]}
        db.set("keymap", keys)
        m = bk.export(db, d, d / "backups", ["atalhos"])
        d2, db2 = self.place()
        bk.restore(db2, d2, m["path"], ["atalhos"])
        self.assertEqual(db2.get("keymap"), keys)

    def test_opening_a_database_with_old_shortcuts_unifies_them(self):
        d, db = self.place()
        db.set("keymap", {"row_finish": ["F9", []], "ride_pause": ["O", []],
                          "run_pause": ["Y", []], "save": ["W", ["ctrl"]]})
        db.conn.commit()
        db.close()
        again = Database(d / "perennia.db")
        self.assertEqual(again.get("keymap"), {"save": ["W", ["ctrl"]], "finish": ["F9", []],
                                               "pause": ["O", []]})
        again.close()

    def test_the_new_unified_id_wins_over_an_old_one(self):
        from velo.core import shortcuts
        self.assertEqual(shortcuts.migrate({"ride_lap": ["K", []], "lap": ["H", []]}),
                         {"lap": ["H", []]})
        self.assertEqual(shortcuts.migrate({}), {})
        self.assertIsNone(shortcuts.migrate(None))
        self.assertEqual(shortcuts.migrate({"devices": ["F6", []]}), {"devices": ["F6", []]})

    def test_partial_export_and_credentials_only_when_asked(self):
        d, db, _rid = self.with_a_ride()
        m = bk.export(db, d, d / "b", ["rotas", "atalhos"])
        self.assertTrue(m["path"].endswith("_parcial.zip"))
        self.assertEqual([c["key"] for c in m["components"]], ["atalhos", "rotas"])
        m2 = bk.export(db, d, d / "b2" / "x.zip", ["rotas"], include_secrets=True)
        with zipfile.ZipFile(m2["path"]) as z:
            text = z.read("18-ligacoes/settings.jsonl").decode()
        self.assertIn("strava_client_secret", text)

    def test_merge_twice_adds_nothing_and_remaps_ids(self):
        d, db, rid = self.with_a_ride()
        path = bk.export(db, d, d / "b")["path"]
        # um computador com as suas próprias rotas e segmentos (ids que batem)
        d2, db2 = self.place()
        _, raw = gpx.parse_gpx(GPX)
        pts = gpx.resample(raw)
        other = db2.insert_route("Outra", pts, climbs_mod.detect(pts))
        seg.save_perennia(db2, None, other, "Local", 500, 900)
        bk.restore(db2, d2, path, mode="merge", safety=False)
        segs = {s.name: s.route_id for s in seg.perennia_segments(db2)}
        self.assertEqual(segs, {"Local": other, "Muro": rid})
        n_climbs = db2.conn.execute("SELECT COUNT(*) FROM climbs").fetchone()[0]
        self.assertEqual(n_climbs, 2)
        linked = db2.conn.execute(
            "SELECT COUNT(*) FROM climb_efforts ce JOIN climbs c ON c.id = ce.climb_id"
            " WHERE c.route_id = ?", (rid,)).fetchone()[0]
        self.assertEqual(linked, 1)                     # o esforço ficou na subida certa
        before = counts(db2)
        bk.restore(db2, d2, path, mode="merge", safety=False)
        self.assertEqual(counts(db2), before)            # juntar outra vez não duplica
        self.assertEqual(db2.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_replacing_routes_only_tidies_rides_that_lose_their_route(self):
        d, db, rid = self.with_a_ride()
        path = bk.export(db, d, d / "b", ["perfil"])["path"]          # sem rotas
        rep = bk.restore(db, d, path, ["perfil"], safety=False)
        self.assertEqual(rep["fixed"], 0)
        # um backup de rotas de outro sítio: a rota da sessão desaparece
        d2, db2 = self.place()
        p2 = bk.export(db2, d2, d2 / "b", ["rotas"])["path"]
        rep = bk.restore(db, d, p2, ["rotas"], safety=False)
        self.assertGreater(rep["fixed"], 0)
        self.assertIsNone(db.conn.execute("SELECT route_id FROM rides").fetchone()[0])
        self.assertEqual(db.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_a_failure_changes_nothing_and_bad_files_are_refused(self):
        d, db, _rid = self.with_a_ride()
        path = bk.export(db, d, d / "b")["path"]
        before = counts(db)
        with mock.patch.object(bk, "_load_table", side_effect=RuntimeError("falhou")):
            with self.assertRaises(RuntimeError):
                bk.restore(db, d, path, safety=False)
        self.assertEqual(counts(db), before)
        bad = d / "mau.zip"
        bad.write_text("não é zip")
        with self.assertRaises(bk.BackupError):
            bk.inspect(bad)
        other = d / "outro.zip"
        with zipfile.ZipFile(other, "w") as z:
            z.writestr("manifest.json", json.dumps({"app": "Outra"}))
        with self.assertRaises(bk.BackupError):
            bk.inspect(other)
        self.assertEqual([Path(m["path"]).name for m in bk.find([d / "b", d])],
                         [Path(path).name])

    def test_command_line(self):
        import contextlib
        import io
        import main as main_mod
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        err = contextlib.redirect_stderr(io.StringIO())
        err.__enter__()
        self.addCleanup(err.__exit__, None, None, None)
        d, db, _rid = self.with_a_ride()
        db.close()
        ns = argparse.Namespace(data_dir=str(d), componentes="rotas,sessoes", modo="substituir",
                                credenciais=False, backup="", restore=None)
        self.assertEqual(main_mod.backup_cli(ns), 0)
        made = sorted((d / "backups").glob("perennia-backup_*.zip"))
        self.assertEqual(len(made), 1)
        d2 = Path(tempfile.mkdtemp())
        self.dirs.append(d2)
        ns = argparse.Namespace(data_dir=str(d2), componentes=None, modo="juntar",
                                credenciais=False, backup=None, restore=str(made[0]))
        self.assertEqual(main_mod.backup_cli(ns), 0)
        db2 = Database(d2 / "perennia.db")
        self.assertEqual(db2.conn.execute("SELECT COUNT(*) FROM rides").fetchone()[0], 1)
        db2.close()
        ns.componentes = "xpto"
        self.assertEqual(main_mod.backup_cli(ns), 2)


class TestBackupMenu(tg.GuiCase):
    def setUp(self):
        super().setUp()
        win = self.app.window
        win.width, win.height = 1920, 1080
        self.app._on_resize(1920, 1080)

    def exact(self, label: str) -> None:
        view = self.screen().list
        view.index = next(i for i, it in enumerate(view.items) if it.label == label)
        view._sync()
        view.activate()

    def test_export_some_components_then_restore_them(self):
        from velo.ui import backup_screens as bs
        self.press(key.ESCAPE)
        b = self.app.topbar.buttons["backups"][0]           # na faixa do topo
        self.app._on_mouse_press(int(b.x + 5), int(b.y + 5), 1, 0)
        scr = self.screen()
        self.assertIsInstance(scr, bs.BackupScreen)
        self.assertEqual(scr.tab_labels(), ["Exportar", "Repor", "Sincronização"])
        self.pick("Tudo — exportação completa")          # desmarca tudo
        export = next(i for i in scr.list.items if i.label == "Exportar")
        self.assertFalse(export.enabled)
        self.select("Rotas")
        self.press(key.RIGHT)                             # ←/→ também marcam
        self.pick("Exportar")
        self.assertEqual(self.screen().title_text, "Backup feito")
        self.press(key.ENTER)
        made = list((Path(self.tmp) / "backups").glob("*.zip"))
        self.assertEqual(len(made), 1)
        self.assertEqual([c["key"] for c in bk.inspect(made[0])["components"]], ["rotas"])
        # a rota desaparece… e volta com o backup
        self.app.db.delete_route(self.route_id)
        scr.tab_named("Repor")
        self.pick(made[0].name)
        pop = self.screen()
        self.assertIsInstance(pop, bs.RestorePopup)
        self.select("Como repor")
        self.press(key.RIGHT)
        self.assertEqual(pop.mode, "merge")
        self.exact("Repor")
        self.assertEqual(self.screen().title_text, "Repor o backup?")
        self.exact("Repor")                                # confirma
        self.assertEqual(self.screen().title_text, "Backup reposto")
        self.assertIsNotNone(self.app.db.route(self.route_id))
        self.press(key.ENTER)
        from velo.ui.app import HomeScreen
        self.assertIsInstance(self.screen(), HomeScreen)
        # a cópia de segurança aparece na lista do Repor
        self.app.push(bs.BackupScreen(self.app, tab=1))
        names = [i.label for i in self.screen().list.items]
        self.assertTrue(any(n.startswith("perennia-antes-de-repor") for n in names))

    def test_dropping_a_backup_on_the_window_opens_the_restore(self):
        from velo.ui import backup_screens as bs
        m = bk.export(self.app.db, Path(self.tmp), Path(self.tmp) / "x" / "b.zip", ["atalhos"])
        self.app._on_file_drop(10, 10, [m["path"]])
        self.assertIsInstance(self.screen(), bs.RestorePopup)
        self.app.reset_to_menu()
        bad = Path(self.tmp) / "x" / "nada.zip"
        bad.write_text("x")
        self.app._on_file_drop(10, 10, [str(bad)])
        self.assertIn("nada.zip", self.app._message)


if __name__ == "__main__":
    unittest.main()
