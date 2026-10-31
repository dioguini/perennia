"""Aplicação: janela, ecrãs e ciclo principal.

Tudo o que é lógica vive em `velo.core`; aqui só se mostra e se recolhe
teclas. Os ecrãs formam uma pilha: Esc volta ao anterior.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import pyglet
from pyglet.window import key

from velo.core import boards
from velo.core import boxes as boxes_mod
from velo.core import chase as chase_mod
from velo.core import climbs as climbs_mod
from velo.core import ftp as ftp_mod
from velo.core import gpx, metrics, physics, stats, workouts
from velo.core.db import Athlete, Database
from velo.core.i18n import EN, PT, set_language, t, tr
from velo.core.ride import RideEngine, load_ghosts
from velo.core.units import (balance_text, delta, format_metric, hms, km, pair_text,
                             parse_number, weight)
from velo.core.workouts import WorkoutRunner
from velo.gfx.compat import label as make_label
from velo.gfx.hud import Hud
from velo.gfx.world import PRESETS, World
from velo import __version__, paths
from velo.io import ant, autoconnect, ble
from velo.io.hub import SensorHub
from velo.io.sim import SimulatedTrainer
from velo.ui.widgets import (ACCENT, BAD, BG, BackButton, BoardPanel, Chart, Chrome, DIM,
                             GOOD, Heatmap, Item, ListView, PANEL, Popup, StackedBars,
                             TabBar, TEXT, Tile, TopBar)

PRESET_ORDER = ("low", "medium", "high")

# Resoluções oferecidas nas Definições. As maiores do que o ecrã não aparecem.
# Abaixo de 1024×640 o HUD e os menus já não cabem.
WINDOW_SIZES = ((1280, 720), (1366, 768), (1600, 900), (1920, 1080),
                (2560, 1440), (3840, 2160))
MIN_SIZE = (1024, 640)
DEFAULT_SIZE = (1280, 760)


BOARD_W = 330


class Screen:
    """Base de um ecrã. Só o que for preciso é redefinido.

    Ecrãs com `HAS_BOARD = True` mostram uma classificação à direita, que
    acompanha a linha selecionada (`side_board`). Linhas cujo `data`
    começa por «text:» são campos de texto: o que se escreve vai para
    `text_input`, e Backspace apaga.
    """

    HAS_BOARD = False
    ROOT = False          # o ecrã inicial não tem «Voltar»
    AGENT = True          # F1 / F2: resumos do agente (não durante as sessões)
    IN_SESSION = False    # sessão de treino: Definições e Sair ficam indisponíveis
    MODAL = False         # janela por cima (o ecrã de baixo continua a correr)
    TABBED = False        # separadores por baixo do título (Tab / Shift+Tab)

    def __init__(self, app: "App"):
        self.app = app
        w, h = app.window.width, app.window.height
        self.chrome = Chrome(app.window)
        self.back_button: BackButton | None = None
        if not self.ROOT:
            self.back_button = BackButton(app.window)
            self.chrome.footer_x = 190
            self.chrome.layout()
        self.tab = 0
        self.tabs: TabBar | None = None
        if self.TABBED:
            self.tabs = TabBar(self.tab_labels(), 48, h - 98, self._tabs_width(w))
        top = self.content_top(h)
        self.list = ListView(48, top, self._list_width(w),
                             visible_rows=max(4, (top - 110) // 38))
        if self.AGENT:
            self.chrome.agent_hint.text = t("agent.hint")
        self.board_panel: BoardPanel | None = None
        if self.HAS_BOARD:
            self.board_panel = BoardPanel(w - 48 - BOARD_W, h - 124, BOARD_W)
        self._board_key: tuple | None = None

    def _list_width(self, w: int) -> int:
        return w - 96 - (BOARD_W + 30 if self.HAS_BOARD else 0)

    # -------------------------------------------------------- separadores

    def tab_labels(self) -> list[str]:
        return []

    def _tabs_width(self, w: int) -> int:
        return w - 96

    def content_top(self, h: int) -> int:
        """Onde começa a lista: mais abaixo se houver separadores."""
        return h - 130 - (44 if self.TABBED else 0)

    def set_tab(self, i: int) -> None:
        if self.tabs is None:
            return
        self.tabs.set_labels(self.tab_labels())
        n = len(self.tabs.labels_text)
        if not n:
            return
        self.tab = i % n
        self.tabs.select(self.tab)
        self.list.index = 0
        self.list.scroll = 0
        self.on_tab()
        self.enter()

    def on_tab(self) -> None:
        """Chamado ao mudar de separador (antes de `enter`)."""

    def tab_named(self, text: str) -> bool:
        """Muda para o separador cujo nome contém `text` (rato, testes, atalhos)."""
        if self.tabs is None:
            return False
        for i, lab in enumerate(self.tab_labels()):
            if text.lower() in lab.lower():
                self.set_tab(i)
                return True
        return False

    # -------------------------------------------------------- arrastar

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        return False

    def on_release(self, x: int, y: int) -> bool:
        return False

    def on_device_lost(self, name: str) -> None:
        """Um aparelho deixou de mandar dados (a aplicação já avisou)."""

    def enter(self) -> None: ...
    def leave(self) -> None: ...
    def update(self, dt: float) -> None: ...

    # --------------------------------------------------------- classificação

    def side_board(self) -> "boards.Board | None":
        return None

    def refresh_board(self) -> None:
        if self.board_panel is None:
            return
        try:
            self.board_panel.set(self.side_board())
        except Exception as e:        # um quadro partido não deve partir o menu
            self.board_panel.set(boards.Board(t("common.error"), empty=str(e)))
        self._board_key = (self.list.index, id(self.list.items))

    def draw(self) -> None:
        self.chrome.draw()
        if self.tabs is not None:
            self.tabs.draw()
        self.list.draw()
        if self.back_button is not None:
            self.back_button.draw()
        if self.board_panel is not None:
            if self._board_key != (self.list.index, id(self.list.items)):
                self.refresh_board()
            self.board_panel.draw()

    # ------------------------------------------------------------- texto

    def _text_field(self) -> str | None:
        item = self.list.selected
        if item is not None and isinstance(item.data, str) and item.data.startswith("text:"):
            return item.data[5:]
        return None

    def text_input(self, field: str, text: str) -> None: ...
    def text_backspace(self, field: str) -> None: ...

    def on_text(self, text: str) -> bool:
        field = self._text_field()
        if field is None:
            return False
        clean = "".join(c for c in text if c.isprintable() and c not in "\r\n\t")
        if clean:
            self.text_input(field, clean)
        return True

    # ------------------------------------------------------------ agente

    def agent_context(self) -> dict:
        """O que está no ecrã, para o «resumo desta página». Os ecrãs com
        gráficos ou dados próprios acrescentam-nos em `agent_data`."""
        rows = []
        for it in self.list.items:
            if isinstance(it.data, tuple) and it.data and it.data[0] == "strava":
                continue                     # acordo da API do Strava: nada para a IA
            row = {"rotulo": it.label}
            if it.value:
                row["valor"] = it.value
            if it.detail:
                row["detalhe"] = it.detail
            rows.append(row)
        out = {"ecra": type(self).__name__, "titulo": self.chrome.title.text,
               "subtitulo": self.chrome.subtitle.text, "linhas": rows}
        if self.board_panel is not None and self.board_panel.board is not None:
            b = self.board_panel.board
            out["classificacao"] = {"titulo": b.title, "linhas": [
                {"pos": r.rank, "nome": r.label, "valor": r.value, "eu": r.me}
                for r in b.rows]}
        extra = self.agent_data()
        if extra:
            out["dados"] = extra
        return out

    def agent_data(self) -> dict:
        return {}

    def open_agent(self, kind: str) -> None:
        _extra_health().AgentScreen.open(self.app, self, kind)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.AGENT and symbol in (key.F1, key.F2):
            self.open_agent("page" if symbol == key.F1 else "context")
            return True
        if self.tabs is not None and symbol == key.TAB:
            self.set_tab(self.tab + (-1 if modifiers & key.MOD_SHIFT else 1))
            return True
        if self._text_field() is not None:
            # num campo de texto, letras e espaço escrevem — não navegam
            if symbol == key.BACKSPACE:
                self.text_backspace(self._text_field() or "")
                return True
            if symbol in (key.J, key.K, key.SPACE):
                return True
            if symbol in (key.ENTER, key.RETURN):
                self.list.move(1)
                return True
        if symbol in (key.DOWN, key.J):
            self.list.move(1)
            return True
        if symbol in (key.UP, key.K):
            self.list.move(-1)
            return True
        if symbol in (key.ENTER, key.RETURN, key.SPACE):
            self.list.activate()
            return True
        if symbol == key.ESCAPE:
            self.app.pop()
            return True
        return False

    def on_mouse(self, x: int, y: int) -> bool:
        if self.back_button is not None and self.back_button.hit(x, y):
            self.app.pop()
            return True
        if self.tabs is not None:
            i = self.tabs.hit(x, y)
            if i is not None:
                self.set_tab(i)
                return True
        return self.list.on_mouse_press(x, y)

    def on_resize(self, w: int, h: int) -> None:
        self.chrome.layout()
        if self.back_button is not None:
            self.back_button.layout()
        if self.tabs is not None:
            self.tabs.layout(48, h - 98, self._tabs_width(w))
        top = self.content_top(h)
        self.list.y = top
        self.list.width = self._list_width(w)
        self.list.set_visible_rows(max(4, (top - 110) // 38))
        if self.board_panel is not None:
            self.board_panel.layout(w - 48 - BOARD_W, h - 124, BOARD_W)

    def footer(self) -> str:
        return "↑↓ mover · Enter escolher · Esc ou ← Voltar"


# --------------------------------------------------------------- menu inicial


class SportHub(Screen):
    """O menu de um desporto, por separadores: Treinar · Construtor de treinos ·
    Lista de treinos · Histórico · Estatísticas. Cada desporto preenche-os."""

    TABBED = True
    SPORT = "cycling"
    TAB_KEYS = ("train", "builder", "library", "history", "stats")

    def tab_labels(self) -> list[str]:
        return [tr("Treinar", "Train"), tr("Construtor de treinos", "Workout builder"),
                tr("Lista de treinos", "Workouts"), tr("Histórico", "History"),
                tr("Estatísticas", "Statistics")]

    def title(self) -> str:
        from velo.core import sports as sp
        return sp.name(self.SPORT)

    def subtitle(self) -> str:
        return ""

    def items_for(self, key_: str) -> list[Item]:
        return getattr(self, f"items_{key_}")()

    def items_train(self) -> list[Item]:
        return []

    def items_builder(self) -> list[Item]:
        return []

    def items_library(self) -> list[Item]:
        return []

    def items_history(self) -> list[Item]:
        return []

    def items_stats(self) -> list[Item]:
        return [Item(tr("Gráficos e análise", "Charts and analysis"),
                     detail=tr("Separadores por tipo de gráfico", "Tabs by chart type"),
                     action=lambda: self.app.push(_hubs().stats_screen(self.app, self.SPORT)))]

    def enter(self) -> None:
        key_ = self.TAB_KEYS[self.tab % len(self.TAB_KEYS)]
        items = self.items_for(key_)
        if not items:
            items = [Item(tr("Nada por aqui ainda", "Nothing here yet"), enabled=False)]
        self.chrome.set(self.title(), self.subtitle(), self.footer())
        self.list.set_items(items, keep_index=True)

    def footer(self) -> str:
        return tr("Tab separador · ↑↓ mover · Enter escolher · Esc voltar",
                  "Tab next tab · ↑↓ move · Enter choose · Esc back")


class MainMenu(SportHub):
    """Ciclismo."""

    HAS_BOARD = True
    SPORT = "cycling"

    def side_board(self):
        a = self.app
        item = self.list.selected
        which = item.data if item is not None else None
        if isinstance(which, tuple) and which and which[0] == "workout":
            return boards.workout_board(a.db, which[1], which[2])
        if which == "workouts":
            ws = a.db.workouts()
            return boards.workout_board(a.db, ws[0]["id"], ws[0]["name"]) if ws else \
                boards.Board(t("menu.workouts"), empty=t("board.empty"))
        if which == "ftp":
            return boards.ftp_board(a.db)
        if which == "challenges":
            return boards.challenges_progress_board(a.db, a.units)
        if which == "chase":
            return boards.chase_board(a.db, a.db.get("chase_level", "normal"), None)
        return boards.records_board(a.db, a.units)

    def subtitle(self) -> str:
        a = self.app
        athlete = a.db.athlete()
        wv, wu = weight(athlete.weight_kg, a.units)
        return (f"{athlete.name or '—'} · FTP {athlete.ftp_w} W · {wv:.1f} {wu} · "
                f"{a.device_summary()}")

    def items_train(self) -> list[Item]:
        a = self.app
        return [
            Item(t("menu.ride"), detail=tr("Escolhe uma rota (ou sem rota)",
                                           "Pick a route (or no route)"),
                 action=lambda: a.push(RouteLibrary(a)), data="ride"),
            Item(t("menu.challenge"), detail=t("menu.challenge_detail"),
                 action=lambda: a.push(_extra().ChallengeMenu(a)), data="chase"),
            Item(t("menu.tests"), detail=t("menu.tests_detail"),
                 action=lambda: a.push(_extra_health().TestsMenu(a, "cycling")), data="ftp"),
            Item(t("menu.challenges"), action=lambda: a.push(ChallengeScreen(a)),
                 data="challenges"),
        ]

    def items_builder(self) -> list[Item]:
        a = self.app
        b = _builder()
        items = [Item(tr("+ Novo treino (arrastar blocos)", "+ New workout (drag blocks)"),
                      action=lambda: a.push(b.BlockBuilder(a, "cycling", None)),
                      data="workouts")]
        for w in a.db.workouts():
            tss = f" · TSS ≈ {w['est_tss']:.0f}" if w["est_tss"] else ""
            items.append(Item(w["name"], value=hms(w["total_seconds"] or 0),
                              detail=(w["description"] or w["source_format"] or "") + tss
                              + tr(" · E exportar · P passos", " · E export · P steps"),
                              action=lambda wid=w["id"]: a.push(b.BlockBuilder(a, "cycling",
                                                                               wid)),
                              data=("workout", w["id"], w["name"])))
        return items

    def items_library(self) -> list[Item]:
        a = self.app
        items = [Item(t("wk.import"), action=lambda: self._import_files())]
        for w in a.db.workouts():
            items.append(Item(w["name"], value=hms(w["total_seconds"] or 0),
                              detail=w["description"] or (w["source_format"] or ""),
                              action=lambda wid=w["id"]: a.push(_brief().CyclingBrief(a, wid)),
                              data=("workout", w["id"], w["name"])))
        return items

    def _import_files(self) -> None:
        lib = WorkoutLibrary(self.app)
        self.app.push(lib)
        lib._scan_files()

    def items_history(self) -> list[Item]:
        a = self.app
        out = []
        for r in a.db.rides(limit=100):
            dv, du = km(r["distance_m"] or 0, a.units)
            bits = [f"{dv:.1f} {du}"]
            if r["avg_power_w"]:
                bits.append(f"{r['avg_power_w']:.0f} W")
            if r["tss"]:
                bits.append(f"TSS {r['tss']:.0f}")
            out.append(Item(f"{str(r['started_at'])[:16].replace('T', ' ')}  {_pretty(r['name'])}",
                            value=hms(r["moving_s"] or r["elapsed_s"] or 0),
                            detail=" · ".join(bits),
                            action=lambda rid=r["id"]: a.push(RideDetailScreen(a, rid))))
        return out

    def items_stats(self) -> list[Item]:
        a = self.app
        tot = stats.totals(a.db)
        dv, du = km(tot["km"] * 1000.0, a.units)
        rows = [Item(tr("Sessões", "Rides"), value=str(tot["rides"]), enabled=False),
                Item(tr("Horas", "Hours"), value=f"{tot['hours']:.1f}", enabled=False),
                Item(tr("Distância", "Distance"), value=f"{dv:.0f} {du}", enabled=False)]
        now = stats.fitness_now(a.db, ("cycling",))
        if now:
            rows.append(Item(tr("Fitness · fadiga · forma", "Fitness · fatigue · form"),
                             value=f"{now['ctl']:.0f} · {now['atl']:.0f} · {now['tsb']:+.0f}",
                             enabled=False))
        return super().items_stats() + rows

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if self.TAB_KEYS[self.tab] == "builder" and item is not None and \
                isinstance(item.data, tuple):
            wid = item.data[1]
            if symbol == key.E:
                self.app.push(_extra().ExportScreen(self.app, wid))
                return True
            if symbol == key.P:
                self.app.push(_extra().WorkoutEditor(self.app, wid))
                return True
            if symbol == key.DELETE:
                if getattr(self, "_armed", None) == wid:
                    self.app.db.delete_workout(wid)
                    self.app.message(t("str.deleted", name=item.label))
                    self.enter()
                else:
                    self._armed = wid
                    self.app.message(t("str.delete_again"))
                return True
        return super().on_key(symbol, modifiers)


class RideDetailScreen(Screen):
    """Uma sessão de ciclismo do histórico."""

    def __init__(self, app: "App", ride_id: str):
        super().__init__(app)
        self.ride_id = ride_id

    def enter(self) -> None:
        a = self.app
        r = a.db.conn.execute("SELECT * FROM rides WHERE id = ?", (self.ride_id,)).fetchone()
        if r is None:
            a.pop()
            return
        dv, du = km(r["distance_m"] or 0, a.units)
        items = [Item(tr("Tempo", "Time"), value=hms(r["moving_s"] or r["elapsed_s"] or 0),
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
                items.append(Item(label, value=fmt.format(v), enabled=False))
        for lp in a.db.conn.execute("SELECT * FROM laps WHERE ride_id = ? ORDER BY lap_no",
                                    (self.ride_id,)).fetchall() if _has_table(a.db, "laps") \
                else []:
            items.append(Item(f"  {tr('Volta', 'Lap')} {lp['lap_no']}",
                              value=hms((lp["end_t_s"] or 0) - (lp["start_t_s"] or 0)),
                              enabled=False))
        if r["fit_path"]:
            items.append(Item(".fit", value=r["name"] or "", detail=r["fit_path"],
                              enabled=False))
        self.chrome.set(r["name"] or t("home.cycling"), str(r["started_at"])[:16],
                        self.footer())
        fb_item = _feedback().summary_item(self.app, "ride", self.ride_id)
        if fb_item is not None:
            items.insert(0, fb_item)
        self.list.set_items(items, keep_index=True)


def _has_table(db, name: str) -> bool:
    return db.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (name,)).fetchone() is not None


# ------------------------------------------------------------ ecrã inicial


class HomeScreen(Screen):
    """Ecrã inicial: os desportos e as estatísticas, em cartões com ícone, e a
    sequência de treino (dias e semanas seguidos) com o mapa das últimas
    16 semanas."""

    ROOT = True
    # Os desportos em cima; saúde, estatísticas e inventários em baixo.
    # Dispositivos, Definições e Sair estão na faixa do topo (sempre à vista).
    TILES = (("home.cycling", "bike", ""), ("home.rowing", "rower", ""),
             ("home.running", "runner", ""), ("home.swimming", "swimmer", ""),
             ("home.gym", "kettlebell", ""),
             ("home.calendar", "calendar", ""),
             ("home.health", "heart", ""), ("home.stats", "stats", ""),
             ("home.inventory", "box", ""), ("home.exercises", "checklist", ""))
    BIG = 5               # os cinco desportos; o resto vai na fila de baixo

    def __init__(self, app: "App"):
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self.tiles = [Tile(t(key_), icon, t(note) if note else "", batch=self.batch)
                      for key_, icon, note in self.TILES]
        self.selected = 0
        self.streak_title = make_label("", font_size=16, bold=True, color=ACCENT,
                                       anchor_y="top", batch=self.batch)
        self.streak_lines = [make_label("", font_size=13, color=TEXT, anchor_y="top",
                                        batch=self.batch) for _ in range(3)]
        self.form_title = make_label("", font_size=16, bold=True, color=ACCENT,
                                     anchor_y="top", batch=self.batch)
        self.form_lines = [make_label("", font_size=13, color=TEXT, anchor_y="top",
                                      batch=self.batch) for _ in range(2)]
        self.heat_title = make_label("", font_size=11, color=DIM, anchor_y="top",
                                     batch=self.batch)
        from velo.gfx import icons
        self.flame = icons.sprite("flame", 0, 0, 26, batch=self.batch, opacity=240)
        self.pulse = icons.sprite("pulse", 0, 0, 26, batch=self.batch, opacity=240)
        self.heat = Heatmap(16, batch=self.batch)
        self._layout()

    def _actions(self):
        a = self.app
        hub = _hubs()
        return [lambda: a.push(hub.SportHub(a, "cycling")),
                lambda: a.push(hub.SportHub(a, "rowing")),
                lambda: a.push(hub.SportHub(a, "running")),
                lambda: a.push(hub.SportHub(a, "swimming")),
                lambda: a.push(hub.SportHub(a, "gym")),
                lambda: a.push(_calendar().CalendarScreen(a)),
                lambda: a.push(_extra_health().HealthMenu(a)),
                lambda: a.push(hub.stats_screen(a, None)),
                lambda: a.push(hub.InventoryScreen(a)),
                lambda: a.push(hub.ExerciseInventory(a))]

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        top = h - 120
        gap = 18
        nb = self.BIG
        big_w = (w - 96 - (nb - 1) * gap) / nb
        big_h = max(150, min(210, h * 0.27))
        for i in range(nb):
            self.tiles[i].layout(48 + i * (big_w + gap), top - big_h, big_w, big_h)
        small = len(self.tiles) - nb
        small_w = (w - 96 - (small - 1) * gap) / small
        small_h = 96
        y2 = top - big_h - gap - small_h
        for i in range(small):
            self.tiles[nb + i].layout(48 + i * (small_w + gap), y2, small_w, small_h)
        sy = y2 - 30
        if self.flame is not None:
            self.flame.x, self.flame.y = 48, sy - 26
        self.streak_title.x, self.streak_title.y = 84, sy
        for i, lab in enumerate(self.streak_lines):
            lab.x, lab.y = 84, sy - 28 - i * 22
        # forma (fitness, fadiga, forma) por baixo da sequência, ou ao lado
        fy = sy - 28 - 3 * 22 - 16
        fx = 48
        if fy - 70 < 40:
            fx, fy = 48 + (w - 96) * 0.42, sy
        if self.pulse is not None:
            self.pulse.x, self.pulse.y = fx, fy - 26
        self.form_title.x, self.form_title.y = fx + 36, fy
        for i, lab in enumerate(self.form_lines):
            lab.x, lab.y = fx + 36, fy - 28 - i * 22
            lab.font_size = 13 if w >= 1200 else 12
        cell = max(8, min(14, (h - 260 - (top - y2)) / 10))
        hx = max(420, w - 48 - 16 * (cell + 3))
        self.heat_title.x, self.heat_title.y = hx, sy
        self.heat.layout(hx, sy - 22 - 7 * (cell + 3), cell)
        for i, tile in enumerate(self.tiles):
            tile.set_selected(i == self.selected)

    def enter(self) -> None:
        a = self.app
        athlete = a.db.athlete()
        self.chrome.set("Perennia",
                        f"{athlete.name or '—'} · FTP {athlete.ftp_w} W · {a.device_summary()}",
                        "←→↑↓ escolher · Enter abrir")
        # a lista (invisível) serve o teclado e os testes; os cartões são o que se vê
        self.list.set_items([Item(tile.title.text, action=act)
                             for tile, act in zip(self.tiles, self._actions())],
                            keep_index=True)
        st = stats.streaks(a.db)
        self.streak_title.text = t("home.streak")
        self.streak_lines[0].text = (t("home.streak_days", n=st["days"]) + "   ·   "
                                     + t("home.streak_weeks", n=st["weeks"]))
        self.streak_lines[1].text = t("home.streak_best", d=st["best_days"],
                                      w=st["best_weeks"])
        self.streak_lines[2].text = t("home.this_week", n=st["rides_this_week"])
        self.form_title.text = t("home.form")
        now = stats.fitness_now(a.db)
        if now is None:
            self.form_lines[0].text = t("home.form_none")
            self.form_lines[1].text = ""
        else:
            self.form_lines[0].text = t("home.form_line", ctl=f"{now['ctl']:.0f}",
                                        atl=f"{now['atl']:.0f}", tsb=f"{now['tsb']:+.0f}")
            self.form_lines[1].text = t(f"form.{now['state']}")
        self.heat_title.text = t("home.heatmap")
        self.heat.set(stats.heatmap(a.db, 16))

    def _select(self, i: int) -> None:
        self.selected = max(0, min(len(self.tiles) - 1, i))
        self.list.index = self.selected
        for k, tile in enumerate(self.tiles):
            tile.set_selected(k == self.selected)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.RIGHT:
            self._select(self.selected + 1)
        elif symbol == key.LEFT:
            self._select(self.selected - 1)
        elif symbol == key.DOWN:
            self._select(self.BIG if self.selected < self.BIG else self.selected)
        elif symbol == key.UP:
            self._select(0 if self.selected >= self.BIG else self.selected)
        elif symbol in (key.ENTER, key.RETURN, key.SPACE):
            self._actions()[self.selected]()
        elif symbol == key.ESCAPE:
            pass                  # no ecrã inicial, Esc não sai por acidente
        else:
            return False
        return True

    def on_mouse(self, x: int, y: int) -> bool:
        for i, tile in enumerate(self.tiles):
            if tile.hit(x, y):
                self._select(i)
                self._actions()[i]()
                return True
        return False

    def on_resize(self, w: int, h: int) -> None:
        self.chrome.layout()
        self._layout()

    def draw(self) -> None:
        self.chrome.draw()
        self.batch.draw()


class ComingSoonScreen(Screen):
    """Remo e corrida: ainda por fazer. Diz o que vem aí."""

    def __init__(self, app: "App", sport: str):
        super().__init__(app)
        self.sport = sport
        from velo.gfx import icons
        self.batch = pyglet.graphics.Batch()
        self.icon = icons.sprite("rower" if sport == "rowing" else "runner", 0, 0, 120,
                                 batch=self.batch, opacity=220)
        self.text = make_label("", font_size=15, color=TEXT, multiline=True,
                               width=min(760, app.window.width - 96),
                               anchor_y="top", batch=self.batch)

    def enter(self) -> None:
        self.chrome.set(t(f"home.{self.sport}"), t("soon.title"), self.footer())
        self.text.text = t(f"soon.{self.sport}")
        w, h = self.app.window.width, self.app.window.height
        if self.icon is not None:
            self.icon.x, self.icon.y = 48, h - 290
        self.text.x, self.text.y = 200, h - 170
        self.list.y = h - 330
        self.list.set_items([Item(t("menu.tests"), detail=t("soon.tests"),
                                  action=lambda: self.app.push(
                                      _extra_health().TestsMenu(self.app, self.sport)))])

    def draw(self) -> None:
        super().draw()
        self.batch.draw()


# ------------------------------------------------------------- biblioteca


class RouteLibrary(Screen):
    HAS_BOARD = True

    def side_board(self):
        item = self.list.selected
        if item is not None and item.data:
            return boards.route_board(self.app.db, str(item.data))
        return boards.records_board(self.app.db, self.app.units)

    def enter(self) -> None:
        a = self.app
        rows = a.db.routes()
        items = [Item(t("lib.import_gpx"), action=lambda: a.push(GpxPicker(a)))]
        for row in rows:
            dv, du = km(row["distance_m"], a.units)
            detail = (f"↑ {row['ascent_m']:.0f} m · {row['climb_count']} "
                      f"{t('lib.climbs').lower()} · "
                      + (f"{row['times_ridden']}× " if row["times_ridden"]
                         else t("lib.never_ridden")))
            items.append(Item(
                ("★ " if row["favorite"] else "") + row["name"],
                value=f"{dv:.1f} {du}", detail=detail,
                action=lambda r=row: a.push(RouteDetail(a, r["id"])),
                data=row["id"]))
        self.chrome.set(t("menu.library"),
                        t("lib.empty") if not rows else f"{len(rows)} rotas",
                        "Enter abrir · F favorita · Del apagar · Esc voltar")
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.F and item is not None and item.data:
            self.app.db.toggle_favorite(str(item.data))
            self.enter()
            return True
        if symbol == key.DELETE and item is not None and item.data:
            self.app.db.delete_route(str(item.data))
            self.enter()
            return True
        return super().on_key(symbol, modifiers)


class GpxPicker(Screen):
    """Procura ficheiros .gpx em pastas prováveis; sem dependências de diálogo."""

    SEARCH = ("gpx", ".", "~/Downloads", "~/Documents", "~/Transferências",
              "~/Área de Trabalho", "~/Desktop")

    def enter(self) -> None:
        a = self.app
        found: list[Path] = []
        seen = set()
        folders = [str(p) for p in paths.user_folder("gpx")] + list(self.SEARCH)
        for folder in folders:
            base = Path(os.path.expanduser(folder))
            if not base.is_dir():
                continue
            try:
                for p in sorted(base.glob("*.gpx"))[:40]:
                    if p.resolve() not in seen:
                        seen.add(p.resolve())
                        found.append(p)
            except OSError:
                continue
        items = [Item(p.name, value=str(p.parent),
                      action=lambda q=p: self._import(q)) for p in found]
        if not items:
            items = [Item("Nenhum .gpx encontrado",
                          detail="Põe ficheiros .gpx na pasta 'gpx' ao lado da "
                                 "aplicação, ou em Downloads, e volta a abrir.",
                          enabled=False)]
        self.chrome.set(t("lib.import_gpx"), f"{len(found)} ficheiros encontrados",
                        self.footer())
        self.list.set_items(items)

    def _import(self, path: Path) -> None:
        a = self.app
        try:
            name, points = gpx.import_gpx(path)
            found = climbs_mod.detect(points, climbs_mod.Thresholds(
                min_length_m=float(a.db.get("climb_min_length_m", 500.0)),
                min_avg_grade=float(a.db.get("climb_min_avg_grade", 3.0)),
                min_gain_m=float(a.db.get("climb_min_gain_m", 60.0))))
            route_id = a.db.insert_route(name, points, found, path.name)
            a.message(f"«{name}» importada — {points[-1].dist_m / 1000.0:.1f} km, "
                      f"{len(found)} subidas")
            a.pop()
            a.push(RouteDetail(a, route_id))
        except Exception as e:
            a.message(f"{t('common.error')}: {e}")


class RouteDetail(Screen):
    HAS_BOARD = True

    def __init__(self, app: "App", route_id: str):
        super().__init__(app)
        self.route_id = route_id

    def side_board(self):
        item = self.list.selected
        if item is not None and isinstance(item.data, tuple) and item.data[0] == "climb":
            return boards.climb_board(self.app.db, item.data[1], item.data[2])
        return boards.route_board(self.app.db, self.route_id)

    def enter(self) -> None:
        a = self.app
        row = a.db.route(self.route_id)
        if row is None:
            a.pop()
            return
        dv, du = km(row["distance_m"], a.units)
        self.chrome.set(row["name"],
                        f"{dv:.1f} {du} · ↑ {row['ascent_m']:.0f} m · "
                        f"máx {row['max_grade_pct']:.1f} % · "
                        f"{row['times_ridden']}× {t('lib.times_ridden').lower()}",
                        self.footer())
        items = [Item(t("mode.start"), action=lambda: a.push(RideSetup(a, self.route_id)))]
        for c in a.db.climbs(self.route_id):
            board = a.db.climb_leaderboard(c.id or -1, limit=1)
            best = hms(board[0]["elapsed_s"]) if board else "—"
            items.append(Item(
                f"  {c.name}",
                value=f"{t('sign.category', cat=c.category)} · {best}",
                detail=f"{c.length_m / 1000.0:.1f} km @ {c.avg_grade_pct:.1f} % · "
                       f"↑ {c.gain_m:.0f} m",
                action=lambda cid=c.id, nm=c.name: a.push(
                    LeaderboardScreen(a, nm, a.db.climb_leaderboard(cid or -1))),
                data=("climb", c.id, c.name)))
        n_seg = len(_segments_mod().load(a.db, self.route_id))
        items.append(Item(tr("Segmentos do Strava", "Strava segments"),
                          value=str(n_seg) if n_seg else "",
                          action=lambda: a.push(_connect().StravaSegmentsScreen(a, self.route_id)),
                          data=("strava", "list")))
        board = a.db.route_leaderboard(self.route_id)
        if board:
            items.append(Item(t("lib.leaderboard"), value=f"{len(board)}",
                              action=lambda: a.push(LeaderboardScreen(
                                  a, row["name"], board))))
        self.list.set_items(items, keep_index=True)


class LeaderboardScreen(Screen):
    def __init__(self, app: "App", title: str, rows: list):
        super().__init__(app)
        self.title = title
        self.rows = rows

    def enter(self) -> None:
        items = []
        for i, r in enumerate(self.rows, start=1):
            extra = []
            if r["avg_power_w"]:
                extra.append(f"{r['avg_power_w']:.0f} W")
            if "avg_hr" in r.keys() and r["avg_hr"]:
                extra.append(f"{r['avg_hr']:.0f} bpm")
            items.append(Item(f"{i}.  {hms(r['elapsed_s'])}",
                              value=" · ".join(extra),
                              detail=str(r["started_at"])[:16].replace("T", " "),
                              enabled=False))
        self.chrome.set(t("lib.leaderboard"), self.title, "Esc voltar")
        self.list.set_items(items or [Item(t("stats.no_data"), enabled=False)])


# -------------------------------------------------------- preparar a sessão


class AutoLapOptions:
    """Duas linhas antes de começar qualquer treino: auto lap (desligado por
    omissão) e, se ligado, de quanto em quanto tempo ou distância."""

    AUTOLAP_SPORT = "cycling"

    def autolap_cfg(self) -> dict:
        cfg = getattr(self, "_autolap", None)
        if cfg is None:
            cfg = self._autolap = {"mode": "off", "value": 0}
        return cfg

    def autolap_items(self) -> list[Item]:
        from velo.core import sports as sp
        cfg = self.autolap_cfg()
        mode = cfg["mode"]
        rows = [Item(tr("Auto lap", "Auto lap"),
                     value={"off": tr("desligado", "off"), "time": tr("por tempo", "by time"),
                            "distance": tr("por distância", "by distance")}[mode],
                     detail=tr("←/→ ou Enter muda · desligado por omissão",
                               "←/→ or Enter changes · off by default"),
                     action=lambda: self.autolap_cycle("mode", 1), data="autolap_mode")]
        if mode != "off":
            rows.append(Item(tr("Volta a cada", "Lap every"), value=sp.autolap_text(cfg)[
                len(tr("a cada ", "every ")):], detail=tr("←/→ muda", "←/→ changes"),
                action=lambda: self.autolap_cycle("value", 1), data="autolap_value"))
        return rows

    def autolap_cycle(self, which: str, step: int) -> None:
        from velo.core import sports as sp
        cfg = self.autolap_cfg()
        sport = sp.SPORTS.get(self.AUTOLAP_SPORT)
        modes = ["off"] + list(sport.lap_units if sport else ("time",))
        if which == "mode":
            cfg["mode"] = modes[(modes.index(cfg["mode"]) + step) % len(modes)]
            opts = sp.AUTOLAP_TIMES if cfg["mode"] == "time" else \
                sp.AUTOLAP_DISTANCES.get(self.AUTOLAP_SPORT, (1000,))
            cfg["value"] = opts[min(len(opts) - 1, 3 if cfg["mode"] == "time" else 1)] \
                if cfg["mode"] != "off" else 0
        else:
            opts = list(sp.AUTOLAP_TIMES if cfg["mode"] == "time" else
                        sp.AUTOLAP_DISTANCES.get(self.AUTOLAP_SPORT, (1000,)))
            i = opts.index(cfg["value"]) if cfg["value"] in opts else 0
            cfg["value"] = opts[(i + step) % len(opts)]
        self.enter()

    def autolap_key(self, symbol: int) -> bool:
        item = self.list.selected
        if item is not None and item.data in ("autolap_mode", "autolap_value") and \
                symbol in (key.LEFT, key.RIGHT):
            self.autolap_cycle("mode" if item.data == "autolap_mode" else "value",
                               1 if symbol == key.RIGHT else -1)
            return True
        return False


class StartOptions(AutoLapOptions, Screen):
    """Antes de qualquer treino (remo, corrida, natação, voltas do ginásio):
    o que vai começar, o auto lap (desligado por omissão) e opções do desporto.
    `start(autolap, options)` abre a sessão."""

    def __init__(self, app: "App", sport: str, title: str, start: Callable,
                 lines: list[str] | None = None, options: dict | None = None):
        super().__init__(app)
        self.AUTOLAP_SPORT = sport
        self.title_text = title
        self.start_fn = start
        self.lines = lines or []
        self.options = dict(options or {})

    def enter(self) -> None:
        items = [Item(t("mode.start"), action=self._go)]
        if "pool_m" in self.options:
            items.append(Item(tr("Piscina", "Pool"), value=f"{self.options['pool_m']:g} m",
                              detail=tr("←/→ muda (25 m, 50 m, 33,3 m, 20 m)",
                                        "←/→ changes (25 m, 50 m, 33.3 m, 20 m)"),
                              action=lambda: self._cycle_pool(1), data="pool"))
        if "speed_kmh" in self.options:
            items.append(Item(tr("Velocidade inicial da passadeira", "Treadmill start speed"),
                              value=f"{self.options['speed_kmh']:.1f} km/h",
                              detail=tr("←/→ ±0,5 · na sessão: + / −", "←/→ ±0.5 · in session: + / −"),
                              data="speed"))
        items += self.autolap_items()
        for ln in self.lines:
            items.append(Item(ln, enabled=False))
        self.chrome.set(self.title_text, tr("Prepara a sessão", "Get the session ready"),
                        self.footer())
        self.list.set_items(items, keep_index=True)

    def _cycle_pool(self, step: int) -> None:
        opts = [25.0, 50.0, 33.3, 20.0]
        cur = self.options.get("pool_m", 25.0)
        i = opts.index(cur) if cur in opts else 0
        self.options["pool_m"] = opts[(i + step) % len(opts)]
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.autolap_key(symbol):
            return True
        item = self.list.selected
        if item is not None and symbol in (key.LEFT, key.RIGHT):
            step = 1 if symbol == key.RIGHT else -1
            if item.data == "pool":
                self._cycle_pool(step)
                return True
            if item.data == "speed":
                self.options["speed_kmh"] = max(0.0, min(25.0, self.options["speed_kmh"]
                                                         + 0.5 * step))
                self.enter()
                return True
        return super().on_key(symbol, modifiers)

    def _go(self) -> None:
        self.start_fn(dict(self.autolap_cfg()), dict(self.options))


class RideSetup(AutoLapOptions, Screen):
    HAS_BOARD = True

    def __init__(self, app: "App", route_id: str | None, workout_id: str | None = None,
                 kind: str = "route", ftp_protocol: str | None = None,
                 chase_level: str | None = None):
        super().__init__(app)
        self.route_id = route_id
        self.workout_id = workout_id
        self.kind = kind
        self.ftp_protocol = ftp_protocol
        self.chase_level = chase_level
        self.comparison = False
        self.erg = True
        self.ghosts: set[str] = set()

    def enter(self) -> None:
        a = self.app
        row = a.db.route(self.route_id) if self.route_id else None
        preset = a.db.get("render_preset", "low")
        past = a.db.rides(self.route_id) if self.route_id else []

        items = [
            Item(t("mode.start"), action=self._start),
            Item(t("mode.title"),
                 value=t("mode.comparison") if self.comparison else t("mode.alone"),
                 action=self._toggle_mode),
            Item(t("mode.render"), value=t(f"mode.render.{preset}"),
                 action=self._cycle_preset),
        ]
        if self.workout_id:
            items.append(Item(t("mode.erg"),
                              value=t("common.on") if self.erg else t("common.off"),
                              action=self._toggle_erg))
        items += self.autolap_items()
        if self.comparison:
            if past:
                items.append(Item(t("mode.pick_ghosts"), enabled=False))
            for r in past[:12]:
                chosen = r["id"] in self.ghosts
                items.append(Item(
                    ("✓ " if chosen else "   ") + str(r["started_at"])[:16].replace("T", " "),
                    value=hms(r["elapsed_s"] or 0),
                    detail=(f"{r['avg_power_w']:.0f} W" if r["avg_power_w"] else ""),
                    action=lambda rid=r["id"]: self._toggle_ghost(rid)))
            if not past:
                items.append(Item("Sem sessões anteriores nesta rota", enabled=False))

        if self.chase_level:
            subtitle = (f"{t('chase.title')} · {t(f'chase.level.{self.chase_level}')}"
                        + (f" · {row['name']}" if row else ""))
        else:
            subtitle = row["name"] if row else (t("menu.ftp_test") if self.ftp_protocol
                                                else t("menu.workouts"))
        self.chrome.set(t("mode.title"), subtitle, self.footer())
        self.list.set_items(items, keep_index=True)

    def side_board(self):
        db = self.app.db
        if self.chase_level:
            return boards.chase_board(db, self.chase_level, self.route_id)
        if self.workout_id:
            name = next((w["name"] for w in db.workouts() if w["id"] == self.workout_id), "")
            return boards.workout_board(db, self.workout_id, name)
        if self.ftp_protocol:
            return boards.ftp_board(db)
        return boards.route_board(db, self.route_id)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.autolap_key(symbol):
            return True
        return super().on_key(symbol, modifiers)

    def _toggle_mode(self) -> None:
        self.comparison = not self.comparison
        if not self.comparison:
            self.ghosts.clear()
        self.enter()

    def _toggle_erg(self) -> None:
        self.erg = not self.erg
        self.enter()

    def _toggle_ghost(self, ride_id: str) -> None:
        self.ghosts.symmetric_difference_update({ride_id})
        self.enter()

    def _cycle_preset(self) -> None:
        current = self.app.db.get("render_preset", "low")
        nxt = PRESET_ORDER[(PRESET_ORDER.index(current) + 1) % len(PRESET_ORDER)]
        self.app.db.set("render_preset", nxt)
        self.enter()

    def _start(self) -> None:
        self.app.replace(RideScreen(
            self.app, route_id=self.route_id, workout_id=self.workout_id,
            kind=self.kind, ghosts=sorted(self.ghosts), erg=self.erg,
            ftp_protocol=self.ftp_protocol, chase_level=self.chase_level,
            autolap=dict(self.autolap_cfg())))


# ----------------------------------------------------------------- sessão


class RideScreen(Screen):
    """Prepara o mundo, corre a sessão e passa ao resumo."""

    AGENT = False
    IN_SESSION = True

    def __init__(self, app: "App", *, route_id: str | None, workout_id: str | None,
                 kind: str, ghosts: list[str], erg: bool,
                 ftp_protocol: str | None = None, chase_level: str | None = None,
                 resume: dict | None = None, game_spec: dict | None = None,
                 autolap: dict | None = None):
        super().__init__(app)
        self.autolap = autolap
        self.resume = resume
        self.game_spec = game_spec
        self.chase_level = chase_level
        self.route_id = route_id
        self.workout_id = workout_id
        self.kind = kind
        self.ghost_ids = ghosts
        self.erg = erg
        self.ftp_protocol = ftp_protocol
        self.world: World | None = None
        self.engine: RideEngine | None = None
        self.hud: Hud | None = None
        self.preparing = True
        self._progress = make_label("", font_size=18,
                                           color=TEXT, anchor_x="center",
                                           anchor_y="center")
        self._bar = pyglet.shapes.Rectangle(0, 0, 0, 8, color=ACCENT[:3])

    @classmethod
    def from_checkpoint(cls, app: "App", cp: dict) -> "RideScreen":
        """Retomar uma sessão interrompida, com o que estava no ponto de recuperação."""
        cfg = cp["config"]
        meta = cfg.get("meta") or {}
        return cls(app, route_id=cfg.get("route_id"), workout_id=cfg.get("workout_id"),
                   kind=cfg.get("kind") or "route", ghosts=list(meta.get("ghosts") or []),
                   erg=bool(meta.get("erg", True)), ftp_protocol=meta.get("ftp_protocol"),
                   chase_level=cfg.get("chase_level"), resume=cp,
                   game_spec=meta.get("game"), autolap=meta.get("autolap"))

    def build_engine(self, sensors=None, trainer=None) -> RideEngine:
        a = self.app
        athlete = a.db.athlete()
        if self.resume is not None:
            # a sessão retoma com a FTP e o peso com que começou
            row = a.db.conn.execute("SELECT ftp_at_ride_w, weight_at_ride_kg FROM rides"
                                    " WHERE id = ?", (self.resume["session_id"],)).fetchone()
            if row is not None:
                athlete.ftp_w = row["ftp_at_ride_w"] or athlete.ftp_w
                athlete.weight_kg = row["weight_at_ride_kg"] or athlete.weight_kg
        points = a.db.route_points(self.route_id) if self.route_id else []
        climbs = a.db.climbs(self.route_id) if self.route_id else []
        runner = None
        if self.ftp_protocol:
            wk = ftp_mod.build(self.ftp_protocol, athlete.ftp_w)
            runner = WorkoutRunner(wk, athlete.ftp_w, erg_enabled=False)
        elif self.workout_id:
            rows = a.db.workout_steps(self.workout_id)
            steps = [workouts.Step(
                kind=r["kind"], duration_s=r["duration_s"] or 0,
                target_type=r["target_type"], target_lo=r["target_lo"],
                target_hi=r["target_hi"], cadence_lo=r["cadence_lo"],
                cadence_hi=r["cadence_hi"], text_cue=r["text_cue"]) for r in rows]
            name = next((w["name"] for w in a.db.workouts()
                         if w["id"] == self.workout_id), "")
            if steps:
                runner = WorkoutRunner(workouts.Workout(name, steps), athlete.ftp_w, self.erg)
        game = None
        if self.game_spec:
            from velo.core import games as games_mod
            game = games_mod.create(self.game_spec, athlete, a.db)
        return RideEngine(
            a.db, athlete, route_id=self.route_id, points=points, climbs=climbs,
            workout_runner=runner, workout_id=self.workout_id,
            ghosts=load_ghosts(a.db, self.ghost_ids), kind=self.kind,
            chase_level=self.chase_level, sensors=sensors, trainer=trainer,
            rides_dir=a.rides_dir,
            meta={"ghosts": list(self.ghost_ids), "erg": self.erg,
                  "ftp_protocol": self.ftp_protocol, "game": self.game_spec},
            resume=self.resume, game=game, autolap=self.autolap)

    def enter(self) -> None:
        if self.engine is not None:
            return
        a = self.app
        athlete = a.db.athlete()
        points = a.db.route_points(self.route_id) if self.route_id else []
        self.engine = self.build_engine(sensors=a.hub, trainer=a.hub)
        self.hud = Hud(a.window, a.db, self.engine.athlete)
        if self.workout_id and not self.ftp_protocol:
            try:                                   # objetivo de cada bloco, no plano
                self.hud.set_brief(_brief().endurance_brief(a.db, "cycling", self.workout_id))
            except Exception:
                pass
        for event in self.engine.drain_events():   # «sessão recuperada», etc.
            self.hud.handle(event)

        if points:
            self.world = World(points, a.db.get("render_preset", "low"),
                               seed=self.route_id or "")
            self.world.setup_gl()
        else:
            self.preparing = False
        self.chrome.set("", "", "")

    def update(self, dt: float) -> None:
        a = self.app
        # O render é pré-calculado antes de a sessão arrancar (req. 3).
        if self.preparing and self.world is not None:
            self.world.build_step(budget=3)
            if self.world.ready:
                self.preparing = False
            return
        if self.engine is None or self.hud is None:
            return
        a.hub.tick(dt)
        self.engine.update(dt)
        for event in self.engine.drain_events():
            self.hud.handle(event)
        self.hud.update(self.engine)

    def on_device_lost(self, name: str) -> None:
        if self.hud is not None:
            self.hud.toast(t("toast.sensor_lost", name=name), emphasis=True)

    def draw(self) -> None:
        a = self.app
        if self.preparing and self.world is not None:
            w, h = a.window.width, a.window.height
            self._progress.text = (f"{t('mode.preparing')}  "
                                   f"{self.world.build_progress * 100:.0f} %")
            self._progress.x, self._progress.y = w // 2, h // 2 + 20
            self._bar.x, self._bar.y = w // 4, h // 2 - 20
            self._bar.width = (w // 2) * self.world.build_progress
            self._progress.draw()
            self._bar.draw()
            return
        if self.world is not None and self.engine is not None:
            self.world.draw(a.window, self.engine.state.pos_m)
        if self.hud is not None:
            self.hud.draw()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.engine is None:
            return True
        if symbol == key.L:                     # volta manual (req. 13)
            self.engine.lap("manual")
            return True
        if symbol == key.P:
            self._toggle_pause()
            return True
        if self.hud is not None and self.hud.confirm_visible:
            # diálogo aberto: S/Enter terminam, N/Esc voltam à sessão
            if symbol in (key.ENTER, key.RETURN, key.S, key.Y):
                self._finish()
            elif symbol in (key.ESCAPE, key.N):
                self._cancel_finish()
            elif symbol == key.D:
                self._discard()
            return True
        if symbol == key.F10:
            self._ask_finish()
            return True
        if symbol in (key.PLUS, key.EQUAL, key.NUM_ADD, key.UP):
            self.engine.adjust_resistance(+1)
            return True
        if symbol in (key.MINUS, key.NUM_SUBTRACT, key.DOWN):
            self.engine.adjust_resistance(-1)
            return True
        if symbol == key.ESCAPE:
            # Esc não termina: pausa e mostra como terminar. Só o botão de
            # parar (F10 ou o clique) fecha a sessão e grava o .fit.
            if not self.engine.manual_pause:
                self.engine.pause()
            if self.hud is not None:
                self.hud.toast(t("ride.paused_hint"))
            return True
        return True                              # a sessão não navega menus

    def on_mouse(self, x: int, y: int) -> bool:
        if self.hud is not None and self.hud.confirm_visible:
            choice = self.hud.confirm_hit(x, y)
            if choice == "yes":
                self._finish()
            elif choice == "no":
                self._cancel_finish()
            elif choice == "discard":
                self._discard()
            return True
        if self.hud is not None and self.hud.stop_button_hit(x, y):
            self._ask_finish()
            return True
        if self.hud is not None and self.engine is not None:
            step = self.hud.resistance_hit(x, y)
            if step:
                self.engine.adjust_resistance(step)
                return True
        if self.hud is not None and self.hud.pause_button_hit(x, y):
            self._toggle_pause()
            return True
        return False

    def _ask_finish(self) -> None:
        """Terminar pergunta primeiro. Enquanto pergunta, a sessão fica parada."""
        if self.engine is None or self.hud is None:
            self._finish()
            return
        self.engine.pause(confirming=True)
        self.hud.show_confirm()

    def _cancel_finish(self) -> None:
        """«Não»: volta à sessão em pausa; pedalar retoma."""
        if self.hud is not None:
            self.hud.hide_confirm()
        if self.engine is not None:
            self.engine.resume_on_pedal()

    def _toggle_pause(self) -> None:
        # Só a pausa manual se desfaz aqui. A automática sai ao pedalar, e
        # carregar em P durante ela passa-a a manual, para não arrancar sozinha.
        if self.engine is None:
            return
        if self.engine.manual_pause:
            self.engine.resume()
        else:
            self.engine.pause()

    def _discard(self) -> None:
        """Terminar sem guardar: nada de .fit, resumo nem estatísticas."""
        if self.engine is None:
            return
        self.engine.discard()
        if self.world is not None:
            self.world.delete()
            self.world = None
        self.app.message(tr("Sessão terminada sem guardar.", "Session ended without saving."))
        self.app.pop()

    def _finish(self) -> None:
        if self.engine is None:
            return
        result = self.engine.finish()
        if self.world is not None:
            self.world.delete()
            self.world = None
        self.app.replace(SummaryScreen(self.app, result, self.ftp_protocol))

    def leave(self) -> None:
        if self.engine is not None and not self.engine.finished:
            self.engine.abort()
        if self.world is not None:
            self.world.delete()

    def on_resize(self, w: int, h: int) -> None:
        if self.hud is not None:
            self.hud.layout(w, h)

    def footer(self) -> str:
        return "L volta · P pausa · +/− resistência · F10 terminar e guardar"

    def on_text(self, text: str) -> bool:
        return True                         # na sessão as teclas não escrevem


class SummaryScreen(Screen):
    HAS_BOARD = True

    def side_board(self):
        db = self.app.db
        r = self.result
        rid = r.get("ride_id")
        if r.get("chase"):
            return boards.chase_board(db, r["chase"]["level"], r.get("route_id"),
                                      highlight_ride=rid)
        if r.get("workout_id") and r.get("kind") == "workout":
            return boards.workout_board(db, r["workout_id"], highlight_ride=rid)
        if r.get("kind") == "ftp_test":
            return boards.ftp_board(db)
        if r.get("route_id"):
            return boards.route_board(db, r["route_id"], highlight_ride=rid)
        return boards.challenges_progress_board(db, self.app.units)

    def __init__(self, app: "App", result: dict, ftp_protocol: str | None = None):
        super().__init__(app)
        self.result = result
        self.ftp_protocol = ftp_protocol
        self.ftp_estimate: tuple[float, int] | None = None

    def enter(self) -> None:
        a = self.app
        s = self.result.get("summary")
        if s is None:
            a.pop()
            return
        dv, du = km(s.distance_m, a.units)
        items: list[Item] = []

        def add(label_key: str, text: str) -> None:
            items.append(Item(t(label_key), value=text, enabled=False))

        chase = self.result.get("chase")
        if chase:
            verdict = (t("chase.caught", time=hms(chase["survived_s"])) if chase["caught"]
                       else t("chase.escaped", time=hms(chase["survived_s"])))
            if chase.get("clean") and chase.get("total"):
                verdict += " · " + t("toast.rank", rank=chase["rank"], total=chase["total"])
            elif not chase.get("clean"):
                verdict += " · " + t("chase.not_ranked")
            items.append(Item(t("summary.chase"), value=verdict, enabled=False))
        add("metric.dist_done", f"{dv:.2f} {du}")
        add("metric.elapsed", hms(s.elapsed_s))
        if s.paused_s:
            add("summary.paused", hms(s.paused_s))
        add("metric.ascent", f"{s.ascent_m:.0f} m")
        if s.route_loops:
            best = f" · {hms(s.best_loop_s)}" if s.best_loop_s else ""
            add("metric.loops", f"{s.route_loops}{best}")
        if s.avg_power_w:
            add("metric.power", f"{s.avg_power_w:.0f} W")
        if s.np_w:
            add("metric.np", f"{s.np_w:.0f} W")
        if s.tss:
            add("metric.tss_accum", f"{s.tss:.0f}")
        if s.avg_hr:
            add("metric.avg_hr", f"{s.avg_hr:.0f} bpm")
        if s.avg_cadence:
            add("metric.avg_cadence", f"{s.avg_cadence:.0f} rpm")
        if s.avg_balance_left is not None:
            add("metric.avg_balance", balance_text(s.avg_balance_left))
        p = s.pedal or {}
        if p.get("te_left") is not None or p.get("te_right") is not None:
            add("metric.avg_torque_eff",
                pair_text((p.get("te_left"), p.get("te_right"))))
        if any(p.get(k) is not None for k in ("ps_left", "ps_right", "ps_combined")):
            add("metric.avg_pedal_smooth",
                pair_text((p.get("ps_left"), p.get("ps_right"), p.get("ps_combined"))))
        if s.work_kj:
            add("metric.work_kj", f"{s.work_kj:.0f} kJ")

        for c in self.result.get("climbs", []):
            items.append(Item(f"  {c['name']}", value=hms(c["elapsed_s"]),
                              detail=f"{c.get('avg_power_w') or 0:.0f} W · "
                                     f"{c.get('avg_hr') or 0:.0f} bpm · "
                                     f"{c.get('avg_cadence') or 0:.0f} rpm · "
                                     + (f"E/D {balance_text(c['avg_balance_left'])} · "
                                        if c.get("avg_balance_left") is not None else "")
                                     + t('toast.rank', rank=c['rank'], total=c['total']),
                              enabled=False))

        for sg in self.result.get("strava", []):
            pr = sg.get("pr_s")
            items.append(Item(f"  Strava · {sg['name']}", value=hms(sg["elapsed_s"]),
                              detail=(t("seg.vs_pr", delta=delta(sg["elapsed_s"] - pr))
                                      if pr else "")
                              + (" · " + t("seg.local_pr") if sg.get("local_pr")
                                 and sg.get("local_best_s") is not None else ""),
                              enabled=False, data=("strava", sg.get("id"))))

        game = self.result.get("game")
        if game:
            items.append(Item(t(f"game.{game['game']}"), value=game.get("summary", ""),
                              detail=(t("game.rank_line", rank=game["rank"], total=game["total"])
                                      if game.get("rank") and game.get("total") else "")
                              + ("" if game.get("ranked", True) else " · " + t("chase.not_ranked")),
                              enabled=False))

        laps = self.result.get("laps", [])
        if len(laps) > 1:
            items.append(Item(t("summary.laps"), value=str(len(laps)), enabled=False))

        if self.ftp_protocol in ftp_mod.TEST_PROTOCOLS:
            # sprint, 1 min, 5 min: o resultado fica logo nos testes de aptidão
            series = self.result.get("power_series", [])
            est = ftp_mod.estimate(self.ftp_protocol, series)
            if est:
                from velo.core import fitness_tests as ft
                watts = est[1]
                extra = None
                line = f"{watts} W · {watts / max(1.0, a.db.athlete().weight_kg):.2f} W/kg"
                if self.ftp_protocol == "5min":
                    vo2 = ft.vo2max_from_5min(watts, a.db.athlete().weight_kg)
                    extra = {"vo2max": round(vo2, 1)}
                    line += f" · VO2máx ≈ {vo2:.0f} ml/kg/min"
                if not getattr(self, "_test_saved", False):
                    ft.seed(a.db)
                    ft.record_protocol(a.db, self.ftp_protocol, watts,
                                       self.result.get("ride_id"), extra)
                    self._test_saved = True
                items.insert(0, Item(t(ftp_mod.CATALOG[self.ftp_protocol].label_key),
                                     value=line, detail=t("test.saved"), enabled=False))
        elif self.ftp_protocol:
            series = self.result.get("power_series", [])
            self.ftp_estimate = ftp_mod.estimate(self.ftp_protocol, series)
            if self.ftp_estimate:
                _, est = self.ftp_estimate
                items.append(Item(t("ftp.result", ftp=est), value=t("ftp.accept"),
                                  action=self._accept_ftp))

        fit_path = self.result.get("fit_path")
        subtitle = t("summary.saved_fit", path=fit_path) if fit_path else \
            f"{t('common.error')}: o .fit não foi escrito"
        # «Fechar» à cabeça: selecionado logo, e o resultado fica todo à vista
        items.insert(0, Item(t("summary.close"), action=lambda: a.reset_to_menu()))
        ftp_rows = [i for i in items if i.action == self._accept_ftp]
        for row in ftp_rows:                       # aceitar a FTP também à vista
            items.remove(row)
            items.insert(1, row)

        if self.result.get("name"):
            subtitle = f"{self.result['name']} · {subtitle}"
        self.chrome.set(t("summary.title"), subtitle, self.footer())
        fb_item = _feedback().summary_item(self.app, "ride", self.result.get("ride_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        self.list.set_items(items)
        _feedback().maybe_ask(self, "ride", self.result.get("ride_id"))

    def _accept_ftp(self) -> None:
        if not self.ftp_estimate:
            return
        raw, est = self.ftp_estimate
        self.app.db.save_ftp_test(self.ftp_protocol or "manual", raw, est,
                                  self.result.get("ride_id"), accepted=True)
        try:
            from velo.core import fitness_tests as ft
            ft.seed(self.app.db)
            ft.record_protocol(self.app.db, self.ftp_protocol or "20min", est,
                               self.result.get("ride_id"))
        except Exception:
            pass
        self.app.message(t("ftp.result", ftp=est))
        self.app.reset_to_menu()


# -------------------------------------------------------------- dispositivos


class ModalScreen(Screen):
    """Janela por cima do ecrã atual. O de baixo continua a correr (uma sessão
    não para por se abrir os dispositivos). Esc ou clicar fora fecham."""

    MODAL = True
    AGENT = False
    W, H = 760, 520

    def __init__(self, app: "App"):
        super().__init__(app)
        self.popup = Popup(app.window, self.W, self.H)
        self._place()

    def _place(self) -> None:
        p = self.popup
        p.layout()
        c = self.chrome
        c.title.font_size = 20
        c.title.x, c.title.y = p.x + 24, p.y + p.h - 18
        c.subtitle.x, c.subtitle.y = p.x + 24, p.y + p.h - 50
        c.footer.x, c.footer.y = p.x + 160, p.y + 22
        c.message.x, c.message.y = p.x + 24, p.y + 70
        c.agent_hint.text = ""
        self.list.x = p.x + 28
        self.list.y = p.y + p.h - 92
        self.list.width = p.w - 56
        self.list.set_visible_rows(max(2, int((p.h - 92 - 96) // 38) + 1))
        if self.back_button is not None:
            self.back_button.place(p.x + 16, p.y + 12, tr("Fechar", "Close"))
        self.list._sync()

    def on_resize(self, w: int, h: int) -> None:
        self._place()

    def on_mouse(self, x: int, y: int) -> bool:
        if not self.popup.inside(x, y):
            self.app.pop()
            return True
        return super().on_mouse(x, y)

    def draw(self) -> None:
        self.popup.draw()
        self.chrome.draw()
        self.list.draw()
        if self.back_button is not None:
            self.back_button.draw()


class ConfirmScreen(ModalScreen):
    """Pergunta antes de fazer (sair da aplicação, terminar uma sessão)."""

    W, H = 560, 300

    def __init__(self, app: "App", title: str, sub: str,
                 options: list[tuple[str, Callable]], default: int = 0):
        self.title_text, self.sub_text, self.options = title, sub, options
        self.default = default
        super().__init__(app)

    def enter(self) -> None:
        self.chrome.set(self.title_text, self.sub_text, "")
        self.list.set_items([Item(lab, action=act) for lab, act in self.options])
        self.list.index = self.default
        self.list._sync()


class DeviceScreen(ModalScreen):
    """Gestor de aparelhos, numa janela por cima de tudo (também a meio de uma
    sessão): ligar, desligar, procurar, e a máquina de remo."""

    W, H = 860, 620

    def __init__(self, app: "App"):
        super().__init__(app)
        self.found: list = []
        self.scanning = False
        self.note = ""
        self._scan_result: list | None = None
        self._scan_error = ""
        self.ant_scanning = False
        self._ant_result: tuple | None = None
        self._auto_seen = app.auto_generation

    def enter(self) -> None:
        a = self.app
        pref = a.db.get("connection_preference", autoconnect.ANT_FIRST)
        items = [Item(t("dev.auto") if not a.auto_running else t("dev.auto_running"),
                      value=t(f"set.pref.{pref}"), detail=t("dev.auto_hint"),
                      action=a.start_auto_connect, enabled=not a.auto_running),
                 Item(t("dev.scan") if not self.scanning else t("dev.scanning"),
                      action=self._scan, enabled=not self.scanning),
                 Item(t("dev.scan_ant") if not self.ant_scanning else t("dev.scanning_ant"),
                      detail=t("dev.scan_ant_hint"), action=self._scan_ant,
                      enabled=not self.ant_scanning)]
        for src in a.hub.sources:
            name = getattr(src, "name", "?")
            caps = []
            if getattr(src, "supports_sim", False):
                caps.append("declive")
            if getattr(src, "supports_erg", False):
                caps.append("ERG")
            if getattr(src, "supports_spindown", False):
                caps.append("spindown")
            transport = {"ant": "ANT+", "ble": "Bluetooth"}.get(
                getattr(src, "transport", ""), "")
            items.append(Item(f"✓ {name}", value=transport or t("dev.connected"),
                              detail=" · ".join(caps),
                              action=lambda s=src: self._disconnect(s)))
        from velo.io import rower as rower_io
        for d in self.found:
            if any(getattr(s, "device_id", "") == d.device_id for s in a.hub.sources):
                continue
            proto = rower_io.is_rower(d.name, ["00001826-0000-1000-8000-00805f9b34fb"]
                                      if "ftms" in d.profiles else [])
            if proto:
                items.append(Item(d.name, value=tr("REMO", "ROWER"),
                                  detail=tr("máquina de remo: liga-se no menu do Remo",
                                            "rowing machine: connect it from the Rowing menu"),
                                  action=lambda dd=d, p=proto: self._rower(dd, p)))
                continue
            items.append(Item(d.name, value=" ".join(d.profiles).upper() or "—",
                              detail=f"rssi {d.rssi}" if d.rssi else "",
                              action=lambda dd=d: self._connect(dd)))
        for channel, info in a.ant_found:
            if getattr(info, "trainer_twin", False):
                continue          # a potência do rolo já vem pelo FE-C
            if any(getattr(s, "device_id", "") == info.device_id for s in a.hub.sources):
                continue
            items.append(Item(info.name, value="ANT+",
                              detail=t(f"dev.role.{info.role}"),
                              action=lambda ch=channel, inf=info: self._connect_ant(ch, inf)))
        if not any(getattr(s, "device_id", "") == "sim:trainer" for s in a.hub.sources):
            items.append(Item(t("dev.simulated"), action=self._add_sim))
        # máquina de remo (protocolo próprio): liga-se aqui também
        if a.rower is not None:
            items.append(Item(f"✓ {a.rower.name}", value=tr("REMO", "ROWER"),
                              detail=tr("Enter desliga", "Enter disconnects"),
                              action=self._drop_rower))
        else:
            items.append(Item(tr("Máquina de remo…", "Rowing machine…"),
                              detail=tr("procurar a Domyos / Concept2, ou usar a simulada",
                                        "find the Domyos / Concept2, or use the simulated one"),
                              action=lambda: a.push(_rowing().RowerDeviceScreen(a))))
        items.append(Item(tr("Fechar", "Close"), action=a.pop))
        if a.hub.can_control and getattr(a.hub.trainer, "supports_spindown", False):
            items.append(Item(t("dev.calibrate"), action=self._calibrate))

        reading = a.hub.reading()
        live = []
        if reading.power_w is not None:
            live.append(f"{reading.power_w} W")
        if reading.cadence_rpm is not None:
            live.append(f"{reading.cadence_rpm} rpm")
        if reading.hr_bpm is not None:
            live.append(f"{reading.hr_bpm} bpm")
        if reading.balance_left is not None:
            live.append(f"E/D {reading.balance_left:.0f}/"
                        f"{100 - reading.balance_left:.0f}")
        sub = " · ".join(live) if live else (self.note or t("dev.none"))
        self.chrome.set(t("menu.devices"), sub, self.footer())
        self.list.set_items(items, keep_index=True)

    def update(self, dt: float) -> None:
        if not self.app.in_session:          # a sessão de baixo já avança os sensores
            self.app.hub.tick(dt)
        if self._auto_seen != self.app.auto_generation:
            self._auto_seen = self.app.auto_generation
            self.enter()
        if self.ant_scanning and self._ant_result is not None:
            stick, found, error = self._ant_result
            self._ant_result = None
            self.ant_scanning = False
            self.app.ant_stick = stick
            self.app.ant_found = found
            if stick is None:
                self.note = error
            else:
                self.note = (t("dev.ant_found", n=len(found)) if found
                             else t("dev.ant_none"))
            self.enter()
            return
        # A procura corre num fio; aqui só se recolhe o resultado.
        if self.scanning and self._scan_result is not None:
            self.found = self._scan_result
            self._scan_result = None
            self.scanning = False
            self.note = (f"{len(self.found)} dispositivos" if self.found
                         else (self._scan_error or t("dev.none")))
            self._scan_error = ""
            self.enter()

    def _rower(self, d, proto: str) -> None:
        scr = _rowing().RowerDeviceScreen(self.app)
        scr.found = [(d.address, d.name, proto)]
        self.app.push(scr)

    def _scan(self) -> None:
        if not ble.bleak_available():
            self.note = ("A biblioteca bleak não está instalada — "
                         "pip install bleak. Podes usar o trainer simulado.")
            self.enter()
            return
        self.scanning = True
        self._scan_result = None
        self.note = t("dev.scanning")
        self.enter()

        def worker() -> None:
            try:
                self._scan_result = ble.scan(timeout=8.0)
            except Exception as e:
                self._scan_error = str(e)
                self._scan_result = []

        threading.Thread(target=worker, name="ble-scan", daemon=True).start()

    def _scan_ant(self) -> None:
        a = self.app
        # Uma procura nova recomeça a antena: os sensores ANT+ ligados saem.
        for src in list(a.hub.sources):
            if str(getattr(src, "device_id", "")).startswith("ant:"):
                self._disconnect(src)
        if a.ant_stick is not None:
            try:
                a.ant_stick.close()
            except Exception:
                pass
            a.ant_stick = None
        a.ant_found = []
        self.ant_scanning = True
        self._ant_result = None
        self.note = t("dev.scanning_ant")
        self.enter()

        def worker() -> None:
            try:
                stick, found = ant.scan(timeout=12.0, on_event=a.on_device_event)
                error = "" if stick is not None else ant.diagnose()
                self._ant_result = (stick, found, error)
            except Exception as e:
                self._ant_result = (None, [], f"{t('common.error')}: {e}")

        threading.Thread(target=worker, name="ant-scan", daemon=True).start()

    def _connect_ant(self, channel: int, info) -> None:
        a = self.app
        if a.ant_stick is None:
            return
        sensor = ant.AntSensor(a.ant_stick, channel, info, a.hub,
                               on_event=a.on_device_event)
        a.hub.add_source(sensor, role=info.role, is_trainer=info.can_control)
        a.db.remember_device(info.device_id, "ant", info.name, [info.role], 0,
                             role=info.role)
        self.note = f"{info.name}: {t('dev.connected')}"
        self.enter()

    def _connect(self, discovered) -> None:
        a = self.app
        sensor = ble.BleSensor(discovered, a.hub, on_event=a.on_device_event)
        if sensor.connect():
            a.hub.add_source(sensor, role=discovered.role,
                             is_trainer=discovered.can_control)
            a.db.remember_device(discovered.device_id, "ble", discovered.name,
                                 discovered.profiles, 0, role=discovered.role)
            self.note = f"{discovered.name}: {t('dev.connected')}"
        else:
            self.note = f"{discovered.name}: falhou a ligação"
        self.enter()

    def _disconnect(self, source) -> None:
        if hasattr(source, "disconnect"):
            try:
                source.disconnect()
            except Exception:
                pass
        self.app.hub.remove_source(getattr(source, "device_id", ""))
        self.enter()

    def _drop_rower(self) -> None:
        self.app.set_rower(None)
        self.enter()

    def _add_sim(self) -> None:
        self.app.hub.add_source(SimulatedTrainer(), role="simulated", is_trainer=True)
        self.note = t("dev.simulated")
        self.enter()

    def _calibrate(self) -> None:
        a = self.app
        try:
            a.hub.start_spindown()
            self.note = t("dev.calibrate_hint", speed="30 km/h")
            dev = getattr(a.hub.trainer, "device_id", "?")
            a.db.save_calibration(dev, "spindown", True, "pedido enviado")
        except Exception as e:
            self.note = f"{t('dev.calibrate_fail')}: {e}"
        self.enter()


# ---------------------------------------------------------------- definições


class SettingsScreen(Screen):
    """Definições por separadores, para não haver listas compridas."""

    TABBED = True
    # que linhas vão em cada separador (índices da lista completa, em baixo)
    GROUPS = ((0, 1, 2, 3, 4, 20, 21), (23, 24, 7, 8, 12, 13, 16, 17), (22, 5, 6, 9, 10, 11),
              (14, 15, 18, 19))

    def tab_labels(self) -> list[str]:
        return [tr("Atleta", "Athlete"), tr("Sessões", "Sessions"),
                tr("Ecrã e idioma", "Display & language"), tr("Ligações", "Connections")]

    def enter(self) -> None:
        a = self.app
        db = a.db
        ath = db.athlete()
        wv, wu = weight(ath.weight_kg, a.units)
        diff = float(db.get("trainer_difficulty", 1.0))
        extra = float(db.get("extra_resistance_pct", 0.0))
        items = [
            Item(t("set.name"), value=(ath.name or "") + "▏", detail=t("set.name_hint"),
                 data="text:name"),
            Item(t("set.age"), value=str(ath.age or "—"),
                 detail="←/→ ajustar o ano de nascimento",
                 action=lambda: None, data="age"),
            Item(t("set.weight"), value=f"{wv:.1f} {wu}",
                 detail="←/→ ±0,1 · Shift+←/→ ±1", data="weight"),
            Item(t("set.ftp"), value=f"{ath.ftp_w} W", detail="←/→ ajustar", data="ftp"),
            Item("LTHR", value=str(ath.lthr or "—"), detail="←/→ ajustar", data="lthr"),
            Item(t("set.units"),
                 value=t("set.units.metric") if a.units == "metric"
                 else t("set.units.imperial"), action=self._toggle_units),
            Item(t("set.language"), value="Português" if db.get("language") == PT
                 else "English", action=self._toggle_language),
            Item(t("set.difficulty"), value=f"{diff * 100:.0f} %",
                 detail="←/→ ajustar · escala a sensação de declive", data="difficulty"),
            Item(t("set.extra_resistance"), value=f"{extra:.0f} %",
                 detail="←/→ ajustar · resistência de base adicional", data="extra"),
            Item(t("set.render"), value=t(f"mode.render.{db.get('render_preset', 'low')}"),
                 action=self._cycle_preset),
            Item(t("set.display"), value=a.display_label(), detail=t("set.display_hint"),
                 action=self._cycle_display),
            Item(t("set.msaa"), value=self._msaa_text(), detail=t("set.msaa_hint"),
                 action=self._cycle_msaa),
            Item(t("set.lookahead"), value=str(db.get("workout_lookahead", 2)),
                 detail=t("set.lookahead_hint"), action=self._cycle_lookahead,
                 data="lookahead"),
            Item(t("set.auto_pause"),
                 value=t("common.on") if db.get("auto_pause", True) else t("common.off"),
                 detail=t("set.auto_pause_hint"), action=self._toggle_auto_pause),
            Item(t("set.connection"),
                 value=t(f"set.pref.{db.get('connection_preference', 'ant_first')}"),
                 detail=t("set.connection_hint"), action=self._cycle_connection),
            Item(t("set.auto_connect"),
                 value=t("common.on") if db.get("auto_connect", True) else t("common.off"),
                 detail=t("set.auto_connect_hint"), action=self._toggle_auto_connect),
            Item(t("set.boxes"), value=f"{boxes_mod.N_BOXES}",
                 detail=t("set.boxes_hint"), action=lambda: a.push(BoxesScreen(a))),
            Item(t("set.metrics"),
                 value=f"{len(boxes_mod.enabled_metrics(db, metrics.available()))}",
                 detail=t("set.metrics_hint"), action=lambda: a.push(MetricsCatalogScreen(a))),
            Item("Strava", value=tr("ligado", "connected") if (db.get("strava_tokens") or {})
                 .get("refresh_token") else "", detail=tr("Segmentos das rotas e os teus PR",
                                                          "Route segments and your PRs"),
                 action=lambda: a.push(_connect().StravaScreen(a))),
            Item("GarminDB", detail=tr("Dados diários do Garmin Connect",
                                       "Daily Garmin Connect data"),
                 action=lambda: a.push(_connect().GarminDBScreen(a))),
            Item(tr("Ritmo de limiar (corrida)", "Threshold pace (running)"),
                 value=hms(float(db.get("run_threshold_pace_s", 300))) + " /km",
                 detail=tr("←/→ ±5 s · usado nos treinos e zonas de corrida",
                           "←/→ ±5 s · used for running workouts and zones"), data="run_pace"),
            Item(tr("Ritmo crítico (natação)", "Critical swim speed"),
                 value=hms(float(db.get("swim_css_s", 120))) + " /100 m",
                 detail=tr("←/→ ±1 s · usado nos treinos de natação",
                           "←/→ ±1 s · used for swim workouts"), data="swim_pace"),
            Item(tr("Tema", "Theme"), value=_theme_name(db),
                 detail=tr("←/→ ou Enter · todos claros e profissionais; Ardósia para pouca luz",
                           "←/→ or Enter · light, professional themes; Slate for low light"),
                 action=lambda: self._adjust("theme", 1), data="theme"),
            Item(tr("Ecrã da sessão, por desporto", "Session screen, per sport"),
                 detail=tr("Arrasta as métricas para onde as queres ver",
                           "Drag metrics where you want them"),
                 action=lambda: a.push(_layouts().LayoutSportPicker(a))),
            Item(tr("Feedback no fim de cada sessão", "Feedback after each session"),
                 value=t("common.on") if db.get("ask_feedback", True) else t("common.off"),
                 detail=tr("RPE, dores e comentário; fica para o agente treinador",
                           "RPE, pain and comment; kept for the coach agent"),
                 action=self._toggle_feedback),
        ]
        if self.tabs is not None:
            self.tabs.set_labels(self.tab_labels())
            self.tabs.select(self.tab)
        group = self.GROUPS[self.tab % len(self.GROUPS)]
        items = [items[i] for i in group]
        self.chrome.set(t("menu.settings"), tr("Tab muda de separador", "Tab switches tabs"),
                        "←/→ ajustar · Enter alternar · Tab separador · Esc voltar")
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if item is not None and item.data and symbol in (key.LEFT, key.RIGHT):
            step = 1 if symbol == key.RIGHT else -1
            if modifiers & key.MOD_SHIFT:
                step *= 10
            self._adjust(str(item.data), step)
            return True
        return super().on_key(symbol, modifiers)

    def _adjust(self, field: str, step: int) -> None:
        db = self.app.db
        if field == "theme":
            from velo.gfx import theme as theme_mod
            keys = theme_mod.names()
            cur = str(db.get("theme", theme_mod.DEFAULT))
            i = keys.index(cur) if cur in keys else 0
            self.app.set_theme(keys[(i + (1 if step > 0 else -1)) % len(keys)])
            return
        if field == "run_pace":
            db.set("run_threshold_pace_s", max(150, min(600, float(
                db.get("run_threshold_pace_s", 300)) + 5 * (1 if step > 0 else -1))))
            self.enter()
            return
        if field == "swim_pace":
            db.set("swim_css_s", max(50, min(300, float(db.get("swim_css_s", 120))
                                             + (1 if step > 0 else -1))))
            self.enter()
            return
        ath = db.athlete()
        if abs(step) > 1 and field != "weight":
            step = 1 if step > 0 else -1
        if field == "lookahead":
            db.set("workout_lookahead",
                   max(0, min(4, int(db.get("workout_lookahead", 2)) + step)))
            self.enter()
            return
        if field == "age":
            ath.birth_year = (ath.birth_year or 1990) - step
            db.save_athlete(ath)
        elif field == "weight":
            # passo de 0,1 na unidade mostrada (kg ou lb); Shift dá passos de 1
            unit_kg = 1.0 if self.app.units == "metric" else 0.45359237
            shown = round(ath.weight_kg / unit_kg, 1) + step * 0.1
            ath.weight_kg = max(35.0, min(200.0, round(shown, 1) * unit_kg))
            db.save_athlete(ath)
        elif field == "ftp":
            ath.ftp_w = max(60, min(600, ath.ftp_w + step * 5))
            db.save_athlete(ath)
        elif field == "lthr":
            ath.lthr = max(100, min(220, (ath.lthr or 160) + step))
            db.save_athlete(ath)
        elif field == "difficulty":
            value = max(0.0, min(1.5, float(db.get("trainer_difficulty", 1.0))
                                 + step * 0.05))
            db.set("trainer_difficulty", round(value, 2))
        elif field == "extra":
            value = max(0.0, min(20.0, float(db.get("extra_resistance_pct", 0.0))
                                 + step))
            db.set("extra_resistance_pct", value)
        self.enter()

    def text_input(self, field: str, text: str) -> None:
        if field != "name":
            return
        ath = self.app.db.athlete()
        ath.name = ((ath.name or "") + text)[:40]
        self.app.db.save_athlete(ath)
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field != "name":
            return
        ath = self.app.db.athlete()
        ath.name = (ath.name or "")[:-1]
        self.app.db.save_athlete(ath)
        self.enter()

    def _toggle_feedback(self) -> None:
        db = self.app.db
        db.set("ask_feedback", not db.get("ask_feedback", True))
        self.enter()

    def _cycle_lookahead(self) -> None:
        db = self.app.db
        db.set("workout_lookahead", (int(db.get("workout_lookahead", 2)) + 1) % 5)
        self.enter()

    def _msaa_text(self) -> str:
        want = int(self.app.db.get("msaa_samples", 4))
        text = f"{want}×" if want else t("common.off")
        if want != self.app.msaa_samples:
            text += " · " + t("set.msaa_restart")
        return text

    def _cycle_msaa(self) -> None:
        db = self.app.db
        order = (4, 2, 0)
        cur = int(db.get("msaa_samples", 4))
        db.set("msaa_samples", order[(order.index(cur) + 1) % 3] if cur in order else 4)
        self.enter()

    def _cycle_display(self) -> None:
        a = self.app
        options = a.display_options()
        current = (True, 0, 0) if a.window.fullscreen else \
            (False, a.window.width, a.window.height)
        # próxima opção maior do que a atual; depois do ecrã inteiro, volta ao início
        later = [o for o in options if not o[0] and not current[0]
                 and (o[1], o[2]) > (current[1], current[2])]
        if current[0]:
            nxt = options[0]
        elif later:
            nxt = later[0]
        else:
            nxt = options[-1]
        a.set_display(nxt[0], nxt[1], nxt[2])
        self.enter()

    def _cycle_connection(self) -> None:
        db = self.app.db
        prefs = autoconnect.PREFERENCES
        cur = db.get("connection_preference", autoconnect.ANT_FIRST)
        db.set("connection_preference",
               prefs[(prefs.index(cur) + 1) % len(prefs)] if cur in prefs else prefs[0])
        self.app.apply_connection_preference()
        self.enter()

    def _toggle_auto_connect(self) -> None:
        db = self.app.db
        db.set("auto_connect", not db.get("auto_connect", True))
        self.enter()

    def _toggle_auto_pause(self) -> None:
        db = self.app.db
        db.set("auto_pause", not db.get("auto_pause", True))
        self.enter()

    def _toggle_units(self) -> None:
        a = self.app
        a.db.set("units", "imperial" if a.units == "metric" else "metric")
        a.units = a.db.get("units")
        self.enter()

    def _toggle_language(self) -> None:
        db = self.app.db
        new = EN if db.get("language") == PT else PT
        db.set("language", new)
        set_language(new)
        self.app._topbar_texts()
        self.enter()

    def _cycle_preset(self) -> None:
        db = self.app.db
        current = db.get("render_preset", "low")
        db.set("render_preset",
               PRESET_ORDER[(PRESET_ORDER.index(current) + 1) % len(PRESET_ORDER)])
        self.enter()


class BoxesScreen(Screen):
    """As 6 caixas do ecrã da sessão. Enter abre uma para a editar."""

    def enter(self) -> None:
        a = self.app
        bx = boxes_mod.load(a.db, metrics.REGISTRY)
        items = []
        for i, box in enumerate(bx):
            names = [metrics.REGISTRY[m].label for m in box["metrics"]]
            items.append(Item(boxes_mod.title(bx, i),
                              value=f"{len(names)}/{boxes_mod.MAX_PER_BOX}",
                              detail=" · ".join(f"{k + 1}. {n}" for k, n in enumerate(names))
                              or t("box.empty"),
                              action=lambda idx=i: a.push(BoxEditor(a, idx))))
        items.append(Item(t("box.reset"), action=self._reset))
        self.chrome.set(t("set.boxes"), t("set.boxes_hint"), self.footer())
        self.list.set_items(items, keep_index=True)

    def _reset(self) -> None:
        boxes_mod.save(self.app.db, [{"name": "", "metrics": list(m)}
                                     for m in boxes_mod.DEFAULT_BOXES])
        self.enter()


class MetricsCatalogScreen(Screen):
    """Liga e desliga métricas. As desligadas não aparecem no editor das caixas."""

    def enter(self) -> None:
        a = self.app
        on = set(boxes_mod.enabled_metrics(a.db, metrics.available()))
        items = []
        for mid in metrics.available():
            m = metrics.REGISTRY[mid]
            items.append(Item(("✓ " if mid in on else "   ") + m.label,
                              value=t("common.on") if mid in on else t("common.off"),
                              action=lambda x=mid: self._toggle(x), data=mid))
        self.chrome.set(t("set.metrics"), f"{len(on)}/{len(items)}", self.footer())
        self.list.set_items(items, keep_index=True)

    def _toggle(self, mid: str) -> None:
        on = mid in boxes_mod.enabled_metrics(self.app.db, metrics.available())
        boxes_mod.set_enabled(self.app.db, mid, not on)
        self.enter()


class BoxEditor(Screen):
    """Uma caixa: nome e até 4 métricas, numeradas pela ordem em que aparecem."""

    def __init__(self, app: "App", index: int):
        super().__init__(app)
        self.index = index

    def _boxes(self) -> list[dict]:
        return boxes_mod.load(self.app.db, metrics.REGISTRY)

    def enter(self) -> None:
        bx = self._boxes()
        box = bx[self.index]
        name = box["name"]
        items = [Item(t("ch.name"), value=(name or boxes_mod.default_name(self.index)) + "▏",
                      detail=t("ch.typing"), data="text:name")]
        chosen = box["metrics"]
        enabled = boxes_mod.enabled_metrics(self.app.db, metrics.available())
        for mid in chosen + [m for m in enabled if m not in chosen]:
            label = metrics.REGISTRY[mid].label
            if mid in chosen:
                items.append(Item(f"{chosen.index(mid) + 1}.  {label}", value="✓",
                                  action=lambda m=mid: self._toggle(m), data=("metric", mid)))
            else:
                items.append(Item(f"     {label}", action=lambda m=mid: self._toggle(m),
                                  data=("metric", mid)))
        self.chrome.set(boxes_mod.title(bx, self.index),
                        f"{len(chosen)}/{boxes_mod.MAX_PER_BOX}", t("box.edit_hint"))
        self.list.set_items(items, keep_index=True)

    def _toggle(self, mid: str) -> None:
        bx = self._boxes()
        if not boxes_mod.toggle(bx, self.index, mid):
            self.app.message(t("box.full"))
            return
        boxes_mod.save(self.app.db, bx)
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if (symbol in (key.LEFT, key.RIGHT) and item is not None
                and isinstance(item.data, tuple) and item.data[0] == "metric"):
            bx = self._boxes()
            mid = item.data[1]
            if mid in bx[self.index]["metrics"]:
                boxes_mod.move(bx, self.index, mid, -1 if symbol == key.LEFT else 1)
                boxes_mod.save(self.app.db, bx)
                self.enter()
                # a seleção acompanha a métrica que se mexeu
                for k, it in enumerate(self.list.items):
                    if it.data == ("metric", mid):
                        self.list.index = k
                        self.list._sync()
            return True
        return super().on_key(symbol, modifiers)

    def text_input(self, field: str, text: str) -> None:
        bx = self._boxes()
        bx[self.index]["name"] = (bx[self.index]["name"] + text)[:24]
        boxes_mod.save(self.app.db, bx)
        self.enter()

    def text_backspace(self, field: str) -> None:
        bx = self._boxes()
        current = bx[self.index]["name"] or boxes_mod.default_name(self.index)
        bx[self.index]["name"] = current[:-1]
        boxes_mod.save(self.app.db, bx)
        self.enter()


# ----------------------------------------------------------------- treinos


class WorkoutLibrary(Screen):
    SEARCH = ("workouts", ".", "~/Downloads", "~/Documents")
    HAS_BOARD = True

    def side_board(self):
        item = self.list.selected
        if item is not None and isinstance(item.data, tuple) and item.data[0] == "workout":
            return boards.workout_board(self.app.db, item.data[1], item.data[2])
        return boards.Board(t("menu.workouts"), empty=t("board.empty"))

    def enter(self) -> None:
        a = self.app
        items = [Item(t("wk.import"), action=self._scan_files)]
        for w in a.db.workouts():
            items.append(Item(w["name"], value=hms(w["total_seconds"] or 0),
                              detail=w["description"] or (w["source_format"] or ""),
                              action=lambda wid=w["id"]: a.push(
                                  _brief().CyclingBrief(a, wid)),
                              data=("workout", w["id"], w["name"])))
        self.chrome.set(t("menu.workouts"), "", "Del apagar · Esc voltar")
        self.list.set_items(items, keep_index=True)

    def _scan_files(self) -> None:
        a = self.app
        found: list[Path] = []
        folders = [str(p) for p in paths.user_folder("workouts")] + list(self.SEARCH)
        for folder in dict.fromkeys(folders):
            base = Path(os.path.expanduser(folder))
            if base.is_dir():
                for pattern in ("*.zwo", "*.mrc", "*.erg"):
                    found.extend(sorted(base.glob(pattern))[:25])
        items = [Item(p.name, value=str(p.parent),
                      action=lambda q=p: self._import(q)) for p in found]
        if not items:
            items = [Item("Nenhum treino encontrado",
                          detail="Põe ficheiros .zwo, .mrc ou .erg na pasta "
                                 "'workouts' ao lado da aplicação.", enabled=False)]
        self.chrome.set(t("wk.import"), f"{len(found)} ficheiros", self.footer())
        self.list.set_items(items)

    def _import(self, path: Path) -> None:
        a = self.app
        try:
            wk = workouts.import_workout(path)
            a.db.insert_workout(wk.name, [s.as_dict() for s in wk.steps],
                                wk.source_format, wk.description,
                                wk.estimated_tss(a.db.athlete().ftp_w))
            a.message(f"«{wk.name}» importado — {len(wk.steps)} passos")
            self.enter()
        except Exception as e:
            a.message(f"{t('common.error')}: {e}")


class WorkoutRouteChoice(Screen):
    """Em ERG a rota é só paisagem, mas continua a ser escolhida (req. 21)."""

    def __init__(self, app: "App", workout_id: str):
        super().__init__(app)
        self.workout_id = workout_id

    def enter(self) -> None:
        a = self.app
        items = [Item(f"{r['name']}", value=f"{r['distance_m'] / 1000.0:.1f} km",
                      action=lambda rid=r["id"]: a.push(RideSetup(
                          a, rid, self.workout_id, kind="workout")))
                 for r in a.db.routes()]
        items.append(Item("Sem rota (apenas o treino)",
                          action=lambda: a.push(RideSetup(
                              a, None, self.workout_id, kind="workout"))))
        self.chrome.set(t("menu.workouts"), t("menu.library"), self.footer())
        self.list.set_items(items)


class FtpScreen(Screen):
    HAS_BOARD = True

    def side_board(self):
        return boards.ftp_board(self.app.db)

    def enter(self) -> None:
        a = self.app
        items = []
        for proto in ftp_mod.PROTOCOLS:
            info = ftp_mod.CATALOG[proto]
            items.append(Item(t(info.label_key), detail=info.description_pt,
                              action=lambda p=proto: a.push(FtpRouteChoice(a, p))))
        history = a.db.ftp_history()
        if history:
            items.append(Item("Histórico", value=f"{len(history)} testes", enabled=False))
            for h in history[-5:]:
                items.append(Item(f"  {h['tested_at'][:10]}", value=f"{h['ftp_w']} W",
                                  detail=h["protocol"], enabled=False))
        self.chrome.set(t("menu.ftp_test"), t("ftp.pick"), self.footer())
        self.list.set_items(items, keep_index=True)


class FtpRouteChoice(Screen):
    def __init__(self, app: "App", protocol: str):
        super().__init__(app)
        self.protocol = protocol

    def enter(self) -> None:
        a = self.app
        items = [Item(f"{r['name']}", value=f"{r['distance_m'] / 1000.0:.1f} km",
                      action=lambda rid=r["id"]: a.push(RideSetup(
                          a, rid, None, kind="ftp_test", ftp_protocol=self.protocol)))
                 for r in a.db.routes()]
        items.append(Item("Sem rota", action=lambda: a.push(RideSetup(
            a, None, None, kind="ftp_test", ftp_protocol=self.protocol))))
        self.chrome.set(t("menu.ftp_test"), t(ftp_mod.CATALOG[self.protocol].label_key),
                        self.footer())
        self.list.set_items(items)


# ---------------------------------------------------------------- desafios


class ChallengeScreen(Screen):
    HAS_BOARD = True

    def side_board(self):
        a = self.app
        item = self.list.selected
        if item is not None and isinstance(item.data, int):
            ch = next((c for c in a.db.challenges() if c["id"] == item.data), None)
            if ch is not None:
                return boards.challenge_board(a.db, ch, a.units)
        return boards.challenges_progress_board(a.db, a.units)

    def enter(self) -> None:
        a = self.app
        items = [Item(t("ch.new"), detail=t("ch.new_title"),
                      action=lambda: a.push(ChallengeCreate(a)))]
        for ch in a.db.challenges():
            attempt = a.db.ensure_attempt(ch["id"])
            target, progress = ch["target"], attempt["progress"]
            done_txt = boards.challenge_progress_text(
                ch["metric"], progress, target, ch["display_unit"], a.units)
            pct = min(100.0, progress / max(target, 1e-9) * 100.0)
            board = a.db.challenge_leaderboard(ch["id"], limit=1)
            best = (t("ch.completed_in", time=boards.long_duration(board[0]["elapsed_s"]))
                    if board else t("ch.in_progress"))
            items.append(Item(ch["name"], value=f"{pct:.0f} %",
                              detail=f"{done_txt} · {best}",
                              action=lambda c=ch: a.push(ChallengeDetail(a, dict(c))),
                              data=ch["id"]))
        self.chrome.set(t("menu.challenges"), "", self.footer())
        self.list.set_items(items, keep_index=True)


class ChallengeCreate(Screen):
    """Novo desafio: tipo, objetivo escrito à mão, unidade e nome opcional.

    O objetivo aceita decimais nos dois formatos («5000.34» ou «5000,34»)
    e a linha mostra logo como foi lido, para não haver surpresas.
    """

    METRICS = ("distance_m", "ascent_m")

    def __init__(self, app: "App"):
        super().__init__(app)
        self.metric = "distance_m"
        self.value_text = ""
        self.name_text = ""
        imperial = app.units == "imperial"
        self.unit = "mi" if imperial else "km"

    def _units_for(self) -> tuple[str, ...]:
        imperial = self.app.units == "imperial"
        if self.metric == "distance_m":
            return ("mi", "ft") if imperial else ("km", "m")
        return ("ft", "mi") if imperial else ("m", "km")

    def target_m(self) -> float | None:
        v = parse_number(self.value_text)
        if v is None or v <= 0:
            return None
        return v * boards.CHALLENGE_UNITS[self.unit]

    def auto_name(self) -> str:
        target = self.target_m()
        if target is None:
            return ""
        shown = boards.challenge_target_text(self.metric, target, self.unit, self.app.units)
        return t(f"ch.auto.{self.metric}", v=shown)

    def enter(self) -> None:
        target = self.target_m()
        reading = ""
        if self.value_text:
            reading = (f"= {boards.challenge_target_text(self.metric, target, self.unit)}"
                       if target is not None else t("ch.invalid"))
        name_value = (self.name_text + "▏") if self.name_text else \
            f"({t('ch.name_auto')}: {self.auto_name() or '—'})"
        items = [
            Item(t("ch.type"), value=t(f"ch.type.{self.metric}"),
                 detail="Enter alterna", action=self._toggle_metric),
            Item(t("ch.value"), value=(self.value_text or "") + "▏",
                 detail=reading or t("ch.typing"), data="text:value"),
            Item(t("ch.unit"), value=self.unit, detail="Enter alterna",
                 action=self._cycle_unit),
            Item(t("ch.name"), value=name_value, detail=t("ch.typing"),
                 data="text:name"),
            Item(t("ch.create"), action=self._create, enabled=target is not None),
        ]
        self.chrome.set(t("ch.new_title"), t("ch.typing"), self.footer())
        self.list.set_items(items, keep_index=True)

    def text_input(self, field: str, text: str) -> None:
        if field == "value":
            allowed = "".join(c for c in text if c in "0123456789.,")
            self.value_text = (self.value_text + allowed)[:16]
        elif field == "name":
            self.name_text = (self.name_text + text)[:48]
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "value":
            self.value_text = self.value_text[:-1]
        elif field == "name":
            self.name_text = self.name_text[:-1]
        self.enter()

    def _toggle_metric(self) -> None:
        i = self.METRICS.index(self.metric)
        self.metric = self.METRICS[(i + 1) % len(self.METRICS)]
        self.unit = self._units_for()[0]
        self.enter()

    def _cycle_unit(self) -> None:
        options = self._units_for()
        i = options.index(self.unit) if self.unit in options else -1
        self.unit = options[(i + 1) % len(options)]
        self.enter()

    def _create(self) -> None:
        a = self.app
        target = self.target_m()
        if target is None:
            a.message(t("ch.invalid"))
            return
        name = self.name_text.strip() or self.auto_name()
        a.db.create_challenge(name, self.metric, target, display_unit=self.unit)
        a.message(t("ch.created", name=name))
        a.pop()


class ChallengeDetail(Screen):
    HAS_BOARD = True

    def __init__(self, app: "App", challenge: dict):
        super().__init__(app)
        self.challenge = challenge

    def side_board(self):
        return boards.challenge_board(self.app.db, self.challenge, self.app.units)

    def enter(self) -> None:
        a = self.app
        ch = self.challenge
        attempt = a.db.ensure_attempt(ch["id"])
        items = [Item(t("ch.reset"), action=self._reset)]
        board = a.db.challenge_leaderboard(ch["id"])
        if board:
            items.append(Item(t("ch.leaderboard"), enabled=False))
            for i, row in enumerate(board, start=1):
                items.append(Item(f"{i}.  {boards.long_duration(row['elapsed_s'])}",
                                  detail=f"{row['started_at'][:10]} → "
                                         f"{(row['completed_at'] or '')[:10]}",
                                  enabled=False))
        else:
            items.append(Item(t("stats.no_data"), enabled=False))
        if not ch["is_default"]:
            items.append(Item(t("ch.delete"), action=self._delete))
        progress = boards.challenge_progress_text(
            ch["metric"], attempt["progress"], ch["target"], ch.get("display_unit"),
            a.units)
        self.chrome.set(ch["name"], progress, self.footer())
        self.list.set_items(items)

    def _reset(self) -> None:
        self.app.db.reset_attempt(self.challenge["id"])
        self.app.message(t("ch.reset"))
        self.enter()

    def _delete(self) -> None:
        self.app.db.delete_challenge(self.challenge["id"])
        self.app.pop()


# --------------------------------------------------------------------- fuga


class ChaseScreen(Screen):
    """Escolha do nível da fuga. A classificação acompanha o nível."""

    HAS_BOARD = True

    def side_board(self):
        item = self.list.selected
        level = item.data if item is not None and item.data in chase_mod.LEVELS \
            else self.app.db.get("chase_level", "normal")
        return boards.chase_board(self.app.db, level, None)

    def enter(self) -> None:
        a = self.app
        items = []
        for level in chase_mod.LEVEL_ORDER:
            lv = chase_mod.LEVELS[level]
            best = a.db.chase_leaderboard(level, None, limit=1)
            items.append(Item(
                t(f"chase.level.{level}"),
                value=hms(best[0]["survived_s"]) if best else "—",
                detail=(f"{lv.start_pct * 100:.0f} % FTP, +{lv.step_pct * 100:.0f} %/min · "
                        + t("chase.ftp_after",
                            m=f"{chase_mod.minutes_to_ftp(lv):.0f}")),
                action=lambda lvl=level: self._pick(lvl), data=level))
        self.chrome.set(t("chase.title"), t("chase.pick"), self.footer())
        self.list.set_items(items, keep_index=True)
        if not self.list.index:
            current = a.db.get("chase_level", "normal")
            if current in chase_mod.LEVEL_ORDER:
                self.list.index = chase_mod.LEVEL_ORDER.index(current)
                self.list._sync()

    def _pick(self, level: str) -> None:
        self.app.db.set("chase_level", level)
        self.app.push(ChaseRouteChoice(self.app, level))


class ChaseRouteChoice(Screen):
    """O pelotão anda na mesma estrada; sem rota, é tudo plano."""

    HAS_BOARD = True

    def __init__(self, app: "App", level: str):
        super().__init__(app)
        self.level = level

    def side_board(self):
        item = self.list.selected
        route_id = item.data if item is not None and isinstance(item.data, str) else None
        return boards.chase_board(self.app.db, self.level, route_id)

    def enter(self) -> None:
        a = self.app

        def best(route_id):
            rows = a.db.chase_leaderboard(self.level, route_id, limit=1)
            return hms(rows[0]["survived_s"]) if rows else "—"

        items = [Item(t("board.no_route"), value=best(None), detail=t("chase.flat"),
                      action=lambda: a.push(RideSetup(
                          a, None, None, kind="chase", chase_level=self.level)))]
        for r in a.db.routes():
            items.append(Item(r["name"], value=best(r["id"]),
                              detail=f"{r['distance_m'] / 1000.0:.1f} km · "
                                     f"↑ {r['ascent_m']:.0f} m",
                              action=lambda rid=r["id"]: a.push(RideSetup(
                                  a, rid, None, kind="chase", chase_level=self.level)),
                              data=r["id"]))
        self.chrome.set(t("chase.title"), t(f"chase.level.{self.level}"), self.footer())
        self.list.set_items(items)


# -------------------------------------------------------------- estatísticas


class StatsScreen(Screen):
    """Explorador de estatísticas.

    Quatro linhas de controlo em cima — gráfico, métrica (ou ponto, ou
    tabela), agrupar por, intervalo — que se mudam com ←/→ ou Enter. Por
    baixo, o resumo do período com o percentil em que estás, e o gráfico.

    A curva de potência é sempre do histórico todo; o resto segue o período
    escolhido (dias, semanas, meses, trimestres, semestres ou anos).
    """

    TABBED = True                  # os gráficos por separadores
    VIEW_KEY = "stats.view."
    STATS_SPORT = "cycling"        # o desporto escolhido na linha «Desporto»
    VIEWS = ("power_curve", "evolution", "zones", "zones_period", "load", "eftp", "profile",
             "cadence", "balance")
    SPORTS = ("cycling",)          # de que desportos vem a carga (fitness/fadiga/forma)
    COUNTS = (4, 6, 8, 12, 16, 24, 36, 52, 104)
    RECORD_ROWS = 4
    CHART_BOTTOM = 112

    def __init__(self, app: "App"):
        super().__init__(app)
        self.view = 0
        self.metric = "distance"
        self.grouping = app.db.get("stats_grouping", "week")
        self.count = int(app.db.get("stats_count", 12))
        self.sex = app.db.get("power_profile_sex", "male")
        self.zkind = "power"
        self._eftp: dict | None = None
        self.point: int | None = None
        self._curve: list[dict] = []
        w, h = app.window.width, app.window.height
        self.chart = Chart(*self.chart_box(w, h))
        self.bars = StackedBars()
        self.bars.layout(*self._bars_box(w, h))
        self.summary = [make_label("", font_size=12, color=TEXT, anchor_y="top"),
                        make_label("", font_size=12, color=ACCENT, anchor_y="top")]

    # ---------------------------------------------------------------- medidas

    def tab_labels(self) -> list[str]:
        return [t(f"{self.VIEW_KEY}{v}") for v in self.VIEWS]

    def on_tab(self) -> None:
        self.view = self.tab % len(self.VIEWS)
        self.point = None

    def sport_row(self) -> Item:
        from velo.core import sports as sp
        name = sp.name(self.STATS_SPORT) if self.STATS_SPORT else tr("Todos", "All")
        return Item(tr("Desporto", "Sport"), value=name, data="sport",
                    detail=tr("←/→ outro desporto · Tab outro gráfico",
                              "←/→ another sport · Tab another chart"))

    def switch_sport(self, step: int) -> None:
        order = [None, "cycling", "rowing", "running", "swimming", "gym"]
        cur = order.index(self.STATS_SPORT) if self.STATS_SPORT in order else 0
        nxt = order[(cur + step) % len(order)]
        self.app.replace(_hubs().stats_screen(self.app, nxt))

    def chart_box(self, w: int, h: int) -> tuple[int, int, int, int]:
        list_bottom = self.content_top(h) - (self.RECORD_ROWS - 1) * 38 - 26
        top = list_bottom - 40 - 44           # título do gráfico e as 2 linhas de resumo
        height = max(120, top - self.CHART_BOTTOM)
        return 96, self.CHART_BOTTOM, w - 144, height

    def _bars_box(self, w: int, h: int):
        x, y, cw, ch = self.chart_box(w, h)
        return x, y + ch, cw, max(48, min(72, ch / 4))

    # ------------------------------------------------------------------ linhas

    def enter(self) -> None:
        a = self.app
        tot = stats.totals(a.db)
        dv, du = km(tot["km"] * 1000.0, a.units)
        self.chrome.set(
            t("menu.statistics"),
            f"{t('stats.rides')} {tot['rides']} · {t('stats.total_hours')} "
            f"{tot['hours']:.1f} · {dv:.0f} {du} · ↑ {tot['ascent_m']:.0f} m",
            "←/→ mudar · ↑↓ escolher a linha · clica no gráfico para ver um ponto")
        view = self.VIEWS[self.view]
        rows = [self.sport_row()]
        if view == "power_curve":
            rows.append(Item(t("stats.row.point"), value=self._point_text() or "—",
                             data="point"))
        elif view == "evolution":
            rows.append(Item(t("stats.row.metric"), value=t(f"stats.metric.{self.metric}"),
                             data="metric"))
        elif view == "profile":
            rows.append(Item(t("stats.row.table"), value=t(f"stats.sex.{self.sex}"),
                             data="sex"))
        elif view == "zones_period":
            rows.append(Item(t("stats.row.metric"), value=t(f"tiz.{self.zkind}"),
                             data="zkind"))
        elif view == "eftp":
            est = stats.estimated_ftp(self.app.db)
            self._eftp = est
            rows.append(Item(t("stats.eftp.apply", ftp=est["ftp"]) if est else
                             t("stats.eftp.none"), value=t("ftp.accept") if est else "",
                             data="apply_eftp" if est else None, enabled=bool(est)))
        else:
            rows.append(Item(t("stats.row.metric"), value="—", enabled=False))
        periodic = view in ("evolution", "zones", "zones_period", "load", "eftp", "balance")
        rows.append(Item(t("stats.row.group"), value=t(f"stats.group.{self.grouping}"),
                         data="group", enabled=periodic))
        rows.append(Item(t("stats.row.range"),
                         value=t("stats.range", n=self.count,
                                 unit=t(f"stats.unit.{self.grouping}")),
                         data="range", enabled=periodic))
        self.list.set_items(rows, keep_index=True)
        self.list.y = self.content_top(self.app.window.height)
        self.list.set_visible_rows(self.RECORD_ROWS)
        self._refresh_chart()

    def _cycle(self, which: str, step: int) -> None:
        if which == "sport":
            self.switch_sport(step)
            return
        if which == "view":
            self.view = (self.view + step) % len(self.VIEWS)
            self.point = None
            if self.tabs is not None:
                self.tab = self.view
                self.tabs.select(self.tab)
        elif which == "metric":
            ms = stats.PERIOD_METRICS
            self.metric = ms[(ms.index(self.metric) + step) % len(ms)]
        elif which == "group":
            gs = stats.GROUPINGS
            self.grouping = gs[(gs.index(self.grouping) + step) % len(gs)]
            self.app.db.set("stats_grouping", self.grouping)
        elif which == "range":
            cs = self.COUNTS
            i = cs.index(self.count) if self.count in cs else 3
            self.count = cs[max(0, min(len(cs) - 1, i + step))]
            self.app.db.set("stats_count", self.count)
        elif which == "sex":
            self.sex = "female" if self.sex == "male" else "male"
            self.app.db.set("power_profile_sex", self.sex)
        elif which == "zkind":
            self.zkind = "hr" if self.zkind == "power" else "power"
        elif which == "apply_eftp":
            self._apply_eftp()
            return
        elif which == "point" and self._curve:
            cur = self.point if self.point is not None else -1
            self.point = (cur + step) % len(self._curve)
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        which = item.data if item is not None else None
        if symbol in (key.LEFT, key.RIGHT) and which:
            self._cycle(str(which), 1 if symbol == key.RIGHT else -1)
            return True
        if symbol in (key.ENTER, key.RETURN) and which:
            self._cycle(str(which), 1)
            return True
        return super().on_key(symbol, modifiers)

    def _apply_eftp(self) -> None:
        est = self._eftp or stats.estimated_ftp(self.app.db)
        if not est:
            return
        db = self.app.db
        athlete = db.athlete()
        athlete.ftp_w = int(est["ftp"])
        db.save_athlete(athlete)
        db.save_ftp_test("estimate", float(est["ftp"]), int(est["ftp"]), None, accepted=True)
        self.app.message(t("stats.eftp.applied", ftp=est["ftp"]))
        self.enter()

    def on_mouse(self, x: int, y: int) -> bool:
        if self.VIEWS[self.view] in ("power_curve", "evolution", "load", "balance",
                                     "zones_period", "eftp"):
            idx = self.chart.hit(x, y)
            if idx is not None:
                if self.VIEWS[self.view] == "power_curve":
                    self.point = idx
                    self.enter()
                else:
                    self.chart.select(idx, self._bar_tip(idx))
                return True
        return super().on_mouse(x, y)

    # ------------------------------------------------------------------ gráfico

    def _point_text(self) -> str:
        if self.point is None or not self._curve:
            return ""
        p = self._curve[min(self.point, len(self._curve) - 1)]
        weight = self.app.db.athlete().weight_kg
        return (f"{hms(p['duration_s'])} · {p['watts']:.0f} W · "
                f"{p['watts'] / weight:.2f} W/kg · {p['date']}")

    def _bar_tip(self, idx: int) -> str:
        data = getattr(self, "_series", [])
        if not data or idx >= len(data):
            return ""
        label, value = data[idx]
        view = self.VIEWS[self.view]
        if view == "zones_period":
            total = sum(value) or 1.0
            top = max(range(len(value)), key=lambda i: value[i])
            return (f"{label}: {sum(value) / 3600.0:.1f} h · "
                    f"Z{top + 1} {value[top] / total * 100:.0f}%")
        if view == "load":
            return (f"{label}: {t('form.short', ctl=f'{value[0]:.0f}', atl=f'{value[1]:.0f}', tsb=f'{value[2]:+.0f}')}")
        if view == "eftp":
            return f"{label}: {value:.0f} W" if value else f"{label}: —"
        return f"{label}: {self._fmt_metric(value)}"

    def _fmt_metric(self, v: float, metric: str | None = None) -> str:
        m = metric or self.metric
        if m == "distance":
            dv, du = km(v * 1000.0, self.app.units)
            return f"{dv:.0f} {du}" if dv >= 100 else f"{dv:.1f} {du}"
        if m == "time":
            return f"{v:.1f} h"
        if m == "ascent":
            return f"{v:.0f} m"
        if m == "load":
            return f"{v:.0f} TSS"
        if m == "rides":
            return f"{v:.0f}"
        if m == "avg_power":
            return f"{v:.0f} W"
        if m == "avg_hr":
            return f"{v:.0f} bpm"
        if m == "work":
            return f"{v:.0f} kJ"
        return f"{v:.0f}"

    def _refresh_chart(self) -> None:
        a = self.app
        view = self.VIEWS[self.view]
        empty = t("stats.no_data")
        self.bars.set_rows([])
        self.summary[0].text = self.summary[1].text = ""
        self._series = []
        if view == "power_curve":
            self._curve = stats.power_curve_detail(a.db)
            self.chart.show_line(t("stats.power_curve"), [p["watts"] for p in self._curve],
                                 [hms(p["duration_s"]) for p in self._curve], empty,
                                 log_x=True, xs=[p["duration_s"] for p in self._curve],
                                 fmt=lambda v: f"{v:.0f} W")
            if self._curve:
                if self.point is None:
                    self.point = min(range(len(self._curve)),
                                     key=lambda i: abs(self._curve[i]["duration_s"] - 1200))
                self.chart.select(self.point, self._point_text())
                p = self._curve[self.point]
                self.summary[0].text = t("stats.curve_hint")
                self.summary[1].text = (f"{hms(p['duration_s'])}: {p['watts']:.0f} W "
                                        f"— {p['name'] or p['date']}")
        elif view == "evolution":
            self._series = stats.series(a.db, self.metric, self.grouping, self.count)
            self.chart.show_bars(
                f"{t(f'stats.metric.{self.metric}')} · {t(f'stats.group.{self.grouping}')}",
                [v for _, v in self._series], [lab for lab, _ in self._series], empty,
                fmt=lambda v: self._fmt_metric(v))
            if self.chart.points:
                self.chart.select(len(self._series) - 1, self._bar_tip(len(self._series) - 1))
            self._summary_period()
        elif view == "zones":
            days = stats.GROUPING_DAYS[self.grouping] * self.count
            tiz = stats.time_in_zones(a.db, days)
            self.chart.show_bars(t("stats.view.zones"), [], [], "")
            self.chart.empty.text = "" if sum(tiz["power"]) or sum(tiz["hr"]) else empty
            self.bars.set_rows(self._zone_rows(tiz))
            self._summary_period()
        elif view == "load":
            days = min(730, stats.GROUPING_DAYS[self.grouping] * self.count)
            fit_ = stats.fitness(a.db, days, self.SPORTS)
            self._series = [(f"{d['date'].day:02d}/{d['date'].month:02d}",
                             (d["ctl"], d["atl"], d["tsb"])) for d in fit_]
            labels = [lab for lab, _ in self._series]
            self.chart.show_lines(
                t("stats.view.load"),
                [(t("form.ctl"), [d["ctl"] for d in fit_], (28, 132, 214)),
                 (t("form.atl"), [d["atl"] for d in fit_], (214, 54, 128)),
                 (t("form.tsb"), [d["tsb"] for d in fit_], (206, 146, 20))],
                labels, empty, fmt=lambda v: f"{v:.0f}")
            if fit_:
                cur = fit_[-1]
                self.summary[0].text = t("stats.load_now", ctl=f"{cur['ctl']:.0f}",
                                         atl=f"{cur['atl']:.0f}", tsb=f"{cur['tsb']:+.0f}")
                self.summary[1].text = (t(f"form.{stats.form_state(cur['tsb'])}") + " · "
                                        + t("stats.load_hint"))
                self.chart.select(len(fit_) - 1, self._bar_tip(len(fit_) - 1))
        elif view == "zones_period":
            from velo.gfx.hud import zone_color
            self._series = stats.zones_series(a.db, self.zkind, self.grouping, self.count,
                                              self.SPORTS)
            n = len(self._series[0][1]) if self._series else 0
            self.chart.show_stacked(
                f"{t(f'tiz.{self.zkind}')} · {t(f'stats.group.{self.grouping}')}",
                [[v / 3600.0 for v in z] for _, z in self._series],
                [zone_color(i + 1, self.zkind) for i in range(n)],
                [lab for lab, _ in self._series], empty, fmt=lambda v: f"{v:.1f} h")
            if self.chart.points:
                self.chart.select(len(self._series) - 1, self._bar_tip(len(self._series) - 1))
            self._summary_period()
        elif view == "eftp":
            self._series = stats.eftp_series(a.db, self.grouping, self.count)
            self.chart.show_bars(
                f"{t('stats.view.eftp')} · {t(f'stats.group.{self.grouping}')}",
                [v for _, v in self._series], [lab for lab, _ in self._series], empty,
                fmt=lambda v: f"{v:.0f} W")
            if self.chart.points:
                self.chart.select(len(self._series) - 1, self._bar_tip(len(self._series) - 1))
            est = self._eftp
            ftp_now = a.db.athlete().ftp_w
            if est:
                self.summary[0].text = t(
                    "stats.eftp.now", ftp=est["ftp"], method=t(f"stats.eftp.{est['method']}"),
                    current=ftp_now)
                extra = []
                if est.get("cp"):
                    extra.append(f"CP {est['cp']} W · W′ {est['w_prime_kj']} kJ")
                extra.append(t("stats.eftp.hint"))
                self.summary[1].text = " · ".join(extra)
            else:
                self.summary[0].text = t("stats.eftp.none")
        elif view == "profile":
            prof = stats.power_profile(a.db, self.sex)
            self.chart.show_bars(t("stats.view.profile"), [], [], "")
            has = any(p["wkg"] is not None for p in prof)
            self.chart.empty.text = "" if has else empty
            self.bars.set_rows(self._profile_rows(prof) if has else [])
            self.summary[0].text = t("stats.profile_hint")
        elif view == "cadence":
            hist = stats.cadence_histogram(a.db)
            self.chart.show_bars(t("stats.avg_cadence"), [n / 60.0 for _, n in hist],
                                 [str(c) for c, _ in hist], empty,
                                 fmt=lambda v: f"{v:.0f} min")
        else:
            hist = stats.balance_history(a.db, limit=self.count)
            self._series = [(d[5:], b) for d, b in hist]
            self.chart.show_line(t("stats.balance"), [b for _, b in hist],
                                 [d[5:] for d, _ in hist], empty,
                                 fmt=lambda v: f"{v:.1f} %")
            bal = stats.avg_balance(a.db)
            if bal is not None:
                self.summary[0].text = f"{t('stats.avg_balance')}: {balance_text(bal)}"

    def _summary_period(self) -> None:
        a = self.app
        tot = stats.period_totals(a.db, self.grouping, self.count)
        dv, du = km(tot["distance"] * 1000.0, a.units)
        self.summary[0].text = t(
            "stats.period_totals", n=self.count, unit=t(f"stats.unit.{self.grouping}"),
            km=f"{dv:.0f} {du}", h=f"{tot['time']:.1f}", up=f"{tot['ascent']:.0f}",
            rides=f"{tot['rides']}", load=f"{tot['load']:.0f}")
        metric = self.metric if self.VIEWS[self.view] == "evolution" else "distance"
        pct = stats.percentile_now(a.db, metric, self.grouping)
        if pct is not None:
            self.summary[1].text = t(
                f"stats.now.{self.grouping}", value=self._fmt_metric(pct["value"], metric),
                pct=f"{pct['percentile']:.0f}", best=self._fmt_metric(pct["best"], metric))

    def _zone_rows(self, tiz: dict) -> list[dict]:
        from velo.gfx.hud import zone_color
        rows = []
        for kind in ("power", "hr"):
            secs = tiz[kind]
            total = sum(secs)
            if not total:
                continue
            parts = [(v / total, zone_color(i + 1, kind),
                      f"Z{i + 1} {v / total * 100:.0f}%") for i, v in enumerate(secs)]
            rows.append({"title": t(f"tiz.{kind}"), "note": f"{total / 3600.0:.1f} h",
                         "parts": parts})
        return rows

    def _profile_rows(self, prof: list[dict]) -> list[dict]:
        from velo.gfx.hud import zone_color
        names = {5: "5 s", 60: "1 min", 300: "5 min", 3600: t("stats.profile_ft")}
        rows = []
        for p in prof:
            if p["wkg"] is None:
                rows.append({"title": names[p["duration_s"]], "note": "—", "parts": []})
                continue
            level_idx = stats.COGGAN_LEVELS.index(p["level"])
            color = zone_color(min(7, level_idx), "power")
            rows.append({
                "title": f"{names[p['duration_s']]} · {p['wkg']:.2f} W/kg",
                "note": f"{t('stats.level.' + p['level'])} · {p['position']:.0f}/100"
                        + (f" · {p['date']}" if p.get("date") else ""),
                "parts": [(p["position"] / 100.0, color, f"{p['position']:.0f}")],
            })
        return rows

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.chart = Chart(*self.chart_box(w, h))
        self.bars.layout(*self._bars_box(w, h))
        self.enter()

    def draw(self) -> None:
        super().draw()
        x, y, cw, ch = self.chart.x, self.chart.y, self.chart.width, self.chart.height
        top = y + ch + 40 + 40
        for i, lab in enumerate(self.summary):
            lab.x, lab.y = x, top - i * 20
            lab.draw()
        self.chart.draw()
        self.bars.draw()


# ------------------------------------------------------------------- app


class App:
    def __init__(self, data_dir: Path | None = None, width: int | None = None,
                 height: int | None = None, fullscreen: bool | None = None):
        self.data_dir = Path(data_dir or _default_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.rides_dir = self.data_dir / "rides"
        self.rides_dir.mkdir(exist_ok=True)

        self.db = Database(_database_path(self.data_dir))
        aborted = self.db.purge_incomplete()
        try:
            from velo.core import workout_library
            workout_library.seed(self.db)          # os treinos que vêm com a aplicação
        except Exception:
            pass
        set_language(self.db.get("language", PT))
        self.units = self.db.get("units", "metric")
        from velo.gfx import theme as _theme_mod
        _theme_mod.apply(str(self.db.get("theme", _theme_mod.DEFAULT)))

        # O que vier da linha de comandos manda; senão, a última escolha.
        saved = self.db.get("display", {}) or {}
        if fullscreen is None:
            fullscreen = bool(saved.get("fullscreen", False))
        width = width or int(saved.get("w", DEFAULT_SIZE[0]))
        height = height or int(saved.get("h", DEFAULT_SIZE[1]))
        width, height = max(width, MIN_SIZE[0]), max(height, MIN_SIZE[1])
        self.window, self.msaa_samples = _make_window(
            width=width, height=height, caption=f"Perennia {__version__}",
            resizable=True, fullscreen=fullscreen,
            samples=int(self.db.get("msaa_samples", 4)))
        self._windowed_size = (width, height)
        try:
            self.window.set_minimum_size(*MIN_SIZE)
        except Exception:
            pass
        pyglet.gl.glClearColor(BG[0] / 255, BG[1] / 255, BG[2] / 255, 1.0)

        self.hub = SensorHub()
        self.rower = None                 # máquina de remo ligada (velo.io.rower)
        self.ant_stick = None
        self.ant_found: list = []
        self.auto_running = False
        self.auto_generation = 0           # muda quando a ligação automática acaba
        self._auto_result = None
        self.apply_connection_preference()
        self.stack: list[Screen] = []
        self._message = ""
        self._message_at = 0.0
        self._fps = pyglet.window.FPSDisplay(self.window) if os.environ.get(
            "VELO_FPS") else None

        self.topbar = TopBar(self.window)
        self._topbar_texts()
        self.window.push_handlers(
            on_draw=self._on_draw, on_key_press=self._on_key_press,
            on_text=self._on_text,
            on_mouse_press=self._on_mouse_press, on_mouse_drag=self._on_mouse_drag,
            on_mouse_release=self._on_mouse_release, on_mouse_scroll=self._on_mouse_scroll,
            on_resize=self._on_resize,
            on_close=self._on_close)
        pyglet.clock.schedule_interval(self._tick, 1 / 60.0)

        self.push(HomeScreen(self))
        try:
            from velo.core import fitness_tests, health
            from velo.core import strength as strength_mod
            strength_mod.seed(self.db)
            health.seed(self.db)
            fitness_tests.seed(self.db)
            from velo.core import endurance, gym
            gym.ensure(self.db)
            gym.purge_drafts(self.db)
            endurance.seed(self.db)
        except Exception:
            pass
        if aborted:
            self.message(f"{aborted} sessão(ões) incompleta(s) foram encerradas")
        if self.db.checkpoints():
            # a aplicação fechou a meio de uma sessão: perguntar o que fazer
            from velo.ui.sport_screens import RecoveryScreen
            self.push(RecoveryScreen(self))
        if self.db.get("auto_connect", True) and self.db.known_devices():
            self.start_auto_connect()

    # ------------------------------------------------- ligação automática

    def apply_connection_preference(self) -> None:
        pref = self.db.get("connection_preference", autoconnect.ANT_FIRST)
        self.hub.preferred_transport = "ble" if pref in (
            autoconnect.BLE_FIRST, autoconnect.BLE_ONLY) else "ant"

    def start_auto_connect(self) -> None:
        """Liga os aparelhos conhecidos pela ordem preferida, num fio."""
        if self.auto_running:
            return
        known = [{"id": r["id"], "transport": r["transport"], "name": r["name"],
                  "role": r["role"]} for r in self.db.known_devices()]
        if not known:
            self.message(t("dev.auto_none"))
            return
        pref = self.db.get("connection_preference", autoconnect.ANT_FIRST)
        # Uma procura nova recomeça a antena e larga as ligações anteriores.
        for src in list(self.hub.sources):
            if getattr(src, "transport", None) in ("ant", "ble"):
                try:
                    src.disconnect()
                except Exception:
                    pass
                self.hub.remove_source(getattr(src, "device_id", ""))
        if self.ant_stick is not None:
            try:
                self.ant_stick.close()
            except Exception:
                pass
            self.ant_stick = None
        self.auto_running = True
        self.message(t("dev.auto_running"))
        hub, on_event = self.hub, self.on_device_event

        def worker() -> None:
            try:
                self._auto_result = autoconnect.connect_known(
                    known, pref,
                    ant_scan=lambda: ant.scan(timeout=12.0, on_event=on_event),
                    make_ant=lambda stick, ch, info: ant.AntSensor(
                        stick, ch, info, hub, on_event=on_event),
                    ble_scan=(lambda: ble.scan(timeout=8.0))
                    if ble.bleak_available() else None,
                    make_ble=lambda d: ble.BleSensor(d, hub, on_event=on_event))
            except Exception as e:
                self._auto_result = autoconnect.Result(lines=[f"{t('common.error')}: {e}"])

        threading.Thread(target=worker, name="auto-connect", daemon=True).start()

    def _collect_auto_connect(self) -> None:
        res, self._auto_result = self._auto_result, None
        self.auto_running = False
        if res.ant_stick is not None:
            self.ant_stick = res.ant_stick
            self.ant_found = res.ant_found
        for source, role, is_trainer in res.sources:
            self.hub.add_source(source, role=role, is_trainer=is_trainer)
        self.message(t("dev.auto_done", what=" · ".join(res.lines) or "—"))
        self.auto_generation += 1
        if isinstance(self.current, MainMenu):
            self.current.enter()

    # ------------------------------------------------------------ navegação

    def push(self, screen: Screen) -> None:
        # uma janela por cima não fecha o ecrã de baixo (a sessão continua)
        if self.stack and not screen.MODAL:
            self.stack[-1].leave()
        self.stack.append(screen)
        screen.enter()

    def pop(self) -> None:
        if len(self.stack) <= 1:
            return
        top = self.stack.pop()
        top.leave()
        if top.MODAL and self.stack[-1].IN_SESSION:
            return                 # a sessão de baixo nunca deixou de correr
        self.stack[-1].enter()

    def replace(self, screen: Screen) -> None:
        if self.stack:
            self.stack.pop().leave()
        self.stack.append(screen)
        screen.enter()

    def reset_to_menu(self, menu: type | None = None) -> None:
        """Volta ao menu do desporto (o do ciclismo por omissão), ou ao ecrã
        inicial se esse menu não estiver na pilha."""
        menu = menu or MainMenu
        while len(self.stack) > 1 and not isinstance(self.stack[-1], menu):
            self.stack.pop().leave()
        if self.stack:
            self.stack[-1].enter()
        else:
            self.push(HomeScreen(self))

    @property
    def current(self) -> Screen | None:
        return self.stack[-1] if self.stack else None

    # -------------------------------------------------------------- avisos

    def set_rower(self, rower) -> None:
        """Liga (ou desliga, com None) a máquina de remo."""
        old = self.rower
        if old is not None and old is not rower:
            try:
                old.disconnect()
            except Exception:
                pass
        self.rower = rower

    def message(self, text: str) -> None:
        self._message = text
        self._message_at = time.monotonic()

    # --------------------------------------------------------- faixa do topo

    def set_theme(self, key: str) -> None:
        """Muda de tema e volta a construir o que está à vista com as cores
        novas (só fora das sessões: as Definições estão fechadas durante)."""
        from velo.gfx import theme as theme_mod
        self.db.set("theme", key)
        theme_mod.apply(key)
        bg = theme_mod.P.bg
        pyglet.gl.glClearColor(bg[0] / 255, bg[1] / 255, bg[2] / 255, 1.0)
        self.topbar = TopBar(self.window)
        self._topbar_texts()
        # Os ecrãs abertos foram desenhados com a paleta antiga: volta-se a
        # construir o ecrã inicial e as Definições, no mesmo separador.
        top = self.stack[-1] if self.stack else None
        tab = getattr(top, "tab", 0)
        for scr in reversed(self.stack):
            try:
                scr.leave()
            except Exception:
                pass
        self.stack = [HomeScreen(self)]
        settings = SettingsScreen(self)
        self.stack.append(settings)
        settings.set_tab(tab if isinstance(top, SettingsScreen) else 0)
        settings.enter()

    def _topbar_texts(self) -> None:
        self.topbar.set_texts(tr("Dispositivos", "Devices"), tr("Definições", "Settings"),
                              tr("Desligar", "Power off"))

    @property
    def in_session(self) -> bool:
        """Há uma sessão de treino aberta (em qualquer ponto da pilha)?"""
        for scr in self.stack:
            if scr.IN_SESSION:
                eng = getattr(scr, "engine", None) or getattr(scr, "session", None)
                if eng is None or not getattr(eng, "finished", False):
                    return True
        return False

    def device_states(self) -> list[tuple[str, str]]:
        """[(nome, ok|lost|off)] de todos os aparelhos ligados, para a faixa do topo."""
        out = []
        for src in self.hub.sources:
            dev = getattr(src, "device_id", "")
            name = getattr(src, "name", "?")
            if getattr(src, "connected", True) is False:
                out.append((name, "lost"))
            elif self.hub.is_lost(dev):
                out.append((name, "lost"))
            else:
                out.append((name, "ok"))
        if self.rower is not None:
            out.append((self.rower.name, "ok" if getattr(self.rower, "connected", True)
                        else "lost"))
        return out

    def open_devices(self) -> None:
        if isinstance(self.current, DeviceScreen):
            return
        self.push(DeviceScreen(self))

    def open_settings(self) -> None:
        if self.in_session:
            self.message(tr("As definições não estão disponíveis durante uma sessão de treino.",
                            "Settings are not available during a workout."))
            return
        if isinstance(self.current, SettingsScreen):
            return
        while self.current is not None and self.current.MODAL:
            self.pop()
        self.push(SettingsScreen(self))

    def ask_quit(self) -> None:
        if self.in_session:
            self.message(tr("Termina a sessão de treino antes de sair.",
                            "Finish the workout before quitting."))
            return
        if isinstance(self.current, ConfirmScreen):
            return
        self.push(ConfirmScreen(self, tr("Sair da Perennia?", "Quit Perennia?"),
                                tr("Os aparelhos são desligados.",
                                   "Devices will be disconnected."),
                                [(tr("Sim, sair", "Yes, quit"), self.quit),
                                 (tr("Não", "No"), self.pop)], default=1))

    def _check_devices(self) -> None:
        """Avisa sempre que um aparelho se desliga (em qualquer ecrã)."""
        self.hub.check_lost()
        for name in self.hub.drain_lost():
            self.message(tr("⚠ {n} desligou-se", "⚠ {n} disconnected", n=name))
            for scr in self.stack:
                scr.on_device_lost(name)
        for name in self.hub.drain_back():
            self.message(tr("{n} voltou", "{n} is back", n=name))
        r = self.rower
        was = getattr(self, "_rower_ok", None)
        now = None if r is None else bool(getattr(r, "connected", True))
        if was and now is False:
            self.message(tr("⚠ {n} desligou-se", "⚠ {n} disconnected", n=r.name))
            for scr in self.stack:
                scr.on_device_lost(r.name)
        self._rower_ok = now
        self.topbar.set_devices(self.device_states())
        busy = self.in_session
        self.topbar.set_enabled("settings", not busy)
        self.topbar.set_enabled("quit", not busy)

    def on_device_event(self, kind: str, data: dict) -> None:
        if kind == "disconnected":
            self.message(tr("⚠ {n} desligou-se", "⚠ {n} disconnected",
                            n=data.get("device", "")))
            for scr in self.stack:
                scr.on_device_lost(data.get("device", ""))
        elif kind == "connected":
            self.message(f"{data.get('device', '')}: {t('dev.connected')}")
        elif kind == "control_response" and not data.get("ok", True):
            self.message(f"{data.get('device', '')}: {data.get('text', '')}")

    def device_summary(self) -> str:
        names = [getattr(s, "name", "?") for s in self.hub.sources]
        return " · ".join(names) if names else t("dev.none")

    # --------------------------------------------------------------- ciclo

    def _tick(self, dt: float) -> None:
        if self.auto_running and self._auto_result is not None:
            self._collect_auto_connect()
        screen = self.current
        if screen is not None:
            # com uma janela por cima, a sessão de baixo continua a correr
            if screen.MODAL and len(self.stack) > 1:
                below = self._below_modal()
                if below is not None:
                    below.update(dt)
            screen.update(dt)
        self._check_devices()

    def _below_modal(self):
        for scr in reversed(self.stack):
            if not scr.MODAL:
                return scr
        return None

    def _on_draw(self) -> None:
        screen = self.current
        # O mundo 3D põe o fundo cor de céu e liga o teste de profundidade.
        # Fora da sessão repõe-se tudo em cada desenho: sem isto, os menus
        # ficavam com o fundo cinzento-azulado da estrada depois de sair.
        riding = isinstance(screen, RideScreen) and screen.world is not None \
            and not screen.preparing
        if riding:
            screen.world.setup_gl()
        else:
            pyglet.gl.glClearColor(BG[0] / 255, BG[1] / 255, BG[2] / 255, 1.0)
            pyglet.gl.glDisable(pyglet.gl.GL_DEPTH_TEST)
        self.window.clear()
        if screen is None:
            return
        if screen.MODAL:
            below = self._below_modal()
            if below is not None and below is not screen:
                if isinstance(below, RideScreen) and below.world is not None \
                        and not below.preparing:
                    below.world.setup_gl()
                below.draw()
                pyglet.gl.glDisable(pyglet.gl.GL_DEPTH_TEST)
            self.window.projection = pyglet.math.Mat4.orthogonal_projection(
                0, self.window.width, 0, self.window.height, -255, 255)
            self.window.view = pyglet.math.Mat4()
            screen.draw()
            if self._message and time.monotonic() - self._message_at < 6.0:
                screen.chrome.message.text = self._message
            else:
                screen.chrome.message.text = ""
            self.topbar.draw()
            return
        if not isinstance(screen, RideScreen):
            self.window.projection = pyglet.math.Mat4.orthogonal_projection(
                0, self.window.width, 0, self.window.height, -255, 255)
            self.window.view = pyglet.math.Mat4()
        screen.draw()
        if self._message and time.monotonic() - self._message_at < 6.0:
            if not isinstance(screen, RideScreen):
                screen.chrome.message.text = self._message
        elif not isinstance(screen, RideScreen):
            screen.chrome.message.text = ""
        if isinstance(screen, RideScreen):
            self.window.projection = pyglet.math.Mat4.orthogonal_projection(
                0, self.window.width, 0, self.window.height, -255, 255)
            self.window.view = pyglet.math.Mat4()
            pyglet.gl.glDisable(pyglet.gl.GL_DEPTH_TEST)
        self.topbar.draw()
        if self._fps is not None:
            self._fps.draw()

    def _on_key_press(self, symbol: int, modifiers: int) -> bool:
        if symbol == key.F11:
            self.set_display(fullscreen=not self.window.fullscreen)
            return True
        if symbol == key.F4:
            if isinstance(self.current, DeviceScreen):
                self.pop()
            else:
                self.open_devices()
            return True
        if symbol == key.F8:
            self.open_settings()
            return True
        if symbol == key.Q and modifiers & key.MOD_CTRL:
            self.ask_quit()
            return True
        screen = self.current
        if screen is not None:
            return bool(screen.on_key(symbol, modifiers))
        return False

    def _on_text(self, text: str) -> bool:
        screen = self.current
        if screen is not None:
            return bool(screen.on_text(text))
        return False

    def _on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        which = self.topbar.hit(x, y)
        if which == "devices":
            self.open_devices()
            return
        if which == "settings":
            self.open_settings()
            return
        if which == "quit":
            self.ask_quit()
            return
        if which == "bar":
            return
        screen = self.current
        if screen is not None:
            screen.on_mouse(x, y)

    def _on_mouse_drag(self, x: int, y: int, dx: int, dy: int, buttons: int = 1,
                       modifiers: int = 0) -> None:
        screen = self.current
        if screen is not None:
            screen.on_drag(x, y, dx, dy)

    def _on_mouse_scroll(self, x: int, y: int, scroll_x: float = 0, scroll_y: float = 0) -> None:
        screen = self.current
        if screen is not None and hasattr(screen, "on_scroll"):
            screen.on_scroll(x, y, scroll_x, scroll_y)

    def _on_mouse_release(self, x: int, y: int, button: int = 1, modifiers: int = 0) -> None:
        screen = self.current
        if screen is not None:
            screen.on_release(x, y)

    def _on_resize(self, w: int, h: int) -> None:
        if not self.window.fullscreen:
            self._windowed_size = (w, h)
        self.topbar.layout()
        for screen in self.stack:
            screen.on_resize(w, h)

    # ------------------------------------------------------------ resolução

    def screen_size(self) -> tuple[int, int] | None:
        """Resolução do monitor onde está a janela, se a pyglet a souber."""
        scr = getattr(self.window, "screen", None)
        if scr is None:
            return None
        try:
            return int(scr.width), int(scr.height)
        except Exception:
            return None

    def display_options(self) -> list[tuple[bool, int, int]]:
        """(ecrã inteiro?, largura, altura): janelas que cabem e o ecrã inteiro."""
        limit = self.screen_size()
        sizes = [s for s in WINDOW_SIZES
                 if limit is None or (s[0] <= limit[0] and s[1] <= limit[1])]
        return [(False, w, h) for w, h in sizes] + [(True, 0, 0)]

    def set_display(self, fullscreen: bool, width: int | None = None,
                    height: int | None = None) -> None:
        """Muda já, e fica lembrado para a próxima vez."""
        if fullscreen:
            self.window.set_fullscreen(True)
        else:
            w, h = width or self._windowed_size[0], height or self._windowed_size[1]
            w, h = max(w, MIN_SIZE[0]), max(h, MIN_SIZE[1])
            if self.window.fullscreen:
                self.window.set_fullscreen(False)
            self.window.set_size(w, h)
            self._windowed_size = (w, h)
        self._on_resize(self.window.width, self.window.height)
        self.save_display()

    def save_display(self) -> None:
        w, h = self._windowed_size
        try:
            self.db.set("display", {"fullscreen": bool(self.window.fullscreen),
                                    "w": int(w), "h": int(h)})
        except Exception:
            pass

    def display_label(self) -> str:
        if self.window.fullscreen:
            size = self.screen_size() or (self.window.width, self.window.height)
            return t("set.display.full", w=size[0], h=size[1])
        return t("set.display.window", w=self.window.width, h=self.window.height)

    def _on_close(self) -> None:
        self.shutdown()

    def quit(self) -> None:
        self.shutdown()
        pyglet.app.exit()

    def shutdown(self, crashed: bool = False) -> None:
        """Fecha tudo. Corre ao fechar a janela e outra vez à saída do
        main.py; só a primeira vez faz alguma coisa.

        `crashed`: a aplicação vai abaixo por um erro. A sessão em curso não
        se termina: grava-se o que houver e fica pronta para retomar."""
        if getattr(self, "_shut_down", False):
            return
        self._shut_down = True
        try:
            self.save_display()      # o tamanho com que fechaste é o da próxima vez
        except Exception:
            pass
        screen = self.current
        session = getattr(screen, "session", None)
        if self.rower is not None:
            try:
                self.rower.disconnect()
            except Exception:
                pass
        if crashed:
            for obj in (getattr(screen, "engine", None), session):
                if obj is not None and hasattr(obj, "suspend"):
                    try:
                        obj.suspend()
                    except Exception:
                        pass
        elif session is not None and not session.finished:
            # fechar a janela a meio da força: guarda se já houver séries
            try:
                if session.sets:
                    session.finish()
                else:
                    session.abort()
            except Exception:
                pass
        elif isinstance(screen, RideScreen):
            # Fechar a janela a meio de uma sessão termina-a e grava o .fit,
            # como o botão de parar. Só se aborta se nem chegou a arrancar.
            engine = screen.engine
            if engine is not None and not engine.finished and engine.started:
                try:
                    engine.finish()
                except Exception:
                    pass
            screen.leave()
        try:
            self.hub.release_control()
        except Exception:
            pass
        for source in list(self.hub.sources):
            if hasattr(source, "disconnect"):
                try:
                    source.disconnect()
                except Exception:
                    pass
        try:
            ble.shutdown()
        except Exception:
            pass
        if self.ant_stick is not None:
            try:
                self.ant_stick.close()
            except Exception:
                pass
        self.db.close()

    def run(self) -> None:
        pyglet.app.run()


def _make_window(samples: int = 4, **kw):
    """Janela com antialiasing (MSAA): suaviza as arestas da estrada, as linhas
    dos gráficos e o contorno do perfil. Se a placa gráfica não aceitar 4×,
    tenta 2× e depois sem; devolve também o que conseguiu."""
    attempts = [s for s in (samples, 2) if s and s > 1] + [0]
    last_error: Exception | None = None
    for s in dict.fromkeys(attempts):
        try:
            if s:
                config = pyglet.gl.Config(sample_buffers=1, samples=s, depth_size=24,
                                          double_buffer=True)
                return pyglet.window.Window(config=config, **kw), s
            return pyglet.window.Window(**kw), 0
        except Exception as e:          # NoSuchConfigException e afins
            last_error = e
    raise RuntimeError(f"não foi possível abrir a janela: {last_error}")


def _theme_name(db) -> str:
    from velo.gfx import theme as theme_mod
    return theme_mod.name(str(db.get("theme", theme_mod.DEFAULT)))


def _calendar():
    from velo.ui import calendar_screens
    return calendar_screens


def _brief():
    from velo.ui import brief
    return brief


def _layouts():
    from velo.ui import layout_screens
    return layout_screens


def _default_data_dir() -> Path:
    """Pasta de dados por omissão, respeitando as convenções do sistema."""
    env = os.environ.get("PERENNIA_DATA_DIR") or os.environ.get("VELO_DATA_DIR")
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or str(Path.home()))
        new, old = base / "Perennia", base / "VeloLocal"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        new, old = base / "Perennia", base / "VeloLocal"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share"))
        new, old = base / "perennia", base / "velolocal"
    # A aplicação chamava-se VeloLocal: se os teus dados ainda estão na pasta
    # antiga, continua a usá-la (os caminhos dos .fit gravados apontam para lá).
    if not new.exists() and old.exists():
        return old
    return new


def _database_path(data_dir: Path) -> Path:
    """perennia.db; uma base antiga (velolocal.db) é renomeada uma vez."""
    new, old = data_dir / "perennia.db", data_dir / "velolocal.db"
    if not new.exists() and old.exists():
        try:
            old.rename(new)
        except OSError:
            return old
    return new


def _extra():
    """Ecrãs da força, dos construtores e da recuperação (módulo à parte, que
    importa este: carrega-se só quando é preciso)."""
    from velo.ui import sport_screens
    return sport_screens


def _rowing():
    from velo.ui import rowing_screens
    return rowing_screens


def _hubs():
    from velo.ui import hub_screens
    return hub_screens


def _builder():
    from velo.ui import builder_screens
    return builder_screens


def _connect():
    from velo.ui import connect_screens
    return connect_screens


def _segments_mod():
    from velo.core import segments
    return segments


def _extra_health():
    """Saúde, testes e agente (módulo à parte)."""
    from velo.ui import health_screens
    return health_screens


def _pretty(name) -> str:
    from velo.core.naming import pretty
    return pretty(name)


def _feedback():
    from velo.ui import feedback_screens
    return feedback_screens
