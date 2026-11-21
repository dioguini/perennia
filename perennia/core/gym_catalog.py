"""Catálogo alargado do ginásio: mais exercícios e treinos pré-definidos.

Junta-se ao que já existe em `gym` (os exercícios de cada modalidade) e em `strength` (os três
treinos base). Entra sozinho em qualquer base de dados, uma vez por versão do catálogo:

* os **exercícios** novos entram (os que já tens, com o mesmo nome, ficam como estão);
* os **treinos** novos entram uma só vez — se os apagares, não voltam, e os que editares ficam
  como os deixaste (a verificação é pelo nome do treino de origem, guardado na lista
  `gym_catalog_workouts` das definições).

Cada treino: (nome, modalidade, descrição, [(exercício, séries, repetições ou segundos, carga kg,
RPE, descanso s)]). Uma carga vazia é «a que escolheres»; nos exercícios por tempo as «repetições»
são segundos. Os treinos com complexos de kettlebell entram depois de os complexos existirem.
"""
from __future__ import annotations

import json

from .db import Database
from .i18n import tr


def _x(mod: str, group: str, cat: str, bw: float, measure: str, kit: tuple, *names: str) -> list:
    return [(n, mod, group, cat, bw, measure, kit) for n in names]


EXERCISES: list[tuple] = []
# ------------------------------------------------------------------- força: pernas e anca
EXERCISES += _x("strength", "legs", "squat", 0.0, "reps", ("barbell", "plates", "rack"),
                "Agachamento com pausa", "Agachamento Zercher", "Box squat")
EXERCISES += _x("strength", "legs", "squat", 0.0, "reps", ("dumbbell",),
                "Agachamento com halteres", "Agachamento sumo com haltere")
EXERCISES += _x("strength", "legs", "squat", 0.0, "reps", ("cable",),
                "Smith squat", "Hack squat", "Prensa de pernas 45º")
EXERCISES += _x("strength", "legs", "squat", 0.8, "reps", (),
                "Agachamento sissy", "Agachamento cossaco", "Agachamento com salto lento")
EXERCISES += _x("strength", "legs", "lunge", 0.0, "reps", ("dumbbell",),
                "Afundos caminhando", "Afundos reversos", "Afundos laterais", "Step-up lateral")
EXERCISES += _x("strength", "legs", "leg_curl", 0.0, "reps", ("cable",),
                "Curl femoral deitado", "Curl femoral sentado")
EXERCISES += _x("strength", "legs", "calf_raise", 0.0, "reps", ("dumbbell",),
                "Elevação de gémeos sentado", "Elevação de gémeos a uma perna")
EXERCISES += _x("strength", "legs", "unknown", 0.0, "reps", ("cable",),
                "Adução de anca (máquina)", "Abdução de anca (máquina)")
EXERCISES += _x("strength", "hips", "deadlift", 0.0, "reps", ("barbell", "plates"),
                "Peso morto sumo", "Rack pull", "Good morning")
EXERCISES += _x("strength", "hips", "deadlift", 0.0, "reps", ("trap_bar", "plates"),
                "Peso morto com barra hexagonal")
EXERCISES += _x("strength", "hips", "deadlift", 0.0, "reps", ("dumbbell",),
                "Peso morto com halteres", "Peso morto a uma perna")
EXERCISES += _x("strength", "hips", "hip_raise", 0.0, "reps", ("bench",),
                "Hip thrust a uma perna")
EXERCISES += _x("strength", "hips", "hip_raise", 0.5, "reps", ("mat",),
                "Ponte de glúteos a uma perna", "Ponte de glúteos com banda")
EXERCISES += _x("strength", "hips", "hip_swing", 0.0, "reps", ("cable",),
                "Kickback de glúteo no cabo", "Extensão de anca no cabo")
EXERCISES += _x("strength", "hips", "hyperextension", 0.5, "reps", ("bench",),
                "Hiperextensão a uma perna", "Hiperextensão com peso")
