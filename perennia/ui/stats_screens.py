"""Estatísticas por desporto: gráficos por separadores e a escolha do desporto.

Ciclismo, ginásio e «todos» usam os ecrãs que já existiam (agora com os
gráficos em separadores); remo, corrida e natação usam `SportStatsScreen`.
"""
from __future__ import annotations

import json
from datetime import date

from perennia.core import stats
from perennia.core import sports as sp
from perennia.core.i18n import t, tr
from perennia.core.units import hms
from perennia.ui.sport_screens import EditScreen
from perennia.ui.widgets import Chart, Item


def _km(v: float) -> str:
    return f"{v:,.0f} km".replace(",", " ") if v >= 100 else f"{v:.1f} km"


def overview_items(app, sport: str | None) -> list[Item]:
    """O separador «Geral»: um resumo muito simples. Com um desporto, o dele;
    sem desporto (Estatísticas gerais), uma linha por desporto e o total."""
    db = app.db
    if sport is None:
        rows = []
        tot = {"n": 0, "hours": 0.0, "km": 0.0}
        for ov in stats.overview_all(db):
            t_ = ov["total"]
            for k in tot:
                tot[k] += t_[k]
            last = ov["last"]
            rows.append(Item(sp.name(ov["sport"]) if ov["sport"] != "gym" else tr("Ginásio", "Gym"),
                             value=tr("{n} sessões", "{n} sessions", n=t_["n"]),
                             detail=" · ".join(x for x in (
                                 f"{t_['hours']:.1f} h",
                                 _km(t_["km"]) if t_["km"] else "",
                                 tr("7 dias: {n}", "7 days: {n}", n=ov["week"]["n"]),
                                 tr("última {d}", "last {d}", d=last["at"].strftime("%d/%m"))
                                 if last else "") if x), enabled=False))
        rows.insert(0, Item(tr("Total", "Total"), value=tr("{n} sessões", "{n} sessions",
                                                           n=tot["n"]),
                            detail=f"{tot['hours']:.1f} h" + (f" · {_km(tot['km'])}"
                                                              if tot["km"] else ""),
                            enabled=False))
        return rows
    ov = stats.overview(db, sport)

    def line(label, a):
        bits = [f"{a['hours']:.1f} h"]
        if a["km"]:
            bits.append(_km(a["km"]))
        return Item(label, value=tr("{n} sessões", "{n} sessions", n=a["n"]),
                    detail=" · ".join(bits), enabled=False)
    rows = [line(tr("Total", "Total"), ov["total"]),
            line(tr("Últimos 7 dias", "Last 7 days"), ov["week"]),
            line(tr("Últimos 30 dias", "Last 30 days"), ov["month"]),
            line(tr("Este ano", "This year"), ov["year"])]
    has_records = sport in ("rowing", "running", "swimming")   # já estão nos recordes
    if ov["longest"] and not has_records:
        x = ov["longest"]
        rows.append(Item(tr("Sessão mais longa", "Longest session"), value=hms(x["seconds"]),
                         detail=x["at"].strftime("%d/%m/%Y"), enabled=False))
    if ov["farthest"] and ov["farthest"]["distance_m"] and not has_records:
        x = ov["farthest"]
        rows.append(Item(tr("Maior distância", "Longest distance"),
                         value=_km(x["distance_m"] / 1000) if x["distance_m"] >= 1000
                         else f"{x['distance_m']:.0f} m",
                         detail=x["at"].strftime("%d/%m/%Y"), enabled=False))
    if ov["last"]:
        rows.append(Item(tr("Última sessão", "Last session"),
                         value=ov["last"]["at"].strftime("%d/%m/%Y"), enabled=False))
    # os recordes, cada um com a sessão onde foi feito (Enter abre-a)
    if sport == "rowing":
        from perennia.ui.rowing_screens import record_items
        rows += [Item(tr("— Recordes —", "— Records —"), enabled=False)] + [
            r for r in record_items(app) if r.action is not None]
    elif sport in ("running", "swimming"):
        from perennia.ui.endurance_screens import record_items as erec
        rows += [Item(tr("— Recordes —", "— Records —"), enabled=False)] + [
            r for r in erec(app, sport) if r.action is not None]
    elif sport == "gym":
        from perennia.ui.exercise_stats_screens import ExerciseStatsScreen
        rows.append(Item(tr("Estatísticas por exercício", "Exercise statistics"),
                         detail=tr("Evolução da carga, 1RM, volume, RPE e tempo de cada exercício",
                                   "Progress of load, 1RM, volume, RPE and time per exercise"),
                         action=lambda: app.push(ExerciseStatsScreen(app))))
    if sport == "cycling":
        now = stats.fitness_now(db, ("cycling",))
        if now:
            rows.append(Item(tr("Fitness · fadiga · forma", "Fitness · fatigue · form"),
                             value=f"{now['ctl']:.0f} · {now['atl']:.0f} · {now['tsb']:+.0f}",
                             enabled=False))
        rows.append(Item("FTP", value=f"{db.athlete().ftp_w} W", enabled=False))
    return rows


