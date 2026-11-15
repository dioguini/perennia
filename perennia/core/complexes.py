"""Complexos (kettlebell e afins): um exercício que **junta outros exercícios**, em sequência.

Um complexo é um exercício como os outros (entra nos treinos, tem séries, repetições e carga),
mas é definido por uma lista de exercícios com as repetições de cada um por ronda — por exemplo
«Clean → Press → Front squat», 5 + 5 + 5. Numa sessão:

* acrescentas o complexo ao treino como um só exercício (as «repetições» são as **rondas**);
* durante a sessão vês os exercícios que o compõem e as repetições de cada um por ronda;
* cada série registada guarda também as repetições **por exercício** (rondas × repetições da
  ronda), em `strength_set_parts` — por isso a evolução de, por exemplo, o Press conta o que
  fizeste dentro dos complexos além do que fizeste à parte.

Tudo guardado na base de dados local; nada aqui fala com o ecrã.
"""
from __future__ import annotations

from typing import Sequence

from . import gym
from . import strength as st
from .db import Database
from .i18n import tr

PART_REPS = 5            # repetições de cada exercício por ronda, se não se disser outra coisa


def ensure(db: Database) -> None:
    if getattr(db, "_complexes_ready", False):
        return
    try:
        db._complexes_busy = True
    except Exception:
        pass
    gym.ensure(db)
    db.conn.executescript("""
CREATE TABLE IF NOT EXISTS exercise_complex_parts (
  complex_id  INTEGER NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
  idx         INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  reps        INTEGER NOT NULL DEFAULT 5,
  PRIMARY KEY (complex_id, idx)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS strength_set_parts (
  set_id      INTEGER NOT NULL REFERENCES strength_sets(id) ON DELETE CASCADE,
  idx         INTEGER NOT NULL,
  exercise_id INTEGER NOT NULL REFERENCES exercises(id),
  reps        INTEGER NOT NULL,
  PRIMARY KEY (set_id, idx)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_set_parts_ex ON strength_set_parts(exercise_id);
""")
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(exercises)")}
    if "complex" not in cols:
        db.conn.execute("ALTER TABLE exercises ADD COLUMN complex INTEGER NOT NULL DEFAULT 0")
    db.conn.commit()
    try:
        db._complexes_ready = True
        db._complexes_busy = False
    except Exception:
        pass
    seed(db)


# --------------------------------------------------------------- consulta


def is_complex(db: Database, exercise_id: int) -> bool:
    ensure(db)
    r = db.conn.execute("SELECT complex FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    return bool(r and r["complex"])


def complexes(db: Database) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM exercises WHERE complex = 1 AND COALESCE(archived, 0) = 0 ORDER BY name")]


def parts(db: Database, complex_id: int) -> list[dict]:
    """Os exercícios do complexo, por ordem: `{idx, exercise_id, name, reps, measure}`."""
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT p.idx, p.exercise_id, p.reps, e.name, e.measure FROM exercise_complex_parts p"
        " JOIN exercises e ON e.id = p.exercise_id WHERE p.complex_id = ? ORDER BY p.idx",
        (complex_id,))]


def components_text(db: Database, complex_id: int, rounds: int | None = None) -> str:
    """«Clean 5 → Press 5 → Front squat 5» (com `rounds`, diz também as rondas)."""
    ps = parts(db, complex_id)
    if not ps:
        return ""
    unit = lambda p: "s" if p["measure"] == "time" else ""          # noqa: E731
    text = " → ".join(f"{p['name']} {p['reps']}{unit(p)}" for p in ps)
    if rounds:
        text += " · " + tr("{n} rondas", "{n} rounds", n=rounds)
    return text


def components_map(db: Database, exercise_ids: Sequence[int]) -> dict[int, str]:
    """Só dos que são complexos (para mostrar na sessão)."""
    ensure(db)
    out = {}
    for eid in dict.fromkeys(exercise_ids):
        if is_complex(db, eid):
            out[eid] = components_text(db, eid)
    return out


def expand(db: Database, complex_id: int, rounds: int) -> list[dict]:
    """O que fazer em `rounds` rondas, exercício a exercício: `{exercise_id, name, reps}`."""
    return [{"exercise_id": p["exercise_id"], "name": p["name"], "reps": p["reps"] * max(0, rounds)}
            for p in parts(db, complex_id)]


# --------------------------------------------------------------- escrita


