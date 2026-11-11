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
from velo.core.units import hms  # noqa: E402
from velo.io import rower as rio  # noqa: E402
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

    def test_past_day_cannot_be_planned_only_loaded(self):
        home = self.home()
        day = date.today() - timedelta(days=3)
        home.open_day(day)
        pop = self.screen()
        self.assertIsInstance(pop, dp.DayPopup)
        buttons = [i.label for i in pop.list.items if i.button]
        self.assertEqual(buttons[0], "Nota do dia")
        self.assertTrue(buttons[1].startswith("Diário de saúde"))
        self.assertEqual(buttons[2], "Carregar treino")
        self.assertNotIn("+ Planear treino", buttons)
        self.pick("Carregar treino")
        labels = [i.label for i in self.screen().list.items]
        self.assertTrue(any(".fit" in x for x in labels))
        self.assertTrue(any("HRV" in x for x in labels))
        self.assertTrue(any("saúde" in x.lower() for x in labels))
        self.pick("Sincronizar dados de saúde")
        scr = self.screen()
        self.assertEqual(scr.tab_labels(), ["Exportar", "Repor", "Sincronização"])
        self.assertEqual(scr.sync.source_labels()[scr.sync_tab], "Saúde")

    def test_today_and_future_can_be_planned(self):
        home = self.home()
        for d in (date.today(), date.today() + timedelta(days=5)):
            home.open_day(d)
            buttons = [i.label for i in self.screen().list.items if i.button]
            self.assertEqual(buttons[2], "+ Planear treino")
            self.press(key.ESCAPE)

    def test_plan_it_refuses_the_past(self):
        day = date.today() - timedelta(days=1)
        wid = self.app.db.workouts()[0]["id"]
        dp.plan_it(self.app, day, "cycling", wid, "Antigo")
        self.assertEqual(cv.planned_for(self.app.db, day), [])

    def test_the_brief_date_picker_starts_today(self):
        from velo.ui import brief
        wid = self.app.db.workouts()[0]["id"]
        scr = brief.CyclingBrief(self.app, wid)
        self.app.push(scr)
        self.pick("Planear")
        pop = self.screen()
        self.assertEqual(pop.min_day, date.today())


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
    def open_session(self, free: bool = False):
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = ss.StrengthSessionScreen(self.app, wid, free=free)
        self.app.push(scr)
        return scr

    def test_it_starts_by_itself_and_the_button_is_lap(self):
        scr = self.open_session()
        self.assertTrue(scr.session.started)                  # sem contagem (0 s): já a decorrer
        self.assertEqual(scr.session.phase, st.WORK)
        buttons = [i.label for i in scr.list.items if i.button]
        self.assertEqual(buttons, ["Lap", "+ Série", "Saltar", "Pausa", "Terminar"])
        self.assertFalse([i for i in scr.list.items if "Começar série" in i.label])

    def test_the_countdown_runs_first_then_the_set_starts(self):
        self.app.db.set("session_countdown_s", 15)
        scr = self.open_session()
        self.assertTrue(scr.counting)
        self.assertFalse(scr.session.started)
        for _ in range(40):
            self.app._tick(0.5)                               # 20 s
        self.assertFalse(scr.counting)
        self.assertTrue(scr.session.started)
        self.assertEqual(scr.session.phase, st.WORK)

    def test_reps_and_load_are_in_front_of_each_exercise(self):
        scr = self.open_session()
        head = scr.list.items[0]
        self.assertTrue(head.header)
        self.assertEqual(head.cols, ("Repetições", "Carga"))
        rows = [i for i in scr.list.items if isinstance(i.data, tuple) and i.data[0] == "ex"]
        self.assertEqual(len(rows), len(scr.session.items))
        for r in rows:
            self.assertEqual(len(r.cols), 2)
        # sem linhas à parte para as repetições, a carga e o RPE: só o exercício e o descanso
        datas = [i.data for i in scr.list.items]
        self.assertFalse([d for d in datas if isinstance(d, str) and d.startswith("num:")])
        self.assertFalse([i for i in scr.list.items if "RPE" in i.label])
        k = scr.list.items.index(rows[0])
        self.assertEqual(scr.list.items[k + 1].data, ("rest", 0))   # logo a seguir, o descanso

    def test_the_rest_row_shows_its_time_in_the_reps_column(self):
        scr = self.open_session()
        rests = [i for i in scr.list.items if isinstance(i.data, tuple) and i.data[0] == "rest"]
        self.assertTrue(rests)
        s = scr.session
        for r in rests:
            ex = s.items[r.data[1]]
            self.assertEqual(r.cols[0], hms(ex.rest_s))
            self.assertEqual(r.cols[1], "")
            self.assertEqual(r.label.strip(), "Descanso")
        # em descanso, a linha em curso conta para trás (e passa a +m:ss se ultrapassar)
        self.press(key.SPACE)                                # Lap: descanso
        cur = [i for i in scr.list.items if i.data == ("rest", 0)][0]
        self.assertTrue(cur.label.startswith("▶"))
        self.assertRegex(cur.cols[0], r"^\d+:\d\d$")
        self.app._tick(0.5)
        left = s.rest_until - s.t
        self.assertAlmostEqual(left, s.items[0].rest_s - 0.5, delta=1.5)

    def test_the_workout_is_a_list_and_enter_starts_the_set(self):
        scr = self.open_session()
        rows = [i for i in scr.list.items if isinstance(i.data, tuple) and i.data[0] == "ex"]
        self.assertTrue(rows[0].label.lstrip().startswith("▶"))
        scr.list.select_data(("ex", 1))
        self.press(key.ENTER)                                # a meio de uma série: avisa
        self.assertEqual(scr.session.item_idx, 0)
        self.press(key.SPACE)                                # Lap: descanso
        self.assertEqual(scr.session.phase, st.REST)
        scr.list.select_data(("ex", 2))
        self.press(key.ENTER)                                # vai a esse exercício e começa
        self.assertEqual(scr.session.item_idx, 2)
        self.assertEqual(scr.session.phase, st.WORK)

    def test_rests_are_in_the_list_and_finish_is_red(self):
        scr = self.open_session()
        kinds = [i.data[0] for i in scr.list.items if isinstance(i.data, tuple)]
        self.assertIn("rest", kinds)
        fin = [i for i in scr.list.items if i.button][-1]
        self.assertEqual(fin.label, "Terminar")
        self.assertTrue(fin.danger)
        for _ in range(4):
            self.app._tick(0.5)
        self.press(key.SPACE)                                # Lap: terminou a série, descanso
        cur = [i for i in scr.list.items if i.data and i.data[0] == "rest"
               and i.label.startswith("▶")]
        self.assertEqual(len(cur), 1)
        self.assertEqual(scr.list.selected.data[0], "rest")

    def test_esc_pauses_and_f10_asks_with_the_same_dialog(self):
        scr = self.open_session()
        for _ in range(6):
            self.app._tick(0.5)
        self.press(key.SPACE)                                # Lap: termina a série…
        self.press(key.SPACE)                                # …e Lap começa a seguinte
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

    def test_finishing_the_last_set_stops_and_asks(self):
        scr = self.open_session()
        s = scr.session
        n = sum(s.planned_sets(i) for i in range(len(s.items)))
        for k in range(n):
            for _ in range(2):
                self.app._tick(0.5)
            self.press(key.SPACE)                            # Lap: termina a série
            if k < n - 1:
                self.assertFalse(scr.confirming)
                self.press(key.SPACE)                        # Lap: começa a seguinte
        self.app._tick(0.5)
        self.assertTrue(scr.confirming)                      # o treino acabou: abre sozinho
        self.assertTrue(scr.finish_dialog.visible)
        self.assertTrue(s.paused)                            # e o tempo pára

    def test_free_workout_lap_opens_the_reps_popup_and_rest_goes_on(self):
        scr = self.open_session(free=True)
        s = scr.session
        self.assertTrue(s.free)
        for _ in range(8):
            self.app._tick(0.5)
        self.press(key.SPACE)                                # Lap: acabou o exercício
        self.assertEqual(s.phase, st.REST)
        pop = self.screen()
        self.assertIsInstance(pop, ss.FreeSetPopup)          # as repetições abrem logo
        self.app._on_text("12")
        self.assertEqual(s.sets[-1].reps, 12)
        t0 = s.t
        self.app._tick(2.0)
        self.assertGreater(s.t, t0)                          # o descanso continua por baixo
        self.press(key.ENTER)                                # fecha
        self.assertIs(self.screen(), scr)
        self.assertEqual(s.phase, st.REST)
        self.press(key.SPACE)                                # Lap: o exercício seguinte
        self.assertEqual(s.phase, st.WORK)
        self.assertEqual(s.item_idx, 1)
        self.assertEqual(len(s.sets), 1)                     # só o tempo do exercício guardado
        self.assertGreaterEqual(s.sets[0].end_t - s.sets[0].start_t, 3)

    def test_free_workout_does_not_end_by_itself(self):
        scr = self.open_session(free=True)
        s = scr.session
        for _ in range(len(s.items)):
            self.press(key.SPACE)                            # Lap (termina o exercício)
            self.press(key.ESCAPE)                           # fecha a janela das repetições
            self.press(key.SPACE) if s.phase == st.REST and not s.all_done else None
        self.app._tick(0.5)
        self.assertFalse(scr.confirming)


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

    def test_the_sound_settings_and_free_sessions_travel_in_the_backup(self):
        from velo.core import backup
        db = self.app.db
        cues.save_rules(db, [{"id": "r1", "when": "first", "seconds": 10, "per_s": 0,
                              "scope": "all"}])
        db.set("sound_on", False)
        wid = gym.workouts(db, "strength")[0]["id"]
        ses = st.StrengthSession(db, db.athlete(), wid, out_dir=Path(self.tmp) / "str",
                                 free=True)
        ses.action()
        ses.update(8.0)
        ses.action()
        ses.finish()
        out = Path(self.tmp) / "full.zip"
        backup.export(db, Path(self.tmp), out)
        other = fresh_db()
        backup.restore(other, Path(tempfile.mkdtemp()), out, mode="substituir")
        self.assertEqual(cues.rules(other)[0]["when"], "first")
        self.assertFalse(cues.enabled(other))
        self.assertTrue(st.is_free_session(other, ses.session_id))        # continua «livre»

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


