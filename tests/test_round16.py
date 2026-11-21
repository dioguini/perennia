"""Ronda 16: pressão arterial com várias medições por período, separadores da Saúde com notas,
o Assistente de saúde, o Treinador (sessão, eventos, desafios, longevidade, construtor) e a
escolha regras / LLM local / agente online com os tokens à vista."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from perennia.core import adhoc, advisor, backup, bp, coach, health, health_tabs, options
from perennia.core import blocks as bl
from perennia.core import calendar_view as cal
from perennia.core import health_assistant as ha
from perennia.core.db import Athlete, Database
from perennia.core.i18n import PT, set_language
from tests import test_gui as tg

TODAY = date.today()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_rides(db, n: int = 30, tss: float = 50.0, every: int = 2, secs: int = 3600) -> None:
    """`n` pedaladas acabadas, de ontem para trás, com a mesma carga."""
    now = datetime.now(timezone.utc).replace(hour=12) - timedelta(days=1)
    for i in range(n):
        when = now - timedelta(days=i * every)
        db.conn.execute(
            "INSERT INTO rides(id, name, status, started_at, ftp_at_ride_w, weight_at_ride_kg,"
            " elapsed_s, moving_s, distance_m, avg_power_w, avg_hr, max_hr, tss) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"r{i}", f"Volta {i}", "completed", _iso(when), 250, 72.0, secs, secs, 30000,
             180, 140, 170, tss))
    db.conn.commit()


class CoreCase(unittest.TestCase):
    def setUp(self):
        set_language(PT)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.db = Database(self.tmp / "perennia.db")
        self.addCleanup(self.db.close)
        self.db.save_athlete(Athlete(name="D", birth_year=1993, weight_kg=72.0, ftp_w=250,
                                     lthr=165))


# =========================================================================== pressão arterial


class TestBloodPressure(CoreCase):
    def three_and_two(self, day="2026-11-10"):
        for s, d in ((130, 85), (126, 82), (122, 80)):
            bp.save_reading(self.db, None, day=day, period="morning", sys=s, dia=d, pulse=60)
        for s, d in ((118, 76), (116, 74)):
            bp.save_reading(self.db, None, day=day, period="night", sys=s, dia=d)

    def test_each_period_has_its_mean_and_the_day_has_one(self):
        self.three_and_two()
        s = bp.day_summary(self.db, "2026-11-10")
        per = dict(s["periods"])
        self.assertEqual([k for k, _m in s["periods"]], ["morning", "night"])
        self.assertAlmostEqual(per["morning"]["sys"], 126.0)
        self.assertAlmostEqual(per["morning"]["dia"], (85 + 82 + 80) / 3)
        self.assertEqual(per["morning"]["n"], 3)
        self.assertAlmostEqual(per["night"]["sys"], 117.0)
        # por omissão: a média do dia é a média das médias dos períodos
        self.assertAlmostEqual(s["daily"]["sys"], (126.0 + 117.0) / 2)
        self.assertEqual(s["n"], 5)

    def test_daily_mean_of_all_readings_is_an_option(self):
        self.three_and_two()
        self.db.set("bp_daily_mode", "readings")
        s = bp.day_summary(self.db, "2026-11-10")
        self.assertAlmostEqual(s["daily"]["sys"], (130 + 126 + 122 + 118 + 116) / 5)

    def test_skipping_the_first_reading_is_an_option(self):
        self.three_and_two()
        self.db.set("bp_discard_first", True)
        per = dict(bp.day_summary(self.db, "2026-11-10")["periods"])
        self.assertAlmostEqual(per["morning"]["sys"], 124.0)      # sem a 1.ª (130)
        self.assertAlmostEqual(per["night"]["sys"], 117.0)        # só 2: contam as duas
        self.assertEqual(per["morning"]["used"], 2)

    def test_the_daily_mean_goes_to_the_diary_metrics(self):
        self.three_and_two()
        ms = health.metric_by_key(self.db, "bp_sys")
        md = health.metric_by_key(self.db, "bp_dia")
        vals = health.values_for(self.db, "2026-11-10")
        self.assertEqual(vals[ms["id"]]["value"], 121.5)
        self.assertEqual(vals[ms["id"]]["source"], bp.SOURCE)
        self.assertAlmostEqual(vals[md["id"]]["value"], round(((85 + 82 + 80) / 3 + 75) / 2, 1))
        # mudar a opção e refazer: o diário acompanha
        self.db.set("bp_daily_mode", "readings")
        bp.resync_all(self.db)
        self.assertEqual(health.values_for(self.db, "2026-11-10")[ms["id"]]["value"], 122.4)
        # apagar tudo tira o valor do diário
        for r in bp.readings(self.db, "2026-11-10"):
            bp.delete_reading(self.db, r["id"])
        self.assertNotIn(ms["id"], health.values_for(self.db, "2026-11-10"))

    def test_old_diary_values_become_readings_once(self):
        health.seed(self.db)
        ms = health.metric_by_key(self.db, "bp_sys")
        md = health.metric_by_key(self.db, "bp_dia")
        health.set_value(self.db, "2026-10-01", ms["id"], 131)
        health.set_value(self.db, "2026-10-01", md["id"], 84)
        bp.ensure(self.db)
        rs = bp.readings(self.db, "2026-10-01")
        self.assertEqual([(r["sys"], r["dia"], r["period"]) for r in rs], [(131.0, 84.0, "")])
        bp.ensure(self.db)
        bp.ensure(self.db)
        self.assertEqual(len(bp.readings(self.db, "2026-10-01")), 1)        # idempotente
        bp.delete_reading(self.db, rs[0]["id"])
        bp.ensure(self.db)
        self.assertEqual(bp.readings(self.db, "2026-10-01"), [])            # não ressuscita

    def test_bad_readings_are_refused(self):
        for kw in (dict(sys=None, dia=80), dict(sys=120, dia=None), dict(sys=80, dia=120),
                   dict(sys=400, dia=80), dict(sys=120, dia=10), dict(sys=120, dia=80, pulse=5)):
            with self.assertRaises((ValueError, TypeError)):
                bp.save_reading(self.db, None, day="2026-11-10", period="morning", **kw)
        self.assertEqual(bp.days(self.db), [])

    def test_time_parsing(self):
        self.assertEqual(bp.parse_time("8"), "08:00")
        self.assertEqual(bp.parse_time("0830"), "08:30")
        self.assertEqual(bp.parse_time("8h05"), "08:05")
        self.assertEqual(bp.parse_time("21:45"), "21:45")
        for bad in ("", "25", "8:75", "abc", None):
            self.assertIsNone(bp.parse_time(bad))

    def test_the_period_is_suggested_by_the_time(self):
        self.assertEqual(bp.guess_period(self.db, "07:30"), "morning")
        self.assertEqual(bp.guess_period(self.db, "15:00"), "afternoon")
        self.assertEqual(bp.guess_period(self.db, "22:00"), "night")
        self.db.set("bp_morning_until_h", 7)
        self.assertEqual(bp.guess_period(self.db, "07:30"), "afternoon")

    def test_your_own_periods(self):
        self.three_and_two()
        out = bp.set_periods(self.db, ["Manhã", "Antes do treino", "Noite"])
        self.assertEqual([k for k, _n in out], ["morning", "antes_do_treino", "night"])
        self.assertEqual(bp.period_name(self.db, "antes_do_treino"), "Antes do treino")
        # tirar um período não perde as medições: ficam «sem período»
        bp.set_periods(self.db, ["Manhã"])
        s = bp.day_summary(self.db, "2026-11-10")
        self.assertEqual([k for k, _m in s["periods"]], ["morning", ""])
        self.assertEqual(s["n"], 5)
        with self.assertRaises(ValueError):
            bp.set_periods(self.db, ["  ", ""])

    def test_classification_uses_the_options(self):
        self.assertEqual(bp.classify(self.db, 120, 78), "normal")
        self.assertEqual(bp.classify(self.db, 136, 78), "high")
        self.assertEqual(bp.classify(self.db, 120, 86), "high")
        self.assertEqual(bp.classify(self.db, 85, 55), "low")
        self.assertEqual(bp.classify(self.db, 185, 100), "crisis")
        self.db.set("bp_high_sys", 140)
        self.assertEqual(bp.classify(self.db, 136, 78), "normal")
        self.assertIsNone(bp.classify(self.db, None, 80))

    def test_window_mean_and_series(self):
        for i in range(5):
            bp.save_reading(self.db, None, day=TODAY - timedelta(days=i), period="morning",
                            sys=120 + i, dia=80)
        m = bp.window_mean(self.db, 3, TODAY)
        self.assertEqual(m["days"], 3)
        self.assertAlmostEqual(m["sys"], 121.0)
        self.assertEqual(len(bp.series(self.db, 30, TODAY)), 5)
        self.assertIsNone(bp.window_mean(self.db, 3, TODAY, period="night"))

    def test_adhoc_source_has_readings_with_the_means_beside(self):
        self.three_and_two()
        rows = adhoc.SOURCES["bp"].loader(self.db)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["period_sys"], 126.0)
        self.assertEqual(rows[0]["day_sys"], 121.5)
        self.assertEqual(rows[0]["class"], "normal")
        path, n = adhoc.cli_export(self.db, self.tmp, "bp", folder=self.tmp / "out")
        self.assertEqual(n, 5)
        self.assertTrue(path.exists())


# =========================================================================== separadores


class TestHealthTabs(CoreCase):
    def test_a_tab_always_has_notes(self):
        k = health_tabs.add_tab(self.db, "  Fisioterapia  ")
        self.assertEqual(k, "fisioterapia")
        nid = health_tabs.save_note(self.db, None, k, day="2026-11-10", title="Ombro",
                                    text="melhor")
        health_tabs.save_note(self.db, nid, k, day="2026-11-11", title="Ombro", text="bem")
        self.assertEqual([(n["day"], n["text"]) for n in health_tabs.notes(self.db, k)],
                         [("2026-11-11", "bem")])
        self.assertEqual(health_tabs.tabs(self.db)[0]["n"], 1)

    def test_names_are_checked(self):
        health_tabs.add_tab(self.db, "Dentista")
        for bad in ("", "   ", "dentista"):
            with self.assertRaises(ValueError):
                health_tabs.add_tab(self.db, bad)
        # um nome igual a um separador fixo ganha outra chave (não o substitui)
        self.assertNotIn(health_tabs.add_tab(self.db, "Labs"), health_tabs.RESERVED)
        with self.assertRaises(ValueError):
            health_tabs.save_note(self.db, None, "dentista", day="2026-11-10")
        with self.assertRaises(ValueError):
            health_tabs.save_note(self.db, None, "nao-existe", day="2026-11-10", text="x")

    def test_rename_and_delete(self):
        k = health_tabs.add_tab(self.db, "Fisio")
        health_tabs.save_note(self.db, None, k, day="2026-11-10", text="x")
        health_tabs.rename_tab(self.db, k, "Fisioterapia")
        self.assertEqual(health_tabs.tab(self.db, k)["name"], "Fisioterapia")
        health_tabs.delete_tab(self.db, k)
        self.assertEqual(health_tabs.tabs(self.db), [])
        self.assertEqual(health_tabs.notes(self.db, k), [])


# =========================================================================== assistente de saúde


class TestHealthAssistant(CoreCase):
    def metric(self, key_, values, start=0):
        health.seed(self.db)
        m = health.metric_by_key(self.db, key_)
        for i, v in enumerate(values):
            health.set_value(self.db, TODAY - timedelta(days=start + i), m["id"], v)

    def test_with_no_data_it_says_so(self):
        a = ha.overview(self.db, TODAY)
        self.assertEqual(a.tone, "info")
        self.assertTrue(a.disclaimer)
        self.assertEqual(len(a.sections), 6)

    def test_high_blood_pressure_is_flagged_and_crisis_says_doctor(self):
        for i in range(5):
            bp.save_reading(self.db, None, day=TODAY - timedelta(days=i), period="morning",
                            sys=142, dia=91)
        a = ha.blood_pressure(self.db, TODAY)
        self.assertEqual(a.tone, "warn")
        self.assertIn("142/91", a.verdict)
        self.assertEqual(a.data["pressao_arterial"]["classe"], "high")
        bp.save_reading(self.db, None, day=TODAY, period="night", sys=200, dia=120)
        self.db.set("health_window_days", 3)
        for r in [r for d in range(1, 5) for r in bp.readings(self.db, TODAY - timedelta(days=d))]:
            bp.delete_reading(self.db, r["id"])
        a = ha.blood_pressure(self.db, TODAY)
        self.assertEqual(a.tone, "bad")
        self.assertIn("112", a.as_text())
        self.assertEqual(ha.overview(self.db, TODAY).tone, "bad")

    def test_recovery_compares_recent_with_baseline(self):
        self.metric("rhr", [58] * 14)                    # recente
        self.metric("rhr", [50] * 30, start=14)          # base
        self.metric("sleep_hours", [6.0] * 10)
        a = ha.recovery(self.db, TODAY)
        self.assertEqual(a.tone, "warn")
        self.assertEqual(len(a.data["avisos"]), 2)
        self.db.set("health_rhr_rise_bpm", 12.0)
        self.db.set("health_sleep_min_h", 5.5)
        self.assertEqual(ha.recovery(self.db, TODAY).tone, "good")

    def test_labs_out_of_range_and_the_doctor_stays(self):
        rid = health.save_lab_report(self.db, None, done_on="2026-11-01", lab="X",
                                     doctor_feedback="repetir em 3 meses")
        health.save_lab_result(self.db, None, rid, marker="Colesterol LDL", value=150,
                               unit="mg/dL", ref_low=None, ref_high=115)
        health.save_lab_result(self.db, None, rid, marker="Glicose", value=85, unit="mg/dL",
                               ref_low=70, ref_high=100)
        a = ha.labs(self.db, rid)
        self.assertEqual(a.tone, "warn")
        self.assertIn("Colesterol LDL", a.as_text())
        self.assertIn("repetir em 3 meses", a.as_text())
        self.assertEqual(len(a.data["analises"]["fora_do_intervalo"]), 1)
        self.assertEqual(health.lab_report(self.db, rid)["doctor_feedback"],
                         "repetir em 3 meses")

    def test_your_tabs_notes_are_read(self):
        k = health_tabs.add_tab(self.db, "Fisio")
        health_tabs.save_note(self.db, None, k, day="2026-11-10", title="Ombro", text="dói")
        a = ha.notes(self.db)
        self.assertIn("Ombro", a.as_text())
        self.assertIn("Fisio", ha.overview(self.db, TODAY).data["separadores"])

    def test_habits(self):
        self.metric("alcohol", [3] * 14)
        a = ha.habits(self.db, TODAY)
        self.assertEqual(a.tone, "warn")
        self.db.set("health_alcohol_week_max", 30.0)
        self.assertEqual(ha.habits(self.db, TODAY).tone, "good")


# =========================================================================== treinador


class TestCoachEvents(CoreCase):
    def endurance(self, **ans):
        base = dict(distance_km=160, ascent_m=2800, target_speed_kmh=27, start_time="7:30")
        base.update(ans)
        eid = coach.save_event(self.db, None, kind="endurance", name="Volta", sport="cycling",
                               day=(TODAY + timedelta(days=126)).isoformat(), priority="high",
                               answers=base)
        return coach.event(self.db, eid)

    def test_it_asks_for_what_is_missing(self):
        eid = coach.save_event(self.db, None, kind="endurance", name="Volta",
                               day=(TODAY + timedelta(days=60)).isoformat())
        a = coach.plan_event(self.db, coach.event(self.db, eid), TODAY)
        text = " ".join(a.questions)
        for word in ("distância", "velocidade", "horas partes", "férias"):
            self.assertIn(word, text)
        self.assertTrue(a.schedule)                 # mesmo sem tudo, propõe semanas

    def test_plan_has_phases_food_and_feasibility(self):
        ev = self.endurance()
        a = coach.plan_event(self.db, ev, TODAY)
        titles = [t for t, _x in a.sections]
        for t in ("Quando", "É realista?", "Disponibilidade", "Fases",
                  "Alimentação e hidratação", "Calendário"):
            self.assertIn(t, titles)
        self.assertEqual([p["fase"] for p in a.data["fases"]],
                         ["base", "build", "specific", "taper"])
        food = a.data["alimentacao"]
        self.assertEqual(food["hidratos_g_h"], 80)              # evento longo
        self.assertEqual(food["partida"], "07:30")
        self.assertIn("jantar da véspera", a.as_text())         # parte cedo
        self.assertGreater(a.data["evento"]["potencia_media_w"], 100)
        self.assertEqual(len(a.questions), 1)                   # só as férias

    def test_sessions_respect_availability_and_the_date(self):
        ev = self.endurance(weekday_min=0, weekend_min=120)
        a = coach.plan_event(self.db, ev, TODAY)
        day = date.fromisoformat(ev["day"])
        self.assertTrue(a.schedule)
        for p in a.schedule:
            self.assertGreater(p.day, TODAY)
            self.assertLess(p.day, day)
            self.assertGreaterEqual(p.day.weekday(), 5)         # só há tempo ao fim de semana
            self.assertTrue(p.title.startswith(coach.PLAN_PREFIX))

    def test_holidays_open_weekdays(self):
        v0 = TODAY + timedelta(days=21 - TODAY.weekday())        # uma segunda-feira
        ev = self.endurance(weekday_min=0, weekend_min=120, vacation_from=v0.isoformat(),
                            vacation_to=(v0 + timedelta(days=4)).isoformat())
        a = coach.plan_event(self.db, ev, TODAY)
        in_vac = [p for p in a.schedule if v0 <= p.day <= v0 + timedelta(days=4)]
        self.assertTrue(in_vac)
        self.assertIn("Férias de", a.as_text())

    def test_an_impossible_speed_is_called_out(self):
        a = coach.plan_event(self.db, self.endurance(target_speed_kmh=42), TODAY)
        self.assertEqual(a.tone, "bad")
        self.assertIn("ambicioso", a.as_text())

    def test_fuelling_follows_the_options(self):
        text, facts = coach.fuelling(self.db, 2.0, "10:00")
        self.assertEqual(facts["hidratos_g_h"], 60)
        self.assertIn("07:00", text)                             # 3 h antes
        self.db.set("coach_carbs_g_per_h", 70)
        self.db.set("coach_fluid_ml_per_h", 800)
        _t, facts = coach.fuelling(self.db, 2.0, None)
        self.assertEqual((facts["hidratos_g_h"], facts["liquidos_ml_h"]), (70, 800))
        text, _f = coach.fuelling(self.db, 0.5, "18:00")
        self.assertIn("não precisas de comer", text)

    def test_strength_event_judges_each_goal_and_the_pace(self):
        eid = coach.save_event(
            self.db, None, kind="strength", name="200 + 50",
            day=(TODAY + timedelta(days=80)).isoformat(),
            answers={"time_limit_min": 5, "goals": [
                {"name": "Flexões", "unit": "reps", "target": 200, "current": 60},
                {"name": "Elevações", "unit": "reps", "target": 50, "current": 45},
                {"name": "Peso morto", "unit": "kg", "target": 140}]})
        ev = coach.event(self.db, eid)
        self.assertEqual(ev["sport"], "gym")
        a = coach.plan_event(self.db, ev, TODAY)
        text = a.as_text()
        self.assertEqual(a.tone, "bad")
        self.assertIn("50 por minuto", text)
        self.assertIn("Flexões: de 60 para 200", text)
        self.assertIn("falta o teu valor atual", text)
        self.assertTrue(any("Quanto fazes hoje" in q for q in a.questions))
        self.assertTrue(all(p.sport == "gym" for p in a.schedule))

    def test_past_event(self):
        eid = coach.save_event(self.db, None, kind="endurance", name="Ontem",
                               day=(TODAY - timedelta(days=1)).isoformat())
        a = coach.plan_event(self.db, coach.event(self.db, eid), TODAY)
        self.assertIn("já passou", a.verdict)
        self.assertEqual(a.schedule, [])

    def test_calendar_put_replace_and_delete(self):
        ev = self.endurance()
        a = coach.plan_event(self.db, ev, TODAY)
        n = coach.apply_schedule(self.db, ev["id"], a.schedule)
        self.assertEqual(n, len(a.schedule))
        count = lambda: self.db.conn.execute(                      # noqa: E731
            "SELECT COUNT(*) FROM training_plan").fetchone()[0]
        self.assertEqual(count(), n)
        coach.apply_schedule(self.db, ev["id"], a.schedule[:5])   # voltar a pôr substitui
        self.assertEqual(count(), 5)
        cal.plan_add(self.db, TODAY, "cycling", None, "meu")      # um treino teu fica
        coach.delete_event(self.db, ev["id"])
        self.assertEqual(count(), 1)
        self.assertEqual(coach.events(self.db), [])

    def test_bad_events_are_refused(self):
        with self.assertRaises(ValueError):
            coach.save_event(self.db, None, kind="endurance", name=" ", day="2027-01-01")
        with self.assertRaises(ValueError):
            coach.save_event(self.db, None, kind="outro", name="x", day="2027-01-01")
        with self.assertRaises(ValueError):
            coach.save_event(self.db, None, kind="endurance", name="x", day="não é data")


class TestCoachChallenges(CoreCase):
    def challenge(self, days=60, target=1_000_000):
        cid = self.db.create_challenge("1000 km", "distance_m", target, "km", "cycling",
                                       (TODAY + timedelta(days=days)).isoformat())
        return dict(next(c for c in self.db.challenges("cycling") if c["id"] == cid))

    def test_it_asks_how_important_it_is(self):
        a = coach.challenge_feedback(self.db, self.challenge(), TODAY)
        self.assertEqual(a.tone, "bad")
        self.assertIn("longe", a.verdict)
        self.assertEqual(len(a.questions), 2)
        self.assertEqual(a.schedule, [])
        self.assertAlmostEqual(a.data["desafio"]["preciso_por_semana"], 1_000_000 / 61 * 7,
                               delta=1)

    def test_priority_adjusts_the_training(self):
        ch = self.challenge()
        coach.set_challenge_priority(self.db, ch["id"], "high")
        a = coach.challenge_feedback(self.db, ch, TODAY)
        self.assertEqual(a.questions, [])
        self.assertIn("Prioridade alta", a.as_text())
        self.assertTrue(a.schedule)
        n = coach.add_to_calendar(self.db, f"challenge:{ch['id']}", a.schedule)
        self.assertEqual(n, len(a.schedule))
        self.assertEqual(coach.add_to_calendar(self.db, f"challenge:{ch['id']}",
                                               a.schedule[:2]), 2)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM training_plan"
                                              ).fetchone()[0], 2)
        self.assertEqual(coach.remove_from_calendar(self.db, f"challenge:{ch['id']}"), 2)
        coach.set_challenge_priority(self.db, ch["id"], "low")
        low = coach.challenge_feedback(self.db, ch, TODAY)
        self.assertEqual(low.schedule, [])
        coach.set_challenge_priority(self.db, ch["id"], None)
        self.assertIsNone(coach.challenge_priority(self.db, ch["id"]))

    def test_close_when_ahead(self):
        seed_rides(self.db, 10)
        ch = self.challenge(days=30, target=350_000)
        self.db.ensure_attempt(ch["id"])
        self.db.conn.execute("UPDATE challenge_attempts SET started_at = ?",
                             (_iso(datetime.now(timezone.utc) - timedelta(days=30)),))
        self.db.conn.execute("UPDATE challenge_attempts SET progress = 300000")
        self.db.conn.commit()
        import perennia.core.sport_challenges as sc
        orig = sc.refresh
        sc.refresh = lambda db, c: dict(db.ensure_attempt(c["id"]))
        self.addCleanup(setattr, sc, "refresh", orig)
        a = coach.challenge_feedback(self.db, ch, TODAY)
        self.assertEqual(a.tone, "good")
        self.assertIn("perto", a.verdict)


class TestCoachToday(CoreCase):
    def test_no_history(self):
        a = coach.suggest_today(self.db, TODAY)
        self.assertEqual(a.tone, "info")
        self.assertEqual(a.data["focus"], "endurance")

    def test_overload_means_rest(self):
        seed_rides(self.db, 10, tss=250.0, every=1)
        a = coach.suggest_today(self.db, TODAY)
        self.assertEqual(a.tone, "warn")
        self.assertIn("Descanso", a.verdict)
        self.assertEqual(a.data["focus"], "recovery")

    def test_thresholds_are_options(self):
        seed_rides(self.db, 10, tss=120.0, every=1)
        self.assertIn("Descanso", coach.suggest_today(self.db, TODAY).verdict)
        self.db.set("coach_overload_tsb", -70.0)
        self.db.set("coach_tired_tsb", -50.0)
        self.db.set("coach_heavy_factor", 4.0)
        self.assertNotIn("Descanso", coach.suggest_today(self.db, TODAY).verdict)

    def test_planned_today_is_mentioned(self):
        cal.plan_add(self.db, TODAY, "cycling", None, "Intervalos")
        self.assertIn("Intervalos", coach.suggest_today(self.db, TODAY).as_text())

    def test_longevity_path_points_at_weaknesses(self):
        seed_rides(self.db, 40, tss=60.0)
        a = coach.longevity_path(self.db, TODAY)
        self.assertEqual(a.tone, "warn")
        self.assertIn("Força", a.verdict)
        self.assertTrue(a.data["longevidade"]["fases"])
        self.assertTrue(a.schedule)
        self.assertEqual(coach.longevity_path(Database(self.tmp / "vazia.db"), TODAY).tone,
                         "info")


class TestCoachBuilder(CoreCase):
    def test_built_workouts_fit_the_time(self):
        for focus in coach.FOCUSES:
            for minutes in (30, 60, 90):
                w = coach.build_workout(self.db, "cycling", focus, minutes, TODAY)
                total = sum(b.dur for b in w["blocks"]) / 60
                self.assertLessEqual(total, minutes + 0.01, (focus, minutes))
                self.assertGreaterEqual(total, minutes * 0.6, (focus, minutes))
                self.assertTrue(w["name"].startswith("Treinador"))
        with self.assertRaises(ValueError):
            coach.build_workout(self.db, "swimming", "endurance", 60)

    def test_tired_athlete_gets_a_shorter_main_set(self):
        fresh = coach.build_workout(self.db, "cycling", "threshold", 90, TODAY)
        seed_rides(self.db, 10, tss=250.0, every=1)
        tired = coach.build_workout(self.db, "cycling", "threshold", 90, TODAY)
        self.assertTrue(tired["note"])
        self.assertLess(sum(b.dur for b in tired["blocks"]), sum(b.dur for b in fresh["blocks"]))

    def test_a_heavy_workout_for_little_fitness_is_caught(self):
        seed_rides(self.db, 20, tss=30.0)
        B = bl.Block
        hard = [B("warmup", "time", 600, 50, 75)] + \
            [B("active", "time", 1200, 100) for _ in range(5)] + [B("cooldown", "time", 600, 55)]
        a = coach.review_blocks(self.db, "cycling", hard, TODAY)
        self.assertEqual(a.tone, "bad")
        self.assertIn("pesado demais", a.verdict.lower())
        scale = a.data["treino"]["escala_sugerida"]
        self.assertLess(scale, 1.0)
        light = coach.lighter_blocks(hard, scale)
        self.assertLess(len(light), len(hard))
        self.assertEqual(len(hard), 7)                              # o original fica intacto
        easy = [B("warmup", "time", 600, 55), B("active", "time", 1800, 65)]
        self.assertEqual(coach.review_blocks(self.db, "cycling", easy, TODAY).tone, "good")

    def test_structure_problems(self):
        B = bl.Block
        a = coach.review_blocks(self.db, "cycling", [B("active", "time", 1800, 110),
                                                    B("active", "time", 1800, 115)], TODAY)
        text = a.as_text()
        self.assertIn("sem aquecimento", text)
        self.assertIn("seguidos", text)
        self.assertIn("Z5", text)
        self.assertEqual(coach.review_blocks(self.db, "cycling", [], TODAY).tone, "info")

    def test_session_review_puts_the_coach_first(self):
        from perennia.core import feedback as fbm
        seed_rides(self.db, 5)
        sess = fbm.load_session(self.db, "ride", "r0")
        res = coach.review_session(self.db, sess, {"rpe": 5, "pain": 8})
        self.assertEqual(res["sections"][0][0], "Treinador")
        self.assertIn("dor", res["coach"])
        self.assertIn("verdict", res)
        res = coach.review_session(self.db, sess, {})
        self.assertIn("A seguir", res["coach"])


# =========================================================================== regras / LLM


class TestAdvisor(CoreCase):
    def test_rules_by_default_and_no_calls_yet(self):
        self.assertFalse(advisor.CALLS_ENABLED)
        for fig in advisor.FIGURES:
            self.assertEqual(advisor.mode(self.db, fig), "rules")
        advisor.set_mode(self.db, "coach", "local")
        self.assertEqual(advisor.mode(self.db, "coach"), "local")
        self.assertEqual(advisor.mode(self.db, "health"), "rules")
        advisor.set_mode(self.db, "coach", "nope")
        self.assertEqual(advisor.mode(self.db, "coach"), "local")
        for m in ("local", "online"):
            self.assertFalse(advisor.status(self.db, m)["ready"])

    def test_the_key_only_comes_from_the_environment(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.assertFalse(advisor.status(self.db, "online")["has_key"])
        os.environ["ANTHROPIC_API_KEY"] = "sk-teste-NAO-GUARDAR"
        self.addCleanup(os.environ.pop, "ANTHROPIC_API_KEY", None)
        st = advisor.status(self.db, "online")
        self.assertTrue(st["has_key"])
        self.assertEqual(st["env"], "ANTHROPIC_API_KEY")
        self.assertFalse(st["ready"])
        self.assertNotIn("sk-teste", repr(st))
        self.assertNotIn("sk-teste", advisor.mode_detail(self.db, "online"))
        req = advisor.build_request(self.db, "coach", coach.suggest_today(self.db, TODAY))
        self.assertNotIn("sk-teste", req["text"] + req["system"])
        rows = self.db.conn.execute("SELECT value FROM settings").fetchall()
        self.assertFalse(any("sk-teste" in str(r[0]) for r in rows))
        self.db.set("advisor_online_provider", "gemini")
        self.assertEqual(advisor.status(self.db, "online")["env"], "GEMINI_API_KEY")

    def test_request_has_tokens_and_nothing_from_strava(self):
        adv = coach.suggest_today(self.db, TODAY)
        adv.data["strava_segments"] = [1, 2]
        adv.data["lista"] = [{"source": "strava", "x": 1}, {"source": "garmin", "x": 2}]
        req = advisor.build_request(self.db, "coach", adv, "posso treinar forte?")
        self.assertNotIn("strava", req["text"].lower())
        self.assertIn("garmin", req["text"])
        self.assertIn("posso treinar forte?", req["text"])
        self.assertGreater(req["approx_tokens"], 100)
        self.assertIn("Treinador", req["system"])
        self.assertIn("Assistente de saúde", advisor.build_request(
            self.db, "health", ha.overview(self.db, TODAY))["system"])

    def test_local_has_no_cost_but_has_a_window(self):
        req = advisor.build_request(self.db, "coach", coach.suggest_today(self.db, TODAY))
        self.db.set("agent_price_in_per_mtok", 3.0)
        rep = advisor.report(self.db, req, "local")
        self.assertFalse(rep["priced"])
        self.assertTrue(rep["fits"])
        self.db.set("advisor_local_context_tokens", 1024)
        rep = advisor.report(self.db, req, "local")
        self.assertFalse(rep["fits"])
        self.assertTrue(rep["warn"])
        self.assertTrue(advisor.report(self.db, req, "online")["priced"])

    def test_local_means_this_computer(self):
        for ok in ("http://127.0.0.1:11434", "http://localhost:1234/v1", "http://[::1]:8080"):
            self.assertTrue(advisor.is_local_url(ok), ok)
        for bad in ("http://192.168.1.10:11434", "https://api.example.com", "", "nada"):
            self.assertFalse(advisor.is_local_url(bad), bad)


class TestOptionsAndBackup(CoreCase):
    def test_every_new_option_has_sane_defaults(self):
        keys = [o.key for o in options.OPTIONS]
        self.assertEqual(len(keys), len(set(keys)))
        for o in options.OPTIONS:
            self.assertEqual(options.coerce(o, o.default), o.default, o.key)
            if o.lo is not None:
                self.assertLessEqual(o.lo, o.default, o.key)
                self.assertGreaterEqual(o.hi, o.default, o.key)
            self.assertIn(o.group, options.GROUPS)
        for k in ("bp_daily_mode", "advisor_coach_mode", "coach_live_feedback",
                  "health_window_days", "coach_carbs_g_per_h"):
            self.assertIn(k, options.BY_KEY)
        self.assertNotIn("key", " ".join(k for k in keys if k.startswith("advisor_")))

    def test_backup_takes_readings_tabs_events_and_choices(self):
        bp.save_reading(self.db, None, day="2026-11-10", period="morning", sys=120, dia=80)
        bp.set_periods(self.db, ["Manhã", "Noite"])
        k = health_tabs.add_tab(self.db, "Fisio")
        health_tabs.save_note(self.db, None, k, day="2026-11-10", title="t", text="x")
        coach.save_event(self.db, None, kind="endurance", name="E", day="2027-01-01",
                         answers={"distance_km": 100})
        coach.set_challenge_priority(self.db, 1, "high")
        advisor.set_mode(self.db, "coach", "local")
        info = backup.export(self.db, self.tmp, self.tmp / "b.zip")
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, True)
        db = Database(other / "perennia.db")
        self.addCleanup(db.close)
        backup.restore(db, other, info["path"], mode="replace", safety=False)
        self.assertEqual(len(bp.readings(db, "2026-11-10")), 1)
        self.assertEqual([n for _k, n in bp.periods(db)], ["Manhã", "Noite"])
        self.assertEqual(health_tabs.tabs(db)[0]["n"], 1)
        self.assertEqual(coach.events(db)[0]["answers"]["distance_km"], 100)
        self.assertEqual(coach.challenge_priority(db, 1), "high")
        self.assertEqual(advisor.mode(db, "coach"), "local")

    def test_an_oversized_backup_is_refused_before_touching_anything(self):
        import zipfile
        bp.save_reading(self.db, None, day="2026-11-10", period="morning", sys=120, dia=80)
        info = backup.export(self.db, self.tmp, self.tmp / "b.zip")
        with zipfile.ZipFile(info["path"], "a", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("lixo/zeros.bin", b"\0" * (70 * 1024 * 1024))     # comprime para ~70 kB
        self.assertLess(Path(info["path"]).stat().st_size, 2 * 1024 * 1024)
        self.db.set("backup_restore_max_mb", 64)
        with self.assertRaises(backup.BackupError):
            backup.restore(self.db, self.tmp, info["path"], mode="replace", safety=False)
        self.assertEqual(len(bp.readings(self.db, "2026-11-10")), 1)       # nada mudou
        self.db.set("backup_restore_max_mb", 4096)
        backup.restore(self.db, self.tmp, info["path"], mode="replace", safety=False)

    def test_backup_components_name_the_new_tables(self):
        tables = {t for c in backup.COMPONENTS for t in c.tables}
        for t in ("bp_readings", "health_tabs", "health_tab_notes", "coach_events"):
            self.assertIn(t, tables)


# =========================================================================== interface


class TestHealthUI(tg.GuiCase):
    def open_health(self, tab: str | None = None):
        from perennia.ui import health_screens as hs
        self.app.push(hs.HealthMenu(self.app))
        m = self.screen()
        if tab:
            self.assertTrue(m.tab_named(tab))
        return m

    def test_tabs(self):
        m = self.open_health()
        self.assertEqual(m.tab_labels(), ["Análises", "Diários", "Tendências", "Métricas",
                                          "Pressão arterial", "Assistente de saúde"])

    def test_three_readings_in_a_row_give_one_value(self):
        from perennia.ui import health_extra_screens as hx
        m = self.open_health("Pressão")
        self.pick("+ Medição")
        ed = self.screen()
        self.assertIsInstance(ed, hx.BPReadingEditor)
        for s, d in ((130, 84), (126, 82)):
            ed.v.update(sys=float(s), dia=float(d), period="morning")
            ed.enter()
            self.pick("Guardar e mais uma")
            self.assertIs(self.screen(), ed)
            self.assertIsNone(ed.v["sys"])                  # pronta para a seguinte
        ed.v.update(sys=122.0, dia=80.0)
        ed.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), m)
        s = bp.day_summary(self.app.db, TODAY)
        self.assertEqual(dict(s["periods"])["morning"]["n"], 3)
        self.assertAlmostEqual(s["daily"]["sys"], 126.0)
        row = next(i for i in m.list.items if i.data == ("day", TODAY.isoformat()))
        self.assertEqual(row.value, "126/82")
        self.assertIn("Manhã 126/82 (3)", row.detail)

    def test_typing_numbers_and_refusing_nonsense(self):
        from perennia.ui import health_extra_screens as hx
        self.app.push(hx.BPReadingEditor(self.app, None, TODAY))
        ed = self.screen()
        ed.list.select_data("num:sys")
        for ch in "128":
            self.app._on_text(ch)
        ed.list.select_data("num:dia")
        for ch in "150":
            self.app._on_text(ch)
        self.assertEqual((ed.v["sys"], ed.v["dia"]), (128.0, 150.0))
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), ed)                    # mínima > máxima: não guarda
        self.assertEqual(bp.days(self.app.db), [])
        ed.v["dia"] = 82.0
        ed.v["at"] = "99"
        ed.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), ed)                    # hora impossível
        ed.v["at"] = "0815"
        ed.enter()
        self.pick("Guardar e sair")
        self.assertEqual(bp.readings(self.app.db, TODAY)[0]["at"], "08:15")

    def test_period_is_a_dropdown(self):
        from perennia.ui import health_extra_screens as hx
        from perennia.ui import pickers
        self.app.push(hx.BPReadingEditor(self.app, None, TODAY))
        ed = self.screen()
        ed.list.select_data("cyc:period")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), pickers.ChoicePopup)
        self.pick("Noite")
        self.assertIs(self.screen(), ed)
        self.assertEqual(ed.v["period"], "night")

    def test_day_screen_edit_and_delete(self):
        from perennia.ui import health_extra_screens as hx
        rid = bp.save_reading(self.app.db, None, day=TODAY, period="morning", sys=120, dia=80)
        self.app.push(hx.BPDayScreen(self.app, TODAY))
        scr = self.screen()
        self.assertIn("Média do dia", [i.label for i in scr.list.items])
        scr.list.select_data(("reading", rid))
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), hx.BPReadingEditor)
        self.pick("Apagar esta medição")
        self.pick("Apagar")
        self.assertIs(self.screen(), scr)
        self.assertEqual(bp.readings(self.app.db, TODAY), [])

    def test_periods_popup(self):
        from perennia.ui import health_extra_screens as hx
        self.app.push(hx.BPPeriodsPopup(self.app))
        ed = self.screen()
        ed.v = ["Manhã", "", "Noite"]
        ed.enter()
        self.pick("Guardar e sair")
        self.assertEqual([n for _k, n in bp.periods(self.app.db)], ["Manhã", "Noite"])

    def test_diary_shows_one_row_that_opens_the_readings(self):
        from perennia.ui import health_extra_screens as hx
        from perennia.ui import health_screens as hs
        bp.save_reading(self.app.db, None, day=TODAY, period="morning", sys=120, dia=80)
        self.app.push(hs.DailyLogScreen(self.app, TODAY))
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("Pressão arterial", labels)
        self.assertNotIn("Tensão arterial (máxima)", labels)
        self.assertNotIn("Tensão arterial (mínima)", labels)
        self.pick("Pressão arterial")
        self.assertIsInstance(self.screen(), hx.BPDayScreen)

    def test_new_tab_with_notes_rename_and_delete(self):
        from perennia.ui import health_extra_screens as hx
        m = self.open_health("Diários")
        self.pick("+ Separador")
        pop = self.screen()
        pop.text = "Fisioterapia"
        pop.on_key(key.ENTER, 0)
        self.assertIs(self.screen(), m)
        self.assertEqual(m.tab_labels()[-1], "Fisioterapia")
        self.assertEqual(m.tab_key(), "tab:fisioterapia")
        self.assertIn("Notas", [i.label for i in m.list.items])
        self.pick("+ Nota")
        ed = self.screen()
        self.assertIsInstance(ed, hx.NoteEditor)
        ed.v.update(title="Ombro", text="melhor hoje")
        ed.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), m)
        self.assertEqual(health_tabs.notes(self.app.db, "fisioterapia")[0]["title"], "Ombro")
        self.pick("Mudar o nome")
        pop = self.screen()
        pop.text = "Fisio"
        pop.on_key(key.ENTER, 0)
        self.assertEqual(m.tab_labels()[-1], "Fisio")
        self.pick("Apagar separador")
        self.pick("Apagar")
        self.assertEqual(len(m.tab_labels()), 6)
        self.assertEqual(health_tabs.tabs(self.app.db), [])
        # um nome repetido ou vazio não cria nada
        hx.new_tab(m)
        self.screen().on_key(key.ENTER, 0)
        self.assertEqual(health_tabs.tabs(self.app.db), [])

    def test_assistant_tab_and_component(self):
        from perennia.ui import advice_screens as ad
        m = self.open_health("Assistente")
        comps = [i.data[1] for i in m.list.items
                 if isinstance(i.data, tuple) and i.data[0] == "component"]
        self.assertEqual(tuple(comps), ha.COMPONENTS)
        m.list.select_data(("component", "bp"))
        self.press(key.ENTER)
        scr = self.screen()
        self.assertIsInstance(scr, ad.AdviceScreen)
        self.assertEqual(scr.figure, "health")
        self.assertIn("não um diagnóstico", " ".join(i.label for i in scr.list.items))

    def test_lab_report_has_the_assistant_and_keeps_the_doctor(self):
        from perennia.ui import advice_screens as ad
        from perennia.ui import health_screens as hs
        rid = health.save_lab_report(self.app.db, None, done_on="2026-11-01", lab="X")
        health.save_lab_result(self.app.db, None, rid, marker="LDL", value=150, unit="mg/dL",
                               ref_high=115)
        self.app.push(hs.HealthMenu(self.app, 0, rid))
        labels = [i.label for i in self.screen().list.items]
        self.assertIn("Comentário geral do médico", labels)
        self.pick("Assistente de saúde")
        self.assertIsInstance(self.screen(), ad.AdviceScreen)
        self.assertIn("LDL", self.screen().advice.as_text())


class TestAdviceUI(tg.GuiCase):
    def open(self):
        from perennia.ui import advice_screens as ad
        self.app.push(ad.AdviceScreen(self.app, "coach",
                                      lambda: coach.suggest_today(self.app.db)))
        return self.screen()

    def test_mode_is_a_dropdown_and_llm_shows_tokens_before_sending(self):
        from perennia.ui import advice_screens as ad
        from perennia.ui import pickers
        scr = self.open()
        self.assertEqual(scr.list.items[0].label, "Aconselhamento")
        labels = [i.label for i in scr.list.items]
        self.assertNotIn("Tokens deste pedido", labels)           # regras: sem tokens
        scr.list.select_data("cyc:advisor_mode")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), pickers.ChoicePopup)
        self.pick("LLM local")
        self.assertIs(self.screen(), scr)
        self.assertEqual(advisor.mode(self.app.db, "coach"), "local")
        tok = next(i for i in scr.list.items if i.label == "Tokens deste pedido")
        self.assertTrue(tok.value.startswith("≈ "))
        self.assertIn("sem custo", tok.detail)
        # a leitura das regras continua lá (o LLM ainda não está ligado)
        self.assertTrue(any(isinstance(i.data, tuple) and i.data[0] == "verdict"
                            for i in scr.list.items))
        self.pick("Ver o que seria enviado")
        req = self.screen()
        self.assertIsInstance(req, ad.AdvisorRequestScreen)
        labels = [i.label for i in req.list.items]
        self.assertIn("Janela do modelo local", labels)
        self.assertIn("Total que seria enviado", labels)
        send = next(i for i in req.list.items if i.label == "Enviar")
        self.assertFalse(send.enabled)                             # nada é enviado
        before = advisor.build_request(self.app.db, "coach", scr.advice)["approx_tokens"]
        self.pick("✓ Treino e forma")                              # desliga uma categoria
        after = advisor.build_request(self.app.db, "coach", scr.advice)["approx_tokens"]
        self.assertLess(after, before)

    def test_online_shows_cost_provider_and_key_state(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        advisor.set_mode(self.app.db, "coach", "online")
        self.app.db.set("agent_price_in_per_mtok", 3.0)
        self.app.db.set("agent_price_out_per_mtok", 15.0)
        scr = self.open()
        tok = next(i for i in scr.list.items if i.label == "Tokens deste pedido")
        self.assertIn("US$", tok.detail)
        self.assertIn("Dados partilhados", [i.label for i in scr.list.items])
        self.pick("Ver o que seria enviado")
        key_row = next(i for i in self.screen().list.items if i.label == "Chave do fornecedor")
        self.assertEqual(key_row.value, "em falta")
        self.assertIn("ANTHROPIC_API_KEY", key_row.detail)

    def test_question_goes_with_the_request(self):
        advisor.set_mode(self.app.db, "coach", "local")
        scr = self.open()
        self.pick("A tua pergunta")
        pop = self.screen()
        pop.text = "posso fazer intervalos?"
        pop.save()                                         # várias linhas: Enter muda de linha
        self.assertIs(self.screen(), scr)
        self.assertEqual(scr.question, "posso fazer intervalos?")


class TestCoachUI(tg.GuiCase):
    def menu(self, tab: str | None = None):
        from perennia.ui import coach_screens as cs
        self.app.push(cs.CoachMenu(self.app))
        m = self.screen()
        if tab:
            self.assertTrue(m.tab_named(tab))
        return m

    def test_home_has_the_coach(self):
        from perennia.ui import coach_screens as cs
        self.press(key.ESCAPE)
        self.pick("Treinador")
        m = self.screen()
        self.assertIsInstance(m, cs.CoachMenu)
        self.assertEqual(m.tab_labels(), ["Hoje", "Eventos", "Desafios", "Longevidade",
                                          "Programar treino"])
        for i in range(5):                                  # todos os separadores abrem
            m.set_tab(i)
            self.assertTrue(m.list.items)

    def test_endurance_event_from_a_gpx_to_the_calendar(self):
        from perennia.ui import coach_screens as cs
        from perennia.ui import pickers
        m = self.menu("Eventos")
        self.pick("+ Evento de resistência")
        ed = self.screen()
        self.assertIsInstance(ed, cs.EventEditor)
        ed.list.select_data("cyc:route")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), pickers.ChoicePopup)
        self.pick("Serra de Teste")
        self.assertIs(self.screen(), ed)
        self.assertEqual(ed.v["name"], "Serra de Teste")
        self.assertGreater(ed.v["ans"]["distance_km"], 0)
        ed.list.select_data("num:target_speed_kmh")
        for ch in "22":
            self.app._on_text(ch)
        ed.v["ans"]["start_time"] = "8"
        ed.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), m)
        ev = coach.events(self.app.db)[0]
        self.assertEqual(ev["answers"]["target_speed_kmh"], 22.0)
        self.assertEqual(ev["answers"]["start_time"], "08:00")
        m.list.select_data(("event", ev["id"]))
        self.press(key.ENTER)
        scr = self.screen()
        put = next(i.label for i in scr.list.items if i.label.startswith("Pôr no calendário"))
        self.pick(put)
        n = self.app.db.conn.execute("SELECT COUNT(*) FROM training_plan").fetchone()[0]
        self.assertGreater(n, 0)
        self.assertEqual(len(coach.event(self.app.db, ev["id"])["plan_ids"]), n)
        self.pick("Tirar do calendário")
        self.assertEqual(self.app.db.conn.execute("SELECT COUNT(*) FROM training_plan"
                                                  ).fetchone()[0], 0)
        self.pick("Apagar")
        self.pick("Apagar")
        self.assertIs(self.screen(), m)
        self.assertEqual(coach.events(self.app.db), [])

    def test_event_editor_checks_time_and_holidays(self):
        from perennia.ui import coach_screens as cs
        self.app.push(cs.EventEditor(self.app, None, "endurance"))
        ed = self.screen()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), ed)                    # sem nome
        ed.v["name"] = "X"
        ed.v["ans"]["start_time"] = "99"
        ed.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), ed)
        ed.v["ans"]["start_time"] = ""
        ed.v["ans"]["vacation_from"] = "2027-01-10"
        ed.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), ed)                    # só uma das datas
        ed.list.select_data("cyc:start")
        self.press(key.DELETE)
        self.assertEqual(ed.v["ans"]["vacation_from"], "")
        self.pick("Guardar e sair")
        self.assertEqual(len(coach.events(self.app.db)), 1)

    def test_strength_event_goals_come_from_a_list(self):
        from perennia.ui import coach_screens as cs
        from perennia.ui import pickers
        self.app.push(cs.EventEditor(self.app, None, "strength"))
        ed = self.screen()
        ed.v["name"] = "Prova de força"
        ed.enter()
        self.pick("+ Juntar um exercício")
        g = self.screen()
        self.assertIsInstance(g, cs.GoalEditor)
        g.list.select_data("cyc:exercise")
        self.press(key.ENTER)
        pop = self.screen()
        self.assertIsInstance(pop, pickers.ChoicePopup)     # uma lista, não setas
        self.assertGreater(len(pop.options), 5)
        self.press(key.ENTER)
        self.assertTrue(g.v["name"])
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), g)                     # falta o objetivo
        g.v.update(target=200.0, current=60.0)
        g.enter()
        self.pick("Guardar e sair")
        self.assertIs(self.screen(), ed)
        self.assertEqual(len(ed.v["ans"]["goals"]), 1)
        self.pick("Guardar e sair")
        self.assertEqual(coach.events(self.app.db)[0]["answers"]["goals"][0]["target"], 200.0)

    def test_challenge_detail_asks_the_coach(self):
        from perennia.ui import app as app_mod
        from perennia.ui import coach_screens as cs
        from perennia.ui import pickers
        ch = dict(self.app.db.challenges("cycling")[0])
        self.app.push(app_mod.ChallengeDetail(self.app, ch))
        self.pick("Treinador")
        scr = self.screen()
        self.assertIsInstance(scr, cs.ChallengeCoach)
        scr.list.select_data("cyc:priority")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), pickers.ChoicePopup)
        self.pick("alta")
        self.assertIs(self.screen(), scr)
        self.assertEqual(coach.challenge_priority(self.app.db, ch["id"]), "high")
        self.assertIn("Prioridade alta", scr.advice.as_text())

    def test_build_tab_opens_the_builder_and_the_builder_asks_the_coach(self):
        from perennia.ui import advice_screens as ad
        from perennia.ui import builder_screens as bs
        m = self.menu("Programar")
        m.build.update(focus="vo2max", minutes=60)
        m.enter()
        self.pick("Abrir no construtor")
        b = self.screen()
        self.assertIsInstance(b, bs.BlockBuilder)
        self.assertTrue(b.dirty)
        self.assertTrue(b.name.startswith("Treinador"))
        self.assertGreater(len(b.blocks), 5)
        self.assertIn("Treinador:", b.chrome.subtitle.text)         # ao vivo
        self.pick("Treinador")
        self.assertIsInstance(self.screen(), ad.AdviceScreen)
        self.assertIn("O treino", [i.label for i in self.screen().list.items])

    def test_live_feedback_only_after_asking_and_can_be_turned_off(self):
        from perennia.ui import builder_screens as bs
        self.app.push(bs.BlockBuilder(self.app, "cycling", None, control="erg"))
        b = self.screen()
        self.assertNotIn("Treinador:", b.chrome.subtitle.text)
        self.pick("Treinador")
        self.press(key.ESCAPE)
        self.assertIs(self.screen(), b)
        self.assertIn("Treinador:", b.chrome.subtitle.text)
        first = b.chrome.subtitle.text
        b.blocks[1].dur = 3 * 3600
        b.blocks[1].lo = 105
        b.changed()
        self.assertNotEqual(b.chrome.subtitle.text, first)          # acompanha as alterações
        self.app.db.set("coach_live_feedback", False)
        b.changed()
        self.assertNotIn("Treinador:", b.chrome.subtitle.text)

    def test_lighter_version_button(self):
        from perennia.ui import builder_screens as bs
        seed_rides(self.app.db, 20, tss=30.0)
        self.app.push(bs.BlockBuilder(self.app, "cycling", None, control="erg"))
        b = self.screen()
        B = bl.Block
        b.blocks = [B("warmup", "time", 600, 50, 75)] + \
            [B("active", "time", 1200, 100) for _ in range(5)]
        n = len(b.blocks)
        self.pick("Treinador")
        self.pick("Aplicar a versão mais leve")
        self.assertIs(self.screen(), b)
        self.assertLess(len(b.blocks), n)
        self.assertTrue(b.dirty)

    def test_longevity_menu_has_the_coach(self):
        from perennia.ui import advice_screens as ad
        from perennia.ui import longevity_screens as ls
        self.app.push(ls.LongevityMenu(self.app))
        self.pick("Treinador: caminho")
        self.assertIsInstance(self.screen(), ad.AdviceScreen)

    def test_session_feedback_is_the_coachs(self):
        from perennia.ui import feedback_screens as fs
        seed_rides(self.app.db, 3)
        self.app.push(fs.FeedbackScreen(self.app, "ride", "r0"))
        scr = self.screen()
        scr.draw()
        self.assertEqual(scr.h_an.text, "Treinador")
        self.assertEqual(scr.analysis["sections"][0][0], "Treinador")
        self.assertEqual(scr.an_titles[0].text, "Treinador")


class TestSettingsAndArrows(tg.GuiCase):
    def test_advanced_tab_lists_the_new_groups(self):
        self.app.open_settings()
        scr = self.screen()
        self.assertTrue(scr.tab_named("Avançado"))
        labels = [i.label for i in scr.list.items]
        for name in ("Saúde e pressão arterial", "Treinador e Assistente de saúde",
                     "Pressão arterial: média diária", "Treinador: aconselhamento",
                     "LLM local: endereço"):
            self.assertIn(name, labels)

    def test_pool_length_is_a_dropdown(self):
        from perennia.ui import app as app_mod
        from perennia.ui import pickers
        got = {}
        self.app.push(app_mod.StartOptions(self.app, "swimming", "Natação",
                                           lambda al, o: got.update(o),
                                           options={"pool_m": 25.0}))
        scr = self.screen()
        scr.list.select_data("pool")
        self.press(key.ENTER)
        self.assertIsInstance(self.screen(), pickers.ChoicePopup)
        self.pick("50 m")
        self.assertEqual(scr.options["pool_m"], 50.0)
        self.press(key.RIGHT)                                        # ←/→ continuam a mudar
        self.assertEqual(scr.options["pool_m"], 33.3)

    def test_treadmill_start_speed_respects_the_option(self):
        from perennia.ui import app as app_mod
        self.app.db.set("treadmill_start_speed_max_kmh", 12.0)
        self.app.push(app_mod.StartOptions(self.app, "running", "Corrida", lambda al, o: None,
                                           options={"speed_kmh": 11.5}))
        scr = self.screen()
        scr.list.select_data("speed")
        self.press(key.RIGHT, key.RIGHT, key.RIGHT)
        self.assertEqual(scr.options["speed_kmh"], 12.0)


if __name__ == "__main__":
    unittest.main()
