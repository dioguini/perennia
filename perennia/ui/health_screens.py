"""Saúde (diário, métricas, análises, importação), testes de aptidão e o ecrã
do agente de IA."""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pyglet
from pyglet.window import key

from perennia.core import agent as agent_mod
from perennia.core import fitness_tests as ft
from perennia.core import health
from perennia.core import labs
from perennia.core.i18n import t, tr
from perennia.core.units import hms, parse_number
from perennia.gfx.compat import label as make_label
from perennia.ui.app import FtpRouteChoice, Screen, SnapshotUnsaved
from perennia.ui.goal_popup import GoalPopup
from perennia.ui.sport_screens import EditPopup, EditScreen
from perennia.ui.widgets import ACCENT, BAD, Chart, DIM, GOOD, PANEL, TEXT, Item

WEEKDAYS_PT = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _connect():
    from perennia.ui import connect_screens
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
    """«Resumo desta página» (F1) e «resumo contextualizado» (F2). Antes de enviar mostra **o que
    vai ser enviado e quantos tokens gasta** (estimativa local, por partes), o limite da
    resposta e o custo máximo (se os preços estiverem nas Definições). Enquanto o agente não
    estiver ligado, só se vê o pedido."""

    AGENT = False
    HEAD_KEYS = {"system": ("Instruções do sistema", "System instructions"),
                 "instruction": ("O pedido", "The request"),
                 "page": ("Esta página", "This page"),
                 "ctx:data": ("Data", "Date"),
                 "ctx:atleta": ("Perfil do atleta", "Athlete profile"),
                 "ctx:carga": ("Treino e forma", "Training and form"),
                 "ctx:forca": ("Força", "Strength"),
                 "ctx:diario": ("Diário (saúde e alimentação)", "Daily log (health and food)"),
                 "ctx:analises": ("Análises clínicas", "Lab results"),
                 "ctx:testes": ("Testes de longevidade", "Longevity tests")}
    CATEGORY_NAMES = {"training": ("Treino e forma", "Training and form"),
                      "strength": ("Força", "Strength"),
                      "health": ("Saúde (sono, HRV, FC em repouso…)", "Health (sleep, HRV…)"),
                      "food": ("Alimentação", "Food"),
                      "labs": ("Análises clínicas", "Lab results"),
                      "tests": ("Testes de longevidade", "Longevity tests")}

    @classmethod
    def open(cls, app, source, kind: str) -> None:
        app.push(cls(app, source, kind))

    def __init__(self, app, source, kind: str):
        super().__init__(app)
        self.kind = kind
        self.source = source
        self.request = agent_mod.build_request(kind, source, app.db)
        self.source_name = type(source).__name__

    def _rebuild(self) -> None:
        self.request = agent_mod.build_request(self.kind, self.source, self.app.db)

    def _toggle_category(self, cat: str) -> None:
        share = set(agent_mod.allowed(self.app.db))
        share ^= {cat}
        agent_mod.set_categories(self.app.db, sorted(share))
        self._rebuild()
        self.enter()

    @staticmethod
    def _n(v: int) -> str:
        return f"{v:,}".replace(",", " ")

    def _token_rows(self, rep: dict) -> list[Item]:
        n = self._n
        warn = rep["warn"]
        rows = [Item(tr("— Tokens deste pedido (estimativa) —", "— Tokens in this request "
                        "(estimate) —"), enabled=False),
                Item(tr("Total que seria enviado", "Total that would be sent"),
                     value=f"≈ {n(rep['total'])} tokens",
                     detail=(tr("pedido grande (acima de {w}): desliga categorias mais abaixo",
                                "large request (over {w}): turn categories off below",
                                w=n(rep["warn_at"])) if warn else
                             tr("estimativa local, antes de enviar; a contagem exata só o "
                                "fornecedor a dá, quando estiver ligado",
                                "local estimate, before sending; only the provider gives the "
                                "exact count, once connected")),
                     enabled=False)]
        for name, tokens in rep["parts"]:
            label = tr(*self.HEAD_KEYS.get(name, (name, name)))
            rows.append(Item(label, value=f"≈ {n(tokens)}", enabled=False, indent=1))
        rows.append(Item(tr("Resposta: no máximo", "Reply: at most"),
                         value=tr("{n} tokens", "{n} tokens", n=n(rep["max_output"])),
                         detail=tr("Definições → Avançado", "Settings → Advanced"),
                         enabled=False))
        if rep["priced"]:
            cur = rep["currency"]
            rows.append(Item(tr("Custo máximo estimado", "Estimated maximum cost"),
                             value=f"{cur} {rep['max_cost']:.4f}",
                             detail=tr("envio {a} + resposta no máximo {b} · preços das Definições",
                                       "input {a} + reply at most {b} · prices from Settings",
                                       a=f"{cur} {rep['cost_in']:.4f}",
                                       b=f"{cur} {rep['cost_out_max']:.4f}"), enabled=False))
        else:
            rows.append(Item(tr("Custo estimado", "Estimated cost"), value="—",
                             detail=tr("define o preço por milhão de tokens nas Definições "
                                       "(Avançado) para ver o custo",
                                       "set the price per million tokens in Settings "
                                       "(Advanced) to see the cost"), enabled=False))
        return rows

    def enter(self) -> None:
        a = self.app
        prov = agent_mod.provider(a.db)
        title = tr("Resumo desta página", "Summary of this page") if self.kind == "page" \
            else tr("Resumo contextualizado", "Contextual summary")
        rep = agent_mod.token_report(self.request, a.db)
        if prov["ready"]:
            head = tr("O agente está configurado, mas a ligação ainda não foi ativada nesta "
                      "versão.", "The agent is configured, but calls are not enabled yet.")
        else:
            head = tr("O agente de IA ainda não está ligado. É isto que lhe seria enviado:",
                      "The AI agent is not connected yet. This is what would be sent:")
        items = [Item(head, enabled=False)] + self._token_rows(rep)
        if self.kind == "context":
            share = agent_mod.allowed(a.db)
            items.append(Item(tr("— Categorias partilhadas (Enter liga/desliga) —",
                                 "— Shared categories (Enter toggles) —"), enabled=False))
            for cat in agent_mod.CATEGORIES:
                items.append(Item(("✓ " if cat in share else "   ") +
                                  tr(*self.CATEGORY_NAMES[cat]),
                                  detail=tr("nada do Strava, nunca", "never anything from Strava")
                                  if cat == "training" else "",
                                  action=lambda c=cat: self._toggle_category(c)))
        items.append(Item(tr("— O que seria enviado —", "— What would be sent —"), enabled=False))
        items.append(Item(tr("Pedido", "Request"), value=_excerpt(self.request["instruction"], 90),
                          enabled=False))
        for k, v in agent_mod.flatten(self.request["content"]):
            items.append(Item(k, value=_excerpt(v, 60), enabled=False))
        items.append(Item(tr("Voltar", "Back"), button=True, action=self.app.pop))
        items.append(Item(tr("Enviar ao agente", "Send to the agent"), button=True, primary=True,
                           action=self._send, enabled=bool(prov["ready"])))
        share_txt = ", ".join(sorted(agent_mod.allowed(a.db)))
        self.chrome.set(title, tr("Categorias partilhadas: {s} · nada do Strava",
                                  "Shared categories: {s} · nothing from Strava", s=share_txt),
                        tr("↑↓ percorrer · Esc voltar", "↑↓ scroll · Esc back"))
        self.list.set_items(items, keep_index=True)

    def _send(self) -> None:
        """Pede confirmação com os tokens à vista. (A chamada em si ainda não está ativa.)"""
        a = self.app
        rep = agent_mod.token_report(self.request, a.db)
        cost = (f" · {rep['currency']} {rep['max_cost']:.4f} " + tr("no máximo", "at most")
                if rep["priced"] else "")
        from perennia.ui.app import ConfirmScreen

        def go() -> None:
            a.pop()
            a.message(tr("A ligação ao agente ainda não está ativa nesta versão.",
                         "The connection to the agent is not active in this version yet."))
        a.push(ConfirmScreen(a, tr("Enviar ≈ {n} tokens?", "Send ≈ {n} tokens?",
                                   n=self._n(rep["total"])),
                             tr("Resposta até {m} tokens", "Reply up to {m} tokens",
                                m=self._n(rep["max_output"])) + cost,
                             [(tr("Cancelar", "Cancel"), a.pop), (tr("Enviar", "Send"), go)],
                             default=0, buttons=True, cancel=a.pop))


