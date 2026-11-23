"""Guia da passadeira manual: a Perennia diz o que carregar.

Uma passadeira sem ligação (como a NordicTrack T 7.0 de 2010, que só tem os botões ▲/▼ de
velocidade e de inclinação) não recebe os blocos do treino — mudas tu. Num treino de corrida por
blocos, o guia:

* diz, **antes** de cada mudança (por omissão 10 s antes), a velocidade e a inclinação que vêm aí e
  **quantos toques** dar em cada botão — «▲ velocidade ×25 · ▲ inclinação ×2» —, contando com o
  passo da tua passadeira (Definições → Desportos → Corrida → Sessões Não ERG: «Passo da
  velocidade» e «Passo da inclinação»);
* dá um bip ao começar o aviso; no momento da mudança mostra «AGORA» durante uns segundos;
* no princípio do treino diz a velocidade e a inclinação do primeiro bloco.

Sem pyglet: o ecrã só desenha o que `Guide.state()` devolve. A velocidade de um bloco vem do
construtor (treinos manuais de passadeira) ou, num treino por ritmo, do ritmo do bloco (a meio do
intervalo) arredondado ao passo da passadeira; a inclinação vem do bloco (sem inclinação, fica a
que estava).
"""
from __future__ import annotations

from dataclasses import dataclass

from .i18n import tr

SPEED_STEPS = (0.1, 0.2, 0.5, 1.0)        # km/h por toque
DEFAULT_SPEED_STEP = 0.1
DEFAULT_LEAD_S = 10
LEAD_RANGE = (3, 30)
HOLD_S = 8.0                               # quanto tempo fica o «AGORA» depois da mudança
HOLD_PRESSES = 10                          # a partir daqui, lembra que se pode manter carregado


def _round_to(v: float, step: float) -> float:
    return round(round(v / step) * step, 2)


def presses(cur: float | None, target: float | None, step: float) -> int:
    """Quantos toques (com sinal: + é ▲, − é ▼) para ir de `cur` a `target`."""
    if cur is None or target is None or step <= 0:
        return 0
    return int(round((float(target) - float(cur)) / step))


def fmt_num(v: float, nd: int = 1) -> str:
    """«12,5» em português, «12.5» em inglês."""
    s = f"{v:.{nd}f}"
    return s.replace(".", ",") if tr("pt", "en") == "pt" else s


def press_text(n: int, what: str) -> str:
    if n == 0:
        return ""
    arrow = "▲" if n > 0 else "▼"
    return f"{arrow} {what} ×{abs(n)}"


@dataclass
class Target:
    speed: float | None
    incline: float | None


def settings(db) -> dict:
    """O passo da velocidade e da inclinação e o aviso antes (com os limites)."""
    from .workout_meta import device_limits
    lim = device_limits(db)
    sp = float(db.get("treadmill_speed_step", DEFAULT_SPEED_STEP) or DEFAULT_SPEED_STEP)
    lead = int(db.get("treadmill_guide_lead_s", DEFAULT_LEAD_S) or DEFAULT_LEAD_S)
    return {"speed_step": sp if sp in SPEED_STEPS else DEFAULT_SPEED_STEP,
            "incline_step": float(lim["treadmill_incline_step"]),
            "lead_s": max(LEAD_RANGE[0], min(LEAD_RANGE[1], lead)),
            "max_kmh": float(lim["treadmill_max_kmh"]),
            "max_incline": float(lim["treadmill_max_incline"])}


def targets(engine, cfg: dict) -> list[Target]:
    """A velocidade e a inclinação de cada bloco do treino (as do bloco anterior quando o bloco
    não diz), já arredondadas aos passos da passadeira e aos seus limites."""
    wk = getattr(engine, "workout", None)
    if wk is None:
        return []
    out: list[Target] = []
    speed, inc = None, 0.0
    for i, s in enumerate(wk.steps):
        v = engine.block_speeds[i] if i < len(engine.block_speeds) else None
        if not v and engine.mode == "pace" and s.lo is not None:
            try:
                pace = engine.ctx.pace(s.mid)           # s/km
                v = 3600.0 / pace if pace else None
            except Exception:
                v = None
        if v:
            speed = max(cfg["speed_step"], min(cfg["max_kmh"], _round_to(v, cfg["speed_step"])))
        b = engine.block_inclines[i] if i < len(engine.block_inclines) else None
        if b is not None:
            inc = max(0.0, min(cfg["max_incline"], _round_to(float(b), cfg["incline_step"])))
        out.append(Target(speed, inc))
    return out


