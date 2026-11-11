"""Upload manual de uma atividade: lê um ficheiro do computador (.fit ou .tcx),
mostra o que lá está e, se o utilizador quiser, guarda-a no desporto respetivo.

A atividade fica em `synced_activities` (a mesma tabela das do Garmin e do
TrainingPeaks), com a origem «upload»: aparece no Histórico do desporto e
conta para a forma e a fadiga. Carregar o mesmo ficheiro duas vezes não a
duplica (o id vem do conteúdo).
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from . import fit_decode, garmin_sync as gs, safexml
from .db import now_iso

EXTENSIONS = (".fit", ".tcx")


MAKERS = {1: "Garmin", 15: "Dynastream", 23: "Suunto", 32: "Wahoo", 38: "Stages", 255: None,
          260: "Zwift", 294: "Coros", 70: "Sigmeter", 13: "Cycleops", 89: "Tacx"}


class UploadError(ValueError):
    pass


def perennia_sport(sport: str | None, sub: str | None) -> str:
    """O desporto da Perennia para o desporto do ficheiro."""
    s, ss = (sport or "").lower(), (sub or "").lower()
    if s == "rowing" or ss == "indoor_rowing":
        return "rowing"
    if s in ("running", "walking", "hiking") or ss in ("treadmill", "indoor_running", "track",
                                                        "trail"):
        return "running"
    if s in ("cycling", "e_biking") or ss in ("indoor_cycling", "spin", "road", "mountain"):
        return "cycling"
    if s == "swimming" or ss in ("lap_swimming", "open_water"):
        return "swimming"
    if s == "training" or ss in ("strength_training", "cardio_training"):
        return "gym"
    return "gym" if s in ("fitness_equipment", "generic", "") else "gym"


def _iso(when: datetime | None) -> str | None:
    if when is None:
        return None
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mean(values: list) -> float | None:
    v = [x for x in values if x is not None]
    return sum(v) / len(v) if v else None


def _np(powers: list[float]) -> float | None:
    """Potência normalizada (média móvel de 30 s, à 4.ª)."""
    if len(powers) < 30:
        return None
    win = 30
    roll, total = [], sum(powers[:win])
    roll.append(total / win)
    for i in range(win, len(powers)):
        total += powers[i] - powers[i - win]
        roll.append(total / win)
    return (sum(x ** 4 for x in roll) / len(roll)) ** 0.25


def parse_fit(path: Path) -> dict:
    try:
        msgs = fit_decode.decode(path)
    except fit_decode.FitError as e:
        raise UploadError(str(e)) from e
    except (IndexError, ValueError, OverflowError) as e:           # ficheiro truncado
        raise UploadError("o ficheiro .fit está estragado ou incompleto") from e
    sessions, records = msgs["session"], msgs["record"]
    if not sessions and not records:
        raise UploadError("o ficheiro não tem nenhuma atividade (sessões ou registos)")
    sport_msg = (msgs["sport"] or [{}])[0]
    s0 = sessions[0] if sessions else {}
    sport_id = s0.get("sport", sport_msg.get("sport"))
    sub_id = s0.get("sub_sport", sport_msg.get("sub_sport"))
    sport_name = fit_decode.SPORTS.get(sport_id, "") if sport_id is not None else ""
    sub_name = fit_decode.SUB_SPORTS.get(sub_id, "") if sub_id is not None else ""
    # um ficheiro com mais do que uma sessão (triatlo, …) soma-se
    elapsed = sum(s.get("total_elapsed_time") or 0 for s in sessions)
    moving = sum(s.get("total_timer_time") or 0 for s in sessions)
    dist = sum(s.get("total_distance") or 0 for s in sessions)
    ascent = sum(s.get("total_ascent") or 0 for s in sessions)
    cals = sum(s.get("total_calories") or 0 for s in sessions)
    hr_rec = [r.get("heart_rate") for r in records]
    pw_rec = [r.get("power") for r in records]
    start = s0.get("start_time") or (records[0].get("timestamp") if records else None) or \
        (msgs["file_id"][0].get("time_created") if msgs["file_id"] else None)
    if not elapsed and len(records) > 1 and records[0].get("timestamp"):
        elapsed = (records[-1]["timestamp"] - records[0]["timestamp"]).total_seconds()
    if not moving:
        moving = elapsed
    if not dist and records:
        dist = max([r.get("distance") or 0 for r in records] + [0])
    avg_hr = s0.get("avg_heart_rate") or _mean([h for h in hr_rec if h])
    max_hr = s0.get("max_heart_rate") or max([h for h in hr_rec if h] + [0]) or None
    avg_pw = s0.get("avg_power") or _mean([p for p in pw_rec if p is not None])
    np_w = s0.get("normalized_power") or _np([p or 0 for p in pw_rec])
    alt = [r.get("enhanced_altitude", r.get("altitude")) for r in records]
    alt = [a for a in alt if a is not None]
    if not ascent and len(alt) > 1:
        ascent = sum(max(0.0, b - a) for a, b in zip(alt, alt[1:]))
    sport = perennia_sport(sport_name, sub_name)
    info = {
        "format": "fit", "sport": sport, "source_sport": "/".join(x for x in (sport_name, sub_name)
                                                               if x and x != "generic"),
        "name": (sport_msg.get("name") or "").strip(), "started_at": _iso(start),
        "elapsed_s": float(elapsed or 0), "moving_s": float(moving or 0),
        "distance_m": float(dist or 0) or None, "ascent_m": float(ascent or 0) or None,
        "avg_hr": float(avg_hr) if avg_hr else None, "max_hr": float(max_hr) if max_hr else None,
        "avg_power_w": float(avg_pw) if avg_pw else None, "np_w": float(np_w) if np_w else None,
        "calories": float(cals) if cals else None,
        "tss": s0.get("training_stress_score"), "if_value": s0.get("intensity_factor"),
        "laps": len(msgs["lap"]), "records": len(records),
        "device": MAKERS.get((msgs["file_id"] or [{}])[0].get("manufacturer")),
    }
    if s0.get("pool_length"):
        info["pool_m"] = float(s0["pool_length"])
    return info


def parse_tcx(path: Path) -> dict:
    try:
        root = safexml.parse(path).getroot()
    except (ET.ParseError, safexml.UnsafeXML) as e:
        raise UploadError("o ficheiro .tcx está estragado ou não é seguro") from e

    def tag(el) -> str:
        return el.tag.rsplit("}", 1)[-1]
    acts = [e for e in root.iter() if tag(e) == "Activity"]
    if not acts:
        raise UploadError("o ficheiro não tem nenhuma atividade")
    act = acts[0]
    sport_attr = act.get("Sport", "")
    elapsed = dist = cals = 0.0
    avg_hrs, max_hrs, start, pw, hr, alt = [], [], None, [], [], []
    laps = 0
    for lap in act:
        if tag(lap) != "Lap":
            continue
        laps += 1
        start = start or lap.get("StartTime")
        for ch in lap:
            t = tag(ch)
            try:
                if t == "TotalTimeSeconds":
                    elapsed += float(ch.text)
                elif t == "DistanceMeters":
                    dist += float(ch.text)
                elif t == "Calories":
                    cals += float(ch.text)
                elif t == "AverageHeartRateBpm":
                    avg_hrs.append(float(next(iter(ch)).text))
                elif t == "MaximumHeartRateBpm":
                    max_hrs.append(float(next(iter(ch)).text))
            except (TypeError, ValueError, StopIteration):
                continue
        for p in lap.iter():
            t = tag(p)
            try:
                if t == "HeartRateBpm":
                    hr.append(float(next(iter(p)).text))
                elif t == "Watts":
                    pw.append(float(p.text))
                elif t == "AltitudeMeters":
                    alt.append(float(p.text))
            except (TypeError, ValueError, StopIteration):
                continue
    if start is None:
        ids = [e.text for e in act if tag(e) == "Id"]
        start = ids[0] if ids else None
    when = None
    if start:
        try:
            when = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except ValueError:
            when = None
    sport = perennia_sport({"Running": "running", "Biking": "cycling"}.get(sport_attr,
                                                                           sport_attr), None)
    return {
        "format": "tcx", "sport": sport, "source_sport": sport_attr, "name": "",
        "started_at": _iso(when), "elapsed_s": elapsed, "moving_s": elapsed,
        "distance_m": dist or None,
        "ascent_m": sum(max(0.0, b - a) for a, b in zip(alt, alt[1:])) or None,
        "avg_hr": _mean(avg_hrs) or _mean(hr), "max_hr": max(max_hrs + hr + [0]) or None,
        "avg_power_w": _mean(pw), "np_w": _np(pw), "calories": cals or None, "tss": None,
        "if_value": None, "laps": laps, "records": len(hr) or len(alt), "device": None,
    }


def parse(path: str | Path) -> dict:
    """Lê o ficheiro e devolve o que lá está (sem gravar nada)."""
    p = Path(path)
    if not p.is_file():
        raise UploadError("o ficheiro não existe")
    ext = p.suffix.lower()
    if ext == ".fit":
        info = parse_fit(p)
    elif ext == ".tcx":
        info = parse_tcx(p)
    else:
        raise UploadError("formato não suportado (usa .fit ou .tcx)")
    if not info.get("started_at"):
        raise UploadError("o ficheiro não tem a data da atividade")
    when = datetime.strptime(info["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).astimezone()
    if not info["name"]:
        info["name"] = p.stem.replace("_", " ").strip() or when.strftime("%d/%m/%Y")
    info["file"] = p.name
    info["sha"] = hashlib.sha1(p.read_bytes()).hexdigest()[:20]
    return info


def exists(db, info: dict) -> bool:
    gs.ensure(db)
    return db.conn.execute("SELECT 1 FROM synced_activities WHERE id = ?",
                           ("up:" + info["sha"],)).fetchone() is not None


def save(db, info: dict, sport: str | None = None, name: str | None = None) -> str:
    """Guarda a atividade no desporto (por omissão, o que o ficheiro diz)."""
    gs.ensure(db)
    uid = "up:" + info["sha"]
    db.conn.execute(
        "INSERT OR REPLACE INTO synced_activities(id, source, sport, source_sport, name,"
        " started_at, elapsed_s, moving_s, distance_m, ascent_m, avg_hr, max_hr, calories,"
        " training_load, imported_at, tss, if_value, avg_power_w, np_w)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, "upload", sport or info["sport"], info.get("source_sport") or None,
         (name or info["name"]).strip() or info["file"], info["started_at"], info["elapsed_s"],
         info["moving_s"], info["distance_m"], info["ascent_m"], info["avg_hr"], info["max_hr"],
         info["calories"], None, now_iso(), info.get("tss"), info.get("if_value"),
         info.get("avg_power_w"), info.get("np_w")))
    db.conn.commit()
    return uid


def delete(db, uid: str) -> None:
    gs.ensure(db)
    db.conn.execute("DELETE FROM synced_activities WHERE id = ? AND source = 'upload'", (uid,))
    db.conn.commit()


