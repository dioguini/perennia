"""Remo indoor: sessões, treinos estruturados, testes e jogos.

A máquina (velo.io.rower) dá remadas, remadas por minuto (voga), ritmo por
500 m e resistência; a FC vem da banda ou do relógio (como na força), ou da
própria máquina se não houver outra. A potência é a da máquina (FTMS) ou,
na Domyos, calculada do ritmo pela fórmula da Concept2.

- Livre: rema-se, com voltas manuais.
- Treino: passos por tempo ou por distância, com alvo de ritmo, potência
  (% da FTP do remo) ou voga, e o nível de resistência (1–15) que a app põe
  sozinha no início de cada passo. Nenhum passo dura menos de 10 s.
- Teste: 2000 m, 500 m, 30 min, 1 min — o resultado vai para os testes.
- Challenge: os jogos do ciclismo com a potência do remo, e a Regata
  (corrida de 500 m a 5 km contra bots).

Tudo a 1 Hz, com ponto de recuperação (se a aplicação falhar, retoma-se).
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import naming, physics
from . import strength as st
from .boards import Board, Row
from .db import Athlete, Database, new_id, now_iso
from .i18n import tr
from .units import hms

MIN_STEP_S = 10
MIN_STEP_M = 50
FLUSH_EVERY = 5
IDLE_PAUSE_S = 4.0
KINDS = ("free", "workout", "test", "game")
STEP_KINDS = ("warmup", "active", "rest", "cooldown")
TARGETS = ("none", "pace", "power", "spm")


def watts_from_pace(p):
    from velo.io.rower import watts_from_pace as f
    return f(p)


def pace_from_watts(w):
    from velo.io.rower import pace_from_watts as f
    return f(w)


def pace_text(p) -> str:
    from velo.io.rower import pace_text as f
    return f(p)


def row_ftp(db: Database) -> int:
    """FTP do remo (W): a definida, ou uma estimativa a partir da do ciclismo."""
    v = db.get("row_ftp_w")
    if v:
        return int(v)
    return max(80, int(round(db.athlete().ftp_w * 0.8)))


# =================================================================== tabelas


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS row_sessions (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT, status TEXT NOT NULL,
      workout_id TEXT, protocol TEXT, game TEXT, started_at TEXT NOT NULL, ended_at TEXT,
      elapsed_s INTEGER, moving_s INTEGER, paused_s INTEGER, distance_m REAL, strokes INTEGER,
      avg_spm REAL, avg_pace_s REAL, best_pace_s REAL, avg_power_w REAL, max_power_w INTEGER,
      np_w REAL, kcal REAL, avg_hr REAL, max_hr INTEGER, load REAL, load_source TEXT,
      hr_zone_s TEXT, ftp_w INTEGER, fit_path TEXT, result REAL, device TEXT);
    CREATE TABLE IF NOT EXISTS row_samples (
      session_id TEXT NOT NULL REFERENCES row_sessions(id) ON DELETE CASCADE,
      t_s INTEGER NOT NULL, dist_m REAL, pace_s REAL, power_w INTEGER, spm REAL,
      hr_bpm INTEGER, resistance INTEGER, strokes INTEGER,
      PRIMARY KEY (session_id, t_s)) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS row_laps (
      id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES row_sessions(id)
      ON DELETE CASCADE, lap_no INTEGER NOT NULL, trigger TEXT, start_t REAL, end_t REAL,
      distance_m REAL, strokes INTEGER, avg_pace_s REAL, avg_power_w REAL, avg_spm REAL,
      avg_hr REAL, max_hr INTEGER, step_idx INTEGER);
    CREATE TABLE IF NOT EXISTS row_workouts (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, builtin INTEGER NOT NULL
      DEFAULT 0, created_at TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS row_workout_steps (
      workout_id TEXT NOT NULL REFERENCES row_workouts(id) ON DELETE CASCADE,
      idx INTEGER NOT NULL, kind TEXT NOT NULL, dur_type TEXT NOT NULL, dur_value REAL NOT NULL,
      target TEXT NOT NULL, lo REAL, hi REAL, resistance INTEGER, cue TEXT,
      PRIMARY KEY (workout_id, idx)) WITHOUT ROWID;
    """)
    db.conn.commit()


# ================================================================== treinos


@dataclass
class Step:
    kind: str = "active"
    dur_type: str = "time"          # time (s) | distance (m)
    dur_value: float = 300
    target: str = "none"            # none | pace (s/500 m) | power (% FTP) | spm
    lo: float | None = None
    hi: float | None = None
    resistance: int | None = None
    cue: str = ""

    def clean(self) -> "Step":
        if self.dur_type == "time":
            self.dur_value = max(MIN_STEP_S, int(round(self.dur_value)))
        else:
            self.dur_type = "distance"
            self.dur_value = max(MIN_STEP_M, float(round(self.dur_value)))
        if self.target not in TARGETS:
            self.target = "none"
        if self.lo is not None and self.hi is not None and self.lo > self.hi:
            self.lo, self.hi = self.hi, self.lo
        if self.resistance is not None:
            self.resistance = max(1, min(15, int(self.resistance)))
        return self

    def duration_text(self) -> str:
        if self.dur_type == "time":
            return hms(self.dur_value)
        v = self.dur_value
        return f"{v / 1000:g} km" if v >= 1000 and v % 100 == 0 else f"{v:.0f} m"

    def target_text(self, ftp: int | None = None) -> str:
        lo, hi = self.lo, self.hi
        if self.target == "pace" and lo:
            return f"{pace_text(lo)}–{pace_text(hi or lo)} /500 m"
        if self.target == "power" and lo:
            s = f"{lo:g}–{(hi or lo):g} % FTP"
            if ftp:
                s += f" ({ftp * lo / 100:.0f}–{ftp * (hi or lo) / 100:.0f} W)"
            return s
        if self.target == "spm" and lo:
            return f"{lo:g}–{(hi or lo):g} spm"
        return tr("livre", "free")

    def pace_range(self, ftp: int) -> tuple[float, float] | None:
        """O alvo em ritmo (s/500 m): lento, rápido."""
        if self.target == "pace" and self.lo:
            hi = self.hi or self.lo
            return max(self.lo, hi), min(self.lo, hi)
        if self.target == "power" and self.lo:
            hi = self.hi or self.lo
            return pace_from_watts(ftp * self.lo / 100), pace_from_watts(ftp * hi / 100)
        return None

    def watts_range(self, ftp: int) -> tuple[int, int] | None:
        if self.target == "power" and self.lo:
            return int(ftp * self.lo / 100), int(ftp * (self.hi or self.lo) / 100)
        if self.target == "pace" and self.lo:
            a, b = watts_from_pace(self.lo), watts_from_pace(self.hi or self.lo)
            return min(a, b), max(a, b)
        return None


