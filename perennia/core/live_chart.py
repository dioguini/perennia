"""O gráfico ao vivo das sessões (ciclismo, remo, corrida e natação): que métricas mostra.

Cada desporto só oferece as métricas que **ele** tem (um rolo não tem ritmo /500 m, uma
passadeira não tem voga). A escolha fica em `live_chart_<desporto>` (lista de chaves, em ordem);
sem escolha, valem as de origem. O máximo de linhas é a opção `live_chart_max_series`. Como as
métricas têm unidades diferentes (W, bpm, s/500 m…), cada linha é desenhada na **sua** escala
(do mínimo ao máximo que teve na sessão) e a legenda diz o valor de agora.

Editar: Definições → Ecrã da sessão → Gráfico ao vivo. Ler: `choice(db, sport)`; os valores de
cada momento vêm de `sample(sport, engine_or_state)`.
"""
from __future__ import annotations

from . import options
from .i18n import tr

SPORTS = ("cycling", "rowing", "running", "swimming")

# chave: (PT, EN, unidade, cor RGB)
CATALOG: dict[str, dict[str, tuple]] = {
    "cycling": {
        "power": ("Potência", "Power", "W", (108, 170, 220)),
        "power_3s": ("Potência 3 s", "Power 3 s", "W", (70, 130, 190)),
        "hr": ("FC", "HR", "bpm", (214, 54, 128)),
        "cadence": ("Cadência", "Cadence", "rpm", (120, 200, 150)),
        "speed": ("Velocidade", "Speed", "km/h", (230, 170, 60)),
        "grade": ("Declive", "Grade", "%", (160, 130, 200)),
    },
    "rowing": {
        "power": ("Potência", "Power", "W", (108, 170, 220)),
        "pace": ("Ritmo /500 m", "Pace /500 m", "s", (230, 170, 60)),
        "spm": ("Voga", "Stroke rate", "spm", (120, 200, 150)),
        "hr": ("FC", "HR", "bpm", (214, 54, 128)),
        "speed": ("Velocidade", "Speed", "km/h", (160, 130, 200)),
        "resistance": ("Resistência", "Resistance", "", (150, 150, 150)),
    },
    "running": {
        "hr": ("FC", "HR", "bpm", (214, 54, 128)),
        "speed": ("Velocidade", "Speed", "km/h", (108, 170, 220)),
        "pace": ("Ritmo /km", "Pace /km", "s", (230, 170, 60)),
        "incline": ("Declive", "Incline", "%", (160, 130, 200)),
    },
    "swimming": {
        "hr": ("FC", "HR", "bpm", (214, 54, 128)),
        "speed": ("Velocidade", "Speed", "km/h", (108, 170, 220)),
        "pace": ("Ritmo /100 m", "Pace /100 m", "s", (230, 170, 60)),
    },
}

# o que cada desporto mostrava antes de haver escolha
DEFAULTS = {"cycling": ["power", "hr"], "rowing": ["power", "spm"],
            "running": ["hr", "speed"], "swimming": ["hr", "speed"]}


def key_of(sport: str) -> str:
    return f"live_chart_{sport}"


def keys(sport: str) -> list[str]:
    return list(CATALOG.get(sport, {}))


def label(sport: str, k: str) -> str:
    pt, en, unit, _c = CATALOG[sport][k]
    return tr(pt, en) + (f" ({unit})" if unit else "")


def color(sport: str, k: str) -> tuple:
    return CATALOG[sport][k][3]


def clean(sport: str, raw, limit: int | None = None) -> list[str]:
    """A lista guardada, limpa: só métricas do desporto, sem repetidas, até ao máximo; se
    ficar vazia, as de origem."""
    ok = CATALOG.get(sport, {})
    out: list[str] = []
    for k in (raw or []):
        if k in ok and k not in out:
            out.append(k)
    cap = limit if limit is not None else 5
    out = out[:max(1, cap)]
    return out or list(DEFAULTS.get(sport, []))[:max(1, cap)]


def choice(db, sport: str) -> list[str]:
    return clean(sport, db.get(key_of(sport)), int(options.get(db, "live_chart_max_series")))


def save(db, sport: str, selected) -> list[str]:
    out = clean(sport, selected, int(options.get(db, "live_chart_max_series")))
    db.set(key_of(sport), out)
    return out


