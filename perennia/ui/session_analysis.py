"""A análise de uma sessão do histórico, em qualquer desporto, em quatro
separadores:

1. **Geral** — o tipo de sessão (livre, treino e o tipo do treino, teste,
   Challenge), os números da sessão, as voltas e o .fit;
2. **Feedback** — o ecrã do feedback, ali mesmo (RPE, dores, sensação,
   objetivo cumprido, comentário e a análise que os cruza);
3. **Análise do treino** — num treino por blocos, se cada bloco foi cumprido
   (alvo, feito, tempo dentro do alvo); no ginásio, cada exercício;
4. **Infográficos** — o gráfico da sessão com os blocos do treino por baixo
   (e o alvo), para se perceber os dados; no ciclismo também o relatório, a
   curva de potência, as zonas e os picos.
"""
from __future__ import annotations

import pyglet
import pyglet.shapes
from pyglet.window import key

from perennia.core import feedback as fbm
from perennia.core import intensity as it
from perennia.core import session_review as rv
from perennia.core.i18n import t, tr
from perennia.core.units import hms, km
from perennia.ui.app import Screen
from perennia.ui.session_radar import RadarSide
from perennia.ui.widgets import PANEL, Chart, Item, TabBar, Table

KINDS = {"cycling": "ride", "rowing": "row", "running": "endurance", "swimming": "endurance",
         "gym": "strength"}


def _m(v) -> str:
    v = v or 0
    return f"{v / 1000:.2f} km" if v >= 1000 else f"{v:.0f} m"


# ----------------------------------------------------------- linhas «Geral»


def workout_state(db, kind: str, sid: str, sess) -> str:
    """«Na lista de treinos», «Apagado da lista…», «Carregado do computador…»."""
    if sess is None or kind not in ("ride", "row", "endurance"):
        return ""
    from perennia.core import session_workouts as sw
    try:
        return sw.state_text(sw.state(db, kind, sid, sess.sport,
                                      sess.origin_workout_id or sess.workout_id))
    except Exception:
        return ""


