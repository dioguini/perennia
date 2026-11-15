"""As cores da barra do bloco: quando falta pouco para o fim do bloco, a barra passa a
**amarelo**, depois a **vermelho** e, nos últimos momentos, a **preto**.

Vale igual no ciclismo, no remo, na corrida/natação e — no ginásio — nos exercícios e blocos
medidos em *tempo* (os de repetições não têm barra de tempo). Os três limiares são opções
(Definições → Avançado → Aspeto…): `block_bar_yellow_pct`, `block_bar_red_pct` e
`block_bar_black_pct`, em % do bloco que **falta**; `block_bar_colors` liga e desliga tudo.

Este módulo só decide a cor; desenhar a barra é com cada ecrã (`ui/widgets.BlockBar`).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import options

NORMAL, YELLOW, RED, BLACK = "normal", "yellow", "red", "black"
STAGES = (NORMAL, YELLOW, RED, BLACK)

# as cores de aviso (a normal é a da barra de cada ecrã)
COLORS = {YELLOW: (242, 196, 28), RED: (214, 48, 49), BLACK: (8, 8, 8)}


@dataclass(frozen=True)
class Config:
    enabled: bool = True
    yellow: float = 0.25          # frações do bloco que faltam
    red: float = 0.10
    black: float = 0.03

    @classmethod
    def from_db(cls, db) -> "Config":
        y = int(options.get(db, "block_bar_yellow_pct"))
        r = int(options.get(db, "block_bar_red_pct"))
        k = int(options.get(db, "block_bar_black_pct"))
        return cls.make(bool(options.get(db, "block_bar_colors")), y, r, k)

    @classmethod
    def make(cls, enabled: bool, yellow_pct: float, red_pct: float, black_pct: float
             ) -> "Config":
        """Os limiares em %, arrumados para ficarem sempre em ordem (amarelo > vermelho >
        preto): se alguém pôs o vermelho acima do amarelo, o vermelho desce."""
        yellow = max(0.0, float(yellow_pct))
        red = min(max(0.0, float(red_pct)), yellow)
        black = min(max(0.0, float(black_pct)), red)
        return cls(bool(enabled), yellow / 100.0, red / 100.0, black / 100.0)


def stage(remaining: float, cfg: Config) -> str:
    """A fase da barra para a fração do bloco que falta (1 = acabou de começar, 0 = acabou).
    `NORMAL` se as cores estão desligadas ou o bloco ainda vai longe."""
    if not cfg.enabled:
        return NORMAL
    r = max(0.0, min(1.0, remaining))
    if cfg.black > 0 and r <= cfg.black:
        return BLACK
    if r <= cfg.red:
        return RED
    if r <= cfg.yellow:
        return YELLOW
    return NORMAL


def color(st: str, normal: tuple) -> tuple:
    """A cor da barra nesta fase (`normal` é a de origem do ecrã)."""
    return COLORS.get(st, tuple(normal[:3]))[:3]
