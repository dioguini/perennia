"""Avisos sonoros e visíveis do fim (e do princípio) de um bloco, de uma série ou de um descanso.

As **regras** são do atleta (Definições → Configurações sonoras) e ficam na base, na definição
`sound_rules`. Cada regra diz **quando** (os *primeiros* ou os *últimos* N segundos), **quantos
bips por segundo** (0 = um só bip, no início da janela) e **onde** (em tudo, só nos blocos e séries,
ou só nos descansos). Por exemplo:

* os primeiros 10 s com um bip   → `{"when": "first", "seconds": 10, "per_s": 0}`;
* os últimos 10 s com um bip por segundo → `{"when": "last", "seconds": 10, "per_s": 1}`;
* os últimos 5 s com 2 bips por segundo  → `{"when": "last", "seconds": 5, "per_s": 2}`.

Sem regras guardadas valem as de origem: os últimos 5 s, um bip por segundo, e um bip mais
longo quando o tempo acaba. Os últimos 5 segundos vêm **sempre** também à vista, nos ecrãs
(o `visible_count`), mesmo com o som desligado.
"""
from __future__ import annotations

import math
from typing import Callable

from .i18n import tr

WHENS = ("first", "last")
SCOPES = ("all", "work", "rest")
MAX_PER_S = 4
VISIBLE_S = 5                    # os últimos segundos que se veem sempre
LATE_S = 0.6                     # um bip que já passou há mais do que isto não se toca

DEFAULT_RULES: list[dict] = [
    {"id": "r1", "when": "last", "seconds": 5, "per_s": 1, "scope": "all"},
]


# ------------------------------------------------------------------ definições


def rules(db) -> list[dict]:
    """As regras em vigor (as de origem enquanto não houver outras guardadas)."""
    try:
        saved = db.get("sound_rules", None)
    except Exception:
        saved = None
    if saved is None:
        return [dict(r) for r in DEFAULT_RULES]
    out = []
    for r in saved if isinstance(saved, list) else []:
        if isinstance(r, dict) and r.get("when") in WHENS:
            out.append({"id": str(r.get("id") or f"r{len(out) + 1}"), "when": r["when"],
                        "seconds": max(1, min(600, int(r.get("seconds") or 1))),
                        "per_s": max(0, min(MAX_PER_S, int(r.get("per_s") or 0))),
                        "scope": r.get("scope") if r.get("scope") in SCOPES else "all"})
    return out


def save_rules(db, items: list[dict]) -> None:
    db.set("sound_rules", [dict(r) for r in items])


def enabled(db) -> bool:
    try:
        return bool(db.get("sound_on", True))
    except Exception:
        return True


def end_beep(db) -> bool:
    try:
        return bool(db.get("sound_end", True))
    except Exception:
        return True


def new_id(items: list[dict]) -> str:
    used = {r["id"] for r in items}
    n = 1
    while f"r{n}" in used:
        n += 1
    return f"r{n}"


def when_label(when: str) -> str:
    return tr("Primeiros", "First") if when == "first" else tr("Últimos", "Last")


def scope_label(scope: str) -> str:
    return {"all": tr("em tudo", "everywhere"),
            "work": tr("nos blocos e nas séries", "in blocks and sets"),
            "rest": tr("nos descansos", "in rests")}.get(scope, scope)


def per_label(per_s: int) -> str:
    if per_s <= 0:
        return tr("um só bip", "a single beep")
    if per_s == 1:
        return tr("1 bip por segundo", "1 beep per second")
    return tr("{n} bips por segundo", "{n} beeps per second", n=per_s)


def describe(rule: dict) -> str:
    """«Últimos 5 s · 2 bips por segundo · em tudo»."""
    return (f"{when_label(rule['when'])} {rule['seconds']} s · {per_label(rule['per_s'])}"
            f" · {scope_label(rule['scope'])}")


# --------------------------------------------------------------------- eventos


def events(rule: dict) -> list[float]:
    """Os instantes de uma regra: em segundos a **faltar** (as «últimas») ou **decorridos** (as
    «primeiras»), por ordem de acontecer."""
    n, p = int(rule["seconds"]), int(rule["per_s"])
    if rule["when"] == "first":
        return [0.0] if p <= 0 else [k / p for k in range(n * p)]
    return [float(n)] if p <= 0 else [n - k / p for k in range(n * p)]


def visible_count(remaining: float | None) -> int | None:
    """O número que se vê nos últimos segundos (5, 4, 3, 2, 1), ou None."""
    if remaining is None or remaining <= 0 or remaining > VISIBLE_S:
        return None
    return int(math.ceil(remaining - 1e-9))


class CueTracker:
    """Acompanha o segmento em curso (um bloco, uma série, um descanso) e toca os bips das
    regras. `beep(kind)` toca (`"short"` ou `"long"`); o `update` devolve o número dos
    últimos segundos, para o ecrã o mostrar."""

    def __init__(self, items: list[dict], beep: Callable[[str], None], *, on: bool = True,
                 long_at_end: bool = True):
        self.items = items
        self.beep = beep
        self.on = on
        self.long_at_end = long_at_end
        self._key = None
        self._fired: set = set()

    def reset(self) -> None:
        self._key = None
        self._fired = set()

    def update(self, key, kind: str, elapsed: float, remaining: float | None) -> int | None:
        """`key`: quem é o segmento (muda quando passa ao seguinte); `kind`: `"work"` ou
        `"rest"`; `elapsed`: segundos desde o início; `remaining`: segundos que faltam (None se
        o segmento não tem fim marcado)."""
        if key != self._key:
            self._key = key
            self._fired = set()
        if self.on:
            self._ring(kind, elapsed, remaining)
        return visible_count(remaining)

    def _ring(self, kind: str, elapsed: float, remaining: float | None) -> None:
        ring = None
        for ri, rule in enumerate(self.items):
            if rule["scope"] not in ("all", kind):
                continue
            for ei, at in enumerate(events(rule)):
                tag = (ri, ei)
                if tag in self._fired:
                    continue
                if rule["when"] == "first":
                    late = elapsed - at
                else:
                    if remaining is None:
                        continue
                    late = at - remaining
                if late < 0:
                    continue                          # ainda não é a hora
                self._fired.add(tag)
                if late <= LATE_S:
                    ring = "short"
        if self.long_at_end and remaining is not None and ("end",) not in self._fired \
                and remaining <= 0 and elapsed > 0.5:
            self._fired.add(("end",))
            ring = "long"
        if ring:
            self.beep(ring)
