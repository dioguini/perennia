"""As pastas da Perennia: tudo numa só pasta, `data/`, na raiz do projeto (ao lado do `main.py`;
num executável, ao lado do `.exe`).

    data/
      perennia.db                a base de dados (o estado da aplicação)
      in/                        o que a Perennia **lê** — põe aqui os ficheiros a importar
        gpx/                     rotas (.gpx)
        treinos/                 treinos (.zwo .erg .mrc .fit; ginásio: .csv .json .txt)
        planos/                  planos de treino (.perennia-plan.csv / .json)
        csv/                     conjuntos .csv (artigos, exercícios, saúde, glossário…)
        atividades/              upload manual de uma atividade (.fit .tcx)
        analises/                análises clínicas (.xlsx .csv)
        hrv4training/            o export da app HRV4Training (.csv)
        trainingpeaks/           o .csv de atividades do TrainingPeaks
        historico/               históricos de atividades (TrainingPeaks, Strava, Garmin)
        backups/                 backups a repor (.zip)
      out/                       o que a Perennia **grava**
        sessoes/<desporto>/      o .fit de cada sessão (ciclismo, remo, corrida, natacao,
                                 ginasio)
        treinos/                 treinos exportados
        planos/                  planos exportados
        csv/                     modelos e exportações em .csv
        powerbi/                 o modelo para o Power BI
        backups/                 os backups que fazes (e as cópias antes de repor)
        relatorios/              as exportações da Análise AdHoc
      garmin/
        config/                  a configuração do GarminDB (sem palavra-passe) e o token de
                                 sessão que o próprio GarminDB guarda
        bases/                   o que o GarminDB descarrega (DBs/garmin.db, …)

As listas de importação só procuram na pasta `in/` certa; arrastar um ficheiro para a janela
continua a funcionar com um ficheiro de qualquer sítio. Não há pastas configuráveis.

`data_dir` é sempre a pasta `data/` (ou a de `--data-dir`, ou a de `PERENNIA_DATA_DIR`).
Sem janela nem pyglet: serve também a linha de comandos.
"""
from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from .i18n import tr

# chave → pasta dentro de in/
IN: dict[str, str] = {
    "gpx": "gpx", "workouts": "treinos", "plans": "planos", "csv": "csv",
    "activities": "atividades", "labs": "analises", "hrv4training": "hrv4training",
    "trainingpeaks": "trainingpeaks", "history": "historico", "backups": "backups"}
# chave → pasta dentro de out/
OUT: dict[str, str] = {
    "sessions": "sessoes", "workouts": "treinos", "plans": "planos", "csv": "csv",
    "powerbi": "powerbi", "backups": "backups", "reports": "relatorios"}
# desporto → pasta dentro de out/sessoes/
SPORT_DIRS: dict[str, str] = {"cycling": "ciclismo", "rowing": "remo", "running": "corrida",
                              "swimming": "natacao", "gym": "ginasio", "strength": "ginasio"}

NAMES_IN = {"gpx": ("Rotas (.gpx)", "Routes (.gpx)"),
            "workouts": ("Treinos a importar", "Workouts to import"),
            "plans": ("Planos a importar", "Plans to import"),
            "csv": ("Conjuntos .csv a importar", ".csv sets to import"),
            "activities": ("Atividades (.fit, .tcx)", "Activities (.fit, .tcx)"),
            "labs": ("Análises clínicas", "Lab results"),
            "hrv4training": ("HRV4Training", "HRV4Training"),
            "trainingpeaks": ("TrainingPeaks", "TrainingPeaks"),
            "history": ("Históricos de atividades", "Activity histories"),
            "backups": ("Backups a repor", "Backups to restore")}
NAMES_OUT = {"sessions": ("Sessões (.fit)", "Sessions (.fit)"),
             "workouts": ("Treinos exportados", "Exported workouts"),
             "plans": ("Planos exportados", "Exported plans"),
             "csv": ("Modelos e exportações .csv", ".csv templates and exports"),
             "powerbi": ("Power BI", "Power BI"),
             "backups": ("Backups feitos", "Backups made"),
             "reports": ("Relatórios (AdHoc)", "Reports (AdHoc)")}

# A pasta de dados em uso (posta pela aplicação e pela linha de comandos ao arrancar). As funções
# que não recebem `data_dir` usam esta.
_ROOT: Path | None = None


def set_root(data_dir: Path | str) -> None:
    global _ROOT
    _ROOT = Path(data_dir)


