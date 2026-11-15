"""Os planos de X semanas que vêm com a Perennia, no formato Perennia (`programs.py`).

São **versões gerais de métodos conhecidos e publicados** (StrongLifts 5×5, Starting Strength,
5/3/1, GZCLP, Smolov Jr, Simple & Sinister…) e alguns planos de base desenhados para a
Perennia. As categorias seguem as do catálogo de programas da Capazity
(capazity.ai/programs), que serviu de referência para o que incluir; **o conteúdo de cada
plano não foi copiado de lá** (a maioria só existe na aplicação deles): as séries, as
repetições e as percentagens são as dos métodos originais, como estão descritos publicamente,
ou escolhas próprias quando o plano é da Perennia. Não são versões oficiais nem
individualizadas: ajusta as cargas ao teu nível.

Cada plano é um dicionário no formato do ficheiro; `plans()` valida-os todos uma vez.
"""
from __future__ import annotations

from functools import lru_cache

# ====================================================================== exercícios
# chave: (nome, grupo, medida, fração do peso do corpo, material, modalidade, outros nomes)
X: dict[str, tuple] = {
    # ---- os que já existem na Perennia (mesmo nome)
    "squat": ("Agachamento com barra", "legs", "reps", 0, ("barbell", "plates", "rack"),
              "strength", ("Back squat", "Squat")),
    "front_squat": ("Agachamento frontal", "legs", "reps", 0, ("barbell", "plates", "rack"),
                    "strength", ("Front squat",)),
    "goblet": ("Agachamento goblet", "legs", "reps", 0, ("kettlebell",), "strength",
               ("Goblet squat",)),
    "bulgarian": ("Agachamento búlgaro", "legs", "reps", 0, ("dumbbell", "bench"), "strength",
                  ("Bulgarian split squat",)),
    "leg_press": ("Prensa de pernas", "legs", "reps", 0, ("leg_press",), "strength",
                  ("Leg press",)),
    "lunge": ("Afundos", "legs", "reps", 0, ("dumbbell",), "strength", ("Lunge",)),
    "step_up": ("Step-up", "legs", "reps", 0, ("box",), "strength", ()),
    "leg_ext": ("Extensão de pernas", "legs", "reps", 0, ("cable",), "strength",
                ("Leg extension",)),
    "leg_curl": ("Curl femoral", "legs", "reps", 0, ("cable",), "strength", ("Leg curl",)),
    "calf": ("Elevação de gémeos", "legs", "reps", 0, ("dumbbell",), "strength",
             ("Calf raise",)),
    "deadlift": ("Peso morto", "hips", "reps", 0, ("barbell", "plates"), "strength",
                 ("Deadlift",)),
    "rdl": ("Peso morto romeno", "hips", "reps", 0, ("barbell", "plates"), "strength",
            ("Romanian deadlift", "RDL")),
    "hip_thrust": ("Hip thrust", "hips", "reps", 0, ("barbell", "plates", "bench"), "strength",
                   ()),
    "glute_bridge": ("Ponte de glúteos", "hips", "reps", 0.5, (), "strength", ("Glute bridge",)),
    "swing": ("Kettlebell swing", "hips", "reps", 0, ("kettlebell",), "kettlebell", ()),
    "hip_abduction": ("Abdução de anca (banda)", "hips", "reps", 0, ("bands",), "strength", ()),
    "back_ext": ("Hiperextensão lombar", "hips", "reps", 0.5, (), "strength",
                 ("Back extension", "Hyperextension")),
    "bench": ("Supino com barra", "chest", "reps", 0, ("barbell", "plates", "bench", "rack"),
              "strength", ("Bench press",)),
    "incline_db": ("Supino inclinado com halteres", "chest", "reps", 0, ("dumbbell", "bench"),
                   "strength", ("Incline dumbbell press",)),
    "fly": ("Aberturas com halteres", "chest", "reps", 0, ("dumbbell", "bench"), "strength",
            ("Dumbbell fly",)),
    "pushup": ("Flexões", "chest", "reps", 0.65, (), "calisthenics", ("Push-up", "Push-ups")),
    "press": ("Press militar", "shoulders", "reps", 0, ("barbell", "plates"), "strength",
              ("Overhead press", "Strict press", "OHP")),
    "db_press": ("Press de ombros com halteres", "shoulders", "reps", 0, ("dumbbell",),
                 "strength", ("Dumbbell shoulder press",)),
    "lateral": ("Elevações laterais", "shoulders", "reps", 0, ("dumbbell",), "strength",
                ("Lateral raise",)),
    "face_pull": ("Face pull", "shoulders", "reps", 0, ("cable",), "strength", ("Face pulls",)),
    "row": ("Remada com barra", "back", "reps", 0, ("barbell", "plates"), "strength",
            ("Barbell row", "Bent-over row")),
    "db_row": ("Remada com halter", "back", "reps", 0, ("dumbbell", "bench"), "strength",
               ("Dumbbell row",)),
    "cable_row": ("Remada sentada (cabo)", "back", "reps", 0, ("cable",), "strength",
                  ("Seated cable row",)),
    "pulldown": ("Puxada ao peito", "back", "reps", 0, ("cable",), "strength",
                 ("Lat pulldown",)),
    "pullup": ("Elevações (pull-ups)", "back", "reps", 1.0, ("pullup_bar",), "calisthenics",
               ("Pull-up", "Pull-ups")),
    "shrug": ("Encolhimentos", "back", "reps", 0, ("dumbbell",), "strength", ("Shrug",)),
    "curl": ("Curl de bíceps", "arms", "reps", 0, ("dumbbell",), "strength",
             ("Dumbbell curl", "Biceps curl")),
    "triceps": ("Extensão de tríceps", "arms", "reps", 0, ("dumbbell",), "strength",
                ("Triceps extension",)),
    "dips": ("Fundos (dips)", "arms", "reps", 1.0, ("parallettes",), "calisthenics", ("Dips",)),
    "plank": ("Prancha", "core", "time", 0, (), "strength", ("Plank",)),
    "side_plank": ("Prancha lateral", "core", "time", 0, (), "strength", ("Side plank",)),
    "leg_raise": ("Elevação de pernas", "core", "reps", 0, (), "strength", ("Leg raise",)),
    "hanging_raise": ("Elevação de pernas suspenso", "core", "reps", 0, ("pullup_bar",),
                      "calisthenics", ("Hanging leg raise",)),
    "dead_bug": ("Dead bug", "core", "reps", 0, (), "strength", ()),
    "pallof": ("Pallof press", "core", "reps", 0, ("bands",), "strength", ()),
    "farmer": ("Farmer's carry", "full", "time", 0, ("kettlebell",), "strength",
               ("Farmer's walk", "Farmers carry")),
    "tgu": ("Turkish get-up", "full", "reps", 0, ("kettlebell",), "kettlebell", ()),
    "kb_clean": ("Clean com kettlebell", "full", "reps", 0, ("kettlebell",), "kettlebell", ()),
    "kb_press": ("Press com kettlebell", "shoulders", "reps", 0, ("kettlebell",), "kettlebell",
                 ()),
    "kb_row": ("Remada com kettlebell", "back", "reps", 0, ("kettlebell",), "kettlebell", ()),
    "kb_snatch": ("Snatch com kettlebell", "full", "reps", 0, ("kettlebell",), "kettlebell",
                  ()),
    "halo": ("Halo", "shoulders", "reps", 0, ("kettlebell",), "kettlebell", ()),
    "hang": ("Suspensão na barra", "back", "time", 0, ("pullup_bar",), "isometric",
             ("Dead hang",)),
    "wrist_ext": ("Extensão de punho excêntrica", "arms", "reps", 0, ("dumbbell",), "tendons",
                  ()),
    "burpee": ("Burpees", "full", "reps", 0, (), "hiit", ("Burpee",)),
    "jump_squat": ("Agachamento com salto", "legs", "reps", 0, (), "plyometrics",
                   ("Jump squat",)),
    "mountain": ("Mountain climbers", "core", "time", 0, (), "hiit", ()),
    "jacks": ("Jumping jacks", "full", "time", 0, (), "hiit", ()),
    "box_jump": ("Saltos para caixa", "full", "reps", 0, ("box",), "plyometrics", ("Box jump",)),
    "broad_jump": ("Salto em comprimento", "legs", "reps", 0, (), "plyometrics",
                   ("Broad jump",)),
    "depth_jump": ("Saltos em profundidade", "legs", "reps", 0, ("box",), "plyometrics",
                   ("Depth jump",)),
    "tuck_jump": ("Tuck jumps", "legs", "reps", 0, (), "plyometrics", ()),
    "skater": ("Saltos laterais (skater)", "legs", "reps", 0, (), "plyometrics", ()),
    "rope": ("Saltos à corda", "full", "time", 0, ("jump_rope",), "plyometrics", ()),
    "monster_walk": ("Monster walk", "hips", "reps", 0, ("bands",), "bands", ()),
    "sb_clean": ("Clean com sandbag", "full", "reps", 0, ("sandbag",), "sandbag", ()),
    "sb_press": ("Press com sandbag", "shoulders", "reps", 0, ("sandbag",), "sandbag", ()),
    "sb_shoulder": ("Sandbag ao ombro", "full", "reps", 0, ("sandbag",), "sandbag", ()),
    "sb_squat": ("Bear hug squat", "legs", "reps", 0, ("sandbag",), "sandbag", ()),
    "sb_row": ("Remada com sandbag", "back", "reps", 0, ("sandbag",), "sandbag", ()),
    "sb_carry": ("Transporte de sandbag", "full", "time", 0, ("sandbag",), "sandbag", ()),
    "sb_lunge": ("Afundos com sandbag", "legs", "reps", 0, ("sandbag",), "sandbag", ()),
    "bike": ("Bicicleta (rolo)", "legs", "time", 0, ("trainer",), "cardio", ()),
    "walk": ("Caminhada rápida", "legs", "time", 0, (), "cardio", ()),
    "balance": ("Equilíbrio numa perna", "mobility", "time", 0, (), "isometric", ()),
    "sit_stand": ("Sentar e levantar", "legs", "reps", 0.6, (), "strength", ()),
    "calf_slow": ("Elevação de gémeos lenta (3-0-3)", "legs", "reps", 0.9, (), "tendons", ()),
    "hip_flexor": ("Alongamento do flexor da anca", "hips", "time", 0, (), "mobility", ()),
    "cat_camel": ("Gato-camelo", "mobility", "time", 0, (), "mobility", ()),
    # ---- novos (criados quando um plano os pede)
    "power_clean": ("Power clean", "full", "reps", 0, ("barbell", "plates"), "strength", ()),
    "push_press": ("Push press", "shoulders", "reps", 0, ("barbell", "plates"), "strength", ()),
    "sumo": ("Peso morto sumo", "hips", "reps", 0, ("barbell", "plates"), "strength",
             ("Sumo deadlift",)),
    "pause_squat": ("Agachamento com pausa", "legs", "reps", 0, ("barbell", "plates", "rack"),
                    "strength", ("Pause squat",)),
    "cg_bench": ("Supino com pega fechada", "chest", "reps", 0,
                 ("barbell", "plates", "bench", "rack"), "strength", ("Close-grip bench press",)),
    "incline_bench": ("Supino inclinado com barra", "chest", "reps", 0,
                      ("barbell", "plates", "bench", "rack"), "strength",
                      ("Incline bench press",)),
    "db_bench": ("Supino com halteres", "chest", "reps", 0, ("dumbbell", "bench"), "strength",
                 ("Dumbbell bench press",)),
    "good_morning": ("Good morning", "hips", "reps", 0, ("barbell", "plates"), "strength", ()),
    "chinup": ("Elevações em supinação (chin-ups)", "back", "reps", 1.0, ("pullup_bar",),
               "calisthenics", ("Chin-up", "Chin-ups")),
    "pushdown": ("Extensão de tríceps na polia", "arms", "reps", 0, ("cable",), "strength",
                 ("Tricep pushdown", "Triceps pushdown")),
    "hammer": ("Curl martelo", "arms", "reps", 0, ("dumbbell",), "strength", ("Hammer curl",)),
    "ab_wheel": ("Roda abdominal", "core", "reps", 0, ("ab_wheel",), "strength",
                 ("Ab wheel rollout",)),
    "woodchop": ("Woodchop no cabo", "core", "reps", 0, ("cable",), "strength",
                 ("Cable woodchop",)),
    "curl_up": ("Curl-up de McGill", "core", "reps", 0, ("mat",), "strength",
                ("McGill curl-up",)),
    "bird_dog": ("Bird dog", "core", "reps", 0, ("mat",), "strength", ()),
    "db_squat": ("Agachamento com halteres", "legs", "reps", 0, ("dumbbell",), "strength",
                 ("Dumbbell squat",)),
    "db_rdl": ("Peso morto romeno com halteres", "hips", "reps", 0, ("dumbbell",), "strength",
               ("Dumbbell RDL",)),
    "air_squat": ("Agachamento livre", "legs", "reps", 0.6, (), "calisthenics", ("Air squat",)),
    "kickback": ("Kickback de glúteo no cabo", "hips", "reps", 0, ("cable",), "strength",
                 ("Cable kickback",)),
    "sl_hip_thrust": ("Hip thrust a uma perna", "hips", "reps", 0.5, ("bench",), "strength",
                      ("Single-leg hip thrust",)),
    "suitcase": ("Suitcase carry", "core", "time", 0, ("kettlebell",), "strength", ()),
    "front_carry": ("Transporte frontal (zercher)", "full", "time", 0, ("sandbag",), "sandbag",
                    ("Zercher carry",)),
    "sled_push": ("Empurrar trenó", "legs", "time", 0, ("sled",), "strength", ("Sled push",)),
    "sled_drag": ("Arrastar trenó", "full", "time", 0, ("sled",), "strength", ("Sled drag",)),
    "pogo": ("Pogo jumps", "legs", "reps", 0, (), "plyometrics", ()),
    "cmj": ("Salto vertical (contramovimento)", "legs", "reps", 0, (), "plyometrics",
            ("Countermovement jump", "Vertical jump")),
    "bounds": ("Passadas saltadas (bounds)", "legs", "reps", 0, (), "plyometrics", ("Bounds",)),
    "gripper": ("Gripper (fechos)", "arms", "reps", 0, ("gripper",), "strength",
                ("Gripper closes",)),
    "gripper_neg": ("Gripper: negativas", "arms", "reps", 0, ("gripper",), "strength", ()),
    "gripper_hold": ("Gripper: isométrico fechado", "arms", "time", 0, ("gripper",), "isometric",
                     ()),
    "pinch": ("Pinça de discos", "arms", "time", 0, ("plates",), "isometric",
              ("Plate pinch",)),
    "wrist_roller": ("Rolo de punho", "arms", "reps", 0, ("wrist_roller",), "strength",
                     ("Wrist roller",)),
    "wrist_curl": ("Curl de punho", "arms", "reps", 0, ("dumbbell",), "strength",
                   ("Wrist curl",)),
    "thick_hold": ("Peso morto com pega grossa (segurar)", "arms", "time", 0,
                   ("barbell", "plates", "fat_grips"), "isometric", ("Thick bar hold",)),
    "finger_ext": ("Extensão de dedos com elástico", "arms", "reps", 0, ("bands",), "tendons",
                   ("Finger extensions",)),
    "towel_hang": ("Suspensão em toalha", "arms", "time", 0, ("pullup_bar",), "isometric",
                   ("Towel hang",)),
}

