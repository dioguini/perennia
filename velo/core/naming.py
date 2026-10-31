"""Nome da atividade e do ficheiro .fit: perennia_<data>_<ficheiro .gpx>.

O mesmo nome vai para o ficheiro, para dentro do .fit e para a base de
dados. Sem rota, usa-se o que a sessão foi: o nome do treino, «teste-ftp»,
«fuga» ou «livre».
"""
from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

PREFIX = "perennia"
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def clean(text: str) -> str:
    """Tira o que não pode estar num nome de ficheiro no Windows, macOS ou
    Linux. Mantém acentos e espaços (passam a «-»); corta pontos no fim."""
    text = unicodedata.normalize("NFC", text or "").strip()
    text = _BAD.sub("", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip(". ")[:80]


def gpx_stem(source_filename: str | None, route_name: str | None) -> str:
    if source_filename:
        stem = Path(source_filename).name
        if stem.lower().endswith(".gpx"):
            stem = stem[:-4]
        if clean(stem):
            return clean(stem)
    return clean(route_name or "")


def activity_name(start_unix: float, *, source_filename: str | None = None,
                  route_name: str | None = None, kind: str = "route",
                  workout_name: str | None = None) -> str:
    date = time.strftime("%Y-%m-%d", time.localtime(start_unix))
    what = gpx_stem(source_filename, route_name)
    if not what:
        if kind in ("workout", "strength", "game", "test", "conditioning", "free") and workout_name:
            what = clean(workout_name)
        else:
            what = {"ftp_test": "teste-ftp", "chase": "fuga"}.get(kind, "livre")
    return f"{PREFIX}_{date}_{what or 'livre'}"


def unique_path(folder: Path, name: str, suffix: str = ".fit") -> tuple[Path, str]:
    """Duas sessões no mesmo dia e na mesma rota: a segunda leva «_2», etc."""
    folder = Path(folder)
    candidate, n = name, 1
    while (folder / f"{candidate}{suffix}").exists():
        n += 1
        candidate = f"{name}_{n}"
    return folder / f"{candidate}{suffix}", candidate


def pretty(name: str | None) -> str:
    """«perennia_2026-10-30_Força-A-·-corpo» → «Força A · corpo» (para as listas)."""
    import re as _re
    if not name:
        return ""
    n = _re.sub(r"^(perennia|velolocal)_\d{4}-\d{2}-\d{2}_", "", str(name))
    n = _re.sub(r"_\d+$", "", n)
    return n.replace("-", " ").strip()
