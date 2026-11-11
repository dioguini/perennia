"""O ecrã da sessão de cada desporto: que métricas aparecem e onde.

Um «layout» é uma lista de grupos, cada um com lugares para métricas:

* ciclismo — as 6 caixas do HUD, cada uma com 1 a 7 métricas (perennia.core.boxes);
* remo — 2 páginas de 12 quadrados (4 × 3);
* corrida e natação — 8 quadrados (4 × 2);
* ginásio — 4 quadrados no painel da sessão.

O **número de métricas** é escolhido no editor (e nas Definições): vai de 1
ao máximo de métricas que o desporto conhece (as que não estão desligadas).
Nas grelhas, é o tamanho da lista guardada; o ecrã da sessão distribui-as
sozinho pelo espaço (`grid_for`). No ciclismo é o total das caixas.

O editor (perennia.ui.layout_screens) mexe nisto arrastando; as sessões leem
daqui. Cada desporto guarda no seu próprio valor das definições.
"""
from __future__ import annotations

import math
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
    "time": ("Tempo total", "Total time"),
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
    "time": ("Tempo total", "Total time"),
    "avg_pace": ("Ritmo médio", "Avg pace"),
    "cur_pace": ("Ritmo atual", "Current pace"),
    "speed": ("Velocidade", "Speed"),
    "incline": ("Declive", "Incline"),
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
# o tempo total e o da volta são métricas (já não há contador no topo); a velocidade e a
# inclinação têm os seus botões ao meio do ecrã
DEFAULT_RUN = ["time", "distance", "avg_pace", "cur_pace", "hr", "hr_zone", "lap_time",
               "lap_pace"]
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


ROW_PAGE = 12          # no remo, no máximo 12 quadrados por página (V muda de página)

_GRIDS = {1: (1, 1), 2: (2, 1), 3: (3, 1), 4: (2, 2), 5: (3, 2), 6: (3, 2), 7: (4, 2),
          8: (4, 2), 9: (3, 3), 10: (4, 3), 11: (4, 3), 12: (4, 3)}


