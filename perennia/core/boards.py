"""Classificações para mostrar em todo o lado.

Há dois tipos:

* quadros fixos, para os menus. Cada modo tem o seu: rota, subida, fuga,
  desafio, treino e FTP;
* o quadro ao vivo da sessão (`LiveBoards`). Escolhe o contexto mais
  relevante em cada momento e põe o atleta na posição que teria se
  acabasse agora ao ritmo atual.

Os quadros são dados simples. Quem desenha é o HUD ou o painel dos menus.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .chase import LEVELS
from .i18n import t
from .units import hms, km

MAX_ROWS = 6


@dataclass
class Row:
    rank: int | None
    value: str
    label: str = ""
    me: bool = False


@dataclass
class Board:
    title: str
    rows: list[Row] = field(default_factory=list)
    subtitle: str = ""
    empty: str = ""
    my_rank: int | None = None


# ----------------------------------------------------------------- formatos


def long_duration(seconds: float | None) -> str:
    """Durações de desafios podem durar meses: dias e horas a partir de 1 dia."""
    if seconds is None:
        return "—"
    s = int(max(0.0, seconds))
    if s < 86400:
        return hms(s)
    d, rem = divmod(s, 86400)
    return f"{d} d {rem // 3600} h"


def _date(value: Any) -> str:
    return str(value or "")[:10]


def trim_number(value: float, max_decimals: int = 2) -> str:
    """5000.34 → «5000.34», 23.50 → «23.5», 500.0 → «500»."""
    text = f"{value:.{max_decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


# Unidades em que o objetivo de um desafio pode ser escrito, em metros.
CHALLENGE_UNITS: dict[str, float] = {"km": 1000.0, "m": 1.0, "mi": 1609.344, "ft": 0.3048}


def challenge_target_text(metric: str, target: float, display_unit: str | None,
                          system: str = "metric") -> str:
    if metric in ("distance_m", "ascent_m"):
        unit = display_unit or _default_challenge_unit(metric, target, system)
        factor = CHALLENGE_UNITS.get(unit, 1.0)
        return f"{trim_number(target / factor)} {unit}"
    if metric == "time_s":
        return hms(target)
    return trim_number(target)


def challenge_progress_text(metric: str, progress: float, target: float,
                            display_unit: str | None, system: str = "metric") -> str:
    if metric in ("distance_m", "ascent_m"):
        unit = display_unit or _default_challenge_unit(metric, target, system)
        factor = CHALLENGE_UNITS.get(unit, 1.0)
        decimals = 1 if unit in ("km", "mi") else 0
        return (f"{progress / factor:.{decimals}f} / "
                f"{challenge_target_text(metric, target, unit, system)}")
    if metric == "time_s":
        return f"{hms(progress)} / {hms(target)}"
    return f"{progress:.0f} / {target:.0f}"


def _default_challenge_unit(metric: str, target: float, system: str) -> str:
    if metric == "distance_m":
        return "mi" if system == "imperial" else "km"
    if system == "imperial":
        return "ft"
    return "km" if target >= 10_000 else "m"


# ------------------------------------------------------------ ordenar com «tu»


def ranked_with_me(entries: Sequence[tuple[float, str]], mine: float | None,
                   higher_is_better: bool, fmt: Callable[[float], str],
                   me_label: str, max_rows: int = MAX_ROWS) -> tuple[list[Row], int | None]:
    """Junta o atleta às entradas guardadas e devolve as linhas a mostrar.

    O atleta aparece sempre, mesmo que esteja fora do top: nesse caso
    mostram-se os primeiros e depois a linha dele com a posição real.
    """
    ordered = sorted(entries, key=lambda e: e[0], reverse=higher_is_better)
    rows: list[Row] = []
    my_rank: int | None = None
    if mine is not None:
        if higher_is_better:
            my_rank = 1 + sum(1 for v, _ in ordered if v > mine)
        else:
            my_rank = 1 + sum(1 for v, _ in ordered if v < mine)
    combined: list[Row] = []
    rank = 1
    placed = mine is None
    for value, label in ordered:
        if not placed and my_rank == rank:
            combined.append(Row(rank, fmt(mine), me_label, me=True))
            placed = True
            rank += 1
        combined.append(Row(rank, fmt(value), label))
        rank += 1
    if not placed:
        combined.append(Row(rank, fmt(mine), me_label, me=True))
    if mine is None:
        rows = combined[:max_rows - 1]
        rows.append(Row(None, "—", me_label, me=True))
        return rows, None
    if len(combined) <= max_rows:
        return combined, my_rank
    me_index = next(i for i, r in enumerate(combined) if r.me)
    if me_index < max_rows:
        return combined[:max_rows], my_rank
    rows = combined[:max_rows - 1] + [combined[me_index]]
    return rows, my_rank


def _plain(rows: Sequence[Row], title: str, subtitle: str = "") -> Board:
    return Board(title, list(rows)[:MAX_ROWS], subtitle=subtitle, empty=t("board.empty"))


# ----------------------------------------------------------- quadros fixos


def route_board(db, route_id: str | None, highlight_ride: str | None = None) -> Board:
    if not route_id:
        return Board(t("board.route"), empty=t("board.no_route"))
    row = db.route(route_id)
    title = row["name"] if row else t("board.route")
    rows = [Row(i, hms(r["elapsed_s"]),
                _date(r["started_at"]) + (f" · {r['avg_power_w']:.0f} W"
                                          if r["avg_power_w"] else ""),
                me=bool(highlight_ride) and r["ride_id"] == highlight_ride)
            for i, r in enumerate(db.route_leaderboard(route_id, limit=MAX_ROWS), 1)]
    return _plain(rows, title, t("board.route"))


def climb_board(db, climb_id: int | None, name: str) -> Board:
    rows = [Row(i, hms(r["elapsed_s"]),
                _date(r["started_at"]) + (f" · {r['avg_power_w']:.0f} W"
                                          if r["avg_power_w"] else ""))
            for i, r in enumerate(db.climb_leaderboard(climb_id or -1, limit=MAX_ROWS), 1)]
    return _plain(rows, name, t("board.climb"))


def chase_board(db, level: str, route_id: str | None = None,
                highlight_ride: str | None = None) -> Board:
    rows = []
    for i, r in enumerate(db.chase_leaderboard(level, route_id, limit=MAX_ROWS), 1):
        bits = [_date(r["started_at"])]
        if r["avg_power_w"]:
            bits.append(f"{r['avg_power_w']:.0f} W")
        rows.append(Row(i, hms(r["survived_s"]), " · ".join(bits),
                        me=bool(highlight_ride) and r["ride_id"] == highlight_ride))
    return _plain(rows, t("chase.title"),
                  f"{t(f'chase.level.{level}')} · {_route_name(db, route_id)}")


def _route_name(db, route_id: str | None) -> str:
    if not route_id:
        return t("chase.flat")
    row = db.route(route_id)
    return row["name"] if row else t("chase.flat")


def challenge_board(db, challenge: Any, system: str = "metric") -> Board:
    attempt = db.ensure_attempt(challenge["id"])
    unit = _row_get(challenge, "display_unit")
    progress = challenge_progress_text(challenge["metric"], attempt["progress"],
                                       challenge["target"], unit, system)
    rows = [Row(i, long_duration(r["elapsed_s"]),
                f"{_date(r['started_at'])} → {_date(r['completed_at'])}")
            for i, r in enumerate(db.challenge_leaderboard(challenge["id"],
                                                           limit=MAX_ROWS), 1)]
    return _plain(rows, challenge["name"], progress)


def workout_board(db, workout_id: str, name: str = "",
                  highlight_ride: str | None = None) -> Board:
    rows = []
    for i, r in enumerate(db.workout_leaderboard(workout_id, limit=MAX_ROWS), 1):
        bits = [_date(r["started_at"])]
        if r["compliance"] is not None:
            bits.append(f"{r['compliance']:.0f} % {t('board.in_target')}")
        rows.append(Row(i, f"{r['avg_power_w']:.0f} W", " · ".join(bits),
                        me=bool(highlight_ride) and r["id"] == highlight_ride))
    return _plain(rows, name or t("menu.workouts"), t("board.workout"))


def ftp_board(db) -> Board:
    rows = [Row(i, f"{r['ftp_w']} W", f"{_date(r['tested_at'])} · {r['protocol']}")
            for i, r in enumerate(db.ftp_leaderboard(limit=MAX_ROWS), 1)]
    return _plain(rows, t("menu.ftp_test"), t("board.ftp"))


def challenges_progress_board(db, system: str = "metric") -> Board:
    rows = []
    for ch in db.challenges():
        attempt = db.ensure_attempt(ch["id"])
        pct = min(100.0, attempt["progress"] / max(ch["target"], 1e-9) * 100.0)
        rows.append(Row(None, f"{pct:.0f} %", ch["name"]))
    rows.sort(key=lambda r: -float(r.value.rstrip(" %")))
    return _plain(rows, t("menu.challenges"), t("board.progress"))


def records_board(db, system: str = "metric") -> Board:
    """Recordes pessoais, para o menu inicial."""
    from . import stats                     # evita import circular no arranque
    rec = stats.personal_records(db)
    tot = stats.totals(db)
    rows: list[Row] = []
    if rec.get("longest_ride"):
        v, u = km(rec["longest_ride"]["distance_m"] or 0, system)
        rows.append(Row(None, f"{v:.1f} {u}", t("board.longest")))
    if rec.get("most_ascent"):
        rows.append(Row(None, f"{rec['most_ascent']['ascent_m'] or 0:.0f} m",
                        t("board.most_ascent")))
    if rec.get("max_power_w"):
        rows.append(Row(None, f"{rec['max_power_w']} W", t("board.max_power")))
    if tot.get("best_20min_w"):
        rows.append(Row(None, f"{tot['best_20min_w']:.0f} W", t("board.best_20")))
    for level in ("normal", "hard"):
        best = db.chase_leaderboard(level, None, limit=1)
        if best:
            rows.append(Row(None, hms(best[0]["survived_s"]),
                            f"{t('chase.title')} · {t(f'chase.level.{level}')} · "
                            f"{t('chase.flat')}"))
    return _plain(rows, t("board.records"), f"{tot['rides']} {t('board.rides')}")


def _row_get(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


# ------------------------------------------------------------- ao vivo


class LiveBoards:
    """Quadro da sessão, sempre visível. Escolhe o contexto por prioridade:

    fuga → subida em curso → treino → teste de FTP → rota → desafios.

    As entradas guardadas são lidas uma vez por contexto. A cada frame só
    se recalcula a posição do atleta, que custa nada.
    """

    def __init__(self, engine):
        self.engine = engine
        self._cache: dict[tuple, Any] = {}

    def _cached(self, key: tuple, loader: Callable[[], Any]) -> Any:
        if key not in self._cache:
            self._cache[key] = loader()
        return self._cache[key]

    def board(self) -> Board:
        e = self.engine
        me = t("board.me")
        if e.chase is not None:
            return self._chase_board(me)
        strava = getattr(e, "strava", None)
        if strava is not None:
            sb = strava.board(e.state.pos_m, e.state.t_s)
            if sb is not None:
                return sb
        active = e.active_climb()
        if active is not None:
            return self._climb_board(active, me)
        if e.workout is not None and e.kind == "workout" and e.workout_id:
            return self._workout_board(me)
        if e.kind == "ftp_test":
            board = self._cached(("ftp",), lambda: ftp_board(e.db))
            avg = e.state.avg_power
            board.subtitle = (f"{t('board.now')}: {avg:.0f} W" if avg
                              else t("board.ftp"))
            return board
        if e.route is not None and e.route_id:
            return self._route_board(me)
        return self._cached(("challenges", int(e.state.t_s // 30)),
                            lambda: challenges_progress_board(e.db, e.units))

    # -------------------------------------------------------------- contextos

    def _chase_board(self, me: str) -> Board:
        e = self.engine
        ch = e.chase
        entries = self._cached(("chase", ch.level.id, ch.saved), lambda: [
            (r["survived_s"], _date(r["started_at"]))
            for r in e.db.chase_leaderboard(ch.level.id, e.route_id, limit=50)
            if r["ride_id"] != e.ride_id])
        rows, rank = ranked_with_me(entries, ch.t_s, True, hms, me)
        sub = f"{t(f'chase.level.{ch.level.id}')} · {_route_name(e.db, e.route_id)}"
        if not ch.clean:
            sub += " · " + t("chase.not_ranked")
        return Board(t("chase.title"), rows, subtitle=sub, my_rank=rank)

    def _climb_board(self, active: tuple, me: str) -> Board:
        e = self.engine
        climb, elapsed = active
        entries = self._cached(("climb", climb.id, e.state.loops), lambda: [
            (r["elapsed_s"], _date(r["started_at"]))
            for r in e.db.climb_leaderboard(climb.id or -1, limit=50)])
        done = e.state.pos_m - climb.start_m
        frac = done / max(climb.length_m, 1.0)
        mine = elapsed / frac if frac >= 0.05 else None
        rows, rank = ranked_with_me(entries, mine, False, hms, me)
        return Board(climb.name, rows, subtitle=t("board.projected"), my_rank=rank)

    def _workout_board(self, me: str) -> Board:
        e = self.engine
        entries = self._cached(("workout", e.workout_id), lambda: [
            (r["avg_power_w"], _date(r["started_at"]))
            for r in e.db.workout_leaderboard(e.workout_id, limit=50)])
        rows, rank = ranked_with_me(entries, e.state.avg_power, True,
                                    lambda v: f"{v:.0f} W", me)
        name = e.workout.workout.name if e.workout else t("menu.workouts")
        return Board(name, rows, subtitle=t("board.workout"), my_rank=rank)

    def _route_board(self, me: str) -> Board:
        e = self.engine
        entries = self._cached(("route", e.route_id, e.state.loops), lambda: [
            (r["elapsed_s"], _date(r["started_at"]))
            for r in e.db.route_leaderboard(e.route_id, limit=50)])
        total = e.route.total_m
        pos = e.state.pos_m
        mine = None
        if pos > min(300.0, total * 0.05):
            mine = e.loop_elapsed_s * total / pos
        rows, rank = ranked_with_me(entries, mine, False, hms, me)
        row = self._cached(("route_name", e.route_id), lambda: e.db.route(e.route_id))
        return Board(row["name"] if row else t("board.route"), rows,
                     subtitle=t("board.projected"), my_rank=rank)


def chase_level_label(level: str) -> str:
    lv = LEVELS.get(level)
    if lv is None:
        return level
    return (f"{t(f'chase.level.{level}')} · {lv.start_pct * 100:.0f} % FTP "
            f"+{lv.step_pct * 100:.0f} %/min")
