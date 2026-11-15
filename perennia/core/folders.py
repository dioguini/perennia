"""As pastas que a Perennia usa (exportar, importar, backups, treinos e rotas), configuráveis.

Por omissão ficam dentro da pasta de dados (`exports/`, `imports/`, `backups/`), e os treinos
(`workouts/`) e as rotas (`gpx/`) ao lado da aplicação. Em Definições → Pastas podes pôr outra
(um disco externo, a pasta do Dropbox…): uma pasta vazia quer dizer «a de sempre». Uma pasta que
não existe é criada; se não der (sem permissões, disco desligado), usa-se a de sempre e a
Perennia diz porquê.

* **exports** — o que exportas (treinos, planos, CSV…);
* **imports** — onde se procuram os ficheiros a importar (a pasta de sempre continua a contar);
* **backups** — onde se gravam e procuram os backups;
* **workouts** — onde se guardam e procuram os treinos e planos em ficheiro;
* **gpx** — onde se procuram as rotas.

Sem janela nem pyglet: serve também a linha de comandos.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import options
from .db import Database
from .i18n import tr

KEYS = ("exports", "imports", "backups", "workouts", "gpx")

OPTION = {"exports": "path_exports", "imports": "path_imports", "backups": "path_backups",
          "workouts": "path_workouts", "gpx": "path_gpx"}

NAMES = {"exports": ("Exportações", "Exports"), "imports": ("Importações", "Imports"),
         "backups": ("Backups", "Backups"), "workouts": ("Treinos e planos", "Workouts and plans"),
         "gpx": ("Rotas (.gpx)", "Routes (.gpx)")}


def name(key: str) -> str:
    pt, en = NAMES[key]
    return tr(pt, en)


def configured(db: Database | None, key: str) -> str:
    """O que está escrito nas Definições (vazio = a de sempre)."""
    if db is None:
        return ""
    try:
        return str(options.get(db, OPTION[key]) or "").strip()
    except Exception:
        return ""


def _expand(text: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(text)))


def expand_text(text: str) -> str:
    """O caminho como a Perennia o usa (com ~ e variáveis resolvidos)."""
    return str(_expand(text))


def default(data_dir: Path | str | None, key: str) -> Path:
    """A pasta de sempre: dentro da pasta de dados (exports, imports, backups, workouts) ou ao
    lado da aplicação (gpx)."""
    if key == "gpx":
        from .. import paths
        return paths.app_dir() / key
    return Path(data_dir or ".") / key


def resolve(db: Database | None, data_dir: Path | str | None, key: str) -> Path:
    """A pasta a usar: a das Definições se estiver escolhida e utilizável, senão a de sempre.
    Não cria nada (ver `ensure_dir`)."""
    text = configured(db, key)
    if text:
        p = _expand(text)
        if p.is_dir() or not p.exists():
            return p
    return default(data_dir, key)


def ensure_dir(db: Database | None, data_dir: Path | str | None, key: str) -> Path:
    """Como `resolve`, mas cria a pasta; se não conseguir criar a escolhida, cai na de sempre."""
    p = resolve(db, data_dir, key)
    try:
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        d = default(data_dir, key)
        d.mkdir(parents=True, exist_ok=True)
        return d


def extra(db: Database | None, key: str) -> list[str]:
    """A pasta escolhida, como pasta **a mais** onde procurar (vazio se não houver)."""
    text = configured(db, key)
    return [str(_expand(text))] if text else []


def search_list(db: Database | None, data_dir: Path | str | None, key: str,
                others: list[str] | None = None) -> list[str]:
    """As pastas onde procurar: a escolhida primeiro, depois as de sempre (sem repetir)."""
    out: list[str] = []
    for p in extra(db, key) + [str(x) for x in (others or [])]:
        if p not in out:
            out.append(p)
    return out


def check(text: str) -> tuple[bool, str]:
    """Está utilizável? (existe ou pode ser criada, e dá para escrever). Devolve (ok, porquê)."""
    text = (text or "").strip()
    if not text:
        return True, tr("a de sempre", "the usual one")
    p = _expand(text)
    if p.exists() and not p.is_dir():
        return False, tr("não é uma pasta", "not a folder")
    probe = p if p.exists() else next((q for q in p.parents if q.exists()), None)
    if probe is None:
        return False, tr("o disco ou a pasta de cima não existe", "the drive or parent folder "
                         "does not exist")
    if not probe.is_dir():                       # uma «pasta de cima» que é um ficheiro
        return False, tr("o caminho passa por um ficheiro", "the path goes through a file")
    if not os.access(probe, os.W_OK):
        return False, tr("sem permissão para escrever", "no permission to write")
    return True, tr("existe", "exists") if p.exists() else tr("vai ser criada", "will be created")


def describe(db: Database | None, data_dir: Path | str | None, key: str) -> str:
    """A pasta que está mesmo a ser usada, para mostrar nas Definições."""
    return str(resolve(db, data_dir, key))
