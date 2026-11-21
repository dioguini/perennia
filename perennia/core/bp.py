"""Pressão arterial: várias medições por dia, por período, com médias.

Cada medição é uma linha (`bp_readings`): o dia, o período (manhã, tarde, noite, ou os que
definires), a hora, a máxima (sistólica), a mínima (diastólica), a pulsação e uma nota. Daqui
saem:

* a **média de cada período** de cada dia (três medições de manhã → um valor da manhã);
* a **média diária** — por omissão a média das médias dos períodos (manhã e noite pesam o mesmo,
  mesmo que uma tenha mais medições); pode ser a média de todas as medições (opção
  `bp_daily_mode`);
* opcionalmente, ignora-se a 1.ª medição de cada período com 3 ou mais (`bp_discard_first`).

A média diária é também gravada nas métricas do diário «Tensão arterial (máxima)» e «(mínima)»
(com a origem «bp»), para as tendências, a Análise AdHoc e a longevidade continuarem a vê-la.
Os valores que já estavam no diário passam, uma única vez, a medições «sem período».

A classificação (baixa / normal / alta / muito alta) usa os limiares das opções, que por omissão
são os habituais para medições em casa (135/85). É uma leitura para conversares com o médico:
não é um diagnóstico.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from . import health, options
from .db import Database, now_iso
from .i18n import tr

SOURCE = "bp"                       # a origem das médias diárias gravadas no diário
NO_PERIOD = ""                      # medições antigas, vindas do diário
DEFAULT_PERIODS = (("morning", "Manhã", "Morning"), ("afternoon", "Tarde", "Afternoon"),
                   ("night", "Noite", "Night"))
SYS_RANGE = (50.0, 300.0)           # limites de plausibilidade (erros de escrita)
DIA_RANGE = (30.0, 200.0)
PULSE_RANGE = (25.0, 250.0)


def ensure(db: Database) -> None:
    health.ensure(db)
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS bp_readings (
      id         INTEGER PRIMARY KEY,
      day        TEXT NOT NULL,
      period     TEXT NOT NULL DEFAULT '',
      at         TEXT,
      sys        REAL NOT NULL,
      dia        REAL NOT NULL,
      pulse      REAL,
      notes      TEXT,
      source     TEXT NOT NULL DEFAULT 'manual',
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_bp_day ON bp_readings(day, period);
    """)
    _migrate_from_diary(db)


_migrating = False


def _migrate_from_diary(db: Database) -> None:
    """Os valores que estão no diário sem medições por trás (os antigos, ou os que um .csv
    importou) passam a medições «sem período». Pode correr sempre: depois de passar, o valor do
    diário fica com a origem «bp» e já não é apanhado outra vez."""
    global _migrating
    if _migrating:
        return
    _migrating = True
    try:
        _migrate(db)
    finally:
        _migrating = False


def _migrate(db: Database) -> None:
    ms, md = health.metric_by_key(db, "bp_sys"), health.metric_by_key(db, "bp_dia")
    if not ms or not md:
        return
    rows = db.conn.execute(
        "SELECT s.day, s.num AS sys, d.num AS dia, s.notes, s.source FROM daily_values s"
        " JOIN daily_values d ON d.day = s.day AND d.metric_id = ?"
        " WHERE s.metric_id = ? AND s.num IS NOT NULL AND d.num IS NOT NULL"
        " AND s.source != ?", (md["id"], ms["id"], SOURCE)).fetchall()
    for r in rows:
        if not db.conn.execute("SELECT 1 FROM bp_readings WHERE day = ?",
                               (r["day"],)).fetchone():
            if validate(r["sys"], r["dia"]) is not None:
                continue                              # um valor impossível fica só no diário
            db.conn.execute(
                "INSERT INTO bp_readings (day, period, at, sys, dia, notes, source, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (r["day"], NO_PERIOD, None, r["sys"], r["dia"], r["notes"],
                 r["source"] or "manual", now_iso()))
            db.conn.commit()
        sync_daily(db, r["day"])


# ------------------------------------------------------------------ períodos


def periods(db: Database) -> list[tuple[str, str]]:
    """[(chave, nome)] pela ordem do dia. Os teus (definição `bp_periods`) ou os de origem."""
    custom = db.get("bp_periods", None)
    if isinstance(custom, list) and custom:
        out = []
        for p in custom:
            if isinstance(p, (list, tuple)) and len(p) >= 2 and str(p[0]).strip():
                out.append((str(p[0]), str(p[1])))
        if out:
            return out
    return [(k, tr(pt, en)) for k, pt, en in DEFAULT_PERIODS]


