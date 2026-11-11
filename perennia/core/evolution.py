"""Métricas de evolução: o que mostra como o atleta está a mudar ao longo do
tempo (por oposição às métricas de sessão, que se veem durante um treino).

* **Forma, fadiga e fitness** — em `stats` (CTL/ATL/TSB como o TrainingPeaks).
* **Corrida** — fator de eficiência (EF = velocidade normalizada em m/min
  ÷ FC média), desacoplamento ritmo:FC (a EF da 2.ª metade face à 1.ª) e
  durabilidade (quanto a EF cai no último quarto dos treinos longos).
* **Progressão de carga** — avisos: uma corrida mais de 10 % mais longa do
  que a mais longa dos 30 dias anteriores; o volume semanal a subir mais de
  10 % face à semana anterior.
* **Previsões de prova** — Riegel (T2 = T1 · (D2/D1)^1,06) a partir da melhor
  corrida recente; a maratona também pela fórmula de Tanda (2011), que conta
  com o volume semanal e o ritmo médio dos treinos.
* **Zonas de ritmo** — por três métodos: 80/20 (Fitzgerald), Friel e Daniels
  (VDOT).
* **Prontidão** — HRV, FC em repouso e sono de hoje face à linha de base
  (7 dias) e ao normal (60 dias): pronto, atenção ou descansar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .i18n import tr
from .tss import normalized
from .units import hms

LONG_RUN_S = 75 * 60            # um treino longo, para a durabilidade


def races() -> tuple:
    return ((5000, "5 km"), (10000, "10 km"), (21097.5, tr("Meia maratona", "Half marathon")),
            (42195, tr("Maratona", "Marathon")))


# ============================================================== corrida


@dataclass
class Run:
    id: str
    day: date
    seconds: float
    distance_m: float
    avg_hr: float | None
    speeds: list[float]
    hrs: list[float | None]


def _day(iso: str | None) -> date | None:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().date()
    except (TypeError, ValueError):
        return None


def runs(db, days: int = 120, today: date | None = None, samples: bool = True) -> list[Run]:
    """As corridas concluídas dos últimos `days` dias (as mais antigas primeiro)."""
    from . import endurance as en
    en.ensure(db)
    today = today or date.today()
    since = (today - timedelta(days=days + 1)).isoformat()
    out = []
    for r in db.conn.execute(
            "SELECT id, started_at, moving_s, distance_m, avg_hr FROM endurance_sessions"
            " WHERE status = 'completed' AND sport = 'running' AND started_at >= ?"
            " ORDER BY started_at", (since,)).fetchall():
        d = _day(r["started_at"])
        if d is None or d > today:
            continue
        sp, hr = [], []
        if samples:
            for x in db.conn.execute("SELECT speed_mps, hr_bpm FROM endurance_samples"
                                     " WHERE session_id = ? ORDER BY t_s", (r["id"],)):
                sp.append(x[0] or 0.0)
                hr.append(x[1])
        out.append(Run(r["id"], d, float(r["moving_s"] or 0), float(r["distance_m"] or 0),
                       r["avg_hr"], sp, hr))
    return out


def efficiency(speeds: list[float], hrs: list) -> float | None:
    """EF: velocidade normalizada (m/min) ÷ FC média (como o TrainingPeaks)."""
    hr = [h for h in hrs if h]
    if len(speeds) < 30 or len(hr) < 30:
        return None
    ngs = normalized(speeds)
    return (ngs * 60.0) / (sum(hr) / len(hr)) if ngs else None


def decoupling(speeds: list[float], hrs: list) -> float | None:
    """Pa:HR — quanto a EF da 2.ª metade cai face à 1.ª (%)."""
    n = len(speeds)
    if n < 600:
        return None
    a = efficiency(speeds[: n // 2], hrs[: n // 2])
    b = efficiency(speeds[n // 2:], hrs[n // 2:])
    if not a or not b:
        return None
    return (a - b) / a * 100.0


def durability(speeds: list[float], hrs: list) -> float | None:
    """A queda da EF no último quarto, face aos três primeiros (%)."""
    n = len(speeds)
    if n < LONG_RUN_S:
        return None
    cut = int(n * 0.75)
    a = efficiency(speeds[:cut], hrs[:cut])
    b = efficiency(speeds[cut:], hrs[cut:])
    if not a or not b:
        return None
    return (a - b) / a * 100.0


def running_trends(db, today: date | None = None) -> dict:
    rs = runs(db, 90, today)
    out = {"ef": [], "decoupling": [], "durability": []}
    for r in rs:
        ef = efficiency(r.speeds, r.hrs)
        if ef:
            out["ef"].append((r.day, ef))
        dc = decoupling(r.speeds, r.hrs)
        if dc is not None:
            out["decoupling"].append((r.day, dc))
        du = durability(r.speeds, r.hrs)
        if du is not None:
            out["durability"].append((r.day, du))
    return out


# ================================================== progressão da carga


def load_warnings(db, today: date | None = None) -> list[str]:
    """Os avisos da progressão: uma corrida mais de 10 % mais longa do que a
    mais longa dos 30 dias anteriores; o volume semanal a subir mais de 10 %."""
    today = today or date.today()
    rs = runs(db, 70, today, samples=False)
    out = []
    for r in rs:
        if (today - r.day).days > 14:
            continue
        before = [x for x in rs if r.day - timedelta(days=30) <= x.day < r.day]
        if not before or not r.distance_m:
            continue
        longest = max(x.distance_m for x in before)
        if longest and r.distance_m > longest * 1.10:
            out.append(tr("{d}: {k} km — mais de 10 % acima da mais longa dos 30 dias antes "
                          "({m} km)", "{d}: {k} km — over 10 % above the longest of the 30 days "
                          "before ({m} km)", d=r.day.strftime("%d/%m"),
                          k=f"{r.distance_m / 1000:.1f}", m=f"{longest / 1000:.1f}"))
    weeks = weekly_km(rs, today, 2)
    if len(weeks) == 2 and weeks[0] > 0 and weeks[1] > weeks[0] * 1.10:
        out.append(tr("Volume desta semana: {b} km — subiu {p} % face à anterior ({a} km)",
                      "This week's volume: {b} km — up {p} % on the week before ({a} km)",
                      a=f"{weeks[0]:.1f}", b=f"{weeks[1]:.1f}",
                      p=f"{(weeks[1] / weeks[0] - 1) * 100:.0f}"))
    return out


def weekly_km(rs: list[Run], today: date, n: int) -> list[float]:
    """Os km das últimas `n` semanas de 7 dias (a mais antiga primeiro; a
    última acaba hoje)."""
    out = []
    for k in range(n - 1, -1, -1):
        end = today - timedelta(days=7 * k)
        start = end - timedelta(days=6)
        out.append(sum(r.distance_m for r in rs if start <= r.day <= end) / 1000.0)
    return out


# ============================================================ previsões


def riegel(t1: float, d1: float, d2: float, k: float = 1.06) -> float:
    return t1 * (d2 / d1) ** k


def tanda_marathon(weekly_km_avg: float, pace_s_km: float) -> float:
    """Tanda (2011): ritmo de maratona (s/km) = 17,1 + 140·e^(−0,0053·K) + 0,55·P,
    com K = km por semana (8 semanas) e P = ritmo médio dos treinos (s/km)."""
    return (17.1 + 140.0 * math.exp(-0.0053 * weekly_km_avg) + 0.55 * pace_s_km) * 42.195


def predictions(db, today: date | None = None) -> dict:
    """As previsões de prova a partir da melhor corrida dos últimos 90 dias
    (≥ 3 km), e a maratona também por Tanda."""
    today = today or date.today()
    rs = [r for r in runs(db, 90, today, samples=False) if r.distance_m >= 3000 and r.seconds]
    out: dict = {"basis": None, "races": [], "tanda": None}
    if not rs:
        return out
    # a melhor: a que dá o 10 km mais rápido
    best = min(rs, key=lambda r: riegel(r.seconds, r.distance_m, 10000))
    out["basis"] = best
    for d, name in races():
        out["races"].append((name, d, riegel(best.seconds, best.distance_m, d)))
    eight = [r for r in runs(db, 56, today, samples=False)]
    if eight:
        km = sum(r.distance_m for r in eight) / 1000.0 / 8.0
        dist = sum(r.distance_m for r in eight)
        secs = sum(r.seconds for r in eight)
        if dist > 0:
            out["tanda"] = tanda_marathon(km, secs / (dist / 1000.0))
            out["weekly_km"] = km
    return out


# ================================================================ zonas


def daniels_vdot(distance_m: float, seconds: float) -> float | None:
    """VDOT de Daniels e Gilbert a partir de uma prova (ou esforço máximo)."""
    if distance_m <= 0 or seconds <= 0:
        return None
    t = seconds / 60.0
    v = distance_m / t                                   # m/min
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    pct = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    return vo2 / pct


def pace_at_vo2(vo2: float) -> float:
    """O ritmo (s/km) a que se corre a este VO2 (a mesma equação, ao contrário)."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    v = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)    # m/min
    return 60000.0 / v


