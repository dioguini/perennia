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

from perennia.core import garmin_sync as gs
from perennia.core import options as opt_mod
from perennia.core.i18n import t, tr
from perennia.ui.app import ConfirmScreen, Screen
from perennia.ui.widgets import Item

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


class SyncStore:
    """O «rascunho» da sincronização no menu Backups e Sincronização: aqui não há Guardar,
    por isso cada opção grava-se logo na base de dados."""

    dirty = False

    def __init__(self, db):
        self.db = db

    def get(self, key_: str, default=None):
        return self.db.get(key_, default)

    def put(self, key_: str, value) -> None:
        self.db.set(key_, value)


class SyncPanel:
    """As linhas e o comportamento da sincronização, dentro de um ecrã.

    Cada fonte de dados é um separador (`SOURCES`); por agora só há o
    GarminDB. Juntar uma fonte é acrescentá-la aqui e escrever as linhas dela
    (`items_<chave>`)."""

    SOURCES = (("garmindb", "GarminDB"), ("hrv4training", "HRV4Training"),
               ("labs", "Análises"), ("trainingpeaks", "TrainingPeaks"),
               ("historico", "Histórico"), ("upload", "Upload manual"), ("csv", "CSV"),
               ("saude", "Saúde"), ("wifi", "Wi-Fi"))
    # cada separador procura os ficheiros só na sua pasta de data/in
    FILE_KEYS = {"hrv4training": "hrv4training", "labs": "labs",
                 "trainingpeaks": "trainingpeaks", "historico": "history",
                 "upload": "activities", "csv": "csv", "saude": "csv"}

    def __init__(self, screen: Screen, runner=None, store=None):
        self.screen = screen
        self.app = screen.app
        self.store = store or screen    # o rascunho das Definições
        self.runner = runner            # para os testes: corre «subprocess.run» falso
        self._seen = None

    @property
    def opts(self) -> gs.Options:
        return gs.options_from(self.store.get("sync_garmindb", {}) or {})

    def save(self, o: gs.Options) -> None:
        from dataclasses import asdict
        self.store.put("sync_garmindb", asdict(o.clean()))

    @property
    def pending(self) -> bool:
        """Há alterações por guardar nas Definições? (sincronizar usa o que está gravado)"""
        return bool(getattr(self.store, "dirty", False))

    # A sincronização pertence à aplicação (ronda 34), não a este painel: ao mudar de ecrã
    # continua, e ao voltar vê-se outra vez. O relato e o último resultado também ficam lá.

    @property
    def task(self):
        return getattr(self.app, "task", None)

    @property
    def busy(self) -> bool:
        return bool(getattr(self.app, "task_running", False))

    @property
    def job(self):
        t = self.task
        return t.job if t is not None else None

    @property
    def log(self) -> gs.SyncLog | None:
        return getattr(self.app, "sync_log", None)

    @log.setter
    def log(self, value: gs.SyncLog | None) -> None:
        self.app.sync_log = value

    @property
    def last_report(self) -> dict | None:
        return getattr(self.app, "sync_last_report", None)

    @last_report.setter
    def last_report(self, value: dict | None) -> None:
        self.app.sync_last_report = value

    @property
    def last_error(self) -> str:
        return getattr(self.app, "sync_last_error", "")

    @last_error.setter
    def last_error(self, value: str) -> None:
        self.app.sync_last_error = value

    def refuse_if_busy(self) -> bool:
        """Já há uma sincronização a decorrer? Diz onde a ver (e não começa outra)."""
        if self.busy:
            self.app.message(self.app.task_busy_text())
            return True
        return False

    # ------------------------------------------------------------- linhas

    def source_labels(self) -> list[str]:
        return [name for _k, name in self.SOURCES]

    def items(self, source: str = "garmindb") -> list[Item]:
        return getattr(self, f"items_{source}")()

    # ------------------------------------------------- importar ficheiros

    def files(self, patterns: tuple, kind: str | None = None) -> list:
        """Os ficheiros na pasta de data/in deste tipo (só lá: arrastar um ficheiro para a
        janela continua a servir para um ficheiro de outro sítio)."""
        from perennia.core import folders
        base = folders.in_dir(self.FILE_KEYS.get(kind or "", "activities"), self.app.data_dir)
        out = []
        for pat in patterns:
            out += sorted(base.glob(pat))[:40]
        return list(dict.fromkeys(out))

    def _file_items(self, kind: str, patterns: tuple, how: tuple, check=None) -> list[Item]:
        rows = [Item(tr("Ficheiros encontrados", "Files found"), header=True)]
        found = [p for p in self.files(patterns, kind) if check is None or check(p)]
        for p in found:
            rows.append(Item(p.name, value=p.suffix.lower(), detail=self.where(kind),
                             action=lambda q=p: self.import_file(kind, q)))
        if not found:
            rows.append(Item(tr("Nenhum ficheiro encontrado", "No files found"), enabled=False,
                             detail=tr("põe o ficheiro em {p} (ou arrasta-o para a janela)",
                                       "put the file in {p} (or drag it onto the window)",
                                       p=self.where(kind))))
        rows += [Item(tr("Como exportar", "How to export"), header=True),
                 Item(tr(*how), enabled=False)]
        if self.last_report and self.last_report.get("_kind") == kind:
            rows.insert(0, Item(tr("Última importação", "Last import"),
                                value=self.last_report.get("_text", ""), enabled=False))
        return rows

    def where(self, kind: str) -> str:
        """A pasta de data/in deste separador, para mostrar («data/in/analises»)."""
        from perennia.core import folders
        return folders.shown(folders.in_dir(self.FILE_KEYS.get(kind, "activities"),
                                            self.app.data_dir), self.app.data_dir)

    def import_file(self, kind: str, path) -> None:
        from perennia.core import file_import
        try:
            rep, text = file_import.import_file(self.app.db, kind, path)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        rep["_kind"], rep["_text"] = kind, text
        self.last_report = rep
        self.app.message(text)
        self.screen.enter()

    def items_hrv4training(self) -> list[Item]:
        return self._file_items(
            "hrv4training", ("*.csv",),
            ("Na app HRV4Training: Definições → Exportar medições (CSV) → guarda o ficheiro em "
             "data/in/hrv4training. A Perennia junta a HRV, a FC em repouso e o resto ao "
             "diário da Saúde.",
             "In the HRV4Training app: Settings → Export measurements (CSV) → save the file in "
             "data/in/hrv4training. Perennia adds HRV, resting HR and the rest to the Health "
             "log."))

    def items_labs(self) -> list[Item]:
        return self._file_items(
            "labs", ("*.csv", "*.xlsx", "*.xlsm"),
            ("Um .csv com uma linha por resultado: data, análise, valor (e, se quiseres, "
             "unidade, mínimo, máximo, laboratório). Também serve o Excel «readings» / "
             "«ref_parameter».",
             "A .csv with one row per result: date, test, value (and optionally unit, min, "
             "max, lab). The «readings» / «ref_parameter» Excel also works."),
            check=lambda p: not _is_tp(p))

    def items_trainingpeaks(self) -> list[Item]:
        return self._file_items(
            "trainingpeaks", ("*.csv",),
            ("No TrainingPeaks (web): Calendário → Exportar → «Workouts» (CSV) do período que "
             "quiseres. As atividades entram no histórico com a TSS do TrainingPeaks (e contam "
             "para a forma e a fadiga).",
             "In TrainingPeaks (web): Calendar → Export → «Workouts» (CSV) for the period you "
             "want. Activities join the history with TrainingPeaks' TSS (and count for form "
             "and fatigue)."),
            check=_is_tp)

    def items_wifi(self) -> list[Item]:
        """Sincronizar com outra Perennia na mesma rede (PC ↔ Raspberry Pi…)."""
        from perennia.core import lan_sync as ls
        from perennia.ui.lan_sync_screens import LanReceiveScreen, LanSendScreen
        a = self.app
        return [
            Item(tr("Destino — esta Perennia recebe", "Destination — this Perennia receives"),
                 header=True),
            Item(tr("Receber de outra Perennia", "Receive from another Perennia"),
                 detail=tr("mostra o endereço e um PIN de uso único; fecha sozinho",
                           "shows the address and a single-use PIN; closes by itself"),
                 action=lambda: a.push(LanReceiveScreen(a))),
            Item(tr("Fonte — esta Perennia envia", "Source — this Perennia sends"),
                 header=True),
            Item(tr("Enviar para outra Perennia", "Send to another Perennia"),
                 detail=tr("precisas do endereço e do PIN que o destino mostra",
                           "you need the address and PIN the receiver shows"),
                 action=lambda: a.push(LanSendScreen(a))),
            Item(tr("Como funciona", "How it works"), header=True),
            Item(tr("Cifrado e com PIN; só rede local; nunca envia credenciais ({m})",
                    "Encrypted and PIN-protected; local network only; never sends credentials "
                    "({m})", m=tr("juntar" if ls.mode_of(a.db) == "merge" else "substituir",
                                  "merge" if ls.mode_of(a.db) == "merge" else "replace")),
                 enabled=False,
                 detail=tr("opções em Definições → Avançado → Dados e backups",
                           "options in Settings → Advanced → Data and backups"))]

    def items_historico(self) -> list[Item]:
        """O histórico de outras apps (TrainingPeaks, Strava, Garmin Connect) e as regras que o
        normalizam para os desportos, tipos de treino e etiquetas da Perennia."""
        from perennia.core import history_etl as he
        rows = self._file_items(
            "historico", ("*.csv",),
            ("TrainingPeaks: Calendário → Exportar → Workouts (CSV). Strava: Definições → A "
             "minha conta → Descarregar ou eliminar a conta → «activities.csv». Garmin "
             "Connect: Atividades → Exportar CSV. As atividades que as regras não conhecem "
             "aparecem no relatório «sem regra».",
             "TrainingPeaks: Calendar → Export → Workouts (CSV). Strava: Settings → My "
             "Account → Download or delete → 'activities.csv'. Garmin Connect: Activities → "
             "Export CSV. Activities the rules do not know appear in the 'no rule' report."),
            check=lambda p: _is_tp(p) or he.looks_like(p) is not None)
        rows += [Item(tr("Regras de normalização", "Normalisation rules"), header=True),
                 Item(tr("Ver o que as regras mudariam", "Preview what the rules would change"),
                      detail=tr("não grava nada", "saves nothing"),
                      action=lambda: self.normalize(False)),
                 Item(tr("Aplicar as regras ao histórico", "Apply the rules to the history"),
                      detail=tr("passa tudo para os desportos, tipos e etiquetas da Perennia",
                                "moves everything to Perennia's sports, types and tags"),
                      action=lambda: self.normalize(True)),
                 Item(tr("Criar ficheiro de regras para editar", "Create a rules file to edit"),
                      value=he.rules_path(self.app.db).name,
                      detail=str(he.rules_path(self.app.db).parent),
                      action=self.rules_template)]
        return rows

    def normalize(self, apply: bool) -> None:
        from perennia.core import history_etl as he
        try:
            rep = he.normalize(self.app.db, dry_run=not apply)
        except he.RulesError as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        self.app.message(he.report_text(rep))
        self.screen.enter()

    def rules_template(self) -> None:
        from perennia.core import history_etl as he
        try:
            from perennia.core import folders
            path = he.write_template(folders.in_dir("history", self.app.data_dir))
        except OSError as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        self.app.message(tr("Regras de arranque gravadas em {p}. Edita-as e usa «Aplicar»; "
                            "o ficheiro «regras-historico.json» é o que se usa.",
                            "Starter rules saved to {p}. Edit them and use 'Apply'; the file "
                            "'regras-historico.json' is the one used.", p=path))

    def items_csv(self) -> list[Item]:
        """Artigos, exercícios, grupos musculares… por .csv: modelo, exportação e importação."""
        from perennia.core import csv_sync as cs
        rows = [Item(tr("Conjuntos de dados", "Data sets"), header=True)]
        for d in cs.DATASETS.values():
            n = len(d.export(self.app.db))
            rows.append(Item(d.label, value=tr("{n} linhas", "{n} rows", n=n), detail=d.help,
                             action=lambda k=d.key: self.open_csv(k)))
        rows.append(Item(tr("Ficheiros .csv encontrados", "CSV files found"), header=True))
        found = self.files(("*.csv",), "csv")
        known = 0
        for p in found:
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
                key = cs.detect(text)
            except Exception:
                key = None
            if key is None:
                continue
            known += 1
            rows.append(Item(p.name, value=cs.DATASETS[key].label, detail=self.where("csv"),
                             action=lambda q=p: self.import_csv_file(q)))
        if not known:
            rows.append(Item(tr("Nenhum ficheiro encontrado", "No files found"), enabled=False,
                             detail=tr("descarrega um modelo (fica em data/out/csv), preenche-o "
                                       "e põe-no em {p}", "download a template (it goes to "
                                       "data/out/csv), fill it in and put it in {p}",
                                       p=self.where("csv"))))
        if self.last_report and self.last_report.get("_kind") == "csv":
            rows.insert(0, Item(tr("Último CSV", "Last CSV"),
                                value=self.last_report.get("_text", ""), enabled=False))
        return rows

    def items_saude(self) -> list[Item]:
        """Os dados de saúde de uma ou mais datas por .csv: os campos são os do diário da
        Perennia (uma coluna por métrica). Modelo para descarregar, exportação e importação."""
        from perennia.core import folders
        from perennia.core import health_csv as hc
        db = self.app.db

        def downloads_dir():
            return folders.out_dir("csv", self.app.data_dir)

        def write(what: str) -> None:
            try:
                path = hc.write(db, downloads_dir(), what=what)
            except Exception as e:
                self.app.message(f"{t('common.error')}: {e}")
                return
            self._csv_done(tr("Guardado em {p}", "Saved to {p}", p=path))
            self.app.message(tr("Guardado em {p}", "Saved to {p}", p=path))
        rows = [Item(tr("Descarregar o modelo (.csv)", "Download the template (.csv)"),
                     detail=tr("uma linha por data: data, uma coluna por métrica do diário e a "
                               "nota do dia · grava em {p}", "one row per date: date, one column "
                               "per log metric and the day's note · saved in {p}",
                               p=folders.shown(downloads_dir(), self.app.data_dir)),
                     action=lambda: write("template")),
                Item(tr("Exportar o diário (.csv)", "Export the log (.csv)"),
                     value=tr("{n} métricas", "{n} metrics", n=len(hc.metrics(db))),
                     detail=tr("todos os dias com valores, no mesmo formato do modelo",
                               "every day with values, in the template's format"),
                     action=lambda: write("export")),
                Item(tr("Ficheiros .csv encontrados", "CSV files found"), header=True)]
        known = 0
        for p in self.files(("*.csv",), "saude"):
            try:
                if not hc.detect(db, p.read_text(encoding="utf-8-sig", errors="replace")):
                    continue
            except Exception:
                continue
            known += 1
            rows.append(Item(p.name, value=tr("saúde", "health"), detail=self.where("saude"),
                             action=lambda q=p: self.import_health_csv(q)))
        if not known:
            rows.append(Item(tr("Nenhum ficheiro encontrado", "No files found"), enabled=False,
                             detail=tr("descarrega o modelo (fica em data/out/csv), preenche as "
                                       "datas e põe o .csv em {p}",
                                       "download the template (it goes to data/out/csv), fill "
                                       "in the dates and put the .csv in {p}",
                                       p=self.where("saude"))))
        rows += [Item(tr("Como funciona", "How it works"), header=True),
                 Item(tr("A primeira coluna é a data (AAAA-MM-DD ou DD/MM/AAAA); cada outra é uma "
                         "métrica do diário com o nome que tem na Perennia — número (7,5), sim/não, "
                         "escala 1–5, hora (22:30), texto ou uma das opções. A coluna «nota» é a "
                         "nota do dia. As colunas que não conhecer ignora-se. Os valores novos "
                         "substituem os do mesmo dia.",
                         "The first column is the date (YYYY-MM-DD or DD/MM/YYYY); every other "
                         "one is a log metric with the name it has in Perennia — number (7.5), "
                         "yes/no, 1–5 scale, time (22:30), text or one of the options. The "
                         "“nota” column is the day's note. Unknown columns are ignored. New "
                         "values replace the ones of the same day."), enabled=False)]
        if self.last_report and self.last_report.get("_kind") == "saude":
            rows.insert(0, Item(tr("Última importação", "Last import"),
                                value=self.last_report.get("_text", ""), enabled=False))
        return rows

    def import_health_csv(self, path) -> None:
        from perennia.core import file_import
        self.import_file("saude", path)

    def open_csv(self, key: str) -> None:
        from perennia.ui.csv_screens import CsvDatasetPopup
        self.app.push(CsvDatasetPopup(self.app, key, then=self._csv_done))

    def _csv_done(self, text: str) -> None:
        self.last_report = {"_kind": "csv", "_text": text}
        self.screen.enter()

    def import_csv_file(self, path) -> None:
        from perennia.core import csv_sync as cs
        try:
            key, rep = cs.import_file(self.app.db, path)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        text = f"{cs.DATASETS[key].label}: {rep.text()}"
        self.app.message(text)
        self._csv_done(text)

    def items_upload(self) -> list[Item]:
        """Uma atividade de cada vez: escolhe o ficheiro (.fit ou .tcx) e vê o que
        tem antes de a guardar no desporto respetivo."""
        rows = [Item(tr("Ficheiros encontrados", "Files found"), header=True)]
        found = self.files(("*.fit", "*.FIT", "*.tcx", "*.TCX"), "upload")
        for p in found:
            rows.append(Item(p.name, value=p.suffix.lower(), detail=self.where("upload"),
                             action=lambda q=p: self.open_upload(q)))
        if not found:
            rows.append(Item(tr("Nenhum ficheiro encontrado", "No files found"), enabled=False,
                             detail=tr("põe o ficheiro em {p}, ou arrasta-o para a janela",
                                       "put the file in {p}, or drag it onto the window",
                                       p=self.where("upload"))))
        rows += [Item(tr("Como funciona", "How it works"), header=True),
                 Item(tr("Escolhe um ficheiro .fit (ou .tcx) do teu computador — ou arrasta-o "
                         "para a janela. A Perennia lê-o e mostra o nome, o desporto, o tempo, a "
                         "distância, a FC e a potência; carregas em «Fazer upload» e a atividade "
                         "fica guardada no Histórico desse desporto (e conta para a forma e a "
                         "fadiga).", "Pick a .fit (or .tcx) file from your computer — or drag it "
                         "onto the window. Perennia reads it and shows the name, sport, time, "
                         "distance, HR and power; press “Upload” and the activity is saved to "
                         "that sport's History (and counts for form and fatigue)."),
                      enabled=False)]
        if self.last_report and self.last_report.get("_kind") == "upload":
            rows.insert(0, Item(tr("Último upload", "Last upload"),
                                value=self.last_report.get("_text", ""), enabled=False))
        return rows

    def open_upload(self, path) -> None:
        from perennia.ui import upload_screens as up

        def done() -> None:
            self.last_report = {"_kind": "upload", "_text": str(path.name if hasattr(path, "name")
                                                                else path)}
            self.screen.enter()
        try:
            from perennia.core import activity_upload as au
            info = au.parse(path)
        except Exception as e:
            self.app.message(f"{getattr(path, 'name', path)}: {e}")
            return
        self.app.push(up.UploadPreview(self.app, info, then=done))

    def items_garmindb(self) -> list[Item]:
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
            Item(tr("Estado", "Status"),
                 value=tr("a sincronizar…", "syncing…") if self.busy else
                 (st["last_sync"] or tr("nunca sincronizado", "never synced")),
                 detail=state + " · " + self.python_text(), enabled=False),
            *self.log_rows(),
            *self.requirement_rows(o),
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
        from perennia.core import folders
        rows += [
            Item(tr("Pastas do GarminDB", "GarminDB folders"), enabled=False,
                 value=folders.shown(folders.garmin_bases_dir(self.app.data_dir).parent,
                                     self.app.data_dir),
                 detail=tr("a configuração em garmin/config (sem palavra-passe) e as bases em "
                           "garmin/bases", "the config in garmin/config (no password) and the "
                           "databases in garmin/bases")),
            Item(tr("Comando", "Command"), detail=gs.command_text(db, o, gs.config_dir(db)),
                 enabled=False),
            *self.repair_rows(ready),
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

    @staticmethod
    def python_text() -> str:
        """«Python 3.13.17 (.venv)» ou «Python 3.11.8 (C:/…/python.exe)»: com que Python a
        Perennia está a correr (é nesse que o GarminDB tem de estar)."""
        env = gs.environment()
        where = ".venv" if env["using_venv"] else env["executable"]
        return f"Python {env['python']} ({where})"

    def repair_rows(self, ready: bool) -> list[Item]:
        """«Atualizar o GarminDB»: quando o GarminDB falta ou tem uma versão que já não funciona
        (o erro «field_enums», o login antigo), instala o certo no Python da Perennia."""
        cli = gs.importers.garmindb_cli()
        comp = gs.compatibility(cli)
        missing = cli is None
        if not (comp["can_repair"] or (missing and comp["python_ok"])):
            return []
        cmd = " ".join(gs.repair_command()[1:])
        return [Item(tr("Instalar o GarminDB", "Install GarminDB") if missing else
                     tr("Atualizar o GarminDB", "Update GarminDB"),
                     action=self.ask_repair, enabled=ready,
                     detail=tr("instala o GarminDB 4 no Python da Perennia: {c}",
                               "installs GarminDB 4 in Perennia's Python: {c}", c=cmd))]

    def ask_repair(self) -> None:
        a = self.app

        if self.refuse_if_busy():
            return

        def go() -> None:
            a.pop()
            self.log = gs.SyncLog(self.log_lines(), self.log_chars())
            log = self.log
            log.step(tr("A instalar o GarminDB 4 (pip)", "Installing GarminDB 4 (pip)"))
            self._job(lambda: (gs.repair(log=log), "repair"),
                      tr("Instalação do GarminDB", "GarminDB install"))
        a.push(ConfirmScreen(
            a, tr("Instalar o GarminDB 4?", "Install GarminDB 4?"),
            tr("Corre «pip install --upgrade \"garmindb>=4\"» no Python da Perennia (precisa de "
               "internet; demora um ou dois minutos). Os teus dados e a configuração ficam.",
               "Runs «pip install --upgrade \"garmindb>=4\"» in Perennia's Python (needs the "
               "internet; takes a minute or two). Your data and config stay."),
            [(tr("Cancelar", "Cancel"), a.pop), (tr("Sim, instalar", "Yes, install"), go)],
            default=0, buttons=True, cancel=a.pop))

    # ------------------------------------------------------- passos e requisitos

    def log_rows(self) -> list[Item]:
        """O que está a acontecer (ou aconteceu na última sincronização), passo a passo, e as
        últimas linhas do que o GarminDB escreveu — como na linha de comandos."""
        from perennia.ui.background import log_items
        return log_items(self.log, self.busy)

    def requirement_rows(self, o: gs.Options) -> list[Item]:
        """O que é preciso para sincronizar, com ✓/✗ e, no que falta, como se resolve."""
        checks = gs.preflight(self.app.db, o)
        rows = [Item(tr("— Requisitos —", "— Requirements —"), enabled=False,
                     detail=tr("o que o GarminDB precisa neste computador",
                               "what GarminDB needs on this computer"))]
        for c in checks:
            rows.append(Item(("✓ " if c["ok"] else "✗ ") + c["text"], enabled=False,
                             detail="" if c["ok"] else c["fix"]))
        rows.append(Item(tr("Primeira vez? Passo a passo", "First time? Step by step"),
                         action=self.show_guide,
                         detail=tr("o que fazer num computador novo (ou para um colega)",
                                   "what to do on a new computer (or for a colleague)")))
        return rows

    def show_guide(self) -> None:
        a = self.app
        a.push(ConfirmScreen(
            a, tr("Sincronizar o GarminDB pela primeira vez", "Syncing GarminDB for the first "
                  "time"),
            tr("1) Corre o perennia_setup e responde «s» ao Garmin (instala o GarminDB, guarda o "
               "e-mail da conta e faz o primeiro login, onde metes o código se a conta tiver "
               "verificação em dois passos). Sem o setup: pip install \"garmindb>=4\" no .venv e o "
               "e-mail em Definições → Ligações externas → Garmin; o login (com o código) faz-se "
               "com «python main.py --garmin-login». 2) Aqui, escolhe o período e "
               "os dados e carrega em «Sincronizar agora». 3) A palavra-passe é pedida de cada "
               "vez que se descarrega do Garmin Connect e não fica guardada em lado nenhum. Tudo "
               "fica em data/garmin. Cada pessoa usa a sua conta Garmin: a Perennia não leva a "
               "tua.",
               "1) Run perennia_setup and answer «y» to Garmin (it installs GarminDB, saves the "
               "account e-mail and does the first login, where you type the code if the account "
               "has two-step verification). Without the setup: pip install \"garmindb>=4\" in the .venv "
               "and the e-mail in Settings → External connections → Garmin; log in (with the "
               "code) with «python main.py --garmin-login». 2) Here, pick the "
               "period and data and press «Sync now». 3) The password is asked every time data "
               "is downloaded from Garmin Connect and is never kept anywhere. Everything stays "
               "in data/garmin. Everyone uses their own Garmin account."),
            [(tr("Fechar", "Close"), a.pop)], default=0, buttons=True, cancel=a.pop))

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
        return False                       # as pastas do GarminDB são fixas (data/garmin)

    # ------------------------------------------------------------- correr

    def _job(self, fn, title: str | None = None) -> None:
        """Começa na aplicação (em segundo plano): ver `perennia.ui.background`."""
        self.app.start_task("garmindb", title or tr("Sincronização do GarminDB",
                                                    "GarminDB sync"),
                            fn, log=self.log, finish=finish_garmindb, short="GarminDB")
        self.screen.enter()

    def sync_now(self) -> None:
        if self.refuse_if_busy() or self.pending:
            return
        db, o, runner = self.app.db, self.opts, self.runner
        if not gs.status(db)["cli"]:
            # sem o GarminDB instalado, importa-se o que já lá estiver
            self.import_only()
            return
        bad = gs.blocking_problems(gs.preflight(db, o))
        if bad:
            self.log = gs.SyncLog(self.log_lines(), self.log_chars())
            self.log.step(tr("A verificar os requisitos", "Checking the requirements"))
            self.log.end(False, "; ".join(c["text"] for c in bad))
            self.app.message(tr("Falta: ", "Missing: ") + bad[0]["text"] + " — " + bad[0]["fix"])
            self.screen.enter()
            return
        if gs.needs_password(o):
            self.ask_password(lambda pw: self._start_sync(o, pw))
            return
        self._start_sync(o, None)

    def ask_password(self, then) -> None:
        """A palavra-passe do Garmin Connect, a cada sincronização que descarrega: não fica
        guardada em lado nenhum (passa ao GarminDB e esquece-se)."""
        from perennia.ui.goal_popup import PasswordPopup
        user, _ = gs.credentials(gs.config_path(self.app.db))
        self.app.push(PasswordPopup(
            self.app, tr("Palavra-passe do Garmin Connect", "Garmin Connect password"),
            (user + " · " if user else "") + tr(
                "é usada só nesta sincronização e não fica guardada em lado nenhum",
                "used for this sync only and never kept anywhere"), then))

    def _start_sync(self, o: gs.Options, password: str | None) -> None:
        if self.refuse_if_busy():
            return
        path, runner = self.app.db.path, self.runner
        self.log = gs.SyncLog(self.log_lines(), self.log_chars())
        log = self.log
        self.log.step(tr("A verificar os requisitos", "Checking the requirements"))
        self.log.end(True)

        def run():
            # a thread tem a sua própria ligação à base de dados: enquanto sincroniza, podes
            # andar pela Perennia (o calendário, as estatísticas…) com a ligação da janela
            from perennia.core.db import Database
            wdb = Database(path)
            try:
                return gs.sync(wdb, o, runner=runner, log=log, password=password)
            finally:
                wdb.close()
        self._job(run)

    def log_lines(self) -> int:
        return int(opt_mod.get(self.app.db, "garmin_log_lines"))

    def log_chars(self) -> int:
        return int(opt_mod.get(self.app.db, "garmin_log_line_chars"))

    def import_only(self) -> None:
        if self.refuse_if_busy() or self.pending:
            return
        db, o = self.app.db, self.opts
        self.log = gs.SyncLog(self.log_lines(), self.log_chars())
        try:
            ok, msg, rep = gs.sync(db, o, run_source=False, log=self.log)
        except Exception as e:
            ok, msg, rep = False, str(e), None
        if not gs.status(db)["cli"]:
            from perennia.core import importers
            comp = gs.compatibility(None)
            first = comp["problems"][0] if comp["problems"] else None
            hint = (first["text"] + ". " + first["fix"][:1].upper() + first["fix"][1:] + ".") \
                if first else tr(
                "Não encontrei o programa do GarminDB (procurei no PATH e em {d}), por isso não "
                "descarreguei nada do Garmin. Instala-o no mesmo ambiente da Perennia: «python "
                "-m pip install \"garmindb>=4\"» (Python 3.12+).",
                "Could not find the GarminDB program (looked in PATH and in {d}), so nothing was "
                "downloaded from Garmin. Install it in the same environment as Perennia: "
                "'python -m pip install \"garmindb>=4\"' (Python 3.12+).",
                d=", ".join(importers.cli_search_dirs()[:2]) or "—")
            if ok:
                self.app.message(hint)
                self.last_report = rep
                self.screen.enter()
                return
            msg = hint + " " + (msg or "")
        self._done(ok, msg, rep)

    def ask_maintenance(self, action: str) -> None:
        a = self.app
        if self.refuse_if_busy():
            return
        title = tr("Cópia de segurança das bases?", "Back up the databases?") \
            if action == "backup" else tr("Reconstruir as bases do GarminDB?",
                                          "Rebuild the GarminDB databases?")
        sub = tr("O GarminDB faz um .zip em data/garmin/bases/Backups.",
                 "GarminDB writes a .zip to data/garmin/bases/Backups.") if action == "backup" else \
            tr("Apaga as bases do GarminDB e volta a importá-las dos ficheiros que já tem.",
               "Deletes the GarminDB databases and re-imports them from its files.")

        def go() -> None:
            a.pop()
            db, runner = a.db, self.runner
            self.log = gs.SyncLog(self.log_lines(), self.log_chars())
            log = self.log
            log.step(tr("A correr o GarminDB: {a}", "Running GarminDB: {a}",
                        a="--backup" if action == "backup" else "--rebuild_db"))
            self._job(lambda: (gs.maintenance(db, action, runner=runner, log=log), action),
                      tr("Cópia das bases do GarminDB", "GarminDB backup") if action == "backup"
                      else tr("Reconstrução das bases do GarminDB", "GarminDB rebuild"))
        a.push(ConfirmScreen(a, title, sub, [(tr("Cancelar", "Cancel"), a.pop),
                                             (tr("Sim, continuar", "Yes, go on"), go)],
                             default=0, buttons=True, cancel=a.pop))

    def _done(self, ok: bool, msg: str, rep: dict | None) -> None:
        report(self.app, ok, msg, rep)
        self.screen.enter()

    def update(self) -> None:
        """Em cada fotograma: a tarefa acaba na aplicação (`App.poll_task`); aqui só se
        redesenha quando o relato muda."""
        a = self.app
        if hasattr(a, "poll_task"):
            a.poll_task()
        log = self.log
        key = (id(log), getattr(log, "version", None), self.busy)
        if key == self._seen:
            return
        first = self._seen is None
        self._seen = key
        if not first and getattr(self.screen, "view", "sync") == "sync":
            self.screen.enter()


def report(app, ok: bool, msg: str, rep: dict | None) -> None:
    """O resultado de uma sincronização, numa mensagem (em qualquer ecrã)."""
    if ok and rep is not None:
        app.sync_last_report = rep
        app.message(summary_of(rep))
    else:
        app.sync_last_error = msg
        app.message("GarminDB: " + (msg or tr("falhou", "failed")))


def summary_of(rep: dict) -> str:
    return (tr("Sincronizado: {v} valores em {d} dias · {n} atividades ({k} novas)",
               "Synced: {v} values over {d} days · {n} activities ({k} new)",
               v=rep["values"], d=rep["days"], n=rep["activities"],
               k=rep["new_activities"]) +
            (" · " + tr("{n} valores mantidos (a Fonte do indicador é outra)",
                        "{n} values kept (the indicator's source is another)",
                        n=rep["kept"]) if rep.get("kept") else ""))


def finish_garmindb(app, task) -> None:
    """Quando a tarefa do GarminDB acaba (na thread da janela, em qualquer ecrã): fecha o
    relato, diz o resultado e põe `task.ok` / `task.summary`."""
    j, log = task.job, task.log
    res = j.result
    if j.error:
        if log is not None:
            log.end(False, j.error)
        task.ok, task.summary = False, j.error
        report(app, False, j.error, None)
        return
    if isinstance(res, tuple) and len(res) == 2 and res[1] == "repair":
        (ok, out), _ = res
        import importlib
        importlib.invalidate_caches()             # as versões novas veem-se já
        if log is not None:
            log.end(ok, "" if ok else (out.splitlines()[-1] if out else ""))
        v = gs.versions()
        text = (tr("GarminDB {g} instalado (fitfile {f})", "GarminDB {g} installed "
                   "(fitfile {f})", g=gs._vtext(v["garmindb"]), f=gs._vtext(v["fitfile"]))
                if ok else "GarminDB: " + (out.splitlines()[-1] if out else
                                           tr("falhou", "failed")))
        task.ok, task.summary = ok, text
        app.message(text)
        return
    if isinstance(res, tuple) and len(res) == 2 and isinstance(res[1], str) \
            and res[1] in ("backup", "rebuild"):
        (ok, out), action = res
        if log is not None:
            log.end(ok, "" if ok else (gs.diagnose(out) or out.splitlines()[-1:] and
                                       out.splitlines()[-1] or ""))
        text = (("GarminDB: " + (tr("cópia feita", "backup done") if action == "backup"
                                 else tr("bases reconstruídas", "databases rebuilt")))
                if ok else "GarminDB: " + (out.splitlines()[-1] if out else "falhou"))
        task.ok, task.summary = ok, text
        app.message(text)
        return
    ok, msg, rep = res
    task.ok = bool(ok)
    task.summary = summary_of(rep) if ok and rep is not None else (msg or "")
    report(app, ok, msg, rep)


def _is_tp(path) -> bool:
    from perennia.core import tp_import
    return tp_import.looks_like_tp(path)


def history_items(app, sport: str) -> list[Item]:
    """As atividades sincronizadas (GarminDB) deste desporto, para o fim do
    separador Histórico. Só de leitura: são o que o Garmin registou."""
    try:
        acts = gs.activities(app.db, sport)
    except Exception:
        return []
    if not acts:
        return []
    rows = [Item(tr("— Importadas (Garmin, TrainingPeaks, upload manual) ({n}) —",
                    "— Imported (Garmin, TrainingPeaks, manual upload) ({n}) —", n=len(acts)),
                 enabled=False)]
    from perennia.core.units import hms
    for r in acts:
        bits = []
        if r.get("distance_m"):
            d = r["distance_m"]
            bits.append(f"{d / 1000:.2f} km" if d >= 1000 else f"{d:.0f} m")
        if r.get("avg_hr"):
            bits.append(f"{r['avg_hr']:.0f} bpm")
        if r.get("ascent_m"):
            bits.append(f"↑ {r['ascent_m']:.0f} m")
        if r.get("tss"):
            bits.append(f"TSS {r['tss']:.0f}")
        elif r.get("training_load"):
            bits.append(tr("carga {l}", "load {l}", l=f"{r['training_load']:.0f}"))
        src = {"trainingpeaks": "TrainingPeaks", "upload": tr("upload manual", "manual upload")
               }.get(r.get("source"), "Garmin")
        bits.append(src + (f" · {r['source_sport']}" if r.get("source_sport") else ""))
        rows.append(Item(f"{str(r['started_at'])[:16].replace('T', ' ')}  "
                         f"{r.get('name') or tr('Atividade', 'Activity')}",
                         value=hms(r.get("moving_s") or r.get("elapsed_s") or 0),
                         detail=" · ".join(bits), enabled=False, data=("synced", r["id"])))
    return rows
