"""Os desportos da Perennia: um registo único.

Cinco desportos — ciclismo, remo, corrida, natação e ginásio. O ginásio
divide-se em modalidades (velo.core.gym). Cada desporto diz o seu nome, o
ícone, como se mede a distância e o que o `.fit` leva.
"""
from __future__ import annotations

from dataclasses import dataclass

from .i18n import tr


@dataclass(frozen=True)
class Sport:
    key: str
    pt: str
    en: str
    icon: str
    fit_sport: int
    fit_sub: int
    distance: bool = True           # mede distância
    lap_units: tuple = ("time", "distance")   # auto lap possível por…

    @property
    def name(self) -> str:
        return tr(self.pt, self.en)


SPORTS: dict[str, Sport] = {}


def register(s: Sport) -> Sport:
    SPORTS[s.key] = s
    return s


register(Sport("cycling", "Ciclismo", "Cycling", "bike", 2, 6))
register(Sport("rowing", "Remo", "Rowing", "rower", 15, 14))
register(Sport("running", "Corrida", "Running", "runner", 1, 1))
register(Sport("swimming", "Natação", "Swimming", "swimmer", 5, 17))
register(Sport("gym", "Ginásio", "Gym", "kettlebell", 10, 20, distance=False,
               lap_units=("time",)))

ORDER = ("cycling", "rowing", "running", "swimming", "gym")


def name(key: str) -> str:
    s = SPORTS.get(key)
    return s.name if s else key


def all_sports() -> list[Sport]:
    return [SPORTS[k] for k in ORDER if k in SPORTS] + [
        s for k, s in SPORTS.items() if k not in ORDER]


# --------------------------------------------------------------- auto lap


def autolap_text(cfg: dict | None, units: str = "metric") -> str:
    """«desligado», «a cada 5:00» ou «a cada 1 km»."""
    from .units import hms
    if not cfg or cfg.get("mode", "off") == "off":
        return tr("desligado", "off")
    v = float(cfg.get("value") or 0)
    if cfg["mode"] == "time":
        return tr("a cada {t}", "every {t}", t=hms(v))
    return tr("a cada {d}", "every {d}", d=f"{v / 1000:g} km" if v >= 1000 else f"{v:.0f} m")


AUTOLAP_TIMES = (60, 120, 180, 300, 600, 900, 1200, 1800)
AUTOLAP_DISTANCES = {
    "cycling": (1000, 2000, 5000, 10000),
    "rowing": (250, 500, 1000, 2000),
    "running": (400, 1000, 1609, 5000),
    "swimming": (50, 100, 200, 400),
}


class AutoLap:
    """Marca voltas sozinha, por tempo ou por distância. Desligado por omissão."""

    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.mode = cfg.get("mode", "off")
        self.value = float(cfg.get("value") or 0)
        self._next = self.value

    @property
    def on(self) -> bool:
        return self.mode in ("time", "distance") and self.value > 0

    def due(self, t_s: float, dist_m: float) -> bool:
        if not self.on:
            return False
        x = t_s if self.mode == "time" else dist_m
        if x >= self._next:
            while self._next <= x:
                self._next += self.value
            return True
        return False

    def as_dict(self) -> dict:
        return {"mode": self.mode, "value": self.value}

    def restore(self, t_s: float, dist_m: float) -> None:
        if self.on:
            x = t_s if self.mode == "time" else dist_m
            self._next = (int(x // self.value) + 1) * self.value
