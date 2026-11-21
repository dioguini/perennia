"""Blocos de um treino: o que foi **alterado** e o que foi **saltado**, com o original ao lado.

Num treino por blocos (ciclismo ERG, remo, corrida na passadeira, ginásio) podes, a meio:

* **alterar** a configuração do bloco em curso (mais leve em ERG, outra resistência no remo, outra
  velocidade ou inclinação na corrida). O bloco **não salta**: só acaba quando termina ou quando
  carregas em «Saltar». O valor do plano fica guardado ao lado do que fizeste, para comparar;
* **saltar** o bloco. Fica registado quanto dele foi feito (tempo, metros ou séries) face ao que
  estava previsto, para se perceber se o bloco foi cumprido.

Cada linha é um bloco e um campo (`step_idx`, `field`): várias alterações do mesmo campo no mesmo
bloco ficam numa só linha, com o **primeiro** valor como original, o **último** como atual e o
número de alterações. Nada aqui fala com sensores nem com o ecrã.
"""
from __future__ import annotations

from typing import Any

from .db import Database, now_iso
from .i18n import tr

SKIP = "skip"
CHANGE = "change"

# campo -> (nome pt, nome en, unidade)
FIELDS: dict[str, tuple[str, str, str]] = {
    "target_w": ("potência alvo", "target power", "W"),
    "speed_kmh": ("velocidade", "speed", "km/h"),
    "incline_pct": ("inclinação", "incline", "%"),
    "resistance": ("resistência", "resistance", ""),
}

