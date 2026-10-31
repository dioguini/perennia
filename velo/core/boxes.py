"""As 6 caixas de métricas do ecrã da sessão.

Cada caixa tem um número (1–6), um nome e de 1 a 7 métricas, por ordem. O
atleta escolhe-as nas Definições. Fica tudo num só valor das definições
(`hud_boxes`), uma lista de 6 dicionários `{"name": ..., "metrics": [...]}`.
Um nome vazio usa o nome por omissão dessa caixa, traduzido.
"""
from __future__ import annotations

from typing import Any

from .i18n import t

N_BOXES = 6
MAX_PER_BOX = 7
STACKED_MAX = 4      # até 4 métricas: rótulo por cima, valor grande; mais: em linha

DEFAULT_BOXES: list[list[str]] = [
    ["power_3s", "avg_power", "power_zone", "np"],
    ["cadence", "power_balance", "power_lr", "torque_eff"],
    ["hr", "hr_zone", "avg_hr", "pedal_smooth"],
    ["speed", "dist_done", "dist_left", "avg_speed"],
    ["grade_now", "avg_grade_1km", "ascent", "avg_grade_5km"],
    ["elapsed", "eta", "tss_accum", "work_kj"],
]


def enabled_metrics(db: Any, registry_order: list[str]) -> list[str]:
    """As métricas que o atleta quer ter disponíveis (Definições). As que ele
    desligou não aparecem no editor das caixas. Métricas novas entram ligadas."""
    off = set(db.get("metrics_disabled", []) or [])
    return [m for m in registry_order if m not in off]


def set_enabled(db: Any, mid: str, on: bool) -> None:
    off = set(db.get("metrics_disabled", []) or [])
    if on:
        off.discard(mid)
    else:
        off.add(mid)
    db.set("metrics_disabled", sorted(off))


def default_name(index: int) -> str:
    return t(f"box.default.{index + 1}")


def load(db: Any, registry: dict | None = None) -> list[dict]:
    """Lê as caixas e corrige o que estiver estragado: sempre 6, no máximo
    4 métricas cada, só métricas que existem, sem repetidas na mesma caixa."""
    raw = db.get("hud_boxes", None)
    if not isinstance(raw, list):
        raw = []
    out: list[dict] = []
    for i in range(N_BOXES):
        item = raw[i] if i < len(raw) and isinstance(raw[i], dict) else None
        if item is None:
            out.append({"name": "", "metrics": list(DEFAULT_BOXES[i])})
            continue
        metrics: list[str] = []
        for mid in item.get("metrics", []) or []:
            if not isinstance(mid, str) or mid in metrics:
                continue
            if registry is not None and mid not in registry:
                continue
            metrics.append(mid)
        out.append({"name": str(item.get("name") or "")[:24],
                    "metrics": metrics[:MAX_PER_BOX]})
    return out


def save(db: Any, boxes: list[dict]) -> None:
    db.set("hud_boxes", [{"name": b.get("name", ""), "metrics": list(b["metrics"])[:MAX_PER_BOX]}
                         for b in boxes[:N_BOXES]])


def title(boxes: list[dict], index: int) -> str:
    name = boxes[index].get("name") or default_name(index)
    return f"{index + 1} · {name}"


def toggle(boxes: list[dict], index: int, mid: str) -> bool:
    """Põe ou tira uma métrica da caixa. False se a caixa já estiver cheia."""
    metrics = boxes[index]["metrics"]
    if mid in metrics:
        metrics.remove(mid)
        return True
    if len(metrics) >= MAX_PER_BOX:
        return False
    metrics.append(mid)
    return True


def move(boxes: list[dict], index: int, mid: str, step: int) -> None:
    """Muda a posição de uma métrica dentro da caixa (−1 sobe, +1 desce)."""
    metrics = boxes[index]["metrics"]
    if mid not in metrics:
        return
    i = metrics.index(mid)
    j = max(0, min(len(metrics) - 1, i + step))
    metrics.insert(j, metrics.pop(i))
