"""Ronda 32: o GarminDB que funciona — o erro «module 'fitfile' has no attribute 'field_enums'».

O fitfile 2.0 (16/11/2026) tirou o `field_enums` que o GarminDB 3.x usa; o GarminDB 4 já usa o
fitfile 2, mas precisa do Python 3.12+; e o GarminDB 3.x entra no Garmin pelo «garth», que deixou
de funcionar. A Perennia verifica as versões antes de correr, explica o erro, tem «Atualizar o
GarminDB», e o perennia_setup escolhe um Python 3.12+ (e troca um .venv antigo)."""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia import install  # noqa: E402
from perennia.core import folders  # noqa: E402
from perennia.core import garmin_sync as gs  # noqa: E402
from perennia.core import importers  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")

ROOT = Path(__file__).resolve().parents[1]
ERROR = "AttributeError: module 'fitfile' has no attribute 'field_enums'"


def v(py, gdb, fit) -> dict:
    return {"python": py, "garmindb": gdb, "fitfile": fit}


class TestCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cli = self.tmp / "garmindb_cli.py"
        self.cli.write_text("# cli\n")

    def keys(self, comp) -> list[str]:
        return [p["key"] for p in comp["problems"]]

    def test_the_reported_error_python_311(self):
        comp = gs.compatibility(str(self.cli), v((3, 11, 9), (3, 7, 0), (2, 0, 0)))
        self.assertFalse(comp["ok"])
        self.assertEqual(self.keys(comp), ["fitfile", "python"])
        self.assertFalse(comp["can_repair"])                  # com o 3.11 não há pip que valha
        self.assertIn("field_enums", comp["problems"][0]["text"])
        self.assertIn("Python 3.12", comp["problems"][0]["fix"])

    def test_python_312_with_garmindb_3_can_be_repaired(self):
        comp = gs.compatibility(str(self.cli), v((3, 12, 7), (3, 9, 0), (2, 0, 0)))
        self.assertEqual(self.keys(comp), ["fitfile"])
        self.assertTrue(comp["can_repair"])
        self.assertIn("Atualizar o GarminDB", comp["problems"][0]["fix"])
        self.assertIn("garmindb>=4", comp["problems"][0]["fix"])

    def test_old_garmindb_with_old_fitfile_only_breaks_the_login(self):
        comp = gs.compatibility(str(self.cli), v((3, 12, 7), (3, 7, 0), (1, 2, 0)))
        self.assertEqual(self.keys(comp), ["old"])
        self.assertTrue(comp["problems"][0]["download_only"])

    def test_good_versions(self):
        comp = gs.compatibility(str(self.cli), v((3, 13, 1), (4, 0, 1), (2, 0, 0)))
        self.assertTrue(comp["ok"])
        self.assertFalse(comp["can_repair"])

    def test_cli_found_but_not_in_perennias_python(self):
        comp = gs.compatibility(str(self.cli), v((3, 13, 1), None, None))
        self.assertEqual(self.keys(comp), ["env"])
        self.assertTrue(comp["can_repair"])
        # um programa que não é .py (outro ambiente, um .exe): não se avalia
        self.assertTrue(gs.compatibility("/usr/bin/garmindb_cli", v((3, 11, 0), None, None))["ok"])

    def test_version_checks_block_the_sync(self):
        orig_cli, orig_comp = importers.garmindb_cli, gs.compatibility
        importers.garmindb_cli = lambda: str(self.cli)
        try:
            gs.compatibility = lambda cli=None, vv=None: orig_comp(cli, v((3, 12, 0), (3, 9, 0),
                                                                          (2, 0, 0)))
            checks = gs._version_checks(online=False)
            self.assertTrue(checks[0]["blocking"])                 # nem importa: falha ao abrir
            gs.compatibility = lambda cli=None, vv=None: orig_comp(cli, v((3, 12, 0), (3, 7, 0),
                                                                          (1, 2, 0)))
            self.assertFalse(gs._version_checks(online=False)[0]["blocking"])
            self.assertTrue(gs._version_checks(online=True)[0]["blocking"])
            gs.compatibility = lambda cli=None, vv=None: orig_comp(cli, v((3, 13, 0), (4, 0, 1),
                                                                          (2, 0, 0)))
            ok = gs._version_checks(online=True)
            self.assertTrue(ok[0]["ok"])
            self.assertIn("GarminDB 4.0.1", ok[0]["text"])
        finally:
            importers.garmindb_cli, gs.compatibility = orig_cli, orig_comp

    def test_the_error_is_explained(self):
        self.assertIn("GarminDB 4", gs.diagnose("Traceback ...\n" + ERROR))
        self.assertIn("Python 3.12", gs.diagnose(ERROR))
        self.assertIn("não está instalado", gs.diagnose("ModuleNotFoundError: No module named "
                                                        "'garmindb'"))
        self.assertIn("garth", gs.diagnose("garth.exc.GarthHTTPError: 401"))

    def test_versions_and_command(self):
        got = gs.versions()
        self.assertEqual(got["python"][:2], tuple(sys.version_info[:2]))
        self.assertEqual(gs.repair_command(), [sys.executable, "-m", "pip", "install",
                                               "--upgrade", "garmindb>=4"])


