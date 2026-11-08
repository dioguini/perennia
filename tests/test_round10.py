"""Ronda 10: terminar sessões como no ciclismo, etiquetas e tipos de sessão, Longevidade,
GPX Conversor, grupos musculares e disciplinas, CSV, simuladores."""
from __future__ import annotations

import importlib
import math
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.core import csv_sync as cs  # noqa: E402
from velo.core import fit  # noqa: E402
from velo.core import gpx_convert as gc  # noqa: E402
from velo.core import gym, muscles  # noqa: E402
from velo.core import longevity as lg  # noqa: E402
from velo.core import tags as tg_core  # noqa: E402
from velo.core.db import Database  # noqa: E402
from velo.io import rower as rio  # noqa: E402
from velo.io.sim import SimulatedTrainer, SimulatedTreadmill  # noqa: E402
from velo.ui import builder_screens as bs  # noqa: E402
from velo.ui import endurance_screens as es  # noqa: E402
from velo.ui import rowing_screens as rs  # noqa: E402
from velo.ui import tag_popup as tagpop  # noqa: E402


def fresh_db() -> Database:
    return Database(Path(tempfile.mkdtemp()) / "x.db")


# ============================================================ simuladores


class TestSimulators(tg.GuiCase):
    def test_each_simulator_gives_only_its_own_data(self):
        t = SimulatedTrainer(base_power=200)
        t.connect() if hasattr(t, "connect") else None
        r = t.reading() if hasattr(t, "reading") else None
        self.assertIsNone(getattr(r, "hr_bpm", None))               # o rolo não dá FC
        rower = rio.SimulatedRower()
        self.assertIsNone(getattr(rower, "hr_bpm", None))
        tm = SimulatedTreadmill(20.0, 15.0)
        self.assertEqual(tm.name, "SEM HARDWARE - PASSADEIRA")
        tm.set_speed(10.0)
        for _ in range(40):
            tm.tick(0.5)
        rd = tm.reading()
        self.assertAlmostEqual(rd.speed_mps * 3.6, 10.0, delta=0.6)
        self.assertIsNone(getattr(rd, "hr_bpm", None))

    def test_device_screen_lists_the_treadmill(self):
        self.press(key.ESCAPE)
        self.pick("Dispositivos")
        self.assertIn("SEM HARDWARE - PASSADEIRA", [i.label for i in self.screen().list.items])


# ================================================== terminar como no ciclismo


