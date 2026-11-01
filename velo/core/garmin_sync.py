"""Sincronização para a base da Perennia a partir de uma fonte. Por agora a
fonte é o GarminDB (https://github.com/tcgoetz/GarminDB), que descarrega os
dados do Garmin Connect para bases SQLite locais.

O que o GarminDB permite, e as opções que aqui se montam:

* **Que dados** (`garmindb_cli.py`): `--all` (-A) ou cada um — `--activities`
  (-a), `--monitoring` (-m), `--rhr` (-r), `--hrv`, `--sleep` (-s),
  `--weight` (-w).
* **Que passos**: `--download` (-d, do Garmin Connect), `--copy` (-c, de um
  relógio ligado por USB), `--import` (-i, para as bases do GarminDB),
  `--analyze` (resumos), e o modificador `--overwrite` (-o).
* **Que período**:
    - só o mais recente: `--latest` (-l) — desde o último dia que já está
      na base do GarminDB (nas atividades, as últimas
      `download_latest_activities`);
    - todo o histórico: sem `--latest`, desde as datas de início da
      configuração (`data.<dado>_start_date`; nas atividades, as últimas
      `download_all_activities`);
    - um intervalo: as datas de início e de fim (`data.<dado>_start_date` e
      `data.<dado>_end_date`, no formato MM/DD/AAAA) escrevem-se na
      configuração do GarminDB — com uma cópia `.bak` antes — e corre-se sem
      `--latest`. A Perennia importa só esse intervalo.
* **Manutenção**: `--backup` (-b) e `--rebuild_db`.
* `-f DIR`: a pasta da configuração, se não for a `~/.GarminDb`.

A palavra-passe do Garmin fica na configuração do GarminDB; a Perennia
nunca a lê nem a guarda.

Depois de o GarminDB correr, a Perennia lê:
* `garmin.db` → métricas diárias da Saúde (passos, FC em repouso, sono,
  HRV, stress, Body Battery, SpO2, peso…), via `importers.import_garmindb`;
* `garmin_activities.db` → as atividades, para `synced_activities` (aparecem
  no histórico de cada desporto, marcadas «Garmin»).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import importers
from .db import Database, now_iso

SOURCES = ("garmindb",)

# (chave, opção curta, opção longa)
STATS = (("activities", "-a", "--activities"), ("monitoring", "-m", "--monitoring"),
         ("rhr", "-r", "--rhr"), ("hrv", "--hrv", "--hrv"), ("sleep", "-s", "--sleep"),
         ("weight", "-w", "--weight"))
STAT_KEYS = tuple(k for k, _s, _l in STATS)
# os dados com datas de início e de fim na configuração do GarminDB
DATED = ("weight", "sleep", "rhr", "hrv", "monitoring")
# de que tabela da garmin.db vem cada dado (para a Saúde)
HEALTH_TABLES = {"monitoring": "daily_summary", "sleep": "sleep", "rhr": "resting_hr",
                 "hrv": "hrv", "weight": "weight"}
PERIODS = ("latest", "all", "range")

CONFIG_DIR_DEFAULT = Path.home() / ".GarminDb"
CONFIG_NAME = "GarminConnectConfig.json"


@dataclass
class Options:
    source: str = "garmindb"
    period: str = "latest"              # latest | all | range
    start: str | None = None            # AAAA-MM-DD (intervalo)
    end: str | None = None
    stats: list = field(default_factory=lambda: list(STAT_KEYS))
    download: bool = True
    copy: bool = False
    import_: bool = True
    analyze: bool = True
    overwrite: bool = False
    write_config: bool = True           # intervalo: escrever as datas na configuração

    def clean(self) -> "Options":
        if self.period not in PERIODS:
            self.period = "latest"
        self.stats = [k for k in STAT_KEYS if k in (self.stats or [])]
        today = date.today()
        if self.period == "range":
            if not self.start:
                self.start = (today - timedelta(days=90)).isoformat()
            if not self.end:
                self.end = today.isoformat()
            if self.end < self.start:
                self.start, self.end = self.end, self.start
        return self


def load_options(db: Database) -> Options:
    raw = db.get("sync_garmindb", {}) or {}
    known = {k: v for k, v in raw.items() if k in Options.__dataclass_fields__}
    return Options(**known).clean()


def save_options(db: Database, opts: Options) -> None:
    db.set("sync_garmindb", asdict(opts.clean()))


# --------------------------------------------------------------- pastas


def db_dir(db: Database) -> Path:
    return importers.garmindb_dir(db)


def config_dir(db: Database) -> Path:
    return Path(os.path.expanduser(str(db.get("garmindb_config_dir", "")
                                       or CONFIG_DIR_DEFAULT)))


def config_path(db: Database) -> Path:
    return config_dir(db) / CONFIG_NAME


def read_config(path: Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def garmin_date(iso: str) -> str:
    """AAAA-MM-DD → MM/DD/AAAA (como no exemplo da configuração do GarminDB)."""
    d = date.fromisoformat(iso)
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def iso_from_garmin(text: str | None) -> str | None:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", str(text or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()
    except ValueError:
        return None


def config_dates(cfg: dict | None) -> dict[str, tuple[str | None, str | None]]:
    """{dado: (início, fim)} da configuração, em AAAA-MM-DD."""
    data = (cfg or {}).get("data", {}) or {}
    return {k: (iso_from_garmin(data.get(f"{k}_start_date")),
                iso_from_garmin(data.get(f"{k}_end_date"))) for k in DATED}


def write_range(path: Path, start: str, end: str | None, stats: list[str]) -> Path:
    """Escreve as datas do intervalo na configuração do GarminDB (só as dos
    dados escolhidos), depois de guardar uma cópia em `.bak`. Devolve a cópia."""
    path = Path(path)
    cfg = read_config(path)
    if cfg is None:
        raise FileNotFoundError(f"não encontrei a configuração do GarminDB em {path}")
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    data = cfg.setdefault("data", {})
    for k in DATED:
        if k not in stats:
            continue
        data[f"{k}_start_date"] = garmin_date(start)
        if end:
            data[f"{k}_end_date"] = garmin_date(end)
        else:
            data.pop(f"{k}_end_date", None)
    path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8")
    return backup


def metric_units(cfg: dict | None) -> bool:
    """O GarminDB guarda distâncias em km e m só com settings.metric = true."""
    return bool(((cfg or {}).get("settings", {}) or {}).get("metric", False))


# ------------------------------------------------------------- o comando


def build_command(cli: str, opts: Options, cfg_dir: Path | None = None) -> list[str]:
    opts.clean()
    cmd = [cli]
    if cfg_dir is not None and Path(cfg_dir) != CONFIG_DIR_DEFAULT:
        cmd += ["-f", str(cfg_dir)]
    if set(opts.stats) == set(STAT_KEYS):
        cmd.append("--all")
    else:
        cmd += [long for k, _short, long in STATS if k in opts.stats]
    if opts.copy:
        cmd.append("--copy")
    if opts.download:
        cmd.append("--download")
    if opts.import_:
        cmd.append("--import")
    if opts.analyze:
        cmd.append("--analyze")
    if opts.period == "latest":
        cmd.append("--latest")
    if opts.overwrite:
        cmd.append("--overwrite")
    return cmd


def command_text(db: Database, opts: Options) -> str:
    cmd = build_command(importers.garmindb_cli() or "garmindb_cli.py", opts, config_dir(db))
    cmd[0] = Path(cmd[0]).name
    return " ".join(cmd)


def _run(cmd: list[str], runner: Callable | None, timeout: float,
         cwd: Path | None) -> tuple[bool, str]:
    run = runner or subprocess.run
    try:
        res = run(cmd, capture_output=True, text=True, timeout=timeout,
                  cwd=str(cwd) if cwd and cwd.is_dir() else None)
    except Exception as e:
        return False, str(e)
    out = (getattr(res, "stdout", "") or "")[-600:] + (getattr(res, "stderr", "") or "")[-600:]
    return getattr(res, "returncode", 1) == 0, out.strip()


def run_garmindb(db: Database, opts: Options, runner: Callable | None = None,
                 timeout: float = 3600.0) -> tuple[bool, str]:
    """Corre o GarminDB com as opções escolhidas (no intervalo, escreve
    primeiro as datas na configuração)."""
    opts.clean()
    if not opts.stats:
        return False, "escolhe pelo menos um tipo de dados"
    cli = importers.garmindb_cli()
    if cli is None:
        return False, "GarminDB não encontrado (pip install garmindb)"
    if not (opts.download or opts.copy or opts.import_ or opts.analyze):
        return True, ""
    if opts.period == "range" and opts.write_config and (opts.download or opts.import_):
        try:
            write_range(config_path(db), opts.start, opts.end, opts.stats)
        except OSError as e:
            return False, str(e)
    # o garmindb.log fica na pasta de onde se corre: a dos dados do GarminDB
    return _run(build_command(cli, opts, config_dir(db)), runner, timeout, db_dir(db).parent)


def maintenance(db: Database, action: str, runner: Callable | None = None,
                timeout: float = 3600.0) -> tuple[bool, str]:
    """`backup` (--backup) ou `rebuild` (--rebuild_db) das bases do GarminDB."""
    cli = importers.garmindb_cli()
    if cli is None:
        return False, "GarminDB não encontrado (pip install garmindb)"
    flag = {"backup": "--backup", "rebuild": "--rebuild_db"}[action]
    cmd = [cli]
    if config_dir(db) != CONFIG_DIR_DEFAULT:
        cmd += ["-f", str(config_dir(db))]
    return _run(cmd + [flag], runner, timeout, db_dir(db).parent)


# --------------------------------------------------------- estado da fonte


def status(db: Database) -> dict:
    d = db_dir(db)
    cfg = read_config(config_path(db))
    return {"dir": str(d), "config": str(config_path(db)), "config_found": cfg is not None,
            "garmin_db": (d / "garmin.db").exists(),
            "activities_db": (d / "garmin_activities.db").exists(),
            "cli": importers.garmindb_cli() is not None,
            "dates": config_dates(cfg), "metric": metric_units(cfg),
            "last_sync": db.get("garmindb_last_sync"),
            "activities": count_activities(db)}


# ------------------------------------------------------- para a Perennia


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS synced_activities (
      id TEXT PRIMARY KEY, source TEXT NOT NULL, sport TEXT NOT NULL, source_sport TEXT,
      name TEXT, started_at TEXT, elapsed_s REAL, moving_s REAL, distance_m REAL,
      ascent_m REAL, avg_hr REAL, max_hr REAL, calories REAL, training_load REAL,
      imported_at TEXT);
    CREATE INDEX IF NOT EXISTS ix_synced_sport ON synced_activities(sport, started_at);
    """)
    db.conn.commit()


