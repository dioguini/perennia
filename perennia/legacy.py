"""Migração, uma só vez, de quem ainda tem os dados da versão anterior da aplicação.

É o ÚNICO sítio do código que conhece os nomes antigos (pasta e base de dados da versão
anterior). Quando já abriste a Perennia uma vez com os teus dados, tudo está migrado e este
ficheiro pode ser apagado (os dois pontos de chamada são `datadir.py` e `core/db.py`).

O que faz, sempre sem apagar nada:
* a pasta de dados antiga passa a ter o nome novo (renomear dentro da mesma pasta-mãe é uma
  operação atómica; se falhar, a aplicação continua a usar a pasta antiga — nunca perde dados);
* a base de dados antiga passa a `perennia.db`;
* os caminhos dos `.fit` e das caches gravados na base de dados passam a apontar para a pasta
  nova (idempotente: só mexe no que ainda tem o nome antigo);
* a origem «velolocal» dos treinos da biblioteca passa a «perennia».
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

OLD_DIR_NAMES = ("VeloLocal", "velolocal")
OLD_DB_NAME = "velolocal.db"
OLD_SOURCE = "velolocal"
OLD_FILE_PREFIX = "velolocal"          # ficheiros .fit gravados pela versão anterior
NEW_SOURCE = "perennia"

_PATH_COLUMNS = ("fit_path", "cache_path")


def adopt_previous_dir(new: Path) -> Path:
    """A pasta de dados a usar: a nova; se só existir a antiga, renomeia-a para a nova."""
    old = new.parent / (OLD_DIR_NAMES[0] if new.name[:1].isupper() else OLD_DIR_NAMES[1])
    if new.exists() or not old.exists():
        return new
    try:
        old.rename(new)
        return new
    except OSError:
        return old                       # em uso ou sem permissões: continua na antiga


def adopt_previous_db(data_dir: Path, new_name: str) -> Path:
    new, old = data_dir / new_name, data_dir / OLD_DB_NAME
    if not new.exists() and old.exists():
        try:
            old.rename(new)
        except OSError:
            return old
    return new


def fix_path(value: str, new_dir_name: str) -> str:
    """Troca o nome antigo da pasta de dados, num caminho gravado, pelo novo."""
    out = value
    for name in OLD_DIR_NAMES:
        out = re.sub(rf"(?<=[\\/]){re.escape(name)}(?=[\\/])", new_dir_name, out)
    return out


def migrate_db(conn: sqlite3.Connection, data_dir: Path | None) -> int:
    """Corrige a base de dados. Devolve quantas linhas mudou (0 quando já está feito)."""
    changed = 0
    if data_dir is not None:
        new_name = Path(data_dir).name
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        for t in tables:
            cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')}
            for c in _PATH_COLUMNS:
                if c not in cols:
                    continue
                rows = conn.execute(
                    f'SELECT rowid, "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL').fetchall()
                for rowid, value in rows:
                    fixed = fix_path(str(value), new_name)
                    if fixed != value:
                        conn.execute(f'UPDATE "{t}" SET "{c}" = ? WHERE rowid = ?', (fixed, rowid))
                        changed += 1
    cols = {r[1] for r in conn.execute("PRAGMA table_info(workouts)")}
    if "source_format" in cols:
        cur = conn.execute("UPDATE workouts SET source_format = ? WHERE source_format = ?",
                           (NEW_SOURCE, OLD_SOURCE))
        changed += cur.rowcount or 0
    return changed
