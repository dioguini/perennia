"""Construtor de treinos interativo: arrastam-se blocos e vê-se o treino.

- Da paleta (Z1…Z6, Descanso, Rampa, Free ride) arrasta-se um bloco para o
  gráfico; largar entre dois blocos põe-no ali. Um clique na paleta junta-o
  a seguir ao bloco escolhido.
- No gráfico: arrastar o meio de um bloco muda-o de lugar; a aresta direita
  muda a duração; a aresta de cima muda a intensidade (numa rampa, a metade
  esquerda muda o início e a direita o fim).
- Os separadores mudam a vista: zonas de potência, FC, RPE ou ritmo. O
  treino é o mesmo; a escala do eixo e os números é que mudam.
- Teclado: ←/→ escolhem o bloco, ↑/↓ intensidade (Shift: ±5), + / −
  duração, D duplica, Del apaga.

Funciona para ciclismo, remo, corrida e natação; cada um guarda no seu
formato (o ciclismo no mesmo de sempre, que se exporta para .zwo/.erg/.mrc/.fit).
"""
from __future__ import annotations

from dataclasses import replace

import pyglet
from pyglet.window import key

from perennia.core import intensity as it
from perennia.core import workout_meta as wm
from perennia.core.blocks import (Block, block_seconds, estimate, load_blocks,  # noqa: F401
                               save_blocks)
from perennia.core.i18n import tr
from perennia.core.units import hms
from perennia.gfx.compat import label as make_label
from perennia.ui.sport_screens import EditScreen
from perennia.ui.widgets import ACCENT, DIM, GRID, PANEL, PANEL2, ROW_H, TEXT, Item, text_px

SNAP_S = 10
SNAP_M = {"rowing": 50, "running": 100, "swimming": 25, "cycling": 100}
EDGE_PX = 9


PALETTE = (("Z1", 50), ("Z2", 68), ("Z3", 83), ("Z4", 98), ("Z5", 112), ("Z6", 130),
           ("rest", 45), ("ramp", None), ("free", None))


# ================================================================= ecrã


def builder_items(app, sport: str) -> list[Item]:
    """O separador «Construtor de treinos», igual no ciclismo, no remo, na
    corrida e na natação: cada treino com a duração, a definição e o tipo
    («Potência · ERG»), a descrição e a carga; Enter abre-o nos blocos.
    «+ Novo treino» fica em baixo, à direita."""
    from perennia.core.units import hms as _hms
    db = app.db
    rows: list[Item] = []
    if sport == "cycling":
        src = [{"id": w["id"], "name": w["name"], "s": w["total_seconds"] or 0, "m": 0,
                "desc": w["description"] or w["source_format"] or "", "load": w["est_tss"],
                "mode": "power", "data": ("workout", w["id"], w["name"])}
               for w in db.workouts()]
    elif sport == "rowing":
        from perennia.core import rowing as rw
        src = [{"id": w["id"], "name": w["name"], "s": w["total_s"], "m": w["total_m"],
                "desc": w.get("description") or "", "load": None, "mode": "power",
                "data": ("row_workout", w["id"])} for w in rw.workouts(db)]
    else:
        from perennia.core import endurance as en
        src = [{"id": w["id"], "name": w["name"], "s": w["total_s"], "m": w["total_m"],
                "desc": w.get("description") or "", "load": None, "mode": w.get("mode"),
                "data": ("endurance_workout", w["id"])} for w in en.workouts(db, sport)]
    for w in src:
        dur = " + ".join(x for x in (
            _hms(w["s"]) if w["s"] else "",
            (f"{w['m'] / 1000:g} km" if w["m"] >= 1000 else f"{w['m']:.0f} m") if w["m"]
            else "") if x)
        if sport == "running" and w["s"]:
            # na corrida, a distância total sai das velocidades (ou dos ritmos)
            from perennia.core import endurance as en
            full = en.workout(db, w["id"])
            km = en.planned_m(db, sport, full) / 1000 if full else 0
            if km and km * 1000 > w["m"] + 1:
                dur += f" · ≈ {km:.2f} km"
        load = (f"TSS ≈ {w['load']:.0f}" if sport == "cycling" else
                tr("carga ≈ {v}", "load ≈ {v}", v=f"{w['load']:.0f}")) if w["load"] else ""
        detail = " · ".join(x for x in (wm.label(db, sport, w["id"], w["mode"]), w["desc"], load)
                            if x)
        rows.append(Item(w["name"], value=dur, detail=detail,
                         action=lambda wid=w["id"]: app.push(BlockBuilder(app, sport, wid)),
                         data=w["data"]))
    rows.append(Item(tr("+ Novo treino", "+ New workout"),
                     action=lambda: new_workout(app, sport), button=True, primary=True))
    return rows


def builder_footer(sport: str) -> str:
    keys = {"cycling": tr(" · E exportar · P passos", " · E export · P steps"),
            "rowing": tr(" · P passos", " · P steps")}.get(sport, "")
    return tr("Tab separador · ↑↓ mover · Enter abrir nos blocos", "Tab next tab · ↑↓ move · "
              "Enter open in blocks") + keys + tr(" · Del apagar · Esc voltar",
                                                  " · Del delete · Esc back")


DELETE_SUB = ("Sai da lista de treinos. As sessões já feitas com ele guardam a sua cópia.",
              "It leaves the workout list. Sessions already done with it keep their copy.")


def delete_workout(app, sport: str, wid: str, name: str, then=None) -> None:
    """Apagar um treino da lista (com confirmação). Não se perde nada das
    sessões: o treino fica marcado como apagado e cada sessão tem a sua cópia."""
    def gone() -> None:
        if sport == "cycling":
            app.db.delete_workout(wid)
        elif sport == "rowing":
            from perennia.core import rowing as rw
            rw.delete_workout(app.db, wid)
        else:
            from perennia.core import endurance as en
            en.delete_workout(app.db, wid)
        app.message(tr("«{n}» saiu da lista de treinos", "«{n}» left the workout list", n=name))
        if then is not None:
            then()
    app.confirm(tr("Apagar o treino «{n}»?", "Delete the workout «{n}»?", n=name),
                tr(*DELETE_SUB), gone, yes=tr("Apagar", "Delete"))


def new_workout(app, sport: str) -> None:
    """«+ Novo treino»: primeiro pergunta o tipo (ERG ou Manual) — no ciclismo,
    no remo e na corrida; a natação é sempre manual — e depois abre o
    construtor já com as vistas desse tipo."""
    if sport not in wm.ASKS_TYPE:
        app.push(BlockBuilder(app, sport, None, control="manual"))
        return
    from perennia.ui.app import ConfirmScreen

    def pick(control: str) -> None:
        app.pop()
        app.push(BlockBuilder(app, sport, None, control=control))
    app.push(ConfirmScreen(
        app, tr("Que tipo de treino?", "Which kind of workout?"),
        tr("ERG: {e}.  Manual: {m}.", "ERG: {e}.  Manual: {m}.",
           e=wm.control_help(sport, "erg"), m=wm.control_help(sport, "manual")),
        [(tr("Cancelar", "Cancel"), app.pop), (tr("Manual", "Manual"), lambda: pick("manual")),
         ("ERG", lambda: pick("erg"))], default=2, buttons=True, cancel=app.pop))


