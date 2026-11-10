"""O menu **Backups e Sincronização** (botão da barra do topo), com três separadores:
**Exportar**, **Repor** e **Sincronização** (GarminDB, HRV4Training, Análises,
TrainingPeaks, Upload manual, CSV, Saúde — as opções gravam-se logo, sem «Guardar»).

* **Exportar** — tudo (exportação completa) ou só as componentes que
  escolheres; o .zip fica na pasta `backups` dos teus dados, segmentado por
  componente (ver `velo.core.backup`).
* **Repor** — os backups que a Perennia encontra (na pasta `backups`, em
  Transferências, Documentos e no Ambiente de trabalho). Enter abre a janela
  da reposição: que componentes, e se substitui ou junta. Também se pode
  **arrastar um .zip para a janela** da Perennia, de qualquer ecrã.

Antes de repor guarda-se sempre um backup do que tens agora; depois, a
aplicação volta ao ecrã inicial com os dados (e as definições) repostos.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pyglet.window import key

from velo.core import backup as bk
from velo.core.i18n import tr
from velo.ui.app import Screen
from velo.ui.sport_screens import EditPopup
from velo.ui.widgets import Item, TabBar

SEARCH = ("~/Downloads", "~/Transferências", "~/Documents", "~/Documentos", "~/Desktop",
          "~/Área de Trabalho")


def backups_dir(app) -> Path:
    return Path(app.data_dir) / "backups"


def search_folders(app) -> list[Path]:
    from velo import paths
    out = [backups_dir(app)] + [Path(p) for p in paths.user_folder("backups")]
    return out + [Path(p).expanduser() for p in SEARCH]


def size_text(n: float) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{max(1, round(n / 1024))} KB"


def when_text(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(str(iso))
        return d.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(iso or "")[:16]


def count_text(n: int, one_pt: str, many_pt: str, one_en: str, many_en: str) -> str:
    return tr(one_pt, one_en) if n == 1 else tr(many_pt, many_en, n=n)


def describe(m: dict) -> str:
    """«completo · 17 componentes · 1 945 registos · 12 ficheiros»."""
    comps = m.get("components") or []
    rows = sum(int(c.get("rows") or 0) for c in comps)
    files = sum(len(c.get("files") or []) for c in comps)
    bits = [tr("completo", "full") if m.get("scope") == "completo" else tr("parcial", "partial"),
            count_text(len(comps), "1 componente", "{n} componentes", "1 component",
                       "{n} components"),
            count_text(rows, "1 registo", "{n} registos", "1 record", "{n} records")]
    if files:
        bits.append(count_text(files, "1 ficheiro", "{n} ficheiros", "1 file", "{n} files"))
    if m.get("secrets"):
        bits.append(tr("com credenciais", "with credentials"))
    return " · ".join(bits)


# ================================================================ o menu


class BackupScreen(Screen):
    TABBED = True
    TAB_KEYS = ("export", "restore", "sync")

    def __init__(self, app, tab: int = 0):
        super().__init__(app)
        from velo.ui.sync_screens import SyncPanel, SyncStore
        self.chosen = set(bk.DEFAULT_KEYS)
        self.found: list[dict] = []
        self.sync = SyncPanel(self, store=SyncStore(app.db))
        self.sync_tab = 0
        w, h = app.window.width, app.window.height
        self.sync_tabs = TabBar(self.sync.source_labels(), 48, self.content_top(h) + 6, w - 96)
        if tab:
            self.tab = tab
            if self.tabs is not None:
                self.tabs.select(tab)

    def tab_labels(self) -> list[str]:
        return [tr("Exportar", "Export"), tr("Repor", "Restore"),
                tr("Sincronização", "Synchronisation")]

    def on_tab(self) -> None:
        pass

    @property
    def view(self) -> str:
        return self.TAB_KEYS[self.tab % len(self.TAB_KEYS)]

    def enter(self) -> None:
        h = self.app.window.height
        self.list.y = self.content_top(h)
        if self.view == "export":
            self._export_items()
        elif self.view == "restore":
            self._restore_items()
        else:
            self._sync_items()

    # --------------------------------------------------------- sincronização

    def _sync_items(self) -> None:
        h = self.app.window.height
        src = self.sync.SOURCES[self.sync_tab % len(self.sync.SOURCES)][0]
        self.sync_tabs.set_labels(self.sync.source_labels())
        self.sync_tabs.select(self.sync_tab)
        self.list.y = self.content_top(h) - 52              # por baixo dos separadores
        self.chrome.set(tr("Backups e Sincronização", "Backups and Synchronisation"),
                        tr("Traz dados de fora para a Perennia · as opções gravam-se logo",
                           "Bring outside data into Perennia · options are saved at once"),
                        tr("←/→ mudar · Enter abrir · Tab separador · Esc voltar",
                           "←/→ change · Enter open · Tab tab · Esc back"))
        self.list.set_items(self.sync.items(src), keep_index=True)

    def update(self, dt: float) -> None:
        self.sync.update()

    def draw(self) -> None:
        super().draw()
        if self.view == "sync":
            self.sync_tabs.draw()

    def on_mouse(self, x: int, y: int) -> bool:
        if self.view == "sync":
            i = self.sync_tabs.hit(x, y)
            if i is not None:
                self.sync_tab = i
                self.list.index = 0
                self.enter()
                return True
        return super().on_mouse(x, y)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.sync_tabs.layout(48, self.content_top(h) + 6, w - 96)
        self.enter()

    def text_input(self, field: str, text: str) -> None:
        self.sync.text(field, text)

    def text_backspace(self, field: str) -> None:
        self.sync.text(field, None)

    def _sync_enter_row(self, item) -> bool:
        d = item.data
        from datetime import date
        if d in ("sync:start", "sync:end"):
            from velo.ui.pickers import pick_date
            field = d[5:]
            o = self.sync.opts
            o.clean()

            def put(iso: str, f=field) -> None:
                setattr(o, f, iso)
                if o.start and o.end and o.start > o.end:
                    if f == "start":
                        o.end = o.start
                    else:
                        o.start = o.end
                self.sync.save(o)
                self.enter()
            pick_date(self.app, item.label, getattr(o, field) or date.today().isoformat(), put,
                      max_day=date.today())
            return True
        if d == "sync:period" or str(d).startswith(("sync:opt:", "sync:stat:")):
            from velo.ui.pickers import open_choices
            return open_choices(self, item, lambda s=1, f=d[5:]: self.sync.adjust(f, s, False))
        return False

    # ------------------------------------------------------------ exportar

    @property
    def all_on(self) -> bool:
        return set(bk.DEFAULT_KEYS) <= self.chosen

    def _export_items(self) -> None:
        a = self.app
        info = {s["key"]: s for s in bk.summary(a.db, a.data_dir)}
        items = [Item(tr("Tudo — exportação completa", "Everything — full export"),
                      value="✓" if self.all_on else "—",
                      detail=tr("todas as componentes, cada uma na sua pasta dentro do .zip",
                                "every component, each in its own folder inside the .zip"),
                      action=self._toggle_all, data=("all",)),
                 Item(tr("Componentes", "Components"), header=True)]
        for c in bk.COMPONENTS:
            if c.sensitive:
                continue
            s = info[c.key]
            bits = [c.description,
                    count_text(s["rows"], "1 registo", "{n} registos", "1 record",
                               "{n} records")]
            if s["files"]:
                bits.append(count_text(s["files"], "1 ficheiro", "{n} ficheiros", "1 file",
                                       "{n} files") + f" ({size_text(s['bytes'])})")
            items.append(Item(c.name, value="✓" if c.key in self.chosen else "—",
                              detail=" · ".join(bits),
                              action=lambda k=c.key: self._toggle(k), data=("comp", c.key)))
        sec = bk.BY_KEY["ligacoes"]
        items += [Item(sec.name, value=tr("Sim", "Yes") if "ligacoes" in self.chosen
                       else tr("Não", "No"), detail=sec.description,
                       action=lambda: self._toggle("ligacoes"), data=("comp", "ligacoes")),
                  Item(tr("Exportar", "Export"), button=True, primary=True,
                       enabled=bool(self.chosen), action=self._export)]
        self.chrome.set(tr("Backups e reposição", "Backups and restore"),
                        tr("Escolhe o que guardar: tudo, ou só algumas componentes · o .zip "
                           "fica em {p}", "Pick what to keep: everything, or just some "
                           "components · the .zip goes to {p}", p=backups_dir(a)),
                        tr("Tab separador · Enter ou ←/→ marca · Ctrl+S exportar · Esc voltar",
                           "Tab next tab · Enter or ←/→ ticks · Ctrl+S export · Esc back"))
        self.list.set_items(items, keep_index=True)

    def _toggle_all(self) -> None:
        if self.all_on:
            self.chosen -= set(bk.DEFAULT_KEYS)
        else:
            self.chosen |= set(bk.DEFAULT_KEYS)
        self.enter()

    def _toggle(self, k: str) -> None:
        self.chosen ^= {k}
        self.enter()

    def _export(self) -> None:
        a = self.app
        keys = [k for k in bk.BY_KEY if k in self.chosen]
        if not keys:
            return
        try:
            m = bk.export(a.db, a.data_dir, backups_dir(a), keys,
                          include_secrets="ligacoes" in keys)
        except Exception as e:
            a.notify(tr("Não foi possível fazer o backup", "Could not make the backup"), str(e))
            return
        a.notify(tr("Backup feito", "Backup done"),
                 f"{Path(m['path']).name} · {size_text(m['bytes'])} · {describe(m)} · "
                 + tr("Está em {p}", "It is in {p}", p=Path(m["path"]).parent))

    # --------------------------------------------------------------- repor

    def _restore_items(self) -> None:
        a = self.app
        self.found = bk.find(search_folders(a))
        items = [Item(tr("Repor um backup", "Restore a backup"), header=True)]
        for m in self.found:
            name = Path(m["path"]).name
            extra = tr(" · cópia automática antes de repor", " · automatic copy before a "
                       "restore") if name.startswith("perennia-antes-de-repor") else ""
            items.append(Item(name, value=f"{when_text(m.get('created_at'))} · "
                                          f"{size_text(m['bytes'])}",
                              detail=describe(m) + f" · {Path(m['path']).parent}" + extra,
                              action=lambda mm=m: self.app.push(RestorePopup(self.app, mm)),
                              data=("file", m["path"])))
        if not self.found:
            items.append(Item(tr("Ainda não há backups", "No backups yet"),
                              detail=tr("faz um no separador Exportar, ou traz um .zip",
                                        "make one in the Export tab, or bring a .zip"),
                              enabled=False))
        items.append(Item(tr("Trazer um backup (upload)", "Bring a backup (upload)"),
                          value=tr("arrasta o .zip", "drag the .zip"),
                          detail=tr("arrasta o .zip para a janela da Perennia, ou põe-no em "
                                    "Transferências, Documentos ou na pasta backups",
                                    "drag the .zip onto the Perennia window, or put it in "
                                    "Downloads, Documents or the backups folder"),
                          enabled=False))
        self.chrome.set(tr("Backups e reposição", "Backups and restore"),
                        tr("Escolhe o backup a repor · antes, guardo o que tens agora",
                           "Pick the backup to restore · first I keep what you have now"),
                        tr("Tab separador · Enter abrir · Del apagar o ficheiro · Esc voltar",
                           "Tab next tab · Enter open · Del delete the file · Esc back"))
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if self.view == "sync" and item is not None and isinstance(item.data, str) and \
                item.data.startswith("sync:"):
            if symbol in (key.LEFT, key.RIGHT):
                self.sync.adjust(item.data[5:], 1 if symbol == key.RIGHT else -1,
                                 bool(modifiers & key.MOD_SHIFT))
                return True
            if symbol in (key.ENTER, key.RETURN) and item.action is None and \
                    self._sync_enter_row(item):
                return True
        data = item.data if item is not None and isinstance(item.data, tuple) else ()
        if symbol in (key.LEFT, key.RIGHT) and data and data[0] in ("all", "comp"):
            item.action()
            return True
        if symbol == key.DELETE and data and data[0] == "file":
            path = Path(data[1])

            def gone() -> None:
                try:
                    path.unlink()
                except OSError as e:
                    self.app.message(str(e))
                self.enter()
            self.app.confirm(tr("Apagar o ficheiro «{n}»?", "Delete the file «{n}»?",
                                n=path.name),
                             tr("O backup sai do disco. Os teus dados na Perennia ficam como "
                                "estão.", "The backup leaves the disk. Your data in Perennia "
                                "stays as it is."), gone, yes=tr("Apagar", "Delete"))
            return True
        return super().on_key(symbol, modifiers)


# ================================================================ repor


class RestorePopup(EditPopup):
    """Repor um backup: que componentes e como (substituir ou juntar)."""

    W = 940
    MAX_H = 760

    def __init__(self, app, manifest: dict):
        self.m = manifest
        self.keys = {c["key"] for c in manifest.get("components") or [] if c["key"] in bk.BY_KEY}
        self.mode = "replace"
        super().__init__(app)

    def title(self) -> str:
        return tr("Repor o backup", "Restore the backup")

    def subtitle(self) -> str:
        return f"{Path(self.m['path']).name} · {when_text(self.m.get('created_at'))} · " \
               f"Perennia {self.m.get('version', '?')}"

    def state(self):
        return ""

    def has_unsaved(self) -> bool:
        return False

    def rows(self) -> list[Item]:
        rows = []
        for c in self.m.get("components") or []:
            comp = bk.BY_KEY.get(c["key"])
            if comp is None:
                continue
            files = len(c.get("files") or [])
            detail = count_text(int(c.get("rows") or 0), "1 registo", "{n} registos",
                                "1 record", "{n} records")
            if files:
                detail += " · " + count_text(files, "1 ficheiro", "{n} ficheiros", "1 file",
                                             "{n} files")
            rows.append(Item(comp.name, value="✓" if c["key"] in self.keys else "—",
                             detail=detail, data="cyc:" + c["key"]))
        rows.append(Item(tr("Como repor", "How to restore"),
                         value=tr("Substituir", "Replace") if self.mode == "replace"
                         else tr("Juntar", "Merge"),
                         detail=tr("cópia exata do backup nas componentes marcadas",
                                   "exact copy of the backup in the ticked components")
                         if self.mode == "replace" else
                         tr("acrescenta o que falta; o que já tens fica",
                            "adds what is missing; what you have stays"),
                         data="cyc:mode"))
        rows.append(Item(tr("Segurança", "Safety"), value=tr("backup automático", "auto backup"),
                         detail=tr("antes de repor, o que tens agora fica em backups/",
                                   "before restoring, what you have now goes to backups/"),
                         enabled=False))
        return rows

    def buttons(self) -> list[Item]:
        return [Item(tr("Cancelar", "Cancel"), action=self.close, button=True),
                Item(tr("Repor", "Restore"), action=self._ask, button=True, primary=True,
                     enabled=bool(self.keys))]

    def cycle(self, field: str, step: int) -> None:
        if field == "mode":
            self.mode = "merge" if self.mode == "replace" else "replace"
        elif field in bk.BY_KEY:
            self.keys ^= {field}

    def on_key(self, symbol: int, modifiers: int) -> bool:
        cyc = self._field("cyc:")
        if cyc is not None and symbol in (key.ENTER, key.RETURN, key.SPACE):
            self.cycle(cyc, 1)                  # aqui o Enter também marca
            self.enter()
            return True
        return super().on_key(symbol, modifiers)

    def cancel(self) -> None:
        self.close()

    def on_save(self) -> bool:
        self._ask()
        return True

    def _ask(self) -> None:
        a = self.app
        if not self.keys:
            return
        if a.in_session:
            a.message(tr("Termina a sessão antes de repor um backup",
                         "Finish the session before restoring a backup"))
            return
        n = len(self.keys)
        what = count_text(n, "1 componente", "{n} componentes", "1 component", "{n} components")
        sub = (tr("Os dados de {w} passam a ser os do backup. O que tens agora fica guardado "
                  "antes, na pasta backups.",
                  "The data of {w} become the backup's. What you have now is kept first, in "
                  "the backups folder.", w=what) if self.mode == "replace" else
               tr("Acrescento o que falta em {w}. O que tens agora fica, e guardo uma cópia "
                  "antes, na pasta backups.",
                  "I add what is missing in {w}. What you have stays, and I keep a copy "
                  "first, in the backups folder.", w=what))
        a.confirm(tr("Repor o backup?", "Restore the backup?"), sub, self._run,
                  yes=tr("Repor", "Restore"))

    def _run(self) -> None:
        a = self.app
        keys = [k for k in bk.BY_KEY if k in self.keys]
        try:
            rep = bk.restore(a.db, a.data_dir, self.m["path"], keys, self.mode)
        except Exception as e:
            a.notify(tr("Não foi possível repor", "Could not restore"),
                     tr("Nada mudou: {e}", "Nothing changed: {e}", e=e))
            return
        a.after_restore()
        sub = count_text(rep["rows"], "1 registo", "{n} registos", "1 record", "{n} records")
        if rep["files"]:
            sub += " · " + count_text(rep["files"], "1 ficheiro", "{n} ficheiros", "1 file",
                                      "{n} files")
        if rep["fixed"]:
            sub += " · " + tr("{n} referências sem destino arrumadas",
                              "{n} dangling references tidied", n=rep["fixed"])
        if rep["safety"]:
            sub += " · " + tr("O que tinhas antes está em {p}", "What you had is in {p}",
                             p=Path(rep["safety"]).name)
        a.notify(tr("Backup reposto", "Backup restored"), sub)


def open_dropped(app, paths: list) -> bool:
    """Um ficheiro arrastado para a janela: se for um backup, abre a reposição."""
    for p in paths or []:
        path = Path(str(p))
        if path.suffix.lower() != ".zip":
            continue
        try:
            m = bk.inspect(path)
        except bk.BackupError as e:
            app.message(f"{path.name}: {e}")
            return True
        if app.in_session:
            app.message(tr("Termina a sessão antes de repor um backup",
                           "Finish the session before restoring a backup"))
            return True
        app.push(BackupScreen(app, tab=1))
        app.push(RestorePopup(app, m))
        return True
    return False
