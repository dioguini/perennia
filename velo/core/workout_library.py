"""Treinos que vêm com a aplicação.

Em % da FTP, por isso servem a qualquer atleta. As zonas e as durações
seguem o que é corrente no treino por potência (Coggan, Seiler, e os
protocolos clássicos de VO2máx e limiar). Cada treino tem aquecimento,
retorno à calma e dicas de texto que aparecem no ecrã.

Entram na base de dados na primeira vez que a aplicação abre, e as
versões novas desta lista acrescentam só os treinos novos — um treino que
apagaste não volta.
"""
from __future__ import annotations

from .workouts import Step

LIBRARY_VERSION = 1
SOURCE = "velolocal"


def _s(minutes: float, pct: float, cad: int | None = None, cue: str | None = None) -> Step:
    return Step("steady", int(round(minutes * 60)), "pct_ftp", pct, pct, cad, cad, cue)


def _r(minutes: float, lo: float, hi: float, cue: str | None = None) -> Step:
    return Step("ramp", int(round(minutes * 60)), "pct_ftp", lo, hi, text_cue=cue)


def _rep(n: int, *block: Step, rest: Step | None = None) -> list[Step]:
    """`n` repetições do bloco; `rest` entre repetições (não depois da última)."""
    out: list[Step] = []
    for i in range(n):
        out.extend(block)
        if rest is not None and i < n - 1:
            out.append(rest)
    return out


def _wu(minutes: float = 10) -> list[Step]:
    return [_r(minutes * 0.7, 45, 70, "Aquecimento: sobe aos poucos"),
            _s(minutes * 0.3, 70, 95, "Cadência solta, 90–95 rpm")]


def _cd(minutes: float = 8) -> list[Step]:
    return [_r(minutes, 60, 40, "Retorno à calma: alivia e roda leve")]


def _with_cue(step: Step, cue: str) -> Step:
    return Step(step.kind, step.duration_s, step.target_type, step.target_lo,
                step.target_hi, step.cadence_lo, step.cadence_hi, cue)