class BlockBuilder(EditScreen):
    """Ver o módulo. O tipo do treino (ERG ou Manual) decide as vistas: no
    ciclismo, ERG é por zonas de potência; manual é por FC, RPE ou níveis do
    rolo (para os rolos que não aceitam comandos)."""
    SEARCH = False            # escreve-se texto aqui: sem a pesquisa
    KEY_SCOPE = "builder"

    TABBED = True
    AGENT = True
    PAL_H = 40
    HEAD_ROW_H = 30           # a segunda linha do cabeçalho (o objetivo do treino)
    HEAD_VALUE_X = 230        # onde começam o nome e o objetivo (os dois no mesmo sítio)

    def __init__(self, app, sport: str, wid: str | None, control: str | None = None,
                 plan_day=None):
        self.sport = sport
        self.wid = wid
        self.plan_day = plan_day          # vindo do calendário: ao guardar, fica planeado
        self.name, self.desc, mode, self.blocks = load_blocks(app.db, sport, wid)
        meta = wm.get(app.db, sport, wid)
        self.control = control or meta["control"]
        if sport == "swimming":
            self.control = "manual"
        self.modes = list(wm.modes(sport, self.control))
        mode = meta["mode"] or mode
        for b, extra in zip(self.blocks, meta.get("blocks") or []):
            if isinstance(extra, dict):
                b.extra.update({k: v for k, v in extra.items() if v is not None})
        self.levels = wm.levels(app.db)
        # os aparelhos sem controlo (Definições → Desportos → Sessões Não ERG)
        self.limits = wm.device_limits(app.db)
        self._clamp_blocks()
        from perennia.core import objectives as ob
        from perennia.core import tags as tags_mod
        self.wtype = tags_mod.workout_type(app.db, sport, wid)     # None: pelo esforço
        saved = ob.stored(app.db, sport, wid)
        self.wgoal = saved.get("goal") or ob.library_goal(self.name)
        for b, g in zip(self.blocks, saved.get("blocks") or []):
            b.goal = (g or {}).get("goal", "") if isinstance(g, dict) else ""
        # os objetivos são os do próprio treino: o que a ficha mostra é o que está
        # aqui; o que ainda não foi escrito vem sugerido pela estrutura (editável)
        try:
            ctx0 = it.Context.from_db(app.db, sport)
            suggested = ob.build(app.db, sport, wid, self.name, self.blocks, ctx0)
            for b, rb in zip(self.blocks, suggested.raw_blocks):
                if not b.goal:
                    b.goal = rb.goal
            if not self.wgoal:
                self.wgoal = suggested.goal
        except Exception:
            pass
        self.mode = mode if mode in self.modes else self.modes[0]
        self.ctx = it.Context.from_db(app.db, sport)
        self.sel = 0 if self.blocks else -1
        self.drag: dict | None = None
        self.repeat_n = 4
        self.dirty = False
        self._rects: list = []
        self._labels: list = []               # as etiquetas de cada bloco (ver _block_label)
        super().__init__(app)
        self.tab = self.modes.index(self.mode)
        if self.tabs is not None:
            self.tabs.select(self.tab)
        b = self.batch = pyglet.graphics.Batch()
        self.canvas_bg = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL, batch=b)
        self.pal = []
        self.pal_notes = []
        for name, pct in PALETTE:
            r = pyglet.shapes.Rectangle(0, 0, 10, 10, color=PANEL2, batch=b)
            lab = make_label(self._pal_text(name), font_size=10, bold=True, color=TEXT,
                             anchor_x="center", anchor_y="center", batch=b)
            self.pal.append((name, pct, r, lab))
            # por baixo do nome: o nome da zona e o intervalo dela, na vista escolhida
            self.pal_notes.append(make_label(self._pal_note(name), font_size=8, color=TEXT,
                                             anchor_x="center", anchor_y="center", batch=b))
        self.ghost = pyglet.shapes.Rectangle(0, 0, 10, 10, color=ACCENT[:3], batch=b)
        self.ghost.opacity = 0
        self.insert_mark = pyglet.shapes.Rectangle(0, 0, 3, 10, color=ACCENT[:3], batch=b)
        self.insert_mark.opacity = 0
        self.summary = make_label("", font_size=11, color=TEXT, anchor_y="top", batch=b,
                                  multiline=True, width=300)
        self.axis = [make_label("", font_size=9, color=DIM, anchor_x="right",
                                anchor_y="center", batch=b) for _ in range(6)]
        self.grid = [pyglet.shapes.Rectangle(0, 0, 10, 1, color=GRID, batch=b)
                     for _ in range(6)]
        self.time_labels = [make_label("", font_size=9, color=DIM, anchor_x="center",
                                       anchor_y="top", batch=b) for _ in range(7)]
        self.zone_bar = [pyglet.shapes.Rectangle(0, 0, 0, 8, color=c, batch=b)
                         for c in it.ZONE_COLORS]
        self._layout()
        self.redraw()

    # ----------------------------------------------------------- separadores

    def has_gpx_tab(self) -> bool:
        """O GPX Conversor: nos treinos manuais de ciclismo e de corrida."""
        return getattr(self, "control", "erg") == "manual" and \
            getattr(self, "sport", "") in ("cycling", "running")

    def tab_labels(self) -> list[str]:
        modes = getattr(self, "modes", None) or ["power"]
        labels = [wm.mode_label(m) if m == "level" else it.mode_name(m) for m in modes]
        if self.has_gpx_tab():
            labels.append(tr("GPX Conversor", "GPX Converter"))
        return labels

    def on_tab(self) -> None:
        if self.has_gpx_tab() and self.tab >= len(self.modes):
            # a tab do conversor abre a janela; a vista fica a que estava
            self.tab = self.modes.index(self.mode)
            if self.tabs is not None:
                self.tabs.select(self.tab)
            from perennia.ui.gpx_convert_screens import GpxConverter
            self.app.push(GpxConverter(self.app, self))
            return
        # mudar de vista não mexe no treino: não conta como alteração
        self.mode = self.modes[self.tab % len(self.modes)]
        for (name, pct, r, lab), note in zip(self.pal, self.pal_notes):
            lab.text = self._pal_text(name)
            note.text = self._fit_note(self._pal_note(name), r.width, note.font_size)
        self.redraw()

    # zonas: limites em % do limiar (como as de potência)
    ZONE_EDGES = {"Z1": (0, 55), "Z2": (56, 75), "Z3": (76, 90), "Z4": (91, 105),
                  "Z5": (106, 120), "Z6": (121, 150)}

    def _value(self, pct: float) -> str:
        """Um valor na vista escolhida (W, bpm, RPE, ritmo ou nível)."""
        if self.mode == "level":
            return tr("nível {n}", "level {n}", n=wm.level_of(pct, self.ctx.ftp_w, self.levels))
        return self.ctx.short(self.mode, pct)

    def _pal_note(self, name: str) -> str:
        if name not in self.ZONE_EDGES:
            return {"rest": tr("recuperar", "recover"), "ramp": tr("sobe ou desce", "up or down"),
                    "free": tr("sem alvo · ERG desligado", "no target · ERG off")
                    if self.sport == "cycling" else tr("sem alvo", "no target")}.get(name, "")
        lo, hi = self.ZONE_EDGES[name]
        zname = it.zone_name(int(name[1]))
        mode = getattr(self, "mode", "power")
        ctx = getattr(self, "ctx", None)
        if ctx is None:
            return zname
        if mode == "power":
            rng = f"{ctx.watts(max(lo, 1))}–{ctx.watts(hi)} W"
        elif mode == "pace":
            fast, slow = ctx.short("pace", hi), ctx.short("pace", max(lo, 30))
            rng = f"{fast}–{slow}"
        elif mode == "level":
            rng = tr("níveis {a}–{b}", "levels {a}–{b}",
                     a=wm.level_of(max(lo, 1), ctx.ftp_w, getattr(self, "levels",
                                                                  wm.levels(self.app.db))),
                     b=wm.level_of(hi, ctx.ftp_w, getattr(self, "levels", wm.levels(self.app.db))))
        else:
            rng = f"{ctx.short(mode, max(lo, 40))}–{ctx.short(mode, hi)}"
        return f"{zname} · {rng}"

    @staticmethod
    def _fit_note(text: str, width: float, size: int) -> str:
        """A nota da paleta tem de caber no quadrado: tira primeiro a % e depois
        o nome da zona."""
        from perennia.ui.widgets import text_px

        def fits(t):
            return text_px(t, size) <= width - 10
        if fits(text):
            return text
        parts = text.split(" · ")
        for cand in (" · ".join(p for p in parts if "%" not in p or "W" in p or "bpm" in p),
                     parts[-1]):
            if fits(cand):
                return cand
        from perennia.ui.widgets import fit_text
        return fit_text(parts[-1], width - 10, size)

    def _pal_text(self, name: str) -> str:
        if name in ("rest",):
            return tr("Descanso", "Rest")
        if name == "ramp":
            return tr("Rampa", "Ramp")
        if name == "free":
            return "Free ride"
        return name

    # ---------------------------------------------------------------- layout

    def content_top(self, h: int) -> int:
        return int(getattr(self, "_list_top", h * 0.36))

    def _list_width(self, w: int) -> int:
        return int(getattr(self, "_list_w", w - 96))

    LIST_BOTTOM = 76          # acima da faixa de baixo (Voltar, Guardar)
    BELOW_CHART = 44          # as horas e a barra das zonas, entre o gráfico e a lista

    def _plan_list(self, w: int, h: int, chart_top: float) -> None:
        """A lista do bloco fica por baixo do gráfico, com as descrições à
        frente das opções: numa coluna ao centro se couber (o gráfico fica com
        o resto), senão em duas colunas a toda a largura."""
        lv = self.list
        # sempre o mesmo lugar, seja qual for o bloco (o gráfico não salta):
        # as linhas que o bloco mais completo deste desporto tem
        n = max(self.max_rows(), len([it for it in lv.items
                                      if not it.button and not it.head]))
        avail = chart_top - self.LIST_BOTTOM
        cols, rows, row_h = 2, -(-n // 2), ROW_H
        for rh in (32, 29, 26):                    # numa coluna, com linhas mais baixas
            if avail - n * rh - self.BELOW_CHART >= max(200.0, avail * 0.36):
                cols, rows, row_h = 1, n, rh
                break
        width = min(1000, w - 96) if cols == 1 else w - 96
        lv.row_h = row_h
        self._list_top = self.LIST_BOTTOM + rows * row_h
        self._list_w = width
        lv.max_columns = cols
        lv.detail_below = False
        lv.width = width
        lv.x = (w - width) / 2 if cols == 1 else 48
        lv.y = self._list_top - row_h / 2
        lv.set_visible_rows(rows)

    def _speed_set(self, blk) -> bool:
        return self.sport == "running" and self.control == "manual" and \
            bool(blk.extra.get("speed_kmh"))

    def _block_km(self, blk) -> str:
        """A distância do bloco, pela velocidade da passadeira (ou pelo ritmo)."""
        return f"{self._block_m(blk) / 1000:.2f} km"

    def _block_m(self, blk) -> float:
        if blk.dur_type == "distance":
            return float(blk.dur)
        v = blk.extra.get("speed_kmh")
        mps = v / 3.6 if v else self.ctx.speed_mps(blk.mid() if blk.lo is not None else 60)
        return mps * blk.dur

    def _total_m(self) -> float:
        """A distância do treino de corrida: a dos blocos por distância e, nos
        por tempo, a velocidade da passadeira (ou o ritmo) × o tempo."""
        return sum(self._block_m(b) for b in self.blocks)

    def _to_time(self, b) -> None:
        """Com velocidade, um bloco por distância passa a tempo (a mesma distância)."""
        v = b.extra.get("speed_kmh")
        if v and b.dur_type == "distance":
            b.dur = max(10.0, round(b.dur / (v / 3.6)))
            b.dur_type = "time"

    def _clamp_blocks(self) -> None:
        """Um treino feito antes de mudar os limites fica dentro deles."""
        lim = self.limits
        for b in getattr(self, "blocks", []):
            ex = b.extra
            if ex.get("resistance"):
                ex["resistance"] = max(1, min(lim["rower_levels"], int(ex["resistance"])))
            if ex.get("speed_kmh"):
                ex["speed_kmh"] = min(lim["treadmill_max_kmh"], float(ex["speed_kmh"]))
            if ex.get("incline_pct"):
                ex["incline_pct"] = min(lim["treadmill_max_incline"], float(ex["incline_pct"]))

    def max_rows(self) -> int:
        """As linhas do bloco mais completo (uma rampa) neste desporto."""
        n = 10                    # título, tipo, objetivo, mensagem, duração, início, fim,
        #                           alvo e as 2 ações (apagar é com Del, no rodapé)
        if self.sport != "cycling":
            n += 1                # duração por tempo ou distância
        if self.sport == "cycling":
            n += 1                # cadência alvo
        if self.sport == "running" and self.control == "manual":
            n += 3                # velocidade, inclinação e a distância calculada
        if self.sport == "rowing":
            n += 2                # resistência e voga
        return n

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        # em cima, por baixo dos separadores: o nome e o objetivo do treino
        # o nome e o objetivo do treino: uma linha por baixo da outra
        head_y = h - 98 - 34 - 12
        self.list.head_y, self.list.head_x, self.list.head_w = head_y, 48, w - 96
        self.list.head_stack = True
        self.list.head_value_x = self.HEAD_VALUE_X     # nome e objetivo alinhados à esquerda
        pal_top = head_y - 14 - self.HEAD_ROW_H * 2         # tipo, nome e objetivo
        n = len(self.pal)
        pw = (w - 96 - (n - 1) * 6) / n
        for i, ((_n, _p, r, lab), note) in enumerate(zip(self.pal, self.pal_notes)):
            r.x, r.y, r.width, r.height = 48 + i * (pw + 6), pal_top - self.PAL_H, pw, self.PAL_H
            lab.x, lab.y = r.x + pw / 2, r.y + self.PAL_H / 2 + 7
            note.x, note.y = r.x + pw / 2, r.y + 10
            note.font_size = 8 if pw > 110 else 7
            note.text = self._fit_note(self._pal_note(_n), pw, note.font_size)
            pct = dict(PALETTE)[_n]
            r.color = it.zone_color(pct)[:3] if pct else PANEL2
        self.cx0, self.cx1 = 96, w - 48
        self.cy1 = pal_top - self.PAL_H - 14
        self._plan_list(w, h, self.cy1)
        self.cy0 = self._list_top + self.BELOW_CHART
        self.canvas_bg.x, self.canvas_bg.y = self.cx0, self.cy0
        self.canvas_bg.width, self.canvas_bg.height = self.cx1 - self.cx0, self.cy1 - self.cy0
        # o resumo (duração, carga, IF) vai no subtítulo; a distribuição pelas
        # zonas é uma barra fina logo por baixo do gráfico, da largura dele
        self.summary.x, self.summary.y = -3000, -3000
        for r in self.zone_bar:
            r.x, r.y, r.height = self.cx0, self._list_top + 12, 6

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout()
        self.redraw()

    # ----------------------------------------------------------- geometria

    def y_max(self) -> float:
        top = max([b.lo or 0 for b in self.blocks] + [b.end_pct or 0 for b in self.blocks] + [0])
        return max(150.0, top + 15)

    def x_of(self, secs: float, total: float) -> float:
        return self.cx0 + (self.cx1 - self.cx0) * secs / max(total, 1.0)

    def y_of(self, pct: float) -> float:
        return self.cy0 + (self.cy1 - self.cy0) * max(0.0, pct) / self.y_max()

    def pct_at(self, y: float) -> float:
        return max(30.0, min(200.0, (y - self.cy0) / max(1, self.cy1 - self.cy0) * self.y_max()))

    def spans(self) -> tuple[list[tuple[float, float]], float]:
        out, t = [], 0.0
        for b in self.blocks:
            s = block_seconds(b, self.ctx)
            out.append((t, t + s))
            t += s
        return out, max(t, 600.0)

    def block_at(self, x: float, y: float) -> tuple[int, str] | None:
        if not (self.cx0 <= x <= self.cx1 and self.cy0 - 4 <= y <= self.cy1 + 4):
            return None
        spans, total = self.spans()
        for i, (a, b) in enumerate(spans):
            x0, x1 = self.x_of(a, total), self.x_of(b, total)
            if x0 <= x <= x1 + 2:
                blk = self.blocks[i]
                if x1 - x <= EDGE_PX:
                    return i, "resize"
                frac = (x - x0) / max(1.0, x1 - x0)
                pct = blk.mid() if blk.lo is None else (
                    blk.lo + ((blk.end_pct or blk.lo) - blk.lo) * frac)
                top = self.y_of(pct)
                if abs(y - top) <= EDGE_PX and blk.lo is not None:
                    return i, ("top_lo" if blk.ramp and frac < 0.5 else
                               "top_hi" if blk.ramp else "top")
                if y <= top + 2:
                    return i, "move"
                return i, "move"
        return None

    def insert_index(self, x: float) -> int:
        spans, total = self.spans()
        for i, (a, b) in enumerate(spans):
            if x < (self.x_of(a, total) + self.x_of(b, total)) / 2:
                return i
        return len(self.blocks)

    # ---------------------------------------------------------------- desenho

    def _rect(self, i: int):
        while len(self._rects) <= i:
            self._rects.append(pyglet.shapes.Rectangle(0, 0, 1, 1, color=(80, 80, 80),
                                                       batch=self.batch))
        return self._rects[i]

    # o que se escreve no meio de cada bloco, de cima para baixo (tamanho da letra)
    LINES = (("zone", 11), ("value", 18), ("dur", 13), ("cad", 11))

    def _block_label(self, i: int) -> dict:
        while len(self._labels) <= i:
            self._labels.append({k: make_label("", font_size=size, bold=k in ("zone", "value"),
                                               color=(20, 22, 28, 255), anchor_x="center",
                                               anchor_y="top", batch=self.batch)
                                 for k, size in self.LINES})
        return self._labels[i]

    def block_texts(self, blk) -> dict[str, str]:
        """O que aparece no meio do bloco: a zona, o valor na vista escolhida
        (numa rampa, a média), a duração e a cadência alvo."""
        dur = hms(blk.dur) if blk.dur_type == "time" else (
            f"{blk.dur / 1000:g} km" if blk.dur >= 1000 else f"{blk.dur:.0f} m")
        cad = blk.extra.get("cadence_lo")
        out = {"dur": dur, "cad": f"{cad} rpm" if cad else ""}
        if blk.lo is None:
            out.update(zone=tr("Descanso", "Rest") if blk.kind == "rest" else "Free ride",
                       value="")
            return out
        z = it.zone(blk.mid())
        out["zone"] = f"Z{z} · " + (tr("média", "avg") if blk.ramp else it.zone_name(z))
        out["value"] = self._value(blk.mid())
        if self.mode == "pace":                    # o ritmo leva a unidade
            out["value"] += {"running": " /km", "swimming": " /100 m",
                             "rowing": " /500 m"}.get(self.sport, "")
        return out

    def _place_block_label(self, lab: dict, blk, x0: float, w: float) -> None:
        """Ao centro do bloco, maior; num bloco estreito ou baixo, só o que cabe."""
        texts = self.block_texts(blk)
        if w >= 92:
            keys = ["zone", "value", "dur", "cad"]
            sizes = {"zone": 11, "value": 18, "dur": 13, "cad": 11}
        elif w >= 56:
            keys = ["value", "dur"]
            sizes = {"value": 13, "dur": 11}
        elif w >= 30:
            keys = ["dur"]
            sizes = {"dur": 10}
        else:
            keys, sizes = [], {}
        keys = [k for k in keys if texts.get(k)]
        if blk.lo is None and "zone" not in keys and w >= 56:
            keys.insert(0, "zone")
            sizes["zone"] = 10
        for k in keys:                      # a letra encolhe até caber na largura
            while sizes[k] > 8 and text_px(texts[k], sizes[k], k in ("zone", "value")) > w - 10:
                sizes[k] -= 1
        heights = {k: sizes[k] + 7 for k in keys}
        total = sum(heights.values())
        lo = blk.lo if blk.lo is not None else 50.0
        hi = blk.end_pct if blk.lo is not None and blk.ramp else lo
        inside_top = self.y_of(min(lo, hi or lo))
        inner = inside_top - self.cy0
        if total + 8 <= inner:
            y = self.cy0 + inner / 2 + total / 2           # ao centro do bloco
            ink = (20, 22, 28, 255)
        else:
            y = self.y_of(max(lo, hi or lo)) + total + 6   # não cabe: por cima do bloco
            y = min(y, self.cy1 - 2)                       # sem passar do gráfico
            ink = TEXT
        for k, label in lab.items():
            if k not in keys:
                label.text = ""
                continue
            label.text = texts[k]
            label.font_size = sizes[k]
            label.color = ink
            label.x, label.y = x0 + w / 2, y
            y -= heights[k]

    def redraw(self) -> None:
        spans, total = self.spans()
        n = 0
        nl = 0
        for i, (blk, (a, b)) in enumerate(zip(self.blocks, spans)):
            x0, x1 = self.x_of(a, total), self.x_of(b, total)
            w = max(2.0, x1 - x0 - 2)
            if i == self.sel:                          # contorno do bloco escolhido
                r = self._rect(n)
                n += 1
                top = max(self.y_of(blk.lo or 50), self.y_of(blk.end_pct or blk.lo or 50))
                r.x, r.y, r.width, r.height = x0 - 2, self.cy0 - 3, w + 4, top - self.cy0 + 5
                r.color, r.opacity = ACCENT[:3], 255
            slices = 8 if blk.ramp else 1
            for k in range(slices):
                frac = (k + 0.5) / slices
                if blk.lo is None:
                    pct, color = 50.0, (168, 176, 188)
                else:
                    pct = blk.lo + ((blk.end_pct or blk.lo) - blk.lo) * frac
                    color = it.zone_color(pct)
                r = self._rect(n)
                n += 1
                sw = w / slices
                r.x, r.y = x0 + k * sw, self.cy0
                r.width, r.height = max(1.0, sw + (0.5 if k < slices - 1 else 0)), \
                    max(2.0, self.y_of(pct) - self.cy0)
                r.color, r.opacity = color[:3], 255 if i == self.sel else 225
            self._place_block_label(self._block_label(nl), blk, x0, w)
            nl += 1
        for r in self._rects[n:]:
            r.opacity = 0
            r.width = 0
        for lab in self._labels[nl:]:
            for label in lab.values():
                label.text = ""
        # eixo: limites das zonas na vista escolhida
        ym = self.y_max()
        for k, (g, lab) in enumerate(zip(self.grid, self.axis)):
            pct = it.ZONE_BOUNDS[k] if k < len(it.ZONE_BOUNDS) else None
            if pct is None or pct > ym:
                g.opacity = 0
                lab.text = ""
                continue
            y = self.y_of(pct)
            g.x, g.y, g.width, g.opacity = self.cx0, y, self.cx1 - self.cx0, 255
            lab.x, lab.y = self.cx0 - 6, y
            lab.text = self._value(pct) if self.mode != "power" else f"{pct}%"
        for k, lab in enumerate(self.time_labels):
            secs = total * k / (len(self.time_labels) - 1)
            lab.text = hms(secs)
            lab.x, lab.y = self.x_of(secs, total), self.cy0 - 4
        est = estimate(self.blocks, self.ctx)
        meters = self._total_m() if self.sport == "running" else est["meters"]
        dist = f" · {meters / 1000:.2f} km" if meters else ""
        load = "TSS" if self.sport == "cycling" else tr("Carga", "Load")
        self.summary.text = (
            f"{tr('Duração', 'Duration')} ≈ {hms(est['seconds'])}{dist}\n"
            f"{load} ≈ {est['tss']:.0f} · IF {est['if']:.2f}\n"
            f"{len(self.blocks)} {tr('blocos', 'blocks')} · {tr('vista', 'view')}: "
            f"{it.mode_name(self.mode)}")
        tot = sum(est["zones"]) or 1.0
        x = self.cx0
        width = self.cx1 - self.cx0
        for r, secs in zip(self.zone_bar, est["zones"]):
            r.x = x
            r.width = width * secs / tot
            x += r.width
        # (o impacto na longevidade e o veredicto do Treinador ficavam apagados aqui)
        self.chrome.subtitle.text = (f"{wm.control_name(self.control)} · " if self.sport != "gym"
                                     else "") + self.summary.text.replace("\n", "  ·  ") \
            + self._longevity_text() + self._coach_text()

    def draw(self) -> None:
        super().draw()
        self.batch.draw()

    # ------------------------------------------------------------------- lista

    def enter(self) -> None:
        blk = self.blocks[self.sel] if 0 <= self.sel < len(self.blocks) else None
        rows: list[Item] = []
        if blk is not None:
            kinds = self._kind_names()
            rows += [
                Item(tr("Bloco {i} de {n}", "Block {i} of {n}", i=self.sel + 1,
                        n=len(self.blocks)), header=True,
                     detail=tr("←/→ outro bloco", "←/→ another block")),
                Item(tr("Tipo", "Kind"), value=kinds.get(blk.kind, blk.kind), data="cyc:kind",
                     detail=tr("←/→ aquecimento, trabalho, descanso, retorno à calma",
                               "←/→ warm-up, work, rest, cool-down")),
                Item(tr("Objetivo do bloco", "Block goal"), value=blk.goal or "—",
                     data="text:goal", action=lambda: self._edit_goal("goal"),
                     detail=tr("Enter edita numa janela · aparece na sessão",
                               "Enter edits in a window · shown in the session")),
                Item(tr("Mensagem", "Cue"), value=(blk.cue or "") + "▏", data="text:cue",
                     detail=tr("aparece na sessão no início do bloco",
                               "shown in the session when the block starts")),
            ]
            locked = self._speed_set(blk)
            if self.sport != "cycling" and locked:
                # passadeira manual com velocidade: o bloco é por tempo e a
                # distância sai da velocidade (não se mexe)
                rows.append(Item(tr("Duração por", "Duration by"), value=tr("tempo", "time"),
                                 detail=tr("a distância vem da velocidade do bloco",
                                           "the distance comes from the block speed"),
                                 enabled=False))
            elif self.sport != "cycling":
                rows.append(Item(tr("Duração por", "Duration by"),
                                 value=tr("tempo", "time") if blk.dur_type == "time"
                                 else tr("distância", "distance"), data="cyc:dur_type"))
            dur = hms(blk.dur) if blk.dur_type == "time" else f"{blk.dur:.0f} m"
            rows.append(Item(tr("Duração", "Duration"), value=dur, data="num:dur",
                             detail=tr("arrasta a aresta direita, ou ←/→",
                                       "drag the right edge, or ←/→")))
            if blk.lo is None:
                rows.append(Item(tr("Intensidade", "Intensity"), value="Free ride",
                                 data="cyc:free", detail=tr("sem alvo · ←/→ dá-lhe um alvo",
                                                            "no target · ←/→ gives it a target")))
            else:
                rows.append(Item(tr("Início" if blk.ramp else "Intensidade",
                                    "Start" if blk.ramp else "Intensity"),
                                 value=self._text(blk.lo), data="num:lo",
                                 detail=f"Z{it.zone(blk.lo)} · {it.zone_name(it.zone(blk.lo))}"))
                rows.append(Item(tr("Fim (rampa)", "End (ramp)"),
                                 value=self._text(blk.end_pct) if blk.ramp
                                 else tr("igual", "same"), data="num:hi"))
                tol = blk.extra.get("tol") or 0
                rows.append(Item(tr("Alvo", "Target"),
                                 value=tr("exato", "exact") if not tol else
                                 tr("intervalo ± {t} %", "range ± {t} %", t=f"{tol:g}"),
                                 detail=tr("←/→ 0 = exato · ±1 a ±15 % deixa oscilar",
                                           "←/→ 0 = exact · ±1 to ±15 % lets it float"),
                                 data="num:tol"))
            if self.sport == "cycling":
                c = blk.extra.get("cadence_lo")
                rows.append(Item(tr("Cadência alvo", "Target cadence"),
                                 value=f"{c} rpm" if c else tr("livre", "free"),
                                 detail=tr("←/→ ±5 rpm · 0 = livre", "←/→ ±5 rpm · 0 = free"),
                                 data="num:cad"))
            if self.sport == "running" and self.control == "manual":
                sp_ = blk.extra.get("speed_kmh")
                inc = blk.extra.get("incline_pct")
                rows.append(Item(tr("Velocidade da passadeira", "Treadmill speed"),
                                 value=f"{sp_:.1f} km/h" if sp_ else tr("pelo ritmo", "by pace"),
                                 detail=tr("←/→ ±0,1 · Shift ±1 · muda o ritmo do bloco",
                                           "←/→ ±0.1 · Shift ±1 · sets the block pace"),
                                 data="num:speed"))
                rows.append(Item(tr("Inclinação", "Incline"),
                                 value=f"{inc:.1f} %" if inc else "0 %",
                                 detail=tr("←/→ ±0,5 %", "←/→ ±0.5 %"), data="num:incline"))
                rows.append(Item(tr("Distância (calculada)", "Distance (worked out)"),
                                 value=self._block_km(blk),
                                 detail=tr("velocidade × tempo · ajusta-se sozinha",
                                           "speed × time · adjusts by itself"), enabled=False))
            if self.sport == "rowing":
                res = blk.extra.get("resistance")
                rows.append(Item(tr("Resistência", "Resistance"),
                                 value=str(res) if res else tr("não mexer", "leave it"),
                                 detail=tr("ERG: a app põe este nível · manual: mostra-o",
                                           "ERG: the app sets this level · manual: shows it"),
                                 data="num:resistance"))
                spm = blk.extra.get("rate")
                rows.append(Item(tr("Voga (remadas/min)", "Stroke rate (spm)"),
                                 value=f"{spm:.0f}" if spm else tr("livre", "free"),
                                 data="num:rate"))
            rows += [Item(tr("Duplicar o bloco (D)", "Duplicate the block (D)"),
                          action=self._duplicate),
                     Item(tr("Repetir os 2 últimos blocos", "Repeat the last 2 blocks"),
                          value=f"× {self.repeat_n}", data="cyc:repeat", action=self._repeat)]
        # o nome e o objetivo do treino ficam em cima (head), um por baixo do outro
        rows += [Item(tr("Tipo de treino", "Workout type"), value=self._wtype_text(),
                      data="cyc:wtype", head=True),
                 Item(tr("Nome do treino", "Workout name"), value=self.name + "▏",
                      data="text:name", head=True),
                 Item(tr("Objetivo do treino", "Workout goal"),
                      value=(self.wgoal[:70] + "…" if len(self.wgoal) > 71 else self.wgoal)
                      or tr("Enter escreve o objetivo (numa janela)",
                            "Enter writes the goal (in a window)"),
                      data="text:wgoal", head=True, action=lambda: self._edit_goal("wgoal")),
                 Item(tr("Treinador", "Coach"), button=True, action=self._coach),
                 Item(tr("Guardar", "Save") + (" •" if self.dirty else ""), action=self._save,
                      button=True, primary=True)]
        sport_name = {"cycling": tr("Ciclismo", "Cycling"), "rowing": tr("Remo", "Rowing"),
                      "running": tr("Corrida", "Running"),
                      "swimming": tr("Natação", "Swimming")}[self.sport]
        self.chrome.set(tr("Construtor de treinos", "Workout builder") + f" · {sport_name}"
                        + f" · {wm.control_name(self.control)}",
                        f"{wm.control_name(self.control)} · "
                        + self.summary.text.replace("\n", "  ·  ") + self._longevity_text()
                        + self._coach_text(),
                        tr("Arrasta blocos da paleta · ←/→ bloco · ↑↓ linha · +/− duração · "
                           "D duplicar · Del apagar · Tab vista · o tipo de treino também "
                           "etiqueta o .fit",
                           "Drag palette blocks · ←/→ block · ↑↓ row · +/− duration · "
                           "D duplicate · Del delete · Tab view · the workout type also "
                           "tags the .fit"))
        self.list.set_items(rows, keep_index=True)
        if hasattr(self, "pal"):          # a lista mudou de tamanho: o gráfico acompanha
            self._layout()
            self.redraw()

    @property
    def block(self) -> Block | None:
        return self.blocks[self.sel] if 0 <= self.sel < len(self.blocks) else None

    def changed(self) -> None:
        self.dirty = True
        self.redraw()
        self.enter()

    def _coach(self) -> None:
        """O feedback do Treinador ao treino que está no construtor (só quando o pedes)."""
        from perennia.ui import coach_screens
        coach_screens.builder_feedback(self.app, self)

    def _coach_text(self) -> str:
        """Depois de pedires feedback uma vez, o veredicto acompanha as alterações (ao vivo)."""
        from perennia.ui import coach_screens
        text = coach_screens.live_verdict(self.app, self)
        return ("  ·  " + text) if text else ""

    def _longevity_text(self) -> str:
        """O que este treino acrescentaria ao índice de longevidade (se o fizesses hoje):
        refaz-se só quando os blocos mudam."""
        sig = tuple((b.kind, b.dur_type, round(b.dur), b.lo, b.hi) for b in self.blocks)
        if getattr(self, "_lg_sig", None) != sig:
            self._lg_sig = sig
            try:
                from perennia.core import longevity as lg
                if getattr(self, "_lg_doses", None) is None:
                    self._lg_doses = lg.all_doses(self.app.db)
                imp = lg.impact_of(self.app.db, lg.blocks_mins(self.blocks, self.sport),
                                   sport=self.sport, doses=self._lg_doses)
                text = lg.impact_text(imp)
                self._lg_text = ("  ·  " + tr("Longevidade", "Longevity") + " " + text) \
                    if text else ""
            except Exception:
                self._lg_text = ""
        return self._lg_text

    # ----------------------------------------------------------- campos

    def cycle(self, field: str, step: int) -> None:
        b = self.block
        if field == "repeat":
            self.repeat_n = max(2, min(20, self.repeat_n + (1 if step > 0 else -1)))
            return
        if b is None:
            return
        if field == "wtype":
            from perennia.core import tags as tags_mod
            order = [None, *tags_mod.TYPE_KEYS]
            self.wtype = order[(order.index(self.wtype) + step) % len(order)]
            self.dirty = True
            self.enter()
            return
        if field == "kind":
            ks = ["warmup", "active", "rest", "cooldown"]
            b.kind = ks[(ks.index(b.kind) + step) % len(ks)] if b.kind in ks else "active"
        elif field == "dur_type":
            if self._speed_set(b):
                return            # com velocidade, a distância é calculada
            if b.dur_type == "time":
                b.dur_type, b.dur = "distance", float(SNAP_M.get(self.sport, 100) * 4)
            else:
                b.dur_type, b.dur = "time", 300.0
        elif field == "free":
            b.lo = 75.0
        self.dirty = True
        self.redraw()

    def _wtype_text(self) -> str:
        """O tipo escolhido, ou — se ninguém escolheu — o que os blocos sugerem."""
        from perennia.core import tags as tags_mod
        if self.wtype:
            return tags_mod.type_label(self.wtype)
        try:
            sug = tags_mod.type_label(tags_mod.suggest_for_blocks(self.blocks, self.sport))
        except Exception:
            sug = ""
        return tr("Automático · {s}", "Automatic · {s}", s=sug) if sug else \
            tr("Automático", "Automatic")

    def _text(self, pct: float) -> str:
        if self.mode == "level":
            lv = wm.level_of(pct, self.ctx.ftp_w, self.levels)
            return tr("nível {n} · ≈ {w} W", "level {n} · ≈ {w} W", n=lv,
                      w=f"{wm.level_watts(lv, self.levels):.0f}")
        return self.ctx.text(self.mode, pct)

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        b = self.block
        if b is None:
            return
        if field in ("lo", "hi") and self.mode == "level":
            cur = (b.lo if field == "lo" else b.end_pct) or 75.0
            lv = wm.level_of(cur, self.ctx.ftp_w, self.levels) + steps
            lv = max(1, min(self.levels["n"], lv))
            v = wm.pct_of_level(lv, self.ctx.ftp_w, self.levels)
            if field == "lo":
                b.lo = v
                if not b.ramp:
                    b.hi = None
            else:
                b.hi = v
            self.dirty = True
            self.redraw()
            return
        if field == "tol":
            b.extra["tol"] = max(0, min(15, (b.extra.get("tol") or 0) + steps))
        elif field == "cad":
            c = (b.extra.get("cadence_lo") or 85) + steps * 5
            if not b.extra.get("cadence_lo") and steps < 0:
                c = 0
            b.extra["cadence_lo"] = b.extra["cadence_hi"] = None if c < 40 else min(130, c)
        elif field == "speed":
            cur = b.extra.get("speed_kmh") or round(3600 / max(1, self.ctx.pace(b.mid()) or 360), 1)
            v = max(3.0, min(self.limits["treadmill_max_kmh"],
                             round(cur + steps * (1.0 if big else 0.1), 1)))
            b.extra["speed_kmh"] = v
            # a velocidade dá o ritmo do bloco (e a cor da zona)
            b.lo = max(30.0, min(200.0, self.ctx.pct_from("pace", 3600 / v)))
            b.hi = None
            self._to_time(b)
        elif field == "incline":
            step = self.limits["treadmill_incline_step"]
            b.extra["incline_pct"] = max(0.0, min(self.limits["treadmill_max_incline"],
                                                  round((b.extra.get("incline_pct") or 0)
                                                        + steps * step, 2)))
        elif field == "rate":
            r = (b.extra.get("rate") or 22) + steps
            b.extra["rate"] = None if r < 14 else min(40, r)
        if field in ("tol", "cad", "speed", "incline", "rate"):
            self.dirty = True
            self.redraw()
            return
        if field == "dur":
            self._nudge_duration(steps * (6 if big else 1))
        elif field in ("lo", "hi"):
            cur = (b.lo if field == "lo" else b.end_pct) or 75.0
            v = max(30.0, min(200.0, cur + steps * (5 if big else 1)))
            if field == "lo":
                b.lo = v
                if not b.ramp:
                    b.hi = None
            else:
                b.hi = v
        elif field == "resistance":
            cur = b.extra.get("resistance") or 5
            b.extra["resistance"] = max(1, min(self.limits["rower_levels"], cur + steps))
        self.dirty = True
        self.redraw()

    def num_set(self, field: str, value) -> None:
        b = self.block
        if b is None or value is None:
            return
        if field == "dur":
            # escrito: minutos no tempo, metros na distância
            b.dur = max(10.0, value * 60) if b.dur_type == "time" else max(25.0, value)
        elif field in ("lo", "hi"):
            if self.mode == "level":
                lv = max(1, min(self.levels["n"], int(value)))
                pct = wm.pct_of_level(lv, self.ctx.ftp_w, self.levels)
            else:
                pct = self.ctx.pct_from(self.mode, value) if self.mode != "power" else value
            if field == "lo":
                b.lo = max(30.0, min(200.0, pct))
            else:
                b.hi = max(30.0, min(200.0, pct))
        elif field == "resistance":
            b.extra["resistance"] = max(1, min(self.limits["rower_levels"], int(value)))
        elif field == "cad":
            b.extra["cadence_lo"] = b.extra["cadence_hi"] = int(value) if value >= 40 else None
        elif field == "tol":
            b.extra["tol"] = max(0, min(15, float(value)))
        elif field == "speed":
            v = max(3.0, min(self.limits["treadmill_max_kmh"], float(value)))
            b.extra["speed_kmh"] = v
            b.lo = max(30.0, min(200.0, self.ctx.pct_from("pace", 3600 / v)))
            b.hi = None
            self._to_time(b)
        elif field == "incline":
            step = self.limits["treadmill_incline_step"]
            b.extra["incline_pct"] = max(0.0, min(self.limits["treadmill_max_incline"],
                                                  round(round(float(value) / step) * step, 2)))
        elif field == "rate":
            b.extra["rate"] = int(value) if value >= 14 else None
        self.dirty = True
        self.redraw()

    def _edit_goal(self, field: str, extra: str = "") -> None:
        """Os objetivos (do treino e do bloco) escrevem-se numa janela."""
        if field == "wgoal":
            title, text, limit = tr("Objetivo do treino", "Workout goal"), self.wgoal, 300
            sub = self.name
        elif self.block is not None:
            title, text, limit = tr("Objetivo do bloco", "Block goal"), self.block.goal or "", 160
            sub = tr("Bloco {i} de {n}", "Block {i} of {n}", i=self.sel + 1, n=len(self.blocks))
        else:
            return

        def save(value: str) -> None:
            if field == "wgoal":
                self.wgoal = value
            elif self.block is not None:
                self.block.goal = value
            self.dirty = True
            self.enter()
        from perennia.ui.goal_popup import GoalPopup
        self.app.push(GoalPopup(self.app, title, sub, (text + extra)[:limit], limit, save))

    def text_input(self, field: str, text: str) -> None:
        if field in ("wgoal", "goal"):
            self._edit_goal(field, text)         # escrever abre a janela do objetivo
            return
        if field == "name":
            self.name += text
        elif self.block is not None:
            self.block.cue += text
        self.dirty = True
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "name":
            self.name = self.name[:-1]
        elif field in ("wgoal", "goal"):
            return                                # o objetivo edita-se na janela (Enter)
        elif self.block is not None:
            self.block.cue = self.block.cue[:-1]
        self.dirty = True
        self.enter()

    def _nudge_duration(self, steps: int) -> None:
        b = self.block
        if b is None:
            return
        if b.dur_type == "time":
            unit = SNAP_S if b.dur < 120 else 30
            b.dur = max(10.0, b.dur + steps * unit)
        else:
            b.dur = max(25.0, b.dur + steps * SNAP_M.get(self.sport, 100))

    # ----------------------------------------------------------- ações

    def add_block(self, name: str, index: int | None = None) -> None:
        pct = dict(PALETTE).get(name)
        prev = self.block
        dur_type = prev.dur_type if prev is not None and self.sport != "cycling" else \
            ("distance" if self.sport == "swimming" else "time")
        dur = (300.0 if dur_type == "time" else float(SNAP_M.get(self.sport, 100) * 4))
        if name == "rest":
            blk = Block("rest", dur_type, 120.0 if dur_type == "time" else dur / 2, 45)
        elif name == "ramp":
            blk = Block("warmup", dur_type, dur, 55, 95)
        elif name == "free":
            blk = Block("active", dur_type, dur, None)
        else:
            blk = Block("active", dur_type, dur, float(pct))
        i = (self.sel + 1 if self.sel >= 0 else len(self.blocks)) if index is None else index
        self.blocks.insert(i, blk)
        self.sel = i
        self.changed()

    def _duplicate(self) -> None:
        b = self.block
        if b is None:
            return
        self.blocks.insert(self.sel + 1, replace(b, extra=dict(b.extra)))
        self.sel += 1
        self.changed()

    def _repeat(self) -> None:
        if len(self.blocks) < 2:
            return
        pair = self.blocks[-2:]
        for _ in range(self.repeat_n - 1):
            self.blocks += [replace(b, extra=dict(b.extra)) for b in pair]
        self.changed()

    def _delete(self) -> None:
        """Apagar o bloco escolhido — pergunta primeiro, numa janela."""
        blk = self.block
        if blk is None:
            return
        kinds = self._kind_names()
        dur = hms(blk.dur) if blk.dur_type == "time" else f"{blk.dur:.0f} m"
        self.app.confirm(
            tr("Apagar o bloco {i} de {n}?", "Delete block {i} of {n}?", i=self.sel + 1,
               n=len(self.blocks)),
            tr("{k} · {d}. Tens a certeza? (até guardares, Cancelar no construtor desfaz tudo)",
               "{k} · {d}. Are you sure? (until you save, leaving without saving undoes it)",
               k=kinds.get(blk.kind, blk.kind), d=dur),
            self._delete_now, yes=tr("Apagar o bloco", "Delete the block"))

    def _delete_now(self) -> None:
        if self.block is None:
            return
        del self.blocks[self.sel]
        self.sel = min(self.sel, len(self.blocks) - 1)
        self.changed()

    @staticmethod
    def _kind_names() -> dict[str, str]:
        return {"warmup": tr("Aquecimento", "Warm-up"), "active": tr("Trabalho", "Work"),
                "rest": tr("Descanso", "Rest"), "cooldown": tr("Retorno à calma", "Cool-down")}

    def _manual_cue(self, b) -> str:
        """No treino manual, o que pôr no aparelho vai na mensagem do bloco
        (aparece na sessão): o nível do rolo, a velocidade e a inclinação, a
        resistência e a voga."""
        bits = []
        if self.sport == "cycling" and self.mode == "level" and b.lo is not None:
            bits.append(tr("Nível {n}", "Level {n}",
                           n=wm.level_of(b.mid(), self.ctx.ftp_w, self.levels)))
        if self.sport == "running" and b.extra.get("speed_kmh"):
            bits.append(f"{b.extra['speed_kmh']:.1f} km/h")
        if self.sport == "running" and b.extra.get("incline_pct"):
            bits.append(tr("inclinação {i} %", "incline {i} %", i=f"{b.extra['incline_pct']:g}"))
        if self.sport == "rowing" and self.control == "manual" and b.extra.get("resistance"):
            bits.append(tr("resistência {r}", "resistance {r}", r=b.extra["resistance"]))
        if self.sport == "rowing" and b.extra.get("rate"):
            bits.append(f"{b.extra['rate']:.0f} spm")
        if b.extra.get("tol") and b.lo is not None:
            bits.append(f"± {b.extra['tol']:g} %")
        return " · ".join(bits)

    def _save(self) -> None:
        if not self.blocks:
            self.app.message(tr("O treino não tem blocos.", "The workout has no blocks."))
            return
        import copy
        to_save = copy.deepcopy(self.blocks)
        for b in to_save:
            auto = self._manual_cue(b) if (self.control == "manual" or b.extra.get("tol")) \
                else ""
            base = (b.cue or "").split("  ·  ")[0] if "  ·  " in (b.cue or "") else (b.cue or "")
            b.cue = f"{base}  ·  {auto}" if auto and base else (auto or base)
        self.wid = save_blocks(self.app.db, self.sport, self.wid, self.name.strip() or
                               tr("Treino", "Workout"), self.desc, self.mode, to_save)
        wm.save(self.app.db, self.sport, self.wid, self.control, self.mode,
                [{k: b.extra.get(k) for k in ("tol", "speed_kmh", "incline_pct", "rate")}
                 for b in self.blocks])
        from perennia.core import objectives as ob
        ob.save(self.app.db, self.sport, self.wid, self.wgoal.strip(),
                [{"name": "", "goal": b.goal} for b in self.blocks])
        from perennia.core import tags as tags_mod
        tags_mod.set_workout_type(self.app.db, self.sport, self.wid, self.wtype)
        self.dirty = False
        if self.plan_day is not None:
            from perennia.ui.day_popups import plan_it
            plan_it(self.app, self.plan_day, self.sport, self.wid, self.name.strip())
        self.enter()
        self.app.workout_saved(self.name.strip(), self)

    # ----------------------------------------------------------- teclado

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self._field("text:") is None:
            if symbol in (key.LEFT, key.RIGHT) and self._field("num:") is None and \
                    self._field("cyc:") is None:
                if self.blocks:
                    self.sel = (self.sel + (1 if symbol == key.RIGHT else -1)) % len(self.blocks)
                    self.redraw()
                    self.enter()
                return True
            if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD, key.MINUS, key.NUM_SUBTRACT):
                self._nudge_duration(1 if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD) else -1)
                self.changed()
                return True
            if symbol == key.D:
                self._duplicate()
                return True
        if symbol == key.S and modifiers & key.MOD_CTRL:
            self._save()
            return True
        if self._field("text:") is None and symbol == key.DELETE:
            self._delete()
            return True
        return super().on_key(symbol, modifiers)

    def on_save(self) -> bool:
        self._save()
        return True

    def has_unsaved(self) -> bool:
        return self.dirty

    # --------------------------------------------------------------- rato

    def on_mouse(self, x: int, y: int) -> bool:
        for name, _pct, r, _lab in self.pal:
            if r.x <= x <= r.x + r.width and r.y <= y <= r.y + r.height:
                self.drag = {"what": "palette", "name": name, "x0": x, "y0": y, "moved": False}
                return True
        hit = self.block_at(x, y)
        if hit is not None:
            i, part = hit
            self.sel = i
            b = self.blocks[i]
            self.drag = {"what": part, "i": i, "x0": x, "y0": y, "dur0": b.dur,
                         "moved": False}
            self.redraw()
            self.enter()
            return True
        return super().on_mouse(x, y)

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        d = self.drag
        if d is None:
            return False
        d["moved"] = True
        what = d["what"]
        if what == "palette":
            self.ghost.opacity = 160
            self.ghost.x, self.ghost.y, self.ghost.width, self.ghost.height = x - 30, y - 14, 60, 28
            if self.cx0 <= x <= self.cx1 and self.cy0 <= y <= self.cy1:
                i = self.insert_index(x)
                spans, total = self.spans()
                xm = self.x_of(spans[i][0], total) if i < len(spans) else self.cx1
                self.insert_mark.x, self.insert_mark.y = xm - 1, self.cy0
                self.insert_mark.height = self.cy1 - self.cy0
                self.insert_mark.opacity = 255
            else:
                self.insert_mark.opacity = 0
            return True
        b = self.blocks[d["i"]]
        spans, total = self.spans()
        if what == "resize":
            a, _ = spans[d["i"]]
            secs = max(10.0, (x - self.cx0) / max(1, self.cx1 - self.cx0) * total - a)
            if b.dur_type == "time":
                unit = SNAP_S if secs < 120 else 30
                b.dur = max(10.0, round(secs / unit) * unit)
            else:
                meters = secs * self.ctx.speed_mps(b.mid())
                unit = SNAP_M.get(self.sport, 100)
                b.dur = max(float(unit), round(meters / unit) * unit)
        elif what in ("top", "top_lo", "top_hi"):
            pct = round(self.pct_at(y))
            if what == "top":
                b.lo = float(pct)
                b.hi = None
            elif what == "top_lo":
                b.lo = float(pct)
            else:
                b.hi = float(pct)
        elif what == "move":
            j = self.insert_index(x)
            i = d["i"]
            if j > i:
                j -= 1
            if j != i and 0 <= j < len(self.blocks):
                blk = self.blocks.pop(i)
                self.blocks.insert(j, blk)
                d["i"] = self.sel = j
        self.dirty = True
        self.redraw()
        return True

    def on_release(self, x: int, y: int) -> bool:
        d = self.drag
        self.drag = None
        self.ghost.opacity = 0
        self.insert_mark.opacity = 0
        if d is None:
            return False
        if d["what"] == "palette":
            inside = self.cx0 <= x <= self.cx1 and self.cy0 <= y <= self.cy1
            if d["moved"] and inside:
                self.add_block(d["name"], self.insert_index(x))
            elif not d["moved"]:
                self.add_block(d["name"])
            return True
        self.enter()
        return True

    def agent_data(self) -> dict:
        est = estimate(self.blocks, self.ctx)
        return {"desporto": self.sport, "vista": self.mode,
                "blocos": [{"tipo": b.kind, "duracao": b.dur, "por": b.dur_type,
                            "intensidade_pct": b.lo, "fim_pct": b.end_pct} for b in self.blocks],
                "estimativa": {k: est[k] for k in ("seconds", "meters", "tss", "if")}}