LIBRARY: tuple[tuple[str, str, list], ...] = (
    ("Base 20 minutos", "Remo contínuo e confortável, a 70–80 % da FTP. Voga 20–22.", [
        Step("warmup", "time", 300, "power", 50, 65, 4, "Aquecer: técnica primeiro"),
        Step("active", "time", 1200, "power", 70, 80, 6, "Ritmo confortável, voga 20–22"),
        Step("cooldown", "time", 300, "power", 45, 55, 3, "Soltar")]),
    ("Pirâmide 1-2-3-4-3-2-1", "Blocos de 1 a 4 min a 95–105 % da FTP, 1 min de descanso.", [
        Step("warmup", "time", 480, "power", 50, 70, 5, "Aquecimento")] + [
        x for m in (1, 2, 3, 4, 3, 2, 1) for x in (
            Step("active", "time", m * 60, "power", 95, 105, 8, f"{m} min forte"),
            Step("rest", "time", 60, "none", None, None, 3, "Descansa"))] + [
        Step("cooldown", "time", 300, "power", 45, 55, 3, "Soltar")]),
    ("8 × 500 m", "Ritmo de 2 km, com 1:30 de descanso.", [
        Step("warmup", "time", 600, "power", 50, 70, 5, "Aquecimento")] + [
        x for _ in range(8) for x in (
            Step("active", "distance", 500, "power", 105, 115, 8, "500 m forte"),
            Step("rest", "time", 90, "none", None, None, 3, "Descansa"))] + [
        Step("cooldown", "time", 300, "power", 45, 55, 3, "Soltar")]),
    ("Limiar 3 × 10 minutos", "Três blocos no limiar (95–100 %), 3 min entre eles.", [
        Step("warmup", "time", 600, "power", 50, 70, 5, "Aquecimento")] + [
        x for _ in range(3) for x in (
            Step("active", "time", 600, "power", 95, 100, 7, "Limiar: firme e constante"),
            Step("rest", "time", 180, "none", None, None, 3, "Descansa"))] + [
        Step("cooldown", "time", 300, "power", 45, 55, 3, "Soltar")]),
    ("Força 6 × 2 min", "Resistência alta e voga baixa (18–20): força em cada remada.", [
        Step("warmup", "time", 480, "power", 50, 65, 5, "Aquecimento")] + [
        x for _ in range(6) for x in (
            Step("active", "time", 120, "spm", 18, 20, 13, "Remadas longas e fortes"),
            Step("rest", "time", 90, "none", None, None, 4, "Descansa"))] + [
        Step("cooldown", "time", 300, "power", 45, 55, 3, "Soltar")]),
    ("Voga 20-24-28", "Mudanças de voga com o mesmo esforço técnico.", [
        Step("warmup", "time", 300, "spm", 18, 20, 5, "Aquecimento")] + [
        x for _ in range(3) for x in (
            Step("active", "time", 120, "spm", 20, 20, 6, "Voga 20"),
            Step("active", "time", 120, "spm", 24, 24, 6, "Voga 24"),
            Step("active", "time", 120, "spm", 28, 28, 6, "Voga 28"),
            Step("rest", "time", 60, "none", None, None, 3, "Descansa"))] + [
        Step("cooldown", "time", 300, "spm", 18, 20, 3, "Soltar")]),
    ("Sprints 10 × 20 s", "20 s a fundo, 40 s de descanso.", [
        Step("warmup", "time", 480, "power", 50, 70, 5, "Aquecimento")] + [
        x for _ in range(10) for x in (
            Step("active", "time", 20, "power", 140, 170, 10, "A fundo!"),
            Step("rest", "time", 40, "none", None, None, 3, "Descansa"))] + [
        Step("cooldown", "time", 300, "power", 45, 55, 3, "Soltar")]),
)


def seed(db: Database) -> None:
    ensure(db)
    if db.get("row_workouts_seeded", False):
        return
    for i, (name, desc, steps) in enumerate(LIBRARY):
        save_workout(db, None, name, desc, steps, builtin=True, sort=i)
    db.set("row_workouts_seeded", True)


def workouts(db: Database) -> list[dict]:
    seed(db)
    out = []
    for r in db.conn.execute("SELECT * FROM row_workouts ORDER BY builtin DESC, sort, name"):
        w = dict(r)
        w["steps"] = steps_of(db, w["id"])
        w["total_s"], w["total_m"] = totals(w["steps"])
        out.append(w)
    return out


def workout(db: Database, wid: str) -> dict | None:
    seed(db)
    r = db.conn.execute("SELECT * FROM row_workouts WHERE id = ?", (wid,)).fetchone()
    if r is None:
        return None
    w = dict(r)
    w["steps"] = steps_of(db, wid)
    w["total_s"], w["total_m"] = totals(w["steps"])
    return w


def steps_of(db: Database, wid: str) -> list[Step]:
    return [Step(r["kind"], r["dur_type"], r["dur_value"], r["target"], r["lo"], r["hi"],
                 r["resistance"], r["cue"] or "") for r in db.conn.execute(
        "SELECT * FROM row_workout_steps WHERE workout_id = ? ORDER BY idx", (wid,))]


def totals(steps: list[Step]) -> tuple[float, float]:
    """(segundos dos passos por tempo, metros dos passos por distância)."""
    return (sum(s.dur_value for s in steps if s.dur_type == "time"),
            sum(s.dur_value for s in steps if s.dur_type == "distance"))


def save_workout(db: Database, wid: str | None, name: str, description: str,
                 steps: list[Step], builtin: bool = False, sort: int = 100) -> str:
    ensure(db)
    wid = wid or new_id()
    db.conn.execute(
        "INSERT INTO row_workouts(id, name, description, builtin, created_at, sort)"
        " VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
        " description=excluded.description", (wid, name.strip() or "Treino", description,
                                              int(builtin), now_iso(), sort))
    db.conn.execute("DELETE FROM row_workout_steps WHERE workout_id = ?", (wid,))
    db.conn.executemany(
        "INSERT INTO row_workout_steps(workout_id, idx, kind, dur_type, dur_value, target, lo,"
        " hi, resistance, cue) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(wid, i, s.kind, s.dur_type, s.dur_value, s.target, s.lo, s.hi, s.resistance, s.cue)
         for i, s in enumerate(Step(**asdict(x)).clean() for x in steps)])
    db.conn.commit()
    return wid


def delete_workout(db: Database, wid: str) -> None:
    db.conn.execute("DELETE FROM row_workouts WHERE id = ?", (wid,))
    db.conn.commit()


