"""Definições → Sincronização: trazer os dados de uma fonte (por agora, o
GarminDB) para a base da Perennia. As opções são as do GarminDB — que dados,
que passos, que período — e ficam guardadas com o Guardar das Definições.

`SyncPanel` dá as linhas e trata das teclas dentro das Definições: lê e
escreve no rascunho delas (`store.get` / `store.put`), por isso nada fica
gravado sem carregar em Guardar.
"""
from __future__ import annotations

from datetime import date, timedelta

from pyglet.window import key

from velo.core import garmin_sync as gs
from velo.core.i18n import t, tr
from velo.ui.app import ConfirmScreen, Screen
from velo.ui.widgets import Item

STAT_NAMES = {
    "activities": ("Atividades", "Activities"),
    "monitoring": ("Monitorização diária (passos, stress, Body Battery…)",
                   "Daily monitoring (steps, stress, Body Battery…)"),
    "rhr": ("FC em repouso", "Resting HR"),
    "hrv": ("HRV", "HRV"),
    "sleep": ("Sono", "Sleep"),
    "weight": ("Peso", "Weight"),
}
STEP_NAMES = {
    "download": (("Descarregar do Garmin Connect", "Download from Garmin Connect"), "--download"),
    "copy": (("Copiar de um relógio ligado por USB", "Copy from a USB-connected watch"),
             "--copy"),
    "import_": (("Importar para as bases do GarminDB", "Import into the GarminDB databases"),
                "--import"),
    "analyze": (("Analisar (resumos do GarminDB)", "Analyze (GarminDB summaries)"),
                "--analyze"),
    "overwrite": (("Voltar a descarregar o que já existe", "Download again what already exists"),
                  "--overwrite"),
}


def _period_name(p: str) -> str:
    return {"latest": tr("Só o mais recente", "Only the latest"),
            "all": tr("Todo o histórico", "The whole history"),
            "range": tr("Um intervalo de datas", "A date range")}[p]


def _day(iso: str | None) -> str:
    if not iso:
        return "—"
    d = date.fromisoformat(iso)
    return d.strftime("%d/%m/%Y")


