"""Calendário mensal, ao estilo do intervals.icu.

Cada mês é uma grelha de semanas (segunda a domingo). Em cada dia: as
sessões feitas (de todos os desportos) e os treinos planeados para esse
dia; ao lado de cada semana, o resumo: tempo, distância, carga e o estado
de forma no fim da semana (fitness, fadiga, forma).

O plano é simples: um treino guardado num dia (`training_plan`). Fica
«feito» quando há nesse dia uma sessão desse treino.
"""
from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass
from datetime import date, timedelta

from . import stats
from .db import new_id, now_iso
from .i18n import tr

SPORT_COLORS = {"cycling": (34, 120, 204), "rowing": (28, 150, 110), "running": (226, 118, 36),
                "swimming": (24, 160, 192), "gym": (196, 66, 120)}

MONTHS = (("janeiro", "January"), ("fevereiro", "February"), ("março", "March"),
          ("abril", "April"), ("maio", "May"), ("junho", "June"), ("julho", "July"),
          ("agosto", "August"), ("setembro", "September"), ("outubro", "October"),
          ("novembro", "November"), ("dezembro", "December"))
WEEKDAYS = (("Seg", "Mon"), ("Ter", "Tue"), ("Qua", "Wed"), ("Qui", "Thu"), ("Sex", "Fri"),
            ("Sáb", "Sat"), ("Dom", "Sun"))


def month_name(m: int) -> str:
    return tr(*MONTHS[m - 1])


def weekday_name(i: int) -> str:
    return tr(*WEEKDAYS[i])


@dataclass
class Entry:
    day: date
    kind: str                     # ride | row | endurance | strength | plan
    id: str
    sport: str                    # cycling | rowing | running | swimming | gym
    title: str
    seconds: float = 0.0
    distance_m: float | None = None
    load: float | None = None
    workout_id: str | None = None
    planned: bool = False
    done: bool = False            # planeado e feito
    verdict: str = ""
    tone: str = ""
    useful: str | None = None

    @property
    def color(self) -> tuple[int, int, int]:
        return SPORT_COLORS.get(self.sport, (120, 128, 140))


def weeks_of(year: int, month: int) -> list[list[date]]:
    """As semanas (segunda a domingo) que cobrem o mês."""
    first = date(year, month, 1)
    start = first - timedelta(days=first.weekday())
    last = date(year, month, _cal.monthrange(year, month)[1])
    end = last + timedelta(days=6 - last.weekday())
    out, cur = [], start
    while cur <= end:
        out.append([cur + timedelta(days=i) for i in range(7)])
        cur += timedelta(days=7)
    return out


def shift_month(year: int, month: int, step: int) -> tuple[int, int]:
    m = month - 1 + step
    return year + m // 12, m % 12 + 1


# ================================================================== sessões


def _rows(db, sql: str, args: tuple = ()):
    try:
        return db.conn.execute(sql, args).fetchall()
    except Exception:
        return []


def sessions_between(db, d0: date, d1: date) -> list[Entry]:
    """As sessões concluídas entre d0 e d1 (inclusive), de todos os desportos."""
    from .naming import pretty
    lo = (d0 - timedelta(days=1)).isoformat()
    hi = (d1 + timedelta(days=2)).isoformat()
    out: list[Entry] = []

    def add(kind, sport, r, secs, dist, load, title):
        day = stats._local_date(r["started_at"])
        if day is None or not (d0 <= day <= d1):
            return
        out.append(Entry(day, kind, r["id"], sport, pretty(title or ""), float(secs or 0),
                         dist, load, r["workout_id"] if "workout_id" in r.keys() else None))

    for r in _rows(db, "SELECT id, started_at, name, moving_s, elapsed_s, distance_m, tss,"
                   " workout_id FROM rides WHERE status='completed' AND started_at >= ?"
                   " AND started_at < ?", (lo, hi)):
        add("ride", "cycling", r, r["moving_s"] or r["elapsed_s"], r["distance_m"], r["tss"],
            r["name"])
    for r in _rows(db, "SELECT id, started_at, name, moving_s, elapsed_s, distance_m, load,"
                   " workout_id FROM row_sessions WHERE status='completed' AND started_at >= ?"
                   " AND started_at < ?", (lo, hi)):
        add("row", "rowing", r, r["moving_s"] or r["elapsed_s"], r["distance_m"], r["load"],
            r["name"])
    for r in _rows(db, "SELECT id, sport, started_at, name, moving_s, elapsed_s, distance_m,"
                   " load, workout_id FROM endurance_sessions WHERE status='completed'"
                   " AND started_at >= ? AND started_at < ?", (lo, hi)):
        add("endurance", r["sport"], r, r["moving_s"] or r["elapsed_s"], r["distance_m"],
            r["load"], r["name"])
    for r in _rows(db, "SELECT id, started_at, name, elapsed_s, load, workout_id"
                   " FROM strength_sessions WHERE status='completed' AND started_at >= ?"
                   " AND started_at < ?", (lo, hi)):
        add("strength", "gym", r, r["elapsed_s"], None, r["load"], r["name"])
    # o veredito do feedback, se houver
    try:
        from . import feedback as fbm
        fbm.ensure(db)
        fb = {(r["kind"], r["session_id"]): r for r in db.conn.execute(
            "SELECT kind, session_id, verdict, useful, analysis FROM session_feedback")}
        import json
        for e in out:
            r = fb.get((e.kind, e.id))
            if r is not None:
                e.verdict, e.useful = r["verdict"] or "", r["useful"]
                try:
                    e.tone = json.loads(r["analysis"] or "{}").get("tone", "")
                except ValueError:
                    e.tone = ""
    except Exception:
        pass
    out.sort(key=lambda e: (e.day, e.kind))
    return out


