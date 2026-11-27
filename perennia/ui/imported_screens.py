"""A ficha de uma atividade importada (ronda 36): Garmin (GarminDB), TrainingPeaks, histórico
do Strava ou do Garmin Connect, upload manual. Abre-se no calendário (no dia) e no Histórico
de cada desporto. Só de leitura: é o que a fonte registou, mais o que se tirou do .fit
(potência, TSS, IF)."""
from __future__ import annotations

from perennia.core import calendar_view as cv
from perennia.core import stats
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.ui.app import ModalScreen
from perennia.ui.widgets import Item


def get(db, aid: str) -> dict | None:
    try:
        r = db.conn.execute("SELECT * FROM synced_activities WHERE id = ?", (aid,)).fetchone()
    except Exception:
        return None
    return dict(r) if r else None


def rows_for(db, r: dict) -> list[Item]:
    """As linhas da ficha (o que houver)."""
    from perennia.ui.calendar_screens import sport_label
    try:
        lthr = db.athlete().lthr
    except Exception:
        lthr = None
    out = [Item(tr("Origem", "Source"), value=cv.imported_source(r), enabled=False,
                detail=r.get("source_sport") or ""),
           Item(tr("Desporto", "Sport"), value=sport_label(r.get("sport") or "other"),
                enabled=False),
           Item(tr("Início", "Start"),
                value=str(r.get("started_at") or "")[:16].replace("T", " "), enabled=False)]
    mv, el = r.get("moving_s"), r.get("elapsed_s")
    if mv or el:
        out.append(Item(tr("Tempo", "Time"), value=hms(mv or el or 0), enabled=False,
                        detail=tr("total {t}", "total {t}", t=hms(el)) if el and mv
                        and abs(el - mv) > 30 else ""))
    d = r.get("distance_m")
    if d:
        out.append(Item(tr("Distância", "Distance"),
                        value=f"{d / 1000:.2f} km" if d >= 1000 else f"{d:.0f} m",
                        enabled=False))
    if r.get("ascent_m"):
        out.append(Item(tr("Subida", "Ascent"), value=f"{r['ascent_m']:.0f} m", enabled=False))
    if r.get("avg_hr"):
        out.append(Item(tr("FC média", "Avg HR"), value=f"{r['avg_hr']:.0f} bpm", enabled=False,
                        detail=tr("máx {m:.0f} bpm", "max {m:.0f} bpm", m=r["max_hr"])
                        if r.get("max_hr") else ""))
    if r.get("avg_power_w"):
        out.append(Item(tr("Potência média", "Avg power"), value=f"{r['avg_power_w']:.0f} W",
                        enabled=False,
                        detail=tr("normalizada {n:.0f} W", "normalized {n:.0f} W",
                                  n=r["np_w"]) if r.get("np_w") else ""))
    elif r.get("np_w"):
        out.append(Item(tr("Potência normalizada", "Normalized power"),
                        value=f"{r['np_w']:.0f} W", enabled=False))
    if r.get("if_value"):
        out.append(Item("IF", value=f"{r['if_value']:.2f}", enabled=False))
    load = stats.synced_load(r, lthr)
    if r.get("tss") is not None:
        out.append(Item("TSS", value=f"{r['tss']:.0f}", enabled=False,
                        detail=tr("conta para a forma e a fadiga",
                                  "counts for form and fatigue")))
    elif load:
        out.append(Item(tr("Carga", "Load"), value=f"{load:.0f}", enabled=False,
                        detail=tr("pela FC média e o LTHR (sem potência)",
                                  "from the average HR and LTHR (no power)")))
    if r.get("training_load"):
        out.append(Item(tr("Carga do Garmin", "Garmin load"),
                        value=f"{r['training_load']:.0f}", enabled=False))
    if r.get("calories"):
        out.append(Item(tr("Calorias", "Calories"), value=f"{r['calories']:.0f} kcal",
                        enabled=False))
    f = r.get("fit_file")
    if f and not str(f).startswith("!"):
        from pathlib import Path
        out.append(Item(tr("Ficheiro .fit", "FIT file"), value=Path(f).name, enabled=False,
                        detail=tr("descarregado pelo GarminDB", "downloaded by GarminDB")))
    return out


class ImportedActivityScreen(ModalScreen):
    """A ficha de uma atividade importada, numa janela."""

    W, H = 760, 600

    def __init__(self, app, aid: str):
        super().__init__(app)
        self.aid = aid
        self.back_button = None

    def enter(self) -> None:
        a = self.app
        r = get(a.db, self.aid)
        if r is None:
            self.chrome.set(tr("Atividade", "Activity"), tr("já não existe", "no longer exists"),
                            "")
            rows = []
        else:
            self.chrome.set(r.get("name") or tr("Atividade importada", "Imported activity"),
                            tr("Importada · só de leitura (é o que a fonte registou)",
                               "Imported · read-only (it is what the source recorded)"), "")
            rows = rows_for(a.db, r)
        rows.append(Item(tr("Fechar", "Close"), action=a.pop, button=True, primary=True))
        self.list.set_items(rows, keep_index=True)
        self.list.index = len(self.list.items) - 1
        self.list._sync()
