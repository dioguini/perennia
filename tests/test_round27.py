"""Ronda 27: o glossário das análises (separador, ficha, edições), o texto do rato por cima
dos resultados, a exportação para o Power BI, o mapa da rota na sessão e o segmento ao vivo
(KOM, o meu melhor e eu, com as diferenças e os W/kg)."""
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

from perennia.core import backup as bk  # noqa: E402
from perennia.core import climbs as climbs_mod  # noqa: E402
from perennia.core import gpx, health, labs, powerbi  # noqa: E402
from perennia.core import lab_glossary as lg  # noqa: E402
from perennia.core import lab_glossary_data as lgd  # noqa: E402
from perennia.core import segment_live as sl  # noqa: E402
from perennia.core import segments as segs  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402
from perennia.core.i18n import EN, PT, set_language  # noqa: E402
from perennia.core.ride import RideEngine  # noqa: E402
from perennia.io.hub import SensorHub  # noqa: E402
from perennia.io.sim import SimulatedTrainer  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import health_screens as hs  # noqa: E402
from perennia.ui import lab_glossary_screens as lgs  # noqa: E402
from perennia.ui.widgets import Tooltip  # noqa: E402

GPX = Path(__file__).parent / "teste.gpx"


class Base(unittest.TestCase):
    def setUp(self):
        set_language(PT)
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


def add_report(db, day: str, values: dict) -> int:
    labs.ensure(db)
    rid = health.save_lab_report(db, None, done_on=day, lab="Lab")
    for name, v in values.items():
        labs.add_result(db, rid, name, v)
    return rid


# ===================================================== glossário das análises


