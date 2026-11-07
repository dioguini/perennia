"""Upload manual de uma atividade: a janela que mostra o que o ficheiro tem
(nome, desporto, data, tempo, distância, FC, potência…) e deixa fazer o upload
para o desporto respetivo, ou cancelar."""
from __future__ import annotations

from pathlib import Path

from velo.core import activity_upload as au
from velo.core import sports as sp
from velo.core.i18n import tr
from velo.core.units import hms
from velo.ui.app import PopupMixin
from velo.ui.sport_screens import EditScreen
from velo.ui.widgets import Item

SPORT_CHOICES = ("cycling", "rowing", "running", "swimming", "gym")


def open_upload(app, path) -> bool:
    """Lê o ficheiro e abre a janela de pré-visualização. Os erros vão para a
    zona das mensagens, em vez de rebentar."""
    try:
        info = au.parse(Path(path))
    except au.UploadError as e:
        app.message(f"{Path(str(path)).name}: {e}")
        return False
    except OSError as e:
        app.message(f"{Path(str(path)).name}: {e}")
        return False
    app.push(UploadPreview(app, info))
    return True


def open_dropped(app, paths: list) -> bool:
    """Arrastar um .fit ou .tcx para a janela abre o upload dessa atividade."""
    for p in paths:
        p = Path(str(p))
        if p.suffix.lower() in au.EXTENSIONS:
            if getattr(app.current, "IN_SESSION", False):
                app.message(tr("Termina a sessão antes de carregar uma atividade",
                               "Finish the session before uploading an activity"))
                return True
            return open_upload(app, p)
    return False


def _km(m: float | None) -> str:
    if not m:
        return "—"
    return f"{m / 1000:.2f} km" if m >= 1000 else f"{m:.0f} m"


