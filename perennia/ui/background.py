"""Sincronizações em segundo plano (rondas 34 e 35): pertencem à **aplicação**, não ao ecrã
onde começaram.

Antes, cada sincronização pertencia a um ecrã. Ao ir ver o calendário, a sincronização
continuava a correr, mas ninguém a via, o resultado perdia-se e nada impedia outra por cima.
Agora todas funcionam da mesma maneira: GarminDB, ficheiros (HRV4Training, Análises,
TrainingPeaks, Histórico, Saúde), CSV, upload manual, Wi-Fi e Strava.

- Cada uma é uma `BackgroundTask` em `app.tasks`. Pode correr uma de cada tipo ao mesmo
  tempo, e o resultado é tratado em qualquer ecrã.
- A faixa do topo mostra-a ao lado de «Perennia» (a decorrer, ✓ concluída, ✗ falhou), mesmo
  as que levam um segundo: vê-se sempre o que aconteceu.
- Um clique abre o `TaskPopup`, com os passos de cada uma e os botões Fechar, Ver, Parar e OK.
- Sair da Perennia pede confirmação, e repor um backup espera que acabem.

`run_task` é o caminho simples. Recebe um `work(db, log)`, que corre na thread com a sua
própria ligação à base de dados, conta os passos no `log` e devolve `(ok, texto, relatório)`.
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
    (no `App.poll_task`, em qualquer ecrã): diz o resultado e põe `ok` e `summary`.
    `open_fn(app)` mostra de onde veio («Ver na Sincronização»); `cancel_fn()` pára-o (além
    do `log.cancel()`, que interrompe o GarminDB)."""

    def __init__(self, kind: str, title: str, fn: Callable[[], Any], log=None,
                 finish: Callable[[Any, "BackgroundTask"], None] | None = None,
                 clock_fn: Callable[[], float] = time.monotonic, short: str | None = None,
                 open_fn: Callable[[Any], None] | None = None,
                 cancel_fn: Callable[[], None] | None = None):
        from perennia.ui.connect_screens import Job
        self.kind, self.title, self.log = kind, title, log
        self.short = short or title            # o nome curto, para a faixa do topo
        self.finish = finish
        self.open_fn = open_fn
        self.cancel_fn = cancel_fn
        self._clock = clock_fn
        self.started = clock_fn()
        self.ended: float | None = None
        self.ok: bool | None = None           # None enquanto corre
        self.summary = ""
        self.handled = False
        self._cancelled = False
        self.job = Job(fn)

    # ------------------------------------------------------------- estado

    @property
    def running(self) -> bool:
        return not self.job.done or not self.handled

    @property
    def cancelled(self) -> bool:
        return self._cancelled or bool(self.log is not None
                                       and getattr(self.log, "cancelled", False))

    @property
    def cancellable(self) -> bool:
        return self.cancel_fn is not None or hasattr(self.log, "cancel")

    def cancel(self) -> None:
        self._cancelled = True
        if self.log is not None and hasattr(self.log, "cancel"):
            self.log.cancel()
        if self.cancel_fn is not None:
            try:
                self.cancel_fn()
            except Exception:
                pass

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

    def state_text(self) -> str:
        """«a decorrer há 03:12», «concluída em 00:01»… (no título de cada tarefa na janela)."""
        st = self.state()
        c = clock(self.elapsed())
        if st == "run":
            return tr("a parar…", "stopping…") if self.cancelled else \
                tr("a decorrer há {c}", "running for {c}", c=c)
        return {"stop": tr("parada ao fim de {c}", "stopped after {c}", c=c),
                "ok": tr("concluída em {c}", "done in {c}", c=c)}.get(
            st, tr("falhou ao fim de {c}", "failed after {c}", c=c))

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
        self.save_report(app)

    def save_report(self, app) -> None:
        """O relatório .txt em data/out/sincronizacoes (ronda 37): o que se passou, passo a
        passo, para se saber o que aconteceu mesmo horas depois. Se falhou, a mensagem diz
        onde ficou."""
        self.report_path = None
        if self.log is None or not hasattr(self.log, "transcript"):
            return
        try:
            from perennia.core import garmin_sync as gs
            rep = self.job.result[2] if isinstance(self.job.result, tuple) and \
                len(self.job.result) == 3 and isinstance(self.job.result[2], dict) else None
            self.report_path = gs.save_report(self.log, bool(self.ok), self.summary or
                                              (self.job.error or ""), rep, self.title,
                                              getattr(app, "data_dir", None))
        except Exception:
            self.report_path = None
        if self.report_path is not None and not self.ok and not self.cancelled:
            try:
                from perennia.core import folders
                shown = folders.shown(self.report_path, app.data_dir)
            except Exception:
                shown = str(self.report_path)
            why = (self.summary or self.job.error or "").strip()
            why = why if len(why) <= 160 else why[:157] + "…"
            app.message(tr("{t}: falhou{w} — o relatório ficou em {p}",
                           "{t}: failed{w} — the report is in {p}", t=self.short,
                           w=f" ({why})" if why else "", p=shown))

    def wait(self, seconds: float) -> bool:
        """Espera que a thread acabe (ao sair da Perennia: o GarminDB foi parado e a pasta
        temporária com a palavra-passe tem de ser apagada). True se acabou."""
        th = getattr(self.job, "thread", None)
        if th is not None:
            th.join(seconds)
        return self.job.done


