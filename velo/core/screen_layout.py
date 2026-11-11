"""A disposição do ecrã da sessão de cada desporto: onde fica cada painel.

O ecrã da sessão divide-se numa grelha de `COLS` × `ROWS` (abaixo da faixa
do topo e do cabeçalho com o tempo). Cada painel — as caixas ou quadrados de
métricas, as voltas, a classificação, o plano do treino, os gráficos e as
tabelas — ocupa um retângulo da grelha (x, y, largura, altura; y conta de
cima). Um painel sem retângulo não aparece.

O editor (Definições → Sessões → Ecrã da sessão → Disposição) arrasta e
redimensiona os painéis; as sessões leem daqui. Cada desporto guarda no seu
valor das definições (`screen_layout_<desporto>`). Sem nada guardado, cada
sessão usa a disposição de origem.
"""
from __future__ import annotations

from .i18n import tr

COLS, ROWS = 24, 16
SPORTS = ("cycling", "rowing", "running", "swimming", "gym")

Rect = tuple[int, int, int, int]

# painel: (nome PT, nome EN, descrição PT, descrição EN, retângulo de origem ou None,
#          tamanho mínimo (largura, altura))
PANELS: dict[str, dict[str, tuple]] = {
    "cycling": {
        "boxes": ("Caixas de métricas", "Metric boxes", "as 6 caixas (métricas à escolha)",
                  "the 6 boxes (metrics of your choice)", (0, 0, 24, 5), (12, 3)),
        "gauges": ("Zonas de potência e FC", "Power and HR zones", "a zona atual de cada uma",
                   "the current zone of each", (0, 5, 6, 3), (4, 2)),
        "plan": ("Plano do treino", "Workout plan", "o bloco atual e os seguintes",
                 "the current block and the next ones", (0, 8, 6, 5), (4, 3)),
        "board": ("Classificação", "Leaderboard", "subidas, fantasmas, desafios",
                  "climbs, ghosts, challenges", (18, 5, 6, 4), (4, 3)),
        "laps": ("Voltas", "Laps", "a volta atual e as anteriores", "the current and past laps",
                 (18, 9, 6, 4), (4, 3)),
        "tiz": ("Tempo em cada zona", "Time in each zone", "barras de potência e de FC",
                "power and HR bars", (0, 13, 6, 2), (3, 1)),
        "profile": ("Perfil dos próximos 2 km", "Next 2 km profile", "o declive que vem aí",
                    "the gradient coming up", (6, 13, 12, 2), (6, 1)),
        "strip": ("Rota completa", "Whole route", "onde estás na rota", "where you are",
                  (0, 15, 24, 1), (8, 1)),
    },
    "rowing": {
        "metrics": ("Quadrados de métricas", "Metric tiles", "12 campos por página (V muda)",
                    "12 fields per page (V switches)", (0, 0, 17, 10), (8, 4)),
        "status": ("Estado e plano", "Status and plan", "o passo, o alvo e o que vem a seguir",
                   "the step, the target and what comes next", (0, 10, 17, 6), (6, 2)),
        "laps": ("Voltas", "Laps", "a volta atual e as anteriores", "the current and past laps",
                 (17, 0, 7, 10), (4, 3)),
        "board": ("Classificação", "Leaderboard", "nos jogos e na Regata",
                  "in the games and the Regatta", (17, 10, 7, 6), (4, 3)),
        "chart": ("Gráfico ao vivo", "Live chart", "ritmo e potência ao longo da sessão",
                  "pace and power through the session", None, (6, 3)),
        "zones": ("Tempo em cada zona de FC", "Time in each HR zone", "uma barra por zona",
                  "one bar per zone", None, (4, 2)),
    },
    "running": {
        "metrics": ("Quadrados de métricas", "Metric tiles", "8 campos à escolha",
                    "8 fields of your choice", (0, 0, 17, 8), (8, 3)),
        "status": ("Estado e plano", "Status and plan", "o passo, o alvo e a rota",
                   "the step, the target and the route", (0, 8, 17, 8), (6, 2)),
        "laps": ("Voltas", "Laps", "a volta atual e as anteriores", "the current and past laps",
                 (17, 0, 7, 16), (4, 3)),
        "chart": ("Gráfico ao vivo", "Live chart", "FC e ritmo ao longo da sessão",
                  "HR and pace through the session", None, (6, 3)),
        "zones": ("Tempo em cada zona de FC", "Time in each HR zone", "uma barra por zona",
                  "one bar per zone", None, (4, 2)),
    },
}
PANELS["swimming"] = dict(PANELS["running"])
PANELS["gym"] = {
    "status": ("Estado da série", "Set status", "a fase, o alvo e o tempo da série ou do descanso",
               "the phase, the target and the set or rest time", (0, 0, 24, 2), (8, 2)),
    "metrics": ("Quadrados de métricas", "Metric tiles", "as métricas à escolha e as zonas de FC",
                "the metrics of your choice and the HR zones", (0, 2, 24, 3), (8, 2)),
    "sets": ("Séries do exercício", "Exercise sets", "as séries feitas e o que vem a seguir",
             "the sets done and what comes next", (0, 5, 24, 2), (8, 2)),
    "list": ("O treino em lista", "The workout list", "os exercícios, os descansos e os campos "
             "da série", "the exercises, the rests and the set fields", (0, 7, 24, 9), (8, 4)),
}


