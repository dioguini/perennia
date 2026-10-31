"""Ligações a serviços de fora: Strava (segmentos e PR) e GarminDB.

Os ecrãs do Strava têm o agente desligado (F1/F2): pelo acordo da API do
Strava, esses dados não podem ir para sistemas de IA.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from velo.core import importers
from velo.core import segments as seg_mod
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.io import strava as strava_mod
from velo.ui.app import Screen
from velo.ui.widgets import Item


class Job:
    """Trabalho demorado numa thread; o ecrã vê `done` no `update`."""

    def __init__(self, fn: Callable[[], Any]):
        self.result: Any = None
        self.error: str | None = None
        self.done = False
        self.progress = ""

        def run():
            try:
                self.result = fn()
            except Exception as e:                      # mostra-se no ecrã
                self.error = str(e) or type(e).__name__
            self.done = True
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()


def _mask(s: str) -> str:
    if not s:
        return "—"
    return "•" * max(0, len(s) - 4) + s[-4:]


# ================================================================= Strava


class StravaScreen(Screen):
    AGENT = False

    def __init__(self, app, http=None, open_browser=None):
        super().__init__(app)
        self.client = strava_mod.StravaClient(app.db, http=http)
        self.open_browser = open_browser
        self.job: Job | None = None

    def enter(self) -> None:
        c = self.client
        db = self.app.db
        status = (tr("ligado · {n}", "connected · {n}", n=c.athlete_name or "Strava")
                  if c.connected else tr("não ligado", "not connected"))
        if self.job is not None and not self.job.done:
            status = tr("à espera do browser…", "waiting for the browser…")
        rows = [
            Item(tr("Estado", "Status"), value=status, enabled=False),
            Item("Client ID", value=c.client_id + "▏", data="text:strava_client_id",
                 detail=tr("De strava.com/settings/api", "From strava.com/settings/api")),
            Item("Client Secret", value=_mask(c.client_secret) + "▏",
                 data="text:strava_client_secret",
                 detail=tr("Fica só neste computador", "Stays on this computer")),
            Item(tr("Autorizar no browser", "Authorize in the browser"),
                 action=self._authorize, enabled=bool(c.client_id and c.client_secret),
                 detail=tr("Abre o Strava; aceita e volta aqui", "Opens Strava; accept and come back")),
        ]
        if c.connected:
            rows.append(Item(tr("Desligar o Strava", "Disconnect Strava"), action=self._disconnect))
        rows += [
            Item(tr("Como criar a aplicação no Strava", "How to create the Strava app"),
                 enabled=False,
                 detail=tr("strava.com/settings/api → nome Perennia, site http://localhost, "
                           "Authorization Callback Domain: localhost",
                           "strava.com/settings/api → name Perennia, website http://localhost, "
                           "Authorization Callback Domain: localhost")),
            Item(tr("O que a Perennia lê", "What Perennia reads"), enabled=False,
                 detail=tr("Os segmentos que cruzam as tuas rotas e os teus PR. Nada é enviado "
                           "para o Strava, e nada do Strava vai para o agente de IA.",
                           "Segments crossing your routes and your PRs. Nothing is sent to "
                           "Strava, and nothing from Strava goes to the AI agent.")),
        ]
        self.chrome.set("Strava", tr("Segmentos das rotas e os teus recordes",
                                     "Route segments and your records"), self.footer())
        self.list.set_items(rows, keep_index=True)
        _ = db

    def text_input(self, field: str, text: str) -> None:
        db = self.app.db
        db.set(field, (str(db.get(field, "") or "") + text).strip())
        self.enter()

    def text_backspace(self, field: str) -> None:
        db = self.app.db
        db.set(field, str(db.get(field, "") or "")[:-1])
        self.enter()

    def _authorize(self) -> None:
        if self.job is not None and not self.job.done:
            return
        kw = {"open_browser": self.open_browser} if self.open_browser else {}
        self.job = Job(lambda: strava_mod.authorize_interactive(self.client, **kw))
        self.enter()

    def _disconnect(self) -> None:
        self.client.disconnect()
        self.enter()

    def update(self, dt: float) -> None:
        j = self.job
        if j is not None and j.done:
            self.job = None
            if j.error:
                self.app.message(f"Strava: {j.error}")
            elif j.result:
                self.app.message(tr("Strava ligado", "Strava connected"))
            else:
                self.app.message(tr("O Strava não respondeu a tempo", "Strava did not answer in time"))
            self.enter()


class StravaSegmentsScreen(Screen):
    AGENT = False

    def __init__(self, app, route_id: str, http=None):
        super().__init__(app)
        self.route_id = route_id
        self.client = strava_mod.StravaClient(app.db, http=http)
        self.job: Job | None = None

    def enter(self) -> None:
        a = self.app
        segs = seg_mod.load(a.db, self.route_id)
        busy = self.job is not None and not self.job.done
        rows = [Item(tr("Atualizar do Strava", "Refresh from Strava"),
                     value=tr("a procurar…", "searching…") if busy else "",
                     action=self._refresh, enabled=self.client.connected and not busy,
                     detail="" if self.client.connected else
                     tr("Liga primeiro o Strava em Definições → Strava",
                        "Connect Strava first in Settings → Strava"))]
        if not self.client.connected:
            rows.append(Item(tr("Ligar o Strava", "Connect Strava"),
                             action=lambda: a.push(StravaScreen(a))))
        for s in segs:
            pr = f"PR {hms(s.pr_s)}" if s.pr_s else tr("sem PR", "no PR")
            bits = [f"{s.length_m / 1000:.2f} km"]
            if s.avg_grade is not None:
                bits.append(f"{s.avg_grade:.1f} %")
            bits.append(tr("ao km {k:.1f}", "at km {k:.1f}", k=s.start_m / 1000))
            if s.effort_count:
                bits.append(tr("{n} esforços", "{n} efforts", n=s.effort_count))
            if s.local_best_s:
                bits.append(tr("Perennia {t}", "Perennia {t}", t=hms(s.local_best_s)))
            rows.append(Item(s.name, value=pr, detail=" · ".join(bits), enabled=False,
                             data=("strava", s.id)))
        if not segs:
            rows.append(Item(tr("Ainda sem segmentos para esta rota", "No segments for this route yet"),
                             enabled=False))
        row = a.db.route(self.route_id)
        self.chrome.set(tr("Segmentos do Strava", "Strava segments"),
                        (row["name"] if row else "") + " · " +
                        tr("{n} segmentos", "{n} segments", n=len(segs)), self.footer())
        self.list.set_items(rows, keep_index=True)

    def _refresh(self) -> None:
        if self.job is not None and not self.job.done:
            return
        db, rid, client = self.app.db, self.route_id, self.client
        self.job = Job(lambda: seg_mod.fetch_for_route(db, client, rid))
        self.enter()

    def update(self, dt: float) -> None:
        j = self.job
        if j is not None and j.done:
            self.job = None
            if j.error:
                self.app.message(f"Strava: {j.error}")
            else:
                r = j.result
                self.app.message(tr("{m} segmentos na rota ({e} vistos)",
                                    "{m} segments on the route ({e} seen)",
                                    m=r["matched"], e=r["explored"]))
            self.enter()


# ================================================================ GarminDB


class GarminDBScreen(Screen):
    """Lê o que o GarminDB descarregou (e, se estiver instalado, corre-o)."""

    def __init__(self, app, runner=None):
        super().__init__(app)
        self.runner = runner
        self.job: Job | None = None

    def enter(self) -> None:
        a = self.app
        st = importers.garmindb_status(a.db)
        busy = self.job is not None and not self.job.done
        yes, no = tr("sim", "yes"), tr("não", "no")
        rows = [
            Item(tr("Pasta do GarminDB", "GarminDB folder"), value=st["dir"] + "▏",
                 data="text:garmindb_dir",
                 detail=tr("Onde está a garmin.db (por omissão ~/HealthData/DBs)",
                           "Where garmin.db lives (default ~/HealthData/DBs)")),
            Item("garmin.db", value=yes if st["found"] else no, enabled=False),
            Item(tr("GarminDB instalado", "GarminDB installed"),
                 value=yes if st["cli"] else no, enabled=False,
                 detail="" if st["cli"] else "pip install garmindb"),
            Item(tr("Última importação", "Last import"), value=st["last_import"] or "—",
                 enabled=False),
            Item(tr("Atualizar com o GarminDB e importar", "Update with GarminDB and import"),
                 value=tr("a descarregar…", "downloading…") if busy else "",
                 action=self._update, enabled=st["cli"] and not busy,
                 detail=tr("Corre «garmindb_cli.py --all --download --import --analyze --latest»",
                           "Runs «garmindb_cli.py --all --download --import --analyze --latest»")),
            Item(tr("Importar da garmin.db", "Import from garmin.db"), action=self._import,
                 enabled=st["found"] and not busy,
                 detail=tr("Passos, FC repouso, sono, HRV, stress, Body Battery, SpO2, peso…",
                           "Steps, resting HR, sleep, HRV, stress, Body Battery, SpO2, weight…")),
            Item(tr("A palavra-passe do Garmin", "Your Garmin password"), enabled=False,
                 detail=tr("Fica na configuração do GarminDB (~/.GarminDb), nunca na Perennia.",
                           "Stays in GarminDB's config (~/.GarminDb), never in Perennia.")),
        ]
        self.chrome.set("GarminDB", tr("Os teus dados do Garmin Connect, via GarminDB",
                                       "Your Garmin Connect data, via GarminDB"), self.footer())
        self.list.set_items(rows, keep_index=True)

    def text_input(self, field: str, text: str) -> None:
        db = self.app.db
        db.set(field, str(db.get(field, "") or importers.garmindb_dir(db)) + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        db = self.app.db
        db.set(field, str(db.get(field, "") or importers.garmindb_dir(db))[:-1])
        self.enter()

    def _import(self) -> None:
        try:
            rep = importers.import_garmindb(self.app.db)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        self.last_report = rep
        self.app.message(tr("Garmin: {v} valores em {d} dias", "Garmin: {v} values over {d} days",
                            v=rep["values"], d=rep["days"]))
        self.enter()

    def _update(self) -> None:
        if self.job is not None and not self.job.done:
            return
        runner = self.runner
        self.job = Job(lambda: importers.run_garmindb(runner=runner))
        self.enter()

    def update(self, dt: float) -> None:
        j = self.job
        if j is not None and j.done:
            self.job = None
            ok, out = j.result if j.result else (False, j.error or "")
            if ok:
                self._import()
            else:
                self.app.message("GarminDB: " + (out.splitlines()[-1] if out else "falhou"))
                self.enter()


def folder_exists(p: str) -> bool:
    return Path(p).expanduser().is_dir()
