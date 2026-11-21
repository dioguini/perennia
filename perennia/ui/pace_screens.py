"""Segment Pace e Segment KOM: a janela de preparação do Challenge e a tabela por secção.

A preparação tem os aparelhos e, sobretudo, **uma só escolha de segmento** (abre uma janela com
os da Perennia e os do Strava), o alvo, o ERG e a entrada: sem rota, .gpx, auto lap nem tamanho
de letra. Por baixo mostra, **antes de começar**, o que o alvo pede: tempo, potência média, se cabe na
tua capacidade e os watts de cada secção. Corre tudo offline com o que está guardado.
"""
from __future__ import annotations

import time

from pyglet.window import key

from perennia.core import options as opt_mod
from perennia.core import segment_pace as sp
from perennia.core.boards import Board
from perennia.core.i18n import t, tr
from perennia.core.units import delta, hms
from perennia.ui.app import PopupMixin, RideScreen, Screen
from perennia.ui.session_setup import SessionSetup
from perennia.ui.sport_screens import EditPopup
from perennia.ui.widgets import Dropdown, Item

LEAD_CHOICES = (0, 250, 500, 1000, 2000)      # as entradas da lista (a das opções junta-se)


class ValuePopup(EditPopup):
    """Uma linha de texto numa janela: o valor do alvo (tempo, % ou watts)."""

    W = 640
    MIN_H, MAX_H = 330, 330

    def __init__(self, app, label: str, hint: str, current: str, on_ok):
        self.label, self.hint, self.current, self.on_ok = label, hint, current, on_ok
        self.v = {"text": ""}
        super().__init__(app)

    def title(self) -> str:
        return self.label

    def subtitle(self) -> str:
        return self.hint

    def rows(self) -> list[Item]:
        return [Item(self.label, value=self.v["text"] or "—",
                     detail=tr("escreve · atual: {c}", "type · current: {c}", c=self.current),
                     data="text:value")]

    def text_input(self, field: str, text: str) -> None:
        self.v["text"] = (self.v["text"] + text)[:12]
        self.enter()

    def text_backspace(self, field: str) -> None:
        self.v["text"] = self.v["text"][:-1]
        self.enter()

    def buttons(self) -> list[Item]:
        return [Item(tr("Cancelar", "Cancel"), action=self.close, button=True),
                Item("OK", action=self.save_exit, button=True, primary=True)]

    def commit(self) -> bool:
        if not self.v["text"].strip():
            self.close()
            return False
        return bool(self.on_ok(self.v["text"]))

    def save_exit(self) -> None:
        if self.commit():
            self.close()

    def has_unsaved(self) -> bool:
        return False

    def cancel(self) -> None:
        self.close()


class SegmentPickerPopup(PopupMixin, Screen):
    """Todos os segmentos que se podem jogar, por grupo: Perennia e Strava. Enter escolhe."""

    W, H = 860, 620

    def __init__(self, app, entries: list, current: str | None, on_pick):
        super().__init__(app)
        self.entries, self.current, self.on_pick = entries, current, on_pick
        self._init_popup()

    @staticmethod
    def describe(e) -> tuple[str, str]:
        s = e.segment
        bits = [f"{s.length_m / 1000:.2f} km"]
        if s.avg_grade is not None:
            bits.append(f"{s.avg_grade:+.1f} %")
        det = []
        if sp.my_best(s):
            det.append(tr("o meu melhor {x}", "my best {x}", x=hms(sp.my_best(s))))
        if sp.kom_seconds(s.kom):
            det.append(f"KOM {hms(sp.kom_seconds(s.kom))}")
        det.append(tr("rota {r}", "route {r}", r=e.route_name) if e.route_name
                   else (tr("biblioteca (sem rota)", "library (no route)")
                         if e.group == "strava" else ""))
        return " · ".join(bits), " · ".join(x for x in det if x)

    def enter(self) -> None:
        items: list[Item] = []
        for group, title in (("perennia", "Perennia"), ("strava", "Strava")):
            mine = [e for e in self.entries if e.group == group]
            items.append(Item(f"{title} ({len(mine)})", header=True))
            if not mine:
                items.append(Item(
                    tr("Nenhum segmento", "No segments"), enabled=False, indent=1,
                    detail=(tr("cria-os no menu Segmentos, sobre uma rota", "create them in the "
                               "Segments menu, on a route") if group == "perennia" else
                            tr("importa-os no menu Segmentos → Importar do Strava",
                               "import them in Segments → Import from Strava"))))
            for e in mine:
                value, detail = self.describe(e)
                items.append(Item(e.segment.name + ("  ✓" if e.key == self.current else ""),
                                  value=value, detail=detail, indent=1, data=e.key,
                                  action=lambda k=e.key: self._choose(k)))
        self.chrome.set(tr("Escolhe o segmento", "Pick the segment"),
                        tr("{n} segmentos · Enter escolhe · Esc volta",
                           "{n} segments · Enter picks · Esc goes back", n=len(self.entries)), "")
        self.list.set_items(items, keep_index=True)
        self.list.select_data(self.current)

    def _choose(self, key_: str) -> None:
        self.app.pop()
        self.on_pick(key_)