class RowWorkoutRunner:
    """Avança pelos passos com o tempo e a distância da sessão."""

    def __init__(self, steps: list[Step], ftp: int, name: str = ""):
        self.steps = [Step(**asdict(s)).clean() for s in steps]
        self.ftp = ftp
        self.name = name
        self.idx = 0
        self.step_t = 0.0
        self.step_m = 0.0
        self.done = not self.steps
        self.results: list[dict] = []
        self._acc = {"w": 0.0, "n": 0, "spm": 0.0, "hr": 0.0, "hr_n": 0, "in": 0}

    @property
    def step(self) -> Step | None:
        return None if self.done else self.steps[self.idx]

    @property
    def next_step(self) -> Step | None:
        return self.steps[self.idx + 1] if not self.done and self.idx + 1 < len(self.steps) \
            else None

    def progress(self) -> float:
        s = self.step
        if s is None:
            return 1.0
        got = self.step_t if s.dur_type == "time" else self.step_m
        return max(0.0, min(1.0, got / s.dur_value))

    def remaining_text(self) -> str:
        s = self.step
        if s is None:
            return ""
        if s.dur_type == "time":
            return hms(max(0.0, s.dur_value - self.step_t))
        return f"{max(0.0, s.dur_value - self.step_m):.0f} m"

    def in_target(self, pace: float | None, watts: int | None, spm: float | None) -> bool | None:
        s = self.step
        if s is None or s.target == "none" or not s.lo:
            return None
        lo, hi = s.lo, s.hi or s.lo
        if s.target == "spm":
            return spm is not None and lo - 1 <= spm <= hi + 1
        rng = s.watts_range(self.ftp)
        return watts is not None and rng is not None and rng[0] * 0.97 <= watts <= rng[1] * 1.03

    def advance(self, dt: float, dm: float, watts: int | None, spm: float | None,
                hr: int | None, pace: float | None) -> list[tuple[str, dict]]:
        if self.done:
            return []
        self.step_t += dt
        self.step_m += dm
        a = self._acc
        if watts:
            a["w"] += watts
            a["n"] += 1
        if spm:
            a["spm"] += spm
        if hr:
            a["hr"] += hr
            a["hr_n"] += 1
        if self.in_target(pace, watts, spm):
            a["in"] += 1
        s = self.steps[self.idx]
        got = self.step_t if s.dur_type == "time" else self.step_m
        if got < s.dur_value:
            return []
        n = max(1, a["n"])
        self.results.append({"idx": self.idx, "seconds": self.step_t, "meters": self.step_m,
                             "avg_power_w": a["w"] / n if a["n"] else None,
                             "avg_spm": a["spm"] / n if a["n"] else None,
                             "avg_hr": a["hr"] / a["hr_n"] if a["hr_n"] else None,
                             "in_target_pct": 100.0 * a["in"] / max(1.0, self.step_t)})
        self._acc = {"w": 0.0, "n": 0, "spm": 0.0, "hr": 0.0, "hr_n": 0, "in": 0}
        self.idx += 1
        self.step_t = self.step_m = 0.0
        if self.idx >= len(self.steps):
            self.done = True
            return [("step_end", self.results[-1]), ("workout_done", {})]
        return [("step_end", self.results[-1]), ("step", self.step_info())]

    def step_info(self) -> dict:
        s = self.step
        if s is None:
            return {}
        return {"idx": self.idx, "n": len(self.steps), "kind": s.kind,
                "duration": s.duration_text(), "target": s.target_text(self.ftp),
                "resistance": s.resistance, "cue": s.cue}

    def snapshot(self) -> dict:
        return {"idx": self.idx, "step_t": self.step_t, "step_m": self.step_m,
                "done": self.done, "results": self.results}

    def restore(self, snap: dict) -> None:
        self.idx = int(snap.get("idx", 0))
        self.step_t = float(snap.get("step_t", 0.0))
        self.step_m = float(snap.get("step_m", 0.0))
        self.done = bool(snap.get("done", False)) or self.idx >= len(self.steps)
        self.results = list(snap.get("results", []))


# =================================================================== testes

TESTS = {
    # protocolo: (distância alvo m, tempo alvo s, unidade do resultado)
    "row_2000": (2000.0, None, "s"),
    "row_500": (500.0, None, "s"),
    "row_30min": (None, 1800.0, "m"),
    "row_1min": (None, 60.0, "m"),
}
TEST_NAMES = {"2000 m": "row_2000", "500 m": "row_500",
              "Distância em 30 minutos": "row_30min", "Distância em 1 minuto": "row_1min"}


def link_tests(db: Database) -> None:
    """Os testes de remo do catálogo passam a correr na máquina."""
    from . import fitness_tests as ft
    ft.seed(db)
    for name, proto in TEST_NAMES.items():
        db.conn.execute("UPDATE fitness_tests SET protocol = ? WHERE sport = 'rowing'"
                        " AND name = ? AND custom = 0 AND protocol IS NULL", (proto, name))
    db.conn.commit()


# =================================================================== jogos

ROW_GAMES = ("adaptive", "zone_hero", "ladder", "warmup", "tug", "regatta")
REGATTA_DISTANCES = (500, 1000, 2000, 5000)


