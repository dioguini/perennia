"""O tipo de cada treino (ciclismo, remo, corrida, natação): **ERG** ou
**Manual**, e pelo que está definido (potência, FC, RPE, ritmo, níveis do
rolo…). A grande diferença está na sessão:

* **ERG** — o aparelho segue o treino sozinho: o rolo põe os watts, a
  máquina de remo muda a resistência, a passadeira a velocidade. Precisa de
  um aparelho ligado que aceite comandos.
* **Manual** — a sessão mostra o que o treino pede e és tu que o pões no
  aparelho (o nível do rolo, a velocidade e a inclinação da passadeira, a
  resistência da máquina de remo) ou que o segues pela FC/RPE.

O ginásio não tem tipo. A natação é sempre manual.

Também aqui ficam os extras de cada bloco que os formatos de cada desporto
não guardam: margem do alvo (exato ou ± %), nível do rolo, velocidade e
inclinação da passadeira, voga do remo.
"""
from __future__ import annotations

import json

from .i18n import tr

CONTROLS = ("erg", "manual")
# que vistas (alvos) cada desporto tem em cada tipo
MODES = {
    ("cycling", "erg"): ("power",),
    ("cycling", "manual"): ("hr", "rpe", "level"),
    ("rowing", "erg"): ("power", "pace"),
    ("rowing", "manual"): ("power", "pace", "hr", "rpe"),
    ("running", "erg"): ("pace",),
    ("running", "manual"): ("pace", "hr", "rpe"),
    ("swimming", "manual"): ("pace", "hr", "rpe"),
}
ASKS_TYPE = ("cycling", "rowing", "running")     # a natação é sempre manual


def ensure(db) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS workout_meta (sport TEXT NOT NULL, workout_id TEXT NOT NULL,"
        " control TEXT, mode TEXT, blocks TEXT, PRIMARY KEY (sport, workout_id))")
    db.conn.commit()


def default_control(sport: str) -> str:
    return "erg" if sport in ("cycling", "rowing") else "manual"


def get(db, sport: str, wid: str | None) -> dict:
    """{"control", "mode", "blocks": [dict por bloco]} (com valores por omissão)."""
    out = {"control": default_control(sport), "mode": None, "blocks": []}
    if not wid:
        return out
    ensure(db)
    r = db.conn.execute("SELECT control, mode, blocks FROM workout_meta WHERE sport = ? AND"
                        " workout_id = ?", (sport, str(wid))).fetchone()
    if r is None:
        return out
    try:
        blocks = json.loads(r["blocks"] or "[]")
    except ValueError:
        blocks = []
    out.update(control=r["control"] or out["control"], mode=r["mode"], blocks=blocks)
    if sport == "swimming":
        out["control"] = "manual"
    return out


def save(db, sport: str, wid: str, control: str, mode: str, blocks: list[dict]) -> None:
    ensure(db)
    db.conn.execute(
        "INSERT INTO workout_meta(sport, workout_id, control, mode, blocks) VALUES (?,?,?,?,?)"
        " ON CONFLICT(sport, workout_id) DO UPDATE SET control=excluded.control,"
        " mode=excluded.mode, blocks=excluded.blocks",
        (sport, str(wid), control, mode, json.dumps(blocks, ensure_ascii=False)))
    db.conn.commit()


def modes(sport: str, control: str) -> tuple[str, ...]:
    return MODES.get((sport, control)) or MODES.get((sport, "manual")) or ("power",)


def control_name(control: str) -> str:
    return "ERG" if control == "erg" else tr("Manual", "Manual")


def control_help(sport: str, control: str) -> str:
    if control == "erg":
        return {"cycling": tr("o rolo põe os watts de cada bloco (precisa de um rolo ligado)",
                              "the trainer sets each block's watts (needs a trainer connected)"),
                "rowing": tr("a máquina muda a resistência em cada bloco (precisa dela ligada)",
                             "the machine changes resistance each block (needs it connected)"),
                "running": tr("a passadeira muda a velocidade sozinha (passadeira inteligente)",
                              "the treadmill changes speed itself (smart treadmill)")
                }.get(sport, "")
    return {"cycling": tr("a sessão mostra o alvo e tu pões o nível do rolo, ou segues a FC/RPE",
                          "the session shows the target and you set the trainer level, or follow "
                          "HR/RPE"),
            "rowing": tr("a sessão mostra a resistência e a voga; tu mudas na máquina",
                         "the session shows resistance and rate; you change them on the machine"),
            "running": tr("a sessão mostra a velocidade e a inclinação a pôr na passadeira",
                          "the session shows the speed and incline to set on the treadmill"),
            "swimming": tr("a sessão mostra o que fazer; contas tu as piscinas",
                           "the session shows what to do; you count the lengths")}.get(sport, "")


def mode_label(mode: str | None) -> str:
    return {"power": tr("Potência", "Power"), "hr": tr("FC", "HR"), "rpe": "RPE",
            "pace": tr("Ritmo", "Pace"), "level": tr("Níveis do rolo", "Trainer levels"),
            "custom": tr("Personalizado", "Custom")}.get(mode or "", tr("Personalizado", "Custom"))


def label(db, sport: str, wid: str | None, fallback_mode: str | None = None) -> str:
    """«Potência · ERG», «FC · Manual»… para as listas de treinos."""
    if sport not in ("cycling", "rowing", "running", "swimming"):
        return ""
    m = get(db, sport, wid)
    return f"{mode_label(m['mode'] or fallback_mode)} · {control_name(m['control'])}"


# ------------------------------------------------------------ níveis do rolo


def levels(db) -> dict:
    """Os níveis de um rolo sem controlo (definidos nas Definições): quantos, e
    os watts no nível 1 e no máximo, a 90 rpm. Entre eles, em linha reta."""
    cfg = dict(db.get("trainer_levels", {}) or {})
    return {"n": int(cfg.get("n", 10)), "w_min": float(cfg.get("w_min", 80)),
            "w_max": float(cfg.get("w_max", 400))}


def level_of(pct: float, ftp: int, cfg: dict) -> int:
    watts = pct / 100.0 * ftp
    n = max(2, cfg["n"])
    step = (cfg["w_max"] - cfg["w_min"]) / (n - 1)
    lv = 1 + round((watts - cfg["w_min"]) / step) if step > 0 else 1
    return max(1, min(n, int(lv)))


def pct_of_level(level: int, ftp: int, cfg: dict) -> float:
    n = max(2, cfg["n"])
    watts = cfg["w_min"] + (cfg["w_max"] - cfg["w_min"]) * (level - 1) / (n - 1)
    return watts / max(1, ftp) * 100.0


def level_watts(level: int, cfg: dict) -> float:
    n = max(2, cfg["n"])
    return cfg["w_min"] + (cfg["w_max"] - cfg["w_min"]) * (level - 1) / (n - 1)
