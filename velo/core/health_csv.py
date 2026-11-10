"""CSV da Saúde: os valores do diário (os mesmos campos que a Perennia tem) por data.

Uma linha por dia: a primeira coluna é a **data** (`data`; aceita-se AAAA-MM-DD e
DD/MM/AAAA) e há uma coluna por **métrica do diário**, com o nome que ela tem na
Perennia (as que ligaste ou criaste). Uma coluna extra, `nota`, é a nota livre do dia.
Os valores respeitam o tipo da métrica: número (`7,5`), sim/não (`sim`, `não`, `1`, `0`),
escala 1–5, hora (`22:30`), texto e escolha (uma das opções). Colunas que não correspondam
a nenhuma métrica ignoram-se (e dizem-se no relatório).

Ficheiros UTF-8 (com BOM) com `;`; na importação também se aceita `,` e tab.
"""
from __future__ import annotations

import csv
import io
import unicodedata
from datetime import date
from pathlib import Path

from . import health
from .i18n import tr

DELIM = ";"
DATE_NAMES = ("data", "date", "dia", "day")
NOTE_NAMES = ("nota", "notas", "note", "notes")


def _fold(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def metrics(db) -> list[dict]:
    health.seed(db)
    return health.metrics(db)


def columns(db) -> list[str]:
    return ["data"] + [m["name"] for m in metrics(db)] + ["nota"]


def _example(m: dict) -> str:
    k = m["kind"]
    if k == "bool":
        return "sim"
    if k == "scale":
        return "3"
    if k == "time":
        return "22:30"
    if k == "choice":
        return (m.get("choices") or [""])[0]
    if k == "number":
        return {"sleep_hours": "7,5", "rhr": "52", "hrv_rmssd": "68", "weight": "72,4",
                "steps": "9000", "water": "2"}.get(m.get("key") or "", "")
    return ""


def _render(cols: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=DELIM, lineterminator="\r\n")
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def template(db) -> str:
    ms = metrics(db)
    row = [date.today().isoformat()] + [_example(m) for m in ms] + [""]
    return _render(columns(db), [row])


def _cell(m: dict, v) -> str:
    if v is None or v == "":
        return ""
    k = m["kind"]
    if k == "bool":
        return "sim" if float(v) >= 0.5 else "não"
    if k == "number":
        return f"{float(v):g}".replace(".", ",")
    if k == "scale":
        return f"{float(v):g}"
    return str(v)


def export_csv(db) -> str:
    ms = metrics(db)
    days = sorted({r["day"] for r in db.conn.execute("SELECT day FROM daily_values")}
                  | {r["day"] for r in db.conn.execute("SELECT day FROM day_notes WHERE text"
                                                       " != ''")})
    rows = []
    for d in days:
        vals = health.values_for(db, d)
        rows.append([d] + [_cell(m, (vals.get(m["id"]) or {}).get("value")) for m in ms]
                    + [health.day_note(db, d)])
    return _render(columns(db), rows)


def write(db, folder, *, what: str = "export") -> str:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if what == "template":
        path, text = folder / "perennia_modelo_saude.csv", template(db)
    else:
        path, text = folder / f"perennia_saude_{date.today().isoformat()}.csv", export_csv(db)
    path.write_text(text, encoding="utf-8-sig", newline="")
    return str(path)


def parse(text: str) -> tuple[list[str], list[list[str]]]:
    text = text.lstrip("﻿")
    head = text.splitlines()[0] if text.strip() else ""
    delim = max((";", ",", "\t"), key=head.count) if head else DELIM
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return (rows[0], rows[1:]) if rows else ([], [])


def _bool(v: str) -> float | None:
    s = _fold(v)
    if s in ("sim", "s", "yes", "y", "true", "1", "x"):
        return 1.0
    if s in ("nao", "n", "no", "false", "0"):
        return 0.0
    return None


def _num(v: str) -> float | None:
    try:
        return float(str(v).strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def _value(m: dict, raw: str):
    """O valor de uma célula no tipo da métrica, ou None se não for válido."""
    raw = (raw or "").strip()
    if not raw:
        return None
    k = m["kind"]
    if k == "bool":
        return _bool(raw)
    if k in ("number", "scale"):
        v = _num(raw)
        if v is not None and k == "scale":
            return v if 1 <= v <= 5 else None
        return v
    if k == "time":
        parts = raw.replace("h", ":").split(":")
        try:
            hh, mm = int(parts[0]), int(parts[1]) if len(parts) > 1 and parts[1] else 0
        except ValueError:
            return None
        return f"{hh:02d}:{mm:02d}" if 0 <= hh < 24 and 0 <= mm < 60 else None
    if k == "choice":
        for c in m.get("choices") or []:
            if _fold(c) == _fold(raw):
                return c
        return None
    return raw


def detect(db, text: str) -> bool:
    """É um CSV da Saúde? Tem uma coluna de data e pelo menos uma métrica conhecida."""
    cols, _rows = parse(text)
    low = [_fold(c) for c in cols]
    if not any(c in DATE_NAMES for c in low):
        return False
    names = {_fold(m["name"]) for m in metrics(db)} | {_fold(m.get("key")) for m in metrics(db)}
    return any(c in names for c in low)


def import_csv(db, text: str) -> dict:
    """Importa os valores por data. Devolve {days, values, ignored, invalid}."""
    ms = metrics(db)
    by_name = {}
    for m in ms:
        by_name[_fold(m["name"])] = m
        by_name.setdefault(_fold(m.get("key")), m)
    cols, rows = parse(text)
    low = [_fold(c) for c in cols]
    date_i = next((i for i, c in enumerate(low) if c in DATE_NAMES), None)
    rep = {"days": 0, "values": 0, "ignored": [], "invalid": 0}
    if date_i is None:
        raise ValueError(tr("O .csv não tem a coluna «data».", "The .csv has no “data” column."))
    note_i = next((i for i, c in enumerate(low) if c in NOTE_NAMES), None)
    metric_cols = {}
    for i, c in enumerate(low):
        if i in (date_i, note_i):
            continue
        if c in by_name:
            metric_cols[i] = by_name[c]
        elif c:
            rep["ignored"].append(cols[i])
    days = set()
    for r in rows:
        if len(r) <= date_i:
            continue
        day = health._parse_day(r[date_i])
        if not day:
            continue
        for i, m in metric_cols.items():
            if i >= len(r) or not r[i].strip():
                continue
            v = _value(m, r[i])
            if v is None:
                rep["invalid"] += 1
                continue
            health.set_value(db, day, m["id"], v, source="csv")
            rep["values"] += 1
            days.add(day)
        if note_i is not None and note_i < len(r) and r[note_i].strip():
            health.set_day_note(db, day, r[note_i].strip())
            days.add(day)
    rep["days"] = len(days)
    return rep


def report_text(rep: dict) -> str:
    t = tr("{v} valores em {d} dias", "{v} values over {d} days", v=rep["values"], d=rep["days"])
    if rep["invalid"]:
        t += " · " + tr("{n} inválidos", "{n} invalid", n=rep["invalid"])
    if rep["ignored"]:
        t += " · " + tr("colunas ignoradas: {c}", "ignored columns: {c}",
                        c=", ".join(rep["ignored"][:3]))
    return t
