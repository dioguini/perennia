"""Testes da interface, contra uma pyglet falsa.

Percorrem a aplicação como um utilizador: abrem cada ecrã, movem a seleção,
carregam em Enter, importam um GPX, correm uma sessão com o mundo 3D
construído, terminam e chegam ao resumo. Nada disto desenha pixels — mas
apanha nomes errados, atributos inexistentes e contas impossíveis, que é o
que faria a janela fechar-se na cara de quem instala.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub

pyglet_stub.install()

from pyglet.window import key  # noqa: E402  (vem da pyglet falsa)

from velo.core import climbs as climbs_mod  # noqa: E402
from velo.core import gpx  # noqa: E402
from velo.core.db import Athlete  # noqa: E402
from velo.core.i18n import PT, set_language  # noqa: E402
from velo.gfx.world import PRESETS, World  # noqa: E402
from velo.io.sim import SimulatedTrainer  # noqa: E402
from velo.ui import app as app_mod  # noqa: E402

GPX = Path(__file__).parent / "teste.gpx"


class GuiCase(unittest.TestCase):
    """Base: uma aplicação com uma rota já importada e trainer simulado."""

    def setUp(self):
        set_language(PT)
        pyglet_stub.reset()
        self.tmp = tempfile.mkdtemp()
        self.app = app_mod.App(data_dir=Path(self.tmp), width=1280, height=760)
        # o feedback no fim das sessões tem testes próprios (test_perennia)
        self.app.db.set("ask_feedback", False)
        self.app.db.save_athlete(Athlete(name="Daniel", birth_year=1993,
                                         weight_kg=72.0, ftp_w=250, lthr=165))
        _, raw = gpx.parse_gpx(GPX)
        self.points = gpx.resample(raw)
        self.route_id = self.app.db.insert_route(
            "Serra de Teste", self.points, climbs_mod.detect(self.points))
        self.app.hub.add_source(SimulatedTrainer(base_power=210),
                                role="trainer", is_trainer=True)
        self.app.stack[0].enter()
        self.pick("Ciclismo")                # do ecrã inicial para o menu do ciclismo

    def tearDown(self):
        try:
            self.app.shutdown()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # auxiliares -----------------------------------------------------------

    def screen(self):
        return self.app.current

    def press(self, *symbols: int) -> None:
        for s in symbols:
            self.app._on_key_press(s, 0)

    def labels(self) -> list[str]:
        return [lab.text for lab in pyglet_stub.created["labels"] if lab.text]

    def find(self, text: str) -> bool:
        """Seleciona a linha cujo rótulo contém `text`; procura também nos outros
        separadores do ecrã (como quem carrega em Tab) e, para «Definições» e
        «Dispositivos», usa os botões da faixa do topo."""
        scr = self.screen()
        view = scr.list
        for i, item in enumerate(view.items):
            if text.lower() in item.label.lower():
                view.index = i
                view._sync()
                return True
        if scr.tabs is not None:
            start = scr.tab
            for k in range(1, len(scr.tab_labels())):
                scr.set_tab(start + k)
                for i, item in enumerate(scr.list.items):
                    if text.lower() in item.label.lower():
                        scr.list.index = i
                        scr.list._sync()
                        return True
            scr.set_tab(start)
        return False

    def pick(self, text: str) -> None:
        """Seleciona a linha cujo rótulo contém `text` e ativa-a."""
        if self.find(text):
            self.screen().list.activate()
            return
        scr = self.screen()
        if scr.tabs is not None and scr.tab_named(text):
            return                       # o nome de um separador: abre-o (como Tab)
        top = {"definições": self.app.open_settings, "settings": self.app.open_settings,
               "dispositivos": self.app.open_devices, "devices": self.app.open_devices}
        if text.lower() in top:
            top[text.lower()]()
            return
        self.fail(f"não encontrei a linha «{text}» em "
                  f"{[i.label for i in self.screen().list.items]}")

    def select(self, text: str) -> None:
        """Seleciona a linha sem a ativar (também noutros separadores)."""
        if not self.find(text):
            self.fail(f"não encontrei a linha «{text}»")

    def type(self, text: str) -> None:
        """Como a pyglet: cada tecla dá on_key_press e depois on_text."""
        for ch in text:
            symbol = {"j": key.J, "k": key.K, " ": key.SPACE}.get(ch.lower(), 0)
            if symbol:
                self.app._on_key_press(symbol, 0)
            self.app._on_text(ch)

    def board_texts(self) -> list[str]:
        panel = self.screen().board_panel
        self.assertIsNotNone(panel, "este ecrã não tem classificação")
        self.app._on_draw()
        out = [panel.title.text, panel.subtitle.text, panel.empty.text]
        for rank, name, value in panel._rows:
            out += [rank.text, name.text, value.text]
        return [x for x in out if x]


class TestShell(GuiCase):
    def test_window_and_menu_exist(self):
        self.assertTrue(self.app.window.caption.startswith("Perennia "))
        self.assertIsInstance(self.screen(), app_mod.MainMenu)
        labels = self.labels()
        for expected in ("Sessão de treino", "Lista de treinos", "Desafios", "Estatísticas",
                         "Construtor de treinos", "Histórico",
                         "Dispositivos", "Definições", "Desligar"):
            self.assertIn(expected, labels, f"falta «{expected}» no menu")

    def test_draw_does_not_raise(self):
        self.app._on_draw()
        self.assertGreater(self.app.window.cleared, 0)

    def test_arrows_move_the_selection(self):
        view = self.screen().list
        self.assertEqual(view.index, 0)
        self.press(key.DOWN, key.DOWN)
        self.assertEqual(view.index, 2)
        self.press(key.UP)
        self.assertEqual(view.index, 1)

    def test_selection_wraps_around(self):
        view = self.screen().list
        self.press(key.UP)
        self.assertEqual(view.index, len(view.items) - 1)

    def test_escape_goes_home_and_home_stays(self):
        self.press(key.ESCAPE)                       # do ciclismo para o início
        self.assertIsInstance(self.screen(), app_mod.HomeScreen)
        self.press(key.ESCAPE)                       # no início, Esc não sai
        self.assertIsInstance(self.screen(), app_mod.HomeScreen)
        self.assertEqual(len(self.app.stack), 1)

    def test_resize_relayouts_every_screen(self):
        self.pick("Definições")
        self.app._on_resize(1920, 1080)
        self.app._on_draw()
        self.assertEqual(self.screen().list.width, 1920 - 96)

    def test_mouse_click_activates_a_row(self):
        view = self.screen().list
        row_y = view.y                      # primeira linha
        self.app._on_mouse_press(view.x + 10, row_y, 1, 0)
        self.assertIsInstance(self.screen(), app_mod.RouteLibrary)

    def test_every_screen_opens_updates_and_draws(self):
        for entry in ("Sessão de treino", "Importar treino", "Testes", "Challenge", "Novo treino",
                      "Desafios", "Gráficos e análise", "Dispositivos", "Definições"):
            with self.subTest(ecra=entry):
                self.app.reset_to_menu()
                self.pick(entry)
                screen = self.screen()
                self.assertNotIsInstance(screen, app_mod.MainMenu,
                                         f"«{entry}» não abriu nada")
                screen.update(0.1)
                self.app._on_draw()
                self.press(key.DOWN, key.UP)
                self.app._on_resize(1024, 700)
                self.app._on_draw()


class TestLibraryAndImport(GuiCase):
    def test_route_appears_with_distance_and_climbs(self):
        self.pick("Sessão de treino")
        labels = self.labels()
        self.assertTrue(any("Serra de Teste" in x for x in labels))
        self.assertTrue(any("5.9" in x or "6.0" in x for x in labels),
                        f"distância não aparece: {labels}")

    def test_import_a_gpx_from_the_picker(self):
        before = len(self.app.db.routes())
        self.pick("Sessão de treino")
        self.pick("Importar")
        self.assertIsInstance(self.screen(), app_mod.GpxPicker)
        # o ficheiro de exemplo está na pasta de testes; aponta o seletor a ela
        picker = self.screen()
        picker._import(GPX)
        self.assertEqual(len(self.app.db.routes()), before + 1)
        self.assertIsInstance(self.screen(), app_mod.RouteDetail)

    def test_import_of_a_broken_file_shows_an_error(self):
        self.pick("Sessão de treino")
        self.pick("Importar")
        bad = Path(self.tmp) / "mau.gpx"
        bad.write_text("isto não é xml")
        self.screen()._import(bad)
        self.assertIn("Erro", self.app._message)

    def test_route_detail_lists_the_climb_and_its_board(self):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.assertIsInstance(self.screen(), app_mod.RouteDetail)
        labels = self.labels()
        self.assertTrue(any("Subida 1" in x for x in labels), labels)

    def test_favourite_and_delete_keys(self):
        self.pick("Sessão de treino")
        view = self.screen().list
        view.index = 1                      # a rota
        view._sync()
        self.press(key.F)
        self.assertEqual(self.app.db.route(self.route_id)["favorite"], 1)
        view = self.screen().list
        view.index = 1
        view._sync()
        self.press(key.DELETE)
        self.assertEqual(len(self.app.db.routes()), 0)


class TestSettingsScreen(GuiCase):
    def test_arrows_adjust_values(self):
        self.pick("Definições")
        before = self.app.db.athlete().ftp_w
        self.pick("FTP")                    # seleciona a linha
        self.press(key.RIGHT, key.RIGHT)
        self.assertEqual(self.app.db.athlete().ftp_w, before + 10)
        self.press(key.LEFT)
        self.assertEqual(self.app.db.athlete().ftp_w, before + 5)

    def test_weight_steps_by_a_tenth_and_shift_by_one(self):
        self.pick("Definições")
        self.pick("Peso")                   # 72,0 kg
        self.press(key.RIGHT, key.RIGHT, key.RIGHT)
        self.assertAlmostEqual(self.app.db.athlete().weight_kg, 72.3, places=6)
        self.press(key.LEFT)
        self.assertAlmostEqual(self.app.db.athlete().weight_kg, 72.2, places=6)
        self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)
        self.assertAlmostEqual(self.app.db.athlete().weight_kg, 73.2, places=6)
        for _ in range(20):                 # sem deriva de vírgula flutuante
            self.press(key.RIGHT)
        self.assertAlmostEqual(self.app.db.athlete().weight_kg, 75.2, places=6)
        self.assertTrue(any("75.2 kg" in x for x in self.labels()))

    def test_shift_does_not_multiply_other_fields(self):
        self.pick("Definições")
        before = self.app.db.athlete().ftp_w
        self.pick("FTP")
        self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)
        self.assertEqual(self.app.db.athlete().ftp_w, before + 5)

    def test_name_is_typed_on_the_keyboard(self):
        self.pick("Definições")
        self.select("Nome")
        for _ in range(10):
            self.press(key.BACKSPACE)
        self.assertEqual(self.app.db.athlete().name, "")
        self.type("Jose Kim")
        self.assertEqual(self.app.db.athlete().name, "Jose Kim")
        self.assertIsInstance(self.screen(), app_mod.SettingsScreen)   # não saiu

    def test_auto_pause_toggle(self):
        self.pick("Definições")
        self.pick("Pausa automática")
        self.assertFalse(self.app.db.get("auto_pause"))
        self.pick("Pausa automática")
        self.assertTrue(self.app.db.get("auto_pause"))

    def test_resolution_cycles_and_is_remembered(self):
        self.pick("Definições")
        self.select("Resolução")
        self.assertIn("Janela 1280×760", self.screen().list.selected.value)
        self.pick("Resolução")                      # → 1366×768
        self.assertEqual((self.app.window.width, self.app.window.height), (1366, 768))
        self.pick("Resolução")                      # → 1600×900
        self.pick("Resolução")                      # → 1920×1080
        self.pick("Resolução")                      # → 2560×1440 (o ecrã falso é 2560×1440)
        self.pick("Resolução")                      # 3840×2160 não cabe → ecrã inteiro
        self.assertTrue(self.app.window.fullscreen)
        self.assertIn("Ecrã inteiro (2560×1440)", self.screen().list.selected.value)
        saved = self.app.db.get("display")
        self.assertTrue(saved["fullscreen"])
        self.pick("Resolução")                      # volta ao início, em janela
        self.assertFalse(self.app.window.fullscreen)
        self.assertEqual((self.app.window.width, self.app.window.height), (1280, 720))
        self.assertEqual(self.app.db.get("display"),
                         {"fullscreen": False, "w": 1280, "h": 720})

    def test_lists_grow_and_shrink_with_the_window(self):
        menu = self.app.stack[1]                     # o menu do ciclismo
        self.app.set_display(True)                  # 2560×1440
        self.assertEqual(len(menu.list._rows), menu.list.visible_rows)
        self.assertGreater(menu.list.visible_rows, 10)
        self.app.set_display(False, 1024, 640)
        self.assertEqual(len(menu.list._rows), menu.list.visible_rows)
        self.assertEqual(menu.list.visible_rows, 9)        # os separadores ocupam uma linha

    def test_next_start_uses_the_last_choice(self):
        self.app.set_display(False, 1600, 900)
        self.app.shutdown()
        again = app_mod.App(data_dir=Path(self.tmp))          # sem tamanho na linha de comandos
        try:
            self.assertEqual((again.window.width, again.window.height), (1600, 900))
            self.assertFalse(again.window.fullscreen)
        finally:
            again.shutdown()
        forced = app_mod.App(data_dir=Path(self.tmp), fullscreen=True)
        try:
            self.assertTrue(forced.window.fullscreen)          # --fullscreen manda
        finally:
            forced.shutdown()

    def test_window_asks_for_antialiasing_and_falls_back(self):
        self.assertEqual(self.app.msaa_samples, 4)
        real = app_mod.pyglet.window.Window

        class Picky(real):
            def __init__(self, config=None, **kw):
                if config is not None and config.kw.get("samples", 0) > 2:
                    raise RuntimeError("NoSuchConfigException")
                super().__init__(**kw)

        app_mod.pyglet.window.Window = Picky
        try:
            win, samples = app_mod._make_window(width=1280, height=720)
            self.assertEqual(samples, 2)
        finally:
            app_mod.pyglet.window.Window = real

    def test_profile_bars_follow_the_width(self):
        hud = app_mod.Hud(self.app.window, self.app.db, self.app.db.athlete())
        _, _, prof_w, _ = hud._profile_geometry
        self.assertEqual(len(hud._profile_bars), prof_w // 2)
        hud.layout(2560, 1440)
        _, _, prof_w2, _ = hud._profile_geometry
        self.assertGreater(prof_w2, prof_w)                 # em ecrãs grandes cresce
        self.assertEqual(len(hud._profile_bars), prof_w2 // 2)

    def test_ride_hud_panels_do_not_collide(self):
        """Gauges/plan (left), board/laps (right), centre panels and the bottom
        profiles must not overlap, even on small screens."""
        hud = app_mod.Hud(self.app.window, self.app.db, self.app.db.athlete())
        hud.has_workout = True

        def box(r):
            return (r.x, r.y, r.x + r.width, r.y + r.height)

        def hits(a, b):
            return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

        for w, h in ((1024, 640), (1280, 720), (1280, 760), (1920, 1080), (2560, 1440)):
            hud.layout(w, h)
            px, py, pw, ph = hud._profile_geometry
            tx, ty, tw, th = hud._tiz_geometry
            lx, ly, lw, lh = hud._laps_geometry
            left = [box(hud._gauges["power"]["bg"]), box(hud._gauges["hr"]["bg"]),
                    box(hud._plan_bg)]
            right = [(lx, ly, lx + lw, ly + lh)]
            centre = [box(hud._climb_bg), box(hud._chase_bg), box(hud._sign_bg)]
            bottom = [(px, py, px + pw, py + ph), (tx, ty, tx + tw, ty + th)]
            for a in left + right:
                for b in centre + bottom:
                    self.assertFalse(hits(a, b), f"{w}x{h}: {a} × {b}")
            self.assertFalse(hits(bottom[0], bottom[1]), f"{w}x{h}: perfil × zonas")
            for b in centre:
                self.assertFalse(hits(b, bottom[0]), f"{w}x{h}: centro × perfil")

    def test_antialiasing_setting_cycles(self):
        self.pick("Definições")
        self.select("Suavização")
        self.assertEqual(self.screen().list.selected.value, "4×")
        self.pick("Suavização")
        self.assertEqual(self.app.db.get("msaa_samples"), 2)
        self.assertIn("reabrir", self.screen().list.selected.value)
        self.pick("Suavização")
        self.pick("Suavização")
        self.assertEqual(self.app.db.get("msaa_samples"), 4)

    def test_f11_toggles_and_remembers(self):
        self.press(key.F11)
        self.assertTrue(self.app.window.fullscreen)
        self.assertTrue(self.app.db.get("display")["fullscreen"])
        self.press(key.F11)
        self.assertFalse(self.app.window.fullscreen)

    def test_difficulty_and_extra_resistance_are_bounded(self):
        self.pick("Definições")
        self.pick("Sensação")
        for _ in range(60):
            self.press(key.RIGHT)
        self.assertLessEqual(float(self.app.db.get("trainer_difficulty")), 1.5)
        for _ in range(80):
            self.press(key.LEFT)
        self.assertGreaterEqual(float(self.app.db.get("trainer_difficulty")), 0.0)

    def test_units_toggle_changes_the_display(self):
        self.pick("Definições")
        self.pick("Unidades")
        self.assertEqual(self.app.db.get("units"), "imperial")
        self.assertEqual(self.app.units, "imperial")
        self.screen().tab_named("Atleta")           # o peso está no separador do atleta
        self.app._on_draw()
        self.assertTrue(any("lb" in x for x in self.labels()))

    def test_language_toggle_switches_the_menu(self):
        self.pick("Definições")
        self.pick("Idioma")
        self.app.reset_to_menu()
        self.assertIn("Training session", self.labels())
        self.pick("Settings")               # já em inglês
        self.pick("Language")
        self.app.reset_to_menu()
        self.assertIn("Sessão de treino", self.labels())

    def test_render_preset_cycles_through_all_three(self):
        self.pick("Definições")
        seen = set()
        for _ in range(4):
            seen.add(self.app.db.get("render_preset"))
            self.pick("Qualidade")
        self.assertEqual(seen, set(PRESETS))

    def _boxes(self):
        from velo.core import boxes, metrics
        return boxes.load(self.app.db, metrics.REGISTRY)

    def test_boxes_editor_adds_orders_and_limits(self):
        self.pick("Definições")
        self.pick("Caixas do ecrã")
        self.assertIsInstance(self.screen(), app_mod.BoxesScreen)
        labels = [i.label for i in self.screen().list.items]
        self.assertEqual(labels[:6], ["1 · Potência", "2 · Pedalada", "3 · Cardio",
                                      "4 · Distância", "5 · Declive", "6 · Tempo e carga"])
        self.pick("3 · Cardio")                       # hr, hr_zone, avg_hr, pedal_smooth
        editor = self.screen()
        self.assertIsInstance(editor, app_mod.BoxEditor)
        for name in ("Torque médio", "Potência/peso", "Vel. média"):   # 5.ª, 6.ª e 7.ª
            self.pick(name)
        self.assertEqual(len(self._boxes()[2]["metrics"]), 7)
        self.pick("     Torque")                      # cheia: não entra
        self.assertNotIn("torque", self._boxes()[2]["metrics"])
        self.assertIn("7 métricas", self.app._message)
        self.pick("4.  Suavidade E/D")                # tira a 4.ª
        self.pick("     Torque")                      # agora entra, em último
        self.assertEqual(self._boxes()[2]["metrics"][-1], "torque")
        self.select("7.  Torque")
        self.press(key.LEFT, key.LEFT)                # sobe dois lugares
        self.assertEqual(self._boxes()[2]["metrics"][4], "torque")
        self.assertEqual(self.screen().list.selected.label, "5.  Torque")

    def test_metric_catalog_hides_metrics_from_the_editor(self):
        self.pick("Definições")
        self.pick("Métricas disponíveis")
        self.assertIsInstance(self.screen(), app_mod.MetricsCatalogScreen)
        self.pick("Torque médio")                     # desliga
        self.press(key.ESCAPE)
        self.pick("Caixas do ecrã")
        self.pick("1 · Potência")
        labels = [i.label.strip() for i in self.screen().list.items]
        self.assertNotIn("Torque médio", labels)
        self.assertIn("Torque", labels)

    def test_box_can_be_renamed_and_reset(self):
        self.pick("Definições")
        self.pick("Caixas do ecrã")
        self.pick("1 · Potência")
        self.select("Nome")
        for _ in range(len("Potência")):
            self.press(key.BACKSPACE)
        self.type("Watts")
        self.assertEqual(self._boxes()[0]["name"], "Watts")
        self.press(key.ESCAPE)
        self.assertIn("1 · Watts", [i.label for i in self.screen().list.items])
        self.pick("Repor")
        self.assertEqual(self._boxes()[0]["name"], "")

    def test_ride_hud_shows_the_six_boxes(self):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(40):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        hud = ride.hud
        titles = [w["title"].text for w in hud._box_widgets]
        self.assertEqual(len(titles), 6)
        self.assertEqual(titles[0], "1 · Potência")
        first = [v.text for _, v in hud._box_widgets[0]["rows"]]
        self.assertTrue(first[0].endswith("W"))               # potência 3 s
        self.assertTrue(first[2].startswith("Z"))             # zona de potência
        pedal = [v.text for _, v in hud._box_widgets[1]["rows"]]
        self.assertRegex(pedal[1], r"^\d+ / \d+$")            # balanço E/D do simulador
        self.assertRegex(pedal[2], r"^\d+ / \d+ W$")          # potência por perna
        # nada se sobrepõe: caixas acima da zona do meio, perfis abaixo
        boxes_bottom = min(w["bg"].y for w in hud._box_widgets)
        mid_bottom, mid_top = hud._mid_zone
        self.assertGreater(boxes_bottom, mid_top)
        self.assertGreater(mid_bottom, hud._profile_geometry[1] + hud._profile_geometry[3])
        self.assertGreater(hud._profile_geometry[1], hud._strip_geometry[1]
                           + hud._strip_geometry[3])


class TestDeviceScreen(GuiCase):
    def test_lists_the_connected_trainer_with_capabilities(self):
        self.pick("Dispositivos")
        labels = self.labels()
        self.assertTrue(any("Trainer simulado" in x for x in labels), labels)
        self.assertTrue(any("declive" in x for x in labels), labels)

    def test_shows_live_readings(self):
        self.pick("Dispositivos")
        screen = self.screen()
        for _ in range(20):
            screen.update(0.1)
        screen.enter()
        self.assertTrue(any("W" in x for x in self.labels()))

    def test_calibration_entry_is_offered_and_recorded(self):
        self.pick("Dispositivos")
        self.pick("Calibrar")
        self.assertIsNotNone(self.app.db.last_calibration("sim:trainer"))

    def test_scan_without_bleak_explains_itself(self):
        self.pick("Dispositivos")
        self.pick("Procurar")
        screen = self.screen()
        self.assertIn("bleak", screen.note)
        self.assertFalse(screen.scanning)

    def _fake_ant_scan(self, found):
        class Stick:
            closed = False
            def on_broadcast(self, ch, fn): self.handler = fn
            def close_channel(self, ch): pass
            def close(self): self.closed = True
            def send_acknowledged(self, ch, page): pass
        stick = Stick()
        real = app_mod.ant.scan
        app_mod.ant.scan = lambda timeout=10.0, on_event=None: (stick, found)
        self.addCleanup(setattr, app_mod.ant, "scan", real)
        return stick

    def _wait_ant(self, screen):
        import time as _time
        for _ in range(200):
            if screen._ant_result is not None:
                break
            _time.sleep(0.01)
        screen.update(0.1)

    def test_ant_scan_lists_the_pedals_and_hides_the_trainer_twin(self):
        from velo.io import ant
        assioma = ant.AntDiscovered(4321, ant.DEVICE_POWER, "ANT+ Potência #4321")
        twin = ant.AntDiscovered(555, ant.DEVICE_POWER, "ANT+ Potência #555 (do rolo)",
                                 trainer_twin=True)
        fec = ant.AntDiscovered(555, ant.DEVICE_FEC, "ANT+ Rolo FE-C #555")
        stick = self._fake_ant_scan([(0, fec), (1, twin), (3, assioma)])
        self.pick("Dispositivos")
        self.pick("Procurar ANT+")
        screen = self.screen()
        self._wait_ant(screen)
        labels = [i.label for i in screen.list.items]
        self.assertIn("ANT+ Potência #4321", labels)
        self.assertIn("ANT+ Rolo FE-C #555", labels)
        self.assertNotIn("ANT+ Potência #555 (do rolo)", labels)
        self.pick("ANT+ Potência #4321")
        src = [x for x in self.app.hub.sources if x.device_id == assioma.device_id]
        self.assertEqual(len(src), 1)
        self.assertEqual(src[0]._priority["balance"], 21)      # medidor (20) + ANT+ preferido
        self.assertTrue(any("✓ ANT+ Potência #4321" in i.label
                            for i in screen.list.items))
        # os pedais mandam na potência e no balanço, o simulador continua rolo
        src[0]._on_page(3, bytes((0x10, 5, 0x80 | 52, 86, 0, 0, 0xF0, 0x00)))
        r = self.app.hub.reading()
        self.assertEqual(r.power_w, 240)
        self.assertAlmostEqual(r.balance_left, 48.0)
        self.assertEqual(self.app.hub.trainer.device_id, "sim:trainer")

    def test_ant_scan_without_stick_explains_itself(self):
        real = app_mod.ant.scan
        app_mod.ant.scan = lambda timeout=10.0, on_event=None: (None, [])
        self.addCleanup(setattr, app_mod.ant, "scan", real)
        self.pick("Dispositivos")
        self.pick("Procurar ANT+")
        screen = self.screen()
        self._wait_ant(screen)
        self.assertFalse(screen.ant_scanning)
        self.assertTrue("pyusb" in screen.note or "ANT" in screen.note, screen.note)

    def test_connect_my_devices_uses_ant_first(self):
        from velo.io import ant
        pedals = ant.AntDiscovered(4321, ant.DEVICE_POWER, "ANT+ Potência #4321")
        self.app.db.remember_device(pedals.device_id, "ant", pedals.name, ["power_meter"],
                                    0, role="power_meter")
        self._fake_ant_scan([(3, pedals)])
        real = app_mod.ble.bleak_available
        app_mod.ble.bleak_available = lambda: False
        self.addCleanup(setattr, app_mod.ble, "bleak_available", real)
        self.pick("Dispositivos")
        self.pick("Ligar os meus dispositivos")
        self.assertTrue(self.app.auto_running)
        import time as _time
        for _ in range(300):
            if self.app._auto_result is not None:
                break
            _time.sleep(0.01)
        self.app._tick(0.1)
        self.assertFalse(self.app.auto_running)
        ids = [getattr(x, "device_id", "") for x in self.app.hub.sources]
        self.assertIn(pedals.device_id, ids)
        self.screen().update(0.1)
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("✓ ANT+ Potência #4321", labels)
        self.assertIn("Ligados", self.app._message)

    def test_connection_preference_cycles_in_settings(self):
        self.pick("Definições")
        self.pick("Ligação preferida")
        self.assertEqual(self.app.db.get("connection_preference"), "ble_first")
        self.assertEqual(self.app.hub.preferred_transport, "ble")
        for _ in range(3):
            self.pick("Ligação preferida")
        self.assertEqual(self.app.db.get("connection_preference"), "ant_first")
        self.assertEqual(self.app.hub.preferred_transport, "ant")

    def test_adding_and_removing_the_simulator(self):
        self.pick("Dispositivos")
        screen = self.screen()
        screen._disconnect(self.app.hub.sources[0])
        self.assertEqual(len(self.app.hub.sources), 0)
        screen._add_sim()
        self.assertEqual(len(self.app.hub.sources), 1)
        self.assertTrue(self.app.hub.can_control)


class TestRideFlow(GuiCase):
    def _start_ride(self, comparison: bool = False) -> app_mod.RideScreen:
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        setup = self.screen()
        self.assertIsInstance(setup, app_mod.RideSetup)
        if comparison:
            self.pick("Modo de sessão")
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        return ride

    def test_setup_screen_offers_mode_and_render(self):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        labels = self.labels()
        self.assertTrue(any("Sozinho" in x for x in labels), labels)
        self.assertTrue(any("Baixa" in x or "Média" in x or "Alta" in x
                            for x in labels), labels)

    def test_world_is_prebuilt_before_the_ride_starts(self):
        ride = self._start_ride()
        self.assertTrue(ride.preparing)
        self.assertIsNotNone(ride.world)
        self.assertLess(ride.world.build_progress, 1.0)
        # a barra de progresso desenha-se sem rebentar
        ride.draw()
        guard = 0
        while ride.preparing and guard < 5000:
            ride.update(0.016)
            guard += 1
        self.assertFalse(ride.preparing, "o mundo nunca acabou de construir")
        self.assertTrue(ride.world.ready)
        self.assertGreater(len(pyglet_stub.created["vlists"]), 10)

    def test_ride_runs_draws_and_shows_metrics(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(240):                # ~1 minuto a 4 Hz
            self.app.hub.tick(0.25)
            ride.update(0.25)
        ride.draw()
        self.assertGreater(ride.engine.state.dist_m, 50.0)
        self.assertIsNotNone(ride.hud)
        texts = [lab.text for lab in pyglet_stub.created["labels"]]
        self.assertTrue(any("W" in x for x in texts if x), "HUD sem potência")
        self.assertTrue(any("rpm" in x for x in texts if x), "HUD sem cadência")

    def test_camera_follows_the_road(self):
        ride = self._start_ride()
        ride.world.build_all()
        _, eye_start = ride.world.camera(0.0)
        _, eye_later = ride.world.camera(3000.0)
        self.assertNotAlmostEqual(eye_start[2], eye_later[2], delta=100.0)
        # a 3 km está no meio da subida, portanto mais alto
        self.assertGreater(eye_later[1], eye_start[1] + 50.0)

    def test_only_nearby_chunks_are_visible(self):
        ride = self._start_ride()
        ride.world.build_all()
        world = ride.world
        world.visible_chunks(0.0)
        near = sum(1 for c in world.chunks if c.group.visible)
        self.assertGreater(near, 0)
        self.assertLess(near, len(world.chunks),
                        "a 600 m de distância de desenho não pode mostrar 6 km")

    def test_lap_key_during_the_ride(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(120):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.press(key.L)
        self.assertEqual(len(self.app.db.laps(ride.engine.ride_id)), 1)
        ride.update(0.1)
        self.assertTrue(any("Volta" in (lab.text or "")
                            for lab in pyglet_stub.created["labels"]))

    def test_pause_key(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(40):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.press(key.P)
        self.assertTrue(ride.engine.paused)
        distance = ride.engine.state.dist_m
        for _ in range(40):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.assertAlmostEqual(ride.engine.state.dist_m, distance, delta=0.01)
        self.press(key.P)
        self.assertFalse(ride.engine.paused)

    def test_climb_sign_reaches_the_hud(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        guard = 0
        while ride.hud.climb is None and guard < 8000:
            self.app.hub.tick(0.25)
            ride.update(0.25)
            guard += 1
        self.assertIsNotNone(ride.hud.climb, "a subida nunca foi anunciada")
        self.assertIn("end_m", ride.hud.climb)
        ride.draw()
        texts = [lab.text or "" for lab in pyglet_stub.created["labels"]]
        self.assertTrue(any("SUBIDA" in x.upper() for x in texts), "sem placa")

    def test_finish_goes_to_the_summary_with_a_fit_file(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(400):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        summary = self.screen()
        self.assertIsInstance(summary, app_mod.SummaryScreen)
        self.app._on_draw()
        labels = self.labels()
        self.assertTrue(any("Sessão concluída" in x for x in labels), labels)
        fit_path = summary.result.get("fit_path")
        self.assertIsNotNone(fit_path)
        self.assertTrue(Path(fit_path).exists())
        from velo.core import fit
        self.assertGreater(fit.verify(fit_path)["messages"][fit.MSG_RECORD], 50)

    def test_summary_closes_back_to_the_menu(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(80):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        self.pick("Fechar")
        self.assertIsInstance(self.screen(), app_mod.MainMenu)

    def _run(self, ride, seconds: float) -> None:
        for _ in range(int(seconds / 0.25)):
            self.app.hub.tick(0.25)
            ride.update(0.25)

    def test_escape_pauses_instead_of_stopping(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 30)
        self.press(key.ESCAPE)
        self.assertIsInstance(self.screen(), app_mod.RideScreen)   # continua na sessão
        self.assertTrue(ride.engine.paused)
        self.assertFalse(ride.engine.finished)
        ride.update(0.1)
        self.assertTrue(any("F10" in (lab.text or "")
                            for lab in pyglet_stub.created["labels"]))

    def test_laps_panel_is_always_there_and_keeps_past_laps(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 5)
        hud = ride.hud
        self.assertEqual(hud._lap_title.text, "Volta 1 · em curso")   # já antes de L
        labels = [lab.text for lab, _ in hud._lap_rows]
        self.assertEqual(labels, ["TEMPO", "DISTÂNCIA", "POTÊNCIA MÉDIA",
                                  "ZONA DE POTÊNCIA", "CADÊNCIA MÉDIA", "FC MÉDIA"])
        self._run(ride, 55)
        self.press(key.L)
        ride.update(0.1)
        self.assertEqual(hud._lap_title.text, "Volta 2 · em curso")
        self.assertGreater(hud._laps_flash.opacity, 0)              # pisca ao marcar
        self._run(ride, 30)
        values = [v.text for _, v in hud._lap_rows]
        self.assertRegex(values[0], r"^0:(29|30|31)$")              # volta 2, ao vivo
        self.assertTrue(values[1].endswith("km"))
        self.assertTrue(values[2].endswith("W"))
        self.assertTrue(values[3].startswith("Z"))
        self.assertTrue(values[4].endswith("rpm"))
        self.assertTrue(values[5].endswith("bpm"))
        prev = hud._lap_prev[0].text
        self.assertTrue(prev.startswith("1.  1:00"), prev)          # a volta 1 fica
        self.assertIn(" W", prev)
        hud.lap_flash_at -= 10
        ride.update(0.1)
        self.assertEqual(hud._laps_flash.opacity, 0)
        self.assertEqual(hud._lap_title.text, "Volta 2 · em curso")  # não desaparece

    def test_full_route_strip_tracks_the_position(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 30)
        hud = ride.hud
        sx, sy, sw, sh = hud._strip_geometry
        self.assertEqual(sw, self.app.window.width - 32)          # de lado a lado
        self.assertEqual(len(hud._strip_bars), sw // 2)
        pos = ride.engine.state.pos_m / ride.engine.route.total_m
        self.assertAlmostEqual(hud._strip_marker.x, sx + sw * pos - 1, delta=0.5)
        self.assertIn("Rota completa", hud._strip_label.text)
        # as barras não se recalculam a cada frame
        bars = hud._strip_bars
        self._run(ride, 5)
        self.assertIs(hud._strip_bars, bars)

    def test_menus_get_their_own_background_back_after_a_ride(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 10)
        self.app._on_draw()
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        pyglet_stub.calls.clear()
        self.app._on_draw()
        clears = [c for c in pyglet_stub.calls if c[0] == "gl.glClearColor"]
        self.assertTrue(clears, "a cor de fundo não foi reposta")
        r, g, b, _ = clears[-1][1]
        self.assertAlmostEqual(r, app_mod.BG[0] / 255)
        self.assertAlmostEqual(b, app_mod.BG[2] / 255)

    def test_finish_asks_and_no_returns_paused_until_pedalling(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 20)
        self.press(key.F10)
        hud = ride.hud
        self.assertTrue(hud.confirm_visible)
        self.assertEqual(hud._confirm_title.text, "Terminar a sessão?")
        t0 = ride.engine.state.t_s
        self._run(ride, 5)                               # a pergunta não conta tempo
        self.assertEqual(ride.engine.state.t_s, t0)
        no = hud._confirm_no
        self.app._on_mouse_press(int(no.x + 5), int(no.y + 5), 1, 0)
        self.assertFalse(hud.confirm_visible)
        self.assertIsInstance(self.screen(), app_mod.RideScreen)
        self.assertTrue(ride.engine.auto_pause)           # em pausa…
        self.assertFalse(ride.engine.finished)
        self._run(ride, 5)                               # …e pedalar retoma
        self.assertFalse(ride.engine.paused)
        self.assertGreater(ride.engine.state.t_s, t0 + 3)
        self.press(key.F10, key.N)                        # N também diz que não
        self.assertFalse(hud.confirm_visible)
        self.assertFalse(ride.engine.finished)

    def test_resistance_changes_mid_ride(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 5)
        self.assertEqual(ride.engine.difficulty, 1.0)
        self.press(key.MINUS, key.MINUS)                  # «estou fraco»
        self.assertAlmostEqual(ride.engine.difficulty, 0.8)
        ride.update(0.1)
        self.assertIn("80 %", ride.hud._res_label.text)
        b = ride.hud._res_plus
        self.app._on_mouse_press(int(b.x + 5), int(b.y + 5), 1, 0)
        self.assertAlmostEqual(ride.engine.difficulty, 0.9)
        trainer = self.app.hub.sources[0]
        self._run(ride, 2)
        g = ride.engine.state.grade_pct
        self.assertAlmostEqual(trainer.last_grade, g * 0.9, delta=0.25)

    def test_hud_gauges_time_in_zone_and_trace(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 90)
        hud = ride.hud
        g = hud._gauges["power"]
        self.assertRegex(g["title"].text, r"^Z\d · ")
        self.assertIn("W/kg", g["range"].text)
        self.assertIn("W/kg", g["value"].text)
        self.assertGreater(g["fill"].width, 1)
        self.assertRegex(hud._gauges["hr"]["title"].text, r"^Z\d · ")
        hud._slow_at = 0.0
        ride.update(0.1)
        shares = [seg.width for seg in hud._tiz["power"]["segs"]]
        self.assertAlmostEqual(sum(shares), hud._tiz_geometry[2], delta=1.0)
        hud._trace_at = 0.0
        ride.update(0.1)
        drawn = [ln for ln in hud._trace_power if ln.opacity]
        self.assertGreater(len(drawn), 5)                 # a linha de potência existe
        self.assertTrue(any(ln.opacity for ln in hud._trace_hr))
        sx, sy, sw, sh = hud._strip_geometry
        for ln in drawn:
            self.assertTrue(sy <= ln.y <= sy + sh and sy <= ln.y2 <= sy + sh)

    def test_boxes_with_seven_metrics_switch_to_inline_rows(self):
        from velo.core import boxes, metrics as mm
        bx = boxes.load(self.app.db, mm.REGISTRY)
        bx[0]["metrics"] = ["power_3s", "avg_power", "np", "wkg", "avg_wkg", "torque",
                            "avg_torque"]
        boxes.save(self.app.db, bx)
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 30)
        hud = ride.hud
        self.assertFalse(hud._box_stacked)
        values = [v.text for _, v in hud._box_widgets[0]["rows"]]
        self.assertEqual(len([v for v in values if v]), 7)
        self.assertTrue(values[3].endswith("W/kg"))
        self.assertTrue(values[6].endswith("Nm"))
        icons_made = [ic for ic in hud._box_widgets[0]["icons"] if ic is not None]
        self.assertEqual(len(icons_made), 7)
        mid_bottom, mid_top = hud._mid_zone
        self.assertGreater(mid_top - mid_bottom, 150)

    def test_workout_plan_shows_current_and_next_steps(self):
        from velo.core.workout_library import WORKOUTS
        self.app.db.set("workout_lookahead", 2)
        self.pick("Lista de treinos")
        self.pick("VO2máx 5×4")
        self.pick("Começar")                      # o resumo do treino, primeiro
        self.pick("Serra de Teste")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 20)
        hud = ride.hud
        left = [l.text for l, _ in hud._plan_rows]
        right = [r.text for _, r in hud._plan_rows]
        self.assertTrue(left[0].startswith("AGORA"))
        self.assertTrue(left[1].startswith("A seguir"))
        self.assertTrue(left[2].startswith("Depois"))
        self.assertEqual(left[3], "")
        self.assertIn("W", right[1])
        self.assertIn("Passo 1 de", hud._plan_title.text)
        self.press(key.UP)                                # ERG: +5 % de intensidade
        self.assertAlmostEqual(ride.engine.state.intensity, 1.05)

    def test_pause_button_click_toggles_manual_pause(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 10)
        b = ride.hud._pause_bg
        click = (int(b.x + b.width / 2), int(b.y + b.height / 2), 1, 0)
        self.app._on_mouse_press(*click)
        self.assertTrue(ride.engine.manual_pause)
        self._run(ride, 1)
        self.assertIn("PAUSA", ride.hud._paused_label.text)
        self.assertIn("Retomar", ride.hud._pause_label.text)
        t0 = ride.engine.state.t_s
        self._run(ride, 10)
        self.assertEqual(ride.engine.state.t_s, t0)
        self.app._on_mouse_press(*click)
        self.assertFalse(ride.engine.paused)
        self._run(ride, 5)
        self.assertGreater(ride.engine.state.t_s, t0)

    def test_hud_says_to_start_pedalling(self):
        self.app.hub.sources[0].base_power = 0
        self.app.hub.sources[0]._cadence = 0.0
        self.app.hub.sources[0]._power = 0.0
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 5)
        self.assertEqual(ride.engine.state.t_s, 0.0)
        self.assertIn("pedalar", ride.hud._paused_label.text)

    def test_live_board_is_always_on_screen(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 30)
        panel = ride.hud.board_panel
        self.assertTrue(panel.title.text)
        names = [n.text for _, n, _ in panel._rows]
        self.assertIn("Tu", names)

    def test_closing_the_window_twice_is_harmless(self):
        self.app._on_close()                 # a janela fecha…
        self.app.shutdown()                  # …e o main.py volta a chamar
        self.app.db.close()

    def test_closing_the_window_mid_ride_saves_the_fit(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 40)
        ride_id = ride.engine.ride_id
        rides_dir = self.app.rides_dir
        self.app._on_close()
        self.assertTrue(ride.engine.finished)
        fits = list(Path(rides_dir).glob("perennia_*.fit"))
        self.assertEqual(len(fits), 1)
        from velo.core.db import Database
        db = Database(Path(self.tmp) / "perennia.db")
        row = db.conn.execute("SELECT status FROM rides WHERE id = ?", (ride_id,)).fetchone()
        self.assertEqual(row["status"], "completed")
        db.close()

    def test_stop_button_click_finishes_and_saves(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 45)
        hud = ride.hud
        b = hud._stop_bg
        self.app._on_mouse_press(int(b.x + b.width / 2), int(b.y + b.height / 2), 1, 0)
        self.assertTrue(hud.confirm_visible)                 # pergunta primeiro
        yes = hud._confirm_yes
        self.app._on_mouse_press(int(yes.x + 5), int(yes.y + 5), 1, 0)
        summary = self.screen()
        self.assertIsInstance(summary, app_mod.SummaryScreen)
        self.assertTrue(Path(summary.result["fit_path"]).exists())
        # só 45 s de sessão: o .fit tem os dados até ao momento de parar
        from velo.core import fit
        records = fit.verify(summary.result["fit_path"])["messages"][fit.MSG_RECORD]
        self.assertTrue(40 <= records <= 50, records)

    def test_clicking_elsewhere_does_not_stop(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 10)
        self.app._on_mouse_press(5, 5, 1, 0)
        self.assertIsInstance(self.screen(), app_mod.RideScreen)
        self.assertFalse(ride.engine.finished)

    def test_route_loop_keeps_the_session_alive_and_announces_it(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        guard = 0
        while ride.engine.state.loops == 0 and guard < 20000:
            self.app.hub.tick(0.5)
            ride.update(0.5)
            guard += 1
        self.assertEqual(ride.engine.state.loops, 1)
        self.assertIsInstance(self.screen(), app_mod.RideScreen)
        self.assertFalse(ride.engine.finished)
        texts = [lab.text or "" for lab in pyglet_stub.created["labels"]]
        self.assertTrue(any("Volta 1 completa" in x for x in texts), texts[-12:])
        self.assertTrue(any("Voltas à rota: 1" in x for x in texts))
        # a câmara voltou ao início da estrada
        self.app._on_draw()
        self.assertLess(ride.engine.state.pos_m, 200.0)
        self.assertGreater(ride.engine.state.dist_m, 5000.0)

    def test_stop_mid_workout_saves_partial_fit(self):
        zwo = Path(self.tmp) / "longo.zwo"
        zwo.write_text('<workout_file><name>Longo</name><workout>'
                       '<SteadyState Duration="3600" Power="0.8"/>'
                       '</workout></workout_file>')
        self.pick("Importar treino")
        self.screen()._import(zwo)
        self.pick("Longo")
        self.pick("Começar")
        self.pick("Serra de Teste")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        self._run(ride, 90)
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        summary = self.screen()
        self.assertIsInstance(summary, app_mod.SummaryScreen)
        self.assertEqual(summary.result["summary"].elapsed_s, 90)
        rows = self.app.db.conn.execute(
            "SELECT * FROM workout_step_results WHERE ride_id = ?",
            (summary.result["ride_id"],)).fetchall()
        self.assertEqual(len(rows), 1)            # o passo parcial ficou registado

    def test_leaving_an_unfinished_ride_aborts_it(self):
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(40):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        ride_id = ride.engine.ride_id
        ride.leave()
        status = self.app.db.conn.execute(
            "SELECT status FROM rides WHERE id = ?", (ride_id,)).fetchone()["status"]
        self.assertEqual(status, "aborted")

    def test_comparison_mode_lists_past_efforts(self):
        # grava uma sessão para haver com que comparar
        ride = self._start_ride()
        ride.world.build_all()
        ride.preparing = False
        guard = 0
        while not ride.engine.route_finished and guard < 20000:
            self.app.hub.tick(0.25)
            ride.update(0.25)
            guard += 1
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        self.pick("Fechar")

        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Modo de sessão")          # alterna para comparação
        setup = self.screen()
        self.assertTrue(setup.comparison)
        labels = [i.label for i in setup.list.items]
        self.assertTrue(any("2026" in x or "202" in x for x in labels),
                        f"sem esforços anteriores listados: {labels}")


class TestWorkoutAndFtpScreens(GuiCase):
    def test_import_a_zwo_and_start_it(self):
        zwo = Path(self.tmp) / "treino.zwo"
        zwo.write_text(
            '<workout_file><name>Teste</name><workout>'
            '<Warmup Duration="300" PowerLow="0.5" PowerHigh="0.7"/>'
            '<SteadyState Duration="600" Power="0.95" Cadence="90"/>'
            '</workout></workout_file>')
        self.pick("Importar treino")
        from velo.core.workout_library import WORKOUTS
        self.assertEqual(len(self.app.db.workouts()), len(WORKOUTS))   # os de origem
        self.screen()._import(zwo)
        self.assertEqual(len(self.app.db.workouts()), len(WORKOUTS) + 1)
        self.pick("Teste")
        from velo.ui import brief
        self.assertIsInstance(self.screen(), brief.CyclingBrief)
        self.assertTrue(self.screen().brief_data.goal)        # objetivo (sugerido)
        self.pick("Começar")
        self.assertIsInstance(self.screen(), app_mod.WorkoutRouteChoice)
        self.pick("Serra de Teste")
        setup = self.screen()
        self.assertIsInstance(setup, app_mod.RideSetup)
        self.assertTrue(any("ERG" in i.label for i in setup.list.items))

    def test_erg_can_be_turned_off_before_starting(self):
        zwo = Path(self.tmp) / "t.zwo"
        zwo.write_text('<workout_file><name>Limiar 2x20</name><workout>'
                       '<SteadyState Duration="300" Power="0.9"/>'
                       '</workout></workout_file>')
        self.pick("Importar treino")
        self.screen()._import(zwo)
        self.pick("Limiar 2x20")
        self.pick("Começar")
        self.pick("Serra de Teste")
        setup = self.screen()
        self.assertTrue(setup.erg)
        self.pick("Modo ERG")
        self.assertFalse(setup.erg)

    def test_ftp_protocols_are_listed_and_startable(self):
        self.pick("Testes")
        self.pick("Teste de FTP")
        labels = self.labels()
        for proto in ("20 minutos", "Rampa", "8 minutos"):
            self.assertTrue(any(proto in x for x in labels), f"falta {proto}")
        self.pick("Rampa")
        self.assertIsInstance(self.screen(), app_mod.FtpRouteChoice)
        self.pick("Sem rota")
        self.assertIsInstance(self.screen(), app_mod.RideSetup)
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        self.assertEqual(ride.ftp_protocol, "ramp")
        self.assertIsNone(ride.world)          # sem rota, sem mundo
        ride.update(0.25)
        ride.draw()

    def test_ftp_result_is_offered_and_accepted(self):
        self.pick("Testes")
        self.pick("Teste de FTP")
        self.pick("20 minutos")
        self.pick("Sem rota")
        self.pick("Começar")
        ride = self.screen()
        for _ in range(60):
            self.app.hub.tick(1.0)
            ride.update(1.0)
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        summary = self.screen()
        self.assertIsInstance(summary, app_mod.SummaryScreen)
        summary.ftp_estimate = (300.0, 285)   # como se o teste tivesse corrido
        summary._accept_ftp()
        self.assertEqual(self.app.db.athlete().ftp_w, 285)
        self.assertIsInstance(self.screen(), app_mod.MainMenu)


class TestChallengeScreen(GuiCase):
    def test_lists_defaults_with_progress(self):
        self.pick("Desafios")
        labels = self.labels()
        for name in ("Pedalar 500 km", "Subir 1000 m"):
            self.assertTrue(any(name in x for x in labels), f"falta {name}")
        self.assertTrue(any("%" in x for x in labels))

    def test_open_reset_and_create(self):
        self.pick("Desafios")
        self.pick("Pedalar 500 km")
        self.assertIsInstance(self.screen(), app_mod.ChallengeDetail)
        self.pick("Reiniciar")
        self.assertEqual(self.app.db.active_attempt(1)["progress"], 0.0)
        self.app.pop()
        self.pick("Novo desafio")
        self.assertIsInstance(self.screen(), app_mod.ChallengeCreate)

    def test_create_a_distance_challenge_with_decimals(self):
        self.pick("Desafios")
        before = len(self.app.db.challenges())
        self.pick("Novo desafio")
        self.select("Objetivo")
        self.type("5,000.34")
        self.assertTrue(any("= 5000.34 km" in x for x in self.labels()), self.labels())
        self.pick("Criar desafio")
        self.assertIsInstance(self.screen(), app_mod.ChallengeScreen)
        rows = self.app.db.challenges()
        self.assertEqual(len(rows), before + 1)
        new = rows[-1]
        self.assertEqual(new["metric"], "distance_m")
        self.assertAlmostEqual(new["target"], 5_000_340.0, places=3)
        self.assertEqual(new["name"], "Pedalar 5000.34 km")
        self.assertTrue(any("5000.34 km" in x for x in self.labels()))

    def test_create_an_elevation_challenge_in_km_with_a_name(self):
        self.pick("Desafios")
        self.pick("Novo desafio")
        self.pick("Tipo")                           # distância → subida
        self.select("Objetivo")
        self.type("23,5")
        self.pick("Unidade")                        # m → km
        self.select("Nome")
        self.type("Jakarta kick")                   # j, k e espaço escrevem
        self.assertEqual(self.screen().name_text, "Jakarta kick")
        self.pick("Criar desafio")
        new = self.app.db.challenges()[-1]
        self.assertEqual(new["metric"], "ascent_m")
        self.assertAlmostEqual(new["target"], 23_500.0)
        self.assertEqual(new["name"], "Jakarta kick")
        self.assertEqual(new["display_unit"], "km")

    def test_backspace_and_invalid_values(self):
        self.pick("Desafios")
        self.pick("Novo desafio")
        self.select("Objetivo")
        self.type("12a")                            # a letra é ignorada
        self.assertEqual(self.screen().value_text, "12")
        self.press(key.BACKSPACE, key.BACKSPACE)
        self.assertEqual(self.screen().value_text, "")
        self.type("0")
        create = [i for i in self.screen().list.items if "Criar" in i.label][0]
        self.assertFalse(create.enabled)

    def test_board_follows_the_selected_challenge(self):
        self.pick("Desafios")
        self.select("Subir 1000 m")
        texts = self.board_texts()
        self.assertIn("Subir 1000 m", texts)
        self.assertTrue(any("/ 1000 m" in x for x in texts), texts)

    def test_custom_challenge_can_be_deleted(self):
        cid = self.app.db.create_challenge("Meu desafio", "ascent_m", 100.0)
        self.pick("Desafios")
        self.pick("Meu desafio")
        self.pick("Apagar")
        self.assertFalse(any(c["id"] == cid for c in self.app.db.challenges()))


class TestChaseScreens(GuiCase):
    def test_full_flow_from_menu_to_summary(self):
        self.pick("Challenge")
        self.pick("Fuga")
        self.assertIsInstance(self.screen(), app_mod.ChaseScreen)
        self.assertIn("Fuga", self.board_texts())
        self.pick("Difícil")
        self.assertEqual(self.app.db.get("chase_level"), "hard")
        self.pick("Sem rota")
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        self.assertIsNotNone(ride.engine.chase)
        for _ in range(int(30 / 0.25)):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.assertIn("Vantagem", ride.hud._chase_title.text)
        self.assertEqual(ride.hud.board_panel.title.text, "Fuga")
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        summary = self.screen()
        self.assertIsInstance(summary, app_mod.SummaryScreen)
        self.assertTrue(any("Fuga terminada" in x for x in self.labels()))
        self.assertEqual(len(self.app.db.chase_leaderboard("hard", None)), 1)
        texts = self.board_texts()
        self.assertIn("Fuga", texts)

    def test_route_choice_shows_best_per_route(self):
        self.pick("Challenge")
        self.pick("Fuga")
        self.pick("Normal")
        self.assertIsInstance(self.screen(), app_mod.ChaseRouteChoice)
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("Serra de Teste", labels)


class TestBoardsEverywhere(GuiCase):
    def test_main_menu_board_changes_with_selection(self):
        self.select("Sessão de treino")
        self.assertIn("Recordes", self.board_texts())
        self.select("Testes")
        self.assertIn("Teste de FTP", self.board_texts())
        self.select("Challenge")
        self.assertIn("Fuga", self.board_texts())

    def test_route_library_and_detail_show_route_board(self):
        self.pick("Sessão de treino")
        self.select("Serra de Teste")
        self.assertIn("Serra de Teste", self.board_texts())
        self.pick("Serra de Teste")
        texts = self.board_texts()
        self.assertIn("Serra de Teste", texts)

    def test_summary_highlights_the_ride_just_done(self):
        ride = None
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(4000):
            self.app.hub.tick(0.5)
            ride.update(0.5)
            if ride.engine.state.loops:
                break
        self.assertEqual(ride.engine.state.loops, 1)
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        panel = self.screen().board_panel
        self.app._on_draw()
        self.assertEqual(panel.board.rows[0].me, True)


class TestHomeScreen(GuiCase):
    def test_home_has_the_sports_and_icons(self):
        self.press(key.ESCAPE)
        home = self.screen()
        self.assertIsInstance(home, app_mod.HomeScreen)
        titles = [tile.title.text for tile in home.tiles]
        self.assertEqual(titles[:5], ["Ciclismo", "Remo", "Corrida", "Natação", "Ginásio"])
        self.assertEqual(titles[5:], ["Calendário", "Saúde", "Estatísticas gerais",
                                      "Inventário de artigos", "Exercícios"])
        self.assertTrue(all(tile.icon is not None for tile in home.tiles))
        # os desportos em cima (maiores), o resto em baixo
        self.assertGreater(home.tiles[0].bg.y, home.tiles[5].bg.y)
        self.assertGreater(home.tiles[0].bg.height, home.tiles[5].bg.height)
        self.assertEqual(home.form_title.text, "Forma")
        self.assertIn("seguidos", home.streak_lines[0].text)

    def test_running_hub_and_back_arrow_returns(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        hub = self.screen()
        self.assertEqual(hub.tab_labels(), ["Treinar", "Construtor de treinos",
                                            "Lista de treinos", "Histórico", "Estatísticas"])
        b = hub.back_button.bg
        self.app._on_mouse_press(int(b.x + 5), int(b.y + 5), 1, 0)
        self.assertIsInstance(self.screen(), app_mod.HomeScreen)

    def test_tiles_respond_to_keys_and_mouse(self):
        self.press(key.ESCAPE)
        home = self.screen()
        self.press(key.DOWN)                        # para a fila de baixo
        self.assertTrue(home.tiles[5].selected)
        self.press(key.RIGHT, key.RIGHT, key.ENTER)
        self.assertIsInstance(self.screen(), app_mod.StatsScreen)    # as gerais
        self.assertEqual(type(self.screen()).__name__, "GeneralStatsScreen")
        self.press(key.ESCAPE)
        tile = home.tiles[0].bg
        self.app._on_mouse_press(int(tile.x + 10), int(tile.y + 10), 1, 0)
        self.assertIsInstance(self.screen(), app_mod.MainMenu)

    def test_every_menu_has_a_back_arrow(self):
        for name in ("Sessão de treino", "Importar treino", "Desafios", "Definições"):
            self.app.reset_to_menu()
            self.pick(name)
            self.assertIsNotNone(self.screen().back_button, name)
            b = self.screen().back_button.bg
            self.app._on_mouse_press(int(b.x + 5), int(b.y + 5), 1, 0)
            self.assertIsInstance(self.screen(), app_mod.MainMenu, name)

    def test_top_bar_devices_settings_and_quit(self):
        bar = self.app.topbar
        self.app._tick(0.01)
        self.app._on_draw()
        # aparelhos sempre à vista, com o estado
        self.assertEqual(bar.devices, [("Trainer simulado", "ok")])
        r = bar.buttons["devices"][0]
        self.app._on_mouse_press(int(r.x + 5), int(r.y + 5), 1, 0)
        self.assertIsInstance(self.screen(), app_mod.DeviceScreen)
        self.assertTrue(self.screen().MODAL)
        self.press(key.ESCAPE)
        r = bar.buttons["settings"][0]
        self.app._on_mouse_press(int(r.x + 5), int(r.y + 5), 1, 0)
        self.assertIsInstance(self.screen(), app_mod.SettingsScreen)
        self.press(key.ESCAPE)
        r = bar.buttons["quit"][0]
        self.app._on_mouse_press(int(r.x + 5), int(r.y + 5), 1, 0)
        conf = self.screen()
        self.assertIsInstance(conf, app_mod.ConfirmScreen)       # pede sempre confirmação
        self.assertEqual(conf.list.selected.label, "Não")
        self.pick("Não")
        self.assertIsInstance(self.screen(), app_mod.MainMenu)

    def test_settings_and_quit_are_off_during_a_session(self):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        self.app._tick(0.1)
        self.assertFalse(self.app.topbar.enabled["settings"])
        self.assertFalse(self.app.topbar.enabled["quit"])
        self.press(key.F8)
        self.assertIs(self.screen(), ride)
        self.app.press_ctrl_q = None
        self.app._on_key_press(key.Q, key.MOD_CTRL)
        self.assertIs(self.screen(), ride)
        # os dispositivos continuam disponíveis, por cima da sessão, que não para
        self.press(key.F4)
        self.assertIsInstance(self.screen(), app_mod.DeviceScreen)
        t0 = ride.engine.state.t_s
        ride.preparing = False
        for _ in range(10):
            self.app._tick(0.5)
        self.assertGreater(ride.engine.state.t_s, t0)
        self.assertFalse(ride.engine.finished)
        self.press(key.ESCAPE)
        self.assertIs(self.screen(), ride)

    def test_lost_device_is_announced_once(self):
        now = [0.0]
        hub = self.app.hub
        hub._clock = lambda: now[0]
        hub.names["ble:strap"] = "Cinta"
        hub.push("ble:strap", "hr", 150)
        now[0] += 10.0
        self.app._tick(0.1)
        self.assertIn("Cinta desligou-se", self.app._message)
        self.app._message = ""
        self.app._tick(0.1)
        self.assertEqual(self.app._message, "")


class TestStatsExplorer(GuiCase):
    def _ride(self, seconds=300):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(int(seconds / 0.5)):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.press(key.F10, key.ENTER)
        self.pick("Fechar")

    def test_power_curve_shows_values_and_the_date_of_a_point(self):
        self._ride()
        self.pick("Gráficos e análise")
        screen = self.screen()
        self.assertEqual(screen.VIEWS[screen.view], "power_curve")
        self.assertTrue(screen.chart._yticks[2].text.endswith("W"))   # valores no eixo
        today = __import__("time").strftime("%Y-%m-%d")
        self.assertIn(today, screen.chart._tip.text)                   # data do ponto
        self.select("Ponto")
        before = screen.point
        self.press(key.LEFT)
        self.assertEqual(screen.point, before - 1)
        x, y = screen.chart.points[0]
        self.app._on_mouse_press(int(x), int(y), 1, 0)                 # clicar num ponto
        self.assertEqual(screen.point, 0)
        self.assertTrue(screen.chart._tip.text.startswith("0:01"))

    def test_evolution_by_period_with_percentile(self):
        self._ride()
        self.pick("Gráficos e análise")
        screen = self.screen()
        self.press(key.TAB)                                            # → Evolução
        self.assertEqual(screen.VIEWS[screen.view], "evolution")
        self.assertEqual(len(screen._series), 12)                      # 12 semanas
        self.assertGreater(screen._series[-1][1], 0)                   # esta semana tem km
        self.assertIn("Esta semana", screen.summary[1].text)
        self.assertIn("percentil", screen.summary[1].text)
        self.select("Agrupar")
        self.press(key.RIGHT)                                          # semana → mês
        self.assertEqual(screen.grouping, "month")
        self.assertIn("Este mês", screen.summary[1].text)
        self.select("Intervalo")
        self.press(key.RIGHT)
        self.assertEqual(screen.count, 16)
        self.assertEqual(len(screen._series), 16)
        self.select("Métrica")
        self.press(key.RIGHT)                                          # distância → tempo
        self.assertEqual(screen.metric, "time")
        self.assertTrue(screen.chart._yticks[2].text.endswith("h"))

    def test_time_in_zone_and_power_profile_views(self):
        self._ride()
        self.pick("Gráficos e análise")
        screen = self.screen()
        self.press(key.TAB, key.TAB)                                   # → Tempo em zona
        self.assertEqual(screen.VIEWS[screen.view], "zones")
        titles = [r["title"].text for r in screen.bars.rows]
        self.assertIn("Tempo em zona · potência", titles)
        widths = sum(p.width for p in screen.bars.rows[0]["parts"])
        self.assertAlmostEqual(widths, screen.chart.width, delta=1.0)
        self.press(key.TAB, key.TAB, key.TAB, key.TAB)                 # → Perfil de potência
        self.assertEqual(screen.VIEWS[screen.view], "profile")
        notes = [r["note"].text for r in screen.bars.rows if r["note"].text]
        self.assertTrue(any("/100" in n for n in notes), notes)


class TestStatsScreen(GuiCase):
    def test_opens_empty_without_crashing(self):
        self.pick("Gráficos e análise")
        self.app._on_draw()
        self.assertTrue(any("Sem dados" in x for x in self.labels()))

    def _assert_no_overlap(self):
        screen = self.screen()
        chrome, chart, view = screen.chrome, screen.chart, screen.list
        rows = [view.y - i * 38 for i in range(view.visible_rows)]
        lowest_row = min(rows) - 12 - 8                 # linha de detalhe, mais a letra
        title_top = chart.title.y + 18
        self.assertGreater(lowest_row, title_top, "recordes por cima do gráfico")
        axis_labels = chart.y - 14
        self.assertGreater(axis_labels - 12, chrome.message.y,
                           "legendas do eixo por cima das mensagens")
        self.assertLess(view.y + 10, chrome.subtitle.y - 16, "recordes por cima do título")
        self.assertGreaterEqual(chart.height, 120)

    def test_layout_does_not_overlap(self):
        self.pick("Gráficos e análise")
        self._assert_no_overlap()
        for w, h in ((1024, 640), (1920, 1080), (2560, 1440)):
            self.app.set_display(False, w, h)
            self._assert_no_overlap()

    def test_arrows_cycle_the_charts(self):
        self.pick("Gráficos e análise")
        screen = self.screen()
        titles = set()
        for _ in range(len(screen.VIEWS) + 1):
            titles.add(screen.chart.title.text)
            self.press(key.TAB)                     # os gráficos estão em separadores
            self.app._on_draw()
        self.assertGreaterEqual(len(titles), len(screen.VIEWS))

    def test_charts_have_data_after_a_ride(self):
        self.pick("Sessão de treino")
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(600):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.press(key.F10, key.ENTER)          # terminar → «Sim»
        self.pick("Fechar")

        self.pick("Gráficos e análise")
        screen = self.screen()
        self.assertTrue(any("Horas totais" in (lab.text or "")
                            for lab in pyglet_stub.created["labels"]))
        # a curva de potência é a primeira vista e agora tem pontos
        self.assertEqual(screen.VIEWS[screen.view], "power_curve")
        self.assertEqual(screen.chart.empty.text, "")
        self.app._on_draw()


class TestPygletCompat(unittest.TestCase):
    """O adaptador tem de servir a pyglet 2.0 (`bold`) e a 2.1 (`weight`)."""

    def _with_fake_label(self, fake_cls):
        import pyglet.text
        from velo.gfx import compat
        original, compat._label_style = pyglet.text.Label, None
        pyglet.text.Label = fake_cls
        try:
            yield compat
        finally:
            pyglet.text.Label = original
            compat._label_style = None

    def test_new_api_uses_weight(self):
        class New:
            def __init__(self, text="", weight="normal", **kw):
                self.text, self.weight, self.kw = text, weight, kw
        for compat in self._with_fake_label(New):
            lab = compat.label("Olá", bold=True, font_size=20)
            self.assertEqual(lab.weight, "bold")
            self.assertEqual(lab.kw["font_size"], 20)
            self.assertEqual(compat.label("x").weight, "normal")

    def test_old_api_falls_back_to_bold(self):
        class Old:
            def __init__(self, text="", bold=False, **kw):
                if "weight" in kw:
                    raise TypeError("unexpected keyword argument 'weight'")
                self.text, self.bold = text, bold
        for compat in self._with_fake_label(Old):
            self.assertTrue(compat.label("Olá", bold=True).bold)
            self.assertFalse(compat.label("x").bold)
            self.assertEqual(compat._label_style, "bold")

    def test_font_list_is_passed_by_default(self):
        class New:
            def __init__(self, text="", weight="normal", **kw):
                self.kw = kw
        for compat in self._with_fake_label(New):
            self.assertIn("Segoe UI", compat.label("x").kw["font_name"])


class TestWorldGeometry(unittest.TestCase):
    """O construtor da malha corre de verdade, com a pyglet falsa a validar
    a coerência dos vértices e dos índices."""

    @classmethod
    def setUpClass(cls):
        _, raw = gpx.parse_gpx(GPX)
        cls.points = gpx.resample(raw)

    def test_builds_every_preset(self):
        for preset in PRESETS:
            with self.subTest(preset=preset):
                pyglet_stub.reset()
                world = World(self.points, preset, seed="x")
                world.build_all()
                self.assertTrue(world.ready)
                self.assertGreaterEqual(len(world.chunks), 23)  # 6 km / 250 m
                self.assertGreater(len(pyglet_stub.created["vlists"]), 20)

    def test_draw_distance_grows_with_the_preset(self):
        low = World(self.points, "low")
        high = World(self.points, "high")
        self.assertLess(low.cfg["draw_m"], high.cfg["draw_m"])
        low.build_all()
        high.build_all()
        low.visible_chunks(1000.0)
        high.visible_chunks(1000.0)
        self.assertLess(sum(1 for c in low.chunks if c.group.visible),
                        sum(1 for c in high.chunks if c.group.visible))

    def test_terrain_is_deterministic_for_the_same_route(self):
        a = World(self.points, "low", seed="rota-1")
        b = World(self.points, "low", seed="rota-1")
        a.build_all()
        b.build_all()
        self.assertEqual(len(a.chunks), len(b.chunks))
        # o ruído é semeado pela posição, logo a câmara coincide exatamente
        self.assertEqual(a.camera(500.0)[1], b.camera(500.0)[1])

    def test_delete_releases_the_buffers(self):
        pyglet_stub.reset()
        world = World(self.points, "low")
        world.build_all()
        lists = list(pyglet_stub.created["vlists"])
        world.delete()
        self.assertTrue(all(vl.deleted for vl in lists))
        self.assertEqual(world.chunks, [])

    def test_short_route_still_builds(self):
        world = World(self.points[:40], "low")
        world.build_all()
        self.assertTrue(world.ready)
        world.camera(0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
