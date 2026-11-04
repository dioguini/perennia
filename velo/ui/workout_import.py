"""Carregar um treino do computador (todos os desportos menos o ginásio).

Mostra os ficheiros de treino encontrados (.zwo, .mrc, .erg, .fit) e, ao
escolher um, pergunta **«Guardar na lista de treinos?»** — para a lista não
ir enchendo com treinos que só se querem fazer uma vez:

* *Guardar na lista* — fica na lista de treinos (estado `active`);
* *Só para esta sessão* — não aparece na lista (estado `session`).

Em ambos os casos a sessão guarda a sua própria cópia do treino (ver
`velo.core.session_workouts`). Se o mesmo treino já estiver na lista, usa-se
esse (sem duplicar). A natação não tem sessão na Perennia: o treino vai
direto para a lista.
"""
from __future__ import annotations

from velo.core import sports as sp
from velo.core import workout_files as wf
from velo.core.i18n import tr
from velo.ui.app import ConfirmScreen, PopupMixin, Screen
from velo.ui.widgets import Item

SESSION_SPORTS = ("cycling", "rowing", "running")


def open_session(app, sport: str, wid: str) -> None:
    from velo.ui.session_setup import SessionSetup
    app.push(SessionSetup(app, sport, kind="workout", workout_id=wid))


class WorkoutFilePopup(PopupMixin, Screen):
    """Os ficheiros de treino do computador. `mode`: «session» (a seguir abre
    a preparação da sessão) ou «list» (veio da lista de treinos)."""

    W, H = 820, 560

    def __init__(self, app, sport: str, mode: str = "session", on_done=None,
                 folders: list[str] | None = None):
        super().__init__(app)
        self.sport = sport
        self.mode = mode if sport in SESSION_SPORTS else "list"
        self.on_done = on_done
        self.folders = folders
        self.files = []
        self._init_popup()

    def enter(self) -> None:
        self.files = wf.scan(self.sport, self.folders)
        exts = " ".join(wf.EXTS.get(self.sport, ()))
        items = [Item(p.name, value=p.suffix.lower(), detail=str(p.parent),
                      action=lambda q=p: self.pick(q)) for p in self.files]
        if not items:
            items = [Item(tr("Nenhum treino encontrado", "No workout found"),
                          detail=tr("Põe ficheiros {e} na pasta «workouts» ao lado da "
                                    "aplicação, em Transferências ou em Documentos.",
                                    "Put {e} files in the «workouts» folder next to the app, "
                                    "in Downloads or in Documents.", e=exts), enabled=False)]
        self.chrome.set(tr("Carregar treino do computador", "Load a workout from the computer")
                        + f" · {sp.name(self.sport)}",
                        (tr("1 ficheiro", "1 file") if len(self.files) == 1 else
                         tr("{n} ficheiros", "{n} files", n=len(self.files)))
                        + tr(" ({e}) · Enter escolhe · Esc volta",
                             " ({e}) · Enter picks · Esc goes back", e=exts), "")
        self.list.set_items(items, keep_index=True)

    # ------------------------------------------------------------ escolher

    def pick(self, path) -> None:
        a = self.app
        ftp, thr = wf.context(a.db, self.sport)
        try:
            loaded = wf.read(path, self.sport, ftp, thr)
        except Exception as e:
            a.message(tr("Não consegui ler {f}: {e}", "Could not read {f}: {e}",
                         f=path.name, e=e))
            return
        same = wf.same_in_list(a.db, self.sport, loaded)
        if same:
            a.message(tr("«{n}» já está na lista de treinos: uso esse (sem duplicar)",
                         "«{n}» is already in the workout list: using it (no duplicate)",
                         n=loaded.name))
            self._finish(same, kept=True)
            return
        if self.sport not in SESSION_SPORTS:
            self._save(loaded, keep=True)
            return
        if self.mode == "list":
            options = [(tr("Cancelar", "Cancel"), a.pop),
                       (tr("Usar já, só nesta sessão", "Use now, just this session"),
                        lambda: self._save(loaded, keep=False)),
                       (tr("Guardar na lista", "Keep in the list"),
                        lambda: self._save(loaded, keep=True))]
        else:
            options = [(tr("Cancelar", "Cancel"), a.pop),
                       (tr("Só para esta sessão", "Just this session"),
                        lambda: self._save(loaded, keep=False)),
                       (tr("Guardar na lista", "Keep in the list"),
                        lambda: self._save(loaded, keep=True))]
        n = len(loaded.steps)
        a.push(ConfirmScreen(
            a, tr("Guardar «{n}» na lista de treinos?", "Keep «{n}» in the workout list?",
                  n=loaded.name),
            (tr("1 passo", "1 step") if n == 1 else tr("{k} passos", "{k} steps", k=n))
            + tr(" · {f}. Se não o guardares, não aparece na lista — mas a sessão "
                 "guarda sempre a sua cópia do treino.",
                 " · {f}. If you don't keep it, it won't show in the list — but the "
                 "session always keeps its own copy of the workout.", f=path.name),
            options, default=2, buttons=True, cancel=a.pop))

    def _save(self, loaded, keep: bool) -> None:
        a = self.app
        if isinstance(a.current, ConfirmScreen):
            a.pop()
        wid = wf.save(a.db, self.sport, loaded, keep=keep)
        a.message(tr("«{n}» guardado na lista de treinos", "«{n}» kept in the workout list",
                     n=loaded.name) if keep else
                  tr("«{n}» carregado só para esta sessão", "«{n}» loaded just for this session",
                     n=loaded.name))
        self._finish(wid, kept=keep)

    def _finish(self, wid: str, kept: bool) -> None:
        a = self.app
        if a.current is self:
            a.pop()
        if self.on_done is not None:
            self.on_done(wid)
        # da lista de treinos, guardar só acrescenta à lista; o resto abre a sessão
        if self.sport in SESSION_SPORTS and not (self.mode == "list" and kept):
            open_session(a, self.sport, wid)


def import_item(app, sport: str, on_done=None) -> Item:
    """O botão «+ Carregar do computador» (em cima, à direita) das listas de treinos."""
    return Item(tr("+ Carregar do computador", "+ Load from the computer"), top=True,
                detail=tr(".zwo, .fit… pergunta se fica na lista",
                          ".zwo, .fit… asks whether to keep it in the list"),
                action=lambda: app.push(WorkoutFilePopup(app, sport, mode="list",
                                                         on_done=on_done)))