class TestFinishLikeCycling(tg.GuiCase):
    def _running(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        scr = self.screen()
        self.assertIsInstance(scr, es.EnduranceSession)
        self.press(key.SPACE)
        for _ in range(40):
            self.app._tick(0.5)
        return scr

    def test_esc_pauses_and_f10_asks_with_the_same_dialog(self):
        scr = self._running()
        self.press(key.ESCAPE)
        self.assertTrue(scr.engine.paused)
        self.assertIs(self.screen(), scr)                  # Esc não termina
        self.press(key.P)                                  # P retoma
        self.assertFalse(scr.engine.paused)
        self.press(key.F10)
        self.assertTrue(scr.finish_dialog.visible)
        self.assertEqual(scr.finish_dialog.title.text, "Terminar a sessão?")
        self.assertTrue(scr.engine.paused)                 # enquanto pergunta, para
        self.press(key.N)                                  # N: volta e retoma
        self.assertFalse(scr.finish_dialog.visible)
        self.assertFalse(scr.engine.paused)

    def test_d_discards_without_saving(self):
        scr = self._running()
        sid = scr.engine.session_id
        self.press(key.F10, key.D)
        self.assertNotIsInstance(self.screen(), es.EnduranceSession)
        row = self.app.db.conn.execute("SELECT 1 FROM endurance_sessions WHERE id = ?",
                                       (sid,)).fetchone()
        self.assertIsNone(row)

    def test_yes_opens_the_tag_window_then_the_summary(self):
        scr = self._running()
        self.press(key.F10, key.ENTER)
        pop = self.screen()
        self.assertIsInstance(pop, tagpop.SessionTagsPopup)
        labels = [i.label for i in pop.list.items]
        for want in ("Tipo de treino", "Tipo de sessão", "+ Adicionar etiqueta",
                     "Guardar e terminar"):
            self.assertIn(want, labels)
        sess_type = next(i for i in pop.list.items if i.label == "Tipo de sessão").value
        self.assertIn("Perennia", sess_type)
        self.assertIn("Indoor Running", sess_type)
        self.assertNotIn("Virtual", sess_type)             # a passadeira não é virtual
        self.press(key.ENTER)                              # «Guardar e terminar»
        summ = self.screen()
        self.assertIsInstance(summ, es.EnduranceSummary)
        self.assertEqual(summ.chrome.title.text, "Sessão concluída")
        self.assertNotIn("Voltar ao remo", [i.label for i in summ.list.items])
        self.assertTrue(summ.result["tags"]["session"])

    def test_back_from_the_tag_window_returns_to_the_session(self):
        scr = self._running()
        self.press(key.F10, key.ENTER)
        self.assertIsInstance(self.screen(), tagpop.SessionTagsPopup)
        self.press(key.ESCAPE)
        self.assertIs(self.screen(), scr)
        self.assertFalse(scr.engine.paused)                # retomou

    def test_rowing_uses_the_same_flow(self):
        self.press(key.ESCAPE)
        self.pick("Remo")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        self.pick("SEM HARDWARE - Remo")
        self.press(key.ESCAPE)
        self.pick("Começar")
        ses = self.screen()
        self.assertIsInstance(ses, rs.RowingSessionScreen)
        for _ in range(60):
            ses.update(0.5)
        self.press(key.ESCAPE)
        self.assertTrue(ses.engine.manual_pause)
        self.press(key.F10)
        self.assertTrue(ses.finish_dialog.visible)
        self.press(key.ENTER, key.ENTER)
        self.assertIsInstance(self.screen(), rs.RowSummaryScreen)


# ============================================================== etiquetas


class TestTags(tg.GuiCase):
    def test_effort_suggests_the_type(self):
        self.assertEqual(tg_core.suggest_type(0.45), "recovery")
        self.assertEqual(tg_core.suggest_type(0.65), "endurance")
        self.assertEqual(tg_core.suggest_type(0.82), "tempo")
        self.assertEqual(tg_core.suggest_type(0.95), "threshold")
        self.assertEqual(tg_core.suggest_type(1.05), "vo2max")
        self.assertEqual(tg_core.suggest_type(1.3), "anaerobic")
        self.assertEqual(tg_core.suggest_type(0.9, variability=1.3), "work")
        self.assertEqual(tg_core.suggest_for({"load": 70, "moving_s": 3600}), "tempo")

    def test_session_type_tags_and_virtual(self):
        self.assertEqual(tg_core.session_type_tags("running"), ["Perennia", "Indoor Running"])
        self.assertEqual(tg_core.session_type_tags("running", True),
                         ["Perennia", "Virtual Running", "Indoor Running"])
        self.assertEqual(tg_core.session_type_tags("cycling", True),
                         ["Perennia", "Virtual Cycling", "Indoor Cycling"])
        self.assertEqual(tg_core.session_type_tags("rowing"), ["Perennia", "Indoor Rowing"])
        self.assertEqual(tg_core.sub_sport("running"), tg_core.SUB_TREADMILL)
        self.assertEqual(tg_core.sub_sport("running", True), tg_core.SUB_VIRTUAL)
        self.assertEqual(tg_core.sub_sport("cycling"), tg_core.SUB_INDOOR_CYCLING)
        self.assertFalse(tg_core.is_virtual("running", False))
        self.assertTrue(tg_core.is_virtual("cycling", True))

    def test_known_tags_and_autodetection(self):
        db = self.app.db
        tg_core.save(db, "cycling", "s1", {"workout_type": "tempo", "session": ["Perennia"],
                                           "custom": ["Pré-prova", "Rolo novo"]})
        self.assertIn("Pré-prova", tg_core.known_tags(db))
        self.assertEqual(tg_core.match(db, "pre-p"), ["Pré-prova"])        # sem acentos
        self.assertEqual(tg_core.normalize(db, "  pre-prova "), "Pré-prova")
        self.assertEqual(tg_core.load(db, "cycling", "s1")["custom"], ["Pré-prova", "Rolo novo"])
        self.assertIn("Tempo", tg_core.fit_text(tg_core.load(db, "cycling", "s1")))

    def test_add_tag_popup_suggests_existing_and_creates_new(self):
        db = self.app.db
        tg_core.save(db, "cycling", "s1", {"custom": ["Pré-prova"]})
        got = []
        pop = tagpop.AddTagPopup(self.app, [], got.append)
        self.app.push(pop)
        pop.search_set("pre")
        labels = [i.label for i in pop.list.items]
        self.assertIn("Pré-prova", labels)                  # a existente aparece
        self.assertTrue(any(lab.startswith("Criar") for lab in labels))
        pop.search_set("Nova coisa")
        self.pick("Criar «Nova coisa»")
        self.assertEqual(got, ["Nova coisa"])

    def test_tags_go_into_the_fit_and_the_database(self):
        db = self.app.db
        db.set("session_countdown_s", 0)
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        scr = self.screen()
        self.press(key.SPACE)
        for _ in range(60):
            self.app._tick(0.5)
        self.press(key.F10, key.ENTER)
        pop = self.screen()
        pop.info["custom"] = ["Pré-prova"]
        pop.info["workout_type"] = "threshold"
        pop._done()
        summ = self.screen()
        path = summ.result["fit_path"]
        msgs = dict(fit.read_messages(path)) if False else None
        raw = Path(path).read_bytes()
        self.assertIn("Pré-prova".encode("utf-8"), raw)     # o nome do perfil leva as etiquetas
        self.assertIn(b"Indoor Running", raw)
        info = tg_core.load(db, "running", summ.result["session_id"])
        self.assertEqual(info["workout_type"], "threshold")
        self.assertEqual(info["custom"], ["Pré-prova"])
        _ = scr

    def test_cycling_route_session_is_virtual_and_indoor(self):
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(40):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        self.press(key.F10, key.ENTER, key.ENTER)
        summ = self.screen()
        info = summ.result["tags"]
        self.assertEqual(info["session"], ["Perennia", "Virtual Cycling", "Indoor Cycling"])
        self.assertIn(info["workout_type"], tg_core.TYPE_KEYS)       # sessão livre: pelo esforço
        raw = Path(summ.result["fit_path"]).read_bytes()
        self.assertIn(b"Indoor Cycling", raw)
        self.assertIn(b"Virtual Cycling", raw)
        self.assertEqual(self.app.db.conn.execute(
            "SELECT COUNT(*) FROM session_tags WHERE sport='cycling'").fetchone()[0],
            1 + len(info["session"]) + len(info["custom"]))

    def test_builder_has_a_workout_type_dropdown_above_the_name(self):
        b = bs.BlockBuilder(self.app, "cycling", None, control="erg")
        self.app.push(b)
        heads = [b.list.items[i].label for i in b.list.head_indices()]
        self.assertEqual(heads[0], "Tipo de treino")
        self.assertIn("Automático", next(i for i in b.list.items
                                         if i.label == "Tipo de treino").value)
        self.select("Tipo de treino")
        self.press(key.RIGHT)                               # ←/→ percorre os tipos
        self.assertEqual(b.wtype, "recovery")
        self.press(key.ENTER)                               # Enter abre a lista com pesquisa
        from velo.ui.pickers import ChoicePopup
        self.assertIsInstance(self.screen(), ChoicePopup)
        self.press(key.ESCAPE)
        b.name = "Meu treino"
        b._save()
        self.assertEqual(tg_core.workout_type(self.app.db, "cycling", b.wid), "recovery")
        again = bs.BlockBuilder(self.app, "cycling", b.wid)
        self.assertEqual(again.wtype, "recovery")

    def test_workout_type_wins_over_the_suggestion(self):
        db = self.app.db
        tg_core.set_workout_type(db, "cycling", "w1", "race_warmup")
        info = tg_core.defaults(db, "cycling", workout_id="w1", summary={"load": 10,
                                                                         "moving_s": 3600})
        self.assertEqual(info["workout_type"], "race_warmup")
        free = tg_core.defaults(db, "cycling", summary={"load": 10, "moving_s": 3600})
        self.assertEqual(free["workout_type"], "recovery")


# ============================================================ longevidade


def add_endurance(db, sid: str, day: str, zones: list[float], sport: str = "running") -> None:
    db.conn.execute(
        "INSERT INTO endurance_sessions (id, sport, status, started_at, moving_s, elapsed_s,"
        " hr_zone_s) VALUES (?,?,?,?,?,?,?)",
        (sid, sport, "completed", day + "T10:00:00.000Z", sum(zones), sum(zones),
         __import__("json").dumps(zones)))
    db.conn.commit()


class TestLongevityCore(tg.GuiCase):
    def test_empty_database_is_zero_and_all_periods_exist(self):
        res = lg.compute(self.app.db)
        self.assertEqual(list(res), [k for k, _d in lg.PERIODS])
        self.assertEqual([k for k, _d in lg.PERIODS][:3], ["1d", "1w", "1m"])
        self.assertEqual(len(lg.PERIODS), 13)
        self.assertTrue(all(v["index"] == 0 for v in res.values()))

    def test_z2_session_is_100_percent_aerobic(self):
        db = self.app.db
        add_endurance(db, "e1", "2026-11-01", [0, 3600, 0, 0, 0])
        mine = next(d for d in lg.all_doses(db) if d.sid == "e1")
        self.assertEqual(lg.shares(mine.mins), {"aerobic": 100.0})

    def test_vo2_plus_z2_gives_aerobic_and_vo2max(self):
        db = self.app.db
        add_endurance(db, "e2", "2026-11-01", [0, 1800, 0, 0, 600])
        sh = lg.shares(next(d for d in lg.all_doses(db) if d.sid == "e2").mins)
        self.assertEqual(set(sh), {"aerobic", "vo2max"})
        self.assertAlmostEqual(sum(sh.values()), 100.0)

    def test_more_training_raises_the_index_and_it_saturates(self):
        db = self.app.db
        from datetime import date
        day = date.today().isoformat()
        add_endurance(db, "a", day, [0, 1800, 0, 0, 0])
        small = lg.compute(db)["1w"]["index"]
        for i in range(6):
            add_endurance(db, f"b{i}", day, [0, 3600, 0, 0, 600])
        big = lg.compute(db)["1w"]["index"]
        self.assertGreater(big, small)
        self.assertLess(big, 100.0)
        # o eixo aeróbio nunca passa dos 100
        self.assertLessEqual(max(v["axes"]["aerobic"] for v in lg.compute(db).values()), 100.0)

    def test_session_impact_is_positive_and_removing_it_lowers_the_index(self):
        db = self.app.db
        from datetime import date
        add_endurance(db, "imp", date.today().isoformat(), [0, 3600, 0, 600, 0])
        imp = lg.session_impact(db, "running", "imp")
        self.assertGreater(imp["deltas"]["1w"], 0)
        self.assertTrue(imp["top"])
        self.assertIn("1 sem", lg.impact_text(imp))

    def test_tests_and_habits_enter_the_index(self):
        from velo.core import fitness_tests as ft
        from datetime import date
        db = self.app.db
        ft.seed(db)
        t_ = next(x for x in ft.tests(db, "longevity") if "Prancha" in x["name"])
        before = lg.compute(db)["1m"]["axes"]["stability"]
        ft.add_result(db, t_["id"], 90.0, done_on=date.today().isoformat())
        after = lg.compute(db)["1m"]["axes"]["stability"]
        self.assertGreater(after, before)

    def test_blocks_dose_for_the_builder(self):
        b = bs.BlockBuilder(self.app, "cycling", None, control="erg")
        mins = lg.blocks_mins(b.blocks, "cycling")
        self.assertTrue(mins)
        imp = lg.impact_of(self.app.db, mins, sport="cycling")
        self.assertGreater(imp["deltas"]["1w"], 0)
        self.assertIn("Longevidade", b._longevity_text())


class TestLongevityScreens(tg.GuiCase):
    def test_menu_has_index_and_longevity_tests_and_health_lost_them(self):
        self.press(key.ESCAPE)
        home = self.screen()
        self.assertIn("Longevidade", [t_.title_text for t_ in home.tiles])
        self.pick("Saúde")
        self.assertNotIn("Testes de longevidade", self.screen().tab_labels())
        self.press(key.ESCAPE)
        self.pick("Longevidade")
        menu = self.screen()
        self.assertEqual(menu.tab_labels(), ["Índice", "Testes de longevidade"])
        labels = [i.label for i in menu.list.items]
        self.assertEqual(labels, ["1 dia", "1 semana", "1 mês", "3 meses", "6 meses",
                                  "9 meses", "1 ano", "2 anos", "3 anos", "5 anos", "10 anos",
                                  "15 anos", "20 anos"])
        self.app._on_draw()                                  # desenha o radar
        self.assertEqual(len(menu.radar.values), len(lg.AXES))
        menu.tab_named("Testes de longevidade")
        self.assertIn("Flexões em 1 minuto", [i.label for i in menu.list.items])

    def test_session_pages_show_the_radar_and_the_impact(self):
        from velo.ui import session_analysis as sa
        from datetime import date
        add_endurance(self.app.db, "e9", date.today().isoformat(), [0, 3600, 0, 0, 0])
        an = sa.open_session(self.app, "running", "e9")
        self.app.push(an)
        self.app._on_draw()
        rows = [i.label for i in an.list.items]
        self.assertIn("Longevidade", rows)
        aero = next(v for v in an._radar.values if v[0] == "Aeróbio")
        self.assertEqual(aero[1], 100.0)
        self.assertEqual(an._radar.caption.text, "O que treinou")

    def test_summary_shows_the_longevity_row(self):
        self.press(key.ESCAPE)
        self.pick("Corrida")
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        self.press(key.SPACE)
        for _ in range(80):
            self.app._tick(0.5)
        self.press(key.F10, key.ENTER, key.ENTER)
        summ = self.screen()
        self.assertIsInstance(summ, es.EnduranceSummary)
        self.assertTrue(summ._radar is not None)


# ============================================================ GPX conversor


def hilly(n_m: int = 5000):
    return [NS(dist_m=d, ele_m=100 + 60 * math.sin(d / 800.0)) for d in range(0, n_m + 1, 25)]


class TestGpxConverter(tg.GuiCase):
    def test_formulas_and_precision(self):
        pts = hilly()
        direct = gc.sections(pts, gc.Params(sport="running", formula="direct", seg_m=200))
        calib = gc.sections(pts, gc.Params(sport="running", formula="calibrated", seg_m=200))
        self.assertAlmostEqual(direct[0].setting - calib[0].setting, 1.0, delta=0.01)
        eff = gc.sections(pts, gc.Params(sport="running", formula="effort", seg_m=200))
        self.assertLess(eff[0].speed_kmh, 10.0)               # a subir, abranda
        short = len(gc.sections(pts, gc.Params(sport="running", seg_m=100)))
        long_ = len(gc.sections(pts, gc.Params(sport="running", seg_m=1000)))
        self.assertGreater(short, long_)                      # troços mais curtos = mais mudanças
        smooth = max(abs(s.grade_pct) for s in gc.sections(
            pts, gc.Params(sport="running", window_m=200, seg_m=100)))
        rough = max(abs(s.grade_pct) for s in gc.sections(
            pts, gc.Params(sport="running", window_m=20, seg_m=100)))
        self.assertLessEqual(smooth, rough + 1e-6)

    def test_incline_respects_the_treadmill_step_and_limit(self):
        p = gc.Params(sport="running", formula="direct", incline_step=1.0, max_incline=5.0)
        for s in gc.sections(hilly(), p):
            self.assertEqual(s.setting, round(s.setting))
            self.assertLessEqual(s.setting, 5.0)

    def test_cycling_levels_grow_with_the_grade(self):
        secs = gc.sections(hilly(), gc.Params(sport="cycling", formula="linear"))
        up = max(secs, key=lambda s: s.grade_pct)
        down = min(secs, key=lambda s: s.grade_pct)
        self.assertGreater(up.setting, down.setting)
        phys = gc.sections(hilly(), gc.Params(sport="cycling", formula="physics"))
        self.assertLessEqual(max(s.setting for s in phys), 140)

    def test_tab_only_on_manual_cycling_and_running_and_applies_blocks(self):
        erg = bs.BlockBuilder(self.app, "cycling", None, control="erg")
        self.assertNotIn("GPX Conversor", erg.tab_labels())
        swim = bs.BlockBuilder(self.app, "swimming", None)
        self.assertNotIn("GPX Conversor", swim.tab_labels())
        b = bs.BlockBuilder(self.app, "running", None, control="manual")
        self.assertEqual(b.tab_labels()[-1], "GPX Conversor")
        self.app.push(b)
        b.tab = len(b.modes)
        b.on_tab()
        from velo.ui.gpx_convert_screens import GpxConverter
        conv = self.screen()
        self.assertIsInstance(conv, GpxConverter)
        conv.set_route(self.route_id)
        self.assertGreater(len(conv.secs()), 0)
        labels = [i.label for i in conv.list.items]
        for want in ("Percurso (.gpx)", "Fórmula", "Média móvel da altitude", "Troço mínimo",
                     "Velocidade", "Resultado"):
            self.assertIn(want, labels)
        self.pick("Converter e aplicar")
        self.assertIs(self.screen(), b)
        self.assertGreaterEqual(len(b.blocks), 1)
        self.assertEqual(b.name, "Serra de Teste")
        self.assertTrue(any(bl.extra.get("incline_pct") for bl in b.blocks)
                        or all(not s.setting for s in gc.sections(
                            self.app.db.route_points(self.route_id), conv.p)))

    def test_treadmill_incline_step_setting(self):
        from velo.core import workout_meta as wm
        self.assertEqual(wm.device_limits(self.app.db)["treadmill_incline_step"], 0.5)
        self.app.db.set("treadmill_incline_step", 1.0)
        self.assertEqual(wm.device_limits(self.app.db)["treadmill_incline_step"], 1.0)
        b = bs.BlockBuilder(self.app, "running", None, control="manual")
        b.sel = 0
        b.block.extra["incline_pct"] = 2.0
        b.num_adjust("incline", 1, False)
        self.assertEqual(b.block.extra["incline_pct"], 3.0)


# =============================================== exercícios, grupos, disciplinas


class TestExercises(tg.GuiCase):
    def _inv(self):
        self.press(key.ESCAPE)
        self.pick("Exercícios")
        return self.screen()

    def test_tabs_new_modalities_groups_and_no_longevity(self):
        inv = self._inv()
        labels = inv.tab_labels()
        for want in ("Mobilidade", "Tendões", "Isométrico", "Grupos Musculares"):
            self.assertIn(want, labels)
        self.assertNotIn("Longevidade", labels)
        self.assertEqual(labels[-1], "Grupos Musculares")
        for mod in ("mobility", "tendons", "isometric"):
            self.assertGreater(len(gym.exercises(self.app.db, mod)), 3)

    def test_groups_tab_manages_groups_and_subgroups(self):
        inv = self._inv()
        inv.tab_named("Grupos Musculares")
        labels = [i.label for i in inv.list.items]
        self.assertIn("Pernas", labels)
        self.assertIn("+ Novo grupo", labels)
        db = self.app.db
        key_ = muscles.add_group(db, "Pescoço")
        sid = muscles.add_subgroup(db, key_, "Esternocleidomastoideu")
        inv.enter()
        self.assertIn("Pescoço", [i.label for i in inv.list.items])
        self.assertEqual(muscles.subgroup_name(db, sid), "Esternocleidomastoideu")
        muscles.delete_group(db, key_)
        self.assertNotIn(key_, [g["key"] for g in muscles.groups(db)])

    def test_editor_uses_dropdowns_for_group_subgroup_modalities_and_equipment(self):
        from velo.ui.hub_screens import ExerciseEditor
        from velo.ui.pickers import ChoicePopup, MultiChoicePopup
        ed = ExerciseEditor(self.app, None, "strength")
        self.app.push(ed)
        labels = [i.label for i in ed.list.items]
        for want in ("Grupo muscular", "Subgrupo muscular", "Modalidades", "Material"):
            self.assertIn(want, labels)
        self.select("Grupo muscular")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), ChoicePopup)     # lista, não setas
        self.press(key.ESCAPE)
        self.select("Modalidades")
        self.press(key.ENTER)
        multi = self.screen()
        self.assertIsInstance(multi, MultiChoicePopup)
        self.pick("Isométrico")                               # marca
        self.pick("OK")
        self.assertIn("isometric", ed.v["mods"])
        self.select("Material")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), MultiChoicePopup)
        self.press(key.ESCAPE)

    def test_exercise_keeps_group_and_subgroup(self):
        db = self.app.db
        legs = next(g for g in muscles.groups(db) if g["key"] == "legs")
        quad = legs["subgroups"][0]["id"]
        eid = gym.save_exercise(db, None, name="Teste X", mods=["strength"], group="legs",
                                subgroup=quad)
        e = gym.exercise(db, eid)
        self.assertEqual(e["subgroup_id"], quad)
        self.assertEqual(muscles.subgroup_name(db, e["subgroup_id"]), legs["subgroups"][0]["name"])

    def test_new_discipline_creates_its_tab(self):
        inv = self._inv()
        n = len(inv.tab_labels())
        key_ = gym.add_discipline(self.app.db, "Pilates")
        inv._refresh_tabs(select=key_)
        self.assertEqual(len(inv.tab_labels()), n + 1)
        self.assertIn("Pilates", inv.tab_labels())
        self.assertEqual(inv.modality(), "pilates")
        self.assertTrue(gym.is_custom("pilates"))
        # a disciplina pode receber exercícios
        eid = gym.save_exercise(self.app.db, None, name="Cem (pilates)", mods=["pilates"])
        self.assertEqual([e["name"] for e in gym.exercises(self.app.db, "pilates")],
                         ["Cem (pilates)"])
        gym.delete_discipline(self.app.db, "pilates")
        self.assertNotIn("pilates", [m.key for m in gym.modalities()])
        self.assertEqual("strength" in gym.exercise(self.app.db, eid)["modalities"], True)

    def test_new_discipline_button_exists_in_every_modality_tab(self):
        inv = self._inv()
        self.assertIn("+ Nova disciplina", [i.label for i in inv.list.items])


