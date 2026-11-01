"""Os requisitos de outubro: sincronização (GarminDB), atalhos, botões de ação
em baixo à direita, sem scroll, «Treinar» igual em todos os desportos,
Desafios com data limite, voltas no mesmo sítio, cores das zonas, testes com
blocos e nada de arquivar."""
from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import endurance as en  # noqa: E402
from velo.core import fitness_tests as ft  # noqa: E402
from velo.core import garmin_sync as gsync  # noqa: E402
from velo.core import gym  # noqa: E402
from velo.core import importers  # noqa: E402
from velo.core import sport_challenges as sc  # noqa: E402
from velo.core.db import Database  # noqa: E402
from velo.io import rower as rio  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import builder_screens as bs  # noqa: E402
from velo.ui import challenge_screens as chs  # noqa: E402
from velo.ui import health_screens as hs  # noqa: E402
from velo.ui import rowing_screens as rs  # noqa: E402
from velo.ui import widgets as wd  # noqa: E402


# ================================================================== widgets


class TestListViewHasNoScroll(unittest.TestCase):
    def test_rows_flow_into_columns_and_buttons_go_bottom_right(self):
        view = wd.ListView(48, 600, 1184, visible_rows=10)
        view.bar_right = 1232
        items = [wd.Item(f"linha {i}") for i in range(25)]
        items += [wd.Item("Cancelar", button=True),
                  wd.Item("Guardar", button=True, primary=True, action=lambda: hits.append(1))]
        hits: list = []
        view.set_items(items)
        self.assertEqual(view.columns, 3)                   # 25 linhas em 3 colunas
        self.assertEqual(len(view._cells), 25)              # todas à vista, sem página
        self.assertEqual(view.page_label.text, "")
        xs = sorted({round(x) for _i, x, _y, _w in view._cells})
        self.assertEqual(len(xs), 3)
        # os botões não são linhas; ficam em baixo, à direita, o principal por último
        self.assertEqual([i for i, *_ in view._button_rects], [25, 26])
        last = view._button_rects[-1]
        self.assertAlmostEqual(last[1] + last[2], 1232, delta=1)
        self.assertEqual(last[3], wd.BUTTON_Y)
        self.assertTrue(view.press_button("primary"))
        self.assertEqual(hits, [1])

    def test_pages_only_when_even_columns_do_not_fit(self):
        view = wd.ListView(48, 600, 700, visible_rows=5)      # cabem 2 colunas de 5
        view.set_items([wd.Item(str(i)) for i in range(14)])
        self.assertEqual(view.columns, 2)
        self.assertIn("1/2", view.page_label.text)
        view.index = 12
        view._sync()
        self.assertIn("2/2", view.page_label.text)


class TestTopBarClock(unittest.TestCase):
    def test_date_and_time_next_to_devices(self):
        import pyglet
        win = pyglet.window.Window(width=1280, height=760)
        bar = wd.TopBar(win)
        bar.set_texts("Dispositivos", "Definições", "Desligar")
        bar.now = datetime(2026, 10, 31, 9, 5)
        bar.update_clock()
        bar.layout()
        self.assertEqual(bar.clock.text, "sáb 31/10/2026 · 09:05")
        devices_x = bar.buttons["devices"][0].x
        self.assertLess(bar.clock.x, devices_x)              # à esquerda do botão
        self.assertGreater(bar.clock.x, devices_x - 30)


# =============================================================== a aplicação


