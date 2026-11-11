"""Infográficos de uma sessão de ciclismo, à maneira do relatório do
TrainingPeaks: um separador por vista.

* **Relatório** — duração, distância, subida, trabalho; potência média, NP e
  máxima; IF, TSS, VI e EF; FC, cadência e velocidade médias e máximas; e o
  desacoplamento potência:FC (Pa:HR) entre as duas metades.
* **Curva de potência** — a melhor média da sessão em cada duração.
* **Zonas** — tempo em cada zona de potência e de FC (as cores do construtor).
* **Gráfico** — potência, cadência e FC ao longo da sessão, sobrepostas; ←/→
  em cada linha liga ou desliga essa série (qualquer combinação).
* **Picos** — a melhor média de potência, FC, cadência e velocidade em cada
  duração (5 s a 90 min).
"""
from __future__ import annotations

from pyglet.window import key

from perennia.core import peaks as pk
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.ui.app import Screen
from perennia.ui.widgets import Chart, Item, StackedBars, Table

SERIES = (("power_w", ("Potência", "Power"), (108, 170, 220)),
          ("cadence_rpm", ("Cadência", "Cadence"), (120, 200, 150)),
          ("hr_bpm", ("FC", "HR"), (214, 54, 128)))


def downsample(values: list[float], n: int) -> list[float]:
    """Médias por troços, para caber no gráfico (n pontos)."""
    if len(values) <= n:
        return list(values)
    step = len(values) / n
    out = []
    for i in range(n):
        chunk = values[int(i * step):int((i + 1) * step)] or [values[min(len(values) - 1,
                                                                         int(i * step))]]
        out.append(sum(chunk) / len(chunk))
    return out


