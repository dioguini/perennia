"""Feedback no fim de cada sessão, e a análise que o cruza com o objetivo.

No fim de uma sessão pede-se: esforço percebido (RPE 1–10), dores (0–10),
sensação geral (1–5), se o objetivo foi cumprido (sim / em parte / não) e um
comentário. Tudo opcional. A análise é feita aqui, sem rede nem IA:

* **Sessão** — duração, potência ou ritmo, FC, carga;
* **Execução** — quanto tempo esteve dentro do alvo de cada bloco do treino
  prescrito, e que parte da duração prevista foi feita;
* **Objetivo** — o objetivo escrito do treino, cruzado com o RPE previsto e o
  sentido, com o «objetivo cumprido?» e com a execução: daí sai se a sessão
  foi proveitosa (sim / em parte / não);
* **Sensações** — dores e comentário, com o cuidado que as dores pedem.

Fica tudo guardado (tabela `session_feedback`) para o futuro agente
treinador ler; o comentário vai tal como foi escrito.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import intensity as it
from . import objectives as ob
from .i18n import tr
from .units import hms

KINDS = ("ride", "row", "endurance", "strength")
FEELS = (("Péssima", "Awful"), ("Fraca", "Poor"), ("Normal", "Normal"), ("Boa", "Good"),
         ("Ótima", "Great"))
GOAL_MET = ("yes", "partial", "no")


def feel_name(v: int | None) -> str:
    if not v:
        return "—"
    return tr(*FEELS[max(1, min(5, int(v))) - 1])


def goal_met_name(v: str | None) -> str:
    return {"yes": tr("Sim", "Yes"), "partial": tr("Em parte", "Partly"),
            "no": tr("Não", "No")}.get(v or "", "—")


# ================================================================== sessão


@dataclass
class Session:
    kind: str                       # ride | row | endurance | strength
    id: str
    sport: str                      # cycling | rowing | running | swimming | gym
    title: str
    started_at: str
    elapsed_s: float
    moving_s: float
    workout_id: str | None = None
    distance_m: float | None = None
    avg_power_w: float | None = None
    np_w: float | None = None
    avg_hr: float | None = None
    max_hr: int | None = None
    load: float | None = None
    avg_pace_s: float | None = None
    ftp_w: int | None = None
    sets: int | None = None
    planned_sets: int | None = None
    # (t, % do limiar ou None, valor bruto (W ou m/s), FC)
    samples: list = field(default_factory=list)

    @property
    def workout_sport(self) -> str:
        return "gym" if self.sport == "gym" else self.sport


def _row(db, sql: str, args: tuple):
    r = db.conn.execute(sql, args).fetchone()
    return dict(r) if r is not None else None


def load_session(db, kind: str, sid: str) -> Session | None:
    """Lê a sessão e as amostras (1 por segundo, ou menos) de qualquer desporto."""
    from .naming import pretty
    ctx_cache: dict[str, it.Context] = {}

    def ctx(sport: str) -> it.Context:
        if sport not in ctx_cache:
            ctx_cache[sport] = it.Context.from_db(db, sport)
        return ctx_cache[sport]

    if kind == "ride":
        r = _row(db, "SELECT * FROM rides WHERE id = ?", (sid,))
        if r is None:
            return None
        ftp = r.get("ftp_at_ride_w") or db.athlete().ftp_w
        rows = db.conn.execute("SELECT t_s, power_w, hr_bpm FROM ride_samples WHERE ride_id = ?"
                               " ORDER BY t_s", (sid,)).fetchall()
        samples = [(x[0], (x[1] / ftp * 100) if x[1] is not None and ftp else None, x[1], x[2])
                   for x in rows]
        return Session("ride", sid, "cycling", pretty(r.get("name") or ""), r["started_at"],
                       r.get("elapsed_s") or 0, r.get("moving_s") or r.get("elapsed_s") or 0,
                       r.get("workout_id"), r.get("distance_m"), r.get("avg_power_w"),
                       r.get("np_w"), r.get("avg_hr"), r.get("max_hr"), r.get("tss"),
                       None, ftp, samples=samples)
    if kind == "row":
        from . import rowing as rw
        rw.ensure(db)
        r = _row(db, "SELECT * FROM row_sessions WHERE id = ?", (sid,))
        if r is None:
            return None
        ftp = r.get("ftp_w") or rw.row_ftp(db)
        rows = db.conn.execute("SELECT t_s, power_w, hr_bpm FROM row_samples WHERE session_id = ?"
                               " ORDER BY t_s", (sid,)).fetchall()
        samples = [(x[0], (x[1] / ftp * 100) if x[1] and ftp else None, x[1], x[2])
                   for x in rows]
        return Session("row", sid, "rowing", pretty(r.get("name") or ""), r["started_at"],
                       r.get("elapsed_s") or 0, r.get("moving_s") or 0, r.get("workout_id"),
                       r.get("distance_m"), r.get("avg_power_w"), r.get("np_w"),
                       r.get("avg_hr"), r.get("max_hr"), r.get("load"), r.get("avg_pace_s"),
                       ftp, samples=samples)
    if kind == "endurance":
        from . import endurance as en
        en.ensure(db)
        r = _row(db, "SELECT * FROM endurance_sessions WHERE id = ?", (sid,))
        if r is None:
            return None
        sport = r["sport"]
        c = ctx(sport)
        thr = (1000.0 / c.run_pace_s) if sport == "running" else (100.0 / c.swim_css_s)
        rows = db.conn.execute("SELECT t_s, speed_mps, hr_bpm FROM endurance_samples"
                               " WHERE session_id = ? ORDER BY t_s", (sid,)).fetchall()
        samples = [(x[0], (x[1] / thr * 100) if x[1] else None, x[1], x[2]) for x in rows]
        return Session("endurance", sid, sport, pretty(r.get("name") or ""), r["started_at"],
                       r.get("elapsed_s") or 0, r.get("moving_s") or 0, r.get("workout_id"),
                       r.get("distance_m"), None, None, r.get("avg_hr"), r.get("max_hr"),
                       r.get("load"), r.get("avg_pace_s"), samples=samples)
    if kind == "strength":
        r = _row(db, "SELECT * FROM strength_sessions WHERE id = ?", (sid,))
        if r is None:
            return None
        rows = db.conn.execute("SELECT t_s, hr_bpm FROM strength_hr WHERE session_id = ?"
                               " ORDER BY t_s", (sid,)).fetchall()
        planned = None
        if r.get("workout_id"):
            x = db.conn.execute("SELECT SUM(sets) FROM strength_workout_items WHERE workout_id=?",
                                (r["workout_id"],)).fetchone()
            planned = int(x[0]) if x and x[0] else None
        return Session("strength", sid, "gym", pretty(r.get("name") or ""), r["started_at"],
                       r.get("elapsed_s") or 0, r.get("elapsed_s") or 0, r.get("workout_id"),
                       None, None, None, r.get("avg_hr"), r.get("max_hr"), r.get("load"),
                       sets=r.get("total_sets"), planned_sets=planned,
                       samples=[(x[0], None, None, x[1]) for x in rows])
    return None


def prescribed(db, sess: Session) -> ob.Brief | None:
    return ob.workout_brief(db, sess.workout_sport, sess.workout_id) if sess.workout_id else None


# ================================================================ guardar


def ensure(db) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS session_feedback (kind TEXT NOT NULL, session_id TEXT NOT NULL,"
        " sport TEXT, workout_id TEXT, day TEXT, rpe INTEGER, pain INTEGER, feel INTEGER,"
        " goal_met TEXT, comment TEXT, useful TEXT, verdict TEXT, analysis TEXT,"
        " created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (kind, session_id))")
    db.conn.commit()


def get(db, kind: str, sid: str) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM session_feedback WHERE kind=? AND session_id=?",
                        (kind, sid)).fetchone()
    if r is None:
        return None
    out = dict(r)
    try:
        out["analysis"] = json.loads(out.get("analysis") or "{}")
    except ValueError:
        out["analysis"] = {}
    return out


def save(db, kind: str, sid: str, rpe: int | None = None, pain: int | None = None,
         feel: int | None = None, goal_met: str | None = None, comment: str = "") -> dict:
    """Grava o feedback e a análise; devolve a análise."""
    ensure(db)
    sess = load_session(db, kind, sid)
    fb = {"rpe": rpe, "pain": pain, "feel": feel, "goal_met": goal_met,
          "comment": (comment or "").strip()}
    res = analyse(db, sess, fb) if sess is not None else {"verdict": "", "useful": None,
                                                          "sections": []}
    db.conn.execute(
        "INSERT INTO session_feedback (kind, session_id, sport, workout_id, day, rpe, pain, feel,"
        " goal_met, comment, useful, verdict, analysis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(kind, session_id) DO UPDATE SET rpe=excluded.rpe, pain=excluded.pain,"
        " feel=excluded.feel, goal_met=excluded.goal_met, comment=excluded.comment,"
        " useful=excluded.useful, verdict=excluded.verdict, analysis=excluded.analysis,"
        " updated_at=CURRENT_TIMESTAMP",
        (kind, sid, sess.sport if sess else None, sess.workout_id if sess else None,
         (sess.started_at or "")[:10] if sess else None, rpe, pain, feel, goal_met,
         fb["comment"], res.get("useful"), res.get("verdict"),
         json.dumps(res, ensure_ascii=False)))
    db.conn.commit()
    return res


def all_feedback(db, since: str | None = None) -> list[dict]:
    """Para o agente treinador: todos os feedbacks (o mais recente primeiro)."""
    ensure(db)
    q = "SELECT * FROM session_feedback"
    args: tuple = ()
    if since:
        q += " WHERE day >= ?"
        args = (since,)
    rows = [dict(r) for r in db.conn.execute(q + " ORDER BY day DESC, created_at DESC", args)]
    for r in rows:
        try:
            r["analysis"] = json.loads(r.get("analysis") or "{}")
        except ValueError:
            r["analysis"] = {}
    return rows


# ================================================================ análise


def execution(sess: Session, brief: ob.Brief | None) -> dict:
    """Tempo dentro do alvo de cada bloco e parte da duração prevista feita."""
    out = {"planned_s": brief.seconds if brief else None, "done_s": sess.moving_s,
           "in_target_s": None, "target_s": None, "completion": None}
    if brief and brief.seconds:
        out["completion"] = min(1.5, (sess.moving_s or 0) / brief.seconds)
    if not brief or not sess.samples or sess.sport == "gym":
        return out
    vals = [(t, p) for t, p, _raw, _hr in sess.samples if p is not None]
    if not vals:
        return out
    # média de 5 s para não penalizar as oscilações de cada pedalada
    smooth = []
    win: list[float] = []
    for t, p in vals:
        win.append(p)
        if len(win) > 5:
            win.pop(0)
        smooth.append((t, sum(win) / len(win)))
    inside = counted = 0
    for t, p in smooth:
        _i, blk = ob.block_at(brief, float(t))
        if blk is None or blk.lo is None:
            continue
        end = blk.hi if blk.hi is not None else blk.lo
        lo, hi = min(blk.lo, end) - 6, max(blk.lo, end) + 6
        if blk.kind in ("warmup", "cooldown", "rest"):
            hi += 10                      # nos blocos leves, mais folga para cima
            lo -= 15
        counted += 1
        if lo <= p <= hi:
            inside += 1
    out["in_target_s"], out["target_s"] = inside, counted
    return out


def _zone_word(brief: ob.Brief | None) -> str:
    if brief is None:
        return tr("sessão", "session")
    work = [b for b in brief.raw_blocks if b.lo is not None and b.kind == "active"] or \
        [b for b in brief.raw_blocks if b.lo is not None]
    if not work:
        return tr("sessão livre", "free session")
    by: dict[int, float] = {}
    for b in work:
        z = it.zone((b.lo + (b.hi if b.hi is not None else b.lo)) / 2)
        by[z] = by.get(z, 0.0) + b.seconds
    z = max(by, key=lambda k: (by[k] * (1 + 0.6 * (k - 1)), k))
    return {1: tr("sessão de recuperação", "recovery session"),
            2: tr("sessão de resistência", "endurance session"),
            3: tr("sessão de tempo", "tempo session"),
            4: tr("sessão de limiar", "threshold session"),
            5: tr("sessão de VO2máx", "VO2max session"),
            6: tr("sessão anaeróbia", "anaerobic session"),
            7: tr("sessão de sprints", "sprint session")}[min(7, z)]


def session_text(sess: Session) -> str:
    kind = {"cycling": tr("bicicleta indoor", "indoor cycling"),
            "rowing": tr("remo indoor", "indoor rowing"),
            "running": tr("corrida em passadeira", "treadmill running"),
            "swimming": tr("natação", "swimming"), "gym": tr("ginásio", "gym")}[sess.sport]
    mins = round((sess.moving_s or sess.elapsed_s or 0) / 60)
    bits = [tr("Sessão de {k} com {m} minutos", "{k} session of {m} minutes", k=kind, m=mins)]
    if sess.distance_m:
        bits.append(tr("{d} km", "{d} km", d=f"{sess.distance_m / 1000:.2f}".replace(".", ",")))
    if sess.avg_power_w:
        p = tr("potência média de {a} W", "average power {a} W", a=f"{sess.avg_power_w:.0f}")
        if sess.np_w:
            p += tr(" (normalizada {n} W)", " (normalised {n} W)", n=f"{sess.np_w:.0f}")
        if sess.ftp_w:
            p += tr(", {pc} % da FTP de {f} W", ", {pc} % of the {f} W FTP",
                    pc=f"{(sess.np_w or sess.avg_power_w) / sess.ftp_w * 100:.0f}", f=sess.ftp_w)
        bits.append(p)
    if sess.avg_pace_s and sess.sport in ("running", "swimming", "rowing"):
        unit = {"running": "/km", "swimming": "/100 m", "rowing": "/500 m"}[sess.sport]
        bits.append(tr("ritmo médio {p}", "average pace {p}", p=hms(sess.avg_pace_s) + " " + unit))
    if sess.sets:
        s = tr("{n} séries", "{n} sets", n=sess.sets)
        if sess.planned_sets:
            s += tr(" de {p} previstas", " of {p} planned", p=sess.planned_sets)
        bits.append(s)
    if sess.avg_hr:
        bits.append(tr("FC média {h} bpm", "average HR {h} bpm", h=f"{sess.avg_hr:.0f}"))
    text = ", ".join(bits) + "."
    if sess.load:
        text += tr(" Carga de treino de {l}.", " Training load {l}.", l=f"{sess.load:.0f}")
    return text


def analyse(db, sess: Session, fb: dict) -> dict:
    brief = prescribed(db, sess)
    ex = execution(sess, brief)
    rpe, pain, feel, goal_met = fb.get("rpe"), fb.get("pain"), fb.get("feel"), fb.get("goal_met")
    target = brief.target_rpe if brief else None
    sections: list[tuple[str, str]] = [(tr("Sessão", "Session"), session_text(sess))]

    # ---- execução
    in_t = None
    if ex["target_s"]:
        in_t = ex["in_target_s"] / ex["target_s"]
    comp = ex["completion"]
    if brief is None:
        exe = tr("Sessão livre: não havia alvo prescrito para comparar.",
                 "Free session: there was no prescribed target to compare with.")
    else:
        parts = []
        if in_t is not None:
            parts.append(tr("{p} % do tempo dentro do alvo de cada bloco ({a} s em {b}).",
                            "{p} % of the time inside each block's target ({a} s of {b}).",
                            p=f"{in_t * 100:.0f}", a=ex["in_target_s"], b=ex["target_s"]))
        if comp is not None:
            parts.append(tr("Fizeste {p} % da duração prevista ({d} de {t}).",
                            "You did {p} % of the planned duration ({d} of {t}).",
                            p=f"{min(comp, 1.0) * 100:.0f}", d=hms(ex["done_s"] or 0),
                            t=hms(ex["planned_s"] or 0)))
        if sess.sport == "gym" and sess.sets and sess.planned_sets:
            parts.append(tr("Séries feitas: {a} de {b}.", "Sets done: {a} of {b}.",
                            a=sess.sets, b=sess.planned_sets))
        exe = " ".join(parts) or tr("Sem dados suficientes para medir a execução.",
                                   "Not enough data to measure execution.")
    sections.append((tr("Execução", "Execution"), exe))

    exec_ok = brief is None or (
        (in_t is None or in_t >= 0.7) and (comp is None or comp >= 0.9)
        and not (sess.sport == "gym" and sess.sets and sess.planned_sets
                 and sess.sets < 0.8 * sess.planned_sets))
    harder = rpe is not None and target is not None and rpe >= target + 2
    easier = rpe is not None and target is not None and rpe <= target - 2

    # ---- objetivo, cruzado com o que sentiste
    goal = brief.goal if brief else ""
    word = _zone_word(brief)
    obj = []
    if goal:
        obj.append(tr("Objetivo: «{g}»", "Goal: «{g}»", g=goal.rstrip(".")) + ".")
    if rpe is not None and target is not None:
        if harder:
            obj.append(tr("Sentiste RPE {r} num treino pensado para {t}/10: custou mais do que "
                          "devia. Pode ser fadiga acumulada, sono ou alvos altos demais.",
                          "You felt RPE {r} in a workout planned for {t}/10: harder than "
                          "intended. Could be accumulated fatigue, sleep or targets too high.",
                          r=rpe, t=f"{target:g}"))
        elif easier:
            obj.append(tr("Sentiste RPE {r} para um previsto de {t}/10: mais fácil do que o "
                          "pensado; os alvos podem subir um pouco.",
                          "You felt RPE {r} against a planned {t}/10: easier than expected; "
                          "targets may go up a little.", r=rpe, t=f"{target:g}"))
        else:
            obj.append(tr("O esforço que sentiste (RPE {r}) bate com o previsto ({t}/10).",
                          "Your perceived effort (RPE {r}) matches the plan ({t}/10).",
                          r=rpe, t=f"{target:g}"))
    elif rpe is not None:
        obj.append(tr("Esforço percebido: {r}/10.", "Perceived effort: {r}/10.", r=rpe))
    if goal_met:
        obj.append(tr("Disseste que o objetivo foi cumprido: {v}.",
                      "You said the goal was met: {v}.", v=goal_met_name(goal_met).lower()))

    # ---- proveitosa?
    if goal_met == "no" or (comp is not None and comp < 0.6):
        useful = "no"
    elif not exec_ok or goal_met == "partial":
        useful = "partial"
    elif harder and word.startswith(tr("sessão de recuperação", "recovery session")):
        useful = "partial"            # recuperar a custo não é recuperar
    else:
        useful = "yes"
    if pain is not None and pain >= 7:
        useful = "partial" if useful == "yes" else useful

    if useful == "yes":
        obj.append(tr("A sessão foi proveitosa para o objetivo.",
                      "The session served its goal."))
    elif useful == "partial":
        why = []
        if in_t is not None and in_t < 0.7:
            why.append(tr("pouco tempo dentro do alvo", "little time on target"))
        if comp is not None and comp < 0.9:
            why.append(tr("ficou a faltar parte da duração", "part of the duration was missing"))
        if harder:
            why.append(tr("custou mais do que o previsto", "it was harder than planned"))
        if goal_met == "partial":
            why.append(tr("disseste que só em parte", "you said only partly"))
        obj.append(tr("Foi proveitosa em parte", "It partly served its goal")
                   + (f" ({', '.join(why)})." if why else "."))
    else:
        if comp is not None and comp < 0.6:
            obj.append(tr("Ficaste em {p} % da duração prevista: para este objetivo, a sessão "
                          "não chegou a cumprir-se.", "You stopped at {p} % of the planned "
                          "duration: not enough to meet this goal.", p=f"{comp * 100:.0f}"))
            if goal_met == "yes":
                obj.append(tr("(Disseste que sim; se paraste de propósito, ajusta a duração "
                              "do treino.)", "(You said yes; if you stopped on purpose, shorten "
                              "the workout.)"))
        else:
            obj.append(tr("Não serviu o objetivo desta vez.",
                          "It did not serve the goal this time."))
    sections.append((tr("Objetivo", "Goal"), " ".join(obj)))

    # ---- sensações
    sens = []
    if pain is not None:
        if pain <= 1:
            sens.append(tr("Sem dores.", "No pain."))
        elif pain <= 3:
            sens.append(tr("Dores ligeiras ({p}/10): normais depois de treinar; vigia se "
                           "aumentam.", "Mild pain ({p}/10): normal after training; watch if "
                           "it grows.", p=pain))
        elif pain <= 6:
            sens.append(tr("Dores moderadas ({p}/10): convém aliviar a próxima sessão e ver se "
                           "passam.", "Moderate pain ({p}/10): ease the next session and see "
                           "if it settles.", p=pain))
        else:
            sens.append(tr("Dores fortes ({p}/10): para e, se persistirem, fala com um "
                           "profissional de saúde.", "Strong pain ({p}/10): stop, and if it "
                           "persists, see a health professional.", p=pain))
    if feel:
        sens.append(tr("Sensação geral: {f}.", "Overall feeling: {f}.", f=feel_name(feel).lower()))
    if fb.get("comment"):
        sens.append(tr("Comentário: «{c}»", "Comment: «{c}»", c=fb["comment"]))
    if sens:
        sections.append((tr("Sensações", "How it felt"), " ".join(sens)))

    # ---- veredito (a frase do chip)
    if pain is not None and pain >= 7:
        verdict, tone = tr("Atenção às dores: rever antes do próximo treino",
                           "Mind the pain: review before the next session"), "bad"
    elif useful == "no":
        verdict, tone = tr("{w} com o objetivo por cumprir", "{w} with the goal not met",
                           w=word.capitalize()), "bad"
    elif useful == "partial" and harder:
        verdict, tone = tr("{w} cumprida, mas mais dura do que o previsto",
                           "{w} done, but harder than planned", w=word.capitalize()), "warn"
    elif useful == "partial":
        verdict, tone = tr("{w} cumprida em parte", "{w} partly done",
                           w=word.capitalize()), "warn"
    elif brief is None:
        verdict, tone = tr("Sessão livre registada", "Free session logged"), "good"
    elif harder:
        verdict, tone = tr("{w} cumprida, mas mais dura do que o previsto",
                           "{w} done, but harder than planned", w=word.capitalize()), "warn"
    else:
        verdict, tone = tr("{w} cumprida dentro do prescrito", "{w} done as prescribed",
                           w=word.capitalize()), "good"
    if pain is not None and 4 <= pain <= 6 and tone == "good":
        tone = "warn"
    return {"verdict": verdict, "tone": tone, "useful": useful, "sections": sections,
            "execution": ex, "target_rpe": target, "goal": goal,
            "prescribed": brief.as_dict() if brief else None}