def general_items(app, kind: str, sid: str, sess) -> list[Item]:
    a = app
    db = a.db
    rows = [Item(tr("Tipo de sessão", "Session kind"), value=rv.session_type(db, sess),
                 enabled=False)]
    try:                                     # as etiquetas do .fit (ver perennia.core.tags)
        from perennia.core import tags as tg
        info = tg.load(db, {"ride": "cycling", "row": "rowing"}.get(kind, sess.sport), sid)
        text = " · ".join(tg.labels(info))
    except Exception:
        text = ""
    if text:
        rows.append(Item(tr("Etiquetas", "Tags"), value=text, enabled=False))
    wstate = workout_state(db, kind, sid, sess)
    if wstate:
        rows.append(Item(tr("Treino", "Workout"), value=wstate, enabled=False))
    rows.append(Item(tr("Data", "Date"), value=str(sess.started_at or "")[:16].replace("T", " "),
                     enabled=False))
    if kind == "ride":
        r = db.conn.execute("SELECT * FROM rides WHERE id = ?", (sid,)).fetchone()
        dv, du = km(r["distance_m"] or 0, a.units)
        rows += [Item(tr("Tempo", "Time"), value=hms(r["moving_s"] or r["elapsed_s"] or 0),
                      enabled=False),
                 Item(tr("Distância", "Distance"), value=f"{dv:.2f} {du}", enabled=False)]
        for label, col, fmt in ((tr("Potência média", "Avg power"), "avg_power_w", "{:.0f} W"),
                                ("NP", "np_w", "{:.0f} W"), ("TSS", "tss", "{:.0f}"),
                                (tr("FC média", "Avg HR"), "avg_hr", "{:.0f} bpm"),
                                (tr("Cadência média", "Avg cadence"), "avg_cadence",
                                 "{:.0f} rpm")):
            try:
                v = r[col]
            except (IndexError, KeyError):
                v = None
            if v:
                rows.append(Item(label, value=fmt.format(v), enabled=False))
        from perennia.core import peaks as pk
        try:
            power = pk.ride_peaks(db, sid).get("power_w", {})
        except Exception:
            power = {}
        shown = [(d, power[d]) for d in (5, 60, 300, 1200) if d in power]
        if shown:
            rows.append(Item(tr("Picos de potência", "Power peaks"),
                             value="  ·  ".join(f"{pk.duration_label(d)} {v:.0f} W"
                                                for d, v in shown), enabled=False))
        laps = db.conn.execute("SELECT lap_no, start_t_s AS a, end_t_s AS b FROM laps"
                               " WHERE ride_id = ? ORDER BY lap_no", (sid,)).fetchall()
        fit = r["fit_path"]
    elif kind == "row":
        from perennia.core import rowing as rw
        from perennia.ui.rowing_screens import pace_text
        r = db.conn.execute("SELECT * FROM row_sessions WHERE id = ?", (sid,)).fetchone()
        rows += [Item(tr("Distância", "Distance"), value=_m(r["distance_m"]), enabled=False),
                 Item(tr("Tempo", "Time"), value=hms(r["moving_s"] or 0), enabled=False),
                 Item(tr("Ritmo médio", "Avg pace"), value=pace_text(r["avg_pace_s"]),
                      enabled=False),
                 Item(tr("Potência média", "Avg power"),
                      value=f"{r['avg_power_w']:.0f} W" if r["avg_power_w"] else "—",
                      enabled=False),
                 Item(tr("Voga média", "Avg stroke rate"),
                      value=f"{r['avg_spm']:.1f}" if r["avg_spm"] else "—", enabled=False),
                 Item(tr("Carga", "Load"), value=f"{r['load']:.0f}" if r["load"] else "—",
                      enabled=False)]
        laps = [{"lap_no": x["lap_no"], "a": x["start_t"], "b": x["end_t"]}
                for x in rw.session_laps(db, sid) if x["distance_m"]]
        fit = r["fit_path"]
    elif kind == "endurance":
        from perennia.core import endurance as en
        r = db.conn.execute("SELECT * FROM endurance_sessions WHERE id = ?", (sid,)).fetchone()
        unit = {"running": "/km", "swimming": "/100 m"}.get(r["sport"], "")
        rows += [Item(tr("Distância", "Distance"), value=_m(r["distance_m"]), enabled=False),
                 Item(tr("Tempo", "Time"), value=hms(r["moving_s"] or 0), enabled=False),
                 Item(tr("Ritmo médio", "Avg pace"),
                      value=(hms(r["avg_pace_s"]) + " " + unit) if r["avg_pace_s"] else "—",
                      enabled=False)]
        if r["avg_hr"]:
            rows.append(Item(tr("FC média", "Avg HR"), value=f"{r['avg_hr']:.0f} bpm",
                             enabled=False))
        laps = [{"lap_no": x["lap_no"], "a": x["start_t"], "b": x["end_t"]}
                for x in en.session_laps(db, sid)]
        fit = r["fit_path"]
    else:
        r = db.conn.execute("SELECT * FROM strength_sessions WHERE id = ?", (sid,)).fetchone()
        rows += [Item(tr("Tempo", "Time"), value=hms(r["elapsed_s"] or 0), enabled=False),
                 Item(tr("Séries", "Sets"), value=f"{r['total_sets'] or 0}", enabled=False)]
        if r["avg_hr"]:
            rows.append(Item(tr("FC média", "Avg HR"), value=f"{r['avg_hr']:.0f} bpm",
                             enabled=False))
        if r["load"]:
            rows.append(Item(tr("Carga", "Load"), value=f"{r['load']:.0f}", enabled=False))
        laps = []
        fit = r["fit_path"]
    if laps:
        rows.append(Item(tr("Voltas", "Laps"), header=True))
        for lp in laps[:12]:
            rows.append(Item(tr("Volta {n}", "Lap {n}", n=lp["lap_no"]),
                             value=hms((lp["b"] or 0) - (lp["a"] or 0)), enabled=False))
    if fit:
        rows.append(Item(".fit", value=str(fit).split("/")[-1], detail=str(fit), enabled=False))
    return rows


