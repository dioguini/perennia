"""Construtor de treinos de ciclismo: blocos de repetição e exportação.

Os passos guardam-se como sempre (constante, rampa ou livre, com o alvo em %
da FTP ou em watts). O construtor junta blocos de repetição — «5 × (3 min a
110 % + 2 min a 55 %)» — que se expandem em passos ao gravar.

Exportação para os formatos que os outros programas e aparelhos leem:

- .zwo  — Zwift, TrainerRoad, MyWhoosh, TrainingPeaks Virtual
- .erg  — watts absolutos (calculados com a tua FTP de agora)
- .mrc  — % da FTP (o programa que o abre aplica a FTP dele)
- .fit  — treino estruturado para Garmin Edge / relógios / Wahoo
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence

from . import fit, naming
from .workouts import Step, Workout

FORMATS = ("zwo", "erg", "mrc", "fit")
FORMAT_LABELS = {
    "zwo": ".zwo — Zwift, TrainerRoad, MyWhoosh",
    "erg": ".erg — watts (com a tua FTP atual)",
    "mrc": ".mrc — % da FTP",
    "fit": ".fit — Garmin, Wahoo (treino estruturado)",
}
FREERIDE_PCT = 50.0          # formatos sem «livre» (.erg/.mrc): pedalar leve


def pct_of(step: Step, which: str, ftp_w: int) -> float | None:
    """Alvo do passo em % da FTP (início ou fim), venha em % ou em watts."""
    v = step.target_lo if which == "lo" else (
        step.target_hi if step.target_hi is not None else step.target_lo)
    if step.target_type == "none" or v is None:
        return None
    if step.target_type == "watts":
        return v / max(1, ftp_w) * 100.0
    return float(v)


def expand_repeat(times: int, block: Sequence[Step]) -> list[Step]:
    out: list[Step] = []
    for _ in range(max(1, int(times))):
        out.extend(Step(**s.as_dict()) for s in block)
    return out


# ------------------------------------------------------------------- .zwo


def to_zwo(wk: Workout, ftp_w: int) -> str:
    root = ET.Element("workout_file")
    ET.SubElement(root, "author").text = "Perennia"
    ET.SubElement(root, "name").text = wk.name
    ET.SubElement(root, "description").text = wk.description or ""
    ET.SubElement(root, "sportType").text = "bike"
    ET.SubElement(root, "tags")
    body = ET.SubElement(root, "workout")
    n = len(wk.steps)
    for i, st in enumerate(wk.steps):
        dur = str(int(st.duration_s))
        lo, hi = pct_of(st, "lo", ftp_w), pct_of(st, "hi", ftp_w)
        if st.kind == "freeride" or lo is None:
            el = ET.SubElement(body, "FreeRide", Duration=dur)
        elif st.kind == "ramp" and hi is not None and abs(hi - lo) > 0.5:
            tag = "Warmup" if i == 0 and hi > lo else (
                "Cooldown" if i == n - 1 and hi < lo else "Ramp")
            el = ET.SubElement(body, tag, Duration=dur, PowerLow=f"{lo / 100:.3f}",
                               PowerHigh=f"{hi / 100:.3f}")
        else:
            el = ET.SubElement(body, "SteadyState", Duration=dur, Power=f"{lo / 100:.3f}")
        if st.cadence_lo:
            el.set("Cadence", str(int(st.cadence_lo)))
        if st.text_cue:
            ET.SubElement(el, "textevent", timeoffset="0", message=st.text_cue)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode") + "\n"


# --------------------------------------------------------------- .erg/.mrc


def _course(wk: Workout, ftp_w: int, watts: bool) -> str:
    unit = "WATTS" if watts else "PERCENT"
    lines = ["[COURSE HEADER]", "VERSION = 2", "UNITS = ENGLISH",
             f"DESCRIPTION = {wk.description or wk.name}", f"FILE NAME = {wk.name}"]
    if watts:
        lines.append(f"FTP = {ftp_w}")
    lines += [f"MINUTES {unit}", "[END COURSE HEADER]", "[COURSE DATA]"]
    t = 0.0
    for st in wk.steps:
        lo, hi = pct_of(st, "lo", ftp_w), pct_of(st, "hi", ftp_w)
        if lo is None:
            lo = hi = FREERIDE_PCT
        if st.kind != "ramp" or hi is None:
            hi = lo
        a = lo / 100.0 * ftp_w if watts else lo
        b = hi / 100.0 * ftp_w if watts else hi
        end = t + st.duration_s / 60.0
        lines.append(f"{t:.2f}\t{a:.0f}" if watts else f"{t:.2f}\t{a:.1f}")
        lines.append(f"{end:.2f}\t{b:.0f}" if watts else f"{end:.2f}\t{b:.1f}")
        t = end
    lines.append("[END COURSE DATA]")
    cues = [(sum(s.duration_s for s in wk.steps[:i]), s.text_cue)
            for i, s in enumerate(wk.steps) if s.text_cue]
    if cues:
        lines.append("[COURSE TEXT]")
        for start, text in cues:
            lines.append(f"{int(start)}\t{text}\t10")
        lines.append("[END COURSE TEXT]")
    return "\r\n".join(lines) + "\r\n"


def to_erg(wk: Workout, ftp_w: int) -> str:
    return _course(wk, ftp_w, watts=True)


def to_mrc(wk: Workout, ftp_w: int) -> str:
    return _course(wk, ftp_w, watts=False)


# -------------------------------------------------------------------- .fit


def fit_steps(wk: Workout, ftp_w: int) -> list[dict]:
    """Passos para o .fit. As rampas não existem no formato: partem-se em
    degraus de pelo menos 1 minuto (no máximo 10 por rampa)."""
    out: list[dict] = []
    n = len(wk.steps)
    for i, st in enumerate(wk.steps):
        lo, hi = pct_of(st, "lo", ftp_w), pct_of(st, "hi", ftp_w)
        if lo is None:
            out.append({"name": st.text_cue or "Livre", "seconds": st.duration_s,
                        "low": None, "unit": None, "intensity": "active",
                        "notes": st.text_cue or ""})
            continue
        hi = hi if hi is not None else lo
        if i == 0 and (hi > lo or hi < 60):
            intensity = "warmup"
        elif i == n - 1 and (hi < lo or hi < 60):
            intensity = "cooldown"
        elif max(lo, hi) < 60:
            intensity = "rest"
        else:
            intensity = "active"
        if st.kind == "ramp" and abs(hi - lo) > 0.5:
            pieces = max(1, min(10, st.duration_s // 60))
            base = st.duration_s // pieces
            for k in range(pieces):
                secs = base if k < pieces - 1 else st.duration_s - base * (pieces - 1)
                mid = lo + (hi - lo) * (k + 0.5) / pieces
                out.append({"name": f"Rampa {k + 1}/{pieces}", "seconds": secs,
                            "low": mid - 2.5, "high": mid + 2.5, "unit": "pct",
                            "intensity": intensity, "notes": st.text_cue or ""})
            continue
        name = st.text_cue or f"{lo:.0f} % FTP"
        out.append({"name": name[:31], "seconds": st.duration_s,
                    "low": lo - 2.5, "high": lo + 2.5, "unit": "pct",
                    "intensity": intensity,
                    "notes": (f"{st.cadence_lo} rpm · " if st.cadence_lo else "")
                    + (st.text_cue or "")})
    return out


# ---------------------------------------------------------------- gravar


def export(wk: Workout, fmt: str, folder: str | Path, ftp_w: int) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = naming.clean(wk.name) or "treino"
    path, _ = naming.unique_path(folder, stem, f".{fmt}")
    if fmt == "zwo":
        path.write_text(to_zwo(wk, ftp_w), encoding="utf-8")
    elif fmt == "erg":
        path.write_text(to_erg(wk, ftp_w), encoding="utf-8")
    elif fmt == "mrc":
        path.write_text(to_mrc(wk, ftp_w), encoding="utf-8")
    elif fmt == "fit":
        fit.write_workout(path, wk.name, fit_steps(wk, ftp_w))
    else:
        raise ValueError(f"formato desconhecido: {fmt}")
    return path


def duration_text(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def ceil_div(a: int, b: int) -> int:
    return int(math.ceil(a / b))
