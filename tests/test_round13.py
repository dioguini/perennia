"""Ronda 13: o popup de Dispositivos por ligação (Bluetooth / ANT+ / SEM HARDWARE e a
lista informativa no fim), a corrida livre com velocidade (0,1) e inclinação (0,5)
registadas, e os ecrãs de corrida e remo sem os textos e o contador do topo."""
from __future__ import annotations

import importlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import backup as bk  # noqa: E402
from velo.core import feedback as fbm, fit, layouts as lay, session_review  # noqa: E402
from velo.core.db import Athlete, Database  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.io import ant  # noqa: E402
from velo.io.sim import SimulatedTreadmill  # noqa: E402
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import endurance_screens as es  # noqa: E402


class FakeStick:
    """Uma antena que não faz nada (chega para ligar um sensor ANT+ encontrado)."""
    closed = False

    def on_broadcast(self, ch, fn):
        self.handler = fn

    def close_channel(self, ch):
        pass

    def close(self):
        self.closed = True

    def send_acknowledged(self, ch, page):
        pass


# ===================================================== menu de dispositivos


class TestDevicesByConnection(tg.GuiCase):
    def _open(self) -> app_mod.DeviceScreen:
        self.app.push(app_mod.DeviceScreen(self.app))
        return self.screen()

    def _pedals(self):
        pedals = ant.AntDiscovered(4321, ant.DEVICE_POWER, "ANT+ Potência #4321")
        self.app.ant_stick = FakeStick()
        self.app.ant_found = [(3, pedals)]
        return pedals

    @staticmethod
    def _index(items, label: str, header: bool | None = None) -> int:
        for i, it in enumerate(items):
            if it.label == label and (header is None or it.header == header):
                return i
        raise AssertionError(f"sem «{label}» em {[x.label for x in items]}")

    def test_blocks_come_in_order_with_their_own_search(self):
        scr = self._open()
        items = scr.list.items
        heads = [i.label for i in items if i.header]
        self.assertEqual(heads, ["Bluetooth", "ANT+", "SEM HARDWARE", "Rolo",
                                 "Dispositivos ligados"])
        bt, ant_h = self._index(items, "Bluetooth", True), self._index(items, "ANT+", True)
        self.assertLess(bt, self._index(items, "Procurar Bluetooth"))
        self.assertLess(self._index(items, "Procurar Bluetooth"), ant_h)
        self.assertLess(ant_h, self._index(items, "Procurar ANT+"))
        self.assertLess(self._index(items, "Procurar ANT+"),
                        self._index(items, "SEM HARDWARE", True))
        # as ações das ligações ficam recuadas, por baixo do título da ligação
        self.assertEqual(items[self._index(items, "Procurar Bluetooth")].indent, 1)

    def test_found_ant_device_sits_under_ant_and_is_ticked_when_connected(self):
        pedals = self._pedals()
        scr = self._open()
        items = scr.list.items
        k = self._index(items, "ANT+ Potência #4321")
        self.assertGreater(k, self._index(items, "ANT+", True))
        self.assertLess(k, self._index(items, "SEM HARDWARE", True))
        self.assertEqual(items[k].indent, 1)
        self.assertTrue(items[k].enabled)                  # Enter liga
        scr.list.index = k
        scr.list._sync()
        scr.list.activate()
        self.assertIn(pedals.device_id,
                      [getattr(s, "device_id", "") for s in self.app.hub.sources])
        items = scr.list.items
        tick = self._index(items, "✓ ANT+ Potência #4321")
        self.assertGreater(tick, self._index(items, "ANT+", True))
        self.assertLess(tick, self._index(items, "SEM HARDWARE", True))
        self.assertNotIn("ANT+ Potência #4321", [i.label for i in items])   # já não se oferece
        # o cabeçalho da ligação conta os ligados
        self.assertIn("1", items[self._index(items, "ANT+", True)].value)

    def test_the_list_at_the_end_is_informative_only(self):
        self._pedals()
        scr = self._open()
        scr._connect_ant(*self.app.ant_found[0])
        items = scr.list.items
        end = self._index(items, "Dispositivos ligados", True)
        info = items[end + 1:]
        self.assertEqual(len(info), len(self.app.hub.sources))
        for it in info:
            self.assertTrue(it.label.startswith("✓ "))
            self.assertFalse(it.enabled)                   # só informação
            self.assertIsNone(it.action)
        pedal = next(i for i in info if "Potência" in i.label)
        self.assertIn("ANT+", pedal.value)                 # a ligação
        trainer = next(i for i in info if "Trainer" in i.label)
        self.assertIn("simulado", trainer.value)

    def test_simulated_devices_have_their_own_block_and_toggle(self):
        scr = self._open()
        items = scr.list.items
        sim = self._index(items, "SEM HARDWARE", True)
        self.assertEqual(items[sim].value, "1 ligado(s)")  # o trainer simulado
        t = self._index(items, "✓ SEM HARDWARE - Trainer")
        self.assertGreater(t, sim)
        self.assertLess(t, self._index(items, "Rolo", True))
        scr.list.index = t
        scr.list.activate()                                # Enter desliga
        self.assertEqual(len(self.app.hub.sources), 0)
        labels = [i.label for i in scr.list.items]
        self.assertNotIn("✓ SEM HARDWARE - Trainer", labels)
        self.assertIn("SEM HARDWARE - Trainer", labels)    # volta a poder ligar-se
        self.assertIn("nenhum dispositivo ligado", labels)

    def test_treadmill_and_rower_are_listed_as_connected(self):
        scr = self._open()
        scr._add_sim_treadmill()
        scr._add_sim_rower()
        items = scr.list.items
        for name in ("✓ SEM HARDWARE - Passadeira", "✓ SEM HARDWARE - Remo"):
            first = self._index(items, name)               # no bloco SEM HARDWARE…
            self.assertLess(first, self._index(items, "Rolo", True))
            rest = [i for i in items[self._index(items, "Dispositivos ligados", True):]
                    if i.label == name]
            self.assertEqual(len(rest), 1)                 # …e na lista informativa
            self.assertFalse(rest[0].enabled)
        scr.list.index = self._index(items, "✓ SEM HARDWARE - Passadeira")
        scr.list.activate()
        self.assertIsNone(self.app.treadmill)

    def test_a_small_window_still_lists_everything(self):
        scr = self._open()
        scr.set_popup_size(scr.W, 260)                     # janela baixa: duas colunas, páginas
        scr.list._sync()
        self.assertGreaterEqual(scr.list.columns, 1)
        self.assertEqual([i.label for i in scr.list.items if i.header][-1],
                         "Dispositivos ligados")


