"""As importações de ficheiros (as mesmas do ecrã Definições → Sincronização
e da linha de comandos `--importar`)."""
from __future__ import annotations

from pathlib import Path

from .i18n import tr

KINDS = {"hrv4training": "hrv4training", "analises": "labs", "labs": "labs",
         "trainingpeaks": "trainingpeaks", "tp": "trainingpeaks"}


def import_file(db, kind: str, path: str | Path) -> tuple[dict, str]:
    """Importa `path`; devolve (relatório, frase para mostrar)."""
    kind = KINDS.get(kind, kind)
    if kind == "hrv4training":
        from . import health
        rep = health.import_file(db, path, kind="hrv4training")
        text = tr("{v} valores em {d} dias", "{v} values over {d} days",
                  v=rep.get("values", 0), d=rep.get("days", 0))
    elif kind == "labs":
        from . import labs
        rep = labs.import_xlsx(db, path) if str(path).lower().endswith(
            (".xlsx", ".xlsm")) else labs.import_csv(db, path)
        text = tr("{r} colheitas · {n} resultados", "{r} collections · {n} results",
                  r=rep["reports"], n=rep["results"])
    elif kind == "trainingpeaks":
        from . import tp_import
        rep = tp_import.import_csv(db, path)
        text = tr("{n} atividades · {s} só planeadas (ignoradas)",
                  "{n} activities · {s} only planned (skipped)",
                  n=rep["activities"], s=rep["skipped"])
    else:
        raise ValueError(f"tipo desconhecido: {kind}")
    return rep, text