def save_complex(db: Database, complex_id: int | None, name: str,
                 members: Sequence[tuple[int, int]], *, group: str = "full",
                 mods: Sequence[str] = ("kettlebell",),
                 equipment: Sequence[str] = ("kettlebell",), description: str | None = None) -> int:
    """Cria ou atualiza um complexo. `members`: (exercício, repetições por ronda), por ordem.
    Um complexo não pode conter-se a si próprio nem outro complexo (fica só uma camada)."""
    ensure(db)
    name = (name or "").strip()
    if not name:
        raise ValueError(tr("Falta o nome do complexo.", "The complex needs a name."))
    clean: list[tuple[int, int]] = []
    for eid, reps in members:
        if complex_id is not None and int(eid) == complex_id:
            continue
        if is_complex(db, int(eid)):
            raise ValueError(tr("Um complexo não pode conter outro complexo.",
                                "A complex cannot contain another complex."))
        if st.exercise(db, int(eid)) is None:
            continue
        clean.append((int(eid), max(1, int(reps or PART_REPS))))
    if not clean:
        raise ValueError(tr("Escolhe pelo menos um exercício.", "Choose at least one exercise."))
    cid = gym.save_exercise(db, complex_id, name=name, mods=list(mods), group=group,
                            measure="reps", bodyweight=0.0, equipment=list(equipment),
                            description=description)
    db.conn.execute("UPDATE exercises SET complex = 1 WHERE id = ?", (cid,))
    db.conn.execute("DELETE FROM exercise_complex_parts WHERE complex_id = ?", (cid,))
    db.conn.executemany("INSERT INTO exercise_complex_parts(complex_id, idx, exercise_id, reps)"
                        " VALUES (?,?,?,?)", [(cid, i, e, r) for i, (e, r) in enumerate(clean)])
    db.conn.commit()
    return cid


def delete_complex(db: Database, complex_id: int) -> None:
    """Esconde o complexo (o histórico continua a usá-lo, como nos outros exercícios)."""
    ensure(db)
    gym.archive_exercise(db, complex_id, True)


# ------------------------------------------------------ registo e evolução


def log_parts(db: Database, set_id: int) -> None:
    """Grava, para uma série de um complexo, as repetições de cada exercício (rondas × as da
    ronda). Chamar depois de gravar ou de corrigir a série."""
    ensure(db)
    r = db.conn.execute("SELECT exercise_id, reps FROM strength_sets WHERE id = ?",
                        (set_id,)).fetchone()
    db.conn.execute("DELETE FROM strength_set_parts WHERE set_id = ?", (set_id,))
    if r is not None and is_complex(db, r["exercise_id"]):
        db.conn.executemany(
            "INSERT INTO strength_set_parts(set_id, idx, exercise_id, reps) VALUES (?,?,?,?)",
            [(set_id, i, p["exercise_id"], p["reps"]) for i, p in
             enumerate(expand(db, r["exercise_id"], int(r["reps"] or 0)))])
    db.conn.commit()


def set_parts(db: Database, set_id: int) -> list[dict]:
    """O que se fez em cada exercício do complexo numa série."""
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT p.idx, p.exercise_id, p.reps, e.name FROM strength_set_parts p JOIN exercises e"
        " ON e.id = p.exercise_id WHERE p.set_id = ? ORDER BY p.idx", (set_id,))]


def session_parts(db: Database, session_id: str) -> list[dict]:
    """Por complexo da sessão: o complexo, as séries (rondas, carga) e os exercícios com as
    repetições feitas."""
    ensure(db)
    out = []
    for s in db.conn.execute(
            "SELECT s.id, s.set_no, s.reps, s.load_kg, s.exercise_id, e.name FROM strength_sets s"
            " JOIN exercises e ON e.id = s.exercise_id WHERE s.session_id = ? AND e.complex = 1"
            " ORDER BY s.id", (session_id,)):
        out.append({"set_id": s["id"], "complex": s["name"], "complex_id": s["exercise_id"],
                    "set_no": s["set_no"], "rounds": s["reps"], "load_kg": s["load_kg"],
                    "parts": set_parts(db, s["id"])})
    return out


