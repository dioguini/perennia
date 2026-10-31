"""Objetivos dos treinos: o objetivo geral do treino e o de cada bloco, com o alvo.

Cada treino responde a «o que é que isto treina?» numa frase, e cada bloco
diz o que se faz ali e qual é o alvo (watts, ritmo, FC ou RPE). O objetivo
fica guardado à parte dos passos (tabela `workout_goals`), igual para todos
os desportos, e é o que depois se cruza com o feedback no fim da sessão.

Quando ninguém escreveu nada, o texto sai da estrutura do treino: o bloco
em Z2 de 20 min diz «Trabalho contínuo em Z2…», e o treino diz que é de
resistência aeróbia. Os treinos que vêm com a aplicação têm objetivos
escritos à mão (LIBRARY_GOALS).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import intensity as it
from .i18n import tr
from .units import hms

# ----------------------------------------------------------------- modelo


@dataclass
class BriefBlock:
    name: str
    goal: str
    target: str
    seconds: float
    meters: float | None
    lo: float | None              # % do limiar (None = livre)
    hi: float | None
    kind: str = "active"
    repeat: int = 1               # blocos repetidos juntos: «6 × …»
    dur_text: str = ""
    indices: list = field(default_factory=list)   # que blocos reais representa


@dataclass
class Brief:
    sport: str
    title: str
    goal: str
    intensity: str                # «Intensidade fácil, esforço percebido 3/10»
    target_rpe: float | None
    seconds: float
    meters: float
    tss: float
    blocks: list[BriefBlock] = field(default_factory=list)   # já comprimidos
    raw_blocks: list[BriefBlock] = field(default_factory=list)
    threshold_label: str = ""     # «FTP 250 W» (linha tracejada do gráfico)
    note: str = ""
    goal_written: bool = False    # escrito por alguém (ou da biblioteca)

    def as_dict(self) -> dict:
        return {"desporto": self.sport, "treino": self.title, "objetivo": self.goal,
                "intensidade": self.intensity, "rpe_previsto": self.target_rpe,
                "duracao_s": round(self.seconds), "blocos": [
                    {"nome": b.name, "objetivo": b.goal, "alvo": b.target,
                     "duracao": b.dur_text, "repeticoes": b.repeat} for b in self.blocks]}


# ------------------------------------------------- objetivos escritos à mão

LIBRARY_GOALS: dict[str, tuple[str, str]] = {
    # ciclismo
    "Força: baixa cadência 5×6": (
        "Força específica: empurrar mudança pesada a 55–60 rpm perto do limiar, como numa "
        "subida longa. O objetivo é força nas pernas, não velocidade de pedalada.",
        "Specific strength: push a big gear at 55–60 rpm near threshold, like a long climb."),
    "Cadência 6×(1 + 2)": (
        "Técnica de pedalada: girar acima de 110 rpm sem saltar no selim. A potência é leve; "
        "conta a fluidez.",
        "Pedalling technique: spin above 110 rpm without bouncing. Power stays light."),
    "Ativação pré-prova 30": (
        "Acordar as pernas para amanhã sem cansar: quase tudo leve, com toques curtos de "
        "intensidade.",
        "Wake the legs for tomorrow without fatigue: mostly easy, with short efforts."),
    "Anaeróbico 8×1": (
        "Capacidade anaeróbia: aguentar 1 min muito acima do limiar e recuperar. Para "
        "ataques e subidas curtas.",
        "Anaerobic capacity: hold 1 min well above threshold, then recover."),
    "Sprints 8×15 s": (
        "Potência neuromuscular: sprints curtos a fundo, com recuperação completa entre eles.",
        "Neuromuscular power: short all-out sprints with full recovery."),
    "Pirâmide 1-2-3-4-3-2-1": (
        "VO2máx com variedade: manter 110 % da FTP em esforços de duração crescente e "
        "decrescente.",
        "VO2max with variety: hold 110 % FTP over rising and falling efforts."),
    "Microintervalos 40/20": (
        "VO2máx: acumular tempo com o coração lá em cima graças às recuperações curtas.",
        "VO2max: build time at high heart rate thanks to short recoveries."),
    "VO2máx 5×4": (
        "Subir o teto aeróbio: 4 minutos a 115 % da FTP, com os últimos 2 muito duros.",
        "Raise the aerobic ceiling: 4 min at 115 % FTP, the last 2 very hard."),
    "VO2máx 30/30": (
        "VO2máx com menos sofrimento por esforço: muitos 30 s duros, com 30 s leves.",
        "VO2max with less pain per rep: many hard 30 s with easy 30 s."),
    "Escada de limiar 5-10-15": (
        "Limiar: aguentar 95 % da FTP cada vez mais tempo, sem baixar no fim.",
        "Threshold: hold 95 % FTP for longer and longer without fading."),
    "Over-unders 3×9": (
        "Limiar com mudanças: limpar o lactato a 95 % depois de cada minuto acima do limiar.",
        "Threshold with surges: clear lactate at 95 % after each minute above."),
    "Sweet spot 2×20": (
        "Subir a FTP com fadiga gerível: 2 blocos longos a 90 %, o segundo deve custar.",
        "Raise FTP with manageable fatigue: 2 long blocks at 90 %."),
    "Limiar 2×20": (
        "Referência do limiar: 2×20 min a 97 % da FTP. Acabar inteiro confirma a FTP.",
        "Threshold benchmark: 2×20 min at 97 % FTP. Finishing confirms your FTP."),
    "Tempo 3×15": (
        "Resistência muscular em Z3: ritmo de estrada sustentado, sem a fadiga do limiar.",
        "Muscular endurance in Z3: sustained road pace without threshold fatigue."),
    "Sweet spot 3×12": (
        "Sweet spot: o melhor rendimento por hora para a FTP, a 88–92 %.",
        "Sweet spot: best return per hour for FTP, at 88–92 %."),
    "Resistência Z2 60": (
        "Base aeróbia: 60 min confortáveis em Z2, sempre a conseguir falar.",
        "Aerobic base: 60 easy minutes in Z2, able to talk throughout."),
    "Resistência Z2 90 com acelerações": (
        "Base aeróbia longa, com acelerações de cadência para manter as pernas ágeis.",
        "Long aerobic base with cadence pick-ups to keep the legs quick."),
    "Recuperação ativa 40": (
        "Recuperação ativa: soltar as pernas depois de um treino duro, sem somar fadiga.",
        "Active recovery: loosen the legs after a hard day without adding fatigue."),
    # remo
    "Base 20 minutos": (
        "Base aeróbia no remo: técnica limpa e voga baixa, ritmo confortável.",
        "Rowing aerobic base: clean technique, low rate, comfortable pace."),
    "8 × 500 m": (
        "Ritmo de prova: repetir 500 m rápidos com o mesmo tempo em todos.",
        "Race pace: repeat fast 500 m with the same split every time."),
    "Limiar 3 × 10 minutos": (
        "Limiar no remo: aguentar o ritmo de limiar 10 min, três vezes.",
        "Rowing threshold: hold threshold pace for 10 min, three times."),
    "Força 6 × 2 min": (
        "Força no remo: resistência alta e voga baixa, puxar com as pernas.",
        "Rowing strength: high resistance, low rate, drive with the legs."),
    "Voga 20-24-28": (
        "Controlo da voga: subir a cadência por patamares sem perder a técnica.",
        "Rate control: step the stroke rate up without losing technique."),
    "Sprints 10 × 20 s": (
        "Potência no remo: 20 s explosivos com recuperação completa.",
        "Rowing power: explosive 20 s with full recovery."),
    # corrida
    "Corrida fácil 40 min": (
        "Base aeróbia: correr solto em Z2, com conversa possível.",
        "Aerobic base: run easy in Z2, conversational."),
    "Intervalos 6 × 800 m": (
        "Velocidade aeróbia: 800 m ao ritmo de 5 km, com recuperação curta.",
        "Aerobic speed: 800 m at 5 km pace with short recovery."),
    "Limiar 3 × 10 min": (
        "Limiar: blocos de 10 min ao ritmo de limiar, constantes do princípio ao fim.",
        "Threshold: 10 min blocks at threshold pace, even from start to finish."),
    "Rodagem longa 70 min": (
        "Resistência: 70 min constantes em Z2 para aguentar distâncias longas.",
        "Endurance: 70 steady minutes in Z2 for long distances."),
    # natação
    "Técnica e base 1500 m": (
        "Técnica e base aeróbia: nadar comprido e relaxado, contar braçadas.",
        "Technique and aerobic base: swim long and relaxed, count strokes."),
    "CSS 8 × 100 m": (
        "Ritmo crítico (CSS): 100 m ao CSS com descanso curto, todos iguais.",
        "Critical swim speed: 100 m at CSS with short rest, all even."),
    "Velocidade 12 × 50 m": (
        "Velocidade: 50 m rápidos com técnica, recuperação completa.",
        "Speed: fast 50 m with good technique and full recovery."),
    # ginásio
    "Força A · corpo inteiro": (
        "Força geral: os grandes movimentos com carga, técnica primeiro, 1–2 repetições "
        "na reserva.",
        "General strength: the big lifts with load, technique first, 1–2 reps in reserve."),
    "Força B · corpo inteiro": (
        "Força geral (variante B): equilibrar empurrar e puxar, pernas e tronco.",
        "General strength (B): balance push and pull, legs and trunk."),
    "Longevidade · força e equilíbrio": (
        "Longevidade: manter força funcional, equilíbrio e mobilidade para o dia a dia.",
        "Longevity: keep functional strength, balance and mobility for daily life."),
}

# --------------------------------------------------------------- textos auto

_ZONE_GOALS = {
    1: ("Recuperação ativa: mexer as pernas e ajudar a recuperar, sem somar fadiga.",
        "Active recovery: move the legs and help recovery without adding fatigue."),
    2: ("Resistência aeróbia: consolidar a base com esforço confortável e constante.",
        "Aerobic endurance: build the base with a steady, comfortable effort."),
    3: ("Tempo: ritmo sustentado para a resistência muscular, sem a fadiga do limiar.",
        "Tempo: sustained pace for muscular endurance without threshold fatigue."),
    4: ("Limiar: aumentar o tempo que aguentas perto do limiar.",
        "Threshold: extend how long you can hold near threshold."),
    5: ("VO2máx: intervalos duros para subir o teto aeróbio.",
        "VO2max: hard intervals to raise the aerobic ceiling."),
    6: ("Anaeróbio: esforços curtos e explosivos muito acima do limiar.",
        "Anaerobic: short, explosive efforts well above threshold."),
    7: ("Sprints: potência máxima em esforços muito curtos.",
        "Sprints: maximal power in very short efforts."),
}

_BLOCK_GOALS = {
    1: ("Rolar muito leve, recuperação ativa.", "Very easy, active recovery."),
    2: ("Trabalho contínuo em Z2: aeróbio e confortável.", "Steady Z2: aerobic and easy."),
    3: ("Ritmo de tempo (Z3): sustentado, respiração controlada.",
        "Tempo (Z3): sustained, controlled breathing."),
    4: ("Limiar (Z4): duro mas constante até ao fim.", "Threshold (Z4): hard but even."),
    5: ("VO2máx (Z5): muito duro; o fim custa.", "VO2max (Z5): very hard; the end hurts."),
    6: ("Anaeróbio (Z6): curto e explosivo.", "Anaerobic (Z6): short and explosive."),
    7: ("Sprint a fundo.", "All-out sprint."),
}


def threshold_word(sport: str) -> str:
    return {"running": tr("limiar", "threshold"), "swimming": "CSS"}.get(sport, "FTP")


def block_name(kind: str, n_active: int, k_active: int) -> str:
    if kind == "warmup":
        return tr("Aquecimento", "Warm-up")
    if kind == "cooldown":
        return tr("Arrefecimento", "Cool-down")
    if kind == "rest":
        return tr("Recuperação", "Recovery")
    if n_active <= 1:
        return tr("Principal", "Main set")
    return tr("Esforço {n}", "Effort {n}", n=k_active)


def block_goal(kind: str, lo: float | None, hi: float | None, sport: str = "cycling") -> str:
    if lo is None:
        return tr("Livre: ao teu ritmo.", "Free: at your own pace.")
    end = hi if hi is not None else lo
    za, zb = it.zone(lo), it.zone(end)
    if kind == "warmup":
        if za != zb:
            return tr("Aquecimento progressivo de Z{a} a Z{b}.",
                      "Progressive warm-up from Z{a} to Z{b}.", a=za, b=zb)
        return tr("Aquecer em Z{a}, a soltar as pernas.", "Warm up in Z{a}.", a=za)
    if kind == "cooldown":
        return tr("Arrefecer em Z{a}, a baixar a FC.", "Cool down in Z{a}, let HR drop.",
                  a=min(za, zb))
    if kind == "rest":
        return tr("Recuperar entre esforços: leve, sem parar.",
                  "Recover between efforts: easy, keep moving.")
    if za != zb:
        return tr("Rampa de Z{a} a Z{b}: subir aos poucos.", "Ramp from Z{a} to Z{b}.",
                  a=za, b=zb)
    return tr(*_BLOCK_GOALS[min(7, za)])


def target_text(kind: str, lo: float | None, hi: float | None, ctx: it.Context,
                sport: str) -> str:
    """«FTP 63–73 % · 158–183 W», «5:10–5:30 /km · RPE 6» ou «RPE 2–3»."""
    if lo is None:
        return tr("livre", "free")
    end = hi if hi is not None else lo
    if abs(end - lo) < 0.5:
        a, b = max(30.0, lo - 5), lo + 5
        arrow = "–"
    elif sport != "cycling":                # remo, corrida, natação: lo–hi é um intervalo
        a, b = min(lo, end), max(lo, end)
        arrow = "–"
    else:                                   # rampa: do início ao fim
        a, b = lo, end
        arrow = "→"
    ra, rb = round(ctx.rpe(min(a, b))), round(ctx.rpe(max(a, b)))
    rpe = f"RPE {ra:g}" if ra == rb else f"RPE {ra:g}–{rb:g}"
    if kind in ("warmup", "cooldown", "rest") and max(a, b) < 76:
        return rpe
    word = threshold_word(sport)
    if sport == "cycling":
        return f"{word} {a:.0f}{arrow}{b:.0f} % · {ctx.watts(a)}{arrow}{ctx.watts(b)} W"
    if sport == "rowing":
        pa, pb = ctx.pace(max(a, b)), ctx.pace(min(a, b))
        pace = f" · {hms(pa)}–{hms(pb)} /500 m" if pa and pb else ""
        return f"{ctx.watts(a)}{arrow}{ctx.watts(b)} W{pace}"
    unit = "/km" if sport == "running" else "/100 m"
    pa, pb = ctx.pace(max(a, b)), ctx.pace(min(a, b))     # do mais rápido ao mais lento
    if pa and pb:
        return f"{hms(pa)}–{hms(pb)} {unit} · {rpe}"
    return rpe


def intensity_text(if_: float, rpe: float | None) -> str:
    if if_ < 0.6:
        word = tr("muito fácil", "very easy")
    elif if_ < 0.72:
        word = tr("fácil", "easy")
    elif if_ < 0.83:
        word = tr("moderada", "moderate")
    elif if_ < 0.92:
        word = tr("dura", "hard")
    else:
        word = tr("muito dura", "very hard")
    s = tr("Intensidade {w}", "{w} intensity", w=word)
    if rpe is not None:
        s += tr(", esforço percebido {r}/10", ", perceived effort {r}/10", r=f"{rpe:g}")
    return s[0].upper() + s[1:]


def dur_text(seconds: float, meters: float | None) -> str:
    if meters:
        return f"{meters / 1000:g} km" if meters >= 1000 else f"{meters:g} m"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{int(seconds // 60)} min"
    return hms(seconds) if seconds >= 60 else f"{int(seconds)} s"


def auto_goal(raw: list[BriefBlock]) -> str:
    """Objetivo pela zona onde o treino passa mais tempo em esforço."""
    work = [b for b in raw if b.kind not in ("warmup", "cooldown", "rest") and b.lo is not None]
    if not work:
        work = [b for b in raw if b.lo is not None]
    if not work:
        return tr("Treino livre: ao teu ritmo, a ouvir o corpo.",
                  "Free session: at your own pace, listening to your body.")
    by_zone: dict[int, float] = {}
    for b in work:
        mid = (b.lo + (b.hi if b.hi is not None else b.lo)) / 2
        by_zone[it.zone(mid)] = by_zone.get(it.zone(mid), 0.0) + b.seconds
    top = max(by_zone, key=lambda z: (by_zone[z] * (1 + 0.6 * (z - 1)), z))
    return tr(*_ZONE_GOALS[min(7, top)])


# --------------------------------------------------------------- guardar


def ensure(db) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS workout_goals (sport TEXT NOT NULL, workout_id TEXT NOT NULL,"
        " goal TEXT, blocks TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " PRIMARY KEY (sport, workout_id))")
    db.conn.commit()


def stored(db, sport: str, wid: str | None) -> dict:
    if not wid:
        return {}
    ensure(db)
    r = db.conn.execute("SELECT goal, blocks FROM workout_goals WHERE sport=? AND workout_id=?",
                        (sport, str(wid))).fetchone()
    if r is None:
        return {}
    try:
        blocks = json.loads(r[1] or "[]")
    except ValueError:
        blocks = []
    return {"goal": r[0] or "", "blocks": blocks}


def save(db, sport: str, wid: str, goal: str | None = None,
         blocks: list[dict] | None = None) -> None:
    """Grava o objetivo geral e/ou os dos blocos ([{name, goal}] pela ordem)."""
    ensure(db)
    cur = stored(db, sport, wid)
    g = cur.get("goal", "") if goal is None else goal
    b = cur.get("blocks", []) if blocks is None else blocks
    db.conn.execute(
        "INSERT INTO workout_goals (sport, workout_id, goal, blocks) VALUES (?,?,?,?)"
        " ON CONFLICT(sport, workout_id) DO UPDATE SET goal=excluded.goal,"
        " blocks=excluded.blocks, updated_at=CURRENT_TIMESTAMP",
        (sport, str(wid), g, json.dumps(b, ensure_ascii=False)))
    db.conn.commit()


def library_goal(name: str) -> str:
    g = LIBRARY_GOALS.get((name or "").strip())
    return tr(*g) if g else ""


# --------------------------------------------------------------- construir


def build(db, sport: str, wid: str | None, title: str, blocks: list,
          ctx: it.Context | None = None, description: str = "") -> Brief:
    """O resumo do treino a partir dos blocos (objetos com kind, dur_type, dur,
    lo e hi/end_pct, como os do construtor)."""
    ctx = ctx or it.Context.from_db(db, sport)
    saved = stored(db, sport, wid)
    saved_blocks = saved.get("blocks") or []
    kinds = _kinds(blocks)
    mids = [_mid(b) or 0 for b in blocks]
    n_hard = sum(1 for k, m in zip(kinds, mids) if k == "active" and m >= 76)
    main_idx = -1
    if n_hard <= 1:                    # treino contínuo: o bloco mais longo é o principal
        cands = [i for i, k in enumerate(kinds) if k not in ("warmup", "cooldown")]
        if cands:
            main_idx = max(cands, key=lambda i: float(getattr(blocks[i], "dur", 0) or 0))
    raw: list[BriefBlock] = []
    k_hard = 0
    secs = meters = load = 0.0
    rpe_t = 0.0
    for i, b in enumerate(blocks):
        kind = kinds[i]
        lo = getattr(b, "lo", None)
        hi = getattr(b, "end_pct", None) if hasattr(b, "end_pct") else getattr(b, "hi", None)
        if lo is not None and hi is not None and abs(hi - lo) < 0.5:
            hi = None
        dur = float(getattr(b, "dur", 0) or 0)
        is_dist = getattr(b, "dur_type", "time") == "distance"
        mid = 50.0 if lo is None else (lo + (hi if hi is not None else lo)) / 2
        s = dur / max(0.3, ctx.speed_mps(mid)) if is_dist else dur
        if kind == "active" and mid >= 76:
            k_hard += 1
        sb = saved_blocks[i] if i < len(saved_blocks) and isinstance(saved_blocks[i], dict) \
            else {}
        if i == main_idx:
            auto_name = tr("Principal", "Main set")
        elif kind == "active" and (mid < 76 or n_hard == 0):
            auto_name = tr("Bloco aeróbio", "Aerobic block")
        else:
            auto_name = block_name(kind, n_hard, k_hard)
        name = sb.get("name") or auto_name
        tgt = target_text(kind, lo, hi, ctx, sport)
        if sport != "cycling" and lo is not None and hi is not None:
            lo, hi = mid, None          # remo, corrida, natação: um intervalo, não uma rampa
        cue = (getattr(b, "cue", "") or "").strip()
        # uma deixa curta («On: 120 %», «Bem leve») não é um objetivo
        goal = sb.get("goal") or (cue if len(cue) >= 15 else "") or \
            block_goal(kind, lo, hi, sport)
        raw.append(BriefBlock(name, goal, tgt, s,
                              dur if is_dist else None, lo, hi, kind,
                              dur_text=dur_text(s, dur if is_dist else None), indices=[i]))
        secs += s
        meters += dur if is_dist else 0.0
        load += s / 3600 * (mid / 100) ** 2 * 100
        rpe_t += s * ctx.rpe(mid)
    if_ = (load / (secs / 3600) / 100) ** 0.5 if secs else 0.0
    rpe = round(ctx.rpe(if_ * 100)) if secs else None
    goal = saved.get("goal") or library_goal(title)
    written = bool(goal)
    if not goal:
        goal = auto_goal(raw)
    if sport == "cycling":
        thr = f"FTP {ctx.ftp_w} W"
    elif sport == "rowing":
        thr = f"FTP {ctx.row_ftp_w} W"
    elif sport == "running":
        thr = tr("Limiar {p} /km", "Threshold {p} /km", p=hms(ctx.run_pace_s))
    else:
        thr = f"CSS {hms(ctx.swim_css_s)} /100 m"
    return Brief(sport, title, goal, intensity_text(if_, rpe), rpe, secs, meters, load,
                 compress(raw), raw, thr, description, written)


def _mid(b) -> float | None:
    lo = getattr(b, "lo", None)
    if lo is None:
        return None
    hi = getattr(b, "end_pct", None) if hasattr(b, "end_pct") else getattr(b, "hi", None)
    return (lo + (hi if hi is not None else lo)) / 2


def _kinds(blocks: list) -> list[str]:
    """Os blocos leves antes do primeiro esforço a sério são aquecimento, e os
    leves depois do último são arrefecimento (o construtor só sabe «ativo»)."""
    kinds = [getattr(b, "kind", "active") or "active" for b in blocks]
    hard = [i for i, b in enumerate(blocks) if (_mid(b) or 0) >= 76]
    if not hard:
        return kinds
    for i in range(hard[0]):
        if kinds[i] == "active" and (_mid(blocks[i]) or 0) < 76:
            kinds[i] = "warmup"
    for i in range(hard[-1] + 1, len(blocks)):
        if kinds[i] == "active" and (_mid(blocks[i]) or 100) < 70:
            kinds[i] = "cooldown"
    return kinds


def _merge_edges(raw: list[BriefBlock]) -> list[BriefBlock]:
    """Aquecimento (ou arrefecimento) partido em vários passos fica um só."""
    out: list[BriefBlock] = []
    for b in raw:
        prev = out[-1] if out else None
        if prev is not None and b.kind == prev.kind and b.kind in ("warmup", "cooldown") \
                and b.meters is None and prev.meters is None:
            los = [x for x in (prev.lo, prev.hi, b.lo, b.hi) if x is not None]
            lo, hi = (prev.lo, b.hi if b.hi is not None else b.lo) if los else (None, None)
            secs = prev.seconds + b.seconds
            merged = BriefBlock(prev.name, prev.goal, prev.target, secs, None, lo, hi,
                                b.kind, dur_text=dur_text(secs, None),
                                indices=list(prev.indices) + list(b.indices))
            if los:
                za, zb = it.zone(min(los)), it.zone(max(los))
                if b.kind == "warmup" and za != zb:
                    merged.goal = tr("Aquecimento progressivo de Z{a} a Z{b}.",
                                     "Progressive warm-up from Z{a} to Z{b}.", a=za, b=zb)
                ctx_t = prev.target.split("RPE")[0]
                lo_r = prev.target.split("RPE")[-1].strip().split("–")[0]
                hi_r = b.target.split("RPE")[-1].strip().split("–")[-1]
                if "RPE" in prev.target and "RPE" in b.target and not ctx_t.strip():
                    merged.target = f"RPE {lo_r}–{hi_r}" if lo_r != hi_r else f"RPE {lo_r}"
            out[-1] = merged
        else:
            out.append(b)
    return out


def compress(raw: list[BriefBlock]) -> list[BriefBlock]:
    """Junta repetições: 10 × (30 s Z5 + 30 s Z1) aparece uma vez com «10 ×»."""
    raw = _merge_edges(raw)
    out: list[BriefBlock] = []
    i = 0
    n = len(raw)

    def same(a: BriefBlock, b: BriefBlock) -> bool:
        return (a.kind, round(a.seconds), a.meters, a.lo, a.hi) == \
               (b.kind, round(b.seconds), b.meters, b.lo, b.hi)

    while i < n:
        best_p, best_k = 1, 1
        for p in (1, 2, 3, 4):
            k = 1
            while i + (k + 1) * p <= n and all(same(raw[i + j], raw[i + k * p + j])
                                               for j in range(p)):
                k += 1
            if k > 1 and k * p > best_k * best_p:
                best_p, best_k = p, k
        if best_k > 1:
            group = raw[i:i + best_p]
            # o último esforço muitas vezes não tem a recuperação a seguir
            tail = 0
            while tail < best_p - 1 and i + best_k * best_p + tail < n and \
                    same(raw[i + best_k * best_p + tail], group[tail]):
                tail += 1
            for j, b in enumerate(group):
                count = best_k + (1 if j < tail else 0)
                idxs = [x for r in range(count) for x in raw[i + r * best_p + j].indices]
                out.append(BriefBlock(b.name if best_p == 1 or b.kind != "active" else
                                      tr("Esforço", "Effort"), b.goal, b.target, b.seconds,
                                      b.meters, b.lo, b.hi, b.kind,
                                      repeat=count if j == 0 else -count,
                                      dur_text=b.dur_text, indices=idxs))
            i += best_k * best_p + tail
        else:
            out.append(raw[i])
            i += 1
    return out


def block_at(brief: Brief, t: float) -> tuple[int, BriefBlock | None]:
    """O bloco (não comprimido) em curso ao fim de `t` segundos."""
    acc = 0.0
    for i, b in enumerate(brief.raw_blocks):
        acc += b.seconds
        if t < acc:
            return i, b
    return len(brief.raw_blocks), None


# --------------------------------------------------------------- outros


def gym_brief(db, wid: str, title: str, items: list[dict], modality: str = "strength") -> Brief:
    """Planos do ginásio: cada exercício é um bloco; o alvo é séries × reps,
    carga, RPE e descanso; a intensidade vem do RPE pedido."""
    saved = stored(db, "gym", wid)
    sb = saved.get("blocks") or []
    raw: list[BriefBlock] = []
    secs = rpe_t = 0.0
    def g(x, k):
        return x.get(k) if isinstance(x, dict) else getattr(x, k, None)

    for i, x in enumerate(items):
        sets = int(g(x, "sets") or 1)
        reps = g(x, "reps")
        tsec = reps if g(x, "measure") == "time" else g(x, "time_s")
        rest = int(g(x, "rest_s") or 0)
        kg = g(x, "load_kg") or g(x, "weight_kg")
        rpe = g(x, "rpe")
        work = sets * (float(tsec) if tsec else (reps or 10) * 3.5)
        s = work + max(0, sets - 1) * rest
        bits = [f"{sets} × " + (f"{int(tsec)} s" if tsec else f"{reps or '—'}")]
        if kg:
            bits.append(f"{kg:g} kg")
        if rpe:
            bits.append(f"RPE {rpe:g}")
        if rest:
            bits.append(tr("descanso {s} s", "rest {s} s", s=rest))
        pct = it._inverse(it.RPE_POINTS, float(rpe)) if rpe else 75.0
        extra = sb[i] if i < len(sb) and isinstance(sb[i], dict) else {}
        name = extra.get("name") or g(x, "name") or tr("Exercício", "Exercise")
        goal = extra.get("goal") or g(x, "notes") or tr(
            "Técnica limpa em todas as repetições; parar se a forma cair.",
            "Clean technique on every rep; stop if form breaks.")
        raw.append(BriefBlock(name, goal, " · ".join(bits), s, None, pct, None, "active",
                              dur_text=dur_text(s, None), indices=[i]))
        secs += s
        rpe_t += s * (float(rpe) if rpe else 7.0)
    rpe = round(rpe_t / secs) if secs else None
    goal = saved.get("goal") or library_goal(title)
    written = bool(goal)
    if not goal:
        from . import gym as gym_mod
        m = gym_mod.MODALITIES.get(modality)
        goal = (m.desc if m and m.desc else
                tr("Força e técnica: cada série com controlo, sem chegar à falha.",
                   "Strength and technique: controlled sets, short of failure."))
    if_ = {None: 0.75}.get(rpe, 0.55 + 0.05 * (rpe or 7))
    return Brief("gym", title, goal, intensity_text(if_, rpe), rpe, secs, 0.0, 0.0,
                 raw, raw, "", "", written)


def workout_brief(db, sport: str, wid: str | None) -> Brief | None:
    """O resumo de um treino guardado, de qualquer desporto (None se não houver)."""
    if not wid:
        return None
    if sport in ("gym", "strength"):
        from . import strength as st
        wk = st.workout(db, wid)
        if wk is None:
            return None
        return gym_brief(db, wid, wk["name"], st.workout_items(db, wid),
                         wk.get("modality") or "strength")
    from .blocks import load_blocks
    try:
        name, desc, _mode, blocks = load_blocks(db, sport, wid)
    except Exception:
        return None
    if not name and not blocks:
        return None
    return build(db, sport, wid, name, blocks, description=desc)
