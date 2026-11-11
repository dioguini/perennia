"""Saúde: métricas diárias, análises clínicas e importação de dados.

Métricas diárias
    Cada métrica tem um tipo — sim/não, número, escala 1–5, texto, escolha ou
    hora — e cada dia guarda o valor e uma nota. As que vêm de origem
    cobrem sono, energia, peso, FC em repouso, HRV, passos e alimentação
    («comi doces ao almoço?», «comi fora?», o que almocei…). Podes criar
    quantas quiseres. Há também uma nota livre por dia.

Análises clínicas
    Um relatório por data (laboratório, notas, e a caixa para o comentário do
    médico) com os resultados: marcador, valor, unidade e intervalo de
    referência. A estrutura é deliberadamente simples, à espera da tua.

Importação
    CSV do HRV4Training e dados do Garmin (o export da conta: ficheiros JSON
    diários, ou um CSV). As colunas reconhecidas vão para as métricas
    certas; as outras podem criar métricas novas. Cada valor guarda a origem.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from .db import Database, now_iso

KINDS = ("bool", "number", "scale", "text", "choice", "time")
GROUPS = ("sleep", "body", "recovery", "food", "mind", "activity", "other")

# (chave, nome, tipo, unidade, grupo, escolhas)
DEFAULT_METRICS: tuple[tuple, ...] = (
    ("sleep_hours", "Horas de sono", "number", "h", "sleep", None),
    ("sleep_quality", "Qualidade do sono", "scale", "", "sleep", None),
    ("energy", "Energia", "scale", "", "mind", None),
    ("mood", "Humor", "scale", "", "mind", None),
    ("stress", "Stress", "scale", "", "mind", None),
    ("soreness", "Dores musculares", "scale", "", "recovery", None),
    ("training_feel", "Como me senti no treino", "scale", "", "recovery", None),
    ("weight", "Peso", "number", "kg", "body", None),
    ("waist", "Perímetro da cintura", "number", "cm", "body", None),
    ("bp_sys", "Tensão arterial (máxima)", "number", "mmHg", "body", None),
    ("bp_dia", "Tensão arterial (mínima)", "number", "mmHg", "body", None),
    ("rhr", "FC em repouso", "number", "bpm", "recovery", None),
    ("hrv_rmssd", "HRV (rMSSD)", "number", "ms", "recovery", None),
    ("hrv_score", "HRV4Training — prontidão", "number", "", "recovery", None),
    ("steps", "Passos", "number", "", "activity", None),
    ("lunch", "O que almocei", "text", "", "food", None),
    ("dinner", "O que jantei", "text", "", "food", None),
    ("lunch_cooking", "Confeção do almoço", "choice", "", "food",
     ["grelhado", "cozido", "assado", "estufado", "frito", "cru", "vapor", "misto"]),
    ("dinner_cooking", "Confeção do jantar", "choice", "", "food",
     ["grelhado", "cozido", "assado", "estufado", "frito", "cru", "vapor", "misto"]),
    ("sweets_lunch", "Comi doces ao almoço?", "bool", "", "food", None),
    ("sweets_dinner", "Comi doces ao jantar?", "bool", "", "food", None),
    ("ate_out", "Comi fora?", "bool", "", "food", None),
    ("protein", "Proteína no dia", "choice", "", "food", ["pouca", "média", "muita"]),
    ("alcohol", "Bebidas alcoólicas", "number", "", "food", None),
    ("coffee", "Cafés", "number", "", "food", None),
    ("water", "Água", "number", "L", "food", None),
    ("bedtime", "Hora de deitar", "time", "", "sleep", None),
    ("wake_time", "Hora de acordar", "time", "", "sleep", None),
    ("body_temp", "Temperatura corporal", "number", "°C", "body", None),
)

# Nomes de colunas que se reconhecem nos ficheiros importados → chave da métrica.
ALIASES = {
    "hrv_rmssd": ("rmssd", "hrv", "hrv (rmssd)", "hrv_rmssd", "lastnightavg", "weeklyavg_hrv"),
    "rhr": ("hr", "rhr", "resting hr", "resting_hr", "restingheartrate", "heart rate",
            "resting heart rate", "minheartrate_resting"),
    "hrv_score": ("hrv4t_recovery_points", "recovery points", "readiness", "recovery"),
    "sleep_hours": ("sleep", "sleep hours", "sleep_hours", "sleep_time", "sleepduration",
                    "sleeptimeseconds"),
    "sleep_quality": ("sleep quality", "sleep_quality", "sleepquality"),
    "steps": ("steps", "totalsteps", "total steps"),
    "weight": ("weight", "body weight", "peso"),
    "stress": ("stress", "averagestresslevel", "avg stress"),
    "soreness": ("soreness", "muscle soreness"),
    "mood": ("mood",),
    "energy": ("energy", "fatigue"),
}
DATE_COLUMNS = ("date", "calendardate", "day", "data", "local", "timestamp")


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS metric_defs (
      id        INTEGER PRIMARY KEY,
      key       TEXT UNIQUE,
      name      TEXT NOT NULL,
      kind      TEXT NOT NULL,
      unit      TEXT,
      grp       TEXT NOT NULL DEFAULT 'other',
      choices   TEXT,
      active    INTEGER NOT NULL DEFAULT 1,
      sort      INTEGER NOT NULL DEFAULT 0,
      custom    INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS daily_values (
      day        TEXT NOT NULL,
      metric_id  INTEGER NOT NULL REFERENCES metric_defs(id) ON DELETE CASCADE,
      num        REAL,
      txt        TEXT,
      notes      TEXT,
      source     TEXT NOT NULL DEFAULT 'manual',
      updated_at TEXT NOT NULL,
      PRIMARY KEY (day, metric_id)
    ) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS day_notes (
      day   TEXT PRIMARY KEY,
      text  TEXT
    );
    CREATE TABLE IF NOT EXISTS lab_reports (
      id              INTEGER PRIMARY KEY,
      done_on         TEXT NOT NULL,
      lab             TEXT,
      notes           TEXT,
      doctor_feedback TEXT,
      created_at      TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS lab_results (
      id         INTEGER PRIMARY KEY,
      report_id  INTEGER NOT NULL REFERENCES lab_reports(id) ON DELETE CASCADE,
      marker     TEXT NOT NULL,
      value      REAL,
      value_text TEXT,
      unit       TEXT,
      ref_low    REAL,
      ref_high   REAL,
      comment    TEXT,
      sort       INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS ix_lab_results ON lab_results(marker);
    """)