# ============================================ corrida livre: velocidade e inclinação


class TestFreeRunControls(tg.GuiCase):
    def _start(self) -> es.EnduranceSession:
        self.app.db.set("session_countdown_s", 0)
        self.app.set_treadmill(SimulatedTreadmill(20.0, 15.0))
        scr = es.EnduranceSession(self.app, "running")
        self.app.push(scr)
        self.press(key.SPACE)
        self.app._tick(0.1)
        return scr

    def test_keys_step_speed_by_a_tenth_and_incline_by_half_a_percent(self):
        scr = self._start()
        e = scr.engine
        v0 = e.speed_kmh
        self.press(key.PLUS)
        self.assertAlmostEqual(e.speed_kmh, v0 + 0.1)
        self.press(key.MINUS, key.MINUS)
        self.assertAlmostEqual(e.speed_kmh, v0 - 0.1)
        self.assertEqual(e.incline_pct, 0.0)
        self.press(key.UP)
        self.assertEqual(e.incline_pct, 0.5)
        self.press(key.UP, key.UP)
        self.assertEqual(e.incline_pct, 1.5)
        self.press(key.DOWN)
        self.assertEqual(e.incline_pct, 1.0)
        for _ in range(40):                                # nunca passa do máximo, nem fica < 0
            self.press(key.UP)
        self.assertEqual(e.incline_pct, 15.0)
        for _ in range(40):
            self.press(key.DOWN)
        self.assertEqual(e.incline_pct, 0.0)

    def test_the_controls_are_in_the_middle_and_clickable(self):
        scr = self._start()
        self.assertTrue(scr.controls.visible)
        e = scr.engine
        w, h = self.app.window.width, self.app.window.height
        cards = scr.controls.cards
        self.assertEqual(len(cards), 2)                    # velocidade e inclinação, à parte
        for c in cards:
            bx, by, bw, bh = c["rects"]["+"]
            self.assertTrue(0 < bx < w and 0 < by < h)
        v0 = e.speed_kmh
        bx, by, bw, bh = cards[0]["rects"]["+"]
        self.app._on_mouse_press(int(bx + 5), int(by + 5), 1, 0)
        self.assertAlmostEqual(e.speed_kmh, v0 + 0.1)
        bx, by, bw, bh = cards[1]["rects"]["+"]
        self.app._on_mouse_press(int(bx + 5), int(by + 5), 1, 0)
        self.assertEqual(e.incline_pct, 0.5)
        bx, by, bw, bh = cards[1]["rects"]["-"]
        self.app._on_mouse_press(int(bx + 5), int(by + 5), 1, 0)
        self.assertEqual(e.incline_pct, 0.0)
        self.assertIn("km/h", cards[0]["value"].text)

    def test_no_subtitle_no_mid_text_and_the_times_are_metrics(self):
        scr = self._start()
        self.assertEqual(scr.chrome.title.text, "Corrida livre")
        self.assertEqual(scr.chrome.subtitle.text, "")     # sem «Corrida» por baixo
        self.assertEqual(scr.metric_value("time"), "0:00")
        self.assertEqual(scr.metric_value("lap_time"), "0:00")
        for _ in range(20):
            self.app._tick(1.0)
        self.assertEqual(scr.metric_value("time"), "0:20")
        self.assertEqual(scr.metric_value("lap_time"), "0:20")
        shown = [k for k in lay.DEFAULT_RUN]
        self.assertIn("time", shown)
        self.assertIn("lap_time", shown)
        self.assertEqual(dict(lay.catalog("running"))["time"], "Tempo total")

    def test_choices_are_recorded_and_show_in_the_analysis_and_the_fit(self):
        scr = self._start()
        e = scr.engine
        for _ in range(10):
            self.app._tick(1.0)
        for _ in range(4):
            self.press(key.UP)                             # 2,0 %
        for _ in range(10):
            self.app._tick(1.0)
        self.press(key.PLUS)
        for _ in range(4):
            self.press(key.DOWN)                           # 0,0 %
        for _ in range(10):
            self.app._tick(1.0)
        self.press(key.F10)
        self.press(key.ENTER)                              # «Sim, terminar»
        self.press(key.ENTER)                              # «Guardar e terminar»
        summ = self.screen()
        self.assertIsInstance(summ, es.EnduranceSummary)
        sid = summ.result["session_id"]
        rows = self.app.db.conn.execute(
            "SELECT t_s, speed_mps, incline_pct FROM endurance_samples"
            " WHERE session_id = ? ORDER BY t_s", (sid,)).fetchall()
        inc = [r[2] for r in rows]
        self.assertIn(0.0, inc)
        self.assertIn(2.0, inc)                            # o que escolheste ficou gravado
        self.assertEqual(inc[-1], 0.0)
        speeds = {round(r[1] * 3.6, 1) for r in rows if r[1] is not None}
        self.assertIn(round(e.speed_kmh, 1), speeds)
        self.assertGreater(len(speeds), 1)                 # a velocidade também mudou
        # a análise do treino mostra a série da inclinação
        sess = fbm.load_session(self.app.db, "endurance", sid)
        self.assertIsNotNone(sess)
        data = session_review.series(self.app.db, sess)
        self.assertIn("Inclinação (%)", [ln[0] for ln in data["lines"]])
        # e o .fit leva a inclinação (campo «grade», em centésimos de %)
        msgs = fit.read_messages(summ.result["fit_path"])
        grades = [v[9] for num, v in msgs if num == fit.MSG_RECORD and 9 in v]
        self.assertIn(200, grades)

    def test_a_session_with_no_incline_has_no_incline_series(self):
        self.app.db.set("session_countdown_s", 0)
        scr = es.EnduranceSession(self.app, "running")
        self.app.push(scr)
        self.press(key.SPACE)
        for _ in range(10):
            self.app._tick(1.0)
        e = scr.engine
        e.flush()
        rows = self.app.db.conn.execute(
            "SELECT incline_pct FROM endurance_samples WHERE session_id = ?",
            (e.session_id,)).fetchall()
        self.assertTrue(rows)
        self.assertTrue(all((r[0] or 0.0) == 0.0 for r in rows))


