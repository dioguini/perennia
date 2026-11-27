"""O menu **Segmentos** do ecrã inicial: os segmentos da Perennia e os do
Strava, num só sítio.

* **Visão geral** — todos os segmentos de todas as rotas, com o melhor
  tempo; **Perennia** e **Strava** — só os de cada fonte. À direita, o
  perfil da rota com o segmento escolhido.
* **Biblioteca** — os segmentos do Strava guardados neste computador (importados por ID, pelos
  favoritos ⭐ ou pela pesquisa de uma rota): ligam-se às rotas sem internet.
* **+ Novo segmento** — escolhe-se uma rota do menu Rotas, o km de início e
  o km de fim (ou a distância). A inclinação média e a subida saem do perfil.
* Enter abre o segmento: os tempos feitos nele (ciclismo e corrida) e, nos
  da Perennia, editar e apagar.

Os segmentos de uma rota entram sozinhos nas sessões feitas nela: ao passar
o km de início, o segmento começa; no km de fim, regista-se o tempo.
"""
from __future__ import annotations

import pyglet
from pyglet.window import key

from perennia.core import routes as routes_mod
from perennia.core import segments as seg_mod
from perennia.core import strava_library as lib_mod
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.gfx.compat import label as make_label
from perennia.ui.app import Screen
from perennia.ui.route_screens import PERENNIA_C, ProfileChart, route_bands, segment_item
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import ACCENT, TEXT, Item, fit_text


def delete_segment(app, seg_id: int, name: str, then=None) -> None:
    def gone() -> None:
        seg_mod.delete_perennia(app.db, seg_id)
        if then is not None:
            then()
    app.confirm(tr("Apagar o segmento «{n}»?", "Delete the segment «{n}»?", n=name),
                tr("Os tempos feitos nele vão com ele. Não dá para desfazer.",
                   "The times done on it go with it. This cannot be undone."),
                gone, yes=tr("Apagar", "Delete"))


def delete_library(app, seg_id: int, name: str, then=None) -> None:
    def gone() -> None:
        lib_mod.delete(app.db, seg_id)
        if then is not None:
            then()
    app.confirm(tr("Tirar «{n}» da biblioteca?", "Remove “{n}” from the library?", n=name),
                tr("Deixa de se ligar às rotas e perdem-se os esforços importados do Strava. Os "
                   "teus tempos feitos na Perennia ficam. Podes importá-lo outra vez.",
                   "It stops linking to routes and the efforts imported from Strava are lost. "
                   "The times you did in Perennia stay. You can import it again."),
                gone, yes=tr("Tirar", "Remove"))


# ================================================================ a lista


