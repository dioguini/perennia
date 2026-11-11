"""Modo de teste de FTP (req. 19).

Três protocolos consagrados, cada um gerado como um treino estruturado
normal — o motor da sessão não precisa de saber que é um teste. No fim
calcula-se a FTP a partir das amostras e o atleta aceita ou descarta.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import physics
from .workouts import Step, Workout

PROTOCOLS = ("20min", "ramp", "8x8")          # dão a FTP
TEST_PROTOCOLS = ("sprint", "1min", "5min")    # outros testes de aptidão no rolo


@dataclass
class Protocol:
    key: str
    label_key: str
    description_pt: str


CATALOG = {
    "20min": Protocol("20min", "ftp.20min",
                      "Aquecimento, 5 min forte para abrir, e 20 min no máximo "
                      "sustentável. FTP = 95 % da média dos 20 min."),
    "ramp": Protocol("ramp", "ftp.ramp",
                     "Rampa progressiva até à exaustão. FTP = 75 % do melhor "
                     "minuto. É o mais curto e o menos exigente mentalmente."),
    "8x8": Protocol("8x8", "ftp.8x8",
                    "Dois blocos de 8 min no máximo, com 10 min de recuperação. "
                    "FTP = 90 % da média do melhor bloco."),
    "sprint": Protocol("sprint", "test.sprint", "Três sprints de 10 s; conta o melhor 5 s."),
    "1min": Protocol("1min", "test.1min", "1 min a fundo; conta a média."),
    "5min": Protocol("5min", "test.5min", "5 min no máximo; conta a média (e o VO2máx)."),
}


def build(protocol: str, ftp_w: int) -> Workout:
    """Gera o treino do teste. Os alvos servem de referência visual;
    em rampa são obrigatórios porque é o degrau que define o protocolo."""
    if protocol == "20min":
        steps = [
            Step("ramp", 600, "pct_ftp", 50, 70, text_cue="Aquecimento"),
            Step("steady", 300, "pct_ftp", 105, 105, text_cue="5 min forte"),
            Step("steady", 600, "pct_ftp", 50, 50, text_cue="Recuperação"),
            Step("freeride", 1200, "none", text_cue="20 min no máximo sustentável"),
            Step("steady", 600, "pct_ftp", 50, 50, text_cue="Retorno à calma"),
        ]
    elif protocol == "ramp":
        steps = [Step("steady", 300, "pct_ftp", 50, 50, text_cue="Aquecimento")]
        # degraus de 20 W por minuto a partir de 40 % da FTP atual
        watts = max(80, int(ftp_w * 0.40))
        for i in range(40):
            steps.append(Step("steady", 60, "watts", watts, watts,
                              text_cue=f"Degrau {i + 1}: {watts} W"))
            watts += 20
        steps.append(Step("steady", 300, "pct_ftp", 45, 45, text_cue="Retorno à calma"))
    elif protocol == "8x8":
        steps = [
            Step("ramp", 600, "pct_ftp", 50, 75, text_cue="Aquecimento"),
            Step("freeride", 480, "none", text_cue="Bloco 1 — 8 min no máximo"),
            Step("steady", 600, "pct_ftp", 50, 50, text_cue="Recuperação"),
            Step("freeride", 480, "none", text_cue="Bloco 2 — 8 min no máximo"),
            Step("steady", 600, "pct_ftp", 45, 45, text_cue="Retorno à calma"),
        ]
    elif protocol == "sprint":
        steps = [Step("ramp", 600, "pct_ftp", 50, 75, text_cue="Aquecimento")]
        for i in range(3):
            steps.append(Step("freeride", 10, "none", text_cue=f"Sprint {i + 1} — a fundo!"))
            steps.append(Step("steady", 170, "pct_ftp", 50, 50, text_cue="Recupera"))
        steps.append(Step("steady", 300, "pct_ftp", 45, 45, text_cue="Retorno à calma"))
    elif protocol == "1min":
        steps = [Step("ramp", 600, "pct_ftp", 50, 75, text_cue="Aquecimento"),
                 Step("steady", 120, "pct_ftp", 55, 55, text_cue="Prepara-te"),
                 Step("freeride", 60, "none", text_cue="1 minuto a fundo!"),
                 Step("steady", 300, "pct_ftp", 45, 45, text_cue="Retorno à calma")]
    elif protocol == "5min":
        steps = [Step("ramp", 600, "pct_ftp", 50, 75, text_cue="Aquecimento"),
                 Step("steady", 60, "pct_ftp", 100, 100, text_cue="Abrir"),
                 Step("steady", 240, "pct_ftp", 55, 55, text_cue="Recupera"),
                 Step("freeride", 300, "none", text_cue="5 minutos no máximo"),
                 Step("steady", 300, "pct_ftp", 45, 45, text_cue="Retorno à calma")]
    else:
        raise ValueError(f"protocolo desconhecido: {protocol}")

    label = {"20min": "Teste de FTP — 20 minutos",
             "ramp": "Teste de FTP — rampa",
             "8x8": "Teste de FTP — 2 × 8 minutos",
             "sprint": "Teste — sprint de 5 s",
             "1min": "Teste — 1 minuto máximo",
             "5min": "Teste — 5 minutos máximo"}[protocol]
    return Workout(label, steps, CATALOG[protocol].description_pt, "ftp_test")


def estimate(protocol: str, power_series: list[float]) -> tuple[float, int] | None:
    """Devolve (valor bruto, FTP estimada) a partir das amostras a 1 Hz.

    - 20 min: 95 % da melhor média de 20 min
    - rampa:  75 % do melhor minuto
    - 8 × 8:  90 % da melhor média de 8 min
    """
    if not power_series:
        return None
    if protocol == "20min":
        best = _best_average(power_series, 1200)
        if best is None:
            return None
        return best, int(round(best * 0.95))
    if protocol == "ramp":
        best = _best_average(power_series, 60)
        if best is None:
            return None
        return best, int(round(best * 0.75))
    if protocol == "8x8":
        best = _best_average(power_series, 480)
        if best is None:
            return None
        return best, int(round(best * 0.90))
    # testes que não dão FTP: o resultado é a própria melhor média
    window = {"sprint": 5, "1min": 60, "5min": 300}.get(protocol)
    if window is not None:
        best = _best_average(power_series, window)
        if best is None:
            return None
        return best, int(round(best))
    raise ValueError(f"protocolo desconhecido: {protocol}")


def _best_average(series: list[float], window_s: int) -> float | None:
    curve = dict(physics.power_curve(series, durations=(window_s,)))
    return curve.get(window_s)


def zones_from_ftp(ftp_w: int, bounds_pct: list[float]) -> list[tuple[int, int]]:
    """Intervalos em watts para cada zona, para mostrar nas definições."""
    edges = [0] + [int(round(ftp_w * b / 100.0)) for b in bounds_pct]
    out = []
    for i in range(len(edges) - 1):
        out.append((edges[i] + 1 if i else 0, edges[i + 1]))
    out.append((edges[-1] + 1, 0))   # a última zona não tem topo
    return out
