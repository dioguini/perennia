"""Os painéis das sessões de corrida, natação e remo, no sítio que a
disposição escolheu (perennia.core.screen_layout): os quadrados de métricas, o
estado e o plano, as voltas, a classificação, e — se os puseres no ecrã — o
gráfico ao vivo e o tempo em cada zona de FC."""
from __future__ import annotations

from perennia.core import screen_layout as sl
from perennia.core.i18n import tr

OFF = -20000           # onde fica um painel que não está no ecrã


class ArrangedPanels:
    """Mistura para os ecrãs de sessão. Quem a usa chama `arr_load()` ao
    construir, `arr_rect(painel)` no `_layout`, `arr_sample(...)` a cada
    segundo e `arr_draw()` no fim do `draw`."""

    ARR_SPORT = "running"

    def arr_load(self, sport: str) -> None:
        from perennia.core import live_chart as lc
        from perennia.core import options as opt_mod
        from perennia.ui.widgets import Chart, StackedBars
        self.ARR_SPORT = sport
        self.arrangement = sl.load(self.app.db, sport)
        self.live_chart = Chart(OFF, OFF, 10, 10)
        self.zone_bars = StackedBars()
        # o gráfico ao vivo: as métricas escolhidas (Definições → Ecrã da sessão → Gráfico ao
        # vivo) e as voltas marcadas (ver core/live_chart.py)
        self.live = lc.LiveSeries(sport, lc.choice(self.app.db, sport)
                                  if sport in lc.CATALOG else [],
                                  int(opt_mod.get(self.app.db, "live_chart_points")))
        self._chart_due = 0.0

    def arr_lap_mark(self) -> None:
        """Uma volta marcada: o gráfico ao vivo põe aqui um traço ao alto."""
        self.live.mark()

    def arr_area(self) -> tuple[float, float, float, float]:
        w, h = self.app.window.width, self.app.window.height
        top, bottom = h - 128, 66
        return 48.0, float(bottom), float(w - 96), float(top - bottom)

    def arr_rect(self, panel: str):
        """(x, y_baixo, largura, altura) em píxeis, ou None se não está no ecrã."""
        r = (getattr(self, "arrangement", None) or {}).get(panel)
        return sl.to_px(r, self.arr_area()) if r else None

    def arr_layout_extras(self) -> None:
        from perennia.ui.widgets import Chart
        c = self.arr_rect("chart")
        if c is not None:
            x, y, w, h = c
            self.live_chart = Chart(int(x + 40), int(y + 22), int(w - 56), int(h - 50))
        z = self.arr_rect("zones")
        if z is not None:
            x, y, w, h = z
            self.zone_bars.layout(x, y + h, w, max(40.0, min(64.0, h)))

    def arr_sample(self, dt: float, src, zone_s=None) -> None:
        """Junta uma amostra (a cada segundo) das métricas escolhidas e refaz os gráficos de 2
        em 2 s. `src`: o motor da sessão (ver `live_chart.sample`)."""
        self._chart_due += dt
        if self._chart_due < 1.0:
            return
        self._chart_due = 0.0
        from perennia.core import live_chart as lc
        if self.ARR_SPORT in lc.CATALOG:
            self.live.add(lc.sample(self.ARR_SPORT, src))
        if self.live.total % 2:
            return
        if self.arr_rect("chart") is not None:
            self._draw_chart()
        if self.arr_rect("zones") is not None and zone_s:
            from perennia.gfx.hud import zone_color
            total = sum(zone_s) or 1.0
            self.zone_bars.set_rows([{
                "title": tr("Tempo em cada zona de FC", "Time in each HR zone"), "note": "",
                "parts": [(v / total, zone_color(i + 1, "hr"), f"Z{i + 1}")
                          for i, v in enumerate(zone_s) if v]}])

    def _draw_chart(self) -> None:
        from perennia.core.units import hms
        series, marks, total = self.live.plot()
        n = len(series[0][1]) if series else 0
        labels = [hms(total * i / max(1, n - 1)) for i in range(n)]
        self.live_chart.show_lines(tr("Ao vivo", "Live"), series, labels,
                                   tr("À espera dos dados…", "Waiting for data…"),
                                   fmt=lambda v: "", markers=marks)

    def arr_draw(self) -> None:
        if self.arr_rect("chart") is not None:
            self.live_chart.draw()
        if self.arr_rect("zones") is not None and self.zone_bars.visible:
            self.zone_bars.draw()
