"""Glossário das análises clínicas: o que é cada componente, o que o faz subir e descer, o que é
bom e mau para ele e as estratégias para o pôr no intervalo.

Os componentes de origem vivem no código (`lab_glossary_data`, nos dois idiomas). Na base de
dados (tabela `lab_glossary`) ficam só as tuas alterações, como no Glossário geral:

* uma linha com `builtin_key` = uma edição (ou, com `deleted`=1, a remoção) de um de origem;
* uma linha sem `builtin_key` = um componente teu.

Cada resultado de uma análise liga-se a um componente pelo nome (com os nomes alternativos e
sem acentos): «Ferritina (Electroquimiluminiscência)» → Ferritina; «Colesterol HDL» → HDL. A
referência (`ref`) de um componente é a chave de origem («ferritin») ou `c:<id>` para os teus.

É informação geral, para perceber os resultados — não substitui o médico.
"""
from __future__ import annotations

import re
import unicodedata

from . import lab_glossary_data as data
from .db import Database, now_iso
from .i18n import EN, language, tr

CUSTOM = "c:"
FIELDS = ("summary", "what", "up", "down", "good", "bad", "act")
_SHORT = {"summary": "s", "what": "w", "up": "up", "down": "down", "good": "good",
          "bad": "bad", "act": "act"}


def section_titles() -> list[tuple[str, str]]:
    """(campo, título) das secções de um componente, pela ordem em que se mostram."""
    return [("what", tr("O que é", "What it is")),
            ("up", tr("O que faz subir", "What raises it")),
            ("down", tr("O que faz descer", "What lowers it")),
            ("good", tr("O que é bom", "What is good for it")),
            ("bad", tr("O que é mau", "What is bad for it")),
            ("act", tr("Estratégias para ficar no intervalo", "Strategies to stay in range"))]


DISCLAIMER_PT = ("Informação geral para perceberes os teus resultados — não substitui o médico, "
                 "que conhece o teu caso.")
DISCLAIMER_EN = ("General information to help you understand your results — it does not "
                 "replace your doctor, who knows your case.")


def disclaimer() -> str:
    return tr(DISCLAIMER_PT, DISCLAIMER_EN)


def ensure(db: Database) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS lab_glossary (id INTEGER PRIMARY KEY, builtin_key TEXT,"
        " category TEXT NOT NULL DEFAULT 'other', name TEXT NOT NULL DEFAULT '',"
        " aliases TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',"
        " what TEXT NOT NULL DEFAULT '', up TEXT NOT NULL DEFAULT '',"
        " down TEXT NOT NULL DEFAULT '', good TEXT NOT NULL DEFAULT '',"
        " bad TEXT NOT NULL DEFAULT '', act TEXT NOT NULL DEFAULT '',"
        " deleted INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)")
    db.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS lab_glossary_builtin"
                    " ON lab_glossary(builtin_key) WHERE builtin_key IS NOT NULL")
    db.conn.commit()


# ------------------------------------------------------------------ categorias


def categories() -> list[tuple[str, str]]:
    return [(k, tr(pt, en)) for k, pt, en in data.CATEGORIES]


def category_keys() -> list[str]:
    return [k for k, _pt, _en in data.CATEGORIES]


def category_name(key: str) -> str:
    return dict(categories()).get(key, key)


# ------------------------------------------------------------------ nomes


def fold(text: str) -> str:
    """Minúsculas, sem acentos e com os espaços normalizados."""
    s = "".join(c for c in unicodedata.normalize("NFD", (text or "").lower())
                if unicodedata.category(c) != "Mn")
    return " ".join(s.replace("_", " ").split())


def parse_aliases(text: str) -> list[str]:
    return [fold(a) for a in re.split(r"[,;\n]", text or "") if fold(a)]


# ------------------------------------------------------------------ entradas


def _en() -> bool:
    return language() == EN


def _builtin(m: dict) -> dict:
    loc = m["en"] if _en() else m["pt"]
    e = {"ref": m["key"], "key": m["key"], "builtin": True, "edited": False,
         "category": m["cat"], "name": m["name"][1 if _en() else 0],
         "aliases": [fold(a) for a in m["aliases"]] + [fold(m["name"][0]), fold(m["name"][1])]}
    for f in FIELDS:
        e[f] = loc.get(_SHORT[f], "")
    return e


