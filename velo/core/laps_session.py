"""Treino livre e Conditioning: uma sessão feita de voltas.

Não há plano. Abre-se uma volta de um tipo — força, descanso, passadeira ou
outro cardio —, preenchem-se os dados dela, e abre-se a seguinte (o que fecha
a anterior). A frequência cardíaca vem da banda ou do relógio, como na força.

- Força: exercício, repetições, carga e RPE (também contam para as
  estatísticas da força e para a 1RM estimada).
- Passadeira (uma passadeira «burra», sem ligação): o total que o visor
  mostra no fim do intervalo, a velocidade e a inclinação. A distância da
  volta calcula-se sozinha (total agora − total no fim da volta anterior).
- Cardio: outro aparelho ou exercício, com distância opcional.
- Descanso: só o tempo e a FC.

O Conditioning é o mesmo motor, com a passadeira como primeira escolha.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import naming, physics
from . import strength as st
from .db import Athlete, Database, new_id, now_iso

KINDS = ("strength", "rest", "treadmill", "cardio", "rowing")
MODES = ("free", "conditioning")
HR_FLUSH_EVERY = 5


def ensure(db: Database) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS strength_laps (id INTEGER PRIMARY KEY,"
        " session_id TEXT NOT NULL REFERENCES strength_sessions(id) ON DELETE CASCADE,"
        " lap_no INTEGER NOT NULL, kind TEXT NOT NULL, start_t_s INTEGER NOT NULL,"
        " end_t_s INTEGER, exercise_id INTEGER REFERENCES exercises(id), reps INTEGER,"
        " load_kg REAL, rpe REAL, odometer_km REAL, distance_km REAL, speed_kmh REAL,"
        " incline_pct REAL, notes TEXT, avg_hr REAL, max_hr INTEGER, set_id INTEGER)")
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(strength_sessions)")}
    if "mode" not in cols:
        db.conn.execute("ALTER TABLE strength_sessions ADD COLUMN mode TEXT NOT NULL"
                        " DEFAULT 'plan'")
    if "distance_km" not in cols:
        db.conn.execute("ALTER TABLE strength_sessions ADD COLUMN distance_km REAL")
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS lap_plans (id TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " mode TEXT NOT NULL DEFAULT 'conditioning', items TEXT NOT NULL,"
        " hidden INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)")
    lcols = {r["name"] for r in db.conn.execute("PRAGMA table_info(strength_laps)")}
    for c, decl in (("row_spm", "REAL"), ("row_pace_s", "REAL"), ("row_resistance", "INTEGER")):
        if c not in lcols:
            db.conn.execute(f"ALTER TABLE strength_laps ADD COLUMN {c} {decl}")
    db.conn.commit()


@dataclass
class LapEntry:
    id: int
    no: int
    kind: str
    start_t: float
    end_t: float | None = None
    exercise_id: int | None = None
    name: str = ""
    measure: str = "reps"
    bodyweight: float = 0.0
    fit_category: int | None = None
    reps: int | None = None
    load_kg: float | None = None
    rpe: float | None = None
    odometer_km: float | None = None
    distance_km: float | None = None
    speed_kmh: float | None = None
    incline_pct: float | None = None
    notes: str | None = None
    avg_hr: float | None = None
    max_hr: int | None = None
    set_id: int | None = None
    spm: float | None = None              # remo: voga média
    pace_s: float | None = None           # remo: ritmo médio por 500 m
    resistance: int | None = None         # remo: nível 1–15
    hr: list = field(default_factory=list)
    row: dict = field(default_factory=lambda: {"m": 0.0, "spm": 0.0, "n": 0, "auto": False})

    @property
    def seconds(self) -> float:
        return (self.end_t if self.end_t is not None else self.start_t) - self.start_t

    @property
    def open(self) -> bool:
        return self.end_t is None


# ------------------------------------------------------------------ planos
#
# Um plano de voltas: [{"kind", "seconds"?, "km"?, "exercise_id"?, "name"?, "reps"?,
# "load_kg"?, "measure"?}]. O treino livre e o Conditioning fazem-se a partir
# de um plano (montado antes de começar), que se pode guardar.


def save_plan(db: Database, pid: str | None, name: str, mode: str, items: list[dict],
              hidden: bool = False) -> str:
    ensure(db)
    from .db import new_id as _nid
    pid = pid or _nid()
    db.conn.execute(
        "INSERT INTO lap_plans(id, name, mode, items, hidden, created_at) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(id) DO UPDATE SET name=excluded.name, items=excluded.items,"
        " hidden=excluded.hidden", (pid, name.strip() or "Plano", mode, json.dumps(items),
                                    int(hidden), now_iso()))
    db.conn.commit()
    return pid


def plans(db: Database, mode: str | None = None) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM lap_plans WHERE hidden = 0"
    args: list = []
    if mode:
        sql += " AND mode = ?"
        args.append(mode)
    out = []
    for r in db.conn.execute(sql + " ORDER BY created_at DESC", args):
        d = dict(r)
        d["items"] = json.loads(d["items"] or "[]")
        out.append(d)
    return out


def plan(db: Database, pid: str) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM lap_plans WHERE id = ?", (pid,)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["items"] = json.loads(d["items"] or "[]")
    return d


def delete_plan(db: Database, pid: str) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM lap_plans WHERE id = ?", (pid,))
    db.conn.commit()


def plan_seconds(items: list[dict]) -> float:
    total = 0.0
    for it in items:
        if it.get("seconds"):
            total += it["seconds"]
        elif it.get("km"):
            total += it["km"] * 360            # ~10 km/h
        elif it.get("kind") == "strength":
            total += (it.get("reps") or 10) * 3 + 10
    return total


def surprise_plan(db: Database, seed: int | None = None, rounds: int = 3) -> list[dict]:
    """Conditioning surpresa: voltas de máquina e de força alternadas."""
    import random as _r
    from . import gym
    rng = _r.Random(seed)
    strength = [e for e in gym.exercises(db, "hiit") + gym.exercises(db, "kettlebell")
                if e["measure"] == "reps" or "hiit" in e["modalities"]]
    rng.shuffle(strength)
    machines = ["treadmill", "rowing"]
    items: list[dict] = []
    for i in range(rounds):
        m = machines[i % 2] if rng.random() < 0.7 else rng.choice(machines)
        items.append({"kind": m, "seconds": rng.choice((180, 240, 300))})
        ex = strength[i % max(1, len(strength))] if strength else None
        if ex:
            items.append({"kind": "strength", "exercise_id": ex["id"], "name": ex["name"],
                          "measure": ex["measure"], "reps": 15 if ex["measure"] == "reps"
                          else 40})
        items.append({"kind": "rest", "seconds": 60})
    return items


class LapSession:
    def __init__(self, db: Database, athlete: Athlete, mode: str = "free", *,
                 sensors: Any = None, out_dir: str | Path = "strength", rower: Any = None,
                 clock: Callable[[], float] = time.monotonic, resume: dict | None = None,
                 plan: list[dict] | None = None, autolap: dict | None = None):
        ensure(db)
        st.seed(db)
        self.db = db
        self.athlete = athlete
        self.mode = mode if mode in MODES else "free"
        self.sensors = sensors
        self.rower = rower                 # máquina de remo ligada (voltas de remo)
        self.out_dir = Path(out_dir)
        from .ride import estimate_lthr
        self.lthr = estimate_lthr(athlete)
        self.hr_bounds = list(db.get("hr_zones_pct_lthr", [68, 83, 94, 105]))
        self.hr_zone_s = [0.0] * (len(self.hr_bounds) + 1)
        self.t = 0.0
        self.paused = False
        self.paused_s = 0.0
        self.hr_bpm: int | None = None
        self.laps: list[LapEntry] = []
        self.finished = False
        self.events: list[tuple[str, dict]] = []
        self._accum = 0.0
        self._pending: list[tuple[int, int | None]] = []
        self._hr_all: list[int | None] = []
        self.plan: list[dict] = list(plan or [])
        self.plan_idx = 0
        self._lap_plan: dict | None = None
        from .sports import AutoLap
        self.autolap = AutoLap(autolap)
        self.started = True
        if resume is not None:
            self.session_id = resume["session_id"]
            self.mode = resume["config"].get("mode", self.mode)
            self.plan = list(resume["config"].get("plan") or self.plan)
            self.autolap = AutoLap(resume["config"].get("autolap"))
            self.start_unix = float(resume["config"].get("start_unix") or time.time())
            self._restore(resume["state"])
        else:
            self.session_id = new_id()
            self.start_unix = time.time()
            db.conn.execute(
                "INSERT INTO strength_sessions(id, workout_id, name, status, started_at,"
                " lthr_at_session, weight_at_session_kg, mode) VALUES (?,?,?,'recording',?,?,?,?)",
                (self.session_id, None, self.title, now_iso(), self.lthr, athlete.weight_kg,
                 self.mode))
            try:
                db.conn.execute("UPDATE strength_sessions SET modality = ? WHERE id = ?",
                                ("conditioning" if self.mode == "conditioning" else "strength",
                                 self.session_id))
            except Exception:
                pass
            db.conn.commit()
            self.started = False      # o relógio só arranca com a primeira volta
            self.checkpoint()

    @property
    def title(self) -> str:
        from .i18n import t
        return t(f"laps.mode.{self.mode}")

    # compatível com o fecho da aplicação (fecha e guarda se houver voltas)
    @property
    def sets(self) -> list[LapEntry]:
        return self.laps

    @property
    def current(self) -> LapEntry | None:
        return self.laps[-1] if self.laps and self.laps[-1].open else None

    @property
    def last(self) -> LapEntry | None:
        return self.laps[-1] if self.laps else None

    # -------------------------------------------------------------- ciclo

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
        self._track_rower(dt)
        cur = self.current
        lp = self._lap_plan
        if cur is not None and lp is not None and lp.get("seconds") and \
                self.t - cur.start_t >= lp["seconds"]:
            nxt = self.next_planned
            if nxt is not None:
                self.events.append(("plan_next", {"kind": nxt["kind"]}))
                self.start_planned()
            else:
                self.close_lap()
                self._lap_plan = None
                self.events.append(("plan_done", {}))
        elif cur is not None and self.autolap.on and self.autolap.mode == "time" and \
                cur.kind != "rest" and self.t - cur.start_t >= self.autolap.value:
            self.start_lap(cur.kind)              # auto lap: nova volta do mesmo tipo
        self._accum += dt
        while self._accum >= 1.0:
            self._accum -= 1.0
            self._sample()

    def _track_rower(self, dt: float) -> None:
        """Numa volta de remo com a máquina ligada, os dados enchem-se sozinhos."""
        cur = self.current
        if cur is None or cur.kind != "rowing" or self.rower is None:
            return
        try:
            self.rower.tick(dt)
            d = self.rower.data()
        except Exception:
            d = None
        if d is None:
            return
        acc = cur.row
        acc["auto"] = True
        if d.pace_s:
            acc["m"] += 500.0 / d.pace_s * dt
        if d.spm:
            acc["spm"] += d.spm * dt
            acc["n"] += dt
        cur.distance_km = round(acc["m"] / 1000.0, 3)
        cur.spm = round(acc["spm"] / acc["n"], 1) if acc["n"] else cur.spm
        if d.resistance:
            cur.resistance = d.resistance
        secs = self.t - cur.start_t
        cur.pace_s = secs / acc["m"] * 500.0 if acc["m"] > 10 else None

    def _sample(self) -> None:
        hr = self.hr_bpm
        self._pending.append((int(self.t), hr))
        self._hr_all.append(hr)
        if hr:
            if self.lthr:
                z = physics.zone_of(hr, self.hr_bounds, self.lthr)
                self.hr_zone_s[min(z, len(self.hr_zone_s)) - 1] += 1.0
            cur = self.current
            if cur is not None:
                cur.hr.append(hr)
                cur.avg_hr = sum(cur.hr) / len(cur.hr)
                cur.max_hr = max(cur.hr)
        if len(self._pending) >= HR_FLUSH_EVERY:
            self.flush()

    def flush(self) -> None:
        if self._pending:
            self.db.conn.executemany(
                "INSERT OR REPLACE INTO strength_hr(session_id, t_s, hr_bpm) VALUES (?,?,?)",
                [(self.session_id, t, h) for t, h in self._pending])
            self.db.conn.commit()
            self._pending.clear()
        cur = self.current
        if cur is not None:
            self._save(cur)
        if not self.finished:
            self.checkpoint()

    def drain_events(self) -> list[tuple[str, dict]]:
        out, self.events = self.events, []
        return out

    @property
    def hr_zone(self) -> int | None:
        if not self.hr_bpm or not self.lthr:
            return None
        return physics.zone_of(self.hr_bpm, self.hr_bounds, self.lthr)

    @property
    def avg_hr(self) -> float | None:
        vals = [h for h in self._hr_all if h]
        return sum(vals) / len(vals) if vals else None

    # ------------------------------------------------------------- voltas

    def _prev(self, kind: str, before: LapEntry | None = None) -> LapEntry | None:
        for lap in reversed(self.laps):
            if lap is before:
                continue
            if lap.kind == kind and (before is None or lap.no < before.no):
                return lap
        return None

    def start_lap(self, kind: str, exercise: dict | None = None) -> LapEntry:
        """Fecha a volta aberta (se houver) e abre uma nova do tipo pedido."""
        if kind not in KINDS:
            raise ValueError(kind)
        self.started = True
        self._lap_plan = None
        self.close_lap()
        lap = LapEntry(0, len(self.laps) + 1, kind, self.t)
        if kind == "strength":
            prev = self._prev("strength")
            ex = exercise
            if ex is None and prev is not None:
                ex = {"id": prev.exercise_id, "name": prev.name, "measure": prev.measure,
                      "bodyweight": prev.bodyweight, "fit_category": prev.fit_category}
            if ex is not None:
                self._apply_exercise(lap, ex)
            if prev is not None and prev.exercise_id == lap.exercise_id:
                lap.reps, lap.load_kg, lap.rpe = prev.reps, prev.load_kg, None
        elif kind == "treadmill":
            prev = self._prev("treadmill")
            if prev is not None:
                lap.speed_kmh, lap.incline_pct = prev.speed_kmh, prev.incline_pct
        elif kind == "rowing":
            prev = self._prev("rowing")
            if prev is not None:
                lap.resistance = prev.resistance
        cur = self.db.conn.execute(
            "INSERT INTO strength_laps(session_id, lap_no, kind, start_t_s) VALUES (?,?,?,?)",
            (self.session_id, lap.no, kind, int(lap.start_t)))
        lap.id = int(cur.lastrowid)
        self.laps.append(lap)
        self._save(lap)
        self.paused = False
        self.events.append(("lap_start", {"no": lap.no, "kind": kind}))
        self.checkpoint()
        return lap

    def close_lap(self) -> LapEntry | None:
        cur = self.current
        if cur is None:
            return None
        cur.end_t = self.t
        self._save(cur)
        self.checkpoint()
        return cur

    # ------------------------------------------------------------ plano

    @property
    def next_planned(self) -> dict | None:
        return self.plan[self.plan_idx] if self.plan_idx < len(self.plan) else None

    def start(self) -> None:
        if not self.started:
            self.started = True
            self.events.append(("started", {}))
            self.checkpoint()

    def start_planned(self) -> LapEntry | None:
        it = self.next_planned
        if it is None:
            return None
        ex = None
        if it.get("exercise_id"):
            ex = {"id": it["exercise_id"], "name": it.get("name") or "",
                  "measure": it.get("measure") or "reps", "bodyweight": 0.0,
                  "fit_category": None}
            full = st.exercise(self.db, it["exercise_id"])
            if full:
                ex.update(bodyweight=full.get("bodyweight") or 0.0,
                          fit_category=full.get("fit_category"))
        lap = self.start_lap(it["kind"], ex)
        self.plan_idx += 1
        self._lap_plan = it
        if it.get("reps") is not None and lap.kind == "strength":
            lap.reps = it["reps"]
        if it.get("load_kg") is not None:
            lap.load_kg = it["load_kg"]
        if it.get("km") and lap.kind in ("cardio",):
            lap.distance_km = it["km"]
        self._save(lap)
        return lap

    def toggle(self) -> LapEntry:
        """Espaço: com plano, a volta seguinte do plano; sem plano, de trabalho
        para descanso e de volta ao último trabalho."""
        if self.next_planned is not None:
            return self.start_planned()
        cur = self.current or self.last
        if cur is None:
            return self.start_lap("treadmill" if self.mode == "conditioning" else "strength")
        if cur.kind == "rest" or not cur.open:
            work = next((x for x in reversed(self.laps) if x.kind != "rest"), None)
            return self.start_lap(work.kind if work else "strength")
        return self.start_lap("rest")

    def _apply_exercise(self, lap: LapEntry, ex: dict) -> None:
        lap.exercise_id = ex.get("id")
        lap.name = ex.get("name") or ""
        lap.measure = ex.get("measure") or "reps"
        lap.bodyweight = ex.get("bodyweight") or 0.0
        lap.fit_category = ex.get("fit_category")

    def set_exercise(self, ex: dict, lap: LapEntry | None = None) -> None:
        lap = lap or self.current or self.last
        if lap is None or lap.kind != "strength":
            return
        self._apply_exercise(lap, ex)
        self._save(lap)

    def editable(self) -> LapEntry | None:
        """A volta que os campos mudam: a aberta, ou a última fechada."""
        return self.current or self.last

    def set_field(self, name: str, value, lap: LapEntry | None = None) -> None:
        lap = lap or self.editable()
        if lap is None:
            return
        if name in ("reps", "resistance"):
            value = None if value is None else max(0, int(round(value)))
            if name == "resistance" and value is not None:
                value = max(1, min(15, value))
                if self.rower is not None and lap.kind == "rowing" and lap.open:
                    try:
                        self.rower.set_resistance(value)
                    except Exception:
                        pass
        elif value is not None and name != "notes":
            value = max(0.0, float(value))
            if name == "rpe":
                value = min(10.0, max(1.0, value))
        setattr(lap, name, value)
        if name == "odometer_km":
            self._recompute_distances()
        if lap.kind == "rowing" and name == "distance_km":
            secs = (lap.end_t if lap.end_t is not None else self.t) - lap.start_t
            lap.pace_s = secs / (value * 1000) * 500 if value and secs else None
        self._save(lap)

    def adjust(self, name: str, steps: int, big: bool = False) -> None:
        lap = self.editable()
        if lap is None:
            return
        cur = getattr(lap, name)
        step = {"reps": 5 if big else 1, "load_kg": 10.0 if big else 2.5,
                "rpe": 1.0 if big else 0.5, "speed_kmh": 1.0 if big else 0.1,
                "incline_pct": 1.0 if big else 0.5,
                "odometer_km": 0.1 if big else 0.01,
                "distance_km": 0.1 if big else 0.01,
                "resistance": 3 if big else 1, "spm": 2 if big else 1}[name]
        if cur is None and name == "resistance":
            prev = self._prev("rowing", lap)
            cur = prev.resistance if prev and prev.resistance else 5
        if cur is None and name == "spm":
            cur = 22
        base = cur if cur is not None else (6.5 if name == "rpe" else (
            self._guess_odometer(lap) if name == "odometer_km" else 0))
        self.set_field(name, (base or 0) + steps * step, lap)

    def _guess_odometer(self, lap: LapEntry) -> float:
        prev = self._prev("treadmill", lap)
        base = prev.odometer_km if prev and prev.odometer_km else 0.0
        if lap.speed_kmh:
            base += lap.speed_kmh * lap.seconds / 3600.0
        return round(base, 2)

    def _recompute_distances(self) -> None:
        """Distância de cada volta de passadeira = total no visor − total anterior."""
        prev_total = 0.0
        for lap in self.laps:
            if lap.kind != "treadmill":
                continue
            if lap.odometer_km is not None:
                lap.distance_km = round(max(0.0, lap.odometer_km - prev_total), 3)
                prev_total = lap.odometer_km
                self._save(lap)

    def _save(self, lap: LapEntry) -> None:
        if lap.kind == "strength" and lap.exercise_id is not None and (
                lap.reps is not None or lap.load_kg is not None):
            set_no = sum(1 for x in self.laps if x.kind == "strength"
                         and x.exercise_id == lap.exercise_id and x.no <= lap.no)
            vals = (lap.reps or 0, lap.load_kg, lap.rpe, int(lap.start_t),
                    int(lap.end_t if lap.end_t is not None else self.t), lap.avg_hr, lap.max_hr)
            if lap.set_id is None:
                cur = self.db.conn.execute(
                    "INSERT INTO strength_sets(session_id, item_idx, exercise_id, set_no, reps,"
                    " load_kg, rpe, start_t_s, end_t_s, avg_hr, max_hr) VALUES"
                    " (?,?,?,?,?,?,?,?,?,?,?)",
                    (self.session_id, None, lap.exercise_id, set_no) + vals)
                lap.set_id = int(cur.lastrowid)
            else:
                self.db.conn.execute(
                    "UPDATE strength_sets SET exercise_id=?, set_no=?, reps=?, load_kg=?, rpe=?,"
                    " start_t_s=?, end_t_s=?, avg_hr=?, max_hr=? WHERE id = ?",
                    (lap.exercise_id, set_no) + vals + (lap.set_id,))
        self.db.conn.execute(
            "UPDATE strength_laps SET kind=?, start_t_s=?, end_t_s=?, exercise_id=?, reps=?,"
            " load_kg=?, rpe=?, odometer_km=?, distance_km=?, speed_kmh=?, incline_pct=?,"
            " notes=?, avg_hr=?, max_hr=?, set_id=?, row_spm=?, row_pace_s=?, row_resistance=?"
            " WHERE id = ?",
            (lap.kind, int(lap.start_t), None if lap.end_t is None else int(lap.end_t),
             lap.exercise_id, lap.reps, lap.load_kg, lap.rpe, lap.odometer_km,
             lap.distance_km, lap.speed_kmh, lap.incline_pct, lap.notes, lap.avg_hr,
             lap.max_hr, lap.set_id, lap.spm, lap.pace_s, lap.resistance, lap.id))
        self.db.conn.commit()

    def delete_last(self) -> None:
        lap = self.last
        if lap is None:
            return
        if lap.set_id:
            self.db.conn.execute("DELETE FROM strength_sets WHERE id = ?", (lap.set_id,))
        self.db.conn.execute("DELETE FROM strength_laps WHERE id = ?", (lap.id,))
        self.db.conn.commit()
        self.laps.pop()
        self.checkpoint()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.checkpoint()

    # -------------------------------------------------------- recuperação

    def checkpoint(self) -> None:
        try:
            self.db.save_checkpoint(self.session_id, "strength_laps",
                                    {"mode": self.mode, "start_unix": self.start_unix,
                                     "name": self.title, "plan": self.plan,
                                     "autolap": self.autolap.as_dict()},
                                    {"t": self.t, "paused_s": self.paused_s,
                                     "hr_zone_s": self.hr_zone_s, "plan_idx": self.plan_idx,
                                     "started": self.started})
        except Exception:
            pass

    def _restore(self, snap: dict) -> None:
        self.plan_idx = int(snap.get("plan_idx", 0))
        self.t = float(snap.get("t", 0.0))
        self.paused_s = float(snap.get("paused_s", 0.0))
        z = snap.get("hr_zone_s")
        if z and len(z) == len(self.hr_zone_s):
            self.hr_zone_s = [float(v) for v in z]
        exs = {e["id"]: e for e in st.exercises(self.db)}
        for r in self.db.conn.execute(
                "SELECT * FROM strength_laps WHERE session_id = ? ORDER BY lap_no",
                (self.session_id,)):
            ex = exs.get(r["exercise_id"]) or {}
            self.laps.append(LapEntry(
                r["id"], r["lap_no"], r["kind"], float(r["start_t_s"]),
                None if r["end_t_s"] is None else float(r["end_t_s"]),
                r["exercise_id"], ex.get("name", ""), ex.get("measure") or "reps",
                ex.get("bodyweight") or 0.0, ex.get("fit_category"), r["reps"], r["load_kg"],
                r["rpe"], r["odometer_km"], r["distance_km"], r["speed_kmh"],
                r["incline_pct"], r["notes"], r["avg_hr"], r["max_hr"], r["set_id"],
                r["row_spm"], r["row_pace_s"], r["row_resistance"]))
        for r in self.db.conn.execute(
                "SELECT t_s, hr_bpm FROM strength_hr WHERE session_id = ? ORDER BY t_s",
                (self.session_id,)):
            self._hr_all.append(r["hr_bpm"])
            self.t = max(self.t, float(r["t_s"]))
        # a volta que estava aberta fecha-se no último instante gravado
        if self.laps and self.laps[-1].open:
            self.laps[-1].end_t = max(self.laps[-1].start_t, self.t)
            self._save(self.laps[-1])
        self.paused = True
        self.events.append(("recovered", {"t_s": self.t, "laps": len(self.laps)}))

    def suspend(self) -> None:
        if not self.finished:
            try:
                self.flush()
            except Exception:
                pass

    # ---------------------------------------------------------------- fim

    def summary(self) -> dict:
        body = self.athlete.weight_kg
        by_kind = {k: 0.0 for k in KINDS}
        volume = 0.0
        sets = reps = 0
        dist = 0.0
        rpes = []
        for lap in self.laps:
            by_kind[lap.kind] += lap.seconds
            if lap.kind == "strength" and lap.reps is not None:
                sets += 1
                reps += lap.reps
                volume += st.set_volume(lap.load_kg, lap.reps, lap.bodyweight, body, lap.measure)
                if lap.rpe:
                    rpes.append(lap.rpe)
            if lap.kind in ("treadmill", "cardio", "rowing") and lap.distance_km:
                dist += lap.distance_km
        avg_rpe = sum(rpes) / len(rpes) if rpes else None
        load = st.hr_load(self._hr_all, self.lthr)
        source = "hr"
        hr_n = sum(1 for h in self._hr_all if h)
        if load is None or hr_n < 0.5 * max(1, len(self._hr_all)):
            alt = st.rpe_load(self.t, avg_rpe)
            if alt is not None:
                load, source = alt, "rpe"
        vals = [h for h in self._hr_all if h]
        return {"elapsed_s": int(self.t), "paused_s": int(self.paused_s),
                "laps": list(self.laps), "time_by_kind": by_kind, "total_sets": sets,
                "total_reps": reps, "volume_kg": volume, "distance_km": dist,
                "avg_rpe": avg_rpe, "avg_hr": sum(vals) / len(vals) if vals else None,
                "max_hr": max(vals) if vals else None, "load": load,
                "load_source": source if load is not None else None,
                "hr_zone_s": list(self.hr_zone_s), "mode": self.mode}

    def finish(self) -> dict:
        if self.finished:
            return {}
        self.close_lap()
        self.flush()
        self.finished = True
        summ = self.summary()
        base = naming.activity_name(self.start_unix, workout_name=self.title,
                                    kind=self.mode)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path, name = naming.unique_path(self.out_dir, base)
        fit_path = None
        try:
            from . import fit
            hr_rows = self.db.conn.execute(
                "SELECT t_s, hr_bpm FROM strength_hr WHERE session_id = ? ORDER BY t_s",
                (self.session_id,)).fetchall()
            fit.write_lap_session(path, self.athlete, [(r["t_s"], r["hr_bpm"]) for r in hr_rows],
                                  self.laps, summ, start_unix=self.start_unix, name=name)
            fit_path = str(path)
        except Exception as e:
            self.events.append(("fit_error", {"message": str(e)}))
        self.db.conn.execute(
            "UPDATE strength_sessions SET status='completed', ended_at=?, elapsed_s=?,"
            " paused_s=?, total_sets=?, total_reps=?, volume_kg=?, avg_rpe=?, avg_hr=?,"
            " max_hr=?, load=?, load_source=?, hr_zone_s=?, fit_path=?, name=?, distance_km=?"
            " WHERE id = ?",
            (now_iso(), summ["elapsed_s"], summ["paused_s"], summ["total_sets"],
             summ["total_reps"], summ["volume_kg"], summ["avg_rpe"], summ["avg_hr"],
             summ["max_hr"], summ["load"], summ["load_source"], json.dumps(summ["hr_zone_s"]),
             fit_path, name, summ["distance_km"], self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)
        summ.update(session_id=self.session_id, name=name, fit_path=fit_path,
                    title=self.title)
        return summ

    def abort(self) -> None:
        self.finished = True
        self.db.conn.execute("UPDATE strength_sessions SET status='aborted', ended_at=?"
                             " WHERE id = ?", (now_iso(), self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)
