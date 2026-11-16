"""As métricas de saúde que vêm de origem além das primeiras: alimentação por refeição,
digestão, sono, rotina e recuperação. Entram **uma vez** (a definição `health_catalog_seeded`
guarda as chaves já criadas): se descontinuares ou apagares uma, não volta; se já tiveres uma
com o mesmo nome ou a mesma chave, é ignorada. Podes criar mais à vontade (ecrã Métricas, ou o
CSV «metricas»).

Perguntas «se sim, onde?»: uma métrica pode **depender** de outra (`parent`, uma ou várias
chaves separadas por `|`; `parent_value` é a resposta que a ativa) e só aparece no diário quando
essa resposta foi dada.
"""
from __future__ import annotations

import json
import unicodedata

from .db import Database

YES = "1"
NO = "0"

DIETS = ["vegan", "carnívoro", "peixe", "outro"]
MEAL_TYPES = ["fast food", "caseiro", "pré-feita", "congelada", "outro"]
WHERE_EAT = ["escritório", "casa dos pais", "amigos", "sogros", "restaurante", "outro"]
STOOL_TYPE = ["duras", "normais", "moles", "líquidas"]
STOOL_COLOR = ["clara", "normal", "escura"]
WHERE_DAY = ["escritório", "viagem", "casa de familiares", "amigos", "outro"]

MEALS = (("breakfast", "ao pequeno-almoço", "Pequeno-almoço"), ("lunch", "ao almoço", "Almoço"),
         ("snack", "ao lanche", "Lanche"), ("dinner", "ao jantar", "Jantar"))

# (chave, nome, tipo, unidade, grupo, escolhas, dependência, valor que ativa)
Row = tuple