# ====================================================================== mini-linguagem


def ex(key: str, sets, reps=None, **kw) -> dict:
    out = {"exercise": key, "sets": sets}
    if reps is not None:
        out["reps"] = reps
    out.update(kw)
    return out


def lp(key: str, sets: int, reps: int, add: float, start: float, rest: int = 180,
       per: str = "session", track: str | None = None, **kw) -> dict:
    """Progressão linear: soma `add` kg de cada vez; a carga inicial sugere-se por `start` %."""
    out = ex(key, sets, reps, rest=rest, add_kg=add, per=per, start_pct=start, **kw)
    if track:
        out["track"] = track
    return out


def block(kind: str, exercises: list[dict], rounds: int = 1, rest: int = 60,
          notes: str = "") -> dict:
    return {"kind": kind, "rounds": rounds, "rest": rest, "notes": notes,
            "exercises": exercises}


def session(name: str, blocks: list[dict], notes: str = "") -> dict:
    return {"name": name, "notes": notes, "blocks": blocks}


def _keys(sessions: dict) -> list[str]:
    seen: list[str] = []
    for s in sessions.values():
        for b in s["blocks"]:
            for e in (b["exercises"] if "exercises" in b else [b]):
                if e["exercise"] not in seen:
                    seen.append(e["exercise"])
    return seen


def plan(name: str, category: str, level: str, weeks: int, description: str, sessions: dict,
         rotation: list[str] | None = None, schedule: list[list[str]] | None = None,
         days_per_week: int | None = None, weekdays: list[int] | None = None,
         source: str = "") -> dict:
    exercises = {}
    for k in _keys(sessions):
        n, group, measure, bw, kit, mod, aliases = X[k]
        exercises[k] = {"name": n, "group": group, "measure": measure, "bodyweight": bw,
                        "equipment": list(kit), "modality": mod, "aliases": list(aliases)}
    out = {"format": "perennia-plan", "version": 1, "name": name, "category": category,
           "level": level, "weeks": weeks, "description": description,
           "author": "Perennia", "source": source, "exercises": exercises,
           "sessions": sessions}
    if schedule is not None:
        out["schedule"] = schedule
    else:
        out["rotation"] = rotation
        out["days_per_week"] = days_per_week
    if weekdays:
        out["weekdays"] = weekdays
    return out


GENERAL = ("Versão geral do método, como está publicado; não é a versão oficial nem é "
           "individualizada.")
OWN = "Plano de base da Perennia."
ACC = dict(rpe=7, rest=90)                    # acessórios: RPE 7, 90 s


def w531(key: str) -> dict:
    """As três séries do 5/3/1 (percentagens da 1RM = 90 % do «training max»)."""
    return ex(key, [
        {"reps": [5, 3, 5, 5], "pct1rm": [58.5, 63, 67.5, 36], "rest": 180},
        {"reps": [5, 3, 3, 5], "pct1rm": [67.5, 72, 76.5, 45], "rest": 180},
        {"reps": ["5+", "3+", "1+", 5], "pct1rm": [76.5, 81, 85.5, 54], "rest": 180}],
        notes="5/3/1: semana 1 = 5/5/5+, semana 2 = 3/3/3+, semana 3 = 5/3/1+, semana 4 = "
              "descarga")


