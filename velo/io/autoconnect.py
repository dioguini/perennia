"""Ligar sozinho os aparelhos conhecidos, pela ordem de transporte preferida.

Com «ANT+ primeiro» (o normal): procura por ANT+ os aparelhos que já
ligaste antes; o que não aparecer procura-se por Bluetooth. Os medidores
de potência e as cintas que também existam por Bluetooth ligam-se nos dois,
e o hub dá prioridade ao ANT+. Assim, se o sinal ANT+ cair a meio da sessão,
a potência continua a chegar pelo Bluetooth sem fazeres nada, e volta ao
ANT+ quando ele voltar.

O rolo é exceção: só se liga por um caminho. Dois canais a mandar
resistência ao mesmo rolo dariam ordens contraditórias.

Só se ligam aparelhos já conhecidos (emparelhados uma vez em Dispositivos),
para não apanhar os pedais de quem treina ao lado.

O trabalho de rádio corre num fio; `connect_known` devolve as fontes
prontas, e quem as junta ao hub é o fio principal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

ANT_FIRST, BLE_FIRST, ANT_ONLY, BLE_ONLY = "ant_first", "ble_first", "ant_only", "ble_only"
PREFERENCES = (ANT_FIRST, BLE_FIRST, ANT_ONLY, BLE_ONLY)


@dataclass
class Result:
    sources: list[tuple[Any, str, bool]] = field(default_factory=list)  # (fonte, papel, é rolo)
    lines: list[str] = field(default_factory=list)                      # para mostrar
    ant_stick: Any = None
    ant_found: list = field(default_factory=list)

    def roles(self, transport: str | None = None) -> set[str]:
        return {role for src, role, _ in self.sources
                if transport is None or getattr(src, "transport", None) == transport}


def order(preference: str) -> tuple[str, ...]:
    return {ANT_FIRST: ("ant", "ble"), BLE_FIRST: ("ble", "ant"),
            ANT_ONLY: ("ant",), BLE_ONLY: ("ble",)}.get(preference, ("ant", "ble"))


def connect_known(known: list[dict], preference: str, *,
                  ant_scan: Callable[[], tuple[Any, list]] | None,
                  make_ant: Callable[[Any, int, Any], Any] | None,
                  ble_scan: Callable[[], list] | None,
                  make_ble: Callable[[Any], Any] | None) -> Result:
    """`known`: [{"id", "transport", "role", "name"}] dos aparelhos já usados."""
    res = Result()
    wanted = {"ant": {k["id"]: k for k in known if k["transport"] == "ant"},
              "ble": {k["id"]: k for k in known if k["transport"] == "ble"}}
    if not wanted["ant"] and not wanted["ble"]:
        res.lines.append("nenhum aparelho conhecido")
        return res

    for transport in order(preference):
        if not wanted[transport]:
            continue
        # Um rolo já ligado pelo primeiro transporte não se liga outra vez.
        trainer_done = any(is_trainer for _, _, is_trainer in res.sources)
        if transport == "ant":
            _ant(res, wanted["ant"], ant_scan, make_ant, trainer_done)
        else:
            _ble(res, wanted["ble"], ble_scan, make_ble, trainer_done)
    if not res.sources:
        res.lines.append("nenhum aparelho conhecido respondeu")
    return res


def _ant(res: Result, wanted: dict, scan, make, trainer_done: bool) -> None:
    if scan is None or make is None:
        return
    try:
        stick, found = scan()
    except Exception as e:
        res.lines.append(f"ANT+: {e}")
        return
    if stick is None:
        res.lines.append("ANT+: antena indisponível")
        return
    res.ant_stick, res.ant_found = stick, found
    for channel, info in found:
        if getattr(info, "trainer_twin", False) or info.device_id not in wanted:
            continue
        if info.can_control and trainer_done:
            continue
        try:
            sensor = make(stick, channel, info)
        except Exception as e:
            res.lines.append(f"ANT+ {info.name}: {e}")
            continue
        res.sources.append((sensor, info.role, info.can_control))
        res.lines.append(f"ANT+ {info.name}")


def _ble(res: Result, wanted: dict, scan, make, trainer_done: bool) -> None:
    if scan is None or make is None:
        return
    try:
        found = scan()
    except Exception as e:
        res.lines.append(f"Bluetooth: {e}")
        return
    for d in found:
        if d.device_id not in wanted:
            continue
        if d.can_control and trainer_done:
            continue
        try:
            sensor = make(d)
            ok = sensor.connect() if hasattr(sensor, "connect") else True
        except Exception as e:
            res.lines.append(f"Bluetooth {d.name}: {e}")
            continue
        if not ok:
            res.lines.append(f"Bluetooth {d.name}: não ligou")
            continue
        backup = d.role in res.roles("ant")
        res.sources.append((sensor, d.role, d.can_control))
        res.lines.append(f"Bluetooth {d.name}" + (" (reserva)" if backup else ""))