# ------------------------------------------------------------------- força: peito
EXERCISES += _x("strength", "chest", "bench_press", 0.0, "reps", ("barbell", "plates", "bench",
                "rack"), "Supino inclinado com barra", "Supino declinado", "Supino com pega fechada")
EXERCISES += _x("strength", "chest", "bench_press", 0.0, "reps", ("dumbbell", "bench"),
                "Supino com halteres", "Supino com halteres e pega neutra")
EXERCISES += _x("strength", "chest", "bench_press", 0.0, "reps", ("cable",),
                "Supino na máquina")
EXERCISES += _x("strength", "chest", "flye", 0.0, "reps", ("cable",),
                "Crossover nos cabos", "Peck deck")
EXERCISES += _x("strength", "chest", "flye", 0.0, "reps", ("dumbbell", "bench"),
                "Pullover com haltere")
EXERCISES += _x("strength", "chest", "push_up", 0.65, "reps", (),
                "Flexões diamante", "Flexões com pés elevados", "Flexões com pausa",
                "Flexões inclinadas (mãos elevadas)")
# ------------------------------------------------------------------- força: costas
EXERCISES += _x("strength", "back", "row", 0.0, "reps", ("barbell", "plates"),
                "Remada Pendlay", "Remada em T", "Remada com peito apoiado")
EXERCISES += _x("strength", "back", "row", 0.0, "reps", ("cable",),
                "Remada na máquina", "Remada unilateral no cabo", "Remada baixa pegada neutra")
EXERCISES += _x("strength", "back", "pull_up", 0.0, "reps", ("cable",),
                "Puxada com pega neutra", "Puxada com braços estendidos", "Puxada unilateral")
EXERCISES += _x("strength", "back", "pull_up", 1.0, "reps", ("pullup_bar",),
                "Elevações supinadas (chin-ups)", "Elevações com pega neutra",
                "Elevações escapulares")
EXERCISES += _x("strength", "back", "row", 0.6, "reps", ("pullup_bar",),
                "Australian pull-up")
EXERCISES += _x("strength", "back", "shrug", 0.0, "reps", ("barbell", "plates"),
                "Encolhimentos com barra")
# ------------------------------------------------------------------- força: ombros e braços
EXERCISES += _x("strength", "shoulders", "shoulder_press", 0.0, "reps", ("dumbbell",),
                "Press de ombros sentado", "Press Arnold", "Press landmine")
EXERCISES += _x("strength", "shoulders", "shoulder_press", 0.0, "reps", ("barbell", "plates"),
                "Push press")
EXERCISES += _x("strength", "shoulders", "lateral_raise", 0.0, "reps", ("dumbbell",),
                "Elevações frontais", "Pássaros (elevação posterior)", "Remada alta")
EXERCISES += _x("strength", "shoulders", "lateral_raise", 0.0, "reps", ("cable",),
                "Elevações laterais no cabo")
EXERCISES += _x("strength", "shoulders", "shoulder_stability", 0.0, "reps", ("dumbbell",),
                "Rotação externa com haltere", "Y-T-W no banco")
EXERCISES += _x("strength", "arms", "curl", 0.0, "reps", ("dumbbell",),
                "Curl martelo", "Curl inclinado", "Curl concentrado", "Curl de punho",
                "Curl inverso")
EXERCISES += _x("strength", "arms", "curl", 0.0, "reps", ("barbell", "plates"),
                "Curl com barra", "Curl scott")
EXERCISES += _x("strength", "arms", "curl", 0.0, "reps", ("cable",), "Curl no cabo")
EXERCISES += _x("strength", "arms", "triceps_extension", 0.0, "reps", ("cable",),
                "Tríceps no cabo (pushdown)", "Extensão de tríceps acima da cabeça (cabo)")