class UploadPreview(PopupMixin, EditScreen):
    """O resultado da leitura do ficheiro e o botão «Fazer upload»."""

    W, H = 780, 780
    SEARCH = False
    DATE_FIELDS: tuple = ()

    def __init__(self, app, info: dict, then=None):
        super().__init__(app)
        self.info = info
        self.sport = info["sport"]
        self.then = then
        self.dup = au.exists(app.db, info)
        self.back_button = None
        self._init_popup()

    # ---------------------------------------------------------------- linhas

    def cycle(self, field: str, step: int) -> None:
        if field == "sport":
            i = SPORT_CHOICES.index(self.sport) if self.sport in SPORT_CHOICES else 0
            self.sport = SPORT_CHOICES[(i + step) % len(SPORT_CHOICES)]

    def enter(self) -> None:
        i = self.info
        when = (i["started_at"] or "")[:16].replace("T", " ")
        local = when
        try:
            from datetime import datetime, timezone
            local = datetime.strptime(i["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
        except (TypeError, ValueError):
            pass
        rows = [
            Item(tr("Ficheiro", "File"), value=i["file"], enabled=False),
            Item(tr("Nome da atividade", "Activity name"), value=i["name"], enabled=False),
            Item(tr("Atividade", "Activity"), value=sp.name(self.sport),
                 detail=tr("←/→ muda o desporto onde fica guardada · o ficheiro diz «{s}»",
                           "←/→ changes the sport it is saved to · the file says «{s}»",
                           s=i["source_sport"] or "—"), data="cyc:sport"),
            Item(tr("Data e hora", "Date and time"), value=local, enabled=False),
            Item(tr("Tempo total", "Total time"), value=hms(i["elapsed_s"] or 0),
                 enabled=False),
            Item(tr("Tempo em movimento", "Moving time"), value=hms(i["moving_s"] or 0),
                 enabled=False),
            Item(tr("Distância", "Distance"), value=_km(i["distance_m"]), enabled=False),
        ]
        if i.get("ascent_m"):
            rows.append(Item(tr("Subida", "Ascent"), value=f"{i['ascent_m']:.0f} m",
                             enabled=False))
        if i.get("avg_hr"):
            rows.append(Item(tr("FC média / máxima", "Avg / max HR"),
                             value=f"{i['avg_hr']:.0f} / {i['max_hr'] or 0:.0f} bpm",
                             enabled=False))
        if i.get("avg_power_w"):
            rows.append(Item(tr("Potência média / normalizada", "Avg / normalised power"),
                             value=f"{i['avg_power_w']:.0f} / {i['np_w'] or 0:.0f} W",
                             enabled=False))
        if i.get("tss"):
            rows.append(Item("TSS", value=f"{i['tss']:.0f}", enabled=False))
        if i.get("calories"):
            rows.append(Item(tr("Calorias", "Calories"), value=f"{i['calories']:.0f} kcal",
                             enabled=False))
        rows.append(Item(tr("Voltas · registos", "Laps · records"),
                         value=f"{i['laps']} · {i['records']}", enabled=False))
        if self.dup:
            rows.append(Item(tr("Este ficheiro já foi carregado", "This file was already "
                                "uploaded"), detail=tr("fazer upload outra vez atualiza-o",
                                                       "uploading again updates it"),
                             enabled=False))
        rows += [Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop),
                 Item(tr("Fazer upload", "Upload"), button=True, primary=True,
                      action=self.upload)]
        self.chrome.set(tr("Upload manual", "Manual upload"),
                        tr("O que o ficheiro tem · confirma e faz o upload",
                           "What the file contains · confirm and upload"), "")
        self.list.set_items(rows, keep_index=True)

    def upload(self) -> None:
        au.save(self.app.db, self.info, sport=self.sport)
        self.app.pop()
        self.app.message(tr("Atividade «{n}» guardada em {s}", "Activity «{n}» saved to {s}",
                            n=self.info["name"], s=sp.name(self.sport)))
        if self.then is not None:
            self.then()


# ============================================================ exportar treino


class ExportPopup(PopupMixin, EditScreen):
    """Exportar um treino: o nome do ficheiro e o formato; OK grava-o na pasta
    Transferências e a mensagem diz onde ficou. Cancelar (ou Esc) volta aos
    detalhes do treino."""

    W, H = 760, 420
    SEARCH = False
    DATE_FIELDS: tuple = ()

    def __init__(self, app, sport: str, wid: str, name: str):
        super().__init__(app)
        from velo.core import workout_download as wf
        self.sport, self.wid = sport, wid
        self.formats = wf.formats(sport)
        self.fmt = 0
        self.name = wf.default_name(name)
        self.back_button = None
        self._init_popup()

    def cycle(self, field: str, step: int) -> None:
        if field == "format":
            self.fmt = (self.fmt + step) % len(self.formats)

    def text_input(self, field: str, text: str) -> None:
        self.name = (self.name + text)[:80]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.name = self.name[:-1]
        self.enter()

    def enter(self) -> None:
        from velo.core import workout_download as wf
        ext, label = self.formats[self.fmt]
        rows = [Item(tr("Nome do ficheiro", "File name"), value=self.name + "▏" + f".{ext}",
                     data="text:name",
                     detail=tr("escreve o nome", "type the name")),
                Item(tr("Formato", "Format"), value=label, data="cyc:format",
                     detail=tr("←/→ muda · Enter abre a lista", "←/→ changes · Enter opens "
                               "the list")),
                Item(tr("Fica em", "Saved in"), value=str(wf.downloads_dir()), enabled=False),
                Item(tr("Cancelar", "Cancel"), button=True, action=self.app.pop),
                Item("OK", button=True, primary=True, action=self.export)]
        self.chrome.set(tr("Exportar o treino", "Export the workout"),
                        tr("Dá um nome ao ficheiro e escolhe o formato",
                           "Name the file and pick the format"), "")
        self.list.set_items(rows, keep_index=True)

    def export(self) -> None:
        from velo.core import workout_download as wf
        if not self.name.strip():
            self.app.message(tr("Dá um nome ao ficheiro.", "Give the file a name."))
            return
        ext = self.formats[self.fmt][0]
        try:
            path = wf.export(self.app.db, self.sport, self.wid, ext, wf.downloads_dir(),
                             self.name)
        except Exception as e:
            self.app.message(f"{tr('Erro', 'Error')}: {e}")
            return
        self.exported = path
        self.app.pop()
        self.app.message(tr("Treino guardado em {p}", "Workout saved to {p}", p=str(path)))
