"""Glossário: os termos da Perennia e do treino, por separador.

Os termos de origem vivem no código (`glossary_data`, nos dois idiomas). Na base de dados
(tabela `glossary`) ficam só as tuas alterações:

* uma linha com `builtin_key` = uma edição (ou, com `deleted`=1, a remoção) de um termo de origem;
* uma linha sem `builtin_key` = um termo teu.

Assim uma versão nova da Perennia pode juntar termos de origem sem pisar o que escreveste, e
«Repor» limita-se a apagar a tua linha. Uma referência (`ref`) de um termo é a chave de origem
(«tr.ftp») ou `c:<id>` para os teus.
"""
from __future__ import annotations

import unicodedata

from . import glossary_data as data
from .db import Database, now_iso
from .i18n import tr
from . import options

CUSTOM = "c:"


def max_term(db: Database) -> int:
    """O tamanho máximo do nome de um termo (opção `glossary_term_chars`)."""
    return int(options.get(db, "glossary_term_chars"))


def ensure(db: Database) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS glossary (id INTEGER PRIMARY KEY,"
        " builtin_key TEXT, tab TEXT NOT NULL DEFAULT 'perennia', term TEXT NOT NULL DEFAULT '',"
        " definition TEXT NOT NULL DEFAULT '', deleted INTEGER NOT NULL DEFAULT 0,"
        " updated_at TEXT NOT NULL)")
    db.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS glossary_builtin"
                    " ON glossary(builtin_key) WHERE builtin_key IS NOT NULL")
    db.conn.commit()


def tabs() -> list[tuple[str, str]]:
    return [(k, tr(pt, en)) for k, pt, en in data.TABS]


def tab_keys() -> list[str]:
    return [k for k, _pt, _en in data.TABS]


def tab_name(key: str) -> str:
    for k, name in tabs():
        if k == key:
            return name
    return key


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


def _builtins() -> dict[str, dict]:
    out = {}
    for tab, rows in data.TERMS.items():
        for key_, tpt, ten, dpt, den in rows:
            out[key_] = {"ref": key_, "tab": tab, "term": tr(tpt, ten),
                         "definition": tr(dpt, den), "builtin": True, "edited": False,
                         "deleted": False, "id": None}
    return out


def _overrides(db: Database) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute("SELECT * FROM glossary ORDER BY id")]


def all_entries(db: Database, include_deleted: bool = False) -> list[dict]:
    """Todos os termos (de origem, já com as tuas edições, e os teus), por ordem alfabética."""
    base = _builtins()
    keys = set(tab_keys())
    out: list[dict] = []
    for r in _overrides(db):
        bk = r["builtin_key"]
        if bk:
            b = base.get(bk)
            if b is None:                     # termo de origem que já não existe
                continue
            b["deleted"] = bool(r["deleted"])
            if not r["deleted"]:
                b.update(term=r["term"] or b["term"], definition=r["definition"],
                         tab=r["tab"] if r["tab"] in keys else b["tab"], edited=True)
            b["id"] = r["id"]
        else:
            out.append({"ref": f"{CUSTOM}{r['id']}", "tab": r["tab"] if r["tab"] in keys
                        else "perennia", "term": r["term"], "definition": r["definition"],
                        "builtin": False, "edited": False, "deleted": False, "id": r["id"]})
    out.extend(b for b in base.values() if include_deleted or not b["deleted"])
    out.sort(key=lambda e: _fold(e["term"]))
    return out


def entries(db: Database, tab: str) -> list[dict]:
    return [e for e in all_entries(db) if e["tab"] == tab]


def get(db: Database, ref: str) -> dict | None:
    for e in all_entries(db, include_deleted=True):
        if e["ref"] == ref:
            return e
    return None


def deleted_builtins(db: Database) -> list[dict]:
    return [e for e in all_entries(db, include_deleted=True) if e["deleted"]]


def find(db: Database, text: str) -> list[dict]:
    """Termos cujo nome ou definição tem `text` (sem maiúsculas nem acentos)."""
    words = _fold(text).split()
    return [e for e in all_entries(db)
            if all(w in _fold(e["term"] + " " + e["definition"]) for w in words)]


def save(db: Database, ref: str | None, term: str, definition: str, tab: str) -> str:
    """Cria um termo teu (`ref` vazio) ou grava a edição de um existente. Devolve a referência.
    Levanta ValueError se faltar o termo ou o separador não existir."""
    ensure(db)
    term = (term or "").strip()[:max_term(db)]
    if not term:
        raise ValueError(tr("Falta o termo.", "The term is missing."))
    if tab not in tab_keys():
        raise ValueError(tr("Separador desconhecido: {t}", "Unknown tab: {t}", t=tab))
    definition = (definition or "").strip()[:int(options.get(db, "note_max_chars"))]
    now = now_iso()
    if not ref:
        cur = db.conn.execute("INSERT INTO glossary (tab, term, definition, updated_at)"
                              " VALUES (?,?,?,?)", (tab, term, definition, now))
        db.conn.commit()
        return f"{CUSTOM}{cur.lastrowid}"
    if ref.startswith(CUSTOM):
        db.conn.execute("UPDATE glossary SET tab=?, term=?, definition=?, updated_at=?"
                        " WHERE id=? AND builtin_key IS NULL",
                        (tab, term, definition, now, int(ref[len(CUSTOM):])))
    else:
        if ref not in _builtins():
            raise ValueError(tr("Termo desconhecido: {t}", "Unknown term: {t}", t=ref))
        db.conn.execute(
            "INSERT INTO glossary (builtin_key, tab, term, definition, deleted, updated_at)"
            " VALUES (?,?,?,?,0,?) ON CONFLICT(builtin_key) WHERE builtin_key IS NOT NULL"
            " DO UPDATE SET tab=excluded.tab, term=excluded.term,"
            " definition=excluded.definition, deleted=0, updated_at=excluded.updated_at",
            (ref, tab, term, definition, now))
    db.conn.commit()
    return ref


def delete(db: Database, ref: str) -> None:
    """Um termo teu desaparece; um de origem fica marcado como apagado (dá para repor)."""
    ensure(db)
    if ref.startswith(CUSTOM):
        db.conn.execute("DELETE FROM glossary WHERE id=? AND builtin_key IS NULL",
                        (int(ref[len(CUSTOM):]),))
    elif ref in _builtins():
        db.conn.execute(
            "INSERT INTO glossary (builtin_key, tab, term, definition, deleted, updated_at)"
            " VALUES (?,?,?,?,1,?) ON CONFLICT(builtin_key) WHERE builtin_key IS NOT NULL"
            " DO UPDATE SET deleted=1, updated_at=excluded.updated_at",
            (ref, "", "", "", now_iso()))
    db.conn.commit()


def restore(db: Database, ref: str) -> None:
    """Um termo de origem volta ao texto original (desfaz a edição ou a remoção)."""
    ensure(db)
    db.conn.execute("DELETE FROM glossary WHERE builtin_key=?", (ref,))
    db.conn.commit()


def restore_all(db: Database) -> int:
    """Repõe todos os termos de origem; os teus ficam. Devolve quantos foram repostos."""
    ensure(db)
    n = db.conn.execute("DELETE FROM glossary WHERE builtin_key IS NOT NULL").rowcount
    db.conn.commit()
    return n