def for_sport(app, sport: str | None):
    from perennia.ui import app as app_mod
    from perennia.ui import sport_screens as ss
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
    VIEWS = ("general", "distance", "time", "load", "pace", "hr_zones")
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
        return [tr("Geral", "Overview"), tr("Distância", "Distance"), tr("Tempo", "Time"),
                tr("Carga", "Load"), tr("Ritmo médio", "Avg pace"), tr("Zonas de FC", "HR zones")]

    @property
    def general(self) -> bool:
        return self.VIEWS[self.tab % len(self.VIEWS)] == "general"

    def rows(self) -> list[tuple]:
        return stats.sport_rows(self.app.db, self.sport)

    def sport_item(self) -> Item:
        if self.hub is not None:
            return Item(tr("Desporto", "Sport"), value=sp.name(self.sport), enabled=False,
                        detail=tr("fixo · outros desportos em Estatísticas gerais",
                                  "fixed · other sports in General statistics"))
        return Item(tr("Desporto", "Sport"), value=sp.name(self.sport), data="cyc:sport",
                    detail=tr("←/→ outro desporto · Tab outro gráfico",
                              "←/→ another sport · Tab another chart"))

    def enter(self) -> None:
        rows = self.rows()
        dist = sum(r["distance_m"] or 0 for _, r in rows)
        hours = sum((r["moving_s"] or r["elapsed_s"] or 0) for _, r in rows) / 3600
        title, sub = self.titles(t("menu.statistics") + f" · {sp.name(self.sport)}",
                                 tr("{n} sessões · {d:.1f} km · {h:.1f} h",
                                    "{n} sessions · {d:.1f} km · {h:.1f} h",
                                    n=len(rows), d=dist / 1000, h=hours))
        foot = tr("Tab gráfico · ←/→ mudar · Esc voltar", "Tab chart · ←/→ change · Esc back")
        if self.general:
            items = [self.sport_item()] + overview_items(self.app, self.sport)
            self.list.set_items(items, keep_index=True)
            self.list.set_visible_rows(max(4, (self.content_top(self.app.window.height)
                                               - 110) // 38))
            self.chrome.set(title, sub, foot)
            return
        self.list.set_items([
            self.sport_item(),
            Item(tr("Agrupar por", "Group by"),
                 value=tr("semana", "week") if self.grouping == "week" else tr("mês", "month"),
                 data="cyc:grouping", detail=tr("←/→ muda", "←/→ changes"))], keep_index=True)
        self.list.set_visible_rows(2)
        self.chrome.set(title, sub, foot)
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
            from perennia.gfx.hud import zone_color
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
        peak = max([v for _, v, _ in b] + [0.0])
        if view == "distance":
            # distâncias curtas (uma sessão de remo de 40 m) não podem ficar «0.0»
            if peak < 1.0:
                title, fmt = tr("Distância (m)", "Distance (m)"), (lambda v: f"{v * 1000:.0f}")
            else:
                title, fmt = tr("Distância (km)", "Distance (km)"), (
                    lambda v: f"{v:.1f}" if peak < 20 else f"{v:.0f}")
        elif view == "time":
            title = tr("Tempo", "Time")
            fmt = (lambda v: f"{v * 60:.0f} min") if peak < 2 else (lambda v: f"{v:.1f} h")
        else:
            title, fmt = tr("Carga", "Load"), (lambda v: f"{v:.0f}")
        self.chart.show_bars(title, [v for _, v, _ in b], [lab for lab, _, _ in b], empty,
                             fmt=fmt)

    def cycle(self, field: str, step: int) -> None:
        if field == "grouping":
            self.grouping = "month" if self.grouping == "week" else "week"
        elif field == "sport" and self.hub is None:
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
        if not self.general:
            self.chart.draw()