def ramp(key: str, fractions: list[float], reps: int, add: float, start: float,
         track: str | None = None, extra: list[dict] | None = None) -> dict:
    """Séries em rampa até à carga principal (frações da carga principal)."""
    sets = [{"reps": reps, "of_top": f, "rest": 150} for f in fractions] + (extra or [])
    out = {"exercise": key, "sets": sets, "add_kg": add, "per": "week", "start_pct": start}
    if track:
        out["track"] = track
    return out


# ====================================================================== os planos


def _build() -> dict[str, dict]:
    P: dict[str, dict] = {}

    # ------------------------------------------------------------------ força
    P["stronglifts_5x5"] = plan(
        "StrongLifts 5×5", "strength", "beginner", 12,
        "Três sessões por semana de corpo inteiro, a alternar o Treino A e o Treino B. Cinco "
        "séries de cinco nos exercícios principais (o peso morto é uma série de cinco), a somar "
        "2,5 kg de cada vez que o exercício volta (5 kg no peso morto). Começa leve: metade do "
        "que consegues. Se falhares as repetições três sessões seguidas, usa «Recalcular "
        "cargas» e baixa 10 %. " + GENERAL,
        {"A": session("Treino A", [lp("squat", 5, 5, 2.5, 50), lp("bench", 5, 5, 2.5, 50),
                                   lp("row", 5, 5, 2.5, 50)]),
         "B": session("Treino B", [lp("squat", 5, 5, 2.5, 50), lp("press", 5, 5, 2.5, 50),
                                   lp("deadlift", 1, 5, 5.0, 55)])},
        rotation=["A", "B"], days_per_week=3, source="Método StrongLifts 5×5 (Mehdi)")

    P["starting_strength"] = plan(
        "Starting Strength (progressão linear)", "strength", "beginner", 12,
        "Dois treinos de barra a alternar, três vezes por semana: agachamento em todas as "
        "sessões, supino e press a alternar, peso morto e power clean a alternar. Três séries "
        "de cinco (peso morto 1×5, power clean 5×3), a subir um pouco de cada vez. " + GENERAL,
        {"A": session("Treino A", [lp("squat", 3, 5, 2.5, 60), lp("bench", 3, 5, 2.5, 60),
                                   lp("deadlift", 1, 5, 5.0, 60)]),
         "B": session("Treino B", [lp("squat", 3, 5, 2.5, 60), lp("press", 3, 5, 2.5, 60),
                                   lp("power_clean", 5, 3, 2.5, 50)])},
        rotation=["A", "B"], days_per_week=3, source="Método Starting Strength (Rippetoe)")

    vol = [76, 77, 78, 79, 80, 81]
    top = [85, 86, 87.5, 89, 90, 91]
    P["texas_method"] = plan(
        "Texas Method (6 semanas)", "strength", "intermediate", 6,
        "Semana em três dias: volume (5×5), recuperação (leve) e intensidade (uma série de "
        "cinco pesada). A carga do dia de intensidade sobe todas as semanas. " + GENERAL,
        {"V": session("Volume", [ex("squat", 5, 5, pct1rm=vol, rest=240),
                                 ex("bench", 5, 5, pct1rm=vol, rest=240),
                                 ex("power_clean", 5, 3, rpe=7, rest=150)]),
         "R": session("Recuperação", [ex("squat", 2, 5, pct1rm=62, rest=150),
                                      ex("press", 3, 5, pct1rm=70, rest=150),
                                      ex("chinup", 3, "max", rest=120),
                                      ex("back_ext", 3, 10, rest=90)]),
         "I": session("Intensidade", [ex("squat", 1, 5, pct1rm=top, rest=300),
                                      ex("bench", 1, 5, pct1rm=top, rest=300),
                                      ex("deadlift", 1, 5, pct1rm=top, rest=300)])},
        schedule=[["V", "R", "I"]], source="Texas Method (Rippetoe / Pendlay)")

    r5 = [0.5, 0.625, 0.75, 0.875, 1.0]
    P["madcow_5x5"] = plan(
        "Madcow 5×5", "strength", "intermediate", 9,
        "Corpo inteiro três vezes por semana, em rampa: cinco séries de cinco a subir até à "
        "série principal. Segunda pesada, quarta leve, sexta com uma série de três acima da "
        "principal e uma de oito de recuo. A série principal sobe 2,5 kg por semana. "
        + GENERAL,
        {"M": session("Segunda (pesado)", [ramp("squat", r5, 5, 2.5, 80),
                                           ramp("bench", r5, 5, 2.5, 80),
                                           ramp("row", r5, 5, 2.5, 80)]),
         "W": session("Quarta (leve)", [ramp("squat", [0.5, 0.625, 0.75, 0.75], 5, 2.5, 80),
                                        ramp("press", r5[1:], 5, 2.5, 78),
                                        ramp("deadlift", r5[1:], 5, 2.5, 80)]),
         "F": session("Sexta (intensidade)", [
             ramp("squat", r5[:4], 5, 2.5, 80, extra=[{"reps": 3, "of_top": 1.025, "rest": 240},
                                                    {"reps": 8, "of_top": 0.75, "rest": 180}]),
             ramp("bench", r5[:4], 5, 2.5, 80, extra=[{"reps": 3, "of_top": 1.025, "rest": 240},
                                                    {"reps": 8, "of_top": 0.75, "rest": 180}]),
             ramp("row", r5[:4], 5, 2.5, 80, extra=[{"reps": 3, "of_top": 1.025, "rest": 240},
                                                  {"reps": 8, "of_top": 0.75, "rest": 180}])])},
        schedule=[["M", "W", "F"]], source="Madcow 5×5 (a partir do 5×5 de Bill Starr)")

    P["wendler_531"] = plan(
        "5/3/1 de Wendler (ciclo de 4 dias)", "strength", "intermediate", 4,
        "Um exercício principal por dia (press, peso morto, supino, agachamento) em três "
        "séries: semana 1 de cincos, semana 2 de três, semana 3 de 5/3/1, semana 4 de "
        "descarga. A última série das três primeiras semanas é «o máximo que der». As "
        "percentagens são da tua 1RM estimada, já com os 90 % do «training max». No fim do "
        "ciclo repete, e a 1RM estimada acompanha. " + GENERAL,
        {"P": session("Press", [w531("press"), ex("dips", 5, 10, **ACC),
                                ex("chinup", 5, 10, **ACC)]),
         "D": session("Peso morto", [w531("deadlift"), ex("good_morning", 5, 10, **ACC),
                                     ex("hanging_raise", 5, 12, rest=60)]),
         "B": session("Supino", [w531("bench"), ex("db_bench", 5, 12, **ACC),
                                 ex("db_row", 5, 10, **ACC)]),
         "S": session("Agachamento", [w531("squat"), ex("leg_press", 5, 12, **ACC),
                                      ex("leg_curl", 5, 10, **ACC)])},
        schedule=[["P", "D", "B", "S"]], source="5/3/1 (Jim Wendler)")

    P["russian_squat"] = plan(
        "Rotina russa de agachamento (6 semanas)", "strength", "intermediate", 6,
        "Só agachamento, três vezes por semana, por percentagens: três semanas a juntar "
        "volume a 80 % e três a subir a intensidade até 100–105 %. Usa a tua 1RM real e "
        "recente. É duro: não juntes outro trabalho pesado de pernas. " + GENERAL,
        {"D1": session("Dia 1", [ex("squat", [6, 6, 6, 5, 6, 2], [2, 4, 2, 5, 2, 2],
                                    pct1rm=[80, 80, 80, 85, 80, 100], rest=240)]),
         "D2": session("Dia 2", [ex("squat", [6, 6, 6, 6, 3, 6], [3, 2, 6, 2, 3, 2],
                                    pct1rm=[80, 80, 80, 80, 95, 80], rest=240)]),
         "D3": session("Dia 3", [ex("squat", [6, 6, 6, 4, 6, 1], [2, 5, 2, 4, 2, 1],
                                    pct1rm=[80, 80, 80, 90, 80, 105], rest=240)])},
        schedule=[["D1", "D2", "D3"]], source="Russian Squat Routine")

    jr = [0, 2.5, 5]
    P["smolov_jr_bench"] = plan(
        "Smolov Jr (supino, 3 semanas)", "strength", "intermediate", 3,
        "Especialização de supino em três semanas, quatro dias por semana: 6×6, 7×5, 8×4 e "
        "10×3, com as percentagens a subir todas as semanas. Não treines os empurrões pesados "
        "noutros dias. " + GENERAL,
        {"D1": session("6 × 6", [ex("bench", 6, 6, pct1rm=[70 + j for j in jr], rest=180)]),
         "D2": session("7 × 5", [ex("bench", 7, 5, pct1rm=[75 + j for j in jr], rest=180)]),
         "D3": session("8 × 4", [ex("bench", 8, 4, pct1rm=[80 + j for j in jr], rest=210)]),
         "D4": session("10 × 3", [ex("bench", 10, 3, pct1rm=[85 + j for j in jr], rest=210)])},
        schedule=[["D1", "D2", "D3", "D4"]], source="Smolov Jr")

    up = [65, 67.5, 70, 72.5, 75, 77.5, 80, 80]
    P["base_full_body"] = plan(
        "Força de base (corpo inteiro)", "strength", "beginner", 8,
        "Oito semanas, três dias, todos os padrões de movimento em cada sessão: agachar, "
        "dobrar a anca, empurrar, puxar e estabilizar. As percentagens sobem devagar; os "
        "acessórios ficam a RPE 7 (2–3 repetições em reserva). " + OWN,
        {"A": session("Corpo inteiro A", [
            ex("squat", 3, [6, 6, 6, 5, 5, 5, 5, 5], pct1rm=up, rest=180),
            ex("bench", 3, [8, 8, 8, 6, 6, 6, 5, 5], pct1rm=up, rest=150),
            ex("row", 3, 8, pct1rm=[65, 65, 67.5, 70, 70, 72.5, 75, 75], rest=120),
            ex("db_press", 2, "8-10", **ACC), ex("plank", 3, time=40, rest=45)]),
         "B": session("Corpo inteiro B", [
             ex("rdl", 3, 8, pct1rm=[60, 62.5, 65, 67.5, 70, 70, 72.5, 72.5], rest=150),
             ex("front_squat", 3, 6, pct1rm=[60, 62.5, 65, 65, 67.5, 70, 70, 72.5], rest=150),
             ex("incline_db", 3, "8-10", **ACC), ex("pulldown", 3, "8-10", **ACC),
             ex("face_pull", 2, "12-15", rpe=7, rest=60), ex("curl", 2, "10-12", rpe=7, rest=60)]),
         "C": session("Corpo inteiro C", [
             ex("hip_thrust", 3, 8, pct1rm=up, rest=150),
             ex("squat", 2, 8, pct1rm=[60, 60, 62.5, 62.5, 65, 65, 67.5, 67.5], rest=150),
             ex("press", 3, 6, pct1rm=up, rest=150), ex("db_row", 3, "8-10", **ACC),
             ex("calf", 3, "10-12", rpe=7, rest=60), ex("side_plank", 2, time=30, rest=30)])},
        schedule=[["A", "B", "C"]])

    # ------------------------------------------------------------------ powerlifting
    def t3(key):
        return ex(key, [{"reps": 15, "rpe": 7, "rest": 60}, {"reps": 15, "rpe": 7, "rest": 60},
                        {"reps": "15+", "rpe": 8, "rest": 60}])
    P["gzclp"] = plan(
        "GZCLP (progressão linear)", "powerlifting", "beginner", 12,
        "Quatro sessões em rotação (A1, B1, A2, B2), cada uma com três níveis: T1 pesado "
        "(5×3, a última série é o máximo), T2 de volume (3×10) e T3 acessório (3×15+). O T1 e "
        "o T2 sobem de cada vez que voltam. " + GENERAL,
        {"A1": session("A1", [lp("squat", 5, 3, 2.5, 80, 210, track="squat_t1"),
                              lp("bench", 3, 10, 2.5, 60, 150, track="bench_t2"),
                              t3("pulldown")]),
         "B1": session("B1", [lp("press", 5, 3, 2.5, 80, 210, track="press_t1"),
                              lp("deadlift", 3, 10, 2.5, 60, 150, track="deadlift_t2"),
                              t3("db_row")]),
         "A2": session("A2", [lp("bench", 5, 3, 2.5, 80, 210, track="bench_t1"),
                              lp("squat", 3, 10, 2.5, 60, 150, track="squat_t2"),
                              t3("pulldown")]),
         "B2": session("B2", [lp("deadlift", 5, 3, 5.0, 80, 210, track="deadlift_t1"),
                              lp("press", 3, 10, 2.5, 60, 150, track="press_t2"),
                              t3("db_row")])},
        rotation=["A1", "B1", "A2", "B2"], days_per_week=4, source="GZCLP (Cody Lefever)")

    hv = [58, 60, 62, 64, 64, 64, 64, 64]
    hi = [80, 80, 80, 80, 80, 85, 90, 95]
    P["korte_3x3"] = plan(
        "Korte 3×3", "powerlifting", "intermediate", 8,
        "Só os três levantamentos, três vezes por semana. Quatro semanas de volume (5–6 séries "
        "de 5–6 a 58–64 %) e quatro de intensidade: 3×3 a 60 % e, em cada dia, um dos "
        "levantamentos com singles pesados a subir de 80 a 95 %. " + GENERAL,
        {"V": session("Volume", [ex("squat", 5, 5, pct1rm=hv, rest=180),
                                 ex("bench", 6, 6, pct1rm=hv, rest=150),
                                 ex("deadlift", 5, 5, pct1rm=hv, rest=180)]),
         "H1": session("Agachamento pesado", [
             ex("squat", [{"reps": 3, "pct1rm": 60}, {"reps": 3, "pct1rm": 60},
                          {"reps": 1, "pct1rm": hi, "rest": 300},
                          {"reps": 1, "pct1rm": hi, "rest": 300}]),
             ex("bench", 3, 3, pct1rm=60, rest=150), ex("deadlift", 3, 3, pct1rm=60, rest=180)]),
         "H2": session("Supino pesado", [
             ex("squat", 3, 3, pct1rm=60, rest=180),
             ex("bench", [{"reps": 3, "pct1rm": 60}, {"reps": 3, "pct1rm": 60},
                          {"reps": 1, "pct1rm": hi, "rest": 300},
                          {"reps": 1, "pct1rm": hi, "rest": 300}]),
             ex("deadlift", 3, 3, pct1rm=60, rest=180)]),
         "H3": session("Peso morto pesado", [
             ex("squat", 3, 3, pct1rm=60, rest=180), ex("bench", 3, 3, pct1rm=60, rest=150),
             ex("deadlift", [{"reps": 3, "pct1rm": 60}, {"reps": 3, "pct1rm": 60},
                             {"reps": 1, "pct1rm": hi, "rest": 300},
                             {"reps": 1, "pct1rm": hi, "rest": 300}])])},
        schedule=[["V", "V", "V"]] * 4 + [["H1", "H2", "H3"]] * 4,
        source="Korte 3×3 (Stephan Korte)")

    pl = [70, 72.5, 75, 77.5, 80, 85]
    P["powerlifting_linear"] = plan(
        "Powerlifting linear (iniciação à competição)", "powerlifting", "intermediate", 6,
        "Agachamento, supino e peso morto de competição em progressão linear durante seis "
        "semanas, a chegar a séries de três a 85 % na última. " + OWN,
        {"A": session("Agachamento + supino", [
            ex("squat", [4, 4, 4, 4, 3, 3], [5, 5, 5, 4, 4, 3], pct1rm=pl, rest=240),
            ex("bench", [4, 4, 4, 4, 3, 3], [5, 5, 5, 4, 4, 3], pct1rm=pl, rest=210),
            ex("row", 3, 8, **ACC)]),
         "B": session("Peso morto + press", [
             ex("deadlift", [3, 3, 3, 3, 3, 2], [5, 5, 4, 4, 3, 3], pct1rm=pl, rest=270),
             ex("press", 3, 6, rpe=7, rest=150), ex("pulldown", 3, 10, **ACC),
             ex("plank", 3, time=45, rest=45)]),
         "C": session("Agachamento leve + supino pesado", [
             ex("pause_squat", 3, 4, pct1rm=[60, 62.5, 65, 65, 67.5, 70], rest=180),
             ex("bench", [5, 5, 5, 4, 4, 3], [3, 3, 3, 3, 2, 2],
                pct1rm=[77.5, 80, 82.5, 85, 87.5, 90], rest=240),
             ex("cg_bench", 3, 8, **ACC), ex("back_ext", 3, 12, rest=60)])},
        schedule=[["A", "B", "C"]])

    # ------------------------------------------------------------------ hipertrofia
    hyp = dict(rpe=8, rest=90)
    P["ppl_6day"] = plan(
        "Push / Pull / Legs (6 dias)", "bodybuilding", "intermediate", 8,
        "Empurrar, puxar e pernas, duas voltas por semana: cada grupo muscular duas vezes. "
        "Dupla progressão: quando chegares ao topo do intervalo de repetições em todas as "
        "séries, sobe a carga. " + GENERAL,
        {"PUSH": session("Empurrar", [ex("bench", 4, "6-8", rpe=8, rest=150),
                                      ex("db_press", 3, "8-10", **hyp),
                                      ex("incline_db", 3, "8-12", **hyp),
                                      ex("lateral", 4, "12-15", rpe=8, rest=60),
                                      ex("pushdown", 3, "10-12", rpe=8, rest=60),
                                      ex("triceps", 2, "12-15", rpe=8, rest=60)]),
         "PULL": session("Puxar", [ex("row", 4, "6-8", rpe=8, rest=150),
                                   ex("pullup", 3, "6-10", **hyp),
                                   ex("cable_row", 3, "8-12", **hyp),
                                   ex("face_pull", 3, "12-15", rpe=8, rest=60),
                                   ex("curl", 3, "10-12", rpe=8, rest=60),
                                   ex("hammer", 2, "12-15", rpe=8, rest=60)]),
         "LEGS": session("Pernas", [ex("squat", 4, "6-8", rpe=8, rest=180),
                                    ex("rdl", 3, "8-10", rpe=8, rest=150),
                                    ex("leg_press", 3, "10-12", **hyp),
                                    ex("leg_curl", 3, "10-12", rpe=8, rest=75),
                                    ex("leg_ext", 2, "12-15", rpe=8, rest=60),
                                    ex("calf", 4, "10-15", rpe=8, rest=60)])},
        schedule=[["PUSH", "PULL", "LEGS", "PUSH", "PULL", "LEGS"]],
        source="Divisão Push/Pull/Legs")

    P["upper_lower"] = plan(
        "Upper / Lower (4 dias)", "bodybuilding", "intermediate", 8,
        "Tronco e pernas, duas vezes cada por semana: um dia mais pesado (4–8 repetições) e "
        "um de mais volume (8–15). Dupla progressão. " + GENERAL,
        {"U1": session("Tronco (pesado)", [ex("bench", 4, "4-6", rpe=8, rest=180),
                                           ex("row", 4, "5-8", rpe=8, rest=150),
                                           ex("press", 3, "6-8", rpe=8, rest=150),
                                           ex("pullup", 3, "6-10", **hyp),
                                           ex("curl", 2, "8-12", rpe=8, rest=60),
                                           ex("pushdown", 2, "8-12", rpe=8, rest=60)]),
         "L1": session("Pernas (pesado)", [ex("squat", 4, "4-6", rpe=8, rest=210),
                                           ex("rdl", 3, "6-8", rpe=8, rest=180),
                                           ex("leg_press", 3, "8-10", **hyp),
                                           ex("leg_curl", 3, "8-10", rpe=8, rest=75),
                                           ex("calf", 4, "8-12", rpe=8, rest=60)]),
         "U2": session("Tronco (volume)", [ex("incline_db", 4, "8-12", **hyp),
                                           ex("pulldown", 4, "8-12", **hyp),
                                           ex("db_press", 3, "10-12", **hyp),
                                           ex("cable_row", 3, "10-12", **hyp),
                                           ex("lateral", 3, "12-15", rpe=8, rest=60),
                                           ex("hammer", 2, "12-15", rpe=8, rest=60),
                                           ex("triceps", 2, "12-15", rpe=8, rest=60)]),
         "L2": session("Pernas (volume)", [ex("front_squat", 3, "8-10", rpe=8, rest=150),
                                           ex("hip_thrust", 3, "10-12", **hyp),
                                           ex("bulgarian", 3, "10-12", **hyp),
                                           ex("leg_ext", 3, "12-15", rpe=8, rest=60),
                                           ex("leg_curl", 3, "12-15", rpe=8, rest=60),
                                           ex("hanging_raise", 3, "10-15", rest=60)])},
        schedule=[["U1", "L1", "U2", "L2"]], weekdays=[1, 2, 4, 5],
        source="Divisão Upper/Lower")

    P["gvt_10x10"] = plan(
        "German Volume Training (10 × 10)", "bodybuilding", "intermediate", 6,
        "Dez séries de dez a 60 % no exercício principal, com 60–90 s de descanso, em pares "
        "de músculos opostos. Sobe a carga 4–5 % quando fizeres os 10×10 completos. " + GENERAL,
        {"D1": session("Peito e costas", [
            block("superset", [ex("bench", 10, 10, pct1rm=60), ex("row", 10, 10, pct1rm=60)],
                  rest=90),
            ex("fly", 3, "10-12", rpe=7, rest=60), ex("pulldown", 3, "10-12", rpe=7, rest=60)]),
         "D2": session("Pernas e abdominais", [
             block("superset", [ex("squat", 10, 10, pct1rm=60), ex("leg_curl", 10, 10, rpe=7)],
                   rest=90),
             ex("calf", 3, "15-20", rpe=7, rest=60), ex("hanging_raise", 3, "15-20", rest=60)]),
         "D3": session("Braços e ombros", [
             block("superset", [ex("dips", 10, 10, rpe=7), ex("hammer", 10, 10, rpe=7)],
                   rest=90),
             ex("lateral", 3, "10-12", rpe=7, rest=60),
             ex("face_pull", 3, "10-12", rpe=7, rest=60)])},
        schedule=[["D1", "D2", "D3"]], source="German Volume Training")

    def bbb(key):
        return ex(key, 5, 10, pct1rm=[45, 45, 50, 40], rest=90,
                  notes="Boring But Big: 5×10 leves")
    P["531_bbb"] = plan(
        "5/3/1 Boring But Big", "bodybuilding", "intermediate", 4,
        "O 5/3/1 com cinco séries de dez leves do mesmo exercício a seguir às séries "
        "principais: força e volume no mesmo ciclo de quatro semanas. " + GENERAL,
        {"P": session("Press", [w531("press"), bbb("press"), ex("chinup", 5, 10, **ACC)]),
         "D": session("Peso morto", [w531("deadlift"), bbb("deadlift"),
                                     ex("hanging_raise", 5, 12, rest=60)]),
         "B": session("Supino", [w531("bench"), bbb("bench"), ex("db_row", 5, 10, **ACC)]),
         "S": session("Agachamento", [w531("squat"), bbb("squat"),
                                      ex("leg_curl", 5, 10, **ACC)])},
        schedule=[["P", "D", "B", "S"]], source="5/3/1 Boring But Big (Jim Wendler)")

    # ------------------------------------------------------------------ strongman
    car = [30, 30, 40, 40, 50, 50]
    P["loaded_carry"] = plan(
        "Transportes com carga", "strongman", "intermediate", 6,
        "Três dias à volta dos transportes pesados e da estabilidade do tronco: farmer's "
        "carry, suitcase carry e transporte frontal, com um levantamento de base em cada dia. "
        "O tempo de cada transporte cresce de duas em duas semanas. " + OWN,
        {"A": session("Farmer's + peso morto", [ex("deadlift", 4, 5, rpe=7, rest=210),
                                                ex("farmer", 5, time=car, rest=90),
                                                ex("db_row", 3, "8-10", **ACC),
                                                ex("plank", 3, time=45, rest=45)]),
         "B": session("Suitcase + press", [ex("press", 4, 6, rpe=7, rest=150),
                                           ex("suitcase", 6, time=car, rest=75,
                                              notes="3 de cada lado"),
                                           ex("pullup", 3, "5-8", **ACC),
                                           ex("side_plank", 3, time=30, rest=30)]),
         "C": session("Frontal + agachamento", [ex("front_squat", 4, 5, rpe=7, rest=180),
                                                ex("front_carry", 5, time=car, rest=90),
                                                ex("sb_shoulder", 4, 6, rest=90),
                                                ex("hang", 3, time=30, rest=60)])},
        schedule=[["A", "B", "C"]])

    P["sandbag_strength"] = plan(
        "Força com sandbag", "strongman", "intermediate", 6,
        "Seis semanas só com um sandbag: levantar do chão, pôr ao ombro, agachar abraçado, "
        "empurrar acima da cabeça, remar e transportar. As repetições sobem de duas em duas "
        "semanas; quando ficarem fáceis, enche mais o saco. " + OWN,
        {"A": session("Levantar e carregar", [
            ex("sb_shoulder", 5, [4, 4, 5, 5, 6, 6], rest=120, notes="alterna o ombro"),
            ex("sb_squat", 4, [6, 6, 8, 8, 10, 10], rest=120),
            ex("sb_row", 4, [8, 8, 10, 10, 12, 12], rest=90),
            ex("sb_carry", 4, time=[30, 30, 40, 40, 50, 50], rest=90)]),
         "B": session("Empurrar e afundar", [
             ex("sb_clean", 5, [5, 5, 6, 6, 8, 8], rest=120),
             ex("sb_press", 4, [5, 5, 6, 6, 8, 8], rest=120),
             ex("sb_lunge", 3, [8, 8, 10, 10, 12, 12], rest=90),
             ex("front_carry", 4, time=[30, 30, 40, 40, 50, 50], rest=90)]),
         "C": session("Circuito", [
             block("circuit", [ex("sb_clean", 1, 6), ex("sb_press", 1, 6), ex("sb_squat", 1, 8),
                               ex("sb_row", 1, 10), ex("sb_carry", 1, time=30)],
                   rounds=4, rest=120, notes="uma volta sem pousar o saco, se der")])},
        schedule=[["A", "B", "C"]])

    # ------------------------------------------------------------------ força de mãos
    P["grip_block"] = plan(
        "Bloco de força de mãos", "grip", "intermediate", 8,
        "Três sessões curtas por semana, uma para cada tipo de força de mãos: fechar "
        "(gripper), aguentar (suspensões e transportes) e pinçar/punhos. O volume sobe nas "
        "primeiras seis semanas e desce nas duas últimas, para testares. As mãos recuperam "
        "devagar: se os dedos ou os cotovelos doerem, salta uma sessão. " + OWN,
        {"A": session("Fechar (crush)", [
            ex("gripper", [3, 3, 4, 4, 5, 5, 3, 3], [8, 8, 8, 6, 6, 5, 5, 3], rest=90,
               notes="um gripper que feches 8–10 vezes"),
            ex("gripper_neg", [2, 2, 3, 3, 3, 3, 2, 1], 3, rest=120,
               notes="fecha com ajuda e resiste 5 s a abrir"),
            ex("gripper_hold", 3, time=[8, 8, 10, 10, 12, 12, 10, 10], rest=90),
            ex("finger_ext", 3, 20, rest=45)]),
         "B": session("Aguentar (suporte)", [
             ex("hang", 4, time=[25, 30, 35, 40, 45, 50, 40, 60], rest=90),
             ex("farmer", 4, time=[30, 30, 40, 40, 50, 50, 40, 40], rest=90),
             ex("thick_hold", 3, time=[10, 10, 12, 12, 15, 15, 12, 12], rest=120),
             ex("wrist_ext", 3, 12, rest=60)]),
         "C": session("Pinçar e punhos", [
             ex("pinch", 4, time=[15, 15, 20, 20, 25, 25, 20, 30], rest=90,
                notes="dois discos, lado liso para fora"),
             ex("wrist_roller", 3, [2, 2, 3, 3, 3, 4, 3, 2], rest=90,
                notes="uma repetição = subir e descer"),
             ex("wrist_curl", 3, "12-15", rpe=7, rest=60),
             ex("finger_ext", 3, 20, rest=45)])},
        schedule=[["A", "B", "C"]])

    P["grip_minimal"] = plan(
        "Força de mãos com pouco material", "grip", "beginner", 4,
        "Quatro semanas, duas sessões, só com uma barra de elevações, uma toalha e halteres "
        "ou kettlebells: bom para começar, para viagem, ou para juntar a outro plano. " + OWN,
        {"A": session("Suspensões", [ex("hang", 4, time=[20, 25, 30, 35], rest=90),
                                     ex("towel_hang", 3, time=[10, 12, 15, 18], rest=90),
                                     ex("wrist_curl", 3, 15, rpe=7, rest=60),
                                     ex("finger_ext", 3, 20, rest=45)]),
         "B": session("Transportes", [ex("farmer", 5, time=[30, 35, 40, 45], rest=90),
                                      ex("suitcase", 4, time=[20, 25, 30, 30], rest=60,
                                         notes="2 de cada lado"),
                                      ex("wrist_ext", 3, 12, rest=60),
                                      ex("finger_ext", 3, 20, rest=45)])},
        schedule=[["A", "B"]])

    # ------------------------------------------------------------------ longevidade
    P["simple_sinister"] = plan(
        "Simple & Sinister", "longevity", "beginner", 6,
        "Trinta minutos, quase todos os dias: 100 swings (10×10, a uma mão quando der) e 10 "
        "Turkish get-ups (5 de cada lado), sempre com folga — acabas melhor do que começaste. "
        "Sobe o peso do kettlebell só quando a sessão ficar fácil. " + GENERAL,
        {"S": session("Swings e get-ups", [
            ex("halo", 2, 5, rest=20, notes="aquecimento, para cada lado"),
            ex("goblet", 2, 5, rest=30, notes="aquecimento, com pausa em baixo"),
            ex("swing", 10, 10, rest=60, notes="descansa até a respiração acalmar"),
            ex("tgu", 10, 1, rest=45, notes="alterna o lado")])},
        rotation=["S"], days_per_week=6, source="Simple & Sinister (Pavel Tsatsouline)")

    P["easy_strength"] = plan(
        "Easy Strength", "longevity", "beginner", 8,
        "Os mesmos cinco movimentos cinco dias por semana, com pouco volume e sempre longe da "
        "falha: duas séries de cinco, um transporte e um abdominal. Quarenta sessões fáceis; a "
        "carga sobe quando te apetecer. " + GENERAL,
        {"E": session("Easy Strength", [ex("deadlift", 2, 5, rpe=6, rest=150),
                                        ex("press", 2, 5, rpe=6, rest=120),
                                        ex("pullup", 2, 5, rpe=6, rest=120),
                                        ex("farmer", 2, time=40, rest=90),
                                        ex("ab_wheel", 1, 10, rest=60)])},
        rotation=["E"], days_per_week=5, source="Easy Strength (Dan John / Pavel)")

    P["grease_the_groove"] = plan(
        "Greasing the Groove", "longevity", "intermediate", 4,
        "Muitas séries fáceis espalhadas pelo dia, todos os dias: cada série com metade das "
        "repetições que consegues, nunca perto da falha. Aqui com elevações e flexões; regista "
        "as séries à medida que as fazes ao longo do dia. " + GENERAL,
        {"G": session("Ao longo do dia", [
            ex("pullup", [5, 6, 6, 7], "max", rest=600,
               notes="cada série = metade do teu máximo; pelo menos 10–15 min entre séries"),
            ex("pushup", [5, 6, 6, 7], "max", rest=600,
               notes="cada série = metade do teu máximo")])},
        rotation=["G"], days_per_week=7, source="Greasing the Groove (Pavel Tsatsouline)")

    P["mcgill_big3"] = plan(
        "Big 3 de McGill + força", "longevity", "beginner", 6,
        "As três estabilizações da coluna (curl-up, prancha lateral, bird dog) em pirâmide "
        "descendente de isometrias de 10 s, seguidas de força amiga das costas. Se tens dor "
        "lombar, fala primeiro com um profissional de saúde. " + GENERAL,
        {"A": session("Big 3 + pernas", [
            ex("curl_up", [{"reps": 6}, {"reps": 4}, {"reps": 2}], rest=30,
               notes="cada repetição = 10 s"),
            ex("side_plank", 3, time=10, rest=20, notes="6-4-2 repetições de 10 s por lado"),
            ex("bird_dog", [{"reps": 6}, {"reps": 4}, {"reps": 2}], rest=30,
               notes="cada repetição = 10 s, por lado"),
            ex("goblet", 3, "8-10", **ACC), ex("glute_bridge", 3, 12, rest=60),
            ex("suitcase", 4, time=30, rest=60)]),
         "B": session("Big 3 + tronco", [
             ex("curl_up", [{"reps": 6}, {"reps": 4}, {"reps": 2}], rest=30,
                notes="cada repetição = 10 s"),
             ex("side_plank", 3, time=10, rest=20, notes="6-4-2 repetições de 10 s por lado"),
             ex("bird_dog", [{"reps": 6}, {"reps": 4}, {"reps": 2}], rest=30,
                notes="cada repetição = 10 s, por lado"),
             ex("pushup", 3, "8-12", rest=90), ex("db_row", 3, "8-10", **ACC),
             ex("farmer", 4, time=30, rest=60)])},
        rotation=["A", "B"], days_per_week=3, source="Big 3 (Stuart McGill)")

    P["minimalist_2x"] = plan(
        "Manutenção minimalista (2× por semana)", "longevity", "beginner", 8,
        "Duas sessões de trinta minutos de corpo inteiro: o mínimo que mantém a força. Bom "
        "para épocas de muito volume noutros desportos. " + OWN,
        {"A": session("A", [ex("squat", 3, "5-8", rpe=7, rest=150),
                            ex("bench", 3, "5-8", rpe=7, rest=150),
                            ex("db_row", 3, "8-10", **ACC), ex("plank", 2, time=45, rest=45)]),
         "B": session("B", [ex("deadlift", 3, 5, rpe=7, rest=180),
                            ex("press", 3, "5-8", rpe=7, rest=150),
                            ex("pullup", 3, "5-8", **ACC), ex("farmer", 3, time=40, rest=75)])},
        schedule=[["A", "B"]])

    P["centenarian_base"] = plan(
        "Bases do decatlo do centenário", "longevity", "intermediate", 12,
        "Quatro dias por semana para as capacidades que mais contam para envelhecer bem: "
        "duas sessões de força (com mãos e estabilidade), uma de Zona 2 e uma de VO2máx. Os "
        "blocos de cardio fazem-se no rolo; podes trocá-los por uma sessão de ciclismo, "
        "corrida ou remo da Perennia e marcar esta como feita. " + OWN,
        {"F1": session("Força: pernas e mãos", [
            ex("goblet", 3, "8-10", **ACC), ex("rdl", 3, "8-10", rpe=7, rest=120),
            ex("step_up", 3, 10, rest=75, notes="por perna"),
            ex("hang", 3, time=[20, 20, 25, 25, 30, 30, 35, 35, 40, 40, 45, 45], rest=75),
            ex("farmer", 3, time=40, rest=75), ex("balance", 2, time=30, rest=20)]),
         "Z2": session("Zona 2", [
             ex("bike", 1, time=[1800, 1800, 2100, 2100, 2400, 2400, 2700, 2700, 3000, 3000,
                                 3300, 3600], notes="ritmo de conversa (Zona 2)")]),
         "F2": session("Força: tronco e estabilidade", [
             ex("pushup", 3, "8-12", rest=90), ex("db_row", 3, "8-10", **ACC),
             ex("db_press", 3, "8-10", **ACC), ex("sit_stand", 2, 12, rest=60),
             ex("side_plank", 2, time=30, rest=30), ex("calf_slow", 3, 10, rest=60)]),
         "VO2": session("VO2máx", [
             ex("bike", 1, time=600, notes="aquecimento progressivo"),
             ex("bike", [3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 4, 4], time=240, rest=240,
                notes="4 min fortes (não consegues falar), 4 min muito leves"),
             ex("bike", 1, time=300, notes="retorno à calma")])},
        schedule=[["F1", "Z2", "F2", "VO2"]], weekdays=[1, 2, 4, 6])

    # ------------------------------------------------------------------ forma geral
    P["full_body_3day"] = plan(
        "Corpo inteiro 3× (manutenção)", "general", "beginner", 8,
        "A rotina por omissão para te manteres em forma: três dias, corpo inteiro, 45 minutos. "
        + OWN,
        {"A": session("A", [ex("squat", 3, "6-8", rpe=7, rest=150),
                            ex("bench", 3, "6-8", rpe=7, rest=150),
                            ex("cable_row", 3, "8-10", **ACC), ex("plank", 3, time=40, rest=45)]),
         "B": session("B", [ex("rdl", 3, "8-10", rpe=7, rest=150),
                            ex("db_press", 3, "8-10", **ACC), ex("pulldown", 3, "8-10", **ACC),
                            ex("lunge", 2, 10, rest=75, notes="por perna")]),
         "C": session("C", [ex("goblet", 3, "10-12", **ACC), ex("pushup", 3, "max", rest=90),
                            ex("db_row", 3, "8-10", **ACC), ex("farmer", 3, time=40, rest=75)])},
        schedule=[["A", "B", "C"]])

    P["home_dumbbells"] = plan(
        "Em casa só com halteres", "general", "beginner", 8,
        "Corpo inteiro três vezes por semana só com um par de halteres (de preferência "
        "ajustáveis): sem barra e sem máquinas. Dupla progressão: mais repetições primeiro, "
        "mais carga depois. " + OWN,
        {"A": session("A", [ex("db_squat", 3, "10-12", **ACC), ex("db_bench", 3, "8-12", **ACC),
                            ex("db_row", 3, "8-12", **ACC), ex("plank", 3, time=40, rest=45)]),
         "B": session("B", [ex("db_rdl", 3, "10-12", **ACC), ex("db_press", 3, "8-12", **ACC),
                            ex("lunge", 3, 10, rest=75, notes="por perna"),
                            ex("curl", 2, "10-12", rpe=7, rest=60),
                            ex("triceps", 2, "10-12", rpe=7, rest=60)]),
         "C": session("C", [ex("bulgarian", 3, "8-10", **ACC), ex("pushup", 3, "max", rest=90),
                            ex("db_row", 3, "8-12", **ACC), ex("calf", 3, "12-15", rpe=7, rest=60),
                            ex("side_plank", 2, time=30, rest=30)])},
        schedule=[["A", "B", "C"]])

    # ------------------------------------------------------------------ condicionamento
    P["bodyweight_conditioning"] = plan(
        "Condicionamento só com o corpo", "conditioning", "beginner", 4,
        "Circuitos sem material, quatro vezes por semana, em qualquer lado. As voltas sobem "
        "ao longo das quatro semanas. " + OWN,
        {"A": session("Circuito A", [block("circuit", [
            ex("air_squat", 1, 15), ex("pushup", 1, 10), ex("mountain", 1, time=30),
            ex("glute_bridge", 1, 15), ex("jacks", 1, time=40)], rounds=3, rest=60,
            notes="semana 1: 3 voltas · 2 e 3: 4 voltas · 4: 5 voltas")]),
         "B": session("Circuito B", [block("circuit", [
             ex("burpee", 1, 8), ex("lunge", 1, 12), ex("plank", 1, time=40),
             ex("jump_squat", 1, 10), ex("dead_bug", 1, 12)], rounds=3, rest=75,
             notes="semana 1: 3 voltas · 2 e 3: 4 voltas · 4: 5 voltas")])},
        rotation=["A", "B"], days_per_week=4)

    P["kettlebell_complex"] = plan(
        "Complexos de kettlebell", "conditioning", "intermediate", 6,
        "Trinta minutos, um kettlebell: complexos feitos de seguida, sem pousar, com descanso "
        "só entre voltas. As repetições por movimento sobem de duas em duas semanas. " + OWN,
        {"A": session("Complexo A", [
            ex("halo", 2, 5, rest=20, notes="aquecimento"),
            block("circuit", [ex("swing", 1, [8, 8, 10, 10, 12, 12]),
                              ex("kb_clean", 1, [5, 5, 6, 6, 8, 8]),
                              ex("kb_press", 1, [5, 5, 6, 6, 8, 8]),
                              ex("goblet", 1, [6, 6, 8, 8, 10, 10])], rounds=5, rest=90,
                  notes="de cada lado nos movimentos a uma mão")]),
         "B": session("Complexo B", [
             ex("halo", 2, 5, rest=20, notes="aquecimento"),
             block("circuit", [ex("kb_snatch", 1, [5, 5, 6, 6, 8, 8]),
                               ex("kb_row", 1, [6, 6, 8, 8, 10, 10]),
                               ex("goblet", 1, [6, 6, 8, 8, 10, 10]),
                               ex("swing", 1, [10, 10, 12, 12, 15, 15])], rounds=5, rest=90),
             ex("tgu", 2, 1, rest=45, notes="por lado")])},
        rotation=["A", "B"], days_per_week=4)

    # ------------------------------------------------------------------ atlético
    P["plyo_progression"] = plan(
        "Progressão de pliometria", "athletic", "intermediate", 6,
        "De saltos baixos e muitos (extensivos) para saltos altos e poucos (intensivos), com "
        "saltos em profundidade só nas duas últimas semanas. Faz fresco, com descanso "
        "completo, em piso que amorteça. Se tens dor nos tendões, não é este o plano. " + OWN,
        {"A": session("Verticais", [
            ex("pogo", 3, [20, 20, 20, 15, 15, 10], rest=60),
            ex("cmj", [3, 3, 4, 4, 5, 5], 5, rest=90, notes="máxima intenção em cada salto"),
            ex("box_jump", [3, 3, 4, 4, 4, 3], [5, 5, 4, 4, 3, 3], rest=90),
            ex("depth_jump", [1, 1, 1, 1, 3, 4], [3, 3, 3, 3, 4, 4], rest=120,
               notes="só conta a partir da semana 5; antes, 1×3 de uma caixa baixa")]),
         "B": session("Horizontais e laterais", [
             ex("rope", 3, time=[40, 40, 45, 45, 30, 30], rest=45),
             ex("broad_jump", [3, 3, 4, 4, 5, 5], [4, 4, 4, 3, 3, 3], rest=90),
             ex("skater", 3, [10, 10, 12, 12, 8, 8], rest=60),
             ex("bounds", [2, 2, 3, 3, 4, 4], [6, 6, 6, 8, 8, 8], rest=90),
             ex("tuck_jump", [2, 2, 3, 3, 3, 3], [6, 6, 6, 5, 5, 5], rest=75)]),
         "C": session("Força de apoio", [
             ex("squat", 4, [5, 5, 4, 4, 3, 3], pct1rm=[70, 72.5, 75, 77.5, 80, 82.5], rest=180),
             ex("jump_squat", 4, 5, rest=90, notes="leve e rápido"),
             ex("calf_slow", 3, 10, rest=60), ex("plank", 3, time=45, rest=45)])},
        schedule=[["A", "C", "B"]])

    # ------------------------------------------------------------------ glúteos
    P["glute_builder"] = plan(
        "Bloco de glúteos", "glutes", "intermediate", 8,
        "Hip thrust e peso morto romeno duas vezes por semana (um dia pesado, um de volume), "
        "trabalho a uma perna e um final de bombeamento com elásticos. " + OWN,
        {"A": session("Hip thrust pesado", [ex("hip_thrust", 4, "5-8", rpe=8, rest=150),
                                            ex("bulgarian", 3, "8-10", **ACC),
                                            ex("back_ext", 3, 12, rest=60),
                                            ex("hip_abduction", 3, 20, rest=45)]),
         "B": session("Romeno pesado", [ex("rdl", 4, "6-8", rpe=8, rest=150),
                                        ex("step_up", 3, 10, rest=75, notes="por perna"),
                                        ex("kickback", 3, "12-15", rpe=7, rest=60),
                                        ex("monster_walk", 3, 15, rest=45)]),
         "C": session("Hip thrust volume", [ex("hip_thrust", 3, "10-15", rpe=8, rest=120),
                                            ex("sl_hip_thrust", 3, 10, rest=75,
                                               notes="por perna"),
                                            ex("goblet", 3, "10-12", **ACC),
                                            ex("glute_bridge", 2, 20, rest=45)]),
         "D": session("Romeno volume", [ex("sumo", 3, "8-10", rpe=7, rest=150),
                                        ex("lunge", 3, 12, rest=75, notes="por perna"),
                                        ex("kickback", 3, "15-20", rpe=7, rest=45),
                                        ex("hip_abduction", 3, 25, rest=45)])},
        schedule=[["A", "B", "C", "D"]], weekdays=[1, 2, 4, 5])
    return P


