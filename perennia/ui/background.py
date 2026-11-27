"""Trabalhos demorados em segundo plano (ronda 34): a sincronização do GarminDB pertence à
**aplicação**, não ao ecrã onde começou.

Antes, a sincronização era de um ecrã. Ao ir ver o calendário, o GarminDB continuava a correr,
mas ninguém o via, o resultado perdia-se e nada impedia uma segunda sincronização por cima.
Agora:

- a `BackgroundTask` vive na `App` (`app.task`) e o resultado é tratado em qualquer ecrã;
- a faixa do topo mostra-a ao lado de «Perennia» (a decorrer, ✓ concluída, ✗ falhou);
- um clique abre o `TaskPopup`, com os passos e o que o GarminDB vai dizendo, e com Fechar
  (continua em segundo plano), Ver na Sincronização e Parar;
- sair da Perennia pede confirmação, e repor um backup espera que ela acabe.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from perennia.core.i18n import tr
from perennia.ui.widgets import Item

KEEP_OK_S = 120              # uma tarefa que correu bem fica à vista no topo durante 2 min


def clock(seconds: float) -> str:
    """«03:12» ou «1:02:05»."""
    s = max(0, int(seconds))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


class BackgroundTask:
    """Um trabalho numa thread que pertence à aplicação.

    `fn()` corre na thread; quando acaba, `finish(app, task)` corre na thread da janela
    (no `App.poll_task`, em qualquer ecrã): diz o resultado e põe `ok` e `summary`."""

    def __init__(self, kind: str, title: str, fn: Callable[[], Any], log=None,
                 finish: Callable[[Any, "BackgroundTask"], None] | None = None,
                 clock_fn: Callable[[], float] = time.monotonic, short: str | None = None):
        from perennia.ui.connect_screens import Job
        self.kind, self.title, self.log = kind, title, log
        self.short = short or title            # o nome curto, para a faixa do topo
        self.finish = finish
        self._clock = clock_fn
        self.started = clock_fn()
        self.ended: float | None = None
        self.ok: bool | None = None           # None enquanto corre
        self.summary = ""
        self.handled = False
        self.job = Job(fn)

    # ------------------------------------------------------------- estado

    @property
    def running(self) -> bool:
        return not self.job.done or not self.handled

    @property
    def cancelled(self) -> bool:
        return bool(self.log is not None and getattr(self.log, "cancelled", False))

    def cancel(self) -> None:
        if self.log is not None and hasattr(self.log, "cancel"):
            self.log.cancel()

    def elapsed(self) -> float:
        end = self.ended if self.ended is not None else self._clock()
        return end - self.started

    def state(self) -> str:
        """run | ok | fail | stop"""
        if self.running:
            return "run"
        if self.cancelled:
            return "stop"
        return "ok" if self.ok else "fail"

    def step_text(self) -> str:
        cur = self.log.current() if self.log is not None and hasattr(self.log, "current") else ""
        return cur

    def chip_text(self) -> str:
        """O texto da faixa do topo."""
        st = self.state()
        name = self.short
        if st == "run":
            if self.cancelled:
                return tr("{t} · a parar…", "{t} · stopping…", t=name)
            return f"{name} · {clock(self.elapsed())}"
        if st == "stop":
            return tr("{t} · parado", "{t} · stopped", t=name)
        if st == "ok":
            return "✓ " + name
        return "✗ " + tr("{t} · falhou", "{t} · failed", t=name)

    def finish_now(self, app) -> None:
        """Trata o resultado (uma vez só)."""
        if self.handled or not self.job.done:
            return
        self.handled = True
        self.ended = self._clock()
        if self.finish is not None:
            try:
                self.finish(app, self)
            except Exception as e:                       # nunca deixa a janela ir abaixo
                self.ok = False
                self.summary = str(e) or type(e).__name__
                app.message(self.title + ": " + self.summary)
        elif self.job.error:
            self.ok, self.summary = False, self.job.error
            app.message(self.title + ": " + self.job.error)
        else:
            self.ok = True
        if self.ok is None:
            self.ok = not self.job.error

    def wait(self, seconds: float) -> bool:
        """Espera que a thread acabe (ao sair da Perennia: o GarminDB foi parado e a pasta
        temporária com a palavra-passe tem de ser apagada). True se acabou."""
        th = getattr(self.job, "thread", None)
        if th is not None:
            th.join(seconds)
        return self.job.done


def log_items(log, busy: bool, title_run: str | None = None,
              title_done: str | None = None) -> list[Item]:
    """Os passos (▶ ✓ ✗ –) e as últimas linhas do GarminDB, como linhas de uma lista."""
    if log is None:
        return []
    steps, lines = log.snapshot()
    icon = {"run": "▶", "ok": "✓", "fail": "✗", "skip": "–"}
    rows = [Item(title_run or tr("— O que está a acontecer —", "— What is happening —")
                 if busy else title_done or tr("— Última sincronização —", "— Last sync —"),
                 enabled=False)]
    for n, st in enumerate(steps, 1):
        rows.append(Item(f"{icon[st['state']]} {n}. {st['text']}",
                         detail=st["detail"], enabled=False))
    if lines:
        rows.append(Item(tr("— O que o GarminDB diz —", "— What GarminDB says —"),
                         enabled=False))
        rows += [Item("   " + ln, enabled=False) for ln in lines]
    return rows


def _popup_base():
    from perennia.ui.app import ModalScreen
    return ModalScreen


class TaskPopup(_popup_base()):
    """A janela da tarefa em segundo plano: o que está a acontecer, ao vivo. Fechar não a
    pára; «Parar» pergunta antes."""

    W, H = 860, 600

    def __init__(self, app):
        super().__init__(app)
        self.back_button = None              # Fechar / OK já fecham
        self._seen = None

    @property
    def task(self) -> BackgroundTask | None:
        return getattr(self.app, "task", None)

    def subtitle_text(self) -> str:
        t = self.task
        if t is None:
            return ""
        st = t.state()
        if st == "run":
            if t.cancelled:
                return tr("A parar o GarminDB…", "Stopping GarminDB…")
            return tr("A decorrer há {c} · podes continuar a usar a Perennia",
                      "Running for {c} · you can keep using Perennia", c=clock(t.elapsed()))
        if st == "stop":
            return tr("Parada ao fim de {c}", "Stopped after {c}", c=clock(t.elapsed()))
        if st == "ok":
            return tr("Concluída em {c}", "Done in {c}", c=clock(t.elapsed())) + \
                (" · " + t.summary if t.summary else "")
        return tr("Falhou ao fim de {c}", "Failed after {c}", c=clock(t.elapsed())) + \
            (" · " + t.summary if t.summary else "")

    def enter(self) -> None:
        t = self.task
        a = self.app
        if t is None:
            self.chrome.set(tr("Sem tarefas em segundo plano", "No background tasks"), "", "")
            self.list.set_items([Item(tr("Fechar", "Close"), action=a.pop, button=True,
                                      primary=True)])
            return
        self.chrome.set(t.title, self.subtitle_text(), "")
        rows = log_items(t.log, t.running, title_done=tr("— Como correu —", "— How it went —"))
        if t.running:
            rows += [Item(tr("Parar", "Stop"), action=self.ask_stop, button=True, danger=True,
                          enabled=not t.cancelled),
                     Item(tr("Ver na Sincronização", "Show in Sync"), action=self.show_sync,
                          button=True),
                     Item(tr("Fechar", "Close"), action=a.pop, button=True, primary=True)]
        else:
            rows += [Item(tr("Ver na Sincronização", "Show in Sync"), action=self.show_sync,
                          button=True),
                     Item("OK", action=self.dismiss, button=True, primary=True)]
        self.list.set_items(rows, keep_index=True)
        if not self.list.items[self.list.index].button:
            self.list.index = len(self.list.items) - 1
            self.list._sync()

    def _key(self):
        t = self.task
        if t is None:
            return None
        return (t.state(), t.cancelled, getattr(t.log, "version", 0), int(t.elapsed()))

    def update(self, dt: float) -> None:
        self.app.poll_task()
        k = self._key()
        if k != self._seen:
            self._seen = k
            self.enter()

    # ------------------------------------------------------------- ações

    def ask_stop(self) -> None:
        a = self.app
        t = self.task
        if t is None or not t.running:
            return

        def stop() -> None:
            t.cancel()
            a.message(tr("A parar a sincronização…", "Stopping the sync…"))
        a.confirm(tr("Parar a sincronização?", "Stop the sync?"),
                  tr("O GarminDB é interrompido. O que já foi descarregado fica guardado e a "
                     "próxima sincronização continua daí.",
                     "GarminDB is interrupted. What was already downloaded is kept and the next "
                     "sync carries on from there."), stop,
                  yes=tr("Sim, parar", "Yes, stop"), no=tr("Não, continuar", "No, keep going"))

    def show_sync(self) -> None:
        a = self.app
        a.pop()
        a.show_task_source()

    def dismiss(self) -> None:
        a = self.app
        a.pop()
        t = self.task
        if t is not None and not t.running:
            a.task = None
            a.refresh_task_chip()
