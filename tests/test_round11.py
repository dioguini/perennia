"""Ronda 11: Backups e Sincronização, CSV da Saúde, decoupling, ícones nos botões, etiquetas
do ginásio, calendário (seletor de datas e janela do dia), fórmula da Longevidade, o ginásio
sem Longevidade (janela da sessão, importar do computador), o ecrã da sessão de força e
«Planear» na ficha do treino."""
from __future__ import annotations

import importlib
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo import paths  # noqa: E402
from velo.core import calendar_view as cv  # noqa: E402
from velo.core import gym, health, stats, strength_import  # noqa: E402
from velo.core import health_csv as hcsv  # noqa: E402
from velo.core import longevity as lg  # noqa: E402
from velo.core import strength as st  # noqa: E402
from velo.core import tags as tag_core  # noqa: E402
from velo.core.db import Database  # noqa: E402
from velo.gfx import icons  # noqa: E402
from velo.ui import day_popups as dp  # noqa: E402
from velo.ui import gym_screens as gs  # noqa: E402
from velo.ui import pickers  # noqa: E402
from velo.ui import session_setup as sessetup  # noqa: E402
from velo.ui import sport_screens as ss  # noqa: E402


def fresh_db() -> Database:
    return Database(Path(tempfile.mkdtemp()) / "x.db")


# ============================================================ CSV da Saúde


class TestHealthCsv(tg.GuiCase):
    def test_template_has_the_perennia_fields(self):
        cols = hcsv.columns(self.app.db)
        self.assertEqual(cols[0], "data")
        self.assertEqual(cols[-1], "nota")
        names = {m["name"] for m in health.metrics(self.app.db)}
        self.assertTrue(names <= set(cols))
        text = hcsv.template(self.app.db)
        self.assertIn("data;", text.splitlines()[0])
        self.assertGreaterEqual(len(text.splitlines()), 2)            # cabeçalho + exemplo

    def test_export_and_import_round_trip_by_date(self):
        db = self.app.db
        health.seed(db)
        rhr = health.metric_by_key(db, "rhr")
        sleep = health.metric_by_key(db, "sleep_hours")
        d1, d2 = date.today() - timedelta(days=2), date.today() - timedelta(days=1)
        health.set_value(db, d1, rhr["id"], 51)
        health.set_value(db, d2, rhr["id"], 54)
        health.set_value(db, d2, sleep["id"], 7.5)
        health.set_day_note(db, d1, "dia de viagem")
        text = hcsv.export_csv(db)
        other = fresh_db()
        health.seed(other)
        self.assertTrue(hcsv.detect(other, text))
        rep = hcsv.import_csv(other, text)
        self.assertEqual(rep["days"], 2)
        rhr2 = health.metric_by_key(other, "rhr")
        vals = health.values_for(other, d2)
        self.assertEqual(vals[rhr2["id"]]["value"], 54)
        self.assertEqual(health.day_note(other, d1), "dia de viagem")

    def test_unknown_columns_are_ignored_and_bad_values_counted(self):
        db = fresh_db()
        health.seed(db)
        text = "data;FC em repouso;coluna que não existe\n" \
               "2026-03-01;52;x\n2026-03-02;abc;y\n"
        rep = hcsv.import_csv(db, text)
        self.assertEqual(rep["values"], 1)
        self.assertEqual(rep["invalid"], 1)
        self.assertIn("coluna que não existe", rep["ignored"])
        with self.assertRaises(ValueError):
            hcsv.import_csv(db, "sem;data\n1;2\n".replace("data", "xxx"))

    def test_the_health_tab_is_in_backups_and_sync(self):
        scr = self.open_sync("Saúde")
        self.assertEqual(scr.tab_labels(), ["Exportar", "Repor", "Sincronização"])
        labels = scr.sync.source_labels()
        self.assertIn("Saúde", labels)
        self.assertTrue(any("modelo" in i.label.lower() or "template" in i.label.lower()
                            for i in scr.list.items))


# ================================================================ decoupling