class TestLabGlossaryCatalog(Base):
    def test_every_component_is_complete_in_both_languages(self):
        keys = [m["key"] for m in lgd.MARKERS]
        self.assertGreaterEqual(len(keys), 60)
        self.assertEqual(len(keys), len(set(keys)))                 # chaves únicas
        cats = {k for k, _pt, _en in lgd.CATEGORIES}
        for m in lgd.MARKERS:
            self.assertIn(m["cat"], cats, m["key"])
            self.assertTrue(m["aliases"], m["key"])
            for loc in ("pt", "en"):
                for f in ("s", "w", "up", "down", "good", "bad", "act"):
                    self.assertTrue(m[loc][f].strip(), (m["key"], loc, f))
            for a in m["aliases"]:
                self.assertEqual(a, lg.fold(a), (m["key"], a))       # sem acentos/maiúsculas

    def test_the_users_examples_are_there(self):
        _d, db = self.place()
        fer = lg.get(db, "ferritin")
        self.assertIn("carne vermelha", fer["up"])
        self.assertIn("doar sangue", fer["act"])
        folate = lg.get(db, "folate")
        self.assertIn("brócolos", folate["good"])
        for k in ("hgb", "testo", "wbc", "folate", "ferritin"):
            self.assertIsNotNone(lg.get(db, k), k)

    def test_lab_report_names_find_their_component(self):
        _d, db = self.place()
        cases = {"Ferritina (Electroquimiluminiscência)": "ferritin",
                 "Colesterol HDL": "hdl", "Colesterol LDL": "ldl", "Colesterol total": "chol",
                 "Hemoglobina glicada A1c": "hba1c", "Testosterona livre": "freetesto",
                 "Testosterona total": "testo", "Saturação da transferrina": "tsat",
                 "Ácido fólico": "folate", "Leucócitos": "wbc", "PCR ultrassensível": "crp",
                 "Hemoglobina corpuscular média": "mch", "VCM": "mcv", "TGO/AST": "ast",
                 "Vitamina D (25-OH)": "vitd", "Hemoglobina": "hgb"}
        for name, want in cases.items():
            e = lg.match(db, name)
            self.assertIsNotNone(e, name)
            self.assertEqual(e["key"], want, name)
        self.assertIsNone(lg.match(db, "Xpto qualquer"))

    def test_english_texts(self):
        _d, db = self.place()
        set_language(EN)
        try:
            e = lg.get(db, "ferritin")
            self.assertEqual(e["name"], "Ferritin")
            self.assertIn("donation", e["act"])
            self.assertEqual(lg.category_name("iron"), "Iron and vitamins")
        finally:
            set_language(PT)

    def test_edit_restore_delete_and_own_components(self):
        _d, db = self.place()
        fer = lg.get(db, "ferritin")
        lg.save(db, "ferritin", dict(fer, summary="O meu resumo",
                                     aliases_text="ferritina serica"))
        e = lg.get(db, "ferritin")
        self.assertTrue(e["edited"])
        self.assertEqual(e["summary"], "O meu resumo")
        self.assertEqual(e["what"], fer["what"])                     # o resto continua de origem
        self.assertEqual(lg.match(db, "Ferritina sérica")["ref"], "ferritin")
        lg.restore(db, "ferritin")
        self.assertEqual(lg.get(db, "ferritin")["summary"], fer["summary"])
        lg.delete(db, "psa")
        self.assertIsNone(lg.get(db, "psa"))
        self.assertIn("psa", lg.deleted_builtins(db))
        self.assertEqual(lg.restore_all(db), 1)
        self.assertIsNotNone(lg.get(db, "psa"))
        ref = lg.save(db, None, {"name": "Cistatina C", "category": "kidney",
                                 "aliases_text": "cistatina, cystatin c",
                                 "summary": "Outra medida do rim.", "what": "Proteína."})
        self.assertTrue(ref.startswith(lg.CUSTOM))
        self.assertEqual(lg.match(db, "Cistatina C (soro)")["ref"], ref)
        lg.delete(db, ref)
        self.assertIsNone(lg.get(db, ref))
        with self.assertRaises(ValueError):
            lg.save(db, None, {"name": "  "})

    def test_latest_value_per_component(self):
        _d, db = self.place()
        add_report(db, "2026-01-10", {"Ferritina": "120"})
        add_report(db, "2026-06-10", {"Ferritina": "340", "Colesterol HDL": "48"})
        last = lg.latest_values(db)
        self.assertEqual(last["ferritin"]["text"], "340")
        self.assertEqual(last["ferritin"]["done_on"], "2026-06-10")
        self.assertIn("hdl", last)


