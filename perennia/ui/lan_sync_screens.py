"""Sincronizar duas Perennia pelo Wi-Fi (ver `perennia.core.lan_sync`).

* **Receber** (o destino): mostra o endereço, a porta e um PIN de uso único; quando a outra
  Perennia envia, repõe os dados (com backup de segurança antes).
* **Enviar** (a fonte): escreves o endereço e o PIN do destino, escolhes as componentes e o modo
  (juntar ou substituir) e envias.

O PIN nunca se guarda. O envio e a escuta correm numa thread à parte; o ecrã vai lendo o estado."""
from __future__ import annotations

from perennia.core import backup as bk, lan_sync as ls
from perennia.core.i18n import tr
from perennia.ui.app import Screen
from perennia.ui.widgets import Dropdown, Item


RECEIVE = "sync:wifi-receive"
SEND = "sync:wifi"


class LanReceiveScreen(Screen):
    """Receber: a escuta é uma sincronização em segundo plano (ronda 35). Sair deste ecrã
    não a cancela: continua à espera (vê-se no topo, ao lado de «Perennia», e o PIN aparece
    na janela das sincronizações) até chegar o envio, o PIN caducar ou carregares em Parar."""

    def __init__(self, app, receiver=None):
        super().__init__(app)
        self.rx = receiver
        self.task = None
        self.error = ""
        self.report: dict | None = None
        self._shown = None

    @property
    def thread(self):
        """A thread que escuta (a da tarefa)."""
        return getattr(getattr(self.task, "job", None), "thread", None)

    def enter(self) -> None:
        a = self.app
        running = a.running_task(RECEIVE) if hasattr(a, "running_task") else None
        if running is not None:                         # já está à escuta: mostra-a
            self.task, self.rx = running, getattr(running, "rx", None)
        elif self.task is None and not self.error:
            self._start()
        self._refresh(force=True)

    def _start(self) -> None:
        from perennia.core.db import Database
        from perennia.ui.background import run_task
        a = self.app
        wdb = None
        try:
            if self.rx is None:
                # a escuta e a reposição correm noutra thread: com a sua própria ligação
                wdb = Database(a.db.path)
                self.rx = ls.Receiver(wdb, a.data_dir)
            self.rx.open()
        except Exception as e:                          # a porta, o certificado, a rede…
            self.error = str(e)
            if wdb is not None:
                wdb.close()
            return
        rx = self.rx
        addrs = ", ".join(ls.local_addresses()) or tr("(sem rede?)", "(no network?)")

        def work(_db, log):
            try:
                log.step(tr("À espera da outra Perennia", "Waiting for the other Perennia"))
                log.detail(tr("endereço {a} · porta {p} · PIN {n}",
                              "address {a} · port {p} · PIN {n}",
                              a=addrs, p=rx.port, n=" ".join(rx.pin)))
                rx.wait()
                if rx.status != "received" or not rx.result:
                    why = rx.message or tr("não chegou nada", "nothing arrived")
                    log.end(False, why)
                    return False, tr("Wi-Fi: {w}", "Wi-Fi: {w}", w=why), None
                log.end(True, tr("recebido", "received"))
                log.step(tr("A repor os dados recebidos (com cópia de segurança antes)",
                            "Restoring the received data (with a safety copy first)"))
                rep = rx.apply()
                text = ls.report_text(rep)
                log.end(True, text)
                log.step(tr("Concluído", "Done"))
                log.end(True)
                return True, text, rep
            finally:
                rx.close()
                if wdb is not None:
                    wdb.close()

        def then(ok: bool, text: str, rep) -> None:
            if ok:
                self.report = rep
            elif not self.error and rx.status not in ("closed",):
                self.error = text
            if self in getattr(a, "stack", []):
                self._refresh(force=True)
        self.task = run_task(a, RECEIVE, tr("Wi-Fi: receber de outra Perennia",
                                            "Wi-Fi: receive from another Perennia"),
                             work, short="Wi-Fi", then=then, own_db=False, waits=True,
                             cancel_fn=rx.cancel, open_fn=lambda app: app.push(
                                 LanReceiveScreen(app)))
        if self.task is not None:
            self.task.rx = rx

    def leave(self) -> None:
        pass                       # a escuta continua (Parar na janela das sincronizações)

    def _lines(self) -> list[Item]:
        rx = self.rx
        if self.error:
            return [Item(tr("Não foi possível receber", "Could not receive"),
                         value=self.error, enabled=False)]
        if self.report is not None:
            return [Item(tr("Recebido", "Received"), value=ls.report_text(self.report),
                         enabled=False)]
        if rx is None:
            return []
        addrs = ", ".join(ls.local_addresses()) or tr("(sem rede?)", "(no network?)")
        status = {"waiting": tr("à espera da outra Perennia", "waiting for the other Perennia"),
                  "receiving": tr("a receber…", "receiving…"),
                  "received": tr("recebido — a repor…", "received — restoring…"),
                  "failed": rx.message, "closed": rx.message}.get(rx.status, rx.status)
        left = int(rx.remaining()) if rx.status == "waiting" else 0
        rows = [Item(tr("Endereço", "Address"), value=addrs, enabled=False,
                     detail=tr("o que escreves na outra Perennia", "what you type in the other "
                               "Perennia")),
                Item(tr("Porta", "Port"), value=str(rx.port), enabled=False),
                Item(tr("PIN (uso único)", "PIN (single use)"), value=" ".join(rx.pin),
                     enabled=False, detail=tr("diz-o só à tua outra Perennia", "tell it only to "
                                              "your other Perennia")),
                Item(tr("Estado", "Status"), value=status, enabled=False,
                     detail=tr("fecha sozinho em {s} s · podes sair deste ecrã: continua à "
                               "espera (vê-se no topo)", "closes by itself in {s} s · you can "
                               "leave this screen: it keeps waiting (shown at the top)", s=left)
                     if left else "")]
        if rx.message and rx.status == "waiting":
            rows.append(Item(tr("Última tentativa", "Last attempt"), value=rx.message,
                              enabled=False))
        return rows

    def _cancel(self) -> None:
        t = self.task
        if t is not None and t.running:
            t.cancel()
        self.app.pop()

    def _refresh(self, force: bool = False) -> None:
        rx = self.rx
        key = (rx.status, rx.message, int(rx.remaining()) // 5, self.error,
               self.report is not None) if rx else (self.error,)
        if not force and key == self._shown:
            return
        self._shown = key
        self.chrome.set(tr("Receber de outra Perennia (destino)", "Receive from another Perennia"
                           " (destination)"),
                        tr("Na outra Perennia: Enviar → este endereço e este PIN · rede local "
                           "apenas", "On the other Perennia: Send → this address and PIN · local "
                           "network only"),
                        tr("Esc voltar (continua à espera)", "Esc back (keeps waiting)"))
        waiting = self.task is not None and self.task.running
        buttons = [Item(tr("Parar de receber", "Stop receiving"), action=self._cancel,
                        button=True, danger=True)] if waiting else []
        buttons.append(Item(tr("Voltar", "Back") if waiting else tr("Fechar", "Close"),
                            action=self.app.pop, button=True, primary=True))
        self.list.set_items(self._lines() + buttons, keep_index=True)

    def update(self, dt: float) -> None:
        if hasattr(self.app, "poll_task"):
            self.app.poll_task()
        self._refresh()


class LanSendScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        db = app.db
        self.v = {"host": str(db.get("sync_last_host", "") or ""), "pin": "",
                  "mode": ls.mode_of(db), "keys": set(ls.components(db))}
        self.log = ""

    def enter(self) -> None:
        self._refresh()

    def _busy(self) -> bool:
        a = self.app
        return hasattr(a, "running_task") and a.running_task(SEND) is not None

    def _refresh(self) -> None:
        v = self.v
        self.chrome.set(tr("Enviar para outra Perennia (fonte)", "Send to another Perennia "
                           "(source)"),
                        tr("No destino: Receber → escreve aqui o endereço e o PIN que aparecem · "
                           "rede local apenas", "On the destination: Receive → type here the "
                           "address and PIN shown · local network only"),
                        tr("↑↓ linha · Enter abrir/marcar · Esc voltar",
                           "↑↓ row · Enter open/toggle · Esc back"))
        modes = [("merge", tr("Juntar (acrescenta o que é novo)", "Merge (adds what is new)")),
                 ("replace", tr("Substituir (o destino fica igual à fonte)",
                                "Replace (the receiver becomes a copy of the source)"))]
        rows = [Item(tr("Endereço do destino", "Receiver address"),
                     value=v["host"] + "▏", data="text:host",
                     detail=tr("o que o destino mostra (ex.: 192.168.1.20)",
                               "what the receiver shows (e.g. 192.168.1.20)")),
                Item(tr("PIN do destino", "Receiver PIN"), value="•" * len(v["pin"]) + "▏",
                     data="text:pin", detail=tr("não fica guardado", "it is not saved")),
                Item(tr("Modo", "Mode"), value=dict(modes)[v["mode"]],
                     dropdown=Dropdown([n for _k, n in modes],
                                       [k for k, _n in modes].index(v["mode"]), self._pick_mode,
                                       title=tr("Modo", "Mode")),
                     detail=tr("«Substituir» apaga no destino o que não está na fonte (com "
                               "cópia de segurança)", "'Replace' removes on the receiver what "
                               "is not on the source (with a safety copy)")),
                Item(tr("O que enviar", "What to send"), header=True)]
        for c in bk.COMPONENTS:
            if c.key in ls.NEVER:
                continue
            rows.append(Item(c.name, value="✓" if c.key in v["keys"] else "—",
                             action=lambda k=c.key: self._toggle(k),
                             detail=tr(c.desc_pt, c.desc_en)))
        if self.log:
            rows.append(Item(tr("Estado", "Status"), value=self.log, enabled=False))
        rows.append(Item(tr("Enviar", "Send"), button=True, primary=True,
                          enabled=not self._busy(), action=self._send))
        self.list.set_items(rows, keep_index=True)

    def _pick_mode(self, i: int) -> None:
        self.v["mode"] = ("merge", "replace")[i]
        self._refresh()

    def _toggle(self, key: str) -> None:
        self.v["keys"] ^= {key}
        self._refresh()

    def text_input(self, field: str, text: str) -> None:
        if field == "pin":
            text = "".join(c for c in text if c.isdigit())
        self.v[field] = (self.v[field] + text)[:64 if field == "host" else 12]
        self._refresh()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self._refresh()

    def _send(self) -> None:
        """Envia em segundo plano (ronda 35): podes sair deste ecrã, o envio continua e vê-se
        no topo, ao lado de «Perennia»."""
        from perennia.ui.background import run_task
        v = self.v
        if not v["host"].strip() or not v["pin"] or not v["keys"]:
            self.app.message(tr("Falta o endereço, o PIN ou alguma componente.",
                                "The address, the PIN or a component is missing."))
            return
        a = self.app
        host, pin, keys, mode = v["host"].strip(), v["pin"], sorted(v["keys"]), v["mode"]
        a.db.set("sync_last_host", host)
        data_dir = a.data_dir

        def work(db, log):
            log.step(tr("A enviar para {h}", "Sending to {h}", h=host))
            r = ls.send(db, data_dir, host, pin, None, keys, mode, log.detail)
            text = tr("Enviado {mb:.1f} MB ({m})", "Sent {mb:.1f} MB ({m})",
                      mb=r["bytes"] / 1048576, m=r["mode"])
            log.end(True, text)
            log.step(tr("Concluído", "Done"))
            log.end(True)
            return True, text, r

        def then(ok: bool, text: str, _r) -> None:
            self.log = text
            if ok:
                self.v["pin"] = ""                      # o PIN é de uma vez só
            if self in getattr(a, "stack", []):
                self._refresh()
        if run_task(a, SEND, tr("Wi-Fi: enviar para {h}", "Wi-Fi: send to {h}", h=host), work,
                    short="Wi-Fi", then=then,
                    open_fn=lambda app: app.show_sync_tab("Wi-Fi")) is not None \
                and self._busy():
            self.log = tr("a enviar… (vê o progresso no topo)", "sending… (progress at the top)")
        self._refresh()

    def update(self, dt: float) -> None:
        a = self.app
        t = a.running_task(SEND) if hasattr(a, "running_task") else None
        if t is not None:
            step = t.step_text()
            if step and step != self.log:
                self.log = step
                self._refresh()
