"""Atividades do TrainingPeaks a partir do .csv de exportação (Calendário →
Exportar → «workouts»). Não é a fonte principal: serve para trazer o
histórico — com a TSS que o TrainingPeaks calculou — para o histórico e para
a forma/fadiga da Perennia.

Colunas usadas (as do TrainingPeaks): Title, WorkoutType, WorkoutDay,
TimeTotalInHours, DistanceInMeters, HeartRateAverage, HeartRateMax,
PowerAverage, Energy, IF, TSS. As linhas sem tempo feito (só planeadas)
ficam de fora. Importar duas vezes o mesmo ficheiro não duplica.

Ronda 37 — o que vem escrito também entra:
* WorkoutDescription (a descrição do treino) e CoachComments (os comentários do
  treinador) ficam na atividade (vêem-se na ficha);
* AthleteComments / PostActivityComments (o comentário depois do treino), Rpe
  (1–10) e Feeling (0–10 → 1–5) entram no feedback da sessão;
* HRZone1..10Minutes e PWRZone1..10Minutes dão o tempo em cada zona (para o
  índice de longevidade).
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


def _text(row: dict, *names: str) -> str:
    for n in names:
        v = (row.get(n) or "").strip()
        if v:
            return v
    return ""


def _zones(row: dict, prefix: str, n: int) -> list[float] | None:
    """Os minutos em cada zona do TrainingPeaks («HRZone1Minutes»…) em segundos, juntando as
    zonas a mais na última (a Perennia tem `n`)."""
    vals = [_num(row.get(f"{prefix}{i}Minutes")) or 0.0 for i in range(1, 11)]
    if not any(vals):
        return None
    out = vals[:n]
    out[-1] += sum(vals[n:])
    return [round(v * 60.0) for v in out]


def _feel(v) -> int | None:
    f = _num(v)
    if f is None:
        return None
    return max(1, min(5, int(round(f / 2.0)))) if f > 5 else max(1, min(5, int(round(f))))


def import_csv(db: Database, path: str | Path) -> dict:
    from . import garmin_sync as gs
    gs.ensure(db)
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows or "WorkoutDay" not in rows[0]:
        raise ValueError("não é um .csv de atividades do TrainingPeaks (falta WorkoutDay)")
    n = skipped = 0
    feedback_in: dict[str, dict] = {}
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
        db.conn.execute("UPDATE synced_activities SET description = ?, coach_comments = ?,"
                        " athlete_comments = ?, tss_source = ? WHERE id = ?",
                        (_text(row, "WorkoutDescription") or None,
                         _text(row, "CoachComments") or None,
                         _text(row, "AthleteComments", "PostActivityComments",
                               "Comments") or None,
                         "trainingpeaks" if _num(row.get("TSS")) else None, uid))
        gs.set_zones(db, uid, _zones(row, "HRZone", 5), _zones(row, "PWRZone", 7),
                     "trainingpeaks" if _num(row.get("TSS")) else None)
        rpe = _num(row.get("Rpe") or row.get("RPE"))
        fb = {"rpe": int(round(rpe)) if rpe else None, "feel": _feel(row.get("Feeling")),
              "comment": _text(row, "AthleteComments", "PostActivityComments", "Comments")}
        if any(fb.values()):
            feedback_in[uid] = fb
        n += 1
    db.conn.commit()
    # o comentário do pós-treino, o RPE e a sensação entram no feedback; e todas as atividades
    # novas ficam analisadas (ronda 37)
    from . import feedback as fbm
    for uid, fb in feedback_in.items():
        fbm.auto_analyse(db, "imported", uid, impact=False,
                         **{k: v for k, v in fb.items() if v not in (None, "")})
    analysed = fbm.analyse_imported(db)
    return {"activities": n, "skipped": skipped, "feedback": len(feedback_in),
            "analysed": analysed + len(feedback_in)}