def sample(sport: str, src) -> dict[str, float | None]:
    """Os valores de agora de todas as métricas do desporto (`src`: o motor de remo, de
    corrida ou o estado do ciclismo). Falta de dado = None."""
    def g(name, default=None):
        v = getattr(src, name, default)
        return None if v is None else float(v)
    if sport == "cycling":
        spd = g("speed_mps")
        return {"power": g("power_w"), "power_3s": g("power_3s"), "hr": g("hr_bpm"),
                "cadence": g("cadence_rpm"), "speed": None if spd is None else spd * 3.6,
                "grade": g("grade_pct")}
    if sport == "rowing":
        pace = g("pace_s")
        return {"power": g("power_w"), "pace": pace, "spm": g("spm"), "hr": g("hr_bpm"),
                "speed": (500.0 / pace * 3.6) if pace else None, "resistance": g("resistance")}
    speed = g("speed_kmh")
    pace = (3600.0 / speed) if speed else None          # s/km
    if sport == "swimming":
        pace = (360.0 / speed) if speed else None       # s/100 m
        return {"hr": g("hr_bpm"), "speed": speed, "pace": pace}
    return {"hr": g("hr_bpm"), "speed": speed, "pace": pace, "incline": g("incline_pct")}


def normalize(values: list[float]) -> list[float]:
    """Cada linha na sua escala: 0 = o mínimo da sessão, 100 = o máximo (tudo igual: a meio)."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [50.0] * len(values)
    return [(v - lo) / (hi - lo) * 100.0 for v in values]


def legend(sport: str, k: str, value: float | None) -> str:
    """«Potência (W) 215» (ou «Ritmo /500 m 2:05»)."""
    name = tr(*CATALOG[sport][k][:2])
    unit = CATALOG[sport][k][2]
    if value is None:
        return f"{name} —"
    if k == "pace":
        return f"{name} {int(value // 60)}:{int(value % 60):02d}"
    return f"{name} {value:.0f} {unit}".rstrip()


def _downsample(values: list[float], n: int) -> list[float]:
    """Médias por troços, para caber no gráfico (n pontos)."""
    if len(values) <= n:
        return list(values)
    step = len(values) / n
    out = []
    for i in range(n):
        chunk = values[int(i * step):int((i + 1) * step)] or [values[min(len(values) - 1,
                                                                         int(i * step))]]
        out.append(sum(chunk) / len(chunk))
    return out


class LiveSeries:
    """Os valores do gráfico ao vivo de uma sessão: uma lista por métrica escolhida (uma amostra
    por segundo), as voltas marcadas, e o que desenhar. Serve os quatro desportos (o ecrã só
    põe os números e desenha)."""

    CAP, TRIM = 3600, 600          # amostras guardadas por métrica (corta as mais antigas)

    def __init__(self, sport: str, keys_: list[str], points: int = 90):
        self.sport = sport
        self.keys = list(keys_)
        self.points = max(10, int(points))
        self.series: dict[str, list[float]] = {k: [] for k in self.keys}
        self.seen: dict[str, bool] = {k: False for k in self.keys}
        self.marks: list[int] = []         # nº de amostras no momento de cada volta
        self.last: dict[str, float | None] = {}

    @property
    def total(self) -> int:
        return max((len(v) for v in self.series.values()), default=0)

    def add(self, now: dict[str, float | None]) -> None:
        """Junta uma amostra. Sem dado numa métrica, repete o último valor (ou 0)."""
        self.last = now
        for k in self.keys:
            v = now.get(k)
            lst = self.series[k]
            if v is not None:
                self.seen[k] = True
            lst.append(float(v) if v is not None else (lst[-1] if lst else 0.0))
            if len(lst) > self.CAP:
                del lst[:self.TRIM]
                self.marks = [max(0, m - self.TRIM) for m in self.marks]

    def mark(self) -> None:
        """Uma volta marcada agora."""
        self.marks.append(self.total)

    def plot(self) -> tuple[list, list[float], int]:
        """([(legenda, valores 0–100, cor)], posições das voltas (0–1), amostras): só as
        métricas que já tiveram algum dado."""
        out = []
        for k in self.keys:
            if not self.seen.get(k):
                continue
            out.append((legend(self.sport, k, self.last.get(k)),
                        normalize(_downsample(self.series[k], self.points)),
                        color(self.sport, k)))
        total = self.total
        marks = [m / total for m in self.marks if 0 <= m <= total] if total else []
        return out, marks, total
