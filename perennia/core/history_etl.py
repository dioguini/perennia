"""Histórico de outras apps → Perennia: importar e **normalizar** com regras.

Cada app tem a sua forma de classificar os treinos (o TrainingPeaks diz «Strength», o Strava
«WeightTraining», o Garmin «strength_training»…). Aqui:

1. **Importar** o histórico (TrainingPeaks, Strava `activities.csv`, Garmin Connect
   `Activities.csv`) para `synced_activities`, como já era feito para o TrainingPeaks;
2. **Aplicar regras** — um ficheiro JSON ou CSV que o utilizador escreve — que dizem «quando o
   tipo for X, o desporto passa a ser Y, o tipo de treino Z e levam estas etiquetas». As regras
   atualizam o histórico **já importado** (`normalizar`) e correm sozinhas depois de cada
   importação (opção `etl_auto_apply`). Tudo o que as regras não cobrem aparece num relatório
   «sem regra», para se escreverem as que faltam. O tipo original (`source_sport`) nunca se
   perde: as regras só mudam o desporto, o título, as etiquetas e o tipo de treino da Perennia.

Regra (JSON: `{"regras": [ {…}, … ]}`; CSV com as mesmas colunas):

| campo | o que é |
|---|---|
| `fonte` | `trainingpeaks`, `strava`, `garmin`, `garmindb`, `upload`… ou `*` (qualquer) |
| `campo` | o que se compara: `tipo` (o tipo original da app), `titulo`, `desporto` |
| `operador` | `igual`, `contem`, `comeca`, `regex` (sem distinguir maiúsculas nem acentos) |
| `valor` | o texto a procurar |
| `desporto` | o desporto da Perennia: cycling, rowing, running, swimming, gym, other |
| `tipo_treino` | a chave de tipo de treino da Perennia (recovery, endurance, tempo, threshold, vo2max, anaerobic, work, race, test, technique, strength, mobility…) |
| `etiquetas` | etiquetas a juntar (lista; em CSV separadas por `|`) |
| `remover_etiquetas` | etiquetas a tirar |
| `titulo_novo` | novo título (pode usar `{titulo}`) |
| `ignorar` | `true`: a atividade é apagada do histórico |

As regras aplicam-se por ordem e a última que mandar num campo ganha; as etiquetas somam-se.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .db import Database, now_iso
from .i18n import tr

FIELDS = ("tipo", "titulo", "desporto")
OPERATORS = ("igual", "contem", "comeca", "regex")
SPORT_KEYS = ("cycling", "rowing", "running", "swimming", "gym", "other")
SOURCES = ("trainingpeaks", "strava", "garmin", "garmindb", "upload")

ALIASES = {"source": "fonte", "field": "campo", "operator": "operador", "value": "valor",
           "sport": "desporto", "workout_type": "tipo_treino", "tags": "etiquetas",
           "remove_tags": "remover_etiquetas", "new_title": "titulo_novo", "skip": "ignorar",
           "rules": "regras"}
CSV_COLUMNS = ("fonte", "campo", "operador", "valor", "desporto", "tipo_treino", "etiquetas",
               "remover_etiquetas", "titulo_novo", "ignorar")

# As regras de arranque: o que cada app costuma dizer → o que a Perennia diz.
DEFAULT_RULES: list[dict] = [
    {"fonte": "*", "campo": "tipo", "operador": "igual", "valor": v, "desporto": "gym",
     "tipo_treino": "strength"}
    for v in ("strengthening", "strength", "weighttraining", "weight training",
              "strength_training", "crossfit")
] + [
    {"fonte": "*", "campo": "tipo", "operador": "igual", "valor": v, "desporto": "rowing"}
    for v in ("rowing", "row", "indoor rowing", "indoor_rowing")
] + [
    {"fonte": "*", "campo": "tipo", "operador": "igual", "valor": v, "desporto": "cycling"}
    for v in ("bike", "ride", "virtualride", "virtual ride", "mountainbikeride", "ebikeride",
              "gravelride", "cycling", "road_biking", "indoor_cycling", "virtual_ride")
] + [
    {"fonte": "*", "campo": "tipo", "operador": "igual", "valor": v, "desporto": "running"}
    for v in ("run", "running", "treadmill_running", "trail running", "trailrun", "virtualrun",
              "walk", "walking", "hike")
] + [
    {"fonte": "*", "campo": "tipo", "operador": "igual", "valor": v, "desporto": "swimming"}
    for v in ("swim", "swimming", "lap_swimming", "open_water_swimming")
] + [
    {"fonte": "*", "campo": "tipo", "operador": "igual", "valor": v, "desporto": "gym",
     "tipo_treino": "mobility"}
    for v in ("yoga", "pilates", "stretching", "mobility")
] + [
    {"fonte": "*", "campo": "titulo", "operador": "contem", "valor": "recupera",
     "tipo_treino": "recovery"},
    {"fonte": "*", "campo": "titulo", "operador": "contem", "valor": "recovery",
     "tipo_treino": "recovery"},
    {"fonte": "*", "campo": "titulo", "operador": "contem", "valor": "limiar",
     "tipo_treino": "threshold"},
    {"fonte": "*", "campo": "titulo", "operador": "contem", "valor": "threshold",
     "tipo_treino": "threshold"},
    {"fonte": "*", "campo": "titulo", "operador": "contem", "valor": "vo2",
     "tipo_treino": "vo2max"},
    {"fonte": "*", "campo": "titulo", "operador": "contem", "valor": "tempo",
     "tipo_treino": "tempo"},
]


class RulesError(ValueError):
    """Um ficheiro de regras que não presta (diz onde)."""


# ----------------------------------------------------------------- regras


def _fold(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def _list(v) -> list[str]:
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[|;]", v) if x.strip()]
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def _truthy(v) -> bool:
    return v is True or _fold(v) in ("1", "true", "sim", "yes", "s", "y", "x")


def clean_rule(raw: dict, where: str = "") -> dict:
    """Uma regra válida (nomes em PT) ou `RulesError` a dizer o que está mal."""
    if not isinstance(raw, dict):
        raise RulesError(f"{where}: não é uma regra")
    r = {ALIASES.get(str(k).strip().lower(), str(k).strip().lower()): v for k, v in raw.items()}
    out: dict = {"fonte": _fold(r.get("fonte") or "*") or "*",
                 "campo": _fold(r.get("campo") or "tipo"),
                 "operador": _fold(r.get("operador") or "igual"),
                 "valor": str(r.get("valor") if r.get("valor") is not None else "").strip()}
    if out["campo"] == "type":
        out["campo"] = "tipo"
    if out["campo"] == "title":
        out["campo"] = "titulo"
    if out["campo"] == "sport":
        out["campo"] = "desporto"
    if out["campo"] not in FIELDS:
        raise RulesError(tr("{w}: «campo» tem de ser {c}", "{w}: 'campo' must be {c}",
                            w=where, c=", ".join(FIELDS)))
    if out["operador"] not in OPERATORS:
        raise RulesError(tr("{w}: «operador» tem de ser {c}", "{w}: 'operador' must be {c}",
                            w=where, c=", ".join(OPERATORS)))
    if out["valor"] == "":
        raise RulesError(tr("{w}: falta o «valor»", "{w}: 'valor' is missing", w=where))
    if out["operador"] == "regex":
        try:
            re.compile(out["valor"], re.I)
        except re.error as e:
            raise RulesError(f"{where}: regex: {e}") from None
    sport = _fold(r.get("desporto"))
    if sport:
        sport = {"strength": "gym", "ginasio": "gym", "bike": "cycling", "remo": "rowing",
                 "corrida": "running", "natacao": "swimming", "ciclismo": "cycling"}.get(
                     sport, sport)
        if sport not in SPORT_KEYS:
            raise RulesError(tr("{w}: desporto «{s}» desconhecido (usa {c})",
                                "{w}: unknown sport '{s}' (use {c})", w=where, s=sport,
                                c=", ".join(SPORT_KEYS)))
        out["desporto"] = sport
    if str(r.get("tipo_treino") or "").strip():
        from . import tags
        key = tags.type_key(str(r["tipo_treino"]))
        if not key:
            raise RulesError(tr("{w}: tipo de treino «{t}» desconhecido (usa {c})",
                                "{w}: unknown workout type '{t}' (use {c})", w=where,
                                t=r["tipo_treino"], c=", ".join(tags.TYPE_KEYS)))
        out["tipo_treino"] = key
    for k in ("etiquetas", "remover_etiquetas"):
        if _list(r.get(k)):
            out[k] = _list(r.get(k))
    if str(r.get("titulo_novo") or "").strip():
        out["titulo_novo"] = str(r["titulo_novo"]).strip()
    if _truthy(r.get("ignorar")):
        out["ignorar"] = True
    if not any(k in out for k in ("desporto", "tipo_treino", "etiquetas", "remover_etiquetas",
                                  "titulo_novo", "ignorar")):
        raise RulesError(tr("{w}: a regra não faz nada (falta desporto, tipo_treino, etiquetas…)",
                            "{w}: the rule does nothing (no desporto, tipo_treino, etiquetas…)",
                            w=where))
    return out


def parse_rules(text: str, is_csv: bool = False) -> list[dict]:
    """Lê o texto de um ficheiro de regras (JSON ou CSV)."""
    text = text.lstrip("﻿")
    if is_csv or not text.lstrip().startswith(("{", "[")):
        sample = text[:2000]
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        raw = [dict(r) for r in csv.DictReader(io.StringIO(text), delimiter=delim)
               if any((v or "").strip() for v in r.values() if isinstance(v, str))]
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise RulesError(tr("JSON inválido (linha {l}): {m}", "invalid JSON (line {l}): {m}",
                                l=e.lineno, m=e.msg)) from None
        if isinstance(data, dict):
            data = data.get("regras", data.get("rules"))
        if not isinstance(data, list):
            raise RulesError(tr("o ficheiro tem de ter a lista «regras»",
                                "the file must have a 'regras' list"))
        raw = data
    if not raw:
        raise RulesError(tr("o ficheiro não tem regras", "the file has no rules"))
    return [clean_rule(r, tr("regra {n}", "rule {n}", n=i)) for i, r in enumerate(raw, 1)]


def load_rules(path: str | Path, max_kb: int = 512) -> list[dict]:
    path = Path(path)
    try:
        if path.stat().st_size > max_kb * 1024:
            raise RulesError(tr("ficheiro de regras grande demais (máximo {n} kB)",
                                "rules file too large (max {n} kB)", n=max_kb))
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise RulesError(tr("não consegui ler as regras: {e}", "could not read the rules: {e}",
                            e=str(e)[:100])) from None
    return parse_rules(text, path.suffix.lower() == ".csv")


def rules_path(db: Database) -> Path:
    """O ficheiro de regras: o das Definições, ou `regras-historico.json` na pasta de
    importações."""
    from . import folders, options
    text = str(options.get(db, "etl_rules_file") or "").strip()
    if text:
        return Path(folders.expand_text(text))
    return folders.resolve(db, db.path.parent, "imports") / "regras-historico.json"


def write_template(folder: str | Path) -> Path:
    """Grava o ficheiro de regras de arranque, para editar (nunca substitui um que exista)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "regras-historico.json"
    n = 2
    while path.exists():
        path = folder / f"regras-historico-{n}.json"
        n += 1
    path.write_text(json.dumps({"regras": DEFAULT_RULES}, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path


def active_rules(db: Database) -> list[dict]:
    """As regras em uso: as do ficheiro, se existir; senão as de arranque (opção
    `etl_use_defaults`)."""
    from . import options
    p = rules_path(db)
    rules = load_rules(p, int(options.get(db, "etl_rules_max_kb") or 512)) if p.is_file() else []
    if not rules and options.get(db, "etl_use_defaults"):
        rules = [clean_rule(r, "default") for r in DEFAULT_RULES]
    return rules


# ------------------------------------------------------------ aplicar regras


def _matches(rule: dict, act: dict) -> bool:
    src = _fold(act.get("source"))
    if rule["fonte"] != "*" and rule["fonte"] != src:
        return False
    field = {"tipo": act.get("source_sport"), "titulo": act.get("name"),
             "desporto": act.get("sport")}[rule["campo"]]
    a, b = _fold(field), _fold(rule["valor"])
    op = rule["operador"]
    if op == "igual":
        return a == b
    if op == "contem":
        return b in a
    if op == "comeca":
        return a.startswith(b)
    try:
        return re.search(rule["valor"], str(field or ""), re.I) is not None
    except re.error:
        return False


def evaluate(rules: list[dict], act: dict) -> dict:
    """O que as regras fazem a uma atividade: {sport, workout_type, tags, remove, name, skip,
    matched}. `matched` é o número de regras que se aplicaram."""
    res: dict = {"sport": None, "workout_type": None, "tags": [], "remove": [], "name": None,
                 "skip": False, "matched": 0}
    cur = dict(act)
    for r in rules:
        if not _matches(r, cur):
            continue
        res["matched"] += 1
        if r.get("desporto"):
            res["sport"] = cur["sport"] = r["desporto"]
        if r.get("tipo_treino"):
            res["workout_type"] = r["tipo_treino"]
        for t in r.get("etiquetas") or []:
            if t not in res["tags"]:
                res["tags"].append(t)
        res["remove"] += [t for t in r.get("remover_etiquetas") or [] if t not in res["remove"]]
        if r.get("titulo_novo"):
            res["name"] = cur["name"] = r["titulo_novo"].replace("{titulo}",
                                                                  str(act.get("name") or ""))
        if r.get("ignorar"):
            res["skip"] = True
    return res


def normalize(db: Database, rules: list[dict] | None = None, *, dry_run: bool = True,
              ids: list[str] | None = None) -> dict:
    """Aplica as regras ao histórico já importado. Com `dry_run` (por omissão) só conta e
    mostra; sem ele grava. Devolve {"total", "changed", "skipped", "unmapped": {tipo: n},
    "by_sport": {...}, "examples": [...]}."""
    from . import garmin_sync as gs, tags
    gs.ensure(db)
    tags.ensure(db)
    rules = active_rules(db) if rules is None else rules
    sql, args = "SELECT * FROM synced_activities", []
    if ids is not None:
        if not ids:
            return {"total": 0, "changed": 0, "removed": 0, "unmapped": {}, "by_sport": {},
                    "examples": [], "dry_run": dry_run}
        sql += " WHERE id IN (%s)" % ",".join("?" * len(ids))
        args = list(ids)
    rep: dict = {"total": 0, "changed": 0, "removed": 0, "unmapped": {}, "by_sport": {},
                 "examples": [], "dry_run": dry_run}
    for row in db.conn.execute(sql, args).fetchall():
        act = dict(row)
        rep["total"] += 1
        res = evaluate(rules, act)
        if not res["matched"]:
            k = f"{act.get('source')}:{act.get('source_sport') or '—'}"
            rep["unmapped"][k] = rep["unmapped"].get(k, 0) + 1
            continue
        if res["skip"]:
            rep["removed"] += 1
            if not dry_run:
                db.conn.execute("DELETE FROM synced_activities WHERE id = ?", (act["id"],))
                db.conn.execute("DELETE FROM session_tags WHERE session_id = ?", (act["id"],))
            continue
        new_sport = res["sport"] or act["sport"]
        new_name = res["name"] or act["name"]
        old = tags.load(db, act["sport"], act["id"])
        info = {"workout_type": res["workout_type"] or old["workout_type"],
                "activity": list(old["activity"]),
                "session": list(old["session"]),
                "custom": [t for t in old["custom"] + res["tags"] if t not in res["remove"]]}
        info["custom"] = list(dict.fromkeys(info["custom"]))
        changed = (new_sport != act["sport"] or new_name != act["name"]
                   or info != {k: old[k] for k in info})
        if not changed:
            continue
        rep["changed"] += 1
        rep["by_sport"][new_sport] = rep["by_sport"].get(new_sport, 0) + 1
        if len(rep["examples"]) < 8:
            rep["examples"].append(f"{act.get('source_sport') or '—'} «{act.get('name') or ''}»"
                                   f" → {new_sport}"
                                   + (f" · {tags.type_label(info['workout_type'])}"
                                      if info["workout_type"] else "")
                                   + (" · " + ", ".join(res["tags"]) if res["tags"] else ""))
        if dry_run:
            continue
        if new_sport != act["sport"]:
            db.conn.execute("DELETE FROM session_tags WHERE sport = ? AND session_id = ?",
                            (act["sport"], act["id"]))
        db.conn.execute("UPDATE synced_activities SET sport = ?, name = ? WHERE id = ?",
                        (new_sport, new_name, act["id"]))
        tags.save(db, new_sport, act["id"], info)
    if not dry_run:
        db.conn.commit()
    return rep


def report_text(rep: dict) -> str:
    lines = [tr("{c} de {t} atividades {v}; {r} removidas", "{c} of {t} activities {v}; {r} "
                "removed", c=rep["changed"], t=rep["total"], r=rep["removed"],
                v=tr("seriam alteradas", "would change") if rep["dry_run"]
                else tr("alteradas", "changed"))]
    if rep["by_sport"]:
        lines.append(tr("Por desporto: ", "By sport: ")
                     + ", ".join(f"{k} {v}" for k, v in sorted(rep["by_sport"].items())))
    lines += ["  " + e for e in rep["examples"]]
    if rep["unmapped"]:
        lines.append(tr("Sem regra (escreve regras para estes tipos):",
                        "No rule (write rules for these types):"))
        lines += [f"  {k} · {n}" for k, n in sorted(rep["unmapped"].items(),
                                                     key=lambda kv: -kv[1])[:25]]
    return "\n".join(lines)


def auto_apply(db: Database, ids: list[str] | None = None) -> dict | None:
    """Depois de uma importação: aplica as regras às atividades novas (opção `etl_auto_apply`).
    Um erro nas regras não estraga a importação: devolve `{"error": …}`."""
    from . import options
    if not options.get(db, "etl_auto_apply"):
        return None
    try:
        return normalize(db, dry_run=False, ids=ids)
    except RulesError as e:
        return {"error": str(e)}


# ----------------------------------------------------------------- fontes


def _num(v) -> float | None:
    try:
        s = str(v).strip().replace(",", ".")
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


def _hms(v) -> float | None:
    s = str(v or "").strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _strava_date(s: str) -> str | None:
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%d %b %Y, %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def looks_like(path: str | Path) -> str | None:
    """«strava», «garmin» ou None, pelo cabeçalho do .csv."""
    try:
        head = Path(path).read_text(encoding="utf-8-sig", errors="replace")[:1500]
    except OSError:
        return None
    first = head.splitlines()[0] if head else ""
    if "Activity Date" in first and "Activity Type" in first:
        return "strava"
    if "Activity Type" in first and "Title" in first and "Date" in first:
        return "garmin"
    return None


def _insert(db: Database, source: str, uid: str, kind: str, name: str, started: str,
            elapsed, moving, dist, asc, avg_hr, max_hr, cal, load) -> None:
    db.conn.execute(
        "INSERT INTO synced_activities(id, source, sport, source_sport, name,"
        " started_at, elapsed_s, moving_s, distance_m, ascent_m, avg_hr, max_hr, calories,"
        " training_load, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        # reimportar atualiza os números mas não desfaz o que as regras já normalizaram
        " ON CONFLICT(id) DO UPDATE SET elapsed_s=excluded.elapsed_s, moving_s=excluded.moving_s,"
        " distance_m=excluded.distance_m, ascent_m=excluded.ascent_m, avg_hr=excluded.avg_hr,"
        " max_hr=excluded.max_hr, calories=excluded.calories,"
        " training_load=excluded.training_load, imported_at=excluded.imported_at",
        (uid, source, "other", kind, name, started, elapsed, moving, dist, asc, avg_hr, max_hr,
         cal, load, now_iso()))


def import_history(db: Database, path: str | Path, source: str | None = None) -> dict:
    """Importa o histórico de uma app (TrainingPeaks, Strava ou Garmin Connect, pelo
    cabeçalho) e aplica as regras às atividades novas. Importar o mesmo ficheiro duas vezes não
    duplica. Devolve {"source", "activities", "skipped", "etl": relatório|None}."""
    from . import garmin_sync as gs, tp_import
    gs.ensure(db)
    source = source or ("trainingpeaks" if tp_import.looks_like_tp(path) else looks_like(path))
    if source not in ("trainingpeaks", "strava", "garmin"):
        raise ValueError(tr("não reconheço este ficheiro (esperava o .csv do TrainingPeaks, do "
                            "Strava ou do Garmin Connect)", "unrecognised file (expected a "
                            "TrainingPeaks, Strava or Garmin Connect .csv)"))
    before = {r[0] for r in db.conn.execute("SELECT id FROM synced_activities")}
    if source == "trainingpeaks":
        rep = tp_import.import_csv(db, path)
        ids = [r[0] for r in db.conn.execute(
            "SELECT id FROM synced_activities WHERE source = 'trainingpeaks'")]
        n, skipped = rep["activities"], rep["skipped"]
    else:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        head, body = rows[0], rows[1:]
        n = skipped = 0
        ids = []

        def col(r, *names):
            for nm in names:
                if nm in head:
                    i = head.index(nm)           # (o Strava repete colunas: vale a primeira)
                    return r[i] if i < len(r) else ""
            return ""
        for r in body:
            if source == "strava":
                started = _strava_date(col(r, "Activity Date"))
                kind, name = col(r, "Activity Type"), col(r, "Activity Name")
                elapsed = _num(col(r, "Elapsed Time"))
                moving = _num(col(r, "Moving Time")) or elapsed
                dist = _num(col(r, "Distance"))
                dist = dist * 1000 if dist is not None and dist < 1000 else dist
                asc = _num(col(r, "Elevation Gain"))
                avg_hr, max_hr = _num(col(r, "Average Heart Rate")), _num(col(r, "Max Heart Rate"))
                cal = _num(col(r, "Calories"))
                load = _num(col(r, "Relative Effort"))
                key = col(r, "Activity ID") or f"{started}|{name}"
            else:
                started = _strava_date(col(r, "Date"))
                kind, name = col(r, "Activity Type"), col(r, "Title")
                elapsed = _hms(col(r, "Time", "Elapsed Time"))
                moving = _hms(col(r, "Moving Time")) or elapsed
                dist = _num(col(r, "Distance"))
                dist = dist * 1000 if dist is not None else None
                asc = _num(col(r, "Total Ascent"))
                avg_hr, max_hr = _num(col(r, "Avg HR")), _num(col(r, "Max HR"))
                cal = _num(col(r, "Calories"))
                load = _num(col(r, "Training Stress Score®", "Training Stress Score"))
                key = f"{started}|{name}|{elapsed}"
            if not started or not elapsed:
                skipped += 1
                continue
            uid = f"{source}:" + hashlib.sha1(str(key).encode()).hexdigest()[:16]
            _insert(db, source, uid, kind, name or kind, started, elapsed, moving, dist, asc,
                    avg_hr, max_hr, cal, load)
            ids.append(uid)
            n += 1
        db.conn.commit()
    new_ids = [i for i in ids if i not in before]
    out = {"source": source, "activities": n, "skipped": skipped, "new": len(new_ids)}
    # Só as novas levam as regras; o resto do histórico normaliza-se à parte (`normalizar`).
    # (O TrainingPeaks reescreve o `sport` de todas ao reimportar: por isso lhes aplicamos
    # as regras a todas.)
    out["etl"] = auto_apply(db, ids if source == "trainingpeaks" else new_ids)
    return out


def import_text(rep: dict) -> str:
    base = tr("{s}: {n} atividades ({k} novas) · {x} ignoradas",
              "{s}: {n} activities ({k} new) · {x} skipped", s=rep["source"],
              n=rep["activities"], k=rep.get("new", rep["activities"]), x=rep["skipped"])
    etl = rep.get("etl")
    if etl and etl.get("error"):
        base += "\n" + tr("Regras não aplicadas: ", "Rules not applied: ") + etl["error"]
    elif etl:
        base += "\n" + report_text(etl)
    return base