def grid_for(n: int, sport: str = "") -> tuple[int, int]:
    """(colunas, filas) para desenhar `n` quadrados num ecrã largo."""
    n = max(1, int(n))
    if sport == "gym":                       # o painel do ginásio é estreito: até 4 por fila
        return min(n, 4), -(-n // 4)
    if n in _GRIDS:
        return _GRIDS[n]
    cols = min(6, math.ceil(math.sqrt(n * 1.6)))
    return cols, -(-n // cols)


def page_sizes(sport: str, n: int) -> list[int]:
    """Quantos quadrados em cada página: só o remo tem páginas (até 12), e
    repartem-se por igual (14 → 7 + 7)."""
    n = max(1, int(n))
    if sport != "rowing":
        return [n]
    pages = -(-n // ROW_PAGE)
    base, extra = divmod(n, pages)
    return [base + (1 if i < extra else 0) for i in range(pages)]


def default_count(sport: str) -> int:
    if sport == "rowing":
        return len(ROW_DEFAULT)
    return {"running": len(DEFAULT_RUN), "swimming": len(DEFAULT_SWIM)}.get(
        sport, len(DEFAULT_GYM))


def shape(sport: str, n: int | None = None) -> Shape:
    """A forma do ecrã com `n` métricas (por omissão, as de origem)."""
    if sport == "cycling":
        from .boxes import MAX_PER_BOX, N_BOXES
        return Shape("boxes", N_BOXES, cols=N_BOXES, rows=MAX_PER_BOX, per_group=MAX_PER_BOX)
    n = max(1, int(n if n is not None else default_count(sport)))
    if sport == "rowing":
        sizes = page_sizes(sport, n)
        cols, rows = grid_for(max(sizes), sport)
        return Shape("grid", len(sizes), cols, rows, max(sizes),
                     [tr("Página {n}", "Page {n}", n=i + 1) for i in range(len(sizes))])
    cols, rows = grid_for(n, sport)
    return Shape("grid", 1, cols, rows, n,
                 [tr("Painel", "Panel") if sport == "gym" else tr("Ecrã", "Screen")])


def catalog(sport: str) -> list[tuple[str, str]]:
    """[(id, nome)] das métricas que este desporto pode mostrar."""
    if sport == "cycling":
        from . import metrics
        return [(m, metrics.REGISTRY[m].label) for m in metrics.available()]
    if sport == "rowing":
        return [(k, tr(*v)) for k, v in ROW_FIELDS.items()]
    if sport in ("running", "swimming"):
        keys = [k for k in ENDURANCE_METRICS if not (sport == "running" and k == "lengths")
                and not (sport == "swimming" and k in ("speed", "cur_pace", "incline"))]
        return [(k, tr(*ENDURANCE_METRICS[k])) for k in keys]
    return [(k, tr(*v)) for k, v in GYM_METRICS.items()]


def label(sport: str, key: str) -> str:
    return dict(catalog(sport)).get(key, key)


def _pad(keys: list, n: int) -> list:
    keys = list(keys)[:n]
    return keys + [None] * (n - len(keys))


def split(flat: list, sport: str) -> list[list[str | None]]:
    """A lista corrida repartida pelas páginas do desporto."""
    out, at = [], 0
    for size in page_sizes(sport, len(flat) or 1):
        out.append(list(flat[at:at + size]))
        at += size
    return out


class _Raw:
    """Um valor guardado a fingir-se de base de dados (para ler o rascunho)."""

    def __init__(self, key: str, value):
        self.key, self.value = key, value

    def get(self, key: str, default=None):
        return self.value if key == self.key else default


def decode(sport: str, raw) -> list[list[str | None]]:
    """Os grupos com as métricas a partir do valor guardado (None = lugar
    vazio). Nas grelhas, o número de lugares é o de métricas escolhido."""
    valid = {k for k, _ in catalog(sport)}
    if sport == "cycling":
        from . import boxes, metrics
        return [list(b["metrics"]) for b in
                boxes.load(_Raw("hud_boxes", raw), metrics.REGISTRY)]
    if sport == "rowing":
        raw = list(raw) if isinstance(raw, list) and raw else list(ROW_DEFAULT)
        return split([x if x in valid else None for x in raw], sport)
    default = {"running": DEFAULT_RUN, "swimming": DEFAULT_SWIM}.get(sport, DEFAULT_GYM)
    if not isinstance(raw, list) or not raw:
        raw = list(default)
    return [[x if x in valid else None for x in raw]]


def load(db, sport: str) -> list[list[str | None]]:
    return decode(sport, db.get(settings_key(sport)))


def encode(sport: str, groups: list[list[str | None]], old_raw=None):
    """O valor a guardar nas definições para estes grupos."""
    if sport == "cycling":
        from . import boxes, metrics
        old = boxes.load(_Raw("hud_boxes", old_raw), metrics.REGISTRY)
        return [{"name": old[i]["name"] if i < len(old) else "",
                 "metrics": [m for m in g if m][:boxes.MAX_PER_BOX]}
                for i, g in enumerate(groups)][:boxes.N_BOXES]
    if sport == "rowing":
        flat = [m for g in groups for m in g]
        # o remo guarda uma lista corrida; um lugar vazio fica com a métrica por omissão
        out, used = [], {m for m in flat if m}
        spare = [f for f in ROW_DEFAULT if f not in used]
        for m in flat:
            out.append(m if m else (spare.pop(0) if spare else ROW_DEFAULT[0]))
        return out
    return [m for m in groups[0]]


def save(db, sport: str, groups: list[list[str | None]]) -> None:
    db.set(settings_key(sport), encode(sport, groups, db.get(settings_key(sport))))


def defaults(sport: str) -> list[list[str | None]]:
    """O ecrã de origem do desporto (o que «repor» põe), sem gravar nada."""
    valid = {k for k, _ in catalog(sport)}
    if sport == "cycling":
        from . import boxes
        return [list(m) for m in boxes.DEFAULT_BOXES]
    if sport == "rowing":
        return split([x if x in valid else None for x in ROW_DEFAULT], sport)
    default = {"running": DEFAULT_RUN, "swimming": DEFAULT_SWIM}.get(sport, DEFAULT_GYM)
    return [[x if x in valid else None for x in default]]


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


# ----------------------------------------------------- número de métricas


def count(groups: list[list]) -> int:
    """Quantas métricas (lugares, nas grelhas) tem o ecrã."""
    return sum(len(g) for g in groups)


def settings_key(sport: str) -> str:
    """Onde as Definições guardam o ecrã do desporto."""
    return {"cycling": "hud_boxes", "rowing": "row_fields"}.get(sport, f"layout_{sport}")


def max_count(sport: str, available: list[str]) -> int:
    """O máximo: as métricas que o desporto conhece (as ligadas); no ciclismo,
    também o que cabe nas caixas."""
    n = len(available)
    if sport == "cycling":
        from .boxes import MAX_PER_BOX, N_BOXES
        return min(n, MAX_PER_BOX * N_BOXES)
    return n


def resized(groups: list[list], sport: str, n: int, available: list[str]
            ) -> list[list]:
    """O ecrã com `n` métricas: tira as últimas ou acrescenta as que ainda não
    estão no ecrã (pela ordem do catálogo). Nunca passa do máximo."""
    n = max(1, min(int(n), max_count(sport, available)))
    groups = [list(g) for g in groups]
    used = {m for g in groups for m in g if m}
    spare = [k for k in available if k not in used]
    if sport == "cycling":
        from .boxes import MAX_PER_BOX
        total = sum(len(g) for g in groups)
        while total > n:                   # tira da caixa com mais métricas (a última)
            big = max(range(len(groups)), key=lambda i: (len(groups[i]), i))
            if len(groups[big]) <= 1:
                break
            groups[big].pop()
            total -= 1
        while total < n and spare:         # põe na caixa com menos (a primeira)
            few = [i for i in range(len(groups)) if len(groups[i]) < MAX_PER_BOX]
            if not few:
                break
            groups[min(few, key=lambda i: (len(groups[i]), i))].append(spare.pop(0))
            total += 1
        return groups
    flat = [m for g in groups for m in g]
    if n <= len(flat):
        flat = flat[:n]
    else:
        while len(flat) < n and spare:
            flat.append(spare.pop(0))
        flat += [None] * (n - len(flat))
    return split(flat, sport)
