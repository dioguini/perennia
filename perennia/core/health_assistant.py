"""O Assistente de saúde: uma leitura geral do que a Perennia sabe sobre a tua saúde.

Conhece as análises clínicas, a pressão arterial, o diário (sono, FC em repouso, HRV, peso,
hábitos), os separadores que criaste na Saúde (as notas) e alguns sinais do treino (FC, carga).
Dá uma **avaliação geral** e olha para **componentes específicas** (análises, pressão arterial,
recuperação e sono, corpo, hábitos, treino).

Aqui está a versão **offline por regras**: compara o período recente com o de base (as duas
janelas são opções), aplica limiares que podes mudar nas Definições → Avançado, e escreve o que
vê. Não usa rede nem IA. O pedido para um LLM local ou para um agente online prepara-se em
`advisor.py` com os mesmos factos (`Advice.data`).

**Não é um médico e não faz diagnósticos.** Aponta tendências e perguntas para levares à
consulta; o que existe para o médico (comentários nas análises) continua como estava.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import bp, health, health_tabs, options
from .advice import Advice
from .db import Database
from .i18n import tr

COMPONENTS = ("overview", "labs", "bp", "recovery", "body", "habits", "training", "notes")


def component_name(c: str) -> str:
    return {"overview": tr("Avaliação geral", "Overall assessment"),
            "labs": tr("Análises clínicas", "Lab results"),
            "bp": tr("Pressão arterial", "Blood pressure"),
            "recovery": tr("Recuperação e sono", "Recovery and sleep"),
            "body": tr("Corpo (peso, cintura)", "Body (weight, waist)"),
            "habits": tr("Hábitos diários", "Daily habits"),
            "training": tr("Sinais do treino", "Training signals"),
            "notes": tr("Os teus separadores", "Your tabs")}.get(c, c)


def disclaimer() -> str:
    return tr("Isto é uma leitura dos teus registos, não um diagnóstico. Para decisões de saúde, "
              "fala com o teu médico.",
              "This is a reading of your records, not a diagnosis. For health decisions, talk "
              "to your doctor.")


def _opt(db: Database, key: str) -> float:
    return float(options.get(db, key))


def _min_days(db: Database) -> int:
    return int(options.get(db, "health_min_days"))


# ------------------------------------------------------------------ sinais do diário


def metric_values(db: Database, key: str, start: date, end: date) -> list[float]:
    m = health.metric_by_key(db, key)
    if m is None:
        return []
    return [r["num"] for r in db.conn.execute(
        "SELECT num FROM daily_values WHERE metric_id = ? AND day >= ? AND day <= ?"
        " AND num IS NOT NULL ORDER BY day", (m["id"], start.isoformat(), end.isoformat()))]


def windows(db: Database, key: str, today: date | None = None) -> dict:
    """A métrica no período recente e no de base (o de base acaba onde o recente começa).
    {"recent": média|None, "n": dias, "base": média|None, "base_n": dias, "last": valor|None}"""
    today = today or date.today()
    rd, bd = int(_opt(db, "health_window_days")), int(_opt(db, "health_baseline_days"))
    r0 = today - timedelta(days=rd - 1)
    recent = metric_values(db, key, r0, today)
    base = metric_values(db, key, r0 - timedelta(days=bd), r0 - timedelta(days=1))
    mean = lambda v: sum(v) / len(v) if v else None             # noqa: E731
    return {"recent": mean(recent), "n": len(recent), "base": mean(base), "base_n": len(base),
            "last": recent[-1] if recent else None, "sum": sum(recent), "days": rd}


def _n(v: float | None, dec: int = 0) -> str:
    return "—" if v is None else f"{v:.{dec}f}"


# ------------------------------------------------------------------ componentes


def recovery(db: Database, today: date | None = None) -> Advice:
    a = Advice(component_name("recovery"), tone="good")
    data: dict = {}
    parts, flags = [], []
    sl = windows(db, "sleep_hours", today)
    if sl["n"] >= _min_days(db):
        data["sono_h"] = round(sl["recent"], 2)
        need = _opt(db, "health_sleep_min_h")
        parts.append(tr("Sono: média de {v} h em {n} noites.", "Sleep: mean of {v} h over {n} "
                        "nights.", v=_n(sl["recent"], 1), n=sl["n"]))
        if sl["recent"] < need:
            flags.append(tr("dormes menos do que {h:g} h", "you sleep less than {h:g} h", h=need))
            a.worst("warn")
    rhr = windows(db, "rhr", today)
    if rhr["n"] >= _min_days(db):
        data["fc_repouso"] = round(rhr["recent"], 1)
        t = tr("FC em repouso: {v} bpm", "Resting HR: {v} bpm", v=_n(rhr["recent"]))
        if rhr["base_n"] >= _min_days(db):
            diff = rhr["recent"] - rhr["base"]
            data["fc_repouso_base"] = round(rhr["base"], 1)
            t += tr(" ({d:+.0f} face à base de {b}).", " ({d:+.0f} vs the baseline of {b}).",
                    d=diff, b=_n(rhr["base"]))
            if diff >= _opt(db, "health_rhr_rise_bpm"):
                flags.append(tr("a FC em repouso subiu", "resting HR went up"))
                a.worst("warn")
        else:
            t += "."
        parts.append(t)
    hrv = windows(db, "hrv_rmssd", today)
    if hrv["n"] >= _min_days(db):
        data["hrv_rmssd"] = round(hrv["recent"], 1)
        t = tr("HRV (rMSSD): {v} ms", "HRV (rMSSD): {v} ms", v=_n(hrv["recent"]))
        if hrv["base_n"] >= _min_days(db) and hrv["base"]:
            pct = (hrv["recent"] - hrv["base"]) / hrv["base"] * 100
            data["hrv_base"] = round(hrv["base"], 1)
            t += tr(" ({p:+.0f} % face à base).", " ({p:+.0f} % vs the baseline).", p=pct)
            if pct <= -_opt(db, "health_hrv_drop_pct"):
                flags.append(tr("a HRV desceu", "HRV dropped"))
                a.worst("warn")
        else:
            t += "."
        parts.append(t)
    for key, label in (("soreness", tr("Dores musculares", "Muscle soreness")),
                       ("stress", "Stress"), ("energy", tr("Energia", "Energy"))):
        w = windows(db, key, today)
        if w["n"] >= _min_days(db):
            data[key] = round(w["recent"], 1)
            parts.append(f"{label}: {_n(w['recent'], 1)}/5.")
            if key in ("soreness", "stress") and w["recent"] >= 4:
                flags.append(label.lower() + tr(" em alta", " running high"))
                a.worst("warn")
            if key == "energy" and w["recent"] <= 2:
                flags.append(tr("pouca energia", "low energy"))
                a.worst("warn")
    if not parts:
        a.tone = "info"
        a.verdict = tr("Sem registos recentes de sono, FC em repouso ou HRV.",
                       "No recent sleep, resting HR or HRV records.")
        a.add(tr("O que falta", "What is missing"),
              tr("Preenche o diário alguns dias (ou importa do Garmin / HRV4Training) para eu "
                 "poder comparar com a tua base.", "Fill in the daily log for a few days (or "
                 "import from Garmin / HRV4Training) so I can compare with your baseline."))
    else:
        a.add(tr("O que vejo", "What I see"), " ".join(parts))
        if len(flags) >= 2:
            a.verdict = tr("Vários sinais de recuperação incompleta: {f}.",
                           "Several signs of incomplete recovery: {f}.", f=", ".join(flags))
            a.add(tr("Sugestão", "Suggestion"),
                  tr("Dois ou três dias mais leves, deitar mais cedo e ver se os valores voltam "
                     "à base. Se a FC em repouso continuar alta mais de uma semana ou vier com "
                     "febre ou mal-estar, fala com o médico.",
                     "Two or three lighter days, earlier bedtime, and see if the values return "
                     "to baseline. If resting HR stays high for over a week or comes with fever "
                     "or malaise, see your doctor."))
        elif flags:
            a.verdict = tr("Um sinal a vigiar: {f}.", "One sign to watch: {f}.", f=flags[0])
        else:
            a.verdict = tr("Recuperação dentro do teu normal.", "Recovery within your normal.")
    a.data = {"recuperacao": data, "avisos": flags}
    return a


def blood_pressure(db: Database, today: date | None = None) -> Advice:
    a = Advice(component_name("bp"), tone="good")
    rd, bd = int(_opt(db, "health_window_days")), int(_opt(db, "health_baseline_days"))
    recent = bp.window_mean(db, rd, today)
    base = bp.window_mean(db, bd, today, offset_days=rd)
    if recent is None:
        a.tone = "info"
        a.verdict = tr("Sem medições nos últimos {n} dias.", "No readings in the last {n} days.",
                       n=rd)
        a.add(tr("Como medir", "How to measure"),
              tr("Sentado, 5 minutos em repouso, braço apoiado à altura do coração; 2 a 3 "
                 "medições seguidas com 1 minuto de intervalo, de manhã e à noite. A Perennia "
                 "faz a média de cada período e a do dia.",
                 "Seated, 5 minutes at rest, arm supported at heart level; 2 to 3 readings one "
                 "minute apart, morning and night. Perennia averages each period and the day."))
        return a
    cat = bp.classify(db, recent["sys"], recent["dia"])
    a.tone = bp.category_tone(cat)
    a.verdict = tr("Média de {d} dia(s): {v} — {c}.", "{d}-day mean: {v} — {c}.",
                   d=recent["days"], v=bp.fmt_full(recent), c=bp.category_name(cat))
    data = {"media_recente": [round(recent["sys"]), round(recent["dia"])],
            "dias": recent["days"], "classe": cat}
    parts = []
    for key, name in bp.periods(db):
        m = bp.window_mean(db, rd, today, period=key)
        if m:
            parts.append(f"{name}: {bp.fmt(m)}")
            data[f"periodo_{key}"] = [round(m["sys"]), round(m["dia"])]
    if parts:
        a.add(tr("Por período", "By period"), " · ".join(parts) + ".")
    if base is not None:
        ds, dd = recent["sys"] - base["sys"], recent["dia"] - base["dia"]
        data["media_base"] = [round(base["sys"]), round(base["dia"])]
        a.add(tr("Tendência", "Trend"),
              tr("Face aos {n} dias anteriores ({b}): máxima {s:+.0f}, mínima {d:+.0f} mmHg.",
                 "Against the previous {n} days ({b}): systolic {s:+.0f}, diastolic {d:+.0f} "
                 "mmHg.", n=bd, b=bp.fmt(base), s=ds, d=dd))
    # uma medição isolada muito alta conta, mesmo que a média não o seja
    start = ((today or date.today()) - timedelta(days=rd - 1)).isoformat()
    peaks = [r for r in db.conn.execute(
        "SELECT day, sys, dia FROM bp_readings WHERE day >= ? ORDER BY day DESC", (start,))
        if bp.classify(db, r["sys"], r["dia"]) == "crisis"]
    if peaks and cat != "crisis":
        p = peaks[0]
        a.worst("bad")
        data["medicoes_muito_altas"] = len(peaks)
        a.add(tr("Importante", "Important"),
              tr("Há {n} medição(ões) muito alta(s) neste período (a mais recente: {s:.0f}/"
                 "{d:.0f} em {day}). Se voltar a acontecer depois de 5 minutos em repouso, "
                 "contacta um médico. Com dor no peito, falta de ar, dor de cabeça forte ou "
                 "alterações da visão: liga 112.",
                 "There are {n} very high reading(s) in this period (most recent: {s:.0f}/"
                 "{d:.0f} on {day}). If it happens again after 5 minutes at rest, contact a "
                 "doctor. With chest pain, shortness of breath, severe headache or vision "
                 "changes: call emergency services.", n=len(peaks), s=p["sys"], d=p["dia"],
                 day=p["day"]))
    if cat == "crisis":
        a.add(tr("Importante", "Important"),
              tr("Valores muito altos. Repete a medição depois de 5 minutos em repouso; se se "
                 "mantiverem, contacta um médico hoje. Com dor no peito, falta de ar, dor de "
                 "cabeça forte ou alterações da visão: liga 112.",
                 "Very high values. Repeat the reading after 5 minutes at rest; if they hold, "
                 "contact a doctor today. With chest pain, shortness of breath, severe headache "
                 "or vision changes: call emergency services."))
    elif cat == "high":
        a.add(tr("Sugestão", "Suggestion"),
              tr("A média está acima do limiar ({s}/{d}). Continua a medir de manhã e à noite "
                 "durante uma semana e leva o registo ao médico (podes exportá-lo na AdHoc "
                 "Analysis). Sal, álcool, sono e stress mexem nestes valores.",
                 "The mean is above the threshold ({s}/{d}). Keep measuring morning and night "
                 "for a week and take the record to your doctor (you can export it in AdHoc "
                 "Analysis). Salt, alcohol, sleep and stress move these values.",
                 s=int(_opt(db, "bp_high_sys")), d=int(_opt(db, "bp_high_dia"))))
    elif cat == "low":
        a.add(tr("Sugestão", "Suggestion"),
              tr("Valores baixos são comuns em quem treina resistência. Se tiveres tonturas ou "
                 "desmaios, fala com o médico.",
                 "Low values are common in endurance-trained people. If you get dizzy or "
                 "faint, see your doctor."))
    if recent["days"] < _min_days(db):
        a.add(tr("Poucos dados", "Little data"),
              tr("Só {n} dia(s) com medições: a média ainda diz pouco.",
                 "Only {n} day(s) with readings: the mean says little yet.", n=recent["days"]))
    a.data = {"pressao_arterial": data}
    return a


def labs(db: Database, report_id: int | None = None) -> Advice:
    from . import labs as labs_mod
    a = Advice(component_name("labs"), tone="good")
    labs_mod.ensure(db)
    reps = health.lab_reports(db)
    if not reps:
        a.tone = "info"
        a.verdict = tr("Ainda não há análises registadas.", "No lab results recorded yet.")
        return a
    rep = next((r for r in reps if r["id"] == report_id), None) or reps[0]
    res = health.lab_results(db, rep["id"])
    out = [x for x in res if health.flag(x)]
    a.title = component_name("labs") + f" · {rep['done_on']}"
    facts = []
    lines = []
    for x in out:
        prev = labs_mod.previous_values(db, x["marker"], rep["done_on"], 3)
        was_out = [p for p in prev if health.flag(p)]
        arrow = "▲" if health.flag(x) == "high" else "▼"
        ref = [x.get("ref_low"), x.get("ref_high")]
        t = f"{x['marker']} {arrow} {labs_mod.value_text(x)} {x.get('unit') or ''}".strip()
        if prev:
            if len(was_out) == len(prev):
                t += tr(" (já estava fora nas {n} anteriores)", " (already out in the previous "
                        "{n})", n=len(prev))
            elif not was_out:
                t += tr(" (novo: antes estava dentro)", " (new: it was in range before)")
        lines.append(t)
        facts.append({"marcador": x["marker"], "valor": x.get("value"),
                      "unidade": x.get("unit"), "ref": ref, "estado": health.flag(x),
                      "anteriores": [p.get("value") for p in prev]})
    # o que se mexeu muito, mesmo dentro do intervalo
    moved = []
    for x in res:
        if health.flag(x) or x.get("value") is None:
            continue
        prev = labs_mod.previous_values(db, x["marker"], rep["done_on"], 1)
        lo, hi = x.get("ref_low"), x.get("ref_high")
        if prev and prev[0].get("value") is not None and lo is not None and hi is not None \
                and hi > lo:
            shift = (x["value"] - prev[0]["value"]) / (hi - lo)
            if abs(shift) >= 0.4:
                moved.append(f"{x['marker']} {'↑' if shift > 0 else '↓'}")
    if out:
        a.tone = "warn"
        a.verdict = tr("{n} de {t} resultados fora do intervalo de referência.",
                       "{n} of {t} results outside the reference range.", n=len(out), t=len(res))
        a.add(tr("Fora do intervalo", "Out of range"), "; ".join(lines) + ".")
        a.add(tr("Perguntas para o médico", "Questions for the doctor"),
              tr("Leva esta lista à consulta e pergunta: o que significa cada valor no meu "
                 "caso? É para repetir? Há relação com o treino, a alimentação ou a medicação?",
                 "Take this list to your appointment and ask: what does each value mean for "
                 "me? Should it be repeated? Is it related to training, food or medication?"))
    else:
        a.verdict = tr("Os {t} resultados com referência estão dentro do intervalo.",
                       "All {t} results with a reference are in range.", t=len(res))
    if moved:
        a.add(tr("Dentro do intervalo, mas a mexer", "In range, but moving"),
              ", ".join(moved[:8]) + tr(" — vale a pena seguir na próxima colheita.",
                                         " — worth following in the next collection."))
    if rep.get("doctor_feedback"):
        a.add(tr("O que o médico disse", "What the doctor said"), rep["doctor_feedback"])
    try:
        age_days = (date.today() - date.fromisoformat(str(rep["done_on"])[:10])).days
        if age_days > 365:
            a.add(tr("Data", "Date"),
                  tr("Esta colheita tem mais de um ano ({d} dias).",
                     "This collection is over a year old ({d} days).", d=age_days))
    except ValueError:
        pass
    a.data = {"analises": {"data": rep["done_on"], "resultados": len(res),
                           "fora_do_intervalo": facts, "a_mexer": moved[:8]}}
    return a


def body(db: Database, today: date | None = None) -> Advice:
    a = Advice(component_name("body"), tone="good")
    data, parts = {}, []
    w = windows(db, "weight", today)
    if w["n"]:
        data["peso_kg"] = round(w["recent"], 1)
        t = tr("Peso: {v} kg", "Weight: {v} kg", v=_n(w["recent"], 1))
        if w["base_n"] and w["base"]:
            pct = (w["recent"] - w["base"]) / w["base"] * 100
            data["peso_base_kg"] = round(w["base"], 1)
            t += tr(" ({p:+.1f} % face à base de {b} kg).", " ({p:+.1f} % vs the baseline of "
                    "{b} kg).", p=pct, b=_n(w["base"], 1))
            if abs(pct) >= _opt(db, "health_weight_change_pct"):
                a.worst("warn")
                a.verdict = tr("O peso mudou {p:+.1f} % face à base.",
                               "Weight changed {p:+.1f} % vs the baseline.", p=pct)
        else:
            t += "."
        parts.append(t)
    c = windows(db, "waist", today)
    if c["n"]:
        data["cintura_cm"] = round(c["recent"], 1)
        parts.append(tr("Cintura: {v} cm.", "Waist: {v} cm.", v=_n(c["recent"], 1)))
        try:
            height = float(db.get("athlete_height_cm", 0) or 0)
        except (TypeError, ValueError):
            height = 0.0
        if height > 0:
            ratio = c["recent"] / height
            data["cintura_altura"] = round(ratio, 2)
            parts.append(tr("Cintura/altura: {r:.2f} (a referência habitual é abaixo de 0,50).",
                            "Waist/height: {r:.2f} (the usual reference is below 0.50).",
                            r=ratio))
    if not parts:
        a.tone = "info"
        a.verdict = tr("Sem registos recentes de peso ou cintura.",
                       "No recent weight or waist records.")
    else:
        a.add(tr("O que vejo", "What I see"), " ".join(parts))
        if not a.verdict:
            a.verdict = tr("Peso estável face à tua base.", "Weight stable vs your baseline.")
    a.data = {"corpo": data}
    return a


def habits(db: Database, today: date | None = None) -> Advice:
    a = Advice(component_name("habits"), tone="good")
    data, parts, flags = {}, [], []
    al = windows(db, "alcohol", today)
    if al["n"]:
        per_week = al["sum"] / max(1, al["days"]) * 7
        data["alcool_por_semana"] = round(per_week, 1)
        parts.append(tr("Álcool: cerca de {v} bebidas por semana.", "Alcohol: about {v} drinks "
                        "a week.", v=_n(per_week, 1)))
        if per_week > _opt(db, "health_alcohol_week_max"):
            flags.append(tr("álcool acima do teu máximo semanal",
                            "alcohol above your weekly maximum"))
    for key, label in (("sweets_lunch", tr("doces ao almoço", "sweets at lunch")),
                       ("sweets_dinner", tr("doces ao jantar", "sweets at dinner")),
                       ("ate_out", tr("refeições fora", "meals out"))):
        w = windows(db, key, today)
        if w["n"] >= _min_days(db):
            share = w["recent"] * 100
            data[key] = round(share)
            parts.append(tr("{l}: {p:.0f} % dos dias registados.", "{l}: {p:.0f} % of logged "
                            "days.", l=label.capitalize(), p=share))
            if key.startswith("sweets") and share >= 50:
                flags.append(tr("{l} em metade dos dias ou mais", "{l} on half the days or "
                                "more", l=label))
    wa = windows(db, "water", today)
    if wa["n"] >= _min_days(db):
        data["agua_l"] = round(wa["recent"], 1)
        parts.append(tr("Água: {v} L por dia.", "Water: {v} L a day.", v=_n(wa["recent"], 1)))
    st = windows(db, "steps", today)
    if st["n"] >= _min_days(db):
        data["passos"] = round(st["recent"])
        parts.append(tr("Passos: {v} por dia.", "Steps: {v} a day.", v=_n(st["recent"])))
    co = windows(db, "coffee", today)
    if co["n"] >= _min_days(db):
        data["cafes"] = round(co["recent"], 1)
        parts.append(tr("Cafés: {v} por dia.", "Coffees: {v} a day.", v=_n(co["recent"], 1)))
    if not parts:
        a.tone = "info"
        a.verdict = tr("Sem registos recentes de hábitos no diário.",
                       "No recent habit records in the daily log.")
    else:
        a.add(tr("O que vejo", "What I see"), " ".join(parts))
        if flags:
            a.tone = "warn"
            a.verdict = tr("A rever: {f}.", "To review: {f}.", f="; ".join(flags))
        else:
            a.verdict = tr("Hábitos dentro do que definiste.", "Habits within what you set.")
    a.data = {"habitos": data, "avisos": flags}
    return a


def training(db: Database, today: date | None = None) -> Advice:
    """O que o treino diz sobre a saúde: carga, forma e a FC das sessões."""
    from . import stats
    a = Advice(component_name("training"), tone="good")
    today = today or date.today()
    data, parts = {}, []
    now = stats.fitness_now(db, today=today)
    if now:
        data.update(ctl=round(now["ctl"], 1), atl=round(now["atl"], 1), tsb=round(now["tsb"], 1))
        parts.append(tr("Carga crónica (CTL) {c:.0f}, fadiga (ATL) {a:.0f}, forma (TSB) "
                        "{t:+.0f}.", "Chronic load (CTL) {c:.0f}, fatigue (ATL) {a:.0f}, form "
                        "(TSB) {t:+.0f}.", c=now["ctl"], a=now["atl"], t=now["tsb"]))
        if now["tsb"] <= _opt(db, "coach_overload_tsb"):
            a.worst("warn")
            a.verdict = tr("Fadiga acumulada alta: o corpo está a pedir descanso.",
                           "High accumulated fatigue: the body is asking for rest.")
    st = stats.streaks(db, today)
    if st.get("days"):
        data["dias_seguidos"] = st["days"]
        if st["days"] >= _opt(db, "health_streak_rest_days"):
            parts.append(tr("{n} dias seguidos a treinar: põe um dia de descanso.",
                            "{n} training days in a row: add a rest day.", n=st["days"]))
            a.worst("warn")
    ath = db.athlete()
    since = (today - timedelta(days=int(_opt(db, "coach_history_days")))).isoformat()
    try:
        row = db.conn.execute("SELECT MAX(max_hr) AS m, AVG(avg_hr) AS a, COUNT(*) AS n FROM"
                              " rides WHERE status = 'completed' AND started_at >= ?",
                              (since,)).fetchone()
    except Exception:
        row = None
    if row and row["n"] and row["m"]:
        data["fc_max_vista"] = int(row["m"])
        parts.append(tr("FC máxima vista nas sessões de ciclismo recentes: {m} bpm (média "
                        "{a:.0f}).", "Highest HR seen in recent cycling sessions: {m} bpm (mean "
                        "{a:.0f}).", m=int(row["m"]), a=row["a"] or 0))
        if ath.max_hr and row["m"] > ath.max_hr + 3:
            parts.append(tr("Passou a FC máxima do teu perfil ({p}): atualiza-a nas Definições.",
                            "It exceeded your profile's max HR ({p}): update it in Settings.",
                            p=ath.max_hr))
    if not parts:
        a.tone = "info"
        a.verdict = tr("Ainda sem sessões suficientes para ler sinais do treino.",
                       "Not enough sessions yet to read training signals.")
    else:
        a.add(tr("O que vejo", "What I see"), " ".join(parts))
        if not a.verdict:
            a.verdict = tr("Carga de treino sem sinais de alarme.",
                           "Training load without warning signs.")
    a.data = {"treino": data}
    return a


def notes(db: Database) -> Advice:
    a = Advice(component_name("notes"), tone="info")
    tabs = health_tabs.tabs(db)
    if not tabs:
        a.verdict = tr("Ainda não criaste separadores na Saúde.",
                       "You have not created Health tabs yet.")
        return a
    data = {}
    for t in tabs:
        ns = health_tabs.notes(db, t["key"], limit=5)
        if ns:
            a.add(t["name"], " · ".join(
                f"{n['day']}: {n['title'] or (n['text'] or '')[:60]}" for n in ns))
            data[t["name"]] = [{"dia": n["day"], "titulo": n["title"], "texto": n["text"]}
                               for n in ns]
        else:
            a.add(t["name"], tr("sem notas", "no notes"))
    a.verdict = tr("{n} separador(es) teus; as notas mais recentes de cada um:",
                   "{n} tab(s) of yours; the most recent notes of each:", n=len(tabs))
    a.data = {"separadores": data}
    return a


PARTS = {"labs": labs, "bp": blood_pressure, "recovery": recovery, "body": body,
         "habits": habits, "training": training, "notes": notes}


def component(db: Database, name: str, today: date | None = None, **kw) -> Advice:
    if name == "overview":
        return overview(db, today)
    fn = PARTS[name]
    if name == "labs":
        a = fn(db, kw.get("report_id"))
    elif name == "notes":
        a = fn(db)
    else:
        a = fn(db, today)
    a.disclaimer = disclaimer()
    return a


def overview(db: Database, today: date | None = None) -> Advice:
    """A avaliação geral: uma linha por componente e o que merece atenção primeiro."""
    a = Advice(component_name("overview"), tone="good")
    data: dict = {}
    attention, missing = [], []
    for name in ("labs", "bp", "recovery", "body", "habits", "training"):
        part = component(db, name, today)
        a.add(component_name(name), part.verdict or tr("sem dados", "no data"))
        data.update(part.data)
        if part.tone in ("warn", "bad"):
            attention.append((part.tone, component_name(name)))
            a.worst(part.tone)
        elif part.tone == "info":
            missing.append(component_name(name))
    tabs = health_tabs.tabs(db)
    if tabs:
        a.add(component_name("notes"), ", ".join(
            tr("{n} ({k} notas)", "{n} ({k} notes)", n=t["name"], k=t["n"]) for t in tabs) + ".")
        data.update(notes(db).data)
    if any(t == "bad" for t, _ in attention):
        a.verdict = tr("Há algo a tratar já: {x}.", "Something needs attention now: {x}.",
                       x=", ".join(n for t, n in attention if t == "bad"))
    elif attention:
        a.verdict = tr("No geral bem, com {n} ponto(s) a vigiar: {x}.",
                       "Broadly fine, with {n} point(s) to watch: {x}.", n=len(attention),
                       x=", ".join(n for _t, n in attention))
    elif len(missing) >= 5:
        a.tone = "info"
        a.verdict = tr("Ainda sei pouco: regista o diário, a pressão arterial e as análises.",
                       "I know little yet: log the daily log, blood pressure and lab results.")
    else:
        a.verdict = tr("Sem sinais de alarme nos teus registos.",
                       "No warning signs in your records.")
    if missing and len(missing) < 5:
        a.add(tr("Sem dados", "No data"), ", ".join(missing) + ".")
    a.questions = [tr("Há algum sintoma ou preocupação que queiras juntar? Escreve-o numa nota "
                      "(separador próprio ou nota do dia) para ficar no contexto.",
                      "Any symptom or concern to add? Write it in a note (own tab or day note) "
                      "so it stays in context.")]
    a.data = data
    a.disclaimer = disclaimer()
    return a
