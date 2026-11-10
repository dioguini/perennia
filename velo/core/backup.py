"""Backups e reposição: tudo o que a Perennia guarda, num só ficheiro .zip.

**Exportar** — tudo (exportação completa) ou só algumas componentes. O .zip
vem segmentado, uma pasta por componente e um ficheiro por tabela:

    perennia-backup_2026-11-04_16-30_completo.zip
      manifest.json             o que está lá dentro (versão, data, contagens)
      LEIA-ME.txt
      01-perfil/athlete.jsonl
      07-rotas/routes.jsonl, route_points.jsonl, climbs.jsonl
      11-sessoes/rides.jsonl, ride_samples.jsonl, …
      11-sessoes/ficheiros/rides/<sessão>.fit
      …

Cada linha de um `.jsonl` é um registo, com o nome das colunas — legível e
fácil de ler noutro programa. As definições (tabela `settings`) dividem-se
pelas componentes: atalhos de teclado, ecrã da sessão, ligações externas e o
resto.

**Repor** — escolhe-se o ficheiro (ou arrasta-se para a janela) e a
Perennia faz o resto: antes de mexer, guarda um backup do que tens agora;
depois, em cada componente escolhida,

* **substituir** — os dados dessa componente passam a ser os do backup
  (cópia exata: o normal para mudar de computador ou voltar atrás);
* **juntar** — acrescenta o que falta e deixa o resto como está (os ids
  numéricos que já existem cá recebem números novos e as referências
  acompanham).

Tudo numa só transação: se algo falhar, nada fica a meio. No fim, as
referências que ficaram sem destino (uma sessão de uma rota que não veio)
arrumam-se como a base de dados manda (ficam vazias, ou saem).

As caches que se refazem sozinhas (`route_bakes`, `ride_zone_cache`), o
ponto de recuperação de uma sessão a meio (`session_checkpoints`) e a versão
do esquema não entram. As credenciais (Strava) só entram se as pedires.

Também pela linha de comandos:

    python main.py --backup [pasta ou ficheiro.zip] [--componentes rotas,sessoes]
    python main.py --restore backup.zip [--modo substituir|juntar] [--componentes …]
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from .i18n import tr

FORMAT = 1
APP = "Perennia"


# ================================================================ componentes


@dataclass(frozen=True)
class Component:
    key: str
    pt: str
    en: str
    desc_pt: str
    desc_en: str
    tables: tuple[str, ...] = ()
    settings: Callable[[str], bool] | None = None       # que chaves de `settings`
    folders: tuple[str, ...] = ()                       # pastas de ficheiros (na pasta de dados)
    sensitive: bool = False                             # fica fora, a não ser que se peça

    @property
    def name(self) -> str:
        return tr(self.pt, self.en)

    @property
    def description(self) -> str:
        return tr(self.desc_pt, self.desc_en)


ATALHOS = ("keymap",)
ECRA_PREFIXES = ("screen_layout_", "layout_", "hud_", "metrics_disabled_")
ECRA_KEYS = ("row_fields", "metrics_disabled")
LIGACOES_PREFIXES = ("strava_", "garmindb_", "agent_")
LIGACOES_KEYS = ("sync_garmindb",)
SECRET_WORDS = ("secret", "token", "password", "passwd", "api_key", "apikey")
# chaves internas que não se copiam (caches)
SKIP_SETTINGS = ("zone_cache_key",)


def _is_atalho(k: str) -> bool:
    return k in ATALHOS


def _is_ecra(k: str) -> bool:
    return k.startswith(ECRA_PREFIXES) or k in ECRA_KEYS


def _is_ligacao(k: str) -> bool:
    return k.startswith(LIGACOES_PREFIXES) or k in LIGACOES_KEYS or \
        any(w in k.lower() for w in SECRET_WORDS)


def _is_definicao(k: str) -> bool:
    return not (_is_atalho(k) or _is_ecra(k) or _is_ligacao(k) or k in SKIP_SETTINGS)


COMPONENTS: tuple[Component, ...] = (
    Component("perfil", "Perfil do atleta", "Athlete profile",
              "nome, peso, FTP e limiares", "name, weight, FTP and thresholds",
              tables=("athlete",)),
    Component("definicoes", "Definições", "Settings",
              "unidades, tema, zonas, Geral, limites Não ERG dos aparelhos, forma e "
              "fadiga, a fórmula da Longevidade, preferências de ligação…",
              "units, theme, zones, General, non-ERG device limits, form and fatigue, "
              "the Longevity formula, connection preferences…",
              settings=_is_definicao),
    Component("atalhos", "Atalhos de teclado", "Keyboard shortcuts",
              "as teclas que mudaste", "the keys you changed", settings=_is_atalho),
    Component("ecra", "Ecrã da sessão", "Session screen",
              "disposição do ecrã, número de métricas e métricas de sessão disponíveis em "
              "cada desporto",
              "screen layout, number of metrics and available session metrics of each sport",
              settings=_is_ecra),
    Component("aparelhos", "Aparelhos", "Devices",
              "dispositivos emparelhados e calibrações", "paired devices and calibrations",
              tables=("devices", "trainer_calibrations")),
    Component("rotas", "Rotas", "Routes",
              "os .gpx: pontos, perfil e subidas", "the .gpx: points, profile and climbs",
              tables=("routes", "route_points", "climbs")),
    Component("segmentos", "Segmentos", "Segments",
              "os da Perennia e os do Strava", "Perennia's and Strava's",
              tables=("perennia_segments", "strava_segments")),
    Component("treinos", "Treinos", "Workouts",
              "listas de treinos de todos os desportos, definição, objetivos e planos de "
              "voltas (também as cópias das sessões)",
              "workout lists of every sport, definition, goals and lap plans (also the "
              "sessions' copies)",
              tables=("workouts", "workout_steps", "row_workouts", "row_workout_steps",
                      "endurance_workouts", "endurance_steps", "workout_meta",
                      "workout_goals", "lap_plans", "workout_types")),
    Component("ginasio", "Ginásio e exercícios", "Gym and exercises",
              "exercícios, treinos de força e as suas estruturas",
              "exercises, strength workouts and their structures",
              tables=("exercises", "exercise_equipment", "exercise_modalities",
                      "strength_workouts", "strength_workout_items", "strength_structures",
                      "muscle_groups", "muscle_subgroups", "gym_disciplines")),
    Component("inventario", "Inventário de artigos", "Equipment inventory",
              "bicicletas, sapatilhas, peças, o seu uso e a data e o preço de compra",
              "bikes, shoes, parts, their use and purchase date and price",
              tables=("equipment_items",)),
    Component("sessoes", "Histórico de sessões", "Session history",
              "todas as sessões (ciclismo, remo, corrida, natação, ginásio): amostras, "
              "voltas, tempos em subidas e segmentos, jogos, importadas (Garmin, "
              "TrainingPeaks, upload manual) — e os .fit",
              "every session (cycling, rowing, running, swimming, gym): samples, laps, "
              "climb and segment times, games, imported (Garmin, TrainingPeaks, manual upload) — "
              "and the .fit files",
              tables=("rides", "ride_samples", "laps", "climb_efforts", "route_efforts",
                      "chase_efforts", "ride_comparisons", "workout_step_results",
                      "game_results", "row_sessions", "row_samples", "row_laps",
                      "endurance_sessions", "endurance_samples", "endurance_laps",
                      "strength_sessions", "strength_sets", "strength_laps", "strength_hr",
                      "session_workouts", "segment_efforts", "strava_efforts",
                      "synced_activities", "session_tags", "tag_catalog"),
              folders=("rides", "rowing", "endurance", "strength")),
    Component("analises", "Análises e feedback", "Analyses and feedback",
              "o feedback de cada sessão e a sua análise, picos e curvas de potência",
              "each session's feedback and analysis, peaks and power curves",
              tables=("session_feedback", "ride_peaks", "ride_power_curve")),
    Component("desafios", "Desafios", "Challenges",
              "os teus desafios e as tentativas", "your challenges and attempts",
              tables=("challenges", "challenge_attempts")),
    Component("testes", "Testes de aptidão", "Fitness tests",
              "testes, resultados e testes de FTP", "tests, results and FTP tests",
              tables=("fitness_tests", "test_results", "ftp_tests")),
    Component("saude", "Saúde", "Health",
              "valores diários (HRV4Training incluído), métricas e análises clínicas com os "
              "comentários do médico", "daily values (HRV4Training included), metrics and "
              "lab reports with the doctor's comments",
              tables=("metric_defs", "daily_values", "lab_parameters", "lab_reports",
                      "lab_results")),
    Component("calendario", "Calendário", "Calendar",
              "treinos planeados e notas do dia", "planned workouts and day notes",
              tables=("training_plan", "day_notes")),
    Component("ficheiros", "Ficheiros", "Files",
              "treinos exportados, importações e a pasta workouts",
              "exported workouts, imports and the workouts folder",
              folders=("exports", "imports", "workouts")),
    Component("ligacoes", "Ligações externas (credenciais)", "External connections (credentials)",
              "Strava (chaves e sessão) e GarminDB (pastas) — só se pedires: o ficheiro "
              "fica com as tuas chaves",
              "Strava (keys and session) and GarminDB (folders) — only if you ask: the file "
              "keeps your keys",
              settings=_is_ligacao, sensitive=True),
)
BY_KEY = {c.key: c for c in COMPONENTS}
# o que não entra: estado interno e caches que se refazem sozinhas
SKIP_TABLES = ("schema_version", "session_checkpoints", "route_bakes", "ride_zone_cache",
               "sqlite_sequence")
DEFAULT_KEYS = tuple(c.key for c in COMPONENTS if not c.sensitive)


def folder_of(c: Component) -> str:
    return f"{COMPONENTS.index(c) + 1:02d}-{c.key}"


# ------------------------------------------------------------ base de dados


# os módulos que criam tabelas quando são precisos (lista explícita: no
# executável empacotado não se pode ir procurar os módulos à pasta)
ENSURE_MODULES = ("calendar_view", "endurance", "feedback", "fitness_tests", "games",
                  "garmin_sync", "gym", "health", "inventory", "labs", "laps_session",
                  "objectives", "peaks", "rowing", "segments", "session_workouts",
                  "muscles", "strength_builder", "tags", "workout_meta")


def prepare(db) -> None:
    """Cria todas as tabelas que a aplicação conhece (as que nascem quando se
    abre um ecrã também), para exportar e repor sem faltar nenhuma."""
    import importlib
    for name in ENSURE_MODULES:
        try:
            mod = importlib.import_module(f"velo.core.{name}")
        except Exception:
            continue
        for attr in ("ensure", "ensure_table"):
            fn = getattr(mod, attr, None)
            if callable(fn):
                try:
                    fn(db)
                except Exception:
                    pass


def tables_in(db) -> list[str]:
    return [r[0] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def columns(db, table: str) -> list[str]:
    return [r[1] for r in db.conn.execute(f'PRAGMA table_info("{table}")')]


def pk_columns(db, table: str) -> list[str]:
    rows = sorted((r[5], r[1]) for r in db.conn.execute(f'PRAGMA table_info("{table}")')
                  if r[5])
    return [name for _k, name in rows]


def unknown_tables(db) -> list[str]:
    """Tabelas que nenhuma componente cobre (não devia haver nenhuma)."""
    known = {t for c in COMPONENTS for t in c.tables} | set(SKIP_TABLES) | {"settings"}
    return [t for t in tables_in(db) if t not in known]


def _setting_keys(db, c: Component) -> list[str]:
    if c.settings is None:
        return []
    return [r[0] for r in db.conn.execute("SELECT key FROM settings ORDER BY key")
            if c.settings(r[0])]


def _files(data_dir: Path | None, c: Component) -> list[Path]:
    if data_dir is None:
        return []
    out = []
    for name in c.folders:
        base = Path(data_dir) / name
        if base.is_dir():
            out += sorted(p for p in base.rglob("*") if p.is_file())
    return out


def summary(db, data_dir: Path | None = None) -> list[dict]:
    """Cada componente com o número de registos e de ficheiros (para o menu)."""
    prepare(db)
    have = set(tables_in(db))
    out = []
    for c in COMPONENTS:
        n = 0
        for t in c.tables:
            if t in have:
                n += db.conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        n += len(_setting_keys(db, c))
        files = _files(data_dir, c)
        out.append({"key": c.key, "component": c, "rows": n, "files": len(files),
                    "bytes": sum(p.stat().st_size for p in files)})
    return out


# ================================================================ exportar


def _encode(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"$b64": base64.b64encode(bytes(v)).decode("ascii")}
    return v


def _decode(v):
    if isinstance(v, dict) and set(v) == {"$b64"}:
        return base64.b64decode(v["$b64"])
    return v


def default_name(keys: list[str] | None) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    scope = "completo" if not keys or set(keys) >= set(DEFAULT_KEYS) else "parcial"
    return f"perennia-backup_{stamp}_{scope}.zip"


def export(db, data_dir: Path | None, out: Path | str, keys: list[str] | None = None,
           include_secrets: bool = False, progress: Callable[[str], None] | None = None
           ) -> dict:
    """Escreve o backup. `keys`: as componentes (None = tudo); com
    `include_secrets` entram as credenciais. `out`: um ficheiro .zip, ou uma
    pasta (o nome fica com a data). Devolve o manifest (com o caminho)."""
    from velo import __version__
    prepare(db)
    db.conn.commit()
    keys = list(keys) if keys else list(DEFAULT_KEYS)
    if include_secrets and "ligacoes" not in keys:
        keys.append("ligacoes")
    keys = [k for k in keys if k in BY_KEY]
    out = Path(out)
    if out.suffix.lower() != ".zip":
        out.mkdir(parents=True, exist_ok=True)
        out = out / default_name(keys)
    out.parent.mkdir(parents=True, exist_ok=True)
    have = set(tables_in(db))
    manifest = {"app": APP, "format": FORMAT, "version": __version__,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "scope": "completo" if set(keys) >= set(DEFAULT_KEYS) else "parcial",
                "data_dir": str(Path(data_dir).resolve()) if data_dir else None,
                "secrets": "ligacoes" in keys, "components": []}
    tmp = out.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for c in COMPONENTS:
            if c.key not in keys:
                continue
            base = folder_of(c)
            entry = {"key": c.key, "name": c.pt, "folder": base, "tables": {}, "files": []}
            if progress:
                progress(c.name)
            for t in c.tables:
                if t not in have:
                    continue
                cols = columns(db, t)
                n = 0
                with z.open(f"{base}/{t}.jsonl", "w") as f:
                    for row in db.conn.execute(f'SELECT * FROM "{t}"'):
                        f.write((json.dumps({k: _encode(row[i]) for i, k in enumerate(cols)},
                                            ensure_ascii=False) + "\n").encode("utf-8"))
                        n += 1
                entry["tables"][t] = {"rows": n, "columns": cols}
            skeys = _setting_keys(db, c)
            if skeys:
                with z.open(f"{base}/settings.jsonl", "w") as f:
                    for k in skeys:
                        v = db.conn.execute("SELECT value FROM settings WHERE key = ?",
                                            (k,)).fetchone()[0]
                        f.write((json.dumps({"key": k, "value": v}, ensure_ascii=False)
                                 + "\n").encode("utf-8"))
                entry["tables"]["settings"] = {"rows": len(skeys), "columns": ["key", "value"]}
            for p in _files(data_dir, c):
                rel = p.relative_to(data_dir).as_posix()
                data = p.read_bytes()
                z.writestr(f"{base}/ficheiros/{rel}", data)
                entry["files"].append({"path": rel, "bytes": len(data),
                                       "sha256": hashlib.sha256(data).hexdigest()})
            entry["rows"] = sum(x["rows"] for x in entry["tables"].values())
            manifest["components"].append(entry)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("LEIA-ME.txt", _readme(manifest))
    tmp.replace(out)
    manifest["path"] = str(out)
    manifest["bytes"] = out.stat().st_size
    return manifest


def _readme(m: dict) -> str:
    lines = [f"Backup da Perennia {m['version']} — {m['created_at']}",
             f"Âmbito: {m['scope']}" + (" · com credenciais" if m["secrets"] else ""), "",
             "Para repor: Perennia → Backups e reposição → Repor (ou arrasta este .zip",
             "para a janela da Perennia). Pela linha de comandos:",
             "    python main.py --restore este-ficheiro.zip", "",
             "Uma pasta por componente; um ficheiro .jsonl por tabela (um registo por",
             "linha, em JSON); os .fit em <componente>/ficheiros/.", "", "Componentes:"]
    for e in m["components"]:
        files = f", {len(e['files'])} ficheiros" if e["files"] else ""
        lines.append(f"  {e['folder']}: {e['name']} — {e['rows']} registos{files}")
    return "\n".join(lines) + "\n"


# ============================================================== ler um backup


class BackupError(ValueError):
    pass


def inspect(path: Path | str) -> dict:
    """O manifest de um backup (para mostrar antes de repor). Erro se o
    ficheiro não for um backup da Perennia."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read("manifest.json").decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, ValueError) as e:
        raise BackupError(tr("não é um backup da Perennia ({e})",
                             "not a Perennia backup ({e})", e=e)) from e
    if m.get("app") != APP:
        raise BackupError(tr("não é um backup da Perennia", "not a Perennia backup"))
    if int(m.get("format", 0)) > FORMAT:
        raise BackupError(tr("backup de uma versão mais nova da Perennia: atualiza primeiro",
                             "backup from a newer Perennia: update first"))
    m["path"] = str(path)
    m["bytes"] = path.stat().st_size
    return m


