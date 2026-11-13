"""Separadores da Saúde criados por ti.

Como as disciplinas do ginásio: dás um nome e ganha logo um separador no menu Saúde. Cada
separador tem sempre a componente **Notas** (uma lista de notas datadas, com título e texto);
o módulo próprio de cada um (fisioterapia, dentista, suplementos…) fica para depois, mas a base
— o separador, as notas, o backup e o que o Assistente de saúde lê — já existe.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from .db import Database, now_iso
from .i18n import tr

NAME_MAX = 40
RESERVED = ("labs", "diary", "bp", "trends", "metrics", "assistant")


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS health_tabs (
      key        TEXT PRIMARY KEY,
      name       TEXT NOT NULL,
      sort       INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS health_tab_notes (
      id         INTEGER PRIMARY KEY,
      tab_key    TEXT NOT NULL REFERENCES health_tabs(key) ON DELETE CASCADE,
      day        TEXT NOT NULL,
      title      TEXT,
      text       TEXT,
      updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_health_tab_notes ON health_tab_notes(tab_key, day);
    """)


def tabs(db: Database) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT t.*, (SELECT COUNT(*) FROM health_tab_notes n WHERE n.tab_key = t.key) AS n"
        " FROM health_tabs t ORDER BY t.sort, t.name")]


def tab(db: Database, key: str) -> dict | None:
    return next((t for t in tabs(db) if t["key"] == key), None)


def _key(db: Database, name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    key = re.sub(r"[^a-z0-9]+", "_", "".join(c for c in s if not unicodedata.combining(c))
                 .lower()).strip("_") or "separador"
    taken = {t["key"] for t in tabs(db)} | set(RESERVED)
    base, n = key, 2
    while key in taken:
        key = f"{base}_{n}"
        n += 1
    return key


def _clean(name: str) -> str:
    name = " ".join((name or "").split())[:NAME_MAX]
    if not name:
        raise ValueError(tr("Escreve o nome do separador.", "Type the tab name."))
    return name


def add_tab(db: Database, name: str) -> str:
    ensure(db)
    name = _clean(name)
    if any(t["name"].lower() == name.lower() for t in tabs(db)):
        raise ValueError(tr("Já existe um separador com esse nome.",
                            "A tab with that name already exists."))
    key = _key(db, name)
    top = db.conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM health_tabs").fetchone()[0]
    db.conn.execute("INSERT INTO health_tabs (key, name, sort, created_at) VALUES (?,?,?,?)",
                    (key, name, top, now_iso()))
    db.conn.commit()
    return key


def rename_tab(db: Database, key: str, name: str) -> None:
    ensure(db)
    name = _clean(name)
    if any(t["name"].lower() == name.lower() and t["key"] != key for t in tabs(db)):
        raise ValueError(tr("Já existe um separador com esse nome.",
                            "A tab with that name already exists."))
    db.conn.execute("UPDATE health_tabs SET name = ? WHERE key = ?", (name, key))
    db.conn.commit()


def delete_tab(db: Database, key: str) -> None:
    """Apaga o separador e as notas dele."""
    ensure(db)
    db.conn.execute("DELETE FROM health_tab_notes WHERE tab_key = ?", (key,))
    db.conn.execute("DELETE FROM health_tabs WHERE key = ?", (key,))
    db.conn.commit()


def notes(db: Database, key: str, limit: int | None = None) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM health_tab_notes WHERE tab_key = ? ORDER BY day DESC, id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(r) for r in db.conn.execute(sql, (key,))]


def note(db: Database, note_id: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM health_tab_notes WHERE id = ?", (note_id,)).fetchone()
    return dict(r) if r else None


def save_note(db: Database, note_id: int | None, key: str, *, day: date | str, title: str = "",
              text: str = "") -> int:
    ensure(db)
    if tab(db, key) is None:
        raise ValueError(tr("Esse separador já não existe.", "That tab no longer exists."))
    d = day.isoformat() if isinstance(day, date) else str(day)[:10]
    date.fromisoformat(d)
    title, text = " ".join((title or "").split()), (text or "").strip()
    if not title and not text:
        raise ValueError(tr("Escreve um título ou o texto da nota.",
                            "Type a title or the note text."))
    if note_id:
        db.conn.execute("UPDATE health_tab_notes SET day=?, title=?, text=?, updated_at=?"
                        " WHERE id=?", (d, title, text, now_iso(), note_id))
    else:
        note_id = int(db.conn.execute(
            "INSERT INTO health_tab_notes (tab_key, day, title, text, updated_at)"
            " VALUES (?,?,?,?,?)", (key, d, title, text, now_iso())).lastrowid)
    db.conn.commit()
    return note_id


def delete_note(db: Database, note_id: int) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM health_tab_notes WHERE id = ?", (note_id,))
    db.conn.commit()