# ========================================================== ronda 12: avisos sonoros

from velo.core import cues  # noqa: E402
from velo.io import sound  # noqa: E402


class TestCues(tg.GuiCase):
    def run_segment(self, items, total, kind="work", step=0.1, **kw):
        out = []
        tracker = cues.CueTracker(items, out.append, **kw)
        n = int(total / step) + 6
        for i in range(n):
            el = i * step
            tracker.update("k", kind, el, total - el)
        return out

    def test_default_rule_is_the_last_five_seconds_one_beep_each_plus_a_long_one(self):
        self.assertEqual(cues.rules(self.app.db), cues.DEFAULT_RULES)
        out = self.run_segment(cues.rules(self.app.db), 12)
        self.assertEqual(out, ["short"] * 5 + ["long"])

    def test_last_ten_seconds_one_per_second_and_last_five_two_per_second(self):
        rules = [{"id": "a", "when": "last", "seconds": 10, "per_s": 1, "scope": "all"},
                 {"id": "b", "when": "last", "seconds": 5, "per_s": 2, "scope": "all"}]
        out = self.run_segment(rules, 20, long_at_end=False)
        # 10 do primeiro + 10 do segundo, menos os 5 que calham no mesmo segundo (um só bip)
        self.assertEqual(len(out), 15)

    def test_first_ten_seconds_with_a_single_beep(self):
        rules = [{"id": "a", "when": "first", "seconds": 10, "per_s": 0, "scope": "all"}]
        out = self.run_segment(rules, 30, long_at_end=False)
        self.assertEqual(out, ["short"])

    def test_scope_rest_only(self):
        rules = [{"id": "a", "when": "last", "seconds": 3, "per_s": 1, "scope": "rest"}]
        self.assertEqual(self.run_segment(rules, 10, kind="work", long_at_end=False), [])
        self.assertEqual(len(self.run_segment(rules, 10, kind="rest", long_at_end=False)), 3)

    def test_a_segment_that_starts_late_does_not_play_the_past_beeps(self):
        out = []
        tr_ = cues.CueTracker(cues.rules(self.app.db), out.append, long_at_end=False)
        for i in range(5):                       # um descanso de 3 s: a janela de 5 s já passou
            tr_.update("k", "rest", i * 0.5, 3 - i * 0.5)
        self.assertLessEqual(len(out), 3)

    def test_off_is_silent_but_the_last_seconds_are_still_visible(self):
        out = []
        tr_ = cues.CueTracker(cues.rules(self.app.db), out.append, on=False)
        seen = [tr_.update("k", "work", 10 - r, r) for r in (6.0, 4.6, 3.2, 1.1, 0.4)]
        self.assertEqual(out, [])
        self.assertEqual(seen, [None, 5, 4, 2, 1])

    def test_the_beep_tones_are_valid_wav(self):
        import io
        import wave
        for kind, (hz, secs) in sound.TONES.items():
            w = wave.open(io.BytesIO(sound.tone_wav(hz, secs)))
            self.assertEqual(w.getnchannels(), 1)
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), secs, delta=0.01)

    def test_a_silent_beeper_just_counts(self):
        b = sound.SilentBeeper()
        b.beep("short")
        b.beep("long")
        self.assertEqual((b.count, b.log), (2, ["short", "long"]))
        sound.Beeper().beep("short")             # nunca falha, mesmo sem som