# ================================================================== saúde


class _ChromeProxy:
    """O título de um ecrã metido num separador fica o do ecrã de fora."""

    def __init__(self, host):
        self._host = host

    def set(self, title: str, subtitle: str = "", footer: str = "") -> None:
        self._host.chrome.set(self._host.TITLE(), (title + " · " + subtitle).strip(" ·"),
                              footer)

    def __getattr__(self, name):
        return getattr(self._host.chrome, name)


class HealthMenu(Screen):
    """A Saúde por separadores: Análises (o report de cada colheita) · Diários ·
    Tendências · Métricas. Os testes de longevidade passaram para o menu Longevidade."""

    TABBED = True
    # os separadores fixos; a seguir vêm os que criaste (`health_tabs`), um por cada
    TAB_KEYS = ("labs", "diary", "trends", "metrics", "bp", "assistant")
    CUSTOM = "tab:"

    @staticmethod
    def TITLE() -> str:
        return tr("Saúde", "Health")

    def tab_keys(self) -> list[str]:
        from perennia.core import health_tabs
        return list(self.TAB_KEYS) + [self.CUSTOM + t_["key"]
                                      for t_ in health_tabs.tabs(self.app.db)]

    def tab_key(self) -> str:
        keys = self.tab_keys()
        return keys[self.tab % len(keys)]

    def refresh_tabs(self, select: str | None = None) -> None:
        """Depois de criar, mudar o nome ou apagar um separador teu."""
        keys = self.tab_keys()
        if self.tabs is not None:
            self.tabs.set_labels(self.tab_labels())
        if select in keys:
            self.tab = keys.index(select)
        self.tab = min(self.tab, len(keys) - 1)
        if self.tabs is not None:
            self.tabs.select(self.tab)
        self.list.index = 0
        self.inner = None
        self.on_resize(self.app.window.width, self.app.window.height)
        self.enter()

    def __init__(self, app, tab: int = 0, report_id: int | None = None):
        super().__init__(app)
        self.inner = None
        self.report_id = report_id
        self.tab = tab
        if self.tabs is not None:
            self.tabs.select(tab)

    def tab_labels(self) -> list[str]:
        from perennia.core import health_tabs
        fixed = {"labs": tr("Análises", "Lab results"), "diary": tr("Diários", "Daily logs"),
                 "trends": tr("Tendências", "Trends"), "metrics": tr("Métricas", "Metrics"),
                 "bp": tr("Pressão arterial", "Blood pressure"),
                 "assistant": tr("Assistente de saúde", "Health assistant")}
        return [fixed[k] for k in self.TAB_KEYS] + [t_["name"]
                                                   for t_ in health_tabs.tabs(self.app.db)]

    def on_tab(self) -> None:
        self.inner = None

    def _embed(self, cls, *args):
        """Um ecrã de lista dentro do separador: partilha a lista e o título."""
        if not isinstance(self.inner, cls):
            inner = cls(self.app, *args)
            inner.list = self.list
            inner.chrome = _ChromeProxy(self)
            inner.back_button = None
            self.inner = inner
        return self.inner

    def enter(self) -> None:
        a = self.app
        health.seed(a.db)
        ft.seed(a.db)
        k = self.tab_key()
        self.list.detail_below = False       # os separadores com textos compridos ligam-no
        if k == "labs":
            self.inner = None
            self._labs()
        elif k == "diary":
            self.inner = None
            self._diary()
        elif k == "trends":
            self.inner = None
            self._trends()
        elif k == "metrics":
            self._embed(MetricsManager).enter()
        else:
            from perennia.ui import health_extra_screens as hx
            self.inner = None
            if k == "bp":
                hx.bp_tab(self)
            elif k == "assistant":
                hx.assistant_tab(self)
            else:
                hx.custom_tab(self, k[len(self.CUSTOM):])

    # --------------------------------------------------------- diários

    def _diary(self) -> None:
        a = self.app
        today = date.today()
        rows = [Item(tr("Outro dia…", "Another day…"),
                     detail=tr("abre o calendário", "opens the calendar"),
                     action=self._pick_day)]
        for k in range(21):
            d = today - timedelta(days=k)
            done, total = health.completeness(a.db, d)
            note = health.day_note(a.db, d)
            rows.append(Item(day_label(d), value=f"{done}/{total}",
                             detail=_excerpt(note, 80) if note else "",
                             action=lambda dd=d: a.push(DailyLogScreen(a, dd))))
        from perennia.ui import health_extra_screens as hx
        rows.append(hx.new_tab_button(self))
        self.chrome.set(self.TITLE(), tr("Os diários dos últimos dias · Enter abre o dia",
                                         "The last days' logs · Enter opens the day"),
                        self.footer())
        self.list.set_items(rows, keep_index=True)

    def _pick_day(self) -> None:
        from perennia.ui.pickers import pick_date
        pick_date(self.app, tr("Diário de que dia?", "Log for which day?"), date.today(),
                  lambda iso: self.app.push(DailyLogScreen(self.app, date.fromisoformat(iso))),
                  max_day=date.today())

    # ------------------------------------------------------- tendências

    def _trends(self) -> None:
        a = self.app
        rows = []
        ms = [m for m in health.metrics(a.db) if m["kind"] in ("number", "scale", "bool")]
        for i, m in enumerate(ms):
            pts = health.series(a.db, m["id"], 30)
            vals = [v for _d, v in pts if v is not None]
            last = f"{vals[-1]:g}" if vals else "—"
            rows.append(Item(m["name"], value=last + (f" {m['unit']}" if m["unit"] and vals
                                                     else ""),
                             detail=tr("{n} registos nos últimos 30 dias · Enter abre o gráfico",
                                       "{n} entries in the last 30 days · Enter opens the chart",
                                       n=len(vals)),
                             action=lambda k=i: self._open_trend(k)))
        self.chrome.set(self.TITLE(), tr("A evolução de cada métrica do diário",
                                         "Each log metric over time"), self.footer())
        self.list.set_items(rows, keep_index=True)

    def _open_trend(self, k: int) -> None:
        scr = MetricTrendScreen(self.app)
        scr.metric_idx = k
        self.app.push(scr)

    # -------------------------------------------------------- análises

    def _labs(self) -> None:
        """Análises: a lista das colheitas; Enter numa colheita abre o relatório dela,
        com os botões em baixo (Comentário geral do médico, Editar…)."""
        a = self.app
        labs.ensure(a.db)
        reps = health.lab_reports(a.db)
        if self.report_id not in [r["id"] for r in reps]:
            self.report_id = None
        if self.report_id is None:
            self._labs_list(reps)
            return
        r = health.lab_report(a.db, self.report_id)
        rows: list[Item] = []
        n_out = next((x["out_of_range"] for x in reps if x["id"] == r["id"]), 0)
        if n_out:
            rows.append(Item(tr("Fora do intervalo", "Out of range"), value=str(n_out),
                             detail=tr("marcados com ▲ (alto) ou ▼ (baixo)",
                                       "marked ▲ (high) or ▼ (low)"), enabled=False))
        if r.get("doctor_feedback"):
            rows.append(Item(tr("Comentário do médico", "Doctor's comment"),
                             detail=_excerpt(r.get("doctor_feedback"), 160), enabled=False))
        for area, panel, results in labs.grouped_results(a.db, r["id"]):
            head = area if area and area != "—" else tr("Resultados", "Results")
            rows.append(Item(head + (f" · {panel}" if panel else ""), header=True))
            for x in results:
                rows.append(self._result_row(r, x))
        rows += [Item(tr("Colheitas", "Collections"), button=True, action=self._labs_back),
                 Item(tr("Catálogo", "Catalog"), button=True,
                      action=lambda: a.push(ParameterCatalog(a))),
                 Item(tr("Assistente de saúde", "Health assistant"), button=True,
                      action=self._labs_assistant),
                 Item(tr("Comentário geral do médico", "Doctor's general comment"), button=True,
                      action=self._edit_general),
                 Item(tr("Editar esta colheita", "Edit this collection"), button=True,
                      primary=True, action=lambda: a.push(LabReportEditor(a, self.report_id)))]
        self.chrome.set(self.TITLE(),
                        f"{r['done_on']}" + (f" · {r['lab']}" if r.get("lab") else "") + " · "
                        + tr("valor atual e os 3 anteriores · Enter num resultado escreve o "
                             "comentário do médico", "current value and the 3 before · Enter "
                             "on a result writes the doctor's comment"), self.footer())
        self.list.set_items(rows, keep_index=True)

    def _labs_list(self, reps: list[dict]) -> None:
        a = self.app
        rows: list[Item] = []
        for r in reps:
            bits = [r["lab"]] if r.get("lab") else []
            if r["out_of_range"]:
                bits.append(tr("{n} fora do intervalo", "{n} out of range", n=r["out_of_range"]))
            if r.get("doctor_feedback"):
                bits.append("🩺 " + _excerpt(r["doctor_feedback"], 50))
            rows.append(Item(r["done_on"], value=tr("{n} resultados", "{n} results", n=r["n"]),
                             detail=" · ".join(bits),
                             action=lambda rid=r["id"]: self._open_report(rid),
                             data=("report", r["id"])))
        if not reps:
            rows.append(Item(tr("Ainda não há análises", "No lab results yet"),
                             detail=tr("cria uma (botão em baixo) ou importa do Excel/CSV",
                                       "create one (button below) or import from Excel/CSV"),
                             enabled=False))
        from perennia.ui import health_extra_screens as hx
        rows += [hx.new_tab_button(self),
                 Item(tr("Catálogo", "Catalog"), button=True,
                      action=lambda: a.push(ParameterCatalog(a))),
                 Item(tr("+ Nova análise", "+ New lab report"), button=True, primary=True,
                      action=lambda: a.push(LabReportEditor(a, None)))]
        self.chrome.set(self.TITLE(), tr("As colheitas · Enter abre o relatório de uma",
                                         "The collections · Enter opens one's report"),
                        self.footer())
        self.list.set_items(rows, keep_index=True)

    def _labs_assistant(self) -> None:
        """O que o Assistente de saúde lê nesta colheita (o que existe para o médico fica)."""
        from perennia.ui import health_extra_screens as hx
        hx.open_component(self.app, "labs", report_id=self.report_id)

    def _open_report(self, report_id: int) -> None:
        self.report_id = report_id
        self.list.index = 0
        self.enter()

    def _labs_back(self) -> None:
        self.report_id = None
        self.list.index = 0
        self.enter()

    def go_back(self) -> None:
        """Esc ou «Voltar»: dentro de uma colheita volta à lista das colheitas."""
        if self.tab_key() == "labs" and self.report_id is not None:
            self._labs_back()
            return
        super().go_back()

    def _result_row(self, r: dict, x: dict) -> Item:
        flag = health.flag(x)
        mark = {"high": " ▲", "low": " ▼"}.get(flag, "")
        name = labs.short_name(x["marker"]) if x.get("parameter_id") else x["marker"]
        prev = labs.previous_values(self.app.db, x["marker"], r["done_on"], 3)
        bits = []
        for p in prev:
            d = str(p["done_on"])
            bits.append(f"{labs.value_text(p)} ({d[8:10]}/{d[5:7]}/{d[2:4]})")
        trend = ""
        if prev and x.get("value") is not None and prev[0].get("value") is not None:
            diff = x["value"] - prev[0]["value"]
            trend = " ↑" if diff > 0 else " ↓" if diff < 0 else " ="
        detail = (tr("antes: ", "before: ") + " · ".join(bits) if bits
                  else tr("primeira vez", "first time")) + " · " + ref_text(x)
        if x.get("doctor_comment"):
            detail = "🩺 " + _excerpt(x["doctor_comment"], 60) + " · " + detail
        return Item(f"{name}{mark}", value=f"{labs.value_text(x)} {x['unit'] or ''}{trend}",
                    detail=detail, action=lambda rid=x["id"], nm=name: self._edit_comment(
                        rid, nm), data=("result", x["id"]))

    def _edit_general(self) -> None:
        r = health.lab_report(self.app.db, self.report_id)

        def save(text: str) -> None:
            health.save_lab_report(self.app.db, r["id"], done_on=r["done_on"],
                                   lab=r.get("lab") or "", notes=r.get("notes") or "",
                                   doctor_feedback=text)
        self.app.push(TextEditScreen(self.app, tr("Comentário geral do médico",
                                                  "Doctor's general comment"),
                                     r["done_on"], r.get("doctor_feedback") or "", save))

    def _edit_comment(self, result_id: int, name: str) -> None:
        row = self.app.db.conn.execute("SELECT doctor_comment FROM lab_results WHERE id = ?",
                                       (result_id,)).fetchone()
        self.app.push(TextEditScreen(self.app, tr("Comentário do médico", "Doctor's comment"),
                                     name, (row["doctor_comment"] if row else "") or "",
                                     lambda text: labs.set_doctor_comment(self.app.db,
                                                                          result_id, text)))

    # -------------------------------------------------------- teclado

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.inner is not None and symbol != key.TAB:
            return self.inner.on_key(symbol, modifiers)
        return super().on_key(symbol, modifiers)

    def on_text(self, text: str) -> bool:
        if self.inner is not None:
            return self.inner.on_text(text)
        return super().on_text(text)


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
            if m["key"] in ("bp_sys", "bp_dia"):
                # a pressão arterial tem várias medições por dia: uma linha que as abre
                if m["key"] == "bp_sys":
                    from perennia.ui import health_extra_screens as hx
                    rows.append(hx.diary_bp_row(self.app, self.day))
                continue
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


