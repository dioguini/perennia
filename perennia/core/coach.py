"""O Treinador: a figura que acompanha o treino.

O que faz, sempre a partir do que existe na Perennia:

1. **Avalia um treino feito** (`review_session`): a análise que já existia (execução, objetivo,
   sensações) mais o contexto do atleta — a forma com que entrou, o que a sessão acrescentou à
   longevidade — e o que fazer a seguir.
2. **Ajuda a planear um evento numa data** (`plan_event`): uma volta de bicicleta com um .gpx e
   uma velocidade média pretendida, uma prova de corrida, ou um evento de força («200 flexões e
   50 elevações em 5 minutos», «flexões, elevações, peso morto, agachamento e saco de areia»).
   Recolhe a informação (data, hora de partida, disponibilidade de semana e de fim de semana,
   férias), diz se é realista, divide o tempo em fases, propõe as semanas e — só se pedires —
   põe as sessões no calendário.
3. **Acompanha um desafio** (`challenge_feedback`): longe ou perto, o ritmo que falta, pergunta a
   importância, e com isso ajusta os treinos.
4. **Define um caminho para a longevidade** (`longevity_path`): os eixos fracos do índice e as
   fases para os subir (mais aeróbio, força, VO2máx…).
5. **Sugere o treino e os comportamentos de hoje** (`suggest_today`).
6. **Programa um treino** para o construtor (`build_workout`) e **dá feedback a um treino
   construído** (`review_blocks`), tendo em conta a forma atual (um treino pesado demais para
   quem tem pouca forma é apanhado, com uma alternativa mais leve).

Tudo isto é a versão **offline por regras**: sem rede e sem IA, com os limiares nas Definições →
Avançado. O mesmo pedido pode ser preparado para um LLM local ou para um agente online
(`advisor.py`); enquanto não estiverem ligados, vê-se o que seria enviado e quantos tokens gasta.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date, datetime, timedelta

from . import blocks as bl
from . import calendar_view as cal
from . import health_assistant as ha
from . import intensity as it
from . import longevity as lg
from . import options, physics, stats
from . import sport_challenges as sc
from .advice import Advice, Planned
from .db import Database, now_iso
from .i18n import tr
from .units import hms

PLAN_PREFIX = "Treinador · "
EVENT_KINDS = ("endurance", "strength")
ENDURANCE_SPORTS = ("cycling", "running", "rowing", "swimming")
PRIORITIES = ("low", "medium", "high")
FOCUSES = ("recovery", "endurance", "tempo", "sweetspot", "threshold", "vo2max", "anaerobic")
BUILD_SPORTS = ("cycling", "running", "rowing")
GOAL_UNITS = ("reps", "kg", "s", "m")
MAX_GOALS = 6
CLIMB_ENERGY_SHARE = 0.6        # fração da energia das subidas que não volta nas descidas


def _opt(db: Database, key: str) -> float:
    return float(options.get(db, key))


def sport_name(s: str) -> str:
    return {"cycling": tr("Ciclismo", "Cycling"), "running": tr("Corrida", "Running"),
            "rowing": tr("Remo", "Rowing"), "swimming": tr("Natação", "Swimming"),
            "gym": tr("Ginásio", "Gym"), "strength": tr("Ginásio", "Gym")}.get(s, s)


def priority_name(p: str) -> str:
    return {"low": tr("baixa", "low"), "medium": tr("média", "medium"),
            "high": tr("alta", "high")}.get(p, p)


def focus_name(f: str) -> str:
    return {"recovery": tr("Recuperação", "Recovery"), "endurance": tr("Resistência (Z2)",
                                                                       "Endurance (Z2)"),
            "tempo": "Tempo", "sweetspot": "Sweet spot", "threshold": tr("Limiar", "Threshold"),
            "vo2max": tr("VO2máx", "VO2max"), "anaerobic": tr("Anaeróbio", "Anaerobic")}.get(f, f)


# ====================================================================== retrato


def snapshot(db: Database, today: date | None = None) -> dict:
    """O que o Treinador sabe do atleta hoje (tudo local)."""
    today = today or date.today()
    hist = int(_opt(db, "coach_history_days"))
    out: dict = {"today": today, "history_days": hist}
    series = stats.fitness(db, 8, today=today)
    if series:
        now = series[-1]
        out.update(ctl=now["ctl"], atl=now["atl"], tsb=now["tsb"],
                   state=stats.form_state(now["tsb"]),
                   ramp=now["ctl"] - series[0]["ctl"] if len(series) >= 8 else 0.0)
    else:
        out.update(ctl=0.0, atl=0.0, tsb=0.0, state=None, ramp=0.0)
    loads = stats.daily_load(db)
    recent = {d: v for d, v in loads.items()
              if today - timedelta(days=hist) < d <= today and v > 0}
    out["has_history"] = bool(recent)
    out["typical_load"] = statistics.median(recent.values()) if recent else 0.0
    out["week_load"] = sum(v for d, v in recent.items() if d > today - timedelta(days=7))
    out["avg_week_load"] = sum(recent.values()) / max(1.0, hist / 7.0)
    out["sessions_per_week"] = len(recent) / max(1.0, hist / 7.0)
    last = max(recent) if recent else None
    out["days_since_last"] = (today - last).days if last else None
    out["yesterday_load"] = loads.get(today - timedelta(days=1), 0.0)
    out["today_load"] = loads.get(today, 0.0)
    longest: dict[str, float] = {}
    for sport in ("cycling", "running", "rowing", "swimming", "gym"):
        cut = datetime.combine(today - timedelta(days=hist), datetime.min.time())
        secs = [s["seconds"] for s in sc.sessions_of(db, sport) if s["at"] >= cut]
        if secs:
            longest[sport] = max(secs)
    out["longest_s"] = longest
    ath = db.athlete()
    out["ftp_w"], out["weight_kg"] = ath.ftp_w, ath.weight_kg
    rec = ha.recovery(db, today)
    out["recovery_flags"] = list(rec.data.get("avisos") or [])
    out["recovery"] = rec.data.get("recuperacao") or {}
    out["weak_axes"] = weak_axes(db, today)
    return out


def snapshot_facts(s: dict) -> dict:
    """O retrato em chaves simples (o que seguiria para um agente de IA)."""
    return {"forma": {"ctl": round(s["ctl"], 1), "atl": round(s["atl"], 1),
                      "tsb": round(s["tsb"], 1), "estado": s["state"],
                      "subida_ctl_7d": round(s["ramp"], 1)},
            "carga_tipica_sessao": round(s["typical_load"]),
            "carga_semana": round(s["week_load"]),
            "sessoes_por_semana": round(s["sessions_per_week"], 1),
            "dias_desde_ultima": s["days_since_last"],
            "sessao_mais_longa_h": {k: round(v / 3600, 1) for k, v in s["longest_s"].items()},
            "recuperacao": s["recovery"], "avisos_recuperacao": s["recovery_flags"],
            "eixos_fracos_longevidade": [a for a, _v in s["weak_axes"]]}


def weak_axes(db: Database, today: date | None = None, period: str = "3m"
              ) -> list[tuple[str, float]]:
    """Os eixos da longevidade abaixo do limiar, do mais fraco para o menos."""
    try:
        res = lg.compute(db, today)
    except Exception:
        return []
    axes = (res.get(period) or {}).get("axes") or {}
    cut = _opt(db, "coach_weak_axis_score")
    return sorted(((a, v) for a, v in axes.items() if a in lg.AXES and v < cut),
                  key=lambda x: x[1])


def form_text(s: dict) -> str:
    if not s["has_history"]:
        return tr("Ainda não tenho histórico de treino recente teu.",
                  "I have no recent training history of yours yet.")
    state = {"transition": tr("muito fresco (a perder forma)", "very fresh (losing fitness)"),
             "fresh": tr("fresco", "fresh"), "neutral": tr("neutro", "neutral"),
             "optimal": tr("a construir forma", "building fitness"),
             "overload": tr("em sobrecarga", "overloaded")}.get(s["state"], "")
    return tr("Forma (TSB) {t:+.0f}: {s}. Carga crónica (CTL) {c:.0f}, fadiga (ATL) {a:.0f}.",
              "Form (TSB) {t:+.0f}: {s}. Chronic load (CTL) {c:.0f}, fatigue (ATL) {a:.0f}.",
              t=s["tsb"], s=state, c=s["ctl"], a=s["atl"])


# ====================================================================== 1. sessão feita


def review_session(db: Database, sess, fb: dict, today: date | None = None) -> dict:
    """A avaliação de um treino pelo Treinador. Devolve o mesmo formato de
    `feedback.analyse` (veredicto, tom, secções…), com a secção «Treinador» à cabeça e a chave
    `coach` (o texto dela)."""
    from . import feedback as fbm
    res = fbm.analyse(db, sess, fb)
    s = snapshot(db, today)
    pain, rpe = fb.get("pain"), fb.get("rpe")
    target = res.get("target_rpe")
    harder = rpe is not None and target is not None and rpe >= target + 2
    easier = rpe is not None and target is not None and rpe <= target - 2
    out = []
    if s["has_history"]:
        out.append(form_text(s))
    load = getattr(sess, "load", None)
    if load and s["typical_load"]:
        ratio = load / s["typical_load"]
        if ratio >= _opt(db, "coach_very_heavy_factor"):
            out.append(tr("Esta sessão teve {r:.1f}× a tua carga habitual: conta como um dia "
                          "muito pesado.", "This session was {r:.1f}× your usual load: it "
                          "counts as a very hard day.", r=ratio))
        elif ratio >= _opt(db, "coach_heavy_factor"):
            out.append(tr("Foi uma sessão pesada ({r:.1f}× a tua carga habitual).",
                          "It was a hard session ({r:.1f}× your usual load).", r=ratio))
    try:
        sport = {"ride": "cycling", "row": "rowing", "strength": "gym"}.get(sess.kind, sess.sport)
        imp = lg.impact_text(lg.session_impact(db, sport, sess.id))
        if imp:
            out.append(tr("Longevidade: {i}.", "Longevity: {i}.", i=imp))
    except Exception:
        pass
    # o que fazer a seguir
    if pain is not None and pain >= 7:
        nxt = tr("A seguir: não treines por cima da dor. Descansa, e se não passar em 2–3 dias "
                 "fala com um profissional de saúde.",
                 "Next: do not train through the pain. Rest, and if it does not settle in 2–3 "
                 "days see a health professional.")
    elif s["tsb"] <= _opt(db, "coach_overload_tsb") and s["has_history"]:
        nxt = tr("A seguir: um ou dois dias de descanso ou muito leves — a fadiga está alta.",
                 "Next: one or two rest or very easy days — fatigue is high.")
    elif harder:
        nxt = tr("A seguir: um dia leve, e na próxima vez baixa os alvos 3–5 % ou encurta os "
                 "blocos.", "Next: an easy day, and next time lower the targets 3–5 % or "
                 "shorten the blocks.")
    elif easier and res["useful"] == "yes":
        nxt = tr("A seguir: podes subir os alvos deste treino 2–3 % (ou juntar uma repetição).",
                 "Next: you can raise this workout's targets 2–3 % (or add one repetition).")
    elif res["useful"] == "no":
        nxt = tr("A seguir: repete este treino quando estiveres recuperado, antes de avançar.",
                 "Next: repeat this workout once recovered, before moving on.")
    elif s["recovery_flags"]:
        nxt = tr("A seguir: atenção à recuperação ({f}) — amanhã leve.",
                 "Next: mind recovery ({f}) — easy tomorrow.", f=", ".join(s["recovery_flags"]))
    else:
        nxt = tr("A seguir: segue o plano.", "Next: carry on with the plan.")
    planned = next_planned(db, s["today"])
    if planned:
        nxt += " " + tr("Próximo no calendário: {t} ({d}).", "Next on the calendar: {t} ({d}).",
                        t=planned.title, d=planned.day.strftime("%d/%m"))
    out.append(nxt)
    text = " ".join(out)
    res["coach"] = text
    # a leitura do Treinador vem primeiro (é a que tem de caber sempre no painel)
    res["sections"] = [(tr("Treinador", "Coach"), text)] + list(res["sections"])
    res["snapshot"] = snapshot_facts(s)
    return res


def next_planned(db: Database, today: date, days: int = 14):
    try:
        entries = cal.planned_between(db, today, today + timedelta(days=days))
    except Exception:
        return None
    for e in entries:
        if not getattr(e, "done", False) and (e.day > today or e.day == today):
            return e
    return None


# ====================================================================== 2. eventos


def ensure(db: Database) -> None:
    cal.ensure(db)
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS coach_events (id INTEGER PRIMARY KEY, kind TEXT NOT NULL,"
        " name TEXT NOT NULL, day TEXT NOT NULL, sport TEXT, priority TEXT NOT NULL DEFAULT"
        " 'medium', answers TEXT, plan_ids TEXT, created_at TEXT NOT NULL, updated_at TEXT)")
    db.conn.commit()


def default_answers(db: Database, kind: str) -> dict:
    base = {"weekday_min": int(_opt(db, "coach_weekday_minutes")),
            "weekend_min": int(_opt(db, "coach_weekend_minutes")),
            "vacation_from": "", "vacation_to": "", "notes": ""}
    if kind == "strength":
        base.update(time_limit_min=0.0, sessions_per_week=3, goals=[])
    else:
        base.update(route_id="", distance_km=0.0, ascent_m=0.0, target_speed_kmh=0.0,
                    start_time="")
    return base


def _row(r) -> dict:
    d = dict(r)
    for k in ("answers", "plan_ids"):
        try:
            d[k] = json.loads(d.get(k) or ("{}" if k == "answers" else "[]"))
        except ValueError:
            d[k] = {} if k == "answers" else []
    return d


def events(db: Database, include_past: bool = True, today: date | None = None) -> list[dict]:
    ensure(db)
    rows = [_row(r) for r in db.conn.execute("SELECT * FROM coach_events ORDER BY day, id")]
    if not include_past:
        t = (today or date.today()).isoformat()
        rows = [r for r in rows if r["day"] >= t]
    return rows


def event(db: Database, event_id: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM coach_events WHERE id = ?", (event_id,)).fetchone()
    return _row(r) if r else None


def save_event(db: Database, event_id: int | None, *, kind: str, name: str, day: date | str,
               sport: str = "cycling", priority: str = "medium", answers: dict | None = None
               ) -> int:
    ensure(db)
    if kind not in EVENT_KINDS:
        raise ValueError("tipo de evento desconhecido")
    name = " ".join((name or "").split())
    if not name:
        raise ValueError(tr("Dá um nome ao evento.", "Give the event a name."))
    d = day.isoformat() if isinstance(day, date) else str(day)[:10]
    date.fromisoformat(d)
    if priority not in PRIORITIES:
        priority = "medium"
    if kind == "strength":
        sport = "gym"
    elif sport not in ENDURANCE_SPORTS:
        sport = "cycling"
    ans = default_answers(db, kind)
    ans.update(answers or {})
    if kind == "strength":
        ans["goals"] = [g for g in (ans.get("goals") or []) if str(g.get("name", "")).strip()
                        ][:MAX_GOALS]
    blob = json.dumps(ans, ensure_ascii=False)
    if event_id:
        db.conn.execute("UPDATE coach_events SET kind=?, name=?, day=?, sport=?, priority=?,"
                        " answers=?, updated_at=? WHERE id=?",
                        (kind, name, d, sport, priority, blob, now_iso(), event_id))
    else:
        event_id = int(db.conn.execute(
            "INSERT INTO coach_events (kind, name, day, sport, priority, answers, plan_ids,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            (kind, name, d, sport, priority, blob, "[]", now_iso())).lastrowid)
    db.conn.commit()
    return event_id


def delete_event(db: Database, event_id: int, keep_plan: bool = False) -> None:
    ensure(db)
    if not keep_plan:
        clear_schedule(db, event_id)
    db.conn.execute("DELETE FROM coach_events WHERE id = ?", (event_id,))
    db.conn.commit()


def route_facts(db: Database, route_id: str | None) -> dict | None:
    if not route_id:
        return None
    try:
        r = db.route(route_id)
    except Exception:
        r = None
    if r is None:
        return None
    r = dict(r)
    dist = r.get("distance_m") or r.get("length_m") or 0.0
    asc = r.get("ascent_m") or r.get("elevation_gain_m") or 0.0
    return {"name": r.get("name") or "", "distance_km": float(dist) / 1000.0,
            "ascent_m": float(asc)}


def sustainable_if(hours: float) -> float:
    """A fração do limiar que um atleta treinado aguenta durante `hours` (curva aproximada)."""
    pts = ((0.0, 1.05), (1.0, 1.0), (2.0, 0.90), (3.0, 0.84), (4.0, 0.80), (5.0, 0.76),
           (6.0, 0.73), (8.0, 0.68), (12.0, 0.62), (24.0, 0.55))
    if hours >= pts[-1][0]:
        return pts[-1][1]
    for (h0, v0), (h1, v1) in zip(pts, pts[1:]):
        if h0 <= hours <= h1:
            return v0 + (v1 - v0) * (hours - h0) / (h1 - h0)
    return pts[0][1]


def _weeks_left(day: date, today: date) -> float:
    return max(0.0, (day - today).days / 7.0)


def phases(db: Database, today: date, day: date) -> list[dict]:
    """Divide o tempo até ao evento em fases: base → construção → específica → afinação."""
    total = (day - today).days
    if total <= 0:
        return []
    taper = min(int(_opt(db, "coach_taper_days")), max(1, total // 3))
    rest = total - taper
    out = []
    names = {"base": tr("Base", "Base"), "build": tr("Construção", "Build"),
             "specific": tr("Específica", "Specific"), "taper": tr("Afinação", "Taper")}
    if rest >= 42:
        spec = max(14, rest // 4)
        build = max(14, rest // 3)
        split = (("base", rest - spec - build), ("build", build), ("specific", spec))
    elif rest >= 21:
        spec = max(7, rest // 3)
        split = (("build", rest - spec), ("specific", spec))
    elif rest > 0:
        split = (("specific", rest),)
    else:
        split = ()
    start = today
    for key, n in split:
        if n > 0:
            out.append({"key": key, "name": names[key], "start": start,
                        "end": start + timedelta(days=n - 1), "days": n})
            start += timedelta(days=n)
    out.append({"key": "taper", "name": names["taper"], "start": start,
                "end": day - timedelta(days=1), "days": taper})
    return out


def _parse_day(text) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


def _in_vacation(ans: dict, d: date) -> bool:
    a, b = _parse_day(ans.get("vacation_from")), _parse_day(ans.get("vacation_to"))
    return a is not None and b is not None and a <= d <= b


def _minutes(ans: dict, d: date) -> int:
    """Os minutos disponíveis num dia (nas férias, todos os dias valem como fim de semana)."""
    if d.weekday() >= 5 or _in_vacation(ans, d):
        return int(ans.get("weekend_min") or 0)
    return int(ans.get("weekday_min") or 0)


def _clock(text: str | None) -> tuple[int, int] | None:
    from .bp import parse_time
    t = parse_time(text)
    if not t:
        return None
    return int(t[:2]), int(t[3:])


def _shift(clock: tuple[int, int], minutes: int) -> str:
    total = (clock[0] * 60 + clock[1] + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def fuelling(db: Database, hours: float, start: str | None) -> tuple[str, dict]:
    """O plano de alimentação e hidratação do dia do evento."""
    long_ = hours >= _opt(db, "coach_long_event_h")
    carbs = int(_opt(db, "coach_carbs_long_g_per_h" if long_ else "coach_carbs_g_per_h"))
    fluid = int(_opt(db, "coach_fluid_ml_per_h"))
    facts = {"hidratos_g_h": carbs, "liquidos_ml_h": fluid, "horas": round(hours, 2),
             "hidratos_total_g": round(carbs * hours), "liquidos_total_l": round(
                 fluid * hours / 1000, 1)}
    parts = []
    clock = _clock(start)
    if hours < 1.0:
        parts.append(tr("Esforço com menos de 1 h: não precisas de comer durante; chega bem "
                        "hidratado e com a última refeição 2–3 h antes.",
                        "Under 1 h of effort: no need to eat during it; arrive well hydrated "
                        "with the last meal 2–3 h before."))
    else:
        parts.append(tr("Durante: cerca de {c} g de hidratos por hora (total ≈ {t} g) e {f} ml "
                        "de líquidos por hora (≈ {l} L), em pequenas doses a cada 15–20 min, "
                        "desde a primeira meia hora.",
                        "During: about {c} g of carbs per hour (total ≈ {t} g) and {f} ml of "
                        "fluids per hour (≈ {l} L), in small doses every 15–20 min, from the "
                        "first half hour.", c=carbs, t=facts["hidratos_total_g"], f=fluid,
                        l=facts["liquidos_total_l"]))
        if long_:
            parts.append(tr("Como é longo, junta sódio (bebida com eletrólitos) e alguma comida "
                            "sólida nas primeiras horas.",
                            "Being long, add sodium (electrolyte drink) and some solid food in "
                            "the first hours."))
    if clock:
        facts["partida"] = f"{clock[0]:02d}:{clock[1]:02d}"
        facts["chegada_estimada"] = _shift(clock, int(hours * 60))
        if clock[0] < int(_opt(db, "coach_early_start_h")):
            parts.append(tr("Partida às {s} (cedo): o jantar da véspera é a refeição que conta "
                            "— rico em hidratos e fácil de digerir; pequeno-almoço leve às {m} "
                            "(1 h 45 antes) e água ao acordar. Chegada prevista perto das {e}.",
                            "Start at {s} (early): the dinner the day before is the meal that "
                            "counts — carb-rich and easy to digest; a light breakfast at {m} "
                            "(1 h 45 before) and water on waking. Expected finish around {e}.",
                            s=facts["partida"], m=_shift(clock, -105),
                            e=facts["chegada_estimada"]))
        else:
            parts.append(tr("Partida às {s}: refeição principal até às {m} (3 h antes), um "
                            "reforço leve às {k} (45 min antes) e 400–500 ml de água nas 2 h "
                            "antes. Chegada prevista perto das {e}.",
                            "Start at {s}: main meal by {m} (3 h before), a light top-up at {k} "
                            "(45 min before) and 400–500 ml of water in the 2 h before. "
                            "Expected finish around {e}.", s=facts["partida"],
                            m=_shift(clock, -180), k=_shift(clock, -45),
                            e=facts["chegada_estimada"]))
        end_h = clock[0] + clock[1] / 60 + hours
        if clock[0] < 14 and end_h > 12.5 and hours >= 2:
            parts.append(tr("O esforço atravessa a hora de almoço: leva comida a sério, não só "
                            "géis.", "The effort runs through lunchtime: carry real food, not "
                            "just gels."))
        if clock[0] < 16 and end_h > 12 and hours >= 1.5:
            parts.append(tr("Parte do esforço é nas horas de mais calor: conta com mais líquidos "
                            "e sal se estiver quente.", "Part of the effort is in the hottest "
                            "hours: plan more fluids and salt if it is warm."))
    else:
        parts.append(tr("Diz-me a hora de partida para acertar as refeições antes.",
                        "Tell me the start time to set the meals before."))
    parts.append(tr("Treina isto nos treinos longos: o estômago também se treina.",
                    "Practise this on long sessions: the gut is trainable too."))
    return " ".join(parts), facts


def plan_event(db: Database, ev: dict, today: date | None = None) -> Advice:
    today = today or date.today()
    if ev["kind"] == "strength":
        return _plan_strength(db, ev, today)
    return _plan_endurance(db, ev, today)


def _plan_endurance(db: Database, ev: dict, today: date) -> Advice:
    ans = dict(default_answers(db, "endurance"))
    ans.update(ev.get("answers") or {})
    day = date.fromisoformat(ev["day"])
    sport = ev.get("sport") or "cycling"
    a = Advice(tr("Plano para «{n}»", "Plan for «{n}»", n=ev["name"]), tone="good")
    s = snapshot(db, today)
    left = (day - today).days
    route = route_facts(db, ans.get("route_id"))
    dist = float(ans.get("distance_km") or 0) or (route["distance_km"] if route else 0.0)
    asc = float(ans.get("ascent_m") or 0) or (route["ascent_m"] if route else 0.0)
    speed = float(ans.get("target_speed_kmh") or 0)
    data: dict = {"evento": {"nome": ev["name"], "data": ev["day"], "desporto": sport,
                             "prioridade": ev.get("priority"), "dias_ate": left,
                             "distancia_km": round(dist, 1), "subida_m": round(asc),
                             "velocidade_alvo_kmh": speed or None,
                             "hora_partida": ans.get("start_time") or None,
                             "min_dia_semana": ans.get("weekday_min"),
                             "min_fim_semana": ans.get("weekend_min"),
                             "ferias": [ans.get("vacation_from"), ans.get("vacation_to")]
                             if ans.get("vacation_from") else None,
                             "notas": ans.get("notes") or None},
                  "atleta": snapshot_facts(s)}
    # ---- o que falta saber
    if not dist:
        a.questions.append(tr("Qual é a distância (ou escolhe o .gpx da rota)?",
                              "What is the distance (or pick the route's .gpx)?"))
    if not speed:
        a.questions.append(tr("Que velocidade média queres fazer?",
                              "What average speed do you want?"))
    if not ans.get("start_time"):
        a.questions.append(tr("A que horas partes? (para a alimentação e a hidratação)",
                              "What time do you start? (for food and hydration)"))
    if not ans.get("vacation_from"):
        a.questions.append(tr("Vais ter férias antes do evento em que possas treinar mais? "
                              "Senão, conto só com a tua disponibilidade de semana e de fim de "
                              "semana.", "Will you have holidays before the event when you can "
                              "train more? Otherwise I only count on your weekday and weekend "
                              "availability."))
    if left < 0:
        a.tone = "info"
        a.verdict = tr("Este evento já passou ({d}).", "This event has passed ({d}).",
                       d=day.strftime("%d/%m/%Y"))
        a.data = data
        return a
    a.add(tr("Quando", "When"),
          tr("{d} — faltam {n} dias ({w:.0f} semanas). Prioridade {p}.",
             "{d} — {n} days to go ({w:.0f} weeks). Priority {p}.", d=day.strftime("%d/%m/%Y"),
             n=left, w=left / 7.0, p=priority_name(ev.get("priority") or "medium")))
    hours = dist / speed if dist and speed else 0.0
    # ---- é realista?
    feas = []
    if hours:
        data["evento"]["duracao_h"] = round(hours, 2)
        txt = tr("{k:.0f} km a {v:g} km/h são {t}", "{k:.0f} km at {v:g} km/h is {t}", k=dist,
                 v=speed, t=hms(hours * 3600))
        if asc:
            txt += tr(", com {m:.0f} m de subida", ", with {m:.0f} m of climbing", m=asc)
        feas.append(txt + ".")
        if sport == "cycling":
            ath = db.athlete()
            # em plano à velocidade média, mais a parte da energia das subidas que não se
            # recupera a descer (a descer trava-se e o ar leva o resto)
            watts = physics.power_required(ath.total_mass_kg, ath.cda, ath.crr, speed / 3.6,
                                           0.0)
            if asc and hours:
                watts += CLIMB_ENERGY_SHARE * ath.total_mass_kg * physics.G * asc \
                    / (hours * 3600.0)
            pct = watts / max(1, ath.ftp_w)
            cap = sustainable_if(hours)
            data["evento"].update(potencia_media_w=round(watts), pct_ftp=round(pct * 100),
                                  pct_ftp_sustentavel=round(cap * 100))
            feas.append(tr("Sozinho e em estrada, isso pede perto de {w:.0f} W de média "
                           "({p:.0f} % da tua FTP de {f} W); durante {t}, o que se aguenta anda "
                           "pelos {c:.0f} %.",
                           "Solo on the road, that asks for about {w:.0f} W on average "
                           "({p:.0f} % of your {f} W FTP); for {t}, what is sustainable is "
                           "around {c:.0f} %.", w=watts, p=pct * 100, f=ath.ftp_w,
                           t=hms(hours * 3600), c=cap * 100))
            if pct > cap * 1.08:
                a.worst("bad")
                feas.append(tr("Com a forma de hoje é muito ambicioso: ou sobe a FTP até lá, ou "
                               "aponta a uma média mais baixa, ou conta com andar em grupo "
                               "(poupa 20–30 %).",
                               "With today's fitness this is very ambitious: either raise FTP "
                               "by then, aim for a lower average, or count on riding in a group "
                               "(saves 20–30 %)."))
            elif pct > cap * 0.95:
                a.worst("warn")
                feas.append(tr("É exigente mas possível com um bom bloco de treino.",
                               "Demanding but possible with a good training block."))
            else:
                feas.append(tr("Está ao teu alcance.", "It is within your reach."))
            tss = hours * min(pct, 1.2) ** 2 * 100
            data["evento"]["carga_estimada"] = round(tss)
            feas.append(tr("Carga estimada do dia: {t:.0f} (a tua carga crónica é {c:.0f}).",
                           "Estimated load of the day: {t:.0f} (your chronic load is {c:.0f}).",
                           t=tss, c=s["ctl"]))
        longest = s["longest_s"].get(sport, 0.0) / 3600.0
        share = _opt(db, "coach_long_share_pct") / 100.0
        need = share * hours
        if longest < need:
            a.worst("warn")
            feas.append(tr("O teu treino mais longo recente foi de {l}; convém chegares a {n} "
                           "({p:.0f} % do evento) até 2–3 semanas antes.",
                           "Your longest recent session was {l}; you should reach {n} "
                           "({p:.0f} % of the event) by 2–3 weeks before.", p=share * 100, l=hms(longest * 3600) if longest
                           else tr("0 h", "0 h"), n=hms(need * 3600)))
        else:
            feas.append(tr("Já fizeste treinos de {l}: a duração não é o problema.",
                           "You have done {l} sessions: duration is not the problem.",
                           l=hms(longest * 3600)))
    if feas:
        a.add(tr("É realista?", "Is it realistic?"), " ".join(feas))
    # ---- disponibilidade
    wk = 5 * int(ans.get("weekday_min") or 0) + 2 * int(ans.get("weekend_min") or 0)
    avail = tr("{h:.1f} h por semana ({a} min nos dias de semana, {b} min ao fim de semana).",
               "{h:.1f} h a week ({a} min on weekdays, {b} min on weekend days).", h=wk / 60.0,
               a=int(ans.get("weekday_min") or 0), b=int(ans.get("weekend_min") or 0))
    vf, vt = _parse_day(ans.get("vacation_from")), _parse_day(ans.get("vacation_to"))
    if vf and vt and vt >= vf:
        avail += " " + tr("Férias de {a} a {b}: uso-as para um bloco de volume (dias longos "
                          "seguidos).", "Holidays from {a} to {b}: I use them for a volume "
                          "block (long days in a row).", a=vf.strftime("%d/%m"),
                          b=vt.strftime("%d/%m"))
    else:
        avail += " " + tr("Sem férias: fico limitado ao tempo diário e ao fim de semana.",
                          "No holidays: I am limited to daily time and the weekend.")
    if hours and int(ans.get("weekend_min") or 0) < \
            _opt(db, "coach_long_share_pct") / 100.0 * hours * 60:
        a.worst("warn")
        avail += " " + tr("O teu dia mais longo ({b} min) fica abaixo do treino longo que o "
                          "evento pede: precisas de pelo menos um ou dois dias maiores antes.",
                          "Your longest day ({b} min) is under the long session the event "
                          "asks for: you need at least one or two bigger days before.",
                          b=int(ans.get("weekend_min") or 0))
    a.add(tr("Disponibilidade", "Availability"), avail)
    # ---- fases
    ph = phases(db, today, day)
    focus = {"base": tr("volume em Z2 e um treino de tempo; força 1–2×/semana",
                        "Z2 volume and one tempo session; strength 1–2×/week"),
             "build": tr("dois treinos de qualidade (sweet spot / limiar) e o longo a crescer",
                         "two quality sessions (sweet spot / threshold) and the long one "
                         "growing"),
             "specific": tr("esforços ao ritmo do evento, o longo com a alimentação do dia, e "
                            "o percurso (ou parecido)", "event-pace efforts, the long one with "
                            "race-day fuelling, and the course (or similar)"),
             "taper": tr("menos volume (−40 a −50 %), mantém alguma intensidade curta, dorme",
                         "less volume (−40 to −50 %), keep some short intensity, sleep")}
    if ph:
        a.add(tr("Fases", "Phases"), " ".join(
            f"{p['name']} ({p['start'].strftime('%d/%m')}–{p['end'].strftime('%d/%m')}): "
            f"{focus[p['key']]}." for p in ph))
        data["fases"] = [{"fase": p["key"], "inicio": p["start"].isoformat(),
                          "fim": p["end"].isoformat()} for p in ph]
    if left < 14:
        a.worst("warn")
        a.add(tr("Pouco tempo", "Little time"),
              tr("Com menos de duas semanas já não se constrói forma: chega descansado, treina "
                 "o ritmo em doses curtas e acerta a alimentação.",
                 "With under two weeks fitness can no longer be built: arrive rested, rehearse "
                 "pace in short doses and get the fuelling right."))
    # ---- alimentação
    if hours:
        text, facts = fuelling(db, hours, ans.get("start_time"))
        a.add(tr("Alimentação e hidratação", "Food and hydration"), text)
        data["alimentacao"] = facts
    # ---- carga
    if s["has_history"] and left >= 14:
        ramp = _opt(db, "coach_ramp_max_per_week")
        a.add(tr("Carga", "Load"),
              tr("Sobe a carga devagar: no máximo +{r:g} de CTL por semana, e a cada 3–4 "
                 "semanas uma mais leve.", "Raise load slowly: at most +{r:g} CTL per week, "
                 "and every 3–4 weeks a lighter one.", r=ramp))
    a.schedule = _endurance_schedule(db, ev, ans, today, day, sport, hours, ph, s)
    if a.schedule:
        a.add(tr("Calendário", "Calendar"),
              tr("Proponho {n} sessões até ao evento. «Pôr no calendário» agenda-as (podes "
                 "movê-las ou apagá-las depois; voltar a pôr substitui as anteriores).",
                 "I propose {n} sessions up to the event. 'Put on calendar' schedules them (you "
                 "can move or delete them later; putting again replaces the previous ones).",
                 n=len(a.schedule)))
    if not a.verdict:
        a.verdict = {"good": tr("Objetivo ao teu alcance: segue as fases.",
                                "Goal within reach: follow the phases."),
                     "warn": tr("Possível, com pontos a resolver (ver abaixo).",
                                "Possible, with points to solve (see below)."),
                     "bad": tr("Muito ambicioso para a forma atual: revê o objetivo ou o prazo.",
                               "Very ambitious for current fitness: review the goal or the "
                               "date.")}.get(a.tone, "")
    a.data = data
    return a


def _endurance_schedule(db, ev, ans, today, day, sport, hours, ph, s) -> list[Planned]:
    """As sessões propostas, dia a dia, dentro dos minutos disponíveis de cada dia."""
    out: list[Planned] = []
    if not ph:
        return out
    last = min(day - timedelta(days=1),
               today + timedelta(weeks=int(_opt(db, "coach_plan_weeks_max"))))
    long_now = max(60.0, s["longest_s"].get(sport, 0.0) / 60.0 or 60.0)
    long_goal = max(long_now, _opt(db, "coach_long_share_pct") / 100.0 * hours * 60.0) if hours else long_now * 1.3
    span_weeks = max(1.0, (last - today).days / 7.0)
    d = today + timedelta(days=1)
    week_quality = 0
    week_no = 0
    while d <= last:
        if d.weekday() == 0:
            week_quality = 0
            week_no += 1
        phase = next((p for p in ph if p["start"] <= d <= p["end"]), ph[-1])
        mins = _minutes(ans, d)
        easy_week = week_no % 4 == 3 and phase["key"] != "taper"
        if mins < 20:
            d += timedelta(days=1)
            continue
        title = notes = ""
        wd = d.weekday()
        vac = _in_vacation(ans, d)
        if phase["key"] == "taper":
            left = (day - d).days
            if left == 1:
                title = tr("Ativação: 30 min leves + 3 × 1 min ao ritmo do evento",
                           "Opener: 30 min easy + 3 × 1 min at event pace")
            elif wd in (1, 3, 5):
                title = tr("Afinação: {m} min Z2 com 3 × 3 min ao ritmo do evento",
                           "Taper: {m} min Z2 with 3 × 3 min at event pace",
                           m=int(min(mins, 60)))
        elif wd == 5 or (vac and wd in (1, 3)):
            progress = min(1.0, max(0.0, (d - today).days / 7.0 / span_weeks))
            target = long_now + (long_goal - long_now) * progress
            if easy_week:
                target *= 0.7
            m = int(min(mins, target))
            title = tr("Longo: {t} em Z2", "Long: {t} in Z2", t=hms(m * 60))
            if phase["key"] == "specific":
                title += tr(" com blocos ao ritmo do evento", " with event-pace blocks")
                notes = tr("Treina a alimentação do dia do evento.",
                           "Rehearse race-day fuelling.")
        elif wd == 6:
            m = int(min(mins, 90))
            title = tr("Resistência: {m} min Z2 fácil", "Endurance: {m} min easy Z2", m=m)
        elif wd in (1, 3) and week_quality < 2 and not easy_week:
            week_quality += 1
            m = int(min(mins, 75))
            if phase["key"] == "base":
                title = tr("Tempo: {m} min com 2 × 15 min a 85 %", "Tempo: {m} min with "
                           "2 × 15 min at 85 %", m=m) if wd == 1 else \
                    tr("Resistência: {m} min Z2", "Endurance: {m} min Z2", m=m)
            elif phase["key"] == "build":
                title = tr("Limiar: {m} min com 3 × 10 min a 95–100 %", "Threshold: {m} min "
                           "with 3 × 10 min at 95–100 %", m=m) if wd == 1 else \
                    tr("Sweet spot: {m} min com 2 × 20 min a 90 %", "Sweet spot: {m} min with "
                       "2 × 20 min at 90 %", m=m)
            else:
                title = tr("Ritmo do evento: {m} min com 3 × 12 min ao ritmo alvo",
                           "Event pace: {m} min with 3 × 12 min at target pace", m=m) \
                    if wd == 1 else tr("VO2máx: {m} min com 5 × 3 min a 115 %",
                                       "VO2max: {m} min with 5 × 3 min at 115 %", m=m)
        elif wd == 2 and phase["key"] in ("base", "build"):
            out.append(Planned(d, "gym", PLAN_PREFIX + tr("Força: 40 min (pernas e core)",
                                                         "Strength: 40 min (legs and core)"),
                               ev["name"]))
        if title:
            out.append(Planned(d, sport, PLAN_PREFIX + title,
                               (ev["name"] + (" · " + notes if notes else ""))))
        d += timedelta(days=1)
    return out


def _plan_strength(db: Database, ev: dict, today: date) -> Advice:
    ans = dict(default_answers(db, "strength"))
    ans.update(ev.get("answers") or {})
    day = date.fromisoformat(ev["day"])
    a = Advice(tr("Plano para «{n}»", "Plan for «{n}»", n=ev["name"]), tone="good")
    left = (day - today).days
    weeks = max(1.0, left / 7.0)
    goals = [g for g in (ans.get("goals") or []) if str(g.get("name", "")).strip()]
    limit = float(ans.get("time_limit_min") or 0)
    spw = max(1, int(ans.get("sessions_per_week") or 3))
    data = {"evento": {"nome": ev["name"], "data": ev["day"], "dias_ate": left,
                       "prioridade": ev.get("priority"), "limite_min": limit or None,
                       "sessoes_por_semana": spw, "objetivos": goals,
                       "notas": ans.get("notes") or None}}
    if not goals:
        a.questions.append(tr("Que exercícios e que objetivo em cada um (repetições, kg, "
                              "segundos)?", "Which exercises and what target for each (reps, "
                              "kg, seconds)?"))
    if any(not g.get("current") for g in goals):
        a.questions.append(tr("Quanto fazes hoje em cada exercício? (o máximo atual: sem isso "
                              "não sei a distância ao objetivo)",
                              "How much can you do today in each exercise? (current max: "
                              "without it I cannot tell the gap to the goal)"))
    if not ans.get("vacation_from"):
        a.questions.append(tr("Tens algum período (férias) em que possas treinar mais vezes?",
                              "Is there a period (holidays) when you can train more often?"))
    if left < 0:
        a.tone = "info"
        a.verdict = tr("Este evento já passou ({d}).", "This event has passed ({d}).",
                       d=day.strftime("%d/%m/%Y"))
        a.data = data
        return a
    a.add(tr("Quando", "When"),
          tr("{d} — faltam {n} dias ({w:.0f} semanas). {s} sessões por semana. Prioridade {p}.",
             "{d} — {n} days to go ({w:.0f} weeks). {s} sessions a week. Priority {p}.",
             d=day.strftime("%d/%m/%Y"), n=left, w=left / 7.0, s=spw,
             p=priority_name(ev.get("priority") or "medium")))
    lines = []
    for g in goals:
        unit = g.get("unit") or "reps"
        target, cur = float(g.get("target") or 0), float(g.get("current") or 0)
        u = {"reps": tr("rep.", "reps"), "kg": "kg", "s": "s", "m": "m"}.get(unit, unit)
        if not target:
            continue
        if not cur:
            lines.append(tr("{n}: objetivo {t:g} {u} (falta o teu valor atual).",
                            "{n}: target {t:g} {u} (your current value is missing).",
                            n=g["name"], t=target, u=u))
            continue
        if cur >= target:
            lines.append(tr("{n}: já fazes {c:g} {u} (objetivo {t:g}) — é manter.",
                            "{n}: you already do {c:g} {u} (target {t:g}) — just maintain.",
                            n=g["name"], c=cur, t=target, u=u))
            continue
        rate = ((target / cur) ** (1.0 / weeks) - 1.0) * 100.0
        kind = "load" if unit == "kg" else "reps"
        soft, hard = (_opt(db, f"coach_{kind}_week_soft_pct"),
                      _opt(db, f"coach_{kind}_week_hard_pct"))
        if rate > hard:
            verdict = tr("muito ambicioso", "very ambitious")
            a.worst("bad")
        elif rate > soft:
            verdict = tr("exigente", "demanding")
            a.worst("warn")
        else:
            verdict = tr("realista", "realistic")
        lines.append(tr("{n}: de {c:g} para {t:g} {u} são +{r:.1f} % por semana — {v}.",
                        "{n}: from {c:g} to {t:g} {u} is +{r:.1f} % per week — {v}.",
                        n=g["name"], c=cur, t=target, u=u, r=rate, v=verdict))
    if lines:
        a.add(tr("Objetivos", "Goals"), " ".join(lines))
    reps_total = sum(float(g.get("target") or 0) for g in goals
                     if (g.get("unit") or "reps") == "reps")
    if limit and reps_total:
        per_min = reps_total / limit
        data["evento"]["rep_por_min"] = round(per_min, 1)
        txt = tr("{t:.0f} repetições em {m:g} min são {r:.0f} por minuto, sem parar",
                 "{t:.0f} reps in {m:g} min is {r:.0f} per minute, non-stop", t=reps_total,
                 m=limit, r=per_min)
        if per_min > _opt(db, "coach_reps_per_min_max"):
            a.worst("bad")
            txt += tr(": isto está acima do que atletas de topo fazem num só exercício — "
                      "considera mais tempo ou menos repetições, ou divide por etapas (primeiro "
                      "metade neste tempo).", ": this is above what top athletes do in a single "
                      "exercise — consider more time or fewer reps, or split it in stages "
                      "(first half in this time).")
        elif per_min > _opt(db, "coach_reps_per_min_dense"):
            a.worst("warn")
            txt += tr(": muito denso — a transição entre exercícios e a técnica sob fadiga "
                      "decidem tudo.", ": very dense — transitions between exercises and "
                      "technique under fatigue decide everything.")
        else:
            txt += tr(": denso mas treinável.", ": dense but trainable.")
        a.add(tr("O ritmo que isto pede", "The pace this demands"), txt)
    ph = phases(db, today, day)
    focus = {"base": tr("volume submáximo: muitas séries a 50–60 % do teu máximo, longe da "
                        "falha, várias vezes por semana; técnica limpa",
                        "submaximal volume: many sets at 50–60 % of your max, far from failure, "
                        "several times a week; clean technique"),
             "build": tr("densidade: EMOM e séries com descansos cada vez mais curtos; uma "
                         "sessão pesada (3–6 rep.) para a força máxima",
                         "density: EMOM and sets with ever shorter rests; one heavy session "
                         "(3–6 reps) for max strength"),
             "specific": tr("simulações do evento a 70–90 % (uma por semana), na ordem e com as "
                            "transições reais; o resto é manutenção",
                            "event simulations at 70–90 % (one a week), in order and with the "
                            "real transitions; the rest is maintenance"),
             "taper": tr("metade do volume, nada até à falha, a última simulação 5–7 dias antes",
                         "half the volume, nothing to failure, the last simulation 5–7 days "
                         "before")}
    if ph:
        a.add(tr("Fases", "Phases"), " ".join(
            f"{p['name']} ({p['start'].strftime('%d/%m')}–{p['end'].strftime('%d/%m')}): "
            f"{focus[p['key']]}." for p in ph))
        data["fases"] = [{"fase": p["key"], "inicio": p["start"].isoformat(),
                          "fim": p["end"].isoformat()} for p in ph]
    a.add(tr("Cuidados", "Care"),
          tr("Sobe o volume semanal no máximo 10 %; ombros, cotovelos e pulsos avisam antes de "
             "os músculos — dor na articulação é para parar. Dorme e come proteína suficiente.",
             "Raise weekly volume by at most 10 %; shoulders, elbows and wrists warn before "
             "muscles do — joint pain means stop. Sleep and eat enough protein."))
    if limit:
        a.add(tr("No dia", "On the day"),
              tr("Aquece 10–15 min, parte abaixo do ritmo médio, divide em séries curtas desde "
                 "o início (não vás à falha na primeira) e decide antes onde respiras.",
                 "Warm up 10–15 min, start below average pace, break into short sets from the "
                 "start (do not hit failure on the first) and decide beforehand where you "
                 "breathe."))
    a.schedule = _strength_schedule(db, ev, ans, today, day, ph, spw, goals)
    if a.schedule:
        a.add(tr("Calendário", "Calendar"),
              tr("Proponho {n} sessões até ao evento. «Pôr no calendário» agenda-as.",
                 "I propose {n} sessions up to the event. 'Put on calendar' schedules them.",
                 n=len(a.schedule)))
    if not a.verdict:
        a.verdict = {"good": tr("Objetivo realista: segue as fases.",
                                "Realistic goal: follow the phases."),
                     "warn": tr("Exigente: possível com consistência.",
                                "Demanding: possible with consistency."),
                     "bad": tr("Muito ambicioso neste prazo: revê os números ou a data.",
                               "Very ambitious in this time: review the numbers or the date.")
                     }.get(a.tone, tr("Diz-me os objetivos e o que fazes hoje.",
                                      "Tell me the goals and what you do today."))
    a.data = data
    return a


def _strength_schedule(db, ev, ans, today, day, ph, spw, goals) -> list[Planned]:
    out: list[Planned] = []
    if not ph:
        return out
    patterns = {1: (2,), 2: (1, 4), 3: (0, 2, 4), 4: (0, 1, 3, 5), 5: (0, 1, 2, 4, 5),
                6: (0, 1, 2, 3, 4, 5), 7: (0, 1, 2, 3, 4, 5, 6)}
    days_ = patterns[min(7, spw)]
    names = ", ".join(g["name"] for g in goals[:4]) or tr("os exercícios do evento",
                                                           "the event exercises")
    last = min(day - timedelta(days=1),
               today + timedelta(weeks=int(_opt(db, "coach_plan_weeks_max"))))
    d = today + timedelta(days=1)
    while d <= last:
        vac = _in_vacation(ans, d)
        if d.weekday() in days_ or (vac and d.weekday() in (1, 3, 5)):
            phase = next((p for p in ph if p["start"] <= d <= p["end"]), ph[-1])
            k = d.weekday()
            if phase["key"] == "base":
                title = tr("Volume: séries submáximas ({n})", "Volume: submaximal sets ({n})",
                           n=names)
            elif phase["key"] == "build":
                title = tr("Força pesada: 5 × 3–5 ({n})", "Heavy strength: 5 × 3–5 ({n})",
                           n=names) if k == days_[0] else \
                    tr("Densidade: EMOM 12–16 min ({n})", "Density: EMOM 12–16 min ({n})",
                       n=names)
            elif phase["key"] == "specific":
                title = tr("Simulação do evento a 80 %", "Event simulation at 80 %") \
                    if k == days_[-1] else tr("Manutenção: séries curtas e rápidas ({n})",
                                              "Maintenance: short, fast sets ({n})", n=names)
            else:
                left = (day - d).days
                if left in (5, 6, 7) and k == days_[0]:
                    title = tr("Última simulação a 70 %", "Last simulation at 70 %")
                else:
                    title = tr("Afinação: metade do volume, sem falha",
                               "Taper: half the volume, no failure")
            out.append(Planned(d, "gym", PLAN_PREFIX + title, ev["name"]))
        d += timedelta(days=1)
    return out


def apply_schedule(db: Database, event_id: int, schedule: list[Planned]) -> int:
    """Põe as sessões no calendário (substitui as que este evento já lá tinha)."""
    ensure(db)
    clear_schedule(db, event_id)
    ids = [cal.plan_add(db, p.day, p.sport, None, p.title, p.notes) for p in schedule]
    db.conn.execute("UPDATE coach_events SET plan_ids = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(ids), now_iso(), event_id))
    db.conn.commit()
    return len(ids)


def clear_schedule(db: Database, event_id: int) -> int:
    ev = event(db, event_id)
    if ev is None:
        return 0
    n = 0
    for pid in ev["plan_ids"]:
        cal.plan_remove(db, pid)
        n += 1
    db.conn.execute("UPDATE coach_events SET plan_ids = '[]' WHERE id = ?", (event_id,))
    db.conn.commit()
    return n


def add_to_calendar(db: Database, key: str, schedule: list[Planned]) -> int:
    """Sessões que não são de um evento (um desafio, a fase da longevidade): substituem as
    que o mesmo pedido (`key`) já lá tinha posto."""
    cal.ensure(db)
    store = dict(db.get("coach_plans", {}) or {})
    for pid in store.get(key, []):
        cal.plan_remove(db, pid)
    store[key] = [cal.plan_add(db, p.day, p.sport, None, p.title, p.notes) for p in schedule]
    db.set("coach_plans", store)
    return len(store[key])


def remove_from_calendar(db: Database, key: str) -> int:
    store = dict(db.get("coach_plans", {}) or {})
    ids = store.pop(key, [])
    for pid in ids:
        cal.plan_remove(db, pid)
    db.set("coach_plans", store)
    return len(ids)


# ====================================================================== 3. desafios


def challenge_priority(db: Database, challenge_id: int) -> str | None:
    return (db.get("coach_challenge_priority", {}) or {}).get(str(challenge_id))


def set_challenge_priority(db: Database, challenge_id: int, priority: str | None) -> None:
    store = dict(db.get("coach_challenge_priority", {}) or {})
    if priority in PRIORITIES:
        store[str(challenge_id)] = priority
    else:
        store.pop(str(challenge_id), None)
    db.set("coach_challenge_priority", store)


def _amount_text(metric: str, v: float) -> str:
    if metric == "distance_m":
        return f"{v / 1000:.1f} km"
    if metric == "ascent_m":
        return f"{v:.0f} m"
    if metric == "time_s":
        return hms(v)
    return f"{v:.0f}"


def challenge_feedback(db: Database, ch: dict, today: date | None = None) -> Advice:
    today = today or date.today()
    ch = dict(ch)
    sport = ch.get("sport") or "cycling"
    metric, target = ch["metric"], float(ch["target"])
    att = sc.refresh(db, ch)
    progress = float(att.get("progress") or 0)
    prio = challenge_priority(db, ch["id"])
    a = Advice(tr("Desafio «{n}»", "Challenge «{n}»", n=ch["name"]), tone="good")
    pct = min(1.0, progress / max(target, 1e-9))
    remaining = max(0.0, target - progress)
    started = sc._parse(att.get("started_at"))
    elapsed_d = max(1.0, (datetime.combine(today, datetime.max.time()) - started
                          ).total_seconds() / 86400.0) if started else 1.0
    rate_week = progress / elapsed_d * 7.0
    deadline = sc.deadline_of(ch)
    data = {"desafio": {"nome": ch["name"], "desporto": sport, "metrica": metric,
                        "objetivo": target, "feito": round(progress, 1),
                        "percentagem": round(pct * 100), "ritmo_semanal": round(rate_week, 1),
                        "data_limite": deadline.isoformat() if deadline else None,
                        "prioridade": prio}}
    a.add(tr("Onde estás", "Where you are"),
          tr("{d} de {t} ({p:.0f} %). Faltam {r}. Ritmo desde o início: {w} por semana.",
             "{d} of {t} ({p:.0f} %). {r} to go. Pace since the start: {w} per week.",
             d=_amount_text(metric, progress), t=_amount_text(metric, target), p=pct * 100,
             r=_amount_text(metric, remaining), w=_amount_text(metric, rate_week)))
    need_week = None
    if remaining <= 0:
        a.verdict = tr("Feito! Queres um desafio maior?", "Done! Want a bigger challenge?")
    elif deadline is not None:
        days_left = (deadline - today).days + 1
        if days_left <= 0:
            a.tone = "bad"
            a.verdict = tr("O prazo acabou com {p:.0f} % feito.",
                           "The deadline passed with {p:.0f} % done.", p=pct * 100)
        else:
            need_week = remaining / days_left * 7.0
            total_d = elapsed_d + days_left
            expected = elapsed_d / total_d
            data["desafio"].update(dias_que_faltam=days_left,
                                   preciso_por_semana=round(need_week, 1))
            gap = pct - expected
            ratio = need_week / rate_week if rate_week > 0 else float("inf")
            if gap >= 0.0:
                a.verdict = tr("Estás à frente do ritmo: perto de o conseguir.",
                               "You are ahead of pace: close to making it.")
            elif ratio <= 1.25:
                a.tone = "warn"
                a.verdict = tr("Estás um pouco atrás, mas perto: dá para recuperar.",
                               "You are slightly behind, but close: recoverable.")
            elif ratio <= 2.0:
                a.tone = "warn"
                a.verdict = tr("Estás atrás: é preciso subir o ritmo já.",
                               "You are behind: the pace must go up now.")
            else:
                a.tone = "bad"
                a.verdict = tr("Ainda estás longe: ao ritmo atual não chega.",
                               "You are still far: the current pace is not enough.")
            a.add(tr("O que falta", "What it takes"),
                  tr("Faltam {n} dias: precisas de {w} por semana (tens feito {c}).",
                     "{n} days left: you need {w} per week (you have been doing {c}).",
                     n=days_left, w=_amount_text(metric, need_week),
                     c=_amount_text(metric, rate_week)))
    else:
        if rate_week > 0:
            eta = remaining / rate_week * 7.0
            a.verdict = tr("Sem prazo: ao ritmo atual chegas lá em cerca de {d:.0f} dias.",
                           "No deadline: at the current pace you get there in about {d:.0f} "
                           "days.", d=eta)
            data["desafio"]["dias_estimados"] = round(eta)
        else:
            a.tone = "info"
            a.verdict = tr("Ainda não começaste a somar para este desafio.",
                           "You have not started adding to this challenge yet.")
        a.add(tr("Prazo", "Deadline"),
              tr("Um desafio com data limite puxa mais: queres pôr-lhe uma?",
                 "A challenge with a deadline pulls harder: want to set one?"))
    # ---- importância → ajuste dos treinos
    if prio is None and remaining > 0:
        a.questions += [tr("Quão importante é este desafio para ti?",
                           "How important is this challenge to you?"),
                        tr("Queres dar-lhe prioridade sobre o resto do treino?",
                           "Do you want to prioritise it over the rest of your training?")]
    elif remaining > 0:
        s = snapshot(db, today)
        per = need_week if need_week is not None else max(rate_week, 0.0) * 1.2
        sess_amount = _typical_amount(db, sport, metric, today)
        if prio == "high":
            txt = tr("Prioridade alta: organizo a semana à volta dele.",
                     "High priority: I build the week around it.")
        elif prio == "medium":
            txt = tr("Prioridade média: encaixo-o sem tirar os treinos-chave.",
                     "Medium priority: I fit it in without removing key sessions.")
        else:
            txt = tr("Prioridade baixa: fica em pano de fundo; não mexo nos treinos por ele.",
                     "Low priority: it stays in the background; I do not change sessions for "
                     "it.")
        if per and prio != "low":
            n_sess = max(1, min(7, math.ceil(per / sess_amount))) if sess_amount else 3
            each = per / n_sess
            txt += " " + tr("Por semana: {n} sessões de cerca de {e}.",
                            "Per week: {n} sessions of about {e}.", n=n_sess,
                            e=_amount_text(metric, each) if metric != "sessions"
                            else tr("1 sessão", "1 session"))
            if s["has_history"] and s["tsb"] <= _opt(db, "coach_tired_tsb"):
                txt += " " + tr("Estás cansado (TSB {t:+.0f}): começa pelas sessões fáceis.",
                                "You are tired (TSB {t:+.0f}): start with the easy sessions.",
                                t=s["tsb"])
            a.schedule = _challenge_schedule(db, ch, sport, metric, each, n_sess, today,
                                             deadline, prio)
            data["desafio"].update(sessoes_por_semana=n_sess, por_sessao=round(each, 1))
        a.add(tr("Ajuste dos treinos", "Training adjustment"), txt)
    a.data = data
    return a


def _typical_amount(db: Database, sport: str, metric: str, today: date) -> float:
    cut = datetime.combine(today - timedelta(days=int(_opt(db, "coach_history_days"))),
                           datetime.min.time())
    vals = [sc._amount(metric, s) for s in sc.sessions_of(db, sport) if s["at"] >= cut]
    vals = [v for v in vals if v > 0]
    if vals:
        return statistics.median(vals)
    return {"distance_m": 30000.0 if sport == "cycling" else 8000.0, "time_s": 3600.0,
            "sessions": 1.0, "ascent_m": 500.0}.get(metric, 1.0)


def _challenge_schedule(db, ch, sport, metric, each, n_sess, today, deadline, prio
                        ) -> list[Planned]:
    patterns = {1: (5,), 2: (2, 5), 3: (1, 3, 5), 4: (1, 3, 5, 6), 5: (0, 1, 3, 5, 6),
                6: (0, 1, 2, 3, 5, 6), 7: (0, 1, 2, 3, 4, 5, 6)}
    days_ = patterns[n_sess]
    weeks = 4 if prio == "high" else 2
    last = today + timedelta(weeks=weeks)
    if deadline is not None:
        last = min(last, deadline)
    psport = "gym" if sport == "gym" else sport
    out = []
    d = today + timedelta(days=1)
    while d <= last:
        if d.weekday() in days_:
            amount = _amount_text(metric, each) if metric != "sessions" else ""
            title = (tr("Desafio: {a}", "Challenge: {a}", a=amount) if amount
                     else tr("Desafio: sessão", "Challenge: session"))
            out.append(Planned(d, psport, PLAN_PREFIX + title, ch["name"]))
        d += timedelta(days=1)
    return out


# ====================================================================== 4. longevidade

AXIS_RX = {
    "aerobic": ("3 sessões de Z2 de 45–90 min por semana (conversa possível); é a base de tudo.",
                "3 Z2 sessions of 45–90 min a week (able to talk); the base of everything."),
    "threshold": ("1 sessão por semana com 2–3 × 10–20 min perto do limiar.",
                  "1 session a week with 2–3 × 10–20 min near threshold."),
    "vo2max": ("1 sessão por semana de 4 × 4 min fortes (ou 5 × 3 min), com descanso igual.",
               "1 session a week of 4 × 4 min hard (or 5 × 3 min), equal rest."),
    "anaerobic": ("sprints curtos (6–8 × 30 s) uma vez por semana, bem recuperado.",
                  "short sprints (6–8 × 30 s) once a week, well recovered."),
    "strength": ("2–3 sessões de força por semana: pernas, empurrar, puxar, carregar.",
                 "2–3 strength sessions a week: legs, push, pull, carry."),
    "power": ("saltos e movimentos explosivos (2 × por semana, poucas repetições, frescos).",
              "jumps and explosive moves (2 × a week, few reps, fresh)."),
    "mobility": ("10–15 min de mobilidade por dia, ou 2 sessões de yoga por semana.",
                 "10–15 min of mobility a day, or 2 yoga sessions a week."),
    "stability": ("equilíbrio e isométricos (pranchas, apoio numa perna) 3 × por semana.",
                  "balance and isometrics (planks, single-leg stance) 3 × a week."),
    "recovery": ("dormir 7–9 h a horas regulares e registar o sono e a HRV no diário.",
                 "sleep 7–9 h at regular times and log sleep and HRV in the daily log."),
}
AXIS_SESSION = {
    "aerobic": ("cycling", "Z2: 60 min fácil", "Z2: 60 min easy", (1, 3, 5)),
    "threshold": ("cycling", "Limiar: 3 × 10 min a 95–100 %", "Threshold: 3 × 10 min at 95–100 %",
                  (1,)),
    "vo2max": ("cycling", "VO2máx: 4 × 4 min fortes", "VO2max: 4 × 4 min hard", (3,)),
    "anaerobic": ("cycling", "Sprints: 6 × 30 s", "Sprints: 6 × 30 s", (5,)),
    "strength": ("gym", "Força: 45 min (pernas, empurrar, puxar)",
                 "Strength: 45 min (legs, push, pull)", (0, 2, 4)),
    "power": ("gym", "Potência: saltos e explosivos, 20 min", "Power: jumps and explosives, "
              "20 min", (1, 4)),
    "mobility": ("gym", "Mobilidade: 15 min", "Mobility: 15 min", (0, 2, 4, 6)),
    "stability": ("gym", "Estabilidade: equilíbrio e isométricos, 15 min",
                  "Stability: balance and isometrics, 15 min", (1, 3, 5)),
}


def longevity_path(db: Database, today: date | None = None) -> Advice:
    today = today or date.today()
    a = Advice(tr("Caminho para a longevidade", "Path to longevity"), tone="good")
    try:
        res = lg.compute(db, today)
    except Exception:
        res = {}
    cur = res.get("3m") or {}
    axes = {k: v for k, v in (cur.get("axes") or {}).items() if k in lg.AXES}
    if not axes or not any(v > 0 for v in axes.values()):
        a.tone = "info"
        a.verdict = tr("Ainda não há sessões suficientes para ler o teu índice de longevidade.",
                       "Not enough sessions yet to read your longevity index.")
        a.add(tr("Por onde começar", "Where to start"),
              tr("Três pilares, por esta ordem: {a} {b} E uma vez por semana: {c}",
                 "Three pillars, in this order: {a} {b} And once a week: {c}",
                 a=tr(*AXIS_RX["aerobic"]), b=tr(*AXIS_RX["strength"]),
                 c=tr(*AXIS_RX["vo2max"])))
        a.data = {"longevidade": {"indice": None}}
        return a
    cut = _opt(db, "coach_weak_axis_score")
    order = sorted(axes.items(), key=lambda x: x[1])
    weak = [(k, v) for k, v in order if v < cut]
    strong = [k for k, v in order[::-1] if v >= cut][:3]
    index = cur.get("index") or 0.0
    month = (res.get("1m") or {}).get("index")
    a.add(tr("Onde estás", "Where you are"),
          tr("Índice de longevidade (3 meses): {i:.0f}/100", "Longevity index (3 months): "
             "{i:.0f}/100", i=index)
          + (tr("; no último mês {m:.0f} ({d:+.0f}).", "; in the last month {m:.0f} ({d:+.0f}).",
                m=month, d=month - index) if month is not None else ".")
          + (" " + tr("Os teus pontos fortes: {s}.", "Your strong points: {s}.",
                      s=", ".join(lg.axis_label(k) for k in strong)) if strong else ""))
    data = {"longevidade": {"indice_3m": round(index), "indice_1m": round(month)
                            if month is not None else None,
                            "eixos": {k: round(v) for k, v in axes.items()},
                            "fracos": [k for k, _v in weak]}}
    if not weak:
        a.verdict = tr("Nenhum eixo abaixo de {c:.0f}: o caminho é manter o equilíbrio.",
                       "No axis below {c:.0f}: the path is keeping the balance.", c=cut)
        a.add(tr("Manter", "Maintain"),
              tr("Continua com a mistura atual e revê daqui a um mês. O eixo mais baixo é {x} "
                 "({v:.0f}).", "Keep the current mix and review in a month. The lowest axis is "
                 "{x} ({v:.0f}).", x=lg.axis_label(order[0][0]), v=order[0][1]))
        a.data = data
        return a
    a.tone = "warn"
    a.verdict = tr("As tuas fraquezas para a longevidade: {w}.",
                   "Your longevity weaknesses: {w}.",
                   w=", ".join(f"{lg.axis_label(k)} ({v:.0f})" for k, v in weak[:4]))
    weeks = int(_opt(db, "coach_path_weeks"))
    start = today + timedelta(days=1)
    plan = []
    for i in range(0, min(len(weak), 6), 2):
        pair = [k for k, _v in weak[i:i + 2]]
        end = start + timedelta(weeks=weeks) - timedelta(days=1)
        plan.append((start, end, pair))
        a.add(tr("Fase {n} ({a}–{b}): {x}", "Phase {n} ({a}–{b}): {x}", n=len(plan),
                 a=start.strftime("%d/%m"), b=end.strftime("%d/%m"),
                 x=" + ".join(lg.axis_label(k) for k in pair)),
              " ".join(tr(*AXIS_RX[k]) for k in pair))
        start = end + timedelta(days=1)
    data["longevidade"]["fases"] = [{"inicio": s_.isoformat(), "fim": e_.isoformat(),
                                     "eixos": p} for s_, e_, p in plan]
    a.add(tr("Sem perder o resto", "Without losing the rest"),
          tr("Em cada fase, o que já está bom fica em manutenção (uma sessão por semana chega).",
             "In each phase, what is already good stays in maintenance (one session a week is "
             "enough)."))
    s = snapshot(db, today)
    if s["has_history"] and s["tsb"] <= _opt(db, "coach_tired_tsb"):
        a.add(tr("Antes de começar", "Before starting"),
              tr("Estás cansado (TSB {t:+.0f}): começa a fase depois de 2–3 dias leves.",
                 "You are tired (TSB {t:+.0f}): start the phase after 2–3 easy days.",
                 t=s["tsb"]))
    # as sessões da primeira fase
    s0, e0, pair = plan[0]
    d = s0
    while d <= e0:
        for k in pair:
            spec = AXIS_SESSION.get(k)
            if spec and d.weekday() in spec[3]:
                a.schedule.append(Planned(d, spec[0], PLAN_PREFIX + tr(spec[1], spec[2]),
                                          tr("Longevidade: {x}", "Longevity: {x}",
                                             x=lg.axis_label(k))))
        d += timedelta(days=1)
    a.questions = [tr("Tens alguma limitação (lesão, material, tempo) que me obrigue a trocar "
                      "alguma destas fases?", "Any limitation (injury, equipment, time) that "
                      "makes me swap any of these phases?")]
    a.data = data
    return a


# ====================================================================== 5. hoje


def suggest_today(db: Database, today: date | None = None) -> Advice:
    today = today or date.today()
    s = snapshot(db, today)
    a = Advice(tr("O que fazer hoje", "What to do today"), tone="good")
    a.add(tr("Como estás", "How you are"), form_text(s) + (
        " " + tr("Recuperação: {f}.", "Recovery: {f}.", f=", ".join(s["recovery_flags"]))
        if s["recovery_flags"] else ""))
    try:
        planned = [e for e in cal.planned_for(db, today) if not e.done]
    except Exception:
        planned = []
    focus = None
    if s["today_load"] > 0:
        a.verdict = tr("Já treinaste hoje: agora é recuperar (comer, hidratar, dormir).",
                       "You already trained today: now recover (eat, hydrate, sleep).")
        focus = None
    elif not s["has_history"]:
        a.tone = "info"
        focus = "endurance"
        a.verdict = tr("Começa simples: 30–45 min fáceis, e regista como te sentiste.",
                       "Start simple: 30–45 easy minutes, and log how you felt.")
    elif s["tsb"] <= _opt(db, "coach_overload_tsb"):
        a.tone = "warn"
        a.verdict = tr("Descanso (ou 20–30 min muito leves): a fadiga está alta.",
                       "Rest (or 20–30 very easy minutes): fatigue is high.")
        focus = "recovery"
    elif len(s["recovery_flags"]) >= 2:
        a.tone = "warn"
        a.verdict = tr("Dia leve: o corpo ainda não recuperou ({f}).",
                       "Easy day: the body has not recovered yet ({f}).",
                       f=", ".join(s["recovery_flags"]))
        focus = "recovery"
    elif s["tsb"] <= _opt(db, "coach_tired_tsb") or \
            (s["typical_load"] and s["yesterday_load"] >=
             _opt(db, "coach_heavy_factor") * s["typical_load"]):
        a.verdict = tr("Resistência fácil em Z2 (45–75 min): ontem ou a semana pesaram.",
                       "Easy Z2 endurance (45–75 min): yesterday or the week were heavy.")
        focus = "endurance"
    elif s["days_since_last"] is not None and s["days_since_last"] >= 4:
        a.verdict = tr("Há {n} dias sem treinar: volta com uma sessão fácil.",
                       "{n} days without training: come back with an easy session.",
                       n=s["days_since_last"])
        focus = "endurance"
    else:
        weak = [k for k, _v in s["weak_axes"] if k in AXIS_SESSION]
        pick = weak[0] if weak else None
        if s["tsb"] >= _opt(db, "coach_fresh_tsb") and pick in ("vo2max", "threshold",
                                                               "anaerobic"):
            focus = pick
            a.verdict = tr("Estás fresco: bom dia para qualidade — {x}.",
                           "You are fresh: a good day for quality — {x}.",
                           x=tr(*AXIS_SESSION[pick][1:3]))
        elif pick in ("strength", "power", "mobility", "stability"):
            a.verdict = tr("Hoje: {x} (o teu eixo mais fraco para a longevidade é {k}).",
                           "Today: {x} (your weakest longevity axis is {k}).",
                           x=tr(*AXIS_SESSION[pick][1:3]), k=lg.axis_label(pick))
        elif s["tsb"] >= _opt(db, "coach_fresh_tsb"):
            focus = "threshold"
            a.verdict = tr("Estás fresco: um treino de limiar ou sweet spot cai bem.",
                           "You are fresh: a threshold or sweet spot session fits well.")
        else:
            focus = "endurance"
            a.verdict = tr("Dia de construção: resistência em Z2, ou tempo se te sentires bem.",
                           "Building day: Z2 endurance, or tempo if you feel good.")
    if planned:
        names = ", ".join(e.title or sport_name(e.sport) for e in planned)
        note = tr("No calendário tens: {n}.", "On the calendar you have: {n}.", n=names)
        if a.tone == "warn":
            note += " " + tr("Sugiro trocá-lo por algo leve ou passá-lo para outro dia.",
                             "I suggest swapping it for something easy or moving it to another "
                             "day.")
        a.add(tr("Planeado", "Planned"), note)
    beh = []
    rec = s["recovery"]
    if rec.get("sono_h") is not None and rec["sono_h"] < _opt(db, "health_sleep_min_h"):
        beh.append(tr("deita-te mais cedo (média de {h:.1f} h)", "go to bed earlier (mean of "
                      "{h:.1f} h)", h=rec["sono_h"]))
    hab = ha.habits(db, today)
    for f in hab.data.get("avisos") or []:
        beh.append(f)
    if s["sessions_per_week"] and s["sessions_per_week"] < 2:
        beh.append(tr("regularidade: aponta a 3 sessões por semana", "consistency: aim for 3 "
                      "sessions a week"))
    if not beh:
        beh.append(tr("continua a registar o diário (sono, energia): é o que me deixa afinar "
                      "as sugestões", "keep logging the daily log (sleep, energy): it lets me "
                      "tune the suggestions"))
    a.add(tr("Comportamentos", "Behaviours"), "; ".join(beh).capitalize() + ".")
    a.data = {"atleta": snapshot_facts(s), "sugestao": {"foco": focus},
              "planeado_hoje": [e.title for e in planned]}
    a.data["focus"] = focus
    return a


# ====================================================================== 6. construtor


def build_workout(db: Database, sport: str, focus: str, minutes: int,
                  today: date | None = None) -> dict:
    """Um treino feito pelo Treinador para o construtor: {"name", "goal", "blocks", "note"}.
    Se o atleta estiver cansado, o bloco principal encolhe (e a nota diz porquê)."""
    if sport not in BUILD_SPORTS:
        raise ValueError(tr("O Treinador programa treinos de ciclismo, corrida e remo.",
                            "The coach programs cycling, running and rowing workouts."))
    if focus not in FOCUSES:
        focus = "endurance"
    minutes = int(max(20, min(300, minutes)))
    s = snapshot(db, today)
    tired = s["has_history"] and s["tsb"] <= _opt(db, "coach_tired_tsb")
    B = bl.Block
    warm = 300 if minutes <= 30 else 600 if minutes <= 75 else 900
    cool = 300 if minutes <= 60 else 600
    main = minutes * 60 - warm - cool
    note = ""
    if tired and focus not in ("recovery", "endurance"):
        main = int(main * 0.75)
        note = tr("Estás cansado (TSB {t:+.0f}): encurtei o bloco principal 25 %.",
                  "You are tired (TSB {t:+.0f}): I shortened the main set by 25 %.", t=s["tsb"])
    blocks = [B("warmup", "time", warm, 50, 75, tr("Aquecimento", "Warm-up"))]
    spec = {"tempo": (85, 900, 300, 60), "sweetspot": (90, 1200, 300, 55),
            "threshold": (98, 600, 300, 55), "vo2max": (115, 180, 180, 50),
            "anaerobic": (140, 40, 200, 45)}
    if focus == "recovery":
        blocks = [B("active", "time", minutes * 60, 55, None, tr("Muito fácil", "Very easy"))]
        goal = tr("Recuperar: pernas a rodar, sem esforço.", "Recover: legs spinning, no effort.")
    elif focus == "endurance":
        blocks.append(B("active", "time", max(300, main), 68, None, tr("Z2: conversa possível",
                                                                         "Z2: able to talk")))
        goal = tr("Resistência aeróbia em Z2.", "Aerobic endurance in Z2.")
    else:
        pct, work, rest, rpct = spec[focus]
        n = max(2 if focus in ("tempo", "sweetspot", "threshold") else 3,
                int((main + rest) // (work + rest)))
        cap = {"tempo": 4, "sweetspot": 3, "threshold": 5, "vo2max": 7, "anaerobic": 10}[focus]
        n = min(n, cap)
        while n > 1 and n * work + (n - 1) * rest > main:
            n -= 1
        for i in range(n):
            blocks.append(B("active", "time", work, pct, None, f"{i + 1}/{n}"))
            if i < n - 1:
                blocks.append(B("rest", "time", rest, rpct, None, tr("Recupera", "Recover")))
        used = n * work + (n - 1) * rest
        if main - used >= 300:
            blocks.append(B("active", "time", main - used, 65, None, tr("Z2", "Z2")))
        goal = {"tempo": tr("Tempo: {n} × {m} min a {p} %.", "Tempo: {n} × {m} min at {p} %.",
                            n=n, m=work // 60, p=pct),
                "sweetspot": tr("Sweet spot: {n} × {m} min a {p} %.",
                                "Sweet spot: {n} × {m} min at {p} %.", n=n, m=work // 60, p=pct),
                "threshold": tr("Limiar: {n} × {m} min a {p} %.",
                                "Threshold: {n} × {m} min at {p} %.", n=n, m=work // 60, p=pct),
                "vo2max": tr("VO2máx: {n} × {m} min a {p} %.", "VO2max: {n} × {m} min at {p} %.",
                             n=n, m=work // 60, p=pct),
                "anaerobic": tr("Anaeróbio: {n} × {m} s a {p} %.",
                                "Anaerobic: {n} × {m} s at {p} %.", n=n, m=work, p=pct)}[focus]
    if focus != "recovery":
        blocks.append(B("cooldown", "time", cool, 60, 45, tr("Retorno à calma", "Cool-down")))
    name = tr("Treinador · {f} {m} min", "Coach · {f} {m} min", f=focus_name(focus),
              m=int(sum(b.dur for b in blocks) // 60))
    return {"name": name, "goal": goal, "blocks": blocks, "note": note, "focus": focus}


def review_blocks(db: Database, sport: str, blocks: list, today: date | None = None,
                  snap: dict | None = None, with_longevity: bool = True) -> Advice:
    """O feedback a um treino construído, à luz da forma atual do atleta."""
    a = Advice(tr("Feedback do Treinador", "Coach feedback"), tone="good")
    if not blocks:
        a.tone = "info"
        a.verdict = tr("O treino ainda não tem blocos.", "The workout has no blocks yet.")
        return a
    s = snap or snapshot(db, today)
    ctx = it.Context.from_db(db, sport)
    est = bl.estimate(blocks, ctx)
    tss, secs, if_ = est["tss"], est["seconds"], est["if"]
    zones = est["zones"]
    hard_min = sum(zones[4:]) / 60.0          # Z5 e acima
    thr_min = zones[3] / 60.0
    issues: list[str] = []
    tips: list[str] = []
    data = {"treino": {"desporto": sport, "duracao_min": round(secs / 60), "carga": round(tss),
                       "intensidade": round(if_, 2),
                       "min_por_zona": [round(z / 60, 1) for z in zones]},
            "atleta": snapshot_facts(s)}
    a.add(tr("O treino", "The workout"),
          tr("{t}, carga {l:.0f}, intensidade {i:.2f}; {h:.0f} min em Z5 ou acima e {m:.0f} min "
             "em Z4.", "{t}, load {l:.0f}, intensity {i:.2f}; {h:.0f} min in Z5 or above and "
             "{m:.0f} min in Z4.", t=hms(secs), l=tss, i=if_, h=hard_min, m=thr_min))
    heavy, very = _opt(db, "coach_heavy_factor"), _opt(db, "coach_very_heavy_factor")
    scale = None
    if not s["has_history"]:
        a.tone = "info"
        if tss > 60 or hard_min > 8:
            a.worst("warn")
            issues.append(tr("sem histórico recente, este treino é muito para começar",
                             "with no recent history, this is a lot to start with"))
            tips.append(tr("começa por 30–45 min fáceis durante uma ou duas semanas",
                           "start with 30–45 easy minutes for a week or two"))
    else:
        typical = s["typical_load"]
        a.add(tr("A tua forma", "Your form"), form_text(s) + " " + tr(
            "Carga típica das tuas sessões: {t:.0f}.", "Typical load of your sessions: {t:.0f}.",
            t=typical))
        ratio = tss / typical if typical else 0.0
        data["treino"]["vezes_carga_tipica"] = round(ratio, 2)
        if typical and ratio >= very:
            a.worst("bad")
            issues.append(tr("{r:.1f}× a tua carga habitual: pesado demais para a forma atual",
                             "{r:.1f}× your usual load: too heavy for current fitness",
                             r=ratio))
            scale = heavy * typical / tss
        elif typical and ratio >= heavy:
            a.worst("warn")
            issues.append(tr("{r:.1f}× a tua carga habitual: é um dia pesado",
                             "{r:.1f}× your usual load: this is a hard day", r=ratio))
        k_atl, k_ctl = stats.K_ATL, stats.K_CTL
        ctl2 = s["ctl"] + (tss - s["ctl"]) * k_ctl
        atl2 = s["atl"] + (tss - s["atl"]) * k_atl
        tsb2 = ctl2 - atl2
        data["treino"]["tsb_depois"] = round(tsb2, 1)
        if tsb2 <= _opt(db, "coach_overload_tsb"):
            a.worst("bad" if s["tsb"] <= _opt(db, "coach_tired_tsb") else "warn")
            issues.append(tr("deixa-te em sobrecarga (TSB {t:+.0f} no dia seguinte)",
                             "it leaves you overloaded (TSB {t:+.0f} the next day)", t=tsb2))
        if s["tsb"] <= _opt(db, "coach_tired_tsb") and if_ >= 0.85:
            a.worst("warn")
            issues.append(tr("estás cansado (TSB {t:+.0f}) para um treino desta intensidade",
                             "you are tired (TSB {t:+.0f}) for a workout this intense",
                             t=s["tsb"]))
            tips.append(tr("faz hoje uma versão em Z2 e guarda este para quando o TSB subir",
                           "do a Z2 version today and keep this one for when TSB rises"))
        longest = max(s["longest_s"].get(sport, 0.0), 0.0)
        if longest and secs > 1.5 * longest:
            a.worst("warn")
            issues.append(tr("dura {t}, e o teu treino mais longo recente foi de {l}",
                             "it lasts {t}, and your longest recent session was {l}",
                             t=hms(secs), l=hms(longest)))
            tips.append(tr("sobe a duração dos longos 10–15 % de cada vez",
                           "raise long-session duration 10–15 % at a time"))
        if len(s["recovery_flags"]) >= 2 and if_ >= 0.8:
            a.worst("warn")
            issues.append(tr("a recuperação não está boa ({f})", "recovery is not good ({f})",
                             f=", ".join(s["recovery_flags"])))
    if hard_min > _opt(db, "coach_z5_max_min"):
        a.worst("warn")
        issues.append(tr("{m:.0f} min em Z5 ou acima é muito para uma sessão",
                         "{m:.0f} min in Z5 or above is a lot for one session", m=hard_min))
        tips.append(tr("fica pelos 15–25 min de trabalho em Z5", "stay at 15–25 min of Z5 work"))
    if thr_min > _opt(db, "coach_z4_max_min"):
        a.worst("warn")
        issues.append(tr("{m:.0f} min em Z4 passa do que costuma render (40–60 min)",
                         "{m:.0f} min in Z4 exceeds what usually pays (40–60 min)", m=thr_min))
    first = blocks[0]
    if first.lo is not None and first.mid() > 80 and secs > 900:
        a.worst("warn")
        issues.append(tr("começa forte sem aquecimento", "it starts hard with no warm-up"))
        tips.append(tr("junta 10 min de aquecimento progressivo", "add a 10 min progressive "
                       "warm-up"))
    work_blocks = [b for b in blocks if b.lo is not None and b.mid() >= 105]
    rests_ok = True
    for i, b in enumerate(blocks[:-1]):
        nxt = blocks[i + 1]
        if b.lo is not None and b.mid() >= 105 and nxt.lo is not None and nxt.mid() >= 105:
            rests_ok = False
    if work_blocks and not rests_ok:
        a.worst("warn")
        issues.append(tr("há blocos muito fortes seguidos, sem recuperação entre eles",
                         "there are very hard blocks back to back, with no recovery between"))
    if scale is not None and scale < 0.95:
        work_s = sum(bl.block_seconds(b, ctx) for b in blocks if b.kind == "active")
        tips.insert(0, tr("uma versão para hoje: corta o trabalho para cerca de {m:.0f} min "
                          "(em vez de {w:.0f}) ou baixa os alvos 5–8 %",
                          "a version for today: cut the work to about {m:.0f} min (instead of "
                          "{w:.0f}) or lower targets 5–8 %", m=work_s * scale / 60,
                          w=work_s / 60))
        data["treino"]["escala_sugerida"] = round(scale, 2)
    if issues:
        a.add(tr("O que vejo", "What I see"), "; ".join(issues).capitalize() + ".")
    if tips:
        a.add(tr("Sugestão", "Suggestion"), "; ".join(tips).capitalize() + ".")
    if with_longevity:
        try:
            imp = lg.impact_text(lg.impact_of(db, lg.blocks_mins(blocks, sport), sport=sport))
            if imp:
                a.add(tr("Longevidade", "Longevity"), imp)
        except Exception:
            pass
    a.verdict = {"good": tr("Bem ajustado à tua forma atual.", "Well matched to your current "
                            "fitness."),
                 "info": tr("Parece equilibrado; ainda não tenho histórico teu para comparar.",
                            "Looks balanced; I have no history of yours to compare yet."),
                 "warn": tr("Dá para fazer, com atenção: {x}.", "Doable, with care: {x}.",
                            x=issues[0] if issues else ""),
                 "bad": tr("Pesado demais para agora: {x}.", "Too heavy for now: {x}.",
                           x=issues[0] if issues else "")}[a.tone]
    a.data = data
    return a


def lighter_blocks(blocks: list, scale: float) -> list:
    """Uma versão mais leve: tira repetições do fim do trabalho até a carga descer para
    `scale` (0–1) da original; se só houver um bloco de trabalho, encurta-o."""
    import copy
    out = copy.deepcopy(blocks)
    scale = max(0.3, min(1.0, scale))
    ctx_load = lambda bs: sum(b.dur * ((b.mid() if b.lo is not None else 50.0) / 100) ** 2  # noqa: E731
                              for b in bs if b.dur_type == "time")
    goal = ctx_load(out) * scale
    guard = 0
    while ctx_load(out) > goal and guard < 200:
        guard += 1
        idx = [i for i, b in enumerate(out) if b.kind == "active" and b.lo is not None]
        if len(idx) > 1:
            i = idx[-1]
            del out[i]
            if i - 1 >= 0 and i - 1 < len(out) and out[i - 1].kind == "rest":
                del out[i - 1]
        elif idx:
            b = out[idx[0]]
            if b.dur <= 300:
                break
            b.dur = max(300.0, round(b.dur * 0.9 / 60) * 60)
        else:
            break
    return out