# ===================================================== base de dados e backups


class TestInclineInTheDatabaseAndBackups(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def place(self):
        d = Path(tempfile.mkdtemp())
        self.dirs.append(d)
        db = Database(d / "perennia.db")
        db.save_athlete(Athlete(name="A", birth_year=1990, weight_kg=70, ftp_w=250, lthr=165))
        bk.prepare(db)
        return d, db

    @staticmethod
    def add_samples(db):
        from velo.core import endurance
        endurance.ensure(db)
        db.conn.execute("INSERT INTO endurance_sessions (id, sport, started_at, status)"
                        " VALUES ('s1', 'running', '2026-11-11T10:00:00', 'completed')")
        for t, inc in ((0, 0.0), (1, 0.5), (2, 2.0), (3, 2.0)):
            db.conn.execute("INSERT INTO endurance_samples (session_id, t_s, dist_m, speed_mps,"
                            " hr_bpm, incline_pct) VALUES ('s1', ?, ?, 2.8, 140, ?)",
                            (t, t * 2.8, inc))
        db.conn.commit()

    def test_old_databases_get_the_incline_column_by_themselves(self):
        d, db = self.place()
        db.conn.execute("DROP TABLE endurance_samples")
        db.conn.execute("CREATE TABLE endurance_samples (session_id TEXT, t_s INTEGER,"
                        " dist_m REAL, speed_mps REAL, hr_bpm INTEGER)")        # o formato antigo
        db.conn.commit()
        from velo.core import endurance
        endurance.ensure(db)
        endurance.ensure(db)                                   # e não falha a segunda vez
        self.assertIn("incline_pct", bk.columns(db, "endurance_samples"))

    def test_backup_keeps_the_incline_and_the_gym_layout_and_reads_old_backups(self):
        d, db = self.place()
        self.add_samples(db)
        db.set("screen_layout_gym", {"status": [0, 0, 24, 2]})
        self.assertEqual(bk.unknown_tables(db), [])
        m = bk.export(db, d, d / "b", ["sessoes", "ecra"])
        path = Path(m["path"])
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            sam = next(n for n in names if n.endswith("endurance_samples.jsonl"))
            first = json.loads(z.read(sam).decode("utf-8").splitlines()[0])
            self.assertIn("incline_pct", first)
            self.assertTrue(any("screen_layout_gym" in z.read(n).decode("utf-8")
                                for n in names if n.endswith("settings.jsonl")))
        d2, db2 = self.place()
        bk.restore(db2, d2, path)
        rows = db2.conn.execute("SELECT incline_pct FROM endurance_samples WHERE session_id='s1'"
                                " ORDER BY t_s").fetchall()
        self.assertEqual([r[0] for r in rows], [0.0, 0.5, 2.0, 2.0])
        self.assertEqual(db2.get("screen_layout_gym"), {"status": [0, 0, 24, 2]})
        # um backup antigo (sem a coluna) repõe-se na mesma, com a inclinação por preencher
        old = Path(d) / "antigo.zip"
        with zipfile.ZipFile(path) as zin, zipfile.ZipFile(old, "w") as zout:
            for item in zin.infolist():
                raw = zin.read(item.filename)
                if item.filename == sam:
                    lines = []
                    for ln in raw.decode("utf-8").splitlines():
                        row = json.loads(ln)
                        row.pop("incline_pct", None)
                        lines.append(json.dumps(row))
                    raw = ("\n".join(lines) + "\n").encode("utf-8")
                zout.writestr(item, raw)
        d3, db3 = self.place()
        bk.restore(db3, d3, old)
        rows = db3.conn.execute("SELECT t_s, incline_pct FROM endurance_samples"
                                " WHERE session_id='s1' ORDER BY t_s").fetchall()
        self.assertEqual([r[0] for r in rows], [0, 1, 2, 3])
        self.assertTrue(all(r[1] is None for r in rows))


if __name__ == "__main__":
    import unittest
    unittest.main()
