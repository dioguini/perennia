"""O menu **Segmentos** do ecrã inicial: os segmentos da Perennia e os do
Strava, num só sítio.

* **Visão geral** — todos os segmentos de todas as rotas, com o melhor
  tempo; **Perennia** e **Strava** — só os de cada fonte. À direita, o
  perfil da rota com o segmento escolhido.
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

from velo.core import routes as routes_mod
from velo.core import segments as seg_mod
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx.compat import label as make_label
from velo.ui.app import Screen
from velo.ui.route_screens import ProfileChart, route_bands, segment_item
from velo.ui.sport_screens import EditPopup
from velo.ui.widgets import ACCENT, TEXT, Item, fit_text


def delete_segment(app, seg_id: int, name: str, then=None) -> None:
    def gone() -> None:
        seg_mod.delete_perennia(app.db, seg_id)
        if then is not None:
            then()
    app.confirm(tr("Apagar o segmento «{n}»?", "Delete the segment «{n}»?", n=name),
                tr("Os tempos feitos nele vão com ele. Não dá para desfazer.",
                   "The times done on it go with it. This cannot be undone."),
                gone, yes=tr("Apagar", "Delete"))


# ================================================================ a lista


class SegmentsScreen(Screen):
    TABBED = True
    KEY_SCOPE = "routes"
    TAB_KEYS = ("all", "perennia", "strava")

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
        return [tr("Visão geral", "Overview"), "Perennia", "Strava"]

    def _list_width(self, w: int) -> int:
        return int((w - 96) * 0.5)

    def enter(self) -> None:
        a = self.app
        which = self.TAB_KEYS[self.tab % len(self.TAB_KEYS)]
        segs = seg_mod.overview(a.db)
        if which != "all":
            segs = [s for s in segs if s.source == which]
        items = [Item(tr("+ Novo segmento", "+ New segment"), top=True,
                      action=lambda: a.push(SegmentEditor(a, None)))]
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
                        tr("procura-os no Strava na ficha de uma rota (menu Rotas)",
                           "look them up on Strava from a route (Routes menu)")),
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
                         tr("Melhor: {b} · {n} vezes", "Best: {b} · {n} times",
                            b=hms(ef[0]["elapsed_s"]) if ef else "—", n=len(ef)),
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
        band = [(self.v["start_km"] * 1000, self.v["end_km"] * 1000, (120, 200, 255),
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
        from velo.core import sports as sp
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
        from velo.ui.route_screens import RouteOverview
        self.app.push(RouteOverview(self.app, rid))

    def _open_session(self, kind: str, sid: str) -> None:
        from velo.ui.session_analysis import SessionAnalysis
        self.app.push(SessionAnalysis(self.app, kind, sid))