def _builtins() -> dict[str, dict]:
    return {m["key"]: _builtin(m) for m in data.MARKERS}


def _rows(db: Database) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute("SELECT * FROM lab_glossary ORDER BY id")]


def _from_row(r: dict, base: dict | None) -> dict:
    e = dict(base) if base else {"ref": CUSTOM + str(r["id"]), "key": None, "builtin": False}
    e["edited"] = base is not None
    e["category"] = r["category"] or (base or {}).get("category") or "other"
    e["name"] = r["name"] or (base or {}).get("name", "")
    own = parse_aliases(r["aliases"])
    e["aliases"] = sorted(set(own + ((base or {}).get("aliases") or []) + [fold(e["name"])]))
    for f in FIELDS:
        e[f] = r[f] if r[f] else ((base or {}).get(f, "") if base else "")
    e["id"] = r["id"]
    return e


def all_entries(db: Database, include_deleted: bool = False) -> list[dict]:
    """Todos os componentes (os de origem com as tuas edições e os teus), por categoria e nome."""
    base = _builtins()
    out: dict[str, dict] = dict(base)
    gone: set[str] = set()
    for r in _rows(db):
        if r["builtin_key"]:
            k = r["builtin_key"]
            if k not in base:
                continue
            if r["deleted"]:
                gone.add(k)
                continue
            out[k] = _from_row(r, base[k])
        else:
            if r["deleted"]:
                continue
            e = _from_row(r, None)
            out[e["ref"]] = e
    entries = [e for k, e in out.items() if include_deleted or k not in gone]
    order = {k: i for i, k in enumerate(category_keys())}
    entries.sort(key=lambda e: (order.get(e["category"], 99), fold(e["name"])))
    return entries


def get(db: Database, ref: str) -> dict | None:
    return next((e for e in all_entries(db) if e["ref"] == ref), None)


def deleted_builtins(db: Database) -> list[str]:
    return [r["builtin_key"] for r in _rows(db) if r["builtin_key"] and r["deleted"]]


def edited_builtins(db: Database) -> list[str]:
    return [r["builtin_key"] for r in _rows(db) if r["builtin_key"] and not r["deleted"]]


# ------------------------------------------------------------------ ligação


def match(db: Database, marker: str, entries: list[dict] | None = None) -> dict | None:
    """O componente do glossário de um resultado (pelo nome do boletim), ou None.

    Primeiro um nome igual (sem acentos); depois o nome alternativo mais comprido que apareça
    como palavra inteira no nome do resultado («colesterol hdl» ganha a «colesterol»)."""
    from .labs import short_name
    name = fold(short_name(marker or ""))
    if not name:
        return None
    entries = entries if entries is not None else all_entries(db)
    for e in entries:
        if name in e["aliases"]:
            return e
    best, best_len = None, 0
    for e in entries:
        for a in e["aliases"]:
            if len(a) > best_len and re.search(r"(?<![a-z0-9])" + re.escape(a)
                                               + r"(?![a-z0-9])", name):
                best, best_len = e, len(a)
    return best


def summary_for(db: Database, marker: str, entries: list[dict] | None = None) -> str:
    e = match(db, marker, entries)
    return e["summary"] if e else ""


def tooltip(e: dict) -> str:
    """O texto do rato por cima: o resumo e as estratégias em poucas linhas."""
    out = f"{e['name']} — {e['summary']}"
    if e.get("act"):
        out += "\n" + tr("Para ficar no intervalo: ", "To stay in range: ") + e["act"]
    return out


# ------------------------------------------------------------------ alterações


