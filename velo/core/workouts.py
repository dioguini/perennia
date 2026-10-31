"""Treinos estruturados: importação e controlo ERG (req. 21).

Lê os dois formatos que existem na prática — .zwo (Zwift) e .mrc/.erg
(TrainerRoad, PerfPRO) — e reduz tudo a uma lista de passos uniforme.

Com ERG ligado, o alvo é enviado ao trainer e o atleta só tem de pedalar.
Com ERG desligado, o alvo é só mostrado e o atleta ajusta as mudanças,
como na estrada.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

TOLERANCE_PCT = 5.0   # ±5 % conta como "no alvo"


@dataclass
class Step:
    kind: str                      # steady | ramp | freeride
    duration_s: int
    target_type: str               # pct_ftp | watts | none
    target_lo: float | None = None
    target_hi: float | None = None
    cadence_lo: int | None = None
    cadence_hi: int | None = None
    text_cue: str | None = None

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "duration_s": self.duration_s,
            "target_type": self.target_type, "target_lo": self.target_lo,
            "target_hi": self.target_hi, "cadence_lo": self.cadence_lo,
            "cadence_hi": self.cadence_hi, "text_cue": self.text_cue,
        }

    def watts(self, progress: float, ftp_w: int) -> int | None:
        """Alvo em watts a `progress` (0..1) dentro do passo."""
        if self.target_type == "none" or self.target_lo is None:
            return None
        hi = self.target_hi if self.target_hi is not None else self.target_lo
        value = self.target_lo + (hi - self.target_lo) * min(max(progress, 0.0), 1.0)
        if self.target_type == "pct_ftp":
            return int(round(value / 100.0 * ftp_w))
        return int(round(value))


@dataclass
class Workout:
    name: str
    steps: list[Step]
    description: str | None = None
    source_format: str | None = None

    @property
    def total_seconds(self) -> int:
        return sum(s.duration_s for s in self.steps)

    def estimated_tss(self, ftp_w: int) -> float:
        """TSS estimada somando o quadrado da intensidade de cada passo."""
        total = 0.0
        for s in self.steps:
            w = s.watts(0.5, ftp_w)
            if w is None:
                w = int(ftp_w * 0.55)
            intensity = w / max(ftp_w, 1)
            total += s.duration_s * intensity ** 2
        return total / 3600.0 * 100.0


class WorkoutError(ValueError):
    pass


# ----------------------------------------------------------------------- .zwo


def _fnum(el: ET.Element, *names: str) -> float | None:
    for n in names:
        if n in el.attrib:
            try:
                return float(el.attrib[n])
            except ValueError:
                return None
    return None


def parse_zwo(path: str | Path) -> Workout:
    """Zwift workout. As potências vêm como fração de FTP (0.85 = 85 %)."""
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as e:
        raise WorkoutError(f".zwo inválido: {e}") from e

    name = (root.findtext("name") or Path(path).stem).strip()
    description = (root.findtext("description") or "").strip() or None
    block = root.find("workout")
    if block is None:
        raise WorkoutError("o .zwo não tem secção <workout>")

    steps: list[Step] = []
    for el in block:
        tag = el.tag
        dur = _fnum(el, "Duration") or 0.0
        cad = _fnum(el, "Cadence")
        cad_i = int(cad) if cad else None

        if tag == "IntervalsT":
            repeat = int(_fnum(el, "Repeat") or 1)
            on_d = int(_fnum(el, "OnDuration") or 0)
            off_d = int(_fnum(el, "OffDuration") or 0)
            on_p = (_fnum(el, "OnPower", "PowerOnHigh") or 1.0) * 100.0
            off_p = (_fnum(el, "OffPower", "PowerOffHigh") or 0.5) * 100.0
            on_cad = _fnum(el, "Cadence")
            off_cad = _fnum(el, "CadenceResting")
            for _ in range(repeat):
                if on_d:
                    steps.append(Step("steady", on_d, "pct_ftp", on_p, on_p,
                                      int(on_cad) if on_cad else None,
                                      int(on_cad) if on_cad else None))
                if off_d:
                    steps.append(Step("steady", off_d, "pct_ftp", off_p, off_p,
                                      int(off_cad) if off_cad else None,
                                      int(off_cad) if off_cad else None))
            continue

        if tag == "FreeRide" or tag == "MaxEffort":
            steps.append(Step("freeride", int(dur), "none", cadence_lo=cad_i,
                              cadence_hi=cad_i))
            continue

        lo = _fnum(el, "PowerLow", "Power")
        hi = _fnum(el, "PowerHigh", "Power")
        if lo is None and hi is None:
            continue
        lo = (lo if lo is not None else hi) * 100.0
        hi = (hi if hi is not None else lo / 100.0) * 100.0
        kind = "ramp" if tag in ("Warmup", "Cooldown", "Ramp") and abs(hi - lo) > 0.5 \
            else "steady"
        steps.append(Step(kind, int(dur), "pct_ftp", lo, hi, cad_i, cad_i))

    if not steps:
        raise WorkoutError("o .zwo não tem passos utilizáveis")
    return Workout(name, steps, description, "zwo")


# ------------------------------------------------------------------ .mrc/.erg


_HEADER_RE = re.compile(r"^\s*([A-Z ]+)\s*=\s*(.*?)\s*$")


def parse_mrc(path: str | Path) -> Workout:
    """.mrc (percentagem de FTP) e .erg (watts absolutos).

    O corpo são pares (minutos, valor). Cada par consecutivo define um
    segmento; quando o valor muda sem o tempo avançar, é um degrau.
    """
    text = Path(path).read_text(errors="replace")
    name = Path(path).stem
    description = None
    units_watts = str(path).lower().endswith(".erg")

    in_data = False
    rows: list[tuple[float, float]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        upper = s.upper()
        if upper.startswith("[COURSE DATA]"):
            in_data = True
            continue
        if upper.startswith("[END COURSE DATA]"):
            in_data = False
            continue
        if not in_data:
            m = _HEADER_RE.match(s)
            if m:
                key, value = m.group(1).strip(), m.group(2)
                if key == "DESCRIPTION" and value:
                    description = value
                elif key == "FILE NAME" and value:
                    name = value
                elif key == "UNITS" and "WATT" in value.upper():
                    units_watts = True
            continue
        parts = re.split(r"[\s,]+", s)
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue

    if len(rows) < 2:
        raise WorkoutError("o ficheiro não tem dados de curso utilizáveis")

    target_type = "watts" if units_watts else "pct_ftp"
    steps: list[Step] = []
    for (t0, v0), (t1, v1) in zip(rows, rows[1:]):
        dur = int(round((t1 - t0) * 60.0))
        if dur <= 0:
            continue
        kind = "ramp" if abs(v1 - v0) > 0.5 else "steady"
        steps.append(Step(kind, dur, target_type, v0, v1))
    if not steps:
        raise WorkoutError("o ficheiro não produziu passos")
    return Workout(name, steps, description, "erg" if units_watts else "mrc")


def import_workout(path: str | Path) -> Workout:
    ext = Path(path).suffix.lower()
    if ext == ".zwo":
        return parse_zwo(path)
    if ext in (".mrc", ".erg"):
        return parse_mrc(path)
    raise WorkoutError(f"formato não suportado: {ext}")


# ---------------------------------------------------------------- controlador


class WorkoutRunner:
    """Segue o treino ao longo do tempo e diz qual é o alvo agora."""

    def __init__(self, workout: Workout, ftp_w: int, erg_enabled: bool):
        self.workout = workout
        self.ftp_w = ftp_w
        self.erg_enabled = erg_enabled
        self._starts: list[int] = []
        acc = 0
        for s in workout.steps:
            self._starts.append(acc)
            acc += s.duration_s
        self.total_s = acc
        self.current_idx = -1
        self.intensity = 1.0          # +/− a meio da sessão multiplica o alvo
        # acumuladores por passo, para avaliar o cumprimento
        self._acc: dict[int, dict] = {}

    def step_at(self, elapsed_s: float) -> tuple[int, Step, float] | None:
        """Devolve (índice, passo, progresso 0..1) ou None se terminou."""
        if elapsed_s >= self.total_s:
            return None
        lo, hi = 0, len(self.workout.steps) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._starts[mid] <= elapsed_s:
                lo = mid
            else:
                hi = mid - 1
        step = self.workout.steps[lo]
        offset = elapsed_s - self._starts[lo]
        progress = offset / step.duration_s if step.duration_s else 1.0
        return lo, step, progress

    def target_watts(self, elapsed_s: float) -> int | None:
        found = self.step_at(elapsed_s)
        if found is None:
            return None
        _, step, progress = found
        w = step.watts(progress, self.ftp_w)
        return int(round(w * self.intensity)) if w is not None else None

    def step_watts(self, step: Step) -> tuple[int, int] | None:
        """(início, fim) do alvo do passo, já com a intensidade aplicada."""
        lo = step.watts(0.0, self.ftp_w)
        hi = step.watts(1.0, self.ftp_w)
        if lo is None:
            return None
        return int(round(lo * self.intensity)), int(round((hi or lo) * self.intensity))

    def plan(self, elapsed_s: float, ahead: int = 2) -> list[dict]:
        """O passo atual e os `ahead` seguintes: o que o painel do treino mostra.

        Cada um: índice, duração, quanto falta (só no atual), alvo em watts
        e em % FTP, cadência e a dica de texto.
        """
        found = self.step_at(elapsed_s)
        if found is None:
            return []
        idx, step, progress = found
        out = []
        for k in range(idx, min(len(self.workout.steps), idx + 1 + max(0, ahead))):
            st = self.workout.steps[k]
            w = self.step_watts(st)
            remaining = (st.duration_s * (1.0 - progress)) if k == idx else st.duration_s
            out.append({
                "idx": k, "current": k == idx, "duration_s": st.duration_s,
                "remaining_s": remaining, "kind": st.kind,
                "watts": w, "pct": (None if w is None
                                    else (w[0] / max(self.ftp_w, 1) * 100.0,
                                          w[1] / max(self.ftp_w, 1) * 100.0)),
                "cadence": st.cadence_lo, "cue": st.text_cue,
            })
        return out

    def compliance(self, actual_w: int | None, target_w: int | None) -> int:
        """-1 abaixo, 0 no alvo, +1 acima. Alimenta a barra do HUD."""
        if actual_w is None or target_w is None or target_w <= 0:
            return 0
        tol = target_w * TOLERANCE_PCT / 100.0
        if actual_w < target_w - tol:
            return -1
        if actual_w > target_w + tol:
            return 1
        return 0

    def observe(self, elapsed_s: float, power_w: int | None, hr: int | None,
                cadence: int | None) -> int | None:
        """Acumula a amostra no passo atual. Devolve o índice se mudou de passo."""
        found = self.step_at(elapsed_s)
        if found is None:
            return None
        idx, step, progress = found
        acc = self._acc.setdefault(idx, {"n": 0, "p_sum": 0.0, "p_n": 0, "in_target": 0,
                                         "hr_sum": 0.0, "hr_n": 0, "cad_sum": 0.0,
                                         "cad_n": 0, "target_sum": 0.0})
        acc["n"] += 1
        target = step.watts(progress, self.ftp_w)
        if target is not None:
            acc["target_sum"] += target
        if power_w is not None:
            acc["p_sum"] += power_w
            acc["p_n"] += 1
            if self.compliance(power_w, target) == 0 and target is not None:
                acc["in_target"] += 1
        if hr is not None:
            acc["hr_sum"] += hr
            acc["hr_n"] += 1
        if cadence is not None:
            acc["cad_sum"] += cadence
            acc["cad_n"] += 1

        changed = idx != self.current_idx
        self.current_idx = idx
        return idx if changed else None

    def results(self) -> list[dict]:
        out = []
        for idx, a in sorted(self._acc.items()):
            n = max(a["n"], 1)
            out.append({
                "step_idx": idx,
                "avg_power_w": a["p_sum"] / a["p_n"] if a["p_n"] else None,
                "target_avg_w": a["target_sum"] / n if a["target_sum"] else None,
                "pct_in_target": a["in_target"] / n * 100.0,
                "avg_hr": a["hr_sum"] / a["hr_n"] if a["hr_n"] else None,
                "avg_cadence": a["cad_sum"] / a["cad_n"] if a["cad_n"] else None,
            })
        return out