class PaceSetup(SessionSetup):
    """Segment Pace e Segment KOM (Challenge do ciclismo).

    Sem rota, sem .gpx, sem auto lap e sem tamanho de letra: escolhe-se **o segmento** (uma só
    linha, que abre a lista dos da Perennia e do Strava) e o alvo. Um segmento que está numa rota
    joga-se nela; um da biblioteca do Strava sem rota joga-se num percurso feito só com ele."""

    def __init__(self, app, game_key: str):
        super().__init__(app, "cycling", kind="game", game_key=game_key)
        self.key = game_key
        self.cls = self.game_cls
        self.mode = self.cls.mode
        db = app.db
        self.erg = bool(opt_mod.get(db, "seg_pace_erg")) if self.mode == sp.PACE else False
        self.lead_in = int(sp.LEAD_IN_M)
        self.entries = sp.catalog(db)
        self.entry_key: str | None = self.entries[0].key if self.entries else None
        self.kind = "pr_pct" if self.mode == sp.PACE else "my_kom"
        self.value: float | None = 0.0
        self._cache: dict = {}
        self._ensure_choices()

    # ------------------------------------------------------------- regras

    @property
    def needs_route(self) -> bool:
        return False

    @property
    def comparison_allowed(self) -> bool:
        return False

    def entry(self):
        return next((e for e in self.entries if e.key == self.entry_key), None)

    def segment(self):
        e = self.entry()
        return e.segment if e else None

    def _ensure_choices(self) -> None:
        """Mantém o alvo válido para o segmento escolhido."""
        seg = self.segment()
        if seg is None:
            return
        kinds = [k for k, _ in sp.target_choices(self.mode, seg)]
        if kinds and self.kind not in kinds:
            self.kind = kinds[0]
            self.value = 0.0 if self.kind == "pr_pct" else None
        if self.mode == sp.PACE and self.kind == "pr_pct" and not sp.my_best(seg):
            self.kind, self.value = "time", None

    def prepared(self):
        """(Setup | None, mensagem | None): o plano do alvo escolhido (em cache)."""
        e = self.entry()
        if e is None:
            return None, tr("Ainda não há segmentos: importa-os do Strava (Segmentos → Importar) "
                            "ou cria um sobre uma rota (Segmentos).",
                            "There are no segments yet: import them from Strava (Segments → "
                            "Import) or create one on a route (Segments).")
        seg = e.segment
        if not sp.target_choices(self.mode, seg):
            return None, tr("Este segmento ainda não tem tempos teus nem KOM: faz primeiro "
                            "uma sessão nele, ou usa o Segment Pace.",
                            "This segment has no times of yours and no KOM yet: ride it first, "
                            "or use Segment Pace.")
        key = (e.key, self.mode, self.kind, self.value, self.lead_in, seg.pr_s, seg.local_best_s)
        if key not in self._cache:
            try:
                from perennia.core import stats
                pts, rseg = sp.resolve(self.app.db, e, self.lead_in)
                best = dict(stats.power_curve(self.app.db, days=90))
                pl = sp.planner_for(self.app.db, self.app.db.athlete(), pts, rseg, best,
                                    self.lead_in)
                self._cache = {key: (sp.prepare(pl, rseg, self.mode, self.kind, self.value),
                                     None)}
            except ValueError as err:
                self._cache = {key: (None, str(err))}
            except Exception as err:               # nunca deixa a janela por abrir
                self._cache = {key: (None, tr("Não foi possível preparar o segmento: {e}",
                                              "Could not prepare the segment: {e}",
                                              e=str(err)[:80]))}
        return self._cache[key]

    @property
    def can_start(self) -> bool:
        return self.prepared()[0] is not None

    def autolap_cfg(self) -> dict:
        return {"mode": "off", "value": 0}

    # -------------------------------------------------------------- linhas

    def title(self) -> str:
        return t(f"game.{self.key}")

    def pace_items(self) -> list[Item]:
        e = self.entry()
        seg = self.segment()
        if e is None:
            return [Item(tr("Segmento", "Segment"), value=tr("nenhum", "none"),
                         detail=self.prepared()[1] or "", enabled=False, data="seg")]
        value, detail = SegmentPickerPopup.describe(e)
        rows = [Item(tr("Segmento", "Segment"), value=seg.name,
                     detail=f"{'Perennia' if e.group == 'perennia' else 'Strava'} · {value}"
                            + (" · " + detail if detail else "")
                            + tr(" · Enter abre a lista", " · Enter opens the list"),
                     data="seg", action=self._open_picker)]
        kinds = sp.target_choices(self.mode, seg)
        if kinds:
            ks = [k for k, _ in kinds]
            rows.append(Item(tr("Alvo", "Target"), value=dict(kinds).get(self.kind, "—"),
                             detail=tr("Enter abre a lista · ←/→ muda",
                                       "Enter opens the list · ←/→ changes"), data="tgt",
                             dropdown=Dropdown([n for _, n in kinds],
                                               ks.index(self.kind) if self.kind in ks else 0,
                                               lambda i, ks=ks: self._pick_kind(ks[i]))))
        if self.mode == sp.PACE:
            label, hint = self._value_texts()
            rows.append(Item(label, value=self._value_shown(), detail=hint, data="value",
                             action=self._edit_value))
            rows.append(Item(tr("ERG", "ERG"),
                             value=t("common.on") if self.erg else t("common.off"),
                             detail=tr("Enter abre a lista · ligado: o rolo põe os watts de "
                                       "cada secção; desligado: segues o sinal",
                                       "Enter opens the list · on: the trainer sets each "
                                       "section's watts; off: you follow the sign"),
                             data="erg",
                             dropdown=Dropdown([t("common.on"), t("common.off")],
                                               0 if self.erg else 1,
                                               lambda i: setattr(self, "erg", i == 0))))
        leads = self._lead_choices()
        rows.append(Item(tr("Entrada", "Lead-in"), value=f"{self.lead_in} m",
                         detail=tr("metros antes do segmento para aquecer e ganhar velocidade "
                                   "· Enter abre a lista",
                                   "metres before the segment to warm up and get up to speed "
                                   "· Enter opens the list"), data="lead",
                         dropdown=Dropdown([f"{x} m" for x in leads],
                                           leads.index(self.lead_in)
                                           if self.lead_in in leads else 0,
                                           lambda i, ls=leads: self._pick_lead(ls[i]))))
        return rows + self.summary_items()

    def _lead_choices(self) -> list[int]:
        return sorted(set(LEAD_CHOICES) | {int(sp.LEAD_IN_M), self.lead_in})

    def _value_texts(self) -> tuple[str, str]:
        if self.kind == "time":
            return (tr("Tempo alvo", "Target time"),
                    tr("Enter e escreve mm:ss (ex.: 12:30)", "Enter and type mm:ss (e.g. 12:30)"))
        if self.kind == "pr_pct":
            return (tr("% sobre o meu melhor", "% over my best"),
                    tr("Enter e escreve (0 = igualar; -2 = 2 % mais depressa)",
                       "Enter and type (0 = match; -2 = 2 % faster)"))
        return (tr("Potência média (W)", "Average power (W)"),
                tr("Enter e escreve os watts", "Enter and type the watts"))

    def _value_shown(self) -> str:
        if self.value is None:
            return "—"
        if self.kind == "time":
            return hms(self.value)
        if self.kind == "pr_pct":
            return f"{self.value:+.1f} %".replace(".0 %", " %")
        return f"{self.value:.0f} W"

    def summary_items(self) -> list[Item]:
        setup, err = self.prepared()
        if setup is None:
            return [Item(tr("O alvo", "The target"), value="—", detail=err or "",
                         enabled=False, data="why")]
        p, f = setup.plan, setup.feas
        mark = {"ok": "✓", "hard": "⚠", "over": "✗"}[f["level"]]
        rows = [Item(tr("Tempo previsto", "Planned time"), value=hms(p.total_s),
                     detail=setup.label, enabled=False, data="plan_time"),
                Item(tr("Potência média", "Average power"), value=f"{p.avg_w:.0f} W",
                     detail=f"{f['pct_ftp']:.0f} % FTP · "
                            f"{p.avg_w / max(1.0, self.app.db.athlete().weight_kg):.2f} W/kg",
                     enabled=False, data="plan_w"),
                Item(tr("Cabe em ti?", "Can you do it?"), value=mark, detail=f["text"],
                     enabled=False, data="feas")]
        ws = " · ".join(f"{w:.0f}" for w in p.watts)
        rows.append(Item(tr("Secções", "Sections"), value=str(len(p.sections)),
                         detail=tr("watts de cada uma: {w}", "watts of each: {w}", w=ws),
                         enabled=False, data="sections"))
        if setup.note:
            rows.append(Item(tr("Nota", "Note"), detail=setup.note, enabled=False,
                             data="note"))
        if self.entry() is not None and self.entry().virtual:
            rows.append(Item(tr("Percurso", "Course"), enabled=False, data="virtual",
                             detail=tr("este segmento não está numa rota: joga-se num percurso "
                                       "feito só com ele (o traçado, com a inclinação média)",
                                       "this segment is not on a route: it is ridden on a course "
                                       "made of just it (its path at the average gradient)")))
        hist = sp.segment_history(self.app.db, self.entry_key, self.mode, 3) \
            if self.entry_key else []
        for h in hist:
            if h["elapsed_s"] is None:
                continue
            rows.append(Item("  " + h["date"], value=hms(h["elapsed_s"]),
                             detail=(h["label"] + " · " if h["label"] else "")
                             + (f"{h['avg_w']} W" if h["avg_w"] else ""),
                             enabled=False, data="hist"))
        return rows

    # ------------------------------------------------------------ escolhas

    def _open_picker(self) -> None:
        self.app.push(SegmentPickerPopup(self.app, self.entries, self.entry_key,
                                         self._pick_segment))

    def _pick_segment(self, key_: str) -> None:
        if key_ in [e.key for e in self.entries]:
            self.entry_key = key_
            self._ensure_choices()
        self.enter()

    def _pick_kind(self, kind: str) -> None:
        self.kind = kind
        self.value = 0.0 if kind == "pr_pct" else None
        self._ensure_choices()

    def _pick_lead(self, v: int) -> None:
        self.lead_in = int(v)

    def _edit_value(self) -> None:
        label, hint = self._value_texts()
        self.app.push(ValuePopup(self.app, label, hint, self._value_shown(), self._set_value))

    def _set_value(self, text: str) -> bool:
        v = sp.parse_target(self.mode, self.kind, text)
        if v is None or (self.kind != "pr_pct" and v <= 0):
            self.app.message(tr("Não percebi o valor.", "I did not understand the value."))
            return False
        self.value = float(v)
        return True

    def adjust(self, field: str, step: int) -> bool:
        if field == "tgt":
            seg = self.segment()
            ks = [k for k, _ in sp.target_choices(self.mode, seg)] if seg else []
            if ks:
                self._pick_kind(ks[(ks.index(self.kind) + step) % len(ks)]
                                if self.kind in ks else ks[0])
            return True
        if field == "erg":
            self.erg = not self.erg
            return True
        if field == "lead":
            ls = self._lead_choices()
            i = ls.index(self.lead_in) if self.lead_in in ls else 0
            self._pick_lead(ls[(i + step) % len(ls)])
            return True
        return False          # o resto abre-se com Enter (nada de rota, auto lap ou letra)

    # ------------------------------------------------------------ ecrã

    def enter(self) -> None:
        items = [self.device_item()] + self.pace_items()
        foot = tr("←/→ muda · Enter abre · Esc cancela", "←/→ changes · Enter opens · Esc cancels")
        if not self.can_start:
            foot = tr("Falta o segmento ou o alvo", "The segment or the target is missing")
        self.chrome.set(self.title(), self.subtitle(), foot)
        self.list.set_items(items + self.buttons(), keep_index=True)

    def draw(self) -> None:
        super(SessionSetup, self).draw()        # sem a pré-visualização da letra

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and symbol in (key.LEFT, key.RIGHT) and isinstance(item.data, str):
            if self.adjust(item.data, 1 if symbol == key.RIGHT else -1):
                self.enter()
                return True
        if symbol == key.ESCAPE:
            self.app.pop()
            return True
        return super(SessionSetup, self).on_key(symbol, modifiers)

    def game(self) -> dict:
        e = self.entry()
        return {"key": self.game_key, "erg": self.erg, "seed": int(time.time()) % 100000,
                "route_id": e.route_id if e else None, "virtual": bool(e and e.virtual),
                "segment": self.entry_key, "kind": self.kind, "value": self.value,
                "lead_in_m": self.lead_in}

    def _start(self) -> None:
        a = self.app
        setup, err = self.prepared()
        if setup is None:
            a.message(err or tr("Escolhe um segmento.", "Pick a segment."))
            return
        spec = self.game()
        a.replace(RideScreen(a, route_id=spec["route_id"], workout_id=None, kind="game",
                             ghosts=[], erg=self.erg, autolap={"mode": "off", "value": 0},
                             game_spec=spec))

    def side_board(self):
        seg = self.segment()
        if seg is None:
            return Board(self.title(), [], empty=t("board.empty"))
        return sp.history_board(self.app.db, self.entry_key, self.mode, seg.name)


def section_table(result: dict) -> list[Item]:
    """As linhas da tabela por secção (plano × real × tempo ganho ou perdido) — para o
    resumo do fim da sessão."""
    rows: list[Item] = []
    for r in result.get("sections") or []:
        real_w = "—" if r.get("real_w") is None else f"{r['real_w']}"
        d = r.get("delta_s")
        gain = (tr("ganhaste {s} s", "gained {s} s", s=f"{abs(d):.0f}") if d is not None and d < -0.5
                else tr("perdeste {s} s", "lost {s} s", s=f"{abs(d):.0f}")
                if d is not None and d > 0.5 else tr("igual", "even"))
        rows.append(Item(
            f"  {r['idx'] + 1}. {r['grade']:+.1f} % · {r['length_m']} m",
            value=f"{real_w} / {r['plan_w']} W",
            detail=tr("tempo {a} (plano {b}) · {g} · Δ {d}",
                      "time {a} (plan {b}) · {g} · Δ {d}", a=hms(r["real_s"]),
                      b=hms(r["plan_s"]), g=gain, d=delta(d or 0)),
            enabled=False, data=("pace_section", r["idx"])))
    return rows