def seed(db: Database) -> None:
    ensure(db)
    if db.get("health_seeded", False):
        return
    for i, (k, n, kind, unit, grp, choices) in enumerate(DEFAULT_METRICS):
        db.conn.execute(
            "INSERT OR IGNORE INTO metric_defs(key, name, kind, unit, grp, choices, sort)"
            " VALUES (?,?,?,?,?,?,?)",
            (k, n, kind, unit, grp, json.dumps(choices) if choices else None, i))
    db.conn.commit()
    db.set("health_seeded", True)


# ------------------------------------------------------------ métricas


def metrics(db: Database, include_inactive: bool = False, group: str | None = None
            ) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM metric_defs WHERE 1=1"
    params: list = []
    if not include_inactive:
        sql += " AND active = 1"
    if group:
        sql += " AND grp = ?"
        params.append(group)
    sql += " ORDER BY sort, id"
    out = []
    for r in db.conn.execute(sql, params):
        d = dict(r)
        d["choices"] = json.loads(d["choices"]) if d.get("choices") else []
        out.append(d)
    return out


def metric(db: Database, metric_id: int) -> dict | None:
    for m in metrics(db, include_inactive=True):
        if m["id"] == metric_id:
            return m
    return None


def metric_by_key(db: Database, key: str) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT id FROM metric_defs WHERE key = ?", (key,)).fetchone()
    return metric(db, r["id"]) if r else None


