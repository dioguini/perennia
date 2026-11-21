"""Ronda 21: a biblioteca de segmentos do Strava (importar por ID, favoritos e esforços;
ligar às rotas sem rede, com o traçado) e a pesquisa por rota, que se mantém."""
from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from perennia.core import climbs, gpx, options, segments as sg, strava_library as lib  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402
from perennia.io import strava  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
tc = importlib.import_module("tests.test_connect")
LON0, lat_at = tc.LON0, tc.lat_at


def encode(points) -> str:
    """O inverso de `decode_polyline` (para os testes)."""
    out, plat, plon = [], 0, 0
    for lat, lon in points:
        la, lo = round(lat * 1e5), round(lon * 1e5)
        for v in (la - plat, lo - plon):
            v = ~(v << 1) if v < 0 else v << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plon = la, lo
    return "".join(out)


def path(a, b, lon=LON0, n=12):
    return [(lat_at(a + (b - a) * i / n), lon) for i in range(n + 1)]


def detail(sid, name, a, b, lon=LON0, **kw):
    d = {"id": sid, "name": name, "distance": abs(b - a), "average_grade": 5.5,
         "maximum_grade": 9.0, "total_elevation_gain": 120.0, "climb_category": 2,
         "activity_type": "Ride", "city": "Sintra", "country": "Portugal", "private": False,
         "start_latlng": [lat_at(a), lon], "end_latlng": [lat_at(b), lon],
         "map": {"polyline": encode(path(a, b, lon))},
         "athlete_segment_stats": {"pr_elapsed_time": 900, "pr_date": "2025-06-01T10:00:00Z",
                                   "effort_count": 3},
         "xoms": {"kom": "5:01"}}
    d.update(kw)
    return d


class FakeApi(tc.FakeStrava):
    """O Strava com segmentos completos, favoritos e esforços (ou sem subscrição)."""

    def __init__(self, details=(), starred=(), efforts=None, subscription=True, **kw):
        super().__init__(**kw)
        self.details = {d["id"]: d for d in details}
        self.starred_ids = list(starred)
        self.eff = efforts or {}
        self.subscription = subscription
        self.rate_after = None

    def __call__(self, method, url, params=None, headers=None, timeout=20.0):
        if url == strava.TOKEN_URL:
            return super().__call__(method, url, params, headers, timeout)
        self.calls.append((method, url, dict(params or {}), dict(headers or {})))
        if self.rate_after is not None and len(self.calls) > self.rate_after:
            return 429, None
        if url.endswith("/segments/starred"):
            page = int((params or {}).get("page", 1))
            return 200, [self.details[i] for i in self.starred_ids] if page == 1 else []
        if url.endswith("/segment_efforts"):
            if not self.subscription:
                return 402, None
            return 200, self.eff.get(int(params["segment_id"]), []) \
                if int((params or {}).get("page", 1)) == 1 else []
        if url.endswith("/segments/explore"):
            return super().__call__(method, url, params, headers, timeout)
        if "/segments/" in url:
            sid = int(url.rsplit("/", 1)[1])
            return (200, self.details[sid]) if sid in self.details else (404, None)
        return 404, None


def effort(i, secs, day="2025-05-0%d" % 1, watts=250):
    return {"id": 1000 + i, "elapsed_time": secs, "moving_time": secs - 2,
            "start_date_local": f"2025-05-{i:02d}T08:00:00Z", "average_watts": watts,
            "activity": {"id": 555 + i}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "v.db")
        self.db.save_athlete(Athlete(name="T", birth_year=1990, weight_kg=72, ftp_w=250))
        _, raw = gpx.parse_gpx(tg.GPX)
        self.points = gpx.resample(raw)
        self.db.set("strava_client_id", "123")
        self.db.set("strava_client_secret", "abc")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def route(self, name="Serra"):
        return self.db.insert_route(name, self.points, climbs.detect(self.points))

    def client(self, fake):
        c = strava.StravaClient(self.db, http=fake)
        c.exchange("x", "read,activity:read,read_all")
        return c


