"""Inventário de artigos: o material que tens (máquinas, barras, discos…).

Cada artigo tem um tipo (`kind`), que é o que os exercícios pedem: um
exercício de kettlebell precisa de um artigo do tipo «kettlebell». Assim o
treino surpresa só escolhe exercícios que podes fazer com o que tens.
"""
from __future__ import annotations

from .db import Database, now_iso
from .i18n import tr

# tipo: (pt, en, grupo)
KINDS: dict[str, tuple[str, str, str]] = {
    "trainer": ("Rolo de treino", "Indoor trainer", "machines"),
    "bike": ("Bicicleta", "Bike", "machines"),
    "rower": ("Máquina de remo", "Rowing machine", "machines"),
    "treadmill": ("Passadeira", "Treadmill", "machines"),
    "air_bike": ("Bicicleta de ar", "Air bike", "machines"),
    "ski_erg": ("SkiErg", "SkiErg", "machines"),
    "cable": ("Máquina de cabos", "Cable machine", "machines"),
    "barbell": ("Barra olímpica", "Barbell", "free_weights"),
    "plates": ("Discos", "Weight plates", "free_weights"),
    "dumbbell": ("Halteres", "Dumbbells", "free_weights"),
    "kettlebell": ("Kettlebell", "Kettlebell", "free_weights"),
    "sandbag": ("Sandbag", "Sandbag", "free_weights"),
    "medball": ("Bola medicinal", "Medicine ball", "free_weights"),
    "rack": ("Rack / suporte", "Rack", "stations"),
    "bench": ("Banco", "Bench", "stations"),
    "pullup_bar": ("Barra de elevações", "Pull-up bar", "stations"),
    "rings": ("Argolas de ginástica", "Gymnastic rings", "bodyweight"),
    "trx": ("TRX / fitas", "Suspension trainer", "bodyweight"),
    "parallettes": ("Paralelas", "Parallettes", "bodyweight"),
    "bands": ("Elásticos", "Resistance bands", "bodyweight"),
    "box": ("Caixa de saltos", "Plyo box", "bodyweight"),
    "jump_rope": ("Corda de saltar", "Jump rope", "bodyweight"),
    "mat": ("Tapete", "Mat", "other"),
    "foam_roller": ("Rolo de massagem", "Foam roller", "other"),
    "hr_strap": ("Banda cardíaca", "HR strap", "electronics"),
    "watch": ("Relógio", "Watch", "electronics"),
    "power_meter": ("Medidor de potência", "Power meter", "electronics"),
    "other": ("Outro", "Other", "other"),
}
GROUPS = {"machines": ("Máquinas", "Machines"), "free_weights": ("Pesos livres", "Free weights"),
          "stations": ("Estações", "Stations"), "bodyweight": ("Peso do corpo", "Bodyweight"),
          "electronics": ("Eletrónica", "Electronics"), "other": ("Outros", "Other")}


def kind_name(kind: str) -> str:
    k = KINDS.get(kind)
    return tr(k[0], k[1]) if k else kind


def ensure(db: Database) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS equipment_items (id INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'other', qty INTEGER NOT NULL DEFAULT 1,"
        " weight_kg REAL, notes TEXT, created_at TEXT NOT NULL)")
    db.conn.commit()


def items(db: Database, kind: str | None = None) -> list[dict]:
    ensure(db)
    sql = "SELECT * FROM equipment_items"
    args: list = []
    if kind:
        sql += " WHERE kind = ?"
        args.append(kind)
    rows = [dict(r) for r in db.conn.execute(sql + " ORDER BY kind, weight_kg, name", args)]
    order = list(KINDS)
    rows.sort(key=lambda r: (order.index(r["kind"]) if r["kind"] in order else 99,
                             r["weight_kg"] or 0, r["name"]))
    return rows


def item(db: Database, iid: int) -> dict | None:
    ensure(db)
    r = db.conn.execute("SELECT * FROM equipment_items WHERE id = ?", (iid,)).fetchone()
    return dict(r) if r else None


def save(db: Database, iid: int | None, *, name: str, kind: str = "other", qty: int = 1,
         weight_kg: float | None = None, notes: str | None = None) -> int:
    ensure(db)
    name = (name or "").strip() or kind_name(kind)
    qty = max(0, int(qty))
    if iid is None:
        c = db.conn.execute(
            "INSERT INTO equipment_items(name, kind, qty, weight_kg, notes, created_at)"
            " VALUES (?,?,?,?,?,?)", (name, kind, qty, weight_kg, notes, now_iso()))
        iid = int(c.lastrowid)
    else:
        db.conn.execute("UPDATE equipment_items SET name=?, kind=?, qty=?, weight_kg=?, notes=?"
                        " WHERE id = ?", (name, kind, qty, weight_kg, notes, iid))
    db.conn.commit()
    return iid


def delete(db: Database, iid: int) -> None:
    ensure(db)
    db.conn.execute("DELETE FROM equipment_items WHERE id = ?", (iid,))
    db.conn.commit()


def available_kinds(db: Database) -> set[str]:
    """Tipos de material que tens (quantidade > 0)."""
    ensure(db)
    return {r["kind"] for r in db.conn.execute(
        "SELECT DISTINCT kind FROM equipment_items WHERE qty > 0")}


def total_weight(db: Database, kind: str) -> float:
    """Peso total dos artigos de um tipo (ex.: todos os discos)."""
    ensure(db)
    r = db.conn.execute("SELECT SUM(qty * COALESCE(weight_kg, 0)) AS w FROM equipment_items"
                        " WHERE kind = ?", (kind,)).fetchone()
    return float(r["w"] or 0.0)


def summary(db: Database) -> dict:
    rows = items(db)
    return {"articles": len(rows), "units": sum(r["qty"] for r in rows),
            "kinds": len({r["kind"] for r in rows})}
