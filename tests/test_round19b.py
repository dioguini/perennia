"""Ronda 19 (parte 2): complexos, catálogo, pastas, planos em CSV, regras do histórico, índices
e a sincronização por Wi-Fi."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402,F401

from perennia.core import (backup, complexes, folders, glossary, gym, gym_catalog,  # noqa: E402
                           history_etl as he, indexes, lan_sync as ls, plan_csv, programs,
                           tags)
from perennia.core import strength as st  # noqa: E402
from perennia.core import file_import  # noqa: E402
from perennia.core.db import Athlete, Database  # noqa: E402
from tests.test_round19 import Tmp, run  # noqa: E402
from tests.test_strength import FakeHR  # noqa: E402


class TestComplexes(Tmp):
    def test_builtin_complexes_and_catalog_are_seeded_once(self):
        gym.ensure(self.db)
        cx = complexes.complexes(self.db)
        self.assertGreaterEqual(len(cx), 6)
        names = {w["name"] for w in st.workouts(self.db)}
        for n in gym_catalog.names():
            self.assertIn(n, names)               # também os que precisam de complexos
        total = self.db.conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0]
        self.assertGreater(total, 300)
        gym.ensure(self.db)                       # repetir não duplica
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM exercises").fetchone()[0],
                         total)

    def test_a_deleted_catalog_workout_does_not_come_back(self):
        gym.ensure(self.db)
        w = next(w for w in st.workouts(self.db) if w["name"] == gym_catalog.names()[0])
        gym.delete_plan(self.db, w["id"]) if hasattr(gym, "delete_plan") else \
            st.delete_workout(self.db, w["id"])
        gym_catalog.seed_workouts(self.db)
        self.assertNotIn(w["name"], {x["name"] for x in st.workouts(self.db)})

    def test_complex_rules_and_progress_in_components(self):
        gym.ensure(self.db)
        ex = {e["name"]: e["id"] for e in self.db.conn.execute(
            "SELECT id, name FROM exercises").fetchall()} if False else {
            r["name"]: r["id"] for r in self.db.conn.execute("SELECT id, name FROM exercises")}
        a, b = ex[next(iter(n for n in ex if "Swing" in n))], ex[next(iter(
            n for n in ex if "Clean" in n))]
        cid = complexes.save_complex(self.db, None, "Meu complexo", [(a, 5), (b, 3)])
        self.assertTrue(complexes.is_complex(self.db, cid))
        self.assertEqual([p["reps"] for p in complexes.parts(self.db, cid)], [5, 3])
        self.assertEqual([p["reps"] for p in complexes.expand(self.db, cid, 4)], [20, 12])
        with self.assertRaises(ValueError):
            complexes.save_complex(self.db, None, "Complexo de complexo", [(cid, 1)])
        with self.assertRaises(ValueError):
            complexes.save_complex(self.db, None, "  ", [(a, 1)])
        # numa sessão: o complexo vira os seus exercícios e a correção das rondas refaz-os
        wid = gym.save_plan(self.db, None, "Com complexo", "",
                            [{"exercise_id": cid, "sets": 2, "reps": 3, "load_kg": 16.0,
                              "rpe": None, "rest_s": 30}], mod="kettlebell")
        ses = st.StrengthSession(self.db, self.db.athlete(), str(wid), sensors=FakeHR(120),
                                 out_dir=self.tmp / "strength")
        for _ in range(2):
            ses.action()
            run(ses, 10)
            ses.action()
            run(ses, 5)
        first = ses.sets[0]
        parts = complexes.set_parts(self.db, first.id)
        self.assertEqual([p["reps"] for p in parts], [15, 9])        # 3 rondas × (5, 3)
        ses.edit_done_set(first.id, reps=2, load_kg=first.load_kg, rpe=None)
        self.assertEqual([p["reps"] for p in complexes.set_parts(self.db, first.id)], [10, 6])
        ses.finish()
        prog = complexes.component_progress(self.db, a)
        self.assertTrue(prog)
        self.assertGreaterEqual(sum(x["reps_in_complexes"] for x in prog), 10)


class TestFolders(Tmp):
    """As pastas deixaram de ser configuráveis (ronda 29): tudo em data/in e data/out."""

    def test_fixed_folders_inside_the_data_folder(self):
        self.assertEqual(folders.in_dir("history", self.tmp), self.tmp / "in" / "historico")
        self.assertEqual(folders.out_dir("workouts", self.tmp), self.tmp / "out" / "treinos")
        self.db.set("path_exports", str(self.tmp / "outra"))       # um valor antigo: ignorado
        self.assertEqual(folders.out_dir("workouts", self.tmp), self.tmp / "out" / "treinos")
        for old in ("resolve", "ensure_dir", "search_list", "check", "KEYS"):
            self.assertFalse(hasattr(folders, old), old)


class TestPlanCsv(Tmp):
    def test_template_round_trip_and_json_equivalence(self):
        p = plan_csv.write_template(self.tmp)
        plan = programs.read_file(p)
        self.assertEqual(plan["weeks"], 4)
        self.assertEqual(plan["rotation"], ["A", "B"])
        again = plan_csv.parse(plan_csv.export_text(plan))
        self.assertEqual(again["sessions"], plan["sessions"])
        key = programs.import_file(self.db, p)
        self.assertEqual(programs.get(self.db, key)["origin"], "imported")

    def test_per_week_values_schedule_and_comma_delimiter(self):
        t = ("# nome: T\n# semanas: 3\n# semana 1: A\n# semana 2: B,A\n"
             "sessao,exercicio,grupo,series,reps,carga_kg\n"
             "A,Agachamento,legs,3,8-12,60|65|70\nB,Supino,chest,3,5,40\n")
        p = plan_csv.parse(t)
        self.assertEqual(p["schedule"], [["A"], ["B", "A"], ["B", "A"]])
        blk = p["sessions"]["A"]["blocks"][0]["exercises"][0]
        self.assertEqual((blk["reps"], blk["load"]), ("8-12", [60.0, 65.0, 70.0]))

    def test_bad_files_are_refused_with_a_reason(self):
        for bad in ("", "sessao;x\n1;2\n", "# nome: a\nsessao;exercicio\n"):
            with self.assertRaises(programs.PlanError):
                plan_csv.parse(bad)
        big = self.tmp / "grande.perennia-plan.csv"
        big.write_text("a" * 3000)
        with self.assertRaises(programs.PlanError):
            plan_csv.read_file(big, max_kb=1)

    def test_scan_finds_csv_plans(self):
        plan_csv.write_template(self.tmp)
        self.assertEqual([p.name for p in programs.scan([str(self.tmp)])],
                         ["plano-modelo.perennia-plan.csv"])


class TestHistoryEtl(Tmp):
    def _tp(self):
        f = self.tmp / "tp.csv"
        f.write_text("Title,WorkoutType,WorkoutDay,TimeTotalInHours,DistanceInMeters,"
                     "HeartRateAverage,TSS\nForça A,Strengthening,2024-01-02,1.0,,120,40\n"
                     "Rolo,Bike,2024-01-03,1.5,40000,140,80\nZumba,Dance,2024-01-04,1,,100,20\n"
                     "Plano,Bike,2024-01-05,,,,\n")
        return f

    def test_import_normalizes_with_starter_rules_and_reports_unmapped(self):
        rep, text = file_import.import_file(self.db, "trainingpeaks", self._tp())
        rows = {r["source_sport"]: r for r in
                self.db.conn.execute("SELECT * FROM synced_activities")}
        self.assertEqual(rows["Strengthening"]["sport"], "gym")
        self.assertEqual(rows["Bike"]["sport"], "cycling")
        self.assertEqual(rows["Dance"]["sport"], "other")
        self.assertEqual(tags.load(self.db, "gym", rows["Strengthening"]["id"])["workout_type"],
                         "strength")
        self.assertIn("Dance", text)                          # «sem regra»

    def test_dry_run_changes_nothing_and_custom_rules_win(self):
        self.db.set("etl_auto_apply", False)
        file_import.import_file(self.db, "trainingpeaks", self._tp())
        rules = he.parse_rules(json.dumps({"regras": [
            {"fonte": "trainingpeaks", "campo": "tipo", "operador": "igual", "valor": "Dance",
             "desporto": "gym", "tipo_treino": "mobility", "etiquetas": ["Dança"]},
            {"campo": "titulo", "operador": "contem", "valor": "rolo", "ignorar": True}]}))
        rep = he.normalize(self.db, rules, dry_run=True)
        self.assertEqual((rep["changed"], rep["removed"]), (1, 1))
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM synced_activities").fetchone()[0], 3)
        rep = he.normalize(self.db, rules, dry_run=False)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM synced_activities").fetchone()[0], 2)
        d = self.db.conn.execute("SELECT id, sport FROM synced_activities WHERE source_sport ="
                                 " 'Dance'").fetchone()
        self.assertEqual(d["sport"], "gym")
        info = tags.load(self.db, "gym", d["id"])
        self.assertEqual((info["workout_type"], info["custom"]), ("mobility", ["Dança"]))
        # aplicar outra vez não muda nada
        self.assertEqual(he.normalize(self.db, rules, dry_run=False)["changed"], 0)

    def test_strava_and_garmin_csv_import_is_idempotent_and_keeps_normalization(self):
        f = self.tmp / "strava.csv"
        f.write_text('Activity ID,Activity Date,Activity Name,Activity Type,Elapsed Time,'
                     'Distance,Max Heart Rate,Elapsed Time,Moving Time,Distance\n'
                     '1,"Jun 5, 2020, 7:30:00 AM",Morning Run,Run,3600,10.5,170,3600,3500,10500.0\n'
                     '2,"Jun 6, 2020, 7:30:00 AM",Gym,Weight Training,3000,0,150,3000,3000,0\n')
        rep, text = file_import.import_file(self.db, "historico", f)
        self.assertEqual((rep["source"], rep["activities"], rep["new"]), ("strava", 2, 2))
        file_import.import_file(self.db, "historico", f)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM synced_activities").fetchone()[0], 2)
        sports = {r["source_sport"]: r["sport"] for r in
                  self.db.conn.execute("SELECT * FROM synced_activities")}
        self.assertEqual(sports, {"Run": "running", "Weight Training": "gym"})
        g = self.tmp / "garmin.csv"
        g.write_text("Activity Type,Date,Favorite,Title,Distance,Calories,Time,Avg HR,Max HR\n"
                     "Cycling,2021-03-04 08:00:00,false,Pedalada,25.5,600,01:10:00,140,170\n")
        rep, _ = file_import.import_file(self.db, "historico", g)
        self.assertEqual(rep["source"], "garmin")
        r = self.db.conn.execute("SELECT * FROM synced_activities WHERE source = 'garmin'"
                                 ).fetchone()
        self.assertEqual((r["sport"], r["distance_m"], r["elapsed_s"]), ("cycling", 25500.0, 4200.0))

    def test_rule_files_json_csv_and_errors(self):
        csv_rules = ("fonte;campo;operador;valor;desporto;tipo_treino;etiquetas\n"
                     "*;tipo;igual;pilates;gym;mobility;Pilates|Core\n")
        (r,) = he.parse_rules(csv_rules, True)
        self.assertEqual((r["desporto"], r["tipo_treino"], r["etiquetas"]),
                         ("gym", "mobility", ["Pilates", "Core"]))
        for bad in ('{"regras":[{"campo":"tipo","valor":"x"}]}',
                    '{"regras":[{"campo":"tipo","valor":"x","desporto":"foo"}]}',
                    '{"regras":[{"campo":"tipo","valor":"(","operador":"regex","desporto":"gym"}]}',
                    '{"regras":[]}', "{"):
            with self.assertRaises(he.RulesError):
                he.parse_rules(bad)
        path = he.write_template(self.tmp)
        self.assertGreater(len(he.load_rules(path)), 20)
        self.assertNotEqual(he.write_template(self.tmp), path)      # nunca substitui


class TestIndexes(Tmp):
    def test_indexes_are_created_once(self):
        backup.prepare(self.db)
        indexes.ensure(self.db)
        self.assertEqual(indexes.ensure(self.db), 0)
        names = {r[0] for r in self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("ix_perf_row_laps_session_id", names)


class TestLanSync(unittest.TestCase):
    def setUp(self):
        self.a, self.b = (Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()))
        self.src, self.dst = Database(self.a / "p.db"), Database(self.b / "p.db")
        for d in (self.src, self.dst):
            d.set("sync_kdf_iterations", 10000)
            d.set("sync_timeout_s", 10)
        self.src.set("path_exports", "/origem")
        self.dst.set("path_exports", "/destino")
        glossary.ensure(self.src)
        self.src.conn.execute("INSERT INTO glossary(term, definition) VALUES ('termo-teste', "
                              "'x')") if False else None

    def tearDown(self):
        for d in (self.src, self.dst):
            d.close()
        for p in (self.a, self.b):
            shutil.rmtree(p, ignore_errors=True)

    def _receiver(self, **kw):
        rx = ls.Receiver(self.dst, self.b, port=0, host="127.0.0.1", **kw)
        port = rx.open()
        out = {}
        t = threading.Thread(target=lambda: out.update(r=rx.wait()), daemon=True)
        t.start()
        return rx, port, t, out

    def test_athlete_and_data_travel_and_machine_settings_stay(self):
        self.src.save_athlete(Athlete(name="Fonte", birth_year=1990, weight_kg=70, ftp_w=260,
                                      lthr=170))
        rx, port, t, out = self._receiver()
        sent = ls.send(self.src, self.a, "127.0.0.1", rx.pin, port, ["perfil", "glossario"],
                       "replace")
        t.join(10)
        self.assertEqual(rx.status, "received")
        self.assertEqual(sent["keys"], ["perfil", "glossario"])
        rep = rx.apply()
        self.assertEqual(rep["mode"], "replace")
        self.assertEqual(self.dst.athlete().name, "Fonte")
        self.assertEqual(self.dst.get("path_exports"), "/destino")     # a máquina não se mexe
        self.assertFalse(list((self.b / "sync").glob("entrada-*.zip")))  # limpo no fim

    def test_wrong_pin_is_refused_and_receiver_closes_after_attempts(self):
        rx, port, t, out = self._receiver()
        for _ in range(int(self.dst.get("sync_max_attempts", 3) or 3)):
            with self.assertRaises(ls.SyncError):
                ls.send(self.src, self.a, "127.0.0.1", "00000000", port, ["perfil"], "merge")
        t.join(10)
        self.assertEqual(rx.status, "failed")
        self.assertIsNone(out.get("r"))
        self.assertNotEqual(self.dst.athlete().name, "Fonte")

    def test_credentials_never_travel_and_never_apply(self):
        self.assertNotIn("ligacoes", ls.components(self.src, ["ligacoes", "perfil"]))
        self.assertNotIn("definicoes", ls.components(self.src))       # a máquina fica de fora
        # um remetente malicioso a pedir «ligacoes» não consegue
        rx, port, t, out = self._receiver()
        import socket as s
        import ssl
        import hashlib
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with ctx.wrap_socket(s.create_connection(("127.0.0.1", port), 10)) as tls:
            fp = ls.fingerprint(tls.getpeercert(binary_form=True))
            nonce = ls._read_line(tls)["nonce"]
            ls._send_line(tls, {"mac": ls._mac(rx.pin, "C", nonce, fp, rx.iterations)})
            self.assertTrue(ls._read_line(tls)["ok"])
            data = b"x" * 10
            ls._send_line(tls, {"keys": ["ligacoes"], "mode": "replace", "bytes": len(data),
                                "sha256": hashlib.sha256(data).hexdigest()})
            self.assertFalse(ls._read_line(tls)["ok"])
        rx.cancel()
        t.join(10)
        self.assertIsNone(rx.result)

    def test_package_size_limit_and_lan_only(self):
        self.src.set("sync_lan_only", True)
        with self.assertRaises(ls.SyncError):
            ls.send(self.src, self.a, "8.8.8.8", "12345678", 9, ["perfil"], "merge")
        self.assertTrue(ls.is_local("192.168.1.5"))
        self.assertTrue(ls.is_local("10.0.0.2"))
        self.assertFalse(ls.is_local("8.8.8.8"))
        self.assertFalse(ls.is_local("nonsense"))
        self.src.set("sync_max_mb", 16)
        self.assertEqual(ls.mode_of(self.src), "merge")

    def test_pin_has_requested_digits_and_expires(self):
        self.assertEqual(len(ls.new_pin(8)), 8)
        self.assertTrue(ls.new_pin(12).isdigit())
        self.dst.set("sync_pin_ttl_s", 30)
        rx = ls.Receiver(self.dst, self.b, port=0, host="127.0.0.1")
        rx.open()
        rx.ttl = 0
        self.assertIsNone(rx.wait())
        self.assertEqual(rx.status, "closed")


class TestGarminDiscovery(Tmp):
    def test_cli_is_found_next_to_this_python_and_run_with_it(self):
        from perennia.core import importers, garmin_sync as gs
        scripts = self.tmp / "venv" / "Scripts"
        scripts.mkdir(parents=True)
        cli = scripts / "garmindb_cli.py"
        cli.write_text("print('x')\n")
        orig = importers.cli_search_dirs
        importers.cli_search_dirs = lambda: [str(scripts)]
        import shutil as sh
        orig_which, sh.which = sh.which, lambda *a, **k: None
        try:
            self.assertEqual(importers.garmindb_cli(), str(cli))
            self.assertEqual(importers.launcher(str(cli)), [sys.executable, str(cli)])
            self.assertEqual(importers.launcher("/usr/bin/garmindb_cli"),
                             ["/usr/bin/garmindb_cli"])
        finally:
            importers.cli_search_dirs = orig
            sh.which = orig_which

    def test_sync_without_the_databases_is_an_error_not_zero_records(self):
        from perennia.core import garmin_sync as gs
        old = folders._ROOT
        folders.set_root(self.tmp / "vazio")                   # data/garmin/bases sem nada
        try:
            ok, msg, rep = gs.sync(self.db, gs.Options(), run_source=False)
        finally:
            folders._ROOT = old
        self.assertFalse(ok)
        self.assertIn("garmin.db", msg)
        self.assertIsNone(rep)


# ================================================================== interface


from tests import test_gui as tg  # noqa: E402


class TestScreens(tg.GuiCase):
    def test_settings_has_a_folders_tab_with_every_folder(self):
        self.app.pop()                                         # volta ao ecrã inicial
        self.pick("Definições")
        scr = self.screen()
        self.assertTrue(scr.tab_named("Pastas"))
        labels = " | ".join(i.label for i in scr.list.items)
        values = " | ".join(str(i.value) for i in scr.list.items)
        for k in folders.IN:
            self.assertIn(folders.name_in(k), labels)
            self.assertIn("/in/" + folders.IN[k], values.replace("\\", "/"))   # data/in/…
        for k in folders.OUT:
            self.assertIn(folders.name_out(k), labels)
        self.assertTrue(all(not i.enabled for i in scr.list.items if not i.header))  # só info

    def test_wifi_and_history_tabs_open_their_screens(self):
        from perennia.ui import lan_sync_screens as lss
        from perennia.ui.backup_screens import BackupScreen
        scr = BackupScreen(self.app, tab=2)
        self.app.push(scr)
        for name, first in (("Histórico", "Regras de normalização"), ("Wi-Fi", "Como funciona")):
            scr.sync_tab = [n for _k, n in scr.sync.SOURCES].index(name)
            scr.enter()
            self.assertIn(first, [i.label for i in scr.list.items])
        send = lss.LanSendScreen(self.app)
        self.app.push(send)
        self.assertIn("Enviar", [i.label for i in send.list.items])
        self.app.pop()
        rx = lss.LanReceiveScreen(self.app)
        self.app.db.set("sync_port", 1024 + 7000)
        self.app.push(rx)
        try:
            labels = [i.label for i in rx.list.items]
            self.assertIn("PIN (uso único)", labels)
        finally:
            self.app.pop()
        # sair do ecrã não pára a escuta (ronda 35): continua, e vê-se no topo
        self.assertTrue(rx.task.running)
        self.assertIn("Wi-Fi", self.app.topbar.task_text)
        rx.task.cancel()                                       # «Parar»: fecha a porta
        rx.thread.join(5)
        self.assertEqual(rx.rx.status, "closed")


if __name__ == "__main__":
    unittest.main()