class TestSoundSettings(tg.GuiCase):
    def open_tab(self):
        self.pick_settings = None
        self.press(key.ESCAPE)
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Configurações sonoras")
        return scr

    def test_the_tab_lists_the_rules_and_the_actions(self):
        scr = self.open_tab()
        labels = [i.label for i in scr.list.items]
        self.assertIn("Bips", labels)
        self.assertIn("Últimos 5 s · 1 bip por segundo · em tudo", labels)
        buttons = [i.label for i in scr.list.items if i.button]
        for b in ("+ Nova regra", "Testar os bips", "Repor as de origem", "Guardar"):
            self.assertIn(b, buttons)

    def test_add_edit_and_delete_rules_then_save(self):
        scr = self.open_tab()
        self.pick("Nova regra")
        pop = self.screen()
        from velo.ui import sound_screens as ssc
        self.assertIsInstance(pop, ssc.SoundRulePopup)
        self.select("Quando")
        self.press(key.RIGHT)                    # Primeiros
        self.select("Segundos")
        self.app._on_text("10")
        self.select("Bips por segundo")
        self.app._on_text("0")
        self.pick("Guardar e sair")
        labels = [i.label for i in scr.list.items]
        self.assertIn("Primeiros 10 s · um só bip · em tudo", labels)
        self.assertTrue(scr.dirty)
        scr.list.select_data("rule:r1")
        self.press(key.DELETE)
        self.assertNotIn("Últimos 5 s · 1 bip por segundo · em tudo",
                         [i.label for i in scr.list.items])
        scr.save()
        saved = cues.rules(self.app.db)
        self.assertEqual([(r["when"], r["seconds"], r["per_s"]) for r in saved],
                         [("first", 10, 0)])

    def test_toggle_and_restore_defaults(self):
        scr = self.open_tab()
        scr.list.select_data("sound_on")
        self.press(key.RIGHT)
        scr.save()
        self.assertFalse(cues.enabled(self.app.db))
        self.assertFalse(self.app.new_cues().on)
        scr.list.select_data("sound_on")
        self.press(key.RIGHT)
        self.pick("Repor as de origem")
        scr.save()
        self.assertTrue(cues.enabled(self.app.db))
        self.assertEqual(cues.rules(self.app.db), cues.DEFAULT_RULES)

    def test_the_test_button_plays_through_the_beeper(self):
        scr = self.open_tab()
        self.app.beeper = sound.SilentBeeper()
        self.pick("Testar os bips")
        for _ in range(60):
            self.app._tick(0.5)                  # 30 s
        self.assertEqual(self.app.beeper.log.count("short"), 10)   # 5 no bloco + 5 no descanso
        self.assertEqual(self.app.beeper.log.count("long"), 2)


