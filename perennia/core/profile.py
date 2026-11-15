"""O teu perfil em cada desporto.

* **Ciclismo** — que tipo de ciclista és (sprinter, puncheur, trepador, rolador /
  contrarrelogista ou completo), pela tua curva de potência: os melhores W/kg em 5 s, 1 min,
  5 min e ao limiar, cada um posto numa escala de 0 a 100 entre «sem treino» e «classe
  mundial» (uma aproximação da tabela de perfil de potência de Coggan). O ponto forte dá o
  tipo; o mais fraco diz o que treinar.
* **Ginásio** — o teu perfil de força: força máxima, força relativa (com o peso do corpo),
  **força de mãos**, **tendões**, **explosividade**, **mobilidade**, tronco e condicionamento.
  Cada capacidade junta o que **mediste** (1RM estimada a dividir pelo peso, repetições,
  tempos) com o que **treinaste** nas últimas semanas (séries ou minutos por semana). O que
  não tem dados aparece como «por medir», não como fraco.
* **Remo, corrida e natação** — um perfil simples de velocidade contra resistência, pelas tuas
  melhores sessões curtas, médias e longas.

Isto é o perfil **do desporto**. As capacidades para a vida (aeróbia, força, VO2máx,
mobilidade, estabilidade…) continuam no menu **Longevidade**.

Os níveis de referência («bom nível» = 100 pontos) e as janelas são opções (Definições →
Avançado → Perfil por desporto).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

from . import options
from .db import Database
from .i18n import tr

# W/kg: (sem treino, classe mundial) — aproximação da tabela de perfil de potência de Coggan
POWER_TABLE = {
    "male": {5: (10.2, 24.0), 60: (5.6, 11.5), 300: (2.3, 7.6), "ft": (1.9, 6.4)},
    "female": {5: (8.2, 19.4), 60: (4.6, 9.3), 300: (1.9, 6.6), "ft": (1.5, 5.7)},
}
FT_FROM_20MIN = 0.95                  # o limiar estima-se a 95 % do melhor de 20 minutos
CYCLING_KEYS = (5, 60, 300, "ft")
LEVELS = ((20, ("a começar", "starting out")), (40, ("moderado", "moderate")),
          (60, ("bom", "good")), (80, ("muito bom", "very good")),
          (101, ("excelente", "excellent")))
GYM_DIMS = ("max_strength", "relative", "grip", "tendons", "power", "mobility", "core",
            "conditioning")
MIN_BALANCE_SETS = 10                 # com menos séries do que isto não se fala de equilíbrio
ENDURANCE_BINS = ((0, 20 * 60), (20 * 60, 60 * 60), (60 * 60, 24 * 3600))


def _opt(db: Database, key: str) -> float:
    return float(options.get(db, key))


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))
                  .lower()).strip()


def level(score: float | None) -> str:
    if score is None:
        return tr("sem dados", "no data")
    for cut, (pt, en) in LEVELS:
        if score < cut:
            return tr(pt, en)
    return tr(*LEVELS[-1][1])


def bar(score: float | None, width: int = 10) -> str:
    if score is None:
        return "·" * width
    n = max(0, min(width, round(score / 100.0 * width)))
    return "█" * n + "░" * (width - n)


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


# ====================================================================== ciclismo


def duration_name(k) -> str:
    return {5: tr("Sprint (5 s)", "Sprint (5 s)"), 60: tr("Anaeróbio (1 min)",
                                                          "Anaerobic (1 min)"),
            300: tr("VO2máx (5 min)", "VO2max (5 min)"),
            "ft": tr("Limiar (FTP)", "Threshold (FTP)")}[k]


def rider_type_name(t: str | None) -> str:
    return {"sprinter": tr("Sprinter", "Sprinter"), "puncheur": tr("Puncheur", "Puncheur"),
            "climber": tr("Trepador", "Climber"),
            "rouleur": tr("Rolador / contrarrelogista", "Rouleur / time trialist"),
            "allrounder": tr("Completo (all-rounder)", "All-rounder")}.get(
                t or "", tr("Por definir", "Undetermined"))


def rider_type_text(t: str | None) -> str:
    return {
        "sprinter": tr("A tua potência de poucos segundos destaca-se do resto: ganhas nas "
                       "chegadas e nas acelerações curtas.",
                       "Your few-second power stands out: you win sprints and short "
                       "accelerations."),
        "puncheur": tr("O teu ponto forte são os esforços de 1 a 5 minutos: ataques, rampas "
                       "curtas e duras, fugas no final.",
                       "Your strong point is 1 to 5 minute efforts: attacks, short steep "
                       "ramps, late breakaways."),
        "climber": tr("O teu ponto forte é a potência ao limiar por quilo: as subidas longas "
                      "são o teu terreno.",
                      "Your strong point is threshold power per kilo: long climbs are your "
                      "terrain."),
        "rouleur": tr("O teu ponto forte é a potência sustentada: ritmo alto em plano, "
                      "contrarrelógio e trabalho para o grupo.",
                      "Your strong point is sustained power: high pace on the flat, time "
                      "trials and working for the group."),
        "allrounder": tr("As tuas durações estão equilibradas: não tens um ponto fraco "
                         "evidente nem um ponto forte que se destaque.",
                         "Your durations are balanced: no obvious weakness and no standout "
                         "strength."),
    }.get(t or "", "")


CYCLING_ADVICE = {
    5: ("Para subir o sprint: 6–8 sprints de 10–15 s com recuperação completa, uma vez por "
        "semana, e força máxima de pernas no ginásio.",
        "To raise your sprint: 6–8 sprints of 10–15 s with full recovery, once a week, and "
        "maximal leg strength in the gym."),
    60: ("Para subir o minuto: séries de 30 s a 1 min a fundo (6–8 × 40 s, recuperação 2–3 "
         "min), bem descansado.",
         "To raise your minute: all-out 30 s to 1 min repeats (6–8 × 40 s, 2–3 min recovery), "
         "well rested."),
    300: ("Para subir os 5 minutos: VO2máx — 5 × 3 min ou 4 × 4 min a 110–120 % da FTP, uma a "
          "duas vezes por semana.",
          "To raise your 5 minutes: VO2max — 5 × 3 min or 4 × 4 min at 110–120 % of FTP, once "
          "or twice a week."),
    "ft": ("Para subir o limiar: sweet spot e limiar (2 × 20 min a 88–95 %, 3 × 10 min a "
           "95–100 %) e mais volume em Z2.",
           "To raise threshold: sweet spot and threshold (2 × 20 min at 88–95 %, 3 × 10 min at "
           "95–100 %) and more Z2 volume."),
}


def cycling(db: Database, today: date | None = None) -> dict:
    from . import peaks
    today = today or date.today()
    days = int(_opt(db, "profile_days"))
    since = (today - timedelta(days=days)).isoformat()
    ath = db.athlete()
    weight = ath.weight_kg or 75.0
    ref = options.get(db, "profile_reference")
    table = POWER_TABLE.get(ref, POWER_TABLE["male"])
    try:
        best = peaks.all_peaks(db, since).get("power_w", {})
    except Exception:
        best = {}
    rows = []
    for k in CYCLING_KEYS:
        watts, src, when = None, "", ""
        if k == "ft":
            p20 = best.get(1200)
            if p20:
                watts, src, when = p20["value"] * FT_FROM_20MIN, tr(
                    "95 % dos melhores 20 min", "95 % of best 20 min"), p20["date"]
            if ath.ftp_w and (watts is None or ath.ftp_w > watts):
                watts, src, when = float(ath.ftp_w), tr("FTP do perfil", "profile FTP"), ""
        else:
            p = best.get(k)
            if p:
                watts, src, when = p["value"], p.get("name") or "", p["date"]
        wkg = watts / weight if watts else None
        lo, hi = table[k]
        score = _clamp((wkg - lo) / (hi - lo) * 100.0) if wkg is not None else None
        rows.append({"key": k, "name": duration_name(k), "watts": watts, "wkg": wkg,
                     "score": score, "level": level(score), "source": src, "date": when})
    by = {r["key"]: r["score"] for r in rows}
    measured = [k for k in (5, 60, 300) if by[k] is not None]
    groups = {"sprint": by[5],
              "punch": (sum(by[k] for k in (60, 300) if by[k] is not None)
                        / len([k for k in (60, 300) if by[k] is not None]))
              if any(by[k] is not None for k in (60, 300)) else None,
              "endurance": by["ft"]}
    have = {g: v for g, v in groups.items() if v is not None}
    rider = None
    if len(measured) >= 2 and len(have) >= 2:
        spread = max(have.values()) - min(have.values())
        if len(have) == 3 and spread < _opt(db, "profile_flat_spread"):
            rider = "allrounder"
        else:
            top = max(have, key=have.get)
            rider = {"sprint": "sprinter", "punch": "puncheur",
                     "endurance": "climber" if weight <= _opt(db, "profile_climber_max_kg")
                     else "rouleur"}[top]
    scored = [r for r in rows if r["score"] is not None]
    weakest = min(scored, key=lambda r: r["score"]) if len(scored) >= 2 else None
    strongest = max(scored, key=lambda r: r["score"]) if len(scored) >= 2 else None
    missing = [r["name"] for r in rows if r["score"] is None]
    return {"sport": "cycling", "rows": rows, "type": rider, "type_name": rider_type_name(rider),
            "type_text": rider_type_text(rider), "weakest": weakest, "strongest": strongest,
            "advice": tr(*CYCLING_ADVICE[weakest["key"]]) if weakest and rider != "allrounder"
            else "", "missing": missing, "weight_kg": weight, "days": days, "reference": ref,
            "enough": rider is not None}


# ====================================================================== ginásio


def dim_name(d: str) -> str:
    return {"max_strength": tr("Força máxima", "Maximal strength"),
            "relative": tr("Força relativa (peso do corpo)", "Relative strength (bodyweight)"),
            "grip": tr("Força de mãos", "Grip strength"), "tendons": tr("Tendões", "Tendons"),
            "power": tr("Explosividade", "Explosiveness"),
            "mobility": tr("Mobilidade", "Mobility"),
            "core": tr("Tronco e estabilidade", "Core and stability"),
            "conditioning": tr("Condicionamento", "Conditioning")}.get(d, d)


GYM_ADVICE = {
    "max_strength": ("Poucas repetições e carga alta nos básicos (agachamento, peso morto, "
                     "supino, press, remada), 2–3 vezes por semana. Planos: StrongLifts 5×5, "
                     "Starting Strength, 5/3/1.",
                     "Low reps and high load on the basics (squat, deadlift, bench, press, "
                     "row), 2–3 times a week. Plans: StrongLifts 5×5, Starting Strength, "
                     "5/3/1.", "stronglifts_5x5"),
    "relative": ("Elevações, flexões e fundos várias vezes por semana, longe da falha. Plano: "
                 "Greasing the Groove.",
                 "Pull-ups, push-ups and dips several times a week, far from failure. Plan: "
                 "Greasing the Groove.", "grease_the_groove"),
    "grip": ("Suspensões na barra, transportes pesados, gripper e pinça de discos. Planos: "
             "Bloco de força de mãos, ou o de pouco material.",
             "Bar hangs, heavy carries, gripper and plate pinches. Plans: Grip strength "
             "block, or the minimal-gear one.", "grip_block"),
    "tendons": ("Isometrias longas e excêntricos lentos (gémeos, rótula, Aquiles, punhos), "
                "2–3 vezes por semana: a modalidade Tendões do ginásio.",
                "Long isometrics and slow eccentrics (calves, patellar, Achilles, wrists), "
                "2–3 times a week: the gym's Tendons modality.", None),
    "power": ("Saltos e movimentos rápidos, poucos e frescos (saltos para caixa, salto em "
              "comprimento, swings). Plano: Progressão de pliometria.",
              "Jumps and fast moves, few and fresh (box jumps, broad jumps, swings). Plan: "
              "Plyometric progression.", "plyo_progression"),
    "mobility": ("10–15 minutos por dia de mobilidade (anca, tornozelo, torácica), ou duas "
                 "sessões da modalidade Mobilidade por semana.",
                 "10–15 minutes of mobility a day (hips, ankles, thoracic), or two Mobility "
                 "sessions a week.", None),
    "core": ("Pranchas, prancha lateral, dead bug, Pallof e transportes a uma mão. Plano: Big "
             "3 de McGill + força.",
             "Planks, side planks, dead bug, Pallof and one-hand carries. Plan: McGill Big 3 "
             "+ strength.", "mcgill_big3"),
    "conditioning": ("Circuitos e intervalos curtos uma a duas vezes por semana. Planos: "
                     "Complexos de kettlebell, Condicionamento só com o corpo.",
                     "Circuits and short intervals once or twice a week. Plans: Kettlebell "
                     "complexes, Bodyweight conditioning.", "kettlebell_complex"),
}

# nomes (sem acentos) → o levantamento de referência
LIFTS = {"squat": ("agachamento com barra",), "deadlift": ("peso morto",),
         "bench": ("supino com barra",), "press": ("press militar",),
         "row": ("remada com barra",)}
REPS = {"pullups": ("elevacoes pull ups", "elevacoes em supinacao chin ups"),
        "pushups": ("flexoes",), "dips": ("fundos dips",)}
GRIP_WORDS = ("suspens", "farmer", "carry", "gripper", "pinca", "punho", "pega grossa",
              "toalha", "dedos", "transporte")
PUSH_GROUPS, PULL_GROUPS, LEG_GROUPS = ("chest", "shoulders"), ("back",), ("legs", "hips")


def _gym_rows(db: Database, since: str) -> list[dict]:
    try:
        rows = db.conn.execute(
            "SELECT s.exercise_id, s.reps, s.load_kg, s.rpe, s.start_t_s, s.end_t_s,"
            " ss.started_at, ss.weight_at_session_kg AS body, e.name, e.category, e.measure,"
            " e.bodyweight FROM strength_sets s JOIN strength_sessions ss ON ss.id ="
            " s.session_id JOIN exercises e ON e.id = s.exercise_id WHERE ss.status ="
            " 'completed' AND ss.started_at >= ?", (since,)).fetchall()
    except Exception:
        return []
    mods: dict[int, set[str]] = {}
    try:
        for r in db.conn.execute("SELECT exercise_id, modality FROM exercise_modalities"):
            mods.setdefault(r["exercise_id"], set()).add(r["modality"])
    except Exception:
        pass
    out = []
    for r in rows:
        d = dict(r)
        d["mods"] = mods.get(d["exercise_id"], set())
        d["fold"] = _fold(d["name"])
        d["day"] = str(d["started_at"])[:10]
        if d["measure"] == "time":
            span = (d["end_t_s"] - d["start_t_s"]) if d["end_t_s"] is not None and \
                d["start_t_s"] is not None else 0
            d["seconds"] = max(float(span), float(d["reps"] or 0))
        else:
            d["seconds"] = 0.0
        out.append(d)
    return out


def _is_grip(r: dict) -> bool:
    return any(w in r["fold"] for w in GRIP_WORDS)


def gym(db: Database, today: date | None = None) -> dict:
    from . import strength as st
    today = today or date.today()
    days = int(_opt(db, "profile_days"))
    weeks = int(_opt(db, "profile_recent_weeks"))
    body = db.athlete().weight_kg or 75.0
    rows = _gym_rows(db, (today - timedelta(days=days)).isoformat())
    recent_cut = (today - timedelta(weeks=weeks)).isoformat()
    recent = [r for r in rows if r["day"] >= recent_cut]

    def per_week(pred, minutes: bool = False) -> float:
        sel = [r for r in recent if pred(r)]
        if minutes:
            return sum(r["seconds"] for r in sel) / 60.0 / weeks
        return len(sel) / weeks

    def exposure(value: float, target_key: str) -> float:
        return _clamp(value / max(1e-9, _opt(db, target_key)) * 100.0)

    # ---- medições
    e1: dict[str, float] = {}
    for lift, names in LIFTS.items():
        for r in rows:
            if r["fold"] in names and r["measure"] != "time":
                est = st.e1rm((r["load_kg"] or 0.0) + (r["bodyweight"] or 0.0) * body,
                              r["reps"], r["rpe"])
                if est and est > e1.get(lift, 0.0):
                    e1[lift] = est
    best_reps: dict[str, int] = {}
    for key, names in REPS.items():
        for r in rows:
            if r["fold"] in names and not r["load_kg"] and (r["reps"] or 0) > best_reps.get(
                    key, 0):
                best_reps[key] = int(r["reps"])

    def best_time(pred) -> float:
        return max((r["seconds"] for r in rows if pred(r)), default=0.0)
    hang = best_time(lambda r: r["fold"].startswith("suspensao") and "toalha" not in r["fold"])
    plank = best_time(lambda r: r["fold"] == "prancha")
    carry = max((r["load_kg"] or 0.0 for r in rows if "farmer" in r["fold"]), default=0.0)

    dims: dict[str, dict] = {}

    def put(key: str, perf: float | None, expo: float, measured: list[str], trained: str,
            to_measure: str) -> None:
        if perf is None:
            score = expo if (expo > 0 or rows) else None
        else:
            w = _opt(db, "profile_measured_weight_pct") / 100.0
            score = w * perf + (1 - w) * expo
        dims[key] = {"key": key, "name": dim_name(key), "score": score, "perf": perf,
                     "exposure": expo, "level": level(score), "measured": measured,
                     "trained": trained, "to_measure": to_measure}

    # força máxima
    parts, meas = [], []
    for lift, opt, label in (("squat", "profile_squat_bw", tr("agachamento", "squat")),
                             ("deadlift", "profile_deadlift_bw", tr("peso morto", "deadlift")),
                             ("bench", "profile_bench_bw", tr("supino", "bench")),
                             ("press", "profile_press_bw", tr("press", "press")),
                             ("row", "profile_row_bw", tr("remada", "row"))):
        if lift in e1:
            ratio = e1[lift] / body
            parts.append(_clamp(ratio / _opt(db, opt) * 100.0))
            meas.append(tr("{l} {k:.0f} kg ({r:.2f}× o peso)", "{l} {k:.0f} kg ({r:.2f}× "
                           "bodyweight)", l=label, k=e1[lift], r=ratio))
    heavy = per_week(lambda r: "strength" in r["mods"] and (r["load_kg"] or 0) > 0
                     and r["measure"] != "time")
    put("max_strength", sum(parts) / len(parts) if parts else None,
        exposure(heavy, "profile_strength_sets"), meas,
        tr("{n:.0f} séries com carga por semana", "{n:.0f} loaded sets a week", n=heavy),
        tr("faz séries de 3–8 repetições no agachamento, peso morto, supino, press ou remada",
           "do sets of 3–8 reps in squat, deadlift, bench, press or row"))
    # força relativa
    parts, meas = [], []
    for key, opt, label in (("pullups", "profile_pullups", tr("elevações", "pull-ups")),
                            ("pushups", "profile_pushups", tr("flexões", "push-ups")),
                            ("dips", "profile_dips", tr("fundos", "dips"))):
        if key in best_reps:
            parts.append(_clamp(best_reps[key] / _opt(db, opt) * 100.0))
            meas.append(f"{label} {best_reps[key]}")
    bw_sets = per_week(lambda r: (r["bodyweight"] or 0) > 0 and r["measure"] != "time")
    put("relative", sum(parts) / len(parts) if parts else None,
        exposure(bw_sets, "profile_core_sets"), meas,
        tr("{n:.0f} séries com o peso do corpo por semana", "{n:.0f} bodyweight sets a week",
           n=bw_sets),
        tr("faz uma série máxima de elevações, flexões ou fundos", "do one max set of "
           "pull-ups, push-ups or dips"))
    # mãos
    parts, meas = [], []
    if hang:
        parts.append(_clamp(hang / _opt(db, "profile_hang_s") * 100.0))
        meas.append(tr("suspensão {s:.0f} s", "hang {s:.0f} s", s=hang))
    if carry:
        parts.append(_clamp(2 * carry / body / _opt(db, "profile_carry_bw") * 100.0))
        meas.append(tr("farmer's carry {k:.0f} kg por mão", "farmer's carry {k:.0f} kg per hand",
                       k=carry))
    grip_sets = per_week(_is_grip)
    put("grip", sum(parts) / len(parts) if parts else None,
        exposure(grip_sets, "profile_grip_sets"), meas,
        tr("{n:.1f} séries de mãos por semana", "{n:.1f} grip sets a week", n=grip_sets),
        tr("faz uma suspensão na barra até não aguentares, ou um farmer's carry pesado",
           "do one bar hang to failure, or a heavy farmer's carry"))
    # tendões
    tendon = per_week(lambda r: r["mods"] & {"tendons", "isometric"})
    put("tendons", None, exposure(tendon, "profile_tendon_sets"), [],
        tr("{n:.1f} séries de tendões e isometria por semana", "{n:.1f} tendon and isometric "
           "sets a week", n=tendon),
        tr("não há teste: conta o trabalho de tendões e de isometria que fazes",
           "no test: it counts the tendon and isometric work you do"))
    # explosividade
    power = per_week(lambda r: "plyometrics" in r["mods"] or "swing" in r["fold"]
                     or "clean" in r["fold"] or "snatch" in r["fold"])
    put("power", None, exposure(power, "profile_power_sets"), [],
        tr("{n:.1f} séries explosivas por semana", "{n:.1f} explosive sets a week", n=power),
        tr("não há teste aqui: conta os saltos e os movimentos rápidos (os testes de salto "
           "estão no menu Longevidade)", "no test here: it counts jumps and fast moves (jump "
           "tests are in the Longevity menu)"))
    # mobilidade
    mob = per_week(lambda r: "mobility" in r["mods"] or r["category"] == "mobility",
                   minutes=True)
    put("mobility", None, exposure(mob, "profile_mobility_min"), [],
        tr("{n:.0f} min de mobilidade por semana", "{n:.0f} min of mobility a week", n=mob),
        tr("não há teste: contam os minutos de mobilidade registados",
           "no test: logged mobility minutes count"))
    # tronco
    parts, meas = [], []
    if plank:
        parts.append(_clamp(plank / _opt(db, "profile_plank_s") * 100.0))
        meas.append(tr("prancha {s:.0f} s", "plank {s:.0f} s", s=plank))
    core = per_week(lambda r: r["category"] == "core")
    put("core", parts[0] if parts else None, exposure(core, "profile_core_sets"), meas,
        tr("{n:.1f} séries de tronco por semana", "{n:.1f} core sets a week", n=core),
        tr("faz uma prancha até não aguentares", "hold a plank to failure"))
    # condicionamento
    cond = per_week(lambda r: r["mods"] & {"hiit", "cardio", "conditioning"}, minutes=True)
    put("conditioning", None, exposure(cond, "profile_conditioning_min"), [],
        tr("{n:.0f} min de condicionamento por semana", "{n:.0f} min of conditioning a week",
           n=cond),
        tr("não há teste: contam os minutos de HIIT, cardio e circuitos no ginásio",
           "no test: gym HIIT, cardio and circuit minutes count"))

    order = [dims[k] for k in GYM_DIMS]
    scored = [d for d in order if d["score"] is not None]
    weak_cut = _opt(db, "profile_weak_score")
    weak = sorted((d for d in scored if d["score"] < weak_cut), key=lambda d: d["score"])
    unmeasured = [d for d in order if d["score"] is None]
    strong = sorted(scored, key=lambda d: -d["score"])[:2]
    # equilíbrio entre padrões
    def count(groups):
        return sum(1 for r in recent if r["category"] in groups and r["measure"] != "time")
    push, pull, legs = count(PUSH_GROUPS), count(PULL_GROUPS), count(LEG_GROUPS)
    balance = []
    ratio = _opt(db, "profile_balance_pct") / 100.0
    if push + pull >= MIN_BALANCE_SETS:
        if pull < ratio * push:
            balance.append(tr("puxas pouco face ao que empurras ({a} séries de puxar, {b} de "
                              "empurrar)", "you pull little compared with pushing ({a} pull "
                              "sets, {b} push)", a=pull, b=push))
        elif push < ratio * pull:
            balance.append(tr("empurras pouco face ao que puxas ({b} séries de empurrar, {a} "
                              "de puxar)", "you push little compared with pulling ({b} push "
                              "sets, {a} pull)", a=pull, b=push))
    if push + pull + legs >= MIN_BALANCE_SETS and legs < ratio * (push + pull) / 2:
        balance.append(tr("as pernas levam pouco trabalho ({a} séries, contra {b} de tronco)",
                          "legs get little work ({a} sets, against {b} upper-body)", a=legs,
                          b=push + pull))
    advice = []
    for d in weak[:3]:
        pt, en, plan = GYM_ADVICE[d["key"]]
        advice.append({"dim": d["key"], "name": d["name"], "text": tr(pt, en), "plan": plan})
    if not scored:
        summary = tr("Ainda não há sessões de ginásio suficientes para um perfil.",
                     "Not enough gym sessions yet for a profile.")
    elif weak:
        summary = tr("Mais forte em {s}; as maiores deficiências: {w}.",
                     "Strongest in {s}; the biggest gaps: {w}.",
                     s=", ".join(d["name"].lower() for d in strong),
                     w=", ".join(d["name"].lower() for d in weak[:3]))
    else:
        summary = tr("Perfil equilibrado; mais forte em {s}.", "Balanced profile; strongest in "
                     "{s}.", s=", ".join(d["name"].lower() for d in strong))
    return {"sport": "gym", "dims": order, "weak": weak, "strong": strong,
            "unmeasured": unmeasured, "balance": balance, "advice": advice,
            "summary": summary, "sessions": len({r["day"] for r in rows}), "days": days,
            "weeks": weeks, "body_kg": body, "enough": bool(scored)}


# ====================================================================== resistência


def endurance(db: Database, sport: str, today: date | None = None) -> dict:
    """Remo, corrida e natação: a velocidade média das tuas melhores sessões curtas (< 20
    min), médias (20–60 min) e longas (> 60 min). Quanto menos a velocidade cai da curta para
    a longa, mais «de resistência» és."""
    from . import sport_challenges as sc
    today = today or date.today()
    days = int(_opt(db, "profile_days"))
    cut = datetime.combine(today - timedelta(days=days), datetime.min.time())
    try:
        sess = [s for s in sc.sessions_of(db, sport) if s["at"] >= cut]
    except Exception:
        sess = []
    rows = []
    names = (tr("Curtas (< 20 min)", "Short (< 20 min)"),
             tr("Médias (20–60 min)", "Medium (20–60 min)"),
             tr("Longas (> 60 min)", "Long (> 60 min)"))
    for (lo, hi), name in zip(ENDURANCE_BINS, names):
        best = None
        for s in sess:
            if lo <= s["seconds"] < hi and s["distance_m"] > 0 and s["seconds"] >= 300:
                v = s["distance_m"] / s["seconds"]
                if best is None or v > best["speed"]:
                    best = {"speed": v, "seconds": s["seconds"], "distance": s["distance_m"],
                            "date": s["at"].date().isoformat()}
        rows.append({"name": name, "best": best})
    have = [r["best"]["speed"] for r in rows if r["best"]]
    kind, text = None, ""
    if rows[0]["best"] and (rows[1]["best"] or rows[2]["best"]):
        long_v = (rows[2]["best"] or rows[1]["best"])["speed"]
        keep = long_v / rows[0]["best"]["speed"]
        if keep >= _opt(db, "profile_endurance_keep_pct") / 100.0:
            kind = "endurance"
            text = tr("Perdes pouca velocidade quando a sessão alonga ({p:.0f} % da curta): o "
                      "teu perfil é de resistência. Para equilibrar: séries curtas e rápidas.",
                      "You lose little speed as sessions lengthen ({p:.0f} % of the short "
                      "one): an endurance profile. To balance: short, fast repeats.",
                      p=keep * 100)
        elif keep <= _opt(db, "profile_speed_keep_pct") / 100.0:
            kind = "speed"
            text = tr("És bem mais rápido nas curtas do que nas longas ({p:.0f} %): o teu "
                      "perfil é de velocidade. Para equilibrar: mais volume fácil e sessões "
                      "longas.", "You are much faster on short sessions than long ones "
                      "({p:.0f} %): a speed profile. To balance: more easy volume and long "
                      "sessions.", p=keep * 100)
        else:
            kind = "balanced"
            text = tr("Velocidade e resistência equilibradas ({p:.0f} % da curta nas longas).",
                      "Speed and endurance balanced ({p:.0f} % of the short one on long "
                      "sessions).", p=keep * 100)
    return {"sport": sport, "rows": rows, "type": kind,
            "type_name": {"endurance": tr("Resistência", "Endurance"),
                          "speed": tr("Velocidade", "Speed"),
                          "balanced": tr("Equilibrado", "Balanced")}.get(
                              kind or "", tr("Por definir", "Undetermined")),
            "type_text": text, "sessions": len(sess), "days": days, "enough": kind is not None,
            "have": len(have)}


def of(db: Database, sport: str, today: date | None = None) -> dict:
    if sport == "cycling":
        return cycling(db, today)
    if sport == "gym":
        return gym(db, today)
    return endurance(db, sport, today)


def facts(p: dict) -> dict:
    """O perfil em chaves simples (para o agente de IA e para o Treinador)."""
    if p["sport"] == "cycling":
        return {"tipo": p["type_name"],
                "duracoes": {r["name"]: {"w_kg": round(r["wkg"], 2) if r["wkg"] else None,
                                         "pontos": round(r["score"]) if r["score"] is not None
                                         else None} for r in p["rows"]}}
    if p["sport"] == "gym":
        return {"resumo": p["summary"],
                "capacidades": {d["name"]: round(d["score"]) if d["score"] is not None else None
                                for d in p["dims"]}, "equilibrio": p["balance"]}
    return {"tipo": p["type_name"], "sessoes": p["sessions"]}
