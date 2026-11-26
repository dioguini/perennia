"""Onde ficam os dados da Perennia: na pasta `data/` da raiz do projeto (ao lado do `main.py`;
num executável, ao lado do `.exe`). Ver `perennia.core.folders` para o que há lá dentro.

`--data-dir` (linha de comandos) ou a variável `PERENNIA_DATA_DIR` escolhem outra pasta (os
testes usam isto). Sem precisar da janela nem do pyglet: a linha de comandos usa isto.

**A primeira vez com a organização nova.** As versões anteriores guardavam os dados na pasta do
sistema (`%APPDATA%\\Perennia`, `~/Library/Application Support/Perennia` ou
`~/.local/share/perennia`) e o GarminDB em `~/.GarminDb` e `~/HealthData`. Se `data/` ainda não
tem base de dados e essa pasta antiga tem, tudo é **copiado** para `data/` (os originais ficam
onde estavam — apagas tu quando quiseres): a base, os `.fit` de cada sessão para
`data/out/sessoes/<desporto>`, os backups para `data/out/backups`, e os caminhos gravados na base
passam a apontar para as cópias. Fica uma nota em `data/MIGRADO.txt`.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from . import legacy, paths

DB_NAME = "perennia.db"
MIGRATED_NOTE = "MIGRADO.txt"
_PATH_COLUMNS = ("fit_path", "cache_path")


def project_data_dir() -> Path:
    return paths.app_dir() / "data"


def default_data_dir() -> Path:
    """A pasta de dados: `PERENNIA_DATA_DIR` se estiver definida, senão `<projeto>/data`."""
    env = os.environ.get("PERENNIA_DATA_DIR")
    if env:
        return Path(env)
    return project_data_dir()


def system_data_dir() -> Path:
    """A pasta das versões anteriores (no sítio de cada sistema)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or str(Path.home()))
        new = base / "Perennia"
    elif sys.platform == "darwin":
        new = Path.home() / "Library" / "Application Support" / "Perennia"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
        new = base / "perennia"
    return legacy.adopt_previous_dir(new)


def database_path(data_dir: Path) -> Path:
    """perennia.db (uma base da versão anterior é renomeada uma vez; ver legacy.py)."""
    return legacy.adopt_previous_db(data_dir, DB_NAME)


def prepare(data_dir: Path, migrate: bool = False) -> dict | None:
    """Cria a estrutura de `data/` e, com `migrate`, copia uma vez os dados da pasta antiga.
    Devolve o relatório da cópia, ou None se não houve nada a copiar."""
    from .core import folders
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    report = None
    if migrate:
        try:
            report = migrate_from(system_data_dir(), data_dir)
        except Exception as e:                       # nunca impede a aplicação de abrir
            report = {"error": str(e)}
    folders.ensure_tree(data_dir)
    folders.set_root(data_dir)
    return report


def data_dir_for(arg: str | None) -> Path:
    """A pasta de dados: a que vier da linha de comandos, ou a de sempre (com a estrutura e,
    na primeira vez, a cópia dos dados antigos)."""
    d = Path(arg).expanduser() if arg else default_data_dir()
    prepare(d, migrate=not arg and not os.environ.get("PERENNIA_DATA_DIR"))
    return d


# ------------------------------------------------------- a cópia dos dados antigos