def save_metric(db: Database, metric_id: int | None, *, name: str, kind: str, unit: str = "",
                group: str = "other", choices: list[str] | None = None,
                key: str | None = None) -> int:
    ensure(db)
    if kind not in KINDS:
        raise ValueError(f"tipo desconhecido: {kind}")
    name = name.strip() or "Métrica"
    ch = json.dumps(choices) if choices else None
    if metric_id is None:
        sort = db.conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM metric_defs"
                               ).fetchone()["s"]
        key = key or _slug(name, db)
        cur = db.conn.execute(
            "INSERT INTO metric_defs(key, name, kind, unit, grp, choices, sort, custom)"
            " VALUES (?,?,?,?,?,?,?,1)", (key, name, kind, unit, group, ch, sort))
        db.conn.commit()
        return int(cur.lastrowid)
    db.conn.execute("UPDATE metric_defs SET name=?, kind=?, unit=?, grp=?, choices=?"
                    " WHERE id = ?", (name, kind, unit, group, ch, metric_id))
    db.conn.commit()
    return metric_id


def _slug(name: str, db: Database) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "metrica"
    key, n = base, 1
    while db.conn.execute("SELECT 1 FROM metric_defs WHERE key = ?", (key,)).fetchone():
        n += 1
        key = f"{base}_{n}"
    return key


def set_active(db: Database, metric_id: int, active: bool) -> None:
    db.conn.execute("UPDATE metric_defs SET active = ? WHERE id = ?", (int(active), metric_id))
    db.conn.commit()


def move_metric(db: Database, metric_id: int, step: int) -> None:
    ms = metrics(db, include_inactive=True)
    ids = [m["id"] for m in ms]
    i = ids.index(metric_id)
    j = max(0, min(len(ids) - 1, i + step))
    ids[i], ids[j] = ids[j], ids[i]
    db.conn.executemany("UPDATE metric_defs SET sort = ? WHERE id = ?",
                        [(k, mid) for k, mid in enumerate(ids)])
    db.conn.commit()


# ------------------------------------------------------- valores do dia


def day_key(d: date | str) -> str:
    return d if isinstance(d, str) else d.isoformat()


def set_value(db: Database, day: date | str, metric_id: int, value: Any = None, *,
              notes: str | None = None, source: str = "manual", keep_notes: bool = True
              ) -> None:
    """Grava o valor (número ou texto, conforme o tipo) e/ou a nota do dia."""
    ensure(db)
    m = metric(db, metric_id)
    if m is None:
        raise ValueError("métrica desconhecida")
    num = txt = None
    if value is not None and value != "":
        if m["kind"] in ("text", "choice", "time"):
            txt = str(value)
        elif m["kind"] == "bool":
            num = 1.0 if value in (True, 1, "1", "sim", "yes", "true", 1.0) else 0.0
        else:
            num = float(value)
    old = db.conn.execute("SELECT notes FROM daily_values WHERE day = ? AND metric_id = ?",
                          (day_key(day), metric_id)).fetchone()
    if notes is None and keep_notes and old is not None:
        notes = old["notes"]
    if num is None and txt is None and not notes:
        db.conn.execute("DELETE FROM daily_values WHERE day = ? AND metric_id = ?",
                        (day_key(day), metric_id))
    else:
        db.conn.execute(
            "INSERT INTO daily_values(day, metric_id, num, txt, notes, source, updated_at)"
            " VALUES (?,?,?,?,?,?,?) ON CONFLICT(day, metric_id) DO UPDATE SET"
            " num=excluded.num, txt=excluded.txt, notes=excluded.notes,"
            " source=excluded.source, updated_at=excluded.updated_at",
            (day_key(day), metric_id, num, txt, notes, source, now_iso()))
    db.conn.commit()


def set_note(db: Database, day: date | str, metric_id: int, notes: str | None) -> None:
    cur = values_for(db, day).get(metric_id)
    set_value(db, day, metric_id, cur["value"] if cur else None, notes=notes or None,
              keep_notes=False, source=cur["source"] if cur else "manual")


def values_for(db: Database, day: date | str) -> dict[int, dict]:
    ensure(db)
    out = {}
    for r in db.conn.execute("SELECT * FROM daily_values WHERE day = ?", (day_key(day),)):
        out[r["metric_id"]] = {"value": r["num"] if r["txt"] is None else r["txt"],
                               "notes": r["notes"], "source": r["source"]}
    return out


def day_note(db: Database, day: date | str) -> str:
    ensure(db)
    r = db.conn.execute("SELECT text FROM day_notes WHERE day = ?", (day_key(day),)).fetchone()
    return (r["text"] or "") if r else ""