def component_progress(db: Database, exercise_id: int) -> list[dict]:
    """A evolução de um exercício **incluindo o que fez dentro de complexos**: por sessão, as
    repetições feitas à parte, as feitas em complexos e a carga máxima (dos complexos). Do mais
    antigo para o mais recente."""
    ensure(db)
    rows = db.conn.execute(
        "SELECT ss.id AS sid, ss.started_at AS day, SUM(p.reps) AS reps, MAX(s.load_kg) AS load"
        " FROM strength_set_parts p JOIN strength_sets s ON s.id = p.set_id"
        " JOIN strength_sessions ss ON ss.id = s.session_id WHERE p.exercise_id = ?"
        " GROUP BY ss.id ORDER BY ss.started_at", (exercise_id,)).fetchall()
    inside = {r["sid"]: (r["day"], r["reps"], r["load"]) for r in rows}
    alone = {r["sid"]: (r["day"], r["reps"], r["load"]) for r in db.conn.execute(
        "SELECT ss.id AS sid, ss.started_at AS day, SUM(s.reps) AS reps, MAX(s.load_kg) AS load"
        " FROM strength_sets s JOIN strength_sessions ss ON ss.id = s.session_id"
        " WHERE s.exercise_id = ? GROUP BY ss.id", (exercise_id,))}
    out = []
    for sid in sorted(set(inside) | set(alone), key=lambda k: (inside.get(k) or alone.get(k))[0]):
        a, i = alone.get(sid), inside.get(sid)
        out.append({"session_id": sid, "day": (i or a)[0],
                    "reps_alone": int(a[1] or 0) if a else 0,
                    "reps_in_complexes": int(i[1] or 0) if i else 0,
                    "reps_total": int((a[1] if a else 0) or 0) + int((i[1] if i else 0) or 0),
                    "max_load_kg": max((x for x in ((a[2] if a else None),
                                                    (i[2] if i else None)) if x), default=None)})
    return out


def complex_progress(db: Database, complex_id: int) -> list[dict]:
    """A evolução do próprio complexo: por sessão, rondas, séries, melhor carga e volume
    (rondas × carga)."""
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT ss.id AS session_id, ss.started_at AS day, COUNT(*) AS sets, SUM(s.reps) AS rounds,"
        " MAX(s.load_kg) AS max_load_kg, SUM(s.reps * COALESCE(s.load_kg, 0)) AS volume"
        " FROM strength_sets s JOIN strength_sessions ss ON ss.id = s.session_id"
        " WHERE s.exercise_id = ? GROUP BY ss.id ORDER BY ss.started_at", (complex_id,))]


# ------------------------------------------------------------- de origem

# (nome pt, [(exercício, repetições por ronda)]) — complexos clássicos de kettlebell, com os
# exercícios que já existem no catálogo.
BUILTIN: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = (
    ("Complexo KB · Clean + Press + Front squat",
     (("Clean com kettlebell", 5), ("Press com kettlebell", 5), ("Agachamento goblet", 5))),
    ("Complexo KB · Swing + Clean + Press",
     (("Kettlebell swing", 10), ("Clean com kettlebell", 5), ("Press com kettlebell", 5))),
    ("Complexo KB · Clean + Press + Remada",
     (("Clean com kettlebell", 5), ("Press com kettlebell", 5), ("Remada com kettlebell", 5))),
    ("Complexo KB · Snatch + Goblet squat",
     (("Snatch com kettlebell", 5), ("Agachamento goblet", 5))),
    ("Complexo KB · Swing + Goblet squat + Halo",
     (("Kettlebell swing", 10), ("Agachamento goblet", 8), ("Halo", 5))),
    ("Complexo KB · Clean and press + Windmill",
     (("Clean and press", 5), ("Windmill", 3))),
)


def seed(db: Database) -> None:
    """Os complexos de origem, uma vez por versão; os teus ficam como estão. Os que apagares
    (arquivares) não voltam."""
    version = len(BUILTIN)
    if db.get("complex_seed_version") == version:
        return
    by_name = {r["name"]: r["id"] for r in db.conn.execute("SELECT id, name FROM exercises")}
    for name, members in BUILTIN:
        if name in by_name:
            continue
        ids = [(by_name[n], r) for n, r in members if n in by_name]
        if len(ids) < 2:
            continue
        try:
            save_complex(db, None, name, ids)
        except ValueError:
            continue
        by_name[name] = int(db.conn.execute("SELECT id FROM exercises WHERE name = ?",
                                            (name,)).fetchone()["id"])
    db.set("complex_seed_version", version)
    from . import gym_catalog
    gym_catalog.seed_workouts(db, with_complexes=True)