def save(db: Database, ref: str | None, values: dict) -> str:
    """Grava um componente (novo, teu ou de origem editado). Devolve a referência."""
    ensure(db)
    name = " ".join((values.get("name") or "").split())
    if not name:
        raise ValueError(tr("Escreve o nome do componente.", "Type the component's name."))
    cat = values.get("category") or "other"
    if cat not in category_keys():
        cat = "other"
    cols = {"category": cat, "name": name,
            "aliases": ", ".join(parse_aliases(values.get("aliases_text") or "")
                                 if "aliases_text" in values else []),
            **{f: (values.get(f) or "").strip() for f in FIELDS}}
    now = now_iso()
    if ref is None or ref.startswith(CUSTOM):
        rid = int(ref[len(CUSTOM):]) if ref else None
        if rid is None:
            cur = db.conn.execute(
                "INSERT INTO lab_glossary (builtin_key, category, name, aliases, summary, what,"
                " up, down, good, bad, act, deleted, updated_at)"
                " VALUES (NULL,?,?,?,?,?,?,?,?,?,?,0,?)",
                (cols["category"], cols["name"], cols["aliases"],
                 *[cols[f] for f in FIELDS], now))
            rid = cur.lastrowid
        else:
            db.conn.execute(
                "UPDATE lab_glossary SET category=?, name=?, aliases=?, summary=?, what=?, up=?,"
                " down=?, good=?, bad=?, act=?, updated_at=? WHERE id=?",
                (cols["category"], cols["name"], cols["aliases"],
                 *[cols[f] for f in FIELDS], now, rid))
        db.conn.commit()
        return CUSTOM + str(rid)
    base = _builtins().get(ref)
    if base is None:
        raise ValueError(tr("Componente desconhecido.", "Unknown component."))
    # só fica o que é diferente do original (o resto continua a seguir a versão de origem)
    diff = {f: ("" if cols[f] == base.get(f, "") else cols[f]) for f in FIELDS}
    db.conn.execute(
        "INSERT INTO lab_glossary (builtin_key, category, name, aliases, summary, what, up, down,"
        " good, bad, act, deleted, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?)"
        " ON CONFLICT(builtin_key) WHERE builtin_key IS NOT NULL DO UPDATE SET"
        " category=excluded.category, name=excluded.name, aliases=excluded.aliases,"
        " summary=excluded.summary, what=excluded.what, up=excluded.up, down=excluded.down,"
        " good=excluded.good, bad=excluded.bad, act=excluded.act, deleted=0,"
        " updated_at=excluded.updated_at",
        (ref, cols["category"], "" if name == base["name"] else name, cols["aliases"],
         *[diff[f] for f in FIELDS], now))
    db.conn.commit()
    return ref


def delete(db: Database, ref: str) -> None:
    """Um teu apaga-se; um de origem fica escondido (e pode voltar com «Repor»)."""
    ensure(db)
    if ref.startswith(CUSTOM):
        db.conn.execute("DELETE FROM lab_glossary WHERE id = ?", (int(ref[len(CUSTOM):]),))
    else:
        db.conn.execute(
            "INSERT INTO lab_glossary (builtin_key, deleted, updated_at) VALUES (?,1,?)"
            " ON CONFLICT(builtin_key) WHERE builtin_key IS NOT NULL DO UPDATE SET deleted=1,"
            " updated_at=excluded.updated_at", (ref, now_iso()))
    db.conn.commit()


def restore(db: Database, ref: str) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM lab_glossary WHERE builtin_key = ?", (ref,))
    db.conn.commit()


def restore_all(db: Database) -> int:
    ensure(db)
    n = db.conn.execute("DELETE FROM lab_glossary WHERE builtin_key IS NOT NULL").rowcount
    db.conn.commit()
    return int(n or 0)


def latest_values(db: Database) -> dict[str, dict]:
    """{ref: o último resultado (valor, unidade, data, ▲/▼)} dos componentes que já mediste."""
    from . import health, labs
    labs.ensure(db)
    entries = all_entries(db)
    out: dict[str, dict] = {}
    rows = db.conn.execute(
        "SELECT r.*, p.done_on FROM lab_results r JOIN lab_reports p ON p.id = r.report_id"
        " ORDER BY p.done_on, r.id").fetchall()
    for r in rows:
        x = dict(r)
        e = match(db, x["marker"], entries)
        if e is None:
            continue
        out[e["ref"]] = {"text": labs.value_text(x), "unit": x.get("unit") or "",
                         "done_on": x["done_on"], "flag": health.flag(x)}
    return out