class Regatta:
    """Corrida contra bots numa distância. Ganha quem chegar primeiro."""

    key = "regatta"
    erg_default = False
    has_duration = False
    has_bots = True
    durations = REGATTA_DISTANCES
    default_minutes = 2000
    higher_is_better = False

    def __init__(self, ftp: int, weight_kg: float = 75.0, *, distance_m: int = 2000,
                 bots: int = 5, seed: int = 1, **_):
        self.ftp = max(50, int(ftp))
        self.distance = float(distance_m)
        self.minutes = int(distance_m)
        self.seed = seed
        self.rng = random.Random(seed)
        self.t = 0.0
        self.my_distance = 0.0
        self.my_finish: float | None = None
        self.finished = False
        self.saved = False
        self.target_w: int | None = None
        self.erg = False
        self.headline = ""
        self.detail = ""
        self.progress = 0.0
        self.mood = "neutral"
        self.won: bool | None = None
        self.rank: int | None = None
        self.score = 0.0
        # potência de corrida ~ FTP × fator da duração (2 km ≈ 7 min)
        mult = {500: 1.45, 1000: 1.3, 2000: 1.18, 5000: 1.05}.get(int(distance_m), 1.15)
        names = ["Ana", "Bruno", "Carla", "Diogo", "Eva", "Filipe", "Gil", "Helena"]
        self.rng.shuffle(names)
        self.bots = []
        for i in range(max(1, int(bots))):
            w = self.ftp * mult * self.rng.uniform(0.9, 1.07)
            self.bots.append({"name": names[i % len(names)], "w": w, "dist": 0.0,
                              "finish": None, "kick": self.rng.uniform(0.75, 0.9)})

    @property
    def title(self) -> str:
        return tr("Regata {d} m", "Regatta {d} m", d=int(self.distance))

    def _bot_speed(self, b: dict) -> float:
        from velo.io.rower import speed_from_pace
        frac = b["dist"] / self.distance
        w = b["w"] * (1.08 if self.t < 20 else 1.0)          # arranque rápido
        if frac > b["kick"]:
            w *= 1.07                                           # sprint final
        w *= self.rng.uniform(0.97, 1.03)
        return speed_from_pace(pace_from_watts(w))

    def tick(self, dt: float, power_w: int | None) -> list[tuple[str, dict]]:
        if self.finished:
            return []
        self.t += dt
        ev = []
        for b in self.bots:
            if b["finish"] is None:
                b["dist"] += self._bot_speed(b) * dt
                if b["dist"] >= self.distance:
                    b["dist"] = self.distance
                    b["finish"] = self.t
        if self.my_finish is None and self.my_distance >= self.distance:
            self.my_finish = self.t
        ahead = sum(1 for b in self.bots if b["dist"] > self.my_distance)
        self.progress = min(1.0, self.my_distance / self.distance)
        lead = max((b for b in self.bots), key=lambda b: b["dist"])
        gap = self.my_distance - lead["dist"]
        self.headline = tr("{p}.º lugar", "{p} place", p=ahead + 1)
        self.detail = tr("{m:.0f} m para a meta", "{m:.0f} m to go",
                         m=max(0.0, self.distance - self.my_distance))
        self.mood = "good" if ahead == 0 else ("warn" if gap > -15 else "bad")
        if self.my_finish is not None:
            ev += self.end()
        elif all(b["finish"] is not None for b in self.bots) and self.t > 3 * 3600:
            ev += self.end()
        return ev

    def end(self) -> list[tuple[str, dict]]:
        if self.finished:
            return []
        self.finished = True
        mine = self.my_finish or float("inf")
        # quem não acabou, projeta-se ao ritmo atual
        better = 0
        for b in self.bots:
            fin = b["finish"]
            if fin is None:
                sp = self._bot_speed(b)
                fin = self.t + (self.distance - b["dist"]) / max(0.5, sp)
            if fin < mine:
                better += 1
        self.rank = better + 1
        self.won = self.rank == 1
        self.score = mine if self.my_finish else 0.0
        return [("game_over", self.result())]

    def standings(self):
        rows = [(tr("Tu", "You"), self.my_distance, True)] + [
            (b["name"], b["dist"], False) for b in self.bots]
        rows.sort(key=lambda r: -r[1])
        return rows

    def result(self) -> dict:
        return {"game": self.key, "score": round(self.my_finish) if self.my_finish else None,
                "rank": self.rank, "total": len(self.bots) + 1, "won": self.won,
                "seconds": int(self.t), "distance_m": int(self.distance),
                "summary": (tr("{p}.º em {n} · {t}", "{p} of {n} · {t}", p=self.rank,
                               n=len(self.bots) + 1, t=hms(self.my_finish))
                            if self.my_finish else tr("não terminou", "did not finish"))}

    def board(self, history: list | None = None) -> Board:
        rows = []
        for i, (name, dist, me) in enumerate(self.standings()[:6]):
            gap = dist - self.my_distance
            val = f"{dist:.0f} m" if me else f"{gap:+.0f} m"
            rows.append(Row(i + 1, val, name, me=me))
        sub = tr("Melhor: {t}", "Best: {t}", t=hms(history[0])) if history else \
            tr("{d} m", "{d} m", d=int(self.distance))
        return Board(self.title, rows, subtitle=sub)

    def snapshot(self) -> dict:
        return {k: v for k, v in vars(self).items() if k != "rng"}

    def restore(self, snap: dict) -> None:
        for k, v in snap.items():
            setattr(self, k, v)
        self.rng = random.Random(self.seed + int(self.t))


def create_game(spec: dict, db: Database, athlete: Athlete):
    """Os jogos do ciclismo, com a FTP do remo; ou a Regata."""
    ftp = row_ftp(db)
    key = spec["key"]
    if key == "regatta":
        return Regatta(ftp, athlete.weight_kg, distance_m=int(spec.get("distance", 2000)),
                       bots=spec.get("bots", 5), seed=spec.get("seed", 1))
    from . import games
    cls = games.CLASSES[key]
    return cls(ftp, athlete.weight_kg, best=None, minutes=spec.get("minutes"),
               bots=spec.get("bots", 4), erg=False, seed=spec.get("seed", 1),
               level=float(db.get("row_adaptive_level", 0.9)),
               power_zones=db.get("power_zones_pct", None))


def game_title(key: str) -> str:
    if key == "regatta":
        return tr("Regata", "Regatta")
    from .i18n import t
    return t(f"game.{key}")


def save_game(db: Database, session_id: str, game, ranked: bool = True) -> dict:
    from . import games
    games.ensure_table(db)
    r = game.result()
    r["ranked"] = ranked
    r["session_id"] = session_id
    gkey = f"row:{game.key}" + (f":{int(game.distance)}" if game.key == "regatta" else "")
    db.conn.execute(
        "INSERT INTO game_results(ride_id, game, score, rank, total, won, seconds, details,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (None, gkey, r["score"] if ranked else None, r["rank"], r["total"],
         None if r["won"] is None else int(r["won"]), r["seconds"], json.dumps(r), now_iso()))
    if game.key == "adaptive":
        db.set("row_adaptive_level", round(game.level, 3))
    db.conn.commit()
    game.saved = True
    return r


def game_history(db: Database, game) -> list[float]:
    from . import games
    games.ensure_table(db)
    gkey = f"row:{game.key}" + (f":{int(game.distance)}" if game.key == "regatta" else "")
    order = "ASC" if game.key == "regatta" else "DESC"
    return [r["score"] for r in db.conn.execute(
        f"SELECT score FROM game_results WHERE game = ? AND score IS NOT NULL"
        f" ORDER BY score {order} LIMIT 5", (gkey,))]


# ==================================================================== sessão


@dataclass
class RowLap:
    no: int
    start_t: float
    start_m: float
    start_strokes: int
    trigger: str = "manual"
    end_t: float | None = None
    distance_m: float = 0.0
    strokes: int = 0
    avg_power_w: float | None = None
    avg_spm: float | None = None
    avg_pace_s: float | None = None
    avg_hr: float | None = None
    max_hr: int | None = None
    step_idx: int | None = None
    acc: dict = field(default_factory=lambda: {"w": 0.0, "wn": 0, "spm": 0.0, "sn": 0,
                                               "hr": 0.0, "hn": 0, "mx": 0})


