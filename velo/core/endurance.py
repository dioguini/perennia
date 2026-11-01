"""Corrida e natação: treinos estruturados, sessão, voltas e `.fit`.

Sem GPS (a Perennia é uma aplicação de secretária, offline): a distância
vem da passadeira (a velocidade que escolhes, ou o total do visor que
escreves) e, na natação, das piscinas que vais contando (tecla +). A FC vem
da banda ou do relógio. Os treinos têm passos por tempo ou por distância,
com a intensidade em % do limiar, mostrada em ritmo, FC ou RPE.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from . import naming, physics
from . import strength as st
from .db import Athlete, Database, new_id, now_iso
from .i18n import tr
from .intensity import Context
from .sports import AutoLap
from .units import hms

SPORTS = ("running", "swimming")
FLUSH_EVERY = 5
MIN_STEP_S = 10


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS endurance_workouts (
      id TEXT PRIMARY KEY, sport TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
      mode TEXT NOT NULL DEFAULT 'pace', builtin INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 100);
    CREATE TABLE IF NOT EXISTS endurance_steps (
      workout_id TEXT NOT NULL REFERENCES endurance_workouts(id) ON DELETE CASCADE,
      idx INTEGER NOT NULL, kind TEXT NOT NULL, dur_type TEXT NOT NULL, dur_value REAL NOT NULL,
      lo REAL, hi REAL, cue TEXT, PRIMARY KEY (workout_id, idx)) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS endurance_sessions (
      id TEXT PRIMARY KEY, sport TEXT NOT NULL, name TEXT, status TEXT NOT NULL,
      workout_id TEXT, started_at TEXT NOT NULL, ended_at TEXT, elapsed_s INTEGER,
      moving_s INTEGER, paused_s INTEGER, distance_m REAL, avg_pace_s REAL, avg_hr REAL,
      max_hr INTEGER, load REAL, load_source TEXT, hr_zone_s TEXT, lengths INTEGER,
      pool_m REAL, fit_path TEXT);
    CREATE TABLE IF NOT EXISTS endurance_samples (
      session_id TEXT NOT NULL REFERENCES endurance_sessions(id) ON DELETE CASCADE,
      t_s INTEGER NOT NULL, dist_m REAL, speed_mps REAL, hr_bpm INTEGER,
      PRIMARY KEY (session_id, t_s)) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS endurance_laps (
      id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES endurance_sessions(id)
      ON DELETE CASCADE, lap_no INTEGER NOT NULL, trigger TEXT, start_t REAL, end_t REAL,
      distance_m REAL, avg_hr REAL, max_hr INTEGER, lengths INTEGER);
    """)
    db.conn.commit()


# =================================================================== treinos


@dataclass
class Step:
    kind: str = "active"            # warmup | active | rest | cooldown
    dur_type: str = "time"          # time (s) | distance (m)
    dur_value: float = 300
    lo: float | None = 80.0         # % do limiar
    hi: float | None = 85.0
    cue: str = ""

    def clean(self) -> "Step":
        if self.dur_type == "time":
            self.dur_value = max(MIN_STEP_S, int(round(self.dur_value)))
        else:
            self.dur_type = "distance"
            self.dur_value = max(25.0, float(round(self.dur_value)))
        if self.lo is not None and self.hi is not None and self.lo > self.hi:
            self.lo, self.hi = self.hi, self.lo
        return self

    def duration_text(self) -> str:
        if self.dur_type == "time":
            return hms(self.dur_value)
        v = self.dur_value
        return f"{v / 1000:g} km" if v >= 1000 else f"{v:.0f} m"

    @property
    def mid(self) -> float | None:
        if self.lo is None:
            return None
        return (self.lo + (self.hi if self.hi is not None else self.lo)) / 2