class TestLabGlossaryScreens(tg.GuiCase):
    def setUp(self):
        super().setUp()
        self.rid = add_report(self.app.db, "2026-11-02",
                              {"Ferritina (Electroquimiluminiscência)": "340",
                               "Hemoglobina": "14.6", "Marcador Desconhecido": "1"})

    def open_report(self) -> hs.HealthMenu:
        self.app.push(hs.HealthMenu(self.app, 0, self.rid))
        return self.screen()

    def test_tab_lists_components_by_category_with_my_last_value(self):
        m = self.open_report()
        self.assertEqual(m.tab_labels()[1], "Glossário das análises")
        m.tab_named("Glossário das análises")
        self.assertEqual(m.tab_key(), "labs_glossary")
        heads = [i.label for i in m.list.items if i.header]
        self.assertEqual(heads[:2], ["Hemograma", "Ferro e vitaminas"])
        fer = next(i for i in m.list.items if i.label == "Ferritina")
        self.assertEqual(fer.value, "340")
        self.assertIn("depósito de ferro", fer.detail)
        self.assertIn("Para ficar no intervalo", fer.tip)
        self.assertIn("+ Novo componente", [i.label for i in m.list.items if i.button])

    def test_enter_opens_the_card_with_every_section(self):
        m = self.open_report()
        m.tab_named("Glossário das análises")
        self.pick("Ferritina")
        card = self.screen()
        self.assertIsInstance(card, lgs.ComponentView)
        self.assertEqual(card.chrome.title.text, "Ferritina")
        texts = card.texts()
        for head in ("O QUE É", "O QUE FAZ SUBIR", "O QUE FAZ DESCER", "O QUE É BOM",
                     "O QUE É MAU", "ESTRATÉGIAS PARA FICAR NO INTERVALO", "NOTA"):
            self.assertIn(head, texts)
        self.assertTrue(any("doar sangue" in x for x in texts))
        self.assertIn("340", card.chrome.subtitle.text)
        self.pick("Editar")
        ed = self.screen()
        self.assertIsInstance(ed, lgs.ComponentEditor)
        ed.v["summary"] = "Reservas de ferro."
        self.assertTrue(ed.commit())
        self.assertEqual(lg.get(self.app.db, "ferritin")["summary"], "Reservas de ferro.")

    def test_new_component_from_the_tab(self):
        m = self.open_report()
        m.tab_named("Glossário das análises")
        self.pick("+ Novo componente")
        ed = self.screen()
        self.assertIsInstance(ed, lgs.ComponentEditor)
        self.type("Marcador Desconhecido")
        ed.v["summary"] = "Um teu."
        self.assertTrue(ed.commit())
        self.assertEqual(lg.match(self.app.db, "Marcador Desconhecido")["summary"], "Um teu.")

    def test_result_rows_have_a_hover_text_and_g_opens_the_card(self):
        m = self.open_report()
        fer = next(i for i in m.list.items if i.label.startswith("Ferritina"))
        self.assertIn("depósito de ferro", fer.tip)
        self.assertIn("G abre", fer.tip)
        unknown = next(i for i in m.list.items if i.label.startswith("Marcador"))
        self.assertEqual(unknown.tip, "")                      # fora do glossário: sem texto
        m.list.index = m.list.items.index(fer)
        self.press(key.G)
        self.assertIsInstance(self.screen(), lgs.ComponentView)
        self.assertEqual(self.screen().ref, "ferritin")
        self.press(key.ESCAPE)
        m.list.index = next(i for i, it in enumerate(m.list.items)
                            if it.label.startswith("Marcador"))
        self.press(key.G)
        self.assertIs(self.screen(), m)                        # explica e não abre nada
        self.assertIn("glossário", self.app._message)

    def test_tooltip_appears_after_resting_the_mouse(self):
        m = self.open_report()
        self.app._on_draw()
        idx, x, y, _w = next(c for c in m.list._cells
                             if m.list.items[c[0]].label.startswith("Ferritina"))
        self.app._on_mouse_motion(int(x + 20), int(y), 0, 0)
        self.assertEqual(self.app.tooltip_text(), "")          # ainda a mexer
        self.app._tick(Tooltip.DELAY_S + 0.05)
        tip = self.app.tooltip_text()
        self.assertIn("Ferritina", tip)
        self.app._on_draw()                                    # desenha sem erro
        self.assertEqual(self.app.tooltip.text, tip)
        self.app._on_mouse_motion(5, 5, 0, 0)
        self.app._tick(1.0)
        self.assertEqual(self.app.tooltip_text(), "")          # fora das linhas: nada

    def test_tooltip_box_stays_inside_the_window(self):
        t = Tooltip(self.app.window)
        t.show("x " * 400, self.app.window.width - 5, 5)
        self.assertGreaterEqual(t.bg.x, 0)
        self.assertLessEqual(t.bg.x + t.bg.width, self.app.window.width)
        self.assertGreaterEqual(t.bg.y, 0)


# ================================================================= Power BI


def ride(db, d: Path, rid: str, power: float = 210, until_m: float = 1500.0):
    hub = SensorHub()
    hub.add_source(SimulatedTrainer(base_power=power), role="trainer", is_trainer=True)
    e = RideEngine(db, db.athlete(), route_id=rid, points=db.route_points(rid),
                   climbs=db.climbs(rid), sensors=hub, trainer=hub, rides_dir=d / "rides")
    snaps = []
    for _ in range(3000):
        hub.tick(0.5)
        e.update(0.5)
        s = e.segment_snapshot()
        if s is not None:
            snaps.append(s)
        if e.state.pos_m > until_m:
            break
    e.finish()
    return e, snaps


