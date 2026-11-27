"""Ronda 35: todas as sincronizações funcionam como a do GarminDB (ronda 34).

As importações de ficheiros (HRV4Training, Análises, TrainingPeaks, Histórico, Saúde), as
regras do histórico, o CSV (modelo, exportar, importar), o upload manual, o «Só importar» do
GarminDB, o Wi-Fi (enviar e receber) e o Strava (importar e atualizar segmentos):

- correm em segundo plano e vêem-se no topo, ao lado de «Perennia»;
- mesmo quando levam um segundo, fica `✓ <fonte>` e a janela diz o que aconteceu;
- pode correr uma de cada tipo ao mesmo tempo;
- sair pergunta antes."""
from __future__ import annotations

import importlib
import sys
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
t9 = sys.modules.get("test_round9") or importlib.import_module("tests.test_round9")


def wait_until(cond, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


class Base(tg.GuiCase):
    def setUp(self):
        super().setUp()
        self.app.inline_tasks = False             # aqui interessa o segundo plano a sério

    def tearDown(self):
        for t in list(getattr(self.app, "tasks", [])):
            if t.running:
                t.cancel()
            t.wait(5)
        super().tearDown()

    def settle(self, kind: str | None = None) -> None:
        """Espera que as tarefas acabem e trata o resultado (o que o fotograma faria)."""
        a = self.app
        self.assertTrue(wait_until(lambda: all(t.job.done for t in a.tasks
                                               if kind is None or t.kind == kind)))
        a.poll_task()

    def hrv_file(self, text: str = "date,rMSSD\n2026-10-28,70\n") -> Path:
        d = Path(self.app.data_dir) / "in" / "hrv4training"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "My_Measurements.csv"
        f.write_text(text)
        return f

    def press_button(self, label: str) -> None:
        lst = self.screen().list
        lst.index = next(k for k, i in enumerate(lst.items) if i.button and i.label == label)
        lst.activate()


class TestFileImports(Base):
    def test_a_quick_import_still_shows_what_happened(self):
        """Um .csv que se importa num instante: fica `✓ HRV4Training` no topo e a janela
        diz o que foi feito."""
        from perennia.ui.background import TaskPopup
        self.hrv_file()
        scr = self.open_sync("HRV4Training")
        self.pick("My_Measurements.csv")
        self.assertEqual(self.app.task.kind, "sync:hrv4training")
        self.settle()
        a = self.app
        self.assertEqual(a.task.state(), "ok")
        self.assertEqual(a.topbar.task_text, "✓ HRV4Training")
        self.assertEqual(scr.sync.last_report["values"], 1)
        self.assertIn("1 valores", a._message)
        a.open_task()
        pop = self.screen()
        self.assertIsInstance(pop, TaskPopup)
        self.assertEqual(pop.chrome.title.text, "HRV4Training: My_Measurements.csv")
        labels = [i.label for i in pop.list.items]
        self.assertIn("✓ 1. A importar My_Measurements.csv", labels)
        self.assertIn("✓ 2. Concluído", labels)
        step = next(i for i in pop.list.items if i.label.startswith("✓ 1."))
        self.assertIn("1 valores", step.detail)
        # «Ver na Sincronização» abre o separador de onde veio
        self.press_button("Ver na Sincronização")
        self.assertEqual(self.screen().sync_tabs.current, "HRV4Training")

    def test_a_bad_file_fails_visibly(self):
        f = self.hrv_file("isto não é um csv do HRV4Training\n")
        scr = self.open_sync("HRV4Training")
        scr.sync.import_file("hrv4training", f)
        self.settle()
        a = self.app
        if a.task.state() == "fail":               # o importador recusa o ficheiro
            self.assertTrue(a.topbar.task_text.startswith("✗ HRV4Training"))
            self.assertIn("HRV4Training: My_Measurements.csv", a._message)
        else:                                      # ou aceita-o sem valores: diz isso
            self.assertIn("0 valores", a._message)

    def test_history_rules_and_health_export(self):
        scr = self.open_sync("Histórico")
        scr.sync.normalize(False)
        self.settle()
        self.assertEqual(self.app.task.kind, "sync:historico")
        self.assertEqual(self.app.task.state(), "ok")
        self.assertTrue(self.app.topbar.task_text.startswith("✓ "))
        scr2 = self.open_sync("Saúde")
        self.pick("Exportar o diário (.csv)")
        self.settle("sync:saude")
        out = Path(self.app.data_dir) / "out" / "csv"
        self.assertTrue(any(out.glob("*.csv")))
        self.assertIn("Guardado em", self.app._message)
        _ = scr2

    def test_csv_window_template_runs_in_the_background(self):
        from perennia.ui.csv_screens import CsvDatasetPopup
        self.open_sync("CSV")
        self.app.push(CsvDatasetPopup(self.app, "exercicios"))
        self.pick("Descarregar o modelo (.csv)")
        self.settle("sync:csv")
        out = Path(self.app.data_dir) / "out" / "csv"
        self.assertTrue(any(p.name.startswith("perennia_modelo_exercicios")
                            for p in out.glob("*.csv")))
        self.assertEqual(self.app.topbar.task_text, "✓ CSV")

    def test_manual_upload(self):
        from perennia.ui import upload_screens as up
        f = t9._write_fit(Path(self.tmp) / "ride.fit")
        scr = self.open_sync("Upload manual")
        scr.sync.open_upload(f)
        pop = self.screen()
        self.assertIsInstance(pop, up.UploadPreview)
        pop.upload()
        self.assertIsNot(self.screen(), pop)
        self.settle()
        self.assertEqual(len(gs.activities(self.app.db, "cycling")), 1)
        self.assertEqual(self.app.topbar.task_text, "✓ Upload manual")
        self.assertEqual(scr.sync.last_report["_kind"], "upload")

    def test_garmindb_import_only_is_a_task_too(self):
        tc.make_garmindb(gs.db_dir(self.app.db))
        scr = self.open_sync("GarminDB")
        self.pick("Só importar")
        self.assertEqual(self.app.task.kind, "garmindb")
        self.settle()
        self.assertEqual(scr.sync.last_report["days"], 2)
        self.assertTrue(self.app.topbar.task_text.startswith("✓ GarminDB"))


class TestManyAtOnce(Base):
    def gated(self, kind: str, gate: threading.Event):
        def work(db, log):
            log.step("a trabalhar")
            gate.wait(10)
            log.end(True)
            return True, f"{kind} feito", None
        return bg.run_task(self.app, kind, f"Tarefa {kind}", work, short=kind)

    def test_one_of_each_kind(self):
        a = self.app
        g1, g2 = threading.Event(), threading.Event()
        t1 = self.gated("sync:csv", g1)
        self.assertIsNotNone(t1)
        self.assertIsNone(self.gated("sync:csv", g1))          # o mesmo tipo: recusado
        self.assertIn("Já está a decorrer: Tarefa sync:csv", a._message)
        t2 = self.gated("sync:saude", g2)                       # outro tipo: corre ao lado
        self.assertIsNotNone(t2)
        a.poll_task()
        self.assertEqual(len([t for t in a.tasks if t.running]), 2)
        self.assertIn("+1", a.topbar.task_text)                 # «sync:saude · 00:00 · +1»
        # a janela mostra as duas, cada uma com o seu Parar
        a.open_task()
        pop = self.screen()
        self.assertEqual(pop.chrome.title.text, "Sincronizações")
        labels = [i.label for i in pop.list.items]
        self.assertIn("Tarefa sync:csv", labels)
        self.assertIn("Tarefa sync:saude", labels)
        self.assertIn("Parar sync:csv", labels)
        self.assertIn("Parar sync:saude", labels)
        a.pop()
        # sair pergunta (as duas)
        a.ask_quit()
        self.assertIn("2 sincronizações a decorrer", self.screen().title_text)
        a.pop()
        g1.set()
        g2.set()
        self.settle()
        self.assertFalse(a.task_running)
        # OK tira as acabadas
        a.open_task()
        self.press_button("OK")
        self.assertEqual(a.tasks, [])
        self.assertEqual(a.topbar.task_text, "")

    def test_restore_waits_for_any_sync(self):
        from perennia.ui import backup_screens as bks
        gate = threading.Event()
        self.gated("sync:csv", gate)
        pop = bks.RestorePopup.__new__(bks.RestorePopup)
        pop.app, pop.keys, pop.mode = self.app, {"sessions"}, "merge"
        before = len(self.app.stack)
        pop._ask()
        self.assertEqual(len(self.app.stack), before)
        self.assertIn("Espera que acabe a sincronização", self.app._message)
        gate.set()


class TestWifiAndStrava(Base):
    def test_wifi_send_runs_in_the_background(self):
        from perennia.core import lan_sync as ls
        from perennia.ui import lan_sync_screens as lss
        gate = threading.Event()
        got = {}

        def fake_send(db, data_dir, host, pin, port, keys, mode, progress):
            got.update(host=host, pin=pin, keys=keys)
            progress("a juntar as componentes")
            gate.wait(10)
            return {"bytes": 2 * 1048576, "keys": keys, "mode": mode, "fingerprint": "x"}
        orig = ls.send
        ls.send = fake_send
        try:
            scr = lss.LanSendScreen(self.app)
            self.app.push(scr)
            scr.v.update(host="192.168.1.20", pin="123456")
            scr._send()
            a = self.app
            self.assertTrue(scr._busy())
            self.assertTrue(wait_until(lambda: "a juntar" in a.task.step_text()))
            scr.update(0.1)
            self.assertIn("a juntar as componentes", scr.log)
            a.pop()                                   # sair do ecrã: o envio continua
            self.assertTrue(a.task_running)
            gate.set()
            self.settle()
        finally:
            ls.send = orig
        self.assertEqual(got["host"], "192.168.1.20")
        self.assertEqual(self.app.topbar.task_text, "✓ Wi-Fi")
        self.assertIn("Enviado 2.0 MB", self.app._message)
        self.assertEqual(scr.v["pin"], "")            # o PIN é de uma vez só

    def test_strava_import_is_a_task(self):
        t21 = sys.modules.get("test_round21") or importlib.import_module("tests.test_round21")
        from perennia.core import strava_library as lib
        from perennia.ui import connect_screens as cs
        api = t21.FakeApi(details=[t21.detail(1, "Subida da Serra", 1000, 4000)],
                          subscription=False)
        scr = cs.StravaImportScreen(self.app, http=api)
        scr.client.exchange("x", "read,read_all,activity:read")
        self.app.push(scr)
        scr.ids_text = "1"
        scr._import_ids()
        self.assertEqual(self.app.task.kind, "strava")
        scr._import_starred()                         # outra do Strava: espera pela primeira
        self.settle()
        self.assertEqual({r["segment_id"] for r in lib.library(self.app.db)}, {1})
        self.assertEqual(scr.ids_text, "")
        self.assertEqual(self.app.topbar.task_text, "✓ Strava")


if __name__ == "__main__":
    unittest.main()