class TextEditScreen(GoalPopup):
    """Texto livre com várias linhas (notas, comentário do médico, instruções),
    **numa janela**: Enter muda de linha, Ctrl+S ou Guardar grava, Esc cancela
    (com alterações pergunta primeiro)."""

    def __init__(self, app, title: str, subtitle: str, text: str, on_save):
        super().__init__(app, title, subtitle, text, 4000, on_save, multiline=True)


class MetricsManager(Screen):
    """As métricas do diário. Enter edita; A liga/desliga; ←/→ muda a ordem."""

    def enter(self) -> None:
        a = self.app
        rows = []
        for m in health.metrics(a.db, include_inactive=True):
            rows.append(Item(("✓ " if m["active"] else "✗ ") + m["name"],
                             value=kind_name(m["kind"]) + (f" · {m['unit']}" if m["unit"] else ""),
                             detail=group_name(m["grp"]),
                             action=lambda mid=m["id"]: a.push(MetricEditor(a, mid)),
                             data=("metric", m["id"], m["active"])))
        n = len(rows)
        rows.append(Item(tr("+ Nova métrica", "+ New metric"), button=True, primary=True,
                         action=lambda: a.push(MetricEditor(a, None))))
        self.chrome.set(tr("Métricas do diário", "Log metrics"), f"{n}",
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


class MetricEditor(EditPopup):
    """Uma métrica do diário, numa janela."""

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

    def state(self):
        return (self.name, self.kind, self.unit, self.group, self.choices, self.active)

    def title(self) -> str:
        return tr("Métrica", "Metric") if self.metric_id else tr("Nova métrica", "New metric")

    def subtitle(self) -> str:
        return self.name

    def rows(self) -> list[Item]:
        rows = [Item(tr("Nome", "Name"), value=self.name or "—", data="text:name"),
                Item(tr("Tipo", "Type"), value=kind_name(self.kind), data="cyc:kind"),
                Item(tr("Unidade", "Unit"), value=self.unit or "—", data="text:unit"),
                Item(tr("Grupo", "Group"), value=group_name(self.group), data="cyc:group")]
        if self.kind == "choice":
            rows.append(Item(tr("Opções (separadas por vírgulas)", "Options (comma separated)"),
                             value=self.choices or "—", data="text:choices"))
        rows += [Item(tr("Ativa", "Active"), value=tr("sim", "yes") if self.active
                      else tr("não", "no"), data="cyc:active")]
        return rows

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

    def commit(self) -> bool:
        if not self.name.strip():
            self.app.message(tr("Dá um nome à métrica.", "Give the metric a name."))
            return False
        choices = [c.strip() for c in self.choices.split(",") if c.strip()]
        self.metric_id = health.save_metric(self.app.db, self.metric_id, name=self.name,
                                            kind=self.kind, unit=self.unit, group=self.group,
                                            choices=choices or None)
        health.set_active(self.app.db, self.metric_id, self.active)
        return True


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


class ParameterEditor(EditPopup):
    """Um parâmetro das análises (unidade e intervalo de referência), numa janela."""

    MAX_H = 720

    def __init__(self, app, pid: int):
        super().__init__(app)
        self.pid = pid
        p = labs.parameter(app.db, pid) or {}
        self.p = p
        self.v = {"unit": p.get("unit") or "", "ref_low": p.get("ref_low"),
                  "ref_high": p.get("ref_high")}

    def title(self) -> str:
        return tr("Parâmetro", "Parameter")

    def subtitle(self) -> str:
        return self.p.get("area") or ""

    def saved_message(self) -> str:
        return tr("Parâmetro guardado", "Parameter saved")

    def rows(self) -> list[Item]:
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
        return rows

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

    def commit(self) -> bool:
        labs.set_parameter_reference(self.app.db, self.pid, self.v["ref_low"],
                                     self.v["ref_high"], self.v["unit"] or None)
        return True

    def agent_data(self) -> dict:
        return {"parametro": {k: self.p.get(k) for k in (
            "name", "unit", "reference_text", "ref_low", "ref_high", "ideal_low", "ideal_high")}}


class LabReportEditor(SnapshotUnsaved, EditScreen):
    def __init__(self, app, report_id: int | None):
        super().__init__(app)
        self.report_id = report_id
        r = health.lab_report(app.db, report_id) if report_id else None
        self.done_on = r["done_on"] if r else date.today().isoformat()
        self.lab = (r or {}).get("lab") or ""
        self.notes = (r or {}).get("notes") or ""
        self.doctor = (r or {}).get("doctor_feedback") or ""
        self._armed = False
        self.mark_saved()             # voltar com alterações pergunta

    def snapshot_state(self):
        return (self.done_on, self.lab, self.notes, self.doctor)

    def on_save(self) -> bool:
        self._save()
        return True

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
        self.mark_saved()
        self.app.pop()

    def _delete(self) -> None:
        def gone() -> None:
            health.delete_lab_report(self.app.db, self.report_id)
            self.app.pop(force=True)
        self.app.confirm(tr("Apagar esta análise?", "Delete this lab report?"), tr("Tens a certeza? Não dá para desfazer.", "Are you sure? This cannot be undone."),
                         gone, yes=tr("Apagar", "Delete"))


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


class LabResultEditor(EditPopup):
    """Um resultado de uma análise, numa janela."""

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

    def title(self) -> str:
        return tr("Resultado", "Result")

    def subtitle(self) -> str:
        return self.v["marker"]

    def rows(self) -> list[Item]:
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
                Item(tr("Comentário", "Comment"), value=v["comment"] or "—", data="text:comment")]
        if self.result_id:
            rows.append(Item(tr("Remover o resultado", "Remove the result"), action=self._remove))
        return rows

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

    def commit(self) -> bool:
        v = self.v
        if not v["marker"].strip():
            self.app.message(tr("Escreve o nome do marcador.", "Type the marker name."))
            return False
        self.result_id = health.save_lab_result(
            self.app.db, self.result_id, self.report_id, marker=v["marker"].strip(),
            value=v["value"], unit=v["unit"], ref_low=v["ref_low"], ref_high=v["ref_high"],
            comment=v["comment"])
        return True

    def _remove(self) -> None:
        health.delete_lab_result(self.app.db, self.result_id)
        self._saved_state = self.state()
        self.close()


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
                     detail=tr("←/→ muda", "←/→ changes"), data="create_unknown"),
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

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and item.data == "create_unknown" and symbol in (key.LEFT, key.RIGHT):
            self._toggle()
            return True
        return super().on_key(symbol, modifiers)

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
            from perennia.core import rowing as rw
            rw.link_tests(a.db)
        if self.sport == "swimming":
            from perennia.core import endurance as en
            en.seed(a.db)
        rows = []
        # os protocolos de FTP (20 min, rampa, 2 × 8 min) são testes como os outros
        for x in ft.tests(a.db, self.sport):
            trend = {"up": " ↑", "down": " ↓", "same": " ="}.get(x["trend"] or "", "")
            rows.append(Item(x["name"], value=(ft.fmt_value(x["last"], x["unit"]) + trend)
                             if x["n"] else "—",
                             detail=(tr("melhor {b} · {n} vezes · último {d}",
                                        "best {b} · {n} times · last {d}",
                                        b=ft.fmt_value(x["best"], x["unit"]), n=x["n"],
                                        d=x["last_on"]) if x["n"] else _excerpt(x["instructions"], 90)),
                             action=lambda tid=x["id"]: a.push(TestDetail(a, tid))))
        rows.append(Item(tr("Adicionar teste", "Add test"), button=True, primary=True,
                         action=lambda: a.push(TestEditor(a, None, self.sport))))
        self.chrome.set(tr("Testes · {s}", "Tests · {s}", s=sport_name(self.sport)),
                        tr("Escolhe um teste para o fazer, registar ou editar.",
                           "Pick a test to run, log or edit."), self.footer())
        self.list.set_items(rows, keep_index=True)