def set_day_note(db: Database, day: date | str, text: str) -> None:
    ensure(db)
    db.conn.execute("INSERT INTO day_notes(day, text) VALUES (?,?) ON CONFLICT(day)"
                    " DO UPDATE SET text = excluded.text", (day_key(day), text))
    db.conn.commit()


def series(db: Database, metric_id: int, days: int = 90, today: date | None = None
           ) -> list[tuple[date, float | None]]:
    """(dia, valor) dos últimos `days` dias; None onde não há registo."""
    today = today or date.today()
    start = today - timedelta(days=days - 1)
    vals = {r["day"]: r["num"] for r in db.conn.execute(
        "SELECT day, num FROM daily_values WHERE metric_id = ? AND day >= ?",
        (metric_id, start.isoformat()))}
    return [(start + timedelta(days=i), vals.get((start + timedelta(days=i)).isoformat()))
            for i in range(days)]


def fmt(m: dict, value: Any) -> str:
    if value is None or value == "":
        return "—"
    k = m["kind"]
    if k == "bool":
        return "sim" if float(value) >= 0.5 else "não"
    if k == "scale":
        return f"{float(value):g}/5"
    if k == "number":
        v = float(value)
        txt = f"{v:,.0f}".replace(",", " ") if abs(v) >= 1000 else f"{v:g}"
        return f"{txt} {m['unit']}".strip()
    return str(value)


def completeness(db: Database, day: date | str) -> tuple[int, int]:
    """(preenchidas, ativas) para o dia — o ecrã inicial mostra-o."""
    ms = metrics(db)
    vals = values_for(db, day)
    return sum(1 for m in ms if m["id"] in vals), len(ms)


# ------------------------------------------------------------ análises

COMMON_MARKERS: tuple[tuple[str, str, float | None, float | None], ...] = (
    ("Colesterol total", "mg/dL", None, 190),
    ("Colesterol LDL", "mg/dL", None, 115),
    ("Colesterol HDL", "mg/dL", 40, None),
    ("Triglicéridos", "mg/dL", None, 150),
    ("Apolipoproteína B (ApoB)", "mg/dL", None, None),
    ("Lipoproteína(a)", "nmol/L", None, None),
    ("Glicose em jejum", "mg/dL", 70, 100),
    ("Hemoglobina A1c", "%", None, 5.7),
    ("Insulina em jejum", "µU/mL", None, None),
    ("PCR ultrassensível", "mg/L", None, None),
    ("Vitamina D (25-OH)", "ng/mL", 30, None),
    ("Ferritina", "ng/mL", None, None),
    ("Hemoglobina", "g/dL", None, None),
    ("TSH", "µUI/mL", None, None),
    ("Creatinina", "mg/dL", None, None),
    ("TFG estimada", "mL/min/1,73m²", 90, None),
    ("ALT (TGP)", "U/L", None, None),
    ("AST (TGO)", "U/L", None, None),
    ("GGT", "U/L", None, None),
    ("Ácido úrico", "mg/dL", None, None),
    ("Testosterona total", "ng/dL", None, None),
    ("Vitamina B12", "pg/mL", None, None),
    ("Homocisteína", "µmol/L", None, None),
)


def lab_reports(db: Database) -> list[dict]:
    ensure(db)
    rows = db.conn.execute(
        "SELECT r.*, (SELECT COUNT(*) FROM lab_results x WHERE x.report_id = r.id) AS n,"
        " (SELECT COUNT(*) FROM lab_results x WHERE x.report_id = r.id AND x.value IS NOT NULL"
        "  AND ((x.ref_low IS NOT NULL AND x.value < x.ref_low) OR"
        "       (x.ref_high IS NOT NULL AND x.value > x.ref_high))) AS out_of_range"
        " FROM lab_reports r ORDER BY r.done_on DESC, r.id DESC").fetchall()
    return [dict(r) for r in rows]


