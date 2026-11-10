"""As importações de ficheiros (as mesmas do ecrã Definições → Sincronização
e da linha de comandos `--importar`)."""
from __future__ import annotations

from pathlib import Path

from .i18n import tr

KINDS = {"hrv4training": "hrv4training", "analises": "labs", "labs": "labs",
         "trainingpeaks": "trainingpeaks", "tp": "trainingpeaks",
         "atividade": "upload", "upload": "upload", "csv": "csv", "saude": "saude"}


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
    elif kind == "upload":
        from . import activity_upload as au
        info = au.parse(path)
        au.save(db, info)
        rep = {"activities": 1, "sport": info["sport"]}
        text = tr("Atividade «{n}» guardada em {s}", "Activity «{n}» saved to {s}",
                  n=info["name"], s=info["sport"])
    elif kind == "saude":
        from . import health_csv
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
        rep = health_csv.import_csv(db, text)
        text = health_csv.report_text(rep)
    elif kind == "csv":
        from . import csv_sync
        key, r = csv_sync.import_file(db, path)
        rep = dict(r, dataset=key)
        text = f"{csv_sync.DATASETS[key].label}: {r.text()}"
    elif kind == "trainingpeaks":
        from . import tp_import
        rep = tp_import.import_csv(db, path)
        text = tr("{n} atividades · {s} só planeadas (ignoradas)",
                  "{n} activities · {s} only planned (skipped)",
                  n=rep["activities"], s=rep["skipped"])
    else:
        raise ValueError(f"tipo desconhecido: {kind}")
    return rep, text