class TestParse(unittest.TestCase):
    def test_ids_and_links(self):
        txt = ("https://www.strava.com/segments/12345?filter=overall  67890, 5551234\n"
               "strava.com/activities/998877665/segments/4242 ; lixo 12ab #777")
        self.assertEqual(lib.parse_ids(txt), [12345, 67890, 5551234, 4242, 777])
        self.assertEqual(lib.parse_ids("12345 12345"), [12345])
        self.assertEqual(lib.parse_ids(""), [])

    def test_polyline_round_trip(self):
        pts = [(38.7223, -9.1393), (38.7301, -9.1402), (-33.8688, 151.2093)]
        got = sg.decode_polyline(encode(pts))
        for (a, b), (c, d) in zip(pts, got):
            self.assertAlmostEqual(a, c, places=5)
            self.assertAlmostEqual(b, d, places=5)
        self.assertEqual(sg.decode_polyline(""), [])
        self.assertEqual(sg.decode_polyline("~~~~"), [])         # lixo não rebenta


class TestImport(Base):
    def test_import_by_id_saves_everything(self):
        api = FakeApi(details=[detail(1, "Subida da Serra", 1000, 4000)],
                      efforts={1: [effort(1, 900), effort(2, 950), effort(3, 1010)]})
        rep = lib.import_ids(self.db, self.client(api), [1])
        self.assertEqual((rep["added"], rep["updated"], rep["efforts"]), (1, 0, 3))
        row = lib.get(self.db, 1)
        self.assertEqual(row["name"], "Subida da Serra")
        self.assertEqual((row["pr_s"], row["pr_date"], row["effort_count"]), (900, "2025-06-01", 3))
        self.assertEqual(row["kom"], "5:01")
        self.assertTrue(row["polyline"])
        self.assertEqual(row["origin"], "id")
        self.assertEqual([e["elapsed_s"] for e in lib.library_efforts(self.db, 1)],
                         [900, 950, 1010])
        # repetir não duplica nada
        rep = lib.import_ids(self.db, self.client(api), [1])
        self.assertEqual((rep["added"], rep["updated"]), (0, 1))
        self.assertEqual(len(lib.library_efforts(self.db, 1)), 3)

    def test_without_subscription_only_the_pr(self):
        api = FakeApi(details=[detail(1, "A", 1000, 4000), detail(2, "B", 5000, 6000)],
                      subscription=False)
        rep = lib.import_ids(self.db, self.client(api), [1, 2])
        self.assertEqual(rep["added"], 2)
        self.assertTrue(rep["no_subscription"])
        self.assertEqual(lib.library_efforts(self.db, 1), [])
        self.assertEqual(lib.get(self.db, 2)["pr_s"], 900)
        # só pediu os esforços uma vez (depois de saber que não há subscrição, não insiste)
        self.assertEqual(sum(1 for c in api.calls if c[1].endswith("/segment_efforts")), 1)

    def test_efforts_can_be_turned_off(self):
        self.db.set("strava_import_efforts", False)
        api = FakeApi(details=[detail(1, "A", 1000, 4000)], efforts={1: [effort(1, 900)]})
        rep = lib.import_ids(self.db, self.client(api), [1])
        self.assertEqual(rep["efforts"], 0)
        self.assertFalse(any(c[1].endswith("/segment_efforts") for c in api.calls))

    def test_unknown_id_fails_alone(self):
        api = FakeApi(details=[detail(1, "A", 1000, 4000)])
        rep = lib.import_ids(self.db, self.client(api), [99, 1])
        self.assertEqual(rep["added"], 1)
        self.assertEqual([f[0] for f in rep["failed"]], [99])

    def test_batch_limit_and_rate_limit_leave_the_rest(self):
        ds = [detail(i, f"S{i}", 1000, 2000) for i in range(1, 8)]
        api = FakeApi(details=ds, subscription=False)
        self.db.set("strava_import_batch", 5)
        rep = lib.import_ids(self.db, self.client(api), list(range(1, 8)))
        self.assertEqual(rep["added"], 5)
        self.assertEqual(rep["remaining"], [6, 7])
        api2 = FakeApi(details=ds, subscription=False)
        c = self.client(api2)
        api2.rate_after = len(api2.calls) + 3
        rep = lib.import_ids(self.db, c, [1, 2, 3, 4, 5, 6])
        self.assertTrue(rep["rate_limited"])
        self.assertTrue(rep["remaining"])
        self.assertIn("15 min", rep.text())

    def test_starred_import(self):
        ds = [detail(1, "A", 1000, 2000), detail(2, "B", 3000, 4000)]
        api = FakeApi(details=ds, starred=[1, 2], subscription=False)
        rep = lib.import_starred(self.db, self.client(api))
        self.assertEqual(rep["added"], 2)
        self.assertEqual({r["segment_id"] for r in lib.library(self.db) if r["starred"]}, {1, 2})
        self.assertEqual(lib.get(self.db, 1)["origin"], "starred")

    def test_save_does_not_erase_what_a_summary_lacks(self):
        lib.save(self.db, detail(1, "A", 1000, 4000), "id")
        lib.save(self.db, {"id": 1, "name": "A", "distance": 3000,
                           "start_latlng": [lat_at(1000), LON0],
                           "end_latlng": [lat_at(4000), LON0]}, "route")
        row = lib.get(self.db, 1)
        self.assertEqual(row["pr_s"], 900)
        self.assertTrue(row["polyline"])
        self.assertEqual(row["origin"], "id")

    def test_delete_removes_library_links_and_efforts(self):
        api = FakeApi(details=[detail(1, "A", 1000, 4000)], efforts={1: [effort(1, 900)]})
        lib.import_ids(self.db, self.client(api), [1])
        rid = self.route()
        self.assertEqual(sg.load(self.db, rid)[0].id, 1)
        lib.delete(self.db, 1)
        self.assertIsNone(lib.get(self.db, 1))
        self.assertEqual(lib.library_efforts(self.db, 1), [])
        self.assertEqual(sg.load(self.db, rid), [])