EXERCISES += _x("strength", "arms", "triceps_extension", 0.0, "reps", ("dumbbell",),
                "Tríceps testa (skull crusher)", "Kickback de tríceps",
                "Extensão de tríceps acima da cabeça")
EXERCISES += _x("strength", "arms", "triceps_extension", 0.7, "reps", ("bench",),
                "Fundos em banco")
# ------------------------------------------------------------------- força: core
EXERCISES += _x("strength", "core", "core", 0.0, "reps", ("ab_wheel",), "Roda abdominal")
EXERCISES += _x("strength", "core", "core", 0.0, "reps", (),
                "Russian twist", "Bicycle crunch", "V-ups", "Bird dog", "Prancha com toque no ombro",
                "Mountain climbers lentos")
EXERCISES += _x("strength", "core", "leg_raise", 0.0, "reps", ("pullup_bar",),
                "Elevação de joelhos suspenso", "Toes to bar")
EXERCISES += _x("strength", "core", "crunch", 0.0, "reps", ("cable",), "Crunch no cabo")
EXERCISES += _x("strength", "core", "chop", 0.0, "reps", ("cable",),
                "Anti-rotação no cabo", "Lenhador (wood chop) no cabo")
EXERCISES += _x("strength", "core", "core", 0.0, "reps", ("dumbbell",),
                "Flexão lateral com haltere")
EXERCISES += _x("strength", "core", "carry", 0.0, "time", ("dumbbell",), "Suitcase carry")
EXERCISES += _x("strength", "core", "plank", 0.0, "time", ("mat",),
                "Prancha com arrasto", "Prancha em cima de bola")
# ------------------------------------------------------------------- força: corpo inteiro
EXERCISES += _x("strength", "full", "olympic_lift", 0.0, "reps", ("barbell", "plates"),
                "Power clean", "Hang clean", "Snatch (barra)", "Jerk")
EXERCISES += _x("strength", "full", "total_body", 0.0, "reps", ("dumbbell",),
                "Thruster com barra", "Man maker", "Clean e press com halteres")
EXERCISES += _x("strength", "full", "total_body", 0.0, "reps", ("medball",), "Wall ball")
EXERCISES += _x("strength", "full", "carry", 0.0, "time", ("sled",),
                "Empurrar trenó", "Arrastar trenó")
EXERCISES += _x("strength", "full", "carry", 0.0, "time", ("dumbbell",),
                "Transporte ao peito (goblet carry)", "Transporte acima da cabeça")
EXERCISES += _x("strength", "full", "total_body", 0.0, "time", (), "Bear crawl")
# ------------------------------------------------------------------- calisténicos
EXERCISES += _x("calisthenics", "chest", "push_up", 0.75, "reps", (),
                "Flexões arqueiro", "Flexões em pino contra a parede", "Flexões explosivas")
EXERCISES += _x("calisthenics", "back", "pull_up", 1.0, "reps", ("pullup_bar",),
                "Elevações arqueiro", "Elevações explosivas", "Front lever (progressão)")
EXERCISES += _x("calisthenics", "core", "plank", 0.0, "time", ("parallettes",),
                "Planche lean", "L-sit nas paralelas")
EXERCISES += _x("calisthenics", "legs", "squat", 0.8, "reps", (),
                "Pistol squat assistido", "Nordic curl", "Agachamento a uma perna na caixa")
EXERCISES += _x("calisthenics", "arms", "triceps_extension", 1.0, "reps", ("parallettes",),
                "Fundos nas paralelas")
EXERCISES += _x("calisthenics", "full", "total_body", 0.0, "reps", (),
                "Bear walk", "Wall walk", "Burpee com flexão")
# ------------------------------------------------------------------- kettlebell
EXERCISES += _x("kettlebell", "hips", "hip_swing", 0.0, "reps", ("kettlebell",),
                "Swing a uma mão", "Swing americano", "Swing duplo", "Swing em pé alternado")