class TestDetail(Screen):
    """Um teste: os blocos (como no construtor de treinos), fazer, registar,
    editar e os resultados."""

    PANEL_H = 250                     # o cartão dos blocos; os resultados ficam por baixo

    def __init__(self, app, test_id: int):
        super().__init__(app)
        self.test_id = test_id
        self._armed = None
        self._configure = None
        from perennia.ui.brief import BriefPanel
        self.panel = BriefPanel()
        self.brief = None
        self._layout_panel()

    def _layout_panel(self) -> None:
        """O cartão dos blocos em cima, a toda a largura; a lista (ações e
        resultados) por baixo dele."""
        w, h = self.app.window.width, self.app.window.height
        top = self.content_top(h) + 18
        has = getattr(self, "brief", None) is not None
        self.panel.layout(48, top, w - 96, top - self.PANEL_H)
        list_top = top - self.PANEL_H - 16 if has else self.content_top(h)
        self.list.x, self.list.y, self.list.width = 48, list_top, w - 96
        self.list.set_visible_rows(max(3, int((list_top - 96) // 38) + 1))

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout_panel()

    def make_brief(self, x: dict):
        """O cartão do teste com os blocos (None se o teste não tiver blocos)."""
        from perennia.core import objectives as ob
        blocks = ft.test_blocks(self.app.db, x)
        if not blocks:
            return None
        sport = x["sport"] if x["sport"] in ("cycling", "rowing", "running", "swimming") \
            else "running"
        b = ob.build(self.app.db, sport, None, x["name"], blocks,
                     description=x.get("instructions") or "")
        b.goal = _excerpt(x.get("instructions"), 220) or b.goal
        b.goal_written = True
        if x["sport"] not in ("cycling", "rowing", "running", "swimming"):
            b.sport = x["sport"]
        return b

    def draw(self) -> None:
        super().draw()
        if self.brief is not None:
            self.panel.draw()

    def enter(self) -> None:
        a = self.app
        x = ft.test(a.db, self.test_id)
        if x is None:
            a.pop()
            return
        try:
            self.brief = self.make_brief(x)
        except Exception:
            self.brief = None
        self._layout_panel()
        if self.brief is not None:
            self.panel.set(self.brief)
        s = ft.summary(a.db, x)
        rows = []
        buttons = []
        self._configure = None
        if x["protocol"]:
            # teste no rolo ou na máquina de remo: o resultado vem da sessão.
            # Em baixo, à direita: Editar o teste · Configurar sessão (Enter)
            if str(x["protocol"]).startswith("row_"):
                from perennia.ui import rowing_screens as rs
                self._configure = lambda: rs.start_session(a, protocol=x["protocol"])
            else:
                self._configure = lambda: a.push(FtpRouteChoice(a, x["protocol"]))
            buttons = [Item(tr("Editar o teste", "Edit the test"), button=True,
                            action=lambda: a.push(TestEditor(a, self.test_id, x["sport"]))),
                       Item(tr("Configurar sessão", "Set up the session"), button=True,
                            primary=True, action=self._configure)]
        else:
            # na natação só se regista o resultado (a prova faz-se na piscina)
            if x["sport"] != "swimming":
                rows.append(Item(tr("▶ Fazer o teste", "▶ Run the test"),
                                 detail=tr("com cronómetro", "with a timer"),
                                 action=lambda: a.push(TestRunScreen(a, self.test_id))))
            rows += [Item(tr("Registar um resultado", "Log a result"),
                          detail=tr("numa janela: valor, data e notas",
                                    "in a window: value, date and notes"),
                          action=lambda: a.push(ResultPopup(a, self.test_id, None,
                                                            then=self.enter))),
                     Item(tr("Editar o teste", "Edit the test"),
                          action=lambda: a.push(TestEditor(a, self.test_id, x["sport"])))]
        if self.brief is None:
            rows.append(Item(tr("Instruções", "Instructions"),
                             detail=_excerpt(x["instructions"], 120), enabled=False))
        res = ft.results(a.db, self.test_id)
        rows.append(Item(tr("Resultados ({n})", "Results ({n})", n=len(res)), header=True))
        for r in res:
            rows.append(Item(r["done_on"], value=ft.fmt_value(r["value"], x["unit"]),
                             detail=_excerpt(r["notes"], 90),
                             action=lambda rid=r["id"]: a.push(
                                 ResultPopup(a, self.test_id, rid, then=self.enter)),
                             data=("result", r["id"])))
        if not res:
            rows.append(Item(tr("Ainda sem resultados", "No results yet"), enabled=False))
        best = ft.fmt_value(s["best"], x["unit"]) if s["n"] else "—"
        self.chrome.set(x["name"], tr("Melhor: {b} · {n} resultados · Enter num resultado "
                                      "edita-o ou apaga-o",
                                      "Best: {b} · {n} results · Enter on a result edits or "
                                      "deletes it", b=best, n=s["n"]), self.footer())
        self.list.set_items(rows + buttons, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol in (key.ENTER, key.RETURN) and self._configure is not None and \
                (item is None or (item.action is None and not item.button)):
            self._configure()                  # Enter: configurar a sessão
            return True
        if symbol == key.DELETE and item is not None and isinstance(item.data, tuple):
            rid = item.data[1]

            def gone(rid=rid) -> None:
                ft.delete_result(self.app.db, rid)
                self.enter()
            self.app.confirm(tr("Apagar o resultado de {d}?", "Delete the result from {d}?",
                                d=item.label), tr("Tens a certeza? Não dá para desfazer.", "Are you sure? This cannot be undone."), gone,
                             yes=tr("Apagar", "Delete"))
            return True
        return super().on_key(symbol, modifiers)


class ResultPopup(EditPopup):
    """Registar ou corrigir um resultado de um teste, numa janela: valor, data
    e notas. Ao corrigir há também **Apagar** (com confirmação)."""

    DATE_FIELDS = ("done_on",)

    def __init__(self, app, test_id: int, result_id: int | None, then=None):
        super().__init__(app)
        self.test = ft.test(app.db, test_id)
        self.result_id = result_id
        self.then = then
        r = ft.result(app.db, result_id) if result_id else None
        self.value = r["value"] if r else None
        self.done_on = r["done_on"] if r else date.today().isoformat()
        self.notes = (r or {}).get("notes") or ""

    def title(self) -> str:
        return tr("Resultado", "Result") if self.result_id else tr("Novo resultado",
                                                                    "New result")

    def subtitle(self) -> str:
        return self.test["name"]

    def state(self):
        return (self.value, self.done_on, self.notes)

    def rows(self) -> list[Item]:
        return [Item(tr("Resultado", "Result"), value=ft.fmt_value(self.value, self.test["unit"]),
                     data="num:value",
                     detail=tr("escreve o número ({u}) · ←/→ ±1", "type the number ({u}) · "
                               "←/→ ±1", u=self.test["unit"])),
                Item(tr("Data", "Date"), value=self.done_on, data="cyc:done_on",
                     detail=tr("Enter abre o calendário", "Enter opens the calendar")),
                Item(tr("Notas", "Notes"), value=(self.notes or "") + "▏", data="text:notes")]

    def buttons(self) -> list[Item]:
        out = super().buttons()
        if self.result_id:
            out.insert(0, Item(tr("Apagar", "Delete"), button=True, action=self.delete))
        return out

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        self.value = max(0.0, (self.value or 0) + steps * (10 if big else 1))

    def num_set(self, field: str, value: float | None) -> None:
        self.value = value

    def cycle(self, field: str, step: int) -> None:
        from datetime import timedelta
        try:
            self.done_on = (date.fromisoformat(self.done_on) + timedelta(days=step)).isoformat()
        except ValueError:
            self.done_on = date.today().isoformat()

    def date_set(self, field: str, iso: str) -> None:
        self.done_on = iso
        self.refresh()

    def text_input(self, field: str, text: str) -> None:
        self.notes += text
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.notes = self.notes[:-1]
        self.enter()

    def saved_message(self) -> str:
        return tr("Resultado guardado: {v}", "Result saved: {v}",
                  v=ft.fmt_value(self.value, self.test["unit"]))

    def commit(self) -> bool:
        if self.value is None:
            self.app.message(tr("Falta o resultado.", "The result is missing."))
            return False
        try:
            date.fromisoformat(self.done_on)
        except ValueError:
            self.app.message(tr("Data inválida: usa AAAA-MM-DD.", "Invalid date: use YYYY-MM-DD."))
            return False
        if self.result_id:
            ft.update_result(self.app.db, self.result_id, self.value, done_on=self.done_on,
                             notes=self.notes or None)
        else:
            extra = None
            if "Cooper" in self.test["name"]:
                extra = {"vo2max": round(ft.vo2max_cooper(self.value), 1)}
            self.result_id = ft.add_result(self.app.db, self.test["id"], self.value,
                                           done_on=self.done_on, notes=self.notes or None,
                                           extra=extra)
        if self.then is not None:
            self.then()
        return True

    def delete(self) -> None:
        rid = self.result_id

        def gone() -> None:
            ft.delete_result(self.app.db, rid)
            self._saved_state = self.state()
            self.close()
            self.app.message(tr("Resultado apagado", "Result deleted"))
            if self.then is not None:
                self.then()
        self.app.confirm(tr("Apagar o resultado de {d}?", "Delete the result from {d}?",
                            d=self.done_on),
                         tr("Tens a certeza? Não dá para desfazer.",
                            "Are you sure? This cannot be undone."), gone,
                         yes=tr("Apagar", "Delete"))


class TestRunScreen(SnapshotUnsaved, EditScreen):
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
        self.mark_saved()             # voltar com alterações pergunta

    def snapshot_state(self):
        return (self.value, self.notes, self.done_on)

    def on_save(self) -> bool:
        self._save()
        return True

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
        self.mark_saved()
        self.app.pop()

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


class TestEditor(EditPopup):
    """Criar ou editar um teste (nome, unidade, melhor é, duração, instruções),
    numa janela."""

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

    def state(self):
        return (self.name, self.unit, self.better, self.duration, self.instructions)

    def title(self) -> str:
        return tr("Teste", "Test") if self.test_id else tr("Novo teste", "New test")

    def subtitle(self) -> str:
        return sport_name(self.sport)

    def rows(self) -> list[Item]:
        return [Item(tr("Nome", "Name"), value=(self.name or "") + "▏", data="text:name"),
                Item(tr("Unidade", "Unit"), value=self.unit, data="cyc:unit",
                     detail=tr("←/→ muda", "←/→ changes")),
                Item(tr("Melhor é", "Better is"),
                     value=tr("mais alto", "higher") if self.better == "higher"
                     else tr("mais baixo", "lower"), data="cyc:better",
                     detail=tr("←/→ muda", "←/→ changes")),
                Item(tr("Duração (s, 0 = sem tempo)", "Duration (s, 0 = untimed)"),
                     value=str(self.duration), data="num:duration"),
                Item(tr("Instruções", "Instructions"), value=_excerpt(self.instructions, 50) or "—",
                     detail=tr("Enter escreve", "Enter writes"), action=self._edit_instr)]

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

    def saved_message(self) -> str:
        return tr("Teste guardado", "Test saved")

    def commit(self) -> bool:
        if not self.name.strip():
            self.app.message(tr("Dá um nome ao teste.", "Give the test a name."))
            return False
        self.test_id = ft.save_test(self.app.db, self.test_id, sport=self.sport, name=self.name,
                                    unit=self.unit, better=self.better,
                                    duration_s=self.duration, instructions=self.instructions,
                                    protocol=self.protocol)
        return True