def period_name(db: Database, key: str) -> str:
    if key == NO_PERIOD:
        return tr("Sem período", "No period")
    return dict(periods(db)).get(key, key)


def set_periods(db: Database, names: list[str]) -> list[tuple[str, str]]:
    """Define os períodos pelo nome (a chave de um período de origem mantém-se; os novos ganham
    uma chave a partir do nome). As medições de um período que saia ficam «sem período»."""
    import re
    import unicodedata
    base = {tr(pt, en).lower(): k for k, pt, en in DEFAULT_PERIODS}
    base.update({name.lower(): k for k, name in periods(db)})
    out: list[tuple[str, str]] = []
    used: set[str] = set()
    for name in names:
        name = " ".join(str(name).split())
        if not name:
            continue
        key = base.get(name.lower())
        if key is None:
            s = unicodedata.normalize("NFKD", name)
            key = re.sub(r"[^a-z0-9]+", "_", "".join(c for c in s if not unicodedata.combining(c))
                         .lower()).strip("_") or "periodo"
        root, n = key, 2
        while key in used:
            key = f"{root}_{n}"
            n += 1
        used.add(key)
        out.append((key, name))
    if not out:
        raise ValueError(tr("tem de haver pelo menos um período", "at least one period is needed"))
    ensure(db)
    keep = [k for k, _ in out]
    db.conn.execute(
        f"UPDATE bp_readings SET period = '' WHERE period NOT IN ({','.join('?' * len(keep))})",
        keep)
    db.conn.commit()
    db.set("bp_periods", [list(p) for p in out])
    for (day,) in db.conn.execute("SELECT DISTINCT day FROM bp_readings").fetchall():
        sync_daily(db, day)
    return out


def reset_periods(db: Database) -> None:
    set_periods(db, [tr(pt, en) for _k, pt, en in DEFAULT_PERIODS])
    db.conn.execute("DELETE FROM settings WHERE key = 'bp_periods'")
    db.conn.commit()


def guess_period(db: Database, at: str | None = None) -> str:
    """O período sugerido pela hora (só para os três de origem; senão, o primeiro)."""
    ps = periods(db)
    keys = [k for k, _ in ps]
    try:
        hour = int(str(at)[:2]) if at else datetime.now().hour
    except ValueError:
        hour = datetime.now().hour
    if hour < int(options.get(db, "bp_morning_until_h")):
        want = "morning"
    elif hour < int(options.get(db, "bp_afternoon_until_h")):
        want = "afternoon"
    else:
        want = "night"
    return want if want in keys else keys[0]


# ------------------------------------------------------------------ medições


def parse_time(text: str | None) -> str | None:
    """«8», «0830», «8:30», «8h30» → «08:30». None se não for uma hora."""
    if text is None:
        return None
    digits = "".join(c if c.isdigit() else ":" for c in str(text).strip()).strip(":")
    if not digits:
        return None
    parts = [p for p in digits.split(":") if p]
    if len(parts) == 1:
        p = parts[0]
        parts = [p[:-2] or "0", p[-2:]] if len(p) > 2 else [p, "0"]
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def validate(sys_: Any, dia: Any, pulse: Any = None) -> str | None:
    """A razão por que a medição não pode ser guardada, ou None se está boa."""
    if sys_ is None or dia is None:
        return tr("Escreve a máxima e a mínima.", "Type the systolic and the diastolic.")
    if not SYS_RANGE[0] <= sys_ <= SYS_RANGE[1]:
        return tr("A máxima tem de estar entre {a:g} e {b:g} mmHg.",
                  "Systolic must be between {a:g} and {b:g} mmHg.", a=SYS_RANGE[0],
                  b=SYS_RANGE[1])
    if not DIA_RANGE[0] <= dia <= DIA_RANGE[1]:
        return tr("A mínima tem de estar entre {a:g} e {b:g} mmHg.",
                  "Diastolic must be between {a:g} and {b:g} mmHg.", a=DIA_RANGE[0],
                  b=DIA_RANGE[1])
    if dia >= sys_:
        return tr("A mínima tem de ser menor do que a máxima.",
                  "Diastolic must be lower than systolic.")
    if pulse is not None and not PULSE_RANGE[0] <= pulse <= PULSE_RANGE[1]:
        return tr("A pulsação tem de estar entre {a:g} e {b:g} bpm.",
                  "Pulse must be between {a:g} and {b:g} bpm.", a=PULSE_RANGE[0],
                  b=PULSE_RANGE[1])
    return None