EXERCISES += _x("kettlebell", "full", "olympic_lift", 0.0, "reps", ("kettlebell",),
                "Clean e press a uma mão", "Clean duplo", "Jerk com kettlebell",
                "Long cycle (clean e jerk)", "Snatch a uma mão", "Snatch duplo")
EXERCISES += _x("kettlebell", "legs", "squat", 0.0, "reps", ("kettlebell",),
                "Agachamento frontal com kettlebell", "Agachamento duplo (rack)",
                "Afundos com kettlebell no rack", "Peso morto sumo com kettlebell")
EXERCISES += _x("kettlebell", "shoulders", "shoulder_press", 0.0, "reps", ("kettlebell",),
                "Press duplo", "Bottoms-up press", "Press de pernas no chão (kettlebell)",
                "Armbar")
EXERCISES += _x("kettlebell", "back", "row", 0.0, "reps", ("kettlebell",),
                "Remada renegade", "Remada curvada com kettlebell")
EXERCISES += _x("kettlebell", "core", "core", 0.0, "reps", ("kettlebell",),
                "Figure 8", "Pass around", "Halo ajoelhado", "Get-up parcial (até ao cotovelo)",
                "Rotação russa com kettlebell")
EXERCISES += _x("kettlebell", "full", "carry", 0.0, "time", ("kettlebell",),
                "Rack carry", "Overhead carry", "Suitcase carry com kettlebell")
EXERCISES += _x("kettlebell", "full", "total_body", 0.0, "reps", ("kettlebell",),
                "Thruster com kettlebell", "Complexo de ombro (halo + press)")
# ------------------------------------------------------------------- elásticos, mobilidade, HIIT
EXERCISES += _x("bands", "hips", "hip_stability", 0.0, "reps", ("bands",),
                "Clamshell com elástico", "Passo lateral com elástico", "Ponte com elástico")
EXERCISES += _x("bands", "shoulders", "shoulder_stability", 0.0, "reps", ("bands",),
                "Rotação externa com elástico", "Rotação interna com elástico",
                "Y-T-W com elástico")
EXERCISES += _x("mobility", "mobility", "warm_up", 0.0, "time", ("mat",),
                "Mobilidade de anca (círculos)", "Mobilidade da coluna torácica",
                "Alongamento de peitoral na porta", "Alongamento de gémeos na parede",
                "Alongamento de quadríceps", "Alongamento de glúteos (pombo)",
                "Mobilidade de punhos", "Mobilidade do pescoço", "Postura da criança",
                "World's greatest stretch", "Cat-cow lento", "Rolo de massagem nas costas",
                "Rolo de massagem nas pernas")
EXERCISES += _x("hiit", "full", "cardio", 0.0, "time", (),
                "Sprint no lugar", "Skaters", "Agachamento com salto e toque no chão",
                "Prancha com salto", "Escaladores cruzados", "Inchworm")
EXERCISES += _x("isometric", "core", "plank", 0.0, "time", (),
                "Prancha com elevação de perna", "Bird dog isométrico", "Dead bug isométrico")
EXERCISES += _x("tendons", "legs", "calf_raise", 0.0, "reps", (),
                "Elevação de gémeos isométrica no degrau", "Salto pogo suave")


def register() -> None:
    """Junta o catálogo ao registo do ginásio (feito uma vez ao importar `gym`)."""
    from . import gym
    seen = {e[0:2] for e in gym.SEED_EXERCISES}
    for ex in EXERCISES:
        if ex[0:2] not in seen:
            gym.SEED_EXERCISES.append(ex)
            seen.add(ex[0:2])


# ===================================================================== treinos de origem