class TestDecoupling(tg.GuiCase):
    def test_decoupling_of_steady_and_drifting_rides(self):
        steady = stats.decoupling_of([200] * 3000, [140] * 3000)
        self.assertAlmostEqual(steady["decoupling"], 0.0, places=6)
        drift = stats.decoupling_of([200] * 3000, [140] * 1500 + [154] * 1500)
        self.assertAlmostEqual(drift["decoupling"], (1 - 140 / 154) * 100, places=3)
        self.assertGreater(drift["decoupling"], 5.0)
        self.assertIsNone(stats.decoupling_of([200] * 600, [140] * 600))        # < 20 min

    def test_the_label_reads_the_number(self):
        self.assertIn("forte", stats.decoupling_label(2.0))
        self.assertNotEqual(stats.decoupling_label(7.0), stats.decoupling_label(2.0))
        self.assertNotEqual(stats.decoupling_label(14.0), stats.decoupling_label(7.0))

    def test_history_reads_the_rides_with_hr(self):
        db = self.app.db
        db.conn.execute(
            "INSERT INTO rides (id, name, status, started_at, moving_s, elapsed_s,"
            " ftp_at_ride_w, weight_at_ride_kg) VALUES"
            " ('r1', 'Base', 'completed', ?, 3000, 3000, 250, 72)",
            ((date.today() - timedelta(days=3)).isoformat() + "T08:00:00",))
        db.conn.executemany(
            "INSERT INTO ride_samples (ride_id, t_s, power_w, hr_bpm, dist_m)"
            " VALUES ('r1', ?, 200, ?, ?)",
            [(i, 140 if i < 1500 else 150, i * 8.0) for i in range(3000)])
        db.conn.commit()
        hist = stats.decoupling_history(db, days=30)
        self.assertEqual(len(hist), 1)
        self.assertGreater(hist[0]["decoupling"], 5.0)

    def test_cycling_stats_has_the_decoupling_view(self):
        self.pick("Estatísticas")
        scr = self.screen()
        self.assertIn("decoupling", scr.VIEWS)


# =================================================================== ícones


class TestButtonIcons(tg.GuiCase):
    def test_the_same_action_has_the_same_icon(self):
        self.assertEqual(icons.button_icon("+ Novo treino"), icons.button_icon("+ Nova métrica"))
        self.assertEqual(icons.button_icon("Guardar"), icons.button_icon("Guardar e sair"))
        self.assertEqual(icons.button_icon("Apagar"), icons.button_icon("Apagar a última volta"))
        self.assertEqual(icons.button_icon("Planear"), icons.button_icon("+ Planear treino"))
        self.assertNotEqual(icons.button_icon("Guardar"), icons.button_icon("Apagar"))
        self.assertEqual(icons.button_icon("Cancelar"), icons.button_icon("Cancelar"))

    def test_the_plus_is_drawn_by_the_icon(self):
        self.assertEqual(icons.button_text("+ Novo treino"), "Novo treino")
        self.assertEqual(icons.button_text("Guardar"), "Guardar")
        self.assertEqual(icons.button_text("−"), "")
        self.assertEqual(icons.button_text("+"), "")

    def test_every_icon_exists_and_every_button_in_a_popup_gets_one(self):
        folder = paths.resource("velo", "assets", "icons")
        names = {icons.button_icon(x) for x in ("Guardar", "Apagar", "Cancelar", "Voltar",
                                                "+ Novo treino", "Editar", "Exportar", "Importar",
                                                "Pausa", "Terminar", "Começar", "OK", "Sim")}
        for n in names:
            self.assertTrue((Path(folder) / f"{n}.png").exists(), n)
        self.app.open_backups()
        scr = self.screen()
        buttons = [i for i in scr.list.items if i.button]
        self.assertTrue(buttons)
        for b in buttons:
            self.assertTrue(icons.button_icon(b.label))


# ======================================================== etiquetas do .fit


