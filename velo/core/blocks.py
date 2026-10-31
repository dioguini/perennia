"""Blocos de um treino de resistência (ciclismo, remo, corrida, natação),
num formato único: ler e gravar no formato de cada desporto, e estimar a
duração e a carga. Usado pelo construtor e pelos resumos/feedback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import endurance as en
from . import intensity as it
from . import rowing as rw
from .i18n import tr


@dataclass
class Block:
    kind: str = "active"            # warmup | active | rest | cooldown
    dur_type: str = "time"          # time | distance
    dur: float = 300.0              # s ou m
    lo: float | None = 75.0         # % do limiar; None = livre
    hi: float | None = None         # rampa se diferente de lo
    cue: str = ""
    extra: dict = field(default_factory=dict)
    goal: str = ""                  # objetivo do bloco (velo.core.objectives)

    @property
    def ramp(self) -> bool:
        return self.lo is not None and self.hi is not None and abs(self.hi - self.lo) > 0.5

    @property
    def end_pct(self) -> float | None:
        return self.hi if self.hi is not None else self.lo

    def mid(self) -> float:
        if self.lo is None:
            return 50.0
        return (self.lo + (self.end_pct or self.lo)) / 2


# ============================================================ conversões


def load_blocks(db, sport: str, wid: str | None) -> tuple[str, str, str, list[Block]]:
    """(nome, descrição, vista, blocos)."""
    if sport == "cycling":
        if not wid:
            return tr("Novo treino", "New workout"), "", "power", _starter(sport)
        row = db.workout(wid)
        ftp = db.athlete().ftp_w
        blocks = []
        for r in db.workout_steps(wid):
            lo, hi = r["target_lo"], r["target_hi"]
            if r["target_type"] == "watts":
                lo = None if lo is None else lo / max(1, ftp) * 100
                hi = None if hi is None else hi / max(1, ftp) * 100
            if r["kind"] == "freeride" or r["target_type"] == "none":
                lo = hi = None
            blocks.append(Block("active", "time", float(r["duration_s"] or 0), lo,
                                hi if r["kind"] == "ramp" else None, r["text_cue"] or "",
                                {"cadence_lo": r["cadence_lo"], "cadence_hi": r["cadence_hi"]}))
        _guess_kinds(blocks)
        return (row["name"] if row else ""), (row["description"] or "") if row else "", \
            db.get("builder_mode_cycling", "power"), blocks
    if sport == "rowing":
        if not wid:
            return tr("Novo treino", "New workout"), "", "power", _starter(sport)
        w = rw.workout(db, wid)
        ftp = rw.row_ftp(db)
        blocks = []
        for s in w["steps"]:
            lo = hi = None
            if s.target == "power" and s.lo:
                lo, hi = s.lo, s.hi
            elif s.target == "pace" and s.lo:
                rng = s.watts_range(ftp)
                lo, hi = rng[0] / ftp * 100, rng[1] / ftp * 100
            blocks.append(Block(s.kind, s.dur_type, s.dur_value, lo,
                                hi if hi is not None and abs((hi or 0) - (lo or 0)) > 0.5
                                else None, s.cue,
                                {"resistance": s.resistance,
                                 "spm": (s.lo, s.hi) if s.target == "spm" else None}))
        return w["name"], w["description"] or "", db.get("builder_mode_rowing", "power"), blocks
    # corrida / natação
    if not wid:
        return tr("Novo treino", "New workout"), "", "pace", _starter(sport)
    w = en.workout(db, wid)
    blocks = [Block(s.kind, s.dur_type, s.dur_value, s.lo,
                    s.hi if s.hi is not None and s.lo is not None and abs(s.hi - s.lo) > 0.5
                    else None, s.cue) for s in w["steps"]]
    return w["name"], w["description"] or "", w["mode"], blocks


def _guess_kinds(blocks: list[Block]) -> None:
    if not blocks:
        return
    for b in blocks:
        b.kind = "rest" if b.lo is not None and b.mid() < 56 else "active"
    if blocks[0].lo is None or blocks[0].mid() < 70:
        blocks[0].kind = "warmup"
    if len(blocks) > 1 and (blocks[-1].lo is None or blocks[-1].mid() < 70):
        blocks[-1].kind = "cooldown"


def _starter(sport: str) -> list[Block]:
    dist = sport in ("swimming",)
    if dist:
        return [Block("warmup", "distance", 300, 70), Block("active", "distance", 400, 90),
                Block("cooldown", "distance", 200, 65)]
    return [Block("warmup", "time", 600, 55, 75), Block("active", "time", 1200, 80),
            Block("cooldown", "time", 300, 60, 50)]


def save_blocks(db, sport: str, wid: str | None, name: str, desc: str, mode: str,
                blocks: list[Block]) -> str:
    if sport == "cycling":
        steps = []
        for b in blocks:
            if b.lo is None:
                steps.append({"kind": "freeride", "duration_s": int(b.dur),
                              "target_type": "none", "text_cue": b.cue or None})
            else:
                steps.append({"kind": "ramp" if b.ramp else "steady", "duration_s": int(b.dur),
                              "target_type": "pct_ftp", "target_lo": round(b.lo, 1),
                              "target_hi": round(b.end_pct, 1) if b.ramp else None,
                              "cadence_lo": b.extra.get("cadence_lo"),
                              "cadence_hi": b.extra.get("cadence_hi"),
                              "text_cue": b.cue or None})
        tss = estimate(blocks, it.Context.from_db(db, sport))["tss"]
        db.set("builder_mode_cycling", mode)
        if wid:
            db.update_workout(wid, name, steps, desc, tss)
            return wid
        return db.insert_workout(name, steps, "builder", desc, tss)
    if sport == "rowing":
        steps = []
        for b in blocks:
            spm = b.extra.get("spm")
            if b.lo is None and spm:
                target, lo, hi = "spm", spm[0], spm[1]
            elif b.lo is None:
                target, lo, hi = "none", None, None
            else:
                target, lo, hi = "power", round(b.lo), round(b.end_pct)
            steps.append(rw.Step(b.kind, b.dur_type, b.dur, target, lo, hi,
                                 b.extra.get("resistance"), b.cue))
        db.set("builder_mode_rowing", mode)
        return rw.save_workout(db, wid, name, desc, steps)
    steps = [en.Step(b.kind, b.dur_type, b.dur, None if b.lo is None else round(b.lo, 1),
                     None if b.lo is None else round(b.end_pct, 1), b.cue) for b in blocks]
    return en.save_workout(db, wid, sport, name, desc, steps, mode=mode)


def block_seconds(b: Block, ctx: it.Context) -> float:
    if b.dur_type == "time":
        return b.dur
    return b.dur / max(0.3, ctx.speed_mps(b.mid()))


def estimate(blocks: list[Block], ctx: it.Context) -> dict:
    """Duração, distância (dos blocos por distância), TSS/carga e tempo por zona."""
    secs = dist = load = 0.0
    zones = [0.0] * 7
    for b in blocks:
        s = block_seconds(b, ctx)
        secs += s
        if b.dur_type == "distance":
            dist += b.dur
        pct = b.mid() if b.lo is not None else 50.0
        load += s / 3600 * (pct / 100) ** 2 * 100
        zones[it.zone(pct) - 1] += s
    if_ = (load / (secs / 3600) / 100) ** 0.5 if secs else 0.0
    return {"seconds": secs, "meters": dist, "tss": load, "if": if_, "zones": zones}