@lru_cache(maxsize=1)
def _validated() -> dict[str, dict]:
    from . import programs
    return {k: programs.validate(p) for k, p in _build().items()}


def plans() -> dict[str, dict]:
    return _validated()


def template_plan() -> dict:
    """O ficheiro modelo: um plano pequeno que usa quase tudo o que o formato tem."""
    return {
        "format": "perennia-plan", "version": 1,
        "name": "O meu plano (modelo)", "author": "o teu nome",
        "source": "de onde veio o plano (livro, site…)",
        "category": "strength", "level": "beginner",
        "description": "Explica aqui o plano em duas ou três frases: para quem é, como "
                       "progride, o que fazer quando se falha.",
        "weeks": 4, "days_per_week": 3, "weekdays": [1, 3, 5],
        "equipment": ["barbell", "plates", "rack", "bench"],
        "exercises": {
            "squat": {"name": "Agachamento com barra", "group": "legs", "measure": "reps",
                      "equipment": ["barbell", "plates", "rack"], "modality": "strength",
                      "aliases": ["Back squat", "Squat"]},
            "bench": {"name": "Supino com barra", "group": "chest",
                      "equipment": ["barbell", "plates", "bench", "rack"],
                      "aliases": ["Bench press"]},
            "row": {"name": "Remada com barra", "group": "back",
                    "equipment": ["barbell", "plates"]},
            "pullup": {"name": "Elevações (pull-ups)", "group": "back", "bodyweight": 1.0,
                       "equipment": ["pullup_bar"], "modality": "calisthenics"},
            "plank": {"name": "Prancha", "group": "core", "measure": "time"},
            "meu_exercicio": {"name": "Um exercício que ainda não existe", "group": "arms",
                              "equipment": ["dumbbell"],
                              "description": "É criado na Perennia quando começares o plano."}
        },
        "sessions": {
            "A": {"name": "Treino A", "notes": "Texto livre que aparece no topo da sessão.",
                  "blocks": [
                      {"exercise": "squat", "sets": 5, "reps": 5, "rest": 180,
                       "add_kg": 2.5, "per": "session", "start_pct": 50},
                      {"exercise": "bench", "sets": 3, "reps": "8-12", "rpe": 8, "rest": 120},
                      {"kind": "superset", "rest": 60, "exercises": [
                          {"exercise": "row", "sets": 3, "reps": 10, "pct1rm": [60, 62.5, 65,
                                                                                 55]},
                          {"exercise": "meu_exercicio", "sets": 3, "reps": 12}]},
                      {"exercise": "plank", "sets": 3, "time": [30, 40, 50, 30], "rest": 45}]},
            "B": {"name": "Treino B",
                  "blocks": [
                      {"exercise": "squat", "sets": [
                          {"reps": 5, "pct1rm": 65}, {"reps": 5, "pct1rm": 75},
                          {"reps": "5+", "pct1rm": 85}]},
                      {"exercise": "pullup", "sets": 3, "reps": "max", "rest": 120},
                      {"kind": "circuit", "rounds": 3, "rest": 90, "exercises": [
                          {"exercise": "meu_exercicio", "sets": 1, "reps": 15},
                          {"exercise": "plank", "sets": 1, "time": 30}]}]}
        },
        "rotation": ["A", "B"]
    }