class SyncPanel:
    """As linhas e o comportamento da sincronização, dentro de um ecrã."""

    def __init__(self, screen: Screen, runner=None, store=None):
        self.screen = screen
        self.app = screen.app
        self.store = store or screen    # o rascunho das Definições
        self.runner = runner            # para os testes: corre «subprocess.run» falso
        self.job = None
        self.last_report: dict | None = None
        self.last_error = ""

    @property
    def opts(self) -> gs.Options:
        return gs.options_from(self.store.get("sync_garmindb", {}) or {})

    def save(self, o: gs.Options) -> None:
        from dataclasses import asdict
        self.store.put("sync_garmindb", asdict(o.clean()))

    def folder(self, field: str) -> str:
        db = self.app.db
        default = str(gs.db_dir(db)) if field == "garmindb_dir" else str(gs.config_dir(db))
        return str(self.store.get(field, "") or default)

    @property
    def pending(self) -> bool:
        """Há alterações por guardar nas Definições? (sincronizar usa o que está gravado)"""
        return bool(getattr(self.store, "dirty", False))

    @property
    def busy(self) -> bool:
        return self.job is not None and not self.job.done

    # ------------------------------------------------------------- linhas

    def items(self) -> list[Item]:
        db = self.app.db
        o = self.opts
        st = gs.status(db)
        yes, no = "✓", "✗"
        state = " · ".join([
            tr("GarminDB instalado", "GarminDB installed") + f" {yes if st['cli'] else no}",
            tr("configuração", "config") + f" {yes if st['config_found'] else no}",
            f"garmin.db {yes if st['garmin_db'] else no}",
            f"garmin_activities.db {yes if st['activities_db'] else no}"])
        rows = [
            Item(tr("Fonte", "Source"), value="GarminDB", data="sync:source",
                 detail=tr("a única fonte, por agora: lê o que o GarminDB descarregou do "
                           "Garmin Connect", "the only source for now: reads what GarminDB "
                           "downloaded from Garmin Connect")),
            Item(tr("Estado", "Status"),
                 value=tr("a sincronizar…", "syncing…") if self.busy else
                 (st["last_sync"] or tr("nunca sincronizado", "never synced")),
                 detail=state + ("" if st["cli"] else " · pip install garmindb"),
                 enabled=False),
            Item(tr("Período", "Period"), value=_period_name(o.period), data="sync:period",
                 detail={"latest": tr("--latest: desde o último dia que o GarminDB já tem",
                                      "--latest: since the last day GarminDB already has"),
                         "all": tr("sem --latest: desde as datas de início da configuração",
                                   "no --latest: from the start dates in the config"),
                         "range": tr("as datas vão para a configuração do GarminDB "
                                     "(*_start_date / *_end_date)",
                                     "the dates go to the GarminDB config "
                                     "(*_start_date / *_end_date)")}[o.period]),
        ]
        if o.period == "range":
            rows += [Item(tr("Desde", "From"), value=_day(o.start), data="sync:start",
                          detail=tr("←/→ um dia · Shift+←/→ um mês", "←/→ one day · "
                                    "Shift+←/→ one month")),
                     Item(tr("Até", "To"), value=_day(o.end), data="sync:end",
                          detail=tr("←/→ um dia · Shift+←/→ um mês", "←/→ one day · "
                                    "Shift+←/→ one month")),
                     Item(tr("Escrever as datas na configuração", "Write the dates to the config"),
                          value=t("common.on") if o.write_config else t("common.off"),
                          data="sync:opt:write_config",
                          detail=tr("←/→ muda · com uma cópia .bak de GarminConnectConfig.json",
                                    "←/→ changes · with a .bak copy of GarminConnectConfig.json"))]
        elif o.period == "all":
            dates = [d for d, _e in st["dates"].values() if d]
            if dates:
                rows.append(Item(tr("Início na configuração", "Start in the config"),
                                 value=_day(min(dates)), enabled=False,
                                 detail=tr("o mais antigo das datas de início do GarminDB",
                                           "the earliest GarminDB start date")))
        rows.append(Item(tr("— Dados —", "— Data —"), enabled=False,
                         detail=tr("←/→ liga/desliga · todos = --all",
                                   "←/→ on/off · all = --all")))
        for k, short, long in gs.STATS:
            on = k in o.stats
            rows.append(Item(("✓ " if on else "   ") + tr(*STAT_NAMES[k]), value=long,
                             data=f"sync:stat:{k}"))
        rows.append(Item(tr("— Passos do GarminDB —", "— GarminDB steps —"), enabled=False,
                         detail=tr("←/→ liga/desliga", "←/→ on/off")))
        for k, ((pt, en), flag) in STEP_NAMES.items():
            on = bool(getattr(o, k))
            rows.append(Item(("✓ " if on else "   ") + tr(pt, en), value=flag,
                             data=f"sync:opt:{k}"))
        from pathlib import Path
        ready = not self.busy and not self.pending
        wait = tr("guarda primeiro as alterações", "save your changes first") \
            if self.pending else ""
        rows += [
            Item(tr("Pasta das bases do GarminDB", "GarminDB databases folder"),
                 value=self.folder("garmindb_dir") + "▏", data="text:garmindb_dir",
                 detail=tr("por omissão ~/HealthData/DBs", "default ~/HealthData/DBs")),
            Item(tr("Pasta da configuração", "Config folder"),
                 value=self.folder("garmindb_config_dir") + "▏", data="text:garmindb_config_dir",
                 detail=tr("por omissão ~/.GarminDb · o utilizador e a palavra-passe estão em "
                           "Ligações Externas", "default ~/.GarminDb · user and password are in "
                           "External connections")),
            Item(tr("Comando", "Command"),
                 detail=gs.command_text(db, o, Path(self.folder("garmindb_config_dir"))),
                 enabled=False),
            Item(tr("Cópia de segurança das bases (--backup)", "Back up the databases (--backup)"),
                 action=lambda: self.ask_maintenance("backup"), enabled=st["cli"] and ready,
                 detail=wait),
            Item(tr("Reconstruir as bases (--rebuild_db)", "Rebuild the databases (--rebuild_db)"),
                 action=lambda: self.ask_maintenance("rebuild"),
                 enabled=st["cli"] and ready,
                 detail=wait or tr("se o GarminDB pedir (mudança de versão)",
                                   "if GarminDB asks for it (version change)")),
            Item(tr("Só importar", "Import only"), action=self.import_only, button=True,
                 enabled=(st["garmin_db"] or st["activities_db"]) and ready),
            Item(tr("A sincronizar…", "Syncing…") if self.busy else
                 tr("Sincronizar agora", "Sync now"), action=self.sync_now, button=True,
                 primary=True, enabled=ready),
        ]
        return rows

    # ------------------------------------------------------------- mexer

    def toggle_stat(self, k: str) -> None:
        o = self.opts
        if k in o.stats:
            if len(o.stats) > 1:
                o.stats.remove(k)
        else:
            o.stats.append(k)
        self.save(o)
        self.screen.enter()

    def toggle(self, k: str) -> None:
        o = self.opts
        setattr(o, k, not getattr(o, k))
        self.save(o)
        self.screen.enter()

    def adjust(self, field: str, step: int, big: bool) -> bool:
        """←/→ numa linha da sincronização. Devolve True se era dela."""
        o = self.opts
        if field == "period":
            ps = list(gs.PERIODS)
            o.period = ps[(ps.index(o.period) + (1 if step > 0 else -1)) % len(ps)]
        elif field in ("start", "end"):
            o.clean()
            cur = date.fromisoformat(getattr(o, field) or date.today().isoformat())
            delta = timedelta(days=(30 if big else 1) * (1 if step > 0 else -1))
            new = min(date.today(), cur + delta).isoformat()
            setattr(o, field, new)
            if o.start and o.end and o.start > o.end:
                if field == "start":
                    o.end = o.start
                else:
                    o.start = o.end
        elif field.startswith("stat:"):
            self.toggle_stat(field[5:])
            return True
        elif field.startswith("opt:"):
            self.toggle(field[4:])
            return True
        elif field == "source":
            return True                       # só há uma fonte, por agora
        else:
            return False
        self.save(o)
        self.screen.enter()
        return True

    def text(self, field: str, text: str | None) -> bool:
        if field not in ("garmindb_dir", "garmindb_config_dir"):
            return False
        cur = self.folder(field)
        self.store.put(field, cur[:-1] if text is None else cur + text)
        self.screen.enter()
        return True

    # ------------------------------------------------------------- correr

    def _job(self, fn) -> None:
        from velo.ui.connect_screens import Job
        self.job = Job(fn)
        self.screen.enter()

    def sync_now(self) -> None:
        if self.busy or self.pending:
            return
        db, o, runner = self.app.db, self.opts, self.runner
        if not gs.status(db)["cli"]:
            # sem o GarminDB instalado, importa-se o que já lá estiver
            self.app.message(tr("GarminDB não instalado: importo só o que já está nas bases.",
                                "GarminDB not installed: importing what is already there."))
            self.import_only()
            return
        self._job(lambda: gs.sync(db, o, runner=runner))

    def import_only(self) -> None:
        if self.busy or self.pending:
            return
        db, o = self.app.db, self.opts
        try:
            ok, msg, rep = gs.sync(db, o, run_source=False)
        except Exception as e:
            ok, msg, rep = False, str(e), None
        self._done(ok, msg, rep)

    def ask_maintenance(self, action: str) -> None:
        a = self.app
        title = tr("Cópia de segurança das bases?", "Back up the databases?") \
            if action == "backup" else tr("Reconstruir as bases do GarminDB?",
                                          "Rebuild the GarminDB databases?")
        sub = tr("O GarminDB faz um .zip em HealthData/Backups.",
                 "GarminDB writes a .zip to HealthData/Backups.") if action == "backup" else \
            tr("Apaga as bases do GarminDB e volta a importá-las dos ficheiros que já tem.",
               "Deletes the GarminDB databases and re-imports them from its files.")

        def go() -> None:
            a.pop()
            db, runner = a.db, self.runner
            self._job(lambda: (gs.maintenance(db, action, runner=runner), action))
        a.push(ConfirmScreen(a, title, sub, [(tr("Cancelar", "Cancel"), a.pop),
                                             (tr("Sim, continuar", "Yes, go on"), go)],
                             default=0, buttons=True, cancel=a.pop))

    def _done(self, ok: bool, msg: str, rep: dict | None) -> None:
        a = self.app
        if ok and rep is not None:
            self.last_report = rep
            a.message(tr("Sincronizado: {v} valores em {d} dias · {n} atividades ({k} novas)",
                         "Synced: {v} values over {d} days · {n} activities ({k} new)",
                         v=rep["values"], d=rep["days"], n=rep["activities"],
                         k=rep["new_activities"]))
        else:
            self.last_error = msg
            a.message("GarminDB: " + (msg or tr("falhou", "failed")))
        self.screen.enter()

    def update(self) -> None:
        j = self.job
        if j is None or not j.done:
            return
        self.job = None
        res = j.result
        if j.error:
            self._done(False, j.error, None)
        elif isinstance(res, tuple) and len(res) == 2 and isinstance(res[1], str) \
                and res[1] in ("backup", "rebuild"):
            (ok, out), action = res
            self.app.message(("GarminDB: " + (tr("cópia feita", "backup done") if action ==
                                              "backup" else tr("bases reconstruídas",
                                                               "databases rebuilt")))
                             if ok else "GarminDB: " + (out.splitlines()[-1] if out else "falhou"))
            self.screen.enter()
        else:
            ok, msg, rep = res
            self._done(ok, msg, rep)