# ====================================================================== CSV


class TestCsv(tg.GuiCase):
    def test_every_dataset_has_template_and_export(self):
        self.assertEqual(list(cs.DATASETS), ["artigos", "exercicios", "grupos", "disciplinas",
                                             "testes", "material"])
        for key, d in cs.DATASETS.items():
            tpl = cs.template(key)
            self.assertEqual(tpl.splitlines()[0].split(";"), list(d.columns))
            self.assertGreaterEqual(len(cs.export_csv(self.app.db, key).splitlines()), 1)

    def test_import_creates_then_updates_without_duplicates(self):
        db = self.app.db
        text = ("nome;tipo;quantidade;peso_kg;notas;data_compra;preco_compra\n"
                "Kettlebell 16;Kettlebell;2;16;;2025-01-02;45,5\n")
        rep = cs.import_csv(db, "artigos", text)
        self.assertEqual((rep["created"], rep["updated"]), (1, 0))
        rep = cs.import_csv(db, "artigos", text.replace(";2;", ";3;"))
        self.assertEqual((rep["created"], rep["updated"]), (0, 1))
        from velo.core import inventory
        items = inventory.items(db)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["qty"], 3)
        self.assertEqual(items[0]["purchase_price"], 45.5)
        self.assertEqual(items[0]["kind"], "kettlebell")

    def test_exercises_create_missing_groups_subgroups_and_modalities(self):
        db = self.app.db
        text = ("nome;grupo;subgrupo;medida;peso_corpo;modalidades;material;descricao\n"
                "Ponte lenta;Cadeia posterior;Glúteo profundo;tempo;0;Isométrico|Yoga Flow;"
                "Tapete;Segura 30 s\n")
        rep = cs.import_csv(db, "exercicios", text)
        self.assertEqual(rep["created"], 1)
        e = next(x for x in gym.exercises(db) if x["name"] == "Ponte lenta")
        self.assertEqual(e["measure"], "time")
        self.assertIn("isometric", e["modalities"])
        self.assertIn("yoga_flow", e["modalities"])           # a disciplina nasceu
        self.assertIn("mat", e["equipment"])
        self.assertEqual(muscles.group_name(db, e["category"]), "Cadeia posterior")
        self.assertEqual(muscles.subgroup_name(db, e["subgroup_id"]), "Glúteo profundo")

    def test_round_trip_export_import_changes_nothing(self):
        db = self.app.db
        n = len(gym.exercises(db))
        rep = cs.import_csv(db, "exercicios", cs.export_csv(db, "exercicios"))
        self.assertEqual(rep["created"], 0)
        self.assertEqual(len(gym.exercises(db)), n)
        g = len(muscles.groups(db))
        cs.import_csv(db, "grupos", cs.export_csv(db, "grupos"))
        self.assertEqual(len(muscles.groups(db)), g)

    def test_detect_by_header_and_delimiters(self):
        self.assertEqual(cs.detect("grupo;subgrupo\nPernas;Quadríceps\n"), "grupos")
        self.assertEqual(cs.detect("desporto,nome,unidade\nlongevidade,Prancha,s\n"), "testes")
        self.assertIsNone(cs.detect("a;b;c\n1;2;3\n"))
        rep = cs.import_csv(self.app.db, "grupos", "grupo,subgrupo\nPescoço,Trapézio alto\n")
        self.assertEqual(rep["created"], 2)

    def test_material_is_reference_only(self):
        rep = cs.import_csv(self.app.db, "material", "chave;nome_pt\nx;y\n")
        self.assertTrue(rep["errors"])

    def test_write_and_read_files_and_cli_style_import(self):
        import os
        out = tempfile.mkdtemp()
        p = cs.write(self.app.db, "artigos", out, what="template")
        self.assertTrue(Path(p).read_bytes().startswith(b"\xef\xbb\xbf"))      # UTF-8 com BOM
        key, rep = cs.import_file(self.app.db, p)
        self.assertEqual(key, "artigos")
        self.assertEqual(rep["created"], 1)
        from velo.core import file_import
        _r, text = file_import.import_file(self.app.db, "csv", p)
        self.assertIn("Artigos", text)
        _ = os

    def test_sync_tab_lists_datasets_and_the_dataset_window_works(self):
        os_env = __import__("os").environ
        out = tempfile.mkdtemp()
        os_env["PERENNIA_DOWNLOADS"] = out
        try:
            self.press(key.ESCAPE)
            self.pick("Definições")
            scr = self.screen()
            scr.tab_named("Sincronização")
            scr.sync_tabs.select_label("CSV") if hasattr(scr.sync_tabs, "select_label") else None
            items = scr.sync.items_csv()
            labels = [i.label for i in items]
            self.assertIn("Exercícios", labels)
            self.assertIn("Grupos e subgrupos musculares", labels)
            from velo.ui.csv_screens import CsvDatasetPopup
            pop = CsvDatasetPopup(self.app, "exercicios")
            self.app.push(pop)
            self.pick("Descarregar o modelo (.csv)")
            self.pick("Exportar o que tenho (.csv)")
            names = sorted(p.name for p in Path(out).glob("*.csv"))
            self.assertTrue(any(n.startswith("perennia_modelo_exercicios") for n in names))
            self.assertTrue(any(n.startswith("perennia_exercicios_") for n in names))
        finally:
            os_env.pop("PERENNIA_DOWNLOADS", None)