class TestGymSessionCues(tg.GuiCase):
    def _open(self, tiles=None):
        from velo.core import layouts
        if tiles is not None:
            layouts.save(self.app.db, "gym", [list(tiles)])
        self.app.beeper = sound.SilentBeeper()
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = ss.StrengthSessionScreen(self.app, wid)
        self.app.push(scr)
        return scr, layouts

    def test_there_is_no_clock_at_the_top(self):
        scr, _ = self._open()
        self.assertFalse(hasattr(scr, "clock"))

    def test_a_timed_rest_beeps_and_shows_the_countdown_in_the_centre(self):
        scr, layouts = self._open(["hr", "sets"])           # sem «Série / descanso» no ecrã
        self.assertFalse(scr.phase_time_on_screen())
        for _ in range(4):
            self.app._tick(0.5)
        self.press(key.SPACE)                    # Lap: descanso (de 30 s no 1.º exercício)
        s = scr.session
        self.app._tick(0.5)
        self.assertTrue(scr.notice.visible)      # sem a métrica, abre-se o aviso ao centro
        self.assertEqual(scr.notice.title.text, "DESCANSO")
        self.assertIn("A seguir", scr.notice.sub.text)
        left = s.rest_until - s.t
        self.app._tick(left - 3.2)               # faltam ~3 s
        self.assertIn(scr._cue_n, (3, 4))
        self.assertRegex(scr.notice.big.text, r"^0:0[0-4]$")
        for _ in range(8):
            self.app._tick(0.5)
        self.assertGreaterEqual(self.app.beeper.log.count("short"), 3)
        self.assertIn("long", self.app.beeper.log)

    def test_with_the_set_rest_tile_on_screen_there_is_no_popup(self):
        scr, _ = self._open(["hr", "phase_time"])
        self.assertTrue(scr.phase_time_on_screen())
        for _ in range(4):
            self.app._tick(0.5)
        self.press(key.SPACE)
        self.app._tick(0.5)
        self.assertFalse(scr.notice.visible)
        s = scr.session
        self.assertEqual(scr.tile_value("phase_time"), scr._phase_text(s.phase_seconds))
        self.app._tick(s.rest_until - s.t - 3.2)
        self.assertIn(scr._cue_n, (3, 4))
        self.assertFalse(scr.notice.visible)
        self.assertEqual(scr.tile_value("phase_time"), scr._phase_text(s.phase_seconds))

    def test_a_timed_set_counts_down_and_the_popup_names_it(self):
        from velo.core import layouts
        layouts.save(self.app.db, "gym", [["hr"]])
        self.app.beeper = sound.SilentBeeper()
        wid = next(w["id"] for w in gym.workouts(self.app.db, "strength")
                   if w["name"].startswith("Força A"))
        scr = ss.StrengthSessionScreen(self.app, wid)
        self.app.push(scr)
        s = scr.session
        k = next(i for i, ex in enumerate(s.items) if ex.name == "Prancha")
        self.press(key.SPACE)                              # Lap: acaba o 1.º, descanso
        scr._start_exercise(k)                             # Enter na prancha
        self.app._tick(0.5)
        self.assertEqual(s.item.name, "Prancha")
        self.assertTrue(s.timed_set)
        self.assertTrue(s.counting_down)
        left0 = s.phase_seconds
        self.assertLessEqual(left0, 45)
        self.app._tick(2.0)
        self.assertLess(s.phase_seconds, left0)            # para trás, como o descanso
        self.assertTrue(scr.notice.visible)
        self.assertEqual(scr.notice.title.text, "PRANCHA")
        self.assertIn("Série 1 de", scr.notice.sub.text)
        # os últimos 5 s têm bips, como no descanso
        self.app._tick(s.phase_seconds - 3.2)
        self.assertIn(scr._cue_n, (3, 4))

    def test_the_popup_goes_away_when_paused_or_finishing(self):
        scr, _ = self._open(["hr"])
        for _ in range(4):
            self.app._tick(0.5)
        self.press(key.SPACE)
        self.app._tick(0.5)
        self.assertTrue(scr.notice.visible)
        self.press(key.P)
        self.app._tick(0.5)
        self.assertFalse(scr.notice.visible)              # o PAUSA ocupa o centro
        self.assertTrue(scr.pause_popup)


