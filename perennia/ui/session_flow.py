"""Terminar uma sessão de corrida ou de remo como no ciclismo.

O ciclismo é a base: P pausa, Esc também pausa (e diz como terminar), F10 abre
o diálogo «Terminar a sessão?» — Sim / Não / Terminar sem guardar — e enquanto
pergunta a sessão fica parada. Aqui está o mesmo para os outros desportos: o
diálogo é o `FinishDialog` do HUD do ciclismo e as teclas são as mesmas.
(Enter, S ou Y terminam · Esc ou N voltam · D termina sem guardar.)

O ecrã que usa a mistura dá:
- `_finish()` — grava e mostra o resumo;
- `_discard()` — termina sem gravar;
- `_flow_paused()` / `_flow_set_paused(bool)` — o estado de pausa do motor.
"""
from __future__ import annotations

import time

from pyglet.window import key

from perennia.core.i18n import t, tr
from perennia.gfx.hud import FinishDialog, PauseDialog
from perennia.ui.widgets import Item


def drive_cues(screen, key, kind: str, elapsed: float, remaining: float | None) -> int | None:
    """Alimenta os avisos sonoros (Definições → Configurações sonoras) com o segmento em curso e
    devolve os segundos que se veem (os últimos 5), ou None. O acompanhante nasce com o ecrã, por
    isso as regras que mudares valem na sessão seguinte."""
    tracker = getattr(screen, "_cue_tracker", None)
    if tracker is None:
        tracker = screen._cue_tracker = screen.app.new_cues()
    return tracker.update(key, kind, elapsed, remaining)


def workout_step_cues(screen, w) -> int | None:
    """Corrida e remo: o passo do treino por blocos que está a decorrer (só os de tempo)."""
    s = getattr(w, "step", None) if w is not None else None
    if s is None or s.dur_type != "time":
        return drive_cues(screen, None, "work", 0.0, None)
    kind = "rest" if s.kind == "rest" else "work"
    return drive_cues(screen, ("step", w.idx), kind, w.step_t, s.dur_value - w.step_t)


