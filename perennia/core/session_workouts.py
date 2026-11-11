"""O treino de cada sessão: uma cópia guardada e o estado do original.

Quando uma sessão começa com um treino (ciclismo, remo, corrida), guarda-se
uma **cópia** do treino só para essa sessão — os passos, a definição
(ERG/manual, tolerâncias, velocidades) e os objetivos. Assim a análise da
sessão vê sempre o treino como foi feito, mesmo que o original seja editado
ou apagado da lista.

Os treinos têm um **estado** (coluna `status` nas tabelas de treinos):

* `active`  — está na lista de treinos;
* `deleted` — foi apagado da lista (os passos ficam, para as sessões antigas);
* `session` — não está na lista: é a cópia de uma sessão, ou um treino
  carregado do computador que não se quis guardar na lista.

A tabela `session_workouts` liga cada sessão à sua cópia e ao original
(`workout_id`, NULL quando veio de um ficheiro e não ficou na lista).
"""
from __future__ import annotations

import json

from .i18n import tr
from .db import now_iso

ACTIVE, DELETED, SESSION = "active", "deleted", "session"
TABLES = {"cycling": "workouts", "rowing": "row_workouts", "running": "endurance_workouts",
          "swimming": "endurance_workouts"}
SPORTS = tuple(TABLES)
# o ficheiro de onde veio cada treino carregado do computador (nesta execução)
FILES: dict[str, str] = {}


def _add_status(db, table: str) -> None:
    cols = {r["name"] for r in db.conn.execute(f"PRAGMA table_info({table})")}
    if cols and "status" not in cols:
        db.conn.execute(f"ALTER TABLE {table} ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")


def ensure(db) -> None:
    from . import endurance as en
    from . import rowing as rw
    rw.ensure(db)
    en.ensure(db)
    for table in set(TABLES.values()):
        _add_status(db, table)
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS session_workouts (kind TEXT NOT NULL,"
        " session_id TEXT NOT NULL, sport TEXT NOT NULL, workout_id TEXT, copy_id TEXT NOT NULL,"
        " origin TEXT NOT NULL DEFAULT 'list', source TEXT, name TEXT, created_at TEXT,"
        " PRIMARY KEY (kind, session_id))")
    db.conn.commit()


# ------------------------------------------------------------- estado


def status(db, sport: str, wid: str | None) -> str | None:
    """'active', 'deleted', 'session' — ou None se o treino já não existe."""
    if not wid or sport not in TABLES:
        return None
    ensure(db)
    r = db.conn.execute(f"SELECT status FROM {TABLES[sport]} WHERE id = ?", (wid,)).fetchone()
    return (r["status"] or ACTIVE) if r is not None else None


def set_status(db, sport: str, wid: str, value: str) -> None:
    ensure(db)
    db.conn.execute(f"UPDATE {TABLES[sport]} SET status = ? WHERE id = ?", (value, wid))
    db.conn.commit()


def soft_delete(db, sport: str, wid: str) -> None:
    """«Apagar» um treino da lista: sai da lista, mas os passos ficam, para as
    sessões que já o usaram."""
    set_status(db, sport, wid, DELETED)


# -------------------------------------------------------------- cópias


def copy_workout(db, sport: str, wid: str, status_: str = SESSION) -> str | None:
    """Copia o treino (passos, definição e objetivos) com outro id."""
    ensure(db)
    new = None
    if sport == "cycling":
        row = db.workout(wid)
        if row is None:
            return None
        steps = [{k: r[k] for k in ("kind", "duration_s", "target_type", "target_lo",
                                    "target_hi", "cadence_lo", "cadence_hi", "text_cue")}
                 for r in db.workout_steps(wid)]
        new = db.insert_workout(row["name"], steps, row["source_format"], row["description"],
                                row["est_tss"])
    elif sport == "rowing":
        from . import rowing as rw
        w = rw.workout(db, wid)
        if w is None:
            return None
        new = rw.save_workout(db, None, w["name"], w.get("description") or "", w["steps"])
    elif sport in ("running", "swimming"):
        from . import endurance as en
        w = en.workout(db, wid)
        if w is None:
            return None
        new = en.save_workout(db, None, sport, w["name"], w.get("description") or "",
                              w["steps"], mode=w.get("mode") or "pace")
    if new is None:
        return None
    set_status(db, sport, new, status_)
    _copy_extras(db, sport, wid, new)
    return new


def _copy_extras(db, sport: str, src: str, dst: str) -> None:
    """A definição do treino (workout_meta) e os objetivos (workout_goals)."""
    from . import workout_meta as wm
    wm.ensure(db)
    r = db.conn.execute("SELECT control, mode, blocks FROM workout_meta WHERE sport = ? AND"
                        " workout_id = ?", (sport, str(src))).fetchone()
    if r is not None:
        wm.save(db, sport, dst, r["control"], r["mode"], json.loads(r["blocks"] or "[]"))
    try:
        g = db.conn.execute("SELECT goal, blocks FROM workout_goals WHERE sport = ? AND"
                            " workout_id = ?", (sport, str(src))).fetchone()
    except Exception:
        g = None
    if g is not None:
        db.conn.execute("INSERT OR REPLACE INTO workout_goals(sport, workout_id, goal, blocks)"
                        " VALUES (?,?,?,?)", (sport, dst, g["goal"], g["blocks"]))
        db.conn.commit()


