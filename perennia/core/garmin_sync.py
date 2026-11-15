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

**A palavra-passe do Garmin nunca fica escrita em disco pela Perennia** (nem na base de dados,
nem na configuração do GarminDB, nem nas cópias `.bak`, nem na linha de comandos). Vem da
variável de ambiente `PERENNIA_GARMIN_PASSWORD` ou, se a escreveres nas Definições, fica só na
memória até fechares a aplicação. Quando corre o GarminDB, a Perennia põe-na num ficheiro
temporário privado (só o teu utilizador lê), aponta a opção `credentials.password_file` da
configuração para ele e apaga-o logo que o GarminDB acaba (mesmo que falhe). Se a configuração
já tinha uma palavra-passe em claro (versões anteriores, ou escrita à mão), ela é retirada do
ficheiro e das cópias `.bak` na primeira sincronização e usada só nessa sessão.

Depois de o GarminDB correr, a Perennia lê:
* `garmin.db` → métricas diárias da Saúde (passos, FC em repouso, sono,
  HRV, stress, Body Battery, SpO2, peso…), via `importers.import_garmindb`;
* `garmin_activities.db` → as atividades, para `synced_activities` (aparecem
  no histórico de cada desporto, marcadas «Garmin»).
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import importers
from .db import Database, now_iso
from .i18n import tr

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

SYNC_TIMEOUT_S = 3600.0       # a opção «garmin_sync_timeout_s» (ver options.py)
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
    return options_from(db.get("sync_garmindb", {}) or {})


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
    backup = _write_backup_copy(path)
    data = cfg.setdefault("data", {})
    for k in DATED:
        if k not in stats:
            continue
        data[f"{k}_start_date"] = garmin_date(start)
        if end:
            data[f"{k}_end_date"] = garmin_date(end)
        else:
            data.pop(f"{k}_end_date", None)
    _private_write(path, json.dumps(cfg, indent=4, ensure_ascii=False))
    return backup


ENV_PASSWORD = "PERENNIA_GARMIN_PASSWORD"
_session: dict[str, str] = {}               # só em memória; nunca vai para o disco


def set_session_password(password: str | None) -> None:
    """A palavra-passe escrita nas Definições: fica na memória até fechares a aplicação."""
    if password:
        _session["password"] = password
    else:
        _session.pop("password", None)


def session_password() -> str | None:
    return os.environ.get(ENV_PASSWORD) or _session.get("password") or None


def password_source(path: Path | None = None) -> str:
    """De onde virá a palavra-passe: «env», «session», «keyring» (cofre do sistema, no
    GarminDB), «file» (ficheiro de palavra-passe do GarminDB), «config» (em claro na
    configuração — a Perennia retira-a ao sincronizar) ou «none»."""
    if os.environ.get(ENV_PASSWORD):
        return "env"
    if _session.get("password"):
        return "session"
    cred = ((read_config(path) if path else None) or {}).get("credentials", {}) or {}
    if cred.get("secure_password"):
        return "keyring"
    if cred.get("password_file") and not _is_run_file(str(cred["password_file"])):
        return "file"
    if cred.get("password"):
        return "config"
    return "none"


def credentials(path: Path) -> tuple[str, bool]:
    """(utilizador, há palavra-passe disponível?). O valor nunca sai daqui."""
    cfg = read_config(path) or {}
    cred = cfg.get("credentials", {}) or {}
    return str(cred.get("user") or ""), password_source(path) != "none"


_RUN_PREFIX = "perennia-garmin-"


def _is_run_file(p: str) -> bool:
    return _RUN_PREFIX in p


def _private_write(path: Path, text: str) -> None:
    """Escreve um ficheiro que só o dono lê (0600; no Windows vale a pasta do utilizador)."""
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _blank_password(text: str) -> str:
    """Esvazia «password» num texto JSON, mesmo que o ficheiro esteja estragado."""
    return re.sub(r'("password"\s*:\s*)"(?:[^"\\]|\\.)*"', r'\1""', text)


