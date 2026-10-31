"""Saúde (diário, métricas, análises, importação), testes de aptidão e o ecrã
do agente de IA."""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pyglet
from pyglet.window import key

from velo.core import agent as agent_mod
from velo.core import fitness_tests as ft
from velo.core import health
from velo.core import labs
from velo.core.i18n import t, tr
from velo.core.units import hms, parse_number
from velo.gfx.compat import label as make_label
from velo.ui.app import FtpScreen, FtpRouteChoice, Screen
from velo.ui.sport_screens import EditScreen
from velo.ui.widgets import ACCENT, BAD, Chart, DIM, GOOD, PANEL, TEXT, Item

WEEKDAYS_PT = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _connect():
    from velo.ui import connect_screens
    return connect_screens


def day_label(d: date) -> str:
    today = date.today()
    rel = {0: tr("hoje", "today"), 1: tr("ontem", "yesterday")}.get((today - d).days)
    wd = WEEKDAYS_PT[d.weekday()] if tr("pt", "en") == "pt" else d.strftime("%A").lower()
    return f"{rel + ' · ' if rel else ''}{wd}, {d.day:02d}/{d.month:02d}/{d.year}"


def _excerpt(text: str | None, n: int = 70) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[:n - 1] + "…"


# ================================================================= agente


class AgentScreen(Screen):
    """«Resumo desta página» (F1) e «resumo contextualizado» (F2). Enquanto o
    agente não estiver ligado, mostra o pedido que lhe seria enviado."""

    AGENT = False

    @classmethod
    def open(cls, app, source, kind: str) -> None:
        app.push(cls(app, source, kind))

    def __init__(self, app, source, kind: str):
        super().__init__(app)
        self.kind = kind
        self.request = agent_mod.build_request(kind, source, app.db)
        self.source_name = type(source).__name__

    def enter(self) -> None:
        a = self.app
        prov = agent_mod.provider(a.db)
        title = tr("Resumo desta página", "Summary of this page") if self.kind == "page" \
            else tr("Resumo contextualizado", "Contextual summary")
        if prov["ready"]:
            head = tr("O agente está configurado, mas a ligação ainda não foi ativada nesta "
                      "versão.", "The agent is configured, but calls are not enabled yet.")
        else:
            head = tr("O agente de IA ainda não está ligado. É isto que lhe seria enviado "
                      "(≈ {n} tokens):", "The AI agent is not connected yet. This is what "
                      "would be sent (≈ {n} tokens):", n=self.request["approx_tokens"])
        items = [Item(head, enabled=False),
                 Item(tr("Pedido", "Request"), value=_excerpt(self.request["instruction"], 90),
                      enabled=False)]
        for k, v in agent_mod.flatten(self.request["content"]):
            items.append(Item(k, value=_excerpt(v, 60), enabled=False))
        share = ", ".join(sorted(agent_mod.allowed(a.db)))
        self.chrome.set(title, tr("Categorias partilhadas: {s} · nada do Strava",
                                  "Shared categories: {s} · nothing from Strava", s=share),
                        tr("↑↓ percorrer · Esc voltar", "↑↓ scroll · Esc back"))
        self.list.set_items(items)


# ================================================================== saúde


class HealthMenu(Screen):
    def enter(self) -> None:
        a = self.app
        health.seed(a.db)
        ft.seed(a.db)
        done, total = health.completeness(a.db, date.today())
        reps = health.lab_reports(a.db)
        last_lab = reps[0]["done_on"] if reps else "—"
        self.chrome.set(tr("Saúde", "Health"),
                        tr("Hoje: {d} de {n} métricas preenchidas",
                           "Today: {d} of {n} metrics filled", d=done, n=total), self.footer())
        self.list.set_items([
            Item(tr("Diário de hoje", "Today's log"), value=f"{done}/{total}",
                 detail=tr("sono, energia, corpo, alimentação… com notas",
                           "sleep, energy, body, food… with notes"),
                 action=lambda: a.push(DailyLogScreen(a, date.today()))),
            Item(tr("Diário de ontem", "Yesterday's log"),
                 action=lambda: a.push(DailyLogScreen(a, date.today() - timedelta(days=1)))),
            Item(tr("Tendências", "Trends"), detail=tr("evolução de cada métrica",
                                                       "each metric over time"),
                 action=lambda: a.push(MetricTrendScreen(a))),
            Item(tr("Análises clínicas", "Lab results"), value=last_lab,
                 detail=tr("{n} relatórios · comentário do médico", "{n} reports · doctor's notes",
                           n=len(reps)),
                 action=lambda: a.push(LabsList(a))),
            Item(tr("Testes de longevidade", "Longevity tests"),
                 detail=tr("preensão, flexões, elevações, equilíbrio…",
                           "grip, push-ups, pull-ups, balance…"),
                 action=lambda: a.push(TestsMenu(a, "longevity"))),
            Item(tr("Métricas do diário", "Log metrics"),
                 detail=tr("escolher, criar e ordenar", "choose, create and order"),
                 action=lambda: a.push(MetricsManager(a))),
            Item(tr("Importar dados", "Import data"),
                 detail="HRV4Training · Garmin · CSV",
                 action=lambda: a.push(ImportScreen(a))),
        ], keep_index=True)