class RideInfographics(Screen):
    TABBED = True
    VIEWS = ("report", "curve", "zones", "overlay", "peaks")

    def __init__(self, app, ride_id: str):
        self.ride_id = ride_id
        super().__init__(app)
        self.rep = pk.report(app.db, ride_id)
        self.show = {"power_w": True, "cadence_rpm": True, "hr_bpm": True}
        w, h = app.window.width, app.window.height
        self.chart = Chart(*self._chart_box(w, h))
        self.bars = StackedBars()
        self.bars.layout(96, self.content_top(h) - 20, w - 144)
        self.table = Table()
        self.table.layout(48, self.content_top(h) + 10, w - 96, 70)

    def tab_labels(self) -> list[str]:
        return [tr("Relatório", "Report"), tr("Curva de potência", "Power curve"),
                tr("Zonas", "Zones"), tr("Gráfico", "Chart"), tr("Picos", "Peaks")]

    @property
    def view(self) -> str:
        return self.VIEWS[self.tab % len(self.VIEWS)]

    def _chart_box(self, w: int, h: int) -> tuple:
        top = self.content_top(h) - (3 * 38 + 20 if self.view == "overlay" else 30)
        return 96, 112, w - 144, max(140, top - 112 - 30)

    # -------------------------------------------------------------- linhas

    def _report_rows(self) -> list[Item]:
        r = self.rep
        a = self.app

        def num(v, f):
            return f.format(v) if v is not None else "—"
        rows = []
        row = a.db.conn.execute("SELECT distance_m, ascent_m, moving_s, elapsed_s FROM rides"
                                " WHERE id = ?", (self.ride_id,)).fetchone()
        if row is not None:
            rows += [Item(tr("Duração", "Duration"), value=hms(row["moving_s"] or row["elapsed_s"]
                                                              or 0), enabled=False),
                     Item(tr("Distância", "Distance"),
                          value=f"{(row['distance_m'] or 0) / 1000:.2f} km", enabled=False),
                     Item(tr("Subida", "Climbing"), value=f"{row['ascent_m'] or 0:.0f} m",
                          enabled=False)]
        rows += [
            Item(tr("Trabalho", "Work"), value=num(r.get("work_kj"), "{:.0f} kJ"), enabled=False),
            Item(tr("Potência média", "Avg power"), value=num(r.get("avg_power"), "{:.0f} W"),
                 detail=tr("a pedalar: {w}", "while pedalling: {w}",
                           w=num(r.get("avg_power_moving"), "{:.0f} W")), enabled=False),
            Item(tr("Potência normalizada (NP)", "Normalized power (NP)"),
                 value=num(r.get("np"), "{:.0f} W"), enabled=False),
            Item(tr("Potência máxima", "Max power"), value=num(r.get("max_power"), "{:.0f} W"),
                 enabled=False),
            Item(tr("Fator de intensidade (IF)", "Intensity factor (IF)"),
                 value=num(r.get("if"), "{:.2f}"), detail=f"FTP {r.get('ftp', 0):.0f} W",
                 enabled=False),
            Item("TSS", value=num(r.get("tss"), "{:.0f}"), enabled=False),
            Item(tr("Índice de variabilidade (VI)", "Variability index (VI)"),
                 value=num(r.get("vi"), "{:.2f}"),
                 detail=tr("NP ÷ média: perto de 1 é constante", "NP ÷ average: near 1 is steady"),
                 enabled=False),
            Item(tr("Fator de eficiência (EF)", "Efficiency factor (EF)"),
                 value=num(r.get("ef"), "{:.2f}"), detail=tr("NP ÷ FC média", "NP ÷ avg HR"),
                 enabled=False),
            Item(tr("Desacoplamento Pa:FC", "Pa:HR decoupling"),
                 value=num(r.get("decoupling"), "{:+.1f} %"),
                 detail=tr("potência/FC da 1.ª metade face à 2.ª · abaixo de 5 % é base aeróbia "
                           "sólida", "power/HR of the 1st half vs the 2nd · under 5 % is a solid "
                           "aerobic base"), enabled=False),
            Item(tr("FC média · máxima", "Avg · max HR"),
                 value=f"{num(r.get('avg_hr'), '{:.0f}')} · {num(r.get('max_hr'), '{:.0f}')} bpm",
                 enabled=False),
            Item(tr("Cadência média · máxima", "Avg · max cadence"),
                 value=f"{num(r.get('avg_cadence'), '{:.0f}')} · "
                       f"{num(r.get('max_cadence'), '{:.0f}')} rpm", enabled=False),
            Item(tr("Velocidade média · máxima", "Avg · max speed"),
                 value=f"{num((r.get('avg_speed') or 0) * 3.6, '{:.1f}')} · "
                       f"{num((r.get('max_speed') or 0) * 3.6, '{:.1f}')} km/h", enabled=False),
        ]
        return rows

    def enter(self) -> None:
        r = self.rep
        title = r.get("name") or tr("Sessão", "Session")
        sub = tr("Infográficos de sessão · {d}", "Session infographics · {d}",
                 d=str(r.get("started_at") or "")[:16].replace("T", " "))
        foot = tr("Tab outra vista · Esc voltar", "Tab another view · Esc back")
        view = self.view
        w, h = self.app.window.width, self.app.window.height
        self.chart = Chart(*self._chart_box(w, h))
        items: list[Item] = []
        if not r:
            items = [Item(tr("Sem dados desta sessão.", "No data for this session."),
                          enabled=False)]
        elif view == "report":
            items = self._report_rows()
        elif view == "curve":
            curve = [(d, v) for d, v in r.get("curve", []) if v > 0]
            self.chart.show_line(tr("Curva de potência da sessão", "Session power curve"),
                                 [v for _, v in curve], [pk.duration_label(d) for d, _ in curve],
                                 tr("Sem potência nesta sessão.", "No power in this session."),
                                 log_x=True, xs=[d for d, _ in curve], fmt=lambda v: f"{v:.0f} W")
        elif view == "zones":
            from perennia.gfx.hud import zone_color
            rows = []
            for kind, secs, title_ in (("power", r.get("power_zones") or [], tr("Potência",
                                                                                 "Power")),
                                       ("hr", r.get("hr_zones") or [], tr("FC", "HR"))):
                total = sum(secs)
                if not total:
                    continue
                rows.append({"title": title_, "note": hms(total),
                             "parts": [(v / total, zone_color(i + 1, kind),
                                        f"Z{i + 1} {v / total * 100:.0f}%")
                                       for i, v in enumerate(secs)]})
            self.bars.layout(96, self.content_top(h) - 10, w - 144, 80)
            self.bars.set_rows(rows)
            for kind, secs in (("power", r.get("power_zones") or []), ("hr",
                                                                        r.get("hr_zones") or [])):
                total = sum(secs) or 1
                for i, v in enumerate(secs):
                    if v:
                        items.append(Item(f"{'P' if kind == 'power' else tr('FC', 'HR')} · Z{i + 1}",
                                          value=f"{hms(v)} · {v / total * 100:.0f} %",
                                          enabled=False))
        elif view == "overlay":
            for key_, names, _c in SERIES:
                items.append(Item(("✓ " if self.show[key_] else "   ") + tr(*names),
                                  value=tr("ligada", "on") if self.show[key_] else
                                  tr("desligada", "off"),
                                  detail=tr("←/→ liga/desliga", "←/→ on/off"),
                                  data=f"series:{key_}"))
            series = []
            for key_, names, color in SERIES:
                vals = (r.get("series") or {}).get(key_) or []
                if self.show[key_] and any(vals):
                    series.append((tr(*names), downsample(vals, 119), color))
            n = len((r.get("series") or {}).get("power_w") or [])
            labels = [hms(n * k / 6) for k in range(7)]
            lab_full = []
            pts = len(series[0][1]) if series else 0
            for i in range(pts):
                lab_full.append(hms(n * i / max(1, pts - 1)))
            self.chart.show_lines(tr("Potência, cadência e FC ao longo da sessão",
                                     "Power, cadence and HR through the session"), series,
                                  lab_full, tr("Liga pelo menos uma série.",
                                               "Turn on at least one series."),
                                  fmt=lambda v: f"{v:.0f}")
            _ = labels
        elif view == "peaks":
            cols = [tr("Duração", "Duration"), tr("Potência", "Power"), tr("FC", "HR"),
                    tr("Cadência", "Cadence"), tr("Velocidade", "Speed")]
            ps = r.get("peaks") or {}
            rows = [[pk.duration_label(d)] + [pk.fmt(m, ps.get(m, {}).get(d), self.app.units)
                                              for m in pk.METRICS]
                    for d in pk.DURATIONS if d <= max(1, r.get("seconds", 0))]
            self.table.layout(48, self.content_top(h) + 10, w - 96, 70)
            self.table.set(cols, rows, tr("Picos da sessão", "Session peaks"),
                           empty=tr("Sessão curta demais.", "Session too short."))
        self.chrome.set(title, sub, foot)
        self.list.set_items(items, keep_index=True)
        if view in ("curve", "peaks"):
            self.list.y = -3000
        else:
            self.list.y = self.content_top(h) - (100 if view == "zones" else 0)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and isinstance(item.data, str) and item.data.startswith("series:") \
                and symbol in (key.LEFT, key.RIGHT):
            k = item.data[7:]
            self.show[k] = not self.show[k]
            self.enter()
            return True
        return super().on_key(symbol, modifiers)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.enter()

    def agent_data(self) -> dict:
        r = {k: v for k, v in self.rep.items() if k not in ("series",)}
        return {"relatorio": r}

    def draw(self) -> None:
        super().draw()
        view = self.view
        if view in ("curve", "overlay"):
            self.chart.draw()
        elif view == "zones":
            self.bars.draw()
        elif view == "peaks":
            self.table.draw()
