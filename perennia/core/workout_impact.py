"""O impacto de um treino: o que está planeado (no construtor) e o que a sessão fez.

Para um treino por **potência** (ou por % do limiar), a Perennia mostra logo ao criá-lo:

* o **IF** (fator de intensidade) e a **TSS** estimados;
* o **efeito em cada sistema do desporto** — Resistência (aeróbia), Tempo, Limiar, VO2máx,
  Anaeróbio e Sprint (neuromuscular) — de 0 a 5, como o *Training Effect*: 0–0,9 sem efeito,
  1–1,9 pouco, 2–2,9 mantém, 3–3,9 melhora, 4–4,9 melhora muito, 5 excessivo. Cada sistema liga-se
  à **característica do teu perfil** que puxa (no ciclismo: Sprint 5 s, Anaeróbio 1 min, VO2máx
  5 min, Limiar/FTP), com o teu nível de agora e a marca «o teu ponto fraco» quando é o caso;
* o **impacto no índice de longevidade** (numa semana, num mês, em três meses) e os eixos onde
  mais mexe.

Quando a sessão desse treino acaba, `for_session` junta o **planeado** (a cópia do treino que a
sessão guardou) e o **realizado** (as amostras de potência da sessão): o IF feito contra o IF
alvo, e os dois impactos lado a lado (sistemas e longevidade), para sobrepor.

**Como se conta o efeito de um sistema.** O tempo em cada zona de potência (Coggan, % da FTP)
dá minutos a cada sistema, com um peso (`ZONE_SYSTEMS`): Z2 é Resistência; Z3 é Tempo e um pouco
de Resistência; Z4 é Limiar (e um pouco de Tempo); Z5 é VO2máx; Z6 Anaeróbio; Z7 Sprint. O efeito
satura: `5 · (1 − e^(−minutos ÷ referência))`, com a referência de cada sistema em `REF_MIN`
(os minutos que dão ≈ 3,2 — «melhora»). É uma aproximação transparente, não um modelo fisiológico
fechado.

Sem pyglet: os ecrãs só desenham o que isto devolve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from . import intensity as it
from .i18n import tr

SYSTEMS = ("endurance", "tempo", "threshold", "vo2max", "anaerobic", "sprint")
SYSTEM_NAMES = {"endurance": ("Resistência", "Endurance"), "tempo": ("Tempo", "Tempo"),
                "threshold": ("Limiar", "Threshold"), "vo2max": ("VO2máx", "VO2max"),
                "anaerobic": ("Anaeróbio", "Anaerobic"), "sprint": ("Sprint", "Sprint")}
# zona de potência (1–7) → {sistema: peso dos minutos}
ZONE_SYSTEMS = (
    {"endurance": 0.4},                                        # Z1 recuperação
    {"endurance": 1.0},                                        # Z2 resistência
    {"endurance": 0.6, "tempo": 1.0},                          # Z3 tempo
    {"endurance": 0.3, "tempo": 0.5, "threshold": 1.0},        # Z4 limiar
    {"threshold": 0.3, "vo2max": 1.0},                         # Z5 VO2máx
    {"vo2max": 0.4, "anaerobic": 1.0},                         # Z6 anaeróbio
    {"anaerobic": 0.3, "sprint": 1.0},                         # Z7 neuromuscular
)
# os minutos (já pesados) que dão ≈ 3,2 de efeito («melhora»)
REF_MIN = {"endurance": 90.0, "tempo": 40.0, "threshold": 25.0, "vo2max": 12.0,
           "anaerobic": 5.0, "sprint": 1.5}
EFFECT_MAX = 5.0
EFFECT_LEVELS = ((1.0, ("sem efeito", "no effect")), (2.0, ("pouco", "minor")),
                 (3.0, ("mantém", "maintains")), (4.0, ("melhora", "improves")),
                 (5.0, ("melhora muito", "highly improves")), (99.0, ("excessivo", "overreaching")))
# sistema → a duração do perfil de ciclismo que ele puxa (perennia.core.profile)
PROFILE_KEY = {"sprint": 5, "anaerobic": 60, "vo2max": 300, "threshold": "ft", "tempo": "ft"}
IF_TOLERANCE = 0.03            # IF feito a ±0,03 do alvo: «no alvo»
POWER_SPORTS = ("cycling", "rowing")


def system_name(s: str) -> str:
    return tr(*SYSTEM_NAMES.get(s, (s, s)))


def effect_level(v: float) -> str:
    for cut, (pt, en) in EFFECT_LEVELS:
        if v < cut:
            return tr(pt, en)
    return tr(*EFFECT_LEVELS[-1][1])


def fmt_if(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


@dataclass
class Impact:
    """O impacto de um treino (planeado) ou de uma sessão (realizado)."""
    seconds: float = 0.0
    tss: float | None = None
    if_: float | None = None
    zones: list = field(default_factory=lambda: [0.0] * 7)     # segundos por zona (Z1..Z7)
    systems: dict = field(default_factory=dict)                 # sistema → efeito 0–5
    longevity: dict = field(default_factory=dict)               # {deltas, axes, top, mins}
    source: str = "planned"                                     # planned | actual

    @property
    def focus(self) -> str | None:
        """O sistema onde o treino mais mexe."""
        best = max(self.systems.items(), key=lambda kv: kv[1], default=(None, 0.0))
        return best[0] if best[1] >= 1.0 else None


def system_minutes(zone_seconds: list[float]) -> dict:
    """Os minutos (pesados) de cada sistema a partir do tempo em cada zona."""
    out = {s: 0.0 for s in SYSTEMS}
    for z, secs in enumerate(list(zone_seconds)[:len(ZONE_SYSTEMS)]):
        for s, w in ZONE_SYSTEMS[z].items():
            out[s] += float(secs or 0.0) / 60.0 * w
    return out


def effects(zone_seconds: list[float]) -> dict:
    """{sistema: efeito de 0 a 5} (satura: ver o topo do módulo)."""
    mins = system_minutes(zone_seconds)
    return {s: round(EFFECT_MAX * (1.0 - math.exp(-mins[s] / REF_MIN[s])), 2)
            for s in SYSTEMS}


def _zones7(seconds: list[float]) -> list[float]:
    z = [float(x or 0.0) for x in list(seconds)[:7]]
    return z + [0.0] * (7 - len(z))


# ------------------------------------------------------------------ planeado


def planned(db, sport: str, blocks, ctx=None, doses=None) -> Impact:
    """O impacto de um treino ainda por fazer (os blocos do construtor)."""
    from . import longevity as lg
    from .blocks import estimate
    ctx = ctx or it.Context.from_db(db, sport)
    est = estimate(list(blocks), ctx)
    imp = Impact(seconds=est["seconds"], tss=est["tss"], if_=est["if"] if est["seconds"] else None,
                 zones=_zones7(est["zones"]), source="planned")
    imp.systems = effects(imp.zones)
    try:
        mins = lg.blocks_mins(list(blocks), sport)
        lon = lg.impact_of(db, mins, sport=sport, doses=doses)
        lon["mins"] = mins
        imp.longevity = lon
    except Exception:
        imp.longevity = {}
    return imp


# ------------------------------------------------------------------ realizado


def _ride_actual(db, sid: str) -> Impact | None:
    from . import stats
    r = db.conn.execute("SELECT * FROM rides WHERE id = ?", (sid,)).fetchone()
    if r is None:
        return None
    zones = (stats.ride_zone_seconds(db).get(sid) or {}).get("power") or []
    secs = float(r["moving_s"] or r["elapsed_s"] or 0)
    if_ = r["intensity_factor"]
    if not if_ and r["np_w"] and r["ftp_at_ride_w"]:
        if_ = float(r["np_w"]) / float(r["ftp_at_ride_w"])
    return Impact(seconds=secs, tss=r["tss"], if_=float(if_) if if_ else None,
                  zones=_zones7(zones), source="actual")


def _row_actual(db, sid: str) -> Impact | None:
    r = db.conn.execute("SELECT * FROM row_sessions WHERE id = ?", (sid,)).fetchone()
    if r is None:
        return None
    ftp = float(r["ftp_w"] or 0) or None
    if ftp is None:
        try:
            from .rowing import row_ftp
            ftp = float(row_ftp(db))
        except Exception:
            ftp = 200.0
    bounds = db.get("power_zones_pct", list(it.ZONE_BOUNDS))
    zones = [0.0] * (len(bounds) + 1)
    for s in db.conn.execute("SELECT power_w FROM row_samples WHERE session_id = ?", (sid,)):
        if s["power_w"] is not None:
            pct = float(s["power_w"]) / ftp * 100.0
            zones[sum(1 for b in bounds if pct > b)] += 1.0
    secs = float(r["moving_s"] or r["elapsed_s"] or 0)
    if_ = float(r["np_w"]) / ftp if r["np_w"] else None
    tss = (secs * (r["np_w"] or 0) * (if_ or 0)) / (ftp * 3600) * 100 if if_ else r["load"]
    return Impact(seconds=secs, tss=tss, if_=if_, zones=_zones7(zones), source="actual")


KINDS = {"cycling": "ride", "rowing": "row"}


def actual(db, sport: str, sid: str) -> Impact | None:
    """O impacto do que a sessão fez (das amostras de potência). Só ciclismo e remo."""
    from . import longevity as lg
    sid = str(sid)
    imp = _ride_actual(db, sid) if sport == "cycling" else \
        _row_actual(db, sid) if sport == "rowing" else None
    if imp is None:
        return None
    imp.systems = effects(imp.zones)
    try:
        imp.longevity = lg.session_impact(db, sport, sid)
    except Exception:
        imp.longevity = {}
    return imp


def session_blocks(db, sport: str, sid: str):
    """Os blocos do treino que a sessão fez (a cópia guardada ao começar), ou None."""
    from . import session_workouts as sw
    from .blocks import load_blocks
    kind = KINDS.get(sport)
    if kind is None:
        return None
    try:
        link = sw.of_session(db, kind, str(sid))
    except Exception:
        link = None
    wid = (link or {}).get("copy_id")
    if not wid and sport == "cycling":
        r = db.conn.execute("SELECT workout_id FROM rides WHERE id = ?", (str(sid),)).fetchone()
        wid = r["workout_id"] if r is not None else None
    if not wid and sport == "rowing":
        r = db.conn.execute("SELECT workout_id FROM row_sessions WHERE id = ?",
                            (str(sid),)).fetchone()
        wid = r["workout_id"] if r is not None else None
    if not wid:
        return None
    try:
        _n, _d, _m, blocks = load_blocks(db, sport, wid)
    except Exception:
        return None
    return blocks if any(b.lo is not None for b in blocks) else None


def _session_day(db, sport: str, sid: str) -> date | None:
    from . import stats
    table = {"cycling": "rides", "rowing": "row_sessions"}.get(sport)
    if table is None:
        return None
    r = db.conn.execute(f"SELECT started_at FROM {table} WHERE id = ?", (str(sid),)).fetchone()
    return stats._local_date(r["started_at"]) if r is not None else None


def _planned_longevity_same_day(db, sport: str, sid: str, mins: dict) -> dict:
    """O impacto do treino planeado no índice, medido no mesmo dia e contra a mesma base que
    a sessão (sem ela): assim o planeado e o realizado comparam-se de igual para igual."""
    from . import longevity as lg
    day = _session_day(db, sport, sid) or date.today()
    doses = lg.all_doses(db)
    base = [d for d in doses if (d.sport, d.sid) != (sport, str(sid))]
    without = lg.compute(db, day, doses=base)
    with_ = lg.compute(db, day, doses=base + [lg.Dose(day, sport, "plan", dict(mins))])
    deltas = {p: with_[p]["index"] - without[p]["index"] for p in ("1w", "1m", "3m")}
    axes = {a: with_["1m"]["axes"][a] - without["1m"]["axes"].get(a, 0.0) for a in lg.AXES}
    top = sorted(((a, v) for a, v in axes.items() if v > 0.05), key=lambda kv: -kv[1])
    return {"deltas": deltas, "axes": axes, "top": top[:3], "mins": dict(mins)}


def for_session(db, sport: str, sid: str) -> dict | None:
    """{planned, actual, compare} de uma sessão feita com um treino por potência; None se a
    sessão não teve treino (ou não é de um desporto com potência)."""
    if sport not in POWER_SPORTS:
        return None
    blocks = session_blocks(db, sport, sid)
    if not blocks:
        return None
    act = actual(db, sport, sid)
    if act is None:
        return None
    from . import longevity as lg
    plan = planned(db, sport, blocks)
    try:
        plan.longevity = _planned_longevity_same_day(db, sport, sid, lg.blocks_mins(blocks, sport))
    except Exception:
        pass
    return {"planned": plan, "actual": act, "compare": compare(plan, act)}


# ------------------------------------------------------------------ comparar


def if_verdict(target: float | None, done: float | None) -> tuple[str, str]:
    """(chave, texto): «on» no alvo, «above» acima, «below» abaixo, «none» sem dados."""
    if target is None or done is None:
        return "none", tr("sem dados para comparar", "no data to compare")
    d = done - target
    if abs(d) <= IF_TOLERANCE:
        return "on", tr("no alvo", "on target")
    if d > 0:
        return "above", tr("acima do alvo (+{d:.2f})", "above target (+{d:.2f})", d=d)
    return "below", tr("abaixo do alvo ({d:.2f})", "below target ({d:.2f})", d=d)


def compare(plan: Impact, act: Impact) -> dict:
    key, text = if_verdict(plan.if_, act.if_)
    pct = (act.if_ / plan.if_ * 100.0) if plan.if_ and act.if_ else None
    systems = {s: (plan.systems.get(s, 0.0), act.systems.get(s, 0.0)) for s in SYSTEMS}
    pd, ad = plan.longevity.get("deltas") or {}, act.longevity.get("deltas") or {}
    lon = {p: (pd.get(p), ad.get(p)) for p in ("1w", "1m", "3m")}
    return {"if": (plan.if_, act.if_), "if_key": key, "if_text": text, "if_pct": pct,
            "tss": (plan.tss, act.tss), "systems": systems, "longevity": lon}


# ------------------------------------------------------------------ o perfil


def profile_links(db, sport: str, systems: dict) -> dict:
    """{sistema: {"name", "score", "level", "weakest"}} — a característica do teu perfil de
    ciclismo que cada sistema puxa, com o teu nível de agora. Fora do ciclismo, vazio."""
    if sport != "cycling":
        return {}
    try:
        from . import profile as pf
        p = pf.cycling(db)
    except Exception:
        return {}
    rows = {r["key"]: r for r in p["rows"]}
    weak = (p.get("weakest") or {}).get("key")
    out = {}
    for s, k in PROFILE_KEY.items():
        r = rows.get(k)
        if r is None:
            continue
        out[s] = {"name": r["name"], "score": r["score"], "level": r["level"],
                  "weakest": k == weak and systems.get(s, 0.0) >= 2.0}
    return out


def summary_text(imp: Impact) -> str:
    """Uma linha: «IF 0,82 · TSS 64 · foco VO2máx (3,4 melhora)»."""
    bits = [f"IF {fmt_if(imp.if_)}"]
    if imp.tss is not None:
        bits.append(f"TSS {imp.tss:.0f}")
    f = imp.focus
    if f:
        v = imp.systems[f]
        bits.append(tr("foco {s} ({v:.1f} {l})", "focus {s} ({v:.1f} {l})", s=system_name(f),
                       v=v, l=effect_level(v)))
    return " · ".join(bits)
