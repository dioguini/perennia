"""Base de dados local SQLite (req. 10).

Um único ficheiro portátil: copiar `perennia.db` para outro computador
repõe todo o histórico. Nada sai daqui para a rede.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
  version    INTEGER NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS athlete (
  id             INTEGER PRIMARY KEY CHECK (id = 1),
  name           TEXT NOT NULL DEFAULT '',
  birth_year     INTEGER,
  weight_kg      REAL NOT NULL DEFAULT 75.0,
  ftp_w          INTEGER NOT NULL DEFAULT 200,
  max_hr         INTEGER,
  lthr           INTEGER,
  bike_weight_kg REAL NOT NULL DEFAULT 8.0,
  cda            REAL NOT NULL DEFAULT 0.32,
  crr            REAL NOT NULL DEFAULT 0.004
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
  id            TEXT PRIMARY KEY,
  transport     TEXT NOT NULL,
  name          TEXT,
  profiles      TEXT NOT NULL DEFAULT '[]',
  capabilities  INTEGER NOT NULL DEFAULT 0,
  priority_json TEXT NOT NULL DEFAULT '{}',
  auto_connect  INTEGER NOT NULL DEFAULT 1,
  last_seen_at  TEXT,
  role          TEXT
);

CREATE TABLE IF NOT EXISTS trainer_calibrations (
  id           INTEGER PRIMARY KEY,
  device_id    TEXT NOT NULL,
  performed_at TEXT NOT NULL,
  method       TEXT NOT NULL,
  detail       TEXT,
  success      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS routes (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  source_filename TEXT,
  distance_m      REAL NOT NULL,
  ascent_m        REAL NOT NULL,
  descent_m       REAL NOT NULL,
  max_grade_pct   REAL NOT NULL,
  min_ele_m       REAL,
  max_ele_m       REAL,
  bbox_json       TEXT NOT NULL,
  origin_lat      REAL NOT NULL,
  origin_lon      REAL NOT NULL,
  point_count     INTEGER NOT NULL,
  imported_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  times_ridden    INTEGER NOT NULL DEFAULT 0,
  favorite        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS route_points (
  route_id    TEXT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  idx         INTEGER NOT NULL,
  dist_m      REAL NOT NULL,
  lat         REAL NOT NULL,
  lon         REAL NOT NULL,
  x_m         REAL NOT NULL,
  y_m         REAL NOT NULL,
  ele_m       REAL NOT NULL,
  grade_pct   REAL NOT NULL,
  heading_deg REAL NOT NULL,
  PRIMARY KEY (route_id, idx)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS route_bakes (
  route_id   TEXT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  preset     TEXT NOT NULL,
  status     TEXT NOT NULL,
  baker_ver  INTEGER NOT NULL,
  cache_path TEXT,
  baked_at   TEXT,
  PRIMARY KEY (route_id, preset)
);

CREATE TABLE IF NOT EXISTS climbs (
  id            INTEGER PRIMARY KEY,
  route_id      TEXT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  seq           INTEGER NOT NULL,
  name          TEXT NOT NULL,
  start_m       REAL NOT NULL,
  end_m         REAL NOT NULL,
  length_m      REAL NOT NULL,
  gain_m        REAL NOT NULL,
  avg_grade_pct REAL NOT NULL,
  max_grade_pct REAL NOT NULL,
  category      TEXT NOT NULL,
  score         REAL NOT NULL,
  UNIQUE (route_id, seq)
);

CREATE TABLE IF NOT EXISTS workouts (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  source_format TEXT,
  description   TEXT,
  total_seconds INTEGER,
  est_tss       REAL,
  imported_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS workout_steps (
  workout_id  TEXT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
  idx         INTEGER NOT NULL,
  kind        TEXT NOT NULL,
  duration_s  INTEGER,
  target_type TEXT NOT NULL,
  target_lo   REAL,
  target_hi   REAL,
  cadence_lo  INTEGER,
  cadence_hi  INTEGER,
  text_cue    TEXT,
  PRIMARY KEY (workout_id, idx)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS rides (
  id                 TEXT PRIMARY KEY,
  route_id           TEXT REFERENCES routes(id) ON DELETE SET NULL,
  workout_id         TEXT REFERENCES workouts(id) ON DELETE SET NULL,
  kind               TEXT NOT NULL DEFAULT 'route',
  mode               TEXT NOT NULL DEFAULT 'alone',
  erg_enabled        INTEGER NOT NULL DEFAULT 0,
  status             TEXT NOT NULL,
  started_at         TEXT NOT NULL,
  ended_at           TEXT,
  elapsed_s          INTEGER,
  moving_s           INTEGER,
  distance_m         REAL,
  ascent_m           REAL,
  completed_route    INTEGER NOT NULL DEFAULT 0,
  route_loops        INTEGER NOT NULL DEFAULT 0,
  best_loop_s        INTEGER,
  paused_s           INTEGER NOT NULL DEFAULT 0,
  avg_power_w        REAL,
  max_power_w        INTEGER,
  np_w               REAL,
  intensity_factor   REAL,
  tss                REAL,
  work_kj            REAL,
  avg_hr             REAL,
  max_hr             INTEGER,
  avg_cadence        REAL,
  avg_speed_mps      REAL,
  avg_balance_left   REAL,
  ftp_at_ride_w      INTEGER NOT NULL,
  weight_at_ride_kg  REAL NOT NULL,
  trainer_difficulty REAL,
  extra_resistance_pct REAL,
  render_preset      TEXT,
  fit_path           TEXT,
  notes              TEXT
);
CREATE INDEX IF NOT EXISTS ix_rides_route ON rides(route_id, started_at);
CREATE INDEX IF NOT EXISTS ix_rides_started ON rides(started_at);

CREATE TABLE IF NOT EXISTS ride_samples (
  ride_id         TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  t_s             INTEGER NOT NULL,
  dist_m          REAL NOT NULL,
  speed_mps       REAL,
  power_w         INTEGER,
  cadence_rpm     INTEGER,
  hr_bpm          INTEGER,
  balance_left    REAL,
  torque_nm       REAL,
  grade_pct       REAL,
  ele_m           REAL,
  target_power_w  INTEGER,
  resistance_sent REAL,
  lap_no          INTEGER NOT NULL DEFAULT 1,
  te_left         REAL,
  te_right        REAL,
  ps_left         REAL,
  ps_right        REAL,
  ps_combined     REAL,
  PRIMARY KEY (ride_id, t_s)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS laps (
  id           INTEGER PRIMARY KEY,
  ride_id      TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  lap_no       INTEGER NOT NULL,
  trigger      TEXT NOT NULL,
  start_t_s    INTEGER NOT NULL,
  end_t_s      INTEGER NOT NULL,
  start_dist_m REAL NOT NULL,
  end_dist_m   REAL NOT NULL,
  avg_power_w  REAL,
  np_w         REAL,
  max_power_w  INTEGER,
  avg_hr       REAL,
  max_hr       INTEGER,
  avg_cadence  REAL,
  avg_speed_mps REAL,
  ascent_m     REAL,
  avg_balance_left REAL,
  UNIQUE (ride_id, lap_no)
);

CREATE TABLE IF NOT EXISTS route_efforts (
  id          INTEGER PRIMARY KEY,
  route_id    TEXT NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
  ride_id     TEXT NOT NULL UNIQUE REFERENCES rides(id) ON DELETE CASCADE,
  elapsed_s   INTEGER NOT NULL,
  avg_power_w REAL,
  avg_hr      REAL,
  avg_cadence REAL,
  np_w        REAL
);
CREATE INDEX IF NOT EXISTS ix_route_efforts ON route_efforts(route_id, elapsed_s);

CREATE TABLE IF NOT EXISTS climb_efforts (
  id          INTEGER PRIMARY KEY,
  climb_id    INTEGER NOT NULL REFERENCES climbs(id) ON DELETE CASCADE,
  ride_id     TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  start_t_s   INTEGER NOT NULL,
  end_t_s     INTEGER NOT NULL,
  elapsed_s   INTEGER NOT NULL,
  avg_power_w REAL,
  avg_hr      REAL,
  avg_cadence REAL,
  vam_mh      REAL,
  avg_balance_left REAL
);
CREATE INDEX IF NOT EXISTS ix_climb_efforts ON climb_efforts(climb_id, elapsed_s);

CREATE TABLE IF NOT EXISTS ride_comparisons (
  ride_id       TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  ghost_ride_id TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  final_delta_s REAL,
  PRIMARY KEY (ride_id, ghost_ride_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS workout_step_results (
  ride_id       TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  step_idx      INTEGER NOT NULL,
  avg_power_w   REAL,
  target_avg_w  REAL,
  pct_in_target REAL,
  avg_hr        REAL,
  avg_cadence   REAL,
  PRIMARY KEY (ride_id, step_idx)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ride_power_curve (
  ride_id    TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  duration_s INTEGER NOT NULL,
  max_avg_w  REAL NOT NULL,
  PRIMARY KEY (ride_id, duration_s)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS ftp_tests (
  id          INTEGER PRIMARY KEY,
  ride_id     TEXT REFERENCES rides(id) ON DELETE SET NULL,
  protocol    TEXT NOT NULL,
  tested_at   TEXT NOT NULL,
  raw_value_w REAL,
  ftp_w       INTEGER NOT NULL,
  accepted    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS challenges (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  metric     TEXT NOT NULL,
  target     REAL NOT NULL,
  is_default INTEGER NOT NULL DEFAULT 0,
  display_unit TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS challenge_attempts (
  id                 INTEGER PRIMARY KEY,
  challenge_id       INTEGER NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
  started_at         TEXT NOT NULL,
  completed_at       TEXT,
  progress           REAL NOT NULL DEFAULT 0,
  elapsed_s          REAL,
  completing_ride_id TEXT REFERENCES rides(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_attempts ON challenge_attempts(challenge_id, elapsed_s);

CREATE TABLE IF NOT EXISTS chase_efforts (
  id             INTEGER PRIMARY KEY,
  ride_id        TEXT NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
  route_id       TEXT REFERENCES routes(id) ON DELETE SET NULL,
  level          TEXT NOT NULL,
  survived_s     REAL NOT NULL,
  distance_m     REAL NOT NULL,
  avg_power_w    REAL,
  final_chaser_w INTEGER,
  caught         INTEGER NOT NULL,
  clean          INTEGER NOT NULL DEFAULT 1,
  created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chase ON chase_efforts(level, survived_s);

-- Ponto de recuperação de uma sessão em curso (ciclismo ou força). Se a
-- aplicação fechar de repente, é com isto que se retoma.
CREATE TABLE IF NOT EXISTS session_checkpoints (
  session_id TEXT PRIMARY KEY,
  sport      TEXT NOT NULL,
  saved_at   TEXT NOT NULL,
  config     TEXT NOT NULL,
  state      TEXT NOT NULL
);

-- ------------------------------------------------------------- força
CREATE TABLE IF NOT EXISTS exercises (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL DEFAULT 'other',
  fit_category INTEGER,
  bodyweight  REAL NOT NULL DEFAULT 0,
  measure     TEXT NOT NULL DEFAULT 'reps',
  custom      INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS strength_workouts (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS strength_workout_items (
  workout_id  TEXT NOT NULL REFERENCES strength_workouts(id) ON DELETE CASCADE,
  idx         INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  sets        INTEGER NOT NULL DEFAULT 3,
  reps        INTEGER NOT NULL DEFAULT 10,
  load_kg     REAL,
  rpe         REAL,
  rest_s      INTEGER NOT NULL DEFAULT 90,
  notes       TEXT,
  PRIMARY KEY (workout_id, idx)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS strength_sessions (
  id           TEXT PRIMARY KEY,
  workout_id   TEXT REFERENCES strength_workouts(id) ON DELETE SET NULL,
  name         TEXT,
  status       TEXT NOT NULL,
  started_at   TEXT NOT NULL,
  ended_at     TEXT,
  elapsed_s    INTEGER,
  paused_s     INTEGER NOT NULL DEFAULT 0,
  total_sets   INTEGER,
  total_reps   INTEGER,
  volume_kg    REAL,
  avg_rpe      REAL,
  avg_hr       REAL,
  max_hr       INTEGER,
  load         REAL,
  load_source  TEXT,
  hr_zone_s    TEXT,
  lthr_at_session INTEGER,
  weight_at_session_kg REAL,
  fit_path     TEXT
);
CREATE INDEX IF NOT EXISTS ix_strength_started ON strength_sessions(started_at);

CREATE TABLE IF NOT EXISTS strength_sets (
  id          INTEGER PRIMARY KEY,
  session_id  TEXT NOT NULL REFERENCES strength_sessions(id) ON DELETE CASCADE,
  item_idx    INTEGER,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  set_no      INTEGER NOT NULL,
  reps        INTEGER NOT NULL,
  load_kg     REAL,
  rpe         REAL,
  start_t_s   INTEGER,
  end_t_s     INTEGER,
  avg_hr      REAL,
  max_hr      INTEGER,
  planned_reps INTEGER,
  planned_load_kg REAL
);
CREATE INDEX IF NOT EXISTS ix_strength_sets ON strength_sets(session_id, id);
CREATE INDEX IF NOT EXISTS ix_strength_sets_ex ON strength_sets(exercise_id);

CREATE TABLE IF NOT EXISTS strength_hr (
  session_id TEXT NOT NULL REFERENCES strength_sessions(id) ON DELETE CASCADE,
  t_s        INTEGER NOT NULL,
  hr_bpm     INTEGER,
  PRIMARY KEY (session_id, t_s)
) WITHOUT ROWID;

CREATE VIEW IF NOT EXISTS v_totals AS
SELECT COUNT(*) AS rides,
       COALESCE(SUM(moving_s), 0) / 3600.0 AS hours,
       COALESCE(SUM(distance_m), 0) / 1000.0 AS km,
       COALESCE(SUM(ascent_m), 0) AS ascent_m,
       AVG(avg_cadence) AS avg_cadence,
       COALESCE(SUM(tss), 0) AS tss,
       MAX(max_power_w) AS max_power_w
FROM rides WHERE status = 'completed';
"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "units": "metric",
    "language": "pt_PT",
    "render_preset": "low",
    "trainer_difficulty": 1.0,
    "extra_resistance_pct": 0.0,
    "hud_metrics": [
        "power", "hr", "cadence", "speed", "dist_done", "dist_left",
        "grade_now", "avg_grade_1km", "elapsed", "avg_power", "power_balance",
        "torque_eff", "pedal_smooth",
    ],
    "power_zones_pct": [55, 75, 90, 105, 120, 150],
    "hr_zones_pct_lthr": [68, 83, 94, 105],
    "climb_min_length_m": 500.0,
    "climb_min_avg_grade": 3.0,
    "climb_min_gain_m": 60.0,
    "fit_include_coords": True,
    "auto_pause": True,
    "msaa_samples": 4,
    "workout_lookahead": 2,
    "connection_preference": "ant_first",
    "auto_connect": True,
    "chase_level": "normal",
}

DEFAULT_CHALLENGES = [
    ("Pedalar 500 km", "distance_m", 500_000.0),
    ("Pedalar 1000 km", "distance_m", 1_000_000.0),
    ("Subir 500 m", "ascent_m", 500.0),
    ("Subir 1000 m", "ascent_m", 1000.0),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_id() -> str:
    return str(uuid.uuid4())


# ----------------------------------------------------------------- estruturas


@dataclass
class RoutePoint:
    dist_m: float
    lat: float
    lon: float
    x_m: float
    y_m: float
    ele_m: float
    grade_pct: float
    heading_deg: float


@dataclass
class Climb:
    seq: int
    name: str
    start_m: float
    end_m: float
    length_m: float
    gain_m: float
    avg_grade_pct: float
    max_grade_pct: float
    category: str
    score: float
    id: int | None = None


@dataclass
class Athlete:
    name: str = ""
    birth_year: int | None = None
    weight_kg: float = 75.0
    ftp_w: int = 200
    max_hr: int | None = None
    lthr: int | None = None
    bike_weight_kg: float = 8.0
    cda: float = 0.32
    crr: float = 0.004

    @property
    def age(self) -> int | None:
        if self.birth_year is None:
            return None
        return datetime.now().year - self.birth_year

    @property
    def total_mass_kg(self) -> float:
        return self.weight_kg + self.bike_weight_kg


PEDAL_KEYS = ("te_left", "te_right", "ps_left", "ps_right", "ps_combined")


@dataclass
class Sample:
    t_s: int
    dist_m: float
    speed_mps: float = 0.0
    power_w: int | None = None
    cadence_rpm: int | None = None
    hr_bpm: int | None = None
    balance_left: float | None = None
    torque_nm: float | None = None
    grade_pct: float = 0.0
    ele_m: float = 0.0
    target_power_w: int | None = None
    resistance_sent: float | None = None
    lap_no: int = 1
    te_left: float | None = None
    te_right: float | None = None
    ps_left: float | None = None
    ps_right: float | None = None
    ps_combined: float | None = None


@dataclass
class Lap:
    lap_no: int
    trigger: str
    start_t_s: int
    end_t_s: int
    start_dist_m: float
    end_dist_m: float
    avg_power_w: float | None = None
    np_w: float | None = None
    max_power_w: int | None = None
    avg_hr: float | None = None
    max_hr: int | None = None
    avg_cadence: float | None = None
    avg_speed_mps: float | None = None
    ascent_m: float = 0.0
    avg_balance_left: float | None = None
    pedal: dict = field(default_factory=dict)     # médias de te_/ps_ da volta


@dataclass
class RideSummary:
    elapsed_s: int = 0
    moving_s: int = 0
    distance_m: float = 0.0
    ascent_m: float = 0.0
    avg_power_w: float | None = None
    max_power_w: int | None = None
    np_w: float | None = None
    intensity_factor: float | None = None
    tss: float | None = None
    work_kj: float | None = None
    avg_hr: float | None = None
    max_hr: int | None = None
    avg_cadence: float | None = None
    avg_speed_mps: float = 0.0
    avg_balance_left: float | None = None
    completed_route: bool = False
    route_loops: int = 0
    best_loop_s: int | None = None
    paused_s: int = 0
    pedal: dict = field(default_factory=dict)     # médias de te_/ps_ da sessão
    power_curve: list[tuple[int, float]] = field(default_factory=list)


# ------------------------------------------------------------------ base


class Database:
    """Acesso a tudo. Métodos curtos, SQL explícito, sem ORM."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        """Pode ser chamado mais do que uma vez: as seguintes não fazem nada."""
        if getattr(self, "_closed", False):
            return
        self._closed = True
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    def _migrate(self) -> None:
        self.conn.executescript(SCHEMA)
        # Colunas acrescentadas depois da v1: bases antigas recebem-nas aqui.
        existing = {r["name"] for r in self.conn.execute("PRAGMA table_info(rides)")}
        for column, decl in (("route_loops", "INTEGER NOT NULL DEFAULT 0"),
                             ("best_loop_s", "INTEGER"),
                             ("paused_s", "INTEGER NOT NULL DEFAULT 0")):
            if column not in existing:
                self.conn.execute(f"ALTER TABLE rides ADD COLUMN {column} {decl}")
        for table in ("laps", "climb_efforts"):
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if "avg_balance_left" not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN avg_balance_left REAL")
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(devices)")}
        if "role" not in cols:
            self.conn.execute("ALTER TABLE devices ADD COLUMN role TEXT")
        additions = {
            "ride_samples": [(k, "REAL") for k in PEDAL_KEYS],
            "laps": [(f"avg_{k}", "REAL") for k in PEDAL_KEYS],
            "rides": [(f"avg_{k}", "REAL") for k in PEDAL_KEYS] + [("name", "TEXT")],
        }
        for table, columns in additions.items():
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for column, decl in columns:
                if column not in cols:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        existing = {r["name"] for r in self.conn.execute("PRAGMA table_info(challenges)")}
        if "display_unit" not in existing:
            # a unidade em que o atleta escreveu o objetivo (km, m, mi, ft)
            self.conn.execute("ALTER TABLE challenges ADD COLUMN display_unit TEXT")
        row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        if row is None or row["v"] is None:
            self.conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
        self.conn.execute("INSERT OR IGNORE INTO athlete(id) VALUES (1)")
        for k, v in DEFAULT_SETTINGS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, json.dumps(v))
            )
        # Uma vez só: métricas novas entram no HUD de quem já tinha a lista
        # gravada. Se o atleta as tirar depois, não voltam.
        for flag, new_metrics in (("migr_balance_hud", ("power_balance",)),
                                  ("migr_pedal_hud", ("torque_eff", "pedal_smooth"))):
            if self.conn.execute("SELECT 1 FROM settings WHERE key = ?",
                                 (flag,)).fetchone() is not None:
                continue
            row = self.conn.execute(
                "SELECT value FROM settings WHERE key = 'hud_metrics'").fetchone()
            if row is not None:
                hud = json.loads(row["value"])
                hud += [m for m in new_metrics if m not in hud]
                self.conn.execute("UPDATE settings SET value = ? WHERE key = 'hud_metrics'",
                                  (json.dumps(hud),))
            self.conn.execute("INSERT INTO settings(key, value) VALUES (?, 'true')",
                              (flag,))
        if self.conn.execute("SELECT COUNT(*) AS n FROM challenges").fetchone()["n"] == 0:
            self.conn.executemany(
                "INSERT INTO challenges(name, metric, target, is_default) VALUES (?,?,?,1)",
                DEFAULT_CHALLENGES,
            )
        self.conn.commit()

    # -------------------------------------------------------- definições

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        return json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self.conn.commit()

    def athlete(self) -> Athlete:
        r = self.conn.execute("SELECT * FROM athlete WHERE id = 1").fetchone()
        return Athlete(
            name=r["name"], birth_year=r["birth_year"], weight_kg=r["weight_kg"],
            ftp_w=r["ftp_w"], max_hr=r["max_hr"], lthr=r["lthr"],
            bike_weight_kg=r["bike_weight_kg"], cda=r["cda"], crr=r["crr"],
        )

    def save_athlete(self, a: Athlete) -> None:
        self.conn.execute(
            "UPDATE athlete SET name=?, birth_year=?, weight_kg=?, ftp_w=?, max_hr=?, lthr=?,"
            " bike_weight_kg=?, cda=?, crr=? WHERE id = 1",
            (a.name, a.birth_year, a.weight_kg, a.ftp_w, a.max_hr, a.lthr,
             a.bike_weight_kg, a.cda, a.crr),
        )
        self.conn.commit()

    # ------------------------------------------------------------ rotas

    def insert_route(self, name: str, points: Sequence[RoutePoint], climbs: Sequence[Climb],
                     source_filename: str | None = None) -> str:
        """Cada importação cria uma rota nova. Não há deduplicação (req. 5)."""
        rid = new_id()
        eles = [p.ele_m for p in points]
        ascent = sum(max(0.0, b.ele_m - a.ele_m) for a, b in zip(points, points[1:]))
        descent = sum(max(0.0, a.ele_m - b.ele_m) for a, b in zip(points, points[1:]))
        lats = [p.lat for p in points]
        lons = [p.lon for p in points]
        self.conn.execute(
            "INSERT INTO routes(id, name, source_filename, distance_m, ascent_m, descent_m,"
            " max_grade_pct, min_ele_m, max_ele_m, bbox_json, origin_lat, origin_lon, point_count)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, name, source_filename, points[-1].dist_m, ascent, descent,
             max((p.grade_pct for p in points), default=0.0), min(eles), max(eles),
             json.dumps([min(lats), min(lons), max(lats), max(lons)]),
             points[0].lat, points[0].lon, len(points)),
        )
        self.conn.executemany(
            "INSERT INTO route_points(route_id, idx, dist_m, lat, lon, x_m, y_m, ele_m,"
            " grade_pct, heading_deg) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(rid, i, p.dist_m, p.lat, p.lon, p.x_m, p.y_m, p.ele_m, p.grade_pct, p.heading_deg)
             for i, p in enumerate(points)],
        )
        self.conn.executemany(
            "INSERT INTO climbs(route_id, seq, name, start_m, end_m, length_m, gain_m,"
            " avg_grade_pct, max_grade_pct, category, score) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(rid, c.seq, c.name, c.start_m, c.end_m, c.length_m, c.gain_m,
              c.avg_grade_pct, c.max_grade_pct, c.category, c.score) for c in climbs],
        )
        self.conn.commit()
        return rid

    def routes(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM climbs c WHERE c.route_id = r.id) AS climb_count"
            " FROM routes r ORDER BY r.favorite DESC, r.imported_at DESC"
        ).fetchall()

    def route(self, route_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM routes WHERE id = ?", (route_id,)).fetchone()

    def route_points(self, route_id: str) -> list[RoutePoint]:
        rows = self.conn.execute(
            "SELECT dist_m, lat, lon, x_m, y_m, ele_m, grade_pct, heading_deg"
            " FROM route_points WHERE route_id = ? ORDER BY idx", (route_id,)
        ).fetchall()
        return [RoutePoint(*tuple(r)) for r in rows]

    def climbs(self, route_id: str) -> list[Climb]:
        rows = self.conn.execute(
            "SELECT id, seq, name, start_m, end_m, length_m, gain_m, avg_grade_pct,"
            " max_grade_pct, category, score FROM climbs WHERE route_id = ? ORDER BY seq",
            (route_id,),
        ).fetchall()
        return [Climb(seq=r["seq"], name=r["name"], start_m=r["start_m"], end_m=r["end_m"],
                      length_m=r["length_m"], gain_m=r["gain_m"], avg_grade_pct=r["avg_grade_pct"],
                      max_grade_pct=r["max_grade_pct"], category=r["category"], score=r["score"],
                      id=r["id"]) for r in rows]

    def delete_route(self, route_id: str) -> None:
        self.conn.execute("DELETE FROM routes WHERE id = ?", (route_id,))
        self.conn.commit()

    def toggle_favorite(self, route_id: str) -> None:
        self.conn.execute("UPDATE routes SET favorite = 1 - favorite WHERE id = ?", (route_id,))
        self.conn.commit()

    def set_bake(self, route_id: str, preset: str, status: str, baker_ver: int,
                 cache_path: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO route_bakes(route_id, preset, status, baker_ver, cache_path, baked_at)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT(route_id, preset) DO UPDATE SET"
            " status=excluded.status, baker_ver=excluded.baker_ver,"
            " cache_path=excluded.cache_path, baked_at=excluded.baked_at",
            (route_id, preset, status, baker_ver, cache_path, now_iso()),
        )
        self.conn.commit()

    def bake(self, route_id: str, preset: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM route_bakes WHERE route_id = ? AND preset = ?", (route_id, preset)
        ).fetchone()

    # --------------------------------------------------------- sessões

    def begin_ride(self, *, route_id: str | None, workout_id: str | None, kind: str, mode: str,
                   erg: bool, athlete: Athlete, difficulty: float, extra: float,
                   preset: str) -> str:
        rid = new_id()
        # Uma sessão sem rota (treino solto, teste de FTP) grava NULL. Uma
        # cadeia vazia violaria a chave estrangeira e abortava o arranque.
        route_id = route_id or None
        workout_id = workout_id or None
        self.conn.execute(
            "INSERT INTO rides(id, route_id, workout_id, kind, mode, erg_enabled, status,"
            " started_at, ftp_at_ride_w, weight_at_ride_kg, trainer_difficulty,"
            " extra_resistance_pct, render_preset) VALUES (?,?,?,?,?,?,'recording',?,?,?,?,?,?)",
            (rid, route_id, workout_id, kind, mode, int(erg), now_iso(), athlete.ftp_w,
             athlete.weight_kg, difficulty, extra, preset),
        )
        self.conn.commit()
        return rid

    def append_samples(self, ride_id: str, samples: Iterable[Sample]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO ride_samples(ride_id, t_s, dist_m, speed_mps, power_w,"
            " cadence_rpm, hr_bpm, balance_left, torque_nm, grade_pct, ele_m, target_power_w,"
            " resistance_sent, lap_no, te_left, te_right, ps_left, ps_right, ps_combined)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(ride_id, s.t_s, s.dist_m, s.speed_mps, s.power_w, s.cadence_rpm, s.hr_bpm,
              s.balance_left, s.torque_nm, s.grade_pct, s.ele_m, s.target_power_w,
              s.resistance_sent, s.lap_no, s.te_left, s.te_right, s.ps_left, s.ps_right,
              s.ps_combined) for s in samples],
        )
        self.conn.commit()

    def samples(self, ride_id: str) -> list[Sample]:
        rows = self.conn.execute(
            "SELECT t_s, dist_m, speed_mps, power_w, cadence_rpm, hr_bpm, balance_left,"
            " torque_nm, grade_pct, ele_m, target_power_w, resistance_sent, lap_no,"
            " te_left, te_right, ps_left, ps_right, ps_combined"
            " FROM ride_samples WHERE ride_id = ? ORDER BY t_s", (ride_id,)
        ).fetchall()
        return [Sample(*tuple(r)) for r in rows]

    def save_lap(self, ride_id: str, lap: Lap) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO laps(ride_id, lap_no, trigger, start_t_s, end_t_s,"
            " start_dist_m, end_dist_m, avg_power_w, np_w, max_power_w, avg_hr, max_hr,"
            " avg_cadence, avg_speed_mps, ascent_m, avg_balance_left)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ride_id, lap.lap_no, lap.trigger, lap.start_t_s, lap.end_t_s, lap.start_dist_m,
             lap.end_dist_m, lap.avg_power_w, lap.np_w, lap.max_power_w, lap.avg_hr,
             lap.max_hr, lap.avg_cadence, lap.avg_speed_mps, lap.ascent_m,
             lap.avg_balance_left),
        )
        if lap.pedal:
            self.conn.execute(
                "UPDATE laps SET " + ", ".join(f"avg_{k} = ?" for k in PEDAL_KEYS)
                + " WHERE ride_id = ? AND lap_no = ?",
                [lap.pedal.get(k) for k in PEDAL_KEYS] + [ride_id, lap.lap_no])
        self.conn.commit()

    def laps(self, ride_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM laps WHERE ride_id = ? ORDER BY lap_no", (ride_id,)
        ).fetchall()

    def save_climb_effort(self, climb_id: int, ride_id: str, start_t: int, end_t: int,
                          avg_power: float | None, avg_hr: float | None,
                          avg_cad: float | None, gain_m: float,
                          avg_balance: float | None = None) -> tuple[int, int, bool]:
        """Grava o esforço e devolve (posição, total, é_recorde) — req. 14."""
        elapsed = end_t - start_t
        vam = (gain_m / elapsed * 3600.0) if elapsed > 0 else 0.0
        self.conn.execute(
            "INSERT INTO climb_efforts(climb_id, ride_id, start_t_s, end_t_s, elapsed_s,"
            " avg_power_w, avg_hr, avg_cadence, vam_mh, avg_balance_left)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (climb_id, ride_id, start_t, end_t, elapsed, avg_power, avg_hr, avg_cad, vam,
             avg_balance),
        )
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT elapsed_s FROM climb_efforts WHERE climb_id = ? ORDER BY elapsed_s",
            (climb_id,),
        ).fetchall()
        times = [r["elapsed_s"] for r in rows]
        rank = times.index(elapsed) + 1
        return rank, len(times), rank == 1 and len(times) > 1

    def climb_leaderboard(self, climb_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT ce.*, r.started_at FROM climb_efforts ce JOIN rides r ON r.id = ce.ride_id"
            " WHERE ce.climb_id = ? ORDER BY ce.elapsed_s LIMIT ?", (climb_id, limit)
        ).fetchall()

    def route_leaderboard(self, route_id: str, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT re.*, r.started_at FROM route_efforts re JOIN rides r ON r.id = re.ride_id"
            " WHERE re.route_id = ? ORDER BY re.elapsed_s LIMIT ?", (route_id, limit)
        ).fetchall()

    def finish_ride(self, ride_id: str, s: RideSummary, fit_path: str | None,
                    ghosts: Sequence[str] = ()) -> None:
        r = self.conn.execute("SELECT route_id FROM rides WHERE id = ?", (ride_id,)).fetchone()
        self.conn.execute(
            "UPDATE rides SET status='completed', ended_at=?, elapsed_s=?, moving_s=?,"
            " distance_m=?, ascent_m=?, completed_route=?, avg_power_w=?, max_power_w=?, np_w=?,"
            " intensity_factor=?, tss=?, work_kj=?, avg_hr=?, max_hr=?, avg_cadence=?,"
            " avg_speed_mps=?, avg_balance_left=?, fit_path=?, route_loops=?,"
            " best_loop_s=?, paused_s=? WHERE id = ?",
            (now_iso(), s.elapsed_s, s.moving_s, s.distance_m, s.ascent_m,
             int(s.completed_route), s.avg_power_w, s.max_power_w, s.np_w, s.intensity_factor,
             s.tss, s.work_kj, s.avg_hr, s.max_hr, s.avg_cadence, s.avg_speed_mps,
             s.avg_balance_left, fit_path, s.route_loops, s.best_loop_s, s.paused_s, ride_id),
        )
        if s.pedal:
            self.conn.execute(
                "UPDATE rides SET " + ", ".join(f"avg_{k} = ?" for k in PEDAL_KEYS)
                + " WHERE id = ?", [s.pedal.get(k) for k in PEDAL_KEYS] + [ride_id])
        if s.power_curve:
            self.conn.executemany(
                "INSERT OR REPLACE INTO ride_power_curve(ride_id, duration_s, max_avg_w)"
                " VALUES (?,?,?)", [(ride_id, d, w) for d, w in s.power_curve],
            )
        # Só esforços completos entram na classificação da rota.
        if r and r["route_id"] and s.completed_route:
            # Com várias voltas, o que conta para a classificação é a volta
            # mais rápida — é isso que se compara entre sessões.
            effort_s = s.best_loop_s if s.best_loop_s else s.elapsed_s
            self.conn.execute(
                "INSERT OR REPLACE INTO route_efforts(route_id, ride_id, elapsed_s,"
                " avg_power_w, avg_hr, avg_cadence, np_w) VALUES (?,?,?,?,?,?,?)",
                (r["route_id"], ride_id, effort_s, s.avg_power_w, s.avg_hr,
                 s.avg_cadence, s.np_w),
            )
        if r and r["route_id"]:
            self.conn.execute(
                "UPDATE routes SET times_ridden = times_ridden + 1 WHERE id = ?",
                (r["route_id"],),
            )
        for g in ghosts:
            self.conn.execute(
                "INSERT OR IGNORE INTO ride_comparisons(ride_id, ghost_ride_id) VALUES (?,?)",
                (ride_id, g),
            )
        self.conn.commit()

    def set_ride_name(self, ride_id: str, name: str) -> None:
        self.conn.execute("UPDATE rides SET name = ? WHERE id = ?", (name, ride_id))
        self.conn.commit()

    def abort_ride(self, ride_id: str) -> None:
        self.conn.execute(
            "UPDATE rides SET status='aborted', ended_at=? WHERE id = ?", (now_iso(), ride_id)
        )
        self.conn.commit()

    def rides(self, route_id: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
        if route_id:
            return self.conn.execute(
                "SELECT * FROM rides WHERE route_id = ? AND status='completed'"
                " ORDER BY started_at DESC LIMIT ?", (route_id, limit)
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM rides WHERE status='completed' ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def purge_incomplete(self) -> int:
        """Fecha as sessões que ficaram em 'recording' e não se podem retomar
        (sem ponto de recuperação). As outras ficam à espera de decisão: o
        ecrã de recuperação pergunta se se retoma, guarda ou descarta."""
        keep = "SELECT session_id FROM session_checkpoints"
        cur = self.conn.execute(
            f"UPDATE rides SET status='aborted' WHERE status='recording' AND id NOT IN ({keep})")
        n = cur.rowcount
        cur = self.conn.execute(
            "UPDATE strength_sessions SET status='aborted' WHERE status='recording'"
            f" AND id NOT IN ({keep})")
        n += cur.rowcount
        rowing = ""
        for table in ("row_sessions", "endurance_sessions"):
            if self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                 (table,)).fetchone():
                cur = self.conn.execute(
                    f"UPDATE {table} SET status='aborted' WHERE status='recording'"
                    f" AND id NOT IN ({keep})")
                n += cur.rowcount
                rowing += f"  UNION SELECT id FROM {table} WHERE status='recording'"
        # pontos de recuperação de sessões que já não estão em curso
        self.conn.execute(
            "DELETE FROM session_checkpoints WHERE session_id NOT IN"
            " (SELECT id FROM rides WHERE status='recording'"
            "  UNION SELECT id FROM strength_sessions WHERE status='recording'" + rowing + ")")
        self.conn.commit()
        return n

    # ------------------------------------------------------- recuperação

    def save_checkpoint(self, session_id: str, sport: str, config: dict,
                        state: dict) -> None:
        self.conn.execute(
            "INSERT INTO session_checkpoints(session_id, sport, saved_at, config, state)"
            " VALUES (?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET"
            " saved_at=excluded.saved_at, config=excluded.config, state=excluded.state",
            (session_id, sport, now_iso(), json.dumps(config), json.dumps(state)))
        self.conn.commit()

    def checkpoint(self, session_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM session_checkpoints WHERE session_id = ?",
                              (session_id,)).fetchone()
        if r is None:
            return None
        return {"session_id": r["session_id"], "sport": r["sport"],
                "saved_at": r["saved_at"], "config": json.loads(r["config"]),
                "state": json.loads(r["state"])}

    def checkpoints(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT session_id FROM session_checkpoints ORDER BY saved_at DESC").fetchall()
        return [c for c in (self.checkpoint(r["session_id"]) for r in rows) if c]

    def delete_checkpoint(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM session_checkpoints WHERE session_id = ?",
                          (session_id,))
        self.conn.commit()

    # ------------------------------------------------------------ treinos

    def insert_workout(self, name: str, steps: Sequence[dict], source_format: str | None = None,
                       description: str | None = None, est_tss: float | None = None) -> str:
        wid = new_id()
        total = sum(int(s.get("duration_s") or 0) for s in steps)
        self.conn.execute(
            "INSERT INTO workouts(id, name, source_format, description, total_seconds, est_tss)"
            " VALUES (?,?,?,?,?,?)", (wid, name, source_format, description, total, est_tss),
        )
        self.conn.executemany(
            "INSERT INTO workout_steps(workout_id, idx, kind, duration_s, target_type,"
            " target_lo, target_hi, cadence_lo, cadence_hi, text_cue) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(wid, i, s["kind"], s.get("duration_s"), s["target_type"], s.get("target_lo"),
              s.get("target_hi"), s.get("cadence_lo"), s.get("cadence_hi"), s.get("text_cue"))
             for i, s in enumerate(steps)],
        )
        self.conn.commit()
        return wid

    def workouts(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM workouts ORDER BY imported_at DESC").fetchall()

    def workout(self, workout_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM workouts WHERE id = ?",
                                 (workout_id,)).fetchone()

    def update_workout(self, workout_id: str, name: str, steps: Sequence[dict],
                       description: str | None = None, est_tss: float | None = None) -> None:
        """Construtor de treinos: grava por cima, passos todos de novo."""
        total = sum(int(s.get("duration_s") or 0) for s in steps)
        self.conn.execute(
            "UPDATE workouts SET name=?, description=?, total_seconds=?, est_tss=?,"
            " source_format=COALESCE(source_format, 'builder') WHERE id = ?",
            (name, description, total, est_tss, workout_id))
        self.conn.execute("DELETE FROM workout_steps WHERE workout_id = ?", (workout_id,))
        self.conn.executemany(
            "INSERT INTO workout_steps(workout_id, idx, kind, duration_s, target_type,"
            " target_lo, target_hi, cadence_lo, cadence_hi, text_cue) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(workout_id, i, s["kind"], s.get("duration_s"), s["target_type"],
              s.get("target_lo"), s.get("target_hi"), s.get("cadence_lo"),
              s.get("cadence_hi"), s.get("text_cue")) for i, s in enumerate(steps)])
        self.conn.commit()

    def workout_steps(self, workout_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM workout_steps WHERE workout_id = ? ORDER BY idx", (workout_id,)
        ).fetchall()

    def delete_workout(self, workout_id: str) -> None:
        self.conn.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
        self.conn.commit()

    def save_step_results(self, ride_id: str, results: Sequence[dict]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO workout_step_results(ride_id, step_idx, avg_power_w,"
            " target_avg_w, pct_in_target, avg_hr, avg_cadence) VALUES (?,?,?,?,?,?,?)",
            [(ride_id, r["step_idx"], r.get("avg_power_w"), r.get("target_avg_w"),
              r.get("pct_in_target"), r.get("avg_hr"), r.get("avg_cadence")) for r in results],
        )
        self.conn.commit()

    # -------------------------------------------------------------- FTP

    def save_ftp_test(self, protocol: str, raw_w: float, ftp_w: int,
                      ride_id: str | None, accepted: bool) -> None:
        self.conn.execute(
            "INSERT INTO ftp_tests(ride_id, protocol, tested_at, raw_value_w, ftp_w, accepted)"
            " VALUES (?,?,?,?,?,?)",
            (ride_id, protocol, now_iso(), raw_w, ftp_w, int(accepted)),
        )
        if accepted:
            self.conn.execute("UPDATE athlete SET ftp_w = ? WHERE id = 1", (ftp_w,))
        self.conn.commit()

    def ftp_history(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM ftp_tests WHERE accepted = 1 ORDER BY tested_at"
        ).fetchall()

    # ---------------------------------------------------------- desafios

    def challenges(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM challenges ORDER BY is_default DESC, created_at"
        ).fetchall()

    def create_challenge(self, name: str, metric: str, target: float,
                         display_unit: str | None = None) -> int:
        if target <= 0:
            raise ValueError("o objetivo tem de ser maior que zero")
        cur = self.conn.execute(
            "INSERT INTO challenges(name, metric, target, display_unit) VALUES (?,?,?,?)",
            (name, metric, target, display_unit)
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def delete_challenge(self, challenge_id: int) -> None:
        self.conn.execute(
            "DELETE FROM challenges WHERE id = ? AND is_default = 0", (challenge_id,)
        )
        self.conn.commit()

    def active_attempt(self, challenge_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM challenge_attempts WHERE challenge_id = ? AND completed_at IS NULL"
            " ORDER BY started_at DESC LIMIT 1", (challenge_id,)
        ).fetchone()

    def start_attempt(self, challenge_id: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO challenge_attempts(challenge_id, started_at) VALUES (?,?)",
            (challenge_id, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def ensure_attempt(self, challenge_id: int) -> sqlite3.Row:
        row = self.active_attempt(challenge_id)
        if row is None:
            self.start_attempt(challenge_id)
            row = self.active_attempt(challenge_id)
        assert row is not None
        return row

    def reset_attempt(self, challenge_id: int) -> int:
        """Fecha a tentativa em curso sem a concluir e abre outra (req. 20)."""
        row = self.active_attempt(challenge_id)
        if row is not None:
            self.conn.execute(
                "UPDATE challenge_attempts SET completed_at = ?, elapsed_s = NULL WHERE id = ?",
                (now_iso(), row["id"]),
            )
        return self.start_attempt(challenge_id)

    def bump_attempt(self, attempt_id: int, add: float, target: float,
                     ride_id: str | None) -> bool:
        """Soma progresso; devolve True se concluiu agora."""
        row = self.conn.execute(
            "SELECT progress, started_at FROM challenge_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        if row is None:
            return False
        progress = row["progress"] + add
        done = progress >= target
        if done:
            started = datetime.strptime(row["started_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=timezone.utc
            )
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            self.conn.execute(
                "UPDATE challenge_attempts SET progress=?, completed_at=?, elapsed_s=?,"
                " completing_ride_id=? WHERE id = ?",
                (progress, now_iso(), elapsed, ride_id, attempt_id),
            )
        else:
            self.conn.execute(
                "UPDATE challenge_attempts SET progress = ? WHERE id = ?", (progress, attempt_id)
            )
        self.conn.commit()
        return done

    def challenge_leaderboard(self, challenge_id: int, limit: int = 10) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM challenge_attempts WHERE challenge_id = ? AND elapsed_s IS NOT NULL"
            " ORDER BY elapsed_s LIMIT ?", (challenge_id, limit)
        ).fetchall()

    # ------------------------------------------------------------ fuga

    def save_chase_effort(self, ride_id: str, route_id: str | None, level: str,
                          survived_s: float, distance_m: float,
                          avg_power_w: float | None, final_chaser_w: int,
                          caught: bool, clean: bool) -> tuple[int, int, bool]:
        """Grava uma fuga e devolve (posição, total, é_recorde) no nível."""
        self.conn.execute(
            "INSERT INTO chase_efforts(ride_id, route_id, level, survived_s, distance_m,"
            " avg_power_w, final_chaser_w, caught, clean, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ride_id, route_id or None, level, survived_s, distance_m, avg_power_w,
             final_chaser_w, int(caught), int(clean), now_iso()))
        self.conn.commit()
        if not clean:
            return 0, 0, False
        route_id = route_id or None
        better = self.conn.execute(
            "SELECT COUNT(*) AS n FROM chase_efforts WHERE level = ? AND clean = 1"
            " AND route_id IS ? AND survived_s > ?",
            (level, route_id, survived_s)).fetchone()["n"]
        total = self.conn.execute(
            "SELECT COUNT(*) AS n FROM chase_efforts WHERE level = ? AND clean = 1"
            " AND route_id IS ?", (level, route_id)).fetchone()["n"]
        rank = better + 1
        return rank, total, rank == 1 and total > 1

    def chase_leaderboard(self, level: str, route_id: str | None = None,
                          limit: int = 20) -> list[sqlite3.Row]:
        """Fugas sem pausas, da mais longa para a mais curta.

        Uma por nível e por rota (sem rota = plano): nas subidas a vantagem
        fecha mais devagar, por isso tempos de estradas diferentes não se
        comparam.
        """
        return self.conn.execute(
            "SELECT ce.*, r.started_at, ro.name AS route_name FROM chase_efforts ce"
            " JOIN rides r ON r.id = ce.ride_id"
            " LEFT JOIN routes ro ON ro.id = ce.route_id"
            " WHERE ce.level = ? AND ce.clean = 1 AND ce.route_id IS ?"
            " ORDER BY ce.survived_s DESC LIMIT ?",
            (level, route_id or None, limit)).fetchall()

    # ------------------------------------------------------- outras tabelas

    def workout_leaderboard(self, workout_id: str, limit: int = 20) -> list[sqlite3.Row]:
        """Execuções completas de um treino, pela potência média."""
        return self.conn.execute(
            "SELECT r.id, r.started_at, r.elapsed_s, r.avg_power_w, r.np_w, r.tss,"
            " (SELECT AVG(pct_in_target) FROM workout_step_results w"
            "   WHERE w.ride_id = r.id) AS compliance"
            " FROM rides r WHERE r.workout_id = ? AND r.status = 'completed'"
            " AND r.avg_power_w IS NOT NULL"
            " ORDER BY r.avg_power_w DESC LIMIT ?", (workout_id, limit)).fetchall()

    def ftp_leaderboard(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM ftp_tests WHERE accepted = 1 ORDER BY ftp_w DESC LIMIT ?",
            (limit,)).fetchall()

    # ------------------------------------------------------- dispositivos

    def remember_device(self, dev_id: str, transport: str, name: str, profiles: list[str],
                        capabilities: int, role: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO devices(id, transport, name, profiles, capabilities, last_seen_at,"
            " role) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " profiles=excluded.profiles, capabilities=excluded.capabilities,"
            " last_seen_at=excluded.last_seen_at, role=COALESCE(excluded.role, role)",
            (dev_id, transport, name, json.dumps(profiles), capabilities, now_iso(), role),
        )
        self.conn.commit()

    def known_devices(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM devices ORDER BY last_seen_at DESC"
        ).fetchall()

    def forget_device(self, dev_id: str) -> None:
        self.conn.execute("DELETE FROM devices WHERE id = ?", (dev_id,))
        self.conn.commit()

    def save_calibration(self, device_id: str, method: str, success: bool,
                         detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO trainer_calibrations(device_id, performed_at, method, detail, success)"
            " VALUES (?,?,?,?,?)", (device_id, now_iso(), method, detail, int(success)),
        )
        self.conn.commit()

    def last_calibration(self, device_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM trainer_calibrations WHERE device_id = ?"
            " ORDER BY performed_at DESC LIMIT 1", (device_id,)
        ).fetchone()
