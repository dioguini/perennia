"""Testes de aptidão por modalidade: ciclismo, remo, corrida e longevidade.

Cada teste tem nome, unidade, se é melhor mais alto ou mais baixo, uma
duração (para os testes «em X segundos» ou «durante X minutos»), as
instruções e, no ciclismo, o protocolo que o motor da sessão corre. Os que
vêm com a aplicação podem ser editados; podes criar os teus. Os resultados
ficam com data e notas, e dão o histórico e a tendência.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from .db import Database, now_iso

SPORTS = ("cycling", "rowing", "running", "swimming", "longevity")

# (desporto, nome, unidade, melhor, duração s, protocolo, instruções)
CATALOG: tuple[tuple, ...] = (
    # ciclismo — correm no rolo, com o protocolo do motor
    ("cycling", "FTP — 20 minutos", "W", "higher", 0, "20min",
     "Aquecimento, 5 min forte, recuperação e 20 min no máximo sustentável. FTP = 95 % da média."),
    ("cycling", "FTP — rampa", "W", "higher", 0, "ramp",
     "Degraus de 1 min, +20 W, até não aguentar. FTP = 75 % do melhor minuto."),
    ("cycling", "FTP — 2 × 8 minutos", "W", "higher", 0, "8x8",
     "Dois blocos de 8 min no máximo. FTP = 90 % do melhor bloco."),
    ("cycling", "Sprint — 5 segundos", "W", "higher", 0, "sprint",
     "Aquecimento e três sprints de 10 s, sentado ou de pé. Conta o melhor 5 s."),
    ("cycling", "1 minuto máximo", "W", "higher", 0, "1min",
     "Aquecimento e 1 min a fundo. Mede a capacidade anaeróbia."),
    ("cycling", "5 minutos máximo (VO2máx)", "W", "higher", 0, "5min",
     "Aquecimento e 5 min no máximo. Dá uma estimativa do VO2máx."),
    # remo — registo à mão por agora (a máquina liga-se mais tarde)
    ("rowing", "2000 m", "s", "lower", 0, None,
     "O teste clássico do remo. Ritmo constante, últimos 500 m a fundo."),
    ("rowing", "500 m", "s", "lower", 0, None, "500 m no máximo."),
    ("rowing", "Distância em 30 minutos", "m", "higher", 1800, None,
     "30 min no máximo sustentável, a uma voga de 20 a 24."),
    ("rowing", "Distância em 1 minuto", "m", "higher", 60, None, "1 min a fundo."),
    # corrida
    ("running", "5 km", "s", "lower", 0, None, "5 km no máximo, em pista ou plano."),
    ("running", "Cooper — 12 minutos", "m", "higher", 720, None,
     "A maior distância possível em 12 min. Dá uma estimativa do VO2máx."),
    ("running", "1 km", "s", "lower", 0, None, "1 km no máximo."),
    ("running", "3 km", "s", "lower", 0, None, "3 km no máximo."),
    # natação
    ("swimming", "400 m", "s", "lower", 0, None, "400 m no máximo, ritmo constante."),
    ("swimming", "200 m", "s", "lower", 0, None,
     "200 m no máximo. Com o de 400 m dá o ritmo crítico (CSS)."),
    ("swimming", "100 m", "s", "lower", 0, None, "100 m a fundo."),
    ("swimming", "Distância em 30 minutos", "m", "higher", 1800, None,
     "30 min no máximo sustentável (teste T30)."),
    # longevidade
    ("longevity", "Força de preensão — mão direita", "kg", "higher", 0, None,
     "Dinamómetro, de pé, braço ao lado do corpo. Três tentativas, conta a melhor."),
    ("longevity", "Força de preensão — mão esquerda", "kg", "higher", 0, None,
     "Dinamómetro, de pé, braço ao lado do corpo. Três tentativas, conta a melhor."),
    ("longevity", "Flexões em 1 minuto", "reps", "higher", 60, None,
     "Flexões completas (peito perto do chão, braços esticados) em 60 s."),
    ("longevity", "Flexões máximas", "reps", "higher", 0, None,
     "Sem pausa, até não conseguires fazer mais uma com boa técnica."),
    ("longevity", "Elevações máximas", "reps", "higher", 0, None,
     "Pegada prona, do braço esticado ao queixo acima da barra."),
    ("longevity", "Elevações em 1 minuto", "reps", "higher", 60, None,
     "Quantas elevações completas em 60 s (podes descansar pendurado)."),
    ("longevity", "Suspensão na barra", "s", "higher", 0, None,
     "Pendurado na barra, braços esticados, o máximo de tempo."),
    ("longevity", "Sentar e levantar em 30 s", "reps", "higher", 30, None,
     "Cadeira de ~43 cm, braços cruzados: levantar e sentar o máximo de vezes em 30 s."),
    ("longevity", "Agachamentos em 1 minuto", "reps", "higher", 60, None,
     "Agachamento ao paralelo, sem carga, o máximo em 60 s."),
    ("longevity", "Equilíbrio numa perna, olhos fechados", "s", "higher", 0, None,
     "Mãos na cintura, olhos fechados. Para quando o pé de apoio se mexe ou o outro toca no chão."),
    ("longevity", "Sentar e levantar do chão (0–10)", "pts", "higher", 0, None,
     "Sentar no chão e levantar sem ajudas: 5 pontos para descer, 5 para subir; tira-se 1 por cada apoio (mão, joelho, antebraço)."),
    ("longevity", "Prancha", "s", "higher", 0, None, "Prancha nos antebraços, o máximo de tempo."),
    ("longevity", "Salto vertical", "cm", "higher", 0, None,
     "Salto com contramovimento; três tentativas, conta a melhor."),
    ("longevity", "Caminhada de 6 minutos", "m", "higher", 360, None,
     "A maior distância a andar (sem correr) em 6 min."),
)

UNITS = ("W", "W/kg", "s", "m", "km", "reps", "kg", "cm", "pts", "bpm", "ml/kg/min", "outro")


def ensure(db: Database) -> None:
    db.conn.executescript("""
    CREATE TABLE IF NOT EXISTS fitness_tests (
      id           INTEGER PRIMARY KEY,
      sport        TEXT NOT NULL,
      name         TEXT NOT NULL,
      unit         TEXT NOT NULL,
      better       TEXT NOT NULL DEFAULT 'higher',
      duration_s   INTEGER NOT NULL DEFAULT 0,
      protocol     TEXT,
      instructions TEXT,
      custom       INTEGER NOT NULL DEFAULT 0,
      active       INTEGER NOT NULL DEFAULT 1,
      sort         INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS test_results (
      id        INTEGER PRIMARY KEY,
      test_id   INTEGER NOT NULL REFERENCES fitness_tests(id) ON DELETE CASCADE,
      done_on   TEXT NOT NULL,
      value     REAL NOT NULL,
      notes     TEXT,
      ride_id   TEXT REFERENCES rides(id) ON DELETE SET NULL,
      extra     TEXT,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_test_results ON test_results(test_id, done_on);
    """)


def seed(db: Database) -> None:
    ensure(db)
    if db.get("tests_seeded", False):
        return
    db.conn.executemany(
        "INSERT INTO fitness_tests(sport, name, unit, better, duration_s, protocol,"
        " instructions, custom, sort) VALUES (?,?,?,?,?,?,?,0,?)",
        [(sp, n, u, b, d, p, ins, i) for i, (sp, n, u, b, d, p, ins) in enumerate(CATALOG)])
    db.conn.commit()
    db.set("tests_seeded", True)


def tests(db: Database, sport: str, include_inactive: bool = False) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM fitness_tests WHERE sport = ?"
    if not include_inactive:
        sql += " AND active = 1"
    sql += " ORDER BY sort, id"
    out = []
    for r in db.conn.execute(sql, (sport,)):
        d = dict(r)
        d.update(summary(db, d))
        out.append(d)
    return out


def test(db: Database, test_id: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM fitness_tests WHERE id = ?", (test_id,)).fetchone()
    return dict(r) if r else None


def by_protocol(db: Database, protocol: str) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM fitness_tests WHERE protocol = ? ORDER BY id LIMIT 1",
                        (protocol,)).fetchone()
    return dict(r) if r else None


def save_test(db: Database, test_id: int | None, *, sport: str, name: str, unit: str,
              better: str = "higher", duration_s: int = 0, instructions: str = "",
              protocol: str | None = None) -> int:
    ensure(db)
    name = name.strip() or "Teste"
    if test_id is None:
        sort = db.conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM fitness_tests"
                               ).fetchone()["s"]
        cur = db.conn.execute(
            "INSERT INTO fitness_tests(sport, name, unit, better, duration_s, protocol,"
            " instructions, custom, sort) VALUES (?,?,?,?,?,?,?,1,?)",
            (sport, name, unit, better, int(duration_s), protocol, instructions, sort))
        db.conn.commit()
        return int(cur.lastrowid)
    db.conn.execute(
        "UPDATE fitness_tests SET name=?, unit=?, better=?, duration_s=?, instructions=?"
        " WHERE id = ?", (name, unit, better, int(duration_s), instructions, test_id))
    db.conn.commit()
    return test_id


def set_active(db: Database, test_id: int, active: bool) -> None:
    db.conn.execute("UPDATE fitness_tests SET active = ? WHERE id = ?", (int(active), test_id))
    db.conn.commit()


def delete_test(db: Database, test_id: int) -> None:
    db.conn.execute("DELETE FROM fitness_tests WHERE id = ?", (test_id,))
    db.conn.commit()


def add_result(db: Database, test_id: int, value: float, *, done_on: str | None = None,
               notes: str | None = None, ride_id: str | None = None,
               extra: dict | None = None) -> int:
    ensure(db)
    cur = db.conn.execute(
        "INSERT INTO test_results(test_id, done_on, value, notes, ride_id, extra, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (test_id, done_on or date.today().isoformat(), float(value), notes, ride_id,
         json.dumps(extra) if extra else None, now_iso()))
    db.conn.commit()
    return int(cur.lastrowid)


def delete_result(db: Database, result_id: int) -> None:
    db.conn.execute("DELETE FROM test_results WHERE id = ?", (result_id,))
    db.conn.commit()


def results(db: Database, test_id: int) -> list[dict]:
    ensure(db)
    return [dict(r) for r in db.conn.execute(
        "SELECT * FROM test_results WHERE test_id = ? ORDER BY done_on DESC, id DESC",
        (test_id,))]


def summary(db: Database, t_: dict) -> dict:
    rows = db.conn.execute("SELECT value, done_on FROM test_results WHERE test_id = ?"
                           " ORDER BY done_on, id", (t_["id"],)).fetchall()
    if not rows:
        return {"last": None, "last_on": None, "best": None, "n": 0, "trend": None}
    vals = [r["value"] for r in rows]
    best = max(vals) if t_["better"] == "higher" else min(vals)
    trend = None
    if len(vals) >= 2:
        diff = vals[-1] - vals[-2]
        good = diff > 0 if t_["better"] == "higher" else diff < 0
        trend = "up" if good else ("same" if diff == 0 else "down")
    return {"last": vals[-1], "last_on": rows[-1]["done_on"], "best": best, "n": len(vals),
            "trend": trend}


def record_protocol(db: Database, protocol: str, value: float, ride_id: str | None,
                    extra: dict | None = None) -> int | None:
    """Um teste de ciclismo acabou: guarda o resultado no teste com esse protocolo."""
    t_ = by_protocol(db, protocol)
    if t_ is None:
        return None
    return add_result(db, t_["id"], value, ride_id=ride_id, extra=extra)


def fmt_value(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "s":
        s = int(round(value))
        if s >= 60:
            return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else \
                f"{s // 60}:{s % 60:02d}"
        return f"{value:g} s"
    if unit == "m":
        return f"{value:,.0f} m".replace(",", " ")
    return f"{value:g} {unit}"


def vo2max_from_5min(watts: float, weight_kg: float) -> float:
    """Estimativa do VO2máx (ml/kg/min) a partir da potência de 5 min,
    pela equação do ACSM para cicloergómetro: 10,8 × W/kg + 7."""
    return 10.8 * watts / max(1.0, weight_kg) + 7.0


def vo2max_cooper(meters: float) -> float:
    """Teste de Cooper (12 min a correr): (m − 504,9) / 44,73."""
    return (meters - 504.9) / 44.73
