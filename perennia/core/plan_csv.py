"""Planos de treino de X semanas em **CSV** (folha de cálculo), além do JSON.

O JSON continua a ser o formato completo (`programs.py`): séries com valores por série,
rampas, 1RM, etc. O CSV é a via fácil: preenches uma tabela no Excel/LibreOffice, com uma linha
por exercício de cada sessão, e a Perennia converte-a no mesmo plano (e valida-o do mesmo jeito).

Ficheiro (UTF-8, separado por `;` ou `,`):

```
# nome: StrongLifts 5x5
# semanas: 12
# dias_por_semana: 3
# dias_da_semana: 1,3,5
# rotacao: A,B
sessao;nome_sessao;exercicio;grupo;series;reps;descanso_s;carga_kg;pct1rm;adiciona_kg;por;nota
A;Treino A;Agachamento com barra;legs;5;5;180;;;2.5;session;
A;Treino A;Supino com barra;chest;5;5;180;;;2.5;session;
B;Treino B;Agachamento com barra;legs;5;5;180;;;2.5;session;
```

As linhas que começam por `#` são os dados do plano (`nome`, `semanas`, `dias_por_semana`,
`dias_da_semana` — 1 = segunda —, `rotacao` ou `semana N`, `categoria`, `nivel`, `descricao`,
`autor`, `fonte`, `material`). Uma célula com `|` tem **um valor por semana** (`70|75|80`: o
último repete-se). Nas repetições vale `8-12`, `5+` e `max`. Colunas: sessao, nome_sessao,
exercicio, grupo, series, reps, descanso_s, carga_kg, pct1rm, rpe, rir, tempo_s, adiciona_kg,
por (`session` ou `week`), pct_inicial, nota. Os nomes em inglês também servem (session, exercise,
group, sets, rest, load, add_kg, per, start_pct, notes).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from . import programs
from .i18n import tr

EXT = ".perennia-plan.csv"

META = {"nome": "name", "name": "name", "categoria": "category", "category": "category",
        "nivel": "level", "level": "level", "semanas": "weeks", "weeks": "weeks",
        "dias_por_semana": "days_per_week", "days_per_week": "days_per_week",
        "dias_da_semana": "weekdays", "weekdays": "weekdays", "descricao": "description",
        "description": "description", "autor": "author", "author": "author", "fonte": "source",
        "source": "source", "material": "equipment", "equipment": "equipment",
        "rotacao": "rotation", "rotation": "rotation"}

COLUMNS = {"sessao": "session", "session": "session", "nome_sessao": "session_name",
           "session_name": "session_name", "exercicio": "exercise", "exercise": "exercise",
           "grupo": "group", "group": "group", "series": "sets", "sets": "sets",
           "reps": "reps", "descanso_s": "rest", "rest": "rest", "carga_kg": "load",
           "load": "load", "pct1rm": "pct1rm", "rpe": "rpe", "rir": "rir", "tempo_s": "time",
           "time": "time", "adiciona_kg": "add_kg", "add_kg": "add_kg", "por": "per",
           "per": "per", "pct_inicial": "start_pct", "start_pct": "start_pct",
           "nota": "notes", "notes": "notes"}

HEADER = ["sessao", "nome_sessao", "exercicio", "grupo", "series", "reps", "descanso_s",
          "carga_kg", "pct1rm", "adiciona_kg", "por", "nota"]


def _num(text: str):
    """Um número, ou uma lista (um por semana, separada por |); texto fica como está
    (`8-12`, `5+`, `max`)."""
    text = text.strip()
    if "|" in text:
        return [_num(x) for x in text.split("|") if x.strip()]
    try:
        f = float(text.replace(",", "."))
        return int(f) if f == int(f) else f
    except ValueError:
        return text


def _rows(text: str) -> tuple[list[list[str]], str]:
    sample = text[:2000]
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    return ([[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)
             if any(c.strip() for c in r)], delim)


def parse(text: str) -> dict:
    """Converte o texto do CSV num plano (já validado). Levanta `programs.PlanError`."""
    rows, delim = _rows(text.lstrip("\ufeff"))
    meta: dict[str, str] = {}
    weeks_map: dict[int, list[str]] = {}
    table: list[list[str]] = []
    for r in rows:
        first = r[0]
        if first.startswith("#"):
            first = delim.join(r)          # o texto de um «# campo: valor» pode ter o separador
            body = first.lstrip("#").strip()
            if ":" in body:
                k, v = body.split(":", 1)
            else:
                k, v = body, ""
            k = k.strip().lower().replace(" ", "_")
            if k.startswith(("semana_", "week_")) and k.split("_", 1)[1].isdigit():
                weeks_map[int(k.split("_", 1)[1])] = [x.strip() for x in v.split(",") if x.strip()]
            elif k in META:
                meta[META[k]] = v.strip()
            continue
        table.append(r)
    if not table:
        raise programs.PlanError(tr("o CSV não tem a tabela dos exercícios",
                                    "the CSV has no exercise table"))
    head = [COLUMNS.get(h.lower().replace(" ", "_"), "") for h in table[0]]
    for need in ("session", "exercise"):
        if need not in head:
            raise programs.PlanError(tr("falta a coluna «{c}» na tabela",
                                        "the table has no '{c}' column",
                                        c="sessao" if need == "session" else "exercicio"))
    exercises: dict[str, dict] = {}
    sessions: dict[str, dict] = {}
    for n, r in enumerate(table[1:], 2):
        row = {h: r[i] if i < len(r) else "" for i, h in enumerate(head) if h}
        skey, ex = row.get("session", "").strip(), row.get("exercise", "").strip()
        if not skey or not ex:
            continue
        ekey = programs.slug(ex)
        if ekey not in exercises:
            exercises[ekey] = {"name": ex, "group": (row.get("group") or "full").strip() or "full"}
        sess = sessions.setdefault(skey, {"name": row.get("session_name") or skey, "blocks": []})
        if row.get("session_name") and sess["name"] == skey:
            sess["name"] = row["session_name"]
        entry: dict = {"exercise": ekey}
        for f in ("sets", "reps", "rest", "load", "pct1rm", "rpe", "rir", "time", "add_kg",
                  "start_pct"):
            if row.get(f, "") != "":
                entry[f] = _num(row[f])
        if row.get("per"):
            entry["per"] = row["per"].strip().lower()
        if row.get("notes"):
            entry["notes"] = row["notes"]
        if "sets" not in entry:
            entry["sets"] = 1
        sess["blocks"].append(entry)
    if not sessions:
        raise programs.PlanError(tr("o CSV não tem nenhuma linha de exercício",
                                    "the CSV has no exercise rows"))
    plan: dict = {"format": programs.FORMAT, "version": programs.VERSION,
                  "name": meta.get("name") or "Plano", "exercises": exercises,
                  "sessions": sessions,
                  "weeks": _num(meta.get("weeks") or "4")}
    for k in ("category", "level", "description", "author", "source"):
        if meta.get(k):
            plan[k] = meta[k]
    if meta.get("equipment"):
        plan["equipment"] = [x.strip() for x in meta["equipment"].split(",") if x.strip()]
    if meta.get("weekdays"):
        plan["weekdays"] = [int(x) for x in meta["weekdays"].replace(";", ",").split(",")
                            if x.strip().isdigit()]
    if weeks_map:
        last = max(weeks_map)
        plan["schedule"] = [weeks_map.get(w) or weeks_map.get(w - 1) or weeks_map[last]
                            for w in range(1, int(plan["weeks"]) + 1)]
    else:
        plan["rotation"] = ([x.strip() for x in meta["rotation"].split(",") if x.strip()]
                            if meta.get("rotation") else list(sessions))
    if meta.get("days_per_week"):
        plan["days_per_week"] = _num(meta["days_per_week"])
    return programs.validate(plan)


def read_file(path: Path | str, max_kb: int = 512) -> dict:
    path = Path(path)
    try:
        if path.stat().st_size > max_kb * 1024:
            raise programs.PlanError(tr("o ficheiro é grande demais (máximo {n} kB)",
                                        "the file is too large (max {n} kB)", n=max_kb))
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise programs.PlanError(tr("não consegui ler o ficheiro: {e}", "could not read the "
                                    "file: {e}", e=str(e)[:100])) from None
    return parse(text)


def export_text(plan: dict, sep: str = ";") -> str:
    """O plano em CSV (só o que cabe no formato simples: valores por exercício, não por série)."""
    plan = programs.validate({k: v for k, v in plan.items() if k not in ("key", "origin")})
    out = io.StringIO()
    w = csv.writer(out, delimiter=sep, lineterminator="\n")

    def meta(k, v):
        if v not in (None, "", []):
            w.writerow([f"# {k}: {v}"])
    meta("nome", plan["name"])
    meta("categoria", plan.get("category"))
    meta("nivel", plan.get("level"))
    meta("semanas", plan.get("weeks"))
    meta("dias_por_semana", plan.get("days_per_week"))
    meta("dias_da_semana", ",".join(str(d) for d in plan.get("weekdays") or []))
    meta("material", ",".join(plan.get("equipment") or []))
    meta("autor", plan.get("author"))
    meta("fonte", plan.get("source"))
    meta("descricao", (plan.get("description") or "").replace("\n", " "))
    if plan.get("rotation"):
        meta("rotacao", ",".join(plan["rotation"]))
    for wk, names in enumerate(plan.get("schedule") or [], 1):
        meta(f"semana {wk}", ",".join(names))
    w.writerow(HEADER)

    def cell(v):
        if isinstance(v, list):
            return "|".join(str(x) for x in v)
        return "" if v is None else v
    for skey, s in plan["sessions"].items():
        for blk in s["blocks"]:
            for b in blk.get("exercises") or [blk]:      # o plano validado agrupa em blocos
                ex = plan["exercises"].get(b.get("exercise"), {})
                sets = b.get("sets")
                if isinstance(sets, list) and sets and isinstance(sets[0], dict):
                    sets = len(sets)              # as séries por série só existem no JSON
                w.writerow([skey, s.get("name", skey), ex.get("name", b.get("exercise")),
                            ex.get("group", ""), cell(sets), cell(b.get("reps")),
                            cell(b.get("rest")), cell(b.get("load")), cell(b.get("pct1rm")),
                            cell(b.get("add_kg")), cell(b.get("per")), b.get("notes") or ""])
    return out.getvalue()


def write_template(folder: Path | str) -> Path:
    """Escreve um plano de exemplo em CSV (sem substituir um que já exista)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("plano-modelo" + EXT)
    n = 2
    while path.exists():
        path = folder / f"plano-modelo-{n}{EXT}"
        n += 1
    sample = ("# nome: O meu plano (modelo CSV)\n# categoria: strength\n# nivel: beginner\n"
              "# semanas: 4\n# dias_por_semana: 3\n# dias_da_semana: 1,3,5\n# rotacao: A,B\n"
              "# descricao: Duas sessões que alternam; sobe 2,5 kg de cada vez.\n"
              + ";".join(HEADER) + "\n"
              "A;Treino A;Agachamento com barra;legs;5;5;180;;;2.5;session;\n"
              "A;Treino A;Supino com barra;chest;5;5;180;;;2.5;session;\n"
              "A;Treino A;Remada com barra;back;5;5;120;;;2.5;session;\n"
              "B;Treino B;Agachamento com barra;legs;5;5;180;;;2.5;session;\n"
              "B;Treino B;Press militar;shoulders;5;5;180;;;2.5;session;\n"
              "B;Treino B;Peso morto;hips;1;5;180;;;5;session;\n")
    path.write_text(sample, encoding="utf-8")
    return path