# (nome, categoria, descrição, passos)
WORKOUTS: list[tuple[str, str, str, list[Step]]] = [
    ("Recuperação ativa 40", "Recuperação",
     "40 min na Z1, cadência alta. Para o dia a seguir a um treino duro: tira as "
     "pernas do sítio sem cansar.",
     [_r(5, 40, 50, "Bem leve"), _s(30, 50, 92, "Z1: conversa fácil, pernas a rodar"),
      *_cd(5)]),

    ("Resistência Z2 60", "Resistência",
     "60 min na Z2. A base do treino aeróbio: melhora a capacidade de queimar "
     "gordura e de aguentar horas. Deve dar para conversar.",
     [*_wu(8), _s(45, 68, 90, "Z2: firme mas confortável"), *_cd(7)]),

    ("Resistência Z2 90 com acelerações", "Resistência",
     "90 min na Z2 com 6 acelerações curtas de cadência. Mantém a base e "
     "lembra as pernas de girar depressa.",
     [*_wu(10),
      *_rep(6, _s(10, 68, 90, "Z2 constante"),
            _s(1, 75, 110, "Acelera a cadência a 110 rpm, sem forçar")),
      _s(8, 68, 90), *_cd(6)]),

    ("Tempo 3×15", "Tempo",
     "3 blocos de 15 min a 82 % da FTP (Z3). Ritmo de estrada sustentado; "
     "treina a resistência muscular sem a fadiga do limiar.",
     [*_wu(10),
      *_rep(3, _s(15, 82, 88, "Z3: ritmo forte e regular"),
            rest=_s(5, 55, 95, "Recupera, roda leve")),
      *_cd(8)]),

    ("Sweet spot 3×12", "Sweet spot",
     "3×12 min a 88–92 % da FTP. O melhor rendimento por hora de treino: "
     "sobe a FTP com uma fadiga gerível.",
     [*_wu(10),
      *_rep(3, _s(12, 90, 90, "Sweet spot: duro mas aguentável"),
            rest=_s(4, 55, 95, "Recupera")),
      *_cd(8)]),

    ("Sweet spot 2×20", "Sweet spot",
     "2×20 min a 90 % da FTP. Clássico para subir a FTP; o segundo bloco "
     "deve custar, mas sem rebentar.",
     [*_wu(12),
      _s(20, 90, 88, "Sweet spot: respira fundo e regular"),
      _s(5, 55, 95, "Recupera"),
      _s(20, 90, 88, "Último bloco: mantém a potência"), *_cd(8)]),

    ("Limiar 2×20", "Limiar",
     "2×20 min a 97 % da FTP. O treino de referência do limiar. Se não "
     "conseguires acabar, a FTP pode estar alta demais.",
     [*_wu(15),
      _s(20, 97, 90, "Limiar: no fio, sem passar"),
      _s(8, 55, 95, "Recupera bem"),
      _s(20, 97, 90, "Mais um: igual ao primeiro"), *_cd(10)]),

    ("Escada de limiar 5-10-15", "Limiar",
     "Blocos de 5, 10 e 15 min a 95 % da FTP. Vai crescendo, para "
     "habituar a cabeça a sofrer mais tempo.",
     [*_wu(12),
      _s(5, 95, 90, "5 min no limiar"), _s(4, 55, 95, "Recupera"),
      _s(10, 95, 90, "10 min no limiar"), _s(5, 55, 95, "Recupera"),
      _s(15, 95, 90, "15 min: o mais longo, guarda forças"), *_cd(8)]),

    ("Over-unders 3×9", "Limiar",
     "3 blocos de 9 min a alternar 2 min a 95 % e 1 min a 105 %. Ensina a "
     "limpar o lactato sem baixar o ritmo, como nos ataques em subida.",
     [*_wu(12),
      *_rep(3, *_rep(3, _s(2, 95, 90, "Under: 95 %, controla"),
                     _s(1, 105, 95, "Over: 105 %, acima do limiar")),
            rest=_s(5, 55, 95, "Recupera")),
      *_cd(8)]),

    ("VO2máx 5×4", "VO2máx",
     "5×4 min a 115 % da FTP, com 4 min de recuperação. Sobe o teto "
     "aeróbio. Os últimos 2 minutos de cada um devem ser muito duros.",
     [*_wu(15),
      *_rep(5, _s(4, 115, 100, "VO2máx: cadência alta, respira tudo"),
            rest=_s(4, 50, 90, "Recupera a sério")),
      *_cd(10)]),

    ("VO2máx 30/30", "VO2máx",
     "3 séries de 10×(30 s a 120 % / 30 s a 50 %). Mais tempo perto do "
     "VO2máx do que nos intervalos longos, com menos sofrimento por esforço.",
     [*_wu(15),
      *_rep(3, *_rep(10, _s(0.5, 120, 100, "On: 120 %"),
                     _s(0.5, 50, 90, "Off")),
            rest=_s(5, 55, 90, "Recupera entre séries")),
      *_cd(8)]),

    ("Microintervalos 40/20", "VO2máx",
     "3 séries de 8×(40 s a 120 % / 20 s a 50 %). As recuperações curtas "
     "mantêm o coração lá em cima; muito usado para preparar provas.",
     [*_wu(15),
      *_rep(3, *_rep(8, _s(40 / 60, 120, 100, "40 s forte"),
                     _s(20 / 60, 50, 90, "20 s leve")),
            rest=_s(6, 55, 90, "Recupera")),
      *_cd(8)]),

    ("Pirâmide 1-2-3-4-3-2-1", "VO2máx",
     "Esforços de 1 a 4 min e de volta, a 110 % da FTP, com recuperação "
     "igual ao esforço. Variado e duro.",
     [*_wu(12),
      *[s for m in (1, 2, 3, 4, 3, 2, 1)
        for s in (_s(m, 110, 95, f"{m} min a 110 %"), _s(m, 50, 90, "Recupera"))],
      *_cd(8)]),

    ("Anaeróbico 8×1", "Anaeróbico",
     "8×1 min a 135 % da FTP, com 3 min leves. Para os ataques e as "
     "subidas curtas e explosivas.",
     [*_wu(15),
      *_rep(8, _s(1, 135, 105, "Tudo durante 1 min"),
            rest=_s(3, 50, 90, "Recupera completamente")),
      *_cd(10)]),

    ("Sprints 8×15 s", "Neuromuscular",
     "8 sprints de 15 s, com 4 min leves. Melhor com o ERG desligado: "
     "levanta-te e sprinta a fundo com a mudança pesada.",
     [*_wu(15),
      *_rep(8, Step("freeride", 15, "none", cadence_lo=110, cadence_hi=110,
                    text_cue="SPRINT! Tudo durante 15 s"),
            rest=_s(4, 50, 90, "Recupera")),
      *_cd(8)]),

    ("Força: baixa cadência 5×6", "Força",
     "5×6 min a 85 % da FTP com a cadência a 55–60 rpm. Força específica "
     "na bicicleta, como numa subida longa com mudança pesada.",
     [*_wu(12),
      *_rep(5, _s(6, 85, 58, "Cadência 55–60 rpm, tronco quieto"),
            rest=_s(4, 55, 95, "Recupera com cadência alta")),
      *_cd(8)]),

    ("Cadência 6×(1 + 2)", "Técnica",
     "6 vezes 1 min a 110+ rpm e 2 min a 90 rpm, a potência leve. Melhora "
     "a fluidez e a eficiência da pedalada.",
     [*_wu(10),
      *_rep(6, _s(1, 65, 112, "Cadência 110+ rpm, sem saltar no selim"),
            _s(2, 65, 90, "Volta aos 90 rpm")),
      _s(8, 65, 90), *_cd(6)]),

    ("Ativação pré-prova 30", "Ativação",
     "30 min para a véspera de uma prova: sobretudo leve, com 3×1 min a "
     "105 % e 3 sprints curtos para acordar as pernas.",
     [*_wu(10),
      *_rep(3, _s(1, 105, 95, "1 min a 105 %"),
            rest=_s(2, 60, 90, "Leve")),
      _s(3, 60, 90, "Leve"),
      *_rep(3, _s(10 / 60, 150, 110, "Sprint curto"),
            rest=_s(1.5, 55, 90, "Leve")),
      *_cd(7)]),
]


def seed(db) -> int:
    """Põe na base de dados os treinos da lista que ainda lá não foram postos.

    Lembra-se dos nomes já postos, para não repor um treino que o atleta
    apagou. Devolve quantos acrescentou.
    """
    seeded = set(db.get("library_seeded", []) or [])
    added = 0
    ftp = db.athlete().ftp_w
    from .workouts import Workout
    for name, category, description, steps in WORKOUTS:
        if name in seeded:
            continue
        wk = Workout(name, steps, description, SOURCE)
        db.insert_workout(name, [s.as_dict() for s in steps], SOURCE,
                          f"{category} · {description}", wk.estimated_tss(ftp))
        seeded.add(name)
        added += 1
    db.set("library_seeded", sorted(seeded))
    db.set("library_version", LIBRARY_VERSION)
    return added
