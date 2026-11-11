"""Ronda 9: barra do topo com pesquisa e mensagens, ecrã inicial, número de
métricas no ecrã da sessão, Definições por desporto, upload manual, testes e
treinos (exportar, resultados), construtor e janela de sessão."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia.core import layouts as lay  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import layout_screens as ls  # noqa: E402


# ============================================ número de métricas no ecrã


class TestMetricCount(tg.GuiCase):
    def test_resize_keeps_order_and_respects_the_maximum(self):
        for sport in ("running", "rowing", "gym", "cycling"):
            groups = lay.defaults(sport)
            avail = [k for k, _ in lay.catalog(sport)]
            top = lay.max_count(sport, avail)
            more = lay.resized(groups, sport, lay.count(groups) + 3, avail)
            self.assertEqual(lay.count(more), min(lay.count(groups) + 3, top), sport)
            self.assertEqual(lay.count(lay.resized(groups, sport, 999, avail)), top, sport)
            again = [m for g in more for m in g if m]
            self.assertEqual(len(set(again)), len(again), sport)      # sem repetidas
            if sport == "cycling":                 # cada caixa mantém as suas, pela ordem
                for old, new in zip(groups, more):
                    self.assertEqual(new[:len(old)], old, sport)
            else:                                  # a lista corrida mantém as primeiras
                flat = [m for g in groups for m in g]
                self.assertEqual(again[:len(flat)], flat, sport)

    def test_rowing_pages_split_evenly(self):
        self.assertEqual(lay.page_sizes("rowing", 24), [12, 12])
        self.assertEqual(lay.page_sizes("rowing", 14), [7, 7])
        self.assertEqual(lay.page_sizes("rowing", 8), [8])
        self.assertEqual(lay.grid_for(8), (4, 2))
        self.assertEqual(lay.grid_for(1), (1, 1))

    def test_settings_has_no_metric_count_row_in_any_sport(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Desportos")
        for i in range(len(scr.SPORTS)):
            scr.set_sport(i)
            scr.set_section(1)                             # disposição do ecrã de sessão
            labels = [x.label for x in scr.list.items]
            self.assertNotIn("Número de métricas no ecrã", labels)
            self.assertFalse([x for x in scr.list.items if str(x.data).startswith("count:")])
            self.assertIn("Escolher as métricas do ecrã", labels)
            self.assertIn("Disposição dos painéis", labels)

    def test_the_layout_panels_row_opens_the_screen_of_that_sport(self):
        from perennia.ui import arrangement_screens as arr
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Desportos")
        for i, sport in enumerate(scr.SPORTS):
            scr.set_sport(i)
            scr.set_section(1)
            self.pick("Disposição dos painéis")
            ed = self.screen()
            self.assertIsInstance(ed, arr.ArrangementEditor)
            self.assertEqual(ed.sport, sport)              # o ginásio já não vai para o ciclismo
            self.press(key.ESCAPE)
            self.assertIs(self.screen(), scr)

    def test_editor_buttons_and_keys(self):
        ed = ls.LayoutEditor(self.app, "running")
        self.app.push(ed)
        self.assertEqual(ed.tab_labels(), ["Corrida"])
        n = lay.count(ed.groups)
        self.press(key.BRACKETRIGHT)
        self.assertEqual(lay.count(ed.groups), n + 1)
        self.assertTrue(ed.dirty)
        self.press(key.BRACKETLEFT, key.BRACKETLEFT)
        self.assertEqual(lay.count(ed.groups), n - 1)
        ed.set_count(999)
        self.assertEqual(lay.count(ed.groups), ed.max_count())
        self.assertIn(f"{ed.max_count()} de {ed.max_count()}", ed.prev_title.text)
        self.save()
        self.assertEqual(lay.count(lay.load(self.app.db, "running")), ed.max_count())

    def test_rowing_session_pages_follow_the_number(self):
        names = [k for k, _ in lay.catalog("rowing")][:14]
        lay.save(self.app.db, "rowing", lay.split(names, "rowing"))
        from perennia.ui import rowing_screens as rs
        ses = rs.RowingSessionScreen(self.app)
        self.assertEqual(ses.pages, 2)
        self.assertEqual(len(ses.cells), 7)
        self.app.push(ses)
        ses.update(0.1)
        ses.page = 1
        ses.update(0.1)

    def test_gym_session_tiles_follow_the_number(self):
        names = [k for k, _ in lay.catalog("gym")][:7]
        lay.save(self.app.db, "gym", [names])
        from perennia.core import strength as st
        ex = st.exercises(self.app.db)[0]
        wid = st.save_workout(self.app.db, None, "T", None, [
            {"exercise_id": ex["id"], "sets": 3, "reps": 8, "load_kg": 20.0, "rpe": None,
             "rest_s": 60}])
        from perennia.ui import sport_screens as ss
        scr = ss.StrengthSessionScreen(self.app, wid)
        self.assertEqual(len(scr.tiles), 7)
        self.app.push(scr)
        scr._layout_panel()
        scr._update_tiles()

    def test_the_swimming_and_gym_options_are_gone(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Desportos")
        self.assertNotIn("Natação", scr.sport_tabs.labels_text)
        scr.set_sport(3)                                   # o ginásio
        self.assertEqual(scr.sport, "gym")
        self.assertEqual(scr.section_labels(),
                         ["Métricas de sessão disponíveis", "Disposição do ecrã de sessão"])
        scr.set_section(2)                                 # não existe: fica numa que exista
        self.assertLess(scr.section_tab, 2)
        scr.set_sport(0)
        self.assertEqual(len(scr.section_labels()), 3)

    def test_no_initial_ctl_atl_in_the_athlete_tab(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Atleta")
        labels = " ".join(i.label for i in scr.list.items)
        self.assertNotIn("CTL inicial", labels)
        self.assertNotIn("ATL inicial", labels)
        self.assertIn("Contar as atividades importadas", labels)


# ====================================== barra do topo, pesquisa, mensagens


class TestTopBar(tg.GuiCase):
    def test_search_lives_in_the_top_bar_and_keeps_working(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Ecrã e idioma")
        scr.search_focus(True)
        scr.search_text("tema")
        self.assertEqual([i.label for i in scr.list.items if not i.button], ["Tema"])
        right, top, w, h = self.app.topbar.search_slot()
        box = scr.search_box
        self.assertGreater(box.y, self.app.window.height - self.app.topbar.H)   # na faixa do topo
        self.assertLess(box.x + w, self.app.window.width)
        self.assertEqual(self.app.topbar.hit(box.x + 10, box.y + 4), "search")
        scr.search_key(key.ESCAPE, 0)
        self.assertEqual(scr.search_box.text, "")

    def test_the_bar_is_a_bit_taller(self):
        self.assertEqual(self.app.topbar.H, 32)

    def test_messages_are_bold_and_drawn_on_the_top_bar(self):
        self.app.message("Treino exportado para a pasta Transferências")
        screen = self.app.current
        self.app._on_draw()
        bar = self.app.topbar.msg
        self.assertTrue(bar.active)
        self.assertEqual(bar.lines[0].text, "Treino exportado para a pasta Transferências")
        # na linha do título, por baixo da barra do topo
        self.assertLess(bar.bg.y + bar.bg.height, self.app.window.height - self.app.topbar.H)
        self.assertIsNotNone(screen)


# ================================================================ upload manual


def _write_fit(path, minutes: int = 30):
    """Um .fit de ciclismo escrito pelo próprio codificador da Perennia."""
    import time

    from perennia.core import fit, gpx
    from perennia.core.db import Athlete, Lap, RideSummary, Sample
    from perennia.core.route_index import RouteIndex
    gpx_path = Path(__file__).parent / "teste.gpx"
    _, raw = gpx.parse_gpx(gpx_path)
    idx = RouteIndex(gpx.resample(raw))
    n = minutes * 60
    samples = [Sample(t_s=i, dist_m=i * 7.0, speed_mps=7.0, power_w=220 + (i % 11),
                      cadence_rpm=85, hr_bpm=150 + (i % 5), balance_left=51.0,
                      grade_pct=idx.grade_at(i * 7.0 % 2000), ele_m=idx.ele_at(i * 7.0 % 2000),
                      lap_no=1) for i in range(n)]
    summary = RideSummary(elapsed_s=n, moving_s=n, distance_m=n * 7.0, ascent_m=90.0,
                          avg_power_w=225.0, max_power_w=240, np_w=230.0, intensity_factor=0.92,
                          tss=48.0, work_kj=400.0, avg_hr=152.0, max_hr=154, avg_cadence=85.0,
                          avg_speed_mps=7.0)
    fit.write_activity(path, Athlete(name="T", birth_year=1990, weight_kg=72.0, ftp_w=250),
                       samples, [Lap(lap_no=1, trigger="end", start_t_s=0, end_t_s=n - 1,
                                     start_dist_m=0.0, end_dist_m=n * 7.0, avg_power_w=225.0,
                                     max_power_w=240, avg_hr=152.0, max_hr=154, avg_cadence=85.0,
                                     avg_speed_mps=7.0, ascent_m=90.0)],
                       summary, start_unix=time.time() - 7200, include_coords=False,
                       virtual=False)
    return Path(path)


class TestManualUpload(tg.GuiCase):
    def test_fit_is_decoded(self):
        from perennia.core import activity_upload as au
        f = _write_fit(Path(self.tmp) / "ride.fit")
        info = au.parse(f)
        self.assertEqual(info["format"], "fit")
        self.assertEqual(info["sport"], "cycling")
        self.assertAlmostEqual(info["elapsed_s"], 1800, delta=2)
        self.assertAlmostEqual(info["distance_m"], 1800 * 7.0, delta=50)
        self.assertEqual(info["laps"], 1)
        self.assertEqual(info["records"], 1800)
        self.assertGreater(info["avg_power_w"], 200)
        self.assertGreater(info["avg_hr"], 140)
        self.assertTrue(info["started_at"].endswith("Z"))

    def test_broken_and_foreign_files_are_refused(self):
        from perennia.core import activity_upload as au
        f = _write_fit(Path(self.tmp) / "ride.fit")
        cut = Path(self.tmp) / "cut.fit"
        cut.write_bytes(f.read_bytes()[:300])
        with self.assertRaises(au.UploadError):
            au.parse(cut)
        txt = Path(self.tmp) / "x.fit"
        txt.write_text("isto não é um fit")
        with self.assertRaises(au.UploadError):
            au.parse(txt)
        with self.assertRaises(au.UploadError):
            au.parse(Path(self.tmp) / "nada.fit")

    def test_tcx_is_read(self):
        from perennia.core import activity_upload as au
        p = Path(self.tmp) / "run.tcx"
        p.write_text("""<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Running"><Id>2026-10-20T07:00:00Z</Id>
