"""Exportar tudo para o Power BI.

Um ficheiro `.pbix` (o relatório do Power BI) não se consegue escrever fora do Power BI
Desktop: o modelo de dados lá dentro é um formato binário fechado. O que a Perennia faz é
entregar o **modelo já pronto** para o Power BI ler, numa pasta fixa (`data/out/powerbi`),
que se reescreve a cada exportação — assim, depois de montares o relatório uma vez e o
guardares como `.pbix`, basta carregar em **Atualizar** no Power BI para ver os dados novos:

* `Perennia_PowerBI.xlsx` — uma folha por tabela, num modelo em estrela: as dimensões
  (`Calendario`, `Desportos`, `Parametros`, `Atleta`) e os factos (sessões, voltas, carga/PMC,
  curva de potência, análises clínicas, diário, tensão arterial, testes, segmentos, séries do
  ginásio, feedback, planeado). As chaves têm o mesmo nome nas tabelas que se ligam (`Data`,
  `Desporto`, `SessaoID`, `ParametroID`), por isso o Power BI liga-as sozinho;
* `csv/` — as mesmas tabelas em CSV (UTF-8, separador «,», ponto decimal) e ainda as
  **amostras** ao segundo de todas as sessões (`Amostras.csv`, grandes demais para o Excel);
* `Perennia.pbids` — abre o Power BI Desktop já ligado ao Excel (duplo clique);
* `Perennia_Medidas_DAX.txt` — medidas prontas a colar (CTL/ATL/TSB, horas, TSS por semana,
  % de resultados fora do intervalo…);
* `Perennia_Amostras.pq` — a consulta Power Query para juntar o `Amostras.csv`;
* `LEIA-ME.txt` — os passos.

Não precisa de janela nem de pyglet: também corre pela linha de comandos
(`python main.py --powerbi`). As credenciais nunca entram.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from .db import Database, now_iso
from .i18n import tr

XLSX = "Perennia_PowerBI.xlsx"
SAMPLES = "Amostras"
SPORT_NAMES = {"cycling": ("Ciclismo", "Cycling"), "rowing": ("Remo", "Rowing"),
               "running": ("Corrida", "Running"), "swimming": ("Natação", "Swimming"),
               "gym": ("Ginásio", "Gym"), "other": ("Outro", "Other")}
MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


# ------------------------------------------------------------------ ajudas


def _local(iso: str | None) -> datetime | None:
    """Uma data/hora gravada (UTC «…Z» ou local) na hora local, sem fuso."""
    if not iso:
        return None
    s = str(iso)
    try:
        if s.endswith("Z"):
            d = datetime.fromisoformat(s[:-1]).replace(tzinfo=__import__("datetime").timezone.utc)
            return d.astimezone().replace(tzinfo=None)
        d = datetime.fromisoformat(s)
        return d.astimezone().replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        try:
            return datetime.fromisoformat(s[:10])
        except ValueError:
            return None


def _day(iso: str | None) -> date | None:
    d = _local(iso)
    return d.date() if d else None


def _r(v: Any, nd: int = 1) -> float | None:
    if v is None or v == "":
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _min(seconds: Any) -> float | None:
    return None if seconds in (None, "") else round(float(seconds) / 60.0, 2)


def _tables(db: Database) -> set[str]:
    return {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _rows(db: Database, sql: str, args: tuple = ()) -> list[dict]:
    try:
        return [dict(r) for r in db.conn.execute(sql, args)]
    except Exception:
        return []


class Table:
    """Uma tabela do modelo: nome, colunas e linhas (listas)."""

    def __init__(self, name: str, columns: list[str], rows: list[list] | None = None,
                 xlsx: bool = True, note: str = ""):
        self.name, self.columns, self.rows, self.xlsx, self.note = name, columns, rows or [], \
            xlsx, note

    def add(self, *values) -> None:
        self.rows.append(list(values))


# ------------------------------------------------------------------ o modelo


def sessions(db: Database) -> Table:
    t = Table("Sessoes", ["SessaoID", "Data", "Inicio", "Desporto", "Tipo", "Nome", "Fonte",
                          "Duracao_min", "Tempo_total_min", "Distancia_km", "Subida_m", "Carga",
                          "IF", "FC_media", "FC_max", "Potencia_media_W", "Potencia_norm_W",
                          "Potencia_max_W", "Cadencia_media", "Ritmo_medio_s", "Series",
                          "Repeticoes", "Volume_kg", "RPE_medio", "Etiquetas"],
              note=tr("uma linha por sessão (de todos os desportos e as importadas)",
                      "one row per session (every sport and the imported ones)"))
    have = _tables(db)
    tags: dict[str, list[str]] = {}
    if "session_tags" in have:
        for r in _rows(db, "SELECT sport, session_id, tag FROM session_tags"):
            tags.setdefault(str(r["session_id"]), []).append(r["tag"])

    def tg(sid) -> str:
        return ", ".join(sorted(set(tags.get(str(sid), []))))
    if "rides" in have:
        for r in _rows(db, "SELECT * FROM rides WHERE status='completed'"):
            t.add(f"ride:{r['id']}", _day(r["started_at"]), _local(r["started_at"]), "cycling",
                  r.get("kind"), r.get("name"), "Perennia", _min(r["moving_s"]),
                  _min(r["elapsed_s"]), _r((r["distance_m"] or 0) / 1000, 2),
                  _r(r["ascent_m"], 0), _r(r["tss"]), _r(r["intensity_factor"], 3),
                  _r(r["avg_hr"], 0), r["max_hr"], _r(r["avg_power_w"], 0), _r(r["np_w"], 0),
                  r["max_power_w"], _r(r["avg_cadence"], 0), None, None, None, None, None,
                  tg(r["id"]))
    if "row_sessions" in have:
        for r in _rows(db, "SELECT * FROM row_sessions WHERE status='completed'"):
            t.add(f"row:{r['id']}", _day(r["started_at"]), _local(r["started_at"]), "rowing",
                  r.get("kind"), r.get("name"), "Perennia", _min(r["moving_s"]),
                  _min(r["elapsed_s"]), _r((r["distance_m"] or 0) / 1000, 2), None,
                  _r(r["load"]), None, _r(r["avg_hr"], 0), r["max_hr"],
                  _r(r["avg_power_w"], 0), _r(r["np_w"], 0), r["max_power_w"],
                  _r(r["avg_spm"], 0), _r(r["avg_pace_s"]), None, None, None, None,
                  tg(r["id"]))
    if "endurance_sessions" in have:
        for r in _rows(db, "SELECT * FROM endurance_sessions WHERE status='completed'"):
            t.add(f"endurance:{r['id']}", _day(r["started_at"]), _local(r["started_at"]),
                  r["sport"], "workout" if r.get("workout_id") else "free", r.get("name"),
                  "Perennia", _min(r["moving_s"]), _min(r["elapsed_s"]),
                  _r((r["distance_m"] or 0) / 1000, 2), None, _r(r["load"]), None,
                  _r(r["avg_hr"], 0), r["max_hr"], None, None, None, None,
                  _r(r["avg_pace_s"]), None, None, None, None, tg(r["id"]))
    if "strength_sessions" in have:
        for r in _rows(db, "SELECT * FROM strength_sessions WHERE status='completed'"):
            t.add(f"strength:{r['id']}", _day(r["started_at"]), _local(r["started_at"]), "gym",
                  r.get("modality") or r.get("mode"), r.get("name"), "Perennia",
                  _min((r["elapsed_s"] or 0) - (r["paused_s"] or 0)), _min(r["elapsed_s"]),
                  _r(r.get("distance_km"), 2), None, _r(r["load"]), None, _r(r["avg_hr"], 0),
                  r["max_hr"], None, None, None, None, None, r["total_sets"], r["total_reps"],
                  _r(r["volume_kg"]), _r(r["avg_rpe"]), tg(r["id"]))
    if "synced_activities" in have:
        for r in _rows(db, "SELECT * FROM synced_activities"):
            t.add(f"synced:{r['id']}", _day(r["started_at"]), _local(r["started_at"]),
                  r.get("sport") or "other", r.get("source_sport"), r.get("name"),
                  (r.get("source") or "").title(), _min(r["moving_s"]), _min(r["elapsed_s"]),
                  _r((r["distance_m"] or 0) / 1000, 2), _r(r["ascent_m"], 0),
                  _r(r["tss"] if r.get("tss") is not None else r.get("training_load")),
                  _r(r.get("if_value"), 3), _r(r["avg_hr"], 0), r["max_hr"],
                  _r(r.get("avg_power_w"), 0), _r(r.get("np_w"), 0), None, None, None, None,
                  None, None, None, "")
    t.rows.sort(key=lambda x: (x[2] or datetime.min))
    return t


def laps(db: Database) -> Table:
    t = Table("Voltas", ["SessaoID", "Volta", "Inicio_s", "Duracao_s", "Distancia_m",
                         "Potencia_media_W", "FC_media", "FC_max", "Cadencia_media", "Motivo"])
    have = _tables(db)
    if "laps" in have:
        for r in _rows(db, "SELECT * FROM laps ORDER BY ride_id, lap_no"):
            t.add(f"ride:{r['ride_id']}", r["lap_no"], _r(r["start_t_s"], 0),
                  _r((r["end_t_s"] or 0) - (r["start_t_s"] or 0), 0),
                  _r((r["end_dist_m"] or 0) - (r["start_dist_m"] or 0), 0),
                  _r(r["avg_power_w"], 0), _r(r["avg_hr"], 0), r["max_hr"],
                  _r(r["avg_cadence"], 0), r["trigger"])
    if "row_laps" in have:
        for r in _rows(db, "SELECT * FROM row_laps ORDER BY session_id, lap_no"):
            t.add(f"row:{r['session_id']}", r["lap_no"], _r(r["start_t"], 0),
                  _r((r["end_t"] or 0) - (r["start_t"] or 0), 0), _r(r["distance_m"], 0),
                  _r(r["avg_power_w"], 0), _r(r["avg_hr"], 0), r["max_hr"],
                  _r(r["avg_spm"], 0), r["trigger"])
    if "endurance_laps" in have:
        for r in _rows(db, "SELECT * FROM endurance_laps ORDER BY session_id, lap_no"):
            t.add(f"endurance:{r['session_id']}", r["lap_no"], _r(r["start_t"], 0),
                  _r((r["end_t"] or 0) - (r["start_t"] or 0), 0), _r(r["distance_m"], 0),
                  None, _r(r["avg_hr"], 0), r["max_hr"], None, r["trigger"])
    return t


def samples(db: Database) -> Table:
    """As amostras ao segundo (só em CSV: passam facilmente o limite de linhas do Excel)."""
    t = Table(SAMPLES, ["SessaoID", "t_s", "Distancia_m", "Velocidade_kmh", "Potencia_W",
                        "FC", "Cadencia", "Altitude_m", "Inclinacao_pct"], xlsx=False)
    have = _tables(db)
    if "ride_samples" in have:
        for r in db.conn.execute("SELECT ride_id, t_s, dist_m, speed_mps, power_w, hr_bpm,"
                                 " cadence_rpm, ele_m, grade_pct FROM ride_samples"
                                 " ORDER BY ride_id, t_s"):
            t.add(f"ride:{r[0]}", r[1], _r(r[2]), _r((r[3] or 0) * 3.6, 2), r[4], r[5], r[6],
                  _r(r[7]), _r(r[8]))
    if "row_samples" in have:
        for r in db.conn.execute("SELECT session_id, t_s, dist_m, power_w, hr_bpm, spm"
                                 " FROM row_samples ORDER BY session_id, t_s"):
            t.add(f"row:{r[0]}", r[1], _r(r[2]), None, r[3], r[4], r[5], None, None)
    if "endurance_samples" in have:
        cols = {c[1] for c in db.conn.execute("PRAGMA table_info(endurance_samples)")}
        inc = "incline_pct" if "incline_pct" in cols else "NULL"
        for r in db.conn.execute(f"SELECT session_id, t_s, dist_m, speed_mps, hr_bpm, {inc}"
                                 " FROM endurance_samples ORDER BY session_id, t_s"):
            t.add(f"endurance:{r[0]}", r[1], _r(r[2]), _r((r[3] or 0) * 3.6, 2), None, r[4],
                  None, None, _r(r[5]))
    if "strength_hr" in have:
        for r in db.conn.execute("SELECT session_id, t_s, hr_bpm FROM strength_hr"
                                 " ORDER BY session_id, t_s"):
            t.add(f"strength:{r[0]}", r[1], None, None, None, r[2], None, None, None)
    return t


def pmc(db: Database) -> Table:
    from . import stats
    t = Table("PMC", ["Data", "Carga", "CTL", "ATL", "TSB", "Forma"],
              note=tr("a forma ao longo do tempo (fitness, fadiga e frescura)",
                      "form over time (fitness, fatigue and freshness)"))
    try:
        daily = stats.daily_load(db)
    except Exception:
        daily = {}
    if not daily:
        return t
    for d in stats.pmc(daily, date.today(), db):
        t.add(d["date"], _r(d["load"]), _r(d["ctl"]), _r(d["atl"]), _r(d["tsb"]),
              stats.form_state(d["tsb"]))
    return t


def power_curve(db: Database) -> Table:
    t = Table("Curva_potencia", ["SessaoID", "Duracao_s", "Potencia_W"])
    if "ride_power_curve" in _tables(db):
        for r in _rows(db, "SELECT * FROM ride_power_curve ORDER BY ride_id, duration_s"):
            t.add(f"ride:{r['ride_id']}", r["duration_s"], _r(r["max_avg_w"], 0))
    return t


def labs(db: Database) -> tuple[Table, Table]:
    from . import health, lab_glossary, labs as labs_mod
    res = Table("Analises", ["ResultadoID", "Data", "Laboratorio", "Area", "Painel",
                             "ParametroID", "Parametro", "Componente", "Categoria", "Valor",
                             "Valor_texto", "Unidade", "Ref_min", "Ref_max", "Estado",
                             "Comentario_medico"],
                note=tr("um resultado por linha, com o componente do glossário",
                        "one result per row, with the glossary component"))
    par = Table("Parametros", ["ParametroID", "Parametro", "Unidade", "Ref_min", "Ref_max",
                               "Componente", "Categoria", "Resumo"])
    try:
        labs_mod.ensure(db)
    except Exception:
        return res, par
    entries = lab_glossary.all_entries(db)
    names: dict[str, str] = {}
    for r in _rows(db, "SELECT x.*, p.done_on, p.lab FROM lab_results x JOIN lab_reports p"
                       " ON p.id = x.report_id ORDER BY p.done_on, x.sort, x.id"):
        name = labs_mod.short_name(r["marker"])
        g = lab_glossary.match(db, r["marker"], entries)
        pid = r.get("parameter_id") or f"m:{lab_glossary.fold(name)}"
        names.setdefault(str(pid), name)
        state = {"high": "Alto", "low": "Baixo"}.get(health.flag(r), "Normal" if (
            r.get("ref_low") is not None or r.get("ref_high") is not None) else "")
        res.add(r["id"], _day(r["done_on"]), r.get("lab"), r.get("area"), r.get("panel"),
                str(pid), name, g["name"] if g else None,
                lab_glossary.category_name(g["category"]) if g else None, r.get("value"),
                labs_mod.value_text(r), r.get("unit"), r.get("ref_low"), r.get("ref_high"),
                state, r.get("doctor_comment"))
    seen = set()
    for p in _rows(db, "SELECT * FROM lab_parameters ORDER BY sort, id"):
        g = lab_glossary.match(db, p["name"], entries)
        seen.add(str(p["id"]))
        par.add(str(p["id"]), p.get("short_name") or p["name"], p.get("unit"), p.get("ref_low"),
                p.get("ref_high"), g["name"] if g else None,
                lab_glossary.category_name(g["category"]) if g else None,
                g["summary"] if g else None)
    for pid, name in names.items():            # os resultados escritos à mão, sem catálogo
        if pid not in seen:
            g = lab_glossary.match(db, name, entries)
            par.add(pid, name, None, None, None, g["name"] if g else None,
                    lab_glossary.category_name(g["category"]) if g else None,
                    g["summary"] if g else None)
    return res, par


def diary(db: Database) -> Table:
    t = Table("Diario", ["Data", "Metrica", "Grupo", "Valor", "Texto", "Unidade", "Fonte"])
    if "daily_values" not in _tables(db):
        return t
    for r in _rows(db, "SELECT v.day, v.num, v.txt, v.source, m.name, m.grp, m.unit"
                       " FROM daily_values v JOIN metric_defs m ON m.id = v.metric_id"
                       " ORDER BY v.day, m.sort"):
        t.add(_day(r["day"]), r["name"], r["grp"], r["num"], r["txt"], r["unit"], r["source"])
    return t


def blood_pressure(db: Database) -> Table:
    t = Table("Tensao_arterial", ["Data", "Periodo", "Hora", "Sistolica", "Diastolica",
                                  "Pulso", "Notas"])
    if "bp_readings" in _tables(db):
        for r in _rows(db, "SELECT * FROM bp_readings ORDER BY day, at"):
            t.add(_day(r["day"]), r["period"], r["at"], r["sys"], r["dia"], r["pulse"],
                  r["notes"])
    return t


def tests(db: Database) -> Table:
    t = Table("Testes", ["Data", "Teste", "Desporto", "Valor", "Unidade", "Notas"])
    if "test_results" in _tables(db):
        for r in _rows(db, "SELECT r.done_on, r.value, r.notes, t.name, t.sport, t.unit"
                           " FROM test_results r JOIN fitness_tests t ON t.id = r.test_id"
                           " ORDER BY r.done_on"):
            t.add(_day(r["done_on"]), r["name"], r["sport"], r["value"], r["unit"], r["notes"])
    return t


def segment_efforts(db: Database) -> Table:
    t = Table("Segmentos", ["Data", "Segmento", "Fonte", "Desporto", "Tempo_s", "SessaoID"])
    have = _tables(db)
    names: dict[tuple, str] = {}
    for tb, src, key in (("strava_segments", "strava", "segment_id"),
                         ("strava_library", "strava", "segment_id"),
                         ("perennia_segments", "perennia", "id")):
        if tb in have:
            for r in _rows(db, f"SELECT {key} AS k, name FROM {tb}"):
                names[(src, r["k"])] = r["name"]
    if "strava_efforts" in have:
        for r in _rows(db, "SELECT * FROM strava_efforts"):
            t.add(_day(r["created_at"]), names.get(("strava", r["segment_id"]), r["segment_id"]),
                  "strava", "cycling", r["elapsed_s"], f"ride:{r['ride_id']}")
    if "segment_efforts" in have:
        kinds = {"ride": "ride", "row": "row", "endurance": "endurance", "strength": "strength"}
        for r in _rows(db, "SELECT * FROM segment_efforts"):
            k = kinds.get(r["session_kind"], r["session_kind"])
            t.add(_day(r["created_at"]),
                  names.get((r["source"], r["segment_id"]), r["segment_id"]), r["source"],
                  r["sport"], r["elapsed_s"], f"{k}:{r['session_id']}" if r["session_id"]
                  else None)
    t.rows.sort(key=lambda x: (x[0] or date.min))
    return t


def gym_sets(db: Database) -> Table:
    t = Table("Series_ginasio", ["SessaoID", "Data", "Exercicio", "Serie", "Repeticoes",
                                 "Carga_kg", "RPE", "Volume_kg", "FC_media"])
    have = _tables(db)
    if "strength_sets" not in have:
        return t
    for r in _rows(db, "SELECT s.*, e.name AS ex, x.started_at FROM strength_sets s"
                       " LEFT JOIN exercises e ON e.id = s.exercise_id"
                       " JOIN strength_sessions x ON x.id = s.session_id"
                       " WHERE x.status = 'completed' ORDER BY x.started_at, s.id"):
        reps, load = r.get("reps"), r.get("load_kg")
        t.add(f"strength:{r['session_id']}", _day(r["started_at"]), r.get("ex"), r.get("set_no"),
              reps, load, r.get("rpe"), _r((reps or 0) * (load or 0)), _r(r.get("avg_hr"), 0))
    return t


def feedback(db: Database) -> Table:
    t = Table("Feedback", ["SessaoID", "Data", "Desporto", "RPE", "Dor", "Sensacao",
                           "Objetivo_cumprido", "Comentario"])
    if "session_feedback" in _tables(db):
        for r in _rows(db, "SELECT * FROM session_feedback ORDER BY day"):
            t.add(f"{r['kind']}:{r['session_id']}", _day(r["day"]), r["sport"], r["rpe"],
                  r["pain"], r["feel"], r["goal_met"], r["comment"])
    return t


def planned(db: Database) -> Table:
    t = Table("Planeado", ["Data", "Desporto", "Titulo", "Notas"])
    if "training_plan" in _tables(db):
        for r in _rows(db, "SELECT * FROM training_plan ORDER BY day"):
            t.add(_day(r["day"]), r["sport"], r["title"], r["notes"])
    return t


def athlete(db: Database) -> Table:
    a = db.athlete()
    t = Table("Atleta", ["Nome", "Ano_nascimento", "Peso_kg", "FTP_W", "LTHR", "FC_max",
                         "Exportado_em"])
    t.add(a.name, a.birth_year, a.weight_kg, a.ftp_w, a.lthr, getattr(a, "max_hr", None),
          _local(now_iso()))
    return t


def sports_dim() -> Table:
    t = Table("Desportos", ["Desporto", "Nome", "Name"])
    for k, (pt, en) in SPORT_NAMES.items():
        t.add(k, pt, en)
    return t


def calendar(facts: Iterable[Table]) -> Table:
    """Uma linha por dia, do primeiro ao último dia com dados (e até hoje)."""
    days: list[date] = []
    for tb in facts:
        if "Data" in tb.columns:
            i = tb.columns.index("Data")
            days += [r[i] for r in tb.rows if isinstance(r[i], date)]
    t = Table("Calendario", ["Data", "Ano", "Mes", "Mes_nome", "Ano_mes", "Semana_ISO",
                             "Ano_semana", "Dia_semana", "Dia_semana_n", "Trimestre"])
    if not days:
        return t
    d, end = min(days), max(max(days), date.today())
    while d <= end:
        iso = d.isocalendar()
        t.add(d, d.year, d.month, MONTHS[d.month - 1], f"{d.year}-{d.month:02d}", iso[1],
              f"{iso[0]}-S{iso[1]:02d}", WEEKDAYS[d.weekday()], d.weekday() + 1,
              f"T{(d.month - 1) // 3 + 1}")
        d += timedelta(days=1)
    return t


def model(db: Database, with_samples: bool = True) -> list[Table]:
    """Todas as tabelas, pela ordem em que ficam no Excel (o calendário primeiro)."""
    lab_res, lab_par = labs(db)
    facts = [sessions(db), laps(db), pmc(db), power_curve(db), lab_res, diary(db),
             blood_pressure(db), tests(db), segment_efforts(db), gym_sets(db), feedback(db),
             planned(db)]
    out = [calendar(facts), sports_dim(), lab_par, athlete(db)] + facts
    if with_samples:
        out.append(samples(db))
    return out


# ------------------------------------------------------------------ ficheiros


def _cell(v):
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    return "" if v is None else v


def write_csv(tb: Table, path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(tb.columns)
        for r in tb.rows:
            w.writerow([_cell(v) for v in r])


def write_xlsx(tables: list[Table], path: Path) -> None:
    """Uma folha por tabela (cabeçalho a negrito, linha fixa, datas como datas)."""
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for tb in tables:
        if not tb.xlsx:
            continue
        ws = wb.create_sheet(tb.name[:31])
        ws.append(tb.columns)
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for r in tb.rows:
            ws.append([v for v in r])
        for i, col in enumerate(tb.columns, start=1):
            letter = get_column_letter(i)
            ws.column_dimensions[letter].width = max(10, min(40, len(col) + 4))
            sample = next((r[i - 1] for r in tb.rows if r[i - 1] is not None), None)
            if isinstance(sample, datetime):
                for cell in ws[letter][1:]:
                    cell.number_format = "yyyy-mm-dd hh:mm"
            elif isinstance(sample, date):
                for cell in ws[letter][1:]:
                    cell.number_format = "yyyy-mm-dd"
    wb.save(str(path))


def pbids(xlsx_path: Path) -> dict:
    """O ficheiro de ligação do Power BI (.pbids): abre o Power BI Desktop já no Excel."""
    return {"version": "0.1",
            "connections": [{"details": {"protocol": "file",
                                         "address": {"path": str(Path(xlsx_path).resolve())}},
                             "options": {}, "mode": None}]}


DAX = """// Medidas para colar no Power BI (Modelagem → Nova medida). As tabelas e colunas são as do
// Perennia_PowerBI.xlsx. Ligações (o Power BI cria-as sozinho; confirma em Modelo):
//   Calendario[Data] 1—* Sessoes[Data], PMC[Data], Analises[Data], Diario[Data],
//                        Tensao_arterial[Data], Testes[Data], Segmentos[Data], Feedback[Data]
//   Desportos[Desporto] 1—* Sessoes[Desporto]
//   Sessoes[SessaoID] 1—* Voltas[SessaoID], Curva_potencia[SessaoID], Series_ginasio[SessaoID],
//                         Amostras[SessaoID]
//   Parametros[ParametroID] 1—* Analises[ParametroID]

