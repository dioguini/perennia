"""Modo Challenge: desafio adaptativo e mini-jogos para um só atleta.

Cada jogo recebe a potência do atleta a 1 Hz (`tick`) e devolve eventos
para o HUD. Tudo é relativo à FTP e à curva de potência do atleta, por isso
um atleta de 150 W e um de 350 W têm o mesmo desafio. Os adversários são
bots com perfis gerados à volta das capacidades do atleta.

Regra comum: nenhum alvo muda em menos de 10 segundos — dá tempo ao rolo
(um Wahoo em ERG, por exemplo) de fazer a transição sem solavancos.

Jogos:
- adaptive:    desafio adaptativo — blocos de esforço e descanso escolhidos
               para as tuas capacidades; o nível sobe quando cumpres e desce
               quando falhas, e fica guardado para a próxima vez.
- zone_hero:   «Guitar Hero» de watts — manter a zona que vai passando,
               encadear combos e acertar nos anéis de sprint.
- ladder:      escada de potência — o alvo sobe a cada degrau; ganha quem
               aguentar mais tempo acima dele.
- warmup:      aquecimento progressivo; ganha quem for mais preciso.
- elimination: corrida de eliminação em pista, com aspiração (drafting);
               o último de cada volta sai.
- tug:         cabo de guerra contra um bot que puxa por ondas.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from . import physics
from .boards import Board, Row
from .i18n import t
from .units import hms

MIN_BLOCK_S = 10            # nenhum alvo dura menos (transições do rolo)
GAMES = ("adaptive", "zone_hero", "ladder", "warmup", "elimination", "tug")

# Capacidade típica por duração, em múltiplos da FTP, quando o histórico não
# tem esse esforço (valores próximos de um perfil equilibrado).
DEFAULT_CAPACITY = {10: 2.0, 15: 1.8, 20: 1.65, 30: 1.5, 45: 1.38, 60: 1.3, 90: 1.22,
                    120: 1.17, 180: 1.11, 240: 1.08, 300: 1.06, 600: 1.0, 1200: 0.95}


def capacity_curve(ftp: int, best: dict[int, float] | None) -> dict[int, float]:
    """Watts que o atleta consegue por duração: o melhor do histórico recente,
    sem descer abaixo de 85 % do perfil típico (um histórico curto não deve
    tornar o desafio trivial)."""
    best = best or {}
    out = {}
    for d, mult in DEFAULT_CAPACITY.items():
        typical = ftp * mult
        measured = best.get(d)
        out[d] = max(measured, typical * 0.85) if measured else typical
    return out


def capacity_at(curve: dict[int, float], seconds: float) -> float:
    """Interpolação em escala logarítmica da duração."""
    keys = sorted(curve)
    if seconds <= keys[0]:
        return curve[keys[0]]
    if seconds >= keys[-1]:
        return curve[keys[-1]]
    for a, b in zip(keys, keys[1:]):
        if a <= seconds <= b:
            f = (math.log(seconds) - math.log(a)) / (math.log(b) - math.log(a))
            return curve[a] + (curve[b] - curve[a]) * f
    return curve[keys[-1]]


@dataclass
class Block:
    kind: str                 # warmup | effort | rest | cooldown | ring | zone
    seconds: int
    watts: int | None
    pct: float | None = None
    zone: int | None = None
    lo: int | None = None     # banda (zone hero)
    hi: int | None = None


@dataclass
class Bot:
    name: str
    ftp: float
    skill: float = 0.8        # precisão / vontade (0–1)
    wbal: float = 20000.0     # reserva acima da FTP, em J
    wmax: float = 20000.0
    score: float = 0.0
    dist: float = 0.0
    speed: float = 0.0
    out_at: float | None = None
    power: float = 0.0


BOT_NAMES = ("Ana", "Bruno", "Carla", "Diogo", "Eva", "Filipe", "Gil", "Helena", "Inês",
             "João", "Marta", "Nuno", "Rita", "Tiago")


class Game:
    """Base. As subclasses definem `_tick` e o texto."""

    key = ""
    erg_default = False
    has_duration = True
    has_bots = True
    durations = (10, 20, 30)
    default_minutes = 20
    higher_is_better = True       # pontuação; na eliminação conta a posição

    def __init__(self, ftp: int, weight_kg: float = 75.0, *, best: dict | None = None,
                 minutes: int | None = None, bots: int = 4, erg: bool | None = None,
                 seed: int = 1, level: float = 0.9, power_zones: list | None = None):
        self.ftp = max(50, int(ftp))
        self.weight = weight_kg or 75.0
        self.minutes = minutes or self.default_minutes
        self.n_bots = max(0, int(bots)) if self.has_bots else 0
        self.erg = self.erg_default if erg is None else bool(erg)
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.curve = capacity_curve(self.ftp, best)
        self.level = float(level)
        self.zones_pct = list(power_zones or [55, 75, 90, 105, 120, 150])
        self.t = 0.0
        self.score = 0.0
        self.finished = False
        self.saved = False
        self.target_w: int | None = None
        self.headline = ""
        self.detail = ""
        self.progress = 0.0
        self.mood = "neutral"           # good | warn | bad | neutral
        self.won: bool | None = None
        self.rank: int | None = None
        self.bots: list[Bot] = []
        if self.n_bots:
            names = list(BOT_NAMES)
            self.rng.shuffle(names)
            for i in range(self.n_bots):
                self.bots.append(Bot(names[i], self.ftp * self.rng.uniform(0.9, 1.08),
                                     skill=self.rng.uniform(0.6, 0.93),
                                     wbal=0.0, wmax=0.0))
                b = self.bots[-1]
                b.wmax = b.wbal = b.ftp * self.rng.uniform(60, 95)     # ~15–25 kJ
        self.setup()

    # para as subclasses
    def setup(self) -> None: ...
    def _tick(self, power: float) -> list[tuple[str, dict]]: return []

    @property
    def title(self) -> str:
        return t(f"game.{self.key}")

    @property
    def total_s(self) -> int:
        return int(self.minutes * 60)

    def tick(self, dt: float, power_w: int | None) -> list[tuple[str, dict]]:
        """Um segundo de jogo (o motor chama a 1 Hz)."""
        if self.finished:
            return []
        self.t += dt
        events = self._tick(float(power_w or 0))
        if not self.finished and self.has_duration and self.t >= self.total_s:
            events += self.end()
        return events

    def end(self) -> list[tuple[str, dict]]:
        if self.finished:
            return []
        self.finished = True
        self.target_w = None
        self._final_rank()
        return [("game_over", self.result())]

    def _final_rank(self) -> None:
        if not self.bots:
            return
        better = sum(1 for b in self.bots if b.score > self.score)
        self.rank = better + 1
        self.won = self.rank == 1

    def standings(self) -> list[tuple[str, float, bool]]:
        rows = [(t("board.me"), self.score, True)] + [(b.name, b.score, False)
                                                       for b in self.bots]
        rows.sort(key=lambda r: -r[1])
        return rows

    def result(self) -> dict:
        return {"game": self.key, "score": round(self.score), "rank": self.rank,
                "total": len(self.bots) + 1 if self.bots else None, "won": self.won,
                "seconds": int(self.t), "summary": self.summary_text()}

    def summary_text(self) -> str:
        return t("game.points", n=f"{self.score:.0f}")

    def board(self, history: list | None = None) -> Board:
        """Classificação ao vivo: o atleta e os bots."""
        rows = []
        for i, (name, value, me) in enumerate(self.standings()[:6]):
            rows.append(Row(i + 1, self.format_score(value), name, me=me))
        sub = (t("game.best", score=self.format_score(history[0])) if history
               else t("game.live"))
        return Board(self.title, rows, subtitle=sub)

    def format_score(self, v: float) -> str:
        return f"{v:.0f}"

    # ------------------------------------------------------- recuperação

    def snapshot(self) -> dict:
        out = {}
        for k, v in vars(self).items():
            if k in ("rng", "curve"):
                continue
            if isinstance(v, list) and v and isinstance(v[0], (Bot, Block)):
                out[k] = {"__cls": type(v[0]).__name__, "items": [asdict(x) for x in v]}
            else:
                try:
                    json.dumps(v)
                    out[k] = v
                except (TypeError, ValueError):
                    pass
        return out

    def restore(self, snap: dict) -> None:
        classes = {"Bot": Bot, "Block": Block}
        for k, v in snap.items():
            if isinstance(v, dict) and "__cls" in v:
                cls = classes[v["__cls"]]
                setattr(self, k, [cls(**x) for x in v["items"]])
            elif k == "curve":
                continue
            else:
                setattr(self, k, v)
        self.rng = random.Random(self.seed + int(self.t))

    # ----------------------------------------------------------- bots

    def _bot_effort(self, b: Bot, rel: float, dt: float = 1.0) -> float:
        """Potência de um bot que tenta `rel` × FTP, limitada pela reserva W′."""
        want = b.ftp * rel * self.rng.uniform(0.96, 1.04)
        if want > b.ftp:
            spend = (want - b.ftp) * dt
            if spend > b.wbal:
                want = b.ftp + b.wbal / dt * 0.5
                spend = b.wbal * 0.5
            b.wbal -= spend
        else:
            b.wbal = min(b.wmax, b.wbal + (b.ftp - want) * 0.6 * dt)
        b.power = max(0.0, want)
        return b.power


# =========================================================== desafio adaptativo


class AdaptiveChallenge(Game):
    key = "adaptive"
    erg_default = True
    has_bots = False
    durations = (20, 30, 45, 60)
    default_minutes = 30
    WARMUP = ((60, 0.50), (60, 0.60), (60, 0.70), (60, 0.75))
    COOLDOWN_S = 180
    EFFORTS = (10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300)

    def setup(self) -> None:
        self.blocks: list[Block] = [Block("warmup", s, int(self.ftp * p), p * 100)
                                    for s, p in self.WARMUP]
        self.idx = 0
        self.block_t = 0.0
        self.block_sum = 0.0
        self.done = 0
        self.passed = 0
        self.streak = 0
        self.fails_in_row = 0
        self.level_start = self.level
        self._extend()
        self._enter_block()

    def _plan_effort(self) -> tuple[int, float]:
        # mais esforços curtos do que longos; nada de longo perto do fim
        left = self.total_s - self.COOLDOWN_S - self._planned_seconds()
        options = [d for d in self.EFFORTS if d * 2 + MIN_BLOCK_S <= left] or [10]
        weights = [3.0 if d <= 30 else 2.0 if d <= 120 else 1.0 for d in options]
        d = self.rng.choices(options, weights)[0]
        watts = capacity_at(self.curve, d) * self.level
        return d, watts

    def _planned_seconds(self) -> int:
        return sum(b.seconds for b in self.blocks)

    def _extend(self) -> None:
        """Gera os blocos seguintes até cobrir a sessão (sem passar)."""
        while self._planned_seconds() < self.total_s - self.COOLDOWN_S - 2 * MIN_BLOCK_S:
            d, watts = self._plan_effort()
            self.blocks.append(Block("effort", d, int(round(watts)),
                                     round(watts / self.ftp * 100)))
            ratio = 2.0 if d <= 20 else 1.2 if d <= 60 else 0.8 if d <= 180 else 0.6
            if self.fails_in_row >= 2:
                ratio *= 1.5
            rest = int(max(MIN_BLOCK_S, min(240, round(d * ratio / 5) * 5)))
            left = self.total_s - self.COOLDOWN_S - self._planned_seconds()
            rest = max(MIN_BLOCK_S, min(rest, left))
            self.blocks.append(Block("rest", rest, int(self.ftp * 0.5), 50))
            if self._planned_seconds() >= self.total_s - self.COOLDOWN_S:
                break
        if not self.blocks or self.blocks[-1].kind != "cooldown":
            remaining = max(MIN_BLOCK_S, self.total_s - self._planned_seconds())
            self.blocks.append(Block("cooldown", remaining, int(self.ftp * 0.45), 45))

    def _replan_after(self) -> None:
        """O nível mudou: refaz os alvos dos esforços que ainda não começaram."""
        for b in self.blocks[self.idx + 1:]:
            if b.kind == "effort":
                b.watts = int(round(capacity_at(self.curve, b.seconds) * self.level))
                b.pct = round(b.watts / self.ftp * 100)

    @property
    def block(self) -> Block:
        return self.blocks[min(self.idx, len(self.blocks) - 1)]

    def next_block(self) -> Block | None:
        return self.blocks[self.idx + 1] if self.idx + 1 < len(self.blocks) else None

    def _enter_block(self) -> list[tuple[str, dict]]:
        b = self.block
        self.block_t = 0.0
        self.block_sum = 0.0
        self.target_w = b.watts
        return [("game_cue", {"text": self.cue(b)})]

    def cue(self, b: Block) -> str:
        if b.kind == "effort":
            return t("game.adaptive.hold", s=b.seconds, pct=f"{b.pct:.0f}", w=b.watts)
        if b.kind == "rest":
            return t("game.adaptive.rest", s=b.seconds)
        if b.kind == "warmup":
            return t("game.adaptive.warmup", w=b.watts)
        return t("game.adaptive.cooldown")

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        ev: list[tuple[str, dict]] = []
        b = self.block
        self.block_t += 1.0
        self.block_sum += power
        avg = self.block_sum / max(1.0, self.block_t)
        left = max(0, int(b.seconds - self.block_t))
        self.progress = min(1.0, self.block_t / max(1, b.seconds))
        nb = self.next_block()
        nxt = f" · {t('game.next')}: {self.cue(nb)}" if nb is not None else ""
        if b.kind == "effort":
            self.headline = t("game.adaptive.hold_now", w=b.watts, s=left)
            ok = avg >= b.watts * 0.95
            self.mood = "good" if ok else ("warn" if avg >= b.watts * 0.85 else "bad")
            self.detail = (f"{t('game.avg')} {avg:.0f} W · {b.pct:.0f}% FTP · "
                           f"{t('game.level')} {self.level:.2f} · {self.score:.0f} pts")
        else:
            self.headline = f"{self.cue(b)} · {left} s"
            self.mood = "neutral"
            self.detail = (f"{t('game.passed', n=self.passed, total=self.done)} · "
                           f"{self.score:.0f} pts{nxt}")
        if self.block_t >= b.seconds:
            if b.kind == "effort":
                ev += self._judge(b, avg)
            self.idx += 1
            if self.idx >= len(self.blocks):
                return ev + self.end()
            ev += self._enter_block()
        return ev

    def _judge(self, b: Block, avg: float) -> list[tuple[str, dict]]:
        self.done += 1
        ok = avg >= b.watts * 0.95
        if ok:
            self.passed += 1
            self.streak += 1
            self.fails_in_row = 0
            gained = b.seconds * (b.pct or 100) / 100.0 * (1 + 0.1 * min(self.streak, 10))
            self.score += gained
            self.level = min(1.10, self.level + 0.015)
        else:
            self.streak = 0
            self.fails_in_row += 1
            self.level = max(0.75, self.level - 0.03)
        self._replan_after()
        return [("game_judge", {"ok": ok, "avg": round(avg), "target": b.watts,
                                "text": (t("game.adaptive.ok", w=round(avg)) if ok
                                         else t("game.adaptive.fail", w=round(avg),
                                                target=b.watts))})]

    def summary_text(self) -> str:
        return t("game.adaptive.summary", passed=self.passed, total=self.done,
                 score=f"{self.score:.0f}", a=f"{self.level_start:.2f}",
                 b=f"{self.level:.2f}")

    def result(self) -> dict:
        r = super().result()
        r.update(passed=self.passed, efforts=self.done, level=round(self.level, 3),
                 level_start=round(self.level_start, 3))
        return r

    def board(self, history: list | None = None) -> Board:
        rows = []
        upcoming = self.blocks[self.idx:self.idx + 6]
        for i, b in enumerate(upcoming):
            rows.append(Row(None, f"{b.watts} W" if b.watts else "—",
                            f"{hms(b.seconds)} · {t('game.kind.' + b.kind)}", me=i == 0))
        sub = t("game.adaptive.board", passed=self.passed, total=self.done,
                level=f"{self.level:.2f}")
        return Board(self.title, rows, subtitle=sub)


# ================================================================== Zone Hero


class ZoneHero(Game):
    key = "zone_hero"
    durations = (10, 20, 30)
    default_minutes = 20
    RING_EVERY = 120

    def setup(self) -> None:
        z = self.zones_pct
        # bandas das zonas 2 a 5 (em watts), com 10 % de folga nas pontas
        self.bands = {2: (z[0], z[1]), 3: (z[1], z[2]), 4: (z[2], z[3]), 5: (z[3], z[4])}
        self.blocks: list[Block] = []
        tt = 0
        while tt < self.total_s:
            if tt and tt % self.RING_EVERY < 30 and self.blocks[-1].kind != "ring" \
                    and tt + 10 <= self.total_s:
                w = int(self.ftp * 1.5)
                self.blocks.append(Block("ring", 10, w, 150.0, lo=w, hi=None))
                tt += 10
                continue
            zone = self.rng.choice((2, 2, 3, 3, 4, 4, 5)) if tt >= 120 else 2
            secs = self.rng.choice((10, 15, 20, 30, 40)) if zone >= 4 else \
                self.rng.choice((20, 30, 40))
            secs = min(secs, self.total_s - tt)
            if secs < MIN_BLOCK_S:
                if self.blocks:
                    self.blocks[-1].seconds += secs
                break
            lo, hi = self.bands[zone]
            self.blocks.append(Block("zone", secs, int(self.ftp * (lo + hi) / 200), zone=zone,
                                     lo=int(self.ftp * lo / 100), hi=int(self.ftp * hi / 100)))
            tt += secs
        self.idx = 0
        self.block_t = 0.0
        self.ring_sum = 0.0
        self.combo = 0
        self.best_combo = 0
        self.rings = 0
        self.in_zone_s = 0
        self._start_block()

    def _start_block(self) -> None:
        b = self.blocks[min(self.idx, len(self.blocks) - 1)]
        self.block_t = 0.0
        self.ring_sum = 0.0
        self.target_w = b.watts

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        ev = []
        if self.idx >= len(self.blocks):
            return self.end()
        b = self.blocks[self.idx]
        self.block_t += 1
        if b.kind == "ring":
            self.ring_sum += power
            self.headline = t("game.zh.ring", w=b.watts, s=int(b.seconds - self.block_t))
            self.mood = "good" if power >= b.watts else "warn"
        else:
            inside = b.lo * 0.97 <= power <= b.hi * 1.03
            if inside:
                self.combo += 1
                self.in_zone_s += 1
                self.best_combo = max(self.best_combo, self.combo)
                self.score += 10 * min(4, 1 + self.combo // 10)
            else:
                if self.combo >= 10:
                    ev.append(("game_cue", {"text": t("game.zh.combo_lost", n=self.combo)}))
                self.combo = 0
            self.headline = t("game.zh.hold", z=b.zone, lo=b.lo, hi=b.hi,
                              s=int(b.seconds - self.block_t))
            self.mood = "good" if inside else ("warn" if power < b.lo else "bad")
        self.progress = min(1.0, self.block_t / b.seconds)
        upcoming = self.blocks[self.idx + 1:self.idx + 3]
        nxt = " → ".join(f"Z{x.zone}" if x.kind == "zone" else "◎" for x in upcoming)
        self.detail = (f"{self.score:.0f} pts · combo ×{min(4, 1 + self.combo // 10)} "
                       f"({self.combo}) · ◎ {self.rings}" + (f" · {nxt}" if nxt else ""))
        for bot in self.bots:                                   # os bots também jogam
            if b.kind == "ring":
                continue
            if self.rng.random() < bot.skill:
                bot.dist += 1                                   # «combo» do bot
                bot.score += 10 * min(4, 1 + int(bot.dist) // 10)
            else:
                bot.dist = 0
        if self.block_t >= b.seconds:
            if b.kind == "ring":
                hit = self.ring_sum / b.seconds >= b.watts
                if hit:
                    self.rings += 1
                    self.score += 200
                for bot in self.bots:
                    if self.rng.random() < bot.skill * 0.9:
                        bot.score += 200
                ev.append(("game_judge", {"ok": hit, "text": t("game.zh.ring_hit") if hit
                                          else t("game.zh.ring_miss")}))
            self.idx += 1
            if self.idx >= len(self.blocks):
                return ev + self.end()
            self._start_block()
            nb = self.blocks[self.idx]
            ev.append(("game_cue", {"text": t("game.zh.ring", w=nb.watts, s=nb.seconds)
                                    if nb.kind == "ring" else
                                    t("game.zh.zone", z=nb.zone, lo=nb.lo, hi=nb.hi)}))
        return ev

    def summary_text(self) -> str:
        return t("game.zh.summary", score=f"{self.score:.0f}", combo=self.best_combo,
                 rings=self.rings, pct=f"{self.in_zone_s / max(1, self.t) * 100:.0f}")


# =============================================================== Power Ladder


class PowerLadder(Game):
    key = "ladder"
    erg_default = True
    has_duration = False
    STEP_S = 30
    START = 0.5
    INC = 0.05

    def setup(self) -> None:
        self.step = 0
        self.step_t = 0.0
        self.window: list[float] = []
        self.out = False
        # cada bot cai num degrau perto do que o atleta deve aguentar (~1,3 × FTP)
        for b in self.bots:
            b.score = 0.0
            b.out_at = None
            b.skill = self.rng.uniform(1.15, 1.45) * (b.ftp / self.ftp)
        self.target_w = int(self.ftp * self.START)

    @property
    def target_pct(self) -> float:
        return self.START + self.INC * self.step

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        ev = []
        self.step_t += 1
        self.window = (self.window + [power])[-10:]
        self.score = self.t
        target = self.ftp * self.target_pct
        avg10 = sum(self.window) / len(self.window)
        for b in self.bots:
            if b.out_at is None:
                b.score = self.t
                if self.target_pct > b.skill and self.step_t >= 10:
                    b.out_at = self.t
                    ev.append(("game_cue", {"text": t("game.ladder.bot_out", name=b.name)}))
        self.headline = t("game.ladder.hold", w=int(target), s=int(self.STEP_S - self.step_t),
                          step=self.step + 1)
        self.mood = "good" if avg10 >= target * 0.95 else "bad"
        alive = sum(1 for b in self.bots if b.out_at is None)
        self.detail = t("game.ladder.detail", avg=f"{avg10:.0f}", alive=alive,
                        pct=f"{self.target_pct * 100:.0f}")
        self.progress = self.step_t / self.STEP_S
        if self.step_t >= MIN_BLOCK_S and len(self.window) >= 10 and avg10 < target * 0.95:
            ev.append(("game_judge", {"ok": False, "text": t("game.ladder.out",
                                                              w=int(target))}))
            return ev + self.end()
        if self.bots and alive == 0 and not getattr(self, "_told_last", False):
            self._told_last = True
            ev.append(("game_judge", {"ok": True, "text": t("game.ladder.last")}))
        if self.step_t >= self.STEP_S:
            self.step += 1
            self.step_t = 0.0
            self.target_w = int(self.ftp * self.target_pct)
            ev.append(("game_cue", {"text": t("game.ladder.up", w=self.target_w)}))
        return ev

    def format_score(self, v: float) -> str:
        return hms(v)

    def _final_rank(self) -> None:
        if not self.bots:
            return
        # à frente: os bots que ainda estavam na escada, ou que saíram depois
        better = sum(1 for b in self.bots if b.out_at is None or b.out_at > self.t)
        self.rank = better + 1
        self.won = self.rank == 1

    def summary_text(self) -> str:
        return t("game.ladder.summary", steps=self.step,
                 w=int(self.ftp * (self.START + self.INC * max(0, self.step - 1))),
                 time=hms(self.t))


# ================================================================ Aquecimento


class Warmup(Game):
    key = "warmup"
    has_duration = True
    durations = (10, 15)
    default_minutes = 10

    def setup(self) -> None:
        n = self.minutes * 60
        steps = []
        pcts = (45, 50, 55, 60, 65, 70, 75, 80)
        per = max(MIN_BLOCK_S, (n - 120) // len(pcts))
        for p in pcts:
            steps.append(Block("warmup", per, int(self.ftp * p / 100), p))
        for _ in range(2):
            steps.append(Block("effort", 15, int(self.ftp * 1.1), 110))
            steps.append(Block("rest", 45, int(self.ftp * 0.55), 55))
        self.blocks = steps
        self.idx = 0
        self.block_t = 0.0
        self.err_sum = 0.0
        self.n = 0
        self.target_w = steps[0].watts
        for b in self.bots:
            b.skill = self.rng.uniform(0.86, 0.96)

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        ev = []
        if self.idx >= len(self.blocks):
            return self.end()
        b = self.blocks[self.idx]
        self.block_t += 1
        err = min(1.0, abs(power - b.watts) / max(1, b.watts))
        self.err_sum += err
        self.n += 1
        self.score = max(0.0, 100.0 * (1 - self.err_sum / self.n))
        for bot in self.bots:
            bot.score = bot.skill * 100 + self.rng.uniform(-1.5, 1.5)
        self.headline = t("game.warmup.hold", w=b.watts, s=int(b.seconds - self.block_t))
        self.mood = "good" if err < 0.05 else ("warn" if err < 0.12 else "bad")
        self.detail = t("game.warmup.detail", acc=f"{self.score:.1f}")
        self.progress = self.block_t / b.seconds
        if self.block_t >= b.seconds:
            self.idx += 1
            self.block_t = 0.0
            if self.idx >= len(self.blocks):
                return ev + self.end()
            self.target_w = self.blocks[self.idx].watts
            ev.append(("game_cue", {"text": t("game.warmup.next", w=self.target_w)}))
        return ev

    def format_score(self, v: float) -> str:
        return f"{v:.1f}%"

    def summary_text(self) -> str:
        return t("game.warmup.summary", acc=f"{self.score:.1f}")


# ================================================================== Eliminação


class Elimination(Game):
    """Pista de 250 m. A cada `LAP_M` metros sai o último. Aspiração: atrás de
    outro ciclista a menos de 6 m, o arrasto cai 30 %."""

    key = "elimination"
    has_duration = False
    TRACK_M = 250.0
    LAP_M = 500.0             # eliminação a cada duas voltas
    DRAFT_M = 6.0

    def setup(self) -> None:
        self.dist = 0.0
        self.speed = 8.0
        self.next_cut = self.LAP_M
        self.out = False
        self.place: int | None = None
        for b in self.bots:
            b.dist = self.rng.uniform(-3, 3)
            b.speed = 8.0
            b.score = 0.0
            b.out_at = None
        self.mass = self.weight + 8.0
        self.target_w = None

    def _alive(self) -> list[Bot]:
        return [b for b in self.bots if b.out_at is None]

    def _cda(self, mine: float, others: list[float]) -> float:
        for o in others:
            gap = o - mine
            if 0.5 < gap < self.DRAFT_M:
                return 0.32 * 0.7
        return 0.32

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        ev = []
        alive = self._alive()
        to_line = self.next_cut - max([self.dist] + [b.dist for b in alive])
        for b in alive:
            # ritmo a 75–85 % da FTP; perto do corte, quem vai atrás ataca
            behind = sum(1 for o in alive + [None] if (o.dist if o else self.dist) > b.dist)
            rel = self.rng.uniform(0.88, 1.0)
            if to_line < 150 and behind >= len(alive) - 1:
                rel = self.rng.uniform(1.4, 1.8)            # quem vai atrás ataca
            self._bot_effort(b, rel)
        positions = [self.dist] + [b.dist for b in alive]
        for _ in range(4):                                    # física a 4 Hz
            cda = self._cda(self.dist, positions)
            self.speed = physics.step_velocity(self.mass, cda, 0.0025, self.speed, power,
                                               0.0, 0.25)
            self.dist += self.speed * 0.25
            for b in alive:
                bcda = self._cda(b.dist, positions)
                b.speed = physics.step_velocity(self.mass, bcda, 0.0025, b.speed, b.power,
                                                0.0, 0.25)
                b.dist += b.speed * 0.25
            positions = [self.dist] + [b.dist for b in alive]
        self.score = self.dist
        for b in self.bots:
            if b.out_at is None:
                b.score = b.dist
        # corte: o último quando o primeiro passa a linha
        leader = max(positions)
        if leader >= self.next_cut:
            field_ = [(self.dist, None)] + [(b.dist, b) for b in alive]
            field_.sort(key=lambda x: x[0])
            last = field_[0][1]
            self.next_cut += self.LAP_M
            if last is None:
                self.out = True
                self.place = len(field_)
                self.rank = self.place
                self.won = False
                ev.append(("game_judge", {"ok": False,
                                          "text": t("game.elim.you_out", n=self.place)}))
                return ev + self.end()
            last.out_at = self.t
            ev.append(("game_cue", {"text": t("game.elim.bot_out", name=last.name)}))
            if not self._alive():
                self.place = 1
                self.rank = 1
                self.won = True
                ev.append(("game_judge", {"ok": True, "text": t("game.elim.win")}))
                return ev + self.end()
        alive = self._alive()
        order = sorted([(self.dist, True)] + [(b.dist, False) for b in alive],
                       key=lambda x: -x[0])
        pos = next(i for i, (_, me) in enumerate(order) if me) + 1
        gap_last = self.dist - min(b.dist for b in alive) if alive else 0.0
        self.headline = t("game.elim.status", pos=pos, n=len(order),
                          m=int(max(0.0, self.next_cut - leader)))
        self.detail = t("game.elim.detail", kmh=f"{self.speed * 3.6:.1f}",
                        gap=f"{gap_last:+.0f}",
                        draft=t("game.elim.draft") if self._cda(self.dist, [b.dist for b in alive]) < 0.32 else "")
        self.mood = "bad" if pos == len(order) else ("warn" if pos >= len(order) - 1 else "good")
        self.progress = 1.0 - max(0.0, self.next_cut - leader) / self.LAP_M
        return ev

    def _final_rank(self) -> None:
        if self.rank is None:
            alive = self._alive()
            self.rank = 1 + sum(1 for b in alive if b.dist > self.dist)
            self.won = self.rank == 1

    def standings(self):
        rows = [(t("board.me"), self.dist, True)] + [(b.name, b.dist if b.out_at is None
                                                      else -1e6 + (b.out_at or 0), False)
                                                     for b in self.bots]
        rows.sort(key=lambda r: -r[1])
        return rows

    def format_score(self, v: float) -> str:
        return t("game.elim.out_short") if v < -1000 else f"{v:.0f} m"

    def summary_text(self) -> str:
        return t("game.elim.summary", place=self.rank or "—", n=len(self.bots) + 1,
                 m=f"{self.dist:.0f}")


# =============================================================== Cabo de guerra


class TugOfWar(Game):
    key = "tug"
    durations = (5, 10)
    default_minutes = 10
    K = 0.02                  # quanto a corda anda por segundo de diferença

    def setup(self) -> None:
        self.rope = 0.0       # -1 perdes, +1 ganhas
        self.wave_t = 0.0
        self.wave_len = 20
        self.wave_rel = 0.7
        self.n_bots = 1
        self.bots = self.bots[:1] or [Bot("Bot", self.ftp)]
        b = self.bots[0]
        b.ftp = self.ftp * self.rng.uniform(0.95, 1.05)
        b.wmax = b.wbal = b.ftp * 80

    def _tick(self, power: float) -> list[tuple[str, dict]]:
        ev = []
        b = self.bots[0]
        self.wave_t += 1
        if self.wave_t >= self.wave_len:
            self.wave_t = 0
            pulling = self.wave_rel < 1.0
            self.wave_len = self.rng.choice((10, 15, 20, 30)) if pulling else \
                self.rng.choice((10, 15, 20))
            self.wave_rel = self.rng.uniform(1.15, 1.5) if pulling else self.rng.uniform(0.6, 0.8)
            ev.append(("game_cue", {"text": t("game.tug.pull" if pulling else "game.tug.ease",
                                              name=b.name)}))
        bp = self._bot_effort(b, self.wave_rel)
        mine, theirs = power / self.ftp, bp / b.ftp
        self.rope = max(-1.0, min(1.0, self.rope + self.K * (mine - theirs)))
        self.score = (self.rope + 1) * 50
        b.score = (1 - self.rope) * 50
        self.headline = t("game.tug.status", pct=f"{self.score:.0f}", name=b.name,
                          w=int(bp))
        self.detail = t("game.tug.detail", me=f"{mine * 100:.0f}", them=f"{theirs * 100:.0f}",
                        left=hms(max(0, self.total_s - self.t)))
        self.mood = "good" if self.rope > 0.1 else ("bad" if self.rope < -0.1 else "warn")
        self.progress = (self.rope + 1) / 2
        if abs(self.rope) >= 1.0:
            self.won = self.rope > 0
            self.rank = 1 if self.won else 2
            ev.append(("game_judge", {"ok": self.won, "text": t("game.tug.win" if self.won
                                                                  else "game.tug.lose")}))
            return ev + self.end()
        return ev

    def _final_rank(self) -> None:
        if self.rank is None:
            self.won = self.rope > 0
            self.rank = 1 if self.won else 2

    def format_score(self, v: float) -> str:
        return f"{v:.0f}%"

    def summary_text(self) -> str:
        return t("game.tug.summary", res=t("game.won") if self.won else t("game.lost"),
                 pct=f"{self.score:.0f}")


CLASSES = {c.key: c for c in (AdaptiveChallenge, ZoneHero, PowerLadder, Warmup, Elimination,
                              TugOfWar)}


def create(spec: dict, athlete, db=None, best: dict | None = None) -> Game:
    """Cria o jogo a partir das escolhas do ecrã (`spec`) e do atleta."""
    cls = CLASSES[spec["key"]]
    level = 0.9
    zones = None
    if db is not None:
        level = float(db.get("adaptive_level", 0.9))
        zones = db.get("power_zones_pct", None)
        if best is None:
            from . import stats
            best = dict(stats.power_curve(db, days=90))
    return cls(athlete.ftp_w, athlete.weight_kg, best=best, minutes=spec.get("minutes"),
               bots=spec.get("bots", 4), erg=spec.get("erg"), seed=spec.get("seed", 1),
               level=level, power_zones=zones)


# --------------------------------------------------------------- resultados


def ensure_table(db) -> None:
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS game_results (id INTEGER PRIMARY KEY,"
        " ride_id TEXT REFERENCES rides(id) ON DELETE SET NULL, game TEXT NOT NULL,"
        " score REAL, rank INTEGER, total INTEGER, won INTEGER, seconds INTEGER,"
        " details TEXT, created_at TEXT NOT NULL)")


def save_result(db, ride_id: str | None, game: Game, ranked: bool = True) -> dict:
    from .db import now_iso
    ensure_table(db)
    r = game.result()
    r["ranked"] = ranked
    db.conn.execute(
        "INSERT INTO game_results(ride_id, game, score, rank, total, won, seconds, details,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (ride_id, game.key, r["score"] if ranked else None, r["rank"], r["total"],
         None if r["won"] is None else int(r["won"]), r["seconds"], json.dumps(r),
         now_iso()))
    if game.key == "adaptive":
        db.set("adaptive_level", round(game.level, 3))   # a próxima vez começa daqui
    db.conn.commit()
    game.saved = True
    return r


def history(db, key: str, limit: int = 10) -> list[float]:
    ensure_table(db)
    order = "ASC" if key == "elimination" else "DESC"
    col = "rank" if key == "elimination" else "score"
    rows = db.conn.execute(
        f"SELECT {col} AS v FROM game_results WHERE game = ? AND {col} IS NOT NULL"
        f" ORDER BY {col} {order} LIMIT ?", (key, limit)).fetchall()
    return [r["v"] for r in rows]


def leaderboard(db, key: str, limit: int = 10) -> Board:
    ensure_table(db)
    rows = db.conn.execute(
        "SELECT * FROM game_results WHERE game = ? AND score IS NOT NULL"
        " ORDER BY score DESC LIMIT ?", (key, limit)).fetchall()
    out = []
    fmt = CLASSES[key].format_score
    for i, r in enumerate(rows):
        label = str(r["created_at"])[:10]
        if r["rank"] and r["total"]:
            label += f" · {r['rank']}.º/{r['total']}"
        out.append(Row(i + 1, fmt(None, r["score"]), label))
    return Board(t(f"game.{key}"), out, empty=t("board.empty"))