def with_route(db) -> str:
    _, raw = gpx.parse_gpx(GPX)
    pts = gpx.resample(raw)
    return db.insert_route("Serra", pts, climbs_mod.detect(pts))


class TestPowerBI(Base):
    def test_export_writes_the_model_files(self):
        d, db = self.place()
        rid = with_route(db)
        ride(db, d, rid, until_m=600)
        add_report(db, "2026-10-01", {"Ferritina (Electroquimiluminiscência)": "350",
                                      "Colesterol HDL": "45"})
        m = powerbi.export(db, d)
        folder = Path(m["path"])
        self.assertEqual(folder, Path(d) / "out" / "powerbi")      # data/out/powerbi
        for f in ("Perennia_PowerBI.xlsx", "Perennia.pbids", "Perennia_Medidas_DAX.txt",
                  "Perennia_Amostras.pq", "LEIA-ME.txt"):
            self.assertTrue((folder / f).exists(), f)
        for t in ("Calendario", "Sessoes", "Voltas", "PMC", "Analises", "Parametros",
                  "Amostras", "Diario", "Tensao_arterial"):
            self.assertTrue((folder / "csv" / f"{t}.csv").exists(), t)
        self.assertEqual(m["tables"]["Sessoes"], 1)
        self.assertGreater(m["tables"]["Amostras"], 30)
        self.assertEqual(m["tables"]["Analises"], 2)
        # o .pbids aponta para o Excel
        pb = json.loads((folder / "Perennia.pbids").read_text(encoding="utf-8"))
        path = pb["connections"][0]["details"]["address"]["path"]
        self.assertTrue(path.endswith("Perennia_PowerBI.xlsx"))
        self.assertEqual(pb["connections"][0]["details"]["protocol"], "file")
        # o Excel: uma folha por tabela (sem as amostras, que só vão em CSV)
        import openpyxl
        wb = openpyxl.load_workbook(folder / "Perennia_PowerBI.xlsx", read_only=True)
        self.assertIn("Sessoes", wb.sheetnames)
        self.assertIn("Analises", wb.sheetnames)
        self.assertNotIn("Amostras", wb.sheetnames)
        rows = list(wb["Analises"].iter_rows(values_only=True))
        head = list(rows[0])
        comp = {r[head.index("Parametro")]: r[head.index("Componente")] for r in rows[1:]}
        self.assertEqual(comp["Ferritina"], "Ferritina")
        self.assertEqual(comp["Colesterol HDL"], "Colesterol HDL («bom»)")
        ses = list(wb["Sessoes"].iter_rows(values_only=True))
        self.assertTrue(str(ses[1][0]).startswith("ride:"))
        wb.close()
        # as chaves das tabelas ligam-se pelo nome
        dax = (folder / "Perennia_Medidas_DAX.txt").read_text(encoding="utf-8")
        self.assertIn("Sessoes[SessaoID] 1—* Voltas[SessaoID]", dax)
        # exportar outra vez reescreve a mesma pasta (o «Atualizar» do Power BI)
        m2 = powerbi.export(db, d)
        self.assertEqual(m2["path"], m["path"])

    def test_calendar_covers_every_day_with_data(self):
        _d, db = self.place()
        add_report(db, "2026-01-10", {"Ferritina": "120"})
        tables = {t.name: t for t in powerbi.model(db, with_samples=False)}
        cal = tables["Calendario"]
        days = [r[0] for r in cal.rows]
        self.assertEqual(str(days[0]), "2026-01-10")
        self.assertEqual(len(days), len(set(days)))
        self.assertNotIn("Amostras", tables)

    def test_cli(self):
        import main
        d, db = self.place()
        db.close()
        out = d / "pbi"
        import argparse
        args = argparse.Namespace(data_dir=str(d), powerbi=str(out))
        self.assertEqual(main.powerbi_cli(args), 0)
        self.assertTrue((out / "Perennia_PowerBI.xlsx").exists())


