"""A instalação num computador novo: o que o `perennia_setup` (.bat no Windows, .sh no macOS e
no Linux) faz depois de criar o ambiente virtual (`.venv`) e instalar os requisitos:

1. a pasta `data/` com a estrutura toda (`data/in/…`, `data/out/…`, `data/garmin/…`) e os
   ficheiros modelo em `data/in` (ver `perennia.core.folders`); se houver dados de uma versão
   antiga na pasta do sistema, são **copiados** para `data/` (ver `perennia.datadir`);
2. a base de dados `data/perennia.db` com o conteúdo de base: os treinos que vêm com a
   aplicação (ciclismo, corrida, natação, remo), os exercícios e as modalidades do ginásio, os
   complexos, os testes de aptidão, as métricas da Saúde e os glossários;
3. o autoteste do núcleo (o mesmo de `python main.py --self-test`);
4. **opcional** — o GarminDB: instala-o no `.venv`, guarda o **utilizador** (o e-mail da conta
   Garmin) em `data/garmin/config` e faz o primeiro login, que pede a palavra-passe e, se a
   conta tiver, o código MFA. A palavra-passe **não fica guardada em lado nenhum**: escreve-se
   de cada vez que se sincroniza;
5. **opcional** — o atalho no Ambiente de trabalho;
6. o resumo do que ficou feito.

Pode correr-se as vezes que quiseres: o que já existe fica como está (os teus dados, os modelos
que mudaste, a configuração do GarminDB).

Sem janela nem pyglet. As perguntas vêm de `ask` (e a palavra-passe de `secret`) para os testes
poderem responder sem teclado; `--sem-perguntas` responde «não» ao que é opcional.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import datadir, paths

# os módulos com conteúdo de base (`seed`), pela ordem em que se põem
SEED_MODULES = ("workout_library", "endurance", "rowing", "strength", "gym", "complexes",
                "fitness_tests", "health", "health_catalog")


def _say(text: str = "") -> None:
    print(text, flush=True)


def _yes(answer: str, default: bool) -> bool:
    a = (answer or "").strip().lower()
    if not a:
        return default
    return a[0] in ("s", "y")


def database(data_dir: Path) -> dict:
    """Cria (ou completa) a base de dados com todas as tabelas e o conteúdo de base. Devolve
    as contagens para o resumo."""
    from .core import backup
    from .core.db import Database
    db = Database(datadir.database_path(data_dir))
    try:
        backup.prepare(db)                       # todas as tabelas que a aplicação conhece
        problems: list[str] = []
        for name in SEED_MODULES:
            try:
                mod = importlib.import_module(f"perennia.core.{name}")
                mod.seed(db)
                if name == "endurance" and hasattr(mod, "seed_tests"):
                    mod.seed_tests(db)
            except Exception as e:               # um conteúdo que falha não pára o resto
                problems.append(f"{name}: {e}")
        for name in ("glossary", "lab_glossary", "muscles", "inventory", "programs"):
            try:
                importlib.import_module(f"perennia.core.{name}").ensure(db)
            except Exception as e:
                problems.append(f"{name}: {e}")
        try:
            from .core import indexes
            indexes.ensure(db)
        except Exception:
            pass

        def count(sql: str) -> int:
            try:
                return int(db.conn.execute(sql).fetchone()[0])
            except Exception:
                return 0
        return {"workouts": count("SELECT COUNT(*) FROM workouts")
                + count("SELECT COUNT(*) FROM endurance_workouts")
                + count("SELECT COUNT(*) FROM row_workouts"),
                "exercises": count("SELECT COUNT(*) FROM exercises"),
                "metrics": count("SELECT COUNT(*) FROM metric_defs"),
                "tests": count("SELECT COUNT(*) FROM fitness_tests"),
                "problems": problems}
    finally:
        db.close()


# ------------------------------------------------------------------ GarminDB


def garmin_installed() -> bool:
    from .core import importers
    return importers.garmindb_cli() is not None


def python_ok_for_garmindb() -> bool:
    from .core import garmin_sync as gs
    return tuple(sys.version_info[:2]) >= gs.MIN_PYTHON


def install_garmindb(call: Callable = subprocess.call) -> bool:
    """`pip install --upgrade "garmindb>=4"` no mesmo Python (o `.venv` da Perennia). O GarminDB
    4 precisa do Python 3.12+: com um Python mais antigo não se instala (o GarminDB 3.x já não
    funciona — o fitfile 2.0 tirou o `field_enums` e o login antigo deixou de entrar)."""
    from .core import garmin_sync as gs
    if not python_ok_for_garmindb():
        _say(f"  O GarminDB precisa do Python 3.12 ou mais recente (o .venv usa o "
             f"{sys.version_info[0]}.{sys.version_info[1]}). Instala o Python 3.12+ "
             "(python.org), apaga a pasta .venv e corre o perennia_setup outra vez.")
        return False
    _say(f"  A instalar o GarminDB 4 (pip install --upgrade \"{gs.GARMINDB_SPEC}\")…")
    code = call(gs.repair_command())
    import importlib
    importlib.invalidate_caches()
    gs.clear_caches()
    return code == 0 and garmin_installed()


def garmin(data_dir: Path, ask: Callable[[str], str], secret: Callable[[str], str],
           call: Callable = subprocess.call) -> dict:
    """O GarminDB, se quiseres: instalar, o utilizador e o primeiro login (com MFA)."""
    from .core import folders, garmin_sync as gs
    out = {"wanted": False, "installed": garmin_installed(), "user": "", "login": None}
    user, have_cfg = gs.credentials(gs.config_path())
    out["user"] = user
    _say()
    _say("GarminDB (opcional) — traz os teus dados do Garmin Connect (sono, HRV, passos, "
         "atividades…).")
    if have_cfg and user:
        _say(f"  Já está configurado para {user}.")
    if not _yes(ask("  Configurar o GarminDB agora? [s/N] "), False):
        return out
    out["wanted"] = True
    if out["installed"]:
        comp = gs.compatibility()
        for p in comp["problems"]:
            _say(f"  ✗ {p['text']}")
        if comp["problems"]:
            if not comp["python_ok"]:
                install_garmindb(call)              # explica o que fazer com o Python
                return out
            if _yes(ask("  Atualizar o GarminDB para a versão 4? [S/n] "), True):
                out["installed"] = install_garmindb(call)
            if not out["installed"]:
                return out
    if not out["installed"]:
        out["installed"] = install_garmindb(call)
        if not out["installed"]:
            _say("  Não consegui instalar o GarminDB. Podes tentar mais tarde: corre o "
                 "perennia_setup outra vez.")
            return out
    typed = ask(f"  E-mail da conta Garmin Connect{' [' + user + ']' if user else ''}: ").strip()
    if typed or not user:
        if not typed:
            _say("  Sem e-mail não há GarminDB. Podes escrevê-lo depois em Definições → "
                 "Ligações externas.")
            return out
        gs.write_credentials(gs.config_path(), typed)
        out["user"] = typed
    _say(f"  Configuração: {folders.shown(gs.config_path(), data_dir)} (sem palavra-passe)")
    _say(f"  Dados do GarminDB: {folders.shown(folders.garmin_bases_dir(data_dir), data_dir)}")
    if not _yes(ask("  Fazer já o primeiro login? Pede a palavra-passe e, se a conta tiver, o "
                    "código MFA (recomendado) [S/n] "), True):
        return out
    password = secret("  Palavra-passe do Garmin Connect (não fica guardada): ")
    if not password:
        _say("  Sem palavra-passe: fica para a primeira sincronização.")
        return out
    _say("  A entrar no Garmin Connect… (se pedir «MFA code», escreve o código que te chegou)")
    try:
        code = gs.interactive_login(None, password, call=call)
    finally:
        password = ""                           # noqa: F841 — não fica na memória
    out["login"] = code == 0
    _say("  Login feito: o GarminDB guardou a sessão (o token, não a palavra-passe)."
         if code == 0 else
         f"  O GarminDB acabou com erro ({code}). Vê a mensagem acima; podes repetir com "
         "«python main.py --garmin-login».")
    return out


def login_cli(data_dir: Path, user: str | None, ask: Callable[[str], str] = input,
              secret: Callable[[str], str] | None = None) -> int:
    """`main.py --garmin-login [E-MAIL]`: o login do GarminDB num terminal (para o código MFA)."""
    import getpass
    from .core import garmin_sync as gs
    secret = secret or getpass.getpass
    datadir.prepare(data_dir)
    if not garmin_installed():
        _say("O GarminDB não está instalado. Instala-o com: python -m pip install \"garmindb>=4\" "
             "(ou corre o perennia_setup).")
        return 2
    have, _cfg = gs.credentials(gs.config_path())
    user = (user or "").strip() or have or ask("E-mail da conta Garmin Connect: ").strip()
    if not user:
        _say("Sem e-mail não dá para entrar.")
        return 2
    if user != have:
        gs.write_credentials(gs.config_path(), user)
    password = secret(f"Palavra-passe de {user} (não fica guardada): ")
    if not password:
        _say("Sem palavra-passe: nada feito.")
        return 2
    try:
        code = gs.interactive_login(None, password)
    finally:
        password = ""                           # noqa: F841
    _say("Login feito." if code == 0 else f"O GarminDB acabou com erro ({code}).")
    return 0 if code == 0 else 1


# -------------------------------------------------------------------- atalho


def shortcut(call: Callable = subprocess.call) -> str | None:
    """O atalho «Perennia» no Ambiente de trabalho. Devolve onde ficou (ou None)."""
    root = paths.app_dir()
    if os.name == "nt":
        ps1 = root / "packaging" / "criar_atalho.ps1"
        code = call(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                     str(ps1)])
        return str(Path.home() / "Desktop" / "Perennia.lnk") if code == 0 else None
    launcher = root / "perennia.sh"
    desktop = _desktop_dir()
    if sys.platform == "darwin":
        target = desktop / "Perennia.command"
        target.write_text(f'#!/bin/sh\nexec "{launcher}"\n', encoding="utf-8")
        target.chmod(0o755)
        return str(target)
    icon = root / "perennia" / "assets" / "app_icon.png"
    entry = ("[Desktop Entry]\nType=Application\nName=Perennia\n"
             "Comment=Treino indoor\n"
             f'Exec="{launcher}"\nPath={root}\n'
             + (f"Icon={icon}\n" if icon.exists() else "") + "Terminal=false\n"
             "Categories=Sports;\n")
    apps = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / \
        "applications"
    made = None
    for folder in (apps, desktop):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            p = folder / "perennia.desktop"
            p.write_text(entry, encoding="utf-8")
            p.chmod(0o755)
            made = str(p)
        except OSError:
            continue
    return made


def _desktop_dir() -> Path:
    home = Path.home()
    for name in ("Desktop", "Ambiente de trabalho", "Área de Trabalho", "Secretária"):
        if (home / name).is_dir():
            return home / name
    return home / "Desktop"


# -------------------------------------------------------------------- tudo


def run(data_dir: Path | None = None, interactive: bool = True,
        ask: Callable[[str], str] | None = None, secret: Callable[[str], str] | None = None,
        self_test: Callable[[], int] | None = None, call: Callable = subprocess.call) -> int:
    """A instalação toda. Devolve 0 se correu bem (o GarminDB e o atalho não contam)."""
    import getpass
    from .core import folders
    explicit = data_dir is not None or bool(os.environ.get("PERENNIA_DATA_DIR"))
    data_dir = Path(data_dir) if data_dir is not None else datadir.default_data_dir()
    if not interactive:
        ask = lambda _q: ""                    # noqa: E731 — tudo o que é opcional: não
        secret = lambda _q: ""                 # noqa: E731
    ask = ask or input
    secret = secret or getpass.getpass
    _say("=" * 64)
    _say("Perennia — instalação")
    _say("=" * 64)
    _say(f"Pasta da Perennia: {paths.app_dir()}")
    _say(f"Os teus dados:     {data_dir}")
    _say()
    _say("1/5  Pastas de dados e modelos")
    before = data_dir.exists() and (data_dir / datadir.DB_NAME).exists()
    report = datadir.prepare(data_dir, migrate=not explicit)
    if report and report.get("error"):
        _say(f"  Não consegui copiar os dados antigos: {report['error']}")
    elif report:
        _say(f"  Copiei os dados da versão anterior ({report['from']}): {report['files']} "
             f"ficheiros; os originais ficaram onde estavam (ver data/{datadir.MIGRATED_NOTE}).")
    n_models = sum(1 for p in (data_dir / "in").rglob("*") if p.is_file())
    _say(f"  data/in (importar) · data/out (exportar) · data/garmin — {n_models} ficheiros em "
         "data/in")
    _say()
    _say("2/5  Base de dados")
    counts = database(data_dir)
    _say(("  Já existia: completei o que faltava. " if before else "  Criada. ")
         + f"{counts['workouts']} treinos, {counts['exercises']} exercícios, "
         f"{counts['tests']} testes, {counts['metrics']} métricas de saúde.")
    for p in counts["problems"]:
        _say(f"  (aviso) {p}")
    _say()
    _say("3/5  Autoteste do núcleo")
    ok = True
    if self_test is not None:
        try:
            ok = self_test() == 0
        except Exception as e:
            _say(f"  Falhou: {e}")
            ok = False
    _say()
    _say("4/5  GarminDB")
    if interactive:
        g = garmin(data_dir, ask, secret, call)
    else:
        from .core import garmin_sync as gs
        user, _cfg = gs.credentials(gs.config_path())
        g = {"wanted": bool(user), "installed": garmin_installed(), "user": user,
             "login": None}
        _say("  (sem perguntas) fica como está" + (f": {user}" if user else "") + ".")
    _say()
    _say("5/5  Atalho")
    made = None
    if not interactive:
        _say("  (sem perguntas) não criei.")
    elif _yes(ask("  Criar o atalho «Perennia» no Ambiente de trabalho? [S/n] "), True):
        try:
            made = shortcut(call)
        except Exception as e:
            _say(f"  Não consegui: {e}")
        if made:
            _say(f"  Atalho: {made}")
    _say()
    _say("=" * 64)
    _say("Pronto." if ok else "Instalado, mas o autoteste falhou (vê acima).")
    _say(f"  Dados: {data_dir}")
    _say(f"  Põe em {folders.shown(folders.in_dir('gpx', data_dir), data_dir)}, "
         f"{folders.shown(folders.in_dir('workouts', data_dir), data_dir)}, … o que quiseres "
         "importar; o que a Perennia grava fica em data/out.")
    if g["wanted"] and g["user"]:
        _say(f"  GarminDB: {g['user']}" + (" · login feito" if g["login"] else "")
             + " · a palavra-passe é pedida a cada sincronização.")
    else:
        _say("  GarminDB: não configurado (corre o perennia_setup outra vez quando quiseres).")
    opener = "Perennia.bat" if os.name == "nt" else "./perennia.sh"
    _say(f"  Abrir: {'o atalho, ou ' if made else ''}{opener}")
    _say("=" * 64)
    return 0 if ok else 1
