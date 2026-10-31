"""Curvas suaves para os gráficos, sem dependências.

A curva de potência tem poucos pontos (1 s, 5 s, … 60 min) e as durações
crescem de forma exponencial. Desenhá-la com segmentos retos, igualmente
espaçados, dá um traço aos solavancos e com o eixo do tempo deformado. Aqui
os pontos espalham-se em escala logarítmica e ligam-se com uma
interpolação cúbica monótona (Fritsch–Carlson): passa exatamente pelos
pontos medidos e nunca inventa picos ou vales entre eles.
"""
from __future__ import annotations

import math
from typing import Sequence


def monotone_cubic(xs: Sequence[float], ys: Sequence[float],
                   n: int) -> tuple[list[float], list[float]]:
    """`n` pontos igualmente espaçados em x, sobre a curva que passa por (xs, ys)."""
    pts = sorted(zip(xs, ys))
    if len(pts) < 2 or n < 2:
        return [p[0] for p in pts], [p[1] for p in pts]
    x = [p[0] for p in pts]
    y = [p[1] for p in pts]
    k = len(x)
    h = [x[i + 1] - x[i] for i in range(k - 1)]
    delta = [(y[i + 1] - y[i]) / h[i] if h[i] else 0.0 for i in range(k - 1)]
    m = [0.0] * k
    m[0], m[-1] = delta[0], delta[-1]
    for i in range(1, k - 1):
        if delta[i - 1] * delta[i] <= 0:
            m[i] = 0.0
        else:
            # média harmónica ponderada: o que garante a monotonia
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    out_x, out_y = [], []
    j = 0
    for s in range(n):
        xv = x[0] + (x[-1] - x[0]) * s / (n - 1)
        while j < k - 2 and xv > x[j + 1]:
            j += 1
        hh = h[j] or 1.0
        t = (xv - x[j]) / hh
        t2, t3 = t * t, t * t * t
        yv = ((2 * t3 - 3 * t2 + 1) * y[j] + (t3 - 2 * t2 + t) * hh * m[j]
              + (-2 * t3 + 3 * t2) * y[j + 1] + (t3 - t2) * hh * m[j + 1])
        out_x.append(xv)
        out_y.append(yv)
    return out_x, out_y


def log_positions(xs: Sequence[float]) -> list[float]:
    """Posição de cada x entre 0 e 1 numa escala logarítmica."""
    logs = [math.log(max(v, 1e-9)) for v in xs]
    lo, hi = min(logs), max(logs)
    span = (hi - lo) or 1.0
    return [(v - lo) / span for v in logs]
