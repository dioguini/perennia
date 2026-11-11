"""«AdHoc Analysis»: o centro exploratório das Estatísticas gerais.

Duas maneiras de olhar para os mesmos dados (a lógica está em `perennia.core.adhoc`):

* **Gráfico dinâmico** (ao estilo Power BI): escolhe-se a fonte, o eixo X, o valor com a sua
  agregação (soma, média, mínimo, máximo, mediana, contagem), a legenda (uma série por
  categoria) e o tipo de gráfico (colunas, colunas empilhadas, linhas, dispersão).
* **Dataset**: escolhem-se os campos e os filtros, vê-se uma pré-visualização e exporta-se
  para .csv (nome do ficheiro e separador à escolha).

Tudo o que se escolhe fica guardado (a última vista volta quando se reabre o separador) e pode
juntar-se às «vistas guardadas», com nome. Nenhuma lista aqui se percorre só com as setas:
Enter ou um clique abrem uma lista com pesquisa; ←/→ continuam a passar à opção seguinte.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from pyglet.window import key

from perennia.core import adhoc
from perennia.core.i18n import t, tr
from perennia.core.units import parse_number
from perennia.gfx.compat import label as make_label
from perennia.ui.app import PopupMixin, Screen
from perennia.ui.pickers import MultiChoicePopup, parse_date
from perennia.ui.sport_screens import EditPopup, EditScreen
from perennia.ui.widgets import DIM, Chart, Dropdown, Item, Table, fit_text

ADHOC_TAB = "AdHoc Analysis"

# Paleta das séries (a última, cinzenta, é sempre a de «Outros»).
SERIES_COLORS = [(108, 170, 220), (236, 128, 160), (120, 200, 150), (240, 180, 90),
                 (90, 200, 230), (170, 140, 220), (220, 120, 90)]
OTHER_COLOR = (150, 156, 166)

FOOT = ("←/→ mudar · Enter abre a lista · ↑↓ linha · Tab outro gráfico · Esc voltar",
        "←/→ change · Enter opens the list · ↑↓ row · Tab another chart · Esc back")


def num_text(v: float | None) -> str:
    """Um número curto para eixos e dicas."""
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    if a >= 100:
        return f"{v:.0f}"
    if a >= 10:
        return f"{v:.1f}"
    return (f"{v:.2f}".rstrip("0").rstrip(".")) or "0"


def _field_labels(fields) -> list[str]:
    return [f.label for f in fields]


# ===================================================================== o ecrã


class AdHocScreen(EditScreen):
    """O separador «AdHoc Analysis» das Estatísticas gerais."""

    TABBED = True
    DATE_FIELDS = EditScreen.DATE_FIELDS + ("from", "to")

    def __init__(self, app):
        self._choices: dict[str, tuple[int, int, object]] = {}
        self._cache: dict[str, list[dict]] = {}
        self.view_name = ""                       # a vista guardada que está carregada
        super().__init__(app)
        self.spec = adhoc.load_state(app.db)
        self.pv: adhoc.Pivot | None = None
        self.cols: list = []
        self.rows: list[dict] = []
        self.n_rows = 0
        self.n_all = 0
        self.problem = ""
        w, h = app.window.width, app.window.height
        self.chart = Chart(*self._chart_box(w, h))
        self.table = Table()
        self.note = make_label("", font_size=11, color=DIM, anchor_y="center")
        self.tab = self._adhoc_index()
        if self.tabs is not None:
            self.tabs.select(self.tab)

    # ------------------------------------------------------------ separadores

    @staticmethod
    def _adhoc_index() -> int:
        from perennia.ui import sport_screens as ss
        return ss.GeneralStatsScreen.VIEWS.index("adhoc")

    def tab_labels(self) -> list[str]:
        from perennia.ui import sport_screens as ss
        return ss.GeneralStatsScreen.labels()

    def set_tab(self, i: int) -> None:
        n = len(self.tab_labels())
        i %= max(1, n)
        if i == self._adhoc_index():
            return
        from perennia.ui import sport_screens as ss
        gs = ss.GeneralStatsScreen(self.app)
        gs.view = i
        gs.tab = i
        if gs.tabs is not None:
            gs.tabs.select(i)
        self.app.replace(gs)

    # ------------------------------------------------------------- geometria

    def _list_width(self, w: int) -> int:
        return max(380, min(560, int((w - 96) * 0.42)))

    def _right_x(self, w: int) -> int:
        return 48 + self._list_width(w) + 64

    def _chart_box(self, w: int, h: int) -> tuple[int, int, int, int]:
        x = self._right_x(w)
        top = self.content_top(h) + 6
        return x, 112, max(200, w - 48 - x), max(120, top - 112)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.chart = Chart(*self._chart_box(w, h))
        self.enter()

    # ------------------------------------------------------------------ dados

    def _source_rows(self) -> list[dict]:
        src = self.spec.source
        if src not in self._cache:
            self._cache[src] = adhoc.load(self.app.db, src)
        return self._cache[src]

    def _touch(self) -> None:
        """Pôr a vista em ordem e guardá-la como a última usada."""
        self.spec.clean()
        try:
            adhoc.save_state(self.app.db, self.spec)
        except Exception:
            pass

    def _recompute(self) -> None:
        spec = self.spec
        self.problem = ""
        self.pv = None
        self.rows = []
        self.cols = []
        try:
            everything = self._source_rows()
            rows = adhoc.apply_filters(everything, spec)
            self.n_all, self.n_rows = len(everything), len(rows)
            if spec.mode == "chart":
                self.pv = adhoc.pivot(self.app.db, rows, spec)
            else:
                src = adhoc.source_of(spec.source)
                self.cols = [f for f in src.fields if f.key in spec.fields]
                self.rows = rows
        except Exception as e:             # dados esquisitos não podem deitar o ecrã abaixo
            self.problem = f"{type(e).__name__}: {e}"

    # ----------------------------------------------------------------- linhas

    def _dd(self, label: str, field: str, labels: list[str], cur: int, setter,
            enabled: bool = True, detail: str = "") -> Item:
        """Uma linha com lista pendente (Enter/clique) e ←/→ para a opção seguinte."""
        if not labels:
            return Item(label, value="—", enabled=False)
        cur = max(0, min(len(labels) - 1, cur))
        if not enabled:
            return Item(label, value=labels[cur], enabled=False, detail=detail)
        self._choices[field] = (len(labels), cur, setter)
        return Item(label, value=labels[cur], detail=detail, data="cyc:" + field,
                    dropdown=Dropdown(labels, cur, setter, title=label))

    def rows_for_list(self) -> list[Item]:
        a = self.app
        spec = self.spec
        src = adhoc.source_of(spec.source)
        self._choices = {}
        rows: list[Item] = []

        rows.append(self._dd(tr("Modo", "Mode"), "mode",
                             [tr("Gráfico dinâmico", "Dynamic chart"),
                              tr("Dataset (campos e .csv)", "Dataset (fields and .csv)")],
                             0 if spec.mode == "chart" else 1, self._set_mode))
        rows.append(self._dd(tr("Fonte dos dados", "Data source"), "source",
                             [adhoc.SOURCES[k].label for k in adhoc.SOURCE_ORDER],
                             adhoc.SOURCE_ORDER.index(src.key), self._set_source))
        names = [v["name"] for v in adhoc.views(a.db)]
        cur = names.index(self.view_name) + 1 if self.view_name in names else 0
        rows.append(self._dd(tr("Vista guardada", "Saved view"), "view",
                             [tr("— vista atual —", "— current view —")] + names, cur,
                             self._set_view))
        rows.append(self._dd(tr("Período", "Period"), "period",
                             [adhoc.period_name(p) for p in adhoc.PERIODS],
                             adhoc.PERIODS.index(spec.period), self._set_period))
        if spec.period == "custom":
            rows.append(Item(tr("   de", "   from"), value=spec.date_from or "—",
                             data="cyc:from",
                             detail=tr("Enter abre o calendário", "Enter opens the calendar")))
            rows.append(Item(tr("   até", "   to"), value=spec.date_to or "—", data="cyc:to",
                             detail=tr("Enter abre o calendário", "Enter opens the calendar")))
        n = len(spec.filters)
        rows.append(Item(tr("Filtros", "Filters"),
                         value=(tr("{n} ativos", "{n} active", n=n) if n else
                                tr("nenhum", "none")) + "  ›",
                         action=self._open_filters))
        if spec.mode == "dataset":
            rows.append(Item(tr("Campos do dataset", "Dataset fields"),
                             value=tr("{n} de {m}", "{n} of {m}", n=len(spec.fields),
                                      m=len(src.fields)) + "  ›",
                             action=self._pick_fields))
        else:
            rows += self._chart_rows(src)
        rows += self._buttons()
        return rows

    def _chart_rows(self, src) -> list[Item]:
        spec = self.spec
        out: list[Item] = []
        xs = adhoc.x_fields(src)
        out.append(self._dd(tr("Eixo X", "X axis"), "x", _field_labels(xs),
                            next((i for i, f in enumerate(xs) if f.key == spec.x), 0),
                            self._set_x))
        xf = src.field(spec.x)
        if xf is not None and xf.kind == adhoc.DATE and spec.chart != "scatter":
            out.append(self._dd(tr("Agrupar datas por", "Group dates by"), "grain",
                                [adhoc.grain_name(g) for g in adhoc.GRAINS],
                                adhoc.GRAINS.index(spec.grain), self._set_grain))
        ys = [None] + adhoc.y_fields(src)             # None: a contagem de linhas
        out.append(self._dd(tr("Valor (eixo Y)", "Value (Y axis)"), "y",
                            [tr("Contagem de linhas", "Row count")]
                            + _field_labels(ys[1:]),
                            0 if spec.y == adhoc.ROWS else
                            1 + next((i for i, f in enumerate(ys[1:]) if f.key == spec.y), 0),
                            self._set_y))
        counting = spec.y == adhoc.ROWS or spec.chart == "scatter"
        out.append(self._dd(tr("Agregação", "Aggregation"), "agg",
                            [adhoc.agg_name(g).capitalize() for g in adhoc.AGGS],
                            adhoc.AGGS.index(spec.agg), self._set_agg, enabled=not counting,
                            detail=(tr("a dispersão mostra cada linha",
                                       "scatter shows every row") if spec.chart == "scatter"
                                    else "")))
        ss = adhoc.series_fields(src, spec.x)
        out.append(self._dd(tr("Legenda (uma série por…)", "Legend (one series per…)"),
                            "series", [tr("— nenhuma —", "— none —")] + _field_labels(ss),
                            1 + next((i for i, f in enumerate(ss) if f.key == spec.series), -1),
                            self._set_series))
        out.append(self._dd(tr("Tipo de gráfico", "Chart type"), "chart",
                            [adhoc.chart_name(c) for c in adhoc.CHARTS],
                            adhoc.CHARTS.index(spec.chart), self._set_chart))
        if xf is not None and xf.kind == adhoc.CAT and spec.chart != "scatter":
            out.append(self._dd(tr("Ordenar categorias", "Sort categories"), "sort",
                                [tr("Pela ordem natural", "Natural order"),
                                 tr("Maior primeiro", "Largest first")],
                                0 if spec.sort == "x" else 1, self._set_sort))
        return out

    def _buttons(self) -> list[Item]:
        return [
            Item(tr("Exportar .csv…", "Export .csv…"), button=True, primary=True,
                 action=self._open_export),
            Item(tr("Guardar vista…", "Save view…"), button=True, action=self._open_save_view),
            Item(tr("Apagar vista", "Delete view"), button=True, danger=True,
                 enabled=bool(self.view_name), action=self._delete_view),
        ]

    # ----------------------------------------------------------------- escolhas

    def _set_mode(self, k: int) -> None:
        self.spec.mode = ("chart", "dataset")[k]
        self._touch()

    def _set_source(self, k: int) -> None:
        new = adhoc.SOURCE_ORDER[k]
        if new == self.spec.source:
            return
        keep = self.spec
        fresh = adhoc.defaults_for(new)
        fresh.mode, fresh.period = keep.mode, keep.period
        fresh.date_from, fresh.date_to = keep.date_from, keep.date_to
        self.spec = fresh                         # os campos e filtros eram da outra fonte
        self.view_name = ""
        self._touch()

    def _set_view(self, k: int) -> None:
        names = [v["name"] for v in adhoc.views(self.app.db)]
        if k <= 0 or k > len(names):
            self.view_name = ""
            return
        spec = adhoc.view_spec(self.app.db, names[k - 1])
        if spec is not None:
            self.spec = spec
            self.view_name = names[k - 1]
            self._touch()

    def _set_period(self, k: int) -> None:
        self.spec.period = adhoc.PERIODS[k]
        if self.spec.period == "custom" and not (self.spec.date_from or self.spec.date_to):
            today = date.today()
            self.spec.date_from = (today - timedelta(days=30)).isoformat()
            self.spec.date_to = today.isoformat()
        self._touch()

    def _set_x(self, k: int) -> None:
        src = adhoc.source_of(self.spec.source)
        xs = adhoc.x_fields(src)
        self.spec.x = xs[max(0, min(len(xs) - 1, k))].key
        self._touch()

    def _set_grain(self, k: int) -> None:
        self.spec.grain = adhoc.GRAINS[k]
        self._touch()

    def _set_y(self, k: int) -> None:
        src = adhoc.source_of(self.spec.source)
        ys = adhoc.y_fields(src)
        self.spec.y = adhoc.ROWS if k <= 0 else ys[min(len(ys) - 1, k - 1)].key
        self._touch()

    def _set_agg(self, k: int) -> None:
        self.spec.agg = adhoc.AGGS[k]
        self._touch()

    def _set_series(self, k: int) -> None:
        src = adhoc.source_of(self.spec.source)
        ss = adhoc.series_fields(src, self.spec.x)
        self.spec.series = "" if k <= 0 else ss[min(len(ss) - 1, k - 1)].key
        self._touch()

    def _set_chart(self, k: int) -> None:
        self.spec.chart = adhoc.CHARTS[k]
        if self.spec.chart == "scatter":
            # a dispersão precisa de dois números: ajuda-se o eixo X se for preciso
            src = adhoc.source_of(self.spec.source)
            xf = src.field(self.spec.x)
            if xf is None or xf.kind != adhoc.NUM:
                nums = [f.key for f in adhoc.y_fields(src) if f.key != self.spec.y]
                if nums:
                    self.spec.x = nums[0]
            if self.spec.y == adhoc.ROWS:
                nums = [f.key for f in adhoc.y_fields(src) if f.key != self.spec.x]
                if nums:
                    self.spec.y = nums[0]
        self._touch()

    def _set_sort(self, k: int) -> None:
        self.spec.sort = ("x", "value")[k]
        self._touch()

    def cycle(self, field: str, step: int) -> None:
        """←/→ numa linha: passa à opção seguinte (ou muda a data um dia)."""
        if field in ("from", "to"):
            self._shift_date(field, step)
            return
        n, cur, setter = self._choices.get(field, (0, 0, None))
        if setter is not None and n:
            setter((cur + step) % n)

    # ------------------------------------------------------------------ datas

    def date_get(self, field: str) -> str | None:
        return (self.spec.date_from if field == "from" else self.spec.date_to) or None

    def date_set(self, field: str, iso: str) -> None:
        if parse_date(iso) is None:
            return
        if field == "from":
            self.spec.date_from = iso
        else:
            self.spec.date_to = iso
        self._touch()
        self.enter()

    def _shift_date(self, field: str, step: int) -> None:
        cur = parse_date(self.date_get(field) or "") or date.today()
        self.date_set(field, (cur + timedelta(days=step)).isoformat())

    # --------------------------------------------------------------- janelas

    def _open_filters(self) -> None:
        self.app.push(AdHocFiltersPopup(self.app, self))

    def _pick_fields(self) -> None:
        src = adhoc.source_of(self.spec.source)

        def done(keys: list[str]) -> None:
            self.spec.fields = keys
            self._touch()
            self.enter()                       # o popup já fechou (e já refrescou este ecrã)

        self.app.push(MultiChoicePopup(
            self.app, tr("Campos do dataset", "Dataset fields"),
            [(f.key, f.label) for f in src.fields], list(self.spec.fields), done,
            min_one=True))

    def _open_export(self) -> None:
        self._recompute()
        self.app.push(AdHocExportPopup(self.app, self))

    def _open_save_view(self) -> None:
        self.app.push(SaveViewPopup(self.app, self))

    def _delete_view(self) -> None:
        name = self.view_name
        if not name:
            return

        def go() -> None:
            adhoc.delete_view(self.app.db, name)
            self.view_name = ""
            self.app.message(tr("Vista apagada: {n}", "View deleted: {n}", n=name))
            self.enter()

        self.app.confirm(tr("Apagar a vista «{n}»?", "Delete the view «{n}»?", n=name),
                         tr("Só apaga a vista guardada; os dados ficam como estão.",
                            "Only the saved view is deleted; your data stays as it is."),
                         go, yes=tr("Apagar", "Delete"))

    # ----------------------------------------------------------- dados de saída

    def export_payload(self, what: str) -> tuple[list, list[dict]]:
        """As colunas e as linhas a exportar: o dataset, ou os números do gráfico."""
        if what == "chart" and self.pv is not None:
            return adhoc.pivot_table(self.pv)
        src = adhoc.source_of(self.spec.source)
        cols = [f for f in src.fields if f.key in self.spec.fields]
        return cols, adhoc.apply_filters(self._source_rows(), self.spec)

    # ------------------------------------------------------------- apresentação

    def enter(self) -> None:
        spec = self.spec
        self._recompute()
        self.chrome.set(t("home.stats"),
                        tr("AdHoc Analysis · centro exploratório", "AdHoc Analysis · exploration "
                                                                  "centre"),
                        tr(*FOOT))
        self.list.set_items(self.rows_for_list(), keep_index=True)
        self.list.y = self.content_top(self.app.window.height)
        self.list.set_visible_rows(max(4, (self.list.y - 110) // 38))
        w, h = self.app.window.width, self.app.window.height
        self.note.x, self.note.y = self._right_x(w), 74
        width = max(200, w - 48 - self._right_x(w))
        if spec.mode == "chart":
            self._render_chart()
            self.note.text = fit_text(self._summary(), width, 11)
        else:
            self._render_table(width)
            self.note.text = fit_text(self._summary(), width, 11)

    def _summary(self) -> str:
        if self.problem:
            return self.problem
        parts = [tr("{n} linhas de {m} depois dos filtros", "{n} of {m} rows after filters",
                    n=self.n_rows, m=self.n_all)]
        if self.pv is not None and self.pv.note:
            parts.append(self.pv.note)
        if self.spec.mode == "dataset" and len(self.cols) > Table.MAX_COLS:
            parts.append(tr("a pré-visualização mostra {n} colunas; o .csv leva todas",
                            "the preview shows {n} columns; the .csv has them all",
                            n=Table.MAX_COLS))
        return " · ".join(parts)

    def _color(self, i: int, name: str) -> tuple:
        if name == tr("Outros", "Other") and i > 0:
            return OTHER_COLOR
        return SERIES_COLORS[i % len(SERIES_COLORS)]

    def _render_table(self, width: int) -> None:
        h = self.app.window.height
        top = self.content_top(h) + 14
        self.table.layout(self._right_x(self.app.window.width), top, width, 112)
        limit = adhoc.option(self.app.db, "adhoc_preview_rows")
        cols = self.cols[:Table.MAX_COLS]
        decimal = "."
        body = [[adhoc.display(r.get(c.key), c.kind, decimal) for c in cols]
                for r in self.rows[:limit]]
        title = tr("Pré-visualização · {n} linhas · {m} campos",
                   "Preview · {n} rows · {m} fields", n=self.n_rows, m=len(self.cols))
        self.table.set([c.label for c in cols], body, title,
                       self.problem or tr("Sem linhas com estes filtros.",
                                          "No rows with these filters."))

    def _render_chart(self) -> None:
        chart, pv, spec = self.chart, self.pv, self.spec
        empty = self.problem or tr("Sem dados para esta vista.", "No data for this view.")
        if pv is None:
            chart.show_bars("", [], [], empty)
            return
        if pv.note and not pv.points and pv.empty:
            empty = pv.note
        title = tr("{y} por {x}", "{y} by {x}", y=pv.y_title, x=pv.x_title)
        names = [n for n, _ in pv.series]
        colors = [self._color(i, n) for i, n in enumerate(names)]
        labels = pv.labels
        negative = any(v is not None and v < 0 for _n, vs in pv.series for v in vs)
        if spec.chart == "scatter":
            self._render_scatter(title, empty)
            return
        as_bars = [[max(0.0, v) if v is not None else 0.0 for v in vs] for _n, vs in pv.series]
        if spec.chart == "lines" and len(labels) >= 2:
            lines = [(n, self._carry(vs), colors[i]) for i, (n, vs) in enumerate(pv.series)]
            chart.show_lines(title, lines, labels, empty, fmt=num_text)
        elif spec.chart == "stacked":
            rows = [[as_bars[k][i] for k in range(len(names))] for i in range(len(labels))]
            chart.show_stacked(title, rows, colors, labels, empty, fmt=num_text,
                               legend=names if len(names) > 1 else None)
        elif len(names) > 1:
            rows = [[as_bars[k][i] for k in range(len(names))] for i in range(len(labels))]
            chart.show_clustered(title, rows, colors, labels, empty, fmt=num_text, legend=names)
        else:
            chart.show_bars(title, as_bars[0] if as_bars else [], labels, empty, fmt=num_text)
        if negative and spec.chart in ("bars", "stacked"):
            pv.note = (pv.note + " · " if pv.note else "") + tr(
                "valores negativos não aparecem em colunas (usa linhas)",
                "negative values do not show in columns (use lines)")
        if chart.points:
            last = len(chart.points) - 1
            chart.select(last, self._tip(last))

    @staticmethod
    def _carry(values: list[float | None]) -> list[float]:
        """Para as linhas: um período sem dados repete o valor anterior (o primeiro, o seguinte)."""
        known = [v for v in values if v is not None]
        last = known[0] if known else 0.0
        out = []
        for v in values:
            if v is not None:
                last = v
            out.append(last)
        return out

    def _render_scatter(self, title: str, empty: str) -> None:
        pv = self.pv
        index: dict[str, int] = {}
        pts = []
        for x, y, name in pv.points:
            k = index.setdefault(name, len(index))
            pts.append((x, y, min(k, len(SERIES_COLORS) - 1)))
        legend = [n for n in index if n][:len(SERIES_COLORS)]
        self.chart.show_scatter(title, pts, SERIES_COLORS, legend or None, empty,
                                xfmt=num_text, yfmt=num_text)
        if self.chart.points:
            self.chart.select(0, self._tip(0))

    def _tip(self, idx: int) -> str:
        pv = self.pv
        if pv is None:
            return ""
        if pv.points:
            if idx >= len(pv.points):
                return ""
            x, y, name = pv.points[idx]
            tail = f" · {name}" if name else ""
            return f"{pv.x_title} {num_text(x)} · {pv.y_title} {num_text(y)}{tail}"
        if idx >= len(pv.labels):
            return ""
        parts = [f"{n} {num_text(vs[idx])}" if len(pv.series) > 1 else num_text(vs[idx])
                 for n, vs in pv.series if idx < len(vs) and vs[idx] is not None]
        return f"{pv.labels[idx]}: " + (" · ".join(parts) if parts else "—")

    # -------------------------------------------------------------- entradas

    def on_mouse(self, x: int, y: int) -> bool:
        if self.spec.mode == "chart":
            idx = self.chart.hit(x, y)
            if idx is not None:
                self.chart.select(idx, self._tip(idx))
                return True
        return super().on_mouse(x, y)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol in (key.DELETE, key.BACKSPACE):
            item = self.list.selected
            if item is not None and item.data in ("cyc:from", "cyc:to"):
                if item.data == "cyc:from":
                    self.spec.date_from = ""
                else:
                    self.spec.date_to = ""
                self._touch()
                self.enter()
                return True
        return super().on_key(symbol, modifiers)

    def draw(self) -> None:
        super().draw()
        if self.spec.mode == "chart":
            self.chart.draw()
        else:
            self.table.draw()
        self.note.draw()


# ===================================================================== filtros


class AdHocFiltersPopup(PopupMixin, Screen):
    """Os filtros da vista: um por linha (Enter edita), «Adicionar filtro…» e «Limpar»."""

    W, H = 720, 520

    def __init__(self, app, owner: AdHocScreen):
        super().__init__(app)
        self.owner = owner
        self.back_button = None
        self._init_popup()

    def enter(self) -> None:
        o = self.owner
        spec = o.spec
        src = adhoc.source_of(spec.source)
        limit = adhoc.option(self.app.db, "adhoc_max_filters")
        items = [Item(f"{i + 1}.  {f.text(src)}", value=tr("editar", "edit") + "  ›",
                      action=lambda i=i: self._edit(i)) for i, f in enumerate(spec.filters)]
        if not items:
            items.append(Item(tr("Ainda sem filtros: a vista usa todas as linhas.",
                                 "No filters yet: the view uses every row."), enabled=False))
        items.append(Item(tr("Fechar", "Close"), button=True, action=self.app.pop))
        items.append(Item(tr("Limpar filtros", "Clear filters"), button=True, danger=True,
                          enabled=bool(spec.filters), action=self._clear))
        items.append(Item(tr("Adicionar filtro…", "Add filter…"), button=True, primary=True,
                          enabled=len(spec.filters) < limit, action=self._add))
        self.chrome.set(tr("Filtros", "Filters"),
                        tr("Só entram as linhas que passam em todos os filtros "
                           "(máx. {n}; muda-se nas Definições)",
                           "Only rows that pass every filter are used (max {n}; "
                           "change it in Settings)", n=limit), "")
        self.list.set_items(items, keep_index=True)

    def _add(self) -> None:
        self.app.push(AdHocFilterEditor(self.app, self.owner, None))

    def _edit(self, i: int) -> None:
        self.app.push(AdHocFilterEditor(self.app, self.owner, i))

    def _clear(self) -> None:
        self.owner.spec.filters = []
        self.owner._touch()
        self.enter()


class AdHocFilterEditor(EditPopup):
    """Um filtro: campo, operador e valor. Os campos de categoria dão uma lista com os valores
    que existem; os números e os textos escrevem-se; as datas abrem o calendário."""

    W = 760
    DATE_FIELDS = ("day",)

    def __init__(self, app, owner: AdHocScreen, index: int | None):
        super().__init__(app)
        self.owner = owner
        self.index = index
        self.src = adhoc.source_of(owner.spec.source)
        cur = owner.spec.filters[index] if index is not None and \
            index < len(owner.spec.filters) else None
        first = self.src.fields[0]
        self.field = cur.field if cur else first.key
        self.op = cur.op if cur else adhoc.ops_for(first.kind)[0]
        self.value = cur.value if cur else ""
        self._values: list[str] | None = None

    # ------------------------------------------------------------- estado

    def state(self):
        return (self.field, self.op, self.value)

    def title(self) -> str:
        return tr("Editar filtro", "Edit filter") if self.index is not None else \
            tr("Novo filtro", "New filter")

    def subtitle(self) -> str:
        return tr("Campo · operador · valor", "Field · operator · value")

    def _kind(self) -> str:
        f = self.src.field(self.field)
        return f.kind if f else adhoc.CAT

    def _choices_values(self) -> list[str]:
        if self._values is None or getattr(self, "_values_for", None) != self.field:
            self._values = adhoc.distinct_values(self.owner._source_rows(), self.field)
            self._values_for = self.field
        return self._values

    # -------------------------------------------------------------- linhas

    def rows(self) -> list[Item]:
        src = self.src
        fields = list(src.fields)
        kind = self._kind()
        ops = adhoc.ops_for(kind)
        if self.op not in ops:
            self.op = ops[0]
        out = [
            Item(tr("Campo", "Field"), value=src.field(self.field).label,
                 data="cyc:field",
                 dropdown=Dropdown([f.label for f in fields],
                                   next((i for i, f in enumerate(fields)
                                         if f.key == self.field), 0), self._pick_field,
                                   title=tr("Campo", "Field"))),
            Item(tr("Operador", "Operator"), value=adhoc.op_name(self.op), data="cyc:op",
                 dropdown=Dropdown([adhoc.op_name(o) for o in ops], ops.index(self.op),
                                   self._pick_op, title=tr("Operador", "Operator"))),
        ]
        if kind == adhoc.CAT and self.op != "contains":
            values = self._choices_values()
            cur = values.index(self.value) if self.value in values else 0
            if values:
                out.append(Item(tr("Valor", "Value"), value=self.value or "—",
                                data="cyc:value",
                                dropdown=Dropdown(values, cur, self._pick_value,
                                                  title=tr("Valor", "Value"))))
            else:
                out.append(Item(tr("Valor", "Value"), value="—", enabled=False,
                                detail=tr("sem valores nos dados", "no values in the data")))
        elif kind == adhoc.DATE:
            out.append(Item(tr("Valor", "Value"), value=self.value or "—", data="cyc:day",
                            detail=tr("Enter abre o calendário", "Enter opens the calendar")))
        else:
            hint = tr("escreve um número", "type a number") if kind == adhoc.NUM else \
                tr("escreve o texto", "type the text")
            out.append(Item(tr("Valor", "Value"), value=self.value + "▏", data="text:value",
                            detail=hint))
        return out

    def buttons(self) -> list[Item]:
        out = [Item(tr("Cancelar", "Cancel"), action=self.cancel, button=True)]
        if self.index is not None:
            out.append(Item(tr("Remover", "Remove"), action=self._remove, button=True,
                            danger=True))
        out.append(Item(tr("Aplicar", "Apply"), action=self.save_exit, button=True,
                        primary=True))
        return out

    def saved_message(self) -> str:
        return tr("Filtro aplicado", "Filter applied")

    # ------------------------------------------------------------- escolhas

    def _pick_field(self, k: int) -> None:
        fields = list(self.src.fields)
        new = fields[max(0, min(len(fields) - 1, k))].key
        if new != self.field:
            self.field = new
            self.op = adhoc.ops_for(self._kind())[0]
            self.value = ""

    def _pick_op(self, k: int) -> None:
        ops = adhoc.ops_for(self._kind())
        self.op = ops[max(0, min(len(ops) - 1, k))]

    def _pick_value(self, k: int) -> None:
        values = self._choices_values()
        if values:
            self.value = values[max(0, min(len(values) - 1, k))]

    def cycle(self, field: str, step: int) -> None:
        if field == "field":
            fields = list(self.src.fields)
            i = next((j for j, f in enumerate(fields) if f.key == self.field), 0)
            self._pick_field((i + step) % len(fields))
        elif field == "op":
            ops = adhoc.ops_for(self._kind())
            self._pick_op((ops.index(self.op) + step) % len(ops))
        elif field == "value":
            values = self._choices_values()
            if values:
                i = values.index(self.value) if self.value in values else -1
                self._pick_value((i + step) % len(values))
        elif field == "day":
            self.date_set("day", ((parse_date(self.value) or date.today())
                                  + timedelta(days=step)).isoformat())

    def date_get(self, field: str) -> str | None:
        return self.value or date.today().isoformat()

    def date_set(self, field: str, iso: str) -> None:
        if parse_date(iso) is not None:
            self.value = iso
            self.enter()

    def text_input(self, field: str, text: str) -> None:
        if field == "value":
            if self._kind() == adhoc.NUM:
                text = "".join(c for c in text if c in "0123456789.,-")
            self.value = (self.value + text)[:60]
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "value":
            self.value = self.value[:-1]
        self.enter()

    # ---------------------------------------------------------------- gravar

    def commit(self) -> bool:
        kind = self._kind()
        value = self.value.strip()
        if not value:
            self.app.message(tr("Falta o valor do filtro", "The filter needs a value"))
            return False
        if kind == adhoc.NUM and parse_number(value) is None:
            self.app.message(tr("O valor tem de ser um número", "The value must be a number"))
            return False
        if kind == adhoc.DATE and parse_date(value) is None:
            self.app.message(tr("Escolhe uma data no calendário", "Pick a date in the calendar"))
            return False
        flt = adhoc.Filter(self.field, self.op, value)
        spec = self.owner.spec
        if self.index is not None and self.index < len(spec.filters):
            spec.filters[self.index] = flt
        else:
            spec.filters.append(flt)
        self.owner._touch()
        return True

    def _remove(self) -> None:
        spec = self.owner.spec
        if self.index is not None and self.index < len(spec.filters):
            del spec.filters[self.index]
            self.owner._touch()
        self._saved_state = self.state()
        self.close()


# ===================================================================== exportar


class AdHocExportPopup(EditPopup):
    """Exportar para .csv: o nome do ficheiro e o separador de valores à escolha (e o decimal,
    o cabeçalho e o BOM). O que se escolhe aqui só vale para este ficheiro; os valores por
    omissão estão nas Definições → Análise AdHoc."""

    W = 820

    def __init__(self, app, owner: AdHocScreen):
        super().__init__(app)
        self.owner = owner
        db = app.db
        self.name = f"perennia-{owner.spec.source}-{date.today():%Y%m%d}"
        self.sep = str(adhoc.option(db, "adhoc_csv_sep"))
        if self.sep not in adhoc.SEPARATORS:
            self.sep = ";"
        self.decimal = str(adhoc.option(db, "adhoc_csv_decimal"))
        if self.decimal not in adhoc.DECIMALS:
            self.decimal = "."
        self.bom = bool(adhoc.option(db, "adhoc_csv_bom"))
        self.header = "label"
        self.what = "dataset"
        self.folder = adhoc.export_dir(db, app.data_dir)
        self.done_path: Path | None = None

    def state(self):
        return ""                                   # exportar não deixa «alterações por guardar»

    def title(self) -> str:
        return tr("Exportar para .csv", "Export to .csv")

    def subtitle(self) -> str:
        return tr("Escreve o nome do ficheiro; Enter abre as listas",
                  "Type the file name; Enter opens the lists")

    def _payload(self):
        cache = self.__dict__.setdefault("_payloads", {})
        if self.what not in cache:
            cache[self.what] = self.owner.export_payload(self.what)
        return cache[self.what]

    def rows(self) -> list[Item]:
        cols, rows = self._payload()
        out: list[Item] = []
        if self.owner.spec.mode == "chart":
            labels = [tr("Dataset (campos e filtros)", "Dataset (fields and filters)"),
                      tr("Números do gráfico", "Chart numbers")]
            out.append(Item(tr("O que exportar", "What to export"),
                            value=labels[0 if self.what == "dataset" else 1], data="cyc:what",
                            dropdown=Dropdown(labels, 0 if self.what == "dataset" else 1,
                                              self._pick_what)))
        out.append(Item(tr("Nome do ficheiro", "File name"), value=self.name + "▏",
                        detail=".csv", data="text:name"))
        seps = list(adhoc.SEPARATORS)
        out.append(Item(tr("Separador de valores", "Value separator"),
                        value=adhoc.sep_name(self.sep), data="cyc:sep",
                        dropdown=Dropdown([adhoc.sep_name(s) for s in seps],
                                          seps.index(self.sep), self._pick_sep)))
        decs = list(adhoc.DECIMALS)
        out.append(Item(tr("Separador decimal", "Decimal separator"),
                        value=("«.»" if self.decimal == "." else "«,»"), data="cyc:decimal",
                        detail=(tr("igual ao separador: usa o ponto", "same as separator: "
                                   "uses the dot") if self.decimal == self.sep else ""),
                        dropdown=Dropdown(["«.» " + tr("ponto", "dot"),
                                           "«,» " + tr("vírgula", "comma")],
                                          decs.index(self.decimal), self._pick_decimal)))
        out.append(Item(tr("Cabeçalho", "Header"),
                        value=tr("nomes legíveis", "readable names") if self.header == "label"
                        else tr("chaves técnicas", "technical keys"), data="cyc:header",
                        dropdown=Dropdown([tr("Nomes legíveis", "Readable names"),
                                           tr("Chaves técnicas", "Technical keys")],
                                          0 if self.header == "label" else 1,
                                          self._pick_header)))
        out.append(Item(tr("UTF-8 com BOM", "UTF-8 with BOM"),
                        value=tr("sim", "yes") if self.bom else tr("não", "no"),
                        data="cyc:bom", detail=tr("o Excel abre bem os acentos",
                                                  "Excel opens accents correctly"),
                        dropdown=Dropdown([tr("Sim", "Yes"), tr("Não", "No")],
                                          0 if self.bom else 1, self._pick_bom)))
        out.append(Item(tr("Pasta", "Folder"), value=fit_text(str(self.folder), 380, 12),
                        enabled=False, detail=tr("muda nas Definições", "change in Settings")))
        out.append(Item(tr("Conteúdo", "Contents"),
                        value=tr("{n} linhas · {m} colunas", "{n} rows · {m} columns",
                                 n=len(rows), m=len(cols)), enabled=False))
        return out

    def buttons(self) -> list[Item]:
        return [Item(tr("Cancelar", "Cancel"), action=self.close, button=True),
                Item(tr("Exportar", "Export"), action=self.save_exit, button=True,
                     primary=True)]

    def on_save(self) -> bool:
        self.save_exit()
        return True

    def cancel(self) -> None:
        self.close()

    def saved_message(self) -> str:
        if self.done_path is None:
            return ""
        return tr("Exportado: {p}", "Exported: {p}", p=str(self.done_path))

    # ------------------------------------------------------------- escolhas

    def _pick_what(self, k: int) -> None:
        self.what = ("dataset", "chart")[k]

    def _pick_sep(self, k: int) -> None:
        self.sep = list(adhoc.SEPARATORS)[k]

    def _pick_decimal(self, k: int) -> None:
        self.decimal = adhoc.DECIMALS[k]

    def _pick_header(self, k: int) -> None:
        self.header = ("label", "key")[k]

    def _pick_bom(self, k: int) -> None:
        self.bom = k == 0

    def cycle(self, field: str, step: int) -> None:
        if field == "what":
            self._pick_what((0 if self.what == "dataset" else 1) ^ 1)
        elif field == "sep":
            seps = list(adhoc.SEPARATORS)
            self._pick_sep((seps.index(self.sep) + step) % len(seps))
        elif field == "decimal":
            self._pick_decimal((adhoc.DECIMALS.index(self.decimal) + step) % 2)
        elif field == "header":
            self._pick_header((0 if self.header == "label" else 1) ^ 1)
        elif field == "bom":
            self.bom = not self.bom

    def text_input(self, field: str, text: str) -> None:
        if field == "name":
            self.name = (self.name + text)[:100]
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "name":
            self.name = self.name[:-1]
        self.enter()

    # ---------------------------------------------------------------- gravar

    def commit(self) -> bool:
        cols, rows = self._payload()
        if not cols:
            self.app.message(tr("Nada para exportar", "Nothing to export"))
            return False
        try:
            self.done_path = adhoc.export_csv(cols, rows, self.folder, self.name, self.sep,
                                              self.decimal, self.bom, self.header)
        except OSError as e:
            self.app.message(tr("Não consegui gravar: {e}", "Could not save: {e}", e=str(e)))
            return False
        return True


# ===================================================================== guardar vista


class SaveViewPopup(EditPopup):
    """Dá um nome à vista atual (fonte, campos, filtros e gráfico) para a poder voltar a abrir."""

    W = 700
    MIN_H = 260

    def __init__(self, app, owner: AdHocScreen):
        super().__init__(app)
        self.owner = owner
        self.name = owner.view_name

    def state(self):
        return self.name

    def title(self) -> str:
        return tr("Guardar vista", "Save view")

    def subtitle(self) -> str:
        return tr("Um nome que já exista é substituído",
                  "A name that already exists is replaced")

    def rows(self) -> list[Item]:
        return [Item(tr("Nome da vista", "View name"), value=self.name + "▏",
                     data="text:name")]

    def text_input(self, field: str, text: str) -> None:
        self.name = (self.name + text)[:60]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.name = self.name[:-1]
        self.enter()

    def saved_message(self) -> str:
        return tr("Vista guardada: {n}", "View saved: {n}", n=self.name.strip())

    def commit(self) -> bool:
        try:
            adhoc.save_view(self.app.db, self.name, self.owner.spec)
        except ValueError as e:
            self.app.message(str(e))
            return False
        self.owner.view_name = " ".join(self.name.split())[:60]
        return True
