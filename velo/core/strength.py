"""Treino de força: exercícios, planos de treino, sessão e histórico.

Uma sessão segue um plano (lista de exercícios com séries, repetições, carga,
RPE alvo e descanso). Para cada série regista-se o que se fez de facto —
repetições, carga e RPE — e a frequência cardíaca, que chega de uma banda
cardíaca ou de um relógio que a transmita (o Garmin Swim 2 transmite por ANT+).

Como no ciclismo, nada aqui desenha nem fala com sensores: lê a FC de um
objeto com `.reading()` e grava tudo na base local. Isso permite testar sem
hardware e retomar a sessão se a aplicação fechar de repente.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from . import naming, physics
from .db import Athlete, Database, new_id, now_iso

# --------------------------------------------------------------- exercícios

# (nome, grupo, categoria FIT, fração do peso do corpo, medida)
# A categoria FIT é a «família» de exercício que o Garmin Connect reconhece
# (supino, agachamento, remada…). A fração do peso do corpo entra no volume
# de exercícios sem carga externa (elevações ≈ 100 %, flexões ≈ 65 %).
# Medida: «reps» (repetições) ou «time» (segundos, para pranchas e afins).
FIT_CATEGORY = {
    "bench_press": 0, "calf_raise": 1, "cardio": 2, "carry": 3, "chop": 4, "core": 5,
    "crunch": 6, "curl": 7, "deadlift": 8, "flye": 9, "hip_raise": 10,
    "hip_stability": 11, "hip_swing": 12, "hyperextension": 13, "lateral_raise": 14,
    "leg_curl": 15, "leg_raise": 16, "lunge": 17, "olympic_lift": 18, "plank": 19,
    "plyo": 20, "pull_up": 21, "push_up": 22, "row": 23, "shoulder_press": 24,
    "shoulder_stability": 25, "shrug": 26, "sit_up": 27, "squat": 28, "total_body": 29,
    "triceps_extension": 30, "warm_up": 31, "unknown": 65534,
}

GROUPS = ("legs", "hips", "chest", "back", "shoulders", "arms", "core", "full", "mobility")

EXERCISES: tuple[tuple[str, str, str, float, str], ...] = (
    ("Agachamento com barra", "legs", "squat", 0.0, "reps"),
    ("Agachamento frontal", "legs", "squat", 0.0, "reps"),
    ("Agachamento goblet", "legs", "squat", 0.0, "reps"),
    ("Agachamento búlgaro", "legs", "lunge", 0.0, "reps"),
    ("Prensa de pernas", "legs", "squat", 0.0, "reps"),
    ("Afundos", "legs", "lunge", 0.0, "reps"),
    ("Step-up", "legs", "lunge", 0.0, "reps"),
    ("Extensão de pernas", "legs", "unknown", 0.0, "reps"),
    ("Curl femoral", "legs", "leg_curl", 0.0, "reps"),
    ("Elevação de gémeos", "legs", "calf_raise", 0.0, "reps"),
    ("Peso morto", "hips", "deadlift", 0.0, "reps"),
    ("Peso morto romeno", "hips", "deadlift", 0.0, "reps"),
    ("Hip thrust", "hips", "hip_raise", 0.0, "reps"),
    ("Ponte de glúteos", "hips", "hip_raise", 0.5, "reps"),
    ("Kettlebell swing", "hips", "hip_swing", 0.0, "reps"),
    ("Abdução de anca (banda)", "hips", "hip_stability", 0.0, "reps"),
    ("Hiperextensão lombar", "hips", "hyperextension", 0.5, "reps"),
    ("Supino com barra", "chest", "bench_press", 0.0, "reps"),
    ("Supino inclinado com halteres", "chest", "bench_press", 0.0, "reps"),
    ("Flexões", "chest", "push_up", 0.65, "reps"),
    ("Aberturas com halteres", "chest", "flye", 0.0, "reps"),
    ("Elevações (pull-ups)", "back", "pull_up", 1.0, "reps"),
    ("Puxada ao peito", "back", "pull_up", 0.0, "reps"),
    ("Remada com barra", "back", "row", 0.0, "reps"),
    ("Remada com halter", "back", "row", 0.0, "reps"),
    ("Remada sentada (cabo)", "back", "row", 0.0, "reps"),
    ("Remada invertida", "back", "row", 0.6, "reps"),
    ("Encolhimentos", "back", "shrug", 0.0, "reps"),
    ("Press militar", "shoulders", "shoulder_press", 0.0, "reps"),
    ("Press de ombros com halteres", "shoulders", "shoulder_press", 0.0, "reps"),
    ("Elevações laterais", "shoulders", "lateral_raise", 0.0, "reps"),
    ("Face pull", "shoulders", "shoulder_stability", 0.0, "reps"),
    ("Curl de bíceps", "arms", "curl", 0.0, "reps"),
    ("Extensão de tríceps", "arms", "triceps_extension", 0.0, "reps"),
    ("Fundos (dips)", "arms", "triceps_extension", 1.0, "reps"),
    ("Prancha", "core", "plank", 0.0, "time"),
    ("Prancha lateral", "core", "plank", 0.0, "time"),
    ("Dead bug", "core", "core", 0.0, "reps"),
    ("Pallof press", "core", "chop", 0.0, "reps"),
    ("Elevação de pernas", "core", "leg_raise", 0.0, "reps"),
    ("Abdominais (crunch)", "core", "crunch", 0.0, "reps"),
    ("Farmer's carry", "full", "carry", 0.0, "time"),
    ("Turkish get-up", "full", "total_body", 0.0, "reps"),
    ("Burpees", "full", "total_body", 0.0, "reps"),
    ("Saltos para caixa", "full", "plyo", 0.0, "reps"),
    ("Equilíbrio numa perna", "mobility", "hip_stability", 0.0, "time"),
    ("Mobilidade / aquecimento", "mobility", "warm_up", 0.0, "time"),
)

# Planos que vêm com a aplicação. Três sessões que cobrem os padrões de
# movimento principais (agachar, dobrar a anca, empurrar, puxar, carregar) e
# o equilíbrio — a base que a investigação associa à longevidade.
# (nome, descrição, [(exercício, séries, reps, carga, RPE, descanso)])
TEMPLATES = (
    ("Força A · corpo inteiro",
     "Agachar, empurrar, puxar e core. 45–60 min.",
     [("Mobilidade / aquecimento", 1, 300, None, None, 30),
      ("Agachamento com barra", 4, 6, 60.0, 7.5, 150),
      ("Supino com barra", 4, 6, 50.0, 7.5, 150),
      ("Remada com halter", 3, 10, 22.0, 7.5, 90),
      ("Peso morto romeno", 3, 8, 60.0, 7.0, 120),
      ("Prancha", 3, 45, None, 7.0, 60)]),
    ("Força B · corpo inteiro",
     "Dobrar a anca, puxar na vertical, ombros e carregar. 45–60 min.",
     [("Mobilidade / aquecimento", 1, 300, None, None, 30),
      ("Peso morto", 4, 5, 80.0, 7.5, 180),
      ("Elevações (pull-ups)", 4, 6, None, 8.0, 120),
      ("Press militar", 3, 8, 30.0, 7.5, 120),
      ("Agachamento búlgaro", 3, 8, 12.0, 7.5, 90),
      ("Farmer's carry", 3, 40, 24.0, 7.5, 90)]),
    ("Longevidade · força e equilíbrio",
     "Exercícios de base com carga moderada, equilíbrio e estabilidade. 35–45 min.",
     [("Mobilidade / aquecimento", 1, 300, None, None, 30),
      ("Agachamento goblet", 3, 10, 16.0, 7.0, 90),
      ("Hip thrust", 3, 10, 40.0, 7.0, 90),
      ("Flexões", 3, 10, None, 7.0, 75),
      ("Remada invertida", 3, 10, None, 7.0, 75),
      ("Step-up", 3, 8, 8.0, 7.0, 75),
      ("Equilíbrio numa perna", 3, 30, None, None, 30),
      ("Pallof press", 3, 10, 7.5, 6.5, 60)]),
)


def seed(db: Database) -> None:
    """Exercícios e planos de base, uma vez só. Apagados não voltam."""
    if not db.get("strength_seeded", False):
        _ensure_measure_column(db)
        if db.conn.execute("SELECT COUNT(*) AS n FROM exercises").fetchone()["n"] == 0:
            db.conn.executemany(
                "INSERT INTO exercises(name, category, fit_category, bodyweight, measure,"
                " custom) VALUES (?,?,?,?,?,0)",
                [(n, g, FIT_CATEGORY[c], bw, m) for n, g, c, bw, m in EXERCISES])
        db.conn.commit()
        by_name = {r["name"]: r["id"] for r in exercises(db)}
        for name, desc, items in TEMPLATES:
            save_workout(db, None, name, desc, [
                {"exercise_id": by_name[e], "sets": s, "reps": r, "load_kg": ld, "rpe": rpe,
                 "rest_s": rest} for e, s, r, ld, rpe, rest in items if e in by_name])
        db.set("strength_seeded", True)
    _ensure_measure_column(db)


def _ensure_measure_column(db: Database) -> None:
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(exercises)")}
    if "measure" not in cols:
        db.conn.execute("ALTER TABLE exercises ADD COLUMN measure TEXT NOT NULL DEFAULT 'reps'")
        db.conn.commit()


def exercises(db: Database, group: str | None = None) -> list[dict]:
    _ensure_measure_column(db)
    sql = "SELECT * FROM exercises"
    params: list = []
    if group:
        sql += " WHERE category = ?"
        params.append(group)
    sql += " ORDER BY custom DESC, category, name"
    return [dict(r) for r in db.conn.execute(sql, params)]


def exercise(db: Database, exercise_id: int) -> dict | None:
    _ensure_measure_column(db)
    r = db.conn.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    return dict(r) if r else None


def add_exercise(db: Database, name: str, group: str = "full", bodyweight: float = 0.0,
                 measure: str = "reps") -> int:
    _ensure_measure_column(db)
    name = name.strip() or "Exercício"
    fit_cat = {"legs": "squat", "hips": "deadlift", "chest": "bench_press", "back": "row",
               "shoulders": "shoulder_press", "arms": "curl", "core": "core",
               "full": "total_body", "mobility": "warm_up"}.get(group, "unknown")
    cur = db.conn.execute(
        "INSERT INTO exercises(name, category, fit_category, bodyweight, custom, measure)"
        " VALUES (?,?,?,?,1,?)", (name, group, FIT_CATEGORY[fit_cat], bodyweight, measure))
    db.conn.commit()
    return int(cur.lastrowid)


# ---------------------------------------------------------------- planos


@dataclass
class PlanItem:
    exercise_id: int
    name: str
    sets: int = 3
    reps: int = 10
    load_kg: float | None = None
    rpe: float | None = None
    rest_s: int = 90
    notes: str | None = None
    bodyweight: float = 0.0
    measure: str = "reps"
    fit_category: int | None = None

    def as_dict(self) -> dict:
        return {"exercise_id": self.exercise_id, "sets": self.sets, "reps": self.reps,
                "load_kg": self.load_kg, "rpe": self.rpe, "rest_s": self.rest_s,
                "notes": self.notes}

    def target_text(self) -> str:
        unit = "s" if self.measure == "time" else ""
        load = f" @ {self.load_kg:g} kg" if self.load_kg else ""
        rpe = f" · RPE {self.rpe:g}" if self.rpe else ""
        return f"{self.sets} × {self.reps}{unit}{load}{rpe}"


def workouts(db: Database) -> list[dict]:
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(strength_workouts)")}
    hide = " WHERE COALESCE(w.hidden, 0) = 0" if "hidden" in cols else ""
    rows = db.conn.execute(
        "SELECT w.*, (SELECT COUNT(*) FROM strength_workout_items i"
        " WHERE i.workout_id = w.id) AS n_items,"
        " (SELECT COALESCE(SUM(i.sets), 0) FROM strength_workout_items i"
        " WHERE i.workout_id = w.id) AS n_sets,"
        " (SELECT MAX(s.started_at) FROM strength_sessions s WHERE s.workout_id = w.id"
        " AND s.status = 'completed') AS last_done"
        " FROM strength_workouts w" + hide +
        " ORDER BY COALESCE(w.updated_at, w.created_at) DESC")
    return [dict(r) for r in rows]


def workout(db: Database, workout_id: str) -> dict | None:
    r = db.conn.execute("SELECT * FROM strength_workouts WHERE id = ?",
                        (workout_id,)).fetchone()
    return dict(r) if r else None


def workout_items(db: Database, workout_id: str) -> list[PlanItem]:
    _ensure_measure_column(db)
    rows = db.conn.execute(
        "SELECT i.*, e.name, e.bodyweight, e.measure, e.fit_category"
        " FROM strength_workout_items i JOIN exercises e ON e.id = i.exercise_id"
        " WHERE i.workout_id = ? ORDER BY i.idx", (workout_id,)).fetchall()
    return [PlanItem(exercise_id=r["exercise_id"], name=r["name"], sets=r["sets"],
                     reps=r["reps"], load_kg=r["load_kg"], rpe=r["rpe"], rest_s=r["rest_s"],
                     notes=r["notes"], bodyweight=r["bodyweight"] or 0.0,
                     measure=r["measure"] or "reps", fit_category=r["fit_category"])
            for r in rows]


def save_workout(db: Database, workout_id: str | None, name: str, description: str | None,
                 items: Sequence[dict]) -> str:
    """Cria (sem id) ou grava por cima. Os itens vão todos de novo."""
    name = (name or "").strip() or "Treino de força"
    if workout_id is None:
        workout_id = new_id()
        db.conn.execute("INSERT INTO strength_workouts(id, name, description, updated_at)"
                        " VALUES (?,?,?,?)", (workout_id, name, description, now_iso()))
    else:
        db.conn.execute("UPDATE strength_workouts SET name=?, description=?, updated_at=?"
                        " WHERE id = ?", (name, description, now_iso(), workout_id))
        db.conn.execute("DELETE FROM strength_workout_items WHERE workout_id = ?",
                        (workout_id,))
        # gravado pela lista simples: a estrutura por blocos (se havia) deixa de valer;
        # o construtor por blocos volta a gravá-la logo a seguir
        try:
            db.conn.execute("DELETE FROM strength_structures WHERE workout_id = ?",
                            (workout_id,))
        except Exception:
            pass
    db.conn.executemany(
        "INSERT INTO strength_workout_items(workout_id, idx, exercise_id, sets, reps,"
        " load_kg, rpe, rest_s, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        [(workout_id, i, int(it["exercise_id"]), max(1, int(it.get("sets") or 1)),
          max(1, int(it.get("reps") or 1)), it.get("load_kg"), it.get("rpe"),
          max(0, int(it.get("rest_s") or 0)), it.get("notes"))
         for i, it in enumerate(items)])
    db.conn.commit()
    return workout_id


def delete_workout(db: Database, workout_id: str) -> None:
    db.conn.execute("DELETE FROM strength_workouts WHERE id = ?", (workout_id,))
    db.conn.commit()


def plan_seconds(items: Sequence[PlanItem]) -> int:
    """Duração estimada: ~3 s por repetição (ou o tempo pedido) mais descansos."""
    total = 0
    for it in items:
        work = it.reps if it.measure == "time" else it.reps * 3 + 10
        total += it.sets * (work + it.rest_s)
    return total


# ----------------------------------------------------------- cálculos


def e1rm(load_kg: float | None, reps: int | None, rpe: float | None = None) -> float | None:
    """Uma repetição máxima estimada (Epley), contando as repetições que
    ficaram por fazer: RPE 8 = 2 em reserva. Só faz sentido até ~12."""
    if not load_kg or not reps or reps <= 0:
        return None
    rir = max(0.0, 10.0 - rpe) if rpe else 0.0
    total = reps + rir
    if total > 15:
        return None
    if total <= 1:
        return float(load_kg)
    return load_kg * (1.0 + total / 30.0)


def set_volume(load_kg: float | None, reps: int, bodyweight_frac: float,
               body_kg: float | None, measure: str = "reps") -> float:
    """Volume de uma série em kg (carga × repetições). O peso do corpo entra
    na fração que o exercício move; séries por tempo não contam."""
    if measure == "time":
        return 0.0
    moved = (load_kg or 0.0) + bodyweight_frac * (body_kg or 0.0)
    return moved * max(0, reps)


def hr_load(hr: Sequence[int | None], lthr: int | None) -> float | None:
    """Carga pela FC, na mesma escala que a TSS: uma hora no limiar = 100."""
    if not lthr:
        return None
    vals = [h for h in hr if h]
    if not vals:
        return None
    return sum((h / lthr) ** 2 for h in vals) / 3600.0 * 100.0


def rpe_load(seconds: float, avg_rpe: float | None) -> float | None:
    """Sem FC: o esforço percebido faz de intensidade (RPE 10 ≈ limiar)."""
    if not avg_rpe or seconds <= 0:
        return None
    return seconds / 3600.0 * (avg_rpe / 10.0) ** 2 * 100.0


# ---------------------------------------------------------------- sessão

READY, WORK, REST, DONE = "ready", "work", "rest", "done"
HR_FLUSH_EVERY = 5
LOAD_STEP = 2.5
RPE_STEP = 0.5


@dataclass
class LoggedSet:
    id: int
    item_idx: int
    exercise_id: int
    set_no: int
    reps: int
    load_kg: float | None
    rpe: float | None
    start_t: int
    end_t: int
    avg_hr: float | None = None
    max_hr: int | None = None


class StrengthSession:
    """Corre um plano de força. Chamar `update(dt)` a cada frame.

    Fases: READY (à espera de começar a série), WORK (série a decorrer),
    REST (descanso, com contagem decrescente) e DONE (plano cumprido; ainda
    se podem juntar séries). `action()` passa à fase seguinte.

    Os campos `entry` (repetições, carga, RPE) começam com o que o plano
    pede. Durante o descanso, mudá-los corrige a série que acabou de ser
    registada — é quando se sabe quantas saíram e quão duro foi.
    """

    def __init__(self, db: Database, athlete: Athlete, workout_id: str, *,
                 sensors: Any = None, out_dir: str | Path = "strength",
                 clock: Callable[[], float] = time.monotonic,
                 resume: dict | None = None):
        self.db = db
        self.athlete = athlete
        self.workout_id = workout_id
        self.sensors = sensors
        self.out_dir = Path(out_dir)
        self._clock = clock
        wk = workout(db, workout_id) or {"name": "Força", "id": workout_id}
        self.workout_name = wk["name"]
        self.items = workout_items(db, workout_id)
        if not self.items:
            raise ValueError("o treino não tem exercícios")
        # treino feito no construtor por blocos: ordem das séries (supersets,
        # circuitos) e o alvo de cada série
        self.order: list[tuple[int, int]] | None = None
        self.labels: list[str] | None = None
        self.targets: list[list[dict]] | None = None
        self.struct: dict | None = None
        try:
            from . import strength_builder as sb
            struct = sb.stored(db, workout_id)
            if struct is not None:
                tg = sb.set_targets(struct, sb.e1rm_map(db))
                if len(tg) == len(self.items):
                    self.struct, self.targets, self.order = struct, tg, sb.sequence(struct)
                    self.labels = [sb.label(bi, ei, b) for bi, b in enumerate(struct["blocks"])
                                   for ei in range(len(b["exercises"]))]
        except Exception:
            self.order = self.targets = self.struct = None
        from .ride import estimate_lthr
        self.lthr = estimate_lthr(athlete)
        self.hr_bounds = list(db.get("hr_zones_pct_lthr", [68, 83, 94, 105]))
        self.hr_zone_s = [0.0] * (len(self.hr_bounds) + 1)

        self.t = 0.0
        self.paused = False
        self.paused_s = 0.0
        self.phase = READY
        self.item_idx = 0
        self.extra: dict[int, int] = {}          # séries a mais por exercício
        self.skipped: set[int] = set()
        self.sets: list[LoggedSet] = []
        self.carry_load: dict[int, float | None] = {}
        self.set_start_t = 0.0
        self.rest_until = 0.0
        self.hr_bpm: int | None = None
        self.finished = False
        self.events: list[tuple[str, dict]] = []
        self._accum = 0.0
        self._pending: list[tuple[int, int | None]] = []
        self._hr_all: list[int | None] = []
        self._set_hr: list[int] = []
        self._hr_sum = 0.0
        self._hr_n = 0
        self._max_hr = 0
        self.entry: dict[str, Any] = {}

        if resume is not None:
            self.session_id = resume["session_id"]
            self.start_unix = float(resume["config"].get("start_unix") or time.time())
            self._restore(resume["state"])
        else:
            self.session_id = new_id()
            self.start_unix = time.time()
            db.conn.execute(
                "INSERT INTO strength_sessions(id, workout_id, name, status, started_at,"
                " lthr_at_session, weight_at_session_kg) VALUES (?,?,?,'recording',?,?,?)",
                (self.session_id, workout_id, self.workout_name, now_iso(), self.lthr,
                 athlete.weight_kg))
            try:
                db.conn.execute("UPDATE strength_sessions SET modality = (SELECT modality FROM"
                                " strength_workouts WHERE id = ?) WHERE id = ?",
                                (workout_id, self.session_id))
            except Exception:
                pass
            db.conn.commit()
            self.started = False
            self._prefill()
            self.checkpoint()

    # ------------------------------------------------------------ plano

    @property
    def item(self) -> PlanItem:
        return self.items[self.item_idx]

    def planned_sets(self, idx: int) -> int:
        return self.items[idx].sets + self.extra.get(idx, 0)

    def done_sets(self, idx: int) -> int:
        return sum(1 for s in self.sets if s.item_idx == idx)

    def remaining(self, idx: int) -> int:
        if idx in self.skipped:
            return 0
        return max(0, self.planned_sets(idx) - self.done_sets(idx))

    @property
    def set_no(self) -> int:
        """Número da série que vem (ou que está a decorrer)."""
        return self.done_sets(self.item_idx) + 1

    def target(self, idx: int, set_index: int) -> dict | None:
        """O alvo da série `set_index` (0, 1, …) do exercício `idx`, se o plano
        foi feito por blocos."""
        if self.targets is None or not (0 <= idx < len(self.targets)):
            return None
        tg = self.targets[idx]
        return tg[set_index] if 0 <= set_index < len(tg) else None

    def _next_in_order(self) -> int | None:
        """A série seguinte pela ordem do plano por blocos (supersets alternam)."""
        if not self.order:
            return None
        seen: dict[int, int] = {}
        for item, _s in self.order:
            seen[item] = seen.get(item, 0) + 1
            if item in self.skipped:
                continue
            if seen[item] > self.done_sets(item):
                return item
        for idx in range(len(self.items)):          # séries a mais, fora da ordem
            if self.remaining(idx) > 0:
                return idx
        return None

    def next_item(self, after: int | None = None) -> int | None:
        if self.order and after is None:
            nxt = self._next_in_order()
            if nxt is not None and nxt != self.item_idx:
                return nxt
        start = self.item_idx if after is None else after
        n = len(self.items)
        for k in range(1, n + 1):
            idx = (start + k) % n
            if self.remaining(idx) > 0:
                return idx
        return None

    def _prefill(self) -> None:
        it = self.item
        load = self.carry_load.get(self.item_idx, it.load_kg)
        reps, rpe = it.reps, it.rpe
        tg = self.target(self.item_idx, self.done_sets(self.item_idx))
        if tg is not None:
            reps = tg.get("reps") or reps
            load = tg["load_kg"] if tg.get("load_kg") is not None else load
            rpe = tg["rpe"] if tg.get("rpe") is not None else rpe
        self.entry = {"reps": reps, "load_kg": load, "rpe": rpe}

    def _rest_after(self, idx: int, set_index: int) -> int:
        if self.struct is not None:
            try:
                from . import strength_builder as sb
                return sb.set_rest(self.struct, idx, set_index)
            except Exception:
                pass
        return self.items[idx].rest_s

    def _advance_if_complete(self) -> None:
        if self.order:
            nxt = self._next_in_order()
            if nxt is None:
                self.phase = DONE if self.phase != REST else REST
            else:
                self.item_idx = nxt
                if self.phase == REST:
                    self._prefill()
            return
        if self.remaining(self.item_idx) > 0:
            return
        nxt = self.next_item()
        if nxt is None:
            self.phase = DONE if self.phase != REST else REST
            return
        self.item_idx = nxt

    @property
    def all_done(self) -> bool:
        return all(self.remaining(i) == 0 for i in range(len(self.items)))

    # ------------------------------------------------------------ ciclo

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
            return                    # o relógio só arranca com a primeira série
        if self.paused:
            self.paused_s += dt
            return
        self.t += dt
        if self.phase == REST and self.t >= self.rest_until and not self._rest_done_sent:
            self._rest_done_sent = True
            self._emit("rest_done")
        self._accum += dt
        while self._accum >= 1.0:
            self._accum -= 1.0
            self._sample()

    _rest_done_sent = False

    def _sample(self) -> None:
        hr = self.hr_bpm
        self._pending.append((int(self.t), hr))
        self._hr_all.append(hr)
        if hr:
            self._hr_sum += hr
            self._hr_n += 1
            self._max_hr = max(self._max_hr, hr)
            if self.lthr:
                z = physics.zone_of(hr, self.hr_bounds, self.lthr)
                self.hr_zone_s[min(z, len(self.hr_zone_s)) - 1] += 1.0
            if self.phase == WORK:
                self._set_hr.append(hr)
        if len(self._pending) >= HR_FLUSH_EVERY:
            self.flush()

    def flush(self) -> None:
        if self._pending:
            self.db.conn.executemany(
                "INSERT OR REPLACE INTO strength_hr(session_id, t_s, hr_bpm) VALUES (?,?,?)",
                [(self.session_id, t, h) for t, h in self._pending])
            self.db.conn.commit()
            self._pending.clear()
        if not self.finished:
            self.checkpoint()

    def _emit(self, kind: str, **data: Any) -> None:
        self.events.append((kind, data))

    def drain_events(self) -> list[tuple[str, dict]]:
        out, self.events = self.events, []
        return out

    @property
    def avg_hr(self) -> float | None:
        return self._hr_sum / self._hr_n if self._hr_n else None

    @property
    def hr_zone(self) -> int | None:
        if not self.hr_bpm or not self.lthr:
            return None
        return physics.zone_of(self.hr_bpm, self.hr_bounds, self.lthr)

    @property
    def phase_seconds(self) -> float:
        """Tempo da série a decorrer, ou o descanso que falta (negativo = passou)."""
        if self.phase == WORK:
            return self.t - self.set_start_t
        if self.phase == REST:
            return self.rest_until - self.t
        return 0.0

    # ---------------------------------------------------------- ações

    def action(self) -> str:
        """O botão principal: começar a série, terminá-la, ou começar a seguinte."""
        if self.phase in (READY, REST):
            if self.phase == REST and self.all_done:
                self.phase = DONE
                return self.phase
            self.start_set()
        elif self.phase == WORK:
            self.end_set()
        return self.phase

    started = True              # nas sessões novas passa a False até à 1.ª série

    def start_set(self) -> None:
        if self.finished:
            return
        self.started = True
        if self.remaining(self.item_idx) == 0:
            nxt = self._next_in_order() if self.order else self.next_item()
            if nxt is None:
                # plano cumprido: mais uma série do exercício atual
                self.extra[self.item_idx] = self.extra.get(self.item_idx, 0) + 1
            else:
                self.item_idx = nxt
        if self.phase == REST:
            self._prefill()
        self.phase = WORK
        self.paused = False
        self.set_start_t = self.t
        self._set_hr = []
        self._emit("set_start", item=self.item_idx, set_no=self.set_no)

    def end_set(self) -> LoggedSet | None:
        if self.phase != WORK:
            return None
        it = self.item
        reps = int(self.entry.get("reps") or it.reps)
        load = self.entry.get("load_kg")
        rpe = self.entry.get("rpe")
        hr = self._set_hr
        avg = sum(hr) / len(hr) if hr else None
        mx = max(hr) if hr else None
        set_no = self.set_no
        tg = self.target(self.item_idx, set_no - 1)
        plan_reps = (tg.get("reps") if tg else None) or it.reps
        plan_load = tg.get("load_kg") if tg and tg.get("load_kg") is not None else it.load_kg
        cur = self.db.conn.execute(
            "INSERT INTO strength_sets(session_id, item_idx, exercise_id, set_no, reps,"
            " load_kg, rpe, start_t_s, end_t_s, avg_hr, max_hr, planned_reps,"
            " planned_load_kg) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.session_id, self.item_idx, it.exercise_id, set_no, reps, load, rpe,
             int(self.set_start_t), int(self.t), avg, mx, plan_reps, plan_load))
        self.db.conn.commit()
        logged = LoggedSet(int(cur.lastrowid), self.item_idx, it.exercise_id, set_no, reps,
                           load, rpe, int(self.set_start_t), int(self.t), avg, mx)
        self.sets.append(logged)
        self.carry_load[self.item_idx] = load
        self.phase = REST
        self.rest_until = self.t + self._rest_after(self.item_idx, set_no - 1)
        self._rest_done_sent = False
        self._emit("set_logged", item=self.item_idx, set_no=set_no, reps=reps,
                   load_kg=load, rpe=rpe)
        self._advance_if_complete()
        self.checkpoint()
        return logged

    @property
    def editing_last(self) -> bool:
        """No descanso, os campos corrigem a série que acabou."""
        return self.phase in (REST, DONE) and bool(self.sets)

    def field_value(self, name: str):
        if self.editing_last:
            last = self.sets[-1]
            return {"reps": last.reps, "load_kg": last.load_kg, "rpe": last.rpe}[name]
        return self.entry.get(name)

    def set_field(self, name: str, value) -> None:
        if name == "reps":
            value = max(0, int(round(value or 0)))
        elif name == "load_kg":
            value = None if value is None or value <= 0 else round(float(value), 2)
        elif name == "rpe":
            value = None if value is None or value <= 0 else max(1.0, min(10.0, float(value)))
        if self.editing_last:
            last = self.sets[-1]
            setattr(last, name, value)
            column = {"reps": "reps", "load_kg": "load_kg", "rpe": "rpe"}[name]
            self.db.conn.execute(f"UPDATE strength_sets SET {column} = ? WHERE id = ?",
                                 (value, last.id))
            self.db.conn.commit()
            if name == "load_kg":
                self.carry_load[last.item_idx] = value
                if last.item_idx == self.item_idx:
                    self.entry["load_kg"] = value
            self.checkpoint()
        else:
            self.entry[name] = value

    def adjust(self, name: str, steps: int) -> None:
        cur = self.field_value(name)
        if name == "reps":
            self.set_field("reps", (cur or 0) + steps)
        elif name == "load_kg":
            self.set_field("load_kg", max(0.0, (cur or 0.0) + steps * LOAD_STEP))
        elif name == "rpe":
            base = cur if cur is not None else 6.5
            self.set_field("rpe", base + steps * RPE_STEP)

    def goto_item(self, step: int) -> None:
        """Mudar de exercício à mão (fazer fora de ordem)."""
        if self.phase == WORK:
            return
        self.item_idx = (self.item_idx + step) % len(self.items)
        self.skipped.discard(self.item_idx)
        if self.phase == DONE:
            self.phase = READY
        if not self.editing_last or self.phase == READY:
            self._prefill()
        self.checkpoint()

    def add_set(self) -> None:
        self.extra[self.item_idx] = self.extra.get(self.item_idx, 0) + 1
        self.skipped.discard(self.item_idx)
        if self.phase == DONE:
            self.phase = READY
            self._prefill()
        self.checkpoint()

    def skip_item(self) -> None:
        if self.phase == WORK:
            return
        self.skipped.add(self.item_idx)
        nxt = self.next_item()
        if nxt is None:
            self.phase = DONE
        else:
            self.item_idx = nxt
            if self.phase != REST:
                self.phase = READY
                self._prefill()
        self.checkpoint()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.checkpoint()

    # --------------------------------------------------- recuperação

    def checkpoint(self) -> None:
        try:
            self.db.save_checkpoint(self.session_id, "strength", {
                "workout_id": self.workout_id, "start_unix": self.start_unix,
                "name": self.workout_name}, {
                "t": self.t, "paused_s": self.paused_s, "phase": self.phase,
                "item_idx": self.item_idx, "extra": {str(k): v for k, v in self.extra.items()},
                "skipped": sorted(self.skipped), "entry": self.entry,
                "carry_load": {str(k): v for k, v in self.carry_load.items()},
                "rest_until": self.rest_until, "hr_zone_s": self.hr_zone_s})
        except Exception:
            pass

    def _restore(self, st: dict) -> None:
        self.t = float(st.get("t", 0.0))
        self.paused_s = float(st.get("paused_s", 0.0))
        self.item_idx = min(int(st.get("item_idx", 0)), len(self.items) - 1)
        self.extra = {int(k): int(v) for k, v in (st.get("extra") or {}).items()}
        self.skipped = set(int(k) for k in st.get("skipped") or [])
        self.carry_load = {int(k): v for k, v in (st.get("carry_load") or {}).items()}
        self.rest_until = float(st.get("rest_until", 0.0))
        rows = self.db.conn.execute(
            "SELECT * FROM strength_sets WHERE session_id = ? ORDER BY id",
            (self.session_id,)).fetchall()
        self.sets = [LoggedSet(r["id"], r["item_idx"] if r["item_idx"] is not None else 0,
                               r["exercise_id"], r["set_no"], r["reps"], r["load_kg"],
                               r["rpe"], r["start_t_s"] or 0, r["end_t_s"] or 0,
                               r["avg_hr"], r["max_hr"]) for r in rows]
        for r in self.db.conn.execute(
                "SELECT t_s, hr_bpm FROM strength_hr WHERE session_id = ? ORDER BY t_s",
                (self.session_id,)):
            hr = r["hr_bpm"]
            self._hr_all.append(hr)
            if hr:
                self._hr_sum += hr
                self._hr_n += 1
                self._max_hr = max(self._max_hr, hr)
        zones = st.get("hr_zone_s")
        if zones and len(zones) == len(self.hr_zone_s):
            self.hr_zone_s = [float(z) for z in zones]
        if self._hr_all:
            last_t = self.db.conn.execute(
                "SELECT MAX(t_s) AS t FROM strength_hr WHERE session_id = ?",
                (self.session_id,)).fetchone()["t"]
            self.t = max(self.t, float(last_t or 0))
        # uma série a meio quando a aplicação caiu volta ao início: recomeça-se
        phase = st.get("phase", READY)
        self.phase = READY if phase == WORK else phase
        self.entry = dict(st.get("entry") or {})
        if not self.entry:
            self._prefill()
        self.paused = True                  # retoma em pausa: o atleta decide
        self._emit("recovered", t_s=self.t, sets=len(self.sets))

    def suspend(self) -> None:
        if self.finished:
            return
        try:
            self.flush()
        except Exception:
            pass

    # ------------------------------------------------------------ fim

    def summary(self) -> dict:
        body = self.athlete.weight_kg
        by_idx = {i: it for i, it in enumerate(self.items)}
        volume = 0.0
        rpes = []
        per_exercise: dict[int, dict] = {}
        for s in self.sets:
            it = by_idx.get(s.item_idx)
            bw = it.bodyweight if it else 0.0
            measure = it.measure if it else "reps"
            v = set_volume(s.load_kg, s.reps, bw, body, measure)
            volume += v
            if s.rpe:
                rpes.append(s.rpe)
            ex = per_exercise.setdefault(s.exercise_id, {
                "name": it.name if it else "?", "sets": 0, "reps": 0, "volume": 0.0,
                "best_e1rm": None, "measure": measure, "lines": []})
            ex["sets"] += 1
            ex["reps"] += s.reps
            ex["volume"] += v
            est = e1rm((s.load_kg or 0) + bw * (body or 0), s.reps, s.rpe) \
                if measure == "reps" else None
            if est and (ex["best_e1rm"] is None or est > ex["best_e1rm"]):
                ex["best_e1rm"] = est
            ex["lines"].append(s)
        avg_rpe = sum(rpes) / len(rpes) if rpes else None
        load = hr_load(self._hr_all, self.lthr)
        source = "hr"
        if load is None or self._hr_n < 0.5 * max(1, len(self._hr_all)):
            alt = rpe_load(self.t, avg_rpe)
            if alt is not None:
                load, source = alt, "rpe"
        if load is None:
            source = None
        return {
            "elapsed_s": int(self.t), "paused_s": int(self.paused_s),
            "total_sets": len(self.sets), "total_reps": sum(s.reps for s in self.sets),
            "volume_kg": volume, "avg_rpe": avg_rpe, "avg_hr": self.avg_hr,
            "max_hr": self._max_hr or None, "load": load, "load_source": source,
            "hr_zone_s": list(self.hr_zone_s), "exercises": list(per_exercise.values()),
        }

    def finish(self) -> dict:
        if self.finished:
            return {}
        if self.phase == WORK:
            self.end_set()
        self.flush()
        self.finished = True
        summ = self.summary()
        base = naming.activity_name(self.start_unix, workout_name=self.workout_name,
                                    kind="strength")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path, name = naming.unique_path(self.out_dir, base)
        fit_path: str | None = None
        try:
            from . import fit
            hr_rows = self.db.conn.execute(
                "SELECT t_s, hr_bpm FROM strength_hr WHERE session_id = ? ORDER BY t_s",
                (self.session_id,)).fetchall()
            fit.write_strength(path, self.athlete, [(r["t_s"], r["hr_bpm"]) for r in hr_rows],
                               self.sets, self.items, summ, start_unix=self.start_unix,
                               name=name)
            fit_path = str(path)
        except Exception as e:
            self._emit("fit_error", message=str(e))
        self.db.conn.execute(
            "UPDATE strength_sessions SET status='completed', ended_at=?, elapsed_s=?,"
            " paused_s=?, total_sets=?, total_reps=?, volume_kg=?, avg_rpe=?, avg_hr=?,"
            " max_hr=?, load=?, load_source=?, hr_zone_s=?, fit_path=?, name=? WHERE id = ?",
            (now_iso(), summ["elapsed_s"], summ["paused_s"], summ["total_sets"],
             summ["total_reps"], summ["volume_kg"], summ["avg_rpe"], summ["avg_hr"],
             summ["max_hr"], summ["load"], summ["load_source"], json.dumps(summ["hr_zone_s"]),
             fit_path, name, self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)
        summ.update({"session_id": self.session_id, "name": name, "fit_path": fit_path,
                     "workout_id": self.workout_id, "workout_name": self.workout_name})
        return summ

    def abort(self) -> None:
        self.finished = True
        self.db.conn.execute("UPDATE strength_sessions SET status='aborted', ended_at=?"
                             " WHERE id = ?", (now_iso(), self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)


# --------------------------------------------------------------- histórico


def sessions(db: Database, limit: int = 200) -> list[dict]:
    rows = db.conn.execute(
        "SELECT s.*, w.name AS plan_name FROM strength_sessions s"
        " LEFT JOIN strength_workouts w ON w.id = s.workout_id"
        " WHERE s.status = 'completed' ORDER BY s.started_at DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(r) for r in rows]


def session_sets(db: Database, session_id: str) -> list[dict]:
    rows = db.conn.execute(
        "SELECT s.*, e.name FROM strength_sets s JOIN exercises e ON e.id = s.exercise_id"
        " WHERE s.session_id = ? ORDER BY s.id", (session_id,)).fetchall()
    return [dict(r) for r in rows]


def exercises_with_history(db: Database) -> list[dict]:
    rows = db.conn.execute(
        "SELECT e.id, e.name, COUNT(*) AS n FROM strength_sets s"
        " JOIN exercises e ON e.id = s.exercise_id"
        " JOIN strength_sessions ss ON ss.id = s.session_id"
        " WHERE ss.status = 'completed' GROUP BY e.id ORDER BY n DESC, e.name").fetchall()
    return [dict(r) for r in rows]


def exercise_progress(db: Database, exercise_id: int) -> list[dict]:
    """Por sessão: data, melhor 1RM estimada, carga máxima, volume e séries."""
    _ensure_measure_column(db)
    ex = exercise(db, exercise_id) or {"bodyweight": 0.0, "measure": "reps"}
    rows = db.conn.execute(
        "SELECT s.*, ss.started_at, ss.weight_at_session_kg AS body FROM strength_sets s"
        " JOIN strength_sessions ss ON ss.id = s.session_id"
        " WHERE ss.status = 'completed' AND s.exercise_id = ?"
        " ORDER BY ss.started_at, s.id", (exercise_id,)).fetchall()
    out: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        sid = r["session_id"]
        if sid not in out:
            out[sid] = {"date": str(r["started_at"])[:10], "best_e1rm": None, "max_load": None,
                        "volume": 0.0, "sets": 0, "reps": 0}
            order.append(sid)
        o = out[sid]
        bw = ex["bodyweight"] or 0.0
        body = r["body"] or 0.0
        o["sets"] += 1
        o["reps"] += r["reps"]
        o["volume"] += set_volume(r["load_kg"], r["reps"], bw, body, ex["measure"])
        if r["load_kg"] is not None:
            o["max_load"] = max(o["max_load"] or 0.0, r["load_kg"])
        if ex["measure"] == "reps":
            est = e1rm((r["load_kg"] or 0.0) + bw * body, r["reps"], r["rpe"])
            if est and (o["best_e1rm"] is None or est > o["best_e1rm"]):
                o["best_e1rm"] = est
    return [out[k] for k in order]


def recent_bests(db: Database, workout_id: str | None = None) -> dict[int, dict]:
    """Última série registada de cada exercício: para sugerir a carga."""
    rows = db.conn.execute(
        "SELECT s.exercise_id, s.load_kg, s.reps, s.rpe, ss.started_at FROM strength_sets s"
        " JOIN strength_sessions ss ON ss.id = s.session_id"
        " WHERE ss.status = 'completed' ORDER BY ss.started_at, s.id").fetchall()
    out: dict[int, dict] = {}
    for r in rows:
        out[r["exercise_id"]] = dict(r)
    return out


def last_session_date(db: Database) -> str | None:
    r = db.conn.execute("SELECT MAX(started_at) AS d FROM strength_sessions"
                        " WHERE status='completed'").fetchone()
    return str(r["d"])[:10] if r and r["d"] else None


def parse_started(value: str | None):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            from datetime import timezone
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
