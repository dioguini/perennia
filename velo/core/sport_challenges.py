"""Desafios de todos os desportos: objetivo acumulado (distância, subida,
tempo ou sessões) e, se quiseres, uma data limite.

No ciclismo o progresso soma-se ao vivo, durante a sessão (`ride.py`). Nos
outros desportos conta-se a partir do histórico: as sessões concluídas desde
que a tentativa começou e até à data limite. Assim não é preciso mexer em
cada motor de sessão, e apagar uma sessão também a tira do desafio.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from .i18n import tr

SPORTS = ("cycling", "rowing", "running", "swimming", "gym")

# que objetivos fazem sentido em cada desporto
METRICS = {
    "cycling": ("distance_m", "ascent_m", "time_s"),
    "rowing": ("distance_m", "time_s", "sessions"),
    "running": ("distance_m", "time_s", "sessions"),
    "swimming": ("distance_m", "time_s", "sessions"),
    "gym": ("time_s", "sessions"),
}


def metric_name(metric: str) -> str:
    return {"distance_m": tr("Distância", "Distance"), "ascent_m": tr("Subida", "Climbing"),
            "time_s": tr("Tempo de treino", "Training time"),
            "sessions": tr("Sessões", "Sessions")}.get(metric, metric)


# ------------------------------------------------------------ data limite


def _get(row, key: str):
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def deadline_of(ch) -> date | None:
    d = _get(ch, "deadline")
    if not d:
        return None
    try:
        return date.fromisoformat(str(d)[:10])
    except ValueError:
        return None


def deadline_end(d: date) -> datetime:
    """A data limite conta até ao fim desse dia (hora local)."""
    return datetime(d.year, d.month, d.day, 23, 59, 59)


def expired(ch, now: datetime | None = None) -> bool:
    d = deadline_of(ch)
    return d is not None and (now or datetime.now()) > deadline_end(d)


def remaining_text(ch, now: datetime | None = None) -> str:
    """«faltam 12 dias e 4 h» · «termina hoje» · «terminou a 31/10» · ""."""
    d = deadline_of(ch)
    if d is None:
        return ""
    now = now or datetime.now()
    end = deadline_end(d)
    left = (end - now).total_seconds()
    if left <= 0:
        return tr("terminou a {d}", "ended on {d}", d=d.strftime("%d/%m/%Y"))
    days, rest = divmod(int(left), 86400)
    hours = rest // 3600
    if days >= 1:
        if hours:
            return tr("faltam {d} dias e {h} h", "{d} days and {h} h left", d=days, h=hours) \
                if days > 1 else tr("falta 1 dia e {h} h", "1 day and {h} h left", h=hours)
        return tr("faltam {d} dias", "{d} days left", d=days) if days > 1 else \
            tr("falta 1 dia", "1 day left")
    minutes = (rest % 3600) // 60
    return tr("termina hoje · faltam {h} h {m} min", "ends today · {h} h {m} min left",
              h=hours, m=minutes)


# ----------------------------------------------------------- progresso


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    s = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is not None:            # para a hora local, sem fuso
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def sessions_of(db, sport: str) -> list[dict]:
    """Sessões concluídas do desporto: [{id, at (fim), distance_m, seconds}]."""
    queries = {
        "rowing": "SELECT id, COALESCE(ended_at, started_at) AS at, distance_m,"
                  " COALESCE(moving_s, elapsed_s) AS secs FROM row_sessions"
                  " WHERE status='completed'",
        "running": "SELECT id, COALESCE(ended_at, started_at) AS at, distance_m,"
                   " COALESCE(moving_s, elapsed_s) AS secs FROM endurance_sessions"
                   " WHERE status='completed' AND sport='running'",
        "swimming": "SELECT id, COALESCE(ended_at, started_at) AS at, distance_m,"
                    " COALESCE(moving_s, elapsed_s) AS secs FROM endurance_sessions"
                    " WHERE status='completed' AND sport='swimming'",
        "gym": "SELECT id, COALESCE(ended_at, started_at) AS at, NULL AS distance_m,"
               " elapsed_s AS secs FROM strength_sessions WHERE status='completed'",
        "cycling": "SELECT id, COALESCE(ended_at, started_at) AS at, distance_m,"
                   " COALESCE(moving_s, elapsed_s) AS secs FROM rides"
                   " WHERE ended_at IS NOT NULL",
    }
    sql = queries.get(sport)
    if sql is None:
        return []
    try:
        rows = db.conn.execute(sql).fetchall()
    except Exception:                      # a tabela ainda não existe
        return []
    out = []
    for r in rows:
        at = _parse(r["at"])
        if at is None:
            continue
        out.append({"id": r["id"], "at": at, "distance_m": float(r["distance_m"] or 0),
                    "seconds": float(r["secs"] or 0)})
    out.sort(key=lambda x: x["at"])
    return out


def _amount(metric: str, s: dict) -> float:
    return {"distance_m": s["distance_m"], "time_s": s["seconds"],
            "sessions": 1.0}.get(metric, 0.0)


def refresh(db, ch) -> dict:
    """Recalcula a tentativa em curso de um desafio (fora do ciclismo) a partir
    do histórico e fecha-a se o objetivo foi atingido. Devolve a tentativa."""
    sport = _get(ch, "sport") or "cycling"
    attempt = db.ensure_attempt(ch["id"])
    if sport == "cycling":
        return dict(attempt)
    started = _parse(attempt["started_at"])
    limit = deadline_of(ch)
    end = deadline_end(limit) if limit else None
    total = 0.0
    done_at = done_id = None
    for s in sessions_of(db, sport):
        if started is not None and s["at"] < started:
            continue
        if end is not None and s["at"] > end:
            break
        total += _amount(ch["metric"], s)
        if total >= ch["target"]:
            done_at, done_id = s["at"], s["id"]
            break
    if done_at is not None:
        elapsed = max(0.0, (done_at - started).total_seconds()) if started else 0.0
        # a hora local passa a UTC, como as outras datas da base
        done_iso = done_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        db.conn.execute(
            "UPDATE challenge_attempts SET progress=?, completed_at=?, elapsed_s=? WHERE id=?",
            (total, done_iso, elapsed, attempt["id"]))
        db.conn.commit()
        db.ensure_attempt(ch["id"])         # e começa logo a tentativa seguinte
        out = dict(attempt)
        out.update(progress=total, completed_at=done_iso, elapsed_s=elapsed,
                   just_done=bool(done_id))
        return out
    if abs(total - (attempt["progress"] or 0)) > 1e-9:
        db.conn.execute("UPDATE challenge_attempts SET progress=? WHERE id=?",
                        (total, attempt["id"]))
        db.conn.commit()
    out = dict(attempt)
    out["progress"] = total
    return out


def default_name(sport: str, metric: str, shown: str) -> str:
    verb = {"cycling": tr("Pedalar", "Ride"), "rowing": tr("Remar", "Row"),
            "running": tr("Correr", "Run"), "swimming": tr("Nadar", "Swim"),
            "gym": tr("Treinar", "Train")}.get(sport, tr("Treinar", "Train"))
    if metric == "ascent_m":
        return tr("Subir {v}", "Climb {v}", v=shown)
    if metric == "sessions":
        return tr("{v} sessões", "{v} sessions", v=shown)
    return f"{verb} {shown}"