class TestFitTags(tg.GuiCase):
    def test_perennia_and_the_indoor_tag_are_always_there(self):
        self.assertEqual(tag_core.session_type_tags("strength"), ["Perennia", "Indoor Strength"])
        self.assertEqual(tag_core.session_type_tags("cycling")[:2], ["Perennia", "Indoor Cycling"])
        info = tag_core.resolve(self.app.db, "strength", "s1",
                                {"workout_type": None, "session": [], "custom": ["Pernas"]})
        self.assertEqual(info["session"], ["Perennia", "Indoor Strength"])
        self.assertEqual(info["custom"], ["Pernas"])
        self.assertIn("Perennia", tag_core.fit_text(info))

    def test_a_new_tag_can_be_created_in_the_add_popup(self):
        from velo.ui import tag_popup as tp
        got = []
        pop = tp.AddTagPopup(self.app, [], got.append)
        self.app.push(pop)
        pop.search_set("Fim de semana")
        self.assertTrue(any(i.label.startswith("Criar") for i in pop.list.items))
        self.pick("Criar")
        self.assertEqual(got, ["Fim de semana"])

    def test_a_gym_session_writes_its_tags(self):
        db = self.app.db
        wid = gym.workouts(db, "strength")[0]["id"]
        ses = st.StrengthSession(db, db.athlete(), wid, out_dir=Path(self.tmp) / "str")
        ses.action()
        ses.update(30.0)
        ses.action()
        ses.tags_chosen = {"workout_type": None, "session": [], "custom": ["Teste"]}
        res = ses.finish()
        info = tag_core.load(db, "strength", res["session_id"])
        self.assertEqual(info["session"], ["Perennia", "Indoor Strength"])
        self.assertEqual(info["custom"], ["Teste"])
        self.assertTrue(Path(res["fit_path"]).exists())
        self.assertIn(b"Perennia", Path(res["fit_path"]).read_bytes())


# ============================================================== calendário


class TestHomeCalendar(tg.GuiCase):
    def home(self):
        self.press(key.ESCAPE)
        return self.screen()

    def test_no_message_under_the_title_and_a_date_picker(self):
        home = self.home()
        self.assertEqual(home.chrome.subtitle.text, "")
        got = []
        pickers.pick_date(self.app, "Ir para a data", date.today(), got.append)
        self.assertIsInstance(self.screen(), pickers.DatePickerPopup)
        self.press(key.ENTER)
        self.assertEqual(got, [date.today().isoformat()])

    def test_the_calendar_has_month_navigation(self):
        home = self.home()
        cal = home.cal
        m0 = (cal.year, cal.month) if hasattr(cal, "year") else cal.month
        cal.go(date.today().replace(day=1) + timedelta(days=40))
        self.assertNotEqual((getattr(cal, "year", 0), cal.month), m0)

    def test_a_day_popup_with_note_diary_and_plan(self):
        home = self.home()
        day = date.today() + timedelta(days=1)
        home.open_day(day)
        pop = self.screen()
        self.assertIsInstance(pop, dp.DayPopup)
        buttons = [i.label for i in pop.list.items if i.button]
        self.assertEqual(buttons[0], "Nota do dia")
        self.assertTrue(buttons[1].startswith("Diário de saúde"))
        self.assertEqual(buttons[2], "+ Planear treino")
        self.pick("Diário de saúde")
        from velo.ui.health_screens import DailyLogScreen
        self.assertIsInstance(self.screen(), DailyLogScreen)

    def test_future_day_plans_from_list_computer_or_builder(self):
        day = date.today() + timedelta(days=3)
        self.app.push(dp.PlanSportPopup(self.app, day))
        labels = [i.label for i in self.screen().list.items]
        for sport in ("Ciclismo", "Remo", "Corrida", "Natação", "Ginásio"):
            self.assertIn(sport, labels)
        self.pick("Ciclismo")
        src = self.screen()
        self.assertIsInstance(src, dp.PlanSourcePopup)
        labels = [i.label for i in src.list.items]
        self.assertIn("Importar um treino da lista", labels)
        self.assertIn("Importar um treino do computador", labels)
        self.assertIn("Criar um treino no construtor", labels)
        self.pick("Importar um treino da lista")
        wid = self.app.db.workouts()[0]
        self.pick(wid["name"])
        self.assertTrue(any(p.sport == "cycling" for p in cv.planned_for(self.app.db, day)))

    def test_past_day_loads_what_happened(self):
        day = date.today() - timedelta(days=3)
        self.app.push(dp.PlanSportPopup(self.app, day))
        self.pick("Ciclismo")
        labels = [i.label for i in self.screen().list.items]
        self.assertTrue(any(".fit" in x for x in labels))
        self.assertTrue(any("HRV" in x for x in labels))
        self.assertTrue(any("saúde" in x.lower() for x in labels))
        self.pick("Sincronizar dados de saúde")
        scr = self.screen()
        self.assertEqual(scr.tab_labels(), ["Exportar", "Repor", "Sincronização"])
        self.assertEqual(scr.sync.source_labels()[scr.sync_tab], "Saúde")


