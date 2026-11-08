"""Sincronização por CSV: artigos, exercícios, grupos/subgrupos musculares, disciplinas,
testes de aptidão e os tipos de material.

Para cada conjunto há um **modelo** (.csv com o cabeçalho e uma linha de exemplo),
a **exportação** do que tens e a **importação** (cria o que falta e atualiza o que já
existe, pelo nome — sem distinguir maiúsculas nem acentos). Os ficheiros são UTF-8, com
`;` a separar colunas (o Excel português abre-os logo); na importação também se aceita
`,` e `\\t`. Dentro de uma célula, listas separam-se com `|` (ex.: `Força|Isométrico`).
"""
from __future__ import annotations

import csv
import io
import unicodedata
from dataclasses import dataclass

from . import fitness_tests as ft
from . import gym, inventory, muscles
from .i18n import tr

DELIM = ";"


def _fold(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().strip()


def _num(text) -> float | None:
    s = str(text or "").strip().replace("€", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _list(text) -> list[str]:
    return [x.strip() for x in str(text or "").replace(",", "|").split("|") if x.strip()]


@dataclass
class Dataset:
    key: str
    pt: str
    en: str
    columns: tuple[str, ...]
    example: tuple
    export: object          # (db) -> list[list]
    importer: object | None  # (db, rows: list[dict]) -> Report
    help_pt: str = ""
    help_en: str = ""

    @property
    def label(self) -> str:
        return tr(self.pt, self.en)

    @property
    def help(self) -> str:
        return tr(self.help_pt, self.help_en)


class Report(dict):
    def __init__(self):
        super().__init__(created=0, updated=0, skipped=0, errors=[])

    def text(self) -> str:
        t = tr("{c} criados · {u} atualizados · {s} ignorados",
               "{c} created · {u} updated · {s} skipped",
               c=self["created"], u=self["updated"], s=self["skipped"])
        if self["errors"]:
            t += " · " + self["errors"][0]
        return t


# ------------------------------------------------------------------ artigos

KIND_BY_NAME: dict = {}


def _kind_key(text: str) -> str:
    low = _fold(text)
    if not KIND_BY_NAME:
        for k, (pt, en, _g) in inventory.KINDS.items():
            for n in (k, pt, en):
                KIND_BY_NAME[_fold(n)] = k
    return KIND_BY_NAME.get(low, "other")


def _export_items(db) -> list[list]:
    return [[r["name"], inventory.kind_name(r["kind"]), r["qty"], r["weight_kg"] or "",
             r["notes"] or "", r.get("purchase_date") or "", r.get("purchase_price") or ""]
            for r in inventory.items(db)]


def _import_items(db, rows: list[dict]) -> Report:
    rep = Report()
    have = {(_fold(r["name"]), r["kind"]): r["id"] for r in inventory.items(db)}
    for n, row in enumerate(rows, start=2):
        name = (row.get("nome") or "").strip()
        if not name:
            rep["skipped"] += 1
            continue
        kind = _kind_key(row.get("tipo") or "")
        qty = int(_num(row.get("quantidade")) or 1)
        iid = have.get((_fold(name), kind))
        inventory.save(db, iid, name=name, kind=kind, qty=qty, weight_kg=_num(row.get("peso_kg")),
                       notes=(row.get("notas") or "").strip() or None,
                       purchase_date=(row.get("data_compra") or "").strip() or None,
                       purchase_price=_num(row.get("preco_compra")))
        rep["updated" if iid else "created"] += 1
    return rep


# --------------------------------------------------------------- exercícios


def _export_exercises(db) -> list[list]:
    out = []
    for e in gym.exercises(db):
        out.append([e["name"], muscles.group_name(db, e["category"]),
                    "" if not e.get("subgroup_id") else muscles.subgroup_name(db, e["subgroup_id"]),
                    "tempo" if e["measure"] == "time" else "reps", e["bodyweight"] or 0,
                    "|".join(gym.modality(m).name for m in e["modalities"]),
                    "|".join(inventory.kind_name(k) for k in e["equipment"]),
                    e.get("description") or ""])
    return out


def _group_key(db, name: str, create: bool = True) -> str | None:
    low = _fold(name)
    for g in muscles.groups(db):
        if low in (_fold(g["key"]), _fold(g["name_pt"]), _fold(g["name_en"])):
            return g["key"]
    return muscles.add_group(db, name) if create and name.strip() else None


def _subgroup_id(db, group_key: str, name: str) -> int | None:
    if not name.strip():
        return None
    low = _fold(name)
    for g in muscles.groups(db):
        if g["key"] == group_key:
            for s in g["subgroups"]:
                if low in (_fold(s["name_pt"]), _fold(s["name_en"])):
                    return s["id"]
    return muscles.add_subgroup(db, group_key, name)


def _modality_key(db, name: str) -> str | None:
    low = _fold(name)
    for m in gym.modalities():
        if low in (_fold(m.key), _fold(m.pt), _fold(m.en)):
            return m.key
    return gym.add_discipline(db, name) if name.strip() else None


def _import_exercises(db, rows: list[dict]) -> Report:
    rep = Report()
    gym.ensure(db)
    have = {_fold(e["name"]): e for e in gym.exercises(db, include_archived=True)}
    for n, row in enumerate(rows, start=2):
        name = (row.get("nome") or "").strip()
        if not name:
            rep["skipped"] += 1
            continue
        group = _group_key(db, row.get("grupo") or "") or "full"
        sub = _subgroup_id(db, group, row.get("subgrupo") or "")
        mods = [m for m in (_modality_key(db, x) for x in _list(row.get("modalidades"))) if m]
        kit = [_kind_key(x) for x in _list(row.get("material"))]
        old = have.get(_fold(name))
        bw = _num(row.get("peso_corpo")) or 0.0
        gym.save_exercise(
            db, old["id"] if old else None, name=name, mods=mods or (old or {}).get(
                "modalities") or ["strength"], group=group,
            measure="time" if _fold(row.get("medida")) in ("tempo", "time", "s") else "reps",
            bodyweight=bw / 100.0 if bw > 1 else bw, equipment=kit,
            description=(row.get("descricao") or "").strip() or None, subgroup=sub)
        rep["updated" if old else "created"] += 1
    return rep


# ------------------------------------------------------ grupos musculares


def _export_groups(db) -> list[list]:
    out = []
    for g in muscles.groups(db):
        if not g["subgroups"]:
            out.append([g["name_pt"], "", g["name_en"], ""])
        for s in g["subgroups"]:
            out.append([g["name_pt"], s["name_pt"], g["name_en"], s["name_en"]])
    return out


def _import_groups(db, rows: list[dict]) -> Report:
    rep = Report()
    muscles.ensure(db)
    for row in rows:
        g = (row.get("grupo") or "").strip()
        if not g:
            rep["skipped"] += 1
            continue
        key = _group_key(db, g, create=False)
        if key is None:
            key = muscles.add_group(db, g, (row.get("grupo_en") or "").strip() or None)
            rep["created"] += 1
        s = (row.get("subgrupo") or "").strip()
        if s:
            before = _subgroup_id_exists(db, key, s)
            sid = _subgroup_id(db, key, s)
            en = (row.get("subgrupo_en") or "").strip()
            if en and sid:
                muscles.rename_subgroup(db, sid, s, en)
            rep["updated" if before else "created"] += 1
    return rep


def _subgroup_id_exists(db, key: str, name: str) -> bool:
    low = _fold(name)
    return any(low in (_fold(s["name_pt"]), _fold(s["name_en"]))
               for g in muscles.groups(db) if g["key"] == key for s in g["subgroups"])


# ------------------------------------------------------------- disciplinas


def _export_disciplines(db) -> list[list]:
    gym.ensure(db)
    return [[m.pt, m.en] for m in gym.modalities()]


def _import_disciplines(db, rows: list[dict]) -> Report:
    rep = Report()
    gym.ensure(db)
    for row in rows:
        name = (row.get("nome") or "").strip()
        if not name:
            rep["skipped"] += 1
            continue
        low = _fold(name)
        if any(low in (_fold(m.key), _fold(m.pt), _fold(m.en)) for m in gym.modalities()):
            rep["skipped"] += 1
            continue
        gym.add_discipline(db, name, (row.get("nome_en") or "").strip() or None)
        rep["created"] += 1
    return rep


# ------------------------------------------------------------------ testes

SPORTS = ("cycling", "rowing", "running", "swimming", "longevity")


def _export_tests(db) -> list[list]:
    ft.seed(db)
    out = []
    for sport in SPORTS:
        for t_ in ft.tests(db, sport, include_inactive=True):
            out.append([sport, t_["name"], t_["unit"], "menor" if t_["better"] == "lower"
                        else "maior", t_["duration_s"], t_["instructions"] or ""])
    return out


def _import_tests(db, rows: list[dict]) -> Report:
    rep = Report()
    ft.seed(db)
    for row in rows:
        name = (row.get("nome") or "").strip()
        sport = _fold(row.get("desporto"))
        sport = {"ciclismo": "cycling", "remo": "rowing", "corrida": "running",
                 "natacao": "swimming", "longevidade": "longevity"}.get(sport, sport)
        if not name or sport not in SPORTS:
            rep["skipped"] += 1
            continue
        old = next((t_ for t_ in ft.tests(db, sport, include_inactive=True)
                    if _fold(t_["name"]) == _fold(name)), None)
        ft.save_test(db, old["id"] if old else None, sport=sport, name=name,
                     unit=(row.get("unidade") or "").strip() or "reps",
                     better="lower" if _fold(row.get("melhor")) in ("menor", "lower") else "higher",
                     duration_s=int(_num(row.get("duracao_s")) or 0),
                     instructions=(row.get("instrucoes") or "").strip(),
                     protocol=(old or {}).get("protocol"))
        rep["updated" if old else "created"] += 1
    return rep


# --------------------------------------------------------- tipos de material


def _export_kinds(db) -> list[list]:
    return [[k, pt, en, inventory.GROUPS[g][0]] for k, (pt, en, g) in inventory.KINDS.items()]


DATASETS: dict[str, Dataset] = {d.key: d for d in (
    Dataset("artigos", "Artigos (inventário)", "Items (inventory)",
            ("nome", "tipo", "quantidade", "peso_kg", "notas", "data_compra", "preco_compra"),
            ("Kettlebell 16 kg", "Kettlebell", 1, 16, "", "2025-03-01", 45),
            _export_items, _import_items,
            "Cada linha é um artigo. O tipo é o do material (ver «Tipos de material»).",
            "Each row is an item. The type is the equipment kind (see “Equipment kinds”)."),
    Dataset("exercicios", "Exercícios", "Exercises",
            ("nome", "grupo", "subgrupo", "medida", "peso_corpo", "modalidades", "material",
             "descricao"),
            ("Prancha lateral", "Core", "Oblíquos", "tempo", 0, "Isométrico|Força",
             "Tapete", "Aguenta a posição"),
            _export_exercises, _import_exercises,
            "Grupo e subgrupo musculares, modalidades e material por nome (várias com |). "
            "O que não existir é criado.",
            "Muscle group and subgroup, modalities and equipment by name (several with |). "
            "Anything missing is created."),
    Dataset("grupos", "Grupos e subgrupos musculares", "Muscle groups and subgroups",
            ("grupo", "subgrupo", "grupo_en", "subgrupo_en"),
            ("Pernas", "Quadríceps", "Legs", "Quadriceps"),
            _export_groups, _import_groups,
            "Uma linha por subgrupo (o grupo repete-se).",
            "One row per subgroup (the group repeats)."),
    Dataset("disciplinas", "Disciplinas (modalidades de ginásio)", "Disciplines (gym modalities)",
            ("nome", "nome_en"), ("Pilates", "Pilates"),
            _export_disciplines, _import_disciplines,
            "As que não existirem ganham o seu separador na lista de exercícios.",
            "Missing ones get their own tab in the exercise list."),
    Dataset("testes", "Testes de aptidão", "Fitness tests",
            ("desporto", "nome", "unidade", "melhor", "duracao_s", "instrucoes"),
            ("longevidade", "Flexões em 1 minuto", "reps", "maior", 60, "Flexões completas"),
            _export_tests, _import_tests,
            "Desporto: ciclismo, remo, corrida, natação ou longevidade. «Melhor»: maior ou menor.",
            "Sport: cycling, rowing, running, swimming or longevity. “Better”: higher or lower "
            "(maior/menor)."),
    Dataset("material", "Tipos de material", "Equipment kinds",
            ("chave", "nome_pt", "nome_en", "grupo"), ("kettlebell", "Kettlebell", "Kettlebell",
                                                      "Pesos livres"),
            _export_kinds, None,
            "Só para consulta: os tipos que os artigos e os exercícios usam.",
            "Reference only: the kinds that items and exercises use."),
)}


# ----------------------------------------------------------------- ficheiros


def _render(columns, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=DELIM, lineterminator="\r\n")
    w.writerow(columns)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def write(db, key: str, folder, *, what: str = "export") -> str:
    """Grava o modelo (`what="template"`) ou a exportação num ficheiro da pasta; devolve o
    caminho. UTF-8 com BOM, para o Excel abrir bem os acentos."""
    from datetime import date
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if what == "template":
        name, text = f"perennia_modelo_{key}.csv", template(key)
    else:
        name, text = f"perennia_{key}_{date.today().isoformat()}.csv", export_csv(db, key)
    path = folder / name
    path.write_text(text, encoding="utf-8-sig", newline="")
    return str(path)


def import_file(db, path, key: str | None = None) -> tuple[str, Report]:
    """Importa um ficheiro; sem `key`, descobre o conjunto pelo cabeçalho."""
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    key = key or detect(text)
    if key is None:
        raise ValueError(tr("Não reconheço as colunas deste .csv (usa um dos modelos).",
                            "I don't recognise this .csv's columns (use one of the templates)."))
    return key, import_csv(db, key, text)


def template(key: str) -> str:
    d = DATASETS[key]
    return _render(d.columns, [d.example])


def export_csv(db, key: str) -> str:
    d = DATASETS[key]
    return _render(d.columns, d.export(db))


def parse(text: str) -> tuple[list[str], list[dict]]:
    text = text.lstrip("﻿")
    head = text.splitlines()[0] if text.strip() else ""
    delim = max((";", ",", "\t"), key=head.count) if head else DELIM
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return [], []
    cols = [_fold(c).replace(" ", "_") for c in rows[0]]
    return cols, [dict(zip(cols, r)) for r in rows[1:] if any(c.strip() for c in r)]


def detect(text: str) -> str | None:
    """Que conjunto é, pelo cabeçalho (as colunas obrigatórias do conjunto)."""
    cols, _rows = parse(text)
    best, score = None, 0
    for key, d in DATASETS.items():
        if d.importer is None:
            continue
        need = set(d.columns[:2] if key in ("grupos", "artigos") else d.columns[:1])
        if key == "testes":
            need = {"desporto", "nome"}
        if key == "disciplinas":
            need = {"nome"}
        if need <= set(cols):
            s = len(set(cols) & set(d.columns))
            if s > score:
                best, score = key, s
    return best


def import_csv(db, key: str, text: str) -> Report:
    d = DATASETS[key]
    if d.importer is None:
        rep = Report()
        rep["errors"].append(tr("Este conjunto é só de consulta.",
                                "This set is for reference only."))
        return rep
    _cols, rows = parse(text)
    return d.importer(db, rows)