def count_activities(db: Database) -> int:
    try:
        return int(db.conn.execute("SELECT COUNT(*) FROM synced_activities").fetchone()[0])
    except sqlite3.Error:
        return 0


def activities(db: Database, sport: str | None = None, limit: int = 200) -> list[dict]:
    ensure(db)
    sql, args = "SELECT * FROM synced_activities", []
    if sport:
        sql += " WHERE sport = ?"
        args.append(sport)
    sql += " ORDER BY started_at DESC LIMIT ?"
    return [dict(r) for r in db.conn.execute(sql, args + [limit])]


def sport_of(sport: str | None, sub: str | None) -> str:
    s, ss = (sport or "").lower(), (sub or "").lower()
    if "row" in s or "row" in ss:
        return "rowing"
    if s.startswith("cycl") or "biking" in s or "cycling" in ss:
        return "cycling"
    if s.startswith("run") or "running" in ss or "treadmill" in ss:
        return "running"
    if s.startswith("swim") or "swim" in ss:
        return "swimming"
    if "strength" in s or "strength" in ss or s in ("training", "fitness_equipment") \
            or "cardio" in ss or "hiit" in s or "hiit" in ss:
        return "gym"
    return "other"


def _seconds(t: Any) -> float | None:
    """«01:02:03.500000» (Time do GarminDB) → segundos."""
    if t is None or t == "":
        return None
    if isinstance(t, (int, float)):
        return float(t)
    m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", str(t))
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def import_activities(db: Database, folder: str | Path | None = None,
                      since: str | None = None, until: str | None = None,
                      metric: bool | None = None) -> dict:
    """Lê `garmin_activities.db` e grava (ou atualiza) cada atividade.
    `metric`: as distâncias do GarminDB vêm em km (True) ou milhas (False)."""
    ensure(db)
    folder = Path(folder) if folder else db_dir(db)
    path = folder / "garmin_activities.db"
    if not path.exists():
        return {"activities": 0, "new": 0, "found": False}
    if metric is None:
        metric = metric_units(read_config(config_path(db)))
    km = 1.0 if metric else 1.609344                # milhas → km
    m_up = 1.0 if metric else 0.3048                # pés → m
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in src.execute("PRAGMA table_info(activities)")}
    except sqlite3.Error:
        cols = set()
    if "activity_id" not in cols or "start_time" not in cols:
        src.close()
        return {"activities": 0, "new": 0, "found": True}
    want = [c for c in ("activity_id", "name", "sport", "sub_sport", "start_time",
                        "elapsed_time", "moving_time", "distance", "ascent", "avg_hr",
                        "max_hr", "calories", "training_load") if c in cols]
    sql = f"SELECT {', '.join(want)} FROM activities"
    where, args = [], []
    if since:
        where.append("start_time >= ?")
        args.append(since)
    if until:
        where.append("substr(start_time, 1, 10) <= ?")
        args.append(until)
    if where:
        sql += " WHERE " + " AND ".join(where)
    existing = {r[0] for r in db.conn.execute("SELECT id FROM synced_activities")}
    n = new = 0
    stamp = now_iso()
    for r in src.execute(sql, args):
        row = dict(r)
        aid = f"garmin:{row['activity_id']}"
        dist = row.get("distance")
        asc = row.get("ascent")
        db.conn.execute(
            "INSERT INTO synced_activities(id, source, sport, source_sport, name, started_at,"
            " elapsed_s, moving_s, distance_m, ascent_m, avg_hr, max_hr, calories,"
            " training_load, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET sport=excluded.sport, name=excluded.name,"
            " started_at=excluded.started_at, elapsed_s=excluded.elapsed_s,"
            " moving_s=excluded.moving_s, distance_m=excluded.distance_m,"
            " ascent_m=excluded.ascent_m, avg_hr=excluded.avg_hr, max_hr=excluded.max_hr,"
            " calories=excluded.calories, training_load=excluded.training_load,"
            " imported_at=excluded.imported_at",
            (aid, "garmindb", sport_of(row.get("sport"), row.get("sub_sport")),
             "/".join(x for x in (row.get("sport"), row.get("sub_sport")) if x) or None,
             row.get("name"), str(row.get("start_time") or "")[:19],
             _seconds(row.get("elapsed_time")), _seconds(row.get("moving_time")),
             float(dist) * km * 1000 if dist is not None else None,
             float(asc) * m_up if asc is not None else None,
             row.get("avg_hr"), row.get("max_hr"), row.get("calories"),
             row.get("training_load"), stamp))
        n += 1
        new += aid not in existing
    db.conn.commit()
    src.close()
    return {"activities": n, "new": new, "found": True}