def catalog(sport: str) -> list[tuple[str, str, str]]:
    """[(id, nome, descrição)] dos painéis que o desporto conhece."""
    return [(k, tr(v[0], v[1]), tr(v[2], v[3])) for k, v in PANELS.get(sport, {}).items()]


def name(sport: str, panel: str) -> str:
    v = PANELS[sport][panel]
    return tr(v[0], v[1])


def min_size(sport: str, panel: str) -> tuple[int, int]:
    return tuple(PANELS[sport][panel][5])


def defaults(sport: str) -> dict[str, Rect | None]:
    return {k: (tuple(v[4]) if v[4] else None) for k, v in PANELS.get(sport, {}).items()}


def _clean(sport: str, raw) -> dict[str, Rect | None]:
    out = defaults(sport)
    if not isinstance(raw, dict):
        return out
    for k in out:
        if k not in raw:
            continue
        v = raw[k]
        if v is None:
            out[k] = None
            continue
        try:
            x, y, w, h = (int(round(float(n))) for n in v)
        except (TypeError, ValueError):
            continue
        mw, mh = min_size(sport, k)
        w, h = max(mw, min(COLS, w)), max(mh, min(ROWS, h))
        x, y = max(0, min(COLS - w, x)), max(0, min(ROWS - h, y))
        out[k] = (x, y, w, h)
    return out


def load(db, sport: str) -> dict[str, Rect | None]:
    return _clean(sport, db.get(f"screen_layout_{sport}"))


def is_custom(db, sport: str) -> bool:
    return isinstance(db.get(f"screen_layout_{sport}"), dict)


def save(db, sport: str, panels: dict[str, Rect | None]) -> None:
    clean = _clean(sport, {k: (list(v) if v else None) for k, v in panels.items()})
    if clean == defaults(sport):
        db.set(f"screen_layout_{sport}", None)        # igual à origem: não guarda nada
        return
    db.set(f"screen_layout_{sport}", {k: (list(v) if v else None) for k, v in clean.items()})


def reset(db, sport: str) -> None:
    db.set(f"screen_layout_{sport}", None)


def overlaps(a: Rect, b: Rect) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def fits(panels: dict[str, Rect | None], panel: str, rect: Rect) -> bool:
    """O retângulo cabe na grelha e não pisa outro painel?"""
    x, y, w, h = rect
    if x < 0 or y < 0 or x + w > COLS or y + h > ROWS or w < 1 or h < 1:
        return False
    return not any(overlaps(rect, r) for k, r in panels.items() if k != panel and r)


def free_spot(panels: dict[str, Rect | None], w: int, h: int,
              skip: str | None = None) -> Rect | None:
    """O primeiro lugar livre (de cima para baixo) com este tamanho."""
    for y in range(ROWS - h + 1):
        for x in range(COLS - w + 1):
            r = (x, y, w, h)
            if fits({k: v for k, v in panels.items() if k != skip}, "", r):
                return r
    return None


def to_px(rect: Rect, area: tuple[float, float, float, float],
          gap: float = 8.0) -> tuple[float, float, float, float]:
    """Grelha → píxeis. `area` é (x, y_baixo, largura, altura) do ecrã útil;
    devolve (x, y_baixo, largura, altura) do painel, com um intervalo `gap`."""
    ax, ay, aw, ah = area
    gx, gy, gw, gh = rect
    cw, ch = aw / COLS, ah / ROWS
    x = ax + gx * cw
    top = ay + ah - gy * ch
    w, h = gw * cw, gh * ch
    return x + gap / 2, top - h + gap / 2, max(1.0, w - gap), max(1.0, h - gap)
