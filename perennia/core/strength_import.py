"""Importar um treino de força (ginásio) de um ficheiro do computador.

Para criar o treino noutro sítio — por exemplo no TrainingPeaks, que tem treinos estruturados
de força — e trazê-lo para a Perennia. Formatos:

* **.csv** — uma linha por exercício: `exercicio;series;reps;carga_kg;rpe;descanso_s;notas`
  (também `exercise`, `sets`, `load`, `rest`…; `,` ou `;`). O nome do treino é o do ficheiro.
  Um exercício por tempo põe `s` nas repetições (`40 s`).
* **.json** — o export da Perennia (`blocos[].nome` e `blocos[].alvo`: `4 × 8 · 40 kg · RPE 7 ·
  descanso 90 s`) ou uma lista `exercicios`: `[{"nome", "series", "reps", "carga_kg", "rpe",
  "descanso_s"}]` (o que o TrainingPeaks exporta em JSON, depois de mapeado).
* **.txt / .md** — uma linha por exercício: `Supino com barra 4x8 40kg rpe 7 descanso 90` (também
  o `.txt` que a Perennia exporta: `1. Nome — dur — alvo 4 × 8 · 40 kg…`).
* **.fit** — um treino do Garmin/TrainingPeaks cujos passos têm o nome do exercício (nota do
  passo) e as repetições; um passo «repetir» vira as séries.

Os exercícios que ainda não existirem criam-se na modalidade escolhida (grupo «corpo inteiro»).
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import tr

EXTS = (".csv", ".json", ".txt", ".md", ".fit")


class ImportError_(ValueError):
    pass


@dataclass
class Row:
    name: str
    sets: int = 3
    reps: int = 10
    time: bool = False                 # as «reps» são segundos
    load_kg: float | None = None
    rpe: float | None = None
    rest_s: int = 90
    notes: str | None = None


@dataclass
class Loaded:
    name: str
    rows: list[Row] = field(default_factory=list)
    fmt: str = ""


def _fold(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def _num(v) -> float | None:
    try:
        return float(str(v).strip().replace(",", ".").replace("kg", "").replace("s", ""))
    except ValueError:
        return None


# ----------------------------------------------------------------- texto

_SETS_REPS = re.compile(r"(\d+)\s*[x×]\s*(\d+)\s*(s\b|seg\b)?", re.I)
_KG = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg", re.I)
_RPE = re.compile(r"rpe\s*(\d+(?:[.,]\d+)?)", re.I)
_REST = re.compile(r"(?:descanso|rest)\s*(\d+)\s*s?", re.I)


def parse_target(text: str) -> dict:
    """«4 × 8 · 40 kg · RPE 7 · descanso 90 s» → séries, reps, carga, RPE, descanso."""
    out: dict = {}
    m = _SETS_REPS.search(text)
    if m:
        out["sets"], out["reps"], out["time"] = int(m.group(1)), int(m.group(2)), bool(m.group(3))
    m = _KG.search(text)
    if m:
        out["load_kg"] = _num(m.group(1))
    m = _RPE.search(text)
    if m:
        out["rpe"] = _num(m.group(1))
    m = _REST.search(text)
    if m:
        out["rest_s"] = int(m.group(1))
    return out


def _row_from_line(line: str) -> Row | None:
    line = line.strip().strip("-•*").strip()
    line = re.sub(r"^\d+[.)]\s*", "", line)               # «1. Supino…»
    if not line or line.startswith("=") or ":" in line and "—" not in line and "x" not in line:
        return None
    t = parse_target(line)
    if "sets" not in t:
        return None
    name = re.split(r"\s+[—-]\s+|\s{2,}|(?=\s\d+\s*[x×]\s*\d)", line)[0]
    name = _SETS_REPS.sub("", name).strip(" -—:·")
    if not name:
        return None
    return Row(name=name, sets=t["sets"], reps=t["reps"], time=t.get("time", False),
               load_kg=t.get("load_kg"), rpe=t.get("rpe"), rest_s=t.get("rest_s", 90))


def _read_txt(path: Path) -> Loaded:
    rows = []
    title = path.stem
    for i, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines()):
        if i == 0 and line.strip() and not _SETS_REPS.search(line):
            title = line.strip()
            continue
        r = _row_from_line(line)
        if r:
            rows.append(r)
    return Loaded(title, rows, "txt")


# ------------------------------------------------------------------- json


def _read_json(path: Path) -> Loaded:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as e:
        raise ImportError_(tr(".json inválido: {e}", "invalid .json: {e}", e=e)) from e
    if isinstance(data, list):
        data = {"exercicios": data}
    title = data.get("treino") or data.get("name") or data.get("nome") or path.stem
    rows: list[Row] = []
    for x in data.get("exercicios") or data.get("exercises") or []:
        name = x.get("nome") or x.get("name") or x.get("exercicio") or x.get("exercise")
        if not name:
            continue
        reps = x.get("reps") or x.get("repeticoes") or 10
        is_time = isinstance(reps, str) and reps.strip().endswith("s")
        rows.append(Row(name=str(name), sets=int(_num(x.get("series") or x.get("sets") or 3) or 3),
                        reps=int(_num(reps) or 10), time=is_time,
                        load_kg=_num(x.get("carga_kg") or x.get("load_kg") or x.get("carga")),
                        rpe=_num(x.get("rpe")),
                        rest_s=int(_num(x.get("descanso_s") or x.get("rest_s") or 90) or 90),
                        notes=x.get("notas") or x.get("notes")))
    for b in data.get("blocos") or data.get("blocks") or []:         # o export da Perennia
        name = b.get("nome") or b.get("name")
        t = parse_target(str(b.get("alvo") or b.get("target") or ""))
        if name and "sets" in t:
            rows.append(Row(name=str(name), sets=t["sets"], reps=t["reps"],
                            time=t.get("time", False), load_kg=t.get("load_kg"),
                            rpe=t.get("rpe"), rest_s=t.get("rest_s", 90),
                            notes=b.get("objetivo") or None))
    return Loaded(str(title), rows, "json")


# -------------------------------------------------------------------- csv

_ALIASES = {"name": ("exercicio", "exercise", "nome", "name"),
            "sets": ("series", "sets", "serie"),
            "reps": ("reps", "repeticoes", "repetitions"),
            "load": ("carga_kg", "carga", "load", "load_kg", "kg", "peso"),
            "rpe": ("rpe",), "rest": ("descanso_s", "descanso", "rest", "rest_s"),
            "notes": ("notas", "notes", "nota")}


def _read_csv(path: Path) -> Loaded:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    head = text.splitlines()[0] if text.strip() else ""
    delim = max((";", ",", "\t"), key=head.count)
    rows_raw = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows_raw:
        raise ImportError_(tr("o .csv está vazio", "the .csv is empty"))
    cols = [_fold(c).replace(" ", "_") for c in rows_raw[0]]
    idx = {k: next((cols.index(a) for a in als if a in cols), None) for k, als in _ALIASES.items()}
    if idx["name"] is None:
        raise ImportError_(tr("falta a coluna «exercicio»", "the “exercicio” column is missing"))
    rows = []
    for r in rows_raw[1:]:
        def cell(k):
            i = idx[k]
            return r[i].strip() if i is not None and i < len(r) else ""
        if not cell("name"):
            continue
        reps = cell("reps")
        rows.append(Row(name=cell("name"), sets=int(_num(cell("sets")) or 3),
                        reps=int(_num(reps) or 10), time=reps.lower().endswith("s"),
                        load_kg=_num(cell("load")), rpe=_num(cell("rpe")),
                        rest_s=int(_num(cell("rest")) or 90), notes=cell("notes") or None))
    return Loaded(path.stem, rows, "csv")


# -------------------------------------------------------------------- fit


def _read_fit(path: Path) -> Loaded:
    from . import fit
    try:
        msgs = fit.read_messages(path)
    except Exception as e:
        raise ImportError_(tr(".fit inválido: {e}", "invalid .fit: {e}", e=e)) from e
    title, steps = path.stem, []
    for num, f in msgs:
        if num == 26:
            title = f.get(8) or title
        elif num == 27:
            steps.append(f)
    if not steps:
        raise ImportError_(tr("o .fit não é um treino", "the .fit is not a workout"))
    rows: list[Row] = []
    for f in steps:
        dt = f.get(1)
        if dt == 6:                                  # «repetir desde o passo N, X vezes»
            start, times = int(f.get(2, 0)), int(f.get(4, 1))
            for r in rows[start:]:
                r.sets = max(r.sets, times)
            continue
        name = f.get(8) or ""
        if not name or f.get(7) in (1, 4):           # sem nome ou descanso: não é exercício
            if rows and f.get(7) in (1, 4) and dt == 0:
                rows[-1].rest_s = int((f.get(2) or 0) / 1000)
            continue
        if dt == 29:                                  # duração em repetições
            rows.append(Row(name=str(name), reps=int(f.get(2) or 10)))
        elif dt == 0:                                 # por tempo
            rows.append(Row(name=str(name), reps=int((f.get(2) or 40000) / 1000), time=True))
        else:
            rows.append(Row(name=str(name)))
    return Loaded(str(title), rows, "fit")


# --------------------------------------------------------------- API


def read(path) -> Loaded:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        loaded = _read_csv(path)
    elif ext == ".json":
        loaded = _read_json(path)
    elif ext in (".txt", ".md"):
        loaded = _read_txt(path)
    elif ext == ".fit":
        loaded = _read_fit(path)
    else:
        raise ImportError_(tr("formato não suportado: {e}", "unsupported format: {e}", e=ext))
    if not loaded.rows:
        raise ImportError_(tr("não encontrei exercícios neste ficheiro",
                              "I found no exercises in this file"))
    return loaded


def scan(folders: list[str] | None = None) -> list[Path]:
    """Os ficheiros de treino de força nas pastas do costume."""
    import os
    from perennia import paths
    from .workout_files import FOLDERS, PER_FOLDER
    if folders is None:
        folders = [str(p) for p in paths.user_folder("workouts")] + list(FOLDERS)
    found: list[Path] = []
    for folder in dict.fromkeys(folders):
        base = Path(os.path.expanduser(folder))
        if base.is_dir():
            found.extend(sorted(p for p in base.iterdir()
                                if p.is_file() and p.suffix.lower() in EXTS)[:PER_FOLDER])
    return found


def resolve_exercise(db, name: str, modality: str, measure: str) -> int:
    """O id do exercício com este nome (sem contar acentos nem maiúsculas); se não houver,
    cria-o na modalidade."""
    from . import gym
    gym.ensure(db)
    low = _fold(name)
    exs = gym.exercises(db, include_archived=True)
    for e in exs:
        if _fold(e["name"]) == low:
            return e["id"]
    for e in exs:                                    # «Supino» acha «Supino com barra»
        if low and (low in _fold(e["name"]) or _fold(e["name"]) in low):
            return e["id"]
    return gym.save_exercise(db, None, name=name.strip(), mods=[modality], group="full",
                             measure=measure)


def save(db, loaded: Loaded, modality: str = "strength", keep: bool = True) -> str:
    """Grava o treino na modalidade (visível na lista se `keep`, senão só para a sessão)."""
    from . import gym
    items = []
    for r in loaded.rows:
        eid = resolve_exercise(db, r.name, modality, "time" if r.time else "reps")
        items.append({"exercise_id": eid, "sets": r.sets, "reps": r.reps, "load_kg": r.load_kg,
                      "rpe": r.rpe, "rest_s": r.rest_s, "notes": r.notes})
    return gym.save_plan(db, None, loaded.name, None, items, modality, hidden=not keep)
