"""O radar do que uma sessão treinou e o seu efeito no índice de longevidade, ao lado do
resto das páginas de resumo e da análise de cada sessão (todos os desportos)."""
from __future__ import annotations

from velo.core import longevity as lg
from velo.core.i18n import tr
from velo.ui.radar import RadarChart
from velo.ui.widgets import Item


class RadarSide:
    """O radar do que uma sessão treinou, ao lado do resto, e o seu efeito no índice de
    longevidade. Para as páginas de resumo e a análise de cada sessão (todos os desportos).
    Usa-se à esquerda do `Screen`; `radar_attach(desporto, id)` devolve as linhas a juntar."""

    RADAR_BIG = False            # grande, a meio-direita (a análise); senão, na coluna da direita
    radar_visible = True
    _radar: RadarChart | None = None
    _radar_rows: list | None = None

    def _radar_on(self) -> bool:
        return self._radar is not None and self.radar_visible

    def _relayout_list(self) -> None:
        """A lista muda de largura quando o radar aparece ou desaparece."""
        w, h = self.app.window.width, self.app.window.height
        super().on_resize(w, h)           # só a base (Screen): não volta a pedir o conteúdo

    def _list_width(self, w: int) -> int:
        if self._radar_on() and not self.HAS_BOARD:
            return w - 96 - int(w * 0.45)
        return super()._list_width(w)

    def radar_attach(self, sport: str, sid: str | None) -> list[Item]:
        if not sid:
            return []
        if self._radar_rows is not None:
            return list(self._radar_rows)
        db = self.app.db
        imp = lg.session_impact(db, sport, str(sid))
        mins = imp.get("mins") or {}
        if self._radar is None:
            self._radar = RadarChart()
        share = lg.shares(mins)
        self._radar.caption.text = tr("O que treinou", "What it trained")
        self._radar.set([(lg.axis_label(a), share.get(a, 0.0), f"{share.get(a, 0.0):.0f} %")
                         for a in lg.AXES],
                        empty=tr("Sem tempo em zonas", "No time in zones"))
        rows: list[Item] = []
        if mins:
            d = imp.get("deltas") or {}
            rows.append(Item(tr("Longevidade", "Longevity"),
                             value=lg.fmt_delta(d.get("1m", 0.0)),
                             detail=lg.impact_text(imp), enabled=False))
        self._radar_rows = rows
        self._relayout_list()
        self._radar_layout()
        return list(rows)

    def _radar_layout(self) -> None:
        if self._radar is None:
            return
        from velo.ui.app import BOARD_W
        w, h = self.app.window.width, self.app.window.height
        if self.RADAR_BIG or not self.HAS_BOARD:      # sem classificação, o radar é grande
            x0, x1 = w * 0.55, w - 60
            r = min((x1 - x0) / 2 - 90, (h - 330) / 2)
            self._radar.layout((x0 + x1) / 2, h / 2 - 30, r)
        else:
            self._radar.layout(w - 48 - BOARD_W / 2, 230, 100)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._radar_layout()

    def draw(self) -> None:
        super().draw()
        if self._radar_on():
            self._radar.draw()
