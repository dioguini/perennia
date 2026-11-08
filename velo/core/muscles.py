"""Grupos e subgrupos musculares.

Cada exercício tem um **grupo** (pernas, costas…) e, dentro dele, um **subgrupo**
(quadríceps, dorsais…). Vêm uns de origem; podes juntar, mudar o nome e apagar à
vontade (separador «Grupos Musculares» da lista de exercícios) — e importar de um
CSV (Sincronização → CSV).

* `muscle_groups`    — `key` (a que o exercício guarda em `exercises.category`) e os nomes;
* `muscle_subgroups` — o subgrupo, dentro de um grupo;
* `exercises.subgroup_id` — o subgrupo de cada exercício (opcional).
"""
from __future__ import annotations

import re
import unicodedata

from .i18n import tr

# (chave, PT, EN, [subgrupos PT/EN])
DEFAULTS: tuple[tuple[str, str, str, tuple[tuple[str, str], ...]], ...] = (
    ("legs", "Pernas", "Legs", (("Quadríceps", "Quadriceps"), ("Isquiotibiais", "Hamstrings"),
                                ("Gémeos", "Calves"), ("Adutores", "Adductors"),
                                ("Abdutores", "Abductors"))),
    ("hips", "Anca", "Hips", (("Glúteo máximo", "Gluteus maximus"),
                              ("Glúteo médio", "Gluteus medius"),
                              ("Flexores da anca", "Hip flexors"),
                              ("Rotadores da anca", "Hip rotators"))),
    ("chest", "Peito", "Chest", (("Peitoral maior", "Pectoralis major"),
                                 ("Peitoral menor", "Pectoralis minor"))),
    ("back", "Costas", "Back", (("Dorsais", "Lats"), ("Trapézio", "Trapezius"),
                                ("Romboides", "Rhomboids"), ("Lombar", "Lower back"))),
    ("shoulders", "Ombros", "Shoulders", (("Deltoide anterior", "Front deltoid"),
                                          ("Deltoide lateral", "Side deltoid"),
                                          ("Deltoide posterior", "Rear deltoid"),
                                          ("Manguito rotador", "Rotator cuff"))),
    ("arms", "Braços", "Arms", (("Bíceps", "Biceps"), ("Tríceps", "Triceps"),
                                ("Antebraço", "Forearm"))),
    ("core", "Core", "Core", (("Reto abdominal", "Rectus abdominis"), ("Oblíquos", "Obliques"),
                              ("Transverso", "Transverse abdominis"),
                              ("Estabilizadores", "Stabilizers"))),
    ("full", "Corpo inteiro", "Full body", ()),
    ("mobility", "Mobilidade", "Mobility", (("Coluna", "Spine"), ("Anca", "Hip"),
                                            ("Ombros", "Shoulders"), ("Tornozelos", "Ankles"))),
)


def ensure(db) -> None:
    db.conn.execute("CREATE TABLE IF NOT EXISTS muscle_groups (key TEXT PRIMARY KEY,"
                    " name_pt TEXT NOT NULL, name_en TEXT NOT NULL, sort INTEGER NOT NULL"
                    " DEFAULT 0)")
    db.conn.execute("CREATE TABLE IF NOT EXISTS muscle_subgroups (id INTEGER PRIMARY KEY,"
                    " group_key TEXT NOT NULL REFERENCES muscle_groups(key) ON DELETE CASCADE,"
                    " name_pt TEXT NOT NULL, name_en TEXT NOT NULL, sort INTEGER NOT NULL"
                    " DEFAULT 0, UNIQUE (group_key, name_pt))")
    try:
        have = {r["name"] for r in db.conn.execute("PRAGMA table_info(exercises)")}
        if have and "subgroup_id" not in have:
            db.conn.execute("ALTER TABLE exercises ADD COLUMN subgroup_id INTEGER")
    except Exception:
        pass
    db.conn.commit()
    if not db.conn.execute("SELECT 1 FROM muscle_groups LIMIT 1").fetchone():
        for i, (key, pt, en, subs) in enumerate(DEFAULTS):
            db.conn.execute("INSERT OR IGNORE INTO muscle_groups VALUES (?,?,?,?)",
                            (key, pt, en, i))
            for j, (spt, sen) in enumerate(subs):
                db.conn.execute("INSERT OR IGNORE INTO muscle_subgroups (group_key, name_pt,"
                                " name_en, sort) VALUES (?,?,?,?)", (key, spt, sen, j))
        db.conn.commit()