# ------------------------------------------------------- infográficos (ciclismo)


def _ride_info():
    from perennia.ui.ride_report_screens import RideInfographics
    return RideInfographics


class _EmbeddedRide:
    """O relatório, a curva, as zonas e os picos do ciclismo (de
    RideInfographics), por baixo dos separadores da análise."""

    VIEW_OF = {1: 0, 2: 1, 3: 2, 4: 4}      # sub-separador → vista de RideInfographics

    def __init__(self, host, ride_id: str):
        cls = _ride_info()
        top_fn = host.body_top

        class Inner(cls):                     # noqa: D401 — o mesmo ecrã, mais abaixo
            def content_top(self, h: int) -> int:
                return int(top_fn(h))
        self.inner = Inner(host.app, ride_id)

    def show(self, sub: int) -> None:
        self.inner.tab = self.VIEW_OF.get(sub, 0)
        self.inner.enter()

    def draw(self) -> None:
        self.inner.list.draw()
        v = self.inner.view
        if v in ("curve", "overlay"):
            self.inner.chart.draw()
        elif v == "zones":
            self.inner.bars.draw()
        elif v == "peaks":
            self.inner.table.draw()


# ================================================================= o ecrã


class SessionAnalysis(RadarSide, Screen):
    TABBED = True
    RADAR_BIG = True
    VIEWS = ("general", "feedback", "analysis", "infographics")

    def __init__(self, app, kind: str, sid: str, tab: int = 0):
        self.kind, self.sid = kind, sid
        super().__init__(app)
        self.sess = fbm.load_session(app.db, kind, sid)
        self.fb = None
        if self.sess is not None:
            from perennia.ui.feedback_screens import EmbeddedFeedback
            self.fb = EmbeddedFeedback(app, kind, sid, host=self)
        w, h = app.window.width, app.window.height
        self.table = Table()
        self.sub = 0                              # o sub-separador dos infográficos
        self.sub_tabs = TabBar(self.sub_labels(), 48, self.content_top(h) + 6, w - 96,
                               small=True)
        self.ride = _EmbeddedRide(self, sid) if kind == "ride" and self.sess else None
        self.series = rv.series(app.db, self.sess) if self.sess else {"t": [], "lines": []}
        self.target = rv.target_line(app.db, self.sess, self.series["t"]) if self.sess else None
        self.show = [True] * len(self.series["lines"])
        self.show_blocks = True
        self.chart = Chart(96, 112, max(200, w - 144), 300)
        self.bands_batch = pyglet.graphics.Batch()
        self.bands: list = []
        self.chart_bg = pyglet.shapes.Rectangle(0, 0, 1, 1, color=PANEL, batch=self.bands_batch)
        self.tab = tab
        if self.tabs is not None:
            self.tabs.select(tab)

    # ---------------------------------------------------------- separadores

    def tab_labels(self) -> list[str]:
        return [tr("Geral", "Overview"), tr("Feedback", "Feedback"),
                tr("Análise do treino", "Workout analysis"),
                tr("Infográficos", "Infographics")]

    def sub_labels(self) -> list[str]:
        base = [tr("Gráfico com os blocos", "Chart with the blocks")]
        if self.kind == "ride":
            base += [tr("Relatório", "Report"), tr("Curva de potência", "Power curve"),
                     tr("Zonas", "Zones"), tr("Picos", "Peaks")]
        return base

    @property
    def view(self) -> str:
        return self.VIEWS[self.tab % len(self.VIEWS)]

    def body_top(self, h: int) -> float:
        """Onde começa o conteúdo; nos infográficos, por baixo dos sub-separadores."""
        return self.content_top(h) - (40 if self.view == "infographics" else 0)

    def on_tab(self) -> None:
        self.enter()

    # ------------------------------------------------------------ conteúdo

    def enter(self) -> None:
        a = self.app
        s = self.sess
        if s is None:
            self.chrome.set(tr("Sessão não encontrada", "Session not found"), "", self.footer())
            self.list.set_items([Item(tr("Esta sessão já não existe.",
                                         "This session no longer exists."), enabled=False)])
            return
        title = s.title or t("home.cycling")
        sub = f"{str(s.started_at)[:16].replace('T', ' ')} · {rv.session_type(a.db, s)}"
        foot = tr("Tab separador · ↑↓ mover · Esc voltar", "Tab next tab · ↑↓ move · Esc back")
        w, h = a.window.width, a.window.height
        self.list.y = self.content_top(h)
        view = self.view
        items: list[Item] = []
        if (view == "general") != self.radar_visible:
            self.radar_visible = view == "general"
            if self._radar is not None:
                self._relayout_list()
        if view == "general":
            items = general_items(a, self.kind, self.sid, s)
            sport = {"ride": "cycling", "row": "rowing"}.get(self.kind, s.sport)
            items[1:1] = self.radar_attach(sport, self.sid)
        elif view == "feedback":
            self.list.y = -3000
            foot = tr("Tab separador · ↑↓ linha · ←/→ valor · Ctrl+S guardar · Esc voltar",
                      "Tab next tab · ↑↓ row · ←/→ value · Ctrl+S save · Esc back")
            if self.fb is not None:
                self.fb._layout()
                self.fb._refresh()
        elif view == "analysis":
            self.list.y = -3000
            self._fill_analysis(w, h)
            if self.kind == "strength":
                sub += " · " + tr("cumprimento de cada exercício", "compliance per exercise")
                items = [Item(tr("Análise detalhada (séries, 1RM)", "Detailed analysis (sets, "
                                 "1RM)"), button=True, primary=True,
                              action=lambda: a.push(_strength_detail(a, self.sid)))]
                from perennia.core import strength as st_core
                if st_core.is_free_session(a.db, self.sid):      # só os treinos livres
                    items.insert(0, Item(tr("Editar séries", "Edit sets"), button=True,
                                         action=lambda: a.push(_free_sets(a, self.sid))))
            else:
                rows = rv.block_compliance(a.db, s)
                if rows:
                    sub += " · " + rv.summary(rows)
        else:
            self.sub_tabs.set_labels(self.sub_labels())
            self.sub_tabs.layout(48, self.content_top(h) + 6, w - 96)
            self.sub_tabs.select(self.sub)
            foot = tr("Tab separador · [ ] ou clique: outra vista · ←/→ liga/desliga · Esc voltar",
                      "Tab next tab · [ ] or click: another view · ←/→ on/off · Esc back")
            if self.sub == 0 or self.ride is None:
                items = self._chart_rows()
                self.list.y = self.body_top(h)
                self._fill_chart(w, h, len(items))
            else:
                self.list.y = -3000
                self.ride.show(self.sub)
        self.chrome.set(title, sub, foot)
        self.list.set_items(items, keep_index=True)

    # ---- análise do treino
    def _fill_analysis(self, w: int, h: int) -> None:
        a = self.app
        top = self.content_top(h) + 10
        self.table.layout(48, top, w - 96, 70)
        if self.kind == "strength":
            from perennia.core import strength_analysis as sa
            an = sa.session(a.db, self.sid) or {"exercises": []}
            cols = [tr("Exercício", "Exercise"), tr("Séries", "Sets"), tr("Repetições", "Reps"),
                    tr("Volume", "Volume"), tr("Cumprimento", "Compliance")]
            rows = []
            for e in an["exercises"]:
                comp = e["compliance"]
                mark = "" if comp is None else ("✓ " if comp >= 0.95 else
                                                "~ " if comp >= 0.7 else "✗ ")
                rows.append([e["name"], f"{e['done_sets']} / {e['planned_sets'] or '—'}",
                             f"{e['done_reps']} / {e['planned_reps'] or '—'}",
                             f"{e['volume']:.0f} kg" if e["volume"] else "—",
                             (mark + f"{comp * 100:.0f} %") if comp is not None else "—"])
            self.table.set(cols, rows, tr("Plano e realizado", "Planned and done"),
                           empty=tr("Sessão livre: não havia plano para comparar.",
                                    "Free session: there was no plan to compare."))
            return
        rows = rv.block_compliance(a.db, self.sess)
        cols = [tr("Bloco", "Block"), tr("Alvo", "Target"), tr("Feito (média)", "Done (avg)"),
                tr("FC média", "Avg HR"), tr("No alvo", "On target"),
                tr("Resultado", "Result")]
        out = []
        for r in rows:
            out.append([f"{r['i'] + 1}. {r['name']} ({hms(r['seconds'])})", r["target"],
                        r["avg_text"], f"{r['avg_hr']:.0f}" if r["avg_hr"] else "—",
                        f"{r['in_target'] * 100:.0f} %" if r["in_target"] is not None else "—",
                        rv.verdict_text(r["verdict"])])
        self.table.set(cols, out, tr("Cada bloco: cumprido ou não", "Each block: done or not"),
                       empty=tr("Sessão livre: sem blocos de treino para comparar.",
                                "Free session: no workout blocks to compare."))

    # ---- gráfico com os blocos
    def _chart_rows(self) -> list[Item]:
        rows = []
        for i, (name, vals, _c) in enumerate(self.series["lines"]):
            if not any(vals):
                continue
            on = self.show[i]
            rows.append(Item(("✓ " if on else "   ") + name,
                             value=tr("ligada", "on") if on else tr("desligada", "off"),
                             detail=tr("←/→ liga/desliga", "←/→ on/off"), data=f"series:{i}"))
        if self.target is not None:
            rows.append(Item(("✓ " if self.show_blocks else "   ")
                             + tr("Blocos e alvo do treino", "Workout blocks and target"),
                             value=tr("ligados", "on") if self.show_blocks else
                             tr("desligados", "off"),
                             detail=tr("←/→ liga/desliga", "←/→ on/off"), data="blocks"))
        return rows

    def _fill_chart(self, w: int, h: int, n_rows: int) -> None:
        from perennia.ui.ride_report_screens import downsample
        top = self.body_top(h) - n_rows * 38 - 16
        x, y, cw, ch = 96, 96, w - 144, max(140, top - 96 - 30)
        self.chart = Chart(x, y, cw, ch)
        self.chart._bg.opacity = 0                 # o fundo e os blocos desenham-se antes
        self.chart_bg.x, self.chart_bg.y, self.chart_bg.width, self.chart_bg.height = \
            x, y, cw, ch
        t = self.series["t"]
        pts = 119                                  # o gráfico leva até 120 pontos
        lines = []
        for i, (name, vals, color) in enumerate(self.series["lines"]):
            if self.show[i] and any(vals):
                lines.append((name, downsample(vals, pts), color))
        if self.target is not None and self.show_blocks and any(self.target):
            lines.append((tr("Alvo", "Target"), downsample(self.target, pts), (70, 70, 80)))
        n = len(lines[0][1]) if lines else 0
        total = t[-1] if t else 0
        labels = [hms(total * i / max(1, n - 1)) for i in range(n)]
        self.chart.show_lines(tr("A sessão, segundo a segundo", "The session, second by second"),
                              lines, labels, tr("Sem dados desta sessão.",
                                                "No data for this session."),
                              fmt=lambda v: f"{v:.0f}")
        # os blocos do treino por baixo das linhas, com as cores das zonas
        for r in self.bands:
            r.delete()
        self.bands = []
        if self.target is None or not self.show_blocks or not total:
            return
        brief = fbm.prescribed(self.app.db, self.sess)
        for b, (a, z) in zip(brief.raw_blocks, rv.block_windows(self.app.db, self.sess, brief)):
            if z <= a:
                continue
            x0 = x + cw * min(1.0, a / total)
            x1 = x + cw * min(1.0, z / total)
            pct = (b.lo + (b.hi if b.hi is not None else b.lo)) / 2 if b.lo is not None else None
            color = it.zone_color(pct)[:3] if pct is not None else (190, 196, 206)
            band = pyglet.shapes.Rectangle(x0, y, max(1.0, x1 - x0 - 1), ch, color=color,
                                           batch=self.bands_batch)
            band.opacity = 70
            self.bands.append(band)

    # --------------------------------------------------------------- teclas

    def on_key(self, symbol: int, modifiers: int) -> bool:
        view = self.view
        if symbol == key.TAB:
            return super().on_key(symbol, modifiers)
        if view == "feedback" and self.fb is not None:
            return self.fb.on_key(symbol, modifiers)
        if view == "infographics":
            if symbol in (key.BRACKETLEFT, key.BRACKETRIGHT, key.PAGEUP, key.PAGEDOWN):
                step = 1 if symbol in (key.BRACKETRIGHT, key.PAGEDOWN) else -1
                self.sub = (self.sub + step) % len(self.sub_labels())
                self.enter()
                return True
            item = self.list.selected
            if item is not None and symbol in (key.LEFT, key.RIGHT) and \
                    isinstance(item.data, str):
                if item.data.startswith("series:"):
                    i = int(item.data[7:])
                    self.show[i] = not self.show[i]
                elif item.data == "blocks":
                    self.show_blocks = not self.show_blocks
                self.enter()
                return True
        return super().on_key(symbol, modifiers)

    def on_text(self, text: str) -> bool:
        if self.view == "feedback" and self.fb is not None:
            return self.fb.on_text(text)
        return super().on_text(text)

    def on_mouse(self, x: int, y: int) -> bool:
        if self.tabs is not None and self.tabs.hit(x, y) is not None:
            return super().on_mouse(x, y)
        if self.back_button is not None and self.back_button.hit(x, y):
            return super().on_mouse(x, y)
        if self.view == "feedback" and self.fb is not None:
            return self.fb.on_mouse(x, y)
        if self.view == "infographics":
            i = self.sub_tabs.hit(x, y)
            if i is not None:
                self.sub = i
                self.enter()
                return True
        return super().on_mouse(x, y)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        if self.fb is not None:
            self.fb.on_resize(w, h)
        self.enter()

    # ------------------------------------------- alterações (o feedback)

    def has_unsaved(self) -> bool:
        return self.fb is not None and self.fb.has_unsaved()

    def on_save(self) -> bool:
        if self.fb is not None:
            self.fb.save()
            return True
        return False

    def discard(self) -> None:
        if self.fb is not None:
            self.fb.mark_saved()

    def agent_data(self) -> dict:
        s = self.sess
        if s is None:
            return {}
        return {"tipo": rv.session_type(self.app.db, s),
                "blocos": [{k: r[k] for k in ("name", "target", "avg_text", "in_target",
                                              "verdict")}
                           for r in rv.block_compliance(self.app.db, s)]}

    def draw(self) -> None:
        super().draw()
        view = self.view
        if view == "feedback" and self.fb is not None:
            self.fb.draw_body()
        elif view == "analysis":
            self.table.draw()
        elif view == "infographics":
            self.sub_tabs.draw()
            if self.sub == 0 or self.ride is None:
                self.bands_batch.draw()
                self.chart.draw()
            else:
                self.ride.draw()


def _free_sets(app, sid: str):
    from perennia.ui.strength_analysis_screens import FreeSetsScreen
    return FreeSetsScreen(app, sid)


def _strength_detail(app, sid: str):
    from perennia.ui.strength_analysis_screens import StrengthAnalysisScreen
    return StrengthAnalysisScreen(app, sid)


def open_session(app, sport_or_kind: str, sid: str, tab: int = 0) -> SessionAnalysis:
    """A análise de uma sessão (de qualquer desporto)."""
    kind = KINDS.get(sport_or_kind, sport_or_kind)
    return SessionAnalysis(app, kind, sid, tab)