class RowEngine:
    def __init__(self, db: Database, athlete: Athlete, rower: Any, *, sensors: Any = None,
                 kind: str = "free", workout_id: str | None = None,
                 protocol: str | None = None, game_spec: dict | None = None,
                 out_dir: str | Path = "rowing", resume: dict | None = None,
                 clock: Callable[[], float] = time.monotonic, autolap: dict | None = None):
        ensure(db)
        self.db = db
        from .sports import AutoLap
        if autolap is None and resume is not None:
            autolap = resume.get("config", {}).get("autolap")
        self.autolap = AutoLap(autolap)
        self._trail: list[tuple[float, float]] = []     # (t, distância) a 1 Hz
        self._load_acc = 0.0
        self.athlete = athlete
        self.rower = rower
        self.sensors = sensors
        self.kind = kind if kind in KINDS else "free"
        self.out_dir = Path(out_dir)
        self.ftp = row_ftp(db)
        from .ride import estimate_lthr
        self.lthr = estimate_lthr(athlete)
        self.hr_bounds = list(db.get("hr_zones_pct_lthr", [68, 83, 94, 105]))
        self.hr_zone_s = [0.0] * (len(self.hr_bounds) + 1)
        self.events: list[tuple[str, dict]] = []
        self.workout_id = workout_id
        self.protocol = protocol
        self.game_spec = dict(game_spec or {})
        self.workout: RowWorkoutRunner | None = None
        self.title = tr("Remo livre", "Free row")
        if workout_id:
            w = workout(db, workout_id)
            if w:
                self.workout = RowWorkoutRunner(w["steps"], self.ftp, w["name"])
                self.title = w["name"]
                self.kind = "workout"
        self.test = TESTS.get(protocol or "")
        if self.test:
            self.kind = "test"
            self.title = tr("Teste", "Test") + " · " + {
                "row_2000": "2000 m", "row_500": "500 m", "row_30min": "30 min",
                "row_1min": "1 min"}[protocol]
        self.game = None
        if self.game_spec.get("key"):
            self.kind = "game"
            self.game = create_game(self.game_spec, db, athlete)
            self.title = self.game.title
        # estado
        self.t = 0.0                    # tempo em movimento + pausas automáticas curtas
        self.elapsed = 0.0
        self.paused_s = 0.0
        self.distance_m = 0.0
        self.strokes = 0
        self.spm: float | None = None
        self.pace_s: float | None = None
        self.power_w: int | None = None
        self.hr_bpm: int | None = None
        self.resistance: int | None = None
        self.kcal = 0.0
        self.started = False
        self.manual_pause = False
        self.auto_pause = False
        self.finished = False
        self.result_value: float | None = None
        self._idle = 0.0
        self._acc = 0.0
        self._pending: list[tuple] = []
        self._stroke0: int | None = None
        self._last_strokes: int | None = None
        self._last_machine_m: float | None = None
        self._kcal0: float | None = None
        self._watts: list[int] = []
        self._spms: list[float] = []
        self._hrs: list[int | None] = []
        self._best_pace: float | None = None
        self._max_w = 0
        self.laps: list[RowLap] = []
        self._lap: RowLap | None = None
        self._want_level: int | None = None
        if resume is not None:
            self.session_id = resume["session_id"]
            self.start_unix = float(resume["config"].get("start_unix") or time.time())
            self._restore(resume["state"])
        else:
            self.session_id = new_id()
            self.start_unix = time.time()
            db.conn.execute(
                "INSERT INTO row_sessions(id, kind, name, status, workout_id, protocol, game,"
                " started_at, ftp_w, device) VALUES (?,?,?,'recording',?,?,?,?,?,?)",
                (self.session_id, self.kind, self.title, workout_id, protocol,
                 self.game_spec.get("key"), now_iso(), self.ftp,
                 getattr(rower, "name", None)))
            db.conn.commit()
            self._open_lap("start")
            if self.workout is not None:
                self._apply_step()
            self.checkpoint()

    # ------------------------------------------------------------- leitura

    def _read(self):
        d = None
        try:
            d = self.rower.data() if self.rower is not None else None
        except Exception:
            d = None
        hr = None
        if self.sensors is not None:
            try:
                r = self.sensors.reading()
                hr = getattr(r, "hr_bpm", None) if r is not None else None
            except Exception:
                hr = None
        if hr is None and d is not None:
            hr = d.hr_bpm
        return d, hr

    def drain_events(self) -> list[tuple[str, dict]]:
        out, self.events = self.events, []
        return out

    @property
    def status(self) -> str:
        if self.finished:
            return "finished"
        if self.manual_pause:
            return "paused"
        if not self.started:
            return "waiting"
        return "auto_paused" if self.auto_pause else "running"

    @property
    def avg_pace_s(self) -> float | None:
        if self.distance_m < 10 or self.t <= 0:
            return None
        return self.t / self.distance_m * 500.0

    @property
    def avg_power_w(self) -> float | None:
        return sum(self._watts) / len(self._watts) if self._watts else None

    @property
    def avg_spm(self) -> float | None:
        return sum(self._spms) / len(self._spms) if self._spms else None

    @property
    def hr_zone(self) -> int | None:
        if not self.hr_bpm or not self.lthr:
            return None
        return physics.zone_of(self.hr_bpm, self.hr_bounds, self.lthr)

    @property
    def dist_per_stroke(self) -> float | None:
        n = self.strokes
        return self.distance_m / n if n > 5 else None

    # ---------------------------------------------------------------- ciclo

    def update(self, dt: float) -> None:
        if self.finished or dt <= 0:
            return
        try:
            self.rower.tick(dt)
        except Exception:
            pass
        d, hr = self._read()
        self.hr_bpm = hr
        if d is not None:
            if d.resistance is not None:
                self.resistance = d.resistance
            self.spm = d.spm
            self.pace_s = d.pace_s
            self.power_w = d.watts
        else:
            self.spm = self.pace_s = self.power_w = None
        if self.manual_pause:
            self.paused_s += dt
            return
        stroked = False
        if d is not None and d.strokes is not None:
            if self._last_strokes is not None and d.strokes > self._last_strokes:
                stroked = True
            if self._last_strokes is None or d.strokes < self._last_strokes:
                self._stroke0 = d.strokes - self.strokes      # contador reposto
            self._last_strokes = d.strokes
        moving = bool(d is not None and (stroked or (d.spm and d.pace_s)))
        if not self.started:
            if not moving:
                return
            self.started = True
            self.events.append(("started", {}))
            if self._want_level:
                self._send_level(self._want_level)
        if moving:
            self._idle = 0.0
            if self.auto_pause:
                self.auto_pause = False
                self.events.append(("auto_resume", {}))
        else:
            self._idle += dt
            if self._idle >= IDLE_PAUSE_S:
                if not self.auto_pause:
                    self.auto_pause = True
                    self.events.append(("auto_pause", {}))
                self.paused_s += dt
                return
        self.t += dt
        # distância: o contador da máquina (FTMS) ou a velocidade integrada
        dm = 0.0
        if d is not None and d.source == "ftms" and d.distance_m is not None:
            if self._last_machine_m is not None and d.distance_m >= self._last_machine_m:
                dm = d.distance_m - self._last_machine_m
            self._last_machine_m = d.distance_m
        elif d is not None and d.pace_s:
            dm = 500.0 / d.pace_s * dt
        if self.test and self.test[0]:
            dm = min(dm, max(0.0, self.test[0] - self.distance_m))
        self.distance_m += dm
        if d is not None and d.strokes is not None and self._stroke0 is not None:
            self.strokes = max(self.strokes, d.strokes - self._stroke0)
        if d is not None and d.kcal is not None:
            if self._kcal0 is None:
                self._kcal0 = d.kcal - self.kcal
            self.kcal = max(self.kcal, d.kcal - self._kcal0)
        self._acc += dt
        while self._acc >= 1.0:
            self._acc -= 1.0
            self._sample()
        if self.workout is not None:
            for kind, data in self.workout.advance(dt, dm, self.power_w, self.spm, hr,
                                                   self.pace_s):
                self.events.append((kind, data))
                if kind == "step_end":
                    self.lap("workout_step", step_idx=data["idx"])
                elif kind == "step":
                    self._apply_step()
        self._check_test()
        if self.autolap.due(self.t, self.distance_m):
            self.lap(self.autolap.mode)

    def _sample(self) -> None:
        w, hr, spm = self.power_w, self.hr_bpm, self.spm
        self._trail.append((self.t, self.distance_m))
        if len(self._trail) > 3600:
            self._trail = self._trail[-3600:]
        if w and self.ftp:
            self._load_acc += (w / self.ftp) ** 2 / 3600.0 * 100.0
        if w:
            self._watts.append(w)
            self._max_w = max(self._max_w, w)
        if spm:
            self._spms.append(spm)
        if self.pace_s and (self._best_pace is None or self.pace_s < self._best_pace):
            self._best_pace = self.pace_s
        self._hrs.append(hr)
        if hr and self.lthr:
            z = physics.zone_of(hr, self.hr_bounds, self.lthr)
            self.hr_zone_s[min(z, len(self.hr_zone_s)) - 1] += 1.0
        lp = self._lap
        if lp is not None:
            a = lp.acc
            if w:
                a["w"] += w
                a["wn"] += 1
            if spm:
                a["spm"] += spm
                a["sn"] += 1
            if hr:
                a["hr"] += hr
                a["hn"] += 1
                a["mx"] = max(a["mx"], hr)
        self._pending.append((self.session_id, int(self.t), round(self.distance_m, 1),
                              self.pace_s, w, spm, hr, self.resistance, self.strokes))
        if self.game is not None:
            if hasattr(self.game, "my_distance"):
                self.game.my_distance = self.distance_m
            for kind, data in self.game.tick(1.0, w):
                self.events.append(("game_" + kind if not kind.startswith("game") else kind,
                                    data))
            if self.game.finished and not self.game.saved:
                self._save_game()
        if len(self._pending) >= FLUSH_EVERY:
            self.flush()

    def _check_test(self) -> None:
        if not self.test or self.result_value is not None:
            return
        dist, secs, _unit = self.test
        if dist and self.distance_m >= dist - 1e-6:
            self.result_value = round(self.t, 1)
        elif secs and self.t >= secs:
            self.result_value = round(self.distance_m)
        if self.result_value is not None:
            self.events.append(("test_done", {"value": self.result_value,
                                              "unit": self.test[2]}))
            self.lap("test")

    # --------------------------------------------------------- resistência

    def _apply_step(self) -> None:
        if self.workout is None or self.workout.step is None:
            return
        info = self.workout.step_info()
        self.events.append(("step", info))
        if info.get("resistance"):
            self.set_resistance(info["resistance"])

    def _send_level(self, level: int) -> None:
        try:
            self.rower.set_resistance(level)
        except Exception:
            pass

    def set_resistance(self, level: int) -> int:
        level = max(1, min(15, int(level)))
        self._want_level = level
        self.resistance = level
        self._send_level(level)
        self.events.append(("resistance", {"level": level}))
        return level

    def adjust_resistance(self, steps: int) -> int:
        return self.set_resistance((self.resistance or self._want_level or 5) + steps)

    # --------------------------------------------------------------- voltas

    def _open_lap(self, trigger: str, step_idx: int | None = None) -> None:
        self._lap = RowLap(len(self.laps) + 1, self.t, self.distance_m, self.strokes,
                           trigger, step_idx=step_idx)

    def lap(self, trigger: str = "manual", step_idx: int | None = None) -> RowLap | None:
        lp = self._lap
        if lp is None:
            return None
        if self.t - lp.start_t < 1.0 and trigger == "manual":
            return None
        lp.end_t = self.t
        lp.trigger = trigger
        lp.step_idx = step_idx if step_idx is not None else lp.step_idx
        lp.distance_m = self.distance_m - lp.start_m
        lp.strokes = self.strokes - lp.start_strokes
        a = lp.acc
        lp.avg_power_w = a["w"] / a["wn"] if a["wn"] else None
        lp.avg_spm = a["spm"] / a["sn"] if a["sn"] else None
        lp.avg_hr = a["hr"] / a["hn"] if a["hn"] else None
        lp.max_hr = a["mx"] or None
        secs = lp.end_t - lp.start_t
        lp.avg_pace_s = secs / lp.distance_m * 500 if lp.distance_m > 5 else None
        self.laps.append(lp)
        self.db.conn.execute(
            "INSERT INTO row_laps(session_id, lap_no, trigger, start_t, end_t, distance_m,"
            " strokes, avg_pace_s, avg_power_w, avg_spm, avg_hr, max_hr, step_idx)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.session_id, lp.no, trigger, lp.start_t, lp.end_t, lp.distance_m, lp.strokes,
             lp.avg_pace_s, lp.avg_power_w, lp.avg_spm, lp.avg_hr, lp.max_hr, lp.step_idx))
        self.db.conn.commit()
        self.events.append(("lap", {"no": lp.no, "seconds": secs, "distance_m": lp.distance_m,
                                    "avg_pace_s": lp.avg_pace_s, "trigger": trigger}))
        self._open_lap(trigger)
        return lp

    # -------------------------------------------------------------- pausas

    def toggle_pause(self) -> None:
        self.manual_pause = not self.manual_pause
        self.events.append(("paused" if self.manual_pause else "resumed", {}))
        self.checkpoint()

    # ---------------------------------------------------------- recuperação

    def flush(self) -> None:
        if self._pending:
            self.db.conn.executemany(
                "INSERT OR REPLACE INTO row_samples(session_id, t_s, dist_m, pace_s, power_w,"
                " spm, hr_bpm, resistance, strokes) VALUES (?,?,?,?,?,?,?,?,?)",
                self._pending)
            self.db.conn.commit()
            self._pending.clear()
        if not self.finished:
            self.checkpoint()

    def checkpoint(self) -> None:
        state = {"t": self.t, "paused_s": self.paused_s, "distance_m": self.distance_m,
                 "strokes": self.strokes, "kcal": self.kcal, "hr_zone_s": self.hr_zone_s,
                 "resistance": self._want_level, "result": self.result_value,
                 "max_w": self._max_w, "best_pace": self._best_pace,
                 "lap": None if self._lap is None else {
                     k: v for k, v in asdict(self._lap).items()},
                 "workout": self.workout.snapshot() if self.workout else None,
                 "game": self.game.snapshot() if self.game else None}
        try:
            self.db.save_checkpoint(self.session_id, "rowing", {
                "start_unix": self.start_unix, "kind": self.kind, "name": self.title,
                "workout_id": self.workout_id, "protocol": self.protocol,
                "game": self.game_spec or None, "autolap": self.autolap.as_dict()}, state)
        except Exception:
            pass

    def _restore(self, snap: dict) -> None:
        self.t = float(snap.get("t", 0.0))
        self.paused_s = float(snap.get("paused_s", 0.0))
        self.distance_m = float(snap.get("distance_m", 0.0))
        self.strokes = int(snap.get("strokes", 0))
        self.kcal = float(snap.get("kcal", 0.0))
        self._max_w = int(snap.get("max_w") or 0)
        self._best_pace = snap.get("best_pace")
        self.result_value = snap.get("result")
        z = snap.get("hr_zone_s")
        if z and len(z) == len(self.hr_zone_s):
            self.hr_zone_s = [float(v) for v in z]
        self._want_level = snap.get("resistance")
        rows = self.db.conn.execute("SELECT * FROM row_samples WHERE session_id = ? ORDER BY t_s",
                                    (self.session_id,)).fetchall()
        for r in rows:
            if r["power_w"]:
                self._watts.append(r["power_w"])
            if r["spm"]:
                self._spms.append(r["spm"])
            self._hrs.append(r["hr_bpm"])
        if rows:
            self.t = max(self.t, float(rows[-1]["t_s"]))
            self.distance_m = max(self.distance_m, float(rows[-1]["dist_m"] or 0))
        for r in self.db.conn.execute("SELECT * FROM row_laps WHERE session_id = ?"
                                      " ORDER BY lap_no", (self.session_id,)):
            self.laps.append(RowLap(r["lap_no"], r["start_t"], 0.0, 0, r["trigger"],
                                    r["end_t"], r["distance_m"] or 0.0, r["strokes"] or 0,
                                    r["avg_power_w"], r["avg_spm"], r["avg_pace_s"],
                                    r["avg_hr"], r["max_hr"], r["step_idx"]))
        lp = snap.get("lap")
        if lp:
            self._lap = RowLap(**lp)
        else:
            self._open_lap("recovered")
        if self.workout is not None and snap.get("workout"):
            self.workout.restore(snap["workout"])
        if self.game is not None and snap.get("game"):
            self.game.restore(snap["game"])
        self.started = True
        self.manual_pause = True
        self.events.append(("recovered", {"t_s": self.t, "distance_m": self.distance_m}))
        self.autolap.restore(self.t, self.distance_m)

    @property
    def sets(self) -> list:
        """Para o fecho da aplicação: há o que guardar se já se remou."""
        return [1] if self.started and self.t > 0 else []

    def suspend(self) -> None:
        if not self.finished:
            try:
                self.flush()
            except Exception:
                pass

    # ---------------------------------------------------------------- fim

    def _save_game(self) -> None:
        if self.game is None or self.game.saved:
            return
        self.game_result = save_game(self.db, self.session_id, self.game)
        self.events.append(("game_saved", self.game_result))

    def summary(self) -> dict:
        hrs = [h for h in self._hrs if h]
        np_w = physics.normalized_power(self._watts) if len(self._watts) >= 30 else (
            self.avg_power_w)
        load, source = None, None
        if np_w and self.ftp:
            if_ = np_w / self.ftp
            load, source = self.t / 3600.0 * if_ * if_ * 100.0, "power"
        if load is None:
            load = st.hr_load(self._hrs, self.lthr)
            source = "hr" if load is not None else None
        return {"elapsed_s": int(self.t + self.paused_s), "moving_s": int(self.t),
                "paused_s": int(self.paused_s), "distance_m": round(self.distance_m, 1),
                "strokes": self.strokes, "avg_spm": self.avg_spm,
                "avg_pace_s": self.avg_pace_s, "best_pace_s": self._best_pace,
                "avg_power_w": self.avg_power_w, "max_power_w": self._max_w or None,
                "np_w": np_w, "kcal": round(self.kcal) if self.kcal else None,
                "avg_hr": sum(hrs) / len(hrs) if hrs else None,
                "max_hr": max(hrs) if hrs else None, "load": load, "load_source": source,
                "hr_zone_s": list(self.hr_zone_s), "ftp_w": self.ftp,
                "laps": list(self.laps), "result": self.result_value, "kind": self.kind,
                "title": self.title, "protocol": self.protocol,
                "workout_results": self.workout.results if self.workout else []}

    def finish(self) -> dict:
        if self.finished:
            return {}
        if self.game is not None and not self.game.finished and self.started:
            self.game.end()
        if self.game is not None and not self.game.saved and self.started:
            self._save_game()
        self.lap("end")
        self.flush()
        self.finished = True
        summ = self.summary()
        base = naming.activity_name(self.start_unix, workout_name=("remo-" + self.title).replace("×", "x"),
                                    kind="workout")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path, name = naming.unique_path(self.out_dir, base)
        fit_path = None
        try:
            from . import fit
            samples = [dict(r) for r in self.db.conn.execute(
                "SELECT * FROM row_samples WHERE session_id = ? ORDER BY t_s",
                (self.session_id,))]
            for s in samples:
                s["speed_mps"] = 500.0 / s["pace_s"] if s.get("pace_s") else None
            laps = [{"start_t": lp.start_t, "end_t": lp.end_t, "distance_m": lp.distance_m,
                     "avg_hr": lp.avg_hr, "max_hr": lp.max_hr, "strokes": lp.strokes,
                     "avg_power_w": None if lp.avg_power_w is None else int(lp.avg_power_w),
                     "avg_spm": lp.avg_spm,
                     "trigger": {"workout_step": "workout_step", "end": "session_end"}.get(
                         lp.trigger, "manual")} for lp in self.laps]
            fs = dict(summ)
            for k in ("avg_power_w", "np_w"):
                fs[k] = None if fs[k] is None else int(round(fs[k]))
            fit.write_rowing(path, self.athlete, samples, laps, fs, self.start_unix, name=name)
            fit_path = str(path)
        except Exception as e:
            self.events.append(("fit_error", {"message": str(e)}))
        self.db.conn.execute(
            "UPDATE row_sessions SET status='completed', ended_at=?, elapsed_s=?, moving_s=?,"
            " paused_s=?, distance_m=?, strokes=?, avg_spm=?, avg_pace_s=?, best_pace_s=?,"
            " avg_power_w=?, max_power_w=?, np_w=?, kcal=?, avg_hr=?, max_hr=?, load=?,"
            " load_source=?, hr_zone_s=?, fit_path=?, name=?, result=? WHERE id = ?",
            (now_iso(), summ["elapsed_s"], summ["moving_s"], summ["paused_s"],
             summ["distance_m"], summ["strokes"], summ["avg_spm"], summ["avg_pace_s"],
             summ["best_pace_s"], summ["avg_power_w"], summ["max_power_w"], summ["np_w"],
             summ["kcal"], summ["avg_hr"], summ["max_hr"], summ["load"], summ["load_source"],
             json.dumps(summ["hr_zone_s"]), fit_path, name, summ["result"], self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)
        if self.protocol and self.result_value is not None:
            from . import fitness_tests as ft
            link_tests(self.db)
            ft.record_protocol(self.db, self.protocol, self.result_value, None,
                               extra={"row_session": self.session_id})
            if self.protocol == "row_2000" and self.avg_power_w:
                # FTP do remo ≈ 85 % da potência média de 2 km (como no ciclismo:
                # o esforço de ~7 min fica bem acima do limiar)
                self.db.set("row_ftp_w", int(round(self.avg_power_w * 0.85)))
        summ.update(session_id=self.session_id, name=name, fit_path=fit_path,
                    game=getattr(self, "game_result", None))
        return summ

    def abort(self) -> None:
        self.finished = True
        self.db.conn.execute("UPDATE row_sessions SET status='aborted', ended_at=? WHERE id = ?",
                             (now_iso(), self.session_id))
        self.db.conn.commit()
        self.db.delete_checkpoint(self.session_id)

    def discard(self) -> None:
        """«Terminar sem guardar»: a sessão desaparece."""
        self.abort()
        self.db.conn.execute("DELETE FROM row_sessions WHERE id = ?", (self.session_id,))
        self.db.conn.commit()

    # ------------------------------------------------------ mais métricas

    @property
    def lap_elapsed_s(self) -> float:
        return self.t - self._lap.start_t if self._lap else 0.0

    @property
    def lap_distance_m(self) -> float:
        return self.distance_m - self._lap.start_m if self._lap else 0.0

    @property
    def lap_pace_s(self) -> float | None:
        d = self.lap_distance_m
        return self.lap_elapsed_s / d * 500 if d > 10 else None

    @property
    def last_lap(self) -> RowLap | None:
        return self.laps[-1] if self.laps else None

    def split(self, meters: float = 500.0) -> float | None:
        """Tempo dos últimos `meters` metros (o «split» dos remos)."""
        if self.distance_m < meters or not self._trail:
            return None
        target = self.distance_m - meters
        for t_, d in reversed(self._trail):
            if d <= target:
                return self.t - t_
        return None

    @property
    def max_hr(self) -> int | None:
        v = [h for h in self._hrs if h]
        return max(v) if v else None

    @property
    def avg_hr(self) -> float | None:
        v = [h for h in self._hrs if h]
        return sum(v) / len(v) if v else None

    @property
    def joules_per_stroke(self) -> float | None:
        if self.power_w and self.spm:
            return self.power_w * 60.0 / self.spm
        return None

    @property
    def live_load(self) -> float:
        return self._load_acc

    @property
    def pct_ftp(self) -> float | None:
        return self.power_w / self.ftp * 100 if self.power_w and self.ftp else None

    @property
    def kcal_per_hour(self) -> float | None:
        # Concept2: kcal/h ≈ 4 × W × 0,8604 + 300
        return 4 * self.power_w * 0.8604 + 300 if self.power_w else None

    def target_delta(self) -> float | None:
        """Diferença para o meio do alvo do passo, em s/500 m (+ = mais lento)."""
        if self.workout is None or self.workout.step is None or not self.pace_s:
            return None
        rng = self.workout.step.pace_range(self.ftp)
        if not rng or not rng[0] or not rng[1]:
            return None
        return self.pace_s - (rng[0] + rng[1]) / 2

    def projected_finish(self) -> float | None:
        """Num teste por distância ou na regata: o tempo final ao ritmo médio."""
        dist = None
        if self.test and self.test[0]:
            dist = self.test[0]
        elif self.game is not None and getattr(self.game, "distance", None):
            dist = self.game.distance
        if not dist or self.distance_m < 20:
            return None
        return self.t / self.distance_m * dist


# =============================================================== histórico


def sessions(db: Database, limit: int = 100) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM row_sessions WHERE status='completed' ORDER BY started_at DESC LIMIT ?",
        (limit,))]


