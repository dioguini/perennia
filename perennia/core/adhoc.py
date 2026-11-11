"""Análise ad hoc: o «centro exploratório» das Estatísticas gerais.

Duas coisas, sobre os mesmos dados:

1. **Construir um dataset** — escolher a fonte (sessões, séries de força, diário, análises,
   testes), os campos que se querem e os filtros, ver as primeiras linhas e **exportar em
   .csv** (nome do ficheiro e separador à escolha).
2. **Um gráfico dinâmico, ao estilo Power BI** — escolher o eixo X, o valor (com soma, média,
   mínimo, máximo, mediana ou contagem), a legenda (uma série por categoria) e o tipo de
   gráfico (colunas, colunas empilhadas, linhas ou dispersão).

Tudo aqui é lógica pura (sem janela): as linhas vêm da base de dados local, os filtros e as
agregações fazem-se em Python, e uma «vista» (`Spec`) guarda-se como JSON nas Definições
(`adhoc_state` é a última; `adhoc_views` são as que deste nome). Nada do Strava entra aqui, e
nada daqui sai da máquina: o agente de IA só vê o que o ecrã mostra, e só a configuração.
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import options
from . import sports as sp
from . import stats
from .db import Database
from .i18n import tr

DATE, NUM, CAT, TEXT = "date", "number", "category", "text"

SETTING_STATE = "adhoc_state"
SETTING_VIEWS = "adhoc_views"

# As opções (valores por omissão e limites) vivem em `options.py`; mudam-se nas
# Definições → Avançado → Análise AdHoc.
DEFAULTS: dict[str, Any] = options.defaults("adhoc_")
LIMITS: dict[str, tuple[int, int]] = options.limits("adhoc_")

SEPARATORS = {";": "; (ponto e vírgula)", ",": ", (vírgula)", "\t": "Tab", "|": "| (barra)"}
DECIMALS = (".", ",")
GRAINS = ("day", "week", "month", "year")
AGGS = ("sum", "avg", "min", "max", "median", "count")
CHARTS = ("bars", "stacked", "lines", "scatter")
PERIODS = ("all", "7", "30", "90", "365", "ytd", "custom")
OPS = ("=", "!=", ">", ">=", "<", "<=", "contains")
ROWS = "@rows"                  # «contagem de linhas» como valor do eixo Y


def option(db: Database | None, key: str):
    """O valor de uma opção da análise (já dentro dos limites)."""
    return options.get(db, key)


# ===================================================================== nomes (PT/EN)


def grain_name(g: str) -> str:
    return {"day": tr("dia", "day"), "week": tr("semana", "week"), "month": tr("mês", "month"),
            "year": tr("ano", "year")}[g]


def agg_name(a: str) -> str:
    return {"sum": tr("soma", "sum"), "avg": tr("média", "average"),
            "min": tr("mínimo", "minimum"), "max": tr("máximo", "maximum"),
            "median": tr("mediana", "median"), "count": tr("contagem", "count")}[a]


def chart_name(c: str) -> str:
    return {"bars": tr("Colunas", "Columns"), "stacked": tr("Colunas empilhadas", "Stacked columns"),
            "lines": tr("Linhas", "Lines"), "scatter": tr("Dispersão", "Scatter")}[c]


def period_name(p: str) -> str:
    return {"all": tr("Tudo", "All time"), "7": tr("Últimos 7 dias", "Last 7 days"),
            "30": tr("Últimos 30 dias", "Last 30 days"), "90": tr("Últimos 90 dias", "Last 90 days"),
            "365": tr("Último ano", "Last year"), "ytd": tr("Este ano", "This year"),
            "custom": tr("Datas à escolha", "Custom dates")}[p]


def op_name(op: str) -> str:
    return {"=": "=", "!=": "≠", ">": ">", ">=": "≥", "<": "<", "<=": "≤",
            "contains": tr("contém", "contains")}[op]


def sep_name(sep: str) -> str:
    return {";": tr("; (ponto e vírgula)", "; (semicolon)"), ",": tr(", (vírgula)", ", (comma)"),
            "\t": "Tab", "|": tr("| (barra)", "| (pipe)")}.get(sep, sep)


# ===================================================================== campos e fontes


@dataclass(frozen=True)
class Field:
    key: str
    pt: str
    en: str
    kind: str
    unit: str = ""

    @property
    def label(self) -> str:
        name = tr(self.pt, self.en)
        return f"{name} ({self.unit})" if self.unit else name


def _f(key, pt, en, kind, unit=""):
    return Field(key, pt, en, kind, unit)


TIME_FIELDS = (
    _f("date", "Data", "Date", DATE),
    _f("week", "Semana", "Week", CAT),
    _f("month", "Mês", "Month", CAT),
    _f("year", "Ano", "Year", CAT),
    _f("weekday", "Dia da semana", "Weekday", CAT),
)

SESSION_FIELDS = TIME_FIELDS + (
    _f("hour", "Hora do dia", "Hour of day", NUM, "h"),
    _f("sport", "Desporto", "Sport", CAT),
    _f("origin", "Origem", "Origin", CAT),
    _f("name", "Nome", "Name", TEXT),
    _f("duration_min", "Duração", "Duration", NUM, "min"),
    _f("moving_min", "Tempo em movimento", "Moving time", NUM, "min"),
    _f("distance_km", "Distância", "Distance", NUM, "km"),
    _f("ascent_m", "Subida", "Ascent", NUM, "m"),
    _f("avg_speed_kmh", "Velocidade média", "Average speed", NUM, "km/h"),
    _f("avg_power_w", "Potência média", "Average power", NUM, "W"),
    _f("np_w", "Potência normalizada", "Normalized power", NUM, "W"),
    _f("max_power_w", "Potência máxima", "Maximum power", NUM, "W"),
    _f("avg_hr", "FC média", "Average HR", NUM, "bpm"),
    _f("max_hr", "FC máxima", "Maximum HR", NUM, "bpm"),
    _f("avg_cadence", "Cadência média", "Average cadence", NUM, "rpm"),
    _f("load", "Carga (TSS)", "Load (TSS)", NUM),
    _f("intensity_factor", "Fator de intensidade", "Intensity factor", NUM),
    _f("work_kj", "Trabalho", "Work", NUM, "kJ"),
    _f("calories", "Calorias", "Calories", NUM, "kcal"),
    _f("sets", "Séries", "Sets", NUM),
    _f("reps", "Repetições", "Reps", NUM),
    _f("volume_kg", "Volume", "Volume", NUM, "kg"),
    _f("avg_rpe", "RPE médio", "Average RPE", NUM),
)

SET_FIELDS = TIME_FIELDS + (
    _f("session", "Sessão", "Session", TEXT),
    _f("exercise", "Exercício", "Exercise", CAT),
    _f("category", "Categoria do exercício", "Exercise category", CAT),
    _f("set_no", "N.º da série", "Set number", NUM),
    _f("reps", "Repetições", "Reps", NUM),
    _f("load_kg", "Carga", "Load", NUM, "kg"),
    _f("rpe", "RPE", "RPE", NUM),
    _f("volume_kg", "Volume (reps × carga)", "Volume (reps × load)", NUM, "kg"),
    _f("est_1rm_kg", "1RM estimado", "Estimated 1RM", NUM, "kg"),
    _f("duration_s", "Duração da série", "Set duration", NUM, "s"),
    _f("avg_hr", "FC média", "Average HR", NUM, "bpm"),
    _f("planned_reps", "Repetições previstas", "Planned reps", NUM),
    _f("planned_load_kg", "Carga prevista", "Planned load", NUM, "kg"),
)

DAILY_FIELDS = TIME_FIELDS + (
    _f("metric", "Métrica", "Metric", CAT),
    _f("group", "Grupo", "Group", CAT),
    _f("value", "Valor", "Value", NUM),
    _f("unit", "Unidade", "Unit", CAT),
    _f("text", "Texto", "Text", TEXT),
    _f("notes", "Notas", "Notes", TEXT),
    _f("origin", "Origem", "Origin", CAT),
)

LAB_FIELDS = TIME_FIELDS + (
    _f("lab", "Laboratório", "Lab", CAT),
    _f("marker", "Marcador", "Marker", CAT),
    _f("value", "Valor", "Value", NUM),
    _f("unit", "Unidade", "Unit", CAT),
    _f("ref_low", "Referência mínima", "Reference low", NUM),
    _f("ref_high", "Referência máxima", "Reference high", NUM),
    _f("status", "Estado", "Status", CAT),
    _f("comment", "Comentário", "Comment", TEXT),
)

TEST_FIELDS = TIME_FIELDS + (
    _f("sport", "Desporto", "Sport", CAT),
    _f("test", "Teste", "Test", CAT),
    _f("value", "Resultado", "Result", NUM),
    _f("unit", "Unidade", "Unit", CAT),
    _f("better", "Melhor é", "Better is", CAT),
    _f("notes", "Notas", "Notes", TEXT),
)


@dataclass(frozen=True)
class Source:
    key: str
    pt: str
    en: str
    fields: tuple[Field, ...]
    loader: Callable[[Database], list[dict]]
    agent_category: str | None = None        # a categoria do agente (`agent_share`) que a cobre

    @property
    def label(self) -> str:
        return tr(self.pt, self.en)

    def field(self, key: str) -> Field | None:
        return next((f for f in self.fields if f.key == key), None)


# ------------------------------------------------------------------- tempo


def _parse_iso(value: str | None) -> datetime | None:
    """Uma data/hora guardada → hora local. Aceita o formato da app («…Z») e os de fora
    («2026-03-01T10:00:00+00:00», «2026-03-01 10:00:00»); sem fuso, conta como hora local."""
    if not value:
        return None
    when = stats._parse(value)
    if when is None:
        try:
            when = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return when.astimezone()


def _weekday_name(d: date) -> str:
    names = (tr("Seg", "Mon"), tr("Ter", "Tue"), tr("Qua", "Wed"), tr("Qui", "Thu"),
             tr("Sex", "Fri"), tr("Sáb", "Sat"), tr("Dom", "Sun"))
    return f"{d.isoweekday()} {names[d.weekday()]}"           # «1 Seg»: ordena-se bem


def time_columns(d: date | None, when: datetime | None = None) -> dict:
    """date, week, month, year e weekday (e hour, se houver hora) de um dia."""
    if d is None:
        return {"date": None, "week": None, "month": None, "year": None, "weekday": None,
                "hour": None}
    iso = d.isocalendar()
    return {"date": d.isoformat(), "week": f"{iso[0]}-W{iso[1]:02d}", "month": d.strftime("%Y-%m"),
            "year": str(d.year), "weekday": _weekday_name(d),
            "hour": (when.hour + when.minute / 60.0) if when is not None else None}


def _day(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _min(seconds) -> float | None:
    v = _num(seconds)
    return None if v is None else round(v / 60.0, 2)


def _km(metres) -> float | None:
    v = _num(metres)
    return None if v is None else round(v / 1000.0, 3)


def _speed(dist_m, secs) -> float | None:
    d, s = _num(dist_m), _num(secs)
    return round(d / s * 3.6, 2) if d and s and s > 0 else None


# ------------------------------------------------------------------ carregar


def _blank(fields: tuple[Field, ...]) -> dict:
    return {f.key: None for f in fields}


def _rows_of(db: Database, sql: str, args: tuple = ()) -> list:
    try:
        return db.conn.execute(sql, args).fetchall()
    except Exception:                      # a tabela de um desporto ainda não existe
        return []


def load_sessions(db: Database) -> list[dict]:
    out: list[dict] = []

    def add(sport_key: str, origin: str, started: str | None, **cols) -> None:
        when = _parse_iso(started)
        row = _blank(SESSION_FIELDS)
        row.update(time_columns(when.date() if when else None, when))
        row["sport"] = sp.name(sport_key)
        row["origin"] = origin
        row.update(cols)
        if row["date"] is not None:
            out.append(row)

    for r in _rows_of(db, "SELECT * FROM rides WHERE status='completed'"):
        secs = r["moving_s"] or r["elapsed_s"]
        add("cycling", "Perennia", r["started_at"], name=r["name"],
            duration_min=_min(r["elapsed_s"]), moving_min=_min(r["moving_s"]),
            distance_km=_km(r["distance_m"]), ascent_m=_num(r["ascent_m"]),
            avg_speed_kmh=_speed(r["distance_m"], secs), avg_power_w=_num(r["avg_power_w"]),
            np_w=_num(r["np_w"]), max_power_w=_num(r["max_power_w"]), avg_hr=_num(r["avg_hr"]),
            max_hr=_num(r["max_hr"]), avg_cadence=_num(r["avg_cadence"]), load=_num(r["tss"]),
            intensity_factor=_num(r["intensity_factor"]), work_kj=_num(r["work_kj"]))
    for r in _rows_of(db, "SELECT * FROM row_sessions WHERE status='completed'"):
        secs = r["moving_s"] or r["elapsed_s"]
        add("rowing", "Perennia", r["started_at"], name=r["name"],
            duration_min=_min(r["elapsed_s"]), moving_min=_min(r["moving_s"]),
            distance_km=_km(r["distance_m"]), avg_speed_kmh=_speed(r["distance_m"], secs),
            avg_power_w=_num(r["avg_power_w"]), np_w=_num(r["np_w"]),
            max_power_w=_num(r["max_power_w"]), avg_hr=_num(r["avg_hr"]),
            max_hr=_num(r["max_hr"]), avg_cadence=_num(r["avg_spm"]), load=_num(r["load"]),
            calories=_num(r["kcal"]))
    for r in _rows_of(db, "SELECT * FROM endurance_sessions WHERE status='completed'"):
        secs = r["moving_s"] or r["elapsed_s"]
        add(r["sport"] or "running", "Perennia", r["started_at"], name=r["name"],
            duration_min=_min(r["elapsed_s"]), moving_min=_min(r["moving_s"]),
            distance_km=_km(r["distance_m"]), avg_speed_kmh=_speed(r["distance_m"], secs),
            avg_hr=_num(r["avg_hr"]), max_hr=_num(r["max_hr"]), load=_num(r["load"]))
    for r in _rows_of(db, "SELECT * FROM strength_sessions WHERE status='completed'"):
        add("gym", "Perennia", r["started_at"], name=r["name"],
            duration_min=_min(r["elapsed_s"]), avg_hr=_num(r["avg_hr"]), max_hr=_num(r["max_hr"]),
            load=_num(r["load"]), sets=_num(r["total_sets"]), reps=_num(r["total_reps"]),
            volume_kg=_num(r["volume_kg"]), avg_rpe=_num(r["avg_rpe"]))
    for r in _rows_of(db, "SELECT * FROM synced_activities"):
        secs = r["moving_s"] or r["elapsed_s"]
        add(r["sport"] or "other", str(r["source"] or "garmin").capitalize(), r["started_at"],
            name=r["name"], duration_min=_min(r["elapsed_s"]), moving_min=_min(r["moving_s"]),
            distance_km=_km(r["distance_m"]), ascent_m=_num(r["ascent_m"]),
            avg_speed_kmh=_speed(r["distance_m"], secs), avg_power_w=_num(r["avg_power_w"]),
            np_w=_num(r["np_w"]), avg_hr=_num(r["avg_hr"]), max_hr=_num(r["max_hr"]),
            load=_num(r["tss"]) if r["tss"] is not None else _num(r["training_load"]),
            intensity_factor=_num(r["if_value"]), calories=_num(r["calories"]))
    out.sort(key=lambda r: (r["date"], r["hour"] or 0))
    return out


def load_sets(db: Database) -> list[dict]:
    out: list[dict] = []
    sql = ("SELECT s.*, ss.started_at AS started, ss.name AS session_name, e.name AS ex_name,"
           " e.category AS ex_category FROM strength_sets s"
           " JOIN strength_sessions ss ON ss.id = s.session_id"
           " LEFT JOIN exercises e ON e.id = s.exercise_id WHERE ss.status = 'completed'")
    for r in _rows_of(db, sql):
        when = _parse_iso(r["started"])
        row = _blank(SET_FIELDS)
        row.update(time_columns(when.date() if when else None, when))
        reps, load = _num(r["reps"]), _num(r["load_kg"])
        end, start = _num(r["end_t_s"]), _num(r["start_t_s"])
        row.update(session=r["session_name"], exercise=r["ex_name"], category=r["ex_category"],
                   set_no=_num(r["set_no"]), reps=reps, load_kg=load, rpe=_num(r["rpe"]),
                   volume_kg=round(reps * load, 2) if reps and load else None,
                   est_1rm_kg=round(load * (1 + reps / 30.0), 2) if reps and load else None,
                   duration_s=(end - start) if end is not None and start is not None else None,
                   avg_hr=_num(r["avg_hr"]), planned_reps=_num(r["planned_reps"]),
                   planned_load_kg=_num(r["planned_load_kg"]))
        row.pop("hour", None)
        if row["date"] is not None:
            out.append(row)
    out.sort(key=lambda r: (r["date"], r["set_no"] or 0))
    return out


def load_daily(db: Database) -> list[dict]:
    out: list[dict] = []
    sql = ("SELECT v.day, v.num, v.txt, v.notes, v.source, m.name, m.unit, m.grp"
           " FROM daily_values v JOIN metric_defs m ON m.id = v.metric_id")
    for r in _rows_of(db, sql):
        if (r["source"] or "") == "strava":              # nada do Strava (acordo da API)
            continue
        row = _blank(DAILY_FIELDS)
        row.update(time_columns(_day(r["day"])))
        row.pop("hour", None)
        row.update(metric=r["name"], group=r["grp"], value=_num(r["num"]), unit=r["unit"],
                   text=r["txt"], notes=r["notes"], origin=r["source"])
        if row["date"] is not None:
            out.append(row)
    out.sort(key=lambda r: (r["date"], r["metric"] or ""))
    return out


def load_labs(db: Database) -> list[dict]:
    out: list[dict] = []
    sql = ("SELECT r.done_on, r.lab, x.* FROM lab_results x"
           " JOIN lab_reports r ON r.id = x.report_id")
    for r in _rows_of(db, sql):
        row = _blank(LAB_FIELDS)
        row.update(time_columns(_day(r["done_on"])))
        row.pop("hour", None)
        value, lo, hi = _num(r["value"]), _num(r["ref_low"]), _num(r["ref_high"])
        status = None
        if value is not None:
            status = (tr("baixo", "low") if lo is not None and value < lo else
                      tr("alto", "high") if hi is not None and value > hi else
                      tr("normal", "normal"))
        row.update(lab=r["lab"], marker=r["marker"], value=value, unit=r["unit"], ref_low=lo,
                   ref_high=hi, status=status, comment=r["comment"])
        if row["date"] is not None:
            out.append(row)
    out.sort(key=lambda r: (r["date"], r["marker"] or ""))
    return out


def load_tests(db: Database) -> list[dict]:
    out: list[dict] = []
    sql = ("SELECT x.done_on, x.value, x.notes, t.name, t.unit, t.sport, t.better"
           " FROM test_results x JOIN fitness_tests t ON t.id = x.test_id")
    for r in _rows_of(db, sql):
        row = _blank(TEST_FIELDS)
        row.update(time_columns(_day(r["done_on"])))
        row.pop("hour", None)
        row.update(sport=sp.name(r["sport"]) if r["sport"] else None, test=r["name"],
                   value=_num(r["value"]), unit=r["unit"], better=r["better"], notes=r["notes"])
        if row["date"] is not None:
            out.append(row)
    out.sort(key=lambda r: (r["date"], r["test"] or ""))
    return out


SOURCES: dict[str, Source] = {s.key: s for s in (
    Source("sessions", "Sessões (todos os desportos)", "Sessions (all sports)", SESSION_FIELDS,
           load_sessions, "training"),
    Source("sets", "Séries de força (uma linha por série)", "Strength sets (one row per set)",
           SET_FIELDS, load_sets, "strength"),
    Source("daily", "Diário (saúde e alimentação)", "Daily log (health and food)", DAILY_FIELDS,
           load_daily, "health"),
    Source("labs", "Análises clínicas (um marcador por linha)", "Lab results (one marker per row)",
           LAB_FIELDS, load_labs, "labs"),
    Source("tests", "Testes de longevidade", "Longevity tests", TEST_FIELDS, load_tests, "tests"),
)}
SOURCE_ORDER = tuple(SOURCES)


def source_of(key: str) -> Source:
    return SOURCES.get(key) or SOURCES["sessions"]


def load(db: Database, source: str) -> list[dict]:
    return source_of(source).loader(db)


# ===================================================================== vistas (specs)


@dataclass
class Filter:
    field: str
    op: str = "="
    value: str = ""

    def text(self, src: Source) -> str:
        f = src.field(self.field)
        return f"{f.label if f else self.field} {op_name(self.op)} {self.value}"


@dataclass
class Spec:
    """Tudo o que define uma vista: a fonte, o dataset (campos e filtros) e o gráfico."""
    mode: str = "chart"                  # «chart» ou «dataset»
    source: str = "sessions"
    fields: list[str] = field(default_factory=lambda: [
        "date", "sport", "name", "duration_min", "distance_km", "avg_hr", "load"])
    filters: list[Filter] = field(default_factory=list)
    period: str = "all"
    date_from: str = ""
    date_to: str = ""
    x: str = "week"
    grain: str = "week"
    y: str = "duration_min"
    agg: str = "sum"
    series: str = ""
    chart: str = "bars"
    sort: str = "x"                      # «x» (natural) ou «value» (maior primeiro)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["filters"] = [asdict(f) for f in self.filters]
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> "Spec":
        spec = cls()
        raw = raw or {}
        for k in ("mode", "source", "period", "date_from", "date_to", "x", "grain", "y", "agg",
                  "series", "chart", "sort"):
            if isinstance(raw.get(k), str):
                setattr(spec, k, raw[k])
        if isinstance(raw.get("fields"), list):
            spec.fields = [str(x) for x in raw["fields"]]
        spec.filters = [Filter(str(f.get("field", "")), str(f.get("op", "=")),
                               str(f.get("value", "")))
                        for f in raw.get("filters") or [] if isinstance(f, dict)]
        return spec.clean()

    def clean(self) -> "Spec":
        """Põe a vista em ordem: campos que existem, valores válidos."""
        src = source_of(self.source)
        self.source = src.key
        valid = {f.key for f in src.fields}
        if self.mode not in ("chart", "dataset"):
            self.mode = "chart"
        self.fields = [k for k in dict.fromkeys(self.fields) if k in valid] or \
            [f.key for f in src.fields[:6]]
        self.filters = [f for f in self.filters if f.field in valid and f.op in OPS]
        if self.period not in PERIODS:
            self.period = "all"
        if self.grain not in GRAINS:
            self.grain = "week"
        if self.agg not in AGGS:
            self.agg = "sum"
        if self.chart not in CHARTS:
            self.chart = "bars"
        if self.sort not in ("x", "value"):
            self.sort = "x"
        nums = [f.key for f in src.fields if f.kind == NUM]
        cats = [f.key for f in src.fields if f.kind in (CAT, DATE)]
        if self.x not in valid:
            self.x = "date" if "date" in valid else src.fields[0].key
        if self.y != ROWS and self.y not in nums:
            self.y = nums[0] if nums else ROWS
        if self.series and self.series not in cats + [f.key for f in src.fields if f.kind == TEXT]:
            self.series = ""
        if self.series == self.x:
            self.series = ""
        if self.y == ROWS:
            self.agg = "count"
        return self

    def copy(self) -> "Spec":
        return Spec.from_dict(self.to_dict())


def ops_for(kind: str) -> tuple[str, ...]:
    """Os operadores que fazem sentido para o tipo de campo."""
    if kind == NUM:
        return ("=", "!=", ">", ">=", "<", "<=")
    if kind == DATE:
        return ("=", ">=", "<=", ">", "<")
    if kind == TEXT:
        return ("contains", "=", "!=")
    return ("=", "!=", "contains")


def x_fields(src: Source) -> list[Field]:
    return list(src.fields)


def y_fields(src: Source) -> list[Field]:
    return [f for f in src.fields if f.kind == NUM]


def series_fields(src: Source, x: str = "") -> list[Field]:
    return [f for f in src.fields if f.kind == CAT and f.key != x]


def defaults_for(source: str) -> Spec:
    """Uma vista de partida com sentido para cada fonte (os campos mudam de fonte para fonte)."""
    src = source_of(source)
    base = {
        "sessions": dict(fields=["date", "sport", "name", "duration_min", "distance_km",
                                 "avg_hr", "load"], x="week", y="duration_min", agg="sum",
                         series="", chart="bars"),
        "sets": dict(fields=["date", "session", "exercise", "set_no", "reps", "load_kg", "rpe",
                             "volume_kg"], x="week", y="volume_kg", agg="sum", series="",
                     chart="bars"),
        "daily": dict(fields=["date", "metric", "value", "unit"], x="date", grain="week",
                      y="value", agg="avg", series="metric", chart="lines"),
        "labs": dict(fields=["date", "lab", "marker", "value", "unit", "ref_low", "ref_high",
                             "status"], x="date", grain="month", y="value", agg="avg",
                     series="marker", chart="lines"),
        "tests": dict(fields=["date", "sport", "test", "value", "unit"], x="date",
                      grain="month", y="value", agg="avg", series="test", chart="lines"),
    }.get(src.key, {})
    return Spec.from_dict({"source": src.key, **base})


# ===================================================================== filtros


def period_range(spec: Spec, today: date | None = None) -> tuple[str | None, str | None]:
    today = today or date.today()
    p = spec.period
    if p in ("7", "30", "90", "365"):
        return (today - timedelta(days=int(p))).isoformat(), today.isoformat()
    if p == "ytd":
        return date(today.year, 1, 1).isoformat(), today.isoformat()
    if p == "custom":
        return (spec.date_from or None), (spec.date_to or None)
    return None, None


def _compare(a, op: str, b: str, kind: str) -> bool:
    if a is None:
        return False
    if kind == NUM:
        x, y = _num(a), _num(str(b).replace(",", "."))
        if x is None or y is None:
            return False
        return {"=": x == y, "!=": x != y, ">": x > y, ">=": x >= y, "<": x < y,
                "<=": x <= y}.get(op, False)
    x, y = str(a), str(b)
    if op == "contains":
        return y.lower() in x.lower()
    if kind == DATE:
        return {"=": x[:10] == y[:10], "!=": x[:10] != y[:10], ">": x[:10] > y[:10],
                ">=": x[:10] >= y[:10], "<": x[:10] < y[:10], "<=": x[:10] <= y[:10]}.get(op, False)
    xl, yl = x.lower(), y.lower()
    return {"=": xl == yl, "!=": xl != yl}.get(op, False)


def apply_filters(rows: list[dict], spec: Spec, today: date | None = None) -> list[dict]:
    src = source_of(spec.source)
    lo, hi = period_range(spec, today)
    out = rows
    if lo or hi:
        out = [r for r in out if r.get("date") and (not lo or r["date"] >= lo)
               and (not hi or r["date"] <= hi)]
    for flt in spec.filters:
        f = src.field(flt.field)
        if f is None:
            continue
        out = [r for r in out if _compare(r.get(flt.field), flt.op, flt.value, f.kind)]
    return out


def distinct_values(rows: list[dict], key: str, limit: int = 200) -> list[str]:
    seen: dict[str, None] = {}
    for r in rows:
        v = r.get(key)
        if v is not None and v != "":
            seen[str(v)] = None
            if len(seen) >= limit:
                break
    return sorted(seen)


# ===================================================================== dataset


def dataset(db: Database, spec: Spec) -> tuple[list[Field], list[dict]]:
    """As colunas escolhidas (pela ordem da fonte) e as linhas já filtradas."""
    src = source_of(spec.source)
    cols = [f for f in src.fields if f.key in spec.fields]
    return cols, apply_filters(load(db, spec.source), spec)


def display(value, kind: str = TEXT, decimal: str = ".") -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))
        return text.replace(".", decimal) if decimal != "." else text
    return str(value)


# ----------------------------------------------------------------------- CSV

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe_text(text: str) -> str:
    """Um texto que começa por = + - @ seria uma fórmula no Excel («injeção de CSV»):
    põe-se um apóstrofo à frente para ficar só texto."""
    return "'" + text if text.startswith(_FORMULA_START) else text


def csv_text(cols: list[Field], rows: list[dict], sep: str = ";", decimal: str = ".",
             header: str = "label") -> str:
    if sep not in SEPARATORS:
        sep = ";"
    if decimal not in DECIMALS or decimal == sep:
        decimal = "."
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=sep, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow([c.label if header == "label" else c.key for c in cols])
    for r in rows:
        line = []
        for c in cols:
            v = r.get(c.key)
            if c.kind == NUM and isinstance(v, (int, float)):
                line.append(display(float(v), NUM, decimal))
            elif v is None:
                line.append("")
            else:
                line.append(_safe_text(str(v)))
        w.writerow(line)
    return buf.getvalue()


def safe_filename(name: str, default: str = "perennia-analise") -> str:
    """Um nome de ficheiro sem pastas nem caracteres proibidos, sempre com `.csv`."""
    base = Path(str(name or "").strip()).name            # sem caminhos: só o nome
    base = re.sub(r"[^\w.\- ()À-ÿ]", "_", base, flags=re.UNICODE).strip(" .")
    if base.lower().endswith(".csv"):
        base = base[:-4].strip(" .")
    return (base or default)[:120] + ".csv"


def export_dir(db: Database, data_dir: Path | None) -> Path:
    custom = str(option(db, "adhoc_export_dir") or "").strip()
    if custom:
        return Path(custom).expanduser()
    return (Path(data_dir) if data_dir else Path.cwd()) / "exports"


def unique_path(folder: Path, filename: str) -> Path:
    """Nunca escreve por cima de um ficheiro que já existe: junta -2, -3…"""
    path = folder / filename
    n = 2
    stem, suffix = path.stem, path.suffix
    while path.exists():
        path = folder / f"{stem}-{n}{suffix}"
        n += 1
    return path


def export_csv(cols: list[Field], rows: list[dict], folder: Path, name: str, sep: str = ";",
               decimal: str = ".", bom: bool = True, header: str = "label") -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = unique_path(folder, safe_filename(name))
    text = csv_text(cols, rows, sep, decimal, header)
    path.write_text(text, encoding="utf-8-sig" if bom else "utf-8", newline="")
    return path


# ===================================================================== gráfico


@dataclass
class Pivot:
    """O resultado de um gráfico: um rótulo por posição do eixo X e uma lista de valores por
    série (None onde não há dados)."""
    labels: list[str]
    series: list[tuple[str, list[float | None]]]
    x_title: str = ""
    y_title: str = ""
    points: list[tuple[float, float, str]] = field(default_factory=list)   # só na dispersão
    note: str = ""

    @property
    def empty(self) -> bool:
        if self.points:
            return False
        return not self.labels or not any(v for _n, vs in self.series for v in vs if v)

    def totals(self) -> list[float]:
        return [sum((vs[i] or 0.0) for _n, vs in self.series) for i in range(len(self.labels))]


def _aggregate(values: list[float], agg: str) -> float | None:
    if agg == "count":
        return float(len(values))
    if not values:
        return None
    if agg == "sum":
        return float(sum(values))
    if agg == "avg":
        return sum(values) / len(values)
    if agg == "min":
        return float(min(values))
    if agg == "max":
        return float(max(values))
    return float(statistics.median(values))


def bucket(day: str, grain: str) -> str:
    d = date.fromisoformat(day[:10])
    if grain == "day":
        return d.isoformat()
    if grain == "week":
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if grain == "month":
        return d.strftime("%Y-%m")
    return str(d.year)


def _next_bucket(label: str, grain: str) -> str:
    if grain == "day":
        return (date.fromisoformat(label) + timedelta(days=1)).isoformat()
    if grain == "week":
        y, w = label.split("-W")
        d = date.fromisocalendar(int(y), int(w), 1) + timedelta(days=7)
        iso = d.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if grain == "month":
        y, m = int(label[:4]), int(label[5:7])
        return f"{y + (m == 12)}-{(m % 12) + 1:02d}"
    return str(int(label) + 1)


def _fill(labels: list[str], grain: str, limit: int = 600) -> list[str]:
    """Os períodos todos entre o primeiro e o último (os vazios também contam)."""
    if not labels:
        return labels
    out, cur, last = [], labels[0], labels[-1]
    while cur <= last and len(out) < limit:
        out.append(cur)
        cur = _next_bucket(cur, grain)
    return out


def _value_of(row: dict, y: str):
    return 1.0 if y == ROWS else _num(row.get(y))


def _bins(values: list[float], n: int) -> tuple[list[float], list[str]]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [lo, hi + 1.0], [display(float(lo))]
    step = (hi - lo) / n
    edges = [lo + step * i for i in range(n + 1)]
    return edges, [f"{display(round(edges[i], 1))}–{display(round(edges[i + 1], 1))}"
                   for i in range(n)]


def pivot(db: Database | None, rows: list[dict], spec: Spec) -> Pivot:
    """Agrega as linhas segundo a vista: X, Y com agregação, legenda e ordenação."""
    src = source_of(spec.source)
    xf = src.field(spec.x)
    yf = src.field(spec.y)
    sf = src.field(spec.series) if spec.series else None
    x_title = xf.label if xf else spec.x
    y_title = (tr("Linhas", "Rows") if spec.y == ROWS else (yf.label if yf else spec.y))
    y_title = f"{agg_name(spec.agg)} · {y_title}" if spec.y != ROWS else y_title
    max_cat = option(db, "adhoc_max_categories")
    max_ser = option(db, "adhoc_max_series")

    if spec.chart == "scatter":
        return _scatter(db, rows, spec, xf, yf, sf, x_title, y_title)

    # --- chave do eixo X de cada linha
    keyed: list[tuple[str, dict]] = []
    numeric_x = xf is not None and xf.kind == NUM
    edges: list[float] = []
    bin_labels: list[str] = []
    if numeric_x:
        xs_vals = [v for v in (_num(r.get(spec.x)) for r in rows) if v is not None]
        if not xs_vals:
            return Pivot([], [], x_title, y_title)
        edges, bin_labels = _bins(xs_vals, option(db, "adhoc_bins"))
        for r in rows:
            v = _num(r.get(spec.x))
            if v is None:
                continue
            step = edges[1] - edges[0]
            i = int((v - edges[0]) / step) if step > 0 else 0
            keyed.append((bin_labels[min(len(bin_labels) - 1, max(0, i))], r))
    elif xf is not None and xf.kind == DATE:
        for r in rows:
            if r.get(spec.x):
                keyed.append((bucket(str(r[spec.x]), spec.grain), r))
    else:
        for r in rows:
            v = r.get(spec.x)
            if v is not None and v != "":
                keyed.append((str(v), r))

    # --- legenda: as séries principais; o resto vira «Outros»
    series_names: list[str] = []
    if sf is not None:
        totals: dict[str, float] = {}
        for _k, r in keyed:
            s = r.get(spec.series)
            if s is None or s == "":
                continue
            totals[str(s)] = totals.get(str(s), 0.0) + abs(_value_of(r, spec.y) or 0.0)
        ranked = sorted(totals, key=lambda s: (-totals[s], s))
        series_names = ranked[:max_ser]
        has_other = len(ranked) > max_ser
        if has_other:
            series_names.append(tr("Outros", "Other"))
    else:
        series_names = [y_title]

    def series_of(r: dict) -> str | None:
        if sf is None:
            return series_names[0]
        s = r.get(spec.series)
        if s is None or s == "":
            return None
        s = str(s)
        return s if s in series_names else (series_names[-1] if len(series_names) > max_ser
                                            else None)

    cells: dict[tuple[str, str], list[float]] = {}
    for k, r in keyed:
        s = series_of(r)
        if s is None:
            continue
        v = _value_of(r, spec.y)
        if v is None and spec.agg != "count":
            continue
        cells.setdefault((k, s), []).append(v if v is not None else 1.0)

    labels = sorted({k for k, _s in cells})
    note = ""
    if numeric_x:
        labels = list(bin_labels)                      # todas as classes, pela ordem dos números
    elif xf is not None and xf.kind == DATE:
        if spec.agg in ("sum", "count") and labels:
            labels = _fill(labels, spec.grain)
    else:
        if spec.sort == "value":
            tot = {lab: sum(_aggregate(cells.get((lab, s), []), spec.agg) or 0.0
                            for s in series_names) for lab in labels}
            labels = sorted(labels, key=lambda lab: (-tot[lab], lab))
        if len(labels) > max_cat:
            tot = {lab: sum(_aggregate(cells.get((lab, s), []), spec.agg) or 0.0
                            for s in series_names) for lab in labels}
            keep = sorted(sorted(labels, key=lambda lab: (-tot[lab], lab))[:max_cat - 1])
            if spec.sort == "value":
                keep = [lab for lab in labels if lab in set(keep)]
            other = tr("Outros", "Other")
            merged: dict[tuple[str, str], list[float]] = {}
            for (k, s), vs in cells.items():
                kk = k if k in keep else other
                merged.setdefault((kk, s), []).extend(vs)
            cells, labels = merged, keep + [other]
            note = tr("As categorias além das {n} maiores ficam em «Outros».",
                      "Categories beyond the top {n} are grouped as «Other».", n=max_cat - 1)
    cap = 120
    if len(labels) > cap:
        labels = labels[-cap:]
        note = tr("Só os últimos {n} períodos.", "Only the last {n} periods.", n=cap)
    out_series = [(s, [_aggregate(cells.get((lab, s), []), spec.agg) for lab in labels])
                  for s in series_names]
    return Pivot(labels, out_series, x_title, y_title, note=note)


def _scatter(db, rows, spec: Spec, xf, yf, sf, x_title: str, y_title: str) -> Pivot:
    cap = option(db, "adhoc_max_points")
    pts: list[tuple[float, float, str]] = []
    ykey = spec.y if spec.y != ROWS else None
    if xf is None or xf.kind != NUM or ykey is None:
        return Pivot([], [], x_title, y_title, note=tr(
            "A dispersão precisa de dois números: um no eixo X e outro no valor.",
            "Scatter needs two numbers: one on the X axis and one as the value."))
    for r in rows:
        x, y = _num(r.get(spec.x)), _num(r.get(ykey))
        if x is None or y is None:
            continue
        name = str(r.get(spec.series)) if sf is not None and r.get(spec.series) not in (None, "") \
            else ""
        pts.append((x, y, name))
    note = ""
    if len(pts) > cap:
        step = len(pts) / cap
        pts = [pts[int(i * step)] for i in range(cap)]
        note = tr("{n} pontos (amostra).", "{n} points (sampled).", n=cap)
    y_label = (yf.label if yf else spec.y)
    return Pivot([], [], x_title, y_label, points=pts, note=note)


def pivot_table(pv: "Pivot") -> tuple[list[Field], list[dict]]:
    """Os números do gráfico como tabela (para exportar): uma linha por posição do eixo X e uma
    coluna por série; na dispersão, uma linha por ponto."""
    if pv.points:
        cols = [Field("x", pv.x_title or "x", pv.x_title or "x", NUM),
                Field("y", pv.y_title or "y", pv.y_title or "y", NUM),
                Field("series", tr("Série", "Series"), "Series", CAT)]
        return cols, [{"x": x, "y": y, "series": name} for x, y, name in pv.points]
    cols = [Field("x", pv.x_title or "x", pv.x_title or "x", CAT)]
    keys = []
    for i, (name, _vs) in enumerate(pv.series):
        key = f"s{i}"
        keys.append(key)
        cols.append(Field(key, name, name, NUM))
    rows = []
    for i, lab in enumerate(pv.labels):
        row: dict = {"x": lab}
        for key, (_name, vs) in zip(keys, pv.series):
            row[key] = vs[i] if i < len(vs) else None
        rows.append(row)
    return cols, rows


# ===================================================================== guardar vistas


def load_state(db: Database) -> Spec:
    return Spec.from_dict(db.get(SETTING_STATE, None))


def save_state(db: Database, spec: Spec) -> None:
    db.set(SETTING_STATE, spec.to_dict())


def views(db: Database) -> list[dict]:
    raw = db.get(SETTING_VIEWS, []) or []
    return [v for v in raw if isinstance(v, dict) and v.get("name")]


def save_view(db: Database, name: str, spec: Spec) -> None:
    name = " ".join(str(name).split())[:60]
    if not name:
        raise ValueError(tr("dá um nome à vista", "give the view a name"))
    kept = [v for v in views(db) if v["name"].lower() != name.lower()]
    kept.append({"name": name, "spec": spec.to_dict()})
    db.set(SETTING_VIEWS, sorted(kept, key=lambda v: v["name"].lower()))


def delete_view(db: Database, name: str) -> bool:
    kept = [v for v in views(db) if v["name"] != name]
    changed = len(kept) != len(views(db))
    if changed:
        db.set(SETTING_VIEWS, kept)
    return changed


def view_spec(db: Database, name: str) -> Spec | None:
    for v in views(db):
        if v["name"] == name:
            return Spec.from_dict(v.get("spec"))
    return None


# ===================================================================== linha de comandos


def cli_export(db: Database, data_dir: Path | None, source: str, folder: Path | str | None = None,
               view: str | None = None, name: str | None = None, sep: str | None = None,
               decimal: str | None = None, header: str = "label") -> tuple[Path, int]:
    """O que o botão «Exportar .csv» faz, sem abrir a janela (`main.py --adhoc-exportar`).

    Sem vista, exporta a fonte com os campos por omissão; com `view` (o nome de uma vista
    guardada), usa os campos, o período e os filtros dessa vista. O separador, o decimal e o BOM
    vêm das opções, se não forem dados. Devolve o ficheiro e o número de linhas."""
    if view:
        spec = view_spec(db, view)
        if spec is None:
            raise ValueError(tr("não existe a vista «{n}»", "there is no view «{n}»", n=view))
        if source and source in SOURCES and spec.source != source:
            raise ValueError(tr("a vista «{n}» é da fonte «{s}»", "the view «{n}» is from the "
                                "source «{s}»", n=view, s=spec.source))
    else:
        if source not in SOURCES:
            raise ValueError(tr("fonte desconhecida: {s} (existem: {l})",
                                "unknown source: {s} (available: {l})", s=source,
                                l=", ".join(SOURCE_ORDER)))
        spec = defaults_for(source)
    cols, rows = dataset(db, spec)
    sep = sep if sep is not None else str(option(db, "adhoc_csv_sep"))
    decimal = decimal if decimal is not None else str(option(db, "adhoc_csv_decimal"))
    if sep not in SEPARATORS:
        raise ValueError(tr("separador inválido: use ; , | ou tab", "invalid separator: use ; , | or tab"))
    if decimal not in DECIMALS:
        raise ValueError(tr("decimal inválido: use . ou ,", "invalid decimal: use . or ,"))
    folder = Path(folder).expanduser() if folder else export_dir(db, data_dir)
    stem = name or f"perennia-{spec.source}-{date.today():%Y%m%d}"
    path = export_csv(cols, rows, folder, stem, sep, decimal, bool(option(db, "adhoc_csv_bom")),
                      header)
    return path, len(rows)
