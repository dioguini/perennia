"""Ronda 34: a sincronização em segundo plano.

Antes, a sincronização pertencia ao ecrã: ao ir ver o calendário, o GarminDB continuava a
correr, mas ninguém o via, o resultado perdia-se e podia começar-se outra por cima. Agora
pertence à aplicação (`app.task`):

- vê-se no topo, ao lado de «Perennia»;
- o resultado aparece em qualquer ecrã;
- pode parar-se (o GarminDB é interrompido);
- sair pede confirmação, e repor um backup espera que ela acabe;
- ao abrir, apaga-se o que uma sincronização interrompida tenha deixado."""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import garmin_sync as gs  # noqa: E402
from perennia.ui import background as bg  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
tc = sys.modules.get("test_connect") or importlib.import_module("tests.test_connect")


def wait_until(cond, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class TestCancel(unittest.TestCase):
    def test_cancel_kills_the_running_garmindb(self):
        """«Parar» interrompe o processo do GarminDB que está a correr."""
        log = gs.SyncLog()
        cmd = [sys.executable, "-c",
               "import time\nprint('a descarregar', flush=True)\ntime.sleep(60)"]
        out: list = []
        th = threading.Thread(target=lambda: out.append(gs._run_streaming(cmd, 120, None, log)))
        t0 = time.monotonic()
        th.start()
        self.assertTrue(wait_until(lambda: log._proc is not None))
        log.cancel()
        th.join(10)
        self.assertFalse(th.is_alive())
        self.assertLess(time.monotonic() - t0, 10)
        ok, msg = out[0]
        self.assertFalse(ok)
        self.assertEqual(msg, gs.stopped())
        self.assertIsNone(log._proc)

    def test_cancelled_before_it_starts(self):
        log = gs.SyncLog()
        log.cancel()
        self.assertEqual(gs._run(["x"], None, 10, None, log), (False, gs.stopped()))
        ran = []
        self.assertEqual(gs._run(["x"], lambda *a, **k: ran.append(a), 10, None, log),
                         (False, gs.stopped()))
        self.assertEqual(ran, [])

    def test_current_step_for_the_top_bar(self):
        log = gs.SyncLog()
        self.assertEqual(log.current(), "")
        log.step("A correr o GarminDB")
        log.detail("a descarregar")
        self.assertEqual(log.current(), "A correr o GarminDB · a descarregar")


class TestLeftovers(unittest.TestCase):
    def test_cleanup_removes_the_temporary_password(self):
        """Uma sincronização interrompida (a Perennia fechada a meio) podia deixar a pasta
        temporária com a palavra-passe: ao abrir, apaga-se."""
        from perennia.core import folders
        cfg_dir = gs.config_dir(None)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        run = cfg_dir / (gs._RUN_PREFIX + "abc")
        run.mkdir()
        (run / "gp").write_text("segredo")
        path = gs.config_path(None)
        had = path.read_text() if path.exists() else None
        cfg = gs.new_config()
        cfg.setdefault("credentials", {})["password_file"] = str(run / "gp")
        path.write_text(json.dumps(cfg))
        try:
            self.assertGreaterEqual(gs.cleanup_leftovers(None), 0)
            self.assertFalse(run.exists())
            again = json.loads(path.read_text())
            self.assertIsNone(again["credentials"].get("password_file"))
        finally:
            if had is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(had)
        _ = folders


class TestTask(unittest.TestCase):
    def make(self, fn, finish=None, log=None):
        now = [100.0]
        t = bg.BackgroundTask("garmindb", "Sincronização do GarminDB", fn, log=log,
                              finish=finish, clock_fn=lambda: now[0])
        return t, now

    def app(self):
        msgs: list[str] = []
        return types.SimpleNamespace(message=msgs.append, msgs=msgs)

    def test_states_and_chip(self):
        gate = threading.Event()
        t, now = self.make(lambda: gate.wait(5) and "feito")
        self.assertTrue(t.running)
        self.assertEqual(t.state(), "run")
        now[0] = 100 + 192
        self.assertEqual(t.chip_text(), "Sincronização do GarminDB · 03:12")
        t.short = "GarminDB"
        self.assertEqual(t.chip_text(), "GarminDB · 03:12")
        gate.set()
        t.wait(5)
        self.assertTrue(t.running)          # acabou, mas o resultado ainda não foi tratado
        app = self.app()
        t.finish_now(app)
        self.assertFalse(t.running)
        self.assertEqual(t.state(), "ok")
        self.assertTrue(t.chip_text().startswith("✓"))
        t.finish_now(app)                   # só uma vez
        self.assertEqual(app.msgs, [])

    def test_error_and_stop(self):
        def boom():
            raise RuntimeError("sem rede")
        t, _ = self.make(boom)
        t.wait(5)
        app = self.app()
        t.finish_now(app)
        self.assertEqual(t.state(), "fail")
        self.assertIn("sem rede", app.msgs[-1])
        self.assertTrue(t.chip_text().startswith("✗"))
        log = gs.SyncLog()
        t2, _ = self.make(lambda: None, log=log)
        t2.cancel()
        self.assertTrue(log.cancelled)
        t2.wait(5)
        t2.finish_now(app)
        self.assertEqual(t2.state(), "stop")

    def test_clock(self):
        self.assertEqual(bg.clock(5), "00:05")
        self.assertEqual(bg.clock(3725), "1:02:05")


class TestBackgroundSync(tg.GuiCase):
    """O caso real: sincronizar, ir ver o calendário e não perder nada."""

    def setUp(self):
        super().setUp()
        self.app.inline_tasks = False               # aqui interessa o segundo plano
        tc.make_garmindb(gs.db_dir(self.app.db))
        self.gate = threading.Event()
        self.ran: list = []
        self.o_cli = gs.importers.garmindb_cli
        gs.importers.garmindb_cli = lambda: "/x/garmindb_cli"

        def runner(cmd, **kw):
            # o GarminDB «a correr» até o teste o deixar acabar (ou até ser parado)
            self.ran.append(cmd)
            end = time.monotonic() + 10
            while not self.gate.is_set() and time.monotonic() < end:
                log = getattr(self.app, "sync_log", None)
                if log is not None and log.cancelled:
                    break
                time.sleep(0.01)
            return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
        self.runner = runner

    def tearDown(self):
        self.gate.set()
        t = getattr(self.app, "task", None)
        if t is not None:
            t.wait(5)
        gs.importers.garmindb_cli = self.o_cli
        super().tearDown()

    def start(self):
        scr = self.open_sync("GarminDB")
        scr.sync.runner = self.runner
        o = scr.sync.opts
        o.download, o.copy, o.import_, o.analyze = False, False, True, False
        scr.sync._start_sync(o, None)
        self.assertTrue(wait_until(lambda: self.ran))
        return scr

    def press_button(self, label: str) -> None:
        lst = self.screen().list
        lst.index = next(k for k, i in enumerate(lst.items) if i.button and i.label == label)
        lst.activate()

    def test_the_sync_survives_a_change_of_screen(self):
        scr = self.start()
        a = self.app
        self.assertTrue(a.task_running)
        self.assertIn("GarminDB ·", a.topbar.task_text)
        self.assertEqual(a.topbar.task_state, "run")
        # sair do ecrã (ir ver o calendário): a tarefa continua na aplicação
        a.pop()
        self.assertNotIsInstance(self.screen(), type(scr))
        a.poll_task()
        self.assertTrue(a.task_running)
        # outra sincronização por cima: recusada, com o sítio onde ver o progresso
        scr2 = self.open_sync("GarminDB")
        self.assertTrue(scr2.sync.busy)
        self.assertTrue(any("A sincronizar" in i.label or "O que está a acontecer" in i.label
                            for i in scr2.list.items))           # ao voltar, vê-se outra vez
        scr2.sync.sync_now()
        self.assertIn("Já está a decorrer", a._message)
        self.assertEqual(len(self.ran), 1)
        a.pop()
        # acaba enquanto estás noutro ecrã: o resultado aparece na mesma
        self.gate.set()
        self.assertTrue(wait_until(lambda: a.task.job.done))
        a.poll_task()
        self.assertFalse(a.task_running)
        self.assertIn("Sincronizado", a._message)
        self.assertEqual(a.task.state(), "ok")
        self.assertTrue(a.topbar.task_text.startswith("✓"))
        self.assertEqual(a.sync_last_report["days"], 2)

    def test_top_bar_chip_opens_the_progress(self):
        from perennia.ui.background import TaskPopup
        self.start()
        a = self.app
        a.pop()
        x0, x1 = a.topbar._task_rect
        self.assertEqual(a.topbar.hit((x0 + x1) / 2, a.window.height - 10), "task")
        a._on_mouse_press((x0 + x1) / 2, a.window.height - 10, 1, 0)
        pop = self.screen()
        self.assertIsInstance(pop, TaskPopup)
        labels = [i.label for i in pop.list.items]
        for want in ("Parar", "Ver na Sincronização", "Fechar"):
            self.assertIn(want, labels)
        self.assertTrue(any("A correr o GarminDB" in x for x in labels))
        # Fechar: a sincronização continua
        self.press_button("Fechar")
        self.assertNotIsInstance(self.screen(), TaskPopup)
        self.assertTrue(a.task_running)
        # Parar: pergunta, e o GarminDB é interrompido
        a.open_task()
        self.press_button("Parar")
        self.pick("Sim, parar")
        self.assertTrue(a.task.cancelled)
        self.gate.set()
        self.assertTrue(wait_until(lambda: a.task.job.done))
        a.poll_task()
        self.assertEqual(a.task.state(), "stop")
        self.assertIn("parada por ti", a._message)

    def test_popup_after_it_ends_and_ok_clears(self):
        from perennia.ui.background import TaskPopup
        self.start()
        a = self.app
        self.gate.set()
        self.assertTrue(wait_until(lambda: a.task.job.done))
        a.poll_task()
        a.open_task()
        pop = self.screen()
        self.assertIsInstance(pop, TaskPopup)
        self.assertIn("Concluída", pop.chrome.subtitle.text)
        self.press_button("OK")
        self.assertIsNone(a.task)
        self.assertEqual(a.topbar.task_text, "")
        self.assertIsNone(a.topbar._task_rect)

    def test_quit_and_close_ask_first(self):
        from perennia.ui.app import ConfirmScreen
        self.start()
        a = self.app
        a.ask_quit()
        conf = self.screen()
        self.assertIsInstance(conf, ConfirmScreen)
        self.assertIn("a decorrer", conf.title_text)
        self.assertIn("Parar e sair", [i.label for i in conf.list.items])
        a.pop()
        self.assertTrue(a._on_close())               # a janela não fecha sem perguntar
        self.assertIsInstance(self.screen(), ConfirmScreen)
        a.pop()
        # sair: pára o GarminDB e espera que acabe (a pasta da palavra-passe é apagada)
        a._stop_task_for_exit(wait_s=5)
        self.assertTrue(a.task.cancelled)
        self.assertTrue(a.task.job.done)

    def test_restore_waits_for_the_sync(self):
        from perennia.ui import backup_screens as bks
        self.start()
        a = self.app
        pop = bks.RestorePopup.__new__(bks.RestorePopup)
        pop.app, pop.keys, pop.mode = a, {"sessions"}, "merge"
        before = len(a.stack)
        pop._ask()
        self.assertEqual(len(a.stack), before)        # nenhuma pergunta: recusado
        self.assertIn("Espera que acabe a sincronização", a._message)


if __name__ == "__main__":
    unittest.main()