# (nome, modalidade, descrição, [(exercício, séries, reps|s, carga, RPE, descanso)], precisa de complexos)
_W = tuple
WORKOUTS: tuple[tuple, ...] = (
    ("Push · peito, ombros e tríceps", "strength",
     "Empurrar: supino, press de ombros, tríceps. 50–60 min.",
     [("Mobilidade / aquecimento", 1, 300, None, None, 30),
      ("Supino com barra", 4, 6, None, 8.0, 150),
      ("Press de ombros com halteres", 3, 8, None, 7.5, 120),
      ("Supino inclinado com halteres", 3, 10, None, 7.5, 90),
      ("Elevações laterais", 3, 12, None, 8.0, 60),
      ("Tríceps no cabo (pushdown)", 3, 12, None, 8.0, 60),
      ("Fundos (dips)", 2, 10, None, 8.0, 90)], False),
    ("Pull · costas e bíceps", "strength",
     "Puxar: elevações, remadas e bíceps. 50–60 min.",
     [("Mobilidade / aquecimento", 1, 300, None, None, 30),
      ("Elevações (pull-ups)", 4, 6, None, 8.0, 150),
      ("Remada com barra", 4, 8, None, 7.5, 120),
      ("Remada sentada (cabo)", 3, 10, None, 7.5, 90),
      ("Face pull", 3, 15, None, 7.0, 60),
      ("Curl de bíceps", 3, 10, None, 8.0, 60),
      ("Curl martelo", 2, 12, None, 8.0, 60)], False),
    ("Pernas · quadríceps e glúteos", "strength",
     "Agachar e dobrar a anca, com unilaterais. 55–65 min.",
     [("Mobilidade / aquecimento", 1, 300, None, None, 30),
      ("Agachamento com barra", 4, 6, None, 8.0, 180),
      ("Peso morto romeno", 3, 8, None, 7.5, 150),
      ("Agachamento búlgaro", 3, 8, None, 8.0, 90),
      ("Hip thrust", 3, 10, None, 8.0, 90),
      ("Curl femoral", 3, 12, None, 8.0, 60),
      ("Elevação de gémeos", 4, 12, None, 8.0, 60)], False),
    ("Parte superior · A", "strength",
     "Empurrar e puxar equilibrados. 50 min.",
     [("Supino com halteres", 4, 8, None, 7.5, 120),
      ("Remada com halter", 4, 10, None, 7.5, 90),
      ("Press de ombros sentado", 3, 10, None, 7.5, 90),
      ("Puxada ao peito", 3, 10, None, 7.5, 90),
      ("Curl de bíceps", 2, 12, None, 8.0, 60),
      ("Extensão de tríceps", 2, 12, None, 8.0, 60)], False),
    ("Parte inferior · A", "strength",
     "Pernas e anca, com core. 50 min.",
     [("Agachamento frontal", 4, 6, None, 8.0, 150),
      ("Peso morto", 3, 5, None, 8.0, 180),
      ("Afundos caminhando", 3, 10, None, 7.5, 90),
      ("Prensa de pernas", 3, 12, None, 8.0, 90),
      ("Prancha", 3, 45, None, 7.0, 45)], False),
    ("Corpo inteiro · iniciante (máquinas)", "strength",
     "Primeiros treinos: máquinas e cabos, séries curtas. 40 min.",
     [("Prensa de pernas", 3, 12, None, 6.5, 90),
      ("Supino na máquina", 3, 12, None, 6.5, 90),
      ("Remada na máquina", 3, 12, None, 6.5, 90),
      ("Press de ombros sentado", 2, 12, None, 6.5, 75),
      ("Curl femoral sentado", 2, 12, None, 6.5, 60),
      ("Prancha", 2, 30, None, 6.0, 45)], False),
    ("Corpo inteiro · halteres em casa", "strength",
     "Só com halteres e um banco. 40–50 min.",
     [("Agachamento com halteres", 4, 10, None, 7.5, 90),
      ("Supino com halteres", 3, 10, None, 7.5, 90),
      ("Remada com halter", 3, 10, None, 7.5, 90),
      ("Peso morto com halteres", 3, 10, None, 7.5, 90),
      ("Press de ombros com halteres", 3, 10, None, 7.5, 75),
      ("Russian twist", 3, 20, None, 7.0, 45)], False),
    ("Glúteos e isquiotibiais", "strength",
     "Hip thrust, pesos mortos e abdução. 45 min.",
     [("Hip thrust", 4, 8, None, 8.0, 120),
      ("Peso morto romeno", 3, 10, None, 7.5, 120),
      ("Hip thrust a uma perna", 3, 10, None, 7.5, 75),
      ("Curl femoral deitado", 3, 12, None, 8.0, 60),
      ("Abdução de anca (banda)", 3, 15, None, 7.5, 45)], False),
    ("Ombros e braços", "strength",
     "Volume para ombros e braços. 40 min.",
     [("Press militar", 4, 6, None, 8.0, 120),
      ("Elevações laterais", 4, 12, None, 8.5, 60),
      ("Pássaros (elevação posterior)", 3, 15, None, 8.0, 60),
      ("Curl com barra", 3, 10, None, 8.0, 60),
      ("Tríceps testa (skull crusher)", 3, 10, None, 8.0, 60),
      ("Curl martelo", 2, 12, None, 8.0, 45)], False),
    ("Core e anca · 30 min", "strength",
     "Estabilidade do tronco e da anca. 30 min.",
     [("Dead bug", 3, 12, None, 6.5, 30),
      ("Bird dog", 3, 12, None, 6.5, 30),
      ("Prancha lateral", 3, 30, None, 7.0, 30),
      ("Pallof press", 3, 12, None, 7.0, 45),
      ("Ponte de glúteos", 3, 15, None, 6.5, 45),
      ("Elevação de pernas", 3, 12, None, 7.0, 45)], False),
    ("Força para ciclistas", "strength",
     "Pernas, anca e core para pedalar mais forte. 45 min.",
     [("Agachamento com barra", 4, 5, None, 8.0, 150),
      ("Peso morto romeno", 3, 8, None, 7.5, 120),
      ("Step-up", 3, 8, None, 7.5, 90),
      ("Hip thrust", 3, 8, None, 8.0, 90),
      ("Prancha com toque no ombro", 3, 30, None, 7.0, 45),
      ("Pallof press", 3, 10, None, 7.0, 45)], False),
    ("Força para remadores", "strength",
     "Puxar, pernas e core: a base de uma boa remada. 50 min.",
     [("Peso morto", 4, 5, None, 8.0, 180),
      ("Remada com barra", 4, 8, None, 8.0, 120),
      ("Agachamento frontal", 3, 6, None, 7.5, 150),
      ("Puxada ao peito", 3, 10, None, 7.5, 90),
      ("Face pull", 3, 15, None, 7.0, 60),
      ("Hollow hold", 3, 30, None, 7.0, 45)], False),
    ("Força para corredores", "strength",
     "Unilateral, gémeos e anca para correr com menos lesões. 40 min.",
     [("Agachamento búlgaro", 3, 8, None, 7.5, 90),
      ("Peso morto a uma perna", 3, 8, None, 7.5, 90),
      ("Elevação de gémeos a uma perna", 3, 12, None, 8.0, 60),
      ("Step-up lateral", 3, 10, None, 7.0, 60),
      ("Ponte de glúteos a uma perna", 3, 12, None, 7.0, 45),
      ("Prancha lateral", 3, 30, None, 7.0, 30)], False),
    ("Prevenção de lesões · ombros e anca", "bands",
     "Elásticos para ombros e anca: aquecimento ou dia leve. 20 min.",
     [("Rotação externa com elástico", 2, 15, None, 5.5, 30),
      ("Y-T-W com elástico", 2, 10, None, 5.5, 30),
      ("Clamshell com elástico", 2, 15, None, 5.5, 30),
      ("Passo lateral com elástico", 2, 12, None, 6.0, 30),
      ("Ponte com elástico", 2, 15, None, 6.0, 30),
      ("Pull-apart", 2, 15, None, 5.5, 30)], False),
    ("Peso do corpo · base", "calisthenics",
     "Sem material (ou só uma barra). 35 min.",
     [("Flexões", 4, 10, None, 7.5, 75),
      ("Australian pull-up", 4, 8, None, 7.5, 75),
      ("Agachamento cossaco", 3, 8, None, 7.0, 60),
      ("Fundos em banco", 3, 10, None, 7.5, 60),
      ("Prancha", 3, 40, None, 7.0, 45),
      ("Bear crawl", 3, 20, None, 7.0, 45)], False),
    ("Calistenia · empurrar e puxar", "calisthenics",
     "Elevações, fundos e progressões. 45 min.",
     [("Elevações (pull-ups)", 5, 5, None, 8.0, 120),
      ("Fundos nas paralelas", 5, 6, None, 8.0, 120),
      ("Flexões em pino (pike)", 3, 8, None, 7.5, 90),
      ("Elevação de pernas suspenso", 3, 8, None, 7.5, 75),
      ("L-sit", 4, 15, None, 8.0, 60)], False),
    ("Kettlebell · swings e get-ups (iniciante)", "kettlebell",
     "A base do kettlebell: anca, equilíbrio e ombro. 30 min.",
     [("Kettlebell swing", 5, 15, None, 7.0, 45),
      ("Turkish get-up", 3, 3, None, 7.0, 60),
      ("Agachamento goblet", 3, 10, None, 7.0, 60),
      ("Halo", 3, 8, None, 6.5, 45),
      ("Farmer's carry", 3, 40, None, 7.0, 60)], False),
    ("Kettlebell · corpo inteiro 30 min", "kettlebell",
     "Clean, press, agachamento e remada. 30 min.",
     [("Clean com kettlebell", 4, 8, None, 7.0, 60),
      ("Press com kettlebell", 4, 6, None, 7.5, 75),
      ("Agachamento frontal com kettlebell", 4, 8, None, 7.5, 75),
      ("Remada com kettlebell", 3, 10, None, 7.0, 60),
      ("Swing a uma mão", 3, 12, None, 7.5, 60)], False),
    ("Kettlebell · potência e core", "kettlebell",
     "Snatch, swing e rotação: potência e tronco. 30 min.",
     [("Snatch com kettlebell", 5, 8, None, 7.5, 60),
      ("Kettlebell swing", 5, 20, None, 7.5, 45),
      ("Windmill", 3, 5, None, 6.5, 45),
      ("Rotação russa com kettlebell", 3, 20, None, 7.0, 45),
      ("Rack carry", 3, 40, None, 7.0, 60)], False),
    ("Kettlebell · complexos (clean, press, agachamento)", "kettlebell",
     "Cada série é uma ronda completa do complexo: as repetições são as rondas. 30 min.",
     [("Kettlebell swing", 3, 15, None, 6.5, 45),
      ("Complexo KB · Clean + Press + Front squat", 5, 4, None, 8.0, 90),
      ("Complexo KB · Swing + Clean + Press", 3, 4, None, 8.0, 90),
      ("Halo", 2, 8, None, 6.0, 30)], True),
    ("Kettlebell · complexos de ombro e core", "kettlebell",
     "Complexos mais leves, para técnica. 25 min.",
     [("Complexo KB · Snatch + Goblet squat", 4, 4, None, 7.5, 75),
      ("Complexo KB · Clean and press + Windmill", 3, 4, None, 7.5, 75),
      ("Complexo KB · Swing + Goblet squat + Halo", 3, 5, None, 7.0, 60)], True),
    ("Mobilidade matinal · 15 min", "mobility",
     "Acordar o corpo antes do dia ou do treino. 15 min.",
     [("Gato-camelo", 1, 60, None, None, 10), ("Cat-cow lento", 1, 60, None, None, 10),
      ("Rotação torácica (open book)", 1, 60, None, None, 10),
      ("Alongamento do flexor da anca", 2, 45, None, None, 10),
      ("World's greatest stretch", 2, 45, None, None, 10),
      ("Círculos de ombro", 1, 45, None, None, 10),
      ("Agachamento profundo (estático)", 1, 60, None, None, 10)], False),
    ("Mobilidade de anca e ombros", "mobility",
     "Para quem passa o dia sentado. 20 min.",
     [("90/90 de anca", 2, 60, None, None, 15),
      ("Mobilidade de anca (círculos)", 2, 45, None, None, 15),
      ("Alongamento de glúteos (pombo)", 2, 60, None, None, 15),
      ("Mobilidade da coluna torácica", 2, 45, None, None, 15),
      ("Alongamento de peitoral na porta", 2, 45, None, None, 15),
      ("Postura da criança", 1, 60, None, None, 15)], False),
    ("Isométricos · tendões e core", "isometric",
     "Isométricos longos, carga baixa. 25 min.",
     [("Prancha", 3, 45, None, 7.0, 45), ("Prancha lateral", 3, 30, None, 7.0, 45),
      ("Hollow hold", 3, 30, None, 7.0, 45),
      ("Agachamento na parede (wall sit)", 3, 45, None, 7.5, 60),
      ("Ponte de glúteos isométrica", 3, 40, None, 7.0, 45)], False),
    ("HIIT · 20 min peso do corpo", "hiit",
     "Trabalho curto e descanso curto, sem material. 20 min.",
     [("Burpees", 4, 30, None, 8.5, 30), ("Skaters", 4, 30, None, 8.0, 30),
      ("Mountain climbers", 4, 30, None, 8.0, 30), ("Agachamento com salto", 4, 30, None, 8.0, 30),
      ("Sprint no lugar", 4, 30, None, 8.5, 30)], False),
)

