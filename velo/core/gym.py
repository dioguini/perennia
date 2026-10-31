"""Ginásio: modalidades, inventário de exercícios e treinos por modalidade.

Uma modalidade é uma entrada no registo `MODALITIES`. Para juntar uma nova
(ex.: «Yoga»), basta:

    register(Modality("yoga", "Yoga", "Yoga", icon="pulse",
                      description=("…", "…"),
                      surprise=Scheme(n=6, sets=1, reps=60, measure="time", rest_s=15)),
             exercises=[("Saudação ao sol", "mobility", "warm_up", 0.0, "time", ())])

e tudo o resto — menu, treinos, treino livre, treino surpresa, exercícios,
histórico e estatísticas — aparece sozinho.

Os exercícios vivem numa só tabela (`exercises`) e cada um pertence a uma ou
mais modalidades (`exercise_modalities`) e pode pedir material
(`exercise_equipment`, com os tipos do inventário de artigos). Só a
modalidade Longevidade junta exercícios de todas as outras — incluindo
blocos de outros desportos (remo, bicicleta, corrida).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

from . import inventory
from . import strength as st
from .db import Database, new_id, now_iso
from .i18n import tr


@dataclass(frozen=True)
class Scheme:
    """Como o treino surpresa é montado: n exercícios, séries × reps (ou s)."""
    n: int = 5
    sets: int = 3
    reps: int = 10
    measure: str = "reps"          # se o exercício for por tempo usa `time_s`
    time_s: int = 40
    rest_s: int = 90
    rpe: float | None = 7.0


@dataclass(frozen=True)
class Modality:
    key: str
    pt: str
    en: str
    icon: str = "dumbbell"
    description: tuple[str, str] = ("", "")
    surprise: Scheme = Scheme()
    multi: bool = False            # junta exercícios de todas as modalidades (e desportos)
    laps: bool = False             # sessão por voltas (Conditioning)

    @property
    def name(self) -> str:
        return tr(self.pt, self.en)

    @property
    def desc(self) -> str:
        return tr(*self.description)


MODALITIES: dict[str, Modality] = {}
SEED_EXERCISES: list[tuple] = []     # (nome, modalidade, grupo, cat FIT, peso do corpo, medida, material)


def register(m: Modality, exercises: Sequence[tuple] = ()) -> Modality:
    MODALITIES[m.key] = m
    for ex in exercises:
        SEED_EXERCISES.append((ex[0], m.key) + tuple(ex[1:]))
    return m


def modalities() -> list[Modality]:
    return list(MODALITIES.values())


def modality(key: str | None) -> Modality:
    return MODALITIES.get(key or "strength") or MODALITIES["strength"]


# ------------------------------------------------------------ o registo

# Os exercícios de força que já existiam (strength.EXERCISES) passam para a
# modalidade Força; aqui só se diz que material pedem.
STRENGTH_EQUIPMENT = {
    "Agachamento com barra": ("barbell", "plates", "rack"),
    "Agachamento frontal": ("barbell", "plates", "rack"),
    "Agachamento goblet": ("kettlebell",), "Agachamento búlgaro": ("dumbbell", "bench"),
    "Prensa de pernas": ("cable",), "Afundos": ("dumbbell",), "Step-up": ("box",),
    "Extensão de pernas": ("cable",), "Curl femoral": ("cable",),
    "Elevação de gémeos": ("dumbbell",), "Peso morto": ("barbell", "plates"),
    "Peso morto romeno": ("barbell", "plates"), "Hip thrust": ("barbell", "plates", "bench"),
    "Kettlebell swing": ("kettlebell",), "Abdução de anca (banda)": ("bands",),
    "Supino com barra": ("barbell", "plates", "bench", "rack"),
    "Supino inclinado com halteres": ("dumbbell", "bench"),
    "Aberturas com halteres": ("dumbbell", "bench"), "Elevações (pull-ups)": ("pullup_bar",),
    "Puxada ao peito": ("cable",), "Remada com barra": ("barbell", "plates"),
    "Remada com halter": ("dumbbell", "bench"), "Remada sentada (cabo)": ("cable",),
    "Remada invertida": ("rings",), "Encolhimentos": ("dumbbell",),
    "Press militar": ("barbell", "plates"), "Press de ombros com halteres": ("dumbbell",),
    "Elevações laterais": ("dumbbell",), "Face pull": ("cable",),
    "Curl de bíceps": ("dumbbell",), "Extensão de tríceps": ("dumbbell",),
    "Pallof press": ("bands",), "Farmer's carry": ("kettlebell",),
    "Turkish get-up": ("kettlebell",), "Saltos para caixa": ("box",),
}

register(Modality("strength", "Força", "Strength", "dumbbell",
                  ("Cargas, séries e repetições: agachar, dobrar a anca, empurrar, puxar.",
                   "Loads, sets and reps: squat, hinge, push, pull."),
                  Scheme(n=5, sets=4, reps=8, rest_s=120, rpe=7.5)))

register(Modality("plyometrics", "Pliométricos", "Plyometrics", "flame",
                  ("Saltos e lançamentos: potência e reatividade.",
                   "Jumps and throws: power and reactivity."),
                  Scheme(n=5, sets=4, reps=6, rest_s=90, rpe=7.0)), [
    ("Saltos para caixa", "legs", "plyo", 0.0, "reps", ("box",)),
    ("Agachamento com salto", "legs", "plyo", 0.0, "reps", ()),
    ("Afundos com salto", "legs", "plyo", 0.0, "reps", ()),
    ("Salto em comprimento", "legs", "plyo", 0.0, "reps", ()),
    ("Saltos laterais (skater)", "legs", "plyo", 0.0, "reps", ()),
    ("Tuck jumps", "legs", "plyo", 0.0, "reps", ()),
    ("Saltos em profundidade", "legs", "plyo", 0.0, "reps", ("box",)),
    ("Flexões pliométricas", "chest", "push_up", 0.65, "reps", ()),
    ("Lançamento de bola medicinal", "full", "plyo", 0.0, "reps", ("medball",)),
    ("Saltos à corda", "full", "cardio", 0.0, "time", ("jump_rope",)),
    ("Burpees", "full", "total_body", 0.0, "reps", ()),
])

register(Modality("animal_flow", "Animal Flow", "Animal Flow", "wave",
                  ("Movimento no chão: força, mobilidade e coordenação.",
                   "Ground-based movement: strength, mobility, coordination."),
                  Scheme(n=6, sets=3, reps=40, measure="time", time_s=40, rest_s=30,
                         rpe=6.5)), [
    ("Beast hold", "core", "core", 0.0, "time", ("mat",)),
    ("Crab reach", "full", "total_body", 0.0, "time", ("mat",)),
    ("Ape traveling", "full", "total_body", 0.0, "time", ()),
    ("Side kickthrough", "full", "total_body", 0.0, "time", ()),
    ("Underswitch", "full", "total_body", 0.0, "time", ()),
    ("Scorpion reach", "mobility", "warm_up", 0.0, "time", ("mat",)),
    ("Loaded beast", "full", "total_body", 0.0, "time", ()),
    ("Beast crawl", "full", "total_body", 0.0, "time", ()),
    ("Crab walk", "full", "total_body", 0.0, "time", ()),
    ("Flow livre (sequência)", "full", "total_body", 0.0, "time", ("mat",)),
])

register(Modality("cardio", "Cardio", "Cardio", "pulse",
                  ("Máquinas e cardio contínuo ou por intervalos.",
                   "Machines and steady or interval cardio."),
                  Scheme(n=3, sets=1, reps=600, measure="time", time_s=600, rest_s=60,
                         rpe=6.0)), [
    ("Remo (máquina)", "full", "cardio", 0.0, "time", ("rower",)),
    ("Bicicleta (rolo)", "legs", "cardio", 0.0, "time", ("trainer",)),
    ("Passadeira", "legs", "cardio", 0.0, "time", ("treadmill",)),
    ("Bicicleta de ar", "full", "cardio", 0.0, "time", ("air_bike",)),
    ("SkiErg", "full", "cardio", 0.0, "time", ("ski_erg",)),
    ("Corda de saltar", "full", "cardio", 0.0, "time", ("jump_rope",)),
    ("Jumping jacks", "full", "cardio", 0.0, "time", ()),
    ("Shadow boxing", "full", "cardio", 0.0, "time", ()),
    ("Caminhada rápida", "legs", "cardio", 0.0, "time", ()),
])

register(Modality("hiit", "HIIT", "HIIT", "flame",
                  ("Intervalos curtos e intensos com pouco descanso.",
                   "Short, intense intervals with little rest."),
                  Scheme(n=6, sets=4, reps=30, measure="time", time_s=30, rest_s=15,
                         rpe=8.5)), [
    ("Burpees", "full", "total_body", 0.0, "time", ()),
    ("Mountain climbers", "core", "core", 0.0, "time", ()),
    ("Jumping jacks", "full", "cardio", 0.0, "time", ()),
    ("Agachamento com salto", "legs", "plyo", 0.0, "time", ()),
    ("Sprint no lugar (high knees)", "legs", "cardio", 0.0, "time", ()),
    ("Kettlebell swing", "hips", "hip_swing", 0.0, "time", ("kettlebell",)),
    ("Thrusters com halteres", "full", "total_body", 0.0, "time", ("dumbbell",)),
    ("Flexões", "chest", "push_up", 0.65, "time", ()),
    ("Saltos à corda", "full", "cardio", 0.0, "time", ("jump_rope",)),
])

register(Modality("calisthenics", "Calisténicos", "Calisthenics", "runner",
                  ("Peso do corpo: empurrar, puxar, pernas e core.",
                   "Bodyweight: push, pull, legs and core."),
                  Scheme(n=5, sets=4, reps=8, rest_s=90, rpe=7.5)), [
    ("Flexões", "chest", "push_up", 0.65, "reps", ()),
    ("Elevações (pull-ups)", "back", "pull_up", 1.0, "reps", ("pullup_bar",)),
    ("Fundos (dips)", "arms", "triceps_extension", 1.0, "reps", ("parallettes",)),
    ("Pistol squat", "legs", "squat", 0.0, "reps", ()),
    ("Muscle-up", "full", "pull_up", 1.0, "reps", ("pullup_bar",)),
    ("L-sit", "core", "core", 0.0, "time", ("parallettes",)),
    ("Pino (handstand)", "shoulders", "shoulder_stability", 0.0, "time", ()),
    ("Flexões em pino (pike)", "shoulders", "shoulder_press", 0.0, "reps", ()),
    ("Elevação de pernas suspenso", "core", "leg_raise", 0.0, "reps", ("pullup_bar",)),
    ("Dragon flag", "core", "core", 0.0, "reps", ("bench",)),
    ("Prancha", "core", "plank", 0.0, "time", ()),
])

register(Modality("rings", "Argolas de ginástica", "Gymnastic rings", "loops",
                  ("Instabilidade e força relativa nas argolas.",
                   "Instability and relative strength on the rings."),
                  Scheme(n=5, sets=4, reps=8, rest_s=90, rpe=7.5)), [
    ("Remada nas argolas", "back", "row", 0.6, "reps", ("rings",)),
    ("Flexões nas argolas", "chest", "push_up", 0.65, "reps", ("rings",)),
    ("Fundos nas argolas", "arms", "triceps_extension", 1.0, "reps", ("rings",)),
    ("Suporte nas argolas", "arms", "core", 0.0, "time", ("rings",)),
    ("Elevações nas argolas", "back", "pull_up", 1.0, "reps", ("rings",)),
    ("Skin the cat", "full", "total_body", 0.0, "reps", ("rings",)),
    ("Muscle-up nas argolas", "full", "pull_up", 1.0, "reps", ("rings",)),
    ("Aberturas nas argolas", "chest", "flye", 0.5, "reps", ("rings",)),
    ("L-sit nas argolas", "core", "core", 0.0, "time", ("rings",)),
])

register(Modality("bands", "Elásticos", "Bands", "wave",
                  ("Resistência elástica: força, ativação e reabilitação.",
                   "Elastic resistance: strength, activation and rehab."),
                  Scheme(n=6, sets=3, reps=15, rest_s=45, rpe=6.5)), [
    ("Pull-apart", "shoulders", "shoulder_stability", 0.0, "reps", ("bands",)),
    ("Remada com elástico", "back", "row", 0.0, "reps", ("bands",)),
    ("Press de peito com elástico", "chest", "bench_press", 0.0, "reps", ("bands",)),
    ("Agachamento com elástico", "legs", "squat", 0.0, "reps", ("bands",)),
    ("Monster walk", "hips", "hip_stability", 0.0, "reps", ("bands",)),
    ("Face pull com elástico", "shoulders", "shoulder_stability", 0.0, "reps", ("bands",)),
    ("Curl com elástico", "arms", "curl", 0.0, "reps", ("bands",)),
    ("Extensão de tríceps com elástico", "arms", "triceps_extension", 0.0, "reps",
     ("bands",)),
    ("Good morning com elástico", "hips", "deadlift", 0.0, "reps", ("bands",)),
    ("Pallof press", "core", "chop", 0.0, "reps", ("bands",)),
])

register(Modality("kettlebell", "Kettlebell", "Kettlebell", "kettlebell",
                  ("Balanços, levantamentos e transportes com kettlebell.",
                   "Swings, lifts and carries with a kettlebell."),
                  Scheme(n=5, sets=4, reps=10, rest_s=75, rpe=7.5)), [
    ("Kettlebell swing", "hips", "hip_swing", 0.0, "reps", ("kettlebell",)),
    ("Agachamento goblet", "legs", "squat", 0.0, "reps", ("kettlebell",)),
    ("Turkish get-up", "full", "total_body", 0.0, "reps", ("kettlebell",)),
    ("Clean com kettlebell", "full", "olympic_lift", 0.0, "reps", ("kettlebell",)),
    ("Snatch com kettlebell", "full", "olympic_lift", 0.0, "reps", ("kettlebell",)),
    ("Press com kettlebell", "shoulders", "shoulder_press", 0.0, "reps", ("kettlebell",)),
    ("Remada com kettlebell", "back", "row", 0.0, "reps", ("kettlebell",)),
    ("Windmill", "core", "core", 0.0, "reps", ("kettlebell",)),
    ("Farmer's carry", "full", "carry", 0.0, "time", ("kettlebell",)),
    ("Halo", "shoulders", "shoulder_stability", 0.0, "reps", ("kettlebell",)),
    ("Clean and press", "full", "olympic_lift", 0.0, "reps", ("kettlebell",)),
])

register(Modality("sandbag", "Sandbag", "Sandbag", "box",
                  ("Carga instável: levantar, carregar e arrastar.",
                   "Unstable load: lift, carry and drag."),
                  Scheme(n=5, sets=4, reps=8, rest_s=90, rpe=7.5)), [
    ("Clean com sandbag", "full", "olympic_lift", 0.0, "reps", ("sandbag",)),
    ("Bear hug squat", "legs", "squat", 0.0, "reps", ("sandbag",)),
    ("Sandbag ao ombro", "full", "total_body", 0.0, "reps", ("sandbag",)),
    ("Transporte de sandbag", "full", "carry", 0.0, "time", ("sandbag",)),
    ("Afundos com sandbag", "legs", "lunge", 0.0, "reps", ("sandbag",)),
    ("Remada com sandbag", "back", "row", 0.0, "reps", ("sandbag",)),
    ("Press com sandbag", "shoulders", "shoulder_press", 0.0, "reps", ("sandbag",)),
    ("Get-up com sandbag", "full", "total_body", 0.0, "reps", ("sandbag",)),
    ("Arrastar sandbag", "full", "total_body", 0.0, "time", ("sandbag",)),
    ("Sandbag por cima do ombro", "full", "total_body", 0.0, "reps", ("sandbag",)),
])

register(Modality("longevity", "Longevidade", "Longevity", "heart",
                  ("Junta tudo: força, equilíbrio, mobilidade e cardio de outros desportos.",
                   "Brings it all together: strength, balance, mobility and other sports' cardio."),
                  Scheme(n=6, sets=3, reps=10, rest_s=75, rpe=7.0), multi=True), [
    ("Equilíbrio numa perna", "mobility", "hip_stability", 0.0, "time", ()),
    ("Sentar e levantar", "legs", "squat", 0.0, "reps", ()),
    ("Suspensão na barra", "back", "pull_up", 0.0, "time", ("pullup_bar",)),
    ("Agachamento profundo (estático)", "mobility", "squat", 0.0, "time", ()),
    ("Mobilidade / aquecimento", "mobility", "warm_up", 0.0, "time", ()),
    ("Caminhada rápida", "legs", "cardio", 0.0, "time", ()),
])

register(Modality("conditioning", "Conditioning", "Conditioning", "stopwatch",
                  ("Voltas de passadeira, remo, força e descanso, com a FC do relógio.",
                   "Laps of treadmill, rowing, strength and rest, with your watch's HR."),
                  Scheme(n=4, sets=1, reps=300, measure="time", time_s=300, rest_s=60),
                  laps=True))

# Os desportos que a Longevidade pode juntar: um bloco de tempo de cada um.
SPORT_BLOCKS = {"rowing": "Remo (máquina)", "cycling": "Bicicleta (rolo)",
                "running": "Passadeira", "swimming": "Natação (piscina)"}
SEED_EXERCISES.append(("Natação (piscina)", "cardio", "full", "cardio", 0.0, "time", ()))


# ================================================================ tabelas


def ensure(db: Database) -> None:
    st.seed(db)
    inventory.ensure(db)
    db.conn.execute("CREATE TABLE IF NOT EXISTS exercise_modalities (exercise_id INTEGER NOT"
                    " NULL REFERENCES exercises(id) ON DELETE CASCADE, modality TEXT NOT NULL,"
                    " PRIMARY KEY (exercise_id, modality)) WITHOUT ROWID")
    db.conn.execute("CREATE TABLE IF NOT EXISTS exercise_equipment (exercise_id INTEGER NOT"
                    " NULL REFERENCES exercises(id) ON DELETE CASCADE, kind TEXT NOT NULL,"
                    " PRIMARY KEY (exercise_id, kind)) WITHOUT ROWID")
    for table, cols in (("exercises", (("description", "TEXT"), ("archived", "INTEGER NOT NULL"
                                                                  " DEFAULT 0"))),
                        ("strength_workouts", (("modality", "TEXT NOT NULL DEFAULT 'strength'"),
                                               ("hidden", "INTEGER NOT NULL DEFAULT 0"))),
                        ("strength_sessions", (("modality", "TEXT"),))):
        have = {r["name"] for r in db.conn.execute(f"PRAGMA table_info({table})")}
        for c, decl in cols:
            if c not in have:
                db.conn.execute(f"ALTER TABLE {table} ADD COLUMN {c} {decl}")
    db.conn.commit()
    seed(db)


def seed(db: Database) -> None:
    """Põe cada exercício na(s) sua(s) modalidade(s), uma vez por versão do
    catálogo; exercícios novos do catálogo entram, os teus ficam como estão."""
    version = len(SEED_EXERCISES) * 1000 + len(MODALITIES)
    if db.get("gym_seed_version") == version:
        return
    by_name = {r["name"]: r["id"] for r in db.conn.execute("SELECT id, name FROM exercises")}
    # os de força que já existiam
    for name, *_ in st.EXERCISES:
        eid = by_name.get(name)
        if eid is None:
            continue
        db.conn.execute("INSERT OR IGNORE INTO exercise_modalities VALUES (?, 'strength')",
                        (eid,))
        for k in STRENGTH_EQUIPMENT.get(name, ()):
            db.conn.execute("INSERT OR IGNORE INTO exercise_equipment VALUES (?, ?)", (eid, k))
    for name, mod, group, cat, bw, measure, kit in SEED_EXERCISES:
        eid = by_name.get(name)
        if eid is None:
            c = db.conn.execute(
                "INSERT INTO exercises(name, category, fit_category, bodyweight, measure, custom)"
                " VALUES (?,?,?,?,?,0)", (name, group, st.FIT_CATEGORY.get(cat, 65534), bw,
                                          measure))
            eid = int(c.lastrowid)
            by_name[name] = eid
        db.conn.execute("INSERT OR IGNORE INTO exercise_modalities VALUES (?, ?)", (eid, mod))
        for k in kit:
            db.conn.execute("INSERT OR IGNORE INTO exercise_equipment VALUES (?, ?)", (eid, k))
    # os teus exercícios antigos (sem modalidade) ficam na Força
    db.conn.execute("INSERT OR IGNORE INTO exercise_modalities SELECT id, 'strength' FROM"
                    " exercises WHERE id NOT IN (SELECT exercise_id FROM exercise_modalities)")
    # planos antigos sem modalidade: os de longevidade passam para lá
    db.conn.execute("UPDATE strength_workouts SET modality = 'longevity' WHERE"
                    " name LIKE 'Longevidade%' AND modality = 'strength'")
    db.conn.commit()
    db.set("gym_seed_version", version)


# =============================================================== exercícios


def exercises(db: Database, mod: str | None = None, *, available_only: bool = False,
              include_archived: bool = False) -> list[dict]:
    """Exercícios de uma modalidade (a Longevidade vê todos), com o material
    e as modalidades a que pertencem."""
    ensure(db)
    m = MODALITIES.get(mod or "")
    rows = [dict(r) for r in db.conn.execute("SELECT * FROM exercises ORDER BY name")]
    mods: dict[int, list[str]] = {}
    for r in db.conn.execute("SELECT * FROM exercise_modalities"):
        mods.setdefault(r["exercise_id"], []).append(r["modality"])
    kit: dict[int, list[str]] = {}
    for r in db.conn.execute("SELECT * FROM exercise_equipment"):
        kit.setdefault(r["exercise_id"], []).append(r["kind"])
    have = inventory.available_kinds(db) if available_only else set()
    out = []
    for r in rows:
        if r.get("archived") and not include_archived:
            continue
        r["modalities"] = mods.get(r["id"], [])
        r["equipment"] = kit.get(r["id"], [])
        if mod and not (m and m.multi) and mod not in r["modalities"] and not (
                m and m.laps and set(r["modalities"]) & {"strength", "cardio"}):
            continue
        if available_only and not set(r["equipment"]) <= have:
            continue
        out.append(r)
    return out


def exercise(db: Database, eid: int) -> dict | None:
    for r in exercises(db, include_archived=True):
        if r["id"] == eid:
            return r
    return None


def save_exercise(db: Database, eid: int | None, *, name: str, mods: Sequence[str],
                  group: str = "full", measure: str = "reps", bodyweight: float = 0.0,
                  equipment: Sequence[str] = (), description: str | None = None) -> int:
    ensure(db)
    name = (name or "").strip() or tr("Exercício", "Exercise")
    if eid is None:
        eid = st.add_exercise(db, name, group, bodyweight, measure)
    else:
        fit_cat = db.conn.execute("SELECT fit_category FROM exercises WHERE id = ?",
                                  (eid,)).fetchone()
        db.conn.execute("UPDATE exercises SET name=?, category=?, bodyweight=?, measure=?"
                        " WHERE id = ?", (name, group, bodyweight, measure, eid))
        _ = fit_cat
    db.conn.execute("UPDATE exercises SET description = ? WHERE id = ?", (description, eid))
    db.conn.execute("DELETE FROM exercise_modalities WHERE exercise_id = ?", (eid,))
    db.conn.execute("DELETE FROM exercise_equipment WHERE exercise_id = ?", (eid,))
    for m in dict.fromkeys(mods or ["strength"]):
        db.conn.execute("INSERT INTO exercise_modalities VALUES (?, ?)", (eid, m))
    for k in dict.fromkeys(equipment):
        db.conn.execute("INSERT INTO exercise_equipment VALUES (?, ?)", (eid, k))
    db.conn.commit()
    return eid


def archive_exercise(db: Database, eid: int, archived: bool = True) -> None:
    """Esconde o exercício das listas (o histórico continua a usá-lo)."""
    ensure(db)
    db.conn.execute("UPDATE exercises SET archived = ? WHERE id = ?", (int(archived), eid))
    db.conn.commit()


def missing_equipment(db: Database, ex: dict) -> list[str]:
    have = inventory.available_kinds(db)
    return [k for k in ex.get("equipment", []) if k not in have]


# ================================================================== planos


def workouts(db: Database, mod: str | None = None) -> list[dict]:
    """Treinos guardados de uma modalidade (sem os rascunhos)."""
    ensure(db)
    out = []
    for w in st.workouts(db):
        if w.get("hidden"):
            continue
        if mod and (w.get("modality") or "strength") != mod:
            continue
        out.append(w)
    return out


def save_plan(db: Database, wid: str | None, name: str, description: str | None,
              items: Sequence[dict], mod: str = "strength", hidden: bool = False) -> str:
    ensure(db)
    wid = st.save_workout(db, wid, name, description, items)
    db.conn.execute("UPDATE strength_workouts SET modality = ?, hidden = ? WHERE id = ?",
                    (mod, int(hidden), wid))
    db.conn.commit()
    return wid


def keep_plan(db: Database, wid: str, name: str) -> None:
    """Um rascunho (treino livre ou surpresa) passa a treino guardado."""
    db.conn.execute("UPDATE strength_workouts SET hidden = 0, name = ?, updated_at = ?"
                    " WHERE id = ?", (name.strip() or "Treino", now_iso(), wid))
    db.conn.commit()


def purge_drafts(db: Database) -> None:
    """Rascunhos que nunca chegaram a ser usados."""
    ensure(db)
    db.conn.execute("DELETE FROM strength_workouts WHERE hidden = 1 AND id NOT IN"
                    " (SELECT workout_id FROM strength_sessions WHERE workout_id IS NOT NULL)")
    db.conn.commit()


def surprise(db: Database, mod: str, seed: int | None = None,
             minutes: int | None = None) -> list[dict]:
    """Treino surpresa: exercícios à sorte da modalidade, só com o material
    que tens (se o inventário estiver vazio, conta tudo como disponível)."""
    ensure(db)
    m = modality(mod)
    rng = random.Random(seed)
    have_inventory = bool(inventory.items(db))
    pool = exercises(db, m.key, available_only=have_inventory)
    if m.multi:
        pool = [e for e in pool if e["category"] != "mobility" or "longevity" in e["modalities"]]
    if not pool:
        pool = exercises(db, m.key)
    sc = m.surprise
    picked: list[dict] = []
    if m.multi:
        # Longevidade: um bloco de cardio de outro desporto, força, equilíbrio, mobilidade
        cardio = [e for e in pool if "cardio" in e["modalities"]]
        balance = [e for e in pool if e["category"] == "mobility"]
        strength_like = [e for e in pool if e not in cardio and e not in balance]
        for group, n in ((cardio, 1), (strength_like, max(1, sc.n - 3)), (balance, 2)):
            rng.shuffle(group)
            picked += [g for g in group if g not in picked][:n]
    else:
        rng.shuffle(pool)
        groups_seen: dict[str, int] = {}
        for e in pool:                         # variedade: no máximo 2 do mesmo grupo
            if groups_seen.get(e["category"], 0) >= 2:
                continue
            picked.append(e)
            groups_seen[e["category"]] = groups_seen.get(e["category"], 0) + 1
            if len(picked) >= sc.n:
                break
    items = []
    for e in picked:
        timed = e.get("measure") == "time"
        reps = sc.reps if sc.measure == ("time" if timed else "reps") else (
            sc.time_s if timed else 10)
        sets = sc.sets
        rest = sc.rest_s
        if timed and "cardio" in e["modalities"] and m.key != "hiit":
            reps, sets, rest = 600, 1, 60          # bloco de cardio: 10 min
        items.append({"exercise_id": e["id"], "sets": sets, "reps": reps, "load_kg": None,
                      "rpe": sc.rpe, "rest_s": rest})
    return items


def plan_minutes(db: Database, wid: str) -> int:
    return round(st.plan_seconds(st.workout_items(db, wid)) / 60)


def sessions(db: Database, mod: str | None = None, limit: int = 200) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM strength_sessions WHERE status='completed'"
    args: list = []
    if mod:
        sql += " AND COALESCE(modality, CASE WHEN mode IN ('free','conditioning') THEN" \
               " 'conditioning' ELSE 'strength' END) = ?"
        args.append(mod)
    try:
        return [dict(r) for r in db.conn.execute(sql + " ORDER BY started_at DESC LIMIT ?",
                                                 args + [limit])]
    except Exception:
        return [dict(r) for r in db.conn.execute(
            "SELECT * FROM strength_sessions WHERE status='completed' ORDER BY started_at"
            " DESC LIMIT ?", (limit,))]