class TestPowerBIButton(tg.GuiCase):
    def test_button_in_the_export_tab(self):
        self.app.open_backups()
        scr = self.screen()
        scr.tab_named("Exportar")
        btn = next(i for i in scr.list.items if i.button and i.label == "Power BI")
        btn.action()
        self.assertTrue((Path(self.tmp) / "exports" / "PowerBI" / "Perennia.pbids").exists()
                        or any(Path(self.tmp).rglob("Perennia.pbids")))


# ================================================================= segmento ao vivo


class TestSegmentLive(Base):
    def setUp(self):
        super().setUp()
        self.d, self.db = self.place()
        self.rid = with_route(self.db)
        self.db.conn.execute(
            "INSERT INTO strava_segments(route_id, segment_id, name, distance_m, avg_grade,"
            " climb_cat, start_m, end_m, pr_s, pr_date, effort_count, kom, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.rid, 999, "Subida KOM", 1000, 5.0, 0, 300, 1300, None, None, 0, "1:40",
             "2026-01-01"))
        self.db.conn.commit()

    def test_three_markers_deltas_and_wkg(self):
        e1, snaps1 = ride(self.db, self.d, self.rid, power=200)
        self.assertTrue(snaps1)
        first = snaps1[-1]
        self.assertEqual({r["key"] for r in first["rows"]}, {"kom", "me"})   # ainda sem melhor
        self.assertEqual(len(first["profile"]), sl.PROFILE_POINTS)
        mine = segs.efforts(self.db, "strava", 999)
        self.assertEqual(len(mine), 1)
        # segundo passeio, mais forte: o melhor é o primeiro (com amostras e W/kg reais)
        _e2, snaps2 = ride(self.db, self.d, self.rid, power=260)
        s = snaps2[-1]
        rows = {r["key"]: r for r in s["rows"]}
        self.assertEqual(set(rows), {"kom", "best", "me"})
        best = rows["best"]
        self.assertFalse(best["estimated"])
        self.assertAlmostEqual(best["total_s"], mine[0]["elapsed_s"], delta=2)
        self.assertAlmostEqual(best["wkg"], 200 / 70, delta=0.35)
        self.assertLess(best["delta_s"], 0)                    # mais forte: à frente do melhor
        self.assertGreater(s["positions"]["me"], s["positions"]["best"])
        kom = rows["kom"]
        self.assertTrue(kom["estimated"])
        self.assertEqual(kom["total_s"], 100)
        self.assertGreater(kom["delta_s"], 0)                  # atrás do KOM
        self.assertGreater(s["positions"]["kom"], s["positions"]["me"])
        self.assertAlmostEqual(rows["me"]["wkg"], 260 / 70, delta=0.4)

    def test_kom_position_follows_the_physics(self):
        seg = segs.load(self.db, self.rid)[0]
        from perennia.core.route_index import RouteIndex
        live = sl.build(self.db, self.db.athlete(), RouteIndex(self.db.route_points(self.rid)),
                        seg, wait=True)
        self.assertIsNotNone(live.kom.track)                   # a física acabou
        self.assertGreater(live.kom.wkg, 3.0)
        snap = live.snapshot(50.0, 0.4)
        self.assertGreater(snap["positions"]["kom"], 0)
        self.assertLessEqual(snap["positions"]["kom"], live.length_m)

    def test_window_from_samples(self):
        rows = [{"t_s": t, "dist_m": 10.0 * t, "power_w": 200} for t in range(0, 200)]
        win = sl._window(rows, 300.0, 1300.0, 6000.0, 100.0)
        dist, tim, watts = win
        self.assertAlmostEqual(tim[-1], 100.0, delta=1.5)
        self.assertEqual(dist[-1], 1000.0)
        self.assertTrue(all(w == 200 for w in watts))