def migrate_from(old: Path, new: Path, home: Path | None = None) -> dict | None:
    """Copia a pasta de dados antiga para a nova organização. Só corre se a nova ainda não tem
    base de dados e a antiga tem. Nunca apaga nada da antiga."""
    from .core import folders
    old, new = Path(old), Path(new)
    if (new / DB_NAME).exists():
        return None
    old_db = old / DB_NAME
    if not old_db.exists():
        old_db = old / legacy.OLD_DB_NAME
    if not old_db.is_file():
        return None
    if old.resolve() == new.resolve():
        return None
    new.mkdir(parents=True, exist_ok=True)
    report = {"from": str(old), "files": 0, "paths": 0, "garmin": False}
    # os ficheiros: cada um no seu sítio novo
    moved: dict[str, str] = {}
    for f in sorted(old.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(old).as_posix()
        if rel in (DB_NAME, legacy.OLD_DB_NAME) or rel.endswith(("-wal", "-shm")):
            continue
        if rel.split("/")[0] not in folders.LEGACY_DIRS and rel.split("/")[0] != "endurance":
            continue                               # caches e afins: refazem-se sozinhas
        dst = new / folders.relocate(rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(f, dst)
            report["files"] += 1
        moved[str(f)] = str(dst)
    # a base de dados (com o que estiver no -wal), pela API de cópia do SQLite
    src = sqlite3.connect(str(old_db))
    try:
        dst_conn = sqlite3.connect(str(new / DB_NAME))
        try:
            src.backup(dst_conn)
            # os caminhos do nome antigo da aplicação passam primeiro para a pasta antiga
            legacy.migrate_db(dst_conn, old)
            report["paths"] = _repoint(dst_conn, old, new, moved)
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src.close()
    report["garmin"] = migrate_garmin(new, home)
    note = (f"Dados copiados em {datetime.now():%Y-%m-%d %H:%M} de:\n  {old}\n"
            f"{report['files']} ficheiros, {report['paths']} caminhos corrigidos na base.\n"
            + ("GarminDB copiado de ~/.GarminDb e ~/HealthData.\n" if report["garmin"] else "")
            + "Os originais continuam lá: apaga-os quando confirmares que está tudo aqui.\n")
    (new / MIGRATED_NOTE).write_text(note, encoding="utf-8")
    return report


def _repoint(conn: sqlite3.Connection, old: Path, new: Path, moved: dict[str, str]) -> int:
    """Os caminhos gravados na base (os .fit) passam a apontar para as cópias."""
    from .core import folders
    n = 0
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    old_txt = str(old)
    by_rel: dict[str, str] = {}
    for src, dst in moved.items():
        try:
            by_rel[Path(src).relative_to(old).as_posix()] = dst
        except ValueError:
            continue
    for t in tables:
        cols = {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')}
        for c in _PATH_COLUMNS:
            if c not in cols:
                continue
            for rowid, value in conn.execute(
                    f'SELECT rowid, "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL').fetchall():
                v = str(value)
                fixed = moved.get(v) or _by_suffix(v, by_rel)
                if fixed is None and v.startswith(old_txt):
                    rel = v[len(old_txt):].lstrip("/\\").replace("\\", "/")
                    if rel and ".." not in rel.split("/"):
                        fixed = str(new / folders.relocate(rel))
                if fixed and fixed != v:
                    conn.execute(f'UPDATE "{t}" SET "{c}" = ? WHERE rowid = ?', (fixed, rowid))
                    n += 1
    return n


def _by_suffix(value: str, by_rel: dict[str, str]) -> str | None:
    """Um caminho gravado noutro sítio (outro disco, outro nome da pasta) que acaba num dos
    ficheiros copiados («…/rides/a.fit»)."""
    parts = value.replace("\\", "/").split("/")
    for k in range(min(4, len(parts) - 1), 0, -1):
        hit = by_rel.get("/".join(parts[-k:]))
        if hit:
            return hit
    return None


def migrate_garmin(new: Path, home: Path | None = None) -> bool:
    """O GarminDB das versões anteriores (`~/.GarminDb` e `~/HealthData`) passa para
    `data/garmin/config` e `data/garmin/bases`. A palavra-passe que esteja escrita na
    configuração antiga **não** é copiada."""
    from .core import folders, garmin_sync
    home = Path(home) if home else Path.home()
    old_cfg_dir = home / ".GarminDb"
    old_cfg = old_cfg_dir / garmin_sync.CONFIG_NAME
    if not old_cfg.is_file():
        return False
    cfg_dir = folders.garmin_config_dir(new)
    bases = folders.garmin_bases_dir(new)
    try:
        cfg = json.loads(old_cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    old_base = None
    d = cfg.get("directories") or {}
    if d.get("base_dir"):
        old_base = (home / d["base_dir"]) if d.get("relative_to_home", True) else \
            Path(d["base_dir"])
    if old_base is not None and old_base.is_dir() and not any(bases.iterdir()):
        shutil.copytree(old_base, bases, dirs_exist_ok=True)
    tokens = old_cfg_dir / "garmin_tokens.json"
    if tokens.is_file() and not (cfg_dir / tokens.name).exists():
        shutil.copy2(tokens, cfg_dir / tokens.name)
    if not (cfg_dir / garmin_sync.CONFIG_NAME).exists():
        garmin_sync.save_config(cfg_dir / garmin_sync.CONFIG_NAME, cfg, bases)
    return True