<Lap StartTime="2026-10-20T07:00:00Z"><TotalTimeSeconds>1800</TotalTimeSeconds>
<DistanceMeters>5000</DistanceMeters><Calories>380</Calories>
<AverageHeartRateBpm><Value>150</Value></AverageHeartRateBpm>
<MaximumHeartRateBpm><Value>171</Value></MaximumHeartRateBpm><Track></Track></Lap>
</Activity></Activities></TrainingCenterDatabase>""", encoding="utf-8")
        info = au.parse(p)
        self.assertEqual((info["sport"], info["distance_m"], info["avg_hr"]),
                         ("running", 5000.0, 150.0))

    def test_upload_flow_saves_to_the_sport_and_counts_in_history(self):
        from perennia.core import garmin_sync as gs
        from perennia.ui import upload_screens as up
        f = _write_fit(Path(self.tmp) / "ride.fit")
        scr = self.open_sync()
        labels = scr.sync.source_labels()
        self.assertIn("Upload manual", labels)
        scr.sync_tab = labels.index("Upload manual")
        scr.enter()
        self.assertTrue(any("Como funciona" in i.label for i in scr.list.items))
        scr.sync.open_upload(f)
        pop = self.screen()
        self.assertIsInstance(pop, up.UploadPreview)
        text = " ".join(f"{i.label} {i.value}" for i in pop.list.items)
        for needle in ("Ficheiro", "Nome da atividade", "Atividade", "Tempo total", "Distância",
                       "Ciclismo", "Fazer upload"):
            self.assertIn(needle, text)
        pop.sport = "running"                              # o desporto muda-se antes de guardar
        pop.upload()
        self.assertIsNot(self.screen(), pop)
        rows = gs.activities(self.app.db, "running")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "upload")
        self.assertEqual(gs.activities(self.app.db, "cycling"), [])
        # outra vez o mesmo ficheiro: não duplica
        scr.sync.open_upload(f)
        self.assertTrue(self.screen().dup)
        self.screen().upload()                           # volta a gravar o mesmo: atualiza
        self.assertEqual(len(gs.activities(self.app.db)), 1)
        # aparece no Histórico do desporto
        from perennia.ui.sync_screens import history_items
        self.assertTrue(any("upload manual" in i.detail for i in history_items(self.app, "cycling")
                            if i.detail))

    def test_dropping_a_fit_opens_the_upload(self):
        from perennia.ui import upload_screens as up
        f = _write_fit(Path(self.tmp) / "drop.fit", minutes=5)
        self.app._on_file_drop(0, 0, [str(f)])
        self.assertIsInstance(self.screen(), up.UploadPreview)
        self.press(key.ESCAPE)
        self.app._on_file_drop(0, 0, [str(Path(self.tmp) / "x.txt")])      # sem rebentar


# ======================================== testes, exportar, treinos e desportos


class TestResultsAndExport(tg.GuiCase):
    def setUp(self):
        super().setUp()
        import tempfile
        self.dl = tempfile.mkdtemp()
        import os
        os.environ["PERENNIA_DOWNLOADS"] = self.dl

    def tearDown(self):
        import os
        import shutil
        os.environ.pop("PERENNIA_DOWNLOADS", None)
        shutil.rmtree(self.dl, ignore_errors=True)
        super().tearDown()

    def _test_id(self, sport: str) -> int:
        from perennia.core import fitness_tests as ft
        ft.seed(self.app.db)
        if sport == "swimming":
            from perennia.core import endurance as en
            en.seed(self.app.db)
        x = next(t for t in ft.tests(self.app.db, sport) if not t["protocol"])
        return x["id"]

    def test_results_list_and_the_popups_to_edit_and_delete(self):
        from perennia.core import fitness_tests as ft
        from perennia.ui import health_screens as hs
        tid = self._test_id("running")
        ft.add_result(self.app.db, tid, 100.0, done_on="2026-05-01", notes="a")
        ft.add_result(self.app.db, tid, 120.0, done_on="2026-06-01")
        self.app.push(hs.TestDetail(self.app, tid))
        det = self.screen()
        labels = [i.label for i in det.list.items]
        self.assertIn("Resultados (2)", labels)
        self.assertEqual(labels.index("2026-06-01") + 1, labels.index("2026-05-01"))
        det.list.select_data(("result", ft.results(self.app.db, tid)[0]["id"]))
        self.press(key.ENTER)
        pop = self.screen()
        self.assertIsInstance(pop, hs.ResultPopup)
        self.assertIn("Apagar", [i.label for i in pop.list.items])
        pop.num_set("value", 130.0)
        pop.notes = "melhor"
        self.assertTrue(pop.save())
        r = ft.results(self.app.db, tid)[0]
        self.assertEqual((r["value"], r["notes"]), (130.0, "melhor"))
        pop.delete()
        self.assertIsInstance(self.screen(), app_mod.ConfirmScreen)
        self.pick("Apagar")
        self.assertEqual(len(ft.results(self.app.db, tid)), 1)
        self.assertIsInstance(self.screen(), hs.TestDetail)

    def test_new_result_in_a_popup_and_no_timer_test_in_swimming(self):
        from perennia.core import fitness_tests as ft
        from perennia.ui import health_screens as hs
        sw = self._test_id("swimming")
        self.app.push(hs.TestDetail(self.app, sw))
        labels = [i.label for i in self.screen().list.items]
        self.assertNotIn("▶ Fazer o teste", labels)
        self.assertIn("Registar um resultado", labels)
        run = self._test_id("running")
        self.app.push(hs.TestDetail(self.app, run))
        self.assertIn("▶ Fazer o teste", [i.label for i in self.screen().list.items])
        self.pick("Registar um resultado")
        pop = self.screen()
        self.assertIsInstance(pop, hs.ResultPopup)
        self.assertNotIn("Apagar", [i.label for i in pop.list.items])
        pop.num_set("value", 42.0)
        pop.save_exit()
        self.assertEqual(ft.results(self.app.db, run)[0]["value"], 42.0)

    def test_export_popup_names_the_file_and_saves_in_downloads(self):
        from perennia.core import endurance as en
        from perennia.ui import endurance_screens as es
        from perennia.ui import upload_screens as up
        en.seed(self.app.db)
        w = en.workouts(self.app.db, "running")[0]
        self.app.push(es.EndurancePreview(self.app, "running", w["id"]))
        prev = self.screen()
        self.assertIn("Exportar", [i.label for i in prev.list.items])
        self.pick("Exportar")
        pop = self.screen()
        self.assertIsInstance(pop, up.ExportPopup)
        self.assertEqual(pop.formats[0][0], "json")
        pop.name = "o meu treino"
        pop.cycle("format", 1)                      # .txt
        pop.export()
        self.assertIs(self.screen(), prev)         # volta aos detalhes do treino
        out = Path(self.dl) / "o meu treino.txt"
        if not out.exists():                        # o nome é limpo para o sistema de ficheiros
            out = next(Path(self.dl).glob("*.txt"))
        self.assertIn(w["name"], out.read_text(encoding="utf-8"))
        self.assertIn(self.dl, self.app._message)   # a mensagem diz onde ficou
        # cancelar também volta aos detalhes
        self.pick("Exportar")
        self.press(key.ESCAPE)
        self.assertIs(self.screen(), prev)

    def test_cycling_exports_zwo_erg_mrc_fit(self):
        from perennia.core import workout_download as wd
        self.assertEqual([f for f, _ in wd.formats("cycling")],
                         ["zwo", "erg", "mrc", "fit", "json", "txt"])
        self.assertEqual([f for f, _ in wd.formats("rowing")], ["fit", "json", "txt"])
        self.assertEqual([f for f, _ in wd.formats("gym")], ["json", "txt"])
        w = self.app.db.workouts()[0]
        for fmt in ("zwo", "erg", "mrc", "fit", "json", "txt"):
            p = wd.export(self.app.db, "cycling", w["id"], fmt, self.dl, "treino x")
            self.assertTrue(p.exists() and p.stat().st_size > 20, fmt)
        again = wd.export(self.app.db, "cycling", w["id"], "zwo", self.dl, "treino x")
        self.assertTrue(again.name.endswith("_2.zwo"))              # não escreve por cima

    def test_brief_has_no_about_section_and_swimming_has_no_session(self):
        from perennia.core import endurance as en
        from perennia.ui import endurance_screens as es
        en.seed(self.app.db)
        run = es.EndurancePreview(self.app, "running", en.workouts(self.app.db, "running")[0]["id"])
        self.app.push(run)
        self.assertFalse(hasattr(run, "about"))
        self.assertIn("Configurar sessão de treino", [i.label for i in run.list.items])
        swim = es.EndurancePreview(self.app, "swimming",
                                   en.workouts(self.app.db, "swimming")[0]["id"])
        self.app.push(swim)
        labels = [i.label for i in swim.list.items]
        self.assertNotIn("Configurar sessão de treino", labels)
        self.assertIn("Exportar", labels)

    def test_swimming_train_tab_and_gym_hub_options(self):
        self.press(key.ESCAPE)
        self.pick("Natação")
        self.assertEqual([i.label for i in self.screen().list.items][:2], ["Desafios", "Testes"])
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        labels = [i.label for i in self.screen().list.items]
        self.assertNotIn("Exercícios", labels)
        self.assertNotIn("Inventário de artigos", labels)


# ================================================== construtor e janela da sessão


class TestBuilderAndSessionWindow(tg.GuiCase):
    def _builder(self):
        self.pick("Lista de treinos")
        self.pick("Novo treino")
        self.pick("ERG")
        return self.screen()

    def test_name_and_goal_values_start_at_the_same_x(self):
        b = self._builder()
        self.app._on_draw()
        self.assertEqual(b.list.head_value_x, b.HEAD_VALUE_X)
        xs = {}
        for (hl, label, value, detail), cell in zip(b.list._rows, b.list._cells):
            idx = cell[0]
            if b.list.items[idx].head:
                xs[b.list.items[idx].label] = (value.x, value.anchor_x)
        self.assertEqual(len(xs), 3)
        self.assertEqual(len({v for v in xs.values()}), 1)         # o mesmo x, à esquerda
        self.assertEqual(next(iter(xs.values()))[1], "left")

    def test_goal_popup_cancel_and_unsaved_question(self):
        from perennia.ui.goal_popup import GoalPopup
        b = self._builder()
        self.pick("Objetivo do treino")
        pop = self.screen()
        self.assertIsInstance(pop, GoalPopup)
        self.type("rascunho")
        self.press(key.ESCAPE)                                     # com texto novo: pergunta
        self.assertIsInstance(self.screen(), app_mod.ConfirmScreen)
        self.pick("Sair sem guardar")
        self.assertIs(self.screen(), b)
        self.assertEqual(b.wgoal, b.wgoal if b.wgoal != "rascunho" else "")
        self.assertNotEqual(b.wgoal, "rascunho")

    def test_session_window_is_bigger_and_has_every_mode(self):
        from perennia.ui import session_setup as ss
        self.pick("Sessão de treino")
        pop = self.screen()
        self.assertIsInstance(pop, ss.SessionModePopup)
        self.assertEqual([i.label for i in pop.list.items if not i.button],
                         ["Livre", "Carregar treino", "Do computador", "Challenge", "Testes"])
        self.assertGreater(ss.SessionSetup.W, 820)
        self.pick("Testes")                                        # na mesma janela
        self.assertIs(self.screen(), pop)
        names = [i.label for i in pop.list.items]
        self.assertTrue(any("FTP" in n or "minutos" in n for n in names))
        self.assertIn("Adicionar teste", names)
        self.press(key.ESCAPE)
        self.pick("Challenge")
        self.assertIn("Fuga", [i.label for i in pop.list.items])
        self.pick("Fuga")                                          # fecha e passa à preparação
        self.assertIsNot(self.screen(), pop)

    def test_every_sport_has_the_window_except_swimming(self):
        from perennia.ui import session_setup as ss
        self.press(key.ESCAPE)
        for name in ("Remo", "Corrida", "Ginásio"):
            self.pick(name)
            self.pick("Sessão de treino")
            pop = self.screen()
            self.assertIsInstance(pop, ss.SessionModePopup, name)
            labels = [i.label for i in pop.list.items]
            self.assertIn("Challenge", labels, name)
            self.assertIn("Testes", labels, name)
            self.press(key.ESCAPE)
            self.press(key.ESCAPE)


class TestCliAndBackup(tg.GuiCase):
    def test_import_cli_uploads_an_activity(self):
        import main
        f = _write_fit(Path(self.tmp) / "cli.fit", minutes=10)

        class A:
            data_dir = str(Path(self.tmp) / "cli-data")
            importar = ("atividade", str(f))
        self.assertEqual(main.import_cli(A), 0)
        from perennia.core.db import Database
        from perennia.datadir import database_path, data_dir_for
        db = Database(database_path(data_dir_for(A.data_dir)))
        from perennia.core import garmin_sync as gs
        rows = gs.activities(db, "cycling")
        db.close()
        self.assertEqual((len(rows), rows[0]["source"]), (1, "upload"))

    def test_layout_keys_and_synced_uploads_are_in_the_backup_components(self):
        from perennia.core import backup
        for k in ("layout_running", "layout_gym", "row_fields", "hud_boxes",
                  "metrics_disabled_gym"):
            self.assertTrue(backup.BY_KEY["ecra"].settings(k), k)
        self.assertIn("synced_activities", backup.BY_KEY["sessoes"].tables)
        backup.prepare(self.app.db)
        self.assertEqual(backup.unknown_tables(self.app.db), [])