class TestRideMapAndSegmentPanel(tg.GuiCase):
    def _start(self) -> app_mod.RideScreen:
        self.app.db.conn.execute(
            "INSERT INTO strava_segments(route_id, segment_id, name, distance_m, avg_grade,"
            " climb_cat, start_m, end_m, pr_s, pr_date, effort_count, kom, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.route_id, 777, "Muro", 600, 6.0, 0, 200, 800, None, None, 0, "1:10",
             "2026-01-01"))
        self.app.db.conn.commit()
        self.open_routes()
        self.pick("Serra de Teste")
        self.pick("Começar")
        self.pick("Começar")
        ride = self.screen()
        self.assertIsInstance(ride, app_mod.RideScreen)
        ride.world.build_all()
        ride.preparing = False
        return ride

    def _run(self, ride, seconds: float) -> None:
        for _ in range(int(seconds / 0.25)):
            self.app.hub.tick(0.25)
            ride.update(0.25)

    def test_map_shows_where_i_am_and_m_toggles_it(self):
        ride = self._start()
        self._run(ride, 20)
        hud = ride.hud
        self.assertTrue(hud.route_map.visible)
        p = hud.route_map.screen_at(ride.engine.state.pos_m)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(hud.route_map.dot.x, p[0], delta=2)
        self.assertEqual(len(hud.route_map._seg_lines) > 0, True)   # o segmento a vermelho
        self.press(key.M)
        self.assertFalse(hud.map_on)
        self.assertFalse(self.app.db.get("ride_map_on"))
        self._run(ride, 1)
        self.assertFalse(hud.route_map.visible)
        self.press(key.M)
        self.assertTrue(self.app.db.get("ride_map_on"))

    def test_segment_panel_appears_inside_the_segment(self):
        ride = self._start()
        hud = ride.hud
        self._run(ride, 5)
        self.assertFalse(hud.segment_panel.visible)
        for _ in range(600):
            self._run(ride, 1)
            if ride.engine.state.pos_m > 400:
                break
        self.assertTrue(hud.segment_panel.visible)
        texts = hud.segment_panel.texts()
        self.assertIn("Muro", texts)
        self.assertIn("KOM", texts)
        self.assertIn("Eu agora", texts)
        self.assertIn("1:10", texts)
        self.assertIsNotNone(hud.segment_panel.marker_x("me"))
        self.assertIsNotNone(hud.segment_panel.marker_x("kom"))
        self.assertIsNone(hud.segment_panel.marker_x("best"))   # ainda sem melhor
        for _ in range(600):
            self._run(ride, 1)
            if ride.engine.state.pos_m > 850:
                break
        self.assertFalse(hud.segment_panel.visible)            # à saída desaparece

    def test_layout_panels_include_map_and_segment(self):
        from perennia.core import screen_layout
        names = [k for k, _n, _d in screen_layout.catalog("cycling")]
        self.assertIn("map", names)
        self.assertIn("segment", names)
        from perennia.ui import keymap
        self.assertEqual(keymap.default("ride_map"), ("M", ()))


class TestBackupKeepsTheLabGlossary(Base):
    def test_round_trip(self):
        d, db = self.place()
        self.assertEqual(bk.unknown_tables(db), [])
        lg.save(db, None, {"name": "Cistatina C", "category": "kidney", "summary": "Rim."})
        lg.delete(db, "psa")
        m = bk.export(db, d, d / "b", ["glossario"])
        with zipfile.ZipFile(m["path"]) as z:
            self.assertTrue(any(n.endswith("lab_glossary.jsonl") for n in z.namelist()))
        d2, db2 = self.place()
        bk.restore(db2, d2, m["path"])
        self.assertIsNotNone(lg.match(db2, "Cistatina C"))
        self.assertIsNone(lg.get(db2, "psa"))


if __name__ == "__main__":
    unittest.main()
