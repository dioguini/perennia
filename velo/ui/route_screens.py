"""O menu **Rotas** do ecrã inicial: o centro das rotas (.gpx) da Perennia.

* **Rotas** — todas as rotas, com a distância, a subida, as subidas e
  quantas vezes já foram feitas (no ciclismo e na corrida); à direita, o
  perfil de altimetria da rota escolhida. «+ Carregar .gpx» em cima, à
  direita, é o único sítio da aplicação onde se carregam ficheiros .gpx.
* **A rota** — o perfil em cima (cores pela inclinação, com os segmentos
  por cima) e por baixo os números, as subidas, os segmentos (Perennia e
  Strava), as sessões feitas nela e «Começar» no ciclismo ou na corrida.

O ciclismo e a corrida escolhem só entre as rotas que já existem aqui.
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import routes as routes_mod
from velo.core.i18n import t, tr
from velo.core.units import hms, km
from velo.gfx.compat import label as make_label
from velo.ui.app import GpxPicker, LeaderboardScreen, Screen
from velo.ui.widgets import ACCENT, DIM, PANEL, TEXT, Item, fit_text

# cores pela inclinação (a descer · plano · 2–5 % · 5–8 % · mais)
GRADES = ((-0.5, (96, 140, 190)), (2.0, (88, 170, 110)), (5.0, (214, 190, 80)),
          (8.0, (230, 140, 60)), (99.0, (210, 70, 60)))
PERENNIA_C = (40, 120, 220)
STRAVA_C = (252, 82, 0)
STRIP_H = 15          # a faixa de cor do segmento, em cima do perfil


def grade_color(g: float) -> tuple[int, int, int]:
    for top, c in GRADES:
        if g < top:
            return c
    return GRADES[-1][1]


class ProfileChart:
    """O perfil de altimetria de uma rota: barras coloridas pela inclinação,
    com faixas por cima (os segmentos) e as altitudes e os km nos eixos."""

    BARS = 160
    BANDS = 14

    def __init__(self, batch=None):
        self.batch = batch or pyglet.graphics.Batch()
        b = self.batch
        self.bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL, batch=b)
        self.bars = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=GRADES[1][1], batch=b)
                     for _ in range(self.BARS)]
        self.bands = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=PERENNIA_C, batch=b)
                      for _ in range(self.BANDS)]
        # a cor da fonte (Perennia azul, Strava laranja) numa faixa por cima
        self.strips = [pyglet.shapes.Rectangle(0, 0, 1, 1, color=PERENNIA_C, batch=b)
                       for _ in range(self.BANDS)]
        self.band_labels = [make_label("", font_size=9, bold=True, color=TEXT,
                                       anchor_y="bottom", batch=b) for _ in range(self.BANDS)]
        self.top_lab = make_label("", font_size=10, color=DIM, anchor_y="top", batch=b)
        self.low_lab = make_label("", font_size=10, color=DIM, anchor_y="bottom", batch=b)
        self.km_labs = [make_label("", font_size=10, color=DIM, anchor_x="center",
                                   anchor_y="top", batch=b) for _ in range(5)]
        self.empty = make_label("", font_size=12, color=DIM, anchor_x="center",
                                anchor_y="center", batch=b)
        self.rect = (0, 0, 1, 1)

    def set(self, prof: list, x: float, y: float, w: float, h: float,
            bands: list | None = None, empty: str = "") -> None:
        """`prof`: [(dist m, alt m, inclinação %)]; `bands`: [(início m, fim m,
        cor, texto, forte)]."""
        self.rect = (x, y, w, h)
        self.bg.x, self.bg.y, self.bg.width, self.bg.height = x, y, w, h
        if not prof:
            for r in self.bars + self.bands + self.strips:
                r.opacity = 0
            for lab in self.band_labels + self.km_labs:
                lab.text = ""
            self.top_lab.text = self.low_lab.text = ""
            self.empty.text = empty or tr("Sem perfil", "No profile")
            self.empty.x, self.empty.y = x + w / 2, y + h / 2
            return
        self.empty.text = ""
        pad_l, pad_b, pad_t = 52, 20, 14 + STRIP_H * 2 + 4
        cx, cy, cw, ch = x + pad_l, y + pad_b, w - pad_l - 10, h - pad_b - pad_t
        eles = [e for _d, e, _g in prof]
        lo, hi = min(eles), max(eles)
        span = max(10.0, hi - lo)
        base = lo - span * 0.12
        total = prof[-1][0] or 1.0
        n = min(len(prof), self.BARS)
        bw = cw / n
        for k, bar in enumerate(self.bars):
            if k >= n:
                bar.opacity = 0
                continue
            d, e, g = prof[int(k * (len(prof) - 1) / max(1, n - 1))]
            bar.opacity = 255
            bar.x, bar.y = cx + k * bw, cy
            bar.width = max(1.0, bw - 0.5)
            bar.height = max(1.0, (e - base) / (hi - base) * ch)
            bar.color = grade_color(g)
        self.top_lab.text = f"{hi:.0f} m"
        self.top_lab.x, self.top_lab.y = x + 6, y + h - 4
        self.low_lab.text = f"{lo:.0f} m"
        self.low_lab.x, self.low_lab.y = x + 6, cy
        for k, lab in enumerate(self.km_labs):
            d = total * k / (len(self.km_labs) - 1)
            lab.text = f"{d / 1000:.1f} km"
            lab.x, lab.y = cx + cw * k / (len(self.km_labs) - 1), cy - 2
        bands = list(bands or [])[:self.BANDS]
        top = cy + ch + 4
        for k, (rect, strip, lab) in enumerate(zip(self.bands, self.strips, self.band_labels)):
            if k >= len(bands):
                rect.opacity = strip.opacity = 0
                lab.text = ""
                continue
            a, z, color, text, strong = bands[k]
            x0 = cx + max(0.0, min(1.0, a / total)) * cw
            x1 = cx + max(0.0, min(1.0, z / total)) * cw
            # por cima das barras, uma sombra leve; a cor forte fica na faixa
            rect.x, rect.y = x0, cy
            rect.width, rect.height = max(2.0, x1 - x0), ch
            rect.color = (255, 255, 255)
            rect.opacity = 70 if strong else 0
            row = k % 2                      # duas filas, para não se taparem
            strip.x, strip.y = x0, top + row * (STRIP_H + 2)
            strip.width, strip.height = max(3.0, x1 - x0), STRIP_H
            strip.color = color
            strip.opacity = 255 if strong else 120
            lab.text = fit_text(text, max(40.0, x1 - x0), 9, bold=True) if strong else ""
            lab.color = (255, 255, 255, 255)
            lab.x, lab.y = x0 + 3, strip.y + 1

    def draw(self) -> None:
        self.batch.draw()


def route_bands(db, route_id: str, chosen: str | None = None) -> list:
    """As faixas do perfil: os segmentos da rota (Perennia e Strava)."""
    from velo.core import segments as seg_mod
    out = []
    for s in seg_mod.load(db, route_id):
        color = PERENNIA_C if s.source == "perennia" else STRAVA_C
        out.append((s.start_m, s.end_m, color, s.name, chosen in (None, s.key)))
    return out


def route_line(row, units: str, done: dict | None = None, climbs: int | None = None) -> str:
    dv, du = km(row["distance_m"], units)
    if climbs is None:
        climbs = row["climb_count"] if "climb_count" in row.keys() else 0
    bits = [f"{dv:.1f} {du}", f"↑ {row['ascent_m']:.0f} m",
            tr("1 subida", "1 climb") if climbs == 1 else
            tr("{n} subidas", "{n} climbs", n=climbs)]
    if done is not None:
        bits.append(routes_mod.times_text(done))
    return " · ".join(bits)


# ================================================================ a lista


class RoutesScreen(Screen):
    """Todas as rotas; à direita, o perfil da rota escolhida."""

    KEY_SCOPE = "routes"

    def __init__(self, app):
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self.chart = ProfileChart(self.batch)
        self.info = [make_label("", font_size=12, color=TEXT, anchor_y="top", batch=self.batch)
                     for _ in range(4)]
        self.head = make_label("", font_size=15, bold=True, color=ACCENT, anchor_y="top",
                               batch=self.batch)
        self._shown: object = ()

    def _list_width(self, w: int) -> int:
        return int((w - 96) * 0.48)

    def enter(self) -> None:
        a = self.app
        rows = a.db.routes()
        items = [Item(tr("+ Carregar .gpx", "+ Load .gpx"), top=True,
                      detail=tr("procura nas pastas gpx, Transferências e Documentos",
                                "looks in the gpx, Downloads and Documents folders"),
                      action=lambda: a.push(GpxPicker(a, on_pick=self._imported)))]
        for row in rows:
            done = routes_mod.times_done(a.db, row["id"])
            dv, du = km(row["distance_m"], a.units)
            items.append(Item(("★ " if row["favorite"] else "") + row["name"],
                              value=f"{dv:.1f} {du}",
                              detail=f"↑ {row['ascent_m']:.0f} m · "
                                     + routes_mod.times_text(done),
                              action=lambda r=row: a.push(RouteOverview(a, r["id"])),
                              data=row["id"]))
        if not rows:
            items.append(Item(tr("Ainda não tens rotas", "No routes yet"),
                              detail=tr("carrega um .gpx (em cima, à direita)",
                                        "load a .gpx (top right)"), enabled=False))
        self.chrome.set(tr("Rotas", "Routes"),
                        (tr("1 rota", "1 route") if len(rows) == 1 else
                         tr("{n} rotas", "{n} routes", n=len(rows)))
                        + tr(" · para o ciclismo e a corrida", " · for cycling and running"),
                        tr("Enter abrir · F favorita · Del apagar · Esc voltar",
                           "Enter open · F favourite · Del delete · Esc back"))
        self.list.set_items(items, keep_index=True)
        self._shown = ()

    def _imported(self, route_id: str) -> None:
        self.app.push(RouteOverview(self.app, route_id))

    def _side(self) -> None:
        item = self.list.selected
        rid = item.data if item is not None and isinstance(item.data, str) else None
        key_ = (rid, id(self.list.items))
        if key_ == self._shown:
            return
        self._shown = key_
        w, h = self.app.window.width, self.app.window.height
        x = 48 + self._list_width(w) + 30
        cw = w - 48 - x
        top = self.content_top(h)
        row = self.app.db.route(rid) if rid else None
        self.head.x, self.head.y = x, top + 4
        self.head.text = fit_text(row["name"], cw, 15, bold=True) if row else ""
        ch = max(160.0, min(320.0, (top - 120) * 0.55))
        prof = routes_mod.profile(self.app.db, rid) if rid else []
        self.chart.set(prof, x, top - 30 - ch, cw, ch,
                       route_bands(self.app.db, rid) if rid else [],
                       empty=tr("Escolhe uma rota para ver o perfil",
                                "Pick a route to see its profile"))
        lines = []
        if row is not None:
            done = routes_mod.times_done(self.app.db, rid)
            lines = [route_line(row, self.app.units, None,
                                len(self.app.db.climbs(rid))),
                     tr("Descida {d} m · altitude {a}–{b} m · inclinação máx. {g:.1f} %",
                        "Descent {d} m · altitude {a}–{b} m · max grade {g:.1f} %",
                        d=f"{row['descent_m']:.0f}", a=f"{row['min_ele_m'] or 0:.0f}",
                        b=f"{row['max_ele_m'] or 0:.0f}", g=row["max_grade_pct"] or 0),
                     routes_mod.times_text(done).capitalize()]
            from velo.core import segments as seg_mod
            segs = seg_mod.load(self.app.db, rid)
            if segs:
                n_p = sum(1 for s in segs if s.source == "perennia")
                lines.append(tr("Segmentos: {p} Perennia · {s} Strava",
                                "Segments: {p} Perennia · {s} Strava", p=n_p,
                                s=len(segs) - n_p))
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
        rid = item.data if item is not None and isinstance(item.data, str) else None
        if symbol == key.F and rid:
            self.app.db.toggle_favorite(rid)
            self.enter()
            return True
        if symbol == key.DELETE and rid:
            delete_route(self.app, rid, item.label.lstrip("★ "), then=self.enter)
            return True
        return super().on_key(symbol, modifiers)


def delete_route(app, rid: str, name: str, then=None) -> None:
    def gone() -> None:
        app.db.delete_route(rid)
        if then is not None:
            then()
    app.confirm(tr("Apagar a rota «{n}»?", "Delete the route «{n}»?", n=name),
                tr("As sessões feitas nela ficam no histórico; os segmentos da Perennia "
                   "desta rota vão com ela. Não dá para desfazer.",
                   "Sessions done on it stay in the history; this route's Perennia "
                   "segments go with it. This cannot be undone."),
                gone, yes=tr("Apagar", "Delete"))


# ================================================================= a rota


class RouteOverview(Screen):
    """Uma rota: o perfil em cima e, por baixo, os números, as subidas, os
    segmentos, as sessões feitas nela e «Começar» (ciclismo ou corrida)."""

    KEY_SCOPE = "routes"

    def __init__(self, app, route_id: str):
        self.route_id = route_id
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self.chart = ProfileChart(self.batch)
        self._shown: object = ()

    def chart_h(self, h: int) -> float:
        return max(130.0, min(250.0, (h - 240) * 0.36))

    def content_top(self, h: int) -> int:
        return int(h - 130 - self.chart_h(h) - 24)

    def enter(self) -> None:
        a = self.app
        row = a.db.route(self.route_id)
        if row is None:
            a.pop()
            return
        from velo.core import segments as seg_mod
        done = routes_mod.times_done(a.db, self.route_id)
        dv, du = km(row["distance_m"], a.units)
        items = [Item(tr("+ Novo segmento", "+ New segment"), top=True,
                      action=self._new_segment),
                 Item(tr("Rota", "Route"), header=True),
                 Item(tr("Distância", "Distance"), value=f"{dv:.2f} {du}",
                      detail=tr("subida {u} m · descida {d} m", "ascent {u} m · descent {d} m",
                                u=f"{row['ascent_m']:.0f}", d=f"{row['descent_m']:.0f}"),
                      enabled=False),
                 Item(tr("Altitude", "Altitude"),
                      value=f"{row['min_ele_m'] or 0:.0f}–{row['max_ele_m'] or 0:.0f} m",
                      detail=tr("inclinação máxima {g:.1f} %", "max grade {g:.1f} %",
                                g=row["max_grade_pct"] or 0), enabled=False),
                 Item(tr("Vezes feita", "Times done"), value=str(done["total"]),
                      detail=routes_mod.times_text(done), enabled=False)]
        board = a.db.route_leaderboard(self.route_id)
        if board:
            items.append(Item(tr("Melhor tempo (ciclismo)", "Best time (cycling)"),
                              value=hms(board[0]["elapsed_s"]),
                              detail=tr("Enter abre a classificação", "Enter opens the board"),
                              action=lambda: a.push(LeaderboardScreen(a, row["name"], board))))
        climbs = a.db.climbs(self.route_id)
        if climbs:
            items.append(Item(tr("Subidas", "Climbs"), header=True))
            for c in climbs:
                best = a.db.climb_leaderboard(c.id or -1, limit=1)
                items.append(Item(
                    c.name, value=f"{t('sign.category', cat=c.category)} · "
                                  f"{hms(best[0]['elapsed_s']) if best else '—'}",
                    detail=f"km {c.start_m / 1000:.1f} · {c.length_m / 1000:.1f} km @ "
                           f"{c.avg_grade_pct:.1f} % · ↑ {c.gain_m:.0f} m",
                    action=lambda cid=c.id, nm=c.name: a.push(
                        LeaderboardScreen(a, nm, a.db.climb_leaderboard(cid or -1))),
                    data=("climb", c.id)))
        segs = seg_mod.load(a.db, self.route_id)
        items.append(Item(tr("Segmentos", "Segments"), header=True))
        for s in segs:
            items.append(segment_item(a, s, show_route=False))
        from velo.ui import connect_screens
        n_strava = sum(1 for s in segs if s.source == "strava")
        items.append(Item(tr("Segmentos do Strava", "Strava segments"),
                          value=str(n_strava) if n_strava else "",
                          detail=tr("procurar no Strava os segmentos desta rota",
                                    "look up this route's segments on Strava"),
                          action=lambda: a.push(connect_screens.StravaSegmentsScreen(
                              a, self.route_id)), data=("strava", "list")))
        sess = routes_mod.sessions(a.db, self.route_id, limit=6)
        if sess:
            from velo.core import sports as sp
            items.append(Item(tr("Sessões nesta rota", "Sessions on this route"), header=True))
            for r in sess:
                items.append(Item(
                    f"{str(r['started_at'])[:16].replace('T', ' ')}  {sp.name(r['sport'])}",
                    value=hms(r["moving_s"] or r["elapsed_s"] or 0),
                    detail=" · ".join(x for x in (
                        f"{(r['distance_m'] or 0) / 1000:.1f} km",
                        f"{r['avg_power_w']:.0f} W" if r.get("avg_power_w") else "",
                        f"{r['avg_hr']:.0f} bpm" if r.get("avg_hr") else "") if x),
                    action=lambda k=r["kind"], sid=r["id"]: self._open_session(k, sid)))
        items += [Item(tr("Começar no ciclismo", "Start cycling"), button=True,
                       action=lambda: self._start("cycling")),
                  Item(tr("Começar na corrida", "Start running"), button=True, primary=True,
                       action=lambda: self._start("running"))]
        self.chrome.set(("★ " if row["favorite"] else "") + row["name"],
                        route_line(row, a.units, done, len(climbs)),
                        tr("↑↓ mover · Enter abrir · F favorita · Del apagar · Esc voltar",
                           "↑↓ move · Enter open · F favourite · Del delete · Esc back"))
        self.list.set_items(items, keep_index=True)
        self._shown = ()

    def _open_session(self, kind: str, sid: str) -> None:
        from velo.ui.session_analysis import SessionAnalysis
        self.app.push(SessionAnalysis(self.app, kind, sid))

    def _start(self, sport: str) -> None:
        from velo.ui.session_setup import SessionSetup
        self.app.push(SessionSetup(self.app, sport, kind="free", route_id=self.route_id))

    def _new_segment(self) -> None:
        from velo.ui.segment_screens import SegmentEditor
        self.app.push(SegmentEditor(self.app, None, route_id=self.route_id))

    def _chart(self) -> None:
        item = self.list.selected
        chosen = item.data[1] if item is not None and isinstance(item.data, tuple) and \
            item.data[0] == "segment" else None
        key_ = (chosen, id(self.list.items))
        if key_ == self._shown:
            return
        self._shown = key_
        w, h = self.app.window.width, self.app.window.height
        ch = self.chart_h(h)
        self.chart.set(routes_mod.profile(self.app.db, self.route_id), 48, h - 130 - ch,
                       w - 96, ch, route_bands(self.app.db, self.route_id, chosen))

    def draw(self) -> None:
        super().draw()
        self._chart()
        self.batch.draw()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._shown = ()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        a = self.app
        item = self.list.selected
        if symbol == key.F:
            a.db.toggle_favorite(self.route_id)
            self.enter()
            return True
        if symbol == key.DELETE:
            if item is not None and isinstance(item.data, tuple) and \
                    item.data[0] == "segment" and item.data[1].startswith("perennia:"):
                from velo.ui.segment_screens import delete_segment
                delete_segment(a, int(item.data[1].split(":")[1]), item.label,
                               then=self.enter)
                return True
            row = a.db.route(self.route_id)
            delete_route(a, self.route_id, row["name"] if row else "",
                         then=lambda: a.pop(force=True))
            return True
        return super().on_key(symbol, modifiers)


def segment_item(app, s, show_route: bool = True) -> Item:
    """Uma linha de segmento: o nome, o melhor tempo, e onde fica na rota."""
    src = "Perennia" if s.source == "perennia" else "Strava"
    best = s.local_best_s
    bits = [src]
    if show_route and s.route_id:
        r = app.db.route(s.route_id)
        if r is not None:
            bits.append(r["name"])
    bits.append(f"km {s.start_m / 1000:.1f}–{s.end_m / 1000:.1f} · "
                f"{s.length_m / 1000:.2f} km")
    if s.avg_grade is not None:
        bits.append(f"{s.avg_grade:.1f} %")
    if s.source == "strava" and s.pr_s:
        bits.append(f"PR {hms(s.pr_s)}")
    if s.source == "perennia" and s.effort_count:
        bits.append(tr("1 vez", "once") if s.effort_count == 1 else
                    tr("{n} vezes", "{n} times", n=s.effort_count))
    from velo.ui.segment_screens import SegmentDetail
    return Item(s.name, value=hms(best) if best else "—", detail=" · ".join(bits),
                action=lambda: app.push(SegmentDetail(app, s.source, s.id)),
                data=("segment", s.key, s.route_id))