Sessões = COUNTROWS ( Sessoes )
Horas de treino = DIVIDE ( SUM ( Sessoes[Duracao_min] ), 60 )
Distância (km) = SUM ( Sessoes[Distancia_km] )
Carga (TSS) = SUM ( Sessoes[Carga] )
TSS por semana = DIVIDE ( [Carga (TSS)], DISTINCTCOUNT ( Calendario[Ano_semana] ) )
Subida (m) = SUM ( Sessoes[Subida_m] )
FC média ponderada = DIVIDE ( SUMX ( Sessoes, Sessoes[FC_media] * Sessoes[Duracao_min] ),
                              SUMX ( FILTER ( Sessoes, NOT ISBLANK ( Sessoes[FC_media] ) ),
                                     Sessoes[Duracao_min] ) )
Potência média ponderada (W) = DIVIDE (
    SUMX ( Sessoes, Sessoes[Potencia_media_W] * Sessoes[Duracao_min] ),
    SUMX ( FILTER ( Sessoes, NOT ISBLANK ( Sessoes[Potencia_media_W] ) ), Sessoes[Duracao_min] ) )
CTL (forma) = CALCULATE ( LASTNONBLANKVALUE ( PMC[Data], MAX ( PMC[CTL] ) ) )
ATL (fadiga) = CALCULATE ( LASTNONBLANKVALUE ( PMC[Data], MAX ( PMC[ATL] ) ) )
TSB (frescura) = CALCULATE ( LASTNONBLANKVALUE ( PMC[Data], MAX ( PMC[TSB] ) ) )
Melhor potência (W) = MAX ( Curva_potencia[Potencia_W] )
Volume ginásio (kg) = SUM ( Series_ginasio[Volume_kg] )
Resultados = COUNTROWS ( Analises )
Fora do intervalo = CALCULATE ( COUNTROWS ( Analises ), Analises[Estado] IN { "Alto", "Baixo" } )
% fora do intervalo = DIVIDE ( [Fora do intervalo], [Resultados] )
Último valor = CALCULATE ( LASTNONBLANKVALUE ( Analises[Data], MAX ( Analises[Valor] ) ) )
Tensão sistólica média = AVERAGE ( Tensao_arterial[Sistolica] )
Tensão diastólica média = AVERAGE ( Tensao_arterial[Diastolica] )
RPE médio = AVERAGE ( Feedback[RPE] )
"""

PQ = """// Power Query (Obter dados → Consulta em branco → Editor avançado): junta o Amostras.csv,
// que é grande demais para o Excel. Muda o caminho se mudaste a pasta.
let
    Origem = Csv.Document(File.Contents("{path}"), [Delimiter = ",", Encoding = 65001,
                                                     QuoteStyle = QuoteStyle.Csv]),
    Cabecalhos = Table.PromoteHeaders(Origem, [PromoteAllScalars = true]),
    Tipos = Table.TransformColumnTypes(Cabecalhos, {{"SessaoID", type text},
        {"t_s", Int64.Type}, {"Distancia_m", type number}, {"Velocidade_kmh", type number},
        {"Potencia_W", Int64.Type}, {"FC", Int64.Type}, {"Cadencia", Int64.Type},
        {"Altitude_m", type number}, {"Inclinacao_pct", type number}}, "en-US")