def _slug(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "grupo"


def groups(db) -> list[dict]:
    """[{key, name, name_pt, name_en, subgroups: [{id, name, name_pt, name_en}]}]"""
    ensure(db)
    subs: dict[str, list[dict]] = {}
    for r in db.conn.execute("SELECT * FROM muscle_subgroups ORDER BY sort, name_pt"):
        subs.setdefault(r["group_key"], []).append(
            {"id": r["id"], "name": tr(r["name_pt"], r["name_en"]), "name_pt": r["name_pt"],
             "name_en": r["name_en"]})
    return [{"key": r["key"], "name": tr(r["name_pt"], r["name_en"]), "name_pt": r["name_pt"],
             "name_en": r["name_en"], "subgroups": subs.get(r["key"], [])}
            for r in db.conn.execute("SELECT * FROM muscle_groups ORDER BY sort, name_pt")]


def group_name(db, key: str | None) -> str:
    for g in groups(db):
        if g["key"] == key:
            return g["name"]
    return key or "—"


def subgroup_name(db, sid: int | None) -> str:
    if not sid:
        return "—"
    ensure(db)
    r = db.conn.execute("SELECT * FROM muscle_subgroups WHERE id = ?", (sid,)).fetchone()
    return tr(r["name_pt"], r["name_en"]) if r else "—"


def subgroup_group(db, sid: int | None) -> str | None:
    if not sid:
        return None
    r = db.conn.execute("SELECT group_key FROM muscle_subgroups WHERE id = ?", (sid,)).fetchone()
    return r["group_key"] if r else None


def add_group(db, name_pt: str, name_en: str | None = None) -> str:
    ensure(db)
    name_pt = " ".join((name_pt or "").split())
    if not name_pt:
        raise ValueError("nome vazio")
    key = _slug(name_pt)
    base, n = key, 2
    while db.conn.execute("SELECT 1 FROM muscle_groups WHERE key = ?", (key,)).fetchone():
        key = f"{base}_{n}"
        n += 1
    top = db.conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM muscle_groups").fetchone()[0]
    db.conn.execute("INSERT INTO muscle_groups VALUES (?,?,?,?)",
                    (key, name_pt, (name_en or name_pt).strip(), top))
    db.conn.commit()
    return key


def rename_group(db, key: str, name_pt: str, name_en: str | None = None) -> None:
    ensure(db)
    db.conn.execute("UPDATE muscle_groups SET name_pt = ?, name_en = ? WHERE key = ?",
                    (name_pt.strip(), (name_en or name_pt).strip(), key))
    db.conn.commit()


def delete_group(db, key: str) -> None:
    """Apaga o grupo e os seus subgrupos; os exercícios passam a «corpo inteiro»."""
    ensure(db)
    if key == "full":
        return
    db.conn.execute("UPDATE exercises SET category = 'full', subgroup_id = NULL WHERE"
                    " category = ?", (key,))
    db.conn.execute("DELETE FROM muscle_subgroups WHERE group_key = ?", (key,))
    db.conn.execute("DELETE FROM muscle_groups WHERE key = ?", (key,))
    db.conn.commit()


def add_subgroup(db, group_key: str, name_pt: str, name_en: str | None = None) -> int:
    ensure(db)
    name_pt = " ".join((name_pt or "").split())
    if not name_pt:
        raise ValueError("nome vazio")
    r = db.conn.execute("SELECT id FROM muscle_subgroups WHERE group_key = ? AND name_pt = ?",
                        (group_key, name_pt)).fetchone()
    if r:
        return int(r["id"])
    top = db.conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM muscle_subgroups WHERE"
                          " group_key = ?", (group_key,)).fetchone()[0]
    cur = db.conn.execute("INSERT INTO muscle_subgroups (group_key, name_pt, name_en, sort)"
                          " VALUES (?,?,?,?)", (group_key, name_pt, (name_en or name_pt).strip(),
                                                top))
    db.conn.commit()
    return int(cur.lastrowid)


def rename_subgroup(db, sid: int, name_pt: str, name_en: str | None = None) -> None:
    ensure(db)
    db.conn.execute("UPDATE muscle_subgroups SET name_pt = ?, name_en = ? WHERE id = ?",
                    (name_pt.strip(), (name_en or name_pt).strip(), sid))
    db.conn.commit()


def delete_subgroup(db, sid: int) -> None:
    ensure(db)
    db.conn.execute("UPDATE exercises SET subgroup_id = NULL WHERE subgroup_id = ?", (sid,))
    db.conn.execute("DELETE FROM muscle_subgroups WHERE id = ?", (sid,))
    db.conn.commit()


def exercise_counts(db) -> dict:
    """{chave do grupo: nº de exercícios} e {id do subgrupo: nº}."""
    ensure(db)
    g = {r["category"]: r["n"] for r in db.conn.execute(
        "SELECT category, COUNT(*) AS n FROM exercises GROUP BY category")}
    s = {r["subgroup_id"]: r["n"] for r in db.conn.execute(
        "SELECT subgroup_id, COUNT(*) AS n FROM exercises WHERE subgroup_id IS NOT NULL"
        " GROUP BY subgroup_id")}
    return {"groups": g, "subgroups": s}
