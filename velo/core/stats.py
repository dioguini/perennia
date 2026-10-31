"""Estatísticas globais (req. 29).

Agregações sobre o histórico todo: horas, quilómetros, subida, curva de
potência, distribuição por zonas, volume por semana e carga de treino.
Tudo em SQL sobre a base local — nenhum serviço externo envolvido.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import Database

POWER_CURVE_DURATIONS = (1, 5, 10, 15, 20, 30, 60, 120, 300, 600, 1200, 1800, 3600)


def totals(db: Database) -> dict:
    row = db.conn.execute("SELECT * FROM v_totals").fetchone()
    out = dict(row) if row else {}
    out["rides"] = out.get("rides") or 0
    for key in ("hours", "km", "ascent_m", "tss"):
        out[key] = out.get(key) or 0.0
    best = db.conn.execute(
        "SELECT MAX(max_avg_w) AS w FROM ride_power_curve WHERE duration_s = 1200"
    ).fetchone()
    out["best_20min_w"] = best["w"] if best and best["w"] else None
    return out


def power_curve(db: Database, days: int | None = None) -> list[tuple[int, float]]:
    """Melhor potência média por duração, no período pedido."""
    sql = ("SELECT pc.duration_s AS d, MAX(pc.max_avg_w) AS w"
           " FROM ride_power_curve pc JOIN rides r ON r.id = pc.ride_id"
           " WHERE r.status = 'completed'")
    params: list = []
    if days:
        sql += " AND r.started_at >= ?"
        params.append(_days_ago(days))
    sql += " GROUP BY pc.duration_s ORDER BY pc.duration_s"
    return [(r["d"], r["w"]) for r in db.conn.execute(sql, params).fetchall()]


def weekly_volume(db: Database, weeks: int = 16) -> list[tuple[str, float, float]]:
    """(semana ISO, quilómetros, horas) das últimas `weeks` semanas."""
    rows = db.conn.execute(
        "SELECT started_at, distance_m, moving_s FROM rides"
        " WHERE status = 'completed' AND started_at >= ?"
        " ORDER BY started_at", (_days_ago(weeks * 7),)
    ).fetchall()
    buckets: dict[str, list[float]] = {}
    for r in rows:
        when = _parse(r["started_at"])
        if when is None:
            continue
        key = f"{when.isocalendar().year}-S{when.isocalendar().week:02d}"
        acc = buckets.setdefault(key, [0.0, 0.0])
        acc[0] += (r["distance_m"] or 0.0) / 1000.0
        acc[1] += (r["moving_s"] or 0) / 3600.0
    return [(k, v[0], v[1]) for k, v in sorted(buckets.items())]


def zone_distribution(db: Database, days: int | None = None) -> list[float]:
    """Segundos passados em cada zona de potência, usando a FTP de cada sessão."""
    bounds = db.get("power_zones_pct", [55, 75, 90, 105, 120, 150])
    sql = ("SELECT s.power_w AS p, r.ftp_at_ride_w AS ftp FROM ride_samples s"
           " JOIN rides r ON r.id = s.ride_id"
           " WHERE r.status = 'completed' AND s.power_w IS NOT NULL")
    params: list = []
    if days:
        sql += " AND r.started_at >= ?"
        params.append(_days_ago(days))
    out = [0.0] * (len(bounds) + 1)
    for row in db.conn.execute(sql, params):
        ftp = row["ftp"] or 200
        pct = row["p"] / ftp * 100.0
        zone = 0
        for b in bounds:
            if pct > b:
                zone += 1
            else:
                break
        out[min(zone, len(out) - 1)] += 1.0
    return out


def training_load(db: Database, days: int = 90) -> list[tuple[str, float, float, float]]:
    """(dia, CTL, ATL, TSB) a partir da TSS diária.

    CTL é a média exponencial a 42 dias, ATL a 7 dias, e TSB a diferença —
    as mesmas definições que as plataformas usam, para os números serem
    comparáveis com o que o atleta já conhece.
    """
    rows = db.conn.execute(
        "SELECT started_at, tss FROM rides WHERE status = 'completed'"
        " AND started_at >= ? ORDER BY started_at", (_days_ago(days + 42),)
    ).fetchall()
    daily: dict[str, float] = {}
    for r in rows:
        when = _parse(r["started_at"])
        if when is None:
            continue
        key = when.date().isoformat()
        daily[key] = daily.get(key, 0.0) + (r["tss"] or 0.0)
    if not daily:
        return []
    start = datetime.fromisoformat(min(daily)).date()
    end = datetime.now(timezone.utc).date()
    ctl = atl = 0.0
    out = []
    day = start
    while day <= end:
        tss = daily.get(day.isoformat(), 0.0)
        ctl += (tss - ctl) / 42.0
        atl += (tss - atl) / 7.0
        out.append((day.isoformat(), ctl, atl, ctl - atl))
        day += timedelta(days=1)
    return out[-days:]


def personal_records(db: Database) -> dict:
    out: dict = {}
    row = db.conn.execute(
        "SELECT r.id, r.started_at, r.distance_m, ro.name FROM rides r"
        " LEFT JOIN routes ro ON ro.id = r.route_id"
        " WHERE r.status='completed' ORDER BY r.distance_m DESC LIMIT 1").fetchone()
    if row:
        out["longest_ride"] = dict(row)
    row = db.conn.execute(
        "SELECT r.id, r.started_at, r.ascent_m, ro.name FROM rides r"
        " LEFT JOIN routes ro ON ro.id = r.route_id"
        " WHERE r.status='completed' ORDER BY r.ascent_m DESC LIMIT 1").fetchone()
    if row:
        out["most_ascent"] = dict(row)
    row = db.conn.execute(
        "SELECT MAX(max_power_w) AS w FROM rides WHERE status='completed'").fetchone()
    out["max_power_w"] = row["w"] if row else None
    return out


def cadence_histogram(db: Database, bucket: int = 5) -> list[tuple[int, float]]:
    rows = db.conn.execute(
        "SELECT cadence_rpm AS c, COUNT(*) AS n FROM ride_samples s"
        " JOIN rides r ON r.id = s.ride_id"
        " WHERE r.status='completed' AND c IS NOT NULL AND c > 0"
        " GROUP BY c").fetchall()
    buckets: dict[int, float] = {}
    for r in rows:
        key = int(r["c"] // bucket) * bucket
        buckets[key] = buckets.get(key, 0.0) + r["n"]
    return sorted(buckets.items())


def balance_history(db: Database, limit: int = 40) -> list[tuple[str, float]]:
    """(data, % da perna esquerda) das últimas sessões com balanço medido."""
    rows = db.conn.execute(
        "SELECT started_at, avg_balance_left FROM rides WHERE status='completed'"
        " AND avg_balance_left IS NOT NULL ORDER BY started_at DESC LIMIT ?",
        (limit,)).fetchall()
    return [(r["started_at"][:10], r["avg_balance_left"]) for r in reversed(rows)]


def avg_balance(db: Database) -> float | None:
    """Média ponderada pelo tempo em movimento, em todas as sessões."""
    row = db.conn.execute(
        "SELECT SUM(avg_balance_left * moving_s) / SUM(moving_s) AS b FROM rides"
        " WHERE status='completed' AND avg_balance_left IS NOT NULL AND moving_s > 0"
    ).fetchone()
    return row["b"] if row and row["b"] is not None else None


def recent_rides(db: Database, limit: int = 20) -> list[dict]:
    rows = db.conn.execute(
        "SELECT r.*, ro.name AS route_name FROM rides r"
        " LEFT JOIN routes ro ON ro.id = r.route_id"
        " WHERE r.status='completed' ORDER BY r.started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ------------------------------------------------------------ sequência


def _local_date(value: str | None):
    when = _parse(value)
    return when.astimezone().date() if when else None


def ride_days(db: Database) -> dict:
    """{data local: minutos de treino} de todas as sessões concluídas, de
    todos os desportos (ciclismo e força): a sequência é do atleta."""
    out: dict = {}
    for r in db.conn.execute(
            "SELECT started_at, moving_s, elapsed_s FROM rides WHERE status='completed'"):
        day = _local_date(r["started_at"])
        if day is None:
            continue
        out[day] = out.get(day, 0.0) + ((r["moving_s"] or r["elapsed_s"] or 0) / 60.0)
    try:
        rows = db.conn.execute("SELECT started_at, elapsed_s FROM strength_sessions"
                               " WHERE status='completed'").fetchall()
    except Exception:
        rows = []
    for r in rows:
        day = _local_date(r["started_at"])
        if day is not None:
            out[day] = out.get(day, 0.0) + (r["elapsed_s"] or 0) / 60.0
    for sp in ("rowing", "running", "swimming"):
        for day, r in sport_rows(db, sp):
            out[day] = out.get(day, 0.0) + (r["moving_s"] or r["elapsed_s"] or 0) / 60.0
    return out


def _endurance_rows(db: Database, sport: str) -> list[tuple]:
    """Sessões de corrida ou natação concluídas: [(dia, linha)]."""
    try:
        rows = db.conn.execute(
            "SELECT started_at, elapsed_s, moving_s, load, distance_m, hr_zone_s, avg_pace_s"
            " FROM endurance_sessions WHERE status='completed' AND sport = ?",
            (sport,)).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        day = _local_date(r["started_at"])
        if day is not None:
            out.append((day, r))
    return out


def sport_rows(db: Database, sport: str) -> list[tuple]:
    """[(dia, linha)] das sessões de remo, corrida ou natação."""
    return _row_rows(db) if sport == "rowing" else _endurance_rows(db, sport)


def _row_rows(db: Database) -> list[tuple]:
    """Sessões de remo concluídas: [(dia, linha)]."""
    try:
        rows = db.conn.execute(
            "SELECT started_at, elapsed_s, moving_s, load, distance_m, hr_zone_s"
            " FROM row_sessions WHERE status='completed'").fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        day = _local_date(r["started_at"])
        if day is not None:
            out.append((day, r))
    return out


def streaks(db: Database, today=None) -> dict:
    """Dias e semanas seguidos a treinar.

    A sequência atual conta até hoje, ou até ontem se hoje ainda não houve
    sessão: não se perde a meio do dia. O mesmo para as semanas (semana
    ISO, de segunda a domingo). Devolve também os melhores de sempre.
    """
    from datetime import date as _date
    today = today or _date.today()
    days = set(ride_days(db))
    out = {"days": 0, "weeks": 0, "best_days": 0, "best_weeks": 0,
           "rides_this_week": 0, "total_days": len(days)}
    if not days:
        return out

    def run_back(start, step, has) -> int:
        n, cur = 0, start
        while has(cur):
            n += 1
            cur = cur - step
        return n

    one_day = timedelta(days=1)
    start = today if today in days else today - one_day
    out["days"] = run_back(start, one_day, lambda d: d in days)

    weeks = {d - timedelta(days=d.weekday()) for d in days}      # segunda de cada semana
    this_week = today - timedelta(days=today.weekday())
    one_week = timedelta(days=7)
    wstart = this_week if this_week in weeks else this_week - one_week
    out["weeks"] = run_back(wstart, one_week, lambda w: w in weeks)

    def best(sorted_items, step) -> int:
        best_n = n = 0
        prev = None
        for item in sorted_items:
            n = n + 1 if prev is not None and item - prev == step else 1
            best_n = max(best_n, n)
            prev = item
        return best_n

    out["best_days"] = best(sorted(days), one_day)
    out["best_weeks"] = best(sorted(weeks), one_week)
    out["rides_this_week"] = sum(1 for d in days if d >= this_week)
    return out


def heatmap(db: Database, weeks: int = 16, today=None) -> list[list[float]]:
    """Minutos por dia das últimas `weeks` semanas: [semana][dia 0=segunda]."""
    from datetime import date as _date
    today = today or _date.today()
    days = ride_days(db)
    first = today - timedelta(days=today.weekday()) - timedelta(days=7 * (weeks - 1))
    grid = []
    for w in range(weeks):
        col = []
        for d in range(7):
            day = first + timedelta(days=7 * w + d)
            col.append(days.get(day, 0.0) if day <= today else -1.0)
        grid.append(col)
    return grid


# ------------------------------------------------------ explorador por período

GROUPINGS = ("day", "week", "month", "quarter", "semester", "year")
PERIOD_METRICS = ("distance", "time", "ascent", "load", "rides", "avg_power", "avg_hr",
                  "work")
_MONTHS_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out",
              "nov", "dez")


def bucket_of(day, grouping: str):
    """Chave do grupo a que um dia pertence (ordenável)."""
    if grouping == "day":
        return day
    if grouping == "week":
        return day - timedelta(days=day.weekday())
    if grouping == "month":
        return (day.year, day.month)
    if grouping == "quarter":
        return (day.year, (day.month - 1) // 3 + 1)
    if grouping == "semester":
        return (day.year, 1 if day.month <= 6 else 2)
    return day.year


def _previous(key, grouping: str):
    if grouping == "day":
        return key - timedelta(days=1)
    if grouping == "week":
        return key - timedelta(days=7)
    if grouping == "month":
        y, m = key
        return (y - 1, 12) if m == 1 else (y, m - 1)
    if grouping == "quarter":
        y, q = key
        return (y - 1, 4) if q == 1 else (y, q - 1)
    if grouping == "semester":
        y, s = key
        return (y - 1, 2) if s == 1 else (y, 1)
    return key - 1


def bucket_label(key, grouping: str) -> str:
    if grouping == "day":
        return f"{key.day:02d}/{key.month:02d}"
    if grouping == "week":
        return f"S{key.isocalendar().week:02d}"
    if grouping == "month":
        return f"{_MONTHS_PT[key[1] - 1]} {key[0] % 100:02d}"
    if grouping == "quarter":
        return f"T{key[1]} {key[0] % 100:02d}"
    if grouping == "semester":
        return f"S{key[1]} {key[0] % 100:02d}"
    return str(key)


def _ride_rows(db: Database):
    return db.conn.execute(
        "SELECT started_at, distance_m, moving_s, elapsed_s, ascent_m, tss, avg_power_w,"
        " avg_hr, work_kj FROM rides WHERE status='completed'").fetchall()


def _per_bucket(db: Database, grouping: str) -> dict:
    """{chave: acumuladores} de todas as sessões, por grupo."""
    out: dict = {}
    for r in _ride_rows(db):
        day = _local_date(r["started_at"])
        if day is None:
            continue
        acc = out.setdefault(bucket_of(day, grouping), {
            "distance": 0.0, "time": 0.0, "ascent": 0.0, "load": 0.0, "rides": 0,
            "work": 0.0, "p_sum": 0.0, "p_t": 0.0, "h_sum": 0.0, "h_t": 0.0})
        secs = r["moving_s"] or r["elapsed_s"] or 0
        acc["distance"] += (r["distance_m"] or 0.0) / 1000.0
        acc["time"] += secs / 3600.0
        acc["ascent"] += r["ascent_m"] or 0.0
        acc["load"] += r["tss"] or 0.0
        acc["rides"] += 1
        acc["work"] += r["work_kj"] or 0.0
        if r["avg_power_w"]:
            acc["p_sum"] += r["avg_power_w"] * secs
            acc["p_t"] += secs
        if r["avg_hr"]:
            acc["h_sum"] += r["avg_hr"] * secs
            acc["h_t"] += secs
    return out


def _value(acc: dict | None, metric: str) -> float:
    if not acc:
        return 0.0
    if metric == "avg_power":
        return acc["p_sum"] / acc["p_t"] if acc["p_t"] else 0.0
    if metric == "avg_hr":
        return acc["h_sum"] / acc["h_t"] if acc["h_t"] else 0.0
    return float(acc[metric])


def series(db: Database, metric: str, grouping: str, count: int,
           today=None) -> list[tuple[str, float]]:
    """Os últimos `count` grupos (o atual incluído), com zero onde não houve
    sessões: (rótulo, valor), do mais antigo para o mais recente."""
    from datetime import date as _date
    today = today or _date.today()
    data = _per_bucket(db, grouping)
    keys = [bucket_of(today, grouping)]
    while len(keys) < count:
        keys.append(_previous(keys[-1], grouping))
    keys.reverse()
    return [(bucket_label(k, grouping), _value(data.get(k), metric)) for k in keys]


def period_totals(db: Database, grouping: str, count: int, today=None) -> dict:
    """Somas dos últimos `count` grupos, para a linha de resumo."""
    from datetime import date as _date
    today = today or _date.today()
    data = _per_bucket(db, grouping)
    key = bucket_of(today, grouping)
    keys = []
    for _ in range(count):
        keys.append(key)
        key = _previous(key, grouping)
    total = {"distance": 0.0, "time": 0.0, "ascent": 0.0, "load": 0.0, "rides": 0,
             "work": 0.0}
    for k in keys:
        acc = data.get(k)
        if acc:
            for m in total:
                total[m] += acc[m]
    return total


def percentile_now(db: Database, metric: str, grouping: str, today=None) -> dict | None:
    """Em que percentil do teu histórico está o grupo atual (esta semana, este
    mês…). Conta todos os grupos desde a primeira sessão, também os vazios:
    treinar sempre um pouco vale mais do que um pico isolado.

    Devolve {"value", "percentile" (0–100), "best", "n"} ou None sem histórico.
    """
    from datetime import date as _date
    today = today or _date.today()
    data = _per_bucket(db, grouping)
    if not data:
        return None
    first = min(data)
    key = bucket_of(today, grouping)
    values = []
    while True:
        values.append(_value(data.get(key), metric))
        if key == first or len(values) > 5000:
            break
        key = _previous(key, grouping)
    current = values[0]
    below = sum(1 for v in values if v < current)
    equal = sum(1 for v in values if v == current)
    pct = 100.0 * (below + 0.5 * equal) / len(values)
    return {"value": current, "percentile": pct, "best": max(values), "n": len(values)}


def power_curve_detail(db: Database) -> list[dict]:
    """Melhor potência de sempre por duração, com a data e a sessão."""
    rows = db.conn.execute(
        "SELECT pc.duration_s AS d, pc.max_avg_w AS w, r.started_at, r.name, r.id"
        " FROM ride_power_curve pc JOIN rides r ON r.id = pc.ride_id"
        " WHERE r.status = 'completed' ORDER BY pc.duration_s, pc.max_avg_w DESC"
    ).fetchall()
    best: dict[int, dict] = {}
    for r in rows:
        if r["d"] not in best:
            best[r["d"]] = {"duration_s": r["d"], "watts": r["w"],
                            "date": str(r["started_at"])[:10], "name": r["name"] or "",
                            "ride_id": r["id"]}
    return [best[d] for d in sorted(best)]


def time_in_zones(db: Database, days: int | None = None) -> dict:
    """Segundos em cada zona de potência (7) e de FC (5), no período.

    Potência pela FTP de cada sessão; FC pelo limiar cardíaco atual (ou
    estimado), porque o histórico não o guarda por sessão.
    """
    from .ride import estimate_lthr
    p_bounds = db.get("power_zones_pct", [55, 75, 90, 105, 120, 150])
    h_bounds = db.get("hr_zones_pct_lthr", [68, 83, 94, 105])
    lthr = estimate_lthr(db.athlete())
    power = [0.0] * (len(p_bounds) + 1)
    hr = [0.0] * (len(h_bounds) + 1)
    sql = ("SELECT s.power_w AS p, s.hr_bpm AS h, r.ftp_at_ride_w AS ftp FROM ride_samples s"
           " JOIN rides r ON r.id = s.ride_id WHERE r.status = 'completed'")
    params: list = []
    if days:
        sql += " AND r.started_at >= ?"
        params.append(_days_ago(days))
    for row in db.conn.execute(sql, params):
        if row["p"] is not None:
            z = _zone(row["p"], p_bounds, row["ftp"] or 200)
            power[z] += 1.0
        if row["h"] is not None and lthr:
            hr[_zone(row["h"], h_bounds, lthr)] += 1.0
    return {"power": power, "hr": hr}


def _zone(value: float, bounds: list[float], ref: float) -> int:
    pct = value / ref * 100.0
    z = 0
    for b in bounds:
        if pct > b:
            z += 1
        else:
            break
    return min(z, len(bounds))


GROUPING_DAYS = {"day": 1, "week": 7, "month": 31, "quarter": 92, "semester": 183,
                 "year": 366}


# ---------------------------------------------------- perfil de potência

# Escala de potência por quilo (aproximação da tabela de Coggan): o valor
# mais baixo («não treinado») e o mais alto («classe mundial») para cada
# duração. A posição 0–100 é linear entre os dois. Não é um percentil de
# uma população medida — é onde estás nesta escala, que é a referência
# habitual no treino por potência.
COGGAN = {
    "male": {5: (10.17, 25.18), 60: (5.64, 11.50), 300: (2.33, 7.60), 3600: (1.86, 6.40)},
    "female": {5: (8.19, 19.42), 60: (4.71, 9.29), 300: (1.80, 6.61), 3600: (1.50, 5.69)},
}
COGGAN_LEVELS = ("untrained", "fair", "moderate", "good", "very_good", "excellent",
                 "exceptional", "world_class")


def power_profile(db: Database, sex: str = "male", weight_kg: float | None = None) -> list[dict]:
    """Para 5 s, 1 min, 5 min e o limiar (95 % dos melhores 20 min): W/kg,
    posição 0–100 na escala e o nível."""
    weight = weight_kg or db.athlete().weight_kg
    curve = {p["duration_s"]: p for p in power_curve_detail(db)}
    table = COGGAN.get(sex, COGGAN["male"])
    out = []
    for dur, (lo, hi) in table.items():
        if dur == 3600:
            src = curve.get(1200)
            watts = src["watts"] * 0.95 if src else None
        else:
            src = curve.get(dur)
            watts = src["watts"] if src else None
        if watts is None or not weight:
            out.append({"duration_s": dur, "wkg": None, "position": None, "level": None,
                        "date": None})
            continue
        wkg = watts / weight
        pos = max(0.0, min(100.0, (wkg - lo) / (hi - lo) * 100.0))
        level = COGGAN_LEVELS[min(len(COGGAN_LEVELS) - 1, int(pos / 100 * len(COGGAN_LEVELS)))]
        out.append({"duration_s": dur, "wkg": wkg, "watts": watts, "position": pos,
                    "level": level, "date": src["date"] if src else None})
    return out


# ================================================================ fitness
#
# Fitness (CTL), fadiga (ATL) e forma (TSB): médias exponenciais da carga
# diária a 42 e a 7 dias, e a diferença. A carga do ciclismo é a TSS; a da
# força é calculada pela frequência cardíaca (uma hora no limiar = 100) ou,
# sem FC, pelo esforço percebido. Juntas dão a carga total do corpo.

SPORTS = ("cycling", "strength", "rowing", "running", "swimming")
FORM_STATES = (            # (limite inferior da forma, chave)
    (25.0, "transition"),  # muito fresco: a perder forma
    (5.0, "fresh"),        # fresco: bom para competir ou testar
    (-10.0, "neutral"),    # zona cinzenta: nem carga nem descanso
    (-30.0, "optimal"),    # a construir forma
    (float("-inf"), "overload"),   # risco de excesso
)


def form_state(tsb: float) -> str:
    for lo, key in FORM_STATES:
        if tsb >= lo:
            return key
    return "overload"


def daily_load(db: Database, sports: tuple[str, ...] = SPORTS) -> dict:
    """{data local: carga} somando os desportos pedidos."""
    out: dict = {}
    if "cycling" in sports:
        for r in db.conn.execute("SELECT started_at, tss FROM rides WHERE status='completed'"):
            day = _local_date(r["started_at"])
            if day is not None:
                out[day] = out.get(day, 0.0) + (r["tss"] or 0.0)
    if "strength" in sports:
        for r in db.conn.execute(
                "SELECT started_at, load FROM strength_sessions WHERE status='completed'"):
            day = _local_date(r["started_at"])
            if day is not None:
                out[day] = out.get(day, 0.0) + (r["load"] or 0.0)
    for sp in ("rowing", "running", "swimming"):
        if sp in sports:
            for day, r in sport_rows(db, sp):
                out[day] = out.get(day, 0.0) + (r["load"] or 0.0)
    return out


def fitness(db: Database, days: int = 90, sports: tuple[str, ...] = SPORTS,
            today=None) -> list[dict]:
    """[{date, load, ctl, atl, tsb}] dos últimos `days` dias, até hoje."""
    from datetime import date as _date
    today = today or _date.today()
    daily = daily_load(db, sports)
    if not daily:
        return []
    # começa no primeiro dia com carga, ou antes, para haver sempre `days` dias
    day = min(min(daily), today - timedelta(days=days - 1))
    ctl = atl = 0.0
    out = []
    while day <= today:
        load = daily.get(day, 0.0)
        ctl += (load - ctl) / 42.0
        atl += (load - atl) / 7.0
        out.append({"date": day, "load": load, "ctl": ctl, "atl": atl, "tsb": ctl - atl})
        day += timedelta(days=1)
    return out[-days:]


def fitness_now(db: Database, sports: tuple[str, ...] = SPORTS, today=None) -> dict | None:
    series_ = fitness(db, 1, sports, today)
    if not series_:
        return None
    cur = dict(series_[-1])
    cur["state"] = form_state(cur["tsb"])
    return cur


# ------------------------------------------------------------ FTP estimada


def _curve_rows(db: Database) -> list[tuple]:
    rows = db.conn.execute(
        "SELECT r.started_at, pc.duration_s, pc.max_avg_w FROM ride_power_curve pc"
        " JOIN rides r ON r.id = pc.ride_id WHERE r.status = 'completed'").fetchall()
    out = []
    for r in rows:
        day = _local_date(r["started_at"])
        if day is not None:
            out.append((day, r["duration_s"], r["max_avg_w"]))
    return out


def critical_power(best: dict[int, float]) -> tuple[float, float] | None:
    """Modelo de 2 parâmetros (trabalho = CP × t + W′) a partir dos melhores
    esforços entre 2 e 20 minutos. Devolve (CP em W, W′ em J)."""
    pts = [(t, w * t) for t, w in best.items() if 120 <= t <= 1200 and w]
    if len(pts) < 3:
        return None
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    mw = sum(j for _, j in pts) / n
    var = sum((t - mt) ** 2 for t, _ in pts)
    if var <= 0:
        return None
    cp = sum((t - mt) * (j - mw) for t, j in pts) / var
    w_prime = mw - cp * mt
    if cp <= 0 or w_prime < 0:
        return None
    return cp, w_prime


def estimate_ftp_from(best: dict[int, float]) -> dict | None:
    """FTP estimada a partir dos melhores esforços de um período.

    - 60 min, se existir um esforço de uma hora (é a definição de FTP);
    - senão 95 % dos melhores 20 min;
    - senão, o modelo de potência crítica (CP), que pede 3 esforços de
      2 a 20 min. O CP fica quase sempre um pouco acima da FTP: usa-se 97 %.
    Fica sempre o valor mais alto que os dados suportam.
    """
    cands = []
    if best.get(3600):
        cands.append((best[3600], "60min"))
    if best.get(1200):
        cands.append((best[1200] * 0.95, "20min"))
    cp = critical_power(best)
    if cp is not None and not cands:
        cands.append((cp[0] * 0.97, "cp"))
    if not cands:
        return None
    ftp, method = max(cands)
    return {"ftp": int(round(ftp)), "method": method,
            "cp": round(cp[0]) if cp else None,
            "w_prime_kj": round(cp[1] / 1000.0, 1) if cp else None,
            "best20": best.get(1200), "best60": best.get(3600)}


def estimated_ftp(db: Database, days: int = 90, today=None) -> dict | None:
    """FTP estimada com as sessões dos últimos `days` dias."""
    from datetime import date as _date
    today = today or _date.today()
    start = today - timedelta(days=days)
    best: dict[int, float] = {}
    for day, d, w in _curve_rows(db):
        if start < day <= today and w > best.get(d, 0.0):
            best[d] = w
    return estimate_ftp_from(best)


def eftp_series(db: Database, grouping: str, count: int, window_days: int = 90,
                today=None) -> list[tuple[str, float]]:
    """FTP estimada no fim de cada período (janela móvel de `window_days`)."""
    from datetime import date as _date
    today = today or _date.today()
    rows = _curve_rows(db)
    keys = [bucket_of(today, grouping)]
    while len(keys) < count:
        keys.append(_previous(keys[-1], grouping))
    keys.reverse()
    out = []
    for k in keys:
        end = _bucket_end(k, grouping, today)
        start = end - timedelta(days=window_days)
        best: dict[int, float] = {}
        for day, d, w in rows:
            if start < day <= end and w > best.get(d, 0.0):
                best[d] = w
        est = estimate_ftp_from(best)
        out.append((bucket_label(k, grouping), float(est["ftp"]) if est else 0.0))
    return out


def _bucket_end(key, grouping: str, today):
    """Último dia de um período (sem passar de hoje)."""
    from datetime import date as _date
    if grouping == "day":
        end = key
    elif grouping == "week":
        end = key + timedelta(days=6)
    elif grouping == "month":
        y, m = key
        end = (_date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    elif grouping == "quarter":
        y, q = key
        m = q * 3
        end = _date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    elif grouping == "semester":
        y, s_ = key
        end = _date(y, 6, 30) if s_ == 1 else _date(y, 12, 31)
    else:
        end = _date(key, 12, 31)
    return min(end, today)


# --------------------------------------------------------- tempo em zona


def _ensure_zone_cache(db: Database) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS ride_zone_cache (ride_id TEXT NOT NULL REFERENCES"
        " rides(id) ON DELETE CASCADE, kind TEXT NOT NULL, zone INTEGER NOT NULL,"
        " seconds REAL NOT NULL, PRIMARY KEY (ride_id, kind, zone)) WITHOUT ROWID")


def ride_zone_seconds(db: Database) -> dict[str, dict]:
    """{ride_id: {"power": [...], "hr": [...], "day": data}} — em cache na base,
    calculado uma vez por sessão (com a FTP dessa sessão e o limiar atual)."""
    from .ride import estimate_lthr
    _ensure_zone_cache(db)
    p_bounds = db.get("power_zones_pct", [55, 75, 90, 105, 120, 150])
    h_bounds = db.get("hr_zones_pct_lthr", [68, 83, 94, 105])
    lthr = estimate_lthr(db.athlete())
    key = [p_bounds, h_bounds, lthr]
    if db.get("zone_cache_key") != key:          # zonas ou limiar mudaram: recalcula
        db.conn.execute("DELETE FROM ride_zone_cache")
        db.set("zone_cache_key", key)
    rides = db.conn.execute(
        "SELECT id, started_at, ftp_at_ride_w FROM rides WHERE status='completed'").fetchall()
    cached = {}
    for r in db.conn.execute("SELECT ride_id, kind, zone, seconds FROM ride_zone_cache"):
        cached.setdefault(r["ride_id"], {"power": [0.0] * (len(p_bounds) + 1),
                                         "hr": [0.0] * (len(h_bounds) + 1)})
        arr = cached[r["ride_id"]][r["kind"]]
        if r["zone"] < len(arr):
            arr[r["zone"]] = r["seconds"]
    out = {}
    for ride in rides:
        rid = ride["id"]
        if rid not in cached:
            power = [0.0] * (len(p_bounds) + 1)
            hr = [0.0] * (len(h_bounds) + 1)
            for s in db.conn.execute("SELECT power_w, hr_bpm FROM ride_samples"
                                     " WHERE ride_id = ?", (rid,)):
                if s["power_w"] is not None:
                    power[_zone(s["power_w"], p_bounds, ride["ftp_at_ride_w"] or 200)] += 1.0
                if s["hr_bpm"] is not None and lthr:
                    hr[_zone(s["hr_bpm"], h_bounds, lthr)] += 1.0
            db.conn.executemany(
                "INSERT OR REPLACE INTO ride_zone_cache(ride_id, kind, zone, seconds)"
                " VALUES (?,?,?,?)",
                [(rid, "power", z, v) for z, v in enumerate(power)]
                + [(rid, "hr", z, v) for z, v in enumerate(hr)])
            cached[rid] = {"power": power, "hr": hr}
        out[rid] = dict(cached[rid], day=_local_date(ride["started_at"]))
    db.conn.commit()
    return out


def strength_zone_seconds(db: Database) -> list[tuple]:
    """[(dia, [segundos por zona de FC])] das sessões de força."""
    import json as _json
    out = []
    for r in db.conn.execute("SELECT started_at, hr_zone_s FROM strength_sessions"
                             " WHERE status='completed'"):
        day = _local_date(r["started_at"])
        try:
            zones = _json.loads(r["hr_zone_s"]) if r["hr_zone_s"] else []
        except ValueError:
            zones = []
        if day is not None and zones:
            out.append((day, zones))
    return out


def zones_series(db: Database, kind: str, grouping: str, count: int,
                 sports: tuple[str, ...] = ("cycling",), today=None) -> list[tuple[str, list]]:
    """Segundos em cada zona, por período: [(rótulo, [z1, z2, …])]."""
    from datetime import date as _date
    today = today or _date.today()
    n = (len(db.get("power_zones_pct", [55, 75, 90, 105, 120, 150])) + 1 if kind == "power"
         else len(db.get("hr_zones_pct_lthr", [68, 83, 94, 105])) + 1)
    buckets: dict = {}

    def add(day, zones):
        acc = buckets.setdefault(bucket_of(day, grouping), [0.0] * n)
        for i, v in enumerate(zones[:n]):
            acc[i] += v

    if "cycling" in sports:
        for info in ride_zone_seconds(db).values():
            if info["day"] is not None:
                add(info["day"], info[kind])
    if "strength" in sports and kind == "hr":
        for day, zones in strength_zone_seconds(db):
            add(day, zones)
    for sp in ("rowing", "running", "swimming"):
        if sp not in sports or kind != "hr":
            continue
        import json as _json
        for day, r in sport_rows(db, sp):
            try:
                zones = _json.loads(r["hr_zone_s"]) if r["hr_zone_s"] else []
            except ValueError:
                zones = []
            if zones:
                add(day, zones)
    keys = [bucket_of(today, grouping)]
    while len(keys) < count:
        keys.append(_previous(keys[-1], grouping))
    keys.reverse()
    return [(bucket_label(k, grouping), buckets.get(k, [0.0] * n)) for k in keys]


# --------------------------------------------------- força e todos os desportos

STRENGTH_METRICS = ("volume", "sessions", "sets", "reps", "time", "load", "avg_rpe", "avg_hr")
GENERAL_METRICS = ("time", "sessions", "load")


def _strength_rows(db: Database) -> list[tuple]:
    rows = db.conn.execute(
        "SELECT started_at, elapsed_s, volume_kg, total_sets, total_reps, load, avg_rpe,"
        " avg_hr FROM strength_sessions WHERE status='completed'").fetchall()
    out = []
    for r in rows:
        day = _local_date(r["started_at"])
        if day is not None:
            out.append((day, r))
    return out


def strength_series(db: Database, metric: str, grouping: str, count: int,
                    today=None) -> list[tuple[str, float]]:
    from datetime import date as _date
    today = today or _date.today()
    acc: dict = {}
    for day, r in _strength_rows(db):
        a = acc.setdefault(bucket_of(day, grouping), {
            "volume": 0.0, "sessions": 0, "sets": 0, "reps": 0, "time": 0.0, "load": 0.0,
            "rpe_sum": 0.0, "rpe_n": 0, "hr_sum": 0.0, "hr_t": 0.0})
        secs = r["elapsed_s"] or 0
        a["volume"] += r["volume_kg"] or 0.0
        a["sessions"] += 1
        a["sets"] += r["total_sets"] or 0
        a["reps"] += r["total_reps"] or 0
        a["time"] += secs / 3600.0
        a["load"] += r["load"] or 0.0
        if r["avg_rpe"]:
            a["rpe_sum"] += r["avg_rpe"]
            a["rpe_n"] += 1
        if r["avg_hr"]:
            a["hr_sum"] += r["avg_hr"] * secs
            a["hr_t"] += secs

    def value(a):
        if not a:
            return 0.0
        if metric == "avg_rpe":
            return a["rpe_sum"] / a["rpe_n"] if a["rpe_n"] else 0.0
        if metric == "avg_hr":
            return a["hr_sum"] / a["hr_t"] if a["hr_t"] else 0.0
        return float(a[metric])

    keys = [bucket_of(today, grouping)]
    while len(keys) < count:
        keys.append(_previous(keys[-1], grouping))
    keys.reverse()
    return [(bucket_label(k, grouping), value(acc.get(k))) for k in keys]


def sport_series(db: Database, metric: str, grouping: str, count: int,
                 today=None) -> list[tuple[str, dict]]:
    """Por período e por desporto: horas, sessões ou carga.
    [(rótulo, {"cycling": v, "strength": v})]."""
    from datetime import date as _date
    today = today or _date.today()
    acc: dict = {}

    def add(day, sport, secs, load):
        a = acc.setdefault(bucket_of(day, grouping), {s: {"time": 0.0, "sessions": 0,
                                                          "load": 0.0} for s in SPORTS})
        a[sport]["time"] += secs / 3600.0
        a[sport]["sessions"] += 1
        a[sport]["load"] += load or 0.0

    for r in _ride_rows(db):
        day = _local_date(r["started_at"])
        if day is not None:
            add(day, "cycling", r["moving_s"] or r["elapsed_s"] or 0, r["tss"])
    for day, r in _strength_rows(db):
        add(day, "strength", r["elapsed_s"] or 0, r["load"])
    for sp in ("rowing", "running", "swimming"):
        for day, r in sport_rows(db, sp):
            add(day, sp, r["moving_s"] or r["elapsed_s"] or 0, r["load"])
    keys = [bucket_of(today, grouping)]
    while len(keys) < count:
        keys.append(_previous(keys[-1], grouping))
    keys.reverse()
    out = []
    for k in keys:
        a = acc.get(k)
        out.append((bucket_label(k, grouping),
                    {s: (float(a[s][metric]) if a else 0.0) for s in SPORTS}))
    return out


def sport_totals(db: Database, grouping: str, count: int, today=None) -> dict:
    """Somas por desporto nos últimos `count` períodos."""
    data = {m: sport_series(db, m, grouping, count, today) for m in GENERAL_METRICS}
    out = {s: {m: sum(v[s] for _, v in data[m]) for m in GENERAL_METRICS} for s in SPORTS}
    return out
