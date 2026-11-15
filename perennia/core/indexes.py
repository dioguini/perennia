"""Índices que aceleram as consultas «as voltas desta sessão», «os esforços desta subida»…

Quase todas as tabelas de detalhe (voltas, amostras, esforços) são lidas pela sessão a que
pertencem. Sem índice, cada leitura percorre a tabela toda, o que se nota quando o histórico
cresce (anos de sessões). Aqui criam-se, sem apagar nem mudar dados, os que faltavam. Só se criam
nas tabelas que já existem (as que nascem a pedir criam-nas no arranque seguinte) e é seguro
repetir."""
from __future__ import annotations

from .db import Database

# (tabela, colunas)
INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("endurance_laps", ("session_id",)),
    ("row_laps", ("session_id",)),
    ("strength_laps", ("session_id",)),
    ("strength_laps", ("set_id",)),
    ("climb_efforts", ("ride_id",)),
    ("chase_efforts", ("ride_id",)),
    ("game_results", ("ride_id",)),
    ("ftp_tests", ("ride_id",)),
    ("test_results", ("ride_id",)),
    ("strava_efforts", ("ride_id",)),
    ("strava_efforts", ("segment_id",)),
    ("segment_efforts", ("session_id",)),
    ("segment_efforts", ("segment_id",)),
    ("perennia_segments", ("route_id",)),
    ("lab_results", ("report_id",)),
    ("lab_results", ("parameter_id",)),
    ("exercise_complex_parts", ("exercise_id",)),
    ("strength_workout_items", ("exercise_id",)),
    ("exercises", ("subgroup_id",)),
    ("session_workouts", ("copy_id",)),
    ("program_days", ("plan_id",)),
    ("synced_activities", ("started_at",)),
)


def ensure(db: Database) -> int:
    """Cria os índices que faltam; devolve quantos criou."""
    made = 0
    have = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, cols in INDEXES:
        if table not in have:
            continue
        existing = {r[1] for r in db.conn.execute(f'PRAGMA table_info("{table}")')}
        if not set(cols) <= existing:
            continue
        name = f"ix_perf_{table}_{'_'.join(cols)}"
        before = db.conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name = ?",
                                 (name,)).fetchone()
        if before:
            continue
        db.conn.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}"('
                        + ", ".join(f'"{c}"' for c in cols) + ")")
        made += 1
    if made:
        db.conn.commit()
    return made