class SegmentsScreen(Screen):
    TABBED = True
    KEY_SCOPE = "routes"
    TAB_KEYS = ("all", "perennia", "strava", "library")

    def __init__(self, app):
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self.chart = ProfileChart(self.batch)
        self.head = make_label("", font_size=15, bold=True, color=ACCENT, anchor_y="top",
                               batch=self.batch)
        self.info = [make_label("", font_size=12, color=TEXT, anchor_y="top", batch=self.batch)
                     for _ in range(3)]
        self._shown: object = ()

    def tab_labels(self) -> list[str]:
        return [tr("Visão geral", "Overview"), "Perennia", "Strava",
                tr("Biblioteca", "Library")]

    def _list_width(self, w: int) -> int:
        return int((w - 96) * 0.5)

    def enter(self) -> None:
        a = self.app
        which = self.TAB_KEYS[self.tab % len(self.TAB_KEYS)]
        if which == "library":
            self._library_tab()
            return
        segs = seg_mod.overview(a.db)
        if which != "all":
            segs = [s for s in segs if s.source == which]
        items = [Item(tr("+ Novo segmento", "+ New segment"), top=True,
                      action=lambda: a.push(SegmentEditor(a, None))),
                 Item(tr("Importar do Strava", "Import from Strava"), top=True,
                      action=self._import)]
        last = None
        for s in segs:
            if s.route_id != last:
                r = a.db.route(s.route_id)
                items.append(Item(r["name"] if r else "—", header=True))
                last = s.route_id
            items.append(segment_item(a, s, show_route=False))
        if not segs:
            items.append(Item(
                tr("Ainda não há segmentos", "No segments yet"),
                detail=(tr("cria um em cima, à direita, numa rota do menu Rotas",
                           "create one top right, on a route from the Routes menu")
                        if which != "strava" else
                        tr("procura-os no Strava na ficha de uma rota (menu Rotas), ou "
                           "importa-os por ID em «Importar do Strava»",
                           "look them up on Strava from a route (Routes menu), or import "
                           "them by ID with “Import from Strava”")),
                enabled=False))
        n_p = sum(1 for s in seg_mod.overview(a.db) if s.source == "perennia")
        n_all = len(seg_mod.overview(a.db))
        self.chrome.set(tr("Segmentos", "Segments"),
                        tr("{p} da Perennia · {s} do Strava · melhores tempos à direita",
                           "{p} from Perennia · {s} from Strava · best times on the right",
                           p=n_p, s=n_all - n_p),
                        tr("Tab separador · Enter abrir · Del apagar · Esc voltar",
                           "Tab next tab · Enter open · Del delete · Esc back"))
        self.list.set_items(items, keep_index=True)
        self._shown = ()

    def _import(self) -> None:
        from perennia.ui.connect_screens import StravaImportScreen
        self.app.push(StravaImportScreen(self.app))

    def _link_all(self) -> None:
        r = lib_mod.link_all(self.app.db)
        self.app.message(tr("{n} ligações a rotas ({r} rotas vistas)",
                            "{n} links to routes ({r} routes checked)", n=r["linked"],
                            r=r["routes"]))
        self.enter()

    def _library_tab(self) -> None:
        a = self.app
        lib = lib_mod.library(a.db)
        items = [Item(tr("Importar do Strava", "Import from Strava"), top=True, primary=True,
                      action=self._import),
                 Item(tr("Ligar às minhas rotas", "Link to my routes"), top=True,
                      action=self._link_all)]
        for r in lib:
            bits = []
            if r["distance_m"]:
                bits.append(f"{r['distance_m'] / 1000:.2f} km")
            if r["avg_grade"] is not None:
                bits.append(f"{r['avg_grade']:.1f} %")
            if r["city"] or r["country"]:
                bits.append(", ".join(x for x in (r["city"], r["country"]) if x))
            bits.append(tr("{n} esforços", "{n} efforts", n=r["n_efforts"]) if r["n_efforts"]
                        else tr("sem esforços importados", "no efforts imported"))
            bits.append(tr("ligado a {n} rotas", "linked to {n} routes", n=r["n_routes"])
                        if r["n_routes"] else tr("sem rota", "no route"))
            items.append(Item(("⭐ " if r["starred"] else "") + r["name"],
                              value=hms(r["pr_s"]) if r["pr_s"] else "—",
                              detail=" · ".join(bits), data=("lib", r["segment_id"]),
                              action=lambda sid=r["segment_id"]: a.push(
                                  LibrarySegmentDetail(a, sid))))
        if not lib:
            items.append(Item(
                tr("A biblioteca está vazia", "The library is empty"),
                detail=tr("«Importar do Strava» (em cima, à direita): por ID, pelos favoritos, ou "
                          "«Atualizar do Strava» na ficha de uma rota",
                          "“Import from Strava” (top right): by ID, from your favourites, or "
                          "“Refresh from Strava” on a route's page"), enabled=False))
        self.chrome.set(tr("Segmentos", "Segments"),
                        tr("{n} na biblioteca do Strava · funcionam sem internet",
                           "{n} in the Strava library · they work offline", n=len(lib)),
                        tr("Tab separador · Enter abrir · Del tirar da biblioteca · Esc voltar",
                           "Tab next tab · Enter open · Del remove from the library · Esc back"))
        self.list.set_items(items, keep_index=True)
        self._shown = ()

    def on_tab(self) -> None:
        self._shown = ()

    def _side(self) -> None:
        item = self.list.selected
        data = item.data if item is not None and isinstance(item.data, tuple) and \
            item.data[0] == "segment" else None
        key_ = (data, id(self.list.items))
        if key_ == self._shown:
            return
        self._shown = key_
        w, h = self.app.window.width, self.app.window.height
        x = 48 + self._list_width(w) + 30
        cw = w - 48 - x
        top = self.content_top(h)
        rid = data[2] if data else None
        row = self.app.db.route(rid) if rid else None
        self.head.x, self.head.y = x, top + 4
        self.head.text = fit_text(row["name"], cw, 15, bold=True) if row else ""
        ch = max(150.0, min(300.0, (top - 120) * 0.55))
        self.chart.set(routes_mod.profile(self.app.db, rid) if rid else [], x, top - 30 - ch,
                       cw, ch, route_bands(self.app.db, rid, data[1]) if rid else [],
                       empty=tr("Escolhe um segmento para o ver na rota",
                                "Pick a segment to see it on the route"))
        lines = []
        if data:
            src, sid = data[1].split(":")
            seg = next((s for s in seg_mod.load(self.app.db, rid) if s.key == data[1]), None)
            if seg is not None:
                ef = seg_mod.efforts(self.app.db, src, int(sid))
                lines = [f"{seg.name} · {seg.length_m / 1000:.2f} km"
                         + (f" · {seg.avg_grade:.1f} %" if seg.avg_grade is not None else ""),
                         tr("Melhor: {b} · {n}", "Best: {b} · {n}",
                            b=hms(ef[0]["elapsed_s"]) if ef else "—",
                            n=tr("1 vez", "once") if len(ef) == 1 else
                            tr("{n} vezes", "{n} times", n=len(ef))),
                         (tr("PR no Strava: {p}", "Strava PR: {p}", p=hms(seg.pr_s))
                          if seg.pr_s else "")]
        for k, lab in enumerate(self.info):
            lab.text = fit_text(lines[k], cw, 12) if k < len(lines) else ""
            lab.x, lab.y = x, top - 44 - ch - k * 22

    def draw(self) -> None:
        super().draw()
        self._side()
        self.batch.draw()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._shown = ()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.DELETE and item is not None and isinstance(item.data, tuple) and \
                item.data[0] == "lib":
            delete_library(self.app, item.data[1], item.label.lstrip("⭐ "), then=self.enter)
            return True
        if symbol == key.DELETE and item is not None and isinstance(item.data, tuple) and \
                item.data[0] == "segment":
            if item.data[1].startswith("perennia:"):
                delete_segment(self.app, int(item.data[1].split(":")[1]), item.label,
                               then=self.enter)
            else:
                self.app.message(tr("Os segmentos do Strava apagam-se com a rota",
                                    "Strava segments go away with the route"))
            return True
        return super().on_key(symbol, modifiers)


