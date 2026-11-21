"""Preparação do agente de IA (ainda por ligar).

Dois pedidos estão disponíveis em todos os ecrãs:

- «Resumo desta página» (F1): o agente comenta o que está no ecrã. Envia-se
  o que o ecrã mostra (títulos, linhas, valores, séries do gráfico).
- «Resumo contextualizado» (F2): o mesmo, mais um retrato do atleta —
  carga e forma, FTP estimada, força, sono, HRV, FC em repouso, alimentação,
  análises fora do intervalo e testes — para relacionar as coisas.

Enquanto não houver um fornecedor configurado, o ecrã do agente mostra
exatamente o que seria enviado: é a forma de verificar a privacidade antes
de ligar. Regras que ficam desde já:

* Só saem as categorias autorizadas nas definições (`agent_share`).
* Nada que venha do Strava é enviado (o acordo da API do Strava proíbe
  usar os dados em sistemas de IA).
* O agente sugere; não diagnostica. Nas análises aponta tendências e
  perguntas para levar ao médico.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

from . import fitness_tests, health, options, stats
from . import strength as st
from .db import Database

KINDS = ("page", "context")
CATEGORIES = ("training", "strength", "health", "food", "labs", "tests")
EXCLUDED_SOURCES = ("strava",)

SYSTEM_PROMPT = (
    "És o guia pessoal de longevidade e treino do atleta. Respondes em português "
    "de Portugal, de forma direta e concreta. Baseias-te só nos dados enviados; quando "
    "faltarem dados, dizes o que falta. Relacionas treino, recuperação, sono, alimentação "
    "e análises quando isso ajudar. Sugeres ajustes práticos para os próximos dias. Não "
    "fazes diagnósticos: em análises clínicas apontas tendências e perguntas para o médico."
)


def allowed(db: Database) -> set[str]:
    return set(db.get("agent_share", list(CATEGORIES)))


def provider(db: Database) -> dict:
    """Configuração do fornecedor. Sem chave, o agente fica em pré-visualização."""
    name = db.get("agent_provider", "none")
    key = os.environ.get("ANTHROPIC_API_KEY") if name == "anthropic" else None
    return {"name": name, "ready": bool(key), "model": db.get("agent_model", "")}


def page_payload(screen) -> dict:
    fn = getattr(screen, "agent_context", None)
    try:
        return fn() if fn else {}
    except Exception as e:                       # um ecrã partido não parte o agente
        return {"error": str(e)}


def athlete_context(db: Database, days: int = 28, today: date | None = None) -> dict:
    """Retrato do atleta para o resumo contextualizado."""
    today = today or date.today()
    share = allowed(db)
    a = db.athlete()
    out: dict[str, Any] = {"data": today.isoformat(), "atleta": {
        "idade": a.age, "peso_kg": a.weight_kg, "ftp_w": a.ftp_w, "lthr": a.lthr,
        "fc_max": a.max_hr}}
    if "training" in share:
        now = stats.fitness_now(db, today=today)
        cyc = stats.fitness_now(db, ("cycling",), today=today)
        out["carga"] = {
            "total": _round(now), "ciclismo": _round(cyc),
            "estado_forma": now["state"] if now else None,
            "ftp_estimada": stats.estimated_ftp(db, today=today),
            "ultimas_4_semanas": stats.sport_series(db, "time", "week", 4, today=today),
            "sequencia": stats.streaks(db, today),
        }
    if "strength" in share:
        prog = {}
        for ex in st.exercises_with_history(db)[:8]:
            p = st.exercise_progress(db, ex["id"])
            vals = [x["best_e1rm"] for x in p if x["best_e1rm"]]
            if vals:
                prog[ex["name"]] = {"1rm_estimada_ultima": round(vals[-1], 1),
                                    "1rm_estimada_max": round(max(vals), 1),
                                    "sessoes": len(p)}
        out["forca"] = prog
    if "health" in share or "food" in share:
        daily = {}
        for m in health.metrics(db):
            if m["grp"] == "food" and "food" not in share:
                continue
            if m["grp"] != "food" and "health" not in share:
                continue
            rows = db.conn.execute(
                "SELECT day, num, txt, notes, source FROM daily_values WHERE metric_id = ?"
                " AND day >= ? ORDER BY day", (m["id"], (today - timedelta(days=days)).isoformat()))
            vals = [r for r in rows if r["source"] not in EXCLUDED_SOURCES]
            if not vals:
                continue
            if m["kind"] in ("number", "scale", "bool"):
                nums = [r["num"] for r in vals if r["num"] is not None]
                if nums:
                    daily[m["name"]] = {"media": round(sum(nums) / len(nums), 2),
                                        "ultimo": nums[-1], "dias": len(nums)}
            else:
                daily[m["name"]] = [f"{r['day']}: {r['txt']}" for r in vals[-7:] if r["txt"]]
            notes = [f"{r['day']}: {r['notes']}" for r in vals if r["notes"]]
            if notes:
                daily.setdefault("_notas", {})[m["name"]] = notes[-5:]
        out["diario"] = daily
    if "labs" in share:
        reps = health.lab_reports(db)[:3]
        labs = []
        for r in reps:
            res = health.lab_results(db, r["id"])
            labs.append({"data": r["done_on"], "comentario_medico": r["doctor_feedback"],
                         "fora_do_intervalo": [
                             {"marcador": x["marker"], "valor": x["value"], "unidade": x["unit"],
                              "ref": [x["ref_low"], x["ref_high"]], "estado": health.flag(x)}
                             for x in res if health.flag(x)]})
        out["analises"] = labs
    if "tests" in share:
        tests_out = {}
        for sport in fitness_tests.SPORTS:
            for t_ in fitness_tests.tests(db, sport):
                if t_["n"]:
                    tests_out[t_["name"]] = {"ultimo": t_["last"], "melhor": t_["best"],
                                             "unidade": t_["unit"], "tendencia": t_["trend"],
                                             "data": t_["last_on"]}
        out["testes"] = tests_out
    return out


def _round(d: dict | None) -> dict | None:
    if not d:
        return None
    return {k: (round(v, 1) if isinstance(v, float) else str(v) if k == "date" else v)
            for k, v in d.items()}


# ------------------------------------------------------------------ tokens
#
# Os fornecedores cobram por «tokens» (pedaços de texto, em média ~3-4 caracteres cada). Antes de
# enviar, a Perennia faz uma ESTIMATIVA local, sem rede e sem custo: caracteres do que vai sair
# ÷ caracteres por token (definição `agent_chars_per_token`, 3,5 por omissão — em português e com
# JSON gasta-se um pouco mais do que em inglês). A contagem exata só o fornecedor a dá (a
# Anthropic tem um pedido «count_tokens», gratuito): fica para quando o agente estiver ligado.

AGENT_DEFAULTS = options.defaults("agent_")       # os valores por omissão vivem em options.py


def setting(db: Database, key: str):
    return options.get(db, key)


def compact(obj: Any) -> str:
    """O texto que vai mesmo no pedido (JSON compacto: sem espaços a mais, gasta menos)."""
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


def estimate_tokens(text: str, db: Database | None = None) -> int:
    cpt = float(setting(db, "agent_chars_per_token")) if db is not None \
        else AGENT_DEFAULTS["agent_chars_per_token"]
    return int(-(-len(text) // max(1.0, cpt))) if text else 0


CONTEXT_PARTS = {"atleta": "Perfil do atleta", "carga": "Treino e forma", "forca": "Força",
                 "diario": "Diário (saúde e alimentação)", "analises": "Análises clínicas",
                 "testes": "Testes de longevidade", "data": "Data"}


def token_report(request: dict, db: Database) -> dict:
    """Quanto vai gastar este pedido: por partes, o total, o limite da resposta e o custo.

    `parts` é uma lista de (nome, tokens) pela ordem em que o pedido se compõe. `max_cost` é o
    pior caso (pedido + resposta no limite) e só existe se os preços estiverem nas definições.
    """
    content = request["content"]
    parts: list[tuple[str, int]] = [
        ("system", estimate_tokens(request["system"], db)),
        ("instruction", estimate_tokens(request["instruction"], db)),
        ("page", estimate_tokens(compact(content.get("pagina")), db)),
    ]
    ctx = content.get("contexto")
    if ctx:
        for k, v in ctx.items():
            parts.append((f"ctx:{k}", estimate_tokens(compact({k: v}), db)))
    # o envelope (chaves, «pedido», etc.) cabe no que sobra da diferença para o texto inteiro
    total_text = request["system"] + request["instruction"] + compact(content)
    total = estimate_tokens(total_text, db)
    max_out = int(setting(db, "agent_max_output_tokens"))
    p_in = float(setting(db, "agent_price_in_per_mtok"))
    p_out = float(setting(db, "agent_price_out_per_mtok"))
    priced = p_in > 0 or p_out > 0
    return {
        "parts": parts, "total": total, "max_output": max_out,
        "warn": total > int(setting(db, "agent_warn_tokens")),
        "warn_at": int(setting(db, "agent_warn_tokens")),
        "priced": priced, "currency": str(setting(db, "agent_currency")),
        "cost_in": total * p_in / 1e6 if priced else None,
        "cost_out_max": max_out * p_out / 1e6 if priced else None,
        "max_cost": (total * p_in + max_out * p_out) / 1e6 if priced else None,
        "exact": False,
    }


def set_categories(db: Database, categories: list[str]) -> None:
    db.set("agent_share", [c for c in CATEGORIES if c in set(categories)])


def build_request(kind: str, screen, db: Database) -> dict:
    """O pedido completo (sistema + conteúdo). É o que o ecrã do agente mostra."""
    page = page_payload(screen)
    content: dict[str, Any] = {"pedido": "resumo desta página" if kind == "page"
                               else "resumo contextualizado", "pagina": page}
    if kind == "context":
        content["contexto"] = athlete_context(db)
    instr = ("Resume o que está nesta página e o que é importante reparar."
             if kind == "page" else
             "Relaciona o que está nesta página com o contexto do atleta e diz o que "
             "isso significa para a longevidade e para os próximos dias de treino.")
    text = json.dumps(content, ensure_ascii=False, default=str, indent=1)
    out = {"system": SYSTEM_PROMPT, "instruction": instr, "content": content, "text": text}
    out["approx_tokens"] = token_report(out, db)["total"]
    return out


def flatten(obj: Any, prefix: str = "", out: list | None = None, limit: int = 400
            ) -> list[tuple[str, str]]:
    """Para mostrar o pedido como linhas «chave: valor»."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(v, f"{prefix}{k}." if not isinstance(v, (dict, list)) or True else prefix,
                    out, limit)
    elif isinstance(obj, list) and obj and isinstance(obj[0], (dict, list)):
        for i, v in enumerate(obj):
            flatten(v, f"{prefix}{i}.", out, limit)
    else:
        if isinstance(obj, list):
            obj = ", ".join(str(x) for x in obj)
        out.append((prefix.rstrip("."), "—" if obj is None else str(obj)))
    return out