def run_task(app, kind: str, title: str, work: Callable[[Any, Any], tuple],
             short: str | None = None, then: Callable[[bool, str, Any], None] | None = None,
             open_fn: Callable[[Any], None] | None = None,
             cancel_fn: Callable[[], None] | None = None, own_db: bool = True,
             waits: bool = False):
    """Corre `work(db, log)` em segundo plano. `work` conta os passos no `log` e devolve
    `(ok, texto, relatório)`. No fim, o texto aparece na mensagem e `then(ok, texto,
    relatório)` corre na thread da janela (para o ecrã que estiver aberto se atualizar).
    Devolve a tarefa, ou None se já estava a correr uma do mesmo tipo."""
    from perennia.core import garmin_sync as gs
    log = gs.SyncLog()
    path = getattr(app.db, "path", None)

    def run():
        if own_db and path is not None:
            # a thread tem a sua própria ligação: andar pela Perennia não mistura as escritas
            from perennia.core.db import Database
            wdb = Database(path)
            try:
                return work(wdb, log)
            finally:
                wdb.close()
        return work(app.db, log)

    def finish(app_, task) -> None:
        j = task.job
        if j.error:
            log.end(False, j.error)
            task.ok, task.summary = False, j.error
            app_.message(f"{title}: {j.error}")
            if then is not None:
                then(False, j.error, None)
            return
        ok, text, rep = j.result
        task.ok, task.summary = bool(ok), text or ""
        if task.cancelled and not ok:
            text = text or tr("parada por ti", "stopped by you")
        if text:
            # a mensagem diz de onde veio («HRV4Training: 2 valores em 2 dias»)
            name = short or ""
            app_.message(text if not name or text.startswith(name) else f"{name}: {text}")
        if then is not None:
            then(bool(ok), text or "", rep)
    return app.start_task(kind, title, run, log=log, finish=finish, short=short,
                          open_fn=open_fn, cancel_fn=cancel_fn, waits=waits)


def one_step(log, title: str, fn: Callable[[], tuple], done: str | None = None) -> tuple:
    """Um passo só: «A importar x.csv» → o resultado no pormenor → «Concluído». `fn()` devolve
    `(texto, relatório)`; um erro sobe (e o passo fica como falhado)."""
    log.step(title)
    text, rep = fn()
    log.end(True, text)
    log.step(done or tr("Concluído", "Done"))
    log.end(True)
    return True, text, rep