class TestActionButtonsAndUnsaved(tg.GuiCase):
    def open_builder(self):
        self.pick("Construtor de treinos")
        self.pick("Novo treino")
        b = self.screen()
        self.assertIsInstance(b, bs.BlockBuilder)
        return b

    def test_save_is_a_bottom_right_button(self):
        b = self.open_builder()
        buttons = [i for i in b.list.items if i.button]
        self.assertEqual(buttons[-1].label.split()[0], "Guardar")
        self.assertTrue(buttons[-1].primary)
        self.app._on_draw()
        left = b.list.buttons_left
        self.assertIsNotNone(left)
        self.assertGreater(left, b.back_button.bg.x + b.back_button.bg.width)
        # o rodapé não passa por baixo dos botões
        self.assertLess(b.chrome.footer.x + len(b.chrome.footer.text) * 6.4, left)

    def test_back_with_changes_asks_and_cancel_stays(self):
        b = self.open_builder()
        b.add_block("Z2")
        self.press(key.ESCAPE)
        pop = self.screen()
        self.assertIsInstance(pop, app_mod.ConfirmScreen)
        self.assertEqual([i.label for i in pop.list.items],
                         ["Sair sem gravar", "Cancelar", "Guardar"])
        self.pick("Cancelar")
        self.assertIs(self.screen(), b)
        self.assertTrue(b.dirty)

    def test_leave_without_saving(self):
        n = len(self.app.db.workouts())
        b = self.open_builder()
        b.add_block("Z3")
        self.press(key.ESCAPE)
        self.pick("Sair sem gravar")
        self.assertIsInstance(self.screen(), app_mod.MainMenu)
        self.assertEqual(len(self.app.db.workouts()), n)

    def test_save_from_the_popup_saves_and_leaves(self):
        n = len(self.app.db.workouts())
        b = self.open_builder()
        b.add_block("Z4")
        self.press(key.ESCAPE)
        self.pick("Guardar")
        self.assertIsInstance(self.screen(), app_mod.MainMenu)
        self.assertEqual(len(self.app.db.workouts()), n + 1)

    def test_ctrl_s_saves_any_editor(self):
        self.pick("Definições")
        self.app._on_key_press(key.S, key.MOD_CTRL)          # nada para guardar aqui
        self.assertIn("nada para guardar", self.app._message.lower())
        self.press(key.ESCAPE)
        b = self.open_builder()
        b.add_block("Z2")
        self.app._on_key_press(key.S, key.MOD_CTRL)
        self.assertFalse(b.dirty)
        self.press(key.ESCAPE)                               # já está guardado: sai logo
        self.assertIsInstance(self.screen(), app_mod.MainMenu)

    def test_no_changes_no_question(self):
        self.open_builder()
        self.press(key.ESCAPE)
        self.assertIsInstance(self.screen(), app_mod.MainMenu)