# ================================================================ editar


class SegmentEditor(EditPopup):
    """Um segmento da Perennia: a rota, o nome, o km de início e o km de fim
    (ou a distância). O perfil por baixo mostra o segmento na rota."""

    W = 900
    MIN_H, MAX_H = 560, 720
    CHART_H = 150

    def __init__(self, app, seg_id: int | None, route_id: str | None = None):
        self.seg_id = seg_id
        routes = [r["id"] for r in app.db.routes()]
        self.v = {"route": route_id or (routes[0] if routes else None), "name": "",
                  "start_km": 0.0, "end_km": 1.0, "by": "end"}
        if seg_id:
            s = next((x for x in seg_mod.perennia_segments(app.db) if x.id == seg_id), None)
            if s is not None:
                self.v.update(route=s.route_id, name=s.name, start_km=s.start_m / 1000,
                              end_km=s.end_m / 1000)
        elif self.v["route"]:
            r = app.db.route(self.v["route"])
            if r is not None:
                self.v["end_km"] = round(min(1.0, r["distance_m"] / 1000), 1)
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self.chart = ProfileChart(self.batch)

    def title(self) -> str:
        return tr("Editar segmento", "Edit segment") if self.seg_id else \
            tr("Novo segmento", "New segment")

    def subtitle(self) -> str:
        return tr("Numa rota do menu Rotas · o km de início e o de fim (ou a distância)",
                  "On a route from the Routes menu · the start km and the end km "
                  "(or the distance)")

    def _route(self):
        return self.app.db.route(self.v["route"]) if self.v["route"] else None

    def _total_km(self) -> float:
        r = self._route()
        return (r["distance_m"] / 1000) if r is not None else 0.0

    def rows(self) -> list[Item]:
        r = self._route()
        if r is None:
            return [Item(tr("Ainda não tens rotas", "No routes yet"),
                         detail=tr("carrega primeiro um .gpx no menu Rotas",
                                   "load a .gpx in the Routes menu first"), enabled=False)]
        a, z = self.v["start_km"], self.v["end_km"]
        st = seg_mod.route_stats(self.app.db.route_points(r["id"]), a * 1000, z * 1000)
        by_end = self.v["by"] == "end"
        rows = [Item(tr("Rota", "Route"), value=r["name"],
                     detail=tr("←/→ muda de rota · {k:.1f} km", "←/→ changes route · {k:.1f} km",
                               k=self._total_km()), data="cyc:route"),
                Item(tr("Nome", "Name"), value=self.v["name"] or "—",
                     detail=tr("escreve o nome", "type the name"), data="text:name"),
                Item(tr("Início", "Start"), value=f"km {a:.2f}",
                     detail=tr("←/→ ±0,1 km · Shift ±1 km · ou escreve",
                               "←/→ ±0.1 km · Shift ±1 km · or type"), data="num:start"),
                Item(tr("Fim por", "End by"),
                     value=tr("km de destino", "end km") if by_end else
                     tr("distância", "distance"), data="cyc:by"),
                Item(tr("Fim", "End") if by_end else tr("Distância", "Distance"),
                     value=f"km {z:.2f}" if by_end else f"{z - a:.2f} km",
                     detail=tr("←/→ ±0,1 km · Shift ±1 km · ou escreve",
                               "←/→ ±0.1 km · Shift ±1 km · or type"), data="num:end"),
                Item(tr("No perfil", "On the profile"),
                     value=f"{(z - a):.2f} km · {st['grade']:.1f} % · ↑ {st['gain_m']:.0f} m",
                     detail=tr("inclinação média e subida, do .gpx",
                               "average grade and gain, from the .gpx"), enabled=False)]
        return rows

    def state(self):
        return repr(sorted(self.v.items()))

    def cycle(self, field: str, step: int) -> None:
        if field == "route":
            ids = [r["id"] for r in self.app.db.routes()]
            if ids:
                i = ids.index(self.v["route"]) if self.v["route"] in ids else 0
                self.v["route"] = ids[(i + step) % len(ids)]
                self._clamp()
        elif field == "by":
            self.v["by"] = "dist" if self.v["by"] == "end" else "end"

    def _clamp(self) -> None:
        total = self._total_km()
        a = max(0.0, min(total - 0.05, round(self.v["start_km"], 2)))
        z = max(a + 0.05, min(total, round(self.v["end_km"], 2)))
        self.v["start_km"], self.v["end_km"] = a, z

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        d = steps * (1.0 if big else 0.1)
        if field == "start":
            length = self.v["end_km"] - self.v["start_km"]
            self.v["start_km"] += d
            if self.v["by"] == "dist":            # a distância mantém-se
                self.v["end_km"] = self.v["start_km"] + length
        else:
            self.v["end_km"] += d
        self._clamp()

    def num_set(self, field: str, value) -> None:
        if value is None:
            return
        if field == "start":
            length = self.v["end_km"] - self.v["start_km"]
            self.v["start_km"] = float(value)
            if self.v["by"] == "dist":
                self.v["end_km"] = self.v["start_km"] + length
        elif self.v["by"] == "end":
            self.v["end_km"] = float(value)
        else:
            self.v["end_km"] = self.v["start_km"] + float(value)
        self._clamp()

    def text_input(self, field: str, text: str) -> None:
        if field == "name":
            self.v["name"] = (self.v["name"] + text)[:60]
            self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "name":
            self.v["name"] = self.v["name"][:-1]
            self.enter()

    def commit(self) -> bool:
        if not self.v["route"]:
            self.app.message(tr("Carrega primeiro uma rota no menu Rotas",
                                "Load a route in the Routes menu first"))
            return False
        try:
            self.seg_id = seg_mod.save_perennia(self.app.db, self.seg_id, self.v["route"],
                                                self.v["name"], self.v["start_km"] * 1000,
                                                self.v["end_km"] * 1000)
        except ValueError as e:
            self.app.message(str(e))
            return False
        return True

    def saved_message(self) -> str:
        return tr("Segmento guardado", "Segment saved")

    def enter(self) -> None:
        super().enter()
        # espaço para o perfil por baixo das linhas
        rows = len(self.rows())
        h = max(self.MIN_H, min(self.MAX_H, 92 + 96 + rows * 38 + self.CHART_H + 30))
        self.set_popup_size(self.W, h)
        self._chart()

    def _chart(self) -> None:
        p = self.popup
        rid = self.v["route"]
        band = [(self.v["start_km"] * 1000, self.v["end_km"] * 1000, PERENNIA_C,
                 self.v["name"] or tr("este segmento", "this segment"), True)]
        self.chart.set(routes_mod.profile(self.app.db, rid) if rid else [], p.x + 28,
                       p.y + 66, p.w - 56, self.CHART_H, band)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._chart()

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