# ============================================================= longevidade


class TestLongevityFormula(tg.GuiCase):
    def test_the_formula_is_editable_and_recomputed(self):
        db = self.app.db
        base = lg.formula(db)
        self.assertIn("aerobic", base["axes"])
        before = lg.compute(db)["1m"]["index"]
        f = lg.formula(db)
        f["axes"]["aerobic"]["weight"] = base["axes"]["aerobic"]["weight"] * 3
        lg.save_formula(db, f)
        self.assertEqual(lg.formula(db)["axes"]["aerobic"]["weight"],
                         base["axes"]["aerobic"]["weight"] * 3)
        after = lg.compute(db)["1m"]["index"]
        self.assertIsNotNone(after if before is None else before)
        lg.reset_formula(db)
        self.assertEqual(lg.formula(db)["axes"]["aerobic"]["weight"],
                         base["axes"]["aerobic"]["weight"])

    def test_a_new_parameter_enters_the_radar_and_the_text(self):
        db = self.app.db
        health.seed(db)
        cid = lg.add_custom(db, name="Passos", kind="metric", source="steps", target=8000)
        self.assertIn(cid, lg.all_axes(db))
        self.assertEqual(lg.label_of(db, cid), "Passos")
        health_steps = health.metric_by_key(db, "steps")
        if health_steps:
            for i in range(5):
                health.set_value(db, date.today() - timedelta(days=i), health_steps["id"], 8000)
            res = lg.compute(db)["1w"]
            self.assertIn(cid, res["axes"])
        self.assertIn("1", dict(lg.formula_lines(db))["Parâmetros próprios"])
        lg.remove_custom(db, cid)
        self.assertNotIn(cid, lg.all_axes(db))

    def test_the_menu_shows_the_formula_tab(self):
        self.press(key.ESCAPE)
        self.pick("Longevidade")
        menu = self.screen()
        self.assertIn("Fórmula", menu.tab_labels())
        menu.tab_named("Fórmula")
        labels = [i.label for i in menu.list.items]
        self.assertTrue(any("aeróbi" in x.lower() or "aerob" in x.lower() for x in labels))
        self.assertTrue(any("novo" in x.lower() or "parâmetro" in x.lower() for x in labels))


# ============================================================ ginásio

TXT = """Treino de pernas
Agachamento com barra 4x8 60kg
Prancha 3x45s
"""