class FinishFlow:
    finish_dialog: FinishDialog | None = None
    pause_dialog: PauseDialog | None = None
    _resume_on_cancel = False
    _pause_before_finish = False       # o popup «PAUSA» estava aberto quando se pediu para terminar
    _menu_pause = False                # a pausa veio de abrir Dispositivos ou Definições

    # ------------------------------------------------- botões (como no ciclismo)
    #
    # Em baixo, à direita: [−] [+] (a velocidade, as piscinas ou a resistência), Pausa/Retomar
    # e Terminar — os mesmos botões do HUD do ciclismo. Cada ecrã diz o que − e + fazem.

    _btn_sig = None

    def _flow_adjust(self, step: int) -> None:
        """− / +: a velocidade, as piscinas ou a resistência (do ecrã)."""

    def _flow_has_adjust(self) -> bool:
        return True

    def _flow_toggle_pause(self) -> None:
        """Pausa/Retomar (botão, P ou o atalho): a pausa à mão abre o popup «PAUSA»."""
        if self._flow_paused():
            self.resume_session()
        else:
            self.pause_session()

    def session_buttons(self) -> list[Item]:
        paused = self._flow_paused()
        items: list[Item] = []
        if self._flow_has_adjust():
            items += [Item("−", button=True, action=lambda: self._flow_adjust(-1)),
                      Item("+", button=True, action=lambda: self._flow_adjust(1))]
        items += [Item(tr("Retomar", "Resume") if paused else tr("Pausa", "Pause"), button=True,
                       action=self._flow_toggle_pause),
                  Item(tr("Terminar", "Finish"), button=True, danger=True,
                       action=self.ask_finish)]
        return items

    def place_session_buttons(self) -> None:
        """Os botões da sessão ficam **em cima, à direita**, ao lado do relógio (o Terminar a
        vermelho, como no ciclismo). Se a janela for estreita demais para os pôr à direita do
        relógio, descem para a barra de baixo."""
        from perennia.ui.widgets import BUTTON_Y, button_width
        w, h = self.app.window.width, self.app.window.height
        lst = self.list
        labels = [i.label for i in lst.items if i.button]
        total = sum(button_width(x) for x in labels) + 10 * max(0, len(labels) - 1)
        right = w - 36
        clock_right = w / 2 + 115 + 12
        if labels and right - total >= clock_right:
            lst.bar_right, lst.bar_y = right, h - 108
        else:
            lst.bar_right, lst.bar_y = w - 48, BUTTON_Y
        lst._sync_buttons()

    def refresh_buttons(self, force: bool = False) -> None:
        """Põe os botões na lista (escondida); refaz-se só quando muda a pausa."""
        sig = (self._flow_paused(), self.confirming, self._flow_has_adjust())
        if sig == self._btn_sig and not force:
            return
        self._btn_sig = sig
        self.list.set_items(self.session_buttons() if not self.confirming else [],
                            keep_index=False)
        self.place_session_buttons()

    # ---------------------------------------------------------------- pausa

    def _flow_paused(self) -> bool:
        raise NotImplementedError

    def _flow_set_paused(self, paused: bool) -> None:
        raise NotImplementedError

    def _flow_toast(self, text: str) -> None:
        self.toast = text
        self._toast_until = time.monotonic() + 4.0

    # ------------------------------------------------------------- diálogo

    def init_finish(self) -> None:
        self.finish_dialog = FinishDialog()
        self.pause_dialog = PauseDialog()
        self._layout_finish()

    def _layout_finish(self) -> None:
        if self.finish_dialog is not None:
            w = self.app.window
            self.finish_dialog.layout(w.width, w.height)
            if self.pause_dialog is not None:
                self.pause_dialog.layout(w.width, w.height)
            self.place_session_buttons()

    # ----------------------------------------------------- o popup «PAUSA»

    @property
    def pause_popup(self) -> bool:
        return self.pause_dialog is not None and self.pause_dialog.visible

    def _flow_can_pause(self) -> bool:
        """A sessão já começou (antes disso não há o que pausar)?"""
        return True

    def pause_session(self) -> None:
        """Pausa à mão: o motor pára e abre-se o popup, ao centro, com **Retomar sessão** e
        **Terminar treino**."""
        if self.confirming or self.counting or not self._flow_can_pause():
            return
        if not self._flow_paused():
            self._flow_set_paused(True)
        if self._flow_paused() and self.pause_dialog is not None:
            self.pause_dialog.show()

    def resume_session(self) -> None:
        if self.pause_dialog is not None:
            self.pause_dialog.hide()
        self._menu_pause = False
        if self._flow_paused():
            self._flow_set_paused(False)

    def pause_for_menu(self) -> None:
        """Dispositivos e Definições abrem por cima da sessão: ela fica em pausa e, quando o
        menu fecha, aparece o popup «PAUSA» (a sessão não retoma sozinha)."""
        if self.confirming or self.counting or not self._flow_can_pause():
            return
        if not self._flow_paused():
            self._flow_set_paused(True)
        if self._flow_paused():
            self._menu_pause = True
            if self.pause_dialog is not None:
                self.pause_dialog.hide()

    def on_modal_closed(self) -> None:
        """O menu que estava por cima da sessão fechou."""
        if self._menu_pause:
            self._menu_pause = False
            if self._flow_paused() and not self.confirming and self.pause_dialog is not None:
                self.pause_dialog.show()

    @property
    def confirming(self) -> bool:
        return self.finish_dialog is not None and self.finish_dialog.visible

    def ask_finish(self) -> None:
        """Terminar pergunta primeiro. Enquanto pergunta, a sessão fica parada."""
        if self.finish_dialog is None or self.confirming:
            return
        self._pause_before_finish = self.pause_popup or self._menu_pause
        if self.pause_dialog is not None:
            self.pause_dialog.hide()
        self._menu_pause = False
        self._resume_on_cancel = not self._flow_paused()
        if self._resume_on_cancel:
            self._flow_set_paused(True)
        self.finish_dialog.show()

    def plan_complete(self) -> None:
        """O último bloco acabou: o tempo pára de imediato e abre-se, sozinho, o diálogo de
        terminar (como se tivesses carregado em «Terminar»)."""
        if not self.confirming:
            self.ask_finish()

    def cancel_finish(self) -> None:
        """«Não»: volta à sessão (retoma, se foi o diálogo que a parou)."""
        if self.finish_dialog is not None:
            self.finish_dialog.hide()
        if self._pause_before_finish:
            # estava no popup «PAUSA»: volta a ele (a sessão continua parada)
            self._pause_before_finish = False
            self._resume_on_cancel = False
            if self._flow_paused() and self.pause_dialog is not None:
                self.pause_dialog.show()
            return
        if self._resume_on_cancel and self._flow_paused():
            self._flow_set_paused(False)
        self._resume_on_cancel = False

    def go_back(self) -> None:
        self.ask_finish()

    # ------------------------------------------------- etiquetas do .fit

    def _tag_context(self):
        """(desporto, treino, segue uma rota?, resumo ao vivo) — None se não há nada
        a gravar. Cada ecrã diz o seu."""
        return None

    def finish_with_tags(self) -> None:
        """«Sim, terminar»: antes de gravar, a janela das etiquetas do .fit."""
        ctx = self._tag_context()
        if ctx is None:
            self._finish()
            return
        sport, wid, has_route, summ = ctx
        from perennia.ui.tag_popup import open_session_tags
        open_session_tags(self, sport, workout_id=wid, has_route=has_route, summary=summ,
                          on_done=self._tags_done, on_back=self.cancel_finish)

    def _tags_done(self, info: dict) -> None:
        self.engine.tags_chosen = info
        self._finish()

    # --------------------------------------------------------------- teclas

    def finish_key(self, symbol: int) -> bool | None:
        """Teclas do diálogo e Esc/F10 da sessão. `None`: não é com o fluxo."""
        if self.confirming:
            if symbol in (key.ENTER, key.RETURN, key.S, key.Y):
                self.finish_dialog.hide()
                self.finish_with_tags()
            elif symbol in (key.ESCAPE, key.N):
                self.cancel_finish()
            elif symbol == key.D:
                self.finish_dialog.hide()
                self._discard()
            return True
        if self.pause_popup:
            # o popup «PAUSA»: P, Esc, Enter ou Espaço retomam · F10 ou D perguntam se termina
            if symbol in (key.P, key.ESCAPE, key.ENTER, key.RETURN, key.SPACE):
                self.resume_session()
            elif symbol in (key.F10, key.D):
                self.ask_finish()
            return True
        if symbol == key.F10:
            self.ask_finish()
            return True
        if symbol == key.ESCAPE:
            # Esc não termina: pausa e abre o popup «PAUSA» (Retomar ou Terminar)
            self.pause_session()
            return True
        return None

    def finish_mouse(self, x: int, y: int) -> bool | None:
        if self.pause_popup and not self.confirming:
            choice = self.pause_dialog.hit(x, y)
            if choice == "resume":
                self.resume_session()
            elif choice == "finish":
                self.ask_finish()
            return True                    # com o popup aberto, nada passa para baixo
        if self.confirming:
            choice = self.finish_dialog.hit(x, y)
            if choice == "yes":
                self.finish_dialog.hide()
                self.finish_with_tags()
            elif choice == "no":
                self.cancel_finish()
            elif choice == "discard":
                self.finish_dialog.hide()
                self._discard()
            return True
        if self.back_button is not None and self.back_button.hit(x, y):
            self.ask_finish()
            return True
        return None

    def draw_finish(self) -> None:
        if self.pause_dialog is not None:
            self.pause_dialog.draw()
        if self.finish_dialog is not None:
            self.finish_dialog.draw()