def _write_backup_copy(path: Path) -> Path:
    """A cópia `.bak` da configuração — sempre sem a palavra-passe."""
    backup = path.with_name(path.name + ".bak")
    text = path.read_text(encoding="utf-8")
    _private_write(backup, _blank_password(text))
    return backup


def scrub_config(path: Path) -> str | None:
    """Retira da configuração do GarminDB (e do `.bak`) uma palavra-passe em claro e uma
    referência esquecida a um ficheiro temporário de uma execução que não acabou. Devolve a
    palavra-passe que lá estava, para ser usada nesta sessão."""
    path = Path(path)
    cfg = read_config(path)
    if cfg is None:
        return None
    cred = cfg.get("credentials")
    if not isinstance(cred, dict):
        return None
    found = str(cred.get("password") or "") or None
    changed = False
    if found:
        cred["password"] = ""
        changed = True
    pf = cred.get("password_file")
    if pf and _is_run_file(str(pf)):
        with contextlib.suppress(OSError):
            shutil.rmtree(Path(str(pf)).parent, ignore_errors=True)
        cred["password_file"] = None
        changed = True
    if changed:
        _private_write(path, json.dumps(cfg, indent=4, ensure_ascii=False))
    bak = path.with_name(path.name + ".bak")
    if bak.exists():
        try:
            text = bak.read_text(encoding="utf-8")
            blank = _blank_password(text)
            if blank != text:
                if found is None:
                    m = re.search(r'"password"\s*:\s*"((?:[^"\\]|\\.)+)"', text)
                    if m:
                        with contextlib.suppress(ValueError):
                            found = json.loads('"' + m.group(1) + '"')
                _private_write(bak, blank)
        except OSError:
            pass
    return found


class PasswordMissing(RuntimeError):
    pass


def adopt_legacy_password(path: Path) -> None:
    """Uma palavra-passe em claro na configuração sai do ficheiro (e do `.bak`) e passa a
    viver só na memória desta sessão."""
    legacy_pw = scrub_config(path)
    if legacy_pw and not _session.get("password"):
        _session["password"] = legacy_pw