class TestLinkOffline(Base):
    def test_importing_a_route_links_the_library_without_network(self):
        api = FakeApi(details=[detail(1, "Subida da Serra", 1000, 4000),
                               detail(2, "Ao contrário", 4000, 1000),
                               detail(3, "Noutra estrada", 1500, 2500, lon=LON0 + 0.01)],
                      efforts={1: [effort(1, 880), effort(2, 950)]})
        lib.import_ids(self.db, self.client(api), [1, 2, 3])
        n_calls = len(api.calls)
        rid = self.route()                                   # importar a rota liga sozinho
        got = sg.load(self.db, rid)
        self.assertEqual([s.name for s in got], ["Subida da Serra"])
        self.assertAlmostEqual(got[0].start_m, 1000, delta=20)
        self.assertAlmostEqual(got[0].end_m, 4000, delta=20)
        self.assertEqual(got[0].pr_s, 900)
        self.assertEqual(got[0].local_best_s, 880)           # o melhor dos esforços importados
        self.assertEqual(len(api.calls), n_calls)            # nenhum pedido: offline

    def test_auto_link_option_off(self):
        api = FakeApi(details=[detail(1, "A", 1000, 4000)], subscription=False)
        lib.import_ids(self.db, self.client(api), [1])
        self.db.set("strava_auto_link", False)
        rid = self.route()
        self.assertEqual(sg.load(self.db, rid), [])
        self.assertEqual(lib.link_route(self.db, rid)["linked"], 1)   # à mão continua a ir

    def test_path_must_be_followed_not_just_start_and_end(self):
        """Um segmento que começa e acaba na rota mas faz um desvio de 400 m não se liga."""
        far = path(1000, 4000)
        far = [(la, lo + (0.005 if 3 <= i <= 9 else 0)) for i, (la, lo) in enumerate(far)]
        api = FakeApi(details=[detail(1, "Com desvio", 1000, 4000, map={"polyline": encode(far)}),
                               detail(2, "Direito", 1000, 4000)], subscription=False)
        lib.import_ids(self.db, self.client(api), [1, 2])
        rid = self.route()
        self.assertEqual([s.name for s in sg.load(self.db, rid)], ["Direito"])

    def test_path_tolerance_is_an_option(self):
        near = [(la, lo + 0.0007) for la, lo in path(1000, 4000)]     # ~60 m ao lado
        api = FakeApi(details=[detail(1, "Ao lado", 1000, 4000, map={"polyline": encode(near)},
                                      start_latlng=[lat_at(1000), LON0],
                                      end_latlng=[lat_at(4000), LON0])], subscription=False)
        lib.import_ids(self.db, self.client(api), [1])
        rid = self.route()
        self.assertEqual(sg.load(self.db, rid), [])
        self.db.set("strava_path_radius_m", 100.0)
        options.apply(self.db)
        try:
            self.assertEqual(lib.link_route(self.db, rid)["linked"], 1)
        finally:
            self.db.set("strava_path_radius_m", 40.0)
            options.apply(self.db)

    def test_far_segments_are_not_even_checked(self):
        api = FakeApi(details=[detail(1, "No Brasil", 1000, 4000, start_latlng=[-22.9, -43.2],
                                      end_latlng=[-22.8, -43.2], map={"polyline": ""})],
                      subscription=False)
        lib.import_ids(self.db, self.client(api), [1])
        self.assertEqual(lib.link_route(self.db, self.route()), {"checked": 0, "linked": 0})