def root(data_dir: Path | str | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    if _ROOT is not None:
        return _ROOT
    from perennia.datadir import default_data_dir
    return default_data_dir()


def _make(p: Path, create: bool) -> Path:
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def in_dir(key: str, data_dir: Path | str | None = None, create: bool = True) -> Path:
    """`data/in/<pasta>`: onde a Perennia procura os ficheiros a importar desse tipo."""
    return _make(root(data_dir) / "in" / IN[key], create)


def out_dir(key: str, data_dir: Path | str | None = None, create: bool = True) -> Path:
    """`data/out/<pasta>`: onde a Perennia grava o que exporta desse tipo."""
    return _make(root(data_dir) / "out" / OUT[key], create)


def session_dir(sport: str, data_dir: Path | str | None = None, create: bool = True) -> Path:
    """`data/out/sessoes/<desporto>`: o .fit de cada sessão."""
    return _make(root(data_dir) / "out" / OUT["sessions"] / SPORT_DIRS.get(sport, sport),
                 create)


def garmin_config_dir(data_dir: Path | str | None = None, create: bool = True) -> Path:
    return _make(root(data_dir) / "garmin" / "config", create)


def garmin_bases_dir(data_dir: Path | str | None = None, create: bool = True) -> Path:
    return _make(root(data_dir) / "garmin" / "bases", create)


def name_in(key: str) -> str:
    return tr(*NAMES_IN[key])


def name_out(key: str) -> str:
    return tr(*NAMES_OUT[key])


def shown(p: Path, data_dir: Path | str | None = None) -> str:
    """Um caminho para mostrar: relativo à pasta de dados («data/in/gpx»), se estiver lá dentro."""
    base = root(data_dir)
    try:
        return str(PurePosixPath(base.name, *Path(p).resolve().relative_to(
            base.resolve()).parts))
    except (ValueError, OSError):
        return str(p)


# ----------------------------------------------------------------- criar tudo


def templates_dir() -> Path:
    """Os modelos que vêm com a aplicação (copiados para data/in na primeira vez)."""
    from perennia import paths
    return paths.resource("modelos")


def ensure_tree(data_dir: Path | str | None = None, copy_templates: bool = True) -> list[Path]:
    """Cria a estrutura toda (idempotente). Na primeira vez, copia os modelos que vêm com a
    aplicação para `data/in/…` (um ficheiro que já existe nunca é substituído). Devolve os
    ficheiros copiados."""
    base = root(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    for k in IN:
        in_dir(k, base)
    for k in OUT:
        out_dir(k, base)
    for sport in dict.fromkeys(SPORT_DIRS.values()):
        (base / "out" / OUT["sessions"] / sport).mkdir(parents=True, exist_ok=True)
    garmin_config_dir(base)
    garmin_bases_dir(base)
    copied: list[Path] = []
    src = templates_dir()
    if copy_templates and src.is_dir():
        for f in sorted(src.rglob("*")):
            if not f.is_file():
                continue
            dst = base / f.relative_to(src)
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            copied.append(dst)
    return copied


# ------------------------------------------------- caminhos das versões antigas

# a pasta antiga (relativa à pasta de dados de antes) → a nova
LEGACY_DIRS: dict[str, str] = {
    "rides": "out/sessoes/ciclismo", "rowing": "out/sessoes/remo",
    "strength": "out/sessoes/ginasio", "exports": "out/treinos", "backups": "out/backups",
    "imports": "in/atividades", "workouts": "in/treinos", "gpx": "in/gpx"}


def relocate(rel: str) -> str:
    """Um caminho relativo da organização antiga («rides/x.fit») na nova
    («out/sessoes/ciclismo/x.fit»). Os da organização nova ficam como estão. Na pasta antiga
    `endurance/` estavam a corrida e a natação: o nome do ficheiro diz qual."""
    p = PurePosixPath(str(rel).replace("\\", "/"))
    if not p.parts:
        return str(rel)
    head = p.parts[0]
    if head == "endurance":
        sport = "natacao" if "natacao" in p.name.lower() or "swim" in p.name.lower() \
            else "corrida"
        return str(PurePosixPath("out", "sessoes", sport, *p.parts[1:]))
    if head == "imports" and len(p.parts) >= 2:
        return str(PurePosixPath("in", _import_kind(p.name), *p.parts[1:]))
    if head in LEGACY_DIRS:
        return str(PurePosixPath(LEGACY_DIRS[head], *p.parts[1:]))
    return str(p)


def _import_kind(name: str) -> str:
    """A antiga pasta `imports` tinha de tudo: cada ficheiro vai para a pasta `in/` do seu
    tipo (pela extensão e pelo nome)."""
    low = name.lower()
    suf = PurePosixPath(low).suffix
    if suf in (".fit", ".tcx"):
        return IN["activities"]
    if suf in (".xlsx", ".xlsm"):
        return IN["labs"]
    if "hrv" in low or "measurement" in low:
        return IN["hrv4training"]
    if "regras" in low or "rules" in low:
        return IN["history"]
    if low.endswith((".perennia-plan.json", ".perennia-plan.csv")):
        return IN["plans"]
    return IN["csv"]
