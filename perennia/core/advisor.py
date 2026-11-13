"""De onde vem o conselho do Treinador e do Assistente de saúde.

Três modos, escolhidos no próprio ecrã (e guardados por figura):

* **rules** — as regras da Perennia: offline, sem rede, sem IA. Funciona já.
* **local** — um LLM a correr no teu computador (Ollama, LM Studio, llama.cpp…): offline, nada
  sai da máquina. Fica **preparado**: o ecrã mostra o pedido e os tokens; a chamada ainda não
  está ativa nesta versão.
* **online** — um agente de um fornecedor (Claude, ChatGPT, Gemini ou outro compatível):
  alguns dados teus seriam partilhados com ele. Também **preparado**, sem chamada.

Regras de sempre: a chave do fornecedor vem **só de uma variável de ambiente** (nunca se
escreve nas Definições nem fica na base); só seguem as categorias autorizadas; nada do Strava;
e antes de enviar vê-se o pedido inteiro e a estimativa de tokens (e do custo, no online).
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import agent, options
from .advice import Advice
from .db import Database
from .i18n import tr

MODES = ("rules", "local", "online")
FIGURES = ("coach", "health")
ENV_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY", "other": "PERENNIA_AI_API_KEY"}
ENV_LOCAL_URL = "PERENNIA_LLM_URL"
CALLS_ENABLED = False            # as chamadas a LLM (local ou online) ainda não estão ativas

SYSTEM = {
    "coach": (
        "És o Treinador da Perennia: acompanhas o treino de um atleta amador com foco na "
        "longevidade. Respondes em português de Portugal, de forma direta e concreta. "
        "Baseias-te só nos dados enviados (o retrato do atleta e os factos do pedido); quando "
        "faltarem dados, perguntas. Propões ajustes práticos: sessões, cargas, descanso. "
        "Respeitas a disponibilidade indicada. Não fazes diagnósticos médicos; perante dor ou "
        "sinais de doença, recomendas um profissional de saúde."),
    "health": (
        "És o Assistente de saúde da Perennia: lês os registos de saúde de um atleta amador "
        "(análises, pressão arterial, sono, FC em repouso, HRV, peso, hábitos e notas) e dás "
        "uma avaliação geral e por componente. Respondes em português de Portugal, com "
        "clareza. Não fazes diagnósticos nem prescreves medicação: apontas tendências, "
        "relações prováveis e perguntas para levar ao médico. Perante valores de alarme, "
        "dizes para contactar um médico."),
}


def figure_name(figure: str) -> str:
    return tr("Treinador", "Coach") if figure == "coach" else tr("Assistente de saúde",
                                                                "Health assistant")


def mode_key(figure: str) -> str:
    return f"advisor_{figure}_mode"


def mode(db: Database, figure: str) -> str:
    m = options.get(db, mode_key(figure))
    return m if m in MODES else "rules"


def set_mode(db: Database, figure: str, m: str) -> None:
    if m in MODES:
        db.set(mode_key(figure), m)


def mode_name(m: str) -> str:
    return {"rules": tr("Regras da Perennia (offline)", "Perennia rules (offline)"),
            "local": tr("LLM local (offline)", "Local LLM (offline)"),
            "online": tr("Agente online", "Online agent")}.get(m, m)


def mode_detail(db: Database, m: str) -> str:
    if m == "rules":
        return tr("sem rede e sem IA: nada sai do computador", "no network, no AI: nothing "
                  "leaves the computer")
    st = status(db, m)
    if m == "local":
        return tr("um modelo no teu computador ({u}{m}): nada sai da máquina · ainda por ligar",
                  "a model on your computer ({u}{m}): nothing leaves the machine · not "
                  "connected yet", u=st["url"], m=" · " + st["model"] if st["model"] else "")
    return tr("{p}: os dados do pedido seriam partilhados com o fornecedor · chave: {k} · ainda "
              "por ligar", "{p}: the request data would be shared with the provider · key: {k} "
              "· not connected yet", p=st["provider_name"],
              k=tr("definida ({e})", "set ({e})", e=st["env"]) if st["has_key"]
              else tr("falta a variável {e}", "variable {e} missing", e=st["env"]))


def status(db: Database, m: str) -> dict:
    """O que está configurado para o modo. `ready` só é verdade quando há tudo E as chamadas
    estiverem ativas (nesta versão nunca estão: fica em pré-visualização)."""
    if m == "local":
        url = os.environ.get(ENV_LOCAL_URL) or str(options.get(db, "advisor_local_url"))
        model = str(options.get(db, "advisor_local_model") or "")
        return {"mode": m, "url": url, "model": model, "configured": bool(url and model),
                "ready": CALLS_ENABLED and bool(url and model), "local": is_local_url(url)}
    if m == "online":
        prov = str(options.get(db, "advisor_online_provider"))
        env = ENV_KEYS.get(prov, ENV_KEYS["other"])
        has = bool(os.environ.get(env))
        opt = options.BY_KEY["advisor_online_provider"]
        return {"mode": m, "provider": prov, "provider_name": options.choice_label(opt, prov),
                "env": env, "has_key": has,
                "model": str(options.get(db, "advisor_online_model") or ""),
                "configured": has, "ready": CALLS_ENABLED and has}
    return {"mode": "rules", "configured": True, "ready": True}


def is_local_url(url: str) -> bool:
    """O endereço do LLM «local» tem mesmo de ser deste computador (senão seria online)."""
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def scrub(obj: Any) -> Any:
    """Tira do que seguiria para um LLM tudo o que venha do Strava (chaves ou valores)."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()
                if "strava" not in str(k).lower()
                and not (isinstance(v, dict) and str(v.get("source", "")).lower() == "strava")}
    if isinstance(obj, (list, tuple)):
        return [scrub(v) for v in obj
                if not (isinstance(v, dict) and str(v.get("source", "")).lower() == "strava")]
    return obj