def _catalog() -> list[Row]:
    c: list[Row] = []

    def add(key, name, kind, grp, choices=None, parent=None, pvalue=None, unit=""):
        c.append((key, name, kind, unit, grp, choices, parent, pvalue))

    # --- alimentação
    add("lunch_diet", "Tipo de almoço", "choice", "food", DIETS)
    add("dinner_diet", "Tipo de jantar", "choice", "food", DIETS)
    add("lunch_type", "Tipo de refeição (almoço)", "choice", "food", MEAL_TYPES)
    add("dinner_type", "Tipo de refeição (jantar)", "choice", "food", MEAL_TYPES)
    add("snack_what", "O que lanchei", "text", "food")
    add("lunch_on_time", "Almoço iniciou à hora normal (12h30–13h00)?", "bool", "food")
    add("dinner_on_time", "Jantar iniciou à hora normal (20h00–20h45)?", "bool", "food")
    add("lunch_out", "Almoço fora de casa?", "bool", "food")
    add("lunch_out_where", "Almoço fora: onde?", "choice", "food", WHERE_EAT, "lunch_out", YES)
    add("dinner_out", "Jantar fora de casa?", "bool", "food")
    add("dinner_out_where", "Jantar fora: onde?", "choice", "food", WHERE_EAT, "dinner_out", YES)
    for k, when in (("lunch", "ao almoço"), ("dinner", "ao jantar")):
        add(f"alcohol_{k}", f"Bebi álcool {when}?", "bool", "food")
        add(f"white_meat_{k}", f"Carne branca {when}?", "bool", "food")
        add(f"red_meat_{k}", f"Carne vermelha {when}?", "bool", "food")
        add(f"meat_which_{k}", f"Qual a carne ({when})?", "text", "food",
            None, f"white_meat_{k}|red_meat_{k}", YES)
        add(f"white_fish_{k}", f"Peixe branco {when}?", "bool", "food")
        add(f"fatty_fish_{k}", f"Peixe gorduroso {when}?", "bool", "food")
        add(f"fish_which_{k}", f"Qual o peixe ({when})?", "text", "food",
            None, f"white_fish_{k}|fatty_fish_{k}", YES)
        add(f"dessert_{k}", f"Sobremesa {when}?", "bool", "food")
        add(f"veg_{k}", f"Comi legumes {when}?", "bool", "food")
    add("sweets_snack", "Comi doces ao lanche?", "bool", "food")
    add("sweets_which", "Que doces (chocolate, bolachas…)?", "text", "food",
        None, "sweets_lunch|sweets_dinner|sweets_snack", YES)
    for k, when, _n in MEALS:
        add(f"heavy_{k}", f"{_n} foi pesado?", "bool", "food")
    for k, when, _n in (("breakfast", "ao pequeno-almoço", ""), ("lunch", "ao almoço", ""),
                        ("dinner", "ao jantar", "")):
        add(f"coffee_{k}", f"Bebi café {when}?", "bool", "food")
        add(f"decaf_{k}", f"Bebi descafeinado {when}?", "bool", "food")
    # --- digestão
    add("pooped", "Fiz cocó?", "bool", "digestion")
    add("stool_type", "Como eram as fezes?", "choice", "digestion", STOOL_TYPE, "pooped", YES)
    add("stool_hard_to_pass", "Dificuldade em evacuar?", "bool", "digestion", None, "pooped",
        YES)
    add("stool_color", "Cor das fezes", "choice", "digestion", STOOL_COLOR, "pooped", YES)
    # --- sono
    add("kids_let_rest", "Os filhos deram descanso durante a noite?", "bool", "sleep")
    add("night_pee", "Levantei-me durante a noite para fazer xixi?", "bool", "sleep")
    add("insomnia", "Tive insónias durante a noite?", "bool", "sleep")
    add("read_before_bed", "Li antes de ir para a cama?", "bool", "sleep")
    add("phone_before_bed", "Estive no telemóvel nos minutos antes de me deitar?", "bool",
        "sleep")
    add("bedtime_stress", "Tive stress no momento de deitar/adormecer?", "bool", "sleep")
    add("nasal_strips", "Usei nasal strips para dormir?", "bool", "sleep")
    add("long_in_bed", "Ao acordar estive muito tempo na cama?", "bool", "sleep")
    # --- rotina
    add("home_all_day", "Passei o dia em casa?", "bool", "routine")
    add("away_where", "Se não, onde estive?", "choice", "routine", WHERE_DAY, "home_all_day",
        NO)
    add("holiday", "Dia de férias do trabalho?", "bool", "routine")
    add("productive", "O dia foi produtivo?", "bool", "routine")
    add("travelling", "Estive em viagem?", "bool", "routine")
    add("sexual_activity", "Atividade sexual?", "bool", "routine")
    add("allergy_symptoms", "Tive sintomas de alergia?", "bool", "routine")
    # --- recuperação
    add("mobility_routine", "Fiz a rotina de mobilidade diária?", "bool", "recovery")
    add("stretching", "Fiz alongamentos?", "bool", "recovery")
    add("myofascial", "Fiz libertação miofascial?", "bool", "recovery")
    return c


CATALOG: list[Row] = _catalog()


def _fold(text) -> str:
    s = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).casefold().strip(" ?.")


def keys() -> list[str]:
    return [r[0] for r in CATALOG]


def seed(db: Database) -> int:
    """Cria as que faltam (sem duplicar por chave nem por nome). Devolve quantas criou."""
    from . import health, options
    health.ensure(db)
    if not options.get(db, "health_catalog_seed"):
        return 0
    done = set(db.get("health_catalog_seeded", []) or [])
    have_keys = {r["key"] for r in db.conn.execute("SELECT key FROM metric_defs")}
    have_names = {_fold(r["name"]) for r in db.conn.execute("SELECT name FROM metric_defs")}
    sort = db.conn.execute("SELECT COALESCE(MAX(sort), 0) FROM metric_defs").fetchone()[0]
    made = 0
    for key, name, kind, unit, grp, choices, parent, pvalue in CATALOG:
        if key in done:
            continue
        done.add(key)
        if key in have_keys or _fold(name) in have_names:
            continue
        sort += 1
        db.conn.execute(
            "INSERT INTO metric_defs(key, name, kind, unit, grp, choices, sort, source,"
            " parent_key, parent_value) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (key, name, kind, unit, grp, json.dumps(choices, ensure_ascii=False) if choices
             else None, sort, "manual", parent, pvalue))
        have_keys.add(key)
        have_names.add(_fold(name))
        made += 1
    db.conn.commit()
    db.set("health_catalog_seeded", sorted(done))
    return made
