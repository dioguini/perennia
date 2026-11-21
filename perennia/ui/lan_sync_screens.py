"""Sincronizar duas Perennia pelo Wi-Fi (ver `perennia.core.lan_sync`).

* **Receber** (o destino): mostra o endereço, a porta e um PIN de uso único; quando a outra
  Perennia envia, repõe os dados (com backup de segurança antes).
* **Enviar** (a fonte): escreves o endereço e o PIN do destino, escolhes as componentes e o modo
  (juntar ou substituir) e envias.

O PIN nunca se guarda. O envio e a escuta correm numa thread à parte; o ecrã vai lendo o estado."""
from __future__ import annotations

import threading
import time

from perennia.core import backup as bk, lan_sync as ls
from perennia.core.i18n import tr
from perennia.ui.app import Screen
from perennia.ui.widgets import Dropdown, Item


class LanReceiveScreen(Screen):
    def __init__(self, app, receiver=None):
        super().__init__(app)
        self.rx = receiver
        self.thread: threading.Thread | None = None
        self.error = ""
        self.report: dict | None = None
        self._applied = False
        self._shown = None

    def enter(self) -> None:
        if self.rx is None and not self.error:
            try:
                self.rx = ls.Receiver(self.app.db, self.app.data_dir)
                self.rx.open()
            except ls.SyncError as e:
                self.error = str(e)
            except Exception as e:                      # certificado, rede…
                self.error = str(e)
        if self.rx is not None and self.thread is None and self.rx.status == "waiting":
            self.thread = threading.Thread(target=self.rx.wait, daemon=True)
            self.thread.start()
        self._refresh(force=True)

    def leave(self) -> None:
        if self.rx is not None and self.rx.status in ("waiting", "receiving"):
            self.rx.cancel()

    def _lines(self) -> list[Item]:
        rx = self.rx
        if self.error:
            return [Item(tr("Não foi possível receber", "Could not receive"),
                         value=self.error, enabled=False)]
        if self.report is not None:
            return [Item(tr("Recebido", "Received"), value=ls.report_text(self.report),
                         enabled=False)]
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
                     detail=tr("fecha sozinho em {s} s", "closes by itself in {s} s", s=left)
                     if left else "")]
        if rx.message and rx.status == "waiting":
            rows.append(Item(tr("Última tentativa", "Last attempt"), value=rx.message,
                              enabled=False))
        return rows

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
                        tr("Esc cancelar e voltar", "Esc cancel and go back"))
        self.list.set_items(self._lines() + [Item(
            tr("Cancelar", "Cancel") if self.report is None else tr("Fechar", "Close"),
            action=self.app.pop, button=True, primary=True)], keep_index=True)

    def update(self, dt: float) -> None:
        rx = self.rx
        if rx is None:
            return
        if rx.status == "received" and not self._applied and rx.result:
            self._applied = True
            try:
                self.report = rx.apply()
                self.app.message(ls.report_text(self.report))
            except ls.SyncError as e:
                self.error = str(e)
            self._refresh(force=True)
            return
        self._refresh()


class LanSendScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        db = app.db
        self.v = {"host": str(db.get("sync_last_host", "") or ""), "pin": "",
                  "mode": ls.mode_of(db), "keys": set(ls.components(db))}
        self.job: dict | None = None
        self.log = ""

    def enter(self) -> None:
        self._refresh()

    def _busy(self) -> bool:
        return self.job is not None and not self.job.get("done")

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
        v = self.v
        if not v["host"].strip() or not v["pin"] or not v["keys"]:
            self.app.message(tr("Falta o endereço, o PIN ou alguma componente.",
                                "The address, the PIN or a component is missing."))
            return
        a = self.app
        a.db.set("sync_last_host", v["host"].strip())
        job = self.job = {"done": False, "error": "", "report": None, "step": ""}
        args = (a.db, a.data_dir, v["host"].strip(), v["pin"], None, sorted(v["keys"]),
                v["mode"], lambda n: job.__setitem__("step", n))

        def run() -> None:
            try:
                job["report"] = ls.send(*args)
            except ls.SyncError as e:
                job["error"] = str(e)
            except Exception as e:
                job["error"] = str(e)
            finally:
                job["done"] = True
        threading.Thread(target=run, daemon=True).start()
        self.log = tr("a enviar…", "sending…")
        self._refresh()

    def update(self, dt: float) -> None:
        job = self.job
        if job is None:
            return
        if job["done"]:
            self.job = None
            if job["error"]:
                self.log = job["error"]
                self.app.message(job["error"])
            else:
                r = job["report"]
                self.log = tr("Enviado {mb:.1f} MB ({m})", "Sent {mb:.1f} MB ({m})",
                              mb=r["bytes"] / 1048576, m=r["mode"])
                self.v["pin"] = ""                      # o PIN é de uma vez só
                self.app.message(self.log)
            self._refresh()
        elif job["step"] and job["step"] != self.log:
            self.log = job["step"]
            self._refresh()