class TestEnvironment(unittest.TestCase):
    """A Perennia aberta com outro Python (o do sistema, pelo PyCharm) não vê o GarminDB do
    .venv do projeto: diz-se com que Python está a correr e como a abrir."""

    def fake_project(self, version="3.13.17") -> Path:
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".venv").mkdir()
        (tmp / ".venv" / "pyvenv.cfg").write_text(f"home = x\nversion = {version}\n")
        return tmp

    def with_app_dir(self, d: Path):
        from perennia import paths
        orig = paths.app_dir
        paths.app_dir = lambda: d
        self.addCleanup(setattr, paths, "app_dir", orig)

    def test_running_outside_the_project_venv(self):
        self.with_app_dir(self.fake_project())
        env = gs.environment()
        self.assertTrue(env["venv_exists"])
        self.assertFalse(env["using_venv"])
        self.assertEqual(env["venv_version"], "3.13.17")
        comp = gs.compatibility(None, v((3, 11, 8), None, None))
        keys = [p["key"] for p in comp["problems"]]
        self.assertEqual(keys, ["venv"])                       # a causa, não o Python 3.11
        self.assertIn(sys.executable, comp["problems"][0]["text"])
        self.assertIn("Perennia.bat", comp["problems"][0]["fix"])
        self.assertIn("Python Interpreter", comp["problems"][0]["fix"])
        checks = gs._version_checks(online=True)                # aparece nos requisitos
        self.assertTrue(any(c["key"] == "versions:venv" and c["blocking"] for c in checks))

    def test_running_inside_the_project_venv(self):
        d = self.fake_project()
        self.with_app_dir(d)
        orig = sys.prefix
        sys.prefix = str(d / ".venv")
        try:
            env = gs.environment()
            comp = gs.compatibility(None, v((3, 13, 17), None, None))
        finally:
            sys.prefix = orig
        self.assertTrue(env["using_venv"])
        self.assertNotIn("venv", [p["key"] for p in comp["problems"]])

    def test_no_project_venv_no_warning(self):
        self.with_app_dir(Path(tempfile.mkdtemp()))
        self.assertFalse(gs.environment()["venv_exists"])
        comp = gs.compatibility(None, v((3, 13, 0), None, None))
        self.assertTrue(comp["ok"])
        old = gs.compatibility(None, v((3, 11, 8), None, None))
        self.assertEqual([p["key"] for p in old["problems"]], ["python"])

    def test_status_line_says_which_python(self):
        from perennia.ui.sync_screens import SyncPanel
        self.with_app_dir(self.fake_project())
        text = SyncPanel.python_text()
        self.assertIn(sys.executable, text)
        self.assertTrue(text.startswith("Python "))


