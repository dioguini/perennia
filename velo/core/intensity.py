"""Intensidade de um bloco de treino, vista de várias maneiras.

Um bloco guarda a intensidade numa escala única: % do limiar (100 % = a
FTP no ciclismo e no remo, o ritmo de limiar na corrida, o ritmo crítico na
natação). O construtor mostra o mesmo treino em zonas de potência, em FC
(% da LTHR), em RPE (1–10) ou em ritmo — muda-se a vista e o treino é o
mesmo, só a escala muda.
"""
from __future__ import annotations

from dataclasses import dataclass

from .i18n import tr

MODES = ("power", "hr", "rpe", "pace")
SPORT_MODES = {"cycling": ("power", "hr", "rpe"), "rowing": ("power", "pace", "hr", "rpe"),
               "running": ("pace", "hr", "rpe"), "swimming": ("pace", "hr", "rpe")}

ZONE_BOUNDS = (55, 75, 90, 105, 120, 150)          # % do limiar (Coggan)
# Cores das zonas como no intervals.icu: verde-água, verde, amarelo, laranja,
# vermelho, roxo.
ZONE_COLORS = ((79, 180, 172), (86, 170, 92), (228, 190, 44), (240, 134, 44),
               (224, 64, 58), (170, 72, 170), (120, 62, 150))
ZONE_NAMES = (("Recuperação", "Recovery"), ("Resistência", "Endurance"), ("Tempo", "Tempo"),
              ("Limiar", "Threshold"), ("VO2máx", "VO2max"), ("Anaeróbio", "Anaerobic"),
              ("Neuromuscular", "Neuromuscular"))
# Pontos (% do limiar → % da LTHR) e (% → RPE), por interpolação.
HR_POINTS = ((40, 55), (55, 68), (75, 83), (90, 94), (105, 100), (120, 104), (150, 106),
             (200, 108))
RPE_POINTS = ((40, 1.0), (50, 2.0), (60, 3.0), (70, 4.0), (80, 5.0), (88, 6.0), (95, 7.0),
              (103, 8.0), (112, 9.0), (130, 10.0), (200, 10.0))


def mode_name(mode: str) -> str:
    return {"power": tr("Zonas de potência", "Power zones"), "hr": tr("FC", "Heart rate"),
            "rpe": "RPE", "pace": tr("Ritmo", "Pace")}[mode]


def zone(pct: float) -> int:
    z = 1
    for b in ZONE_BOUNDS:
        if pct > b:
            z += 1
    return z


def zone_color(pct: float) -> tuple:
    return ZONE_COLORS[min(len(ZONE_COLORS), zone(pct)) - 1]


def zone_name(z: int) -> str:
    return tr(*ZONE_NAMES[max(1, min(len(ZONE_NAMES), z)) - 1])


def _interp(points, x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def _inverse(points, y: float) -> float:
    return _interp([(b, a) for a, b in points], y)


@dataclass
class Context:
    """O atleta: os limiares que transformam % em watts, bpm, RPE e ritmo."""
    sport: str = "cycling"
    ftp_w: int = 250
    lthr: int | None = 165
    run_pace_s: float = 300.0          # s/km no limiar
    swim_css_s: float = 120.0          # s/100 m
    row_ftp_w: int = 200

    @classmethod
    def from_db(cls, db, sport: str) -> "Context":
        ath = db.athlete()
        from .ride import estimate_lthr
        try:
            from .rowing import row_ftp
            rftp = row_ftp(db)
        except Exception:
            rftp = int(ath.ftp_w * 0.8)
        return cls(sport, ath.ftp_w, estimate_lthr(ath),
                   float(db.get("run_threshold_pace_s", 300)), float(db.get("swim_css_s", 120)),
                   rftp)

    # ---- conversões
    def watts(self, pct: float) -> int:
        return int(round((self.row_ftp_w if self.sport == "rowing" else self.ftp_w) * pct / 100))

    def hr(self, pct: float) -> int | None:
        if not self.lthr:
            return None
        return int(round(self.lthr * _interp(HR_POINTS, pct) / 100))

    def rpe(self, pct: float) -> float:
        return round(_interp(RPE_POINTS, pct) * 2) / 2

    def pace(self, pct: float) -> float | None:
        """s/km (corrida), s/100 m (natação) ou s/500 m (remo)."""
        if pct <= 0:
            return None
        if self.sport == "running":
            return self.run_pace_s / (pct / 100)
        if self.sport == "swimming":
            return self.swim_css_s / (pct / 100)
        if self.sport == "rowing":
            from velo.io.rower import pace_from_watts
            return pace_from_watts(self.watts(pct))
        return None

    def speed_mps(self, pct: float) -> float:
        """Velocidade aproximada (para estimar o tempo de um bloco por distância)."""
        p = self.pace(pct)
        unit = {"running": 1000.0, "swimming": 100.0, "rowing": 500.0}.get(self.sport)
        if p and unit:
            return unit / p
        return 8.0 * (max(30.0, pct) / 100) ** 0.5     # ciclismo: só para não dar zero

    def pct_from(self, mode: str, value: float) -> float:
        if mode == "power":
            return value                                      # já é % da FTP
        if mode == "hr":
            return _inverse(HR_POINTS, value / max(1, self.lthr or 165) * 100)
        if mode == "rpe":
            return _inverse(RPE_POINTS, value)
        if mode == "pace":
            if self.sport == "running":
                return self.run_pace_s / value * 100
            if self.sport == "swimming":
                return self.swim_css_s / value * 100
            if self.sport == "rowing":
                from velo.io.rower import watts_from_pace
                return (watts_from_pace(value) or 0) / max(1, self.row_ftp_w) * 100
        return value

    def text(self, mode: str, pct: float) -> str:
        from .units import hms
        if mode == "power":
            return f"{pct:.0f} % · {self.watts(pct)} W"
        if mode == "hr":
            hr = self.hr(pct)
            return f"{_interp(HR_POINTS, pct):.0f} % LTHR" + (f" · {hr} bpm" if hr else "")
        if mode == "rpe":
            return f"RPE {self.rpe(pct):g}"
        if mode == "pace":
            p = self.pace(pct)
            unit = {"running": "/km", "swimming": "/100 m", "rowing": "/500 m"}.get(
                self.sport, "")
            return (hms(p) if p else "—") + f" {unit}"
        return f"{pct:.0f} %"

    def short(self, mode: str, pct: float) -> str:
        from .units import hms
        if mode == "power":
            return f"{self.watts(pct)} W"
        if mode == "hr":
            hr = self.hr(pct)
            return f"{hr} bpm" if hr else f"{_interp(HR_POINTS, pct):.0f}%"
        if mode == "rpe":
            return f"{self.rpe(pct):g}"
        p = self.pace(pct)
        return hms(p) if p else "—"