def build_request(db: Database, figure: str, advice: Advice, question: str = "",
                  with_context: bool = True) -> dict:
    """O pedido que seguiria para o LLM: as instruções da figura, o pedido, os factos em que
    as regras se basearam e (se quiseres) o retrato do atleta nas categorias autorizadas.
    Tem o mesmo formato do pedido do agente (F1/F2), para os tokens se contarem igual."""
    facts = scrub(json.loads(json.dumps(advice.data, default=str, ensure_ascii=False)))
    page = {"figura": figure_name(figure), "tema": advice.title, "factos": facts,
            "leitura_das_regras": {"veredicto": advice.verdict,
                                   "seccoes": [{"titulo": t, "texto": x}
                                               for t, x in advice.sections]}}
    if question.strip():
        page["pergunta_do_atleta"] = question.strip()
    content: dict[str, Any] = {"pedido": advice.title, "pagina": page}
    if with_context:
        content["contexto"] = scrub(agent.athlete_context(db))
    instr = tr("Com estes dados, dá o teu conselho sobre «{t}»: o que vês, o que recomendas "
               "para os próximos dias e que perguntas farias ao atleta.",
               "With this data, give your advice on '{t}': what you see, what you recommend "
               "for the coming days and what you would ask the athlete.", t=advice.title)
    text = json.dumps(content, ensure_ascii=False, default=str, indent=1)
    out = {"system": SYSTEM[figure], "instruction": instr, "content": content, "text": text,
           "figure": figure}
    out["approx_tokens"] = agent.token_report(out, db)["total"]
    return out


def report(db: Database, request: dict, m: str) -> dict:
    """Os tokens do pedido para o modo: no local não há custo, mas há a janela de contexto."""
    rep = agent.token_report(request, db)
    rep["mode"] = m
    if m == "local":
        window = int(options.get(db, "advisor_local_context_tokens"))
        rep.update(priced=False, max_cost=None, cost_in=None, cost_out_max=None,
                   window=window, fits=rep["total"] + rep["max_output"] <= window)
        rep["warn"] = not rep["fits"]
    return rep