FORMAT_DOC = """# O formato de um plano Perennia

Um plano é um ficheiro de texto **JSON** com o nome a acabar em `.perennia-plan.json`.
Põe-no na pasta `workouts` (ao lado da aplicação), em Transferências ou em Documentos, e em
**Ginásio → Lista de treinos → Planos de X semanas → Importar plano…** escolhe-o. Se alguma
coisa não obedecer ao formato, a Perennia diz o campo e a razão, e não importa nada.

O ficheiro `plano-modelo.perennia-plan.json` é um plano pequeno, que funciona, com quase tudo
o que o formato tem: copia-o e muda-o. Também podes **exportar** qualquer plano que venha com
a Perennia (botão «Exportar (.json)» na ficha do plano) e partir daí.

## Campos de topo

| Campo | Obrigatório | O que é |
|---|---|---|
| `format` | sim | sempre `"perennia-plan"` |
| `version` | não | `1` |
| `name` | sim | o nome do plano (até 80 letras) |
| `description`, `author`, `source` | não | texto livre |
| `category` | não | `strength`, `powerlifting`, `bodybuilding`, `strongman`, `grip`, `longevity`, `general`, `conditioning`, `athletic`, `glutes`, `other` |
| `level` | não | `beginner`, `intermediate`, `advanced` |
| `weeks` | sim | número de semanas (1 a 104) |
| `exercises` | sim | os exercícios que o plano usa (ver abaixo) |
| `sessions` | sim | as sessões-tipo: «Treino A», «Treino B»… |
| `rotation` **ou** `schedule` | sim | a ordem das sessões (ver abaixo) |
| `days_per_week` | com `rotation` | sessões por semana (1 a 7) |
| `weekdays` | não | os dias por omissão: 1 = segunda … 7 = domingo. Ao começar o plano podes escolher outros |
| `equipment` | não | material, além do que os exercícios já pedem |

## `exercises`

Um objeto `chave → exercício`. A chave (letras, números, `_`, `-`) é o que as sessões usam.

```json
"squat": {"name": "Agachamento com barra", "group": "legs", "measure": "reps",
          "bodyweight": 0, "equipment": ["barbell", "plates", "rack"],
          "modality": "strength", "aliases": ["Back squat", "Squat"]}
```

- `name` — obrigatório. Se já existir um exercício com esse nome (ou com um dos `aliases`),
  sem contar acentos nem maiúsculas, usa-se esse; **se não existir, é criado** quando
  começares o plano.
- `group` — `legs`, `hips`, `chest`, `back`, `shoulders`, `arms`, `core`, `full`, `mobility`.
- `measure` — `reps` (por omissão) ou `time` (segundos).
- `bodyweight` — fração do peso do corpo que conta como carga (0 a 1; elevações = 1).
- `equipment` — tipos de material do Inventário: `barbell`, `plates`, `dumbbell`,
  `kettlebell`, `sandbag`, `rack`, `bench`, `pullup_bar`, `cable`, `bands`, `box`, `rings`,
  `leg_press`, `trap_bar`, `sled`, `gripper`, `fat_grips`, `wrist_roller`, `ab_wheel`…
- `modality` — a modalidade do ginásio onde fica (`strength`, `kettlebell`, `calisthenics`,
  `plyometrics`, `tendons`, `isometric`, `mobility`, `cardio`…).

## `sessions`

Um objeto `chave → sessão`. Cada sessão tem `name`, `notes` (opcional) e `blocks`.

Um bloco é **um exercício**:

```json
{"exercise": "squat", "sets": 5, "reps": 5, "rest": 180}
```

ou **um grupo** (`kind`: `superset`, `circuit`, `warmup`, `cooldown`) com `exercises`,
`rounds` (voltas do circuito) e `rest` (descanso entre voltas, em segundos):

```json
{"kind": "circuit", "rounds": 4, "rest": 90, "exercises": [
   {"exercise": "swing", "sets": 1, "reps": 10},
   {"exercise": "plank", "sets": 1, "time": 30}]}
```

### Campos de um exercício numa sessão

| Campo | O que é |
|---|---|
| `sets` | número de séries iguais, **ou** a lista das séries (cada uma com os campos abaixo) |
| `reps` | `5`, `"8-12"` (intervalo), `"5+"` (cinco ou mais: o máximo que der) ou `"max"` |
| `load` | carga em kg (fixa) |
| `pct1rm` | % da tua 1RM estimada: a carga calcula-se no momento da sessão |
| `rpe`, `rir` | esforço (1–10) ou repetições em reserva |
| `time` | segundos (para exercícios por tempo) |
| `distance` | metros |
| `rest` | descanso em segundos |
| `notes` | texto que aparece no exercício |

**Um valor por semana.** Qualquer número pode ser uma lista com um valor por semana:
`"pct1rm": [70, 75, 80, 60]`. Se a lista for mais curta do que o plano, o último repete-se.
`sets` também: `"sets": [3, 3, 4, 4]`.

**Séries diferentes na mesma sessão.**

```json
{"exercise": "squat", "sets": [
   {"reps": 5, "pct1rm": 65}, {"reps": 5, "pct1rm": 75}, {"reps": "5+", "pct1rm": 85}]}
```

**Progressão linear.** `"add_kg": 2.5` soma essa carga de cada vez que o exercício volta
(`"per": "session"`, por omissão) ou de semana a semana (`"per": "week"`). A **carga inicial**
pede-se quando começas o plano; `"start_pct": 50` sugere 50 % da tua 1RM estimada. Dentro de
uma lista de séries, `"of_top": 0.75` é a fração da carga principal (séries em rampa e de
recuo). Se o mesmo exercício tiver duas progressões diferentes no plano (uma pesada e uma de
volume), dá a cada uma um `"track"` próprio: `"track": "squat_volume"`.

## A ordem das sessões

- **`rotation`** — as sessões alternam por esta ordem ao longo de todos os dias do plano.
  Com `"rotation": ["A", "B"]` e `"days_per_week": 3`: semana 1 = A, B, A; semana 2 = B, A, B.
- **`schedule`** — a lista das sessões de cada semana. Com uma só semana, repete-se sempre:
  `"schedule": [["A", "B", "C"]]`. Com várias, segue-as por ordem (e volta ao princípio se o
  plano tiver mais semanas): `"schedule": [["V", "V", "V"], ["H1", "H2", "H3"]]`.

## Limites

Até 104 semanas, 60 sessões-tipo, 30 blocos por sessão, 12 exercícios por bloco, 30 séries por
exercício e 200 exercícios. O ficheiro não pode passar do tamanho definido em Definições →
Avançado → Planos de treino (512 kB por omissão). Só se lê JSON: um plano não pode trazer
código.

## Traduzir um plano que já existe

1. Copia `plano-modelo.perennia-plan.json` e muda `name`, `weeks` e `description`.
2. Lista os exercícios em `exercises` (usa os nomes da Perennia quando existirem; os outros
   são criados).
3. Escreve cada treino-tipo em `sessions`.
4. Se o plano alterna treinos (A/B), usa `rotation`; se cada semana tem dias fixos, usa
   `schedule`.
5. O que muda de semana para semana vai em listas (`[70, 75, 80]`); o que soma carga de cada
   vez vai em `add_kg`.
6. Importa. Se houver um erro, a mensagem diz o campo.
"""
