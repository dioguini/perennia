"""Importação de .gpx: parse, projeção local, reamostragem e suavização (req. 2, 4).

A geometria exata da estrada — traçado, curvas, comprimentos, declives — vem
toda daqui. É ela que faz reconhecer a estrada ao pedalar.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

from .db import RoutePoint

RESAMPLE_STEP_M = 5.0
_SMOOTH_WINDOW = 11      # ±5 amostras = ±25 m
_GRADE_WINDOW_M = 25.0   # declive medido em ±25 m, para não apanhar ruído do GPS

# Metros por grau, suficientemente preciso à escala de uma rota.
_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON = 111_320.0


class GpxError(ValueError):
    pass


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_gpx(path: str | Path) -> tuple[str, list[tuple[float, float, float]]]:
    """Devolve (nome, [(lat, lon, elevação)]).

    Aceita trkpt (track) e rtept (route). Pontos sem elevação herdam a do
    anterior — alguns exportadores omitem-na em pontos isolados.
    """
    try:
        tree = ET.parse(str(path))
    except ET.ParseError as e:
        raise GpxError(f"ficheiro .gpx inválido: {e}") from e

    root = tree.getroot()
    name = ""
    raw: list[tuple[float, float, float]] = []
    last_ele = 0.0

    for el in root.iter():
        tag = _strip_ns(el.tag)
        if tag == "name" and not name and (el.text or "").strip():
            name = el.text.strip()
        elif tag in ("trkpt", "rtept"):
            try:
                lat = float(el.attrib["lat"])
                lon = float(el.attrib["lon"])
            except (KeyError, ValueError):
                continue
            ele = last_ele
            for child in el:
                if _strip_ns(child.tag) == "ele" and (child.text or "").strip():
                    try:
                        ele = float(child.text.strip())
                    except ValueError:
                        pass
                    break
            last_ele = ele
            raw.append((lat, lon, ele))

    if len(raw) < 2:
        raise GpxError("o ficheiro não tem pontos de percurso suficientes")
    if not name:
        name = Path(path).stem
    return name, raw


def _project(raw: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Projeta para metros num plano local centrado no primeiro ponto."""
    lat0, lon0, _ = raw[0]
    cos_lat = math.cos(math.radians(lat0))
    return [
        ((lon - lon0) * _M_PER_DEG_LON * cos_lat, (lat - lat0) * _M_PER_DEG_LAT, ele)
        for lat, lon, ele in raw
    ]


def _smooth(values: list[float], window: int) -> list[float]:
    """Média móvel centrada, com a janela encurtada nas extremidades."""
    if window <= 1 or len(values) < 3:
        return list(values)
    half = window // 2
    out = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out


def resample(raw: list[tuple[float, float, float]],
             step_m: float = RESAMPLE_STEP_M) -> list[RoutePoint]:
    """Reamostra a passo constante e devolve pontos com declive e rumo.

    Passo constante simplifica tudo a jusante: o índice de distância fica
    O(1), o render gera troços uniformes e o declive não depende da
    densidade de pontos do ficheiro original.
    """
    xy = _project(raw)

    # Distância cumulativa sobre os pontos originais, descartando duplicados.
    pts: list[tuple[float, float, float, float]] = []  # (dist, x, y, ele)
    total = 0.0
    px, py, pe = xy[0]
    pts.append((0.0, px, py, pe))
    for x, y, ele in xy[1:]:
        d = math.hypot(x - px, y - py)
        if d < 1e-6:
            continue
        total += d
        pts.append((total, x, y, ele))
        px, py, pe = x, y, ele

    if total < step_m * 2:
        raise GpxError("percurso demasiado curto")

    lat0, lon0, _ = raw[0]
    cos_lat = math.cos(math.radians(lat0))

    # Interpolação linear em passos fixos.
    n_steps = int(total // step_m)
    sampled: list[tuple[float, float, float, float]] = []
    j = 0
    for k in range(n_steps + 1):
        d = min(k * step_m, total)
        while j + 1 < len(pts) - 1 and pts[j + 1][0] < d:
            j += 1
        d0, x0, y0, e0 = pts[j]
        d1, x1, y1, e1 = pts[min(j + 1, len(pts) - 1)]
        span = d1 - d0
        f = 0.0 if span <= 1e-9 else (d - d0) / span
        sampled.append((d, x0 + f * (x1 - x0), y0 + f * (y1 - y0), e0 + f * (e1 - e0)))

    # Suaviza a elevação antes de derivar o declive: sem isto o trainer
    # recebe saltos de declive que não existem na estrada.
    eles = _smooth([s[3] for s in sampled], _SMOOTH_WINDOW)

    span = max(1, int(round(_GRADE_WINDOW_M / step_m)))
    out: list[RoutePoint] = []
    for i, (d, x, y, _) in enumerate(sampled):
        lo = max(0, i - span)
        hi = min(len(sampled) - 1, i + span)
        run = sampled[hi][0] - sampled[lo][0]
        grade = ((eles[hi] - eles[lo]) / run * 100.0) if run > 1e-6 else 0.0

        nxt = min(i + 1, len(sampled) - 1)
        prv = max(i - 1, 0)
        dx = sampled[nxt][1] - sampled[prv][1]
        dy = sampled[nxt][2] - sampled[prv][2]
        heading = math.degrees(math.atan2(dx, dy)) % 360.0

        out.append(RoutePoint(
            dist_m=d,
            lat=lat0 + y / _M_PER_DEG_LAT,
            lon=lon0 + x / (_M_PER_DEG_LON * cos_lat) if cos_lat else lon0,
            x_m=x, y_m=y, ele_m=eles[i],
            grade_pct=max(-30.0, min(30.0, grade)),
            heading_deg=heading,
        ))
    return out


def import_gpx(path: str | Path) -> tuple[str, list[RoutePoint]]:
    name, raw = parse_gpx(path)
    return name, resample(raw)