def import_range(db: Database, opts: Options) -> tuple[str | None, str | None]:
    """De que dia a que dia se importa para a Perennia."""
    opts.clean()
    if opts.period == "range":
        return opts.start, opts.end
    if opts.period == "latest":
        last = db.get("garmindb_last_sync_day")
        if last:
            try:
                return (date.fromisoformat(last) - timedelta(days=1)).isoformat(), None
            except ValueError:
                pass
    return None, None


def sync_into_perennia(db: Database, opts: Options, folder: str | Path | None = None) -> dict:
    """Importa da fonte para a base da Perennia, segundo as opções."""
    opts.clean()
    since, until = import_range(db, opts)
    report: dict = {"since": since, "until": until, "values": 0, "days": 0,
                    "activities": 0, "new_activities": 0, "tables": []}
    folder = Path(folder) if folder else db_dir(db)
    tables = tuple(HEALTH_TABLES[k] for k in opts.stats if k in HEALTH_TABLES)
    if tables:
        if (folder / "garmin.db").exists():
            rep = importers.import_garmindb(db, folder, since=since, until=until, tables=tables)
            report.update(values=rep["values"], days=rep["days"], tables=rep["tables"],
                          created=rep.get("created", []))
        elif "activities" not in opts.stats:
            raise FileNotFoundError(f"não encontrei {folder / 'garmin.db'}")
    if "activities" in opts.stats:
        rep = import_activities(db, folder, since=since, until=until)
        report.update(activities=rep["activities"], new_activities=rep["new"])
    db.set("garmindb_last_sync", now_iso()[:16].replace("T", " "))
    db.set("garmindb_last_sync_day", date.today().isoformat())
    return report


def sync(db: Database, opts: Options, runner: Callable | None = None,
         run_source: bool = True) -> tuple[bool, str, dict | None]:
    """Corre a fonte (se `run_source`) e importa. (ok, mensagem, relatório)."""
    if run_source:
        ok, out = run_garmindb(db, opts, runner=runner)
        if not ok:
            return False, out.splitlines()[-1] if out else "falhou", None
    try:
        rep = sync_into_perennia(db, opts)
    except FileNotFoundError as e:
        return False, str(e), None
    return True, "", rep


def parse_day(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None