class TestRepair(unittest.TestCase):
    def test_repair_runs_pip_in_perennias_python(self):
        seen = []

        def runner(cmd, **kw):
            seen.append(cmd)

            class R:
                returncode, stdout, stderr = 0, "Successfully installed garmindb-4.0.1", ""
            return R()
        ok, out = gs.repair(runner=runner)
        self.assertTrue(ok)
        self.assertEqual(seen[0], gs.repair_command())

    def test_repair_refuses_an_old_python(self):
        orig = gs.MIN_PYTHON
        gs.MIN_PYTHON = (99, 0)
        try:
            ok, out = gs.repair(runner=lambda *a, **k: self.fail("não devia correr"))
        finally:
            gs.MIN_PYTHON = orig
        self.assertFalse(ok)
        self.assertIn("apaga a pasta .venv", out)

    def test_the_cli_of_perennias_own_python_comes_first(self):
        tmp = Path(tempfile.mkdtemp())
        own = tmp / "venv" / "bin"
        other = tmp / "outro"
        for d in (own, other):
            d.mkdir(parents=True)
            (d / "garmindb_cli.py").write_text("#\n")
        o_exe, o_dirs = importers.sys.executable, importers.cli_search_dirs
        import shutil as sh
        o_which = sh.which
        importers.sys.executable = str(own / "python")
        importers.cli_search_dirs = lambda: [str(own), str(other)]
        sh.which = lambda n: str(other / n) if n == "garmindb_cli.py" else None
        try:
            self.assertEqual(importers.garmindb_cli(), str(own / "garmindb_cli.py"))
        finally:
            importers.sys.executable, importers.cli_search_dirs = o_exe, o_dirs
            sh.which = o_which


class TestSetup(unittest.TestCase):
    def setUp(self):
        self._root = folders._ROOT
        self.tmp = Path(tempfile.mkdtemp())
        folders.set_root(self.tmp / "data")

    def tearDown(self):
        folders._ROOT = self._root

    def quiet(self, fn, *a, **kw):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            res = fn(*a, **kw)
        return res, buf.getvalue()

    def test_install_refuses_an_old_python(self):
        orig = gs.MIN_PYTHON
        gs.MIN_PYTHON = (99, 0)
        try:
            ok, out = self.quiet(install.install_garmindb,
                                 lambda *a, **k: self.fail("não devia instalar"))
        finally:
            gs.MIN_PYTHON = orig
        self.assertFalse(ok)
        self.assertIn("Python 3.12", out)

    def test_setup_offers_to_update_a_broken_garmindb(self):
        calls = []
        o_cli, o_comp, o_inst = importers.garmindb_cli, gs.compatibility, install.garmin_installed
        importers.garmindb_cli = lambda: "/x/garmindb_cli.py"
        install.garmin_installed = lambda: True
        gs.compatibility = lambda cli=None, vv=None: o_comp(
            str(Path(__file__)), v((3, 12, 0), (3, 9, 0), (2, 0, 0)))
        answers = iter(["s", "s", "eu@exemplo.pt", "n"])
        try:
            g, out = self.quiet(install.garmin, self.tmp / "data", lambda _q: next(answers),
                                lambda _q: "", lambda cmd, **k: calls.append(cmd) or 0)
        finally:
            importers.garmindb_cli, gs.compatibility = o_cli, o_comp
            install.garmin_installed = o_inst
        self.assertIn("field_enums", out)
        self.assertEqual(calls[0], gs.repair_command())

    def test_scripts_prefer_python_312_and_replace_an_old_venv(self):
        sh = (ROOT / "perennia_setup.sh").read_text(encoding="utf-8")
        self.assertIn("python3.12", sh)
        self.assertLess(sh.index("python3.13"), sh.index("python3.12"))   # o 3.13 primeiro
        self.assertLess(sh.index("python3.12"), sh.index("python3.14"))
        self.assertIn(".venv-antigo", sh)
        bat = (ROOT / "perennia_setup.bat").read_bytes().decode("ascii")
        self.assertIn("py -%%V", bat)
        self.assertIn("3.13 3.12 3.14", bat)                # o 3.13 (o testado) primeiro
        self.assertIn(r"%LocalAppData%\Python\bin\python%%V.exe", bat)   # o install manager
        self.assertIn(".venv-antigo", bat)
        self.assertIn("\r\n", bat)
        self.assertIn(".venv-antigo/", (ROOT / ".gitignore").read_text())