# ==================================================================== plano


def ensure(db) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS training_plan (id TEXT PRIMARY KEY, day TEXT NOT NULL,"
        " sport TEXT NOT NULL, workout_id TEXT, title TEXT, notes TEXT, created_at TEXT)")
    db.conn.commit()


def plan_add(db, day: date, sport: str, workout_id: str | None, title: str,
             notes: str = "") -> str:
    ensure(db)
    pid = new_id()
    db.conn.execute("INSERT INTO training_plan (id, day, sport, workout_id, title, notes,"
                    " created_at) VALUES (?,?,?,?,?,?,?)",
                    (pid, day.isoformat(), sport, workout_id, title, notes, now_iso()))
    db.conn.commit()
    return pid


def plan_remove(db, pid: str) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM training_plan WHERE id = ?", (pid,))
    db.conn.commit()


def plan_move(db, pid: str, day: date) -> None:
    ensure(db)
    db.conn.execute("UPDATE training_plan SET day = ? WHERE id = ?", (day.isoformat(), pid))
    db.conn.commit()


def planned_between(db, d0: date, d1: date, done_sessions: list[Entry] | None = None
                    ) -> list[Entry]:
    ensure(db)
    rows = db.conn.execute("SELECT * FROM training_plan WHERE day >= ? AND day <= ?"
                           " ORDER BY day, created_at", (d0.isoformat(), d1.isoformat()))
    done = {(e.day, e.workout_id) for e in (done_sessions or []) if e.workout_id}
    out = []
    for r in rows:
        day = date.fromisoformat(r["day"])
        e = Entry(day, "plan", r["id"], r["sport"], r["title"] or "", planned=True,
                  workout_id=r["workout_id"])
        e.done = (day, r["workout_id"]) in done
        try:
            from . import objectives as ob
            b = ob.workout_brief(db, r["sport"], r["workout_id"])
            if b is not None:
                e.seconds, e.load = b.seconds, b.tss or None
        except Exception:
            pass
        out.append(e)
    return out


def planned_for(db, day: date) -> list[Entry]:
    return planned_between(db, day, day, sessions_between(db, day, day))


# ================================================================== resumos


@dataclass
class WeekSummary:
    seconds: float = 0.0
    distance_m: float = 0.0
    load: float = 0.0
    sessions: int = 0
    planned_s: float = 0.0
    ctl: float | None = None
    atl: float | None = None
    tsb: float | None = None


def month_data(db, year: int, month: int) -> dict:
    """Tudo o que o ecrã do mês precisa, de uma vez."""
    weeks = weeks_of(year, month)
    d0, d1 = weeks[0][0], weeks[-1][-1]
    done = sessions_between(db, d0, d1)
    plan = planned_between(db, d0, d1, done)
    by_day: dict[date, list[Entry]] = {}
    for e in done + [p for p in plan if not p.done]:
        by_day.setdefault(e.day, []).append(e)
    for p in plan:
        if p.done:
            for e in by_day.get(p.day, []):
                if e.workout_id == p.workout_id and not e.planned:
                    e.done = True                     # feito como estava planeado
    today = date.today()
    fit = {f["date"]: f for f in stats.fitness(db, max(1, (min(d1, today) - d0).days + 60),
                                                today=min(d1, today))} if d0 <= today else {}
    summaries = []
    for wk in weeks:
        s = WeekSummary()
        for d in wk:
            for e in by_day.get(d, []):
                if e.planned:
                    s.planned_s += e.seconds
                    continue
                s.seconds += e.seconds
                s.distance_m += e.distance_m or 0.0
                s.load += e.load or 0.0
                s.sessions += 1
        end = min(wk[-1], today)
        f = fit.get(end)
        if f is not None and end >= wk[0]:
            s.ctl, s.atl, s.tsb = f["ctl"], f["atl"], f["tsb"]
        summaries.append(s)
    return {"weeks": weeks, "by_day": by_day, "summaries": summaries}