def session_laps(db: Database, sid: str) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM row_laps WHERE session_id = ? ORDER BY lap_no", (sid,))]


def bests(db: Database) -> dict:
    """Recordes: melhor 500 m (ritmo), maior distância, mais potência média."""
    ensure(db)
    r = db.conn.execute(
        "SELECT MIN(best_pace_s) AS pace, MAX(distance_m) AS dist, MAX(avg_power_w) AS w,"
        " COUNT(*) AS n, SUM(distance_m) AS total FROM row_sessions WHERE status='completed'"
    ).fetchone()
    out = dict(r) if r else {}
    out["sessions"] = best_sessions(db)
    return out


def best_sessions(db: Database) -> dict[str, dict]:
    """A sessão onde cada recorde foi feito: {recorde: linha da sessão}."""
    ensure(db)
    picks = {"pace": "best_pace_s IS NOT NULL ORDER BY best_pace_s ASC",
             "avg_pace": "avg_pace_s IS NOT NULL AND distance_m > 0 ORDER BY avg_pace_s ASC",
             "dist": "distance_m IS NOT NULL ORDER BY distance_m DESC",
             "w": "avg_power_w IS NOT NULL ORDER BY avg_power_w DESC",
             "max_w": "max_power_w IS NOT NULL ORDER BY max_power_w DESC",
             "spm": "avg_spm IS NOT NULL ORDER BY avg_spm DESC",
             "time": "COALESCE(moving_s, elapsed_s) IS NOT NULL"
                     " ORDER BY COALESCE(moving_s, elapsed_s) DESC"}
    out = {}
    for k, cond in picks.items():
        row = db.conn.execute(f"SELECT * FROM row_sessions WHERE status='completed' AND {cond}"
                              " LIMIT 1").fetchone()
        if row is not None:
            out[k] = dict(row)
    return out