class TestTrainTabEverywhere(tg.GuiCase):
    def test_same_order_in_every_sport(self):
        self.press(key.ESCAPE)
        for name in ("Ciclismo", "Remo", "Corrida", "Natação", "Ginásio"):
            self.pick(name)
            labels = [i.label for i in self.screen().list.items]
            self.assertEqual(labels[:4], ["Sessão de treino", "Challenge", "Desafios",
                                          "Testes"], name)
            self.press(key.ESCAPE)

    def test_cycling_challenge_has_no_games_header(self):
        self.pick("Challenge")
        labels = [i.label for i in self.screen().list.items]
        self.assertFalse(any("Jogos" in x for x in labels))

    def test_running_challenge_runs_a_time_trial(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Challenge")
        menu = self.screen()
        self.assertIsInstance(menu, chs.EnduranceChallengeMenu)
        self.assertIn("5 km contra o relógio", [i.label for i in menu.list.items])
        # os treinos das provas não se misturam com a lista de treinos
        names = [w["name"] for w in en.workouts(self.app.db, "running")]
        self.assertNotIn("5 km contra o relógio", names)
        self.pick("5 km contra o relógio")
        self.pick("Começar")
        ses = self.screen()
        self.assertEqual(ses.engine.workout.name, "5 km contra o relógio")

    def test_gym_challenge_and_session_picker(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Challenge")
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("EMOM 20 min", labels)
        self.assertTrue(any(x.startswith("Surpresa · Força") for x in labels))
        self.press(key.ESCAPE)
        self.pick("Sessão de treino")
        self.assertIsInstance(self.screen(), chs.GymSessionPicker)


class TestChallengesWithDeadline(tg.GuiCase):
    def test_create_a_running_challenge_with_a_deadline(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Desafios")
        self.pick("Novo desafio")
        scr = self.screen()
        self.assertIsInstance(scr, app_mod.ChallengeCreate)
        self.select("Objetivo")
        self.type("50")
        self.select("Data limite")
        self.press(key.RIGHT)                                 # amanhã
        for _ in range(4):
            self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)  # + 4 semanas
        self.assertEqual(scr.deadline, date.today() + timedelta(days=29))
        self.pick("Criar")
        ch = self.app.db.challenges("running")[-1]
        self.assertEqual(ch["deadline"], (date.today() + timedelta(days=29)).isoformat())
        self.assertEqual(ch["target"], 50_000)
        self.assertNotIn(ch["id"], [c["id"] for c in self.app.db.challenges()])  # não é do ciclismo
        lst = self.screen()
        row = next(i for i in lst.list.items if i.data == ch["id"])
        self.assertIn("faltam 29 dias", row.detail)

    def test_progress_comes_from_the_history(self):
        db = self.app.db
        cid = db.create_challenge("Correr 10 km", "distance_m", 10_000, "km", sport="running")
        ch = next(c for c in db.challenges("running") if c["id"] == cid)
        en.ensure(db)
        later = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        for i, dist in enumerate((6000, 5000)):
            db.conn.execute(
                "INSERT INTO endurance_sessions(id, sport, name, status, started_at, ended_at,"
                " moving_s, distance_m) VALUES (?,?,?,?,?,?,?,?)",
                (f"s{i}", "running", "Corrida", "completed", later, later, 1800, dist))
        db.conn.commit()
        att = sc.refresh(db, ch)
        self.assertGreaterEqual(att["progress"], 10_000)
        self.assertIsNotNone(att.get("completed_at"))
        self.assertEqual(len(db.challenge_leaderboard(cid)), 1)

    def test_remaining_text(self):
        now = datetime(2026, 10, 31, 20, 0)
        self.assertEqual(sc.remaining_text({"deadline": "2026-11-02"}, now),
                         "faltam 2 dias e 3 h")
        self.assertIn("termina hoje", sc.remaining_text({"deadline": "2026-10-31"}, now))
        self.assertIn("terminou", sc.remaining_text({"deadline": "2026-10-30"}, now))
        self.assertEqual(sc.remaining_text({"deadline": None}, now), "")
        self.assertTrue(sc.expired({"deadline": "2026-10-30"}, now))


class TestDevicesMenu(tg.GuiCase):
    def test_labels_and_rowing_machine(self):
        self.pick("Dispositivos")
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("Procurar Bluetooth", labels)
        self.assertNotIn("Fechar", labels)                    # fica só o botão
        self.assertFalse(any(x.startswith("Máquina de remo…") for x in labels))
        self.pick("Máquina de remo simulada")
        self.assertIsInstance(self.app.rower, rio.SimulatedRower)
        labels = [i.label for i in self.screen().list.items]
        self.assertIn(f"✓ {self.app.rower.name}", labels)
        self.assertIsNotNone(self.screen().back_button)

    def test_calibrate_needs_a_trainer(self):
        for src in list(self.app.hub.sources):
            self.app.hub.remove_source(getattr(src, "device_id", ""))
        self.pick("Dispositivos")
        cal = next(i for i in self.screen().list.items if "Calibrar" in i.label)
        self.assertFalse(cal.enabled)


class TestSettingsTabs(tg.GuiCase):
    def test_tabs_and_athlete_rowing_ftp(self):
        self.pick("Definições")
        scr = self.screen()
        self.assertEqual(scr.tab_labels(), ["Atleta", "Sessões", "Ecrã e idioma", "Ligações",
                                            "Sincronização", "Atalhos de teclado"])
        self.assertIn("FTP do remo", [i.label for i in scr.list.items])
        scr.tab_named("Sessões")
        self.assertFalse(any("Resistência extra" in i.label or "resistência" in i.label.lower()
                             for i in scr.list.items))

    def test_shortcuts_fill_the_screen(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Atalhos")
        self.app._on_draw()
        texts = [lab.text for lab in scr.keys_view.labels if lab.text]
        for k in ("Ctrl+S", "L", "P", "F10", "Guardar", "Marcar volta (lap)"):
            self.assertIn(k, texts)
        x, top, width, bottom = scr.keys_view.geometry
        for lab in scr.keys_view.labels:
            if lab.text:
                self.assertGreaterEqual(lab.y, bottom, lab.text)
                self.assertLessEqual(lab.x, x + width)

    def test_metrics_are_a_grid(self):
        self.pick("Definições")
        self.pick("Métricas")
        scr = self.screen()
        self.assertIsInstance(scr, app_mod.MetricsCatalogScreen)
        n = len(scr.list.items)
        self.assertEqual(len(scr.grid.rects), n)
        x, top, width, bottom = scr.grid.geometry
        for cx, cy, tw, th in scr.grid.rects:
            self.assertGreaterEqual(cy, bottom - 1)
            self.assertLessEqual(cx + tw, x + width + 1)
        self.assertGreater(scr.grid.cols, 1)
        first = scr.list.items[0].label
        self.press(key.ENTER)                                 # liga/desliga
        self.assertNotEqual(scr.list.items[0].label, first)
        self.press(key.DOWN)
        self.assertEqual(scr.list.index, scr.grid.cols)


# ================================================================ GarminDB


def make_activities(folder: Path, metric: bool) -> None:
    con = sqlite3.connect(folder / "garmin_activities.db")
    con.executescript("""
    CREATE TABLE activities (activity_id TEXT PRIMARY KEY, name TEXT, sport TEXT,
      sub_sport TEXT, start_time DATETIME, elapsed_time TIME, moving_time TIME,
      distance FLOAT, ascent FLOAT, avg_hr INT, max_hr INT, calories INT,
      training_load FLOAT);
    INSERT INTO activities VALUES ('101', 'Volta à serra', 'cycling', 'road',
      '2026-10-20 08:00:00', '02:00:00.000000', '01:50:00.000000', 31.0686, 2000, 140,
      170, 1500, 120);
    INSERT INTO activities VALUES ('102', 'Remo', 'fitness_equipment', 'indoor_rowing',
      '2026-10-25 18:00:00', '00:30:00.000000', '00:30:00.000000', 3.10686, 0, 150, 172,
      400, 60);
    INSERT INTO activities VALUES ('103', 'Força', 'training', 'strength_training',
      '2026-10-27 18:00:00', '00:45:00.000000', '00:40:00.000000', NULL, NULL, 110, 150,
      300, 30);
    """)
    con.commit()
    con.close()


class TestGarminSync(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.folder = tg.Path(self.tmp / "HealthData" / "DBs")
        from tests.test_connect import make_garmindb
        make_garmindb(self.folder)
        make_activities(self.folder, metric=False)
        self.db.set("garmindb_dir", str(self.folder))
        self.cfg_dir = self.tmp / ".GarminDb"
        self.cfg_dir.mkdir()
        (self.cfg_dir / "GarminConnectConfig.json").write_text(json.dumps({
            "credentials": {"user": "x", "password": "segredo"},
            "data": {"weight_start_date": "12/31/2019", "sleep_start_date": "12/31/2019",
                     "rhr_start_date": "12/31/2019", "hrv_start_date": "12/31/2019",
                     "monitoring_start_date": "12/31/2019"},
            "settings": {"metric": False}}))
        self.db.set("garmindb_config_dir", str(self.cfg_dir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_command_follows_the_options(self):
        o = gsync.Options()
        cmd = gsync.build_command("garmindb_cli.py", o)
        self.assertEqual(cmd, ["garmindb_cli.py", "--all", "--download", "--import",
                               "--analyze", "--latest"])
        o = gsync.Options(period="all", stats=["sleep", "weight"], analyze=False,
                          overwrite=True, copy=True)
        cmd = gsync.build_command("garmindb_cli.py", o, self.cfg_dir)
        self.assertEqual(cmd, ["garmindb_cli.py", "-f", str(self.cfg_dir), "--sleep",
                               "--weight", "--copy", "--download", "--import", "--overwrite"])
        self.assertNotIn("--latest", cmd)

    def test_range_writes_the_config_dates_with_a_backup(self):
        o = gsync.Options(period="range", start="2026-01-15", end="2026-03-01",
                          stats=["sleep", "activities"])
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli.py"
        try:
            ok, msg, rep = gsync.sync(self.db, o, runner=runner)
        finally:
            importers.garmindb_cli = orig
        self.assertTrue(ok, msg)
        cfg = json.loads((self.cfg_dir / "GarminConnectConfig.json").read_text())
        self.assertEqual(cfg["data"]["sleep_start_date"], "01/15/2026")
        self.assertEqual(cfg["data"]["sleep_end_date"], "03/01/2026")
        self.assertEqual(cfg["data"]["weight_start_date"], "12/31/2019")   # não escolhido
        self.assertEqual(cfg["credentials"]["password"], "segredo")        # intacto
        self.assertTrue((self.cfg_dir / "GarminConnectConfig.json.bak").exists())
        self.assertNotIn("--latest", calls[0])
        self.assertNotIn("segredo", " ".join(calls[0]))
        self.assertEqual(rep["since"], "2026-01-15")
        self.assertEqual(rep["activities"], 0)                # nenhuma no intervalo

    def test_import_activities_converts_miles(self):
        rep = gsync.import_activities(self.db, self.folder)
        self.assertEqual((rep["activities"], rep["new"]), (3, 3))
        acts = {a["id"]: a for a in gsync.activities(self.db)}
        ride = acts["garmin:101"]
        self.assertEqual(ride["sport"], "cycling")
        self.assertAlmostEqual(ride["distance_m"], 50_000, delta=5)        # 31,07 mi
        self.assertAlmostEqual(ride["ascent_m"], 609.6, delta=0.5)         # 2000 pés
        self.assertEqual(ride["moving_s"], 6600)
        self.assertEqual(acts["garmin:102"]["sport"], "rowing")
        self.assertEqual(acts["garmin:103"]["sport"], "gym")
        again = gsync.import_activities(self.db, self.folder)
        self.assertEqual(again["new"], 0)                     # não duplica

    def test_sync_without_running_the_source(self):
        ok, msg, rep = gsync.sync(self.db, gsync.Options(period="all"), run_source=False)
        self.assertTrue(ok, msg)
        self.assertEqual(rep["days"], 2)
        self.assertEqual(rep["activities"], 3)
        self.assertTrue(self.db.get("garmindb_last_sync"))
        # «só o mais recente» depois: importa só a partir de ontem
        since, until = gsync.import_range(self.db, gsync.Options(period="latest"))
        self.assertEqual(since, (date.today() - timedelta(days=1)).isoformat())

    def test_maintenance_commands(self):
        calls = []

        def runner(cmd, **kw):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli.py"
        try:
            gsync.maintenance(self.db, "backup", runner=runner)
            gsync.maintenance(self.db, "rebuild", runner=runner)
        finally:
            importers.garmindb_cli = orig
        self.assertEqual(calls[0][-1], "--backup")
        self.assertEqual(calls[1][-1], "--rebuild_db")


class TestSyncTabGui(tg.GuiCase):
    def test_tab_options_and_history(self):
        folder = Path(self.tmp) / "g"
        from tests.test_connect import make_garmindb
        make_garmindb(folder)
        make_activities(folder, metric=False)
        self.app.db.set("garmindb_dir", str(folder))
        self.pick("Definições")
        self.pick("Sincronização")
        scr = self.screen()
        self.select("Período")
        self.press(key.RIGHT, key.RIGHT)                      # mais recente → tudo → intervalo
        self.assertEqual(gsync.load_options(self.app.db).period, "range")
        self.assertIn("Desde", [i.label for i in scr.list.items])
        self.select("Desde")
        self.press(key.LEFT)
        o = gsync.load_options(self.app.db)
        self.assertEqual(o.start, (date.today() - timedelta(days=91)).isoformat())
        self.pick("HRV")                                     # tira a HRV
        self.assertNotIn("hrv", gsync.load_options(self.app.db).stats)
        cmd = next(i for i in scr.list.items if i.label == "Comando").detail
        self.assertIn("--sleep", cmd)
        self.assertNotIn("--hrv", cmd)
        self.select("Período")
        self.press(key.RIGHT)                                 # volta a «só o mais recente»
        self.pick("Só importar")
        self.assertEqual(scr.sync.last_report["activities"], 3)
        self.press(key.ESCAPE)
        self.pick("Histórico")
        labels = [i.label for i in self.screen().list.items]
        self.assertTrue(any("Volta à serra" in x for x in labels))


# ================================================================ sessões


class TestLapsInOnePlace(tg.GuiCase):
    def test_rowing_laps_panel(self):
        self.app.set_rower(rio.SimulatedRower())
        ses = rs.RowingSessionScreen(self.app)
        self.app.push(ses)
        for _ in range(80):
            ses.update(0.5)
        self.press(key.L)
        for _ in range(20):
            ses.update(0.5)
        panel = ses.laps_panel
        self.assertEqual(panel.title.text, "Volta 2")
        self.assertTrue(panel.prev[0].text.startswith("1."))
        caps = [c.text for c, _v in panel.cells]
        self.assertIn("RITMO /500 M", caps)
        x, top, width, bottom = panel.geometry
        self.assertGreater(x, ses.cells[3][0].x + ses.cells[3][0].width)   # ao lado dos campos

    def test_running_laps_panel(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Começar")
        ses = self.screen()
        self.press(key.SPACE)
        for _ in range(30):
            ses.update(1.0)
        self.press(key.L)
        ses.update(1.0)
        self.assertEqual(ses.laps_panel.title.text, "Volta 2")
        self.assertTrue(ses.laps_panel.prev[0].text.startswith("1."))


class TestZoneColours(tg.GuiCase):
    def test_hr_zone_bars_use_the_builder_colours(self):
        from velo.gfx.hud import zone_color
        from velo.core import intensity as it
        from velo.ui import stats_screens as sts
        scr = sts.SportStatsScreen(self.app, "running")
        self.app.push(scr)
        scr.set_tab(4)                                        # Zonas de FC
        self.assertEqual([tuple(zone_color(i + 1, "hr")) for i in range(5)],
                         [tuple(c) for c in it.ZONE_COLORS[:5]])


class TestTestsShowBlocks(tg.GuiCase):
    def test_ftp_test_blocks(self):
        ft.seed(self.app.db)
        x = next(t_ for t_ in ft.tests(self.app.db, "cycling") if t_["protocol"] == "20min")
        scr = hs.TestDetail(self.app, x["id"])
        self.app.push(scr)
        self.assertIsNotNone(scr.brief)
        self.assertEqual(len(scr.brief.raw_blocks), 5)
        self.assertIsNone(scr.brief.raw_blocks[3].lo)         # 20 min no máximo: livre
        self.app._on_draw()
        self.assertFalse(any("Desativar" in i.label for i in scr.list.items))

    def test_timed_and_untimed_tests(self):
        ft.seed(self.app.db)
        timed = next((t_ for t_ in ft.tests(self.app.db, "running") if t_["duration_s"]
                      and not t_["protocol"]), None)
        if timed is not None:
            self.assertEqual(len(ft.test_blocks(self.app.db, timed)), 1)
        reps = {"protocol": None, "duration_s": 0, "name": "Flexões"}
        self.assertEqual(ft.test_blocks(self.app.db, reps), [])


class TestNoArchive(tg.GuiCase):
    def test_exercise_editor_has_no_archive_and_hidden_come_back(self):
        from velo.ui import hub_screens as hub
        eid = gym.exercises(self.app.db, "strength")[0]["id"]
        scr = hub.ExerciseEditor(self.app, eid, "strength")
        self.app.push(scr)
        self.assertFalse(any("Arquivar" in i.label for i in scr.list.items))
        gym.archive_exercise(self.app.db, eid)
        self.app.db.set("migr_unarchive", False)
        self.app._unarchive_once()
        self.assertIn(eid, [e["id"] for e in gym.exercises(self.app.db, "strength")])


class TestRowingRecords(tg.GuiCase):
    def test_each_record_shows_its_session(self):
        self.app.set_rower(rio.SimulatedRower())
        ses = rs.RowingSessionScreen(self.app)
        self.app.push(ses)
        for _ in range(240):
            ses.update(0.5)
        ses._finish()
        self.app.reset_to_menu(rs.RowingMenu) if any(
            isinstance(s, rs.RowingMenu) for s in self.app.stack) else None
        menu = rs.RowingMenu(self.app)
        self.app.push(menu)
        menu.tab_named("Estatísticas")
        rec = next(i for i in menu.list.items if i.label == "Maior distância")
        self.assertIn("em ", rec.detail)
        rec.action()
        self.assertIsInstance(self.screen(), rs.RowSessionDetail)


if __name__ == "__main__":
    unittest.main()