class TestGymWithoutLongevity(tg.GuiCase):
    def test_there_is_no_longevity_modality(self):
        keys = [m.key for m in gym.modalities()]
        self.assertNotIn("longevity", keys)
        for k in ("strength", "conditioning", "mobility"):
            self.assertIn(k, keys)
        for w in gym.workouts(self.app.db, "strength"):
            self.assertNotIn("longevidade", w["name"].lower())

    def test_import_a_workout_from_a_text_file(self):
        p = Path(self.tmp) / "pernas.txt"
        p.write_text(TXT, encoding="utf-8")
        loaded = strength_import.read(p)
        self.assertEqual(len(loaded.rows), 2)
        self.assertEqual(loaded.rows[0].sets, 4)
        self.assertEqual(loaded.rows[0].reps, 8)
        self.assertEqual(loaded.rows[0].load_kg, 60)
        wid = strength_import.save(self.app.db, loaded, "strength", keep=True)
        self.assertIn(wid, [w["id"] for w in gym.workouts(self.app.db, "strength")])
        hidden = strength_import.save(self.app.db, loaded, "strength", keep=False)
        self.assertNotIn(hidden, [w["id"] for w in gym.workouts(self.app.db, "strength")])
        with self.assertRaises(strength_import.ImportError_):
            q = Path(self.tmp) / "nada.txt"
            q.write_text("\n", encoding="utf-8")
            strength_import.read(q)

    def test_the_session_window_goes_modality_then_options(self):
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Sessão de treino")
        pop = self.screen()
        self.assertIsInstance(pop, sessetup.SessionModePopup)
        mods = [i.label for i in pop.list.items]
        self.assertIn("Força", mods)
        self.assertNotIn("Longevidade", mods)
        self.pick("Força")
        self.assertEqual(self.screen().level, "mod:strength")
        labels = [i.label for i in self.screen().list.items]
        self.assertEqual(labels[:5], ["Treino livre", "Treino surpresa", "Carregar treino",
                                      "Treino livre por blocos", "Do computador"])
        self.assertIn("Challenge", labels)
        self.assertIn("Testes", labels)
        self.press(key.ESCAPE)                              # Esc volta às modalidades
        self.assertIsNone(self.screen().level)
        self.assertIsInstance(self.screen(), sessetup.SessionModePopup)

    def test_set_up_the_session_has_a_locked_auto_lap(self):
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        self.app.push(gs.GymSessionSetup(self.app, wid))
        setup = self.screen()
        lap = next(i for i in setup.list.items if i.label == "Auto lap")
        self.assertFalse(lap.enabled)
        self.assertIn("bloco", lap.value + lap.detail)
        self.assertEqual([i.label for i in setup.list.items if i.button][-1], "Começar")


class TestStrengthSessionScreen(tg.GuiCase):
    def open_session(self):
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = ss.StrengthSessionScreen(self.app, wid)
        self.app.push(scr)
        return scr

    def test_the_workout_is_a_list_and_enter_starts_the_set(self):
        scr = self.open_session()
        rows = [i for i in scr.list.items if isinstance(i.data, tuple) and i.data[0] == "ex"]
        self.assertEqual(len(rows), len(scr.session.items))
        self.assertTrue(rows[0].label.lstrip().startswith("▶"))
        scr.list.select_data(("ex", 1))
        self.press(key.ENTER)                                # vai ao 2.º exercício e começa
        self.assertEqual(scr.session.item_idx, 1)
        self.assertEqual(scr.session.phase, st.WORK)
        scr.list.select_data(("ex", 0))
        self.press(key.ENTER)                                # a meio de uma série: avisa
        self.assertEqual(scr.session.item_idx, 1)
        self.assertEqual(scr.session.phase, st.WORK)

    def test_buttons_are_at_the_bottom_like_the_other_sports(self):
        scr = self.open_session()
        labels = [i.label for i in scr.list.items if i.button]
        self.assertEqual(labels[1:], ["+ Série", "Saltar", "Pausa", "Terminar"])
        self.assertTrue(scr.list.items[-1].button)
        self.press(key.P)
        self.assertTrue(scr.session.paused)
        self.assertEqual([i.label for i in scr.list.items if i.button][-2], "Retomar")

    def test_rests_are_in_the_list_and_finish_is_red(self):
        scr = self.open_session()
        kinds = [i.data[0] for i in scr.list.items if isinstance(i.data, tuple)]
        self.assertIn("rest", kinds)
        first = [i.data for i in scr.list.items if isinstance(i.data, tuple)][:2]
        self.assertEqual([d[0] for d in first], ["ex", "rest"])      # exercício, depois o descanso
        fin = [i for i in scr.list.items if i.button][-1]
        self.assertEqual(fin.label, "Terminar")
        self.assertTrue(fin.danger)
        self.press(key.SPACE)
        for _ in range(4):
            self.app._tick(0.5)
        self.press(key.SPACE)                                # terminou a série: descanso
        cur = [i for i in scr.list.items if i.data and i.data[0] == "rest"
               and i.label.startswith("▶")]
        self.assertEqual(len(cur), 1)
        self.assertEqual(scr.list.selected.data[0], "rest")

    def test_esc_pauses_and_f10_asks_with_the_same_dialog(self):
        scr = self.open_session()
        self.press(key.SPACE)                                # começa a série…
        for _ in range(6):
            self.app._tick(0.5)
        self.press(key.SPACE)                                # …e termina-a
        self.press(key.SPACE)
        self.press(key.ESCAPE)
        self.assertTrue(scr.session.paused)
        self.assertFalse(scr.confirming)
        self.press(key.F10)
        self.assertTrue(scr.finish_dialog.visible)
        self.press(key.ESCAPE)                               # «Não»
        self.assertFalse(scr.confirming)
        self.press(key.F10)
        self.press(key.ENTER)                                # «Sim»: as etiquetas
        from velo.ui import tag_popup as tp
        self.assertIsInstance(self.screen(), tp.SessionTagsPopup)
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), ss.StrengthSummaryScreen)