_SEEDED_KEY = "gym_catalog_workouts"


def _seeded(db: Database) -> list[str]:
    try:
        v = json.loads(db.get(_SEEDED_KEY, "[]") or "[]")
        return [str(x) for x in v]
    except (TypeError, ValueError):
        return []


def seed_workouts(db: Database, with_complexes: bool = False) -> int:
    """Põe os treinos de origem que ainda não entraram nesta base. Devolve quantos entraram."""
    from . import gym
    from . import strength as st
    if getattr(db, "_catalog_busy", False):            # `save_plan` volta a chamar `ensure`
        return 0
    done = _seeded(db)
    todo = [w for w in WORKOUTS if w[0] not in done and w[4] == with_complexes]
    if not todo:
        return 0
    by_name = {r["name"]: r["id"] for r in db.conn.execute("SELECT id, name FROM exercises")}
    have = {w["name"] for w in st.workouts(db)}
    n = 0
    db._catalog_busy = True
    try:
        n = _seed_each(db, gym, todo, by_name, have, done)
    finally:
        db._catalog_busy = False
    db.set(_SEEDED_KEY, json.dumps(done, ensure_ascii=False))
    return n


def _seed_each(db, gym, todo, by_name, have, done) -> int:
    n = 0
    for name, mod, desc, items, _cx in todo:
        rows = [{"exercise_id": by_name[e], "sets": s, "reps": r, "load_kg": ld, "rpe": rpe,
                 "rest_s": rest} for e, s, r, ld, rpe, rest in items if e in by_name]
        if len(rows) < max(2, len(items) - 1):          # faltam exercícios no catálogo: espera
            continue
        done.append(name)
        if name in have:                                # já tens um treino com este nome
            continue
        gym.save_plan(db, None, name, desc, rows, mod=mod)
        n += 1
    return n


def names() -> list[str]:
    return [w[0] for w in WORKOUTS]


def describe() -> str:
    return tr("{a} exercícios e {b} treinos de origem", "{a} built-in exercises and {b} "
              "workouts", a=len(EXERCISES), b=len(WORKOUTS))
