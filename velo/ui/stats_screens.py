"""Estatísticas por desporto: gráficos por separadores e a escolha do desporto.

Ciclismo, ginásio e «todos» usam os ecrãs que já existiam (agora com os
gráficos em separadores); remo, corrida e natação usam `SportStatsScreen`.
"""
from __future__ import annotations

import json
from datetime import date

from velo.core import stats
from velo.core import sports as sp
from velo.core.i18n import t, tr
from velo.core.units import hms
from velo.ui.sport_screens import EditScreen
from velo.ui.widgets import Chart, Item


def for_sport(app, sport: str | None):
    from velo.ui import app as app_mod
    from velo.ui import sport_screens as ss
    if sport is None:
        return ss.GeneralStatsScreen(app)
    if sport == "cycling":
        return app_mod.StatsScreen(app)
    if sport == "gym":
        return ss.StrengthStatsScreen(app)
    return SportStatsScreen(app, sport)


class SportStatsScreen(EditScreen):
    """Remo, corrida e natação: volume, tempo, carga, ritmo e zonas de FC."""

    TABBED = True
    VIEWS = ("distance", "time", "load", "pace", "hr_zones")
    GROUPINGS = ("week", "month")

    def __init__(self, app, sport: str):
        self.sport = sport
        super().__init__(app)
        self.grouping = "week"
        w, h = app.window.width, app.window.height
        top = self.content_top(h) - 2 * 38 - 60
        self.chart = Chart(96, 112, w - 144, max(120, top - 112))
        self._series: list = []

    def tab_labels(self) -> list[str]:
        return [tr("Distância", "Distance"), tr("Tempo", "Time"), tr("Carga", "Load"),
                tr("Ritmo médio", "Avg pace"), tr("Zonas de FC", "HR zones")]

    def rows(self) -> list[tuple]:
        return stats.sport_rows(self.app.db, self.sport)

    def enter(self) -> None:
        rows = self.rows()
        dist = sum(r["distance_m"] or 0 for _, r in rows)
        hours = sum((r["moving_s"] or r["elapsed_s"] or 0) for _, r in rows) / 3600
        self.list.set_items([
            Item(tr("Desporto", "Sport"), value=sp.name(self.sport), data="cyc:sport",
                 detail=tr("←/→ outro desporto · Tab outro gráfico",
                           "←/→ another sport · Tab another chart")),
            Item(tr("Agrupar por", "Group by"),
                 value=tr("semana", "week") if self.grouping == "week" else tr("mês", "month"),
                 data="cyc:grouping")], keep_index=True)
        self.list.set_visible_rows(2)
        self.chrome.set(t("menu.statistics") + f" · {sp.name(self.sport)}",
                        tr("{n} sessões · {d:.1f} km · {h:.1f} h", "{n} sessions · {d:.1f} km · "
                           "{h:.1f} h", n=len(rows), d=dist / 1000, h=hours),
                        tr("Tab gráfico · ←/→ mudar · Esc voltar",
                           "Tab chart · ←/→ change · Esc back"))
        self._draw_chart(rows)

    def _buckets(self, rows, value) -> list[tuple[str, float]]:
        acc: dict = {}
        cnt: dict = {}
        for day, r in rows:
            v = value(r)
            if v is None:
                continue
            k = stats.bucket_of(day, self.grouping)
            acc[k] = acc.get(k, 0.0) + v
            cnt[k] = cnt.get(k, 0) + 1
        keys = [stats.bucket_of(date.today(), self.grouping)]
        while len(keys) < 12:
            keys.append(stats._previous(keys[-1], self.grouping))
        keys.reverse()
        return [(stats.bucket_label(k, self.grouping), acc.get(k, 0.0), cnt.get(k, 0))
                for k in keys]

    def _draw_chart(self, rows) -> None:
        view = self.VIEWS[self.tab % len(self.VIEWS)]
        empty = tr("Ainda sem sessões.", "No sessions yet.")
        if view == "hr_zones":
            series = stats.zones_series(self.app.db, "hr", self.grouping, 12, (self.sport,))
            totals = [sum(z[i] for _, z in series) / 60 for i in range(len(series[0][1]))] \
                if series else []
            self._series = list(zip([f"Z{i + 1}" for i in range(len(totals))], totals))
            from velo.gfx.hud import zone_color
            # as cores das zonas são as do construtor de treinos, em todo o lado
            self.chart.show_bars(tr("Minutos por zona de FC", "Minutes per HR zone"), totals,
                                 [f"Z{i + 1}" for i in range(len(totals))], empty,
                                 fmt=lambda v: f"{v:.0f}",
                                 colors=[zone_color(i + 1, "hr") for i in range(len(totals))])
            return
        if view == "pace":
            unit = {"rowing": 500.0, "running": 1000.0, "swimming": 100.0}[self.sport]

            def val(r):
                d, s = r["distance_m"] or 0, r["moving_s"] or r["elapsed_s"] or 0
                return s / d * unit if d > 50 else None
            b = self._buckets(rows, val)
            data = [(lab, v / c if c else 0.0) for lab, v, c in b]
            self._series = data
            self.chart.show_bars(tr("Ritmo médio", "Avg pace"), [v for _, v in data],
                                 [lab for lab, _ in data], empty,
                                 fmt=lambda v: hms(v) if v else "—")
            return
        fn = {"distance": lambda r: (r["distance_m"] or 0) / 1000,
              "time": lambda r: (r["moving_s"] or r["elapsed_s"] or 0) / 3600,
              "load": lambda r: r["load"] or 0}[view]
        b = self._buckets(rows, fn)
        self._series = [(lab, v) for lab, v, _ in b]
        title = {"distance": tr("Distância (km)", "Distance (km)"),
                 "time": tr("Horas", "Hours"), "load": tr("Carga", "Load")}[view]
        self.chart.show_bars(title, [v for _, v, _ in b], [lab for lab, _, _ in b], empty,
                             fmt=lambda v: f"{v:.1f}")

    def cycle(self, field: str, step: int) -> None:
        if field == "grouping":
            self.grouping = "month" if self.grouping == "week" else "week"
        elif field == "sport":
            order = [None, "cycling", "rowing", "running", "swimming", "gym"]
            i = order.index(self.sport)
            self.app.replace(for_sport(self.app, order[(i + step) % len(order)]))

    def refresh(self) -> None:
        if self.app.current is self:
            self.enter()

    def agent_data(self) -> dict:
        return {"desporto": self.sport, "grafico": self.VIEWS[self.tab % len(self.VIEWS)],
                "serie": self._series}

    def draw(self) -> None:
        super().draw()
        self.chart.draw()
