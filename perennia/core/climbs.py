"""Deteção automática de subidas significativas (req. 14).

Pedir a um GPX "onde estão as subidas" não tem resposta única. O algoritmo
abre um candidato quando o declive sobe acima de um limiar, tolera patamares
curtos e descidas pequenas no meio (uma subida real raramente é monótona), e
no fim aceita o candidato se for longa e inclinada o suficiente.
"""
from __future__ import annotations

from dataclasses import dataclass

from .db import Climb, RoutePoint

# Limiares de categoria pelo produto comprimento × declive, à maneira do
# ciclismo de estrada. Ajustáveis nas definições.
_CATEGORY_SCORE = [
    (80_000.0, "HC"),
    (64_000.0, "1"),
    (32_000.0, "2"),
    (16_000.0, "3"),
    (8_000.0, "4"),
]


@dataclass
class Thresholds:
    min_length_m: float = 500.0
    min_avg_grade: float = 3.0
    min_gain_m: float = 60.0
    start_grade: float = 2.0
    merge_gap_m: float = 150.0


def categorize(length_m: float, avg_grade: float) -> str:
    score = length_m * avg_grade
    for limit, cat in _CATEGORY_SCORE:
        if score >= limit:
            return cat
        continue
    return "4"


def detect(points: list[RoutePoint], th: Thresholds | None = None,
           name_fmt: str = "Subida {n} ({km:.1f} km @ {grade:.1f} %)") -> list[Climb]:
    """Devolve as subidas encontradas, ordenadas por distância."""
    th = th or Thresholds()
    if len(points) < 3:
        return []

    out: list[Climb] = []
    start: int | None = None

    def ahead_resumes(i: int) -> bool:
        """Volta a subir dentro de merge_gap_m? Então o candidato não fecha."""
        d0 = points[i].dist_m
        for p in points[i:]:
            if p.dist_m - d0 > th.merge_gap_m:
                return False
            if p.grade_pct >= th.start_grade:
                return True
        return False

    def close(a: int, b: int) -> None:
        length = points[b].dist_m - points[a].dist_m
        if length < th.min_length_m:
            return
        gain = points[b].ele_m - points[a].ele_m
        avg = gain / length * 100.0
        if avg < th.min_avg_grade and gain < th.min_gain_m:
            return
        seq = len(out) + 1
        out.append(Climb(
            seq=seq,
            name=name_fmt.format(n=seq, km=length / 1000.0, grade=avg),
            start_m=points[a].dist_m,
            end_m=points[b].dist_m,
            length_m=length,
            gain_m=gain,
            avg_grade_pct=avg,
            max_grade_pct=max(p.grade_pct for p in points[a:b + 1]),
            category=categorize(length, avg),
            score=length * avg,
        ))

    for i, p in enumerate(points):
        climbing = p.grade_pct >= th.start_grade
        if start is None and climbing:
            start = i
        elif start is not None and not climbing and not ahead_resumes(i):
            close(start, i)
            start = None
    if start is not None:
        close(start, len(points) - 1)
    return out


def signs_for(climb: Climb, every_m: float = 500.0) -> list[float]:
    """Distâncias (desde o início da rota) onde colocar placas de "falta X".

    Conta a partir do topo para baixo, para as placas caírem em números
    redondos de distância ao cume, como na estrada.
    """
    marks: list[float] = []
    d = climb.end_m - every_m
    while d > climb.start_m + every_m * 0.5:
        marks.append(d)
        d -= every_m
    return sorted(marks)