class TestPlanCompleteStopsAndAsks(tg.GuiCase):
    def test_running_workout_done_opens_the_finish_dialog(self):
        from velo.ui import endurance_screens as es_
        scr = es_.EnduranceSession(self.app, "running")
        self.app.push(scr)
        scr.engine.start()
        scr._event("workout_done", {})
        self.assertTrue(scr.confirming)
        self.assertTrue(scr._flow_paused())                  # o tempo parou

    def test_rowing_workout_done_opens_the_finish_dialog(self):
        from velo.ui import rowing_screens as rs_
        self.app.set_rower(rio.SimulatedRower())
        scr = rs_.RowingSessionScreen(self.app)
        self.app.push(scr)
        self.press(key.SPACE)                                # começa a remar
        scr._event("workout_done", {})
        self.assertTrue(scr.confirming)

    def test_cycling_workout_done_opens_the_finish_dialog(self):
        from velo.ui import app as am
        wid = self.app.db.workouts()[0]["id"]
        ride = am.RideScreen(self.app, route_id=None, workout_id=wid, kind="workout",
                             ghosts=[], erg=True)
        self.app.push(ride)
        ride.preparing = False
        ride.update(0.5)
        ride.engine._emit("workout_done")
        ride.update(0.5)
        self.assertTrue(ride.hud.finish_dialog.visible)