def save_reading(db: Database, reading_id: int | None, *, day: date | str, period: str,
                 sys: float, dia: float, pulse: float | None = None, at: str | None = None,
                 notes: str = "", source: str = "manual") -> int:
    ensure(db)
    err = validate(sys, dia, pulse)
    if err:
        raise ValueError(err)
    d = health.day_key(day)
    at = parse_time(at)
    old_day = None
    if reading_id:
        row = db.conn.execute("SELECT day FROM bp_readings WHERE id = ?", (reading_id,)).fetchone()
        old_day = row["day"] if row else None
        db.conn.execute("UPDATE bp_readings SET day=?, period=?, at=?, sys=?, dia=?, pulse=?,"
                        " notes=? WHERE id=?", (d, period, at, float(sys), float(dia), pulse,
                                                notes or None, reading_id))
    else:
        cur = db.conn.execute(
            "INSERT INTO bp_readings (day, period, at, sys, dia, pulse, notes, source,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (d, period, at, float(sys), float(dia), pulse, notes or None, source, now_iso()))
        reading_id = int(cur.lastrowid)
    db.conn.commit()
    sync_daily(db, d)
    if old_day and old_day != d:
        sync_daily(db, old_day)
    return reading_id


def delete_reading(db: Database, reading_id: int) -> None:
    ensure(db)
    row = db.conn.execute("SELECT day FROM bp_readings WHERE id = ?", (reading_id,)).fetchone()
    db.conn.execute("DELETE FROM bp_readings WHERE id = ?", (reading_id,))
    db.conn.commit()
    if row:
        sync_daily(db, row["day"])


def reading(db: Database, reading_id: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM bp_readings WHERE id = ?", (reading_id,)).fetchone()
    return dict(r) if r else None


def readings(db: Database, day: date | str) -> list[dict]:
    """As medições de um dia, pela ordem dos períodos e depois pela hora."""
    ensure(db)
    order = {k: i for i, (k, _n) in enumerate(periods(db))}
    rows = [dict(r) for r in db.conn.execute(
        "SELECT * FROM bp_readings WHERE day = ? ORDER BY COALESCE(at, '99:99'), id",
        (health.day_key(day),))]
    rows.sort(key=lambda r: order.get(r["period"], len(order)))
    return rows


# ------------------------------------------------------------------ médias


def _mean(rows: list[dict], discard_first: bool) -> dict | None:
    used = rows[1:] if discard_first and len(rows) >= 3 else rows
    if not used:
        return None
    pulses = [r["pulse"] for r in used if r["pulse"] is not None]
    return {"sys": sum(r["sys"] for r in used) / len(used),
            "dia": sum(r["dia"] for r in used) / len(used),
            "pulse": sum(pulses) / len(pulses) if pulses else None,
            "n": len(rows), "used": len(used)}


def summarise(db: Database, rows: list[dict]) -> dict:
    """{"periods": [(chave, média)], "daily": média | None, "n": medições} de um dia."""
    discard = bool(options.get(db, "bp_discard_first"))
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["period"], []).append(r)
    order = [k for k, _ in periods(db)] + [NO_PERIOD]
    per = []
    for k in order + [k for k in by if k not in order]:
        if k in by:
            m = _mean(by[k], discard)
            if m:
                per.append((k, m))
    daily = None
    if per:
        if options.get(db, "bp_daily_mode") == "readings":
            flat = [r for k, _m in per for r in
                    (by[k][1:] if discard and len(by[k]) >= 3 else by[k])]
            daily = _mean(flat, False)
        else:
            pulses = [m["pulse"] for _k, m in per if m["pulse"] is not None]
            daily = {"sys": sum(m["sys"] for _k, m in per) / len(per),
                     "dia": sum(m["dia"] for _k, m in per) / len(per),
                     "pulse": sum(pulses) / len(pulses) if pulses else None,
                     "n": len(rows), "used": sum(m["used"] for _k, m in per)}
    return {"periods": per, "daily": daily, "n": len(rows)}


def day_summary(db: Database, day: date | str) -> dict:
    return summarise(db, readings(db, day))


def sync_daily(db: Database, day: date | str) -> None:
    """Grava a média diária nas métricas do diário (ou tira-a, se o dia ficou sem medições)."""
    health.seed(db)
    d = health.day_key(day)
    ms, md = health.metric_by_key(db, "bp_sys"), health.metric_by_key(db, "bp_dia")
    if not ms or not md:
        return
    daily = day_summary(db, d)["daily"]
    for m, k in ((ms, "sys"), (md, "dia")):
        if daily is None:
            db.conn.execute("DELETE FROM daily_values WHERE day = ? AND metric_id = ?"
                            " AND source = ?", (d, m["id"], SOURCE))
        else:
            db.conn.execute(
                "INSERT INTO daily_values (day, metric_id, num, source, updated_at)"
                " VALUES (?,?,?,?,?) ON CONFLICT(day, metric_id) DO UPDATE SET"
                " num = excluded.num, source = excluded.source, updated_at = excluded.updated_at",
                (d, m["id"], round(daily[k], 1), SOURCE, now_iso()))
    db.conn.commit()


def resync_all(db: Database) -> None:
    """Depois de mudar a forma de calcular (opções): refaz as médias diárias gravadas."""
    ensure(db)
    for (day,) in db.conn.execute("SELECT DISTINCT day FROM bp_readings").fetchall():
        sync_daily(db, day)


def days(db: Database, limit: int | None = None, since: date | str | None = None) -> list[dict]:
    """Os dias com medições, do mais recente para o mais antigo: [{"day", **day_summary}]."""
    ensure(db)
    sql, args = "SELECT * FROM bp_readings", []
    if since is not None:
        sql += " WHERE day >= ?"
        args.append(health.day_key(since))
    sql += " ORDER BY day DESC, COALESCE(at, '99:99'), id"
    by: dict[str, list[dict]] = {}
    for r in db.conn.execute(sql, args):
        by.setdefault(r["day"], []).append(dict(r))
    out = []
    for d in sorted(by, reverse=True):
        s = summarise(db, by[d])
        s["day"] = d
        out.append(s)
        if limit and len(out) >= limit:
            break
    return out


def window_mean(db: Database, n_days: int, today: date | None = None,
                period: str | None = None, offset_days: int = 0) -> dict | None:
    """A média das médias diárias (ou de um período) dos últimos `n_days` dias (a acabar
    `offset_days` dias atrás). {"sys","dia","pulse","days"} ou None."""
    today = (today or date.today()) - timedelta(days=offset_days)
    start = today - timedelta(days=n_days - 1)
    vals = []
    for s in days(db, since=start):
        if s["day"] > today.isoformat():
            continue
        m = s["daily"] if period is None else dict(s["periods"]).get(period)
        if m:
            vals.append(m)
    if not vals:
        return None
    pulses = [m["pulse"] for m in vals if m["pulse"] is not None]
    return {"sys": sum(m["sys"] for m in vals) / len(vals),
            "dia": sum(m["dia"] for m in vals) / len(vals),
            "pulse": sum(pulses) / len(pulses) if pulses else None, "days": len(vals)}


# ------------------------------------------------------------------ leitura

CATEGORIES = ("low", "normal", "high", "crisis")


def classify(db: Database, sys_: float | None, dia: float | None) -> str | None:
    if sys_ is None or dia is None:
        return None
    g = lambda k: float(options.get(db, k))                      # noqa: E731
    if sys_ >= g("bp_crisis_sys") or dia >= g("bp_crisis_dia"):
        return "crisis"
    if sys_ >= g("bp_high_sys") or dia >= g("bp_high_dia"):
        return "high"
    if sys_ < g("bp_low_sys") or dia < g("bp_low_dia"):
        return "low"
    return "normal"


def category_name(cat: str | None) -> str:
    return {"low": tr("baixa", "low"), "normal": tr("normal", "normal"),
            "high": tr("alta", "high"), "crisis": tr("muito alta", "very high")}.get(cat or "",
                                                                                     "—")


def category_tone(cat: str | None) -> str:
    return {"low": "warn", "normal": "good", "high": "warn", "crisis": "bad"}.get(cat or "",
                                                                                 "good")


def fmt(m: dict | None) -> str:
    if not m:
        return "—"
    return f"{m['sys']:.0f}/{m['dia']:.0f}"


def fmt_full(m: dict | None) -> str:
    if not m:
        return "—"
    out = f"{m['sys']:.0f}/{m['dia']:.0f} mmHg"
    if m.get("pulse") is not None:
        out += f" · {m['pulse']:.0f} bpm"
    return out


def series(db: Database, n_days: int = 90, today: date | None = None,
           period: str | None = None) -> list[tuple[date, float, float]]:
    """[(dia, máxima, mínima)] das médias diárias (ou de um período), do mais antigo."""
    today = today or date.today()
    out = []
    for s in days(db, since=today - timedelta(days=n_days - 1)):
        m = s["daily"] if period is None else dict(s["periods"]).get(period)
        if m:
            out.append((date.fromisoformat(s["day"]), m["sys"], m["dia"]))
    out.reverse()
    return out