def lab_report(db: Database, report_id: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM lab_reports WHERE id = ?", (report_id,)).fetchone()
    return dict(r) if r else None


def save_lab_report(db: Database, report_id: int | None, *, done_on: str, lab: str = "",
                    notes: str = "", doctor_feedback: str = "") -> int:
    ensure(db)
    if report_id is None:
        cur = db.conn.execute(
            "INSERT INTO lab_reports(done_on, lab, notes, doctor_feedback, created_at)"
            " VALUES (?,?,?,?,?)", (done_on, lab, notes, doctor_feedback, now_iso()))
        db.conn.commit()
        return int(cur.lastrowid)
    db.conn.execute("UPDATE lab_reports SET done_on=?, lab=?, notes=?, doctor_feedback=?"
                    " WHERE id = ?", (done_on, lab, notes, doctor_feedback, report_id))
    db.conn.commit()
    return report_id


def delete_lab_report(db: Database, report_id: int) -> None:
    db.conn.execute("DELETE FROM lab_reports WHERE id = ?", (report_id,))
    db.conn.commit()


def lab_results(db: Database, report_id: int) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM lab_results WHERE report_id = ? ORDER BY sort, id", (report_id,))]


def save_lab_result(db: Database, result_id: int | None, report_id: int, *, marker: str,
                    value: float | None = None, unit: str = "", ref_low: float | None = None,
                    ref_high: float | None = None, comment: str = "",
                    value_text: str | None = None) -> int:
    ensure(db)
    if result_id is None:
        sort = db.conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM lab_results"
                               " WHERE report_id = ?", (report_id,)).fetchone()["s"]
        cur = db.conn.execute(
            "INSERT INTO lab_results(report_id, marker, value, value_text, unit, ref_low,"
            " ref_high, comment, sort) VALUES (?,?,?,?,?,?,?,?,?)",
            (report_id, marker, value, value_text, unit, ref_low, ref_high, comment, sort))
        db.conn.commit()
        return int(cur.lastrowid)
    db.conn.execute(
        "UPDATE lab_results SET marker=?, value=?, value_text=?, unit=?, ref_low=?, ref_high=?,"
        " comment=? WHERE id = ?",
        (marker, value, value_text, unit, ref_low, ref_high, comment, result_id))
    db.conn.commit()
    return result_id


def delete_lab_result(db: Database, result_id: int) -> None:
    db.conn.execute("DELETE FROM lab_results WHERE id = ?", (result_id,))
    db.conn.commit()


def flag(r: dict) -> str:
    """«baixo», «alto» ou "" (dentro, ou sem referência)."""
    v = r.get("value")
    if v is None:
        return ""
    if r.get("ref_low") is not None and v < r["ref_low"]:
        return "low"
    if r.get("ref_high") is not None and v > r["ref_high"]:
        return "high"
    return ""


def marker_history(db: Database, marker: str) -> list[dict]:
    """O mesmo marcador em todas as análises, por data."""
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT x.*, r.done_on FROM lab_results x JOIN lab_reports r ON r.id = x.report_id"
        " WHERE x.marker = ? ORDER BY r.done_on", (marker,))]


def markers_seen(db: Database) -> list[str]:
    ensure(db)
    return [r["marker"] for r in db.conn.execute(
        "SELECT marker, COUNT(*) AS n FROM lab_results GROUP BY marker ORDER BY n DESC, marker")]


# ------------------------------------------------------------ importação


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _parse_day(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10,13}", s):                     # epoch (s ou ms)
        n = int(s)
        if n > 10 ** 11:
            n //= 1000
        return datetime.utcfromtimestamp(n).date().isoformat()
    for cand in (s, s[:19], s[:10]):
        for fmt_ in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(cand, fmt_).date().isoformat()
            except ValueError:
                continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def match_column(header: str) -> str | None:
    """A métrica a que uma coluna corresponde, ou None."""
    n = _norm(header)
    for key, names in ALIASES.items():
        if n in names or n.replace(" ", "_") in names or n.replace(" ", "") in names:
            return key
    return None