def record(db, kind: str, session_id: str, sport: str, wid: str | None) -> str | None:
    """Ao começar uma sessão com um treino: guarda a cópia do treino para ela.
    Devolve o id da cópia (None sem treino)."""
    if not wid or sport not in TABLES:
        return None
    ensure(db)
    have = db.conn.execute("SELECT copy_id FROM session_workouts WHERE kind = ? AND"
                           " session_id = ?", (kind, session_id)).fetchone()
    if have is not None:
        return have["copy_id"]
    st = status(db, sport, wid)
    if st is None:
        return None
    if st == SESSION:
        # carregado do computador e não guardado na lista: ele próprio é a cópia
        copy, origin_id, origin = wid, None, "file"
    else:
        copy, origin_id, origin = copy_workout(db, sport, wid), wid, "list"
    if copy is None:
        return None
    name = db.conn.execute(f"SELECT name FROM {TABLES[sport]} WHERE id = ?",
                           (copy,)).fetchone()
    db.conn.execute(
        "INSERT OR REPLACE INTO session_workouts(kind, session_id, sport, workout_id, copy_id,"
        " origin, source, name, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (kind, session_id, sport, origin_id, copy, origin, FILES.get(wid),
         name["name"] if name else None, now_iso()))
    db.conn.commit()
    return copy


def of_session(db, kind: str, session_id: str) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM session_workouts WHERE kind = ? AND session_id = ?",
                        (kind, session_id)).fetchone()
    return dict(r) if r is not None else None


def forget(db, kind: str, session_id: str) -> None:
    """A sessão foi descartada: a cópia vai com ela."""
    ensure(db)
    r = of_session(db, kind, session_id)
    if r is None:
        return
    db.conn.execute("DELETE FROM session_workouts WHERE kind = ? AND session_id = ?",
                    (kind, session_id))
    db.conn.commit()
    _drop_copy(db, r["sport"], r["copy_id"])


def _drop_copy(db, sport: str, copy_id: str) -> None:
    """Apaga uma cópia que já nenhuma sessão usa."""
    if status(db, sport, copy_id) != SESSION:
        return
    if db.conn.execute("SELECT 1 FROM session_workouts WHERE copy_id = ?",
                       (copy_id,)).fetchone():
        return
    for table in ("rides", "row_sessions", "endurance_sessions"):
        if db.conn.execute(f"SELECT 1 FROM {table} WHERE workout_id = ?",
                           (copy_id,)).fetchone():
            return
    db.conn.execute(f"DELETE FROM {TABLES[sport]} WHERE id = ?", (copy_id,))
    db.conn.execute("DELETE FROM workout_meta WHERE sport = ? AND workout_id = ?",
                    (sport, copy_id))
    db.conn.commit()


def purge(db) -> int:
    """Arrumação no arranque: ligações de sessões que já não existem e cópias
    (ou treinos carregados só para uma sessão) que ficaram sem sessão."""
    ensure(db)
    n = 0
    for sport in ("cycling", "rowing", "running", "swimming"):
        table = TABLES[sport]
        extra = " AND sport = ?" if table == "endurance_workouts" else ""
        args = (sport,) if extra else ()
        for r in db.conn.execute(f"SELECT id FROM {table} WHERE status = 'session'{extra}",
                                 args).fetchall():
            _drop_copy(db, sport, r["id"])
    for kind, table in (("ride", "rides"), ("row", "row_sessions"),
                        ("endurance", "endurance_sessions")):
        gone = db.conn.execute(
            f"SELECT session_id, sport, copy_id FROM session_workouts WHERE kind = ? AND"
            f" session_id NOT IN (SELECT id FROM {table})", (kind,)).fetchall()
        for r in gone:
            db.conn.execute("DELETE FROM session_workouts WHERE kind = ? AND session_id = ?",
                            (kind, r["session_id"]))
            db.conn.commit()
            _drop_copy(db, r["sport"], r["copy_id"])
            n += 1
    return n


# ------------------------------------------------------------- textos


def state(db, kind: str, session_id: str, sport: str, wid: str | None) -> str | None:
    """O estado do treino desta sessão: 'list' (está na lista), 'deleted'
    (apagado da lista), 'file' (do computador, não guardado), 'gone' (já não
    existe) — None se a sessão não teve treino."""
    r = of_session(db, kind, session_id)
    if r is None:
        if not wid:
            return None
        st = status(db, sport, wid)
        return {ACTIVE: "list", DELETED: "deleted", SESSION: "file"}.get(st or "", "gone")
    if r["workout_id"] is None:
        return "file"
    st = status(db, sport, r["workout_id"])
    return {ACTIVE: "list", DELETED: "deleted"}.get(st or "", "gone")


STATE_TEXT = {
    "list": ("Na lista de treinos", "In the workout list"),
    "deleted": ("Apagado da lista · a cópia ficou com a sessão",
                "Deleted from the list · the copy stays with the session"),
    "file": ("Carregado do computador · não guardado na lista",
             "Loaded from the computer · not kept in the list"),
    "gone": ("Já não existe na lista", "No longer in the list"),
}


def state_text(value: str | None) -> str:
    return tr(*STATE_TEXT[value]) if value in STATE_TEXT else ""