class TestFreeWorkoutEditAfterwards(tg.GuiCase):
    def finished_free_session(self):
        from velo.ui import sport_screens as ss_
        wid = gym.workouts(self.app.db, "strength")[0]["id"]
        scr = ss_.StrengthSessionScreen(self.app, wid, free=True)
        self.app.push(scr)
        for _ in range(6):
            self.app._tick(0.5)
        self.press(key.SPACE)                                # Lap
        self.press(key.ESCAPE)                               # fecha a janela das repetições
        self.press(key.SPACE)                                # Lap: o exercício seguinte
        for _ in range(4):
            self.app._tick(0.5)
        res = scr.session.finish()
        return res["session_id"]

    def test_only_free_sessions_are_editable_afterwards(self):
        db = self.app.db
        sid = self.finished_free_session()
        self.assertTrue(st.is_free_session(db, sid))
        sets = db.conn.execute("SELECT id, reps FROM strength_sets WHERE session_id = ?",
                               (sid,)).fetchall()
        self.assertEqual(sets[0]["reps"], 0)
        self.assertTrue(st.edit_free_set(db, sets[0]["id"], reps=15, load_kg=20, rpe=7))
        row = db.conn.execute("SELECT reps, load_kg, rpe FROM strength_sets WHERE id = ?",
                              (sets[0]["id"],)).fetchone()
        self.assertEqual((row["reps"], row["load_kg"], row["rpe"]), (15, 20, 7))
        tot = db.conn.execute("SELECT total_reps, volume_kg FROM strength_sessions WHERE id = ?",
                              (sid,)).fetchone()
        self.assertEqual((tot["total_reps"], tot["volume_kg"]), (15, 300.0))
        # um treino planeado não se edita depois
        plan = st.StrengthSession(db, db.athlete(), gym.workouts(db, "strength")[0]["id"],
                                  out_dir=Path(self.tmp) / "str")
        plan.action()
        plan.update(10.0)
        plan.action()
        plan.finish()
        pid = plan.session_id
        self.assertFalse(st.is_free_session(db, pid))
        psets = db.conn.execute("SELECT id FROM strength_sets WHERE session_id = ?",
                                (pid,)).fetchall()
        self.assertFalse(st.edit_free_set(db, psets[0]["id"], reps=99))

    def test_the_analysis_has_an_edit_button_for_free_sessions(self):
        from velo.ui import session_analysis as sa_ui
        from velo.ui import strength_analysis_screens as sas
        sid = self.finished_free_session()
        an = sa_ui.SessionAnalysis(self.app, "strength", sid)
        self.app.push(an)
        an.tab_named("Análise do treino")
        self.assertIn("Editar séries", [i.label for i in an.list.items if i.button])
        self.pick("Editar séries")
        scr = self.screen()
        self.assertIsInstance(scr, sas.FreeSetsScreen)
        self.press(key.ENTER)                                # a 1.ª série
        pop = self.screen()
        self.assertIsInstance(pop, sas.FreeSetEditor)
        self.select("Repetições")
        self.app._on_text("12")
        self.pick("Guardar e sair")
        reps = self.app.db.conn.execute("SELECT reps FROM strength_sets WHERE session_id = ?"
                                        " ORDER BY id", (sid,)).fetchone()["reps"]
        self.assertEqual(reps, 12)