SPORT_NAMES = {"cycling": ("Ciclismo", "Cycling"), "rowing": ("Remo", "Rowing"),
               "running": ("Corrida", "Running"), "swimming": ("Natação", "Swimming"),
               "strength": ("Ginásio", "Gym")}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS block_events (
  id         INTEGER PRIMARY KEY,
  sport      TEXT NOT NULL,
  session_id TEXT NOT NULL,
  step_idx   INTEGER NOT NULL,
  kind       TEXT NOT NULL,
  field      TEXT NOT NULL DEFAULT '',
  original   REAL,
  value      REAL,
  planned    REAL,
  done       REAL,
  unit       TEXT NOT NULL DEFAULT '',
  changes    INTEGER NOT NULL DEFAULT 1,
  t_s        REAL,
  updated_at TEXT NOT NULL,
  UNIQUE (sport, session_id, step_idx, kind, field)
);
CREATE INDEX IF NOT EXISTS ix_block_events_session ON block_events(session_id);
"""


def ensure(db: Database) -> None:
    if getattr(db, "_block_log_ready", False):
        return
    db.conn.executescript(_SCHEMA)
    db.conn.commit()
    try:
        db._block_log_ready = True
    except Exception:
        pass


def scope(db: Database) -> str:
    """«block»: a alteração vale só para o bloco em curso (volta ao plano no seguinte);
    «session»: fica até ao fim da sessão. Opção `block_change_scope`."""
    from . import options
    v = str(options.get(db, "block_change_scope"))
    return v if v in ("block", "session") else "block"


def can_edit(db: Database) -> bool:
    """Pode alterar-se a configuração do bloco em curso? (opção `block_edit_enabled`; se estiver
    desligada, a velocidade da passadeira fica presa à do bloco)."""
    from . import options
    return bool(options.get(db, "block_edit_enabled"))


def record_change(db: Database, sport: str, session_id: str, step_idx: int, field: str,
                  original: float | None, value: float | None, t_s: float | None = None) -> None:
    """Regista uma alteração de configuração do bloco `step_idx`. O original é o do plano e
    guarda-se uma só vez por bloco e campo."""
    if not session_id or step_idx is None or step_idx < 0:
        return
    ensure(db)
    unit = FIELDS.get(field, ("", "", ""))[2]
    db.conn.execute(
        "INSERT INTO block_events(sport, session_id, step_idx, kind, field, original, value,"
        " unit, changes, t_s, updated_at) VALUES (?,?,?,?,?,?,?,?,1,?,?)"
        " ON CONFLICT(sport, session_id, step_idx, kind, field) DO UPDATE SET"
        " value = excluded.value, changes = changes + 1, updated_at = excluded.updated_at",
        (sport, session_id, int(step_idx), CHANGE, field, original, value, unit, t_s, now_iso()))
    db.conn.commit()


def record_skip(db: Database, sport: str, session_id: str, step_idx: int, planned: float | None,
                done: float | None, unit: str, t_s: float | None = None) -> None:
    """Regista que o bloco foi saltado, com o que já estava feito (`done`) do previsto
    (`planned`), na unidade `unit` («s», «m» ou «séries»)."""
    if not session_id or step_idx is None or step_idx < 0:
        return
    ensure(db)
    db.conn.execute(
        "INSERT INTO block_events(sport, session_id, step_idx, kind, field, planned, done,"
        " unit, changes, t_s, updated_at) VALUES (?,?,?,?,'',?,?,?,1,?,?)"
        " ON CONFLICT(sport, session_id, step_idx, kind, field) DO UPDATE SET"
        " planned = excluded.planned, done = excluded.done, unit = excluded.unit,"
        " changes = changes + 1, updated_at = excluded.updated_at",
        (sport, session_id, int(step_idx), SKIP, planned, done, unit, t_s, now_iso()))
    db.conn.commit()


def safely(fn, *args, **kw) -> None:
    """O registo nunca pode estragar uma sessão: um erro aqui é engolido."""
    try:
        fn(*args, **kw)
    except Exception:
        pass


def events(db: Database, session_id: str, sport: str | None = None) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM block_events WHERE session_id = ?"
    args: list[Any] = [session_id]
    if sport:
        sql += " AND sport = ?"
        args.append(sport)
    return [dict(r) for r in db.conn.execute(sql + " ORDER BY step_idx, kind DESC, field", args)]


def by_step(db: Database, session_id: str, sport: str | None = None) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for e in events(db, session_id, sport):
        out.setdefault(e["step_idx"], []).append(e)
    return out


def purge(db: Database, session_id: str) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM block_events WHERE session_id = ?", (session_id,))
    db.conn.commit()


def _num(v: float | None, unit: str) -> str:
    if v is None:
        return "—"
    txt = f"{v:g}" if abs(v - round(v)) > 1e-6 else f"{int(round(v))}"
    return f"{txt} {unit}".strip()


def _amount(v: float | None, unit: str) -> str:
    """Tempo em m:ss, metros ou séries."""
    if v is None:
        return "—"
    if unit == "s":
        s = int(round(v))
        return f"{s // 60}:{s % 60:02d}"
    if unit == "m":
        return f"{v:.0f} m"
    return f"{v:g} " + tr("séries", "sets") if unit == "sets" else f"{v:g} {unit}".strip()


def describe(e: dict, number: int | None = None) -> str:
    """Uma linha: «Bloco 3 · potência alvo 200 → 170 W (2 alterações)» ou
    «Bloco 5 saltado · feito 2:10 de 5:00»."""
    n = e["step_idx"] + 1 if number is None else number
    if e["kind"] == SKIP:
        return tr("Bloco {n} saltado · feito {d} de {p}", "Block {n} skipped · did {d} of {p}",
                  n=n, d=_amount(e["done"], e["unit"]), p=_amount(e["planned"], e["unit"]))
    pt, en, unit = FIELDS.get(e["field"], (e["field"], e["field"], e["unit"]))
    more = (tr(" ({k} alterações)", " ({k} changes)", k=e["changes"]) if e["changes"] > 1 else "")
    return tr("Bloco {n} · {f}: plano {a} → feito {b}{m}", "Block {n} · {f}: plan {a} → done "
              "{b}{m}", n=n, f=tr(pt, en), a=_num(e["original"], unit), b=_num(e["value"], unit),
              m=more)


def lines(db: Database, session_id: str, sport: str | None = None) -> list[str]:
    return [describe(e) for e in events(db, session_id, sport)]


def completion(e: dict) -> float | None:
    """Quanto do bloco saltado foi feito (0..1)."""
    if e["kind"] != SKIP or not e.get("planned"):
        return None
    return max(0.0, min(1.0, float(e.get("done") or 0.0) / float(e["planned"])))
