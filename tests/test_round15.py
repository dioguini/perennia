"""Ronda 15 — segurança, listas pendentes, opções afináveis, tokens do agente e «AdHoc Analysis».

* segurança: a palavra-passe do Garmin nunca vai para o disco nem para a linha de comandos; o
  XML de fora é recusado se trouxer DTD; um backup não escreve fora da pasta de dados; o OAuth do
  Strava confere o `state`;
* seleção por listas pendentes (Enter/clique) nas linhas onde as setas demoravam;
* as opções afináveis (registo único em `core/options.py`) e o separador «Avançado»;
* os tokens do pedido ao agente, antes de enviar;
* a análise ad hoc: dataset + .csv e o gráfico dinâmico.
"""
from __future__ import annotations

import csv
import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.core import adhoc, agent, backup, garmin_sync, options, safexml  # noqa: E402
from perennia.core.db import Database  # noqa: E402
from perennia.io import strava  # noqa: E402
from perennia.ui import adhoc_screens as ads  # noqa: E402
from perennia.ui import app as app_mod  # noqa: E402
from perennia.ui import sport_screens as ss  # noqa: E402
from perennia.ui.widgets import Dropdown, Item  # noqa: E402

SECRET = "s3gredo-MUITO-secreto"


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_rides(db, n: int = 30) -> None:
    """`n` pedaladas acabadas, uma de dois em dois dias, de ontem para trás."""
    now = datetime.now(timezone.utc) - timedelta(days=1)
    for i in range(n):
        when = now - timedelta(days=i * 2)
        db.conn.execute(
            "INSERT INTO rides(id, name, status, started_at, ftp_at_ride_w, weight_at_ride_kg,"
            " elapsed_s, moving_s, distance_m, avg_power_w, avg_hr, tss) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"id{i}", f"Volta {i}", "completed", _iso(when), 250, 72.0, 3600 + i * 60,
             3500 + i * 60, 30000 + i * 500, 180 + i, 140 + i % 10, 50 + i))
    db.conn.commit()


# =========================================================================== segurança