def pace_zones(threshold_s_km: float, vdot: float | None = None) -> dict:
    """{método: [(zona, ritmo mais lento, ritmo mais rápido)]} em s/km."""
    t = threshold_s_km
    friel = [("Z1", None, t * 1.29), ("Z2", t * 1.29, t * 1.14), ("Z3", t * 1.13, t * 1.06),
             ("Z4", t * 1.05, t * 1.01), ("Z5a", t * 1.00, t * 0.97),
             ("Z5b", t * 0.96, t * 0.90), ("Z5c", t * 0.90, None)]
    eighty = [(tr("Fácil (80 %)", "Easy (80 %)"), None, t * 1.06),
              (tr("Moderado (evitar)", "Moderate (avoid)"), t * 1.06, t * 1.01),
              (tr("Intenso (20 %)", "Hard (20 %)"), t * 1.01, None)]
    out = {"80/20": eighty, "Friel": friel}
    if vdot:
        out["Daniels"] = [
            ("E", pace_at_vo2(vdot * 0.65), pace_at_vo2(vdot * 0.74)),
            ("M", pace_at_vo2(vdot * 0.80), pace_at_vo2(vdot * 0.85)),
            ("T", pace_at_vo2(vdot * 0.86), pace_at_vo2(vdot * 0.88)),
            ("I", pace_at_vo2(vdot * 0.97), pace_at_vo2(vdot * 1.00)),
            ("R", pace_at_vo2(vdot * 1.05), pace_at_vo2(vdot * 1.10))]
    return out