# ============================================================ teste da FC por ANT+

from velo.io import ant as ant_mod  # noqa: E402


class FakeStick:
    """Uma antena de brincar: abre, deixa abrir um canal e entrega pacotes de FC."""

    def __init__(self, pages=(), opens=True):
        self.pages, self.opens = list(pages), opens
        self._on_event = lambda k, d: None
        self.handler = None
        self.opened_channels = []
        self.closed = False

    def open(self):
        return self.opens

    def on_broadcast(self, channel, handler):
        self.handler = handler

    def open_channel(self, channel, device_type, *a, **kw):
        self.opened_channels.append((channel, device_type))
        self._on_event("ant_device_found", {"device": ant_mod.AntDiscovered(
            7125, ant_mod.DEVICE_HR, "ANT+ Cardio #7125")})

    def close(self):
        self.closed = True

    def feed(self, n, hr):
        for _ in range(n):
            self.handler(0, bytes((0x04, 0, 0, 0, 0, 0, 0, hr)))


class TestAntHrTest(tg.GuiCase):
    def run_test(self, per_second, hr, seconds=5, opens=True):
        stick = FakeStick(opens=opens)
        lines = []
        t = [0.0]

        def sleep(dt):
            t[0] += dt
            if stick.handler:
                stick.feed(per_second, hr)

        res = ant_mod.hr_test(seconds, out=lines.append, stick_factory=lambda: stick,
                              clock=lambda: t[0], sleep=sleep)
        return res, stick, lines

    def test_it_opens_a_single_hr_channel_and_reports_a_good_link(self):
        res, stick, lines = self.run_test(4, 72)
        self.assertEqual(stick.opened_channels, [(0, ant_mod.DEVICE_HR)])    # só o do cardio
        self.assertEqual(res["found"], "ANT+ Cardio #7125")
        self.assertEqual((res["min"], res["max"]), (72, 72))
        self.assertIn("ligação rádio está bem", res["verdict"])
        self.assertTrue(stick.closed)

    def test_few_packets_point_to_interference(self):
        res, _stick, _lines = self.run_test(1, 70)
        self.assertIn("interferência", res["verdict"])

    def test_nothing_received_says_the_watch_is_not_broadcasting(self):
        res, _stick, _lines = self.run_test(0, 0)
        self.assertEqual(res["packets"], 0)
        self.assertIn("não está a transmitir", res["verdict"])

    def test_zero_hr_means_the_sensor_has_not_measured_yet(self):
        res, _stick, _lines = self.run_test(4, 0)
        self.assertEqual(res["valid"], 0)
        self.assertIn("FC 0", res["verdict"])

    def test_a_stick_that_will_not_open_is_diagnosed(self):
        res, stick, lines = self.run_test(0, 0, opens=False)
        self.assertEqual(stick.opened_channels, [])
        self.assertTrue(res["verdict"])
        self.assertEqual(lines[-1], res["verdict"])

    def test_diagnose_tells_the_truth_about_the_stick(self):
        # sem antena (ou sem a biblioteca) diz porquê; nunca afirma «existe mas não abriu»
        # sem a ter tentado abrir
        msg = ant_mod.diagnose()
        self.assertTrue(msg)
        self.assertNotIn("Zwift", msg) if "não encontrada" in msg or "Falta" in msg else None


