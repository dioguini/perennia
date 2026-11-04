"""Onde ficam os dados da Perennia (sem precisar da janela nem do pyglet:
a linha de comandos dos backups usa isto)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def default_data_dir() -> Path:
    """Pasta de dados por omissão, respeitando as convenções do sistema."""
    env = os.environ.get("PERENNIA_DATA_DIR") or os.environ.get("VELO_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or str(Path.home()))
        new, old = base / "Perennia", base / "VeloLocal"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        new, old = base / "Perennia", base / "VeloLocal"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
        new, old = base / "perennia", base / "velolocal"
    # A aplicação chamava-se VeloLocal: se os teus dados ainda estão na pasta
    # antiga, continua a usá-la (os caminhos dos .fit gravados apontam para lá).
    if not new.exists() and old.exists():
        return old
    return new


def database_path(data_dir: Path) -> Path:
    """perennia.db; uma base antiga (velolocal.db) é renomeada uma vez."""
    new, old = data_dir / "perennia.db", data_dir / "velolocal.db"
    if not new.exists() and old.exists():
        try:
            old.rename(new)
        except OSError:
            return old
    return new


def data_dir_for(arg: str | None) -> Path:
    """A pasta de dados: a que vier da linha de comandos, ou a de sempre."""
    d = Path(arg).expanduser() if arg else default_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
