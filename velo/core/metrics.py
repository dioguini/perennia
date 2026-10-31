"""Registo de métricas extensível (req. 9).

Acrescentar uma métrica nova é escrever uma função com o decorador. Não é
preciso tocar no HUD, na base de dados ou no motor da sessão — o HUD pede
métricas por `id` e recebe valor, rótulo e unidade.

    @metric("vam", "m", "metric.vam")
    def _vam(s): return s.vam_mh
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import physics
from .i18n import t
from .units import format_metric


@dataclass(frozen=True)
class MetricDef:
    id: str
    unit: str
    label_key: str
    fn: Callable[[object], float | None]

    @property
    def label(self) -> str:
        return t(self.label_key)


REGISTRY: dict[str, MetricDef] = {}
ORDER: list[str] = []


def metric(mid: str, unit: str, label_key: str | None = None):
    def deco(fn: Callable[[object], float | None]) -> Callable[[object], float | None]:
        REGISTRY[mid] = MetricDef(mid, unit, label_key or f"metric.{mid}", fn)
        ORDER.append(mid)
        return fn
    return deco


def value(mid: str, state: object) -> float | None:
    m = REGISTRY.get(mid)
    if m is None:
        return None
    try:
        return m.fn(state)
    except Exception:
        return None


def formatted(mid: str, state: object, system: str = "metric") -> tuple[str, str]:
    """Devolve (rótulo, texto do valor) já traduzido e convertido."""
    m = REGISTRY.get(mid)
    if m is None:
        return (mid, "—")
    return (m.label, format_metric(value(mid, state), m.unit, system))


def available() -> list[str]:
    return list(ORDER)


# ------------------------------------------------------------------ distância

@metric("dist_done", "km")
def _dist_done(s):
    return s.dist_m


@metric("dist_left", "km")
def _dist_left(s):
    return None if s.route is None else max(0.0, s.route.total_m - s.pos_m)


@metric("ascent", "m")
def _ascent(s):
    return s.ascent_m


# ------------------------------------------------------------------- declives

@metric("grade_now", "%")
def _grade_now(s):
    return s.grade_pct


@metric("avg_grade_500m", "%")
def _g500(s):
    return None if s.route is None else s.route.avg_grade_ahead(s.pos_m, 500.0)


@metric("avg_grade_1km", "%")
def _g1k(s):
    return None if s.route is None else s.route.avg_grade_ahead(s.pos_m, 1_000.0)


@metric("avg_grade_3km", "%")
def _g3k(s):
    return None if s.route is None else s.route.avg_grade_ahead(s.pos_m, 3_000.0)


@metric("avg_grade_5km", "%")
def _g5k(s):
    return None if s.route is None else s.route.avg_grade_ahead(s.pos_m, 5_000.0)


@metric("avg_grade_10km", "%")
def _g10k(s):
    return None if s.route is None else s.route.avg_grade_ahead(s.pos_m, 10_000.0)


# ------------------------------------------------------------------ potência

@metric("power", "W")
def _power(s):
    return s.power_w


@metric("power_3s", "W")
def _power3(s):
    return s.power_3s


@metric("avg_power", "W", "metric.power")
def _avg_power(s):
    return s.avg_power


@metric("np", "W")
def _np(s):
    return s.np_w


@metric("power_balance", "balance")
def _balance(s):
    # média de 3 s: o valor de cada pedalada salta de um lado para o outro
    smooth = getattr(s, "balance_3s", None)
    return smooth if smooth is not None else s.balance_left


def _pair(d: dict | None, a: str, b: str, c: str | None = None):
    if not d:
        return None
    vals = (d.get(a), d.get(b), d.get(c) if c else None)
    return None if all(v is None for v in vals) else vals


@metric("torque_eff", "pair_pct")
def _torque_eff(s):
    return _pair(getattr(s, "pedal", None), "te_left", "te_right")


@metric("pedal_smooth", "pair_pct")
def _pedal_smooth(s):
    return _pair(getattr(s, "pedal", None), "ps_left", "ps_right", "ps_combined")


@metric("avg_torque_eff", "pair_pct")
def _avg_torque_eff(s):
    return _pair(getattr(s, "avg_pedal", None), "te_left", "te_right")


@metric("avg_pedal_smooth", "pair_pct")
def _avg_pedal_smooth(s):
    return _pair(getattr(s, "avg_pedal", None), "ps_left", "ps_right", "ps_combined")


@metric("avg_balance", "balance")
def _avg_balance(s):
    return getattr(s, "avg_balance", None)


@metric("power_zone", "pzone")
def _pzone(s):
    p = s.power_3s if s.power_3s is not None else s.power_w
    if p is None:
        return None
    return physics.zone_of(p, s.power_zone_bounds, s.ftp_w)


@metric("avg_power_zone", "pzone")
def _avg_pzone(s):
    if s.avg_power is None:
        return None
    return physics.zone_of(s.avg_power, s.power_zone_bounds, s.ftp_w)


@metric("wkg", "wkg")
def _wkg(s):
    """Potência por quilo (média de 3 s), com o peso do atleta, sem a bicicleta."""
    p = s.power_3s if s.power_3s is not None else s.power_w
    w = getattr(s, "weight_kg", None)
    return p / w if p is not None and w else None


@metric("avg_wkg", "wkg")
def _avg_wkg(s):
    w = getattr(s, "weight_kg", None)
    return s.avg_power / w if s.avg_power is not None and w else None


@metric("power_zone_range", "text")
def _pzone_range(s):
    """Intervalo da zona atual em W e W/kg: «188–225 W · 2,6–3,1 W/kg»."""
    from . import zones
    p = s.power_3s if s.power_3s is not None else s.power_w
    if p is None or not s.ftp_w:
        return None
    zs = zones.power_zones(s.ftp_w, getattr(s, "weight_kg", None), s.power_zone_bounds)
    return zones.zone_for(p, zs).range_text()


@metric("hr_zone_range", "text")
def _hzone_range(s):
    from . import zones
    if s.hr_bpm is None or not s.lthr:
        return None
    zs = zones.hr_zones(s.lthr, s.hr_zone_bounds)
    return zones.zone_for(s.hr_bpm, zs).range_text()


@metric("power_lr", "pair_w")
def _power_lr(s):
    """Watts de cada perna, a partir da potência e do balanço (média de 3 s)."""
    p = s.power_3s if s.power_3s is not None else s.power_w
    bal = getattr(s, "balance_3s", None)
    if bal is None:
        bal = s.balance_left
    if p is None or bal is None:
        return None
    return (p * bal / 100.0, p * (100.0 - bal) / 100.0)


@metric("torque", "Nm")
def _torque(s):
    return physics.torque_nm(s.power_w, s.cadence_rpm)


@metric("avg_torque", "Nm")
def _avg_torque(s):
    return getattr(s, "avg_torque", None)


@metric("work_kj", "kJ")
def _work(s):
    return s.joules / 1000.0


@metric("tss_accum", "TSS")
def _tss(s):
    return s.tss


# ------------------------------------------------------- frequência cardíaca

@metric("hr", "bpm")
def _hr(s):
    return s.hr_bpm


@metric("avg_hr", "bpm")
def _avg_hr(s):
    return s.avg_hr


@metric("hr_zone", "hzone")
def _hrzone(s):
    if s.hr_bpm is None or not s.lthr:
        return None
    return physics.zone_of(s.hr_bpm, s.hr_zone_bounds, s.lthr)


@metric("avg_hr_zone", "hzone")
def _avg_hrzone(s):
    if s.avg_hr is None or not s.lthr:
        return None
    return physics.zone_of(s.avg_hr, s.hr_zone_bounds, s.lthr)


# ------------------------------------------------------- cadência e velocidade

@metric("cadence", "rpm")
def _cadence(s):
    return s.cadence_rpm


@metric("avg_cadence", "rpm")
def _avg_cadence(s):
    return s.avg_cadence


@metric("speed", "mps")
def _speed(s):
    return s.speed_mps


@metric("avg_speed", "mps")
def _avg_speed(s):
    return s.avg_speed


# ------------------------------------------------------------------- tempo

@metric("elapsed", "s")
def _elapsed(s):
    return s.t_s


@metric("eta", "s")
def _eta(s):
    """Tempo estimado até ao fim, à velocidade média dos últimos minutos."""
    if s.route is None or s.avg_speed in (None, 0):
        return None
    left = max(0.0, s.route.total_m - s.pos_m)
    return left / max(s.avg_speed, 0.5)


@metric("loops", "count")
def _loops(s):
    return s.loops


@metric("target_power", "W")
def _target(s):
    return s.target_power_w
