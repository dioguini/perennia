"""Onde ficam os dados da Perennia (sem precisar da janela nem do pyglet:
a linha de comandos dos backups usa isto)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import legacy


def default_data_dir() -> Path:
    """Pasta de dados por omissão, respeitando as convenções do sistema."""
    env = os.environ.get("PERENNIA_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or str(Path.home()))
        new = base / "Perennia"
    elif sys.platform == "darwin":
        new = Path.home() / "Library" / "Application Support" / "Perennia"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
        new = base / "perennia"
    # Quem tem os dados da versão anterior: a pasta é renomeada uma vez (ver legacy.py).
    return legacy.adopt_previous_dir(new)


def database_path(data_dir: Path) -> Path:
    """perennia.db (uma base da versão anterior é renomeada uma vez; ver legacy.py)."""
    return legacy.adopt_previous_db(data_dir, "perennia.db")


def data_dir_for(arg: str | None) -> Path:
    """A pasta de dados: a que vier da linha de comandos, ou a de sempre."""
    d = Path(arg).expanduser() if arg else default_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