class DailyLogScreen(EditScreen):
    """Um dia: todas as métricas ativas, agrupadas. ←/→ no «Dia» muda de dia;
    N numa métrica abre a nota dela."""

    def __init__(self, app, day: date):
        super().__init__(app)
        self.day = day

    def enter(self) -> None:
        db = self.app.db
        health.seed(db)
        vals = health.values_for(db, self.day)
        rows = [Item(tr("Dia", "Day"), value=day_label(self.day), data="cyc:day")]
        group = None
        for m in health.metrics(db):
            if m["grp"] != group:
                group = m["grp"]
                rows.append(Item(f"— {group_name(group)} —", enabled=False))
            v = vals.get(m["id"])
            value = health.fmt(m, v["value"]) if v else "—"
            detail = ""
            if v and v.get("notes"):
                detail = "✎ " + _excerpt(v["notes"], 80)
            elif v and v.get("source") not in (None, "manual"):
                detail = tr("de {s}", "from {s}", s=v["source"])
            kind = m["kind"]
            data = (f"cyc:m{m['id']}" if kind in ("bool", "choice") else
                    f"text:m{m['id']}" if kind in ("text", "time") else f"num:m{m['id']}")
            rows.append(Item(m["name"], value=value, detail=detail, data=data))
        note = health.day_note(db, self.day)
        rows.append(Item(tr("Nota do dia", "Day note"), value=_excerpt(note, 50) or "—",
                         action=self._edit_day_note))
        done, total = health.completeness(db, self.day)
        self.chrome.set(tr("Diário", "Log"), f"{day_label(self.day)} · {done}/{total}",
                        tr("←/→ mudar · escreve · N nota da métrica · Esc voltar",
                           "←/→ change · type · N metric note · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def _metric(self, field: str) -> dict | None:
        return health.metric(self.app.db, int(field[1:])) if field.startswith("m") else None

    def cycle(self, field: str, step: int) -> None:
        if field == "day":
            nd = self.day + timedelta(days=step)
            if nd <= date.today():
                self.day = nd
            return
        m = self._metric(field)
        if m is None:
            return
        cur = health.values_for(self.app.db, self.day).get(m["id"])
        value = cur["value"] if cur else None
        if m["kind"] == "bool":
            order = [None, 1.0, 0.0]
            i = order.index(value) if value in order else 0
            new = order[(i + step) % 3]
        else:
            opts = [None] + list(m["choices"])
            i = opts.index(value) if value in opts else 0
            new = opts[(i + step) % len(opts)]
        health.set_value(self.app.db, self.day, m["id"], new)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        m = self._metric(field)
        if m is None:
            return
        cur = health.values_for(self.app.db, self.day).get(m["id"])
        v = cur["value"] if cur else None
        if m["kind"] == "scale":
            new = max(1, min(5, (v or 3) + steps)) if v is not None or steps else None
            if v is None:
                new = 3
        else:
            step = {"kg": 0.1, "h": 0.25, "L": 0.25, "cm": 0.5}.get(m["unit"], 1.0)
            if m["key"] == "steps":
                step = 500
            new = max(0.0, (v if v is not None else self._guess(m)) + steps * step * (10 if big else 1))
            new = round(new, 2)
        health.set_value(self.app.db, self.day, m["id"], new)

    def _guess(self, m: dict) -> float:
        """Ponto de partida das setas: o último valor registado."""
        r = self.app.db.conn.execute(
            "SELECT num FROM daily_values WHERE metric_id = ? AND num IS NOT NULL AND day < ?"
            " ORDER BY day DESC LIMIT 1", (m["id"], health.day_key(self.day))).fetchone()
        return r["num"] if r else 0.0

    def num_set(self, field: str, value: float | None) -> None:
        m = self._metric(field)
        if m is None:
            return
        if m["kind"] == "scale" and value is not None:
            value = max(1, min(5, value))
        health.set_value(self.app.db, self.day, m["id"], value)

    def text_input(self, field: str, text: str) -> None:
        m = self._metric(field)
        cur = health.values_for(self.app.db, self.day).get(m["id"]) if m else None
        health.set_value(self.app.db, self.day, m["id"], ((cur or {}).get("value") or "") + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        m = self._metric(field)
        cur = health.values_for(self.app.db, self.day).get(m["id"]) if m else None
        health.set_value(self.app.db, self.day, m["id"],
                         (str((cur or {}).get("value") or ""))[:-1] or None)
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        data = item.data if item is not None else None
        if symbol == key.N and isinstance(data, str) and data[4:5] == "m" \
                and not data.startswith("text:"):
            self._edit_note(int(data[5:]))
            return True
        return super().on_key(symbol, modifiers)

    def _edit_note(self, metric_id: int) -> None:
        db = self.app.db
        m = health.metric(db, metric_id)
        cur = health.values_for(db, self.day).get(metric_id)
        self.app.push(TextEditScreen(
            self.app, tr("Nota · {n}", "Note · {n}", n=m["name"]), day_label(self.day),
            (cur or {}).get("notes") or "",
            lambda text: health.set_note(db, self.day, metric_id, text)))

    def _edit_day_note(self) -> None:
        db = self.app.db
        self.app.push(TextEditScreen(
            self.app, tr("Nota do dia", "Day note"), day_label(self.day),
            health.day_note(db, self.day), lambda text: health.set_day_note(db, self.day, text)))

    def agent_data(self) -> dict:
        return {"dia": self.day.isoformat()}


def group_name(g: str) -> str:
    return {"sleep": tr("Sono", "Sleep"), "body": tr("Corpo", "Body"),
            "recovery": tr("Recuperação", "Recovery"), "food": tr("Alimentação", "Food"),
            "mind": tr("Mente", "Mind"), "activity": tr("Atividade", "Activity"),
            "other": tr("Outras", "Other")}.get(g, g)


class TextEditScreen(Screen):
    """Texto livre com várias linhas (notas, comentário do médico).
    Enter muda de linha; Esc guarda e volta."""

    AGENT = False

    def __init__(self, app, title: str, subtitle: str, text: str, on_save):
        super().__init__(app)
        self.title, self.sub = title, subtitle
        self.text = text or ""
        self.on_save = on_save
        w, h = app.window.width, app.window.height
        self.batch = pyglet.graphics.Batch()
        self.box = pyglet.shapes.Rectangle(40, 100, w - 80, h - 230, color=PANEL,
                                           batch=self.batch)
        self.label = make_label("", font_size=14, color=TEXT, multiline=True,
                                width=w - 120, anchor_y="top", batch=self.batch)
        self.label.x, self.label.y = 60, h - 150

    def enter(self) -> None:
        self.chrome.set(self.title, self.sub,
                        tr("Escreve · Enter nova linha · Esc guardar e voltar",
                           "Type · Enter new line · Esc save and go back"))
        self.list.set_items([])
        self._render()

    def _render(self) -> None:
        self.label.text = self.text + "▏"

    def on_text(self, text: str) -> bool:
        clean = "".join(c for c in text if c.isprintable() or c == "\n").replace("\r", "")
        if clean:
            self.text += clean
            self._render()
        return True

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol in (key.ENTER, key.RETURN):
            self.text += "\n"
            self._render()
            return True
        if symbol == key.BACKSPACE:
            self.text = self.text[:-1]
            self._render()
            return True
        if symbol == key.ESCAPE:
            self.save()
            return True
        return True

    def save(self) -> None:
        self.on_save(self.text.strip())
        self.app.pop()

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.save()
            return True
        return False

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


class MetricsManager(Screen):
    """As métricas do diário. Enter edita; A liga/desliga; ←/→ muda a ordem."""

    def enter(self) -> None:
        a = self.app
        rows = [Item(tr("+ Nova métrica", "+ New metric"),
                     action=lambda: a.push(MetricEditor(a, None)))]
        for m in health.metrics(a.db, include_inactive=True):
            rows.append(Item(("✓ " if m["active"] else "✗ ") + m["name"],
                             value=kind_name(m["kind"]) + (f" · {m['unit']}" if m["unit"] else ""),
                             detail=group_name(m["grp"]),
                             action=lambda mid=m["id"]: a.push(MetricEditor(a, mid)),
                             data=("metric", m["id"], m["active"])))
        self.chrome.set(tr("Métricas do diário", "Log metrics"), f"{len(rows) - 1}",
                        tr("Enter editar · A ligar/desligar · ←/→ ordem · Esc voltar",
                           "Enter edit · A on/off · ←/→ order · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and isinstance(item.data, tuple):
            _, mid, active = item.data
            if symbol == key.A:
                health.set_active(self.app.db, mid, not active)
                self.enter()
                return True
            if symbol in (key.LEFT, key.RIGHT):
                health.move_metric(self.app.db, mid, 1 if symbol == key.RIGHT else -1)
                self.list.index += 1 if symbol == key.RIGHT else -1
                self.enter()
                return True
        return super().on_key(symbol, modifiers)


def kind_name(k: str) -> str:
    return {"bool": tr("sim/não", "yes/no"), "number": tr("número", "number"),
            "scale": tr("escala 1–5", "scale 1–5"), "text": tr("texto", "text"),
            "choice": tr("escolha", "choice"), "time": tr("hora", "time")}.get(k, k)


class MetricEditor(EditScreen):
    def __init__(self, app, metric_id: int | None):
        super().__init__(app)
        self.metric_id = metric_id
        m = health.metric(app.db, metric_id) if metric_id else None
        self.name = m["name"] if m else ""
        self.kind = m["kind"] if m else "bool"
        self.unit = (m or {}).get("unit") or ""
        self.group = m["grp"] if m else "other"
        self.choices = ", ".join(m["choices"]) if m and m["choices"] else ""
        self.active = bool(m["active"]) if m else True

    def enter(self) -> None:
        rows = [Item(tr("Nome", "Name"), value=self.name or "—", data="text:name"),
                Item(tr("Tipo", "Type"), value=kind_name(self.kind), data="cyc:kind"),
                Item(tr("Unidade", "Unit"), value=self.unit or "—", data="text:unit"),
                Item(tr("Grupo", "Group"), value=group_name(self.group), data="cyc:group")]
        if self.kind == "choice":
            rows.append(Item(tr("Opções (separadas por vírgulas)", "Options (comma separated)"),
                             value=self.choices or "—", data="text:choices"))
        rows += [Item(tr("Ativa", "Active"), value=tr("sim", "yes") if self.active
                      else tr("não", "no"), data="cyc:active"),
                 Item(tr("Guardar", "Save"), action=self._save, button=True, primary=True)]
        self.chrome.set(tr("Métrica", "Metric"), self.name, self.footer())
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        if field == "kind":
            ks = list(health.KINDS)
            self.kind = ks[(ks.index(self.kind) + step) % len(ks)]
        elif field == "group":
            gs = list(health.GROUPS)
            self.group = gs[(gs.index(self.group) + step) % len(gs)]
        elif field == "active":
            self.active = not self.active

    def text_input(self, field: str, text: str) -> None:
        setattr(self, field, getattr(self, field) + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        setattr(self, field, getattr(self, field)[:-1])
        self.enter()

    def _save(self) -> None:
        if not self.name.strip():
            self.app.message(tr("Dá um nome à métrica.", "Give the metric a name."))
            return
        choices = [c.strip() for c in self.choices.split(",") if c.strip()]
        mid = health.save_metric(self.app.db, self.metric_id, name=self.name, kind=self.kind,
                                 unit=self.unit, group=self.group, choices=choices or None)
        health.set_active(self.app.db, mid, self.active)
        self.app.pop()


class MetricTrendScreen(EditScreen):
    RANGES = (14, 30, 90, 180, 365)

    def __init__(self, app):
        super().__init__(app)
        self.metric_idx = 0
        self.days = 30
        w, h = app.window.width, app.window.height
        self.chart = Chart(96, 112, w - 144, max(140, h - 130 - 3 * 38 - 160))
        self.summary = make_label("", font_size=12, color=TEXT, anchor_y="top")

    def _numeric(self) -> list[dict]:
        return [m for m in health.metrics(self.app.db) if m["kind"] in ("number", "scale", "bool")]

    def enter(self) -> None:
        ms = self._numeric()
        m = ms[self.metric_idx % len(ms)] if ms else None
        rows = [Item(tr("Métrica", "Metric"), value=m["name"] if m else "—", data="cyc:metric"),
                Item(tr("Intervalo", "Range"), value=tr("últimos {n} dias", "last {n} days",
                                                         n=self.days), data="cyc:range")]
        self.chrome.set(tr("Tendências", "Trends"), "", self.footer())
        self.list.set_items(rows, keep_index=True)
        self.list.set_visible_rows(3)
        self._series = []
        if m is None:
            return
        data = [(d, v) for d, v in health.series(self.app.db, m["id"], self.days)
                if v is not None]
        self._series = data
        vals = [v for _, v in data]
        self.chart.show_line(m["name"], vals, [f"{d.day:02d}/{d.month:02d}" for d, _ in data],
                             tr("Ainda sem registos suficientes.", "Not enough records yet."),
                             fmt=lambda v: health.fmt(m, v) if m["kind"] != "bool" else f"{v:.1f}")
        if vals:
            self.summary.text = tr("média {a} · mín {lo} · máx {hi} · último {last} · {n} dias",
                                   "mean {a} · min {lo} · max {hi} · last {last} · {n} days",
                                   a=health.fmt(m, sum(vals) / len(vals)),
                                   lo=health.fmt(m, min(vals)), hi=health.fmt(m, max(vals)),
                                   last=health.fmt(m, vals[-1]), n=len(vals))
        else:
            self.summary.text = ""

    def cycle(self, field: str, step: int) -> None:
        if field == "metric":
            self.metric_idx += step
        else:
            i = self.RANGES.index(self.days)
            self.days = self.RANGES[(i + step) % len(self.RANGES)]

    def agent_data(self) -> dict:
        return {"serie": [(d.isoformat(), v) for d, v in self._series]}

    def draw(self) -> None:
        super().draw()
        self.summary.x, self.summary.y = self.chart.x, self.chart.y + self.chart.height + 48
        self.summary.draw()
        self.chart.draw()


# ------------------------------------------------------------- análises


class LabsList(Screen):
    def enter(self) -> None:
        a = self.app
        labs.ensure(a.db)
        rows = [Item(tr("+ Nova análise", "+ New lab report"),
                     action=lambda: a.push(LabReportEditor(a, None))),
                Item(tr("Importar do Excel", "Import from Excel"),
                     detail=tr("Folhas «readings» e «ref_parameter» (.xlsx)",
                               "Sheets «readings» and «ref_parameter» (.xlsx)"),
                     action=lambda: a.push(ImportScreen(a, patterns=("*.xlsx", "*.xlsm"))))]
        for r in health.lab_reports(a.db):
            out = f" · {r['out_of_range']} " + tr("fora do intervalo", "out of range") \
                if r["out_of_range"] else ""
            kind = f"  · {r['kind']}" if r.get("kind") else ""
            rows.append(Item(f"{r['done_on']}  {r['lab'] or ''}{kind}",
                             value=tr("{n} marcadores", "{n} markers", n=r["n"]) + out,
                             detail=("🩺 " + _excerpt(r["doctor_feedback"], 90))
                             if r["doctor_feedback"] else _excerpt(r["notes"], 90),
                             action=lambda rid=r["id"]: a.push(LabReportEditor(a, rid))))
        if health.markers_seen(a.db):
            rows.append(Item(tr("Evolução de um marcador", "A marker over time"),
                             action=lambda: a.push(MarkerHistoryScreen(a))))
        n_par = len(labs.parameters(a.db))
        rows.append(Item(tr("Catálogo de parâmetros", "Parameter catalog"),
                         value=str(n_par) if n_par else "",
                         detail=tr("Unidades e intervalos de referência",
                                   "Units and reference ranges"),
                         action=lambda: a.push(ParameterCatalog(a))))
        self.chrome.set(tr("Análises clínicas", "Lab results"),
                        tr("Por data. Cada análise tem os resultados e o comentário do médico.",
                           "By date. Each report has the results and the doctor's notes."),
                        self.footer())
        self.list.set_items(rows, keep_index=True)


class ParameterCatalog(Screen):
    def enter(self) -> None:
        a = self.app
        rows = []
        area = None
        for p in labs.parameters(a.db):
            rng = ref_text(p)
            if p.get("ideal_low") is not None or p.get("ideal_high") is not None:
                rng += " · " + tr("ideal", "ideal") + " " + ref_text(
                    {"ref_low": p.get("ideal_low"), "ref_high": p.get("ideal_high")}).replace(
                    "ref. ", "")
            if p.get("ref_manual"):
                rng += " ✎"
            if p.get("area") and p["area"] != area:
                area = p["area"]
            rows.append(Item(p["short_name"] or p["name"], value=p["unit"] or "",
                             detail=rng, action=lambda pid=p["id"]: a.push(
                                 ParameterEditor(a, pid))))
        if not rows:
            rows.append(Item(tr("Ainda sem parâmetros: importa o Excel das análises.",
                                "No parameters yet: import the lab Excel."), enabled=False))
        self.chrome.set(tr("Catálogo de parâmetros", "Parameter catalog"),
                        tr("✎ = intervalo corrigido à mão", "✎ = range edited by hand"),
                        self.footer())
        self.list.set_items(rows, keep_index=True)


class ParameterEditor(EditScreen):
    def __init__(self, app, pid: int):
        super().__init__(app)
        self.pid = pid
        p = labs.parameter(app.db, pid) or {}
        self.p = p
        self.v = {"unit": p.get("unit") or "", "ref_low": p.get("ref_low"),
                  "ref_high": p.get("ref_high")}

    def enter(self) -> None:
        v, p = self.v, self.p

        def n(x):
            return "—" if x is None else f"{x:g}"
        rows = [Item(tr("Nome", "Name"), value=p.get("short_name") or "", enabled=False,
                     detail=p.get("name") or ""),
                Item(tr("Unidade", "Unit"), value=(v["unit"] or "") + "▏", data="text:unit"),
                Item(tr("Referência mínima", "Reference low"), value=n(v["ref_low"]),
                     data="num:ref_low"),
                Item(tr("Referência máxima", "Reference high"), value=n(v["ref_high"]),
                     data="num:ref_high")]
        for line in (p.get("reference_text") or "").splitlines()[:8]:
            if line.strip():
                rows.append(Item("  " + line.strip()[:90], enabled=False))
        if p.get("ref_source"):
            rows.append(Item(tr("Linha usada", "Line used"), value=p["ref_source"][:60],
                             enabled=False))
        rows += [Item(tr("Guardar", "Save"), action=self._save, button=True, primary=True)]
        self.chrome.set(tr("Parâmetro", "Parameter"), p.get("area") or "", self.footer())
        self.list.set_items(rows, keep_index=True)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        cur = self.v[field] or 0.0
        self.v[field] = round(cur + steps * (10 if big else 1), 3)

    def num_set(self, field: str, value: float | None) -> None:
        self.v[field] = value

    def text_input(self, field: str, text: str) -> None:
        self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def _save(self) -> None:
        labs.set_parameter_reference(self.app.db, self.pid, self.v["ref_low"],
                                     self.v["ref_high"], self.v["unit"] or None)
        self.app.message(tr("Parâmetro guardado", "Parameter saved"))
        self.app.pop()

    def agent_data(self) -> dict:
        return {"parametro": {k: self.p.get(k) for k in (
            "name", "unit", "reference_text", "ref_low", "ref_high", "ideal_low", "ideal_high")}}


class LabReportEditor(EditScreen):
    def __init__(self, app, report_id: int | None):
        super().__init__(app)
        self.report_id = report_id
        r = health.lab_report(app.db, report_id) if report_id else None
        self.done_on = r["done_on"] if r else date.today().isoformat()
        self.lab = (r or {}).get("lab") or ""
        self.notes = (r or {}).get("notes") or ""
        self.doctor = (r or {}).get("doctor_feedback") or ""
        self._armed = False

    def _ensure(self) -> int:
        self.report_id = health.save_lab_report(self.app.db, self.report_id,
                                                done_on=self.done_on, lab=self.lab,
                                                notes=self.notes, doctor_feedback=self.doctor)
        return self.report_id

    def enter(self) -> None:
        a = self.app
        rows = [Item(tr("Data das análises", "Date"), value=self.done_on, data="cyc:date",
                     detail=tr("←/→ muda o dia · escreve AAAA-MM-DD", "←/→ day · type YYYY-MM-DD")),
                Item(tr("Laboratório", "Lab"), value=self.lab or "—", data="text:lab"),
                Item(tr("Comentário do médico", "Doctor's feedback"),
                     value=_excerpt(self.doctor, 50) or "—", action=self._edit_doctor),
                Item(tr("Notas", "Notes"), value=_excerpt(self.notes, 50) or "—",
                     action=self._edit_notes)]
        if self.report_id:
            groups = labs.grouped_results(a.db, self.report_id)
            show_headers = len(groups) > 1 or (groups and groups[0][0] != "—")
            for area, panel, results in groups:
                if show_headers:
                    rows.append(Item(f"— {area}" + (f" · {panel}" if panel else ""),
                                     enabled=False))
                for x in results:
                    flag = health.flag(x)
                    mark = {"high": " ▲", "low": " ▼"}.get(flag, "")
                    ref = ref_text(x)
                    name = labs.short_name(x["marker"]) if x.get("parameter_id") else x["marker"]
                    rows.append(Item(f"{name}{mark}",
                                     value=f"{labs.value_text(x)} {x['unit'] or ''}",
                                     detail=(ref + (" · " + x["comment"] if x["comment"]
                                                    else "")),
                                     action=lambda rid=x["id"]: a.push(
                                         LabResultEditor(a, self.report_id, rid))))
        rows += [Item(tr("+ Adicionar resultado", "+ Add result"), action=self._add),
                 Item(tr("Apagar esta análise", "Delete this report"), action=self._delete,
                      enabled=bool(self.report_id), button=True),
                 Item(tr("Guardar", "Save"), action=self._save, button=True, primary=True)]
        self.chrome.set(tr("Análises", "Lab report"), f"{self.done_on} {self.lab}",
                        self.footer())
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        try:
            d = date.fromisoformat(self.done_on)
        except ValueError:
            d = date.today()
        self.done_on = (d + timedelta(days=step)).isoformat()

    def on_text(self, text: str) -> bool:
        if self._field("cyc:") == "date":
            for ch in text:
                if ch not in "0123456789-":
                    continue
                if len(self.done_on) >= 10 or not getattr(self, "_typing", False):
                    self.done_on = ""
                    self._typing = True
                self.done_on += ch
            self.enter()
            return True
        self._typing = False
        return super().on_text(text)

    def text_input(self, field: str, text: str) -> None:
        setattr(self, field, getattr(self, field) + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        setattr(self, field, getattr(self, field)[:-1])
        self.enter()

    def _edit_doctor(self) -> None:
        def save(text):
            self.doctor = text
            self._ensure()
        self.app.push(TextEditScreen(self.app, tr("Comentário do médico", "Doctor's feedback"),
                                     self.done_on, self.doctor, save))

    def _edit_notes(self) -> None:
        def save(text):
            self.notes = text
            self._ensure()
        self.app.push(TextEditScreen(self.app, tr("Notas", "Notes"), self.done_on,
                                     self.notes, save))

    def _add(self) -> None:
        rid = self._ensure()
        self.app.push(MarkerPicker(self.app, rid))

    def _save(self) -> None:
        try:
            date.fromisoformat(self.done_on)
        except ValueError:
            self.app.message(tr("Data inválida: usa AAAA-MM-DD.", "Invalid date: use YYYY-MM-DD."))
            return
        self._ensure()
        self.app.message(tr("Análise guardada", "Report saved"))
        self.app.pop()

    def _delete(self) -> None:
        if not self._armed:
            self._armed = True
            self.app.message(tr("Escolhe outra vez para apagar.", "Choose again to delete."))
            return
        health.delete_lab_report(self.app.db, self.report_id)
        self.app.pop()


def ref_text(x: dict) -> str:
    lo, hi = x.get("ref_low"), x.get("ref_high")
    if lo is not None and hi is not None:
        return f"ref. {lo:g}–{hi:g}"
    if lo is not None:
        return f"ref. > {lo:g}"
    if hi is not None:
        return f"ref. < {hi:g}"
    return tr("sem referência", "no reference")


class MarkerPicker(Screen):
    def __init__(self, app, report_id: int):
        super().__init__(app)
        self.report_id = report_id

    def enter(self) -> None:
        a = self.app
        seen = health.markers_seen(a.db)
        rows = [Item(tr("+ Outro marcador (escrever)", "+ Other marker (type)"),
                     action=lambda: a.replace(LabResultEditor(a, self.report_id, None)))]
        common = {m[0]: m for m in health.COMMON_MARKERS}
        for name in seen + [m for m in common if m not in seen]:
            preset = common.get(name)
            rows.append(Item(name, value=preset[1] if preset else "",
                             action=lambda n=name, p=preset: a.replace(LabResultEditor(
                                 a, self.report_id, None, preset=p or (n, "", None, None)))))
        self.chrome.set(tr("Escolhe o marcador", "Pick the marker"), "", self.footer())
        self.list.set_items(rows, keep_index=True)


class LabResultEditor(EditScreen):
    def __init__(self, app, report_id: int, result_id: int | None, preset: tuple | None = None):
        super().__init__(app)
        self.report_id = report_id
        self.result_id = result_id
        r = None
        if result_id:
            r = next((x for x in health.lab_results(app.db, report_id) if x["id"] == result_id),
                     None)
        if r is None and preset is not None:
            prev = health.marker_history(app.db, preset[0])
            last = prev[-1] if prev else {}
            r = {"marker": preset[0], "unit": last.get("unit") or preset[1],
                 "ref_low": last.get("ref_low", preset[2]),
                 "ref_high": last.get("ref_high", preset[3])}
        r = r or {}
        self.v = {"marker": r.get("marker") or "", "value": r.get("value"),
                  "unit": r.get("unit") or "", "ref_low": r.get("ref_low"),
                  "ref_high": r.get("ref_high"), "comment": r.get("comment") or ""}

    def enter(self) -> None:
        v = self.v

        def n(x):
            return "—" if x is None else f"{x:g}"
        rows = [Item(tr("Marcador", "Marker"), value=v["marker"] or "—", data="text:marker"),
                Item(tr("Valor", "Value"), value=n(v["value"]), data="num:value"),
                Item(tr("Unidade", "Unit"), value=v["unit"] or "—", data="text:unit"),
                Item(tr("Referência mínima", "Reference low"), value=n(v["ref_low"]),
                     data="num:ref_low"),
                Item(tr("Referência máxima", "Reference high"), value=n(v["ref_high"]),
                     data="num:ref_high"),
                Item(tr("Comentário", "Comment"), value=v["comment"] or "—", data="text:comment"),
                Item(tr("Guardar", "Save"), action=self._save, button=True, primary=True),
                Item(tr("Remover", "Remove"), action=self._remove, enabled=bool(self.result_id))]
        self.chrome.set(tr("Resultado", "Result"), v["marker"], self.footer())
        self.list.set_items(rows, keep_index=True)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        cur = self.v[field] or 0.0
        self.v[field] = round(cur + steps * (10 if big else 1), 3)

    def num_set(self, field: str, value: float | None) -> None:
        self.v[field] = value

    def text_input(self, field: str, text: str) -> None:
        self.v[field] += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v[field] = self.v[field][:-1]
        self.enter()

    def _save(self) -> None:
        v = self.v
        if not v["marker"].strip():
            self.app.message(tr("Escreve o nome do marcador.", "Type the marker name."))
            return
        health.save_lab_result(self.app.db, self.result_id, self.report_id,
                               marker=v["marker"].strip(), value=v["value"], unit=v["unit"],
                               ref_low=v["ref_low"], ref_high=v["ref_high"],
                               comment=v["comment"])
        self.app.pop()

    def _remove(self) -> None:
        health.delete_lab_result(self.app.db, self.result_id)
        self.app.pop()


class MarkerHistoryScreen(EditScreen):
    def __init__(self, app):
        super().__init__(app)
        self.idx = 0
        w, h = app.window.width, app.window.height
        self.chart = Chart(96, 112, w - 144, max(140, h - 130 - 2 * 38 - 150))

    def enter(self) -> None:
        ms = health.markers_seen(self.app.db)
        name = ms[self.idx % len(ms)] if ms else None
        self.list.set_items([Item(tr("Marcador", "Marker"), value=name or "—",
                                  data="cyc:marker")])
        self.list.set_visible_rows(2)
        self.chrome.set(tr("Evolução de um marcador", "A marker over time"), "", self.footer())
        self._hist = health.marker_history(self.app.db, name) if name else []
        vals = [x["value"] for x in self._hist if x["value"] is not None]
        labels = [x["done_on"] for x in self._hist if x["value"] is not None]
        if len(vals) >= 2:
            self.chart.show_line(name or "", vals, labels, "", fmt=lambda v: f"{v:g}")
        else:
            self.chart.show_bars(name or "", vals, labels,
                                 tr("Só há uma análise com este marcador.",
                                    "Only one report has this marker."), fmt=lambda v: f"{v:g}")

    def cycle(self, field: str, step: int) -> None:
        self.idx += step

    def agent_data(self) -> dict:
        return {"historico": [{k: x[k] for k in ("done_on", "value", "unit", "ref_low",
                                                 "ref_high")} for x in self._hist]}

    def draw(self) -> None:
        super().draw()
        self.chart.draw()


# ------------------------------------------------------------- importação


class ImportScreen(Screen):
    FOLDERS = ("imports", "~/Downloads", "~/Transferências", "~/Documents", ".")
    PATTERNS = ("*.csv", "*.json", "*.xlsx", "*.xlsm")

    def __init__(self, app, patterns: tuple | None = None):
        super().__init__(app)
        self.create_unknown = False
        self.patterns = patterns or self.PATTERNS

    def folders(self) -> list[Path]:
        out = [self.app.data_dir / "imports"]
        for f in self.FOLDERS:
            out.append(Path(os.path.expanduser(f)))
        return out

    def enter(self) -> None:
        a = self.app
        (a.data_dir / "imports").mkdir(parents=True, exist_ok=True)
        found: list[Path] = []
        for folder in dict.fromkeys(self.folders()):
            if folder.is_dir():
                for pat in self.patterns:
                    found += sorted(folder.glob(pat))[:40]
        rows = [Item(tr("Criar métricas para colunas desconhecidas", "Create metrics for unknown columns"),
                     value=tr("sim", "yes") if self.create_unknown else tr("não", "no"),
                     action=self._toggle),
                Item(tr("Sincronização (GarminDB)", "Sync (GarminDB)"),
                     detail=tr("Trazer os dados do GarminDB: tudo, o mais recente ou um "
                               "intervalo", "Bring in GarminDB data: all, the latest or a range"),
                     action=lambda: a.push(_connect().GarminDBScreen(a)))]
        n_fixed = len(rows)
        for p in dict.fromkeys(found):
            suf = p.suffix.lower()
            kind = "Garmin (JSON)" if suf == ".json" else (
                tr("Análises (Excel)", "Labs (Excel)") if suf in (".xlsx", ".xlsm") else
                "HRV4Training" if "hrv" in p.name.lower() or "measurement" in p.name.lower()
                else "CSV")
            rows.append(Item(p.name, value=kind, detail=str(p.parent),
                             action=lambda q=p: self._import(q)))
        if len(rows) == n_fixed:
            rows.append(Item(tr("Nenhum ficheiro encontrado", "No files found"), enabled=False,
                             detail=tr("Põe os ficheiros em {p}", "Put the files in {p}",
                                       p=a.data_dir / "imports")))
        rows += [
            Item(tr("Como exportar do HRV4Training", "How to export from HRV4Training"),
                 detail=tr("Na app: exportar as medições (CSV) para o Google Drive; descarrega "
                           "o ficheiro para Transferências.",
                           "In the app: export measurements (CSV) to Google Drive; download it."),
                 enabled=False),
            Item(tr("Como exportar do Garmin", "How to export from Garmin"),
                 detail=tr("Garmin Connect (web): Gestão de dados → Exportar dados; descompacta "
                           "e põe os JSON diários na pasta imports.",
                           "Garmin Connect (web): Data Management → Export; unzip into imports."),
                 enabled=False),
        ]
        self.chrome.set(tr("Importar dados", "Import data"),
                        tr("CSV do HRV4Training, JSON do Garmin, ou qualquer CSV com uma coluna de data",
                           "HRV4Training CSV, Garmin JSON, or any CSV with a date column"),
                        self.footer())
        self.list.set_items(rows, keep_index=True)

    def _toggle(self) -> None:
        self.create_unknown = not self.create_unknown
        self.enter()

    def _import(self, path: Path) -> None:
        try:
            rep = health.import_file(self.app.db, path, create_unknown=self.create_unknown)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        self.last_report = rep
        if "results" in rep:                                  # Excel das análises
            self.app.message(tr("{r} análises · {n} resultados · {p} parâmetros",
                                "{r} reports · {n} results · {p} parameters",
                                r=rep["reports"], n=rep["results"], p=rep["parameters"]))
            return
        msg = tr("{v} valores em {d} dias", "{v} values over {d} days", v=rep["values"],
                 d=rep["days"])
        if rep.get("created"):
            msg += tr(" · {n} métricas novas", " · {n} new metrics", n=len(rep["created"]))
        if rep.get("ignored"):
            msg += tr(" · ignoradas: {c}", " · ignored: {c}", c=", ".join(rep["ignored"][:6]))
        self.app.message(msg)
        self.last_report = rep


# ================================================================== testes


def sport_name(s: str) -> str:
    return {"cycling": t("home.cycling"), "rowing": t("home.rowing"),
            "running": t("home.running"), "swimming": tr("Natação", "Swimming"),
            "longevity": tr("Longevidade", "Longevity")}.get(s, s)


class TestsMenu(Screen):
    """Testes de aptidão de uma modalidade: último, melhor e tendência."""

    def __init__(self, app, sport: str):
        super().__init__(app)
        self.sport = sport

    def enter(self) -> None:
        a = self.app
        ft.seed(a.db)
        if self.sport == "rowing":
            from velo.core import rowing as rw
            rw.link_tests(a.db)
        if self.sport == "swimming":
            from velo.core import endurance as en
            en.seed(a.db)
        rows = []
        if self.sport == "cycling":
            rows.append(Item(t("menu.ftp_test"), value=f"FTP {a.db.athlete().ftp_w} W",
                             detail=tr("os três protocolos de FTP", "the three FTP protocols"),
                             action=lambda: a.push(FtpScreen(a))))
        for x in ft.tests(a.db, self.sport):
            trend = {"up": " ↑", "down": " ↓", "same": " ="}.get(x["trend"] or "", "")
            rows.append(Item(x["name"], value=(ft.fmt_value(x["last"], x["unit"]) + trend)
                             if x["n"] else "—",
                             detail=(tr("melhor {b} · {n} vezes · último {d}",
                                        "best {b} · {n} times · last {d}",
                                        b=ft.fmt_value(x["best"], x["unit"]), n=x["n"],
                                        d=x["last_on"]) if x["n"] else _excerpt(x["instructions"], 90)),
                             action=lambda tid=x["id"]: a.push(TestDetail(a, tid))))
        rows.append(Item(tr("+ Novo teste", "+ New test"),
                         action=lambda: a.push(TestEditor(a, None, self.sport))))
        self.chrome.set(tr("Testes · {s}", "Tests · {s}", s=sport_name(self.sport)),
                        tr("Escolhe um teste para o fazer, registar ou editar.",
                           "Pick a test to run, log or edit."), self.footer())
        self.list.set_items(rows, keep_index=True)


class TestDetail(Screen):
    def __init__(self, app, test_id: int):
        super().__init__(app)
        self.test_id = test_id
        self._armed = None

    def enter(self) -> None:
        a = self.app
        x = ft.test(a.db, self.test_id)
        if x is None:
            a.pop()
            return
        s = ft.summary(a.db, x)
        rows = []
        if x["protocol"] and str(x["protocol"]).startswith("row_"):
            from velo.ui import rowing_screens as rs
            rows.append(Item(tr("▶ Fazer o teste na máquina de remo",
                                "▶ Run the test on the rowing machine"),
                             action=lambda: rs.start_session(a, protocol=x["protocol"])))
        elif x["protocol"]:
            rows.append(Item(tr("▶ Fazer o teste no rolo", "▶ Run the test on the trainer"),
                             action=lambda: a.push(FtpRouteChoice(a, x["protocol"]))))
        else:
            rows.append(Item(tr("▶ Fazer o teste", "▶ Run the test"),
                             detail=tr("com cronómetro", "with a timer"),
                             action=lambda: a.push(TestRunScreen(a, self.test_id))))
        rows += [Item(tr("Registar um resultado", "Log a result"),
                      action=lambda: a.push(TestRunScreen(a, self.test_id, timer=False))),
                 Item(tr("Editar o teste", "Edit the test"),
                      action=lambda: a.push(TestEditor(a, self.test_id, x["sport"]))),
                 Item(tr("Desativar (deixa de aparecer)", "Deactivate (hide it)"),
                      action=self._deactivate)]
        rows.append(Item(tr("Instruções", "Instructions"), detail=_excerpt(x["instructions"], 120),
                         enabled=False))
        for r in ft.results(a.db, self.test_id):
            rows.append(Item(r["done_on"], value=ft.fmt_value(r["value"], x["unit"]),
                             detail=_excerpt(r["notes"], 90), data=("result", r["id"])))
        best = ft.fmt_value(s["best"], x["unit"]) if s["n"] else "—"
        self.chrome.set(x["name"], tr("Melhor: {b} · {n} resultados · Del apaga um resultado",
                                      "Best: {b} · {n} results · Del deletes a result",
                                      b=best, n=s["n"]), self.footer())
        self.list.set_items(rows, keep_index=True)

    def _deactivate(self) -> None:
        ft.set_active(self.app.db, self.test_id, False)
        self.app.pop()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.DELETE and item is not None and isinstance(item.data, tuple):
            rid = item.data[1]
            if self._armed == rid:
                ft.delete_result(self.app.db, rid)
                self.enter()
            else:
                self._armed = rid
                self.app.message(t("str.delete_again"))
            return True
        return super().on_key(symbol, modifiers)


class TestRunScreen(EditScreen):
    """Cronómetro do teste (contagem decrescente se tiver duração; se o
    resultado for um tempo, o cronómetro dá-o) e registo do resultado."""

    AGENT = False

    def __init__(self, app, test_id: int, timer: bool = True):
        super().__init__(app)
        self.test = ft.test(app.db, test_id)
        self.timer = timer
        self.running = False
        self.elapsed = 0.0
        self.value: float | None = None
        self.notes = ""
        self.done_on = date.today().isoformat()
        self.batch = pyglet.graphics.Batch()
        self.big = make_label("", font_size=56, bold=True, color=ACCENT, anchor_x="center",
                              anchor_y="center", batch=self.batch)
        self.hint = make_label("", font_size=13, color=DIM, anchor_x="center", batch=self.batch)

    @property
    def countdown(self) -> bool:
        return bool(self.test["duration_s"])

    def enter(self) -> None:
        x = self.test
        rows = []
        if self.timer:
            rows.append(Item((tr("■ Parar", "■ Stop") if self.running else
                              tr("▶ Começar", "▶ Start")) + tr(" (Espaço)", " (Space)"),
                             action=self._toggle))
        rows += [Item(tr("Resultado", "Result"), value=ft.fmt_value(self.value, x["unit"]),
                      data="num:value", detail=tr("escreve o número ({u})", "type the number ({u})",
                                                  u=x["unit"])),
                 Item(tr("Data", "Date"), value=self.done_on, data="text:done_on"),
                 Item(tr("Notas", "Notes"), value=self.notes or "—", data="text:notes"),
                 Item(tr("Guardar o resultado", "Save the result"), action=self._save, button=True,
                      primary=True)]
        self.chrome.set(x["name"], _excerpt(x["instructions"], 140), self.footer())
        self.list.set_items(rows, keep_index=True)
        self._layout()

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        self.big.x, self.big.y = w * 0.72, h * 0.55
        self.hint.x, self.hint.y = w * 0.72, h * 0.55 - 70

    def _list_width(self, w: int) -> int:
        return int(w * 0.5)

    def _toggle(self) -> None:
        if not self.running:
            self.running, self.elapsed = True, 0.0
        else:
            self.running = False
            if self.test["unit"] == "s" and not self.countdown:
                self.value = round(self.elapsed, 1)
        self.enter()

    def update(self, dt: float) -> None:
        if self.running:
            self.elapsed += dt
            if self.countdown and self.elapsed >= self.test["duration_s"]:
                self.running = False
                self.elapsed = float(self.test["duration_s"])
                self.app.message(tr("Tempo! Escreve o resultado.", "Time! Type the result."))
                self.list.index = 1
                self.enter()
        if self.timer:
            if self.countdown:
                left = max(0.0, self.test["duration_s"] - self.elapsed)
                self.big.text = hms(left) if left >= 60 else f"{left:.0f}"
                self.hint.text = tr("contagem decrescente", "countdown")
            else:
                self.big.text = f"{self.elapsed:.1f} s" if self.elapsed < 60 else hms(self.elapsed)
                self.hint.text = tr("cronómetro", "stopwatch")
        else:
            self.big.text = ""
            self.hint.text = ""

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.SPACE and self.timer and self._field("text:") is None:
            self._toggle()
            return True
        return super().on_key(symbol, modifiers)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        self.value = max(0.0, (self.value or 0) + steps * (10 if big else 1))

    def num_set(self, field: str, value: float | None) -> None:
        self.value = value

    def text_input(self, field: str, text: str) -> None:
        setattr(self, field, getattr(self, field) + text)
        self.enter()

    def text_backspace(self, field: str) -> None:
        setattr(self, field, getattr(self, field)[:-1])
        self.enter()

    def _save(self) -> None:
        if self.value is None:
            self.app.message(tr("Falta o resultado.", "The result is missing."))
            return
        try:
            date.fromisoformat(self.done_on)
        except ValueError:
            self.app.message(tr("Data inválida: usa AAAA-MM-DD.", "Invalid date: use YYYY-MM-DD."))
            return
        extra = None
        if "Cooper" in self.test["name"]:
            extra = {"vo2max": round(ft.vo2max_cooper(self.value), 1)}
        ft.add_result(self.app.db, self.test["id"], self.value, done_on=self.done_on,
                      notes=self.notes or None, extra=extra)
        self.app.message(tr("Resultado guardado: {v}", "Result saved: {v}",
                            v=ft.fmt_value(self.value, self.test["unit"])))
        self.app.pop()

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


class TestEditor(EditScreen):
    def __init__(self, app, test_id: int | None, sport: str):
        super().__init__(app)
        self.test_id = test_id
        x = ft.test(app.db, test_id) if test_id else None
        self.sport = x["sport"] if x else sport
        self.name = x["name"] if x else ""
        self.unit = x["unit"] if x else "reps"
        self.better = x["better"] if x else "higher"
        self.duration = x["duration_s"] if x else 0
        self.instructions = (x or {}).get("instructions") or ""
        self.protocol = (x or {}).get("protocol")

    def enter(self) -> None:
        rows = [Item(tr("Nome", "Name"), value=self.name or "—", data="text:name"),
                Item(tr("Unidade", "Unit"), value=self.unit, data="cyc:unit"),
                Item(tr("Melhor é", "Better is"),
                     value=tr("mais alto", "higher") if self.better == "higher"
                     else tr("mais baixo", "lower"), data="cyc:better"),
                Item(tr("Duração (s, 0 = sem tempo)", "Duration (s, 0 = untimed)"),
                     value=str(self.duration), data="num:duration"),
                Item(tr("Instruções", "Instructions"), value=_excerpt(self.instructions, 50) or "—",
                     action=self._edit_instr),
                Item(tr("Guardar", "Save"), action=self._save, button=True, primary=True)]
        self.chrome.set(tr("Teste", "Test"), sport_name(self.sport), self.footer())
        self.list.set_items(rows, keep_index=True)

    def cycle(self, field: str, step: int) -> None:
        if field == "unit":
            us = list(ft.UNITS)
            self.unit = us[(us.index(self.unit) + step) % len(us)] if self.unit in us else us[0]
        else:
            self.better = "lower" if self.better == "higher" else "higher"

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        self.duration = max(0, self.duration + steps * (60 if big else 10))

    def num_set(self, field: str, value: float | None) -> None:
        self.duration = int(value or 0)

    def text_input(self, field: str, text: str) -> None:
        self.name += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.name = self.name[:-1]
        self.enter()

    def _edit_instr(self) -> None:
        def save(text):
            self.instructions = text
        self.app.push(TextEditScreen(self.app, tr("Instruções", "Instructions"), self.name,
                                     self.instructions, save))

    def _save(self) -> None:
        if not self.name.strip():
            self.app.message(tr("Dá um nome ao teste.", "Give the test a name."))
            return
        ft.save_test(self.app.db, self.test_id, sport=self.sport, name=self.name,
                     unit=self.unit, better=self.better, duration_s=self.duration,
                     instructions=self.instructions, protocol=self.protocol)
        self.app.pop()