def find(folders: list[Path | str], limit: int = 60) -> list[dict]:
    """Os backups da Perennia nestas pastas (os mais recentes primeiro)."""
    seen, out = set(), []
    for folder in folders:
        base = Path(folder).expanduser()
        if not base.is_dir():
            continue
        try:
            files = sorted(base.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            continue
        for p in files[:limit]:
            key = p.resolve()
            if key in seen:
                continue
            seen.add(key)
            try:
                out.append(inspect(p))
            except BackupError:
                continue
    out.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return out[:limit]


# ================================================================ repor


EXTRA_REFS = (
    # (tabela, coluna, tabela apontada, condição) — referências sem chave estrangeira
    ("lab_results", "parameter_id", "lab_parameters", None),
    ("segment_efforts", "segment_id", "perennia_segments", ("source", "perennia")),
    ("strength_laps", "set_id", "strength_sets", None),
)


def _refs(db, tables: set[str]) -> dict[str, list[tuple[str, str, str | None, tuple | None]]]:
    """Para cada tabela: (coluna, tabela apontada, ação ao apagar, condição)."""
    out: dict[str, list] = {t: [] for t in tables}
    for t in tables:
        for r in db.conn.execute(f'PRAGMA foreign_key_list("{t}")'):
            out[t].append((r[3], r[2], r[6], None))
    for t, col, target, cond in EXTRA_REFS:
        if t in out:
            out[t].append((col, target, None, cond))
    return out


def _order(tables: list[str], refs: dict) -> list[str]:
    """As tabelas apontadas antes das que apontam para elas."""
    done: list[str] = []
    pending = list(tables)
    while pending:
        progressed = False
        for t in list(pending):
            deps = {target for _c, target, _a, _cd in refs.get(t, ()) if target in pending
                    and target != t}
            if not deps:
                done.append(t)
                pending.remove(t)
                progressed = True
        if not progressed:                    # ciclo: segue pela ordem que estiver
            done += pending
            break
    return done


def _int_pk(db, t: str) -> str | None:
    info = list(db.conn.execute(f'PRAGMA table_info("{t}")'))
    pks = [r for r in info if r[5]]
    if len(pks) == 1 and (pks[0][2] or "").upper() == "INTEGER":
        return pks[0][1]
    return None


def safety_backup(db, data_dir: Path) -> dict:
    """O que tens agora, antes de repor (com credenciais: é para ficar cá)."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return export(db, data_dir, Path(data_dir) / "backups" /
                  f"perennia-antes-de-repor_{stamp}.zip", keys=list(BY_KEY),
                  include_secrets=True)


def restore(db, data_dir: Path | None, path: Path | str, keys: list[str] | None = None,
            mode: str = "replace", safety: bool = True,
            progress: Callable[[str], None] | None = None) -> dict:
    """Repõe o backup. `keys`: as componentes a repor (None = todas as que o
    ficheiro tem); `mode`: "replace" (substituir) ou "merge" (juntar)."""
    m = inspect(path)
    mode = "merge" if mode in ("merge", "juntar") else "replace"
    entries = [e for e in m["components"] if e["key"] in BY_KEY and
               (keys is None or e["key"] in keys)]
    if not entries:
        raise BackupError(tr("nada para repor", "nothing to restore"))
    prepare(db)
    report = {"mode": mode, "components": [], "rows": 0, "files": 0, "skipped": [],
              "fixed": 0, "safety": None}
    if safety and data_dir is not None:
        report["safety"] = safety_backup(db, data_dir)["path"]
    old_dir = m.get("data_dir")
    have = set(tables_in(db))
    conn = db.conn
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN")
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            # as tabelas de todas as componentes, pela ordem das referências
            plan: list[tuple[dict, str]] = []
            for e in entries:
                for t in e["tables"]:
                    plan.append((e, t))
            tabs = {t for _e, t in plan if t != "settings"}
            refs = _refs(db, {t for t in tabs if t in have})
            order = _order([t for t in tabs if t in have], refs)
            ordered = [(e, t) for e, t in plan if t == "settings"] + \
                [(e, t) for t in order for e, tt in plan if tt == t]
            for t in tabs - have:
                report["skipped"].append(t)
            idmap: dict[str, dict] = {}
            last = None
            if mode == "replace":
                for e, t in ordered:
                    c = BY_KEY[e["key"]]
                    if t == "settings":
                        for k in _setting_keys(db, c):
                            conn.execute("DELETE FROM settings WHERE key = ?", (k,))
                    elif t in have:
                        conn.execute(f'DELETE FROM "{t}"')
            for e, t in ordered:
                c = BY_KEY[e["key"]]
                if t != "settings" and t not in have:
                    continue
                name = f"{e['folder']}/{t}.jsonl"
                if name not in names:
                    continue
                if progress and c.name != last:
                    progress(c.name)
                    last = c.name
                n = _load_table(db, z, name, t, c, mode, refs.get(t, []), idmap, old_dir,
                                data_dir)
                report["rows"] += n
            # os ficheiros (.fit e afins)
            if data_dir is not None:
                for e in entries:
                    for f in e.get("files") or []:
                        rel = PurePosixPath(f["path"])
                        if rel.is_absolute() or ".." in rel.parts:
                            continue
                        src = f"{e['folder']}/ficheiros/{rel.as_posix()}"
                        if src not in names:
                            continue
                        dst = Path(data_dir) / Path(*rel.parts)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if mode == "merge" and dst.exists():
                            continue
                        dst.write_bytes(z.read(src))
                        report["files"] += 1
            for e in entries:
                report["components"].append(e["key"])
        report["fixed"] = _fix_orphans(db)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    _after(db)
    return report


def _rewrite_path(v, old_dir: str | None, data_dir: Path | None):
    """Um caminho absoluto da pasta antiga passa para a pasta de agora."""
    if not isinstance(v, str) or not old_dir or data_dir is None:
        return v
    if v.startswith(old_dir):
        rest = v[len(old_dir):].lstrip("/\\")
        return str(Path(data_dir) / Path(*PurePosixPath(rest.replace("\\", "/")).parts))
    return v


PATH_COLUMNS = ("fit_path",)


def _load_table(db, z, name: str, t: str, c: Component, mode: str, refs: list,
                idmap: dict, old_dir, data_dir) -> int:
    conn = db.conn
    n = 0
    if t == "settings":
        for line in io.TextIOWrapper(z.open(name), encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if c.settings is not None and not c.settings(r["key"]):
                continue
            verb = "INSERT OR IGNORE" if mode == "merge" else "INSERT OR REPLACE"
            conn.execute(f"{verb} INTO settings(key, value) VALUES (?, ?)",
                         (r["key"], r["value"]))
            n += 1
        return n
    target_cols = set(columns(db, t))
    ipk = _int_pk(db, t) if mode == "merge" else None
    batch: list[tuple] = []
    sig = None
    for line in io.TextIOWrapper(z.open(name), encoding="utf-8"):
        if not line.strip():
            continue
        row = {k: _decode(v) for k, v in json.loads(line).items() if k in target_cols}
        for col in PATH_COLUMNS:
            if col in row:
                row[col] = _rewrite_path(row[col], old_dir, data_dir)
        if mode == "merge":
            for col, target, _act, cond in refs:
                if col in row and row[col] is not None and target in idmap:
                    if cond is not None and row.get(cond[0]) != cond[1]:
                        continue
                    row[col] = idmap[target].get(row[col], row[col])
            if t == "strength_structures" and "exercises" in idmap and row.get("data"):
                row["data"] = _remap_exercises(row["data"], idmap["exercises"])
            if ipk is not None:
                old = row.pop(ipk, None)
                new = _merge_int(conn, t, ipk, row, old)
                idmap.setdefault(t, {})[old] = new
                n += 1
                continue
        keys = tuple(sorted(row))
        if keys != sig and batch:
            n += _flush(conn, t, sig, batch, mode)
            batch = []
        sig = keys
        batch.append(tuple(row[k] for k in keys))
        if len(batch) >= 2000:
            n += _flush(conn, t, sig, batch, mode)
            batch = []
    if batch:
        n += _flush(conn, t, sig, batch, mode)
    return n


def _flush(conn, t: str, cols: tuple, rows: list, mode: str) -> int:
    verb = "INSERT OR IGNORE" if mode == "merge" else "INSERT OR REPLACE"
    names = ", ".join(f'"{c}"' for c in cols)
    marks = ", ".join("?" for _ in cols)
    conn.executemany(f'{verb} INTO "{t}" ({names}) VALUES ({marks})', rows)
    return len(rows)


def _merge_int(conn, t: str, pk: str, row: dict, old) -> int:
    """Juntar um registo com id numérico: se já houver um igual (tirando o
    id), é esse; senão entra com o mesmo id se estiver livre, ou com um novo."""
    cols = sorted(row)
    if cols:
        where = " AND ".join(f'"{c}" IS ?' for c in cols)
        hit = conn.execute(f'SELECT "{pk}" FROM "{t}" WHERE {where} LIMIT 1',
                           [row[c] for c in cols]).fetchone()
        if hit is not None:
            return hit[0]
    free = old is not None and conn.execute(f'SELECT 1 FROM "{t}" WHERE "{pk}" = ?',
                                            (old,)).fetchone() is None
    names = ([pk] if free else []) + cols
    vals = ([old] if free else []) + [row[c] for c in cols]
    cur = conn.execute(f'INSERT INTO "{t}" ({", ".join(chr(34) + c + chr(34) for c in names)})'
                       f' VALUES ({", ".join("?" for _ in names)})', vals)
    return old if free else cur.lastrowid


def _remap_exercises(data: str, ids: dict) -> str:
    try:
        obj = json.loads(data)
    except (TypeError, ValueError):
        return data

    def walk(x):
        if isinstance(x, dict):
            return {k: (ids.get(v, v) if k == "exercise_id" else walk(v)) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return json.dumps(walk(obj), ensure_ascii=False)


def _fix_orphans(db) -> int:
    """Referências que ficaram sem destino (uma sessão de uma rota que não veio
    no backup): ficam vazias (SET NULL) ou saem (CASCADE), como a base de
    dados faria ao apagar."""
    conn = db.conn
    fixed = 0
    for _ in range(4):                        # o que sai pode deixar outros sem pai
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if not bad:
            break
        for table, fkid in sorted({(r[0], r[3]) for r in bad}):
            fk = [r for r in conn.execute(f'PRAGMA foreign_key_list("{table}")')
                  if r[0] == fkid]
            if not fk:
                continue
            _id, _seq, parent, col, to, _upd, on_delete, _m = fk[0]
            to = to or (pk_columns(db, parent) or ["rowid"])[0]
            orphan = (f'"{col}" IS NOT NULL AND "{col}" NOT IN '
                      f'(SELECT "{to}" FROM "{parent}" WHERE "{to}" IS NOT NULL)')
            if (on_delete or "").upper() == "SET NULL":
                cur = conn.execute(f'UPDATE "{table}" SET "{col}" = NULL WHERE {orphan}')
            else:
                cur = conn.execute(f'DELETE FROM "{table}" WHERE {orphan}')
            fixed += max(0, cur.rowcount)
    return fixed


def _after(db) -> None:
    """Arrumação depois de repor: cópias de treinos e tempos sem sessão."""
    for mod_name in ("session_workouts", "segments"):
        try:
            import importlib
            importlib.import_module(f"velo.core.{mod_name}").purge(db)
        except Exception:
            pass
    try:
        from . import session_workouts as sw
        tables = " UNION ".join(f"SELECT id FROM {t}" for t in sorted(set(sw.TABLES.values())))
        db.conn.execute(f"DELETE FROM session_workouts WHERE copy_id NOT IN ({tables})")
        db.conn.commit()
    except Exception:
        pass


# ================================================================ linha de comandos


def cli_export(db, data_dir: Path, out: str | None, keys: list[str] | None,
               secrets: bool) -> int:
    dest = Path(out) if out else Path(data_dir) / "backups"
    m = export(db, data_dir, dest, keys, include_secrets=secrets,
               progress=lambda n: print(f"  {n}…"))
    print(f"Backup feito: {m['path']} ({m['bytes'] / 1024:.0f} KB)")
    for e in m["components"]:
        print(f"  {e['folder']}: {e['rows']} registos, {len(e['files'])} ficheiros")
    return 0


def cli_restore(db, data_dir: Path, path: str, keys: list[str] | None, mode: str) -> int:
    m = inspect(path)
    print(f"Backup de {m['created_at']} (Perennia {m['version']}, {m['scope']})")
    rep = restore(db, data_dir, path, keys, mode, progress=lambda n: print(f"  {n}…"))
    print(f"Reposto ({'substituir' if rep['mode'] == 'replace' else 'juntar'}): "
          f"{rep['rows']} registos, {rep['files']} ficheiros")
    if rep["safety"]:
        print(f"Antes de repor, o que tinhas ficou em: {rep['safety']}")
    if rep["fixed"]:
        print(f"{rep['fixed']} referências sem destino arrumadas")
    return 0
