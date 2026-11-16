"""Ligações a serviços de fora: Strava (segmentos, PR e a biblioteca de segmentos). O GarminDB está na
Sincronização (perennia.ui.sync_screens).

Os ecrãs do Strava têm o agente desligado (F1/F2): pelo acordo da API do
Strava, esses dados não podem ir para sistemas de IA.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from perennia.core import importers
from perennia.core import segments as seg_mod
from perennia.core import strava_library as lib_mod
from perennia.core.i18n import t, tr
from perennia.core.units import hms
from perennia.io import strava as strava_mod
from pyglet.window import key

from perennia.ui.app import Screen
from perennia.ui.widgets import Item


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


def strava_job(app_db, http, fn: Callable[[Any, Any], Any]) -> "Job":
    """Um trabalho do Strava numa thread **com a sua própria ligação à base de dados**: a
    ligação do ecrã não pode ser usada por duas threads ao mesmo tempo (a SQLite pode
    estoirar). `fn(db, client)` corre na thread; o ecrã continua a ler pela ligação dele."""
    from perennia.core.db import Database
    path = app_db.path

    def run():
        wdb = Database(path)
        try:
            return fn(wdb, strava_mod.StravaClient(wdb, http=http))
        finally:
            wdb.close()
    return Job(run)


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
            Item("Client Secret",
                 value=(tr("(variável de ambiente)", "(environment variable)") if c.secret_from_env
                        else _mask(c.client_secret) + "▏"),
                 data=None if c.secret_from_env else "text:strava_client_secret",
                 enabled=not c.secret_from_env,
                 detail=tr("Fica só neste computador. Em alternativa, define a variável de "
                           f"ambiente {strava_mod.ENV_CLIENT_SECRET} e nada fica na base de dados",
                           "Stays on this computer. Alternatively set the "
                           f"{strava_mod.ENV_CLIENT_SECRET} environment variable and nothing is "
                           "stored in the database")),
            Item(tr("Autorizar no browser", "Authorize in the browser"),
                 action=self._authorize, enabled=bool(c.client_id and c.client_secret),
                 detail=tr("Abre o Strava; aceita e volta aqui", "Opens Strava; accept and come back")),
        ]
        if c.connected:
            rows.append(Item(
                tr("Permissões", "Permissions"),
                value=tr("autoriza de novo", "authorize again") if c.needs_reauth
                else tr("completas", "complete"),
                detail=(tr("falta a permissão «read_all» (o teu PR e os teus esforços): carrega "
                           "em «Autorizar no browser» outra vez",
                           "the “read_all” permission (your PR and efforts) is missing: press "
                           "“Authorize in the browser” again") if c.needs_reauth else
                        tr("leitura dos teus segmentos e esforços", "read your segments and "
                           "efforts")), enabled=False))
            rows.append(Item(tr("Desligar o Strava", "Disconnect Strava"), action=self._disconnect))
        rows += [
            Item(tr("Como criar a aplicação no Strava", "How to create the Strava app"),
                 enabled=False,
                 detail=tr("strava.com/settings/api → nome Perennia, site http://localhost, "
                           "Authorization Callback Domain: localhost",
                           "strava.com/settings/api → name Perennia, website http://localhost, "
                           "Authorization Callback Domain: localhost")),
            Item(tr("O que a Perennia lê", "What Perennia reads"), enabled=False,
                 detail=tr("Os segmentos que cruzam as tuas rotas, os que importas por ID ou "
                           "pelos favoritos, os teus PR e (com subscrição) os teus esforços. Nada "
                           "é enviado para o Strava, e nada do Strava vai para o agente de IA.",
                           "Segments crossing your routes, those you import by ID or from your "
                           "favourites, your PRs and (with a subscription) your efforts. Nothing "
                           "is sent to Strava, and nothing from Strava goes to the AI agent.")),
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
        rows.append(Item(tr("Ligar da biblioteca (sem internet)", "Link from the library (offline)"),
                         action=self._link_library,
                         detail=tr("os segmentos que já importaste e que esta rota percorre",
                                   "segments you already imported that this route follows")))
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
                bits.append(tr("melhor {t}", "best {t}", t=hms(s.local_best_s)))
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

    def _link_library(self) -> None:
        r = lib_mod.link_route(self.app.db, self.route_id)
        self.app.message(tr("{n} segmentos da biblioteca nesta rota ({c} vistos)",
                            "{n} library segments on this route ({c} checked)",
                            n=r["linked"], c=r["checked"]))
        self.enter()

    def _refresh(self) -> None:
        if self.job is not None and not self.job.done:
            return
        rid = self.route_id
        self.job = strava_job(self.app.db, self.client.http,
                              lambda db, client: seg_mod.fetch_for_route(db, client, rid))
        self.enter()

    def update(self, dt: float) -> None:
        j = self.job
        if j is not None and j.done:
            self.job = None
            if j.error:
                self.app.message(f"Strava: {j.error}")
            else:
                r = j.result
                self.app.message(tr("{m} segmentos na rota ({e} vistos) · {l} ligados da "
                                    "biblioteca", "{m} segments on the route ({e} seen) · {l} "
                                    "linked from the library",
                                    m=r["matched"], e=r["explored"], l=r.get("linked", 0)))
            self.enter()


def clipboard_text(window) -> str:
    """O texto copiado (Ctrl+V). Vazio se o sistema não o der."""
    try:
        return str(window.get_clipboard_text() or "")
    except Exception:
        pass
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        try:
            return str(root.clipboard_get())
        finally:
            root.destroy()
    except Exception:
        return ""


class StravaImportScreen(Screen):
    """Importar segmentos do Strava para a biblioteca (precisa de internet, uma vez):
    por **ID ou ligação** (vários de uma vez), pelos teus **favoritos ⭐**, ou **atualizar** os
    que já lá estão. Depois ficam neste computador e ligam-se às rotas sem rede."""

    AGENT = False

    def __init__(self, app, http=None):
        super().__init__(app)
        self.client = strava_mod.StravaClient(app.db, http=http)
        self.ids_text = ""
        self.job: Job | None = None
        self.progress: tuple[int, int] = (0, 0)
        self._shown_progress: tuple[int, int] = (0, 0)

    def _busy(self) -> bool:
        return self.job is not None and not self.job.done

    def enter(self) -> None:
        c = self.client
        ids = lib_mod.parse_ids(self.ids_text)
        busy = self._busy()
        ok = c.connected and not busy
        batch = int(self.app.db.get("strava_import_batch", 30) or 30)
        rows = [
            Item(tr("Estado", "Status"),
                 value=(tr("a importar {n}/{m}…", "importing {n}/{m}…", n=self.progress[0],
                           m=self.progress[1]) if busy else
                        (tr("ligado · {n}", "connected · {n}", n=c.athlete_name or "Strava")
                         if c.connected else tr("não ligado", "not connected"))),
                 detail=(tr("liga o Strava em Definições → Strava", "connect Strava in "
                            "Settings → Strava") if not c.connected else
                         (tr("falta a permissão read_all: autoriza de novo em Definições → "
                             "Strava", "the read_all permission is missing: authorize again in "
                             "Settings → Strava") if c.needs_reauth else "")),
                 enabled=False),
            Item(tr("IDs ou ligações", "IDs or links"),
                 value=(self.ids_text[-60:] + "▏") if self.ids_text else "▏",
                 data="text:ids",
                 detail=tr("cola (Ctrl+V) ou escreve: strava.com/segments/12345, 67890… "
                           "separados por espaços, vírgulas ou linhas · {n} reconhecidos",
                           "paste (Ctrl+V) or type: strava.com/segments/12345, 67890… "
                           "separated by spaces, commas or lines · {n} recognised",
                           n=len(ids))),
            Item(tr("Importar estes segmentos", "Import these segments"), button=True,
                 primary=True, enabled=ok and bool(ids), action=self._import_ids,
                 detail=tr("o traçado, a distância, o teu PR e (com subscrição) os teus esforços",
                           "the path, distance, your PR and (with a subscription) your efforts")),
            Item(tr("Importar os meus favoritos ⭐", "Import my starred segments ⭐"),
                 button=True, enabled=ok, action=self._import_starred,
                 detail=tr("os segmentos que marcaste com ⭐ no Strava",
                           "the segments you starred on Strava")),
            Item(tr("Atualizar a biblioteca", "Refresh the library"), button=True, enabled=ok,
                 action=self._refresh_all,
                 detail=tr("{n} segmentos: o PR e os esforços de cada um",
                           "{n} segments: the PR and efforts of each",
                           n=len(lib_mod.library(self.app.db)))),
            Item(tr("Limites do Strava", "Strava limits"), enabled=False,
                 detail=tr("~100 pedidos a cada 15 min: cada segmento custa 1 (2 com esforços); "
                           "no máximo {b} por importação, o resto fica à espera. Os esforços "
                           "precisam de subscrição Strava (sem ela só entra o PR).",
                           "~100 requests per 15 min: each segment costs 1 (2 with efforts); at "
                           "most {b} per import, the rest waits. Efforts need a Strava "
                           "subscription (without it only the PR comes in).", b=batch)),
        ]
        self.chrome.set(tr("Importar do Strava", "Import from Strava"),
                        tr("para usares os segmentos sem internet",
                           "to use the segments offline"), self.footer())
        self.list.set_items(rows, keep_index=True)

    def text_input(self, field: str, text: str) -> None:
        if field == "ids":
            self.ids_text = (self.ids_text + text)[-4000:]
            self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "ids":
            self.ids_text = self.ids_text[:-1]
            self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.V and modifiers & (key.MOD_CTRL | getattr(key, "MOD_COMMAND", 0)) and \
                item is not None and item.data == "text:ids":
            got = clipboard_text(self.app.window)
            if got:
                self.ids_text = (self.ids_text + " " + got)[-4000:]
                self.enter()
            else:
                self.app.message(tr("Não consegui ler o que copiaste; escreve os IDs.",
                                    "Could not read the clipboard; type the IDs."))
            return True
        if symbol == key.DELETE and item is not None and item.data == "text:ids":
            self.ids_text = ""
            self.enter()
            return True
        return super().on_key(symbol, modifiers)

    # ------------------------------------------------------------- trabalhos

    def _progress(self, n: int, m: int) -> None:
        self.progress = (n, m)

    def _start(self, fn) -> None:
        if self._busy():
            return
        self.progress = (0, 0)
        self.job = strava_job(self.app.db, self.client.http, fn)
        self.enter()

    def _import_ids(self) -> None:
        ids = lib_mod.parse_ids(self.ids_text)
        self._start(lambda db, c: lib_mod.import_ids(db, c, ids, progress=self._progress))

    def _import_starred(self) -> None:
        self._start(lambda db, c: lib_mod.import_starred(db, c, progress=self._progress))

    def _refresh_all(self) -> None:
        self._start(lambda db, c: lib_mod.refresh(db, c, progress=self._progress))

    def update(self, dt: float) -> None:
        j = self.job
        if j is None:
            return
        if not j.done:
            if self.progress != self._shown_progress:
                self._shown_progress = self.progress
                self.enter()
            return
        self.job = None
        if j.error:
            self.app.message(f"Strava: {j.error}")
        else:
            rep = j.result
            linked = lib_mod.link_all(self.app.db)["linked"] if rep["added"] or rep["updated"] \
                else 0
            self.ids_text = " ".join(str(i) for i in rep["remaining"]) if rep["remaining"] \
                else ("" if not rep["failed"] else " ".join(str(f[0]) for f in rep["failed"]))
            self.app.message(rep.text() + (" · " + tr("{n} ligações às rotas",
                                                      "{n} links to routes", n=linked)
                                           if linked else ""))
        self.enter()


# ================================================================ GarminDB


def GarminDBScreen(app, runner=None):                      # noqa: N802 — compatibilidade
    """O GarminDB está em Definições → Sincronização: abre as Definições lá."""
    from perennia.ui.app import SettingsScreen
    scr = SettingsScreen(app)
    scr.sync.runner = runner
    scr.tab_named(tr("Sincronização", "Sync"))
    return scr


def folder_exists(p: str) -> bool:
    return Path(p).expanduser().is_dir()