@contextlib.contextmanager
def password_for_run(db: Database):
    """Durante um `with`, o GarminDB consegue autenticar-se sem que a palavra-passe fique
    escrita: ela vai para um ficheiro temporário privado, referido por `password_file`, e
    tudo é desfeito no fim (também se o GarminDB falhar)."""
    path = config_path(db)
    cfg = read_config(path)
    if cfg is None:
        yield                                  # sem configuração: o GarminDB explica o que falta
        return
    adopt_legacy_password(path)
    cfg = read_config(path) or cfg
    cred = cfg.setdefault("credentials", {})
    if cred.get("secure_password") or cred.get("password_file"):
        yield                                  # cofre do sistema / ficheiro do próprio utilizador
        return
    pw = session_password()
    if not pw:
        raise PasswordMissing(
            f"falta a palavra-passe do Garmin: define a variável {ENV_PASSWORD} ou escreve-a "
            "nas Definições (só fica na memória, nunca no disco)")
    tmpdir = Path(tempfile.mkdtemp(prefix=_RUN_PREFIX))
    pwfile = tmpdir / "gp"
    try:
        fd = os.open(str(pwfile), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(pw)
        cred["password"] = ""
        cred["secure_password"] = False
        cred["password_file"] = str(pwfile)
        _private_write(path, json.dumps(cfg, indent=4, ensure_ascii=False))
        yield
    finally:
        with contextlib.suppress(OSError):
            pwfile.write_bytes(b"\0" * len(pw.encode("utf-8")))
        shutil.rmtree(tmpdir, ignore_errors=True)
        cfg2 = read_config(path)
        if cfg2 is not None:
            c2 = cfg2.setdefault("credentials", {})
            if _is_run_file(str(c2.get("password_file") or "")):
                c2["password_file"] = None
                with contextlib.suppress(OSError):
                    _private_write(path, json.dumps(cfg2, indent=4, ensure_ascii=False))


def new_config(start: str | None = None) -> dict:
    """Uma configuração do GarminDB nova, como a do exemplo do projeto."""
    start = start or garmin_date((date.today() - timedelta(days=365 * 5)).isoformat())
    return {
        "db": {"type": "sqlite"},
        "garmin": {"domain": "garmin.com"},
        "credentials": {"user": "", "secure_password": False, "password": "",
                        "password_file": None},
        "data": {"weight_start_date": start, "sleep_start_date": start,
                 "rhr_start_date": start, "hrv_start_date": start,
                 "monitoring_start_date": start, "download_latest_activities": 25,
                 "download_all_activities": 1000},
        "directories": {"relative_to_home": True, "base_dir": "HealthData",
                        "mount_dir": "/Volumes/GARMIN"},
        "enabled_stats": {k: True for k in ("monitoring", "steps", "itime", "sleep", "rhr",
                                            "hrv", "weight", "activities")},
        "settings": {"metric": True, "default_display_activities": ["walking", "running",
                                                                    "cycling"]},
        "checkup": {"look_back_days": 90},
    }


def write_credentials(path: Path, user: str | None, password: str | None = None) -> Path | None:
    """Grava só o **utilizador** do Garmin Connect na configuração do GarminDB (cria o
    ficheiro se não existir; se existir, guarda antes uma cópia `.bak` sem palavra-passe).
    A palavra-passe nunca se grava: se vier, fica só na memória desta sessão."""
    path = Path(path)
    cfg = read_config(path)
    backup = None
    if cfg is None:
        cfg = new_config()
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        backup = _write_backup_copy(path)
    cred = cfg.setdefault("credentials", {})
    if user is not None:
        cred["user"] = user
    cred["password"] = ""
    cred["secure_password"] = bool(cred.get("secure_password"))
    _private_write(path, json.dumps(cfg, indent=4, ensure_ascii=False))
    if password:
        set_session_password(password)
    return backup


def options_from(raw: dict | None) -> Options:
    raw = raw or {}
    known = {k: v for k, v in raw.items() if k in Options.__dataclass_fields__}
    return Options(**known).clean()


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


def command_text(db: Database, opts: Options, cfg_dir: Path | None = None) -> str:
    cmd = build_command(importers.garmindb_cli() or "garmindb_cli.py", opts,
                        cfg_dir if cfg_dir is not None else config_dir(db))
    cmd[0] = Path(cmd[0]).name
    return " ".join(cmd)


# ------------------------------------------------- o relato (passos e linhas)


class SyncLog:
    """O que a sincronização está a fazer, para o ecrã mostrar (como o GarminDB faz na linha
    de comandos): uma lista de **passos** (a decorrer, feito, falhou) e as últimas linhas
    que o GarminDB foi escrevendo. Pode ser lido pelo ecrã enquanto outra thread escreve."""

    def __init__(self, keep: int = 14, line_chars: int = 300):
        self.line_chars = max(20, int(line_chars))       # opção «garmin_log_line_chars»
        self._lock = threading.Lock()
        self.steps: list[dict] = []
        self.lines: deque = deque(maxlen=max(1, int(keep)))
        self.version = 0

    def step(self, text: str) -> None:
        """Começa um passo (o anterior, se ainda decorria, fica feito)."""
        with self._lock:
            if self.steps and self.steps[-1]["state"] == "run":
                self.steps[-1]["state"] = "ok"
            self.steps.append({"text": text, "state": "run", "detail": ""})
            self.version += 1

    def detail(self, text: str) -> None:
        with self._lock:
            if self.steps:
                self.steps[-1]["detail"] = text
                self.version += 1

    def end(self, ok: bool = True, detail: str | None = None) -> None:
        """Fecha o passo atual: feito (ok) ou falhou."""
        with self._lock:
            if self.steps:
                self.steps[-1]["state"] = "ok" if ok else "fail"
                if detail is not None:
                    self.steps[-1]["detail"] = detail
                self.version += 1

    def skip(self, text: str, why: str = "") -> None:
        with self._lock:
            self.steps.append({"text": text, "state": "skip", "detail": why})
            self.version += 1

    def line(self, text: str) -> None:
        text = (text or "").strip()
        if text:
            with self._lock:
                self.lines.append(text[:self.line_chars])
                self.version += 1

    def snapshot(self) -> tuple[list[dict], list[str]]:
        with self._lock:
            return [dict(s) for s in self.steps], list(self.lines)

    @property
    def failed(self) -> bool:
        return any(s["state"] == "fail" for s in self.steps)


# palavras que o GarminDB usa nas suas linhas → em que fase vai
_PHASES = (("download", re.compile(r"download|fetch|get(ting)? ", re.I),
            ("a descarregar do Garmin Connect", "downloading from Garmin Connect")),
           ("import", re.compile(r"import|process(ing)? |read(ing)? ", re.I),
            ("a importar para as bases do GarminDB", "importing into the GarminDB databases")),
           ("analyze", re.compile(r"analy[sz]|summar|calculat", re.I),
            ("a analisar e resumir", "analysing and summarising")))


def phase_of(line: str) -> str | None:
    """A fase em que o GarminDB vai, a julgar por uma linha do que escreve (ou None)."""
    for _k, pat, (pt, en) in _PHASES:
        if pat.search(line or ""):
            return tr(pt, en)
    return None


# (padrão, mensagem PT, mensagem EN): o que uma falha típica quer dizer e o que fazer
_DIAGNOSES = (
    (re.compile(r"mfa|2fa|two.?factor|verification code|security code", re.I),
     ("A conta Garmin tem verificação em dois passos (MFA): o GarminDB pede o código no "
      "terminal. Corre uma vez «garmindb_cli.py --download --latest» numa linha de comandos, "
      "introduz o código, e depois volta a sincronizar aqui.",
      "The Garmin account has two-step verification (MFA): GarminDB asks for the code in the "
      "terminal. Run «garmindb_cli.py --download --latest» once in a command line, enter the "
      "code, then sync here again.")),
    (re.compile(r"429|too many requests|rate.?limit", re.I),
     ("O Garmin limitou os pedidos (demasiadas tentativas). Espera uns 30 minutos e tenta "
      "outra vez.", "Garmin limited the requests (too many attempts). Wait about 30 minutes "
      "and try again.")),
    (re.compile(r"401|403|unauthori[sz]ed|invalid (user|cred|pass)|incorrect|login failed|"
                r"authentication|sign.?in", re.I),
     ("O Garmin recusou o utilizador ou a palavra-passe. Confirma o utilizador na "
      "configuração e a palavra-passe (variável PERENNIA_GARMIN_PASSWORD ou Definições).",
      "Garmin rejected the user or password. Check the user in the config and the password "
      "(PERENNIA_GARMIN_PASSWORD variable or Settings).")),
    (re.compile(r"no such file|not found|GarminConnectConfig|config.*(missing|not)", re.I),
     ("O GarminDB não encontrou a configuração. Confirma a «Pasta da configuração» e que "
      "GarminConnectConfig.json existe lá.",
      "GarminDB did not find its configuration. Check the «Config folder» and that "
      "GarminConnectConfig.json exists there.")),
    (re.compile(r"ssl|certificate|connection|timed? ?out|resolve|network|unreachable", re.I),
     ("Falhou a ligação à internet ou ao Garmin. Confirma a rede e tenta outra vez.",
      "The connection to the internet or to Garmin failed. Check the network and try "
      "again.")),
    (re.compile(r"permission denied", re.I),
     ("Sem permissão para escrever numa pasta do GarminDB. Confirma as pastas nas opções.",
      "No permission to write to a GarminDB folder. Check the folders in the options.")),
)


def diagnose(output: str) -> str | None:
    """Uma explicação em português/inglês para uma falha típica do GarminDB, ou None."""
    for pat, (pt, en) in _DIAGNOSES:
        if pat.search(output or ""):
            return tr(pt, en)
    return None


def preflight(db: Database, opts: "Options") -> list[dict]:
    """Os requisitos para sincronizar, um a um: `{key, ok, text, fix, blocking}`. Serve para
    dizer ao utilizador o que falta **antes** de correr, em vez de um erro do GarminDB."""
    opts.clean()
    path = config_path(db)
    cfg = read_config(path)
    user, has_pw = credentials(path) if cfg is not None else ("", False)
    online = bool(opts.download)                   # só descarregar precisa de conta Garmin
    cli = importers.garmindb_cli() is not None
    out = [
        {"key": "cli", "ok": cli, "blocking": False,
         "text": tr("GarminDB instalado", "GarminDB installed"),
         "fix": tr("instala-o com «pip install garmindb» (sem ele só se importa o que já está "
                   "nas bases)", "install it with «pip install garmindb» (without it only what "
                   "is already in the databases is imported)")},
        {"key": "config", "ok": cfg is not None, "blocking": cli,
         "text": tr("Configuração do GarminDB", "GarminDB configuration"),
         "fix": tr("falta {p} · em Definições → Ligações externas → Garmin guarda o utilizador "
                   "e a Perennia cria-o", "{p} is missing · in Settings → External connections "
                   "→ Garmin save the user and Perennia creates it", p=str(path))},
        {"key": "user", "ok": bool(user), "blocking": cli and online,
         "text": tr("Utilizador do Garmin Connect", "Garmin Connect user"),
         "fix": tr("escreve o e-mail da conta em Definições → Ligações externas → Garmin",
                   "type the account e-mail in Settings → External connections → Garmin")},
        {"key": "password", "ok": has_pw, "blocking": cli and online,
         "text": tr("Palavra-passe disponível", "Password available"),
         "fix": tr("define a variável de ambiente {v} antes de abrir a Perennia, ou escreve-a "
                   "nas Definições (fica só na memória)", "set the {v} environment variable "
                   "before opening Perennia, or type it in Settings (kept in memory only)",
                   v=ENV_PASSWORD)},
        {"key": "stats", "ok": bool(opts.stats), "blocking": True,
         "text": tr("Pelo menos um tipo de dados", "At least one kind of data"),
         "fix": tr("liga um dos tipos em «Dados»", "turn on one of the kinds under «Data»")},
        {"key": "steps", "ok": bool(opts.download or opts.copy or opts.import_ or opts.analyze),
         "blocking": False, "text": tr("Pelo menos um passo do GarminDB", "At least one "
                                       "GarminDB step"),
         "fix": tr("sem passos só se importa para a Perennia o que já está nas bases",
                   "with no steps only what is already in the databases is imported")},
    ]
    return out


def blocking_problems(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c["blocking"] and not c["ok"]]


def _run(cmd: list[str], runner: Callable | None, timeout: float,
         cwd: Path | None, log: SyncLog | None = None) -> tuple[bool, str]:
    """Corre o comando. Com `log` (e sem um `runner` de teste), lê o que o GarminDB vai
    escrevendo, linha a linha, e passa-o ao relato."""
    if runner is None and log is not None:
        return _run_streaming(cmd, timeout, cwd, log)
    run = runner or subprocess.run
    try:
        res = run(cmd, capture_output=True, text=True, timeout=timeout,
                  cwd=str(cwd) if cwd and cwd.is_dir() else None)
    except Exception as e:
        return False, str(e)
    out = (getattr(res, "stdout", "") or "")[-600:] + (getattr(res, "stderr", "") or "")[-600:]
    if log is not None:
        for ln in out.splitlines()[-log.lines.maxlen:]:
            log.line(ln)
    return getattr(res, "returncode", 1) == 0, out.strip()


def _run_streaming(cmd: list[str], timeout: float, cwd: Path | None,
                   log: SyncLog) -> tuple[bool, str]:
    # a palavra-passe do ambiente não vai para o GarminDB (ele lê-a do ficheiro temporário)
    env = {k: v for k, v in os.environ.items() if k != ENV_PASSWORD}
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, errors="replace", stdin=subprocess.DEVNULL,
                                cwd=str(cwd) if cwd and cwd.is_dir() else None)
    except OSError as e:
        return False, str(e)
    fired: list[bool] = []

    def _stop() -> None:
        fired.append(True)
        proc.kill()
    timer = threading.Timer(timeout, _stop)
    timer.daemon = True
    timer.start()
    tail: deque = deque(maxlen=40)
    try:
        for raw in proc.stdout:                       # type: ignore[union-attr]
            for ln in re.split(r"[\r\n]+", raw):
                if ln.strip():
                    tail.append(ln.strip())
                    log.line(ln)
                    ph = phase_of(ln)
                    if ph:
                        log.detail(ph)
        code = proc.wait()
    finally:
        timer.cancel()
        if proc.poll() is None:
            proc.kill()
    out = "\n".join(tail)[-1200:]
    if fired:                                         # o temporizador disparou: demorou demais
        return False, tr("o GarminDB demorou mais de {s} s e foi parado",
                         "GarminDB took more than {s} s and was stopped", s=int(timeout))
    return code == 0, out