in
    Tipos
"""


def readme(tables: list[Table], folder: Path) -> str:
    lines = [
        "PERENNIA → POWER BI",
        "===================",
        "",
        "Esta pasta é reescrita a cada exportação (Perennia → Backups e Sincronização →",
        "Exportar → Exportar para o Power BI, ou «python main.py --powerbi»).",
        "",
        "Primeira vez:",
        "  1. Duplo clique em Perennia.pbids — abre o Power BI Desktop já ligado ao Excel.",
        "     (Sem o .pbids: Obter dados → Livro do Excel → Perennia_PowerBI.xlsx.)",
        "  2. No Navegador marca todas as folhas e carrega em Carregar.",
        "  3. Em Modelo confirma as ligações (o Power BI cria-as pelas colunas com o mesmo",
        "     nome: Data, Desporto, SessaoID, ParametroID). Marca Calendario como tabela de",
        "     datas (Calendario[Data]).",
        "  4. (Opcional) As amostras ao segundo: Obter dados → Consulta em branco → cola o",
        "     Perennia_Amostras.pq.",
        "  5. Cola as medidas do Perennia_Medidas_DAX.txt e monta o teu relatório.",
        "  6. Guarda como .pbix onde quiseres (fora desta pasta).",
        "",
        "Depois: exporta de novo na Perennia e, no Power BI, carrega em Atualizar.",
        "",
        "Porque não um .pbix pronto? O .pbix guarda o modelo num formato binário que só o",
        "Power BI Desktop escreve; a Perennia entrega o modelo pronto a ligar.",
        "",
        "Tabelas:",
    ]
    for tb in tables:
        where = "Excel + CSV" if tb.xlsx else "só CSV"
        lines.append(f"  {tb.name:<18} {len(tb.rows):>8} linhas  ({where})"
                     + (f" — {tb.note}" if tb.note else ""))
    lines += ["", f"Pasta: {folder}", f"Exportado em: {datetime.now():%Y-%m-%d %H:%M}"]
    return "\n".join(lines) + "\n"


def output_dir(db: Database, data_dir: Path | str | None) -> Path:
    """`data/out/powerbi` (sempre a mesma: o Power BI lê sempre do mesmo sítio)."""
    from . import folders
    return folders.out_dir("powerbi", data_dir)


def export(db: Database, data_dir: Path | str | None, out: Path | str | None = None,
           with_samples: bool = True, progress: Callable[[str], None] | None = None) -> dict:
    """Escreve a pasta do Power BI. Devolve {path, xlsx, tables: {nome: linhas}}."""
    folder = Path(out) if out else output_dir(db, data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "csv").mkdir(exist_ok=True)
    say = progress or (lambda _t: None)
    say(tr("A preparar as tabelas", "Preparing the tables"))
    tables = model(db, with_samples)
    for tb in tables:
        say(tb.name)
        write_csv(tb, folder / "csv" / f"{tb.name}.csv")
    xlsx = folder / XLSX
    have_xlsx = True
    try:
        say(XLSX)
        write_xlsx(tables, xlsx)
    except ImportError:
        have_xlsx = False            # sem openpyxl ficam os CSV (o Power BI lê a pasta csv/)
    (folder / "Perennia.pbids").write_text(json.dumps(pbids(xlsx), indent=2), encoding="utf-8")
    (folder / "Perennia_Medidas_DAX.txt").write_text(DAX, encoding="utf-8")
    samples_csv = (folder / "csv" / f"{SAMPLES}.csv").resolve()
    (folder / "Perennia_Amostras.pq").write_text(
        PQ.replace("{path}", str(samples_csv).replace("\\", "\\\\")), encoding="utf-8")
    (folder / "LEIA-ME.txt").write_text(readme(tables, folder), encoding="utf-8")
    return {"path": str(folder), "xlsx": str(xlsx) if have_xlsx else None,
            "tables": {tb.name: len(tb.rows) for tb in tables}}


def cli_export(db: Database, data_dir: Path, out: str | None) -> int:
    m = export(db, data_dir, out, progress=lambda n: print(f"  {n}…"))
    print(f"Power BI: {m['path']}")
    if m["xlsx"] is None:
        print("  (sem a biblioteca openpyxl: só os CSV — pip install openpyxl)")
    for name, n in m["tables"].items():
        print(f"  {name}: {n} linhas")
    print("Abre o Perennia.pbids (ou o Perennia_PowerBI.xlsx) no Power BI Desktop.")
    return 0
