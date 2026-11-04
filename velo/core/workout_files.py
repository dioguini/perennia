"""Treinos carregados do computador, em todos os desportos menos o ginásio.

Formatos:

* `.zwo` (Zwift; no remo, na corrida e na natação o valor é a % do limiar);
* `.mrc` / `.erg` (TrainerRoad, PerfPRO — só ciclismo);
* `.fit` do tipo «workout» (Garmin, Wahoo, e os que a Perennia exporta):
  passos por tempo ou por distância, alvo em potência (% FTP ou W) ou em
  velocidade, e os blocos «repetir».

`read()` reduz tudo a passos neutros (`FileStep`) e `save()` grava-os no
formato do desporto — na lista de treinos (`keep=True`) ou só para a sessão
(estado `session`, ver session_workouts).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import session_workouts as sw
from .i18n import tr

EXTS = {"cycling": (".zwo", ".mrc", ".erg", ".fit"), "rowing": (".zwo", ".fit"),
        "running": (".zwo", ".fit"), "swimming": (".zwo", ".fit")}
FOLDERS = ("workouts", ".", "~/Downloads", "~/Documents")
PER_FOLDER = 25


@dataclass
class FileStep:
    kind: str = "active"            # warmup | active | rest | cooldown
    dur_type: str = "time"          # time (s) | distance (m)
    dur: float = 300.0
    lo: float | None = None         # % do limiar (FTP ou ritmo); None = livre
    hi: float | None = None
    ramp: bool = False
    cadence: int | None = None
    cue: str = ""


@dataclass
class Loaded:
    name: str
    description: str = ""
    steps: list[FileStep] = field(default_factory=list)
    fmt: str = ""
    path: str = ""


class FileError(ValueError):
    pass


# --------------------------------------------------------------- procurar


def scan(sport: str, folders: list[str] | None = None) -> list[Path]:
    """Os ficheiros de treino nas pastas do costume (a pasta «workouts» ao lado
    da aplicação, Transferências, Documentos)."""
    from velo import paths
    exts = EXTS.get(sport, ())
    if folders is None:
        folders = [str(p) for p in paths.user_folder("workouts")] + list(FOLDERS)
    found: list[Path] = []
    for folder in dict.fromkeys(folders):
        base = Path(os.path.expanduser(folder))
        if not base.is_dir():
            continue
        files = sorted(p for p in base.iterdir() if p.is_file() and p.suffix.lower() in exts)
        found.extend(files[:PER_FOLDER])
    return found


# ------------------------------------------------------------------ ler


def _classify(steps: list[FileStep]) -> None:
    """Aquecimento no início, retorno à calma no fim, recuperação abaixo de 60 %."""
    n = len(steps)
    for i, s in enumerate(steps):
        if s.lo is None:
            continue
        hi = s.hi if s.hi is not None else s.lo
        if i == 0 and (hi > s.lo + 0.5 or hi < 60):
            s.kind = "warmup"
        elif i == n - 1 and n > 1 and (hi < s.lo - 0.5 or hi < 60):
            s.kind = "cooldown"
        elif max(s.lo, hi) < 60:
            s.kind = "rest"


def read(path: str | Path, sport: str, ftp_w: int | None = None,
         threshold_mps: float | None = None) -> Loaded:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in EXTS.get(sport, ()):
        raise FileError(tr("formato não suportado neste desporto: {e}",
                           "format not supported in this sport: {e}", e=ext))
    if ext == ".fit":
        out = _read_fit(path, ftp_w, threshold_mps)
    else:
        out = _read_text(path, ftp_w)
    if not out.steps:
        raise FileError(tr("o ficheiro não tem passos", "the file has no steps"))
    out.path = str(path)
    return out


def _read_text(path: Path, ftp_w: int | None) -> Loaded:
    from . import workouts as wk_mod
    try:
        wk = wk_mod.import_workout(path)
    except wk_mod.WorkoutError as e:
        raise FileError(str(e)) from e
    steps = []
    for s in wk.steps:
        lo, hi = s.target_lo, s.target_hi
        if s.target_type == "watts" and lo is not None and ftp_w:
            lo = lo / ftp_w * 100
            hi = (hi / ftp_w * 100) if hi is not None else None
        if s.target_type == "none" or s.kind == "freeride":
            lo = hi = None
        ramp = s.kind == "ramp" and lo is not None and hi is not None and abs(hi - lo) > 0.5
        steps.append(FileStep("active", "time", float(s.duration_s), lo,
                              hi if ramp else None, ramp, s.cadence_lo, s.text_cue or ""))
    _classify(steps)
    return Loaded(wk.name, wk.description or "", steps, wk.source_format or path.suffix[1:])


FIT_INTENSITY = {0: "active", 1: "rest", 2: "warmup", 3: "cooldown", 4: "rest", 5: "active"}
FIT_TIME, FIT_DISTANCE, FIT_OPEN, FIT_REPEAT = 0, 1, 5, 6
FIT_SPEED, FIT_HR, FIT_TARGET_OPEN, FIT_POWER = 0, 1, 2, 4


def _read_fit(path: Path, ftp_w: int | None, threshold_mps: float | None) -> Loaded:
    from . import fit
    try:
        msgs = fit.read_messages(path)
    except Exception as e:
        raise FileError(tr(".fit inválido: {e}", "invalid .fit: {e}", e=e)) from e
    name = path.stem
    raw: list[dict] = []
    for num, f in msgs:
        if num == 26:
            name = f.get(8) or name
        elif num == 27:
            raw.append(f)
    if not raw:
        raise FileError(tr("o .fit não é um treino", "the .fit is not a workout"))
    steps: list[FileStep] = []
    for f in raw:
        dt = f.get(1, FIT_TIME)
        if dt == FIT_REPEAT:
            # «repetir desde o passo N, X vezes»: os passos já estão uma vez
            start, times = int(f.get(2, 0)), int(f.get(4, 1))
            block = steps[start:]
            for _ in range(max(0, times - 1)):
                steps.extend(FileStep(**vars(s)) for s in block)
            continue
        if dt == FIT_DISTANCE:
            kind_d, dur = "distance", (f.get(2) or 0) / 100.0
        elif dt == FIT_TIME:
            kind_d, dur = "time", (f.get(2) or 0) / 1000.0
        else:
            kind_d, dur = "time", 300.0               # «até carregar no botão»
        tt = f.get(3, FIT_TARGET_OPEN)
        lo_raw, hi_raw = f.get(5), f.get(6)
        lo = hi = None
        if tt == FIT_POWER and lo_raw is not None:
            def pct(v):
                if v > 1000:                            # watts + 1000
                    return (v - 1000) / ftp_w * 100 if ftp_w else None
                return float(v)
            lo, hi = pct(lo_raw), pct(hi_raw if hi_raw is not None else lo_raw)
        elif tt == FIT_SPEED and lo_raw is not None and threshold_mps:
            lo = lo_raw / 1000.0 / threshold_mps * 100
            hi = (hi_raw if hi_raw is not None else lo_raw) / 1000.0 / threshold_mps * 100
        if lo is not None and hi is not None:
            # um intervalo de ±2,5 % (como a Perennia exporta) é um alvo fixo
            mid = (lo + hi) / 2
            lo, hi = (round(mid, 1), None) if abs(hi - lo) <= 6.5 else (lo, hi)
        steps.append(FileStep(FIT_INTENSITY.get(f.get(7, 0), "active"), kind_d,
                              max(1.0, dur), lo, hi, False, None,
                              f.get(8) or f.get(0) or ""))
    return Loaded(name, "", steps, "fit")


# ---------------------------------------------------------------- gravar


def save(db, sport: str, loaded: Loaded, keep: bool) -> str:
    """Grava o treino no formato do desporto. `keep`: fica na lista de treinos;
    senão fica só para a sessão (não aparece na lista)."""
    name = loaded.name.strip() or tr("Treino", "Workout")
    if sport == "cycling":
        from . import workouts as wk_mod
        steps = []
        for s in loaded.steps:
            secs = s.dur if s.dur_type == "time" else s.dur / (30 / 3.6)
            if s.lo is None:
                steps.append(wk_mod.Step("freeride", int(round(secs)), "none",
                                         cadence_lo=s.cadence, cadence_hi=s.cadence,
                                         text_cue=s.cue or None))
            else:
                steps.append(wk_mod.Step("ramp" if s.ramp else "steady", int(round(secs)),
                                         "pct_ftp", s.lo, s.hi if s.hi is not None else s.lo,
                                         s.cadence, s.cadence, s.cue or None))
        wk = wk_mod.Workout(name, steps, loaded.description or None, loaded.fmt)
        wid = db.insert_workout(name, [s.as_dict() for s in steps], loaded.fmt,
                                loaded.description or None,
                                wk.estimated_tss(db.athlete().ftp_w))
    elif sport == "rowing":
        from . import rowing as rw
        wid = rw.save_workout(db, None, name, loaded.description, [
            rw.Step(s.kind, s.dur_type, s.dur, "power" if s.lo is not None else "none",
                    s.lo, s.hi, None, s.cue) for s in loaded.steps])
    else:
        from . import endurance as en
        wid = en.save_workout(db, None, sport, name, loaded.description, [
            en.Step(s.kind, s.dur_type, s.dur, s.lo, s.hi, s.cue) for s in loaded.steps],
            mode="pace")
    sw.set_status(db, sport, wid, sw.ACTIVE if keep else sw.SESSION)
    if loaded.path:
        sw.FILES[wid] = Path(loaded.path).name
    return wid


def same_in_list(db, sport: str, loaded: Loaded) -> str | None:
    """Um treino da lista com o mesmo nome e os mesmos passos (para não duplicar)."""
    name = loaded.name.strip()
    def low(lo, hi):                     # (os passos de endurance põem lo ≤ hi)
        return None if lo is None else round(min(lo, hi if hi is not None else lo))
    want = [(s.dur_type, int(round(s.dur)), low(s.lo, s.hi)) for s in loaded.steps]
    if sport == "cycling":
        for w in db.workouts():
            if w["name"] != name:
                continue
            have = [("time", int(r["duration_s"] or 0),
                     None if r["target_lo"] is None or r["target_type"] == "none"
                     else low(r["target_lo"], r["target_hi"])) for r in db.workout_steps(w["id"])]
            if have == want:
                return w["id"]
        return None
    if sport == "rowing":
        from . import rowing as rw
        pool = rw.workouts(db)
    else:
        from . import endurance as en
        pool = en.workouts(db, sport)
    for w in pool:
        if w["name"] != name:
            continue
        have = [(s.dur_type, int(round(s.dur_value)), low(s.lo, s.hi)) for s in w["steps"]]
        if have == want:
            return w["id"]
    return None


def context(db, sport: str) -> tuple[int | None, float | None]:
    """(FTP, velocidade do limiar em m/s) para converter os alvos do ficheiro."""
    from . import intensity as it
    ctx = it.Context.from_db(db, sport)
    if sport == "rowing":
        return ctx.row_ftp_w, None
    if sport == "cycling":
        return ctx.ftp_w, None
    return None, ctx.speed_mps(100)