def _import_rows(db: Database, rows: Iterable[dict], source: str, create_unknown: bool,
                 scale: dict[str, float] | None = None) -> dict:
    """Linhas {coluna: valor} com uma coluna de data → valores diários."""
    seed(db)
    report = {"days": set(), "values": 0, "created": [], "ignored": set()}
    cache: dict[str, int | None] = {}
    for row in rows:
        day = None
        for col, v in row.items():
            if _norm(col) in DATE_COLUMNS:
                day = _parse_day(v)
                if day:
                    break
        if not day:
            continue
        for col, raw in row.items():
            if _norm(col) in DATE_COLUMNS:
                continue
            num = _number(raw)
            if num is None:
                continue
            if col not in cache:
                key = match_column(col)
                m = metric_by_key(db, key) if key else None
                if m is None and create_unknown:
                    mid = save_metric(db, None, name=f"{col} ({source})", kind="number",
                                      group="other")
                    report["created"].append(col)
                    cache[col] = mid
                else:
                    cache[col] = m["id"] if m else None
                    if m is None:
                        report["ignored"].add(col)
            mid = cache[col]
            if mid is None:
                continue
            key = metric(db, mid)["key"]
            if scale and key in scale:
                num = num * scale[key]
            set_value(db, day, mid, num, source=source)
            report["days"].add(day)
            report["values"] += 1
    report["days"] = len(report["days"])
    report["ignored"] = sorted(report["ignored"])
    return report


def import_csv(db: Database, path: str | Path, source: str = "csv",
               create_unknown: bool = False) -> dict:
    """CSV com uma coluna de data e uma coluna por métrica (HRV4Training,
    Garmin Connect, folhas de cálculo…). Separador `,` ou `;`."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    return _import_rows(db, rows, source, create_unknown)


def import_hrv4training(db: Database, path: str | Path, create_unknown: bool = False) -> dict:
    """Export do HRV4Training (CSV). Reconhece data, rMSSD, FC, pontos de
    recuperação e as perguntas diárias que tiverem nome conhecido."""
    return import_csv(db, path, source="hrv4training", create_unknown=create_unknown)


GARMIN_KEYS = {
    "totalSteps": "steps", "restingHeartRate": "rhr", "averageStressLevel": "stress",
    "sleepTimeSeconds": "sleep_hours", "lastNightAvg": "hrv_rmssd",
}
GARMIN_SCALE = {"sleep_hours": 1 / 3600.0}


def import_garmin_json(db: Database, path: str | Path, create_unknown: bool = False) -> dict:
    """Ficheiros JSON do export da conta Garmin (resumos diários com
    `calendarDate`). Os campos conhecidos vão para as métricas certas."""
    data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    items = data if isinstance(data, list) else data.get("items") or data.get("data") or [data]
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        day = it.get("calendarDate") or it.get("date")
        if isinstance(day, dict):
            day = day.get("date")
        row = {"date": day}
        for k, v in it.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                row[GARMIN_KEYS.get(k, k)] = v
            elif isinstance(v, dict):               # p. ex. hrvSummary: {lastNightAvg: …}
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)) and k2 in GARMIN_KEYS:
                        row[GARMIN_KEYS[k2]] = v2
        rows.append(row)
    return _import_rows(db, _keyed(rows), "garmin", create_unknown, scale=GARMIN_SCALE)


DEFAULT_KEYS = {m[0] for m in DEFAULT_METRICS}


def _keyed(rows: list[dict]) -> list[dict]:
    """As chaves que já são métricas conhecidas passam a nome de coluna que o
    `match_column` reconhece."""
    out = []
    for r in rows:
        out.append({(ALIASES[k][0] if k in ALIASES else k): v for k, v in r.items()})
    return out


def import_file(db: Database, path: str | Path, kind: str = "auto",
                create_unknown: bool = False) -> dict:
    p = Path(path)
    from . import importers
    if kind in ("auto", "hrv4training") and p.suffix.lower() == ".csv" \
            and importers.looks_like_hrv4training(p):
        return importers.import_hrv4training(db, p, create_unknown=create_unknown)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        from . import labs
        return labs.import_xlsx(db, p)
    if kind == "auto":
        kind = "garmin_json" if p.suffix.lower() == ".json" else (
            "hrv4training" if "hrv" in p.name.lower() or "measurement" in p.name.lower()
            else "csv")
    if kind == "garmin_json":
        return import_garmin_json(db, p, create_unknown)
    if kind == "hrv4training":
        return import_hrv4training(db, p, create_unknown)
    return import_csv(db, p, "garmin" if "garmin" in p.name.lower() else "csv", create_unknown)