S = Step
LIBRARY = {
    "running": (
        ("Corrida fácil 40 min", "Zona 2, conversa possível.", "pace", [
            S("warmup", "time", 600, 65, 72), S("active", "time", 1500, 75, 82),
            S("cooldown", "time", 300, 60, 68)]),
        ("Intervalos 6 × 800 m", "Ritmo de 5 km, 2 min de recuperação.", "pace", [
            S("warmup", "time", 900, 65, 75)] + [
            x for _ in range(6) for x in (S("active", "distance", 800, 103, 107),
                                          S("rest", "time", 120, 55, 60))] + [
            S("cooldown", "time", 600, 60, 68)]),
        ("Limiar 3 × 10 min", "Ao ritmo de limiar, 2 min entre blocos.", "pace", [
            S("warmup", "time", 900, 65, 75)] + [
            x for _ in range(3) for x in (S("active", "time", 600, 97, 100),
                                          S("rest", "time", 120, 60, 65))] + [
            S("cooldown", "time", 600, 60, 68)]),
        ("Rodagem longa 70 min", "Constante em zona 2.", "hr", [
            S("warmup", "time", 600, 65, 72), S("active", "time", 3000, 72, 80),
            S("cooldown", "time", 600, 60, 68)]),
    ),
    "swimming": (
        ("Técnica e base 1500 m", "Aquecer, 10 × 100 m confortável, soltar.", "pace", [
            S("warmup", "distance", 300, 70, 78)] + [
            x for _ in range(10) for x in (S("active", "distance", 100, 85, 90),
                                           S("rest", "time", 20, 40, 45))] + [
            S("cooldown", "distance", 200, 65, 72)]),
        ("CSS 8 × 100 m", "Ao ritmo crítico, 15 s de descanso.", "pace", [
            S("warmup", "distance", 400, 70, 80)] + [
            x for _ in range(8) for x in (S("active", "distance", 100, 99, 102),
                                          S("rest", "time", 15, 40, 45))] + [
            S("cooldown", "distance", 200, 65, 72)]),
        ("Velocidade 12 × 50 m", "Rápido, 30 s de descanso.", "rpe", [
            S("warmup", "distance", 400, 70, 80)] + [
            x for _ in range(12) for x in (S("active", "distance", 50, 110, 118),
                                           S("rest", "time", 30, 40, 45))] + [
            S("cooldown", "distance", 200, 65, 72)]),
    ),
}


SWIM_TESTS = (
    ("400 m", "s", "lower", "400 m no máximo, ritmo constante."),
    ("200 m", "s", "lower", "200 m no máximo. Com o de 400 m dá o ritmo crítico (CSS)."),
    ("100 m", "s", "lower", "100 m a fundo."),
    ("Distância em 30 minutos", "m", "higher", "30 min no máximo sustentável (teste T30)."),
)


def seed_tests(db: Database) -> None:
    """Testes de natação (as bases antigas não os tinham)."""
    from . import fitness_tests as ft
    ft.seed(db)
    for i, (name, unit, better, instr) in enumerate(SWIM_TESTS):
        if db.conn.execute("SELECT 1 FROM fitness_tests WHERE sport='swimming' AND name=?",
                           (name,)).fetchone():
            continue
        db.conn.execute(
            "INSERT INTO fitness_tests(sport, name, unit, better, duration_s, protocol,"
            " instructions, custom, sort) VALUES ('swimming',?,?,?,?,NULL,?,0,?)",
            (name, unit, better, 1800 if unit == "m" else 0, instr, 500 + i))
    db.conn.commit()


def seed(db: Database) -> None:
    ensure(db)
    if not db.get("swim_tests_seeded", False):
        try:
            seed_tests(db)
            db.set("swim_tests_seeded", True)
        except Exception:
            pass
    if db.get("endurance_seeded", False):
        return
    for sport, entries in LIBRARY.items():
        for i, (name, desc, mode, steps) in enumerate(entries):
            save_workout(db, None, sport, name, desc, steps, mode=mode, builtin=True, sort=i)
    db.set("endurance_seeded", True)


CHALLENGE = 2      # endurance_workouts.builtin: os treinos do modo Challenge


def workouts(db: Database, sport: str, challenges: bool = False) -> list[dict]:
    """Os treinos do desporto. Os do Challenge (builtin = 2) só aparecem com
    `challenges=True` — não se misturam com a lista de treinos."""
    seed(db)
    out = []
    cond = "builtin = 2" if challenges else "builtin < 2"
    for r in db.conn.execute(f"SELECT * FROM endurance_workouts WHERE sport = ? AND {cond}"
                             " ORDER BY builtin DESC, sort, name", (sport,)):
        w = dict(r)
        w["steps"] = steps_of(db, w["id"])
        w["total_s"], w["total_m"] = totals(w["steps"])
        out.append(w)
    return out