def history_items(app, sport: str) -> list[Item]:
    """As atividades sincronizadas (GarminDB) deste desporto, para o fim do
    separador Histórico. Só de leitura: são o que o Garmin registou."""
    try:
        acts = gs.activities(app.db, sport)
    except Exception:
        return []
    if not acts:
        return []
    rows = [Item(tr("— Sincronizadas do Garmin ({n}) —", "— Synced from Garmin ({n}) —",
                    n=len(acts)), enabled=False)]
    from velo.core.units import hms
    for r in acts:
        bits = []
        if r.get("distance_m"):
            d = r["distance_m"]
            bits.append(f"{d / 1000:.2f} km" if d >= 1000 else f"{d:.0f} m")
        if r.get("avg_hr"):
            bits.append(f"{r['avg_hr']:.0f} bpm")
        if r.get("ascent_m"):
            bits.append(f"↑ {r['ascent_m']:.0f} m")
        if r.get("training_load"):
            bits.append(tr("carga {l}", "load {l}", l=f"{r['training_load']:.0f}"))
        bits.append("Garmin" + (f" · {r['source_sport']}" if r.get("source_sport") else ""))
        rows.append(Item(f"{str(r['started_at'])[:16].replace('T', ' ')}  "
                         f"{r.get('name') or tr('Atividade', 'Activity')}",
                         value=hms(r.get("moving_s") or r.get("elapsed_s") or 0),
                         detail=" · ".join(bits), enabled=False, data=("synced", r["id"])))
    return rows