def log_items(log, busy: bool, title_run: str | None = None,
              title_done: str | None = None, heading: bool = True) -> list[Item]:
    """Os passos (▶ ✓ ✗ –) e as últimas linhas do GarminDB, como linhas de uma lista."""
    if log is None:
        return []
    steps, lines = log.snapshot()
    icon = {"run": "▶", "ok": "✓", "fail": "✗", "skip": "–"}
    rows = []
    if heading:
        rows.append(Item(title_run or tr("— O que está a acontecer —", "— What is happening —")
                         if busy else title_done or tr("— Última sincronização —",
                                                       "— Last sync —"), enabled=False))
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
    """A janela das sincronizações: o que cada uma está a fazer, ao vivo. Fechar não as pára;
    «Parar» pergunta antes; OK tira as que já acabaram."""

    W, H = 860, 600

    def __init__(self, app):
        super().__init__(app)
        self.back_button = None              # Fechar / OK já fecham
        self._seen = None

    @property
    def task(self) -> BackgroundTask | None:
        """A principal (a mais recente a correr, ou a mais recente)."""
        return getattr(self.app, "task", None)

    @property
    def tasks(self) -> list[BackgroundTask]:
        return list(reversed(getattr(self.app, "tasks", [])))     # a mais recente primeiro

    def subtitle_text(self) -> str:
        tasks = self.tasks
        if not tasks:
            return ""
        if len(tasks) == 1:
            t = tasks[0]
            text = t.state_text()
            text = text[:1].upper() + text[1:]
            if t.state() == "run" and not t.cancelled:
                text += tr(" · podes continuar a usar a Perennia",
                           " · you can keep using Perennia")
            elif t.summary and t.state() != "run":
                text += " · " + t.summary
            return text
        run = sum(1 for t in tasks if t.running)
        return tr("{r} a decorrer · {d} acabadas · podes continuar a usar a Perennia",
                  "{r} running · {d} finished · you can keep using Perennia",
                  r=run, d=len(tasks) - run)

    def enter(self) -> None:
        tasks = self.tasks
        a = self.app
        if not tasks:
            self.chrome.set(tr("Sem sincronizações", "No syncs"), "", "")
            self.list.set_items([Item(tr("Fechar", "Close"), action=a.pop, button=True,
                                      primary=True)])
            return
        title = tasks[0].title if len(tasks) == 1 else tr("Sincronizações", "Syncs")
        self.chrome.set(title, self.subtitle_text(), "")
        rows: list[Item] = []
        for t in tasks:
            if len(tasks) > 1:
                rows.append(Item(t.title, value=t.state_text(), header=True))
                rows += log_items(t.log, t.running, heading=False)
            else:
                rows += log_items(t.log, t.running,
                                  title_done=tr("— Como correu —", "— How it went —"))
        running = [t for t in tasks if t.running]
        for t in running:
            if t.cancellable:
                rows.append(Item(tr("Parar", "Stop") if len(running) == 1 else
                                 tr("Parar {s}", "Stop {s}", s=t.short),
                                 action=lambda t=t: self.ask_stop(t), button=True,
                                 danger=True, enabled=not t.cancelled))
        main = tasks[0]
        if main.open_fn is not None:
            rows.append(Item(tr("Ver na Sincronização", "Show in Sync"), action=self.show_sync,
                             button=True))
        if running:
            rows.append(Item(tr("Fechar", "Close"), action=a.pop, button=True,
                             primary=len(running) == len(tasks)))
        if len(running) < len(tasks):
            rows.append(Item("OK", action=self.dismiss, button=True, primary=True))
        self.list.set_items(rows, keep_index=True)
        if not self.list.items[self.list.index].button:
            self.list.index = len(self.list.items) - 1
            self.list._sync()

    def _key(self):
        return tuple((id(t), t.state(), t.cancelled, getattr(t.log, "version", 0),
                      int(t.elapsed())) for t in self.tasks)

    def update(self, dt: float) -> None:
        self.app.poll_task()
        k = self._key()
        if k != self._seen:
            self._seen = k
            self.enter()

    # ------------------------------------------------------------- ações

    def ask_stop(self, t: BackgroundTask | None = None) -> None:
        a = self.app
        t = t or self.task
        if t is None or not t.running:
            return

        def stop() -> None:
            t.cancel()
            a.message(tr("A parar: {t}…", "Stopping: {t}…", t=t.title))
        a.confirm(tr("Parar «{t}»?", "Stop «{t}»?", t=t.short),
                  tr("O GarminDB é interrompido. O que já foi descarregado fica guardado e a "
                     "próxima sincronização continua daí.",
                     "GarminDB is interrupted. What was already downloaded is kept and the next "
                     "sync carries on from there.") if t.kind == "garmindb" else
                  tr("O que já foi feito fica guardado; o resto fica para a próxima vez.",
                     "What was already done is kept; the rest is left for next time."), stop,
                  yes=tr("Sim, parar", "Yes, stop"), no=tr("Não, continuar", "No, keep going"))

    def show_sync(self) -> None:
        a = self.app
        main = self.tasks[0] if self.tasks else None
        a.pop()
        if main is not None and main.open_fn is not None:
            main.open_fn(a)

    def dismiss(self) -> None:
        a = self.app
        a.pop()
        a.clear_finished_tasks()
