"""Exportar um treino de qualquer desporto para um ficheiro (Transferências).

* ciclismo — .zwo, .erg, .mrc e .fit (ver `workout_export`);
* remo — .fit (treino estruturado) e os dois abaixo;
* todos — .json (o treino da Perennia, com blocos e objetivos) e .txt (para ler
  ou imprimir).

O ficheiro vai para a pasta Transferências do computador.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import naming
from . import objectives as ob
from .i18n import tr

COMMON = {"json": ".json — Perennia (blocos e objetivos)", "txt": ".txt — para ler ou imprimir"}


def formats(sport: str) -> list[tuple[str, str]]:
    """[(extensão, descrição)] dos formatos do desporto."""
    from . import workout_export as wx
    out: list[tuple[str, str]] = []
    if sport == "cycling":
        out += [(f, wx.FORMAT_LABELS[f]) for f in wx.FORMATS]
    elif sport == "rowing":
        out.append(("fit", ".fit — Garmin, Wahoo (treino estruturado)"))
    out += list(COMMON.items())
    return out


def downloads_dir() -> Path:
    """A pasta Transferências (Downloads): a que existir, senão cria-se
    `~/Downloads`. `PERENNIA_DOWNLOADS` força outra (testes, servidores)."""
    forced = os.environ.get("PERENNIA_DOWNLOADS")
    if forced:
        p = Path(forced)
    else:
        home = Path(os.path.expanduser("~"))
        p = next((home / n for n in ("Downloads", "Transferências", "Descargas")
                  if (home / n).is_dir()), home / "Downloads")
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_name(name: str | None) -> str:
    return naming.clean(name or "") or "treino"


def brief_text(brief: ob.Brief) -> str:
    lines = [brief.title, "=" * max(3, len(brief.title)), ""]
    meta = [brief.sport]
    if brief.seconds:
        s = int(round(brief.seconds))
        meta.append(f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600
                    else f"{s // 60}:{s % 60:02d}")
    if brief.meters:
        meta.append(f"{brief.meters / 1000:.2f} km")
    if brief.tss:
        meta.append(f"TSS ≈ {brief.tss:.0f}")
    lines.append(" · ".join(meta))
    if brief.goal:
        lines += ["", tr("Objetivo", "Goal") + ": " + brief.goal]
    if brief.intensity:
        lines.append(brief.intensity)
    lines += ["", tr("Blocos", "Blocks") + ":"]
    for i, b in enumerate(brief.blocks, 1):
        rep = f"{b.repeat} × " if b.repeat > 1 else ""
        lines.append(f"{i:>2}. {rep}{b.name} — {b.dur_text} — "
                     + tr("alvo", "target") + f" {b.target}")
        if b.goal:
            lines.append(f"      {b.goal}")
    return "\n".join(lines) + "\n"


def export(db, sport: str, wid: str, fmt: str, folder: str | Path, filename: str) -> Path:
    """Grava o treino em `folder/filename.fmt` (sem escrever por cima de outro:
    acrescenta «_2», «_3»…). Devolve o caminho."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = default_name(filename)
    path, _ = naming.unique_path(folder, stem, f".{fmt}")
    if sport == "cycling" and fmt in ("zwo", "erg", "mrc", "fit"):
        from . import workout_export as wx
        from . import workouts
        row = db.workout(wid)
        if row is None:
            raise ValueError("o treino já não existe")
        from perennia.ui.sport_screens import _steps_from_db
        wk = workouts.Workout(row["name"], _steps_from_db(db, wid), row["description"],
                              row["source_format"])
        ftp = db.athlete().ftp_w
        if fmt == "zwo":
            path.write_text(wx.to_zwo(wk, ftp), encoding="utf-8")
        elif fmt == "erg":
            path.write_text(wx.to_erg(wk, ftp), encoding="utf-8")
        elif fmt == "mrc":
            path.write_text(wx.to_mrc(wk, ftp), encoding="utf-8")
        else:
            from . import fit
            fit.write_workout(path, wk.name, wx.fit_steps(wk, ftp))
        return path
    if sport == "rowing" and fmt == "fit":
        from . import fit
        from . import rowing as rw
        wk = rw.workout(db, wid)
        if wk is None:
            raise ValueError("o treino já não existe")
        ftp = rw.row_ftp(db)
        steps = []
        for s in wk["steps"]:
            rng = s.watts_range(ftp)
            steps.append({"name": s.kind, "seconds": s.dur_value if s.dur_type == "time"
                          else None, "meters": s.dur_value if s.dur_type == "distance" else None,
                          "lo_w": rng[0] if rng else None, "hi_w": rng[1] if rng else None,
                          "intensity": s.kind, "notes": s.cue})
        fit.write_row_workout(path, wk["name"], steps)
        return path
    brief = ob.workout_brief(db, sport, wid) if sport != "gym" else _gym_brief(db, wid)
    if brief is None:
        raise ValueError("o treino já não existe")
    if fmt == "json":
        path.write_text(json.dumps({"perennia": 1, **brief.as_dict()}, ensure_ascii=False,
                                   indent=2), encoding="utf-8")
    elif fmt == "txt":
        path.write_text(brief_text(brief), encoding="utf-8")
    else:
        raise ValueError(f"formato desconhecido: {fmt}")
    return path


def _gym_brief(db, wid: str):
    from . import strength as st
    wk = st.workout(db, wid)
    if wk is None:
        return None
    return ob.gym_brief(db, wid, wk["name"], st.workout_items(db, wid),
                        wk.get("modality") or "strength")