def zone_text(lo: float | None, hi: float | None) -> str:
    """«5:40–6:10 /km» (lo é o mais lento)."""
    if lo is None:                       # sem limite do lado lento
        return tr("mais lento que {p} /km", "slower than {p} /km", p=hms(hi))
    if hi is None:                       # sem limite do lado rápido
        return tr("mais rápido que {p} /km", "faster than {p} /km", p=hms(lo))
    return f"{hms(hi)}–{hms(lo)} /km"


# ============================================================= prontidão


def readiness(db, today: date | None = None) -> dict:
    """HRV (rMSSD, em ln), FC em repouso e sono de hoje face à linha de base
    de 7 dias e ao normal de 60 dias (média ± 0,5 desvio-padrão, como o
    HRV4Training). Devolve {estado, linhas}."""
    from . import health
    today = today or date.today()
    lines, flags = [], 0

    def series(key: str, n: int) -> dict:
        m = health.metric_by_key(db, key)
        if m is None:
            return {}
        return {d: v for d, v in health.series(db, m["id"], n, today) if v is not None}

    hrv = series("hrv_rmssd", 60)
    if today in hrv and len(hrv) >= 7:
        ln = {d: math.log(v) for d, v in hrv.items() if v > 0}
        days = sorted(ln)
        base7 = sum(ln[d] for d in days[-7:]) / min(7, len(days))
        vals = list(ln.values())
        mean = sum(vals) / len(vals)
        sd = (sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)) ** 0.5
        lo, hi = mean - 0.5 * sd, mean + 0.5 * sd
        state = tr("dentro do normal", "within normal") if lo <= base7 <= hi else (
            tr("abaixo do normal", "below normal") if base7 < lo else
            tr("acima do normal", "above normal"))
        if base7 < lo or ln[today] < mean - 2 * sd:     # a tendência, ou um dia muito baixo
            flags += 1
        lines.append(tr("HRV hoje {v} ms · média de 7 dias {b} ms · {s}",
                        "HRV today {v} ms · 7-day average {b} ms · {s}",
                        v=f"{hrv[today]:.0f}", b=f"{math.exp(base7):.0f}", s=state))
    rhr = series("rhr", 30)
    if today in rhr and len(rhr) >= 5:
        base = sum(v for d, v in rhr.items() if d != today) / max(1, len(rhr) - 1)
        diff = rhr[today] - base
        if diff >= 5:
            flags += 1
        lines.append(tr("FC em repouso {v} bpm · {d:+.0f} face à linha de base",
                        "Resting HR {v} bpm · {d:+.0f} vs baseline", v=f"{rhr[today]:.0f}",
                        d=diff))
    sleep = series("sleep_hours", 30)
    if today in sleep and len(sleep) >= 5:
        base = sum(v for d, v in sleep.items() if d != today) / max(1, len(sleep) - 1)
        diff = sleep[today] - base
        if diff <= -1.0:
            flags += 1
        lines.append(tr("Sono {v} h · {d:+.1f} h face ao costume",
                        "Sleep {v} h · {d:+.1f} h vs usual", v=f"{sleep[today]:.1f}", d=diff))
    if not lines:
        state = None
    elif flags == 0:
        state = "ready"
    elif flags == 1:
        state = "caution"
    else:
        state = "rest"
    return {"state": state, "lines": lines}


READINESS_TEXT = {"ready": ("Pronto: treina como planeado", "Ready: train as planned"),
                  "caution": ("Atenção: um sinal fora do normal — mais leve ou mais curto",
                              "Caution: one sign off — easier or shorter"),
                  "rest": ("Descansa: vários sinais fora do normal",
                           "Rest: several signs off")}
