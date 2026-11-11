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
        from perennia.ui.widgets import Chart, StackedBars
        self.ARR_SPORT = sport
        self.arrangement = sl.load(self.app.db, sport)
        self.live_chart = Chart(OFF, OFF, 10, 10)
        self.zone_bars = StackedBars()
        self._series: dict[str, list[float]] = {"a": [], "b": []}
        self._chart_due = 0.0

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

    # séries: (nome, cor) de cada uma, por desporto
    def arr_series_names(self) -> tuple[tuple[str, tuple], tuple[str, tuple]]:
        if self.ARR_SPORT == "rowing":
            return ((tr("Potência (W)", "Power (W)"), (108, 170, 220)),
                    (tr("Voga (spm)", "Rate (spm)"), (120, 200, 150)))
        return ((tr("FC (bpm)", "HR (bpm)"), (214, 54, 128)),
                (tr("Velocidade (km/h)", "Speed (km/h)"), (108, 170, 220)))

    def arr_sample(self, dt: float, a: float | None, b: float | None, zone_s=None) -> None:
        """Junta uma amostra (a cada segundo) e refaz os gráficos de 2 em 2 s."""
        self._chart_due += dt
        if self._chart_due < 1.0:
            return
        self._chart_due = 0.0
        self._series["a"].append(float(a or 0))
        self._series["b"].append(float(b or 0))
        for k in self._series:
            if len(self._series[k]) > 3600:
                del self._series[k][:600]
        if len(self._series["a"]) % 2:
            return
        if self.arr_rect("chart") is not None:
            from perennia.ui.ride_report_screens import downsample
            (na, ca), (nb, cb) = self.arr_series_names()
            series = [(na, downsample(self._series["a"], 90), ca),
                      (nb, downsample(self._series["b"], 90), cb)]
            series = [s for s in series if any(s[1])]
            n = len(series[0][1]) if series else 0
            from perennia.core.units import hms
            secs = len(self._series["a"])
            labels = [hms(secs * i / max(1, n - 1)) for i in range(n)]
            self.live_chart.show_lines(tr("Ao vivo", "Live"), series, labels,
                                       tr("À espera dos dados…", "Waiting for data…"),
                                       fmt=lambda v: f"{v:.0f}")
        if self.arr_rect("zones") is not None and zone_s:
            from perennia.gfx.hud import zone_color
            total = sum(zone_s) or 1.0
            self.zone_bars.set_rows([{
                "title": tr("Tempo em cada zona de FC", "Time in each HR zone"), "note": "",
                "parts": [(v / total, zone_color(i + 1, "hr"), f"Z{i + 1}")
                          for i, v in enumerate(zone_s) if v]}])

    def arr_draw(self) -> None:
        if self.arr_rect("chart") is not None:
            self.live_chart.draw()
        if self.arr_rect("zones") is not None and self.zone_bars.visible:
            self.zone_bars.draw()