# ================================================================ um segmento


class SegmentDetail(Screen):
    """Um segmento: onde fica, os tempos feitos nele (o melhor primeiro) e,
    nos da Perennia, editar e apagar."""

    KEY_SCOPE = "routes"

    def __init__(self, app, source: str, seg_id: int):
        super().__init__(app)
        self.source = source
        self.seg_id = int(seg_id)

    def _segment(self):
        for s in seg_mod.overview(self.app.db):
            if s.source == self.source and s.id == self.seg_id:
                return s
        return None

    def enter(self) -> None:
        a = self.app
        s = self._segment()
        if s is None:
            a.pop()
            return
        r = a.db.route(s.route_id)
        ef = seg_mod.efforts(a.db, self.source, self.seg_id)
        from perennia.core import sports as sp
        items = []
        if self.source == "perennia":
            items.append(Item(tr("Editar", "Edit"), top=True,
                              action=lambda: a.push(SegmentEditor(a, self.seg_id))))
        items += [Item(tr("Segmento", "Segment"), header=True),
                  Item(tr("Rota", "Route"), value=r["name"] if r else "—",
                       detail=f"km {s.start_m / 1000:.2f}–{s.end_m / 1000:.2f}",
                       action=(lambda: self._open_route(s.route_id)) if r else None),
                  Item(tr("Distância", "Distance"), value=f"{s.length_m / 1000:.2f} km",
                       detail=(f"{s.avg_grade:.1f} %" if s.avg_grade is not None else "")
                       + (f" · ↑ {s.gain_m:.0f} m" if s.gain_m else ""), enabled=False),
                  Item(tr("Fonte", "Source"),
                       value="Perennia" if self.source == "perennia" else "Strava",
                       detail=(tr("PR no Strava {p}", "Strava PR {p}", p=hms(s.pr_s))
                               if s.pr_s else ""), enabled=False),
                  Item(tr("Tempos", "Times"), header=True)]
        for i, e in enumerate(ef[:40], start=1):
            kind, sid = e.get("kind"), e.get("session_id")
            items.append(Item(f"{i}.  {hms(e['elapsed_s'])}",
                              value=sp.name(e.get("sport") or "cycling"),
                              detail=str(e.get("created_at") or "")[:16].replace("T", " "),
                              action=(lambda k=kind, x=sid: self._open_session(k, x))
                              if sid else None))
        if not ef:
            items.append(Item(tr("Ainda sem tempos", "No times yet"),
                              detail=tr("faz uma sessão nesta rota (ciclismo ou corrida)",
                                        "do a session on this route (cycling or running)"),
                              enabled=False))
        if self.source == "perennia":
            items.append(Item(tr("Apagar", "Delete"), button=True,
                              action=lambda: delete_segment(a, self.seg_id, s.name,
                                                            then=lambda: a.pop(force=True))))
        self.chrome.set(s.name, tr("{n} tempos · melhor {b}", "{n} times · best {b}",
                                   n=len(ef), b=hms(ef[0]["elapsed_s"]) if ef else "—"),
                        self.footer())
        self.list.set_items(items, keep_index=True)

    def _open_route(self, rid: str) -> None:
        from perennia.ui.route_screens import RouteOverview
        self.app.push(RouteOverview(self.app, rid))

    def _open_session(self, kind: str, sid: str) -> None:
        from perennia.ui.session_analysis import SessionAnalysis
        self.app.push(SessionAnalysis(self.app, kind, sid))


