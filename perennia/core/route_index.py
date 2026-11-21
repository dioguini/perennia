"""Índice da rota: consultas rápidas de elevação, declive e perfil (req. 9, 25).

Os pontos vêm reamostrados a passo constante, por isso localizar uma
distância é uma divisão, não uma busca. É o que permite calcular os declives
médios de 500 m a 10 km a cada frame sem custo.
"""
from __future__ import annotations

from .db import RoutePoint


class RouteIndex:
    def __init__(self, points: list[RoutePoint]):
        if not points:
            raise ValueError("rota sem pontos")
        self.points = points
        self.total_m = points[-1].dist_m
        self.step_m = points[1].dist_m - points[0].dist_m if len(points) > 1 else 1.0

    # --------------------------------------------------------- localização

    def _frac_index(self, dist_m: float) -> tuple[int, float]:
        """Devolve (índice inferior, fração até ao próximo)."""
        d = min(max(dist_m, 0.0), self.total_m)
        raw = d / self.step_m
        i = int(raw)
        if i >= len(self.points) - 1:
            return len(self.points) - 1, 0.0
        return i, raw - i

    def point_at(self, dist_m: float) -> RoutePoint:
        i, f = self._frac_index(dist_m)
        if f == 0.0 or i >= len(self.points) - 1:
            return self.points[i]
        a, b = self.points[i], self.points[i + 1]
        return RoutePoint(
            dist_m=dist_m,
            lat=a.lat + f * (b.lat - a.lat),
            lon=a.lon + f * (b.lon - a.lon),
            x_m=a.x_m + f * (b.x_m - a.x_m),
            y_m=a.y_m + f * (b.y_m - a.y_m),
            ele_m=a.ele_m + f * (b.ele_m - a.ele_m),
            grade_pct=a.grade_pct + f * (b.grade_pct - a.grade_pct),
            heading_deg=a.heading_deg,
        )

    def ele_at(self, dist_m: float) -> float:
        i, f = self._frac_index(dist_m)
        if f == 0.0 or i >= len(self.points) - 1:
            return self.points[i].ele_m
        return self.points[i].ele_m + f * (self.points[i + 1].ele_m - self.points[i].ele_m)

    def grade_at(self, dist_m: float) -> float:
        i, _ = self._frac_index(dist_m)
        return self.points[i].grade_pct

    def heading_at(self, dist_m: float) -> float:
        i, _ = self._frac_index(dist_m)
        return self.points[i].heading_deg

    # ------------------------------------------------------------ declives

    def avg_grade_ahead(self, from_m: float, ahead_m: float) -> float | None:
        """Declive médio nos próximos `ahead_m`.

        Devolve None quando a rota acaba antes: mostrar o declive dos
        próximos 10 km quando só faltam 2 seria enganador.
        """
        to = from_m + ahead_m
        if to > self.total_m or ahead_m <= 0:
            return None
        return (self.ele_at(to) - self.ele_at(from_m)) / ahead_m * 100.0

    def ascent_between(self, a_m: float, b_m: float) -> float:
        """Subida acumulada no intervalo, somando só os trechos positivos."""
        i0, _ = self._frac_index(min(a_m, b_m))
        i1, _ = self._frac_index(max(a_m, b_m))
        gain = 0.0
        for i in range(i0, min(i1, len(self.points) - 1)):
            d = self.points[i + 1].ele_m - self.points[i].ele_m
            if d > 0:
                gain += d
        return gain

    # -------------------------------------------------------------- perfil

    def profile(self, from_m: float, window_m: float, n: int = 64) -> list[tuple[float, float]]:
        """`n` pares (distância, elevação) para desenhar o perfil que vem (req. 25)."""
        n = max(2, n)
        out = []
        for k in range(n):
            d = from_m + window_m * k / (n - 1)
            # a rota dá a volta: para lá do fim mostra-se o início outra vez
            out.append((d, self.ele_at(d % self.total_m if self.total_m > 0 else d)))
        return out

    def profile_normalized(self, from_m: float, window_m: float, n: int = 64,
                           min_span_m: float = 30.0
                           ) -> tuple[list[tuple[float, float]], float, float]:
        """Perfil com y em 0..1 e os extremos reais, para desenhar sem escalar à mão.

        A escala vertical nunca é menor do que `min_span_m`: sem isto, num
        troço plano, um metro de ruído do GPS ocupava a altura toda e o
        perfil parecia uma serra. Num troço plano, a linha fica baixa e
        direita.
        """
        pts = self.profile(from_m, window_m, n)
        eles = [e for _, e in pts]
        lo, hi = min(eles), max(eles)
        span = hi - lo
        base = lo
        if span < min_span_m:
            base = lo - (min_span_m - span) * 0.25     # fica no quarto de baixo
            span = min_span_m
        return ([((d - from_m) / window_m, (e - base) / span) for d, e in pts], lo, hi)