class TestDevicesShowLiveValues(tg.GuiCase):
    def test_a_connected_ant_hr_sensor_shows_its_bpm_and_then_no_data(self):
        a = self.app
        stick = ant_mod.AntStick()
        stick._ep_out = object()
        stick._send = lambda *x: None
        info = ant_mod.AntDiscovered(7125, ant_mod.DEVICE_HR, "ANT+ Cardio #7125")
        sensor = ant_mod.AntSensor(stick, 2, info, a.hub)
        a.hub.add_source(sensor, role=info.role)
        self.press(key.F4)                                    # Dispositivos
        scr = self.screen()
        row = lambda: next(i for i in scr.list.items if "ANT+ Cardio #7125" in i.label)  # noqa
        info_row = lambda: [i for i in scr.list.items  # noqa: E731
                            if "ANT+ Cardio #7125" in i.label][-1]   # a lista informativa do fim
        self.assertEqual(row().value, "sem dados")             # ligado, mas ainda mudo
        self.assertEqual(info_row().value, "ANT+ · sem dados")
        stick._dispatch(ant_mod.MSG_BROADCAST_DATA, bytes((2, 0x04, 0, 0, 0, 0, 0, 0, 61)))
        scr.update(1.2)                                        # refresca ao segundo
        self.assertEqual(row().value, "61 bpm")
        self.assertEqual(info_row().value, "ANT+ · 61 bpm")
        self.assertIn("61 bpm", scr.chrome.subtitle.text)
        self.assertEqual(a.hub.live_of("ant:7125:120")["hr"][0], 61)


class TestAntReadLoopDoesNotSpin(tg.GuiCase):
    """Uma antena que falha de vez não pode deixar a leitura a girar a 100 % de um núcleo."""

    def make_stick(self, ep, **attrs):
        stick = ant_mod.AntStick(on_event=lambda k, d: self.events.append((k, d)))
        stick._ep_in = ep
        stick._running = True
        for k, v in attrs.items():
            setattr(stick, k, v)
        return stick

    def setUp(self):
        super().setUp()
        self.events = []

    def test_a_hard_error_backs_off_and_finally_gives_up(self):
        reads = []

        class Broken:
            def read(self, n, timeout=0):
                reads.append(1)
                raise OSError("Input/Output Error")

        stick = self.make_stick(Broken(), ERROR_SLEEP_S=0.002, MAX_ERRORS=30)
        stick._read_loop()                                   # corre até desistir
        self.assertEqual(len(reads), 30)
        self.assertFalse(stick._running)
        self.assertTrue(any(k == "ant_error" for k, _ in self.events))

    def test_timeouts_are_normal_and_never_give_up(self):
        calls = [0]

        class Quiet:
            def read(self, n, timeout=0):
                calls[0] += 1
                if calls[0] > 100:
                    stick._running = False
                raise OSError(110, "Operation timed out")

        stick = self.make_stick(Quiet(), ERROR_SLEEP_S=0.5, MAX_ERRORS=3)
        stick._read_loop()
        self.assertEqual(calls[0], 101)                      # nunca desistiu nem dormiu
        self.assertFalse([e for e in self.events if e[0] == "ant_error"])

    def test_garbage_does_not_grow_the_buffer_without_limit(self):
        class Noise:
            n = 0

            def read(self, n, timeout=0):
                Noise.n += 1
                if Noise.n > 400:
                    stick._running = False
                return bytes((0xA4, 0xFF)) + bytes(60)       # SYNC + comprimento enorme, sem fim

        stick = self.make_stick(Noise())
        stick._read_loop()
        self.assertLessEqual(len(stick._buffer), stick.MAX_BUFFER + 64)

    def test_only_one_reopen_per_channel_at_a_time(self):
        stick = ant_mod.AntStick()
        stick._running = True
        stick._handlers[2] = lambda c, d: None
        started = []
        stick.reopen = lambda ch: started.append(ch) or __import__("time").sleep(0.2)
        for _ in range(5):                                   # cinco eventos «canal fechado» seguidos
            stick._dispatch(ant_mod.MSG_CHANNEL_EVENT, bytes((2, 1, ant_mod.EVENT_CHANNEL_CLOSED)))
        __import__("time").sleep(0.4)
        self.assertEqual(started, [2])
