"""O menu Longevidade: o índice por período (1 dia … 20 anos) com a tendência, o
radar de onde o corpo tem estado concentrado, e os testes de longevidade (que
saíram da Saúde). A fórmula está em `perennia.core.longevity`."""
from __future__ import annotations

import time

from perennia.core import longevity as lg
from perennia.core.i18n import tr
from perennia.ui.app import Screen
from perennia.ui.radar import RadarChart
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Item


class LongevityMenu(Screen):
    TABBED = True
    TAB_KEYS = ("index", "formula", "tests")
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
        return [tr("Índice", "Index"), tr("Fórmula", "Formula"),
                tr("Testes de longevidade", "Longevity tests")]

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
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "formula":
            self.inner = None
            self._formula()
            return
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "tests":
            from perennia.ui import health_screens as hs
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
        from perennia.ui import coach_screens
        rows.append(Item(tr("Treinador: caminho para a longevidade",
                            "Coach: path to longevity"), button=True, primary=True,
                         action=lambda: coach_screens.open_longevity(self.app)))
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
        db = self.app.db
        self.radar.set([(lg.label_of(db, a), axes[a], f"{axes[a]:.0f}") for a in axes],
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



    # ----------------------------------------------------------- a fórmula

    def _formula(self) -> None:
        """A fórmula do índice, escrita com os números em vigor, e tudo o que se pode mudar nela:
        os pesos e as doses de cada eixo, a mistura dos testes, os hábitos e os parâmetros
        próprios. Cada alteração grava-se e o índice recalcula-se logo."""
        a = self.app
        f = lg.formula(a.db)
        rows = [Item(tr("A fórmula", "The formula"), header=True)]
        for title, text in lg.formula_lines(a.db):
            rows.append(Item(title, detail=text, enabled=False))
        rows.append(Item(tr("Eixos · peso e dose de referência (min/semana)",
                            "Axes · weight and reference dose (min/week)"), header=True))
        for ax in lg.AXES:
            cfg = f["axes"][ax]
            rows.append(Item(lg.axis_label(ax),
                             value=tr("peso {w:g} · T {t:g} min/sem", "weight {w:g} · T {t:g} "
                                      "min/wk", w=cfg["weight"], t=cfg["target"]),
                             detail=tr("Enter edita", "Enter edits"),
                             action=lambda k=ax: a.push(AxisEditor(a, k, self.enter)),
                             data=("axis", ax)))
        rows.append(Item(tr("Testes e hábitos", "Tests and habits"), header=True))
        rows.append(Item(tr("Mistura dos testes", "Test blend"),
                         value=f"{f['blend']:.2f}",
                         detail=tr("a parte da nota de um eixo que vem dos testes (0 = só treino)",
                                   "the share of an axis' score that comes from tests (0 = "
                                   "training only)"),
                         action=lambda: a.push(HabitsEditor(a, self.enter))))
        rows.append(Item(tr("Hábitos de recuperação", "Recovery habits"),
                         value=tr("sono {s:g} · HRV {h:g} min", "sleep {s:g} · HRV {h:g} min",
                                  s=f["sleep_min"], h=f["hrv_min"]),
                         action=lambda: a.push(HabitsEditor(a, self.enter))))
        rows.append(Item(tr("Parâmetros próprios", "Custom parameters"), header=True))
        for c in f["custom"]:
            src = c["source"]
            if c["kind"] == "metric":
                m = health_metric(a.db, src)
                src = m["name"] if m else src
            rows.append(Item(c["name"],
                             value=tr("peso {w:g} · alvo {t:g}", "weight {w:g} · target {t:g}",
                                      w=c["weight"], t=c["target"]),
                             detail=(tr("métrica: ", "metric: ") if c["kind"] == "metric"
                                     else tr("desporto: ", "sport: ")) + src,
                             action=lambda cid=c["id"]: a.push(CustomEditor(a, cid, self.enter)),
                             data=("custom", c["id"])))
        if not f["custom"]:
            rows.append(Item(tr("Nenhum ainda", "None yet"),
                             detail=tr("junta uma métrica do diário (sono, HRV, peso…) ou os "
                                       "minutos de um desporto", "add a log metric (sleep, HRV, "
                                       "weight…) or a sport's minutes"), enabled=False))
        rows += [Item(tr("Repor a fórmula original", "Restore the original formula"),
                      button=True, action=self._reset),
                 Item(tr("+ Novo parâmetro", "+ New parameter"), button=True, primary=True,
                      action=lambda: a.push(CustomEditor(a, None, self.enter)))]
        res = self.result(fresh=True)
        self.chrome.set(self.TITLE(),
                        tr("Índice agora (3 meses): {v:.0f} · muda o que quiseres: o índice "
                           "recalcula-se logo", "Index now (3 months): {v:.0f} · change anything: "
                           "the index recalculates at once", v=res["3m"]["index"]),
                        tr("Enter edita · Tab separador · Esc voltar",
                           "Enter edits · Tab next tab · Esc back"))
        self.list.set_items(rows, keep_index=True)

    def _reset(self) -> None:
        def go() -> None:
            lg.reset_formula(self.app.db)
            self._result = None
            self.enter()
        self.app.confirm(tr("Repor a fórmula original?", "Restore the original formula?"),
                         tr("Os pesos, as doses, os hábitos e os parâmetros próprios voltam ao "
                            "que vinha de origem.", "Weights, doses, habits and custom "
                            "parameters go back to the defaults."), go,
                         yes=tr("Repor", "Restore"))


def health_metric(db, key: str):
    from perennia.core import health
    return health.metric_by_key(db, key)


class _FormulaEditor(EditPopup):
    """Base dos editores da fórmula: grava logo na definição `longevity_formula`."""

    W = 760

    def __init__(self, app, on_done=None):
        super().__init__(app)
        self.on_done = on_done

    def saved_message(self) -> str:
        return tr("Fórmula guardada", "Formula saved")

    def _after(self) -> None:
        if self.on_done is not None:
            self.on_done()


class AxisEditor(_FormulaEditor):
    """O peso e a dose de referência de um eixo."""

    def __init__(self, app, axis: str, on_done=None):
        super().__init__(app, on_done)
        self.axis = axis
        cfg = lg.formula(app.db)["axes"][axis]
        self.v = {"weight": cfg["weight"], "target": cfg["target"]}

    def title(self) -> str:
        return lg.axis_label(self.axis)

    def subtitle(self) -> str:
        return tr("quanto pesa no índice e quanto é preciso por semana para 63 % da nota",
                  "how much it weighs in the index and how much per week it takes for 63 % of "
                  "the score")

    def rows(self) -> list[Item]:
        return [Item(tr("Peso", "Weight"), value=f"{self.v['weight']:g}", data="num:weight",
                     detail=tr("←/→ ±0,1 · Shift ±1", "←/→ ±0.1 · Shift ±1")),
                Item(tr("Dose de referência (T)", "Reference dose (T)"),
                     value=f"{self.v['target']:g} min/sem", data="num:target",
                     detail=tr("minutos por semana · ←/→ ±1 · Shift ±10",
                               "minutes per week · ←/→ ±1 · Shift ±10"))]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field == "weight":
            self.v["weight"] = max(0.0, round(self.v["weight"] + steps * (1.0 if big else 0.1), 2))
        else:
            self.v["target"] = max(1.0, round(self.v["target"] + steps * (10 if big else 1), 1))

    def num_set(self, field: str, value) -> None:
        if value is None:
            return
        if field == "weight":
            self.v["weight"] = max(0.0, float(value))
        else:
            self.v["target"] = max(1.0, float(value))

    def commit(self) -> bool:
        f = lg.formula(self.app.db)
        f["axes"][self.axis] = {"weight": self.v["weight"], "target": self.v["target"]}
        lg.save_formula(self.app.db, f)
        self._after()
        return True


class HabitsEditor(_FormulaEditor):
    """A mistura dos testes e os minutos de recuperação dos hábitos."""

    def __init__(self, app, on_done=None):
        super().__init__(app, on_done)
        f = lg.formula(app.db)
        self.v = {"blend": f["blend"], "sleep_min": f["sleep_min"], "hrv_min": f["hrv_min"]}

    def title(self) -> str:
        return tr("Testes e hábitos", "Tests and habits")

    def rows(self) -> list[Item]:
        return [Item(tr("Mistura dos testes", "Test blend"), value=f"{self.v['blend']:.2f}",
                     data="num:blend", detail=tr("0 a 1 · ←/→ ±0,05", "0 to 1 · ←/→ ±0.05")),
                Item(tr("Sono 7 h ou mais", "Sleep 7 h or more"),
                     value=f"{self.v['sleep_min']:g} min/dia", data="num:sleep_min",
                     detail=tr("minutos de recuperação por dia", "recovery minutes per day")),
                Item(tr("HRV registada", "HRV logged"), value=f"{self.v['hrv_min']:g} min/dia",
                     data="num:hrv_min", detail=tr("minutos de recuperação por dia",
                                                   "recovery minutes per day"))]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field == "blend":
            self.v["blend"] = max(0.0, min(1.0, round(self.v["blend"] + steps * 0.05, 2)))
        else:
            self.v[field] = max(0.0, round(self.v[field] + steps * (10 if big else 1), 1))

    def num_set(self, field: str, value) -> None:
        if value is None:
            return
        self.v[field] = (max(0.0, min(1.0, float(value))) if field == "blend"
                         else max(0.0, float(value)))

    def commit(self) -> bool:
        f = lg.formula(self.app.db)
        f.update(self.v)
        lg.save_formula(self.app.db, f)
        self._after()
        return True


class CustomEditor(_FormulaEditor):
    """Um parâmetro próprio: uma métrica do diário (a média no período) ou os minutos por
    semana de um desporto."""

    SPORTS = ("cycling", "rowing", "running", "swimming", "strength")

    def __init__(self, app, cid: str | None, on_done=None):
        super().__init__(app, on_done)
        self.cid = cid
        c = next((x for x in lg.formula(app.db)["custom"] if x["id"] == cid), None) or {}
        self.v = {"name": c.get("name", ""), "kind": c.get("kind", "metric"),
                  "source": c.get("source", ""), "target": float(c.get("target", 8.0)),
                  "weight": float(c.get("weight", 1.0)), "better": c.get("better", "higher")}
        if not self.v["source"]:
            self.v["source"] = self._sources()[0][0] if self._sources() else ""

    def _sources(self) -> list[tuple[str, str]]:
        if self.v["kind"] == "sport":
            from perennia.core import sports as sp
            return [(s, sp.name(s) if s != "strength" else tr("Ginásio", "Gym"))
                    for s in self.SPORTS]
        from perennia.core import health
        health.seed(self.app.db)
        return [(m["key"], m["name"]) for m in health.metrics(self.app.db)
                if m["kind"] in ("number", "scale", "bool")]

    def title(self) -> str:
        return tr("Parâmetro", "Parameter") if self.cid else tr("Novo parâmetro", "New parameter")

    def subtitle(self) -> str:
        return self.v["name"]

    def rows(self) -> list[Item]:
        names = dict(self._sources())
        rows = [Item(tr("Nome", "Name"), value=self.v["name"] + "▏", data="text:name"),
                Item(tr("De onde vem", "Where it comes from"),
                     value=tr("métrica do diário", "log metric") if self.v["kind"] == "metric"
                     else tr("minutos de um desporto", "a sport's minutes"), data="cyc:kind"),
                Item(tr("Qual", "Which"), value=names.get(self.v["source"], "—"),
                     data="cyc:source", detail=tr("Enter abre a lista", "Enter opens the list")),
                Item(tr("Alvo", "Target"), value=f"{self.v['target']:g}", data="num:target",
                     detail=(tr("o valor médio que dá a nota máxima", "the average value that "
                                "gives the top score") if self.v["kind"] == "metric" else
                             tr("minutos por semana (63 % da nota)", "minutes per week (63 % of "
                                "the score)"))),
                Item(tr("Peso", "Weight"), value=f"{self.v['weight']:g}", data="num:weight")]
        if self.v["kind"] == "metric":
            rows.append(Item(tr("Melhor é", "Better is"), data="cyc:better",
                             value=tr("mais alto", "higher") if self.v["better"] == "higher"
                             else tr("mais baixo", "lower")))
        if self.cid:
            rows.append(Item(tr("Apagar o parâmetro", "Delete the parameter"), button=True,
                             action=self._delete))
        return rows

    def cycle(self, field: str, step: int) -> None:
        v = self.v
        if field == "kind":
            v["kind"] = "sport" if v["kind"] == "metric" else "metric"
            srcs = self._sources()
            v["source"] = srcs[0][0] if srcs else ""
            v["target"] = 8.0 if v["kind"] == "metric" else 60.0
        elif field == "source":
            keys = [k for k, _n in self._sources()]
            if keys:
                i = keys.index(v["source"]) if v["source"] in keys else 0
                v["source"] = keys[(i + step) % len(keys)]
        elif field == "better":
            v["better"] = "lower" if v["better"] == "higher" else "higher"

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field == "weight":
            self.v["weight"] = max(0.0, round(self.v["weight"] + steps * (1.0 if big else 0.1), 2))
        else:
            self.v["target"] = max(0.1, round(self.v["target"] + steps * (10 if big else 1), 2))

    def num_set(self, field: str, value) -> None:
        if value is None:
            return
        self.v[field] = max(0.0, float(value))

    def text_input(self, field: str, text: str) -> None:
        self.v["name"] = (self.v["name"] + text)[:40]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v["name"] = self.v["name"][:-1]
        self.enter()

    def commit(self) -> bool:
        v = self.v
        if not v["name"].strip() or not v["source"]:
            self.app.message(tr("Dá um nome e escolhe de onde vem.", "Give it a name and pick "
                                "where it comes from."))
            return False
        self.cid = lg.add_custom(self.app.db, name=v["name"], kind=v["kind"],
                                 source=v["source"], target=v["target"], weight=v["weight"],
                                 better=v["better"], cid=self.cid)
        self._after()
        return True

    def _delete(self) -> None:
        def gone() -> None:
            lg.remove_custom(self.app.db, self.cid)
            self._saved_state = self.state()
            self._after()
            self.app.pop()
        self.app.confirm(tr("Apagar o parâmetro?", "Delete the parameter?"),
                         tr("Deixa de contar para o índice.", "It stops counting towards the "
                            "index."), gone, yes=tr("Apagar", "Delete"))
