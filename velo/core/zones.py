"""Zonas de potência e de FC, com os intervalos em W, W/kg e bpm.

As zonas de potência são as de Coggan, em % da FTP. Cada uma tem o seu
intervalo em watts e em W/kg (com o peso do atleta). A barra do HUD
(`gauge`) vai de 0 até um pouco acima do início da última zona, que não
tem teto, e diz onde cai o valor atual: em que zona está e quanto da zona
já preencheu.
"""
from __future__ import annotations

from dataclasses import dataclass

from .i18n import t

POWER_BOUNDS = [55, 75, 90, 105, 120, 150]          # % FTP → 7 zonas
HR_BOUNDS = [68, 83, 94, 105]                       # % LTHR → 5 zonas
TOP_HEADROOM = 1.2                                  # a última zona desenha-se até ×1,2


@dataclass(frozen=True)
class Zone:
    n: int                     # 1-based
    lo: float                  # unidade da referência: W ou bpm
    hi: float | None           # None: sem teto (última zona)
    kind: str                  # "power" | "hr"
    weight_kg: float | None = None

    @property
    def name(self) -> str:
        return t(f"zone.{self.kind}.{self.n}")

    @property
    def lo_wkg(self) -> float | None:
        return self.lo / self.weight_kg if self.weight_kg else None

    @property
    def hi_wkg(self) -> float | None:
        if self.hi is None or not self.weight_kg:
            return None
        return self.hi / self.weight_kg

    def range_text(self) -> str:
        """«188–225 W · 2,6–3,1 W/kg», «> 375 W · > 5,2 W/kg», «138–152 bpm»."""
        unit = "W" if self.kind == "power" else "bpm"
        if self.hi is None:
            main = f"> {self.lo:.0f} {unit}"
        elif self.lo <= 0:
            main = f"< {self.hi:.0f} {unit}"
        else:
            main = f"{self.lo:.0f}–{self.hi:.0f} {unit}"
        if self.kind != "power" or not self.weight_kg:
            return main
        if self.hi is None:
            wkg = f"> {self.lo_wkg:.1f} W/kg"
        elif self.lo <= 0:
            wkg = f"< {self.hi_wkg:.1f} W/kg"
        else:
            wkg = f"{self.lo_wkg:.1f}–{self.hi_wkg:.1f} W/kg"
        return f"{main} · {wkg}"


def build(reference: float, bounds_pct: list[float], kind: str,
          weight_kg: float | None = None) -> list[Zone]:
    edges = [0.0] + [reference * b / 100.0 for b in bounds_pct]
    zones = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        zones.append(Zone(i + 1, lo, hi, kind, weight_kg))
    return zones


def power_zones(ftp_w: float, weight_kg: float | None = None,
                bounds_pct: list[float] | None = None) -> list[Zone]:
    return build(ftp_w, bounds_pct or POWER_BOUNDS, "power", weight_kg)


def hr_zones(lthr: float, bounds_pct: list[float] | None = None) -> list[Zone]:
    return build(lthr, bounds_pct or HR_BOUNDS, "hr")


def zone_for(value: float, zones: list[Zone]) -> Zone:
    for z in zones:
        if z.hi is None or value <= z.hi:
            return z
    return zones[-1]


@dataclass(frozen=True)
class Gauge:
    zone: Zone
    position: float            # 0..1 ao longo da barra inteira
    in_zone: float             # 0..1 dentro da zona atual
    scale_max: float           # valor que corresponde ao fim da barra


def gauge(value: float | None, zones: list[Zone]) -> Gauge | None:
    """Onde cai `value` na barra das zonas. None sem valor."""
    if value is None or not zones:
        return None
    top = zones[-1].lo * TOP_HEADROOM
    z = zone_for(value, zones)
    hi = z.hi if z.hi is not None else top
    span = max(hi - z.lo, 1e-9)
    return Gauge(z, max(0.0, min(1.0, value / top)),
                 max(0.0, min(1.0, (value - z.lo) / span)), top)


def segments(zones: list[Zone]) -> list[tuple[float, float]]:
    """(início, fim) de cada zona em 0..1 ao longo da barra, para a desenhar."""
    top = zones[-1].lo * TOP_HEADROOM
    out = []
    for z in zones:
        hi = z.hi if z.hi is not None else top
        out.append((z.lo / top, min(1.0, hi / top)))
    return out