# ====================================================== ciclismo e outros ecrãs


class TestSmallThings(tg.GuiCase):
    def test_cycling_header_has_no_distance_or_session_time(self):
        self.pick("Sessão de treino")
        self.pick("Livre")
        self.pick("Começar")
        ride = self.screen()
        ride.world.build_all()
        ride.preparing = False
        for _ in range(30):
            self.app.hub.tick(0.5)
            ride.update(0.5)
        hud = ride.hud
        self.assertEqual(hud._clock.text, "")
        self.assertEqual(hud._dist.text, "")

    def test_backup_knows_the_new_tables(self):
        from velo.core import backup
        backup.prepare(self.app.db)
        known = {t_ for c in backup.COMPONENTS for t_ in c.tables}
        for table in ("workout_types", "session_tags", "tag_catalog", "muscle_groups",
                      "muscle_subgroups", "gym_disciplines"):
            self.assertIn(table, known)
        self.assertEqual(backup.unknown_tables(self.app.db), [])

    def test_workout_page_actions_and_no_builder_tab(self):
        self.pick("Lista de treinos")
        hub = self.screen()
        self.assertNotIn("Construtor de treinos", hub.tab_labels())
        self.assertIn("+ Novo treino", [i.label for i in hub.list.items])
        self.pick("Tempo 3×15")
        self.assertEqual([i.label for i in self.screen().list.items],
                         ["Editar", "Exportar", "Configurar sessão de treino"])


if __name__ == "__main__":
    import unittest
    unittest.main()
