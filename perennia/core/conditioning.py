"""O treino de Conditioning (ronda 26): uma sequência de **blocos de vários desportos** —
ciclismo, passadeira (corrida), remo, ginásio — e descansos, cada um com o seu construtor.

Um bloco é um dicionário:

    {"sport": "cycling" | "running" | "rowing" | "gym" | "rest",
     "control": "manual" | "erg",          # nos de resistência; o ginásio e o descanso: manual
     "name": "...",
     "mode": "power" | "hr" | ...,          # a vista do construtor (resistência)
     "blocks": [Block…],                    # resistência: os blocos do construtor (como dict)
     "struct": {...}, "modality": "...",    # ginásio: a estrutura do construtor de força
     "seconds": 600}                         # descanso (e o total calculado de todos)

Grava-se em `lap_plans` (os planos de Conditioning): cada item tem `kind`/`seconds`/`name`
(o que o motor por voltas sabe fazer) e o bloco inteiro em `cond`. Os planos antigos (voltas
soltas) continuam a abrir: cada volta vira um bloco simples.

Na sessão cada bloco é uma volta planeada, com os **passos** do bloco a guiar (o alvo e o
tempo de cada passo); num bloco de ciclismo **ERG** a app põe a potência do passo no rolo.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

from . import intensity as it
from .blocks import Block, block_seconds
from .i18n import tr

SPORTS = ("cycling", "running", "rowing", "gym", "rest")
LAP_KIND = {"cycling": "bike", "running": "treadmill", "rowing": "rowing", "gym": "strength",
            "rest": "rest"}
SPORT_OF_KIND = {"bike": "cycling", "treadmill": "running", "rowing": "rowing",
                 "strength": "gym", "cardio": "gym", "rest": "rest"}
ENDURANCE = ("cycling", "running", "rowing")
ERG_SPORTS = ("cycling", "running", "rowing")     # os que têm construtor ERG/Manual

# ---- afináveis (Definições → Avançado; ver perennia.core.options)
REST_DEFAULT_S = 120.0          # um descanso novo
GYM_DEFAULT_S = 900.0           # um bloco de ginásio sem exercícios ainda


def sport_name(sport: str) -> str:
    return {"cycling": tr("Ciclismo", "Cycling"), "running": tr("Passadeira", "Treadmill"),
            "rowing": tr("Remo", "Rowing"), "gym": tr("Ginásio", "Gym"),
            "rest": tr("Descanso", "Rest")}.get(sport, sport)


def control_name(control: str) -> str:
    return "ERG" if control == "erg" else tr("Manual", "Manual")


# ------------------------------------------------------------------- blocos


def new_block(sport: str, control: str = "manual", **kw) -> dict:
    b = {"sport": sport, "control": control if sport in ERG_SPORTS else "manual",
         "name": kw.pop("name", "") or sport_name(sport)}
    if sport == "rest":
        b["seconds"] = float(kw.pop("seconds", REST_DEFAULT_S))
    b.update(kw)
    return b


def endurance_payload(blocks: list[Block], mode: str) -> dict:
    return {"blocks": [asdict(x) for x in blocks], "mode": mode}


def to_blocks(b: dict) -> list[Block]:
    out = []
    for d in b.get("blocks") or []:
        d = dict(d)
        out.append(Block(**{k: d[k] for k in ("kind", "dur_type", "dur", "lo", "hi", "cue",
                                              "extra", "goal") if k in d}))
    return out


def _ctx(db, sport: str, cache: dict | None = None):
    """O contexto de intensidade do desporto (FTP, limiares…); com `cache`, lê-se da base de
    dados uma vez por desporto (o construtor refaz as contas a cada tecla)."""
    if cache is not None and sport in cache:
        return cache[sport]
    try:
        ctx = it.Context.from_db(db, sport)
    except Exception:
        ctx = None
    if cache is not None:
        cache[sport] = ctx
    return ctx


def seconds(db, b: dict, cache: dict | None = None) -> float:
    """A duração do bloco (s): a soma dos blocos do construtor, a estimativa do ginásio, ou
    o tempo do descanso."""
    sport = b.get("sport")
    if sport in ENDURANCE and b.get("blocks"):
        ctx = _ctx(db, sport, cache)
        if ctx is not None:
            return float(sum(block_seconds(x, ctx) for x in to_blocks(b)))
        return float(sum(x.dur for x in to_blocks(b) if x.dur_type == "time"))
    if sport == "gym" and b.get("struct") and (b["struct"].get("blocks") or []):
        from . import strength_builder as sb
        try:
            return float(sb.estimate_seconds(b["struct"]))
        except Exception:
            pass
    if sport == "gym" and b.get("legacy"):          # uma volta de força de um plano antigo
        from . import laps_session as ls
        return float(ls.plan_seconds([b["legacy"]]))
    if sport == "gym":
        return float(b.get("seconds") or GYM_DEFAULT_S)
    return float(b.get("seconds") or 0.0)


def steps(db, b: dict, cache: dict | None = None) -> list[dict]:
    """Os passos que guiam o bloco na sessão: [{"seconds", "text", "watts"}]. Ginásio: um
    passo por exercício (sem tempo próprio: o bloco conta o total)."""
    from . import objectives as ob
    sport = b.get("sport")
    out: list[dict] = []
    if sport in ENDURANCE:
        ctx = _ctx(db, sport, cache)
        for x in to_blocks(b):
            secs = block_seconds(x, ctx) if ctx is not None else x.dur
            text = ob.target_text(x.kind, x.lo, x.hi, ctx, sport) if ctx is not None else ""
            watts = ctx.watts(x.mid()) if (ctx is not None and x.lo is not None
                                           and sport == "cycling") else None
            if x.cue:
                text = f"{text} · {x.cue.split('  ·  ')[0]}" if text else x.cue
            out.append({"seconds": float(secs), "text": text, "watts": watts})
    elif sport == "gym" and b.get("struct"):
        from . import strength_builder as sb
        for _lab, name, presc in sb.summary_lines(b["struct"]):
            if not presc:                    # o cabeçalho de um bloco (série, circuito)
                continue
            out.append({"seconds": None, "text": f"{name} · {presc}".strip(" ·"),
                        "watts": None})
    return out


def summary(db, b: dict) -> str:
    """«3 passos · ERG · 63–88 % FTP» — o que a linha do bloco mostra por baixo."""
    sport = b.get("sport")
    if sport == "rest":
        return tr("descanso", "rest")
    bits = []
    if sport in ERG_SPORTS:
        bits.append(control_name(b.get("control") or "manual"))
    if sport in ENDURANCE:
        n = len(b.get("blocks") or [])
        bits.append(tr("{n} passos", "{n} steps", n=n) if n != 1 else tr("1 passo", "1 step"))
    if sport == "gym":
        from . import gym
        bits.append(gym.modality(b.get("modality")).name)
        ex = sum(len(x.get("exercises") or []) for x in (b.get("struct") or {}).get("blocks")
                 or [])
        bits.append(tr("{n} exercícios", "{n} exercises", n=ex) if ex else
                    tr("exercícios marcados na sessão", "exercises marked in the session"))
    return " · ".join(bits)


def total_by_sport(db, blocks: list[dict], cache: dict | None = None) -> dict[str, float]:
    """{desporto: segundos} pela ordem em que aparecem; o descanso conta para o bloco de
    antes (como na sessão e nos .fit)."""
    out: dict[str, float] = {}
    prev = None
    pending = 0.0
    for b in blocks:
        s = b.get("sport")
        secs = seconds(db, b, cache)
        if s == "rest":
            if prev is None:
                pending += secs
            else:
                out[prev] += secs
            continue
        out[s] = out.get(s, 0.0) + secs + pending
        pending = 0.0
        prev = s
    if pending and not out:
        out["rest"] = pending
    return out


def duplicate(blocks: list[dict], i: int) -> int:
    """Duplica o bloco `i` logo a seguir; devolve o índice da cópia."""
    blocks.insert(i + 1, copy.deepcopy(blocks[i]))
    return i + 1


def move(blocks: list[dict], src: int, dst: int) -> int:
    """Leva o bloco `src` para a posição `dst` (arrastar); devolve onde ficou."""
    if not (0 <= src < len(blocks)):
        return src
    dst = max(0, min(len(blocks) - 1, dst))
    b = blocks.pop(src)
    blocks.insert(dst, b)
    return dst


# ------------------------------------------------------------- gravar e ler


def to_items(db, blocks: list[dict]) -> list[dict]:
    """Os itens de `lap_plans` (e do motor por voltas): uma volta planeada por bloco."""
    cache: dict = {}
    out = []
    for b in blocks:
        if b.get("legacy"):                 # a volta de força de um plano antigo, tal e qual
            item = dict(b["legacy"])
            item["cond"] = copy.deepcopy(b)
            out.append(item)
            continue
        item: dict[str, Any] = {"kind": LAP_KIND[b["sport"]],
                                "seconds": round(seconds(db, b, cache)),
                                "name": b.get("name") or sport_name(b["sport"]),
                                "cond": copy.deepcopy(b)}
        st = steps(db, b, cache)
        if st:
            item["steps"] = st
        if b["sport"] in ERG_SPORTS:
            item["control"] = b.get("control") or "manual"
        out.append(item)
    return out


def from_items(items: list[dict]) -> list[dict]:
    """Os blocos de um plano gravado; um plano antigo (voltas soltas) vira blocos simples."""
    out = []
    for it_ in items or []:
        if isinstance(it_.get("cond"), dict):
            out.append(copy.deepcopy(it_["cond"]))
            continue
        sport = SPORT_OF_KIND.get(it_.get("kind") or "rest", "gym")
        b = new_block(sport, "manual", name=it_.get("name") or "")
        if sport == "running" and it_.get("seconds"):       # uma volta de passadeira: 1 passo
            b.update(endurance_payload([Block("active", "time", float(it_["seconds"]), None)],
                                       "rpe"))
        elif sport == "rowing" and it_.get("seconds"):
            b.update(endurance_payload([Block("active", "time", float(it_["seconds"]), None)],
                                       "power"))
        elif sport == "gym":
            if it_.get("exercise_id") or it_.get("reps"):    # o exercício e as repetições
                b["legacy"] = dict(it_)
                b["name"] = it_.get("name") or b["name"]
            else:
                b["seconds"] = float(it_.get("seconds") or GYM_DEFAULT_S)
        else:
            b["seconds"] = float(it_.get("seconds") or REST_DEFAULT_S)
        out.append(b)
    return out


def sports_used(blocks: list[dict]) -> list[str]:
    """Os desportos do treino (sem o descanso), pela ordem."""
    seen: list[str] = []
    for b in blocks:
        s = b.get("sport")
        if s != "rest" and s not in seen:
            seen.append(s)
    return seen