def workout(db: Database, wid: str) -> dict | None:
    seed(db)
    r = db.conn.execute("SELECT * FROM endurance_workouts WHERE id = ?", (wid,)).fetchone()
    if r is None:
        return None
    w = dict(r)
    w["steps"] = steps_of(db, wid)
    w["total_s"], w["total_m"] = totals(w["steps"])
    return w


def steps_of(db: Database, wid: str) -> list[Step]:
    return [Step(r["kind"], r["dur_type"], r["dur_value"], r["lo"], r["hi"], r["cue"] or "")
            for r in db.conn.execute("SELECT * FROM endurance_steps WHERE workout_id = ?"
                                     " ORDER BY idx", (wid,))]


def totals(steps: list[Step]) -> tuple[float, float]:
    return (sum(s.dur_value for s in steps if s.dur_type == "time"),
            sum(s.dur_value for s in steps if s.dur_type == "distance"))


def save_workout(db: Database, wid: str | None, sport: str, name: str, description: str,
                 steps: list[Step], mode: str = "pace", builtin: bool | int = False,
                 sort: int = 100) -> str:
    ensure(db)
    wid = wid or new_id()
    db.conn.execute(
        "INSERT INTO endurance_workouts(id, sport, name, description, mode, builtin, created_at,"
        " sort) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
        " description=excluded.description, mode=excluded.mode",
        (wid, sport, name.strip() or "Treino", description, mode, int(builtin), now_iso(), sort))
    db.conn.execute("DELETE FROM endurance_steps WHERE workout_id = ?", (wid,))
    db.conn.executemany(
        "INSERT INTO endurance_steps(workout_id, idx, kind, dur_type, dur_value, lo, hi, cue)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [(wid, i, s.kind, s.dur_type, s.dur_value, s.lo, s.hi, s.cue)
         for i, s in enumerate(Step(**asdict(x)).clean() for x in steps)])
    db.conn.commit()
    return wid


def delete_workout(db: Database, wid: str) -> None:
    db.conn.execute("DELETE FROM endurance_workouts WHERE id = ?", (wid,))
    db.conn.commit()


class Runner:
    """Avança pelos passos com o tempo e a distância."""

    def __init__(self, steps: list[Step], name: str = ""):
        self.steps = [Step(**asdict(s)).clean() for s in steps]
        self.name = name
        self.idx = 0
        self.step_t = 0.0
        self.step_m = 0.0
        self.done = not self.steps

    @property
    def step(self) -> Step | None:
        return None if self.done else self.steps[self.idx]

    @property
    def next_step(self) -> Step | None:
        if self.done or self.idx + 1 >= len(self.steps):
            return None
        return self.steps[self.idx + 1]

    def remaining_text(self) -> str:
        s = self.step
        if s is None:
            return ""
        if s.dur_type == "time":
            return hms(max(0.0, s.dur_value - self.step_t))
        return f"{max(0.0, s.dur_value - self.step_m):.0f} m"

    def progress(self) -> float:
        s = self.step
        if s is None:
            return 1.0
        got = self.step_t if s.dur_type == "time" else self.step_m
        return max(0.0, min(1.0, got / s.dur_value))

    def advance(self, dt: float, dm: float) -> list[tuple[str, dict]]:
        if self.done:
            return []
        self.step_t += dt
        self.step_m += dm
        s = self.steps[self.idx]
        got = self.step_t if s.dur_type == "time" else self.step_m
        if got < s.dur_value:
            return []
        ev = [("step_end", {"idx": self.idx, "seconds": self.step_t, "meters": self.step_m})]
        self.idx += 1
        self.step_t = self.step_m = 0.0
        if self.idx >= len(self.steps):
            self.done = True
            ev.append(("workout_done", {}))
        else:
            ev.append(("step", {"idx": self.idx, "cue": self.steps[self.idx].cue}))
        return ev

    def snapshot(self) -> dict:
        return {"idx": self.idx, "step_t": self.step_t, "step_m": self.step_m, "done": self.done}

    def restore(self, snap: dict) -> None:
        self.idx = int(snap.get("idx", 0))
        self.step_t = float(snap.get("step_t", 0))
        self.step_m = float(snap.get("step_m", 0))
        self.done = bool(snap.get("done")) or self.idx >= len(self.steps)


