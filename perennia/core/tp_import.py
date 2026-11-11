"""Atividades do TrainingPeaks a partir do .csv de exportação (Calendário →
Exportar → «workouts»). Não é a fonte principal: serve para trazer o
histórico — com a TSS que o TrainingPeaks calculou — para o histórico e para
a forma/fadiga da Perennia.

Colunas usadas (as do TrainingPeaks): Title, WorkoutType, WorkoutDay,
TimeTotalInHours, DistanceInMeters, HeartRateAverage, HeartRateMax,
PowerAverage, Energy, IF, TSS. As linhas sem tempo feito (só planeadas)
ficam de fora. Importar duas vezes o mesmo ficheiro não duplica.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path

from .db import Database, now_iso

SPORTS = {"bike": "cycling", "mtb": "cycling", "cycling": "cycling", "ride": "cycling",
          "run": "running", "running": "running", "walk": "running",
          "swim": "swimming", "swimming": "swimming",
          "rowing": "rowing", "row": "rowing",
          "strength": "gym", "crosstrain": "gym", "x-train": "gym"}


def _num(v) -> float | None:
    try:
        s = str(v).strip().replace(",", ".")
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def looks_like_tp(path: str | Path) -> bool:
    try:
        head = Path(path).read_text(encoding="utf-8-sig", errors="replace")[:600]
    except OSError:
        return False
    return "WorkoutType" in head and "WorkoutDay" in head


def import_csv(db: Database, path: str | Path) -> dict:
    from . import garmin_sync as gs
    gs.ensure(db)
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows or "WorkoutDay" not in rows[0]:
        raise ValueError("não é um .csv de atividades do TrainingPeaks (falta WorkoutDay)")
    n = skipped = 0
    for row in rows:
        hours = _num(row.get("TimeTotalInHours"))
        day = (row.get("WorkoutDay") or "").strip()[:10]
        if not hours or not day:
            skipped += 1                          # só planeado
            continue
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            skipped += 1
            continue
        title = (row.get("Title") or "").strip() or (row.get("WorkoutType") or "TrainingPeaks")
        kind = (row.get("WorkoutType") or "").strip()
        sport = SPORTS.get(kind.lower(), "other")
        uid = "tp:" + hashlib.sha1(f"{day}|{title}|{hours}|{kind}".encode()).hexdigest()[:16]
        energy = _num(row.get("Energy"))
        db.conn.execute(
            "INSERT OR REPLACE INTO synced_activities(id, source, sport, source_sport, name,"
            " started_at, elapsed_s, moving_s, distance_m, ascent_m, avg_hr, max_hr, calories,"
            " training_load, imported_at, tss, if_value, avg_power_w, np_w)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, "trainingpeaks", sport, kind, title, f"{day}T12:00:00", hours * 3600,
             hours * 3600, _num(row.get("DistanceInMeters")), None,
             _num(row.get("HeartRateAverage")), _num(row.get("HeartRateMax")),
             energy * 0.239 if energy else None, _num(row.get("TSS")), now_iso(),
             _num(row.get("TSS")), _num(row.get("IF")), _num(row.get("PowerAverage")), None))
        n += 1
    db.conn.commit()
    return {"activities": n, "skipped": skipped}
