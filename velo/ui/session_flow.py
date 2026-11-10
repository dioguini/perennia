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

from velo.core.i18n import t, tr
from velo.gfx.hud import FinishDialog
from velo.ui.widgets import Item


class FinishFlow:
    finish_dialog: FinishDialog | None = None
    _resume_on_cancel = False

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
        self._flow_set_paused(not self._flow_paused())

    def session_buttons(self) -> list[Item]:
        paused = self._flow_paused()
        items: list[Item] = []
        if self._flow_has_adjust():
            items += [Item("−", button=True, action=lambda: self._flow_adjust(-1)),
                      Item("+", button=True, action=lambda: self._flow_adjust(1))]
        items += [Item(tr("Retomar", "Resume") if paused else tr("Pausa", "Pause"), button=True,
                       action=self._flow_toggle_pause),
                  Item(tr("Terminar", "Finish"), button=True, primary=True,
                       action=self.ask_finish)]
        return items

    def refresh_buttons(self, force: bool = False) -> None:
        """Põe os botões na lista (escondida); refaz-se só quando muda a pausa."""
        sig = (self._flow_paused(), self.confirming, self._flow_has_adjust())
        if sig == self._btn_sig and not force:
            return
        self._btn_sig = sig
        self.list.set_items(self.session_buttons() if not self.confirming else [],
                            keep_index=False)

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
        self._layout_finish()

    def _layout_finish(self) -> None:
        if self.finish_dialog is not None:
            w = self.app.window
            self.finish_dialog.layout(w.width, w.height)

    @property
    def confirming(self) -> bool:
        return self.finish_dialog is not None and self.finish_dialog.visible

    def ask_finish(self) -> None:
        """Terminar pergunta primeiro. Enquanto pergunta, a sessão fica parada."""
        if self.finish_dialog is None or self.confirming:
            return
        self._resume_on_cancel = not self._flow_paused()
        if self._resume_on_cancel:
            self._flow_set_paused(True)
        self.finish_dialog.show()

    def cancel_finish(self) -> None:
        """«Não»: volta à sessão (retoma, se foi o diálogo que a parou)."""
        if self.finish_dialog is not None:
            self.finish_dialog.hide()
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
        from velo.ui.tag_popup import open_session_tags
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
        if symbol == key.F10:
            self.ask_finish()
            return True
        if symbol == key.ESCAPE:
            # Esc não termina: pausa e mostra como terminar (como no ciclismo)
            if not self._flow_paused():
                self._flow_set_paused(True)
            self._flow_toast(t("ride.paused_hint"))
            return True
        return None

    def finish_mouse(self, x: int, y: int) -> bool | None:
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
        if self.finish_dialog is not None:
            self.finish_dialog.draw()