class TestRouteSearchKept(Base):
    def test_search_by_route_still_works_and_feeds_the_library(self):
        api = FakeApi(segments=[tc.seg(1, "Subida da Serra", 1000, 4000),
                                tc.seg(4, "Descida", 4200, 5600)],
                      details=[detail(1, "Subida da Serra", 1000, 4000)], subscription=False)
        rid = self.route()
        rep = sg.fetch_for_route(self.db, self.client(api), rid)
        self.assertEqual(rep["matched"], 2)
        self.assertEqual([s.name for s in sg.load(self.db, rid)],
                         ["Subida da Serra", "Descida"])
        names = {r["segment_id"]: r for r in lib.library(self.db)}
        self.assertEqual(set(names), {1, 4})                 # ficam na biblioteca…
        self.assertEqual(names[1]["pr_s"], 900)              # …o 1 com o detalhe
        self.assertIsNone(names[4]["pr_s"])
        self.assertEqual(names[1]["origin"], "route")

    def test_autosave_option_off(self):
        self.db.set("strava_library_autosave", False)
        api = FakeApi(segments=[tc.seg(1, "S", 1000, 4000)], details=[detail(1, "S", 1000, 4000)])
        sg.fetch_for_route(self.db, self.client(api), self.route())
        self.assertEqual(lib.library(self.db), [])

    def test_route_search_keeps_library_segments_too(self):
        api = FakeApi(segments=[tc.seg(4, "Descida", 4200, 5600)],
                      details=[detail(1, "Só da biblioteca", 1000, 4000)], subscription=False)
        lib.import_ids(self.db, self.client(api), [1])
        rid = self.route()
        rep = sg.fetch_for_route(self.db, self.client(api), rid)
        self.assertEqual({s.name for s in sg.load(self.db, rid)},
                         {"Só da biblioteca", "Descida"})
        self.assertEqual(rep["linked"], 2)               # a da biblioteca + a que a pesquisa guardou

    def test_explore_denied_gives_a_useful_message(self):
        def denied(method, url, params=None, headers=None, timeout=20.0):
            if url == strava.TOKEN_URL:
                return 200, {"access_token": "t", "refresh_token": "r", "expires_at": 10 ** 10}
            return 403, None
        c = strava.StravaClient(self.db, http=denied)
        c.exchange("x")
        with self.assertRaises(strava.StravaError) as e:
            c.explore((0, 0, 1, 1))
        self.assertIn("ID", str(e.exception))
        self.assertEqual(e.exception.status, 403)


class TestScope(Base):
    def test_scope_includes_read_all_and_reauth_detection(self):
        self.assertIn("read_all", strava.SCOPE.split(","))
        c = strava.StravaClient(self.db, http=FakeApi())
        c.exchange("x")                                      # sem scope conhecido
        self.assertTrue(c.needs_reauth)
        c.exchange("x", "read,activity:read,read_all")
        self.assertFalse(c.needs_reauth)
        c.exchange("x", "read,activity:read")
        self.assertTrue(c.needs_reauth)