# ================================================================ um da biblioteca


class LibrarySegmentDetail(Screen):
    """Um segmento da biblioteca do Strava: os números, os teus esforços importados (o melhor
    primeiro), as rotas a que está ligado e as ações (atualizar, ligar, tirar)."""

    AGENT = False
    KEY_SCOPE = "routes"

    def __init__(self, app, segment_id: int, http=None):
        super().__init__(app)
        self.segment_id = int(segment_id)
        self.http = http
        self.job = None

    def enter(self) -> None:
        a = self.app
        r = lib_mod.get(a.db, self.segment_id)
        if r is None:
            a.pop()
            return
        ef = lib_mod.library_efforts(a.db, self.segment_id)
        routes = a.db.conn.execute(
            "SELECT s.route_id, s.start_m, s.end_m FROM strava_segments s WHERE s.segment_id = ?",
            (self.segment_id,)).fetchall()
        from perennia.ui.connect_screens import strava_busy
        busy = strava_busy(a)
        items = [Item(tr("Atualizar do Strava", "Refresh from Strava"), top=True,
                       value=tr("a atualizar…", "refreshing…") if busy else "",
                       enabled=not busy, action=self._refresh),
                 Item(tr("Ligar às minhas rotas", "Link to my routes"), top=True,
                      action=self._link),
                 Item(tr("Segmento", "Segment"), header=True),
                 Item(tr("Distância", "Distance"),
                      value=f"{(r['distance_m'] or 0) / 1000:.2f} km",
                      detail=" · ".join(x for x in (
                          f"{r['avg_grade']:.1f} %" if r["avg_grade"] is not None else "",
                          f"↑ {r['elev_gain_m']:.0f} m" if r["elev_gain_m"] else "",
                          tr("máx. {g:.0f} %", "max {g:.0f} %", g=r["max_grade"])
                          if r["max_grade"] else "",
                          ", ".join(x for x in (r["city"], r["country"]) if x)) if x),
                      enabled=False),
                 Item(tr("O meu PR no Strava", "My Strava PR"),
                      value=hms(r["pr_s"]) if r["pr_s"] else "—",
                      detail=" · ".join(x for x in (
                          r["pr_date"] or "",
                          tr("{n} esforços no Strava", "{n} efforts on Strava",
                             n=r["effort_count"]) if r["effort_count"] else "",
                          f"KOM {r['kom']}" if r["kom"] else "") if x), enabled=False),
                 Item(tr("Importado", "Imported"), value=str(r["fetched_at"] or "")[:16]
                      .replace("T", " "),
                      detail=tr("ID {i} · origem: {o}", "ID {i} · source: {o}",
                                i=r["segment_id"], o=r["origin"] or "—"), enabled=False),
                 Item(tr("Rotas ligadas", "Linked routes"), header=True)]
        for lk in routes:
            row = a.db.route(lk["route_id"])
            items.append(Item(row["name"] if row else "—",
                              detail=f"km {lk['start_m'] / 1000:.2f}–{lk['end_m'] / 1000:.2f}",
                              action=(lambda rid=lk["route_id"]: self._open_route(rid))
                              if row else None))
        if not routes:
            items.append(Item(tr("Nenhuma rota percorre este segmento",
                                 "No route follows this segment"),
                              detail=tr("importa um .gpx que passe por ele, ou «Ligar às minhas "
                                        "rotas»", "import a .gpx that goes through it, or "
                                        "“Link to my routes”"), enabled=False))
        items.append(Item(tr("Os meus esforços importados", "My imported efforts"), header=True))
        for i, e in enumerate(ef[:60], start=1):
            items.append(Item(f"{i}.  {hms(e['elapsed_s'])}",
                              value=(f"{e['avg_watts']:.0f} W" if e["avg_watts"] else ""),
                              detail=str(e["start_date"] or "")[:10], enabled=False))
        if not ef:
            items.append(Item(tr("Sem esforços importados", "No efforts imported"),
                              detail=tr("precisam de subscrição Strava; «Atualizar do Strava» "
                                        "tenta outra vez", "they need a Strava subscription; "
                                        "“Refresh from Strava” tries again"), enabled=False))
        items.append(Item(tr("Tirar da biblioteca", "Remove from the library"), button=True,
                          action=lambda: delete_library(a, self.segment_id, r["name"],
                                                        then=lambda: a.pop(force=True))))
        self.chrome.set(r["name"], tr("{n} esforços importados · melhor {b}",
                                      "{n} imported efforts · best {b}", n=len(ef),
                                      b=hms(ef[0]["elapsed_s"]) if ef else "—"), self.footer())
        self.list.set_items(items, keep_index=True)

    def _link(self) -> None:
        r = lib_mod.link_all(self.app.db)
        self.app.message(tr("{n} ligações a rotas", "{n} links to routes", n=r["linked"]))
        self.enter()

    def _refresh(self) -> None:
        from perennia.io import strava as strava_mod
        from perennia.ui.connect_screens import strava_busy, strava_task
        client = strava_mod.StravaClient(self.app.db, http=self.http)
        if not client.connected:
            self.app.message(tr("Liga primeiro o Strava em Definições → Strava",
                                "Connect Strava first in Settings → Strava"))
            return
        if strava_busy(self.app):
            self.app.message(self.app.task_busy_text("strava"))
            return
        sid = self.segment_id

        def fn(db, c, _log):
            rep = lib_mod.import_ids(db, c, [sid])
            return rep.text(), rep

        def then(_ok, _text, _rep) -> None:
            if self in getattr(self.app, "stack", []):
                self.enter()
        task = strava_task(self.app, tr("Strava: atualizar o segmento",
                                        "Strava: refresh the segment"), client.http, fn, then)
        self.job = task.job if task is not None else None
        self.enter()

    def update(self, dt: float) -> None:
        if hasattr(self.app, "poll_task"):
            self.app.poll_task()

    def _open_route(self, rid: str) -> None:
        from perennia.ui.route_screens import RouteOverview
        self.app.push(RouteOverview(self.app, rid))

    def _open_session(self, kind: str, sid: str) -> None:
        from perennia.ui.session_analysis import SessionAnalysis
        self.app.push(SessionAnalysis(self.app, kind, sid))