def run_garmindb(db: Database, opts: Options, runner: Callable | None = None,
                 timeout: float | None = None, log: SyncLog | None = None
                 ) -> tuple[bool, str]:
    """Corre o GarminDB com as opções escolhidas (no intervalo, escreve
    primeiro as datas na configuração)."""
    timeout = SYNC_TIMEOUT_S if timeout is None else timeout     # opção «garmin_sync_timeout_s»
    opts.clean()
    if not opts.stats:
        return False, "escolhe pelo menos um tipo de dados"
    cli = importers.garmindb_cli()
    if cli is None:
        return False, "GarminDB não encontrado (pip install garmindb)"
    if not (opts.download or opts.copy or opts.import_ or opts.analyze):
        return True, ""
    adopt_legacy_password(config_path(db))
    if opts.period == "range" and opts.write_config and (opts.download or opts.import_):
        try:
            write_range(config_path(db), opts.start, opts.end, opts.stats)
        except OSError as e:
            return False, str(e)
    # o garmindb.log fica na pasta de onde se corre: a dos dados do GarminDB
    try:
        with password_for_run(db):
            return _run(build_command(cli, opts, config_dir(db)), runner, timeout,
                        db_dir(db).parent, log)
    except PasswordMissing as e:
        return False, str(e)


def maintenance(db: Database, action: str, runner: Callable | None = None,
                timeout: float | None = None, log: SyncLog | None = None
                ) -> tuple[bool, str]:
    """`backup` (--backup) ou `rebuild` (--rebuild_db) das bases do GarminDB."""
    timeout = SYNC_TIMEOUT_S if timeout is None else timeout
    cli = importers.garmindb_cli()
    if cli is None:
        return False, "GarminDB não encontrado (pip install garmindb)"
    flag = {"backup": "--backup", "rebuild": "--rebuild_db"}[action]
    cmd = [cli]
    if config_dir(db) != CONFIG_DIR_DEFAULT:
        cmd += ["-f", str(config_dir(db))]
    try:
        with password_for_run(db):
            return _run(cmd + [flag], runner, timeout, db_dir(db).parent, log)
    except PasswordMissing as e:
        return False, str(e)


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
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(synced_activities)")}
    for c, decl in (("tss", "REAL"), ("if_value", "REAL"), ("avg_power_w", "REAL"),
                    ("np_w", "REAL")):
        if c not in cols:                 # a TSS do TrainingPeaks (e a calculada)
            db.conn.execute(f"ALTER TABLE synced_activities ADD COLUMN {c} {decl}")
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
                    "activities": 0, "new_activities": 0, "tables": [], "kept": 0}
    folder = Path(folder) if folder else db_dir(db)
    tables = tuple(HEALTH_TABLES[k] for k in opts.stats if k in HEALTH_TABLES)
    if tables:
        if (folder / "garmin.db").exists():
            rep = importers.import_garmindb(db, folder, since=since, until=until, tables=tables)
            report.update(values=rep["values"], days=rep["days"], tables=rep["tables"],
                          created=rep.get("created", []), kept=rep.get("kept", 0))
        elif "activities" not in opts.stats:
            raise FileNotFoundError(f"não encontrei {folder / 'garmin.db'}")
    if "activities" in opts.stats:
        rep = import_activities(db, folder, since=since, until=until)
        report.update(activities=rep["activities"], new_activities=rep["new"])
    db.set("garmindb_last_sync", now_iso()[:16].replace("T", " "))
    db.set("garmindb_last_sync_day", date.today().isoformat())
    return report