# ====================================================== «Planear» na ficha


class TestPlanFromTheBrief(tg.GuiCase):
    def test_every_sport_brief_has_a_plan_button(self):
        from velo.ui import brief
        wid = self.app.db.workouts()[0]["id"]
        scr = brief.CyclingBrief(self.app, wid)
        self.app.push(scr)
        labels = [i.label for i in scr.list.items if i.button]
        self.assertIn("Planear", labels)
        self.assertEqual(labels, ["Editar", "Planear", "Exportar", "Configurar sessão de treino"])

    def test_plan_puts_the_workout_in_the_calendar(self):
        from velo.ui import brief
        wid = self.app.db.workouts()[0]["id"]
        scr = brief.CyclingBrief(self.app, wid)
        self.app.push(scr)
        self.pick("Planear")
        self.assertIsInstance(self.screen(), pickers.DatePickerPopup)
        self.press(key.ENTER)                                # hoje
        self.assertTrue(any(p.workout_id == wid for p in cv.planned_for(self.app.db,
                                                                         date.today())))
        self.pick_again = None
        n = len(cv.planned_for(self.app.db, date.today()))
        self.pick("Planear")
        self.press(key.ENTER)
        self.assertEqual(len(cv.planned_for(self.app.db, date.today())), n)   # sem duplicar

    def test_gym_brief_can_be_planned_too(self):
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = ss.StrengthPreview(self.app, wid)
        self.app.push(scr)
        self.pick("Planear")
        self.press(key.ENTER)
        self.assertTrue(any(p.sport == "gym" and p.workout_id == wid
                            for p in cv.planned_for(self.app.db, date.today())))


# =============================================== menus dos desportos

class TestSportSubtitles(tg.GuiCase):
    def test_athlete_ftp_lthr_everywhere_but_the_gym(self):
        self.press(key.ESCAPE)
        for name in ("Ciclismo", "Corrida", "Remo", "Natação"):
            self.pick(name)
            sub = self.screen().chrome.subtitle.text
            self.assertIn("Daniel", sub, name)
            self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.assertEqual(self.screen().chrome.subtitle.text, "")


# ================================================================= backups


class TestBackupRound11(tg.GuiCase):
    def test_the_longevity_formula_travels_with_the_settings(self):
        from velo.core import backup
        db = self.app.db
        self.assertEqual(backup.unknown_tables(db), [])           # nenhuma tabela nova por tratar
        health.seed(db)
        cid = lg.add_custom(db, name="Passos", kind="metric", source="steps", target=8000)
        out = Path(self.tmp) / "defs.zip"
        backup.export(db, Path(self.tmp), out, keys=["definicoes"])
        other = fresh_db()
        backup.restore(other, Path(tempfile.mkdtemp()), out, keys=["definicoes"], mode="substituir")
        self.assertIn(cid, [c["id"] for c in lg.formula(other)["custom"]])

    def test_the_health_csv_is_a_cli_import(self):
        import subprocess
        main = Path(__file__).resolve().parents[1] / "main.py"
        data = Path(tempfile.mkdtemp())
        out = subprocess.run([sys.executable, str(main), "--data-dir", str(data),
                              "--csv-modelo", "saude", "--destino", str(data)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)
        files = list(data.glob("*.csv"))
        self.assertTrue(files, out.stdout + out.stderr)
        res = subprocess.run([sys.executable, str(main), "--data-dir", str(data),
                              "--importar", "saude", str(files[0])],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