class TestBackupAndThreads(Base):
    def test_library_travels_in_the_segments_backup(self):
        from perennia.core import backup
        api = FakeApi(details=[detail(1, "A", 1000, 4000)], efforts={1: [effort(1, 880)]})
        lib.import_ids(self.db, self.client(api), [1])
        zp = self.tmp / "b.zip"
        backup.export(self.db, None, zp, ["segmentos"])
        other = Database(self.tmp / "o.db")
        backup.restore(other, None, zp, ["segmentos"])
        self.assertEqual(lib.get(other, 1)["name"], "A")
        self.assertTrue(lib.get(other, 1)["polyline"])
        self.assertEqual([e["elapsed_s"] for e in lib.library_efforts(other, 1)], [880])
        self.assertNotIn("segmentos", [c.key for c in backup.COMPONENTS
                                       if c.key != "segmentos" and "strava_library" in c.tables])

    def test_strava_jobs_use_their_own_connection(self):
        from perennia.ui import connect_screens as cs2
        seen = {}

        def fn(db, client):
            seen["same"] = db is self.db
            seen["rows"] = len(lib.library(db))
            return 1
        lib.save(self.db, detail(1, "A", 1000, 4000), "id")
        job = cs2.strava_job(self.db, FakeApi(), fn)
        job.thread.join(5)
        self.assertTrue(job.done and job.error is None, job.error)
        self.assertFalse(seen["same"])
        self.assertEqual(seen["rows"], 1)             # vê o que a ligação principal gravou


class TestOptions(Base):
    def test_options_bind_the_constants(self):
        self.db.set("strava_match_radius_m", 70.0)
        self.db.set("strava_max_tiles", 12)
        options.apply(self.db)
        try:
            self.assertEqual(sg.MATCH_RADIUS_M, 70.0)
            self.assertEqual(sg.MAX_TILES, 12)
        finally:
            self.db.set("strava_match_radius_m", 45.0)
            self.db.set("strava_max_tiles", 30)
            options.apply(self.db)
        self.assertEqual(sg.MATCH_RADIUS_M, 45.0)


from pyglet.window import key  # noqa: E402
from perennia.ui import connect_screens as cs  # noqa: E402
from perennia.ui import segment_screens as ss  # noqa: E402


def finish(scr) -> None:
    scr.job.thread.join(5)
    scr.update(0.1)