class TestGarminPassword(unittest.TestCase):
    """A palavra-passe do Garmin só existe na memória; durante a execução vai para um ficheiro
    temporário privado (referido por `password_file`) e tudo é desfeito no fim."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "p.db")
        self.cfg_dir = self.tmp / "cfg"
        self.cfg_dir.mkdir()
        self.db.set("garmindb_config_dir", str(self.cfg_dir))
        self.path = garmin_sync.config_path(self.db)
        garmin_sync.set_session_password(None)
        os.environ.pop(garmin_sync.ENV_PASSWORD, None)

    def tearDown(self):
        garmin_sync.set_session_password(None)
        os.environ.pop(garmin_sync.ENV_PASSWORD, None)

    def all_text(self) -> str:
        return "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                         for p in self.cfg_dir.rglob("*") if p.is_file())

    def test_write_credentials_never_stores_the_password(self):
        garmin_sync.write_credentials(self.path, "daniel", SECRET)
        self.assertNotIn(SECRET, self.all_text())
        self.assertEqual(garmin_sync.credentials(self.path), ("daniel", True))
        self.assertEqual(garmin_sync.password_source(self.path), "session")
        # outra escrita (com o ficheiro já a existir) cria o .bak, também sem a palavra-passe
        garmin_sync.write_credentials(self.path, "daniel2", SECRET)
        self.assertTrue(self.path.with_name(self.path.name + ".bak").exists())
        self.assertNotIn(SECRET, self.all_text())

    def test_environment_variable_wins(self):
        garmin_sync.write_credentials(self.path, "daniel")
        os.environ[garmin_sync.ENV_PASSWORD] = SECRET
        self.assertEqual(garmin_sync.password_source(self.path), "env")

    def test_run_uses_a_private_file_and_cleans_up(self):
        garmin_sync.write_credentials(self.path, "daniel", SECRET)
        seen = {}

        def fake_runner(cmd, **kw):
            seen["cmd"] = list(cmd)
            cfg = json.loads(self.path.read_text(encoding="utf-8"))
            pf = Path(cfg["credentials"]["password_file"])
            seen["file"] = pf
            seen["content"] = pf.read_text(encoding="utf-8")
            seen["mode"] = pf.stat().st_mode & 0o777
            seen["config_has_secret"] = SECRET in self.path.read_text(encoding="utf-8")

            class R:
                returncode, stdout, stderr = 0, "ok", ""
            return R()

        opts = garmin_sync.Options(stats=["activities"])
        opts.download = True
        from perennia.core import importers
        orig = importers.garmindb_cli
        importers.garmindb_cli = lambda: "/usr/bin/garmindb_cli.py"
        try:
            ok, _out = garmin_sync.run_garmindb(self.db, opts, runner=fake_runner)
        finally:
            importers.garmindb_cli = orig
        self.assertTrue(ok)
        self.assertEqual(seen["content"], SECRET)                # o ficheiro tinha-a…
        self.assertFalse(seen["config_has_secret"])              # …mas a configuração não
        self.assertNotIn(SECRET, " ".join(seen["cmd"]))          # nem a linha de comandos
        if os.name == "posix":
            self.assertEqual(seen["mode"], 0o600)
        self.assertFalse(seen["file"].exists())                  # e o ficheiro desapareceu
        cfg = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIsNone(cfg["credentials"]["password_file"])
        self.assertNotIn(SECRET, self.all_text())

    def test_run_without_password_explains_what_is_missing(self):
        garmin_sync.write_credentials(self.path, "daniel")
        with self.assertRaises(garmin_sync.PasswordMissing):
            with garmin_sync.password_for_run(self.db):
                pass

    def test_legacy_plain_password_is_scrubbed_and_adopted(self):
        cfg = garmin_sync.new_config()
        cfg["credentials"].update(user="daniel", password=SECRET)
        self.path.write_text(json.dumps(cfg), encoding="utf-8")
        self.path.with_name(self.path.name + ".bak").write_text(json.dumps(cfg),
                                                                encoding="utf-8")
        garmin_sync.adopt_legacy_password(self.path)
        self.assertNotIn(SECRET, self.all_text())                # saiu do ficheiro e do .bak
        self.assertEqual(garmin_sync.session_password(), SECRET)  # e ficou na memória

    def test_timeout_comes_from_the_option(self):
        self.assertEqual(garmin_sync.SYNC_TIMEOUT_S, options.BY_KEY[
            "garmin_sync_timeout_s"].default)


class TestSafeXml(unittest.TestCase):
    def test_plain_xml_parses(self):
        root = safexml.fromstring("<gpx><trk/></gpx>")
        self.assertEqual(root.tag, "gpx")

    def test_dtd_and_entities_are_refused(self):
        bomb = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;&a;</x>')
        with self.assertRaises(safexml.UnsafeXML):
            safexml.fromstring(bomb)
        with self.assertRaises(safexml.UnsafeXML):
            safexml.fromstring(bomb.encode("utf-16"))             # também em UTF-16

    def test_gpx_import_refuses_a_dtd(self):
        from perennia.core import gpx
        p = Path(tempfile.mkdtemp()) / "mau.gpx"
        p.write_text('<?xml version="1.0"?><!DOCTYPE g [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
                     "<gpx>&e;</gpx>", encoding="utf-8")
        with self.assertRaises(Exception):
            gpx.parse_gpx(p)


class TestBackupPaths(unittest.TestCase):
    def test_paths_outside_the_data_folder_are_refused(self):
        base = Path(tempfile.mkdtemp())
        for bad in ("../fora.txt", "/etc/passwd", "a/../../b", "C:\\x", "a\\b", "", "x\x00y",
                    "D:/x"):
            self.assertIsNone(backup._safe_destination(base, bad), bad)
        ok = backup._safe_destination(base, "rides/a.fit")
        self.assertIsNotNone(ok)
        self.assertTrue(str(ok).startswith(str(base.resolve())))

    def test_option_keys_are_settings_and_secrets_are_connections(self):
        self.assertFalse(backup._is_ligacao("agent_max_output_tokens"))
        self.assertTrue(backup._is_definicao("adhoc_views"))
        self.assertTrue(backup._is_ligacao("strava_tokens"))
        self.assertTrue(backup._is_ligacao("agent_share"))


class TestStravaOAuth(unittest.TestCase):
    def setUp(self):
        self.db = Database(Path(tempfile.mkdtemp()) / "s.db")
        for k in (strava.ENV_CLIENT_ID, strava.ENV_CLIENT_SECRET):
            os.environ.pop(k, None)

    def test_secret_from_environment_is_not_stored(self):
        os.environ[strava.ENV_CLIENT_SECRET] = "do-ambiente"
        try:
            c = strava.StravaClient(self.db)
            self.assertTrue(c.secret_from_env)
            self.assertEqual(c.client_secret, "do-ambiente")
            self.assertEqual(self.db.get("strava_client_secret", ""), "")
        finally:
            os.environ.pop(strava.ENV_CLIENT_SECRET, None)

    def test_auth_url_carries_state_and_the_configured_port(self):
        c = strava.StravaClient(self.db)
        self.assertIn("state=abc", c.auth_url("abc"))
        old = strava.REDIRECT_PORT
        try:
            self.db.set("strava_redirect_port", 9123)
            options.apply(self.db)
            self.assertIn("localhost:9123", c.redirect_uri())
        finally:
            strava.REDIRECT_PORT = old

    def test_callback_without_the_right_state_is_refused(self):
        import threading
        import time
        c = strava.StravaClient(self.db)
        holder = {}

        def opener(url):
            holder["url"] = url

        port = 18723
        old = strava.REDIRECT_PORT
        strava.REDIRECT_PORT = port
        try:
            t = threading.Thread(target=lambda: holder.setdefault(
                "ok", strava.authorize_interactive(c, opener, timeout=2.0)))
            t.start()
            time.sleep(0.4)
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/exchange?code=x&state=errado",
                                       timeout=2)
                refused = False
            except Exception:
                refused = True
            t.join(5)
            self.assertTrue(refused)
            self.assertFalse(holder.get("ok"))
        finally:
            strava.REDIRECT_PORT = old


class TestGitignoreAndConfig(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_claude_folder_and_secrets_are_ignored(self):
        text = (self.ROOT / ".gitignore").read_text(encoding="utf-8")
        for needed in (".claude/", ".env", "*.db"):
            self.assertIn(needed, text)

    def test_no_literal_password_or_key_in_the_code(self):
        import re
        pat = re.compile(r"""(password|passwd|secret|api_key|apikey|token)\s*=\s*["'][^"']{6,}["']""",
                         re.I)
        offenders = []
        for p in list((self.ROOT / "perennia").rglob("*.py")) + list(
                (self.ROOT / "packaging").rglob("*")):
            if p.is_file() and p.suffix in (".py", ".bat", ".sh", ".spec", ".txt"):
                for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore")
                                         .splitlines(), 1):
                    if pat.search(line) and "environ" not in line and "ENV_" not in line:
                        offenders.append(f"{p.relative_to(self.ROOT)}:{n}: {line.strip()[:80]}")
        self.assertEqual(offenders, [])

    def test_no_velolocal_left_outside_the_migration_and_history(self):
        allowed = {"legacy.py", "test_perennia.py", "test_round15.py", "LEIA-ME.txt", "README.md",
                   "RUN.md", "CHANGELOG.md"}
        offenders = []
        for p in list((self.ROOT / "perennia").rglob("*.py")) + list(
                (self.ROOT / "tests").rglob("*.py")) + list(
                (self.ROOT / "packaging").rglob("*")):
            if p.is_file() and p.name not in allowed and "__pycache__" not in str(p):
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if "velolocal" in text.lower():
                    offenders.append(str(p.relative_to(self.ROOT)))
        self.assertEqual(offenders, [])


# ============================================================================ opções


class TestOptions(unittest.TestCase):
    def setUp(self):
        self.db = Database(Path(tempfile.mkdtemp()) / "o.db")

    def test_every_default_is_inside_its_limits_and_typed(self):
        for o in options.OPTIONS:
            self.assertEqual(options.coerce(o, o.default), o.default, o.key)
            if o.lo is not None:
                self.assertTrue(o.lo <= o.default <= o.hi, o.key)
            self.assertIn(o.group, options.GROUPS, o.key)
        self.assertEqual(len({o.key for o in options.OPTIONS}), len(options.OPTIONS))

    def test_bound_constants_start_at_the_default(self):
        for o in options.OPTIONS:
            for module, name in o.binds:
                try:
                    mod = importlib.import_module(module)
                except ImportError:
                    continue
                self.assertEqual(getattr(mod, name), o.default, f"{o.key}: {module}.{name}")

    def test_apply_puts_the_value_in_the_module_and_back(self):
        from perennia.core import ride
        self.db.set("auto_pause_after_s", 7.5)
        options.apply(self.db)
        try:
            self.assertEqual(ride.AUTO_PAUSE_AFTER_S, 7.5)
        finally:
            self.db.set("auto_pause_after_s", 3.0)
            options.apply(self.db)
        self.assertEqual(ride.AUTO_PAUSE_AFTER_S, 3.0)

    def test_values_are_clamped_and_bad_values_fall_back(self):
        self.db.set("adhoc_max_series", 99)
        self.assertEqual(options.get(self.db, "adhoc_max_series"), 7)
        self.db.set("adhoc_max_series", "lixo")
        self.assertEqual(options.get(self.db, "adhoc_max_series"), 6)
        self.db.set("adhoc_csv_sep", "x")
        self.assertEqual(options.get(self.db, "adhoc_csv_sep"), ";")

    def test_stepping(self):
        o = options.BY_KEY["workout_tolerance_pct"]
        self.assertEqual(options.stepped(o, 5.0, 1), 5.5)
        self.assertEqual(options.stepped(o, 5.0, -10), 1.0)            # no limite
        self.assertEqual(options.stepped(o, 24.9, 5), 25.0)
        c = options.BY_KEY["adhoc_csv_sep"]
        self.assertEqual(options.stepped(c, ";", 1), ",")
        self.assertEqual(options.stepped(c, "|", 1), ";")               # dá a volta
        self.assertFalse(options.stepped(options.BY_KEY["adhoc_csv_bom"], True, 1))

    def test_the_defaults_are_used_by_the_modules_that_read_them(self):
        self.assertEqual(agent.AGENT_DEFAULTS, options.defaults("agent_"))
        self.assertEqual(adhoc.DEFAULTS, options.defaults("adhoc_"))
        self.assertEqual(set(adhoc.SEPARATORS), {c[0] for c in options.BY_KEY[
            "adhoc_csv_sep"].choices})

    def test_hub_and_gpx_read_the_constant_when_used(self):
        from perennia.io import hub as hubmod
        old = hubmod.STALE_AFTER_S
        try:
            hubmod.STALE_AFTER_S = 11.0
            self.assertEqual(hubmod.SensorHub()._stale, 11.0)
            self.assertEqual(hubmod.SensorHub(stale_after_s=2.0)._stale, 2.0)
        finally:
            hubmod.STALE_AFTER_S = old


# ====================================================================== tokens (agente)


class TestTokens(unittest.TestCase):
    def setUp(self):
        self.db = Database(Path(tempfile.mkdtemp()) / "t.db")

    def request(self, size: int = 100):
        return {"system": "x" * 350, "instruction": "y" * 70,
                "content": {"pagina": {"texto": "z" * size}, "contexto": {"carga": {"a": 1}}}}

    def test_estimate_uses_the_characters_per_token_option(self):
        self.assertEqual(agent.estimate_tokens("a" * 70, self.db), 20)
        self.db.set("agent_chars_per_token", 7.0)
        self.assertEqual(agent.estimate_tokens("a" * 70, self.db), 10)
        self.assertEqual(agent.estimate_tokens("", self.db), 0)

    def test_report_has_parts_total_and_no_cost_without_prices(self):
        rep = agent.token_report(self.request(), self.db)
        self.assertEqual([p[0] for p in rep["parts"]][:3], ["system", "instruction", "page"])
        self.assertGreater(rep["total"], 0)
        self.assertFalse(rep["priced"])
        self.assertIsNone(rep["max_cost"])
        self.assertFalse(rep["exact"])                  # é uma estimativa local

    def test_cost_and_warning_follow_the_options(self):
        self.db.set("agent_price_in_per_mtok", 3.0)
        self.db.set("agent_price_out_per_mtok", 15.0)
        self.db.set("agent_max_output_tokens", 1000)
        rep = agent.token_report(self.request(), self.db)
        self.assertTrue(rep["priced"])
        self.assertAlmostEqual(rep["max_cost"], (rep["total"] * 3.0 + 1000 * 15.0) / 1e6)
        self.assertFalse(rep["warn"])
        self.db.set("agent_warn_tokens", 500)
        self.assertTrue(agent.token_report(self.request(5000), self.db)["warn"])


# ======================================================================= AdHoc (núcleo)


class TestAdHocCore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = Database(self.tmp / "a.db")
        seed_rides(self.db, 30)

    def test_sessions_load_with_time_columns(self):
        rows = adhoc.load(self.db, "sessions")
        self.assertEqual(len(rows), 30)
        r = rows[-1]
        for k in ("date", "week", "month", "year", "weekday", "hour", "sport", "duration_min",
                  "distance_km", "load"):
            self.assertIn(k, r)
        self.assertEqual(r["sport"], "Ciclismo")
        self.assertRegex(r["week"], r"^\d{4}-W\d{2}$")

    def test_every_source_loads_even_when_empty(self):
        db = Database(self.tmp / "vazia.db")
        for key in adhoc.SOURCE_ORDER:
            self.assertEqual(adhoc.load(db, key), [], key)

    def test_foreign_date_formats_are_understood(self):
        for text in ("2026-03-01T10:00:00Z", "2026-03-01T10:00:00.123Z",
                     "2026-03-01T10:00:00+00:00", "2026-03-01 10:00:00"):
            self.assertIsNotNone(adhoc._parse_iso(text), text)
        self.assertIsNone(adhoc._parse_iso("ontem"))
        self.assertIsNone(adhoc._parse_iso(None))

    def test_weekly_sum_fills_empty_weeks_and_matches_the_total(self):
        spec = adhoc.Spec(x="date", grain="week", y="duration_min", agg="sum")
        rows = adhoc.apply_filters(adhoc.load(self.db, "sessions"), spec)
        pv = adhoc.pivot(self.db, rows, spec)
        total = sum(v or 0 for v in pv.series[0][1])
        self.assertAlmostEqual(total, sum(r["duration_min"] for r in rows), places=3)
        self.assertEqual(pv.labels, sorted(pv.labels))
        self.assertGreater(len(pv.labels), 6)

    def test_average_does_not_invent_zero_for_empty_periods(self):
        spec = adhoc.Spec(x="date", grain="day", y="avg_hr", agg="avg")
        rows = adhoc.load(self.db, "sessions")
        pv = adhoc.pivot(self.db, rows, spec)
        self.assertEqual(len(pv.labels), 30)                 # só os dias com dados
        self.assertTrue(all(v and v >= 140 for v in pv.series[0][1]))
        total = adhoc.pivot(self.db, rows, adhoc.Spec(x="date", grain="day", y="avg_hr",
                                                      agg="sum"))
        self.assertGreater(len(total.labels), 30)            # a soma conta os dias vazios (0)

    def test_series_beyond_the_limit_become_others(self):
        db = self.db
        for i in range(10):
            db.conn.execute(
                "INSERT INTO strength_sessions(id, name, status, started_at) VALUES (?,?,?,?)",
                (f"s{i}", f"Força {i}", "completed", _iso(datetime.now(timezone.utc))))
        db.conn.commit()
        db.set("adhoc_max_series", 2)
        spec = adhoc.Spec(x="sport", y=adhoc.ROWS, series="origin", chart="bars")
        rows = adhoc.load(db, "sessions")
        for k, r in enumerate(rows):                     # origens diferentes
            r["origin"] = f"O{k % 5}"
        pv = adhoc.pivot(db, rows, spec)
        self.assertEqual(len(pv.series), 3)
        self.assertEqual(pv.series[-1][0], "Outros")

    def test_histogram_bins_cover_every_row(self):
        self.db.set("adhoc_bins", 5)
        spec = adhoc.Spec(x="avg_hr", y=adhoc.ROWS, agg="count")
        spec.clean()
        pv = adhoc.pivot(self.db, adhoc.load(self.db, "sessions"), spec)
        self.assertEqual(len(pv.labels), 5)
        self.assertEqual(sum(v or 0 for v in pv.series[0][1]), 30)

    def test_scatter_needs_two_numbers_and_samples(self):
        rows = adhoc.load(self.db, "sessions")
        ok = adhoc.pivot(self.db, rows, adhoc.Spec(x="distance_km", y="duration_min",
                                                   chart="scatter"))
        self.assertEqual(len(ok.points), 30)
        self.db.set("adhoc_max_points", 10)
        sample = adhoc.pivot(self.db, rows, adhoc.Spec(x="distance_km", y="duration_min",
                                                       chart="scatter"))
        self.assertEqual(len(sample.points), 10)
        bad = adhoc.pivot(self.db, rows, adhoc.Spec(x="sport", y="duration_min",
                                                    chart="scatter"))
        self.assertEqual(bad.points, [])
        self.assertTrue(bad.note)

    def test_filters(self):
        rows = adhoc.load(self.db, "sessions")
        f = lambda *flt, **kw: adhoc.apply_filters(  # noqa: E731
            rows, adhoc.Spec(filters=[adhoc.Filter(*flt)], **kw))
        self.assertEqual(len(f("sport", "=", "ciclismo")), 30)
        self.assertEqual(len(f("sport", "!=", "ciclismo")), 0)
        self.assertEqual(len(f("name", "contains", "volta 1")), 11)       # 1, 10…19
        self.assertTrue(all(r["avg_hr"] >= 145 for r in f("avg_hr", ">=", "145")))
        self.assertEqual(len(f("avg_hr", ">", "1000")), 0)
        self.assertEqual(len(f("avg_hr", "=", "texto")), 0)               # número inválido
        recent = adhoc.apply_filters(rows, adhoc.Spec(period="30"))
        self.assertTrue(0 < len(recent) < 30)
        lo = (date.today() - timedelta(days=10)).isoformat()
        rng = adhoc.apply_filters(rows, adhoc.Spec(period="custom", date_from=lo))
        self.assertTrue(all(r["date"] >= lo for r in rng))

    def test_spec_is_cleaned_and_round_trips(self):
        spec = adhoc.Spec.from_dict({"source": "nao-existe", "chart": "pizza", "x": "zzz",
                                     "fields": ["zzz"], "filters": [{"field": "zzz"}],
                                     "series": "sport", "grain": "hora"})
        self.assertEqual(spec.source, "sessions")
        self.assertEqual(spec.chart, "bars")
        self.assertEqual(spec.grain, "week")
        self.assertEqual(spec.filters, [])
        self.assertTrue(spec.fields)
        again = adhoc.Spec.from_dict(spec.to_dict())
        self.assertEqual(again.to_dict(), spec.to_dict())
        counting = adhoc.Spec(y=adhoc.ROWS, agg="sum").clean()
        self.assertEqual(counting.agg, "count")

    def test_defaults_make_sense_for_every_source(self):
        for key in adhoc.SOURCE_ORDER:
            spec = adhoc.defaults_for(key)
            src = adhoc.source_of(key)
            self.assertEqual(spec.source, key)
            self.assertIsNotNone(src.field(spec.x), key)
            self.assertIn(spec.y, [f.key for f in adhoc.y_fields(src)], key)
            self.assertTrue(all(src.field(f) for f in spec.fields), key)

    def test_views_are_saved_replaced_and_deleted(self):
        spec = adhoc.Spec(y="load", agg="avg")
        adhoc.save_view(self.db, "  Carga   média ", spec)
        adhoc.save_view(self.db, "carga média", adhoc.Spec(y="load", agg="max"))     # substitui
        views = adhoc.views(self.db)
        self.assertEqual([v["name"] for v in views], ["carga média"])
        self.assertEqual(adhoc.view_spec(self.db, "carga média").agg, "max")
        with self.assertRaises(ValueError):
            adhoc.save_view(self.db, "   ", spec)
        self.assertTrue(adhoc.delete_view(self.db, "carga média"))
        self.assertFalse(adhoc.delete_view(self.db, "carga média"))
        adhoc.save_state(self.db, spec)
        self.assertEqual(adhoc.load_state(self.db).y, "load")

    def test_ops_by_kind(self):
        self.assertIn(">", adhoc.ops_for(adhoc.NUM))
        self.assertNotIn(">", adhoc.ops_for(adhoc.CAT))
        self.assertEqual(adhoc.ops_for(adhoc.TEXT)[0], "contains")

    def test_pivot_table_is_exportable(self):
        spec = adhoc.Spec(x="week", y="duration_min", agg="sum", series="")
        pv = adhoc.pivot(self.db, adhoc.load(self.db, "sessions"), spec)
        cols, rows = adhoc.pivot_table(pv)
        self.assertEqual(len(rows), len(pv.labels))
        self.assertEqual(len(cols), 2)
        sc = adhoc.pivot(self.db, adhoc.load(self.db, "sessions"),
                         adhoc.Spec(x="distance_km", y="duration_min", chart="scatter"))
        cols, rows = adhoc.pivot_table(sc)
        self.assertEqual(len(rows), 30)


class TestAdHocCsv(unittest.TestCase):
    def setUp(self):
        self.cols = [adhoc.Field("name", "Nome", "Name", adhoc.TEXT),
                     adhoc.Field("value", "Valor", "Value", adhoc.NUM, "kg")]
        self.rows = [{"name": "Agachamento", "value": 102.5},
                     {"name": 'com "aspas"; e ponto e vírgula', "value": 80.0},
                     {"name": "=HYPERLINK(\"http://x\")", "value": None},
                     {"name": "@cmd|' /C calc'!A0", "value": 3}]

    def parse(self, text: str, sep: str):
        return list(csv.reader(io.StringIO(text), delimiter=sep))

    def test_separator_and_decimal(self):
        for sep in (";", ",", "\t", "|"):
            text = adhoc.csv_text(self.cols, self.rows, sep=sep, decimal=",")
            rows = self.parse(text, sep)
            self.assertEqual(rows[0], ["Nome", "Valor (kg)"])
            self.assertEqual(len(rows), 5)
            expect = "102,5" if sep != "," else "102.5"      # a vírgula não pode ser decimal
            self.assertEqual(rows[1][1], expect)
            self.assertEqual(rows[2][0], 'com "aspas"; e ponto e vírgula')

    def test_formulas_are_neutralised(self):
        rows = self.parse(adhoc.csv_text(self.cols, self.rows), ";")
        self.assertTrue(rows[3][0].startswith("'="))
        self.assertTrue(rows[4][0].startswith("'@"))
        self.assertEqual(rows[3][1], "")                     # sem valor: célula vazia

    def test_technical_header(self):
        rows = self.parse(adhoc.csv_text(self.cols, self.rows, header="key"), ";")
        self.assertEqual(rows[0], ["name", "value"])

    def test_safe_filename(self):
        self.assertEqual(adhoc.safe_filename("../../etc/passwd"), "passwd.csv")
        self.assertEqual(adhoc.safe_filename("a:b*c?.csv"), "a_b_c_.csv")
        self.assertEqual(adhoc.safe_filename("  "), "perennia-analise.csv")
        self.assertEqual(adhoc.safe_filename("relatório março"), "relatório março.csv")
        self.assertTrue(len(adhoc.safe_filename("x" * 500)) <= 124)
        self.assertEqual(adhoc.safe_filename("C:\\Users\\x\\saida"), "saida.csv"
                         if os.name == "nt" else "C__Users_x_saida.csv")

    def test_export_never_overwrites_and_writes_bom(self):
        folder = Path(tempfile.mkdtemp()) / "exports"
        a = adhoc.export_csv(self.cols, self.rows, folder, "dados")
        b = adhoc.export_csv(self.cols, self.rows, folder, "dados")
        self.assertEqual((a.name, b.name), ("dados.csv", "dados-2.csv"))
        self.assertTrue(a.read_bytes().startswith(b"\xef\xbb\xbf"))
        c = adhoc.export_csv(self.cols, self.rows, folder, "sem-bom", bom=False)
        self.assertFalse(c.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         ["dados-2.csv", "dados.csv", "sem-bom.csv"])

    def test_export_dir_option(self):
        db = Database(Path(tempfile.mkdtemp()) / "e.db")
        data = Path(tempfile.mkdtemp())
        self.assertEqual(adhoc.export_dir(db, data), data / "exports")
        db.set("adhoc_export_dir", str(data / "meus"))
        self.assertEqual(adhoc.export_dir(db, data), data / "meus")


# ============================================================================ AdHoc (ecrã)


class AdHocCase(tg.GuiCase):
    def setUp(self):
        super().setUp()
        seed_rides(self.app.db, 30)

    def open_adhoc(self) -> ads.AdHocScreen:
        self.app.reset_to_menu(app_mod.HomeScreen)
        self.pick("Estatísticas gerais")
        gen = self.screen()
        self.assertIsInstance(gen, ss.GeneralStatsScreen)
        gen.tab_named("AdHoc")
        scr = self.screen()
        self.assertIsInstance(scr, ads.AdHocScreen)
        return scr

    def row(self, scr, text: str) -> Item:
        for i, item in enumerate(scr.list.items):
            if text.lower() in item.label.lower():
                scr.list.index = i
                scr.list._sync()
                return item
        self.fail(f"sem a linha «{text}» em {[i.label for i in scr.list.items]}")

    def pick_option(self, scr, row: str, option: str) -> None:
        """Abre a lista pendente da linha e escolhe a opção pelo nome (Enter e escreve-se)."""
        item = self.row(scr, row)
        self.assertIsNotNone(item.dropdown, row)
        self.press(key.ENTER)
        pop = self.screen()
        labels = [i.label for i in pop.list.items]
        k = next(i for i, lab in enumerate(labels) if option.lower() in lab.lower())
        pop.list.index = k
        pop.list._sync()
        self.press(key.ENTER)
        self.assertIs(self.screen(), scr)


class TestAdHocTab(AdHocCase):
    def test_tab_is_the_last_one_and_leads_back(self):
        scr = self.open_adhoc()
        self.assertEqual(scr.tab_labels()[-1], "AdHoc Analysis")
        self.assertEqual(scr.tabs.index, len(scr.tab_labels()) - 1)
        self.press(key.TAB)                               # dá a volta: a primeira tab
        gen = self.screen()
        self.assertIsInstance(gen, ss.GeneralStatsScreen)
        self.assertEqual(gen.view, 0)
        scr = self.open_adhoc()
        self.press(key.TAB, key.TAB)                      # Tab, e a seguir Tab outra vez
        self.assertIsInstance(self.screen(), ss.GeneralStatsScreen)

    def test_walks_every_general_tab_with_tab_key(self):
        self.app.reset_to_menu(app_mod.HomeScreen)
        self.pick("Estatísticas gerais")
        seen = set()
        for _ in range(len(ss.GeneralStatsScreen.VIEWS) * 2):
            self.app._on_draw()
            seen.add(type(self.screen()).__name__)
            self.press(key.TAB)
        self.assertEqual(seen, {"GeneralStatsScreen", "AdHocScreen"})

    def test_back_arrow_leaves(self):
        self.open_adhoc()
        self.press(key.ESCAPE)
        self.assertNotIsInstance(self.screen(), ads.AdHocScreen)


class TestAdHocChart(AdHocCase):
    def test_default_view_draws_a_chart_with_the_rows(self):
        scr = self.open_adhoc()
        self.app._on_draw()
        self.assertTrue(scr.chart.points)
        self.assertIn("30", scr.note.text)
        self.assertEqual(scr.n_rows, 30)

    def test_every_chart_type_draws_or_explains(self):
        scr = self.open_adhoc()
        for chart in adhoc.CHARTS:
            self.pick_option(scr, "Tipo de gráfico", adhoc.chart_name(chart))
            self.app._on_draw()
            self.assertEqual(scr.spec.chart, chart)
            self.assertTrue(scr.chart.points, chart)

    def test_series_legend_and_clustered_columns(self):
        scr = self.open_adhoc()
        scr.spec.x, scr.spec.series, scr.spec.chart = "weekday", "sport", "bars"
        scr._touch()
        scr.enter()
        self.app._on_draw()
        self.assertTrue(scr.chart.points)
        scr.spec.series = "origin"
        scr.spec.chart = "stacked"
        scr._touch()
        scr.enter()
        self.assertTrue(scr.chart.points)

    def test_changing_a_value_is_remembered(self):
        scr = self.open_adhoc()
        self.pick_option(scr, "Valor", "Distância")
        self.pick_option(scr, "Agregação", "média")
        self.assertEqual((scr.spec.y, scr.spec.agg), ("distance_km", "avg"))
        again = self.open_adhoc()                       # outra vez: a mesma vista
        self.assertEqual((again.spec.y, again.spec.agg), ("distance_km", "avg"))

    def test_arrows_cycle_the_dropdown_rows(self):
        scr = self.open_adhoc()
        self.row(scr, "Agregação")
        before = scr.spec.agg
        self.press(key.RIGHT)
        self.assertNotEqual(scr.spec.agg, before)
        self.press(key.LEFT)
        self.assertEqual(scr.spec.agg, before)

    def test_changing_the_source_resets_fields_and_filters(self):
        scr = self.open_adhoc()
        scr.spec.filters = [adhoc.Filter("sport", "=", "Ciclismo")]
        self.pick_option(scr, "Fonte", "Diário")
        self.assertEqual(scr.spec.source, "daily")
        self.assertEqual(scr.spec.filters, [])
        self.assertIn(scr.spec.x, [f.key for f in adhoc.source_of("daily").fields])
        self.app._on_draw()                                # sem dados: não deita nada abaixo
        self.assertEqual(scr.chart.points, [])

    def test_scatter_fixes_the_x_axis(self):
        scr = self.open_adhoc()
        self.pick_option(scr, "Tipo de gráfico", "Dispersão")
        xf = adhoc.source_of("sessions").field(scr.spec.x)
        self.assertEqual(xf.kind, adhoc.NUM)
        self.assertTrue(scr.chart.points)

    def test_hit_selects_a_point(self):
        scr = self.open_adhoc()
        self.app._on_draw()
        x, y = scr.chart.points[2]
        self.assertTrue(scr.on_mouse(int(x), int(y)))
        self.assertEqual(scr.chart.selected, 2)

    def test_period_custom_shows_dates(self):
        scr = self.open_adhoc()
        self.pick_option(scr, "Período", "Datas")
        labels = [i.label.strip() for i in scr.list.items]
        self.assertIn("de", labels)
        self.assertIn("até", labels)
        self.assertTrue(scr.spec.date_from and scr.spec.date_to)


class TestAdHocDataset(AdHocCase):
    def test_dataset_mode_shows_a_preview_and_picks_fields(self):
        scr = self.open_adhoc()
        self.pick_option(scr, "Modo", "Dataset")
        self.app._on_draw()
        self.assertEqual(scr.spec.mode, "dataset")
        self.assertTrue(scr.table.rows)
        self.assertLessEqual(len(scr.table.rows), 12)
        item = self.row(scr, "Campos do dataset")
        item.action()
        pop = self.screen()
        self.assertEqual(type(pop).__name__, "MultiChoicePopup")
        pop.selected = ["date", "sport"]
        pop._ok()
        self.assertIs(self.screen(), scr)
        self.assertEqual(scr.spec.fields, ["date", "sport"])
        self.assertEqual(len(scr.table.rows[0]), 2)

    def test_preview_rows_option(self):
        self.app.db.set("adhoc_preview_rows", 3)
        scr = self.open_adhoc()
        scr.spec.mode = "dataset"
        scr.enter()
        self.assertEqual(len(scr.table.rows), 3)

    def test_filter_flow_adds_edits_and_removes(self):
        scr = self.open_adhoc()
        self.row(scr, "Filtros").action()
        pop = self.screen()
        self.assertIsInstance(pop, ads.AdHocFiltersPopup)
        pop.list.items[-1].action()                        # «Adicionar filtro…»
        ed = self.screen()
        self.assertIsInstance(ed, ads.AdHocFilterEditor)
        ed.field = "avg_hr"
        ed.op = ">="
        ed.value = "145"
        ed.save_exit()
        self.assertIsInstance(self.screen(), ads.AdHocFiltersPopup)
        self.assertEqual(len(scr.spec.filters), 1)
        self.assertTrue(all(r["avg_hr"] >= 145 for r in scr.rows or scr._source_rows()
                            if r["avg_hr"] >= 145))
        self.screen().list.items[0].action()               # editar o primeiro
        ed = self.screen()
        ed.value = "abc"
        self.assertFalse(ed.commit())                      # número inválido: recusa
        ed._remove()
        self.assertEqual(scr.spec.filters, [])

    def test_category_filter_offers_the_values_that_exist(self):
        scr = self.open_adhoc()
        ed = ads.AdHocFilterEditor(self.app, scr, None)
        ed.field = "sport"
        self.assertEqual(ed._choices_values(), ["Ciclismo"])
        rows = ed.rows()
        self.assertIsNotNone(rows[2].dropdown)


class TestAdHocExport(AdHocCase):
    def test_export_popup_writes_the_file_with_the_chosen_name_and_separator(self):
        scr = self.open_adhoc()
        scr.spec.mode = "dataset"
        scr.spec.fields = ["date", "name", "distance_km"]
        scr._touch()
        scr.enter()
        folder = Path(tempfile.mkdtemp())
        self.app.db.set("adhoc_export_dir", str(folder))
        self.row(scr, "Exportar").action()
        pop = self.screen()
        self.assertIsInstance(pop, ads.AdHocExportPopup)
        pop.name = "minhas voltas"
        pop.sep = ","
        pop.decimal = ","                                   # igual ao separador → ponto
        pop.save_exit()
        self.assertIs(self.screen(), scr)
        out = folder / "minhas voltas.csv"
        self.assertTrue(out.exists())
        rows = list(csv.reader(io.StringIO(out.read_text(encoding="utf-8-sig")), delimiter=","))
        self.assertEqual(rows[0], ["Data", "Nome", "Distância (km)"])
        self.assertEqual(len(rows), 31)
        self.assertIn(".", rows[1][2])

    def test_chart_numbers_can_be_exported_too(self):
        scr = self.open_adhoc()
        folder = Path(tempfile.mkdtemp())
        self.app.db.set("adhoc_export_dir", str(folder))
        self.row(scr, "Exportar").action()
        pop = self.screen()
        pop.what = "chart"
        pop.name = "grafico"
        pop.save_exit()
        rows = list(csv.reader(io.StringIO((folder / "grafico.csv").read_text("utf-8-sig")),
                               delimiter=";"))
        self.assertEqual(len(rows) - 1, len(scr.pv.labels))

    def test_path_in_the_name_cannot_escape_the_folder(self):
        scr = self.open_adhoc()
        folder = Path(tempfile.mkdtemp()) / "ex"
        self.app.db.set("adhoc_export_dir", str(folder))
        self.row(scr, "Exportar").action()
        pop = self.screen()
        pop.name = "../../fora"
        pop.save_exit()
        self.assertEqual([p.name for p in folder.iterdir()], ["fora.csv"])

    def test_save_and_delete_views(self):
        scr = self.open_adhoc()
        scr.spec.y, scr.spec.agg = "load", "avg"
        scr._touch()
        self.row(scr, "Guardar vista").action()
        pop = self.screen()
        self.assertIsInstance(pop, ads.SaveViewPopup)
        pop.name = "Carga média"
        pop.save_exit()
        self.assertEqual(scr.view_name, "Carga média")
        scr.spec.y = "avg_hr"
        scr.enter()
        self.pick_option(scr, "Vista guardada", "Carga média")
        self.assertEqual((scr.spec.y, scr.spec.agg), ("load", "avg"))
        del_item = next(i for i in scr.list.items if "Apagar vista" in i.label)
        self.assertTrue(del_item.enabled)
        scr._delete_view()
        self.assertIsInstance(self.screen(), app_mod.ConfirmScreen)
        self.screen().options[1][1]()
        self.assertEqual(adhoc.views(self.app.db), [])


# ===================================================== listas pendentes e Definições


class TestDropdowns(tg.GuiCase):
    def test_item_with_dropdown_shows_the_mark_and_opens_a_popup(self):
        picked = []
        scr = self.screen()
        item = Item("Exercício", value="Supino", dropdown=Dropdown(
            ["Agachamento", "Supino", "Remada"], 1, picked.append))
        scr.list.set_items([item])
        self.assertTrue(scr.list.is_dropdown(item))
        scr.list.activate()
        pop = self.screen()
        self.assertEqual(type(pop).__name__, "ChoicePopup")
        pop.list.items[2].action()
        self.assertEqual(picked, [2])
        self.assertIs(self.screen(), scr)

    def test_left_right_still_step_through_the_options(self):
        picked = []
        scr = app_mod.Screen(self.app)
        self.app.push(scr)
        item = Item("X", value="b", dropdown=Dropdown(["a", "b", "c"], 1, picked.append))
        scr.list.set_items([item])
        scr.on_key(key.RIGHT, 0)
        scr.on_key(key.LEFT, 0)
        self.assertEqual(picked, [2, 0])


class TestAdvancedSettings(tg.GuiCase):
    def open_advanced(self):
        self.app.open_settings()
        scr = self.screen()
        self.assertTrue(scr.tab_named("Avançado"))
        return scr

    def row(self, scr, text):
        for i, item in enumerate(scr.list.items):
            if text.lower() in item.label.lower() and not item.header:
                scr.list.index = i
                scr.list._sync()
                return item
        self.fail(f"sem a linha «{text}»")

    def test_every_option_has_a_row(self):
        scr = self.open_advanced()
        labels = {i.label for i in scr.list.items}
        for o in options.OPTIONS:
            self.assertIn(o.label, labels, o.key)

    def test_arrows_change_and_save_applies_to_the_code(self):
        from perennia.core import ride
        scr = self.open_advanced()
        self.row(scr, "Pausa automática")
        self.press(key.RIGHT, key.RIGHT)
        self.assertEqual(scr.draft["auto_pause_after_s"], 4.0)
        self.save()
        self.assertEqual(self.app.db.get("auto_pause_after_s"), 4.0)
        self.assertEqual(ride.AUTO_PAUSE_AFTER_S, 4.0)
        self.app.db.set("auto_pause_after_s", 3.0)
        options.apply(self.app.db)

    def test_shift_gives_ten_steps_and_limits_hold(self):
        scr = self.open_advanced()
        self.row(scr, "Duração dos avisos")
        self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)
        self.assertEqual(scr.draft["message_seconds"], 11.0)
        for _ in range(5):
            self.app._on_key_press(key.RIGHT, key.MOD_SHIFT)
        self.assertEqual(scr.draft["message_seconds"], 20.0)       # o limite

    def test_typed_values_only_count_inside_the_limits(self):
        scr = self.open_advanced()
        self.row(scr, "Porta do retorno")
        scr.on_text("9")                                            # 9: fora dos limites
        self.assertNotIn("strava_redirect_port", scr.draft)
        scr.on_text("123")                                          # 9123
        self.assertEqual(scr.draft["strava_redirect_port"], 9123)

    def test_choice_and_text_rows(self):
        scr = self.open_advanced()
        item = self.row(scr, "separador de valores")
        self.assertIsNotNone(item.dropdown)
        self.press(key.RIGHT)
        self.assertEqual(scr.draft["adhoc_csv_sep"], ",")
        self.row(scr, "pasta das exportações")
        scr.on_text("/tmp/xyz")
        self.assertEqual(scr.draft["adhoc_export_dir"], "/tmp/xyz")
        scr.text_backspace("opt_adhoc_export_dir")
        self.assertEqual(scr.draft["adhoc_export_dir"], "/tmp/xy")

    def test_cancel_discards(self):
        scr = self.open_advanced()
        self.row(scr, "Contagem antes")
        self.press(key.RIGHT)
        self.assertTrue(scr.dirty)
        scr.cancel()
        self.assertFalse(scr.dirty)
        self.assertEqual(options.get(self.app.db, "session_countdown_s"), 0)   # o que estava

    def test_not_available_during_a_session(self):
        scr = app_mod.SettingsScreen(self.app, session=self.app.current)
        self.assertNotIn("Avançado", scr.tab_labels())


class TestScanDurations(tg.GuiCase):
    def test_scan_durations_are_options_and_reach_the_scan(self):
        from perennia.io import ble as ble_io
        seen = {}
        orig_ble, orig_avail = ble_io.scan, ble_io.bleak_available
        ble_io.bleak_available = lambda: True
        ble_io.scan = lambda timeout=0, **kw: seen.setdefault("ble", timeout) and []
        self.addCleanup(setattr, ble_io, "scan", orig_ble)
        self.addCleanup(setattr, ble_io, "bleak_available", orig_avail)
        self.assertEqual(float(options.get(self.app.db, "ble_scan_s")), 8.0)     # por omissão
        self.assertEqual(float(options.get(self.app.db, "ant_scan_s")), 12.0)
        self.app.db.set("ble_scan_s", 5.0)
        self.app.open_devices()
        scr = self.screen()
        scr._scan()
        import time
        for _ in range(100):
            if "ble" in seen:
                break
            time.sleep(0.02)
        self.assertEqual(seen.get("ble"), 5.0)


class TestMessageAndCountdown(tg.GuiCase):
    def test_message_duration_is_an_option(self):
        self.app.db.set("message_seconds", 2.0)
        self.assertEqual(float(options.get(self.app.db, "message_seconds")), 2.0)

    def test_countdown_option_reaches_the_countdown(self):
        from perennia.ui.widgets import StartCountdown
        self.app.db.set("session_countdown_s", 5)
        self.assertEqual(StartCountdown.for_app(self.app).left, 5.0)


class TestAdhocCommandLine(unittest.TestCase):
    """`python main.py --adhoc-exportar …`: o .csv sem abrir a janela."""

    def setUp(self):
        import contextlib
        import io
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        db = Database(self.dir / "perennia.db")
        seed_rides(db, 6)
        db.close()
        self.out = contextlib.redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)
        self.err = contextlib.redirect_stderr(io.StringIO())
        self.err.__enter__()
        self.addCleanup(self.err.__exit__, None, None, None)

    def ns(self, **kw):
        import argparse
        base = dict(data_dir=str(self.dir), adhoc_exportar="sessions", vista=None, nome=None,
                    separador=None, decimal=None, destino=str(self.dir / "saida"))
        base.update(kw)
        return argparse.Namespace(**base)

    def test_exports_the_default_fields_with_name_and_separator(self):
        import main as main_mod
        rc = main_mod.adhoc_cli(self.ns(nome="as-minhas", separador="tab"))
        self.assertEqual(rc, 0)
        f = self.dir / "saida" / "as-minhas.csv"
        self.assertTrue(f.exists())
        lines = f.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(len(lines), 1 + 6)                    # cabeçalho + 6 sessões
        self.assertGreater(len(lines[0].split("\t")), 2)       # separador: tab

    def test_never_overwrites_a_file(self):
        import main as main_mod
        for _ in range(2):
            self.assertEqual(main_mod.adhoc_cli(self.ns(nome="x")), 0)
        names = sorted(p.name for p in (self.dir / "saida").glob("*.csv"))
        self.assertEqual(names, ["x-2.csv", "x.csv"])

    def test_bad_input_is_an_error_not_a_crash(self):
        import main as main_mod
        self.assertEqual(main_mod.adhoc_cli(self.ns(adhoc_exportar="nao-existe")), 2)
        self.assertEqual(main_mod.adhoc_cli(self.ns(separador="xx")), 2)
        self.assertEqual(main_mod.adhoc_cli(self.ns(decimal="x")), 2)
        self.assertEqual(main_mod.adhoc_cli(self.ns(vista="não há")), 2)
        # um nome com pastas fica só com o nome do ficheiro, dentro da pasta de destino
        self.assertEqual(main_mod.adhoc_cli(self.ns(nome="../fora")), 0)
        self.assertFalse((self.dir / "fora.csv").exists())
        self.assertTrue((self.dir / "saida" / "fora.csv").exists())

    def test_a_saved_view_is_used(self):
        import main as main_mod
        db = Database(self.dir / "perennia.db")
        spec = adhoc.defaults_for("sessions")
        adhoc.save_view(db, "Poucas", spec)
        db.close()
        self.assertEqual(main_mod.adhoc_cli(self.ns(vista="Poucas", nome="v")), 0)
        self.assertTrue((self.dir / "saida" / "v.csv").exists())

    def test_the_option_defaults_apply_when_nothing_is_given(self):
        import main as main_mod
        db = Database(self.dir / "perennia.db")
        db.set("adhoc_csv_sep", ",")
        db.set("adhoc_csv_bom", False)
        db.close()
        self.assertEqual(main_mod.adhoc_cli(self.ns(nome="o")), 0)
        raw = (self.dir / "saida" / "o.csv").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b",", raw.splitlines()[0])


class TestBackupRoundTrip(unittest.TestCase):
    """As opções do Avançado e as vistas da AdHoc vão nos backups com as Definições."""

    def setUp(self):
        self.a = Path(tempfile.mkdtemp())
        self.b = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.a, True)
        self.addCleanup(shutil.rmtree, self.b, True)

    def test_options_and_views_come_back_and_secrets_stay_out(self):
        da = Database(self.a / "perennia.db")
        da.set("auto_pause_after_s", 4.5)
        da.set("adhoc_csv_sep", ",")
        da.set("agent_chars_per_token", 3.0)            # opção «agent_…»: definição, não segredo
        da.set("strava_client_secret", SECRET)
        da.set("agent_share", {"x": 1})
        adhoc.save_view(da, "A minha", adhoc.defaults_for("sessions"))
        info = backup.export(da, self.a, self.a / "b.zip", keys=["definicoes"])
        da.close()
        names = " ".join(zipfile.ZipFile(info["path"]).namelist())
        raw = b"".join(zipfile.ZipFile(info["path"]).read(n)
                       for n in zipfile.ZipFile(info["path"]).namelist())
        self.assertNotIn(SECRET.encode(), raw)
        self.assertTrue(names)
        db = Database(self.b / "perennia.db")
        backup.restore(db, self.b, info["path"], keys=["definicoes"], mode="replace",
                       safety=False)
        self.assertEqual(float(options.get(db, "auto_pause_after_s")), 4.5)
        self.assertEqual(options.get(db, "adhoc_csv_sep"), ",")
        self.assertEqual(float(options.get(db, "agent_chars_per_token")), 3.0)
        self.assertEqual([v["name"] for v in adhoc.views(db)], ["A minha"])
        self.assertIsNone(db.get("strava_client_secret", None))
        self.assertIsNone(db.get("agent_share", None))
        db.close()


if __name__ == "__main__":
    unittest.main()