class TestSyncTab(tg.GuiCase):
    def test_update_button_when_garmindb_is_broken(self):
        from perennia.ui.app import ConfirmScreen
        o_cli, o_comp, o_rep = gs.importers.garmindb_cli, gs.compatibility, gs.repair
        gs.importers.garmindb_cli = lambda: "/x/garmindb_cli.py"
        gs.compatibility = lambda cli=None, vv=None: o_comp(
            str(Path(__file__)), v((3, 12, 0), (3, 9, 0), (2, 0, 0)))
        ran = []
        gs.repair = lambda **kw: ran.append(kw) or (True, "ok")
        try:
            scr = self.open_sync("GarminDB")
            labels = [i.label for i in scr.list.items]
            self.assertIn("Atualizar o GarminDB", labels)
            self.assertTrue(any("field_enums" in x for x in labels))       # o requisito ✗
            self.pick("Atualizar o GarminDB")
            self.assertIsInstance(self.screen(), ConfirmScreen)
            self.pick("Sim, instalar")
            job = scr.sync.job
            self.assertIsNotNone(job)
            job.thread.join(5) if hasattr(job, "thread") else None
            for _ in range(50):
                if job.done:
                    break
                import time
                time.sleep(0.02)
            scr.sync.update()
        finally:
            gs.importers.garmindb_cli, gs.compatibility, gs.repair = o_cli, o_comp, o_rep
        self.assertEqual(len(ran), 1)
        self.assertIn("instalado", self.app._message)

    def test_no_update_button_when_all_is_well(self):
        o_cli, o_comp = gs.importers.garmindb_cli, gs.compatibility
        gs.importers.garmindb_cli = lambda: "/x/garmindb_cli.py"
        gs.compatibility = lambda cli=None, vv=None: o_comp(
            str(Path(__file__)), v((3, 13, 0), (4, 0, 1), (2, 0, 0)))
        try:
            scr = self.open_sync("GarminDB")
            labels = [i.label for i in scr.list.items]
        finally:
            gs.importers.garmindb_cli, gs.compatibility = o_cli, o_comp
        self.assertNotIn("Atualizar o GarminDB", labels)
        self.assertTrue(any("GarminDB 4.0.1" in x for x in labels))

    def test_opened_with_another_python(self):
        """O caso real: o GarminDB 4 está no .venv (3.13), mas a Perennia foi aberta com o
        Python 3.11 do sistema — diz-se isso, e não «instala o GarminDB»."""
        from perennia import paths
        d = Path(tempfile.mkdtemp())
        (d / ".venv").mkdir()
        (d / ".venv" / "pyvenv.cfg").write_text("home = x\nversion = 3.13.17\n")
        o_dir, o_cli = paths.app_dir, gs.importers.garmindb_cli
        paths.app_dir = lambda: d
        gs.importers.garmindb_cli = lambda: None
        try:
            self.assertTrue(self.app.warn_wrong_python())
            self.assertIn(".venv", self.app._message)
            scr = self.open_sync("GarminDB")
            details = " ".join(str(i.detail or "") + " " + i.label for i in scr.list.items)
            self.assertIn(sys.executable, details)                 # Estado: com que Python
            self.assertIn("outro Python", details)                 # o requisito ✗
            scr.sync.import_only()
        finally:
            paths.app_dir, gs.importers.garmindb_cli = o_dir, o_cli
        self.assertIn("outro Python", self.app._message)
        self.assertIn("Perennia.bat", self.app._message)
        self.assertNotIn("Não encontrei", self.app._message)

    def test_no_warning_without_a_project_venv(self):
        from perennia import paths
        o_dir = paths.app_dir
        paths.app_dir = lambda: Path(tempfile.mkdtemp())
        try:
            self.assertFalse(self.app.warn_wrong_python())
        finally:
            paths.app_dir = o_dir


if __name__ == "__main__":
    unittest.main()