def sync(db: Database, opts: Options, runner: Callable | None = None,
         run_source: bool = True, log: SyncLog | None = None
         ) -> tuple[bool, str, dict | None]:
    """Corre a fonte (se `run_source`) e importa. (ok, mensagem, relatório). Com `log`, vai
    contando o que faz, passo a passo."""
    log = log or SyncLog()
    opts.clean()
    if run_source:
        if opts.period == "range" and opts.write_config and (opts.download or opts.import_):
            log.step(tr("A escrever o intervalo {a} → {b} na configuração do GarminDB",
                        "Writing the range {a} → {b} to the GarminDB config",
                        a=opts.start, b=opts.end))
        names = [n for n, on in ((tr("descarregar", "download"), opts.download),
                                 (tr("copiar do relógio", "copy from the watch"), opts.copy),
                                 (tr("importar", "import"), opts.import_),
                                 (tr("analisar", "analyse"), opts.analyze)) if on]
        if names:
            log.step(tr("A correr o GarminDB: {n}", "Running GarminDB: {n}",
                        n=" → ".join(names)))
        else:
            log.skip(tr("GarminDB", "GarminDB"), tr("nenhum passo ligado", "no step on"))
        ok, out = run_garmindb(db, opts, runner=runner, log=log)
        if not ok:
            hint = diagnose(out)
            last = out.splitlines()[-1] if out else tr("falhou", "failed")
            log.end(False, hint or last)
            return False, hint or last, None
        if names:
            log.end(True)
    else:
        log.skip(tr("GarminDB", "GarminDB"),
                 tr("só se importa o que já está nas bases", "importing only what is already "
                    "in the databases"))
    try:
        log.step(tr("A importar para a Perennia", "Importing into Perennia"))
        rep = sync_into_perennia(db, opts)
    except FileNotFoundError as e:
        log.end(False, str(e))
        return False, str(e), None
    if opts.stats and any(k in HEALTH_TABLES for k in opts.stats):
        log.detail(tr("saúde: {v} valores em {d} dias", "health: {v} values over {d} days",
                      v=rep["values"], d=rep["days"]) +
                   (" · " + tr("{k} mantidos (outra Fonte)", "{k} kept (other source)",
                               k=rep["kept"]) if rep.get("kept") else "") +
                   (" · " + tr("atividades: {n} ({k} novas)", "activities: {n} ({k} new)",
                               n=rep["activities"], k=rep["new_activities"])
                    if "activities" in opts.stats else ""))
    elif "activities" in opts.stats:
        log.detail(tr("atividades: {n} ({k} novas)", "activities: {n} ({k} new)",
                      n=rep["activities"], k=rep["new_activities"]))
    log.end(True)
    log.step(tr("Concluído", "Done"))
    log.end(True)
    return True, "", rep


def parse_day(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None