# ================================================================ um da biblioteca


class LibrarySegmentDetail(Screen):
    """Um segmento da biblioteca do Strava: os números, os teus esforços importados (o melhor
    primeiro), as rotas a que está ligado e as ações (atualizar, ligar, tirar)."""

    AGENT = False
    KEY_SCOPE = "routes"

    def __init__(self, app, segment_id: int, http=None):
        super().__init__(app)
        self.segment_id = int(segment_id)
        self.http = http
        self.job = None

    def enter(self) -> None:
        a = self.app
        r = lib_mod.get(a.db, self.segment_id)
        if r is None:
            a.pop()
            return
        ef = lib_mod.library_efforts(a.db, self.segment_id)
        routes = a.db.conn.execute(
            "SELECT s.route_id, s.start_m, s.end_m FROM strava_segments s WHERE s.segment_id = ?",
            (self.segment_id,)).fetchall()
        from perennia.ui.connect_screens import strava_busy
        busy = strava_busy(a)
        items = [Item(tr("Atualizar do Strava", "Refresh from Strava"), top=True,
                       value=tr("a atualizar…", "refreshing…") if busy else "",
                       enabled=not busy, action=self._refresh),
                 Item(tr("Ligar às minhas rotas", "Link to my routes"), top=True,
                      action=self._link),
                 Item(tr("Segmento", "Segment"), header=True),
                 Item(tr("Distância", "Distance"),
                      value=f"{(r['distance_m'] or 0) / 1000:.2f} km",
                      detail=" · ".join(x for x in (
                          f"{r['avg_grade']:.1f} %" if r["avg_grade"] is not None else "",
                          f"↑ {r['elev_gain_m']:.0f} m" if r["elev_gain_m"] else "",
                          tr("máx. {g:.0f} %", "max {g:.0f} %", g=r["max_grade"])
                          if r["max_grade"] else "",
                          ", ".join(x for x in (r["city"], r["country"]) if x)) if x),
                      enabled=False),
                 Item(tr("O meu PR no Strava", "My Strava PR"),
                      value=hms(r["pr_s"]) if r["pr_s"] else "—",
                      detail=" · ".join(x for x in (
                          r["pr_date"] or "",
                          tr("{n} esforços no Strava", "{n} efforts on Strava",
                             n=r["effort_count"]) if r["effort_count"] else "",
                          f"KOM {r['kom']}" if r["kom"] else "") if x), enabled=False),
                 Item(tr("Importado", "Imported"), value=str(r["fetched_at"] or "")[:16]
                      .replace("T", " "),
                      detail=tr("ID {i} · origem: {o}", "ID {i} · source: {o}",
                                i=r["segment_id"], o=r["origin"] or "—"), enabled=False),
                 Item(tr("Rotas ligadas", "Linked routes"), header=True)]
        for lk in routes:
            row = a.db.route(lk["route_id"])
            items.append(Item(row["name"] if row else "—",
                              detail=f"km {lk['start_m'] / 1000:.2f}–{lk['end_m'] / 1000:.2f}",
                              action=(lambda rid=lk["route_id"]: self._open_route(rid))
                              if row else None))
        if not routes:
            items.append(Item(tr("Nenhuma rota percorre este segmento",
                                 "No route follows this segment"),
                              detail=tr("importa um .gpx que passe por ele, ou «Ligar às minhas "
                                        "rotas»", "import a .gpx that goes through it, or "
                                        "“Link to my routes”"), enabled=False))
        items.append(Item(tr("Os meus esforços importados", "My imported efforts"), header=True))
        for i, e in enumerate(ef[:60], start=1):
            items.append(Item(f"{i}.  {hms(e['elapsed_s'])}",
                              value=(f"{e['avg_watts']:.0f} W" if e["avg_watts"] else ""),
                              detail=str(e["start_date"] or "")[:10], enabled=False))
        if not ef:
            items.append(Item(tr("Sem esforços importados", "No efforts imported"),
                              detail=tr("precisam de subscrição Strava; «Atualizar do Strava» "
                                        "tenta outra vez", "they need a Strava subscription; "
                                        "“Refresh from Strava” tries again"), enabled=False))
        items.append(Item(tr("Tirar da biblioteca", "Remove from the library"), button=True,
                          action=lambda: delete_library(a, self.segment_id, r["name"],
                                                        then=lambda: a.pop(force=True))))
        self.chrome.set(r["name"], tr("{n} esforços importados · melhor {b}",
                                      "{n} imported efforts · best {b}", n=len(ef),
                                      b=hms(ef[0]["elapsed_s"]) if ef else "—"), self.footer())
        self.list.set_items(items, keep_index=True)

    def _link(self) -> None:
        r = lib_mod.link_all(self.app.db)
        self.app.message(tr("{n} ligações a rotas", "{n} links to routes", n=r["linked"]))
        self.enter()

    def _refresh(self) -> None:
        from perennia.io import strava as strava_mod
        from perennia.ui.connect_screens import strava_job
        client = strava_mod.StravaClient(self.app.db, http=self.http)
        if not client.connected:
            self.app.message(tr("Liga primeiro o Strava em Definições → Strava",
                                "Connect Strava first in Settings → Strava"))
            return
        sid = self.segment_id
        self.job = strava_job(self.app.db, client.http,
                              lambda db, c: lib_mod.import_ids(db, c, [sid]))
        self.enter()

    def update(self, dt: float) -> None:
        j = self.job
        if j is not None and j.done:
            self.job = None
            if j.error:
                self.app.message(f"Strava: {j.error}")
            else:
                self.app.message(j.result.text())
            self.enter()

    def _open_route(self, rid: str) -> None:
        from perennia.ui.route_screens import RouteOverview
        self.app.push(RouteOverview(self.app, rid))
