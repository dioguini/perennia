"""Onde está a aplicação, quer corra como script quer como executável.

Com o PyInstaller, `__file__` aponta para uma pasta temporária ou interna.
A pasta `data/` (os teus dados, ver `perennia.core.folders`) fica ao lado
do executável; os recursos embutidos (os `modelos/`, o .gpx do autoteste)
ficam em `sys._MEIPASS`.
"""
from __future__ import annotations

import sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Pasta do executável, ou a raiz do projeto quando corre com Python."""
    if frozen():
        exe = Path(sys.executable).resolve()
        # macOS: …/Perennia.app/Contents/MacOS/Perennia → pasta onde está a .app
        if exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents":
            return exe.parents[3]
        return exe.parent
    return Path(__file__).resolve().parents[1]


def resource(*parts: str) -> Path:
    """Ficheiro embutido no pacote (ou no projeto, em desenvolvimento)."""
    base = Path(getattr(sys, "_MEIPASS", app_dir()))
    return base.joinpath(*parts)