class Guide:
    """O que dizer agora: o bloco em curso, o que vem a seguir e os toques."""

    def __init__(self, tgts: list[Target], speed_step: float, incline_step: float,
                 lead_s: float = DEFAULT_LEAD_S, hold_s: float = HOLD_S):
        self.targets = tgts
        self.speed_step, self.incline_step = speed_step, incline_step
        self.lead_s, self.hold_s = float(lead_s), float(hold_s)
        self._warned: set[int] = set()

    @classmethod
    def for_engine(cls, engine, db) -> "Guide | None":
        """Só para corrida com um treino por blocos e sem passadeira que a Perennia comande."""
        if getattr(engine, "sport", "") != "running" or getattr(engine, "workout", None) is None:
            return None
        if getattr(engine, "treadmill", None) is not None:
            return None                     # uma passadeira ligada já muda sozinha
        cfg = settings(db)
        tg = targets(engine, cfg)
        if not any(t.speed for t in tg):
            return None                     # sem velocidades (treino só por FC, por exemplo)
        return cls(tg, cfg["speed_step"], cfg["incline_step"], cfg["lead_s"])

    def change(self, a: Target | None, b: Target) -> dict:
        """A mudança de `a` para `b`: os toques em cada botão e o texto."""
        sp = presses(a.speed if a else None, b.speed, self.speed_step)
        ic = presses(a.incline if a else None, b.incline, self.incline_step)
        bits = [press_text(sp, tr("velocidade", "speed")),
                press_text(ic, tr("inclinação", "incline"))]
        text = " · ".join(x for x in bits if x)
        hint = tr("são muitos toques: podes manter o botão carregado",
                  "that's a lot of presses: you can hold the button") \
            if max(abs(sp), abs(ic)) >= HOLD_PRESSES else ""
        return {"speed_presses": sp, "incline_presses": ic,
                "presses_text": text, "hint": hint,
                "target_text": self.target_text(b)}

    def target_text(self, t: Target) -> str:
        parts = []
        if t.speed:
            parts.append(f"{fmt_num(t.speed)} km/h")
        if t.incline is not None:
            parts.append(f"{fmt_num(t.incline)} %")
        return " · ".join(parts)

    def state(self, idx: int, step_left_s: float | None, step_elapsed_s: float,
              started: bool = True) -> dict:
        """`kind`: «start» (antes do 1.º bloco ou nos primeiros segundos), «soon» (a mudança vem
        aí), «now» (acabou de mudar), «steady» (nada a fazer) ou «done»."""
        if idx >= len(self.targets) or idx < 0:
            return {"kind": "done", "title": tr("TREINO CONCLUÍDO", "WORKOUT DONE"),
                    "line": "", "beep": False}
        cur = self.targets[idx]
        prev = self.targets[idx - 1] if idx > 0 else None
        nxt = self.targets[idx + 1] if idx + 1 < len(self.targets) else None
        out = {"current": cur, "next": nxt, "beep": False}
        if not started or (idx == 0 and step_elapsed_s < self.hold_s):
            out.update(kind="start", title=tr("PÕE A PASSADEIRA EM", "SET THE TREADMILL TO"),
                       line=self.target_text(cur), presses_text="")
            return out
        if nxt is not None and step_left_s is not None and step_left_s <= self.lead_s:
            ch = self.change(cur, nxt)
            if ch["speed_presses"] or ch["incline_presses"]:
                out.update(kind="soon", seconds=max(0, int(round(step_left_s))),
                           title=tr("DAQUI A {s} s", "IN {s} s", s=max(0, int(round(
                               step_left_s)))),
                           line=ch["target_text"], presses_text=ch["presses_text"], **{
                               k: ch[k] for k in ("speed_presses", "incline_presses", "hint")})
                if idx not in self._warned:
                    self._warned.add(idx)
                    out["beep"] = True
                return out
        if prev is not None and step_elapsed_s < self.hold_s:
            ch = self.change(prev, cur)
            if ch["speed_presses"] or ch["incline_presses"]:
                out.update(kind="now", title=tr("AGORA", "NOW"), line=ch["target_text"],
                           presses_text=ch["presses_text"],
                           **{k: ch[k] for k in ("speed_presses", "incline_presses", "hint")})
                return out
        line = self.target_text(cur)
        if nxt is not None:
            ch = self.change(cur, nxt)
            line += "  →  " + tr("a seguir ", "next ") + ch["target_text"]
        out.update(kind="steady", title=tr("PASSADEIRA", "TREADMILL"), line=line,
                   presses_text="")
        return out


def step_left_seconds(engine) -> float | None:
    """Quanto falta no bloco, em segundos (num bloco por distância, à velocidade de agora)."""
    wk = getattr(engine, "workout", None)
    if wk is None or wk.step is None:
        return None
    s = wk.step
    if s.dur_type == "time":
        return max(0.0, s.dur_value - wk.step_t)
    v = (engine.speed_kmh or 0.0) / 3.6
    return max(0.0, s.dur_value - wk.step_m) / v if v > 0 else None
