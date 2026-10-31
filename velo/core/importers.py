"""Importadores dedicados: HRV4Training (CSV) e GarminDB (SQLite).

HRV4Training
    O CSV tem ~70 colunas, nomes com espaços à frente, e as datas em
    ano-DIA-mês («2026-20-06»). A ordem de dia e mês descobre-se pelo ficheiro
    todo. Cada coluna conhecida vai para uma métrica: FC da manhã, rMSSD,
    SDNN, AVNN, pNN50, LF, HF, pontos de recuperação, sono (duração, hora de
    deitar e de acordar), energia mental, dores, fadiga, estilo de vida,
    viagem, doença, álcool, o treino que registaste, as tuas etiquetas
    personalizadas (nome numa coluna, valor noutra — «Weight (kg)» vai para o
    Peso) e a nota («BodyTemperature:35.6;» → temperatura corporal).

GarminDB  (https://github.com/tcgoetz/GarminDB)
    O GarminDB descarrega os teus dados do Garmin Connect para bases SQLite
    em ~/HealthData/DBs. A Perennia lê a `garmin.db` (resumo diário, sono,
    FC em repouso, HRV, peso). Também pode correr o GarminDB por ti, se
    estiver instalado. Não guardamos a tua palavra-passe do Garmin: essa fica
    na configuração do próprio GarminDB.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import sqlite3
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import health
from .db import Database

# ------------------------------------------------------------- HRV4Training

# coluna → (chave, nome, tipo, unidade, grupo). As chaves de origem (rhr,
# hrv_rmssd…) reaproveitam as métricas que já existem.
H4T_COLUMNS: dict[str, tuple] = {
    "HR": ("rhr", None, None, None, None),
    "rMSSD": ("hrv_rmssd", None, None, None, None),
    "HRV4T_Recovery_Points": ("hrv_score", None, None, None, None),
    "AVNN": ("h4t_avnn", "AVNN (HRV4T)", "number", "ms", "recovery"),
    "SDNN": ("h4t_sdnn", "SDNN (HRV4T)", "number", "ms", "recovery"),
    "pNN50": ("h4t_pnn50", "pNN50 (HRV4T)", "number", "%", "recovery"),
    "LF": ("h4t_lf", "LF (HRV4T)", "number", "", "recovery"),
    "HF": ("h4t_hf", "HF (HRV4T)", "number", "", "recovery"),
    "sleep_quality": ("h4t_sleep_quality", "Qualidade do sono (HRV4T, 1–10)", "number", "",
                      "sleep"),
    "sleep_time": ("sleep_hours", None, None, None, None),
    "sleep_tobed": ("bedtime", None, None, None, None),
    "sleep_awake": ("wake_time", "Hora de acordar", "time", "", "sleep"),
    "mental_energy": ("h4t_mental_energy", "Energia mental (HRV4T, 0–10)", "number", "",
                      "mind"),
    "muscle_soreness": ("h4t_soreness", "Dores musculares (HRV4T)", "number", "",
                        "recovery"),
    "fatigue": ("h4t_fatigue", "Fadiga (HRV4T)", "number", "", "recovery"),
    "lifestyle": ("h4t_lifestyle", "Estilo de vida (HRV4T)", "number", "", "mind"),
    "physical_condition": ("h4t_condition", "Condição física (HRV4T)", "number", "",
                           "recovery"),
    "traveling": ("h4t_traveling", "Em viagem", "bool", "", "other"),
    "sickness": ("h4t_sick", "Doente", "bool", "", "other"),
    "alcohol": ("h4t_alcohol", "Álcool (HRV4T)", "text", "", "food"),
    "training": ("h4t_training", "Treino (HRV4T)", "text", "", "activity"),
    "training_type": ("h4t_training_type", "Tipo de treino (HRV4T)", "text", "", "activity"),
    "training_performance": ("h4t_training_perf", "Desempenho no treino (HRV4T)", "number",
                             "", "activity"),
    "trainingRPE": ("h4t_rpe", "RPE do treino (HRV4T)", "number", "", "activity"),
    "trainingTSS": ("h4t_tss", "TSS (HRV4T)", "number", "", "activity"),
    "trainingMotivation": ("h4t_motivation", "Motivação para treinar (HRV4T)", "number", "",
                           "mind"),
    "trainingTime": ("h4t_training_time", "Tempo de treino (HRV4T)", "number", "min",
                     "activity"),
    "signal_quality": ("h4t_signal", "Qualidade do sinal (HRV4T)", "text", "", "recovery"),
    "vo2max": ("h4t_vo2max", "VO2máx (HRV4T)", "number", "ml/kg/min", "activity"),
    "daily_message": ("h4t_message", "Mensagem do HRV4Training", "text", "", "recovery"),
    "time": ("h4t_time", "Hora da medição (HRV4T)", "time", "", "recovery"),
}
# etiquetas personalizadas com nome conhecido
TAG_TO_KEY = {"weight (kg)": "weight", "weight": "weight", "peso": "weight",
              "peso (kg)": "weight"}
NOTE_KEYS = {"bodytemperature": ("body_temp", "Temperatura corporal", "number", "°C", "body")}
YES = {"traveling", "sick", "yes", "sim", "true", "1"}
NO = {"not traveling", "not sick", "no", "não", "false", "0"}


def _date_order(values: list[str]) -> str:
    """'ydm' ou 'ymd': se algum «mês» passa de 12, é ano-dia-mês."""
    ydm = ymd = False
    for v in values:
        parts = re.findall(r"\d+", v or "")
        if len(parts) >= 3:
            a, b = int(parts[1]), int(parts[2])
            if a > 12:
                ydm = True
            if b > 12:
                ymd = True
    return "ydm" if ydm and not ymd else "ymd"


def _fix_day(v: str, order: str) -> str | None:
    parts = re.findall(r"\d+", v or "")
    if len(parts) < 3:
        return None
    y, a, b = parts[0], int(parts[1]), int(parts[2])
    if len(y) == 3:                         # «026-20-06»: o HRV4Training comeu o «2»
        y = "2" + y
    if len(y) != 4:
        return None
    day, month = (a, b) if order == "ydm" else (b, a)
    try:
        return date(int(y), month, day).isoformat()
    except ValueError:
        return None


def _hours(v: str) -> float | None:
    m = re.match(r"^\s*(\d+):(\d{2})", v or "")
    if not m:
        return health._number(v)
    return round(int(m.group(1)) + int(m.group(2)) / 60.0, 2)


def _metric_id(db: Database, spec: tuple, cache: dict) -> int | None:
    key = spec[0]
    if key in cache:
        return cache[key]
    m = health.metric_by_key(db, key)
    if m is None:
        if key == "wake_time" or spec[1]:
            mid = health.save_metric(db, None, name=spec[1] or key, kind=spec[2] or "number",
                                     unit=spec[3] or "", group=spec[4] or "other", key=key)
        else:
            mid = None
    else:
        mid = m["id"]
    cache[key] = mid
    return mid


def import_hrv4training(db: Database, path: str | Path, create_unknown: bool = False) -> dict:
    health.seed(db)
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {"days": 0, "values": 0, "created": [], "ignored": [], "skipped_rows": 0}
    header = [h.strip() for h in rows[0]]
    idx = {h: i for i, h in enumerate(header)}
    order = _date_order([r[idx["date"]] for r in rows[1:] if len(r) > idx.get("date", 0)])
    cache: dict = {}
    before = {m["key"] for m in health.metrics(db, include_inactive=True)}
    report = {"days": set(), "values": 0, "skipped_rows": 0, "date_order": order}
    handled = set(H4T_COLUMNS) | {"date", "local", "note"} | {
        f"custom_tag_{n}_{k}" for n in (1, 2, 3) for k in ("name", "value")}
    unused: dict[str, None] = {}
    for r in rows[1:]:
        if not r or len(r) <= idx.get("date", 0):
            continue
        row = {h: (r[i].strip() if i < len(r) else "") for h, i in idx.items()}
        day = _fix_day(row.get("date", ""), order) or _fix_day(row.get("local", ""), order)
        if day is None:
            report["skipped_rows"] += 1
            continue
        for h, v in row.items():
            if v and h and h not in handled:
                if create_unknown and health._number(v) is not None:
                    key = re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")
                    put_spec = (key, h, "number", "", "other")
                    mid = _metric_id(db, put_spec, cache)
                    if mid is not None:
                        health.set_value(db, day, mid, health._number(v),
                                         source="hrv4training")
                        report["values"] += 1
                    continue
                unused.setdefault(h)

        def put(spec: tuple, value: Any) -> None:
            mid = _metric_id(db, spec, cache)
            if mid is None or value in (None, ""):
                return
            health.set_value(db, day, mid, value, source="hrv4training")
            report["days"].add(day)
            report["values"] += 1

        for col, spec in H4T_COLUMNS.items():
            raw = row.get(col, "")
            if raw == "":
                continue
            kind = spec[2] or (health.metric_by_key(db, spec[0]) or {}).get("kind", "number")
            if col == "sleep_time":
                put(spec, _hours(raw))
            elif kind == "time":
                put(spec, raw[:5])
            elif kind == "bool":
                low = raw.lower()
                put(spec, 1.0 if low in YES else 0.0 if low in NO else None)
            elif kind == "text":
                put(spec, raw)
            else:
                v = health._number(raw)
                if v is not None and col == "trainingTime":
                    v = v / 60.0                       # vem em segundos
                put(spec, None if v is None else round(v, 2))
        # etiquetas personalizadas: nome numa coluna, valor noutra
        for n in (1, 2, 3):
            name = row.get(f"custom_tag_{n}_name", "")
            value = health._number(row.get(f"custom_tag_{n}_value", ""))
            if not name or value is None:
                continue
            key = TAG_TO_KEY.get(name.lower())
            spec = (key, None, None, None, None) if key else (
                "h4t_tag_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
                f"{name} (HRV4T)", "number", "", "mind")
            put(spec, value)
        # nota «Chave:valor;»
        note = row.get("note", "")
        for k, v in re.findall(r"([A-Za-z_]+)\s*[:=]\s*([-\d.,]+)", note):
            spec = NOTE_KEYS.get(k.lower())
            if spec:
                put(spec, health._number(v))
    after = {m["key"] for m in health.metrics(db, include_inactive=True)}
    report["created"] = sorted(after - before)
    report["days"] = len(report["days"])
    report["ignored"] = list(unused)
    return report


def looks_like_hrv4training(path: str | Path) -> bool:
    try:
        head = Path(path).read_text(encoding="utf-8-sig", errors="replace")[:600]
    except OSError:
        return False
    return "HRV4T_Recovery_Points" in head or ("rMSSD" in head and "AVNN" in head)


# ------------------------------------------------------------------ GarminDB

GARMINDB_DEFAULT = Path.home() / "HealthData" / "DBs"
GARMIN_METRICS = {
    # (tabela, coluna) → (chave, nome, tipo, unidade, grupo, conversão)
    ("daily_summary", "steps"): ("steps", None, None, None, None, None),
    ("daily_summary", "rhr"): ("rhr", None, None, None, None, None),
    ("daily_summary", "hr_min"): ("g_hr_min", "FC mínima (Garmin)", "number", "bpm",
                                  "recovery", None),
    ("daily_summary", "hr_max"): ("g_hr_max", "FC máxima do dia (Garmin)", "number", "bpm",
                                  "activity", None),
    ("daily_summary", "stress_avg"): ("g_stress", "Stress médio (Garmin, 0–100)", "number", "",
                                      "mind", None),
    ("daily_summary", "bb_max"): ("g_bb_max", "Body Battery máxima", "number", "", "recovery",
                                  None),
    ("daily_summary", "bb_min"): ("g_bb_min", "Body Battery mínima", "number", "", "recovery",
                                  None),
    ("daily_summary", "bb_charged"): ("g_bb_charged", "Body Battery carregada", "number", "",
                                      "recovery", None),
    ("daily_summary", "spo2_avg"): ("g_spo2", "SpO2 média (Garmin)", "number", "%", "recovery",
                                    None),
    ("daily_summary", "rr_waking_avg"): ("g_rr", "Respiração acordado (Garmin)", "number",
                                         "rpm", "recovery", None),
    ("daily_summary", "calories_active"): ("g_kcal_active", "Calorias ativas (Garmin)",
                                           "number", "kcal", "activity", None),
    ("daily_summary", "distance"): ("g_distance", "Distância do dia (Garmin)", "number", "km",
                                    "activity", None),
    ("daily_summary", "floors_up"): ("g_floors", "Andares subidos (Garmin)", "number", "",
                                     "activity", None),
    ("daily_summary", "moderate_activity_time"): ("g_int_mod", "Minutos moderados (Garmin)",
                                                  "number", "min", "activity", "minutes"),
    ("daily_summary", "vigorous_activity_time"): ("g_int_vig", "Minutos vigorosos (Garmin)",
                                                  "number", "min", "activity", "minutes"),
    ("sleep", "total_sleep"): ("sleep_hours", None, None, None, None, "hours"),
    ("sleep", "deep_sleep"): ("g_sleep_deep", "Sono profundo (Garmin)", "number", "h",
                              "sleep", "hours"),
    ("sleep", "light_sleep"): ("g_sleep_light", "Sono leve (Garmin)", "number", "h", "sleep",
                               "hours"),
    ("sleep", "rem_sleep"): ("g_sleep_rem", "Sono REM (Garmin)", "number", "h", "sleep",
                             "hours"),
    ("sleep", "awake"): ("g_sleep_awake", "Acordado durante a noite (Garmin)", "number", "h",
                         "sleep", "hours"),
    ("sleep", "score"): ("g_sleep_score", "Pontuação do sono (Garmin)", "number", "", "sleep",
                         None),
    ("sleep", "avg_stress"): ("g_sleep_stress", "Stress no sono (Garmin)", "number", "",
                              "sleep", None),
    ("resting_hr", "resting_heart_rate"): ("rhr", None, None, None, None, None),
    ("hrv", "last_night_avg"): ("g_hrv", "HRV da noite (Garmin)", "number", "ms", "recovery",
                                None),
    ("hrv", "weekly_avg"): ("g_hrv_week", "HRV média semanal (Garmin)", "number", "ms",
                            "recovery", None),
    ("hrv", "status"): ("g_hrv_status", "Estado da HRV (Garmin)", "text", "", "recovery", None),
    ("weight", "weight"): ("weight", None, None, None, None, None),
}


def garmindb_dir(db: Database) -> Path:
    return Path(os.path.expanduser(db.get("garmindb_dir", str(GARMINDB_DEFAULT))))


def garmindb_status(db: Database) -> dict:
    d = garmindb_dir(db)
    g = d / "garmin.db"
    return {"dir": str(d), "found": g.exists(), "cli": garmindb_cli() is not None,
            "last_import": db.get("garmindb_last_import")}


def garmindb_cli() -> str | None:
    return shutil.which("garmindb_cli.py") or shutil.which("garmindb_cli")


def run_garmindb(timeout: float = 1800.0, runner: Callable | None = None) -> tuple[bool, str]:
    """Corre o GarminDB para trazer o mais recente (precisa de estar instalado
    e configurado em ~/.GarminDb/GarminConnectConfig.json)."""
    cli = garmindb_cli()
    if cli is None:
        return False, "GarminDB não encontrado (pip install garmindb)"
    cmd = [cli, "--all", "--download", "--import", "--analyze", "--latest"]
    run = runner or subprocess.run
    try:
        res = run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return False, str(e)
    out = (getattr(res, "stdout", "") or "")[-400:] + (getattr(res, "stderr", "") or "")[-400:]
    return getattr(res, "returncode", 1) == 0, out.strip()


def _value(raw: Any, conv: str | None) -> Any:
    if raw is None or raw == "":
        return None
    if conv in ("hours", "minutes"):
        m = re.match(r"(\d+):(\d+):(\d+)", str(raw))
        if not m:
            return None
        h = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3)) / 3600
        return round(h if conv == "hours" else h * 60, 2) or None
    return raw


def import_garmindb(db: Database, folder: str | Path | None = None,
                    since: str | None = None) -> dict:
    """Lê a `garmin.db` do GarminDB e grava os valores diários."""
    health.seed(db)
    folder = Path(folder) if folder else garmindb_dir(db)
    path = folder / "garmin.db"
    if not path.exists():
        raise FileNotFoundError(f"não encontrei {path}")
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cache: dict = {}
    before = {m["key"] for m in health.metrics(db, include_inactive=True)}
    report = {"days": set(), "values": 0, "tables": []}
    for table in ("daily_summary", "sleep", "resting_hr", "hrv", "weight"):
        if table not in tables:
            continue
        cols = {r[1] for r in src.execute(f"PRAGMA table_info({table})")}
        wanted = [(c, spec) for (t, c), spec in GARMIN_METRICS.items() if t == table and c in cols]
        if not wanted or "day" not in cols:
            continue
        report["tables"].append(table)
        sql = f"SELECT day, {', '.join(c for c, _ in wanted)} FROM {table}"
        params: list = []
        if since:
            sql += " WHERE day >= ?"
            params.append(since)
        for row in src.execute(sql, params):
            day = str(row["day"])[:10]
            for c, spec in wanted:
                v = _value(row[c], spec[5])
                if v is None or (isinstance(v, (int, float)) and v == 0 and c not in ("awake",)):
                    continue
                mid = _metric_id(db, spec[:5], cache)
                if mid is None:
                    continue
                health.set_value(db, day, mid, v, source="garmin")
                report["days"].add(day)
                report["values"] += 1
    src.close()
    after = {m["key"] for m in health.metrics(db, include_inactive=True)}
    report["created"] = sorted(after - before)
    report["days"] = len(report["days"])
    from .db import now_iso
    db.set("garmindb_last_import", now_iso()[:16].replace("T", " "))
    return report
