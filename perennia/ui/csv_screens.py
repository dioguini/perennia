"""A janela de um conjunto de dados do CSV (Sincronização → CSV): descarregar o modelo,
exportar o que tens e importar um .csv desse conjunto."""
from __future__ import annotations

from perennia.core import csv_sync as cs
from perennia.core.i18n import t, tr
from perennia.core.workout_download import downloads_dir
from perennia.ui.app import PopupMixin, Screen
from perennia.ui.widgets import Item


class CsvDatasetPopup(PopupMixin, Screen):
    W, H = 820, 600
    SEARCH = False
    AGENT = False

    def __init__(self, app, key: str, then=None):
        super().__init__(app)
        self.key = key
        self.then = then
        self.back_button = None
        self._init_popup()

    def enter(self) -> None:
        d = cs.DATASETS[self.key]
        rows = [Item(tr("Descarregar o modelo (.csv)", "Download the template (.csv)"),
                     detail=tr("o cabeçalho e uma linha de exemplo: {c}", "the header and one "
                               "example row: {c}", c=", ".join(d.columns)),
                     action=lambda: self._write("template")),
                Item(tr("Exportar o que tenho (.csv)", "Export what I have (.csv)"),
                     value=tr("{n} linhas", "{n} rows", n=len(d.export(self.app.db))),
                     detail=tr("grava em {p}", "saved in {p}", p=str(downloads_dir())),
                     action=lambda: self._write("export"))]
        if d.importer is not None:
            rows.append(Item(tr("Importar", "Import"), header=True))
            found = []
            for p in self._files():
                try:
                    if cs.detect(p.read_text(encoding="utf-8-sig", errors="replace")) == self.key:
                        found.append(p)
                except Exception:
                    continue
            for p in found:
                rows.append(Item(p.name, detail=str(p.parent),
                                 action=lambda q=p: self._import(q)))
            if not found:
                rows.append(Item(tr("Nenhum ficheiro deste conjunto", "No file of this set"),
                                 enabled=False,
                                 detail=tr("põe o .csv em {p}, Transferências ou Documentos",
                                           "put the .csv in {p}, Downloads or Documents",
                                           p=self.app.data_dir / "imports")))
        rows.append(Item(tr("Fechar", "Close"), button=True, primary=True, action=self.app.pop))
        self.chrome.set(d.label, d.help, "")
        self.list.set_items(rows, keep_index=True)

    def _files(self) -> list:
        import os
        from pathlib import Path
        out = []
        for f in ("imports", "~/Downloads", "~/Transferências", "~/Documents", "~/Documentos",
                  "~/Desktop"):
            base = self.app.data_dir / "imports" if f == "imports" else Path(os.path.expanduser(f))
            if base.is_dir():
                out += sorted(base.glob("*.csv"))[:60]
        return list(dict.fromkeys(out))

    def _write(self, what: str) -> None:
        try:
            path = cs.write(self.app.db, self.key, downloads_dir(), what=what)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        text = tr("Guardado em {p}", "Saved to {p}", p=path)
        self.app.message(text)
        if self.then:
            self.then(text)

    def _import(self, path) -> None:
        try:
            _key, rep = cs.import_file(self.app.db, path, self.key)
        except Exception as e:
            self.app.message(f"{t('common.error')}: {e}")
            return
        text = f"{cs.DATASETS[self.key].label}: {rep.text()}"
        self.app.message(text)
        if self.then:
            self.then(text)
        self.enter()
