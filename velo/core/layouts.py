"""O ecrã da sessão de cada desporto: que métricas aparecem e onde.

Um «layout» é uma lista de grupos, cada um com lugares para métricas:

* ciclismo — as 6 caixas do HUD, cada uma com 1 a 7 métricas (velo.core.boxes);
* remo — 2 páginas de 12 quadrados (4 × 3);
* corrida e natação — 8 quadrados (4 × 2);
* ginásio — 4 quadrados no painel da sessão.

O editor (velo.ui.layout_screens) mexe nisto arrastando; as sessões leem
daqui. Cada desporto guarda no seu próprio valor das definições.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .i18n import tr

# --------------------------------------------------------------------- remo

ROW_FIELDS: dict[str, tuple[str, str]] = {
    "pace": ("Ritmo /500 m", "Pace /500 m"),
    "avg_pace": ("Ritmo médio", "Avg pace"),
    "best_pace": ("Melhor ritmo", "Best pace"),
    "split500": ("Últimos 500 m", "Last 500 m"),
    "spm": ("Voga (spm)", "Stroke rate"),
    "avg_spm": ("Voga média", "Avg stroke rate"),
    "power": ("Potência", "Power"),
    "avg_power": ("Potência média", "Avg power"),
    "max_power": ("Potência máxima", "Max power"),
    "pct_ftp": ("% da FTP", "% of FTP"),
    "wkg": ("W/kg", "W/kg"),
    "jps": ("Energia por remada", "Energy per stroke"),
    "distance": ("Distância", "Distance"),
    "time": ("Tempo", "Time"),
    "strokes": ("Remadas", "Strokes"),
    "dps": ("Metros por remada", "Metres per stroke"),
    "hr": ("FC", "HR"),
    "avg_hr": ("FC média", "Avg HR"),
    "max_hr": ("FC máxima", "Max HR"),
    "zone": ("Zona de FC", "HR zone"),
    "resistance": ("Resistência", "Resistance"),
    "kcal": ("kcal", "kcal"),
    "kcal_h": ("kcal/h", "kcal/h"),
    "load": ("Carga (TSS)", "Load (TSS)"),
    "lap": ("Volta atual", "Current lap"),
    "lap_time": ("Tempo da volta", "Lap time"),
    "lap_dist": ("Distância da volta", "Lap distance"),
    "lap_pace": ("Ritmo da volta", "Lap pace"),
    "last_lap_pace": ("Ritmo da volta anterior", "Last lap pace"),
    "step_left": ("Falta no passo", "Step remaining"),
    "target": ("Alvo do passo", "Step target"),
    "target_delta": ("Diferença para o alvo", "Off target by"),
    "projected": ("Projeção 2 km", "Projected 2 km"),
    "finish": ("Tempo final previsto", "Projected finish"),
}
ROW_DEFAULT = ["pace", "spm", "power", "distance",
               "time", "hr", "resistance", "avg_pace",
               "split500", "lap_time", "avg_power", "dps",
               # página 2
               "avg_spm", "max_power", "best_pace", "pct_ftp",
               "load", "jps", "kcal", "kcal_h",
               "strokes", "zone", "last_lap_pace", "step_left"]

# -------------------------------------------------------------- corrida/natação

ENDURANCE_METRICS: dict[str, tuple[str, str]] = {
    "distance": ("Distância", "Distance"),
    "time": ("Tempo", "Time"),
    "avg_pace": ("Ritmo médio", "Avg pace"),
    "cur_pace": ("Ritmo atual", "Current pace"),
    "speed": ("Velocidade", "Speed"),
    "hr": ("FC", "HR"),
    "hr_zone": ("Zona de FC", "HR zone"),
    "avg_hr": ("FC média", "Avg HR"),
    "max_hr": ("FC máxima", "Max HR"),
    "lap": ("Volta", "Lap"),
    "lap_time": ("Tempo da volta", "Lap time"),
    "lap_dist": ("Distância da volta", "Lap distance"),
    "lap_pace": ("Ritmo da volta", "Lap pace"),
    "lengths": ("Piscinas", "Lengths"),
    "step_left": ("Falta no passo", "Step remaining"),
    "target": ("Alvo do passo", "Step target"),
    "load": ("Carga", "Load"),
}
DEFAULT_RUN = ["distance", "avg_pace", "hr", "hr_zone", "lap", "lap_pace", "speed", "cur_pace"]
DEFAULT_SWIM = ["distance", "avg_pace", "hr", "hr_zone", "lap", "lap_pace", "lengths", "avg_hr"]

# ------------------------------------------------------------------ ginásio

GYM_METRICS: dict[str, tuple[str, str]] = {
    "hr": ("FC", "HR"),
    "hr_zone": ("Zona de FC", "HR zone"),
    "avg_hr": ("FC média", "Avg HR"),
    "sets": ("Séries feitas", "Sets done"),
    "reps": ("Repetições", "Reps"),
    "volume": ("Volume", "Volume"),
    "exercise": ("Exercício", "Exercise"),
    "session_time": ("Tempo total", "Total time"),
    "phase_time": ("Série / descanso", "Set / rest"),
}
DEFAULT_GYM = ["hr", "hr_zone", "sets", "volume"]


@dataclass
class Shape:
    """Como se desenha o layout: caixas em coluna (ciclismo) ou grelha."""
    kind: str                  # "boxes" | "grid"
    groups: int
    cols: int = 4
    rows: int = 3
    per_group: int = 12        # lugares por grupo (máximo, nas caixas)
    group_names: list[str] = field(default_factory=list)


def shape(sport: str) -> Shape:
    if sport == "cycling":
        from .boxes import MAX_PER_BOX, N_BOXES
        return Shape("boxes", N_BOXES, cols=N_BOXES, rows=MAX_PER_BOX, per_group=MAX_PER_BOX)
    if sport == "rowing":
        return Shape("grid", 2, 4, 3, 12, [tr("Página 1", "Page 1"), tr("Página 2", "Page 2")])
    if sport in ("running", "swimming"):
        return Shape("grid", 1, 4, 2, 8, [tr("Ecrã", "Screen")])
    return Shape("grid", 1, 4, 1, 4, [tr("Painel", "Panel")])


def catalog(sport: str) -> list[tuple[str, str]]:
    """[(id, nome)] das métricas que este desporto pode mostrar."""
    if sport == "cycling":
        from . import metrics
        return [(m, metrics.REGISTRY[m].label) for m in metrics.available()]
    if sport == "rowing":
        return [(k, tr(*v)) for k, v in ROW_FIELDS.items()]
    if sport in ("running", "swimming"):
        keys = [k for k in ENDURANCE_METRICS if not (sport == "running" and k == "lengths")
                and not (sport == "swimming" and k in ("speed", "cur_pace"))]
        return [(k, tr(*ENDURANCE_METRICS[k])) for k in keys]
    return [(k, tr(*v)) for k, v in GYM_METRICS.items()]


def label(sport: str, key: str) -> str:
    return dict(catalog(sport)).get(key, key)


def _pad(keys: list, n: int) -> list:
    keys = list(keys)[:n]
    return keys + [None] * (n - len(keys))


def load(db, sport: str) -> list[list[str | None]]:
    """Os grupos com as métricas (None = lugar vazio)."""
    sh = shape(sport)
    valid = {k for k, _ in catalog(sport)}
    if sport == "cycling":
        from . import boxes, metrics
        return [list(b["metrics"]) for b in boxes.load(db, metrics.REGISTRY)]
    if sport == "rowing":
        raw = db.get("row_fields") or list(ROW_DEFAULT)
        raw = [x if x in valid else None for x in raw]
        flat = _pad(raw, sh.groups * sh.per_group)
        return [flat[g * sh.per_group:(g + 1) * sh.per_group] for g in range(sh.groups)]
    key = f"layout_{sport}"
    default = {"running": DEFAULT_RUN, "swimming": DEFAULT_SWIM}.get(sport, DEFAULT_GYM)
    raw = db.get(key)
    if not isinstance(raw, list):
        raw = list(default)
    raw = [x if x in valid else None for x in raw]
    return [_pad(raw, sh.per_group)]


def save(db, sport: str, groups: list[list[str | None]]) -> None:
    if sport == "cycling":
        from . import boxes, metrics
        old = boxes.load(db, metrics.REGISTRY)
        boxes.save(db, [{"name": old[i]["name"] if i < len(old) else "",
                         "metrics": [m for m in g if m]} for i, g in enumerate(groups)])
        return
    if sport == "rowing":
        flat = [m for g in groups for m in g]
        # o remo guarda uma lista corrida; um lugar vazio fica com a métrica por omissão
        out, used = [], {m for m in flat if m}
        spare = [f for f in ROW_DEFAULT if f not in used]
        for m in flat:
            out.append(m if m else (spare.pop(0) if spare else ROW_DEFAULT[0]))
        db.set("row_fields", out)
        return
    db.set(f"layout_{sport}", [m for m in groups[0]])


def reset(db, sport: str) -> None:
    if sport == "cycling":
        db.set("hud_boxes", None)
    elif sport == "rowing":
        db.set("row_fields", None)
    else:
        db.set(f"layout_{sport}", None)


def keys(db, sport: str) -> list[str | None]:
    """Tudo numa lista (as sessões de grelha leem assim)."""
    return [m for g in load(db, sport) for m in g]
