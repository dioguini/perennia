"""Perennia: o nome novo (e os dados da VeloLocal), os temas, os objetivos
dos treinos e dos blocos, o feedback no fim das sessões cruzado com o
objetivo, o editor do ecrã de cada desporto, o calendário mensal e a
carga e prontidão."""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from velo.core import calendar_view as cv  # noqa: E402
from velo.core import feedback as fbm  # noqa: E402
from velo.core import layouts as lay  # noqa: E402
from velo.core import objectives as ob  # noqa: E402
from velo.core.blocks import Block, load_blocks  # noqa: E402
from velo.core.db import Database  # noqa: E402
from velo.gfx import theme  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import brief as br  # noqa: E402
from velo.ui import calendar_screens as cs  # noqa: E402
from velo.ui import feedback_screens as fs  # noqa: E402
from velo.ui import layout_screens as ls  # noqa: E402
from velo.ui import widgets  # noqa: E402


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestNameAndData(unittest.TestCase):
    def test_legacy_data_folder_and_database_are_kept(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            old = tmp / "velolocal"
            old.mkdir()
            Database(old / "velolocal.db").conn.close()
            env = dict(os.environ)
            os.environ.pop("PERENNIA_DATA_DIR", None)
            os.environ.pop("VELO_DATA_DIR", None)
            os.environ["XDG_DATA_HOME"] = str(tmp)
            try:
                if os.name != "nt" and sys.platform != "darwin":
                    self.assertEqual(app_mod._default_data_dir(), old)
                path = app_mod._database_path(old)
                self.assertEqual(path.name, "perennia.db")
                self.assertTrue(path.exists())
                self.assertFalse((old / "velolocal.db").exists())
            finally:
                os.environ.clear()
                os.environ.update(env)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_activity_names_use_the_new_prefix_and_read_the_old(self):
        from velo.core import naming
        self.assertEqual(naming.PREFIX, "perennia")
        self.assertEqual(naming.pretty("velolocal_2026-10-30_Força-A"), "Força A")
        self.assertEqual(naming.pretty("perennia_2026-10-30_Força-A"), "Força A")


class TestThemes(unittest.TestCase):
    def tearDown(self):
        theme.apply(theme.DEFAULT)

    def test_every_theme_has_every_role_and_no_black(self):
        self.assertGreaterEqual(len(theme.THEMES), 3)
        for p in theme.THEMES.values():
            for role in ("bg", "panel", "text", "header", "accent"):
                self.assertEqual(len(getattr(p, role)), 3)
            self.assertGreater(sum(p.bg), 3 * 40, f"{p.key}: fundo demasiado escuro")
            if p.light:          # texto escuro em fundo claro, com contraste
                self.assertGreater(sum(p.bg) - sum(p.text), 400)

    def test_apply_rebinds_the_short_names(self):
        theme.apply("perennia")
        before = widgets.TEXT
        theme.apply("ardosia")
        self.assertNotEqual(widgets.TEXT, before)
        self.assertEqual(widgets.TEXT[:3], theme.THEMES["ardosia"].text)
        from velo.gfx import hud
        self.assertEqual(hud.TEXT[:3], theme.THEMES["ardosia"].text)
        theme.apply("perennia")
        self.assertEqual(widgets.TEXT[:3], theme.THEMES["perennia"].text)

    def test_zone_colours_are_darkened_as_text_on_light_themes(self):
        theme.apply("perennia")
        self.assertLess(sum(theme.ink((228, 190, 44))[:3]), sum((228, 190, 44)))
        theme.apply("ardosia")
        self.assertEqual(theme.ink((228, 190, 44))[:3], (228, 190, 44))


class TestThemeGui(tg.GuiCase):
    def tearDown(self):
        theme.apply(theme.DEFAULT)
        super().tearDown()

    def test_caption_and_theme_switch_from_settings(self):
        self.assertTrue(self.app.window.caption.startswith("Perennia"))
        self.pick("Definições")
        self.select("Tema")
        self.press(key.RIGHT)
        self.assertEqual(self.app.db.get("theme"), theme.names()[1])
        self.assertIs(theme.P, theme.THEMES[theme.names()[1]])
        # o ecrã volta a ser construído: inicial + definições, no mesmo separador
        self.assertIsInstance(self.app.stack[0], app_mod.HomeScreen)
        self.assertIsInstance(self.screen(), app_mod.SettingsScreen)
        self.assertTrue(any("Tema" in i.label for i in self.screen().list.items))
        self.assertEqual(self.app.topbar.bg.color, theme.P.header)


class TestObjectives(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "perennia.db")
        from velo.core import endurance, workout_library
        workout_library.seed(self.db)
        endurance.seed(self.db)

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wid(self, name: str) -> str:
        return next(w["id"] for w in self.db.workouts() if w["name"] == name)

    def test_library_workout_has_written_goal_blocks_and_targets(self):
        b = ob.workout_brief(self.db, "cycling", self._wid("VO2máx 5×4"))
        self.assertTrue(b.goal_written)
        self.assertIn("115", b.goal)
        reps = [x for x in b.blocks if x.repeat == 5]
        self.assertEqual(len(reps), 1)
        self.assertIn("W", reps[0].target)
        self.assertEqual(b.blocks[0].name, "Aquecimento")
        self.assertEqual(b.blocks[-1].name, "Arrefecimento")
        self.assertTrue(all(x.goal for x in b.blocks))
        self.assertIsNotNone(b.target_rpe)
        self.assertIn("esforço percebido", b.intensity)

    def test_auto_goal_from_structure_when_nothing_is_written(self):
        blocks = [Block("warmup", "time", 300, 50, 70), Block("active", "time", 1200, 68),
                  Block("cooldown", "time", 300, 55)]
        b = ob.build(self.db, "cycling", None, "Sem nome", blocks)
        self.assertFalse(b.goal_written)
        self.assertIn("aeróbia", b.goal)
        self.assertEqual(b.blocks[1].name, "Principal")
        self.assertIn("Z2", b.blocks[1].goal)

    def test_running_targets_are_paces_and_ranges(self):
        from velo.core import endurance as en
        wid = next(w["id"] for w in en.workouts(self.db, "running") if "800" in w["name"])
        b = ob.workout_brief(self.db, "running", wid)
        eff = next(x for x in b.blocks if x.repeat == 6)
        self.assertIn("/km", eff.target)
        self.assertNotIn("→", eff.target)

    def test_goals_are_saved_per_workout_and_block(self):
        wid = self._wid("Sweet spot 2×20")
        name, _d, _m, blocks = load_blocks(self.db, "cycling", wid)
        ob.save(self.db, "cycling", wid, "Subir a FTP", [{"name": "", "goal": ""}] * 2 +
                [{"name": "Bloco A", "goal": "Constante a 90 %"}])
        b = ob.workout_brief(self.db, "cycling", wid)
        self.assertEqual(b.goal, "Subir a FTP")
        self.assertEqual(b.raw_blocks[2].name, "Bloco A")
        self.assertEqual(b.raw_blocks[2].goal, "Constante a 90 %")

    def test_block_at_follows_the_clock(self):
        b = ob.workout_brief(self.db, "cycling", self._wid("Limiar 2×20"))
        i, blk = ob.block_at(b, 0)
        self.assertEqual(i, 0)
        i2, _ = ob.block_at(b, b.raw_blocks[0].seconds + 1)
        self.assertEqual(i2, 1)
        self.assertIsNone(ob.block_at(b, b.seconds + 10)[1])


class TestBriefScreens(tg.GuiCase):
    def test_library_opens_the_brief_then_starts(self):
        self.pick("Lista de treinos")
        self.pick("VO2máx 5×4")
        scr = self.screen()
        self.assertIsInstance(scr, br.CyclingBrief)
        self.app._on_draw()
        self.assertTrue(any("Alvo" in x for x in self.labels()))
        self.pick("Começar")
        self.assertIsInstance(self.screen(), app_mod.WorkoutRouteChoice)

    def test_goal_editor_writes_the_goal(self):
        self.pick("Lista de treinos")
        self.pick("Tempo 3×15")
        self.pick("Objetivos")
        self.select("Objetivo do treino")
        for _ in range(200):
            self.press(key.BACKSPACE)
        self.type("Ritmo de estrada")
        self.pick("Guardar")
        wid = self.screen().wid
        self.assertEqual(ob.stored(self.app.db, "cycling", wid)["goal"], "Ritmo de estrada")
        self.assertEqual(self.screen().brief_data.goal, "Ritmo de estrada")

    def test_ride_hud_shows_the_block_goal(self):
        self.pick("Lista de treinos")
        self.pick("Limiar 2×20")
        self.pick("Começar")
        self.pick("Serra de Teste")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(20):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        self.assertIsNotNone(ride.hud.brief)
        text = ride.hud.block_goal_full(0)
        self.assertIn("Aquecimento", text)
        self.assertIn("Alvo", text)

    def test_builder_saves_workout_and_block_goals(self):
        self.pick("Construtor de treinos")
        self.pick("Novo treino")
        b = self.screen()
        b.sel = 1
        b.enter()
        self.select("Objetivo do bloco")
        self.type("Z2 sem picos")
        self.select("Objetivo do treino")
        self.type("Base aeróbia")
        self.pick("Guardar")
        saved = ob.stored(self.app.db, "cycling", b.wid)
        self.assertEqual(saved["goal"], "Base aeróbia")
        self.assertEqual(saved["blocks"][1]["goal"], "Z2 sem picos")


class TestFeedback(tg.GuiCase):
    def _ride_workout(self, name: str, seconds: float):
        self.pick("Lista de treinos")
        self.pick(name)
        self.pick("Começar")
        self.pick("Sem rota")
        self.pick("Começar")
        ride = self.screen()
        ride.preparing = False
        for _ in range(int(seconds / 0.25)):
            self.app.hub.tick(0.25)
            ride.update(0.25)
        return ride

    def test_finishing_asks_for_feedback_and_saves_the_analysis(self):
        self.app.db.set("ask_feedback", True)
        self._ride_workout("Recuperação ativa", 120)
        self.press(key.F10, key.ENTER)
        scr = self.screen()
        self.assertIsInstance(scr, fs.FeedbackScreen)
        self.assertIsNotNone(scr.brief)               # o treino prescrito
        self.app._on_text("3")                         # RPE 3
        self.press(key.DOWN)
        self.app._on_text("2")                         # dores 2
        self.press(key.DOWN, key.RIGHT, key.RIGHT, key.RIGHT, key.RIGHT)   # sensação: boa
        self.press(key.DOWN, key.RIGHT)                # objetivo: sim
        self.press(key.DOWN)
        self.app._on_text("Pernas pesadas")
        self.app._on_key_press(key.S, key.MOD_CTRL)
        got = fbm.get(self.app.db, "ride", scr.sid)
        self.assertEqual(got["rpe"], 3)
        self.assertEqual(got["pain"], 2)
        self.assertEqual(got["feel"], 4)
        self.assertEqual(got["goal_met"], "yes")
        self.assertEqual(got["comment"], "Pernas pesadas")
        self.assertTrue(got["verdict"])
        titles = [t for t, _ in got["analysis"]["sections"]]
        self.assertEqual(titles[:3], ["Sessão", "Execução", "Objetivo"])
        self.press(key.ESCAPE)
        summ = self.screen()
        self.assertIsInstance(summ, app_mod.SummaryScreen)
        self.assertEqual(summ.list.items[0].label, "Como correu esta sessão?")
        self.assertEqual(summ.list.items[0].detail, got["verdict"])
        # não volta a perguntar ao regressar ao resumo
        summ.enter()
        self.assertIs(self.screen(), summ)

    def test_analysis_crosses_goal_and_feedback(self):
        self._ride_workout("Recuperação ativa", 60)
        self.press(key.F10, key.ENTER)
        rid = self.screen().result["ride_id"]
        db = self.app.db
        sess = fbm.load_session(db, "ride", rid)
        self.assertEqual(sess.sport, "cycling")
        self.assertTrue(sess.samples)
        brief = fbm.prescribed(db, sess)
        # curta de propósito: a duração prevista não foi cumprida
        res = fbm.save(db, "ride", rid, rpe=3, pain=1, goal_met="yes")
        self.assertEqual(res["useful"], "no")
        self.assertIn("duração", " ".join(t for _, t in res["sections"]))
        # se a sessão tivesse sido completa e mais dura do que o previsto
        sess.moving_s = brief.seconds
        harder = fbm.analyse(db, sess, {"rpe": int(brief.target_rpe) + 4, "pain": 0})
        self.assertIn("mais dura", harder["verdict"])
        hurt = fbm.analyse(db, sess, {"rpe": 3, "pain": 8})
        self.assertEqual(hurt["tone"], "bad")
        self.assertIn("dores", hurt["verdict"].lower())
        self.assertEqual(len(fbm.all_feedback(db)), 1)

    def test_execution_counts_time_inside_each_block(self):
        b = ob.Brief("cycling", "x", "g", "", 3, 600, 0, 0,
                     raw_blocks=[ob.BriefBlock("A", "", "", 300, None, 60, None),
                                 ob.BriefBlock("B", "", "", 300, None, 100, None)])
        samples = [(t, 60.0 if t < 300 else 70.0, 0, 120) for t in range(600)]
        sess = fbm.Session("ride", "x", "cycling", "x", "2026-10-31T10:00:00Z", 600, 600,
                           samples=samples)
        ex = fbm.execution(sess, b)
        self.assertAlmostEqual(ex["in_target_s"] / ex["target_s"], 0.5, delta=0.03)
        self.assertAlmostEqual(ex["completion"], 1.0)


class TestLayouts(tg.GuiCase):
    def test_rowing_layout_place_and_swap(self):
        db = self.app.db
        ed = ls.LayoutEditor(self.app, "rowing")
        self.app.push(ed)
        ed.place("wkg", 0, 0)
        self.assertEqual(db.get("row_fields")[0], "wkg")
        first, second = lay.load(db, "rowing")[0][:2]
        ed.swap((0, 0), (0, 1))
        self.assertEqual(lay.load(db, "rowing")[0][:2], [second, first])
        # uma métrica que já estava no ecrã muda de sítio (não fica repetida)
        ed.place("wkg", 0, 5)
        flat = [m for m in db.get("row_fields") if m == "wkg"]
        self.assertEqual(len(flat), 1)

    def test_drag_a_chip_onto_a_slot(self):
        ed = ls.LayoutEditor(self.app, "running")
        self.app.push(ed)
        k, cx, cy, cw, ch = next(c for c in ed.chip_geo if c[0] == "max_hr")
        g, i, sx, sy, tw, th = ed.slot_geo[0]
        self.app._on_mouse_press(int(cx + 3), int(cy + 3), 1, 0)
        self.app._on_mouse_drag(int(sx + 10), int(sy + 10), 5, 5)
        self.app._on_mouse_release(int(sx + 10), int(sy + 10))
        self.assertEqual(lay.keys(self.app.db, "running")[0], "max_hr")

    def test_running_session_uses_the_layout(self):
        from velo.ui import endurance_screens as es
        lay.save(self.app.db, "running", [["speed", "hr", None, "time", None, None, None,
                                           None]])
        scr = es.EnduranceSession(self.app, "running")
        self.app.push(scr)
        caps = [c for c, _ in scr.cells_data()]
        self.assertEqual(caps[:2], ["Velocidade", "FC"])
        self.assertEqual(caps[2], "")

    def test_cycling_boxes_move_and_swap(self):
        db = self.app.db
        ed = ls.LayoutEditor(self.app, "cycling")
        self.app.push(ed)
        m = ed.groups[0][0]
        ed.swap((0, 0), (1, 0))                    # passa para a caixa 2
        self.assertEqual(lay.load(db, "cycling")[1][0], m)
        self.assertNotIn(m, lay.load(db, "cycling")[0])
        g0, g1 = lay.load(db, "cycling")[0], lay.load(db, "cycling")[1]
        ed.swap_boxes(0, 1)
        self.assertEqual(lay.load(db, "cycling")[0], g1)
        self.assertEqual(lay.load(db, "cycling")[1], g0)
        ed._armed_reset = True
        self.press(key.R)
        from velo.core.boxes import DEFAULT_BOXES
        self.assertEqual(lay.load(db, "cycling")[0], DEFAULT_BOXES[0])

    def test_gym_tiles_follow_the_layout(self):
        lay.save(self.app.db, "gym", [["volume", "session_time", "hr", "sets"]])
        self.press(key.ESCAPE)
        self.pick("Ginásio")
        self.pick("Sessão de treino")
        self.pick("Força")
        self.pick("Força A")
        self.pick("Começar")
        scr = self.screen()
        self.app._on_draw()
        scr.update(0.5)
        caps = [cap.text for _bg, cap, _v in scr.tiles]
        self.assertEqual(caps[0], "VOLUME")
        self.assertEqual(caps[1], "TEMPO TOTAL")

    def test_settings_open_the_editor(self):
        self.pick("Definições")
        self.pick("Ecrã da sessão")
        self.assertIsInstance(self.screen(), ls.LayoutSportPicker)
        self.pick("Remo")
        self.assertIsInstance(self.screen(), ls.LayoutEditor)
        self.press(key.ENTER)                         # escolher pela lista
        self.assertIsInstance(self.screen(), ls.MetricPicker)
        self.pick("W/kg")
        self.assertEqual(lay.keys(self.app.db, "rowing")[0], "wkg")


class TestCalendar(tg.GuiCase):
    def _ride_on(self, day: date, tss: float = 50, wid: str | None = None) -> None:
        when = datetime(day.year, day.month, day.day, 10, tzinfo=timezone.utc)
        self.app.db.conn.execute(
            "INSERT INTO rides(id, kind, mode, status, started_at, elapsed_s, moving_s, tss,"
            " ftp_at_ride_w, weight_at_ride_kg, name, workout_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"r{day.isoformat()}", "route", "alone", "completed", _iso(when), 3600, 3600, tss,
             250, 72, "perennia_x_teste", wid))
        self.app.db.conn.commit()

    def test_month_grid_and_week_summary(self):
        weeks = cv.weeks_of(2026, 10)
        self.assertEqual(weeks[0][0], date(2026, 9, 28))      # segunda-feira
        self.assertEqual(weeks[-1][-1].weekday(), 6)
        today = date.today()
        self._ride_on(today, 60)
        data = cv.month_data(self.app.db, today.year, today.month)
        self.assertEqual(len(data["by_day"][today]), 1)
        wi = next(i for i, wk in enumerate(data["weeks"]) if today in wk)
        s = data["summaries"][wi]
        self.assertEqual(s.sessions, 1)
        self.assertAlmostEqual(s.load, 60)
        self.assertIsNotNone(s.ctl)

    def test_plan_a_workout_and_mark_it_done(self):
        db = self.app.db
        today = date.today()
        w = db.workouts()[0]
        cv.plan_add(db, today, "cycling", w["id"], w["name"])
        plan = cv.planned_for(db, today)
        self.assertEqual(len(plan), 1)
        self.assertFalse(plan[0].done)
        self.assertGreater(plan[0].seconds, 0)
        self._ride_on(today, 40, w["id"])
        self.assertTrue(cv.planned_for(db, today)[0].done)

    def test_calendar_screen_navigation_and_planning(self):
        self.press(key.ESCAPE)
        self.pick("Calendário")
        scr = self.screen()
        self.assertIsInstance(scr, cs.CalendarScreen)
        today = date.today()
        self.press(key.RIGHT)
        self.assertEqual(scr.sel, today + timedelta(days=1))
        before = (scr.year, scr.month)
        self.press(key.PAGEDOWN)
        self.assertEqual((scr.year, scr.month), cv.shift_month(*before, 1))
        self.press(key.T)
        self.assertEqual(scr.sel, today)
        self.press(key.ENTER)
        day = self.screen()
        self.assertIsInstance(day, cs.DayScreen)
        self.pick("Planear um treino")
        self.pick("Ciclismo")
        self.pick("Sweet spot 2×20")
        self.assertIs(self.screen(), day)
        self.assertTrue(any("Sweet spot 2×20" in i.label for i in day.list.items))
        self.select("Planeado")
        self.press(key.DELETE)
        self.assertFalse(any("Planeado" in i.label for i in day.list.items))
        self.app._on_draw()

    def test_mouse_selects_then_opens_a_day(self):
        self.press(key.ESCAPE)
        self.pick("Calendário")
        scr = self.screen()
        d, cx, cy, cw, ch = next(g for g in scr.cell_geo
                                 if g[0] != scr.sel and g[0].month == scr.month)
        self.app._on_mouse_press(int(cx + cw / 2), int(cy + ch / 2), 1, 0)
        self.assertEqual(scr.sel, d)
        self.app._on_mouse_press(int(cx + cw / 2), int(cy + ch / 2), 1, 0)
        self.assertIsInstance(self.screen(), cs.DayScreen)


class TestLoadReadiness(tg.GuiCase):
    def test_load_readiness_screen(self):
        db = self.app.db
        for k in range(20, 0, -1):
            when = datetime.now(timezone.utc) - timedelta(days=k)
            db.conn.execute(
                "INSERT INTO rides(id, kind, mode, status, started_at, elapsed_s, moving_s, tss,"
                " ftp_at_ride_w, weight_at_ride_kg) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"x{k}", "route", "alone", "completed", _iso(when), 3600, 3600, 60, 250, 72))
        db.conn.commit()
        from velo.ui import load_screens
        self.press(key.ESCAPE)
        self.pick("Estatísticas gerais")
        self.pick("Carga e prontidão")
        scr = self.screen()
        self.assertIsInstance(scr, load_screens.LoadReadinessScreen)
        self.assertTrue(scr.series)
        self.assertGreater(scr.series[-1]["ctl"], 0)
        self.assertTrue(scr.kpis[0].text.startswith("Fitness"))
        self.press(key.RIGHT)
        self.assertEqual(scr.days, 90)
        self.app._on_draw()


if __name__ == "__main__":
    unittest.main()
