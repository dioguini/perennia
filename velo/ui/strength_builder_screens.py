"""Construtor de treinos de força, por blocos (à maneira do «Strength Workout
Builder» do TrainingPeaks).

* **Cartão do treino** em cima: nome, hora de início, «Planear para» (um dia
  do calendário), **Guardar** e **▶ Começar**.
* **À esquerda**, o resumo do treino, que se vai escrevendo à medida que se
  prescreve (A1 Agachamento — 3 × 5 @ 100 kg…), com a duração e o volume
  previstos, e as instruções do treino.
* **Ao centro**, os blocos: pega do lado esquerdo (⋮⋮) para arrastar, ⋮ em
  cima à direita (converter, juntar exercício, notas, remover). Dentro, cada
  exercício com o rótulo (A1, B1, B2…), ⋮ (juntar parâmetro, pré-visualizar,
  notas do treinador, desligar do bloco, substituir, remover), «Ver
  histórico», as notas, e a tabela: uma coluna por parâmetro (▾ muda ou tira)
  e uma linha por série, com «–» onde ainda não há valor.
* **+ Adicionar bloco**: exercício único, superset, circuito, aquecimento ou
  retorno à calma.

Arrastar um bloco: para cima ou para baixo muda a ordem; largado em cima de
outro bloco junta-os (superset). Teclado: setas mexem na seleção, escrever
números preenche a célula, Backspace apaga, Enter abre o que está escolhido,
M abre o ⋮ do bloco/exercício, Alt+↑/↓ muda o bloco de sítio, Ctrl+S grava.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pyglet
import pyglet.shapes
from pyglet.window import key

from velo.core import gym
from velo.core import strength_builder as sb
from velo.core.i18n import tr
from velo.core.units import hms
from velo.gfx import theme as _theme
from velo.gfx.compat import label as make_label
from velo.ui.app import ConfirmScreen, Screen
from velo.ui.brief import wrap
from velo.ui.widgets import Item

ROW = {"bhead": 30, "exhead": 28, "notes": 20, "phead": 22, "set": 24, "addset": 24,
       "bfoot": 24, "gap": 12, "addblock": 40}
NUMERIC = set("0123456789.,")


class MenuPopup(ConfirmScreen):
    """Um ⋮: lista de opções numa janela pequena. Cada opção fecha a janela
    e faz o que diz."""

    def __init__(self, app, title: str, options: list[tuple[str, object]], sub: str = ""):
        n = max(2, len(options))
        self.H = min(560, 150 + n * 38)
        wrapped = [(lab, (lambda f=fn: (app.pop(), f()))) for lab, fn in options]
        super().__init__(app, title, sub, wrapped, default=0)


class StrengthBuilder(Screen):
    AGENT = True
    MAX_RECTS = 420
    MAX_LABELS = 520

    def __init__(self, app, mod: str = "strength", wid: str | None = None,
                 draft: bool = False, plan_day: date | None = None):
        self.mod, self.wid, self.draft = mod, wid, draft
        super().__init__(app)
        db = app.db
        from velo.core import strength as st
        wk = st.workout(db, wid) if wid else None
        self.name = (wk or {}).get("name") or (tr("Treino livre", "Free workout") if draft
                                              else tr("Novo treino de força",
                                                      "New strength workout"))
        if wk and wk.get("modality"):
            self.mod = wk["modality"]
        self.struct = sb.load(db, wid)
        self.plan_day = plan_day
        self.dirty = False
        self.saved_at = 0.0
        self.scroll = 0.0
        self.focus: tuple = ("addblock",) if not self.struct["blocks"] else ("name",)
        self.drag: dict | None = None
        self._typing = False
        self._armed: tuple | None = None
        self.list.y = -3000
        self._build()
        self.refresh()

    # ------------------------------------------------------------ construção

    def _build(self) -> None:
        P = _theme.P
        b = self.batch = pyglet.graphics.Batch()
        self.static = []
        # cartão do treino (faixa do topo)
        self.band = pyglet.shapes.Rectangle(0, 0, 1, 1, color=P.header, batch=b)
        self.rects = [pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.panel, batch=b)
                      for _ in range(self.MAX_RECTS)]
        self.labels = [make_label("", font_size=10, color=_theme.rgba(P.text), batch=b)
                       for _ in range(self.MAX_LABELS)]
        self.ghost = pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.accent, batch=b)
        self.ghost_l = make_label("", font_size=10, bold=True,
                                  color=_theme.rgba(P.accent_text), anchor_y="center", batch=b)
        self.mark = pyglet.shapes.Rectangle(0, 0, 0, 0, color=P.accent, batch=b)
        self._r = self._l = 0

    # pools: cada refresh volta a distribuir formas e etiquetas
    def _rect(self, x, y, w, h, color, opacity=255):
        if self._r >= len(self.rects):
            return None
        r = self.rects[self._r]
        self._r += 1
        r.x, r.y, r.width, r.height = x, y, max(0, w), max(0, h)
        r.color = color[:3]
        r.opacity = opacity
        return r

    def _label(self, text, x, y, size=10, color=None, bold=False, anchor_x="left",
               anchor_y="center"):
        if self._l >= len(self.labels):
            return None
        lab = self.labels[self._l]
        self._l += 1
        lab.text = text
        lab.x, lab.y = x, y
        lab.font_size = size
        lab.color = color if color is not None else _theme.rgba(_theme.P.text)
        try:
            lab.anchor_x, lab.anchor_y = anchor_x, anchor_y
        except Exception:
            pass
        try:
            lab.bold = bold
        except Exception:
            pass
        if hasattr(lab, "weight"):
            try:
                lab.weight = "bold" if bold else "normal"
            except Exception:
                pass
        return lab

    # --------------------------------------------------------------- geometria

    def _areas(self):
        w, h = self.app.window.width, self.app.window.height
        top = h - 26
        band_h = 84
        left_w = max(230, min(320, int(w * 0.26)))
        main_x = 48 + left_w + 20
        return {"w": w, "h": h, "band_top": top, "band_h": band_h,
                "left": (48, top - band_h - 14, left_w, 62),
                "main": (main_x, top - band_h - 14, w - 48 - main_x, 62)}

    def _rows(self) -> list[dict]:
        """As linhas do centro (sem posição): o que se desenha e o que se escolhe."""
        rows: list[dict] = []
        for bi, b in enumerate(self.struct["blocks"]):
            rows.append({"t": "bhead", "bi": bi})
            for ei, e in enumerate(b["exercises"]):
                rows.append({"t": "exhead", "bi": bi, "ei": ei})
                if e.get("notes") or self.focus == ("notes", bi, ei):
                    rows.append({"t": "notes", "bi": bi, "ei": ei})
                rows.append({"t": "phead", "bi": bi, "ei": ei})
                for si in range(len(e["sets"])):
                    rows.append({"t": "set", "bi": bi, "ei": ei, "si": si})
                rows.append({"t": "addset", "bi": bi, "ei": ei})
            if b["kind"] in ("superset", "circuit", "warmup", "cooldown") and \
                    len(b["exercises"]) > 1 or b["kind"] == "circuit":
                rows.append({"t": "bfoot", "bi": bi})
            rows.append({"t": "gap", "bi": bi})
        rows.append({"t": "addblock"})
        return rows

    def _cells(self, row: dict, x: float, w: float) -> list[tuple[tuple, float, float]]:
        """[(id, x, largura)] das zonas escolhíveis de uma linha."""
        t_ = row["t"]
        if t_ == "bhead":
            bi = row["bi"]
            out = [(("bmenu", bi), x + w - 34, 28)]
            b = self.struct["blocks"][bi]
            if b["kind"] == "circuit":
                out.insert(0, (("rounds", bi), x + w - 200, 70))
            return out
        if t_ == "exhead":
            bi, ei = row["bi"], row["ei"]
            return [(("exname", bi, ei), x + 30, w - 260), (("hist", bi, ei), x + w - 170, 100),
                    (("exmenu", bi, ei), x + w - 62, 28)]
        if t_ == "notes":
            return [(("notes", row["bi"], row["ei"]), x + 52, w - 70)]
        if t_ in ("phead", "set"):
            bi, ei = row["bi"], row["ei"]
            params = self.struct["blocks"][bi]["exercises"][ei]["params"]
            col_x, col_w = self._cols(x, w, len(params))
            if t_ == "phead":
                return [(("phead", bi, ei, k), col_x + k * col_w, col_w - 6)
                        for k in range(len(params))]
            out = [(("cell", bi, ei, row["si"], k), col_x + k * col_w, col_w - 6)
                   for k in range(len(params))]
            out.append((("delset", bi, ei, row["si"]), x + w - 30, 22))
            return out
        if t_ == "addset":
            return [(("addset", row["bi"], row["ei"]), x + 52, 110)]
        if t_ == "bfoot":
            return [(("brest", row["bi"]), x + 52, 220)]
        if t_ == "addblock":
            return [(("addblock",), x, 220)]
        return []

    @staticmethod
    def _cols(x: float, w: float, n: int) -> tuple[float, float]:
        col_x = x + 120
        col_w = min(130, (w - 120 - 40) / max(1, n))
        return col_x, col_w

    def _layout_rows(self):
        a = self._areas()
        mx, mtop, mw, mbottom = a["main"]
        y = mtop + self.scroll
        placed = []
        for row in self._rows():
            hgt = ROW[row["t"]]
            placed.append((row, y - hgt, hgt))
            y -= hgt
        self.content_h = mtop + self.scroll - y
        return placed

    # ---------------------------------------------------------------- desenho

    def refresh(self) -> None:
        P = _theme.P
        if hasattr(self, "list"):
            self._set_buttons()
        self._r = self._l = 0
        a = self._areas()
        w, h = a["w"], a["h"]
        dim, txt, faint = _theme.rgba(P.dim), _theme.rgba(P.text), _theme.rgba(P.faint)
        acc = _theme.rgba(P.accent)
        hd_txt, hd_dim = _theme.rgba(P.header_text), _theme.rgba(P.header_dim)
        # ---- cartão do treino (cabeçalho)
        bt, bh = a["band_top"], a["band_h"]
        self.band.x, self.band.y, self.band.width, self.band.height = 0, bt - bh, w, bh
        self.cell_geo: list[tuple[tuple, float, float, float, float]] = []
        name_sel = self.focus == ("name",)
        nm = self.name + ("▏" if name_sel else "")
        lab = self._label(wrap(nm, w * 0.45, 18, 1), 48, bt - 26, 18, hd_txt, True)
        self.cell_geo.append((("name",), 44, bt - 44, w * 0.48, 34))
        if name_sel:
            self._rect(44, bt - 46, w * 0.48, 2, P.accent)
        sub = [tr("Treino de força", "Strength workout"),
               gym.modality(self.mod).name,
               "≈ " + hms(sb.estimate_seconds(self.struct)) if self.struct["blocks"] else "",
               ]
        self._label(" · ".join(x for x in sub if x), 48, bt - 58, 10, hd_dim)
        # botões à direita: hora de início · planear · guardar · começar
        bx = w - 48
        buttons = [("start_session", tr("▶ Começar", "▶ Start"), P.good),
                   ("plan", tr("Planear: {d}", "Plan: {d}",
                               d=self.plan_day.strftime("%d/%m") if self.plan_day
                               else tr("—", "—")), _theme.mix(P.header, (255, 255, 255), 0.14)),
                   ("start", tr("Início: {t}", "Start: {t}",
                                t=(self.struct.get("start_time") or "––:––")
                                + ("▏" if self.focus == ("start",) else "")),
                    _theme.mix(P.header, (255, 255, 255), 0.14))]
        for cid, text, col in buttons:
            bw = len(text) * 7.2 + 26
            bx -= bw
            sel = self.focus == (cid,)
            if sel:
                self._rect(bx - 2, bt - 50, bw + 4, 34, (255, 255, 255))
            self._rect(bx, bt - 48, bw, 30, col)
            fg = hd_txt if cid in ("plan", "start") else _theme.rgba(P.accent_text)
            if cid == "start_session":
                fg = (255, 255, 255, 255)
            self._label(text, bx + bw / 2, bt - 33, 10, fg, True, anchor_x="center")
            self.cell_geo.append(((cid,), bx, bt - 48, bw, 30))
            bx -= 8
        # ---- painel da esquerda: resumo
        lx, ltop, lw, lbottom = a["left"]
        self._rect(lx - 1, lbottom - 1, lw + 2, ltop - lbottom + 2, P.border)
        self._rect(lx, lbottom, lw, ltop - lbottom, P.panel)
        self._label(tr("Resumo do treino", "Workout summary"), lx + 12, ltop - 16, 11, txt,
                    True)
        e1 = sb.e1rm_map(self.app.db) if self.struct["blocks"] else {}
        vol = sb.planned_volume(self.struct, e1)
        nsets = sum(len(e["sets"]) * sb.rounds_of(b) for b in self.struct["blocks"]
                    for e in b["exercises"])
        stat = tr("{n} séries · ≈ {t}", "{n} sets · ≈ {t}", n=nsets,
                  t=hms(sb.estimate_seconds(self.struct)))
        if vol:
            stat += f" · {vol:,.0f} kg".replace(",", " ")
        self._label(stat, lx + 12, ltop - 34, 9, dim)
        y = ltop - 54
        instr_h = 64
        room_bottom = lbottom + instr_h + 30
        for lab_, name, pres in sb.summary_lines(self.struct):
            if y < room_bottom:
                self._label("…", lx + 12, y, 10, dim)
                break
            if not pres:                                 # cabeçalho de bloco
                self._label(f"{lab_} · {name}", lx + 12, y, 9, acc, True)
                y -= 16
                continue
            self._label(lab_, lx + 12, y, 10, txt, True)
            self._label(wrap(name, lw - 54, 10, 1), lx + 40, y, 10, txt)
            y -= 14
            self._label(wrap(pres, lw - 54, 9, 1), lx + 40, y, 9, dim)
            y -= 18
        if not self.struct["blocks"]:
            self._label(tr("Ainda sem blocos.", "No blocks yet."), lx + 12, y, 10, faint)
            self._label(tr("+ Adicionar bloco, ao centro.", "+ Add block, in the middle."),
                        lx + 12, y - 16, 9, faint)
        # instruções do treino
        iy = lbottom + instr_h + 18
        self._label(tr("Instruções do treino", "Workout instructions"), lx + 12, iy, 9, txt,
                    True)
        sel = self.focus == ("instr",)
        self._rect(lx + 10, lbottom + 8, lw - 20, instr_h, P.accent if sel else P.border)
        self._rect(lx + 11, lbottom + 9, lw - 22, instr_h - 2, P.panel)
        itext = self.struct.get("instructions") or ""
        shown = wrap(itext + ("▏" if sel else ""), lw - 36, 9, 4) if (itext or sel) else \
            tr("O que o atleta deve saber (aparece no treino)", "What the athlete should know")
        self._label(shown, lx + 18, lbottom + instr_h + 2, 9, txt if itext or sel else faint,
                    anchor_y="top")
        self.cell_geo.append((("instr",), lx + 10, lbottom + 8, lw - 20, instr_h))
        # ---- centro: blocos
        mx, mtop, mw, mbottom = a["main"]
        placed = self._layout_rows()
        self.row_geo = placed
        # cartões dos blocos (por baixo de tudo o resto do bloco)
        spans: dict[int, list[float]] = {}
        for row, y0, hh in placed:
            if "bi" in row and row["t"] != "gap":
                sp = spans.setdefault(row["bi"], [y0, y0 + hh])
                sp[0], sp[1] = min(sp[0], y0), max(sp[1], y0 + hh)
        self.block_geo = {}
        for bi, (y0, y1) in spans.items():
            vy0, vy1 = max(y0, mbottom), min(y1, mtop)
            self.block_geo[bi] = (y0, y1)
            if vy1 <= vy0:
                continue
            b = self.struct["blocks"][bi]
            dragging = self.drag is not None and self.drag.get("bi") == bi and self.drag["moved"]
            self._rect(mx - 1, vy0 - 1, mw + 2, vy1 - vy0 + 2,
                       P.accent if dragging else P.border)
            self._rect(mx, vy0, mw, vy1 - vy0, P.panel)
            stripe = {"warmup": (79, 180, 172), "cooldown": (120, 150, 200),
                      "superset": P.accent, "circuit": (196, 66, 120)}.get(b["kind"], P.dim)
            self._rect(mx, vy0, 4, vy1 - vy0, stripe)
        for row, y0, hh in placed:
            if y0 < mbottom - 1 or y0 + hh > mtop + 1:      # só as linhas inteiras
                continue
            self._draw_row(row, mx, y0, mw, hh)
        # barra de deslocamento
        view_h = mtop - mbottom
        if self.content_h > view_h + 2:
            frac = view_h / self.content_h
            pos = self.scroll / max(1.0, self.content_h - view_h)
            bar_h = max(30, view_h * frac)
            self._rect(mx + mw + 6, mtop - bar_h - pos * (view_h - bar_h), 4, bar_h, P.border)
        # marca de largada ao arrastar
        self.mark.opacity = 0
        d = self.drag
        if d is not None and d.get("moved") and d.get("target") is not None:
            kind, tbi = d["target"]
            if kind == "combine" and tbi in self.block_geo:
                y0, y1 = self.block_geo[tbi]
                self._rect(mx - 3, y0 - 3, mw + 6, 3, P.accent)
                self._rect(mx - 3, y1, mw + 6, 3, P.accent)
            elif kind == "insert":
                yy = (self.block_geo[tbi][1] if tbi in self.block_geo else
                      (min(g[0] for g in self.block_geo.values()) if self.block_geo else mtop))
                self.mark.x, self.mark.y, self.mark.width, self.mark.height = mx, yy + 2, mw, 3
                self.mark.opacity = 255
        # esconder o que sobrou
        for r in self.rects[self._r:]:
            r.width = r.height = 0
            r.opacity = 0
        for lab in self.labels[self._l:]:
            lab.text = ""

    def _sel(self, cid: tuple) -> bool:
        return self.focus == cid

    def _draw_row(self, row: dict, x: float, y0: float, w: float, hh: float) -> None:
        P = _theme.P
        txt, dim, faint = _theme.rgba(P.text), _theme.rgba(P.dim), _theme.rgba(P.faint)
        acc = _theme.rgba(P.accent)
        t_ = row["t"]
        cy = y0 + hh / 2
        for cid, cx, cw in self._cells(row, x, w):
            self.cell_geo.append((cid, cx, y0 + 2, cw, hh - 4))
            if self._sel(cid):
                self._rect(cx - 2, y0 + 1, cw + 4, hh - 2, P.select)
                self._rect(cx - 2, y0 + 1, 2, hh - 2, P.accent)
        if t_ == "bhead":
            bi = row["bi"]
            b = self.struct["blocks"][bi]
            self._label("⋮⋮", x + 9, cy, 9, faint, True)
            self.cell_geo.append((("handle", bi), x, y0, 28, hh))
            title = f"{sb.letter(bi)} · {sb.kind_name(b['kind'])}"
            self._label(title, x + 34, cy, 11, acc, True)
            if b["kind"] == "circuit":
                self._label(tr("{n} voltas ▾", "{n} rounds ▾", n=b["rounds"]), x + w - 196, cy,
                            10, txt, True)
            if b.get("notes"):
                self._label(wrap(b["notes"], w * 0.35, 9, 1), x + 30 + len(title) * 7.5 + 14,
                            cy, 9, dim)
            self._label("⋮", x + w - 20, cy, 14, txt, True, anchor_x="center")
        elif t_ == "exhead":
            bi, ei = row["bi"], row["ei"]
            b = self.struct["blocks"][bi]
            e = b["exercises"][ei]
            self._label(sb.label(bi, ei, b), x + 14, cy, 10, txt, True)
            self._label(wrap(e["name"], w - 300, 11, 1), x + 52, cy, 11, txt, True)
            self._label(tr("Ver histórico", "View history"), x + w - 120, cy, 9, acc,
                        anchor_x="center")
            self._label("⋮", x + w - 48, cy, 14, txt, True, anchor_x="center")
        elif t_ == "notes":
            bi, ei = row["bi"], row["ei"]
            e = self.struct["blocks"][bi]["exercises"][ei]
            sel = self._sel(("notes", bi, ei))
            text = (e.get("notes") or "") + ("▏" if sel else "")
            self._label(wrap(tr("Notas: ", "Notes: ") + text, w - 80, 9, 1), x + 54, cy, 9,
                        dim)
        elif t_ == "phead":
            bi, ei = row["bi"], row["ei"]
            e = self.struct["blocks"][bi]["exercises"][ei]
            col_x, col_w = self._cols(x, w, len(e["params"]))
            self._label(tr("Série", "Set"), x + 54, cy, 8, dim, True)
            for k, p in enumerate(e["params"]):
                self._label(wrap(sb.param_name(p), col_w - 20, 8, 1) + " ▾", col_x + k * col_w + 4,
                            cy, 8, dim, True)
        elif t_ == "set":
            bi, ei, si = row["bi"], row["ei"], row["si"]
            e = self.struct["blocks"][bi]["exercises"][ei]
            col_x, col_w = self._cols(x, w, len(e["params"]))
            self._label(str(si + 1), x + 60, cy, 10, dim, anchor_x="center")
            for k, p in enumerate(e["params"]):
                cx = col_x + k * col_w
                self._rect(cx, y0 + 3, col_w - 8, hh - 6, P.panel2)
                v = e["sets"][si].get(p)
                cid = ("cell", bi, ei, si, k)
                if self._sel(cid) and self._typing:
                    text, col = self._buf + "▏", txt
                else:
                    text, col = sb.fmt_value(p, v), (txt if v is not None else faint)
                self._label(text, cx + 8, cy, 10, col, v is not None)
            self._label("×", x + w - 19, cy, 10, faint, anchor_x="center")
        elif t_ == "addset":
            self._label(tr("+ Série", "+ Set"), x + 56, cy, 9, acc, True)
        elif t_ == "bfoot":
            b = self.struct["blocks"][row["bi"]]
            what = tr("Descanso no fim de cada volta: {s} s ▾", "Rest after each round: {s} s ▾",
                      s=b.get("rest_s") or 0)
            if b["kind"] == "circuit":
                what += tr("   · o circuito faz-se inteiro", "   · the circuit is done in full")
            elif b["kind"] == "superset":
                what += tr("   · as séries alternam (A1, A2, A1…)",
                           "   · sets alternate (A1, A2, A1…)")
            self._label(what, x + 56, cy, 9, dim)
        elif t_ == "addblock":
            sel = self._sel(("addblock",))
            self._rect(x, y0 + 4, 220, hh - 8, P.accent if sel else P.panel)
            if not sel:
                self._rect(x, y0 + 4, 220, 1, P.border)
                self._rect(x, y0 + hh - 5, 220, 1, P.border)
                self._rect(x, y0 + 4, 1, hh - 8, P.border)
                self._rect(x + 219, y0 + 4, 1, hh - 8, P.border)
            self._label(tr("+ Adicionar bloco", "+ Add block"), x + 110, cy, 11,
                        _theme.rgba(P.accent_text) if sel else acc, True, anchor_x="center")

    # ---------------------------------------------------------------- ecrã

    def enter(self) -> None:
        self.chrome.set("", "", tr(
            "Setas · números · Enter abrir · M menu ⋮ · Alt+↑↓ bloco · Ctrl+S guardar",
            "Arrows · digits · Enter open · M ⋮ menu · Alt+↑↓ block · Ctrl+S save"))
        self.chrome.agent_hint.text = ""
        self._set_buttons()
        self.list.y = -3000
        self.refresh()

    def _set_buttons(self) -> None:
        """Guardar fica em baixo, à direita (como em todos os ecrãs)."""
        saved = time.monotonic() - self.saved_at < 3 and not self.dirty
        label = tr("Guardado ✓", "Saved ✓") if saved else \
            tr("Guardar", "Save") + (" •" if self.dirty else "")
        self.list.set_items([Item(label, action=self.save, button=True, primary=True)])

    def changed(self) -> None:
        self.dirty = True
        self.refresh()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.list.y = -3000
        self.refresh()

    def update(self, dt: float) -> None:
        if self.saved_at and time.monotonic() - self.saved_at > 3 and self._flash_shown:
            self._flash_shown = False
            self.refresh()

    _flash_shown = False

    # --------------------------------------------------------------- foco

    def _focusables(self) -> list[tuple]:
        out = [("name",), ("start",), ("plan",), ("start_session",), ("instr",)]
        for row in self._rows():
            for cid, _x, _w in self._cells(row, 0, 800):
                out.append(cid)
        return out

    def _row_of(self, cid: tuple):
        for row, y0, hh in getattr(self, "row_geo", []):
            for c, _x, _w in self._cells(row, 0, 800):
                if c == cid:
                    return row, y0, hh
        return None

    def _ensure_visible(self) -> None:
        a = self._areas()
        mx, mtop, mw, mbottom = a["main"]
        self._layout_rows()
        got = None
        for row, y0, hh in self._layout_rows():
            for c, _x, _w in self._cells(row, 0, 800):
                if c == self.focus:
                    got = (y0, hh)
        if got is None:
            return
        y0, hh = got
        if y0 < mbottom + 4:
            self.scroll += (mbottom + 4) - y0
        elif y0 + hh > mtop:
            self.scroll -= (y0 + hh) - mtop
        self.scroll = max(0.0, self.scroll)

    def set_focus(self, cid: tuple) -> None:
        self._commit_typing()
        self.focus = cid
        self._ensure_visible()
        self.refresh()

    def _move(self, dx: int, dy: int) -> None:
        cells = self._focusables()
        if self.focus not in cells:
            self.set_focus(cells[0])
            return
        if dx:
            i = cells.index(self.focus)
            self.set_focus(cells[max(0, min(len(cells) - 1, i + dx))])
            return
        # ↑/↓: a célula da linha de cima/baixo mais perto em x
        self.refresh()
        geo = {c: (x, y) for c, x, y, _w, _h in self.cell_geo}
        if self.focus not in geo:
            i = cells.index(self.focus)
            self.set_focus(cells[max(0, min(len(cells) - 1, i + dy))])
            return
        fx, fy = geo[self.focus]
        best = None
        for c in cells:
            if c not in geo or c == self.focus:
                continue
            x, y = geo[c]
            if (dy > 0 and y >= fy - 2) or (dy < 0 and y <= fy + 2):
                continue
            score = abs(y - fy) * 3 + abs(x - fx) * 0.5
            if best is None or score < best[0]:
                best = (score, c)
        if best is None:                      # fora do ecrã: pela ordem
            i = cells.index(self.focus)
            nxt = cells[max(0, min(len(cells) - 1, i + (1 if dy > 0 else -1)))]
            self.set_focus(nxt)
        else:
            self.set_focus(best[1])

    # ------------------------------------------------------------ escrever

    _buf = ""

    def _commit_typing(self) -> None:
        if not self._typing:
            return
        self._typing = False
        cid = self.focus
        if cid and cid[0] == "cell":
            _, bi, ei, si, k = cid
            p = self.struct["blocks"][bi]["exercises"][ei]["params"][k]
            txt = self._buf.replace(",", ".")
            try:
                v = float(txt) if txt else None
            except ValueError:
                v = None
            sb.set_value(self.struct, bi, ei, si, p, v)
            self.dirty = True
        elif cid and cid[0] in ("rounds", "brest"):
            try:
                v = int(float(self._buf.replace(",", "."))) if self._buf else None
            except ValueError:
                v = None
            if v is not None:
                b = self.struct["blocks"][cid[1]]
                if cid[0] == "rounds":
                    b["rounds"] = max(1, min(20, v))
                else:
                    b["rest_s"] = max(0, min(900, v))
                self.dirty = True
        self._buf = ""

    def on_text(self, text: str) -> bool:
        clean = "".join(c for c in text if c.isprintable() and c not in "\r\n\t")
        if not clean:
            return True
        cid = self.focus
        kind = cid[0] if cid else ""
        if kind in ("cell", "rounds", "brest"):
            digits = "".join(c for c in clean if c in NUMERIC)
            if not digits:
                return True
            if not self._typing:
                self._typing, self._buf = True, ""
            self._buf = (self._buf + digits)[:7]
            self.refresh()
            return True
        if kind == "name":
            self.name = (self.name + clean)[:60]
        elif kind == "instr":
            self.struct["instructions"] = (self.struct.get("instructions", "") + clean)[:600]
        elif kind == "notes":
            e = self.struct["blocks"][cid[1]]["exercises"][cid[2]]
            e["notes"] = ((e.get("notes") or "") + clean)[:200]
        elif kind == "start":
            st_ = self.struct.get("start_time") or ""
            for c in clean:
                if c.isdigit() and len(st_) < 5:
                    st_ += c
                    if len(st_) == 2:
                        st_ += ":"
            self.struct["start_time"] = st_
        else:
            if kind == "exname" or kind == "bmenu" or kind == "exmenu":
                if clean.lower() == "m":
                    self.open_menu()
            return True
        self.changed()
        return True

    def _backspace(self) -> None:
        cid = self.focus
        kind = cid[0] if cid else ""
        if kind in ("cell", "rounds", "brest"):
            if self._typing:
                self._buf = self._buf[:-1]
                if not self._buf:
                    self._typing = False
                    if kind == "cell":
                        _, bi, ei, si, k = cid
                        p = self.struct["blocks"][bi]["exercises"][ei]["params"][k]
                        sb.set_value(self.struct, bi, ei, si, p, None)
                        self.dirty = True
            elif kind == "cell":
                _, bi, ei, si, k = cid
                p = self.struct["blocks"][bi]["exercises"][ei]["params"][k]
                sb.set_value(self.struct, bi, ei, si, p, None)
                self.dirty = True
            self.refresh()
            return
        if kind == "name":
            self.name = self.name[:-1]
        elif kind == "instr":
            self.struct["instructions"] = (self.struct.get("instructions") or "")[:-1]
        elif kind == "notes":
            e = self.struct["blocks"][cid[1]]["exercises"][cid[2]]
            e["notes"] = (e.get("notes") or "")[:-1]
        elif kind == "start":
            st_ = (self.struct.get("start_time") or "")[:-1]
            self.struct["start_time"] = st_.rstrip(":")
        else:
            return
        self.changed()

    # --------------------------------------------------------------- ações

    def activate(self, cid: tuple | None = None) -> None:
        cid = cid or self.focus
        if not cid:
            return
        k = cid[0]
        a = self.app
        if k == "save":
            self.save()
        elif k == "start_session":
            self.start_session()
        elif k == "plan":
            self._plan_menu()
        elif k == "addblock":
            self.add_block_menu()
        elif k in ("bmenu", "exmenu", "exname"):
            self.open_menu(cid)
        elif k == "hist":
            ex = self.struct["blocks"][cid[1]]["exercises"][cid[2]]
            from velo.ui.exercise_stats_screens import ExerciseStatsScreen
            a.push(ExerciseStatsScreen(a, ex["exercise_id"]))
        elif k == "phead":
            self.param_menu(cid[1], cid[2], cid[3])
        elif k == "addset":
            sb.add_set(self.struct, cid[1], cid[2])
            self.changed()
        elif k == "delset":
            sb.remove_set(self.struct, cid[1], cid[2], cid[3])
            self.focus = ("addset", cid[1], cid[2])
            self.changed()
        elif k == "cell":
            self._commit_typing()
            _, bi, ei, si, kk = cid
            nsets = len(self.struct["blocks"][bi]["exercises"][ei]["sets"])
            self.set_focus(("cell", bi, ei, si + 1, kk) if si + 1 < nsets
                           else ("addset", bi, ei))
        elif k in ("notes", "name", "instr", "start", "rounds", "brest"):
            self._commit_typing()
            self._move(0, 1)
        self.refresh()

    def add_block_menu(self) -> None:
        a = self.app
        opts = [(sb.kind_name(k), (lambda kk=k: self._pick_exercise_for_new(kk)))
                for k in sb.KINDS]
        a.push(MenuPopup(a, tr("Adicionar bloco", "Add block"), opts,
                         tr("Escolhe o tipo; depois, o exercício", "Pick the type, then the "
                            "exercise")))

    def _exercise_picker(self, cb) -> None:
        from velo.ui.hub_screens import ExerciseInventory
        self.app.push(ExerciseInventory(self.app, self.mod, pick=cb))

    def _pick_exercise_for_new(self, kind: str) -> None:
        def cb(ex: dict) -> None:
            e = sb.new_exercise(ex, ex.get("measure") or "reps")
            bi = sb.add_block(self.struct, kind, [e])
            self.focus = ("cell", bi, 0, 0, 0)
            self.dirty = True
            if kind in ("superset", "circuit", "warmup", "cooldown"):
                self.app.message(tr("Junta mais exercícios: ⋮ do bloco › Adicionar exercício, "
                                    "ou arrasta outro bloco para cima deste",
                                    "Add more: block ⋮ › Add exercise, or drag another block "
                                    "onto this one"))
            self._ensure_visible()
        self._exercise_picker(cb)

    def open_menu(self, cid: tuple | None = None) -> None:
        cid = cid or self.focus
        if not cid or len(cid) < 2:
            return
        if cid[0] in ("bmenu", "rounds", "brest", "handle"):
            self.block_menu(cid[1])
        else:
            self.exercise_menu(cid[1], cid[2])

    def block_menu(self, bi: int) -> None:
        a = self.app
        b = self.struct["blocks"][bi]
        opts = [(tr("Adicionar exercício a este bloco", "Add exercise to this block"),
                 lambda: self._add_to_block(bi))]
        for k in sb.KINDS:
            if k != b["kind"] and not (k == "single" and len(b["exercises"]) > 1):
                opts.append((tr("Converter em {k}", "Convert to {k}", k=sb.kind_name(k)),
                             lambda kk=k: self._convert(bi, kk)))
        if b["kind"] == "circuit":
            opts.append((tr("Voltas: escreve o número na linha do bloco",
                            "Rounds: type the number on the block row"),
                         lambda: self.set_focus(("rounds", bi))))
        opts += [(tr("Mover para cima", "Move up"), lambda: self._move_block(bi, -1)),
                 (tr("Mover para baixo", "Move down"), lambda: self._move_block(bi, 1)),
                 (tr("Duplicar o bloco", "Duplicate block"), lambda: self._dup_block(bi)),
                 (tr("Remover o bloco (não se pode desfazer)", "Remove block (cannot be undone)"),
                  lambda: self._remove_block(bi))]
        a.push(MenuPopup(a, f"{sb.letter(bi)} · {sb.kind_name(b['kind'])}", opts))

    def exercise_menu(self, bi: int, ei: int) -> None:
        a = self.app
        b = self.struct["blocks"][bi]
        e = b["exercises"][ei]
        missing = [p for p in sb.PARAMS if p not in e["params"]]
        opts = [(tr("Adicionar parâmetro…", "Add parameter…"),
                 lambda: self._param_add_menu(bi, ei, missing)),
                (tr("Pré-visualizar o exercício", "Preview exercise"),
                 lambda: a.push(ExercisePreview(a, e["exercise_id"]))),
                (tr("Notas do treinador", "Coach notes"),
                 lambda: self.set_focus(("notes", bi, ei))),
                (tr("Ver histórico", "View history"),
                 lambda: self.activate(("hist", bi, ei))),
                (tr("Substituir o exercício", "Replace exercise"),
                 lambda: self._replace(bi, ei))]
        if len(b["exercises"]) > 1:
            opts.append((tr("Desligar do bloco", "Unlink exercise"), lambda: self._unlink(bi, ei)))
        opts.append((tr("Remover o exercício", "Remove exercise"),
                     lambda: self._remove_ex(bi, ei)))
        a.push(MenuPopup(a, f"{sb.label(bi, ei, b)} · {e['name']}", opts))

    def param_menu(self, bi: int, ei: int, k: int) -> None:
        a = self.app
        e = self.struct["blocks"][bi]["exercises"][ei]
        p = e["params"][k]
        opts = [(tr("Mudar para {p}", "Change to {p}", p=sb.param_name(q)),
                 lambda q=q: self._replace_param(bi, ei, p, q))
                for q in sb.PARAMS if q not in e["params"]]
        opts.append((tr("Copiar o valor da 1.ª série para todas", "Copy set 1 to all sets"),
                     lambda: self._fill(bi, ei, p)))
        if len(e["params"]) > 1:
            opts.append((tr("Remover o parâmetro", "Remove parameter"),
                         lambda: self._remove_param(bi, ei, p)))
        a.push(MenuPopup(a, sb.param_name(p), opts, sb.param_help(p)))

    def _param_add_menu(self, bi, ei, missing):
        a = self.app
        opts = [(sb.param_name(q), lambda q=q: self._add_param(bi, ei, q)) for q in missing]
        if opts:
            a.push(MenuPopup(a, tr("Adicionar parâmetro", "Add parameter"), opts))

    def _plan_menu(self) -> None:
        a = self.app
        today = date.today()
        opts = [(tr("Sem data", "No date"), lambda: self._set_plan(None))]
        for k in range(0, 14):
            d = today + timedelta(days=k)
            from velo.core import calendar_view as cv
            name = tr("Hoje", "Today") if k == 0 else (tr("Amanhã", "Tomorrow") if k == 1 else
                                                         f"{cv.weekday_name(d.weekday())} "
                                                         f"{d.strftime('%d/%m')}")
            opts.append((name, lambda dd=d: self._set_plan(dd)))
        a.push(MenuPopup(a, tr("Planear para", "Plan for"), opts,
                         tr("Fica no calendário ao guardar", "Goes to the calendar on save")))

    # operações (cada uma marca por guardar)
    def _set_plan(self, d):
        self.plan_day = d
        self.changed()

    def _add_to_block(self, bi):
        def cb(ex):
            self.struct["blocks"][bi]["exercises"].append(
                sb.new_exercise(ex, ex.get("measure") or "reps"))
            b = self.struct["blocks"][bi]
            if b["kind"] == "single":
                b["kind"] = "superset"
                b["rest_s"] = b.get("rest_s") or 90
            self.focus = ("cell", bi, len(b["exercises"]) - 1, 0, 0)
            self.dirty = True
        self._exercise_picker(cb)

    def _convert(self, bi, kind):
        sb.convert(self.struct, bi, kind)
        self.changed()

    def _move_block(self, bi, step):
        n = len(self.struct["blocks"])
        dst = bi + step
        if 0 <= dst < n:
            sb.move_block(self.struct, bi, dst + (1 if step > 0 else 0))
            self.focus = ("bmenu", dst)
            self.changed()

    def _dup_block(self, bi):
        self.struct["blocks"].insert(bi + 1, sb.clone(self.struct["blocks"][bi]))
        self.changed()

    def _remove_block(self, bi):
        sb.remove_block(self.struct, bi)
        self.focus = ("addblock",)
        self.changed()

    def _replace(self, bi, ei):
        def cb(ex):
            e = self.struct["blocks"][bi]["exercises"][ei]
            e["exercise_id"], e["name"] = int(ex["id"]), ex["name"]
            self.dirty = True
        self._exercise_picker(cb)

    def _unlink(self, bi, ei):
        nb = sb.unlink(self.struct, bi, ei)
        self.focus = ("bmenu", nb)
        self.changed()

    def _remove_ex(self, bi, ei):
        b = self.struct["blocks"][bi]
        del b["exercises"][ei]
        if not b["exercises"]:
            del self.struct["blocks"][bi]
        elif b["kind"] == "superset" and len(b["exercises"]) == 1:
            b["kind"] = "single"
        self.focus = ("addblock",)
        self.changed()

    def _add_param(self, bi, ei, p):
        sb.add_param(self.struct, bi, ei, p)
        self.changed()

    def _remove_param(self, bi, ei, p):
        sb.remove_param(self.struct, bi, ei, p)
        self.focus = ("phead", bi, ei, 0)
        self.changed()

    def _replace_param(self, bi, ei, old, new):
        sb.replace_param(self.struct, bi, ei, old, new)
        self.changed()

    def _fill(self, bi, ei, p):
        sb.fill_down(self.struct, bi, ei, 0, p)
        self.changed()

    # ------------------------------------------------------- guardar / começar

    def save(self, quiet: bool = False) -> str | None:
        self._commit_typing()
        if not self.struct["blocks"]:
            self.app.message(tr("Junta pelo menos um bloco.", "Add at least one block."))
            return None
        try:
            self.wid = sb.save(self.app.db, self.wid, self.name, self.struct, self.mod,
                               hidden=self.draft)
        except ValueError as e:
            self.app.message(str(e))
            return None
        if self.plan_day is not None and not self.draft:
            from velo.core import calendar_view as cv
            have = [p for p in cv.planned_for(self.app.db, self.plan_day)
                    if p.workout_id == self.wid]
            if not have:
                cv.plan_add(self.app.db, self.plan_day, "gym", self.wid, self.name)
        self.dirty = False
        self.saved_at = time.monotonic()
        self._flash_shown = True
        if not quiet:
            self.app.message(tr("Guardado", "Saved"))
        self.refresh()
        return self.wid

    def start_session(self) -> None:
        wid = self.save(quiet=True)
        if wid is None:
            return
        from velo.ui.sport_screens import StrengthSessionScreen
        try:
            self.app.replace(StrengthSessionScreen(self.app, wid))
        except ValueError as e:
            self.app.message(str(e))

    def keep(self) -> None:
        """Num treino livre: guardar como treino da modalidade."""
        self.draft = False
        if self.save(quiet=True):
            gym.keep_plan(self.app.db, self.wid, self.name)

    # ---------------------------------------------------------------- teclado

    def on_key(self, symbol: int, modifiers: int) -> bool:
        ctrl, alt = modifiers & key.MOD_CTRL, modifiers & key.MOD_ALT
        if symbol == key.S and ctrl:
            self.save()
            return True
        if symbol == key.ESCAPE:
            if self._typing:
                self._typing, self._buf = False, ""
                self.refresh()
                return True
            self.app.pop()            # com alterações por guardar, pergunta primeiro
            return True
        self._armed = None
        if alt and symbol in (key.UP, key.DOWN) and self.focus and len(self.focus) > 1:
            self._move_block(self.focus[1], -1 if symbol == key.UP else 1)
            return True
        if symbol in (key.UP, key.DOWN):
            self._commit_typing()
            self._move(0, -1 if symbol == key.UP else 1)
            return True
        if symbol in (key.LEFT, key.RIGHT, key.TAB):
            self._commit_typing()
            step = -1 if symbol == key.LEFT or (symbol == key.TAB and modifiers & key.MOD_SHIFT) \
                else 1
            self._move(step, 0)
            return True
        if symbol == key.BACKSPACE:
            self._backspace()
            return True
        if symbol == key.DELETE:
            cid = self.focus
            if cid and cid[0] == "cell":
                self._backspace()
            elif cid and cid[0] in ("bmenu", "handle", "rounds", "brest"):
                self._remove_block(cid[1])
            elif cid and cid[0] in ("exname", "exmenu"):
                self._remove_ex(cid[1], cid[2])
            return True
        if symbol in (key.ENTER, key.RETURN):
            self.activate()
            return True
        if symbol == key.M and not (self.focus and self.focus[0] in ("name", "instr", "notes")):
            self.open_menu()
            return True
        if symbol == key.SPACE and self.focus and self.focus[0] not in ("name", "instr",
                                                                          "notes"):
            self.activate()
            return True
        if self.AGENT and symbol in (key.F1, key.F2):
            return super().on_key(symbol, modifiers)
        return True

    # ------------------------------------------------------------------ rato

    def _cell_at(self, x, y):
        for cid, cx, cy, cw, ch in reversed(self.cell_geo):
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                return cid
        return None

    def _block_at(self, y):
        for bi, (y0, y1) in self.block_geo.items():
            if y0 <= y <= y1:
                return bi, y0, y1
        return None

    def on_save(self) -> bool:
        self.save()
        return True

    def has_unsaved(self) -> bool:
        return self.dirty

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.on_key(key.ESCAPE, 0)
            return True
        if self.list.on_mouse_press(x, y):
            return True
        cid = self._cell_at(x, y)
        if cid is not None and cid[0] == "handle":
            self.drag = {"bi": cid[1], "moved": False, "target": None}
            return True
        if cid is None:
            a = self._areas()
            mx, mtop, mw, mbottom = a["main"]
            hit = self._block_at(y) if mx <= x <= mx + mw else None
            if hit is not None and x < mx + 30:
                self.drag = {"bi": hit[0], "moved": False, "target": None}
                return True
            return False
        typing = cid[0] in ("name", "instr", "notes", "start", "cell", "rounds", "brest")
        self.set_focus(cid)
        if not typing:
            self.activate(cid)
        return True

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        d = self.drag
        if d is None:
            return False
        d["moved"] = True
        b = self.struct["blocks"][d["bi"]]
        text = f"⋮⋮ {sb.letter(d['bi'])} · " + ", ".join(e["name"] for e in b["exercises"])[:40]
        gw = len(text) * 7 + 24
        self.ghost.x, self.ghost.y, self.ghost.width, self.ghost.height = x + 8, y - 13, gw, 26
        self.ghost.opacity = 220
        self.ghost_l.text = text
        self.ghost_l.x, self.ghost_l.y = x + 18, y
        d["target"] = self._drop_target(y)
        self.refresh()
        return True

    def _drop_target(self, y):
        """«combine» (largar em cima: superset) ou «insert» (entre blocos)."""
        d = self.drag
        hit = self._block_at(y)
        if hit is None:
            if self.block_geo:
                last = max(self.block_geo, key=lambda k: -self.block_geo[k][0])
                if y < self.block_geo[last][0]:
                    return ("insert", len(self.struct["blocks"]))
            return None
        bi, y0, y1 = hit
        if bi == d["bi"]:
            return None
        hgt = y1 - y0
        if y > y1 - hgt * 0.25:
            return ("insert", bi)                         # na parte de cima: antes dele
        if y < y0 + hgt * 0.25:
            return ("insert", bi + 1)                     # na parte de baixo: depois
        return ("combine", bi)

    def on_release(self, x: int, y: int) -> bool:
        d, self.drag = self.drag, None
        self.ghost.opacity = 0
        self.ghost_l.text = ""
        if d is None:
            return False
        tgt = d.get("target") if d.get("moved") else None
        if tgt is not None:
            kind, bi = tgt
            if kind == "combine":
                nb = sb.combine(self.struct, d["bi"], bi)
                self.focus = ("bmenu", nb)
                self.app.message(tr("Juntos num superset", "Combined into a superset"))
            else:
                nb = sb.move_block(self.struct, d["bi"], bi)
                self.focus = ("bmenu", nb)
            self.dirty = True
        self.refresh()
        return True

    def on_scroll(self, x, y, sx, sy) -> bool:
        self.scroll = max(0.0, self.scroll - sy * 30)
        a = self._areas()
        view = a["main"][1] - a["main"][3]
        self.scroll = min(self.scroll, max(0.0, self.content_h - view))
        self.refresh()
        return True

    def agent_data(self) -> dict:
        return {"treino": self.name, "blocos": [
            {"tipo": b["kind"], "voltas": b["rounds"], "exercicios": [
                {"nome": e["name"], "prescricao": sb.prescription(e), "notas": e["notes"]}
                for e in b["exercises"]]} for b in self.struct["blocks"]]}

    def draw(self) -> None:
        self.batch.draw()
        self.chrome.set_footer_limit(self.list.buttons_left)
        self.chrome.draw()
        self.list.draw()
        if self.back_button is not None:
            self.back_button.draw()


class ExercisePreview(Screen):
    """«Pré-visualizar o exercício»: o que é, o grupo muscular, o material, as
    modalidades e as instruções (escritas no inventário de exercícios)."""

    def __init__(self, app, eid: int):
        super().__init__(app)
        self.eid = eid

    def enter(self) -> None:
        from velo.core import inventory
        from velo.core.i18n import t
        a = self.app
        e = gym.exercise(a.db, self.eid) or {}
        kit = ", ".join(inventory.kind_name(k) for k in e.get("equipment") or []) or \
            tr("sem material", "no equipment")
        items = [Item(tr("Grupo muscular", "Muscle group"),
                      value=t(f"str.group.{e.get('category') or 'full'}"), enabled=False),
                 Item(tr("Medida", "Measure"), value=tr("tempo", "time")
                      if e.get("measure") == "time" else tr("repetições", "reps"), enabled=False),
                 Item(tr("Material", "Equipment"), value=kit, enabled=False),
                 Item(tr("Modalidades", "Modalities"), value=", ".join(
                     gym.modality(m).name for m in e.get("modalities") or []), enabled=False),
                 Item(tr("Instruções", "Instructions"),
                      detail=e.get("description") or tr(
                          "Sem instruções. Escreve-as no inventário de exercícios.",
                          "No instructions yet. Write them in the exercise list."),
                      enabled=False)]
        from velo.ui.exercise_stats_screens import ExerciseStatsScreen
        items.append(Item(tr("Ver histórico e evolução", "View history and progress"),
                          action=lambda: a.push(ExerciseStatsScreen(a, self.eid))))
        self.chrome.set(e.get("name") or tr("Exercício", "Exercise"),
                        tr("Pré-visualização", "Preview"), self.footer())
        self.list.set_items(items)
