"""O menu Longevidade: o índice por período (1 dia … 20 anos) com a tendência, o
radar de onde o corpo tem estado concentrado, e os testes de longevidade (que
saíram da Saúde). A fórmula está em `velo.core.longevity`."""
from __future__ import annotations

import time

from velo.core import longevity as lg
from velo.core.i18n import tr
from velo.ui.app import Screen
from velo.ui.radar import RadarChart
from velo.ui.widgets import Item


class LongevityMenu(Screen):
    TABBED = True
    TAB_KEYS = ("index", "tests")
    AGENT = False

    @staticmethod
    def TITLE() -> str:
        return tr("Longevidade", "Longevity")

    def __init__(self, app, tab: int = 0):
        super().__init__(app)
        self.inner = None
        self.tab = tab
        self.radar = RadarChart()
        self._result: dict | None = None
        self._result_at = 0.0
        self._shown: str | None = None
        if self.tabs is not None:
            self.tabs.select(tab)
        self._layout_radar()

    def tab_labels(self) -> list[str]:
        return [tr("Índice", "Index"), tr("Testes de longevidade", "Longevity tests")]

    def on_tab(self) -> None:
        self.inner = None
        self._shown = None

    def _list_width(self, w: int) -> int:
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "index":
            return int(w * 0.40)
        return super()._list_width(w)

    # ------------------------------------------------------------ índice

    def result(self, fresh: bool = False) -> dict:
        if self._result is None or fresh or time.monotonic() - self._result_at > 30:
            self._result = lg.compute(self.app.db)
            self._result_at = time.monotonic()
        return self._result

    def enter(self) -> None:
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "tests":
            from velo.ui import health_screens as hs
            if not isinstance(self.inner, hs.TestsMenu):
                inner = hs.TestsMenu(self.app, "longevity")
                inner.list = self.list
                inner.chrome = hs._ChromeProxy(self)
                inner.back_button = None
                self.inner = inner
            self.inner.enter()
            return
        self.inner = None
        res = self.result(fresh=True)
        rows = []
        keys = [k for k, _d in lg.PERIODS]
        for key, idx, delta in lg.trend(res):
            nxt = keys[keys.index(key) + 1] if keys.index(key) + 1 < len(keys) else None
            if delta is None:
                detail = tr("todo o histórico", "all the history")
            else:
                arrow = "↑" if delta > 0.5 else "↓" if delta < -0.5 else "="
                detail = tr("{a} {d:+.1f} face a {p}", "{a} {d:+.1f} vs {p}", a=arrow, d=delta,
                            p=lg.period_label(nxt))
            rows.append(Item(lg.period_label(key), value=f"{idx:.0f}", detail=detail,
                             data=("period", key)))
        self.chrome.set(self.TITLE(),
                        tr("O índice (0–100) de cada período · o radar mostra onde o corpo tem "
                           "estado mais ou menos concentrado",
                           "The index (0–100) of each period · the radar shows where the body "
                           "has been more or less focused"),
                        tr("↑↓ período · o radar acompanha · cada treino, hábito e teste conta",
                           "↑↓ period · the radar follows · every workout, habit and test counts"))
        self.list.set_items(rows, keep_index=True)
        if rows and self.list.index < 0:
            self.list.select_data(("period", "3m"))
        self._shown = None
        self._layout_radar()

    def _selected_period(self) -> str:
        it = self.list.selected
        if it is not None and isinstance(it.data, tuple) and it.data[0] == "period":
            return it.data[1]
        return "3m"

    def _sync_radar(self) -> None:
        key = self._selected_period()
        if key == self._shown:
            return
        self._shown = key
        axes = self.result()[key]["axes"]
        self.radar.set([(lg.axis_label(a), axes[a], f"{axes[a]:.0f}") for a in lg.AXES],
                       empty=tr("Sem dados", "No data"))

    # -------------------------------------------------------------- ecrã

    def _layout_radar(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        x0 = 48 + self._list_width(w) + 60
        x1 = w - 60
        cx = (x0 + x1) / 2
        r = min((x1 - x0) / 2 - 90, (h - 330) / 2)
        self.radar.layout(cx, h / 2 - 30, r)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout_radar()

    def draw(self) -> None:
        super().draw()
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "index":
            self._sync_radar()
            self.radar.draw()