# =================================================================== sessão


@dataclass
class Lap:
    no: int
    start_t: float
    start_m: float
    start_len: int = 0
    trigger: str = "manual"
    end_t: float | None = None
    distance_m: float = 0.0
    lengths: int = 0
    avg_hr: float | None = None
    max_hr: int | None = None
    hr_sum: float = 0.0
    hr_n: int = 0

    @property
    def seconds(self) -> float:
        return (self.end_t or self.start_t) - self.start_t


class EnduranceEngine:
    """A sessão de corrida ou de natação. O tempo só conta depois de `start()`."""

    def __init__(self, db: Database, athlete: Athlete, sport: str, *, sensors: Any = None,
                 workout_id: str | None = None, autolap: dict | None = None,
                 pool_m: float = 25.0, out_dir: str | Path = "endurance",
                 resume: dict | None = None):
        ensure(db)
        self.db = db
        self.athlete = athlete
        self.sport = sport if sport in SPORTS else "running"
        self.sensors = sensors
        self.out_dir = Path(out_dir)
        self.pool_m = float(pool_m)
        self.ctx = Context.from_db(db, self.sport)
        from .ride import estimate_lthr
        self.lthr = estimate_lthr(athlete)
        self.hr_bounds = list(db.get("hr_zones_pct_lthr", [68, 83, 94, 105]))
        self.hr_zone_s = [0.0] * (len(self.hr_bounds) + 1)
        self.workout_id = workout_id
        self.workout: Runner | None = None
        self.mode = "pace"
        self.title = tr("Corrida livre", "Free run") if self.sport == "running" else \
            tr("Natação livre", "Free swim")
        if workout_id:
            w = workout(db, workout_id)
            if w:
                self.workout = Runner(w["steps"], w["name"])
                self.title = w["name"]
                self.mode = w["mode"]
        self.autolap = AutoLap(autolap)
        self.events: list[tuple[str, dict]] = []
        self.started = False
        self.paused = False
        self.finished = False
        self.t = 0.0
        self.paused_s = 0.0
        self.distance_m = 0.0
        self.speed_kmh = 10.0 if self.sport == "running" else 0.0
        self.lengths = 0
        self.hr_bpm: int | None = None
        self.laps: list[Lap] = []
        self._lap = Lap(1, 0.0, 0.0)
        self._acc = 0.0
        self._pending: list[tuple] = []
        self._hrs: list[int | None] = []
        if resume is not None:
            self.session_id = resume["session_id"]
            self.start_unix = float(resume["config"].get("start_unix") or time.time())
            self._restore(resume["state"])
        else:
            self.session_id = new_id()
            self.start_unix = time.time()
            db.conn.execute(
                "INSERT INTO endurance_sessions(id, sport, name, status, workout_id, started_at,"
                " pool_m) VALUES (?,?,?,'recording',?,?,?)",
                (self.session_id, self.sport, self.title, workout_id, now_iso(),
                 self.pool_m if self.sport == "swimming" else None))
            db.conn.commit()
            self.checkpoint()

    def drain_events(self) -> list[tuple[str, dict]]:
        out, self.events = self.events, []
        return out

    # ---------------------------------------------------------------- comandos

    def start(self) -> None:
        if not self.started:
            self.started = True
            self.start_unix = time.time()
            self.events.append(("started", {}))
            if self.workout is not None and self.workout.step is not None:
                self.events.append(("step", {"idx": 0, "cue": self.workout.step.cue}))

    def toggle_pause(self) -> None:
        if not self.started:
            self.start()
            return
        self.paused = not self.paused
        self.checkpoint()

    def set_speed(self, kmh: float) -> None:
        self.speed_kmh = max(0.0, min(30.0, round(kmh, 1)))

    def add_length(self, n: int = 1) -> None:
        """Natação: mais uma piscina (ou menos, para corrigir)."""
        if not self.started:
            self.start()
        n = max(-self.lengths, n)
        self.lengths += n
        dm = n * self.pool_m
        self.distance_m = max(0.0, self.distance_m + dm)
        self._advance_distance(dm)

    def set_distance(self, meters: float) -> None:
        """O total que o visor da passadeira mostra."""
        dm = max(0.0, meters) - self.distance_m
        self.distance_m = max(0.0, meters)
        if dm > 0:
            self._advance_distance(dm)

    def _advance_distance(self, dm: float) -> None:
        if self.workout is not None:
            for kind, data in self.workout.advance(0.0, dm):
                self._workout_event(kind, data)
        if self.autolap.due(self.t, self.distance_m):
            self.lap(self.autolap.mode)

    # ------------------------------------------------------------------ ciclo

    @property
    def status(self) -> str:
        if self.finished:
            return "finished"
        if not self.started:
            return "waiting"
        return "paused" if self.paused else "running"

    def update(self, dt: float) -> None:
        if self.finished or dt <= 0:
            return
        if self.sensors is not None:
            try:
                r = self.sensors.reading()
                self.hr_bpm = getattr(r, "hr_bpm", None) if r is not None else None
            except Exception:
                self.hr_bpm = None
        if not self.started:
            return
        if self.paused:
            self.paused_s += dt
            return
        self.t += dt
        dm = 0.0
        if self.sport == "running" and self.speed_kmh > 0:
            dm = self.speed_kmh / 3.6 * dt
            self.distance_m += dm
        if self.workout is not None:
            for kind, data in self.workout.advance(dt, dm):
                self._workout_event(kind, data)
        if self.autolap.due(self.t, self.distance_m):
            self.lap(self.autolap.mode)
        self._acc += dt
        while self._acc >= 1.0:
            self._acc -= 1.0
            self._sample()

    def _workout_event(self, kind: str, data: dict) -> None:
        self.events.append((kind, data))
        if kind == "step_end":
            self.lap("workout_step")

    def _sample(self) -> None:
        hr = self.hr_bpm
        self._hrs.append(hr)
        if hr:
            self._lap.hr_sum += hr
            self._lap.hr_n += 1
            self._lap.max_hr = max(self._lap.max_hr or 0, hr)
            if self.lthr:
                z = physics.zone_of(hr, self.hr_bounds, self.lthr)
                self.hr_zone_s[min(z, len(self.hr_zone_s)) - 1] += 1.0
        speed = self.speed_kmh / 3.6 if self.sport == "running" else None
        self._pending.append((self.session_id, int(self.t), round(self.distance_m, 1), speed, hr))
        if len(self._pending) >= FLUSH_EVERY:
            self.flush()

    # ------------------------------------------------------------------ voltas

    @property
    def lap_elapsed_s(self) -> float:
        return self.t - self._lap.start_t

    @property
    def lap_distance_m(self) -> float:
        return self.distance_m - self._lap.start_m

    def lap(self, trigger: str = "manual") -> Lap | None:
        lp = self._lap
        if self.t - lp.start_t < 1.0 and trigger == "manual":
            return None
        lp.end_t = self.t
        lp.trigger = trigger
        lp.distance_m = self.distance_m - lp.start_m
        lp.lengths = self.lengths - lp.start_len
        lp.avg_hr = lp.hr_sum / lp.hr_n if lp.hr_n else None
        self.laps.append(lp)
        self.db.conn.execute(
            "INSERT INTO endurance_laps(session_id, lap_no, trigger, start_t, end_t, distance_m,"
            " avg_hr, max_hr, lengths) VALUES (?,?,?,?,?,?,?,?,?)",
            (self.session_id, lp.no, trigger, lp.start_t, lp.end_t, lp.distance_m, lp.avg_hr,
             lp.max_hr, lp.lengths))
        self.db.conn.commit()
        self.events.append(("lap", {"no": lp.no, "seconds": lp.seconds,
                                    "distance_m": lp.distance_m, "trigger": trigger}))
        self._lap = Lap(lp.no + 1, self.t, self.distance_m, self.lengths)
        return lp

    # ---------------------------------------------------------- números

    def pace_s(self, seconds: float, meters: float) -> float | None:
        """s/km na corrida, s/100 m na natação."""
        unit = 1000.0 if self.sport == "running" else 100.0
        return seconds / meters * unit if meters > 5 else None

    @property
    def avg_pace_s(self) -> float | None:
        return self.pace_s(self.t, self.distance_m)

    @property
    def avg_hr(self) -> float | None:
        v = [h for h in self._hrs if h]
        return sum(v) / len(v) if v else None

    @property
    def hr_zone(self) -> int | None:
        if not self.hr_bpm or not self.lthr:
            return None
        return physics.zone_of(self.hr_bpm, self.hr_bounds, self.lthr)

    def target_text(self) -> str:
        if self.workout is None or self.workout.step is None:
            return ""
        s = self.workout.step
        if s.lo is None:
            return tr("livre", "free")
        lo, hi = self.ctx.text(self.mode, s.lo), self.ctx.text(self.mode, s.hi or s.lo)
        return lo if lo == hi else f"{lo} – {hi}"

    # ------------------------------------------------------------ recuperação

    def flush(self) -> None:
        if self._pending:
            self.db.conn.executemany(
                "INSERT OR REPLACE INTO endurance_samples(session_id, t_s, dist_m, speed_mps,"
                " hr_bpm) VALUES (?,?,?,?,?)", self._pending)
            self.db.conn.commit()
            self._pending.clear()
        if not self.finished:
            self.checkpoint()

    def checkpoint(self) -> None:
        try:
            self.db.save_checkpoint(self.session_id, "endurance", {
                "start_unix": self.start_unix, "sport": self.sport, "name": self.title,
                "workout_id": self.workout_id, "pool_m": self.pool_m,
                "autolap": self.autolap.as_dict()}, {
                "t": self.t, "paused_s": self.paused_s, "distance_m": self.distance_m,
                "lengths": self.lengths, "speed_kmh": self.speed_kmh, "started": self.started,
                "hr_zone_s": self.hr_zone_s, "lap": asdict(self._lap),
                "workout": self.workout.snapshot() if self.workout else None})
        except Exception:
            pass

    def _restore(self, snap: dict) -> None:
        self.t = float(snap.get("t", 0))
        self.paused_s = float(snap.get("paused_s", 0))
        self.distance_m = float(snap.get("distance_m", 0))
        self.lengths = int(snap.get("lengths", 0))
        self.speed_kmh = float(snap.get("speed_kmh", self.speed_kmh))
        self.started = bool(snap.get("started", True))
        z = snap.get("hr_zone_s")
        if z and len(z) == len(self.hr_zone_s):
            self.hr_zone_s = [float(v) for v in z]
        if snap.get("lap"):
            self._lap = Lap(**snap["lap"])
        for r in self.db.conn.execute("SELECT * FROM endurance_laps WHERE session_id = ?"
                                      " ORDER BY lap_no", (self.session_id,)):
            self.laps.append(Lap(r["lap_no"], r["start_t"], 0.0, 0, r["trigger"], r["end_t"],
                                 r["distance_m"] or 0, r["lengths"] or 0, r["avg_hr"],
                                 r["max_hr"]))
        for r in self.db.conn.execute("SELECT hr_bpm FROM endurance_samples WHERE"
                                      " session_id = ?", (self.session_id,)):
            self._hrs.append(r["hr_bpm"])
        if self.workout is not None and snap.get("workout"):
            self.workout.restore(snap["workout"])
        self.autolap.restore(self.t, self.distance_m)
        self.paused = True
        self.events.append(("recovered", {"t_s": self.t}))

    def suspend(self) -> None:
        if not self.finished:
            try:
                self.flush()
            except Exception:
                pass

    @property
    def sets(self) -> list:
        return [1] if self.started and self.t > 0 else []

    # ------------------------------------------------------------------- fim

    def summary(self) -> dict:
        hrs = [h for h in self._hrs if h]
        load, source = None, None
        tp = self.avg_pace_s
        thr = self.ctx.run_pace_s if self.sport == "running" else self.ctx.swim_css_s
        if tp and self.distance_m > 200:
            if_ = thr / tp
            load, source = self.t / 3600.0 * if_ * if_ * 100.0, "pace"
        if load is None:
            load = st.hr_load(self._hrs, self.lthr)
            source = "hr" if load is not None else None
        return {"sport": self.sport, "title": self.title, "elapsed_s": int(self.t + self.paused_s),
                "moving_s": int(self.t), "paused_s": int(self.paused_s),
                "distance_m": round(self.distance_m, 1), "avg_pace_s": tp,
                "avg_hr": sum(hrs) / len(hrs) if hrs else None,
                "max_hr": max(hrs) if hrs else None, "load": load, "load_source": source,
                "hr_zone_s": list(self.hr_zone_s), "lengths": self.lengths,
                "pool_m": self.pool_m, "laps": list(self.laps)}

    def finish(self) -> dict:
        if self.finished:
            return {}
        if self.t - self._lap.start_t >= 1.0 or not self.laps:
            self.lap("end")
        self.flush()
        self.finished = True
        summ = self.summary()
        base = naming.activity_name(self.start_unix, workout_name=(
            ("corrida-" if self.sport == "running" else "natacao-") + self.title).replace(
            "×", "x"), kind="workout")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path, name = naming.unique_path(self.out_dir, base)
        fit_path = None
        try:
            from . import fit
            from .sports import SPORTS as REG
            samples = [dict(r) for r in self.db.conn.execute(
                "SELECT * FROM endurance_samples WHERE session_id = ? ORDER BY t_s",
                (self.session_id,))]
            laps = [{"start_t": lp.start_t, "end_t": lp.end_t, "distance_m": lp.distance_m,
                     "avg_hr": lp.avg_hr, "max_hr": lp.max_hr, "strokes": lp.lengths or None,
                     "trigger": {"end": "session_end", "workout_step": "workout_step"}.get(
                         lp.trigger, lp.trigger if lp.trigger in ("time", "distance")
                         else "manual")} for lp in self.laps]
            sp = REG[self.sport]
            fit.write_rowing(path, self.athlete, samples, laps,
                             dict(summ, strokes=self.lengths or None, avg_spm=None, kcal=None,
                                  avg_power_w=None, max_power_w=None, np_w=None),
                             self.start_unix, name=name, sport=sp.fit_sport,
                             sub_sport=sp.fit_sub)
            fit_path = str(path)
        except Exception as e:
            self.events.append(("fit_error", {"message": str(e)}))
        self.db.conn.execute(
            "UPDATE endurance_sessions SET status='completed', ended_at=?, elapsed_s=?, moving_s=?,"
            " paused_s=?, distance_m=?, avg_pace_s=?, avg_hr=?, max_hr=?, load=?, load_source=?,"
            " hr_zone_s=?, lengths=?, fit_path=?, name=? WHERE id = ?",
            (now_iso(), summ["elapsed_s"], summ["moving_s"], summ["paused_s"],
             summ["distance_m"], summ["avg_pace_s"], summ["avg_hr"], summ["max_hr"],
             summ["load"], summ["load_source"], json.dumps(summ["hr_zone_s"]), self.lengths,
             fit_path, name, self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)
        summ.update(session_id=self.session_id, name=name, fit_path=fit_path)
        return summ

    def abort(self, delete: bool = False) -> None:
        self.finished = True
        if delete:
            self.db.conn.execute("DELETE FROM endurance_sessions WHERE id = ?",
                                 (self.session_id,))
        else:
            self.db.conn.execute("UPDATE endurance_sessions SET status='aborted', ended_at=?"
                                 " WHERE id = ?", (now_iso(), self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)

    def discard(self) -> None:
        self.abort(delete=True)


def sessions(db: Database, sport: str, limit: int = 100) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM endurance_sessions WHERE status='completed' AND sport = ?"
        " ORDER BY started_at DESC LIMIT ?", (sport, limit))]


def session_laps(db: Database, sid: str) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM endurance_laps WHERE session_id = ? ORDER BY lap_no", (sid,))]