class TestScreens(tg.GuiCase):
    def api(self, **kw):
        kw.setdefault("details", [detail(1, "Subida da Serra", 1000, 4000),
                                  detail(2, "Descida", 4200, 5600)])
        kw.setdefault("subscription", False)
        return FakeApi(**kw)

    def connected_import_screen(self, api):
        scr = cs.StravaImportScreen(self.app, http=api)
        scr.client.exchange("x", "read,read_all,activity:read")
        self.app.push(scr)
        return scr

    def test_import_screen_by_ids_and_links_to_the_route(self):
        scr = self.connected_import_screen(self.api())
        self.select("IDs ou ligações")
        self.type("https://www.strava.com/segments/1 2")
        self.assertIn("2 reconhecidos", scr.list.selected.detail)
        self.pick("Importar estes segmentos")
        finish(scr)
        self.assertEqual({r["segment_id"] for r in lib.library(self.app.db)}, {1, 2})
        names = [s.name for s in sg.load(self.app.db, self.route_id)]   # a rota já existia
        self.assertEqual(names, ["Subida da Serra", "Descida"])
        self.assertEqual(scr.ids_text, "")

    def test_leftover_ids_stay_in_the_field(self):
        self.app.db.set("strava_import_batch", 5)
        ds = [detail(i, f"S{i}", 1000, 2000) for i in range(1, 8)]
        scr = self.connected_import_screen(self.api(details=ds))
        self.select("IDs ou ligações")
        self.type("1 2 3 4 5 6 7")
        self.pick("Importar estes segmentos")
        finish(scr)
        self.assertEqual(lib.parse_ids(scr.ids_text), [6, 7])

    def test_paste_with_ctrl_v(self):
        scr = self.connected_import_screen(self.api())
        orig = cs.clipboard_text
        cs.clipboard_text = lambda w: "strava.com/segments/321\nstrava.com/segments/654"
        try:
            self.select("IDs ou ligações")
            self.assertTrue(scr.on_key(key.V, key.MOD_CTRL))
        finally:
            cs.clipboard_text = orig
        self.assertEqual(lib.parse_ids(scr.ids_text), [321, 654])
        self.assertTrue(scr.on_key(key.DELETE, 0))
        self.assertEqual(scr.ids_text, "")

    def test_import_needs_strava_connected(self):
        scr = cs.StravaImportScreen(self.app, http=self.api())
        self.app.push(scr)
        self.select("IDs ou ligações")
        self.type("1")
        self.find("Importar estes segmentos")
        self.assertFalse(scr.list.selected.enabled)

    def test_starred_and_refresh_buttons(self):
        api = self.api(starred=[1, 2])
        scr = self.connected_import_screen(api)
        self.pick("favoritos")
        finish(scr)
        self.assertEqual(len(lib.library(self.app.db)), 2)
        self.pick("Atualizar a biblioteca")
        finish(scr)
        self.assertEqual(sum(1 for c in api.calls if c[1].endswith("/segments/1")), 2)

    def test_library_tab_detail_and_remove(self):
        api = self.api(efforts={1: [effort(1, 880), effort(2, 950)]}, subscription=True)
        c = strava.StravaClient(self.app.db, http=api)
        c.exchange("x", "read,read_all,activity:read")
        lib.import_ids(self.app.db, c, [1])
        lib.link_all(self.app.db)
        scr = ss.SegmentsScreen(self.app)
        self.app.push(scr)
        scr.set_tab(3)
        labels = [i.label for i in scr.list.items]
        self.assertIn("Subida da Serra", labels)
        self.assertTrue(any("Importar do Strava" in x for x in labels))
        self.assertTrue(any("2 esforços" in i.detail for i in scr.list.items))
        self.pick("Subida da Serra")
        det = self.screen()
        self.assertIsInstance(det, ss.LibrarySegmentDetail)
        self.assertFalse(det.AGENT)
        texts = " ".join(i.label + " " + i.value + " " + i.detail for i in det.list.items)
        self.assertIn("14:40", texts)              # o melhor esforço, 880 s
        self.assertIn("Serra de Teste", texts)     # a rota a que está ligado
        self.pick("Tirar da biblioteca")
        self.press(key.ENTER)                       # confirma
        self.assertIsNone(lib.get(self.app.db, 1))

    def test_library_delete_key_asks_first(self):
        lib.save(self.app.db, detail(1, "Subida da Serra", 1000, 4000), "id")
        scr = ss.SegmentsScreen(self.app)
        self.app.push(scr)
        scr.set_tab(3)
        self.select("Subida da Serra")
        scr.on_key(key.DELETE, 0)
        self.assertIsNotNone(lib.get(self.app.db, 1))      # ainda não: pediu confirmação
        self.press(key.ENTER)
        self.assertIsNone(lib.get(self.app.db, 1))

    def test_route_screen_link_row_works_offline(self):
        lib.save(self.app.db, detail(1, "Subida da Serra", 1000, 4000), "id")
        lib.save(self.app.db, detail(2, "Descida", 4200, 5600), "id")
        self.assertEqual(sg.load(self.app.db, self.route_id), [])   # importados depois da rota
        scr = cs.StravaSegmentsScreen(self.app, self.route_id)
        self.app.push(scr)
        self.pick("Ligar da biblioteca")
        self.assertEqual([s.name for s in sg.load(self.app.db, self.route_id)],
                         ["Subida da Serra", "Descida"])
        self.assertTrue(any("Subida da Serra" in i.label for i in scr.list.items))

    def test_route_search_button_still_there(self):
        scr = cs.StravaSegmentsScreen(self.app, self.route_id)
        self.app.push(scr)
        self.assertIn("Atualizar do Strava", [i.label for i in scr.list.items])

    def test_strava_settings_warn_when_read_all_is_missing(self):
        scr = cs.StravaScreen(self.app, http=self.api())
        scr.client.exchange("x", "read,activity:read")
        scr.enter()
        perm = next(i for i in scr.list.items if i.label == "Permissões")
        self.assertIn("de novo", perm.value)
        scr.client.exchange("x", "read,activity:read,read_all")
        scr.enter()
        perm = next(i for i in scr.list.items if i.label == "Permissões")
        self.assertEqual(perm.value, "completas")

    def test_other_segment_tabs_offer_the_import(self):
        scr = ss.SegmentsScreen(self.app)
        self.app.push(scr)
        self.assertTrue(any("Importar do Strava" in i.label for i in scr.list.items))
        self.assertTrue(any("Novo segmento" in i.label for i in scr.list.items))


if __name__ == "__main__":
    unittest.main()
