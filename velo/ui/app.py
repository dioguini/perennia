"""Aplicação: janela, ecrãs e ciclo principal.

Tudo o que é lógica vive em `velo.core`; aqui só se mostra e se recolhe
teclas. Os ecrãs formam uma pilha: Esc volta ao anterior.
"""
from __future__ import annotations

import os
import sys
from datetime import date
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
from velo.ui.session_radar import RadarSide
from velo.ui.widgets import (ACCENT, BAD, BG, BackButton, BoardPanel, Chart, Chrome, DIM,
                             GOOD, Item, ListView, PANEL, Popup, StackedBars,
                             StartCountdown, TabBar, TEXT, Tile, TopBar)

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
    _pending_hub = None   # ver `hub`: o menu do desporto por cima deste ecrã
    KEY_SCOPE: str | None = None   # o âmbito dos atalhos de teclado (ver keymap)

    def __init__(self, app: "App"):
        self.app = app
        # `hub`: este ecrã abriu num separador do menu de um desporto (as
        # Estatísticas): os separadores do desporto ficam por cima dos dele
        self.hub = Screen._pending_hub
        Screen._pending_hub = None
        w, h = app.window.width, app.window.height
        self.chrome = Chrome(app.window)
        self.back_button: BackButton | None = None
        if not self.ROOT:
            self.back_button = BackButton(app.window)
            self.chrome.footer_x = 190
            self.chrome.layout()
        self.tab = 0
        self.tabs: TabBar | None = None
        self.hub_tabs: TabBar | None = None
        if self.hub is not None:
            self.hub_tabs = TabBar(self.hub.tab_labels(), 48, h - 98, w - 96)
            self.hub_tabs.select(self.hub.TAB_KEYS.index("stats"))
        if self.TABBED:
            self.tabs = TabBar(self.tab_labels(), 48, h - 98 - self._hub_dy(),
                               self._tabs_width(w))
        top = self.content_top(h)
        self.list = ListView(48, top, self._list_width(w),
                             visible_rows=max(4, (top - 110) // 38))
        self.list.bar_right = w - 48          # botões de ação: em baixo, à direita
        self.list.top_y = h - 74              # Adicionar / filtros: em cima, à direita
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

    def _hub_dy(self) -> int:
        return 44 if getattr(self, "hub", None) is not None else 0

    def content_top(self, h: int) -> int:
        """Onde começa a lista: mais abaixo se houver separadores."""
        return h - 130 - (44 if self.TABBED else 0) - self._hub_dy()

    def titles(self, title: str, subtitle: str) -> tuple[str, str]:
        """Dentro do menu de um desporto, o título é o do desporto."""
        if self.hub is not None:
            return self.hub.title(), self.hub.subtitle()
        return title, subtitle

    def set_tab(self, i: int) -> None:
        if self.tabs is None:
            return
        if self.search_box is not None and self.search_box.text:
            self.search_box.text = ""             # a pesquisa é da tab
            self.list.query = ""
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

    # ------------------------------------------------------------ pesquisa
    #
    # Todas as tabs (e listas) têm uma pesquisa no canto superior direito:
    # filtra o que está na tab enquanto se escreve. Os ecrãs que não são
    # listas (o inicial, as sessões, o construtor) põem SEARCH = False.

    SEARCH = True
    search_box = None

    @property
    def has_search(self) -> bool:
        return bool(self.SEARCH) and not self.ROOT and not self.MODAL and \
            not self.IN_SESSION and self.list.y > 0

    @property
    def search_active(self) -> bool:
        return self.search_box is not None and self.search_box.focused

    def search_focus(self, on: bool = True) -> None:
        if self.search_box is None:
            from velo.ui.widgets import SearchBox
            self.search_box = SearchBox()
        self.search_box.focused = on
        self._place_search()

    def search_set(self, text: str) -> None:
        if self.search_box is None:
            self.search_focus(False)
        self.search_box.text = text
        self.list.set_query(text)
        self._place_search()

    def search_key(self, symbol: int, modifiers: int) -> bool:
        """As teclas enquanto se escreve na pesquisa (as letras chegam por texto)."""
        box = self.search_box
        if symbol == key.ESCAPE:
            if box.text:
                self.search_set("")
            else:
                self.search_focus(False)
        elif symbol == key.BACKSPACE:
            self.search_set(box.text[:-1])
        elif symbol in (key.ENTER, key.RETURN):
            self.search_focus(False)
            if getattr(self, "SEARCH_ENTER_PICKS", False):
                self.list.activate()
        elif symbol in (key.DOWN, key.UP):
            self.list.move(1 if symbol == key.DOWN else -1)
        elif symbol == key.TAB:
            self.search_focus(False)
            return self.on_key(symbol, modifiers)
        return True

    def search_text(self, text: str) -> None:
        clean = "".join(c for c in text if c.isprintable() and c not in "\r\n\t")
        if clean:
            self.search_set(self.search_box.text + clean)

    def _place_search(self) -> None:
        if self.search_box is None:
            return
        if self.MODAL and getattr(self, "popup", None) is not None:
            p = self.popup
            self.search_box.place(p.x + p.w - 24, p.y + p.h - 16, min(300, p.w * 0.4))
        else:
            # a pesquisa das tabs fica sempre na barra do topo, no mesmo sítio
            self.search_box.place(*self.app.topbar.search_slot())
        self.search_box.refresh(self.list.hidden_count)

    def _search_prepare(self) -> bool:
        """Cria e põe a pesquisa no sítio; True se este ecrã a mostra."""
        if not (self.has_search or getattr(self, "SEARCH_ENTER_PICKS", False)):
            return False
        if self.search_box is None:
            self.search_focus(False)
        sig = (self.search_box.text, self.search_box.focused, self.list.hidden_count,
               self.app.window.width, self.app.window.height)
        if sig != getattr(self, "_search_sig", None):
            self._search_sig = sig
            self._place_search()
        return True

    def draw_search_top(self) -> None:
        """A pesquisa das tabs, na barra do topo (o App chama-a depois de a
        desenhar, para ficar por cima dela)."""
        if not self.MODAL and self._search_prepare():
            self.search_box.draw()

    def draw(self) -> None:
        self.chrome.set_footer_limit(self.list.buttons_left)
        if self._search_prepare() and self.MODAL:
            self.search_box.draw()          # a janela tem a sua pesquisa; a das tabs vai no topo
        if self.AGENT and not self.MODAL:
            self.chrome.agent_hint.text = t("agent.hint")
        self.chrome.draw()
        if self.hub_tabs is not None:
            self.hub_tabs.draw()
        if self.tabs is not None:
            self.tabs.draw()
        self.list.draw()
        if self.back_button is not None:
            self.back_button.draw()
        if self.board_panel is not None:
            if self._board_key != (self.list.index, id(self.list.items)):
                self.refresh_board()
            self.board_panel.draw()

    # ------------------------------------------------------------ guardar

    def on_save(self) -> bool:
        """Ctrl+S: carrega no botão principal (Guardar) do ecrã, se houver."""
        return self.list.press_button("primary")

    def has_unsaved(self) -> bool:
        """Há alterações por guardar? (os construtores perguntam antes de sair)"""
        return False

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
            self.go_back()
            return True
        return False

    def go_back(self) -> None:
        """O «Voltar» em baixo (e o Esc). Os resumos levam ao menu do desporto."""
        self.app.pop()

    # ---- contagem decrescente antes de uma sessão (ver StartCountdown)
    start_cd: StartCountdown | None = None

    def start_countdown(self, resume=None) -> None:
        """As sessões chamam isto ao abrir: 15 s antes de começar (retomar
        uma sessão interrompida não conta outra vez)."""
        self.start_cd = None if resume is not None else StartCountdown.for_app(self.app)

    @property
    def counting(self) -> bool:
        return self.start_cd is not None and self.start_cd.active \
            and not getattr(self, "preparing", False)

    def countdown_done(self) -> None:
        """A contagem chegou ao fim: a sessão pode começar."""

    def cancel_countdown(self) -> None:
        """Esc durante a contagem: não começa (nada fica gravado)."""
        self.app.pop()

    def on_mouse(self, x: int, y: int) -> bool:
        if self.search_box is not None and self.search_box.hit(x, y) and \
                (self.has_search or getattr(self, "SEARCH_ENTER_PICKS", False)):
            self.search_focus(True)
            return True
        if self.search_active:
            self.search_focus(False)
        if self.back_button is not None and self.back_button.hit(x, y):
            self.go_back()
            return True
        if self.hub_tabs is not None:
            i = self.hub_tabs.hit(x, y)
            if i is not None:
                if i != self.hub.TAB_KEYS.index("stats"):
                    hub = self.hub
                    self.app.pop()
                    hub.set_tab(i)
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
        if self.hub_tabs is not None:
            self.hub_tabs.layout(48, h - 98, w - 96)
        if self.tabs is not None:
            self.tabs.layout(48, h - 98 - self._hub_dy(), self._tabs_width(w))
        top = self.content_top(h)
        self.list.y = top
        self.list.width = self._list_width(w)
        self.list.bar_right = w - 48
        self.list.top_y = h - 74
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
    # O construtor de treinos já não é um separador: abre-se com «+ Novo treino»
    # na Lista de treinos (e com «Editar» na ficha de cada treino).
    TAB_KEYS = ("train", "library", "history", "stats")

    def tab_labels(self) -> list[str]:
        return [tr("Treinar", "Train"), tr("Lista de treinos", "Workouts"),
                tr("Histórico", "History"), tr("Estatísticas", "Statistics")]

    def new_workout_item(self) -> Item:
        """«+ Novo treino»: abre o construtor (o do ginásio pergunta a modalidade)."""
        a = self.app
        if self.SPORT == "gym":
            from velo.ui.gym_screens import ModalityPicker
            action = lambda: a.push(ModalityPicker(a))
        else:
            action = lambda: _builder().new_workout(a, self.SPORT)
        return Item(tr("+ Novo treino", "+ New workout"), button=True, primary=True,
                    action=action, data="new_workout")

    def title(self) -> str:
        from velo.core import sports as sp
        return sp.name(self.SPORT)

    def subtitle(self) -> str:
        """Por baixo do nome do desporto, sempre o mesmo: o atleta, a FTP e o limiar de FC
        (o ginásio não leva nada)."""
        if self.SPORT == "gym":
            return ""
        ath = self.app.db.athlete()
        bits = [ath.name or "—"]
        if ath.ftp_w:
            bits.append(f"FTP {ath.ftp_w} W")
        lthr = getattr(ath, "lthr", None)
        if not lthr:
            try:
                from velo.core.ride import estimate_lthr
                lthr = estimate_lthr(ath)
            except Exception:
                lthr = None
        if lthr:
            bits.append(f"LTHR {int(lthr)} bpm")
        return " · ".join(bits)

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

    def tab_is_screen(self, i: int) -> bool:
        """O separador Estatísticas abre o ecrã das estatísticas do desporto."""
        return self.TAB_KEYS[i % len(self.TAB_KEYS)] == "stats"

    def set_tab(self, i: int) -> None:
        if self.tab_is_screen(i):
            self.open_stats()
            return
        super().set_tab(i)

    def open_stats(self) -> None:
        self.app.push(_hubs().stats_screen(self.app, self.SPORT, hub=self))

    def enter(self) -> None:
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "stats":
            self.tab = 0
            if self.tabs is not None:
                self.tabs.select(0)
        key_ = self.TAB_KEYS[self.tab % len(self.TAB_KEYS)]
        items = self.items_for(key_)
        if key_ == "library":
            items = items + [self.new_workout_item()]
        if not items:
            items = [Item(tr("Nada por aqui ainda", "Nothing here yet"), enabled=False)]
        self.chrome.set(self.title(), self.subtitle(), self.footer())
        self.list.set_items(items, keep_index=True)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if symbol == key.DELETE and self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "library" \
                and self.SPORT in ("cycling", "rowing", "running", "swimming") and \
                item is not None and isinstance(item.data, tuple):
            _builder().delete_workout(self.app, self.SPORT, item.data[1], item.label,
                                      then=self.enter)
            return True
        return super().on_key(symbol, modifiers)

    def footer(self) -> str:
        if self.TAB_KEYS[self.tab % len(self.TAB_KEYS)] == "library" and \
                self.SPORT in ("cycling", "rowing", "running", "swimming"):
            return tr("Tab separador · ↑↓ mover · Enter abre a ficha do treino · Del apagar · "
                      "Esc voltar", "Tab next tab · ↑↓ move · Enter opens the workout page · "
                      "Del delete · Esc back")
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

    def items_train(self) -> list[Item]:
        a = self.app
        from velo.ui.challenge_screens import train_items
        return train_items(a, "cycling", Item(
            tr("Sessão de treino", "Training session"),
            detail=tr("Livre (com uma rota .gpx) ou carregar um treino",
                      "Free (with a .gpx route) or load a workout"),
            action=lambda: _setup().ask_start(a, "cycling", self), data="ride"))

    def items_library(self) -> list[Item]:
        a = self.app
        from velo.ui.workout_import import import_item
        items = [import_item(a, "cycling", on_done=lambda _w: self.enter())]
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
        from velo.ui.sync_screens import history_items
        return out + history_items(a, "cycling")

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

def RideDetailScreen(app: "App", ride_id: str):            # noqa: N802 — compatibilidade
    """Uma sessão de ciclismo do histórico: a análise em separadores."""
    from velo.ui.session_analysis import SessionAnalysis
    return SessionAnalysis(app, "ride", ride_id)


def _has_table(db, name: str) -> bool:
    return db.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (name,)).fetchone() is not None


# ------------------------------------------------------------ ecrã inicial


class HomeScreen(Screen):
    """Ecrã inicial: os desportos e o resto em cartões todos do mesmo tamanho,
    e por baixo a sequência de treino e a forma (à esquerda) e o calendário
    do mês, grande, no resto da largura."""

    ROOT = True
    # Os desportos e a saúde na primeira fila; rotas, segmentos, estatísticas
    # e inventários na segunda (ao centro). O calendário está por baixo, no
    # próprio ecrã. Dispositivos, Backups, Definições e Sair estão na faixa do
    # topo (sempre à vista).
    TILES = (("home.cycling", "bike", ""), ("home.rowing", "rower", ""),
             ("home.running", "runner", ""), ("home.swimming", "swimmer", ""),
             ("home.gym", "kettlebell", ""), ("home.health", "heart", ""),
             ("home.routes", "road", ""), ("home.segments", "flag", ""),
             ("home.stats", "stats", ""),
             ("home.inventory", "box", ""), ("home.exercises", "checklist", ""),
             ("home.longevity", "recover", ""))
    BIG = 6               # cartões por fila
    UPCOMING_DAYS = 14
    UPCOMING_ROWS = 12

    def __init__(self, app: "App"):
        super().__init__(app)
        self.batch = pyglet.graphics.Batch()
        self.tiles = [Tile(t(key_), icon, t(note) if note else "", batch=self.batch)
                      for key_, icon, note in self.TILES]
        self.selected = 0
        self.streak_title = make_label("", font_size=15, bold=True, color=ACCENT,
                                       anchor_y="top", batch=self.batch)
        self.streak_lines = [make_label("", font_size=12, color=TEXT, anchor_y="top",
                                        batch=self.batch) for _ in range(3)]
        self.form_title = make_label("", font_size=15, bold=True, color=ACCENT,
                                     anchor_y="top", batch=self.batch)
        self.form_lines = [make_label("", font_size=12, color=TEXT, anchor_y="top",
                                      batch=self.batch) for _ in range(2)]
        # as próximas atividades planeadas (só para ter noção do que aí vem)
        self.up_title = make_label("", font_size=15, bold=True, color=ACCENT, anchor_y="top",
                                   batch=self.batch)
        self.up_lines = [make_label("", font_size=12, color=TEXT, anchor_y="top",
                                    batch=self.batch) for _ in range(self.UPCOMING_ROWS)]
        self._up_rects: list = []
        # o calendário do mês (antes era um menu à parte)
        self.cal = _calendar().MiniCalendar(self.batch)
        self.upcoming: list = []
        from velo.gfx import icons
        self.flame = icons.sprite("flame", 0, 0, 24, batch=self.batch, opacity=240)
        self.pulse = icons.sprite("pulse", 0, 0, 24, batch=self.batch, opacity=240)
        self._layout()

    def _actions(self):
        a = self.app
        hub = _hubs()
        return [lambda: a.push(hub.SportHub(a, "cycling")),
                lambda: a.push(hub.SportHub(a, "rowing")),
                lambda: a.push(hub.SportHub(a, "running")),
                lambda: a.push(hub.SportHub(a, "swimming")),
                lambda: a.push(hub.SportHub(a, "gym")),
                lambda: a.push(_extra_health().HealthMenu(a)),
                lambda: a.push(_routes().RoutesScreen(a)),
                lambda: a.push(_segments_ui().SegmentsScreen(a)),
                lambda: a.push(hub.stats_screen(a, None)),
                lambda: a.push(hub.InventoryScreen(a)),
                lambda: a.push(hub.ExerciseInventory(a)),
                lambda: a.push(_longevity_ui().LongevityMenu(a))]

    def tile_geometry(self, w: int, h: int) -> tuple[float, float, float]:
        """(largura, altura, topo) dos cartões — todos iguais."""
        top = h - 120
        gap = 14
        tw = (w - 96 - (self.BIG - 1) * gap) / self.BIG
        th = max(84.0, min(112.0, (top - 60 - 300 - gap) / 2))
        return tw, th, top

    def _layout(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        gap = 14
        tw, th, top = self.tile_geometry(w, h)
        n = len(self.tiles)
        for i, tile in enumerate(self.tiles):
            r, c = divmod(i, self.BIG)
            # uma fila com menos cartões fica ao centro
            in_row = min(self.BIG, n - r * self.BIG)
            shift = (self.BIG - in_row) * (tw + gap) / 2
            tile.layout(48 + shift + c * (tw + gap), top - (r + 1) * th - r * gap, tw, th)
        sy = top - 2 * th - gap - 30          # topo da faixa de baixo
        bottom = 56
        # esquerda: sequência e forma
        lx = 48
        if self.flame is not None:
            self.flame.x, self.flame.y = lx, sy - 24
        self.streak_title.x, self.streak_title.y = lx + 32, sy
        for i, lab in enumerate(self.streak_lines):
            lab.x, lab.y = lx + 32, sy - 26 - i * 20
        fy = sy - 26 - 3 * 20 - 14
        if self.pulse is not None:
            self.pulse.x, self.pulse.y = lx, fy - 24
        self.form_title.x, self.form_title.y = lx + 32, fy
        for i, lab in enumerate(self.form_lines):
            lab.x, lab.y = lx + 32, fy - 26 - i * 20
            lab.font_size = 12 if w >= 1200 else 11
        # o calendário do mês: grande e ao centro da página; à esquerda dele
        # ficam a sequência, a forma e as próximas atividades
        cw = max(460.0, min(w * 0.58, w - 2 * 330.0))
        ux = (w - cw) / 2
        self._left_w = max(120.0, ux - 48 - 36 - 28)
        self.cal.layout(ux, sy, cw, sy - bottom)
        uy = fy - 26 - 2 * 20 - 16
        self.up_title.x, self.up_title.y = lx, uy
        self._up_top = uy - 26
        self._up_rows = max(0, min(len(self.up_lines), int((self._up_top - bottom) // 22)))
        for i, lab in enumerate(self.up_lines):
            lab.x, lab.y = lx, self._up_top - i * 22
        self._up_x1 = ux - 16
        for i, tile in enumerate(self.tiles):
            tile.set_selected(i == self.selected and not self.cal.focused)

    def enter(self) -> None:
        a = self.app
        athlete = a.db.athlete()
        self.chrome.set("Perennia", "",                 # sem texto por baixo do título
                        "←→↑↓ escolher · Enter abrir · no calendário: PgUp/PgDn mês · T hoje · "
                        "D escolher data")
        # a lista (invisível) serve o teclado e os testes; os cartões são o que se vê
        self.list.set_items([Item(tile.title_text, action=act)
                             for tile, act in zip(self.tiles, self._actions())],
                            keep_index=True)
        self.list.y = -3000
        st = stats.streaks(a.db)
        self.streak_title.text = t("home.streak")
        lines = [t("home.streak_days", n=st["days"]) + "  ·  "
                 + t("home.streak_weeks", n=st["weeks"]),
                 t("home.streak_best", d=st["best_days"], w=st["best_weeks"]),
                 t("home.this_week", n=st["rides_this_week"])]
        for lab, text in zip(self.streak_lines, lines):
            lab.text = _fit_text(text, self._left_w, lab.font_size)
        self.form_title.text = t("home.form")
        now = stats.fitness_now(a.db)
        if now is None:
            lines = [t("home.form_none"), ""]
        else:
            lines = [t("home.form_line", ctl=f"{now['ctl']:.0f}", atl=f"{now['atl']:.0f}",
                       tsb=f"{now['tsb']:+.0f}"), t(f"form.{now['state']}")]
        for lab, text in zip(self.form_lines, lines):
            lab.text = _fit_text(text, self._left_w, lab.font_size)
        self.cal.load(a.db)
        self.upcoming = self.upcoming_entries()
        self._fill_upcoming()

    def _fill_upcoming(self) -> None:
        from velo.ui.widgets import fit_text
        self.up_title.text = tr("Próximas atividades", "Upcoming activities")
        width = getattr(self, "_up_x1", 300) - 48
        rows = getattr(self, "_up_rows", len(self.up_lines))
        self._up_rects = []
        for i, lab in enumerate(self.up_lines):
            if i >= rows:
                lab.text = ""
                continue
            if i < len(self.upcoming):
                e = self.upcoming[i]
                mark = "✓ " if e.done else ""
                text = f"{cv_weekday(e.day)} · {sport_name(e.sport)} · {e.title or '—'}"
                lab.text = fit_text(mark + text, width, 12)
                lab.color = DIM if e.done else TEXT
                self._up_rects.append((48.0, lab.y - 18, width, 22.0, e.day))
            elif i == 0:
                lab.text = fit_text(tr("Nada planeado nas próximas duas semanas",
                                       "Nothing planned for the next two weeks"), width, 12)
                lab.color = DIM
            else:
                lab.text = ""
        if len(self.upcoming) > rows and rows > 0:
            self.up_lines[rows - 1].text = fit_text(
                tr("+ {n} mais no calendário", "+ {n} more in the calendar",
                   n=len(self.upcoming) - rows + 1), width, 12)
            self.up_lines[rows - 1].color = DIM
            self._up_rects = self._up_rects[:rows - 1]

    def upcoming_entries(self) -> list:
        """O que está planeado de hoje a 13 dias, pela ordem dos dias."""
        from datetime import date as _date, timedelta as _td
        from velo.core import calendar_view as cv
        today = _date.today()
        end = today + _td(days=self.UPCOMING_DAYS - 1)
        try:
            done = cv.sessions_between(self.app.db, today, today)
            return [e for e in cv.planned_between(self.app.db, today, end, done)
                    if not (e.done and e.day < today)]
        except Exception:
            return []

    def _select(self, i: int) -> None:
        self.selected = max(0, min(len(self.tiles) - 1, i))
        self.list.index = self.selected
        self.cal.focused = False
        self.cal.place()
        for k, tile in enumerate(self.tiles):
            tile.set_selected(k == self.selected)

    def _focus_calendar(self) -> None:
        self.cal.focused = True
        for tile in self.tiles:
            tile.set_selected(False)
        self.cal.place()

    def _open(self, i: int) -> None:
        if i < len(self.tiles):
            self._actions()[i]()

    def open_day(self, d) -> None:
        from velo.ui.day_popups import DayPopup
        self.app.push(DayPopup(self.app, d))

    def pick_date(self) -> None:
        """O seletor de datas: salta para qualquer mês/dia do calendário."""
        from datetime import date as _date
        from velo.ui.pickers import pick_date

        def go(iso: str) -> None:
            self._focus_calendar()
            self.cal.go(_date.fromisoformat(iso))
        pick_date(self.app, tr("Ir para a data", "Go to date"), self.cal.sel, go)

    def _cal_nav(self, kind: str) -> None:
        from datetime import date as _date
        if kind == "pick":
            self.pick_date()
            return
        self._focus_calendar()
        if kind == "today":
            self.cal.go(_date.today())
        else:
            y, m = _calendar().cv.shift_month(self.cal.year, self.cal.month,
                                              1 if kind == "next" else -1)
            self.cal.go(_date(y, m, 1))

    def on_key(self, symbol: int, modifiers: int) -> bool:
        from datetime import date as _date, timedelta as _td
        n_tiles = len(self.tiles)
        if self.cal.focused:
            moves = {key.LEFT: -1, key.RIGHT: 1, key.UP: -7, key.DOWN: 7}
            if symbol == key.UP and self.cal.first_week():
                self._select(min(n_tiles - 1, self.BIG + 2))      # de volta aos cartões
            elif symbol in moves:
                self.cal.go(self.cal.sel + _td(days=moves[symbol]))
            elif symbol in (key.PAGEUP, key.PAGEDOWN):
                y, m = _calendar().cv.shift_month(self.cal.year, self.cal.month,
                                                  1 if symbol == key.PAGEDOWN else -1)
                self.cal.go(_date(y, m, 1))
            elif symbol == key.T:
                self.cal.go(_date.today())
            elif symbol in (key.D, key.G):
                self.pick_date()
            elif symbol in (key.ENTER, key.RETURN, key.SPACE):
                self.open_day(self.cal.sel)
            elif symbol == key.ESCAPE:
                self._select(self.selected)
            else:
                return False
            return True
        if symbol == key.RIGHT:
            self._select(min(n_tiles - 1, self.selected + 1))
        elif symbol == key.LEFT:
            self._select(max(0, self.selected - 1))
        elif symbol == key.DOWN:
            if self.selected >= self.BIG:
                self._focus_calendar()
            else:
                self._select(min(n_tiles - 1, self.selected + self.BIG))
        elif symbol == key.UP:
            if self.selected >= self.BIG:
                self._select(self.selected - self.BIG)
        elif symbol in (key.ENTER, key.RETURN, key.SPACE):
            self._open(self.selected)
        elif symbol == key.ESCAPE:
            pass                  # no ecrã inicial, Esc não sai por acidente
        else:
            return False
        return True

    def on_mouse(self, x: int, y: int) -> bool:
        for i, tile in enumerate(self.tiles):
            if tile.hit(x, y):
                self._select(i)
                self._open(i)
                return True
        nav = self.cal.hit_nav(x, y)
        if nav is not None:
            self._cal_nav(nav)
            return True
        d = self.cal.hit(x, y)
        if d is not None:
            self._focus_calendar()
            self.cal.go(d)
            self.open_day(d)
            return True
        for rx, ry, rw, rh, day in self._up_rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.open_day(day)
                return True
        return False

    def on_resize(self, w: int, h: int) -> None:
        self.chrome.layout()
        self._layout()
        self.enter()

    def draw(self) -> None:
        self.chrome.draw()
        self.batch.draw()


def cv_weekday(d) -> str:
    """«qua 04/11» (ou «hoje», «amanhã»)."""
    from datetime import date as _date, timedelta as _td
    today = _date.today()
    if d == today:
        return tr("hoje", "today")
    if d == today + _td(days=1):
        return tr("amanhã", "tomorrow")
    days = tr("seg ter qua qui sex sáb dom", "Mon Tue Wed Thu Fri Sat Sun").split()
    return f"{days[d.weekday()]} {d.day:02d}/{d.month:02d}"


def _fit_text(text: str, width_px: float, size: float) -> str:
    max_chars = max(4, int(width_px / (size * 0.6)))
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def _select_color():
    from velo.ui.widgets import SELECT
    return SELECT


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


def RouteLibrary(app: "App"):            # noqa: N802 — compatibilidade
    """As rotas: agora no menu Rotas do ecrã inicial (ver route_screens)."""
    return _routes().RoutesScreen(app)


class GpxPicker(Screen):
    """Procura ficheiros .gpx em pastas prováveis; sem dependências de diálogo."""

    SEARCH = ("gpx", ".", "~/Downloads", "~/Documents", "~/Transferências",
              "~/Área de Trabalho", "~/Desktop")

    def __init__(self, app: "App", on_pick: Callable | None = None):
        super().__init__(app)
        self.on_pick = on_pick          # chamado com o id da rota nova (e fecha-se)

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
            if self.on_pick is not None:
                self.on_pick(route_id)
            else:
                a.push(RouteDetail(a, route_id))
        except Exception as e:
            a.message(f"{t('common.error')}: {e}")


def RouteDetail(app: "App", route_id: str):        # noqa: N802 — compatibilidade
    """Uma rota: a ficha do menu Rotas (perfil, segmentos, sessões)."""
    return _routes().RouteOverview(app, route_id)


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
    # treino estruturado (um treino, um teste, um plano de voltas): sem auto
    # lap à escolha — a volta fecha-se sozinha no fim de cada bloco
    structured = False

    def autolap_cfg(self) -> dict:
        cfg = getattr(self, "_autolap", None)
        if cfg is None:
            cfg = self._autolap = {"mode": "off", "value": 0}
        if self.structured:
            cfg["mode"], cfg["value"] = "off", 0
        return cfg

    def autolap_items(self) -> list[Item]:
        from velo.core import sports as sp
        if self.structured:
            return [Item(tr("Voltas", "Laps"), value=tr("uma por bloco", "one per block"),
                         detail=tr("treino estruturado: cada bloco feito fecha uma volta, "
                                   "sozinho", "structured workout: each block done closes a "
                                   "lap by itself"), enabled=False)]
        cfg = self.autolap_cfg()
        mode = cfg["mode"]
        rows = [Item(tr("Auto lap", "Auto lap"),
                     value={"off": tr("desligado", "off"), "time": tr("por tempo", "by time"),
                            "distance": tr("por distância", "by distance")}[mode],
                     detail=tr("←/→ muda · desligado por omissão",
                               "←/→ changes · off by default"),
                     data="autolap_mode")]
        if mode != "off":
            rows.append(Item(tr("Volta a cada", "Lap every"), value=sp.autolap_text(cfg)[
                len(tr("a cada ", "every ")):], detail=tr("←/→ muda", "←/→ changes"),
                data="autolap_value"))
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
        if self.structured:
            return False
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
                 lines: list[str] | None = None, options: dict | None = None,
                 structured: bool = False):
        super().__init__(app)
        self.AUTOLAP_SPORT = sport
        self.structured = structured
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
                              data="pool"))
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


def RideSetup(app: "App", route_id: str | None, workout_id: str | None = None,  # noqa: N802
              kind: str = "route", ftp_protocol: str | None = None,
              chase_level: str | None = None):
    """Compatibilidade: a preparação da sessão é agora uma janela
    (`session_setup.SessionSetup`)."""
    return _setup().SessionSetup(app, "cycling", kind="free" if kind == "route" else kind,
                                 route_id=route_id, workout_id=workout_id,
                                 ftp_protocol=ftp_protocol, chase_level=chase_level)


# ----------------------------------------------------------------- sessão


class RideScreen(Screen):
    """Prepara o mundo, corre a sessão e passa ao resumo."""

    KEY_SCOPE = "ride"
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
            row = a.db.workout(self.workout_id)       # também os que não estão na lista
            name = row["name"] if row is not None else ""
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

        # Um treino (blocos) não leva o cenário 3D, por agora: o fundo é o do tema. (O 3D, com o
        # céu cinzento-azulado, fica para os passeios por uma rota.)
        if points and self.kind != "workout":
            self.world = World(points, a.db.get("render_preset", "low"),
                               seed=self.route_id or "")
            self.world.setup_gl()
        else:
            self.preparing = False
        self.start_countdown(self.resume)       # depois de preparar a rota
        self.chrome.set("", "", "")

    def cancel_countdown(self) -> None:
        self._discard()

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
        done = False
        for event in self.engine.drain_events():
            self.hud.handle(event)
            done = done or event.kind == "workout_done"
        self.hud.alert_n = self._cue_tick()
        self.hud.update(self.engine)
        if done:                      # o último bloco acabou: pára e pergunta, como em «Terminar»
            self._ask_finish()

    def _cue_tick(self) -> int | None:
        """Bips e contagem dos últimos segundos de cada bloco do treino (ver `velo.core.cues`)."""
        from velo.ui.session_flow import drive_cues
        e = self.engine
        wk = getattr(e, "workout", None)
        if wk is None or getattr(e, "finished", False):
            return None
        plan = wk.plan(getattr(e, "_t", 0.0), ahead=0)
        if not plan:
            return drive_cues(self, None, "work", 0.0, None)
        cur = plan[0]
        kind = "rest" if cur["kind"] == "rest" else "work"
        return drive_cues(self, ("step", cur["idx"]), kind,
                          cur["duration_s"] - cur["remaining_s"], cur["remaining_s"])

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
            if not self.engine.manual_laps:
                if self.hud is not None:
                    self.hud.toast(tr("Num treino, cada bloco é uma volta (voltas à mão só na sessão livre)", "In a workout each block is a lap (manual laps only in a free session)"))
                return True
            self.engine.lap("manual")
            return True
        if symbol == key.P:
            self._toggle_pause()
            return True
        if self.hud is not None and self.hud.confirm_visible:
            # diálogo aberto: S/Enter terminam, N/Esc voltam à sessão
            if symbol in (key.ENTER, key.RETURN, key.S, key.Y):
                self._finish_with_tags()
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
                self._finish_with_tags()
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

    def _finish_with_tags(self) -> None:
        """«Sim, terminar»: antes de gravar, a janela das etiquetas do .fit."""
        e = self.engine
        if e is None or self.hud is None or getattr(e, "_t", 0) < 1:
            self._finish()
            return
        s = e.summary()
        self.hud.hide_confirm()
        from velo.ui.tag_popup import open_session_tags
        open_session_tags(
            self, "cycling", workout_id=self.workout_id, has_route=bool(self.route_id),
            summary={"ftp_w": e.athlete.ftp_w, "np_w": s.np_w, "avg_power_w": s.avg_power_w,
                     "tss": s.tss, "elapsed_s": s.elapsed_s},
            on_done=self._tags_done, on_back=self._cancel_finish)

    def _tags_done(self, info: dict) -> None:
        self.engine.tags_chosen = info
        self._finish()

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
        lap = "L volta · " if self.engine is None or self.engine.manual_laps else ""
        return lap + "P pausa · +/− resistência · F10 terminar e guardar"

    def on_text(self, text: str) -> bool:
        return True                         # na sessão as teclas não escrevem


class SummaryScreen(RadarSide, Screen):
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

    def go_back(self) -> None:
        self.app.reset_to_menu()

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
        # sem «Fechar» na lista: o «Voltar» de baixo (ou Esc) leva ao menu
        ftp_rows = [i for i in items if i.action == self._accept_ftp]
        for row in ftp_rows:                       # aceitar a FTP também à vista
            items.remove(row)
            items.insert(0, row)

        if self.result.get("name"):
            subtitle = f"{self.result['name']} · {subtitle}"
        self.chrome.set(t("summary.title"), subtitle, self.footer())
        fb_item = _feedback().summary_item(self.app, "ride", self.result.get("ride_id"))
        if fb_item is not None:
            items.insert(0, fb_item)
        items[1:1] = self.radar_attach("cycling", self.result.get("ride_id"))   # o radar + longevidade
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


class SnapshotUnsaved:
    """Mistura para os editores: «há alterações?» compara o estado de agora
    (`snapshot_state`) com o do início ou do último gravado (`mark_saved`).
    Voltar atrás com alterações pergunta (ver App.ask_unsaved)."""

    def snapshot_state(self):
        return None

    def mark_saved(self) -> None:
        self._snap = self.snapshot_state()

    def has_unsaved(self) -> bool:
        if not hasattr(self, "_snap"):
            return False
        return self.snapshot_state() != self._snap


class PopupMixin:
    """Um ecrã numa janela por cima do atual (o de baixo continua a correr: uma
    sessão não para por se abrir os dispositivos). Esc ou clicar fora fecham.
    Usa-se com `Screen` (ou `EditScreen`), à esquerda dele na herança."""

    MODAL = True
    AGENT = False
    W, H = 760, 520

    def _init_popup(self) -> None:
        self.popup = Popup(self.app.window, self.W, self.H)
        self._place()

    def set_popup_size(self, w: float, h: float) -> None:
        if self.popup.want != (w, h):
            self.popup.want = (w, h)
            self._place()

    def _place(self) -> None:
        p = self.popup
        p.layout()
        c = self.chrome
        c.title.font_size = 20
        c.title.x, c.title.y = p.x + 24, p.y + p.h - 18
        c.subtitle.x, c.subtitle.y = p.x + 24, p.y + p.h - 50
        c.footer.x, c.footer.y = p.x + 160, p.y + 22
        c.agent_hint.text = ""
        self.list.x = p.x + 28
        self.list.y = p.y + p.h - 92
        self.list.width = p.w - 56
        self.list.set_visible_rows(max(2, int((p.h - 92 - 96) // 38) + 1))
        self.list.bar_right = p.x + p.w - 16
        self.list.bar_y = p.y + 12
        self.list.top_y = p.y + p.h - 50
        if self.back_button is not None:
            self.back_button.place(p.x + 16, p.y + 12, t("common.back"))
        self.list._sync()

    def on_resize(self, w: int, h: int) -> None:
        self._place()

    def close_outside(self) -> None:
        """Clicar fora da janela."""
        self.app.pop()

    def on_mouse(self, x: int, y: int) -> bool:
        if not self.popup.inside(x, y):
            self.close_outside()
            return True
        return super().on_mouse(x, y)

    def _wrap_subtitle(self) -> None:
        """Um subtítulo comprido parte-se em linhas dentro da janela."""
        sub = self.chrome.subtitle
        maxw = self.popup.w - 48
        if getattr(self, "_wrapped_for", None) == (sub.text, maxw):
            return
        self._wrapped_for = (sub.text, maxw)
        from velo.ui.widgets import set_wrap, text_px
        set_wrap(sub, maxw if text_px(sub.text, 13) > maxw else None)

    def draw(self) -> None:
        self.popup.draw()
        self._wrap_subtitle()
        self.chrome.set_footer_limit(self.list.buttons_left)
        self.chrome.draw()
        self.list.draw()
        if self.back_button is not None:
            self.back_button.draw()


class ModalScreen(PopupMixin, Screen):
    """Janela por cima do ecrã atual (ver `PopupMixin`)."""

    def __init__(self, app: "App"):
        super().__init__(app)
        self._init_popup()


class ConfirmScreen(ModalScreen):
    """Pergunta antes de fazer (sair da aplicação, terminar uma sessão).

    Com `buttons=True` as opções são botões em baixo, à direita (a última é
    a principal), e não há «Fechar»: uma das opções já é a de cancelar."""

    W, H = 560, 300

    def __init__(self, app: "App", title: str, sub: str,
                 options: list[tuple[str, Callable]], default: int = 0,
                 buttons: bool = False, cancel: Callable | None = None):
        self.title_text, self.sub_text, self.options = title, sub, options
        # a janela cresce para caber o título e os botões lado a lado
        from velo.ui.widgets import button_width, text_px
        need = text_px(title, 20, bold=True) + 64
        if buttons:
            need = max(need, sum(button_width(lab) for lab, _a in options)
                       + 10 * (len(options) - 1) + 48)
        self.W = int(max(type(self).W, min(1180, need)))
        self.default = default
        self.as_buttons = buttons
        self.cancel = cancel
        super().__init__(app)
        if buttons:
            self.back_button = None

    def enter(self) -> None:
        self.chrome.set(self.title_text, self.sub_text, "")
        n = len(self.options)
        self.list.set_items([Item(lab, action=act, button=self.as_buttons,
                                  primary=self.as_buttons and k == n - 1)
                             for k, (lab, act) in enumerate(self.options)])
        self.list.index = self.default
        self.list._sync()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        if self.as_buttons and symbol in (key.LEFT, key.RIGHT):
            self.list.move(1 if symbol == key.RIGHT else -1)
            return True
        if symbol == key.ESCAPE and self.cancel is not None:
            self.cancel()
            return True
        return super().on_key(symbol, modifiers)

    def on_mouse(self, x: int, y: int) -> bool:
        if not self.popup.inside(x, y) and self.cancel is not None:
            self.cancel()
            return True
        return super().on_mouse(x, y)


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

    # ------------------------------------------------------------ a lista

    @staticmethod
    def _transport_of(src) -> str:
        """`ble`, `ant` ou `sim` (os aparelhos «SEM HARDWARE» não têm ligação)."""
        tr_ = getattr(src, "transport", "")
        return tr_ if tr_ in ("ant", "ble") else "sim"

    TRANSPORT_NAME = {"ble": "Bluetooth", "ant": "ANT+"}

    def _live_text(self, device_id: str) -> str:
        """O que o aparelho está mesmo a mandar («150 W · 88 rpm»), ou «sem dados»."""
        a = self.app
        live_src = a.hub.live_of(device_id) if hasattr(a.hub, "live_of") else {}
        bits = []
        if "power" in live_src:
            bits.append(f"{int(live_src['power'][0])} W")
        if "cadence" in live_src:
            bits.append(f"{int(live_src['cadence'][0])} rpm")
        if "hr" in live_src:
            bits.append(f"{int(live_src['hr'][0])} bpm")
        if "speed" in live_src and not bits:
            bits.append(f"{live_src['speed'][0] * 3.6:.1f} km/h")
        return " · ".join(bits) if bits else tr("sem dados", "no data")

    def connected_devices(self) -> list[dict]:
        """Os aparelhos ligados agora — do hub, a máquina de remo e a passadeira —
        com a ligação (`ble`/`ant`/`sim`), o que mandam e o que sabem fazer."""
        a = self.app
        out = []
        for src in a.hub.sources:
            caps = []
            if getattr(src, "supports_sim", False):
                caps.append("declive")
            if getattr(src, "supports_erg", False):
                caps.append("ERG")
            if getattr(src, "supports_spindown", False):
                caps.append("spindown")
            out.append({"name": getattr(src, "name", "?"), "via": self._transport_of(src),
                        "live": self._live_text(getattr(src, "device_id", "")),
                        "caps": " · ".join(caps), "id": getattr(src, "device_id", ""),
                        "action": lambda s=src: self._disconnect(s)})
        if a.rower is not None:
            out.append({"name": a.rower.name, "via": self._transport_of(a.rower),
                        "live": tr("máquina de remo", "rowing machine"), "caps": "",
                        "id": getattr(a.rower, "device_id", ""), "action": self._drop_rower})
        tm = getattr(a, "treadmill", None)
        if tm is not None:
            out.append({"name": getattr(tm, "name", "Passadeira"),
                        "via": self._transport_of(tm),
                        "live": tr("passadeira", "treadmill"), "caps": "",
                        "id": getattr(tm, "device_id", ""),
                        "action": self._drop_treadmill})
        return out

    def _connected_rows(self, devices: list[dict], via: str) -> list[Item]:
        """As linhas «✓ nome» de uma ligação: Enter desliga."""
        rows = []
        for d in devices:
            if d["via"] != via:
                continue
            rows.append(Item(f"✓ {d['name']}", value=d["live"],
                             detail=(d["caps"] + " · " if d["caps"] else "")
                             + tr("Enter desliga", "Enter disconnects"),
                             action=d["action"], indent=1))
        return rows

    def enter(self) -> None:
        """Três blocos — **Bluetooth**, **ANT+** e **SEM HARDWARE** — cada um com
        o seu «Procurar», os aparelhos encontrados (✓ nos ligados) por baixo,
        recuados; e, no fim, **Dispositivos ligados**: só informação."""
        from velo.io import rower as rower_io
        a = self.app
        pref = a.db.get("connection_preference", autoconnect.ANT_FIRST)
        devices = self.connected_devices()
        linked_ids = {d["id"] for d in devices}
        items = [Item(t("dev.auto") if not a.auto_running else t("dev.auto_running"),
                      value=t(f"set.pref.{pref}"), detail=t("dev.auto_hint"),
                      action=a.start_auto_connect, enabled=not a.auto_running)]

        def counted(via: str) -> str:
            n = sum(1 for d in devices if d["via"] == via)
            return tr("{n} ligado(s)", "{n} connected", n=n) if n else ""

        # ---- Bluetooth
        items.append(Item(self.TRANSPORT_NAME["ble"], value=counted("ble"), header=True))
        items.append(Item(t("dev.scan") if not self.scanning else t("dev.scanning"),
                          action=self._scan, enabled=not self.scanning, indent=1))
        items += self._connected_rows(devices, "ble")
        ble_rows = 0
        for d in self.found:
            if d.device_id in linked_ids:
                continue
            proto = rower_io.is_rower(d.name, ["00001826-0000-1000-8000-00805f9b34fb"]
                                      if "ftms" in d.profiles else [])
            if proto:
                if a.rower is not None and getattr(a.rower, "address", None) == d.address:
                    continue
                items.append(Item(d.name, value=tr("REMO", "ROWER"),
                                  detail=tr("máquina de remo (Bluetooth) · Enter liga",
                                            "rowing machine (Bluetooth) · Enter connects"),
                                  action=lambda dd=d, p=proto: self._rower(dd, p), indent=1))
            else:
                items.append(Item(d.name, value=" ".join(d.profiles).upper() or "—",
                                  detail=(f"rssi {d.rssi} · " if d.rssi else "")
                                  + tr("Enter liga", "Enter connects"),
                                  action=lambda dd=d: self._connect(dd), indent=1))
            ble_rows += 1
        if not ble_rows and not counted("ble"):
            items.append(Item(tr("nenhum dispositivo Bluetooth", "no Bluetooth devices"),
                              enabled=False, indent=1))

        # ---- ANT+
        items.append(Item(self.TRANSPORT_NAME["ant"], value=counted("ant"), header=True))
        items.append(Item(t("dev.scan_ant") if not self.ant_scanning else t("dev.scanning_ant"),
                          detail=t("dev.scan_ant_hint"), action=self._scan_ant,
                          enabled=not self.ant_scanning, indent=1))
        items += self._connected_rows(devices, "ant")
        ant_rows = 0
        for channel, info in a.ant_found:
            if getattr(info, "trainer_twin", False):
                continue          # a potência do rolo já vem pelo FE-C
            if info.device_id in linked_ids:
                continue
            items.append(Item(info.name, value="ANT+",
                              detail=t(f"dev.role.{info.role}") + " · "
                              + tr("Enter liga", "Enter connects"),
                              action=lambda ch=channel, inf=info: self._connect_ant(ch, inf),
                              indent=1))
            ant_rows += 1
        if not ant_rows and not counted("ant"):
            items.append(Item(tr("nenhum dispositivo ANT+", "no ANT+ devices"),
                              enabled=False, indent=1))

        # ---- SEM HARDWARE (simulados)
        items.append(Item(tr("SEM HARDWARE", "NO HARDWARE"), value=counted("sim"),
                          header=True))
        items += self._connected_rows(devices, "sim")
        if "sim:trainer" not in linked_ids:
            items.append(Item(t("dev.simulated"), action=self._add_sim, indent=1))
        if "sim:hr" not in linked_ids:
            items.append(Item(tr("SEM HARDWARE - Banda cardíaca", "NO HARDWARE - Heart strap"),
                              detail=tr("FC simulada que segue o esforço · todos os desportos",
                                        "simulated HR that follows the effort · every sport"),
                              action=self._add_sim_hr, indent=1))
        if a.rower is None or getattr(a.rower, "protocol", "") != "sim":
            items.append(Item(tr("SEM HARDWARE - Remo", "NO HARDWARE - Rower"),
                              detail=tr("para remar sem a máquina (testes, demonstração)",
                                        "to row without the machine (tests, demo)"),
                              action=self._add_sim_rower, indent=1))
        if getattr(a, "treadmill", None) is None:
            items.append(Item(tr("SEM HARDWARE - Passadeira", "NO HARDWARE - TREADMILL"),
                              detail=tr("passadeira simulada: velocidade, inclinação e passos "
                                        "(sem FC) · corrida", "simulated treadmill: speed, "
                                        "incline and steps (no HR) · running"),
                              action=self._add_sim_treadmill, indent=1))

        # ---- o rolo: só com um rolo ligado (que aceite comandos) é que se pode calibrar
        can_cal = a.hub.can_control and getattr(a.hub.trainer, "supports_spindown", False)
        items.append(Item(tr("Rolo", "Trainer"), header=True))
        items.append(Item(t("dev.calibrate"), action=self._calibrate, enabled=bool(can_cal),
                          detail="" if can_cal else tr("liga primeiro um rolo",
                                                       "connect a trainer first"),
                          indent=1))

        # ---- no fim: só informação (sem ações; as ações estão em cada ligação)
        items.append(Item(tr("Dispositivos ligados", "Connected devices"),
                          value=str(len(devices)) if devices else "", header=True))
        for d in devices:
            via = self.TRANSPORT_NAME.get(d["via"], tr("simulado", "simulated"))
            items.append(Item(f"✓ {d['name']}", value=f"{via} · {d['live']}",
                              detail=d["caps"], enabled=False, indent=1))
        if not devices:
            items.append(Item(tr("nenhum dispositivo ligado", "no device connected"),
                              enabled=False, indent=1))

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
        # uma só coluna, com a janela a crescer para caber os blocos seguidos
        # (só se a janela da aplicação for pequena é que passam a duas colunas)
        rows = sum(1 for it in items if not it.button)
        self.set_popup_size(self.W, 190 + 38 * (rows - 1))
        self.list.set_items(items, keep_index=True)

    def update(self, dt: float) -> None:
        if not self.app.in_session:          # a sessão de baixo já avança os sensores
            self.app.hub.tick(dt)
        # uma vez por segundo: os valores ao vivo (o título e os aparelhos ligados)
        self._live_t = getattr(self, "_live_t", 0.0) + dt
        if self._live_t >= 1.0 and self.app.hub.sources:
            self._live_t = 0.0
            self.enter()
        res = getattr(self, "_rower_result", None)
        if res is not None:
            self._rower_result = None
            ok, sensor = res
            if ok:
                self.app.set_rower(sensor)
                self.note = tr("Ligada: {n}", "Connected: {n}", n=sensor.name)
            else:
                self.note = tr("Não foi possível ligar {n}", "Could not connect {n}",
                               n=sensor.name)
            self.enter()
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
        """Uma máquina de remo encontrada pelo Bluetooth: liga-se aqui mesmo."""
        from velo.io import rower as rower_io
        sensor = rower_io.RowerSensor(d.address, d.name, proto)
        self.note = tr("A ligar {n}…", "Connecting {n}…", n=d.name)

        def work() -> None:
            try:
                self._rower_result = (sensor.connect(), sensor)
            except Exception:
                self._rower_result = (False, sensor)
        threading.Thread(target=work, name="rower-connect", daemon=True).start()
        self.enter()

    def _add_sim_rower(self) -> None:
        from velo.io import rower as rower_io
        self.app.set_rower(rower_io.SimulatedRower())
        self.note = tr("SEM HARDWARE - Remo ligado", "NO HARDWARE - Rower connected")
        self.enter()

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

    def _drop_treadmill(self) -> None:
        self.app.set_treadmill(None)
        self.enter()

    def _add_sim(self) -> None:
        self.app.hub.add_source(SimulatedTrainer(), role="simulated", is_trainer=True)
        self.note = t("dev.simulated")
        self.enter()

    def _add_sim_treadmill(self) -> None:
        from velo.core import workout_meta as wm
        from velo.io.sim import SimulatedTreadmill
        lim = wm.device_limits(self.app.db)
        self.app.set_treadmill(SimulatedTreadmill(lim["treadmill_max_kmh"],
                                                  lim["treadmill_max_incline"]))
        self.note = tr("SEM HARDWARE - Passadeira ligada", "NO HARDWARE - TREADMILL connected")
        self.enter()

    def _add_sim_hr(self) -> None:
        from velo.io.sim import SimulatedHeartStrap
        a = self.app
        a.hub.add_source(SimulatedHeartStrap(effort=a.effort_now), role="hr_monitor")
        self.note = tr("SEM HARDWARE - Banda cardíaca ligada",
                       "NO HARDWARE - Heart strap connected")
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
    """Definições por separadores: Atleta · Geral · Desportos · Ecrã e idioma ·
    Ligações Externas · Atalhos de teclado. (A Sincronização está no menu
    «Backups e Sincronização».)

    **Desportos** tem um separador por desporto e, em cada um, três: as
    métricas disponíveis (as desligadas não aparecem no editor do ecrã), o
    ecrã da sessão (as métricas e a disposição dos painéis) e as sessões não
    ERG (os aparelhos sem controlo: níveis do rolo, resistências do remo,
    velocidade e inclinação máximas da passadeira — o construtor não deixa
    passar destes limites).

    Funcionam em **rascunho**: as setas ←/→ mudam os valores (Enter não),
    mas nada fica gravado até carregar em **Guardar** (em baixo, à direita;
    só fica ativo quando alguma coisa mudou). **Cancelar** volta aos valores
    gravados. Sair com alterações por guardar pergunta primeiro."""

    TABBED = True
    # que linhas vão em cada separador (pelo nome; ver `_rows`)
    GROUPS = (("name", "age", "weight", "ftp", "lthr", "row_ftp", "run_pace", "swim_pace",
               "@pmc_head", "pmc_synced"),
              ("difficulty", "lookahead", "auto_pause", "connection", "auto_connect"),
              ("@sports",),
              ("theme", "units", "language", "render", "display", "msaa"),
              ("strava", "@garmin_head", "garmin_user", "garmin_password", "garmin_cfg"),
              ("@shortcuts",),
              ("@sounds",))
    ATH_FIELDS = ("name", "birth_year", "weight_kg", "ftp_w", "lthr")

    def __init__(self, app: "App"):
        super().__init__(app)
        self.draft: dict = {}
        self._orig: dict = {}
        self.ath = app.db.athlete()
        self._ath0 = self._ath_sig()
        w, h = app.window.width, app.window.height
        # Desportos: um separador por desporto e, em cada um, três secções
        self.sport_tab = 0
        self.section_tab = 0
        self.sport_tabs = TabBar([sport_name(s) for s in self.SPORTS], 48,
                                 self.content_top(h) + 6, w - 96)
        self.section_tabs = TabBar(self.section_labels(), 48, self.content_top(h) - 38, w - 96)

    # A natação não tem opções aqui (só construtor de treinos e estatísticas)
    SPORTS = ("cycling", "rowing", "running", "gym")
    SECTION_NAMES = {"metrics": ("Métricas de sessão disponíveis", "Available session metrics"),
                     "layout": ("Disposição do ecrã de sessão", "Session screen layout"),
                     "limits": ("Sessões Não ERG", "Non-ERG sessions")}

    def sections(self) -> list[str]:
        """As secções do desporto: o ginásio não tem aparelhos Não ERG."""
        return ["metrics", "layout"] + (["limits"] if self.sport != "gym" else [])

    def section_labels(self) -> list[str]:
        return [tr(*self.SECTION_NAMES[s]) for s in self.sections()]

    @property
    def sport(self) -> str:
        return self.SPORTS[self.sport_tab % len(self.SPORTS)]

    def tab_labels(self) -> list[str]:
        return [tr("Atleta", "Athlete"), tr("Geral", "General"), tr("Desportos", "Sports"),
                tr("Ecrã e idioma", "Display & language"),
                tr("Ligações Externas", "External connections"),
                tr("Atalhos de teclado", "Keyboard shortcuts"),
                tr("Configurações sonoras", "Sound settings")]

    def group(self) -> tuple:
        return self.GROUPS[self.tab % len(self.GROUPS)]

    # ------------------------------------------------------------ rascunho

    def _ath_sig(self) -> tuple:
        return tuple(getattr(self.ath, k) for k in self.ATH_FIELDS)

    def get(self, key_: str, default=None):
        if key_ in self.draft:
            return self.draft[key_]
        if key_.startswith("@"):
            return default
        return self.app.db.get(key_, default)

    def put(self, key_: str, value) -> None:
        if key_ not in self._orig:
            self._orig[key_] = self.get(key_, None)
        if value == self._orig[key_]:
            self.draft.pop(key_, None)
        else:
            self.draft[key_] = value

    @property
    def dirty(self) -> bool:
        return bool(self.draft) or self._ath_sig() != self._ath0

    def has_unsaved(self) -> bool:
        return self.dirty

    def on_save(self) -> bool:
        if self.dirty:
            self.save()
            return True
        return self.list.press_button("primary")

    def save(self) -> None:
        a = self.app
        db = a.db
        draft = dict(self.draft)
        if self._ath_sig() != self._ath0:
            db.save_athlete(self.ath)
        for k, v in draft.items():
            if not k.startswith("@") and k not in ("theme", "display"):
                db.set(k, v)
        if "@garmin_user" in draft or "@garmin_password" in draft:
            from velo.core import garmin_sync as gsync
            try:
                gsync.write_credentials(gsync.config_path(db), draft.get("@garmin_user"),
                                        draft.get("@garmin_password"))
            except OSError as e:
                a.message(f"{t('common.error')}: {e}")
        if "units" in draft:
            a.units = draft["units"]
        if "language" in draft:
            set_language(draft["language"])
            a._topbar_texts()
        if "connection_preference" in draft:
            a.apply_connection_preference()
        self.draft.clear()
        self._orig.clear()
        self.ath = db.athlete()
        self._ath0 = self._ath_sig()
        if "display" in draft:
            d = draft["display"]
            a.set_display(bool(d["fullscreen"]), d.get("w"), d.get("h"))
        a.message(tr("Definições guardadas", "Settings saved"))
        if "theme" in draft:
            a.set_theme(draft["theme"])      # volta a construir os ecrãs com as cores novas
            return
        if a.current is self:
            self.enter()

    def cancel(self) -> None:
        """Volta aos valores gravados."""
        previewing = "theme" in self.draft
        self.draft.clear()
        self._orig.clear()
        self.ath = self.app.db.athlete()
        self._ath0 = self._ath_sig()
        if previewing:
            self._preview_theme()               # volta a pôr o tema gravado
            return
        self.enter()

    def discard(self) -> None:
        """Sair sem guardar: se o tema estava em pré-visualização, repõe-se."""
        if "theme" in self.draft:
            self.draft.clear()
            self._orig.clear()
            self._preview_theme()

    def adopt(self, old: "SettingsScreen") -> None:
        """Depois de mudar as cores (pré-visualização do tema), as Definições
        novas ficam com o rascunho das antigas."""
        self.draft, self._orig = old.draft, old._orig
        self.ath, self._ath0 = old.ath, old._ath0

    def _preview_theme(self) -> None:
        """Mostra já o tema escolhido (ou o gravado), sem o gravar."""
        from velo.gfx import theme as theme_mod
        want = self.get("theme", None) or theme_mod.DEFAULT
        self.app.set_theme(want, persist=False, carry=self)

    # -------------------------------------------------------------- linhas

    def _display_now(self) -> dict:
        a = self.app
        cur = {"fullscreen": bool(a.window.fullscreen), "w": a.window.width,
               "h": a.window.height}
        return self.get("display", None) if "display" in self.draft else cur

    def _display_text(self) -> str:
        d = self._display_now()
        if d["fullscreen"]:
            size = self.app.screen_size() or (self.app.window.width, self.app.window.height)
            return t("set.display.full", w=size[0], h=size[1])
        return t("set.display.window", w=d["w"], h=d["h"])

    def _msaa_text(self) -> str:
        want = int(self.get("msaa_samples", 4))
        text = f"{want}×" if want else t("common.off")
        if want != self.app.msaa_samples:
            text += " · " + t("set.msaa_restart")
        return text

    def _rows(self) -> dict[str, Item]:
        a = self.app
        ath = self.ath
        units = self.get("units", a.units)
        wv, wu = weight(ath.weight_kg, units)
        diff = float(self.get("trainer_difficulty", 1.0))
        from velo.core import garmin_sync as gsync
        from velo.core import rowing as rw
        arrows = tr("←/→ muda", "←/→ changes")
        on, off = t("common.on"), t("common.off")
        user0, has_pw = gsync.credentials(gsync.config_path(a.db))
        user = self.get("@garmin_user", None)
        pw = self.get("@garmin_password", None)
        age = (date.today().year - ath.birth_year) if ath.birth_year else None
        return {
            "name": Item(t("set.name"), value=(ath.name or "") + "▏", detail=t("set.name_hint"),
                         data="text:name"),
            "age": Item(t("set.age"), value=str(age or "—"),
                        detail=tr("estima a FC máxima (220 − idade) quando não há outra · "
                                  "←/→ ano de nascimento",
                                  "estimates max HR (220 − age) when there is no other · "
                                  "←/→ year of birth"), data="age"),
            "weight": Item(t("set.weight"), value=f"{wv:.1f} {wu}",
                           detail=tr("para os W/kg e a física da estrada (subidas) · ←/→ ±0,1 · "
                                     "Shift ±1", "for W/kg and the road physics (climbs) · "
                                     "←/→ ±0.1 · Shift ±1"), data="weight"),
            "ftp": Item(t("set.ftp"), value=f"{ath.ftp_w} W",
                        detail=tr("FTP — potência funcional de limiar: a média que aguentas "
                                  "~1 h; base das zonas, do IF e da TSS · ←/→ ±5 W",
                                  "FTP — functional threshold power: what you hold for ~1 h; "
                                  "basis of zones, IF and TSS · ←/→ ±5 W"), data="ftp"),
            "lthr": Item("LTHR", value=str(ath.lthr or "—"),
                         detail=tr("FC de limiar (lactato): a FC média de ~1 h no máximo; base "
                                   "das zonas de FC e do hrTSS · ←/→ ±1",
                                   "lactate threshold heart rate: your average HR over ~1 h "
                                   "all-out; basis of HR zones and hrTSS · ←/→ ±1"),
                         data="lthr"),
            "row_ftp": Item(tr("FTP do remo", "Rowing FTP"),
                            value=f"{int(self.get('row_ftp_w', rw.row_ftp(a.db)))} W",
                            detail=tr("a potência de limiar no remo: zonas e carga do remo · "
                                      "←/→ ±1 · Shift ±10 · o teste de 2000 m atualiza-a",
                                      "rowing threshold power: rowing zones and load · "
                                      "←/→ ±1 · Shift ±10 · the 2000 m test updates it"),
                            data="row_ftp"),
            "@pmc_head": Item(tr("Forma, fadiga e fitness (como o TrainingPeaks)",
                                 "Form, fatigue and fitness (like TrainingPeaks)"), header=True),
            "pmc_synced": Item(tr("Contar as atividades importadas", "Count imported activities"),
                               value=on if self.get("pmc_synced", True) else off,
                               detail=tr("as do Garmin e do TrainingPeaks entram na carga, sem "
                                         "duplicar as feitas na Perennia",
                                         "Garmin and TrainingPeaks ones count in the load, "
                                         "without duplicating those done in Perennia"),
                               data="pmc_synced"),
            "units": Item(t("set.units"),
                          value=t("set.units.metric") if units == "metric"
                          else t("set.units.imperial"), detail=arrows, data="units"),
            "language": Item(t("set.language"),
                             value="Português" if self.get("language", PT) == PT else "English",
                             detail=arrows, data="language"),
            "difficulty": Item(t("set.difficulty"), value=f"{diff * 100:.0f} %",
                               detail=tr("←/→ ajustar · escala a sensação de declive",
                                         "←/→ adjust · scales how the gradient feels"),
                               data="difficulty"),
            "render": Item(t("set.render"),
                           value=t(f"mode.render.{self.get('render_preset', 'low')}"),
                           detail=arrows, data="render"),
            "display": Item(t("set.display"), value=self._display_text(),
                            detail=t("set.display_hint"), data="display"),
            "msaa": Item(t("set.msaa"), value=self._msaa_text(), detail=t("set.msaa_hint"),
                         data="msaa"),
            "lookahead": Item(t("set.lookahead"), value=str(self.get("workout_lookahead", 2)),
                              detail=t("set.lookahead_hint"), data="lookahead"),
            "auto_pause": Item(t("set.auto_pause"),
                               value=on if self.get("auto_pause", True) else off,
                               detail=t("set.auto_pause_hint"), data="auto_pause"),
            "connection": Item(t("set.connection"),
                               value=t(f"set.pref.{self.get('connection_preference', 'ant_first')}"),
                               detail=t("set.connection_hint"), data="connection"),
            "auto_connect": Item(t("set.auto_connect"),
                                 value=on if self.get("auto_connect", True) else off,
                                 detail=t("set.auto_connect_hint"), data="auto_connect"),
            "boxes": Item(t("set.boxes"), value=f"{boxes_mod.N_BOXES}",
                          detail=t("set.boxes_hint"), action=lambda: a.push(BoxesScreen(a))),
            "metrics": Item(t("set.metrics"),
                            value=f"{len(boxes_mod.enabled_metrics(a.db, metrics.available()))}",
                            detail=t("set.metrics_hint"),
                            action=lambda: a.push(MetricsCatalogScreen(a))),
            "strava": Item("Strava", value=tr("ligado", "connected") if (
                a.db.get("strava_tokens") or {}).get("refresh_token") else "",
                detail=tr("Enter abre · segmentos das rotas e os teus PR",
                          "Enter opens · route segments and your PRs"),
                action=lambda: a.push(_connect().StravaScreen(a))),
            "@garmin_head": Item(tr("— GarminDB (Garmin Connect) —",
                                    "— GarminDB (Garmin Connect) —"), enabled=False,
                                 detail=tr("a autenticação; o resto está em Backups e Sincronização",
                                           "the sign-in; the rest is in Sync")),
            "garmin_user": Item(tr("Utilizador do Garmin Connect", "Garmin Connect user"),
                                value=(user if user is not None else user0) + "▏",
                                detail=tr("o email da tua conta Garmin", "your Garmin account email"),
                                data="text:garmin_user"),
            "garmin_password": Item(tr("Palavra-passe do Garmin Connect", "Garmin Connect password"),
                                    value=("•" * len(pw) if pw is not None else
                                           (tr("(definida)", "(set)") if has_pw else "")) + "▏",
                                    detail=tr("fica só na configuração do GarminDB, nunca na base "
                                              "da Perennia", "kept only in the GarminDB config, "
                                              "never in the Perennia database"),
                                    data="text:garmin_password"),
            "garmin_cfg": Item(tr("Configuração do GarminDB", "GarminDB config"),
                               value=str(gsync.config_path(a.db)), enabled=False,
                               detail=tr("criada ao guardar, se ainda não existir (com cópia .bak)",
                                         "created on save if missing (with a .bak copy)")),
            "run_pace": Item(tr("Ritmo de limiar (corrida)", "Threshold pace (running)"),
                             value=hms(float(self.get("run_threshold_pace_s", 300))) + " /km",
                             detail=tr("o ritmo que aguentas ~1 h (entre 10 km e meia maratona); "
                                       "base das zonas e do rTSS · ←/→ ±5 s",
                                       "the pace you hold for ~1 h (between 10 km and half "
                                       "marathon); basis of zones and rTSS · ←/→ ±5 s"),
                             data="run_pace"),
            "swim_pace": Item(tr("Ritmo crítico (natação)", "Critical swim speed"),
                              value=hms(float(self.get("swim_css_s", 120))) + " /100 m",
                              detail=tr("CSS: o ritmo /100 m que aguentas sem parar (teste "
                                        "400 + 200 m); base das zonas e do sTSS · ←/→ ±1 s",
                                        "CSS: the /100 m pace you can sustain (400 + 200 m "
                                        "test); basis of zones and sTSS · ←/→ ±1 s"),
                              data="swim_pace"),
            "theme": Item(tr("Tema", "Theme"), value=_theme_name_of(self.get("theme", None)),
                          detail=tr("←/→ vê-se logo · Guardar fixa-o · Ardósia para pouca luz",
                                    "←/→ shows it now · Save keeps it · Slate for low light"),
                          data="theme"),
            "layouts": Item(tr("Ecrã da sessão, por desporto", "Session screen, per sport"),
                            detail=tr("Enter abre · um separador por desporto; arrasta as métricas",
                                      "Enter opens · one tab per sport; drag the metrics"),
                            action=lambda: a.push(_layouts().LayoutEditor(a, "cycling"))),
            "lv_n": Item(tr("Rolo sem ERG: número de níveis", "Non-ERG trainer: number of levels"),
                         value=str(self._levels()["n"]),
                         detail=tr("←/→ · para os treinos manuais «por níveis do rolo»",
                                   "←/→ · for manual workouts \u00abby trainer levels\u00bb"),
                         data="lv_n"),
            "lv_min": Item(tr("Rolo sem ERG: watts no nível 1", "Non-ERG trainer: watts at level 1"),
                           value=f"{self._levels()['w_min']:.0f} W",
                           detail=tr("←/→ ±5 W · Shift ±50 · a 90 rpm", "←/→ ±5 W · Shift ±50 · at 90 rpm"),
                           data="lv_min"),
            "lv_max": Item(tr("Rolo sem ERG: watts no nível máximo",
                              "Non-ERG trainer: watts at the top level"),
                           value=f"{self._levels()['w_max']:.0f} W",
                           detail=tr("←/→ ±5 W · Shift ±50 · entre eles, em linha reta",
                                     "←/→ ±5 W · Shift ±50 · linear in between"), data="lv_max"),
            "arrangement": Item(tr("Disposição do ecrã da sessão", "Session screen layout"),
                                detail=tr("Enter abre · arrasta caixas, voltas, gráficos e tabelas",
                                          "Enter opens · drag boxes, laps, charts and tables"),
                                action=lambda: a.push(_arrangement().ArrangementEditor(
                                    a, "cycling"))),
            "feedback": Item(tr("Feedback no fim de cada sessão", "Feedback after each session"),
                             value=on if self.get("ask_feedback", True) else off,
                             detail=tr("RPE, dores e comentário; fica para o agente treinador",
                                       "RPE, pain and comment; kept for the coach agent"),
                             data="feedback"),
        }

    def buttons(self) -> list[Item]:
        return [Item(tr("Cancelar", "Cancel"), action=self.cancel, button=True,
                     enabled=self.dirty),
                Item(tr("Guardar", "Save"), action=self.save, button=True, primary=True,
                     enabled=self.dirty)]

    def enter(self) -> None:
        if self.tabs is not None:
            self.tabs.set_labels(self.tab_labels())
            self.tabs.select(self.tab)
        group = self.group()
        foot = tr("←/→ mudar · Enter abrir · Tab separador · Ctrl+S guardar · Esc voltar",
                  "←/→ change · Enter open · Tab tab · Ctrl+S save · Esc back")
        h = self.app.window.height
        self.list.y = self.content_top(h)
        if group == ("@sports",):
            self.sport_tabs.select(self.sport_tab)
            self.section_tabs.set_labels(self.section_labels())
            self.section_tabs.select(self.section_tab)
            self.list.y = self.content_top(h) - 96          # por baixo das duas filas
            items = self.sports_items()
            foot = tr("PgUp/PgDn desporto · Ctrl+←/→ secção · Enter/←/→ muda · Ctrl+S guardar",
                      "PgUp/PgDn sport · Ctrl+←/→ section · Enter/←/→ changes · Ctrl+S save")
        elif group == ("@shortcuts",):
            items = self.shortcut_items()
        elif group == ("@sounds",):
            from velo.ui import sound_screens
            items = sound_screens.sound_items(self)
            foot = tr("←/→ muda · Enter edita · Del apaga a regra · Ctrl+S guardar",
                      "←/→ changes · Enter edits · Del deletes the rule · Ctrl+S save")
        else:
            rows = self._rows()
            items = [rows[k] for k in group]
        sub = tr("Por guardar: carrega em Guardar (Ctrl+S) ou em Cancelar",
                 "Unsaved: press Save (Ctrl+S) or Cancel") if self.dirty else \
            tr("Tab muda de separador", "Tab switches tabs")
        if self.capturing:
            from velo.ui import keymap
            sub = tr("Carrega na nova tecla para «{a}» · Esc cancela",
                     "Press the new key for «{a}» · Esc cancels", a=keymap.label(self.capturing))
        self.chrome.set(t("menu.settings"), sub, foot)
        self.list.set_items(items + self.buttons(), keep_index=True)

    # ----------------------------------------------------------- desportos

    def sports_items(self) -> list[Item]:
        a = self.app
        sport = self.sport
        sec = self.sections()[self.section_tab % len(self.sections())]
        from velo.core import layouts as lay
        from velo.core import workout_meta as wm
        on, off = t("common.on"), t("common.off")
        rows: list[Item] = []
        if sec == "metrics":
            k = wm.metrics_key(sport)
            disabled = set(self.get(k, []) or [])
            cat = lay.catalog(sport)
            rows.append(Item(tr("Métricas de sessão de {s}", "{s} session metrics",
                                s=sport_name(sport)), header=True))
            for mid, name in cat:
                rows.append(Item(name, value=off if mid in disabled else on,
                                 detail=tr("Enter ou ←/→ liga/desliga · as desligadas não "
                                           "aparecem no editor do ecrã",
                                           "Enter or ←/→ turns on/off · off ones don't show "
                                           "in the screen editor"),
                                 action=lambda m=mid: self._toggle_metric(m),
                                 data=f"metric:{mid}"))
        elif sec == "layout":
            groups = self._layout_groups(sport)
            shown = [lay.label(sport, x) for g in groups for x in g if x]
            rows += [Item(tr("Escolher as métricas do ecrã", "Choose the screen's metrics"),
                          detail=(", ".join(shown[:6]) + ("…" if len(shown) > 6 else ""))
                          or tr("Enter abre e arrasta as métricas", "Enter opens; drag metrics"),
                          action=lambda: self._open_layout_editor(sport)),
                     Item(tr("Disposição dos painéis", "Panel layout"),
                          detail=tr("Enter abre · arrasta caixas, voltas, gráficos e tabelas",
                                    "Enter opens · drag boxes, laps, charts and tables"),
                          action=lambda: a.push(_arrangement().ArrangementEditor(a, sport)))]
        else:
            lim = self._limits()
            if sport == "cycling":
                rows.append(Item(tr("Níveis de resistência do rolo", "Trainer resistance levels"),
                                 value=str(lim["trainer_levels"]),
                                 detail=tr("os níveis do teu rolo sem controlo; o construtor não "
                                           "passa deste número · ←/→ ±1",
                                           "your non-smart trainer's levels; the builder "
                                           "won't go past this number · ←/→ ±1"),
                                 data="lim:trainer_levels"))
            elif sport == "rowing":
                rows.append(Item(tr("Níveis de resistência do remo", "Rower resistance levels"),
                                 value=str(lim["rower_levels"]),
                                 detail=tr("a resistência máxima da máquina; o construtor não "
                                           "passa deste número · ←/→ ±1",
                                           "the machine's top resistance; the builder won't "
                                           "go past it · ←/→ ±1"),
                                 data="lim:rower_levels"))
            elif sport == "running":
                rows += [Item(tr("Velocidade máxima da passadeira", "Treadmill top speed"),
                              value=f"{lim['treadmill_max_kmh']:.1f} km/h",
                              detail=tr("o construtor e a sessão não passam desta velocidade · "
                                        "←/→ ±0,5", "the builder and the session won't go "
                                        "past it · ←/→ ±0.5"),
                              data="lim:treadmill_max_kmh"),
                         Item(tr("Inclinação máxima da passadeira", "Treadmill top incline"),
                              value=f"{lim['treadmill_max_incline']:.1f} %",
                              detail=tr("←/→ ±0,5 %", "←/→ ±0.5 %"),
                              data="lim:treadmill_max_incline"),
                         Item(tr("Passo da inclinação", "Incline step"),
                              value=f"{lim['treadmill_incline_step']:g} %",
                              detail=tr("de quanto em quanto a tua passadeira sobe: o "
                                        "construtor e o GPX Conversor arredondam a isto · "
                                        "←/→ 0,1 · 0,5 · 1",
                                        "how much your treadmill's incline moves at a time: "
                                        "the builder and the GPX converter round to it · "
                                        "←/→ 0.1 · 0.5 · 1"),
                              data="lim:treadmill_incline_step")]
            else:
                rows.append(Item(tr("Sem aparelho a configurar", "No device to set up"),
                                 detail=tr("a natação e o ginásio não usam aparelhos com níveis",
                                           "swimming and gym don't use devices with levels"),
                                 enabled=False))
        return rows

    def _layout_groups(self, sport: str) -> list:
        """O ecrã do desporto (com o rascunho, se o houver)."""
        from velo.core import layouts as lay
        k = lay.settings_key(sport)
        return lay.decode(sport, self.get(k, None))

    def _max_metrics(self, sport: str) -> int:
        from velo.core import layouts as lay
        from velo.core import workout_meta as wm
        off = set(self.get(wm.metrics_key(sport), []) or [])
        return lay.max_count(sport, [k for k, _ in lay.catalog(sport) if k not in off])

    def _adjust_count(self, sport: str, step: int) -> None:
        from velo.core import layouts as lay
        from velo.core import workout_meta as wm
        off = set(self.get(wm.metrics_key(sport), []) or [])
        avail = [k for k, _ in lay.catalog(sport) if k not in off]
        groups = self._layout_groups(sport)
        before = lay.count(groups)
        new = lay.resized(groups, sport, before + (1 if step > 0 else -1), avail)
        if lay.count(new) == before:
            return
        k = lay.settings_key(sport)
        self.put(k, lay.encode(sport, new, self.get(k, None)))
        self.enter()

    def _open_layout_editor(self, sport: str) -> None:
        """O editor grava ele próprio: as alterações às Definições vão primeiro."""
        from velo.core import layouts as lay
        if lay.settings_key(sport) in self.draft:
            self.save()
        self.app.push(_layouts().LayoutEditor(self.app, sport))

    def _limits(self) -> dict:
        from velo.core import workout_meta as wm
        lim = wm.device_limits(self.app.db)
        for k in wm.DEVICE_DEFAULTS:
            if k in self.draft:
                lim[k] = self.draft[k]
        lv = self.get("trainer_levels", None)
        if isinstance(lv, dict) and "n" in lv:
            lim["trainer_levels"] = int(lv["n"])
        return lim

    def _toggle_metric(self, mid: str) -> None:
        from velo.core import workout_meta as wm
        k = wm.metrics_key(self.sport)
        cur = set(self.get(k, []) or [])
        cur ^= {mid}
        self.put(k, sorted(cur))
        self.enter()

    def _adjust_limit(self, name: str, step: int) -> None:
        lim = self._limits()
        unit = 1 if step > 0 else -1
        if name == "trainer_levels":
            from velo.core import workout_meta as wm
            lv = dict(self._levels())
            lv["n"] = max(2, min(30, int(lv["n"]) + unit))
            self.put("trainer_levels", lv)
            if self._orig.get("trainer_levels") is None and lv == wm.levels(self.app.db):
                self.draft.pop("trainer_levels", None)      # voltou ao que estava
        elif name == "rower_levels":
            self.put("rower_levels", max(1, min(30, int(lim["rower_levels"]) + unit)))
        elif name == "treadmill_max_kmh":
            self.put("treadmill_max_kmh", max(8.0, min(30.0, lim["treadmill_max_kmh"]
                                                       + 0.5 * unit)))
        elif name == "treadmill_max_incline":
            self.put("treadmill_max_incline", max(0.0, min(40.0, lim["treadmill_max_incline"]
                                                           + 0.5 * unit)))
        elif name == "treadmill_incline_step":
            from velo.core import workout_meta as wm
            order = list(wm.INCLINE_STEPS)
            cur = order.index(lim["treadmill_incline_step"]) \
                if lim["treadmill_incline_step"] in order else 1
            self.put("treadmill_incline_step", order[(cur + unit) % len(order)])
        self.enter()

    # ------------------------------------------------------------ atalhos

    capturing: str | None = None          # a ação à espera da tecla nova

    def shortcut_items(self) -> list[Item]:
        from velo.ui import keymap
        raw = self.get("keymap", {}) or {}
        rows: list[Item] = []
        for scope, pt, en in keymap.SCOPES:
            rows.append(Item(tr(pt, en), header=True))
            for act in keymap.actions_in(scope):
                b = keymap.binding(raw, act)
                changed = b != keymap.default(act)
                rows.append(Item(keymap.label(act), value=keymap.key_text(b),
                                 detail=(tr("era {k} · ", "was {k} · ",
                                            k=keymap.key_text(keymap.default(act)))
                                         if changed else "") + tr("Enter muda a tecla",
                                                                  "Enter changes the key"),
                                 action=lambda a=act: self._start_capture(a), data=f"key:{act}"))
        rows.append(Item(tr("Navegação (fixas)", "Navigation (fixed)"), header=True))
        for k, pt, en in keymap.FIXED:
            rows.append(Item(tr(pt, en), value=k, enabled=False))
        if keymap.custom_map(raw):
            rows.append(Item(tr("Repor as teclas de origem", "Restore the original keys"),
                             button=True, action=self._reset_keys))
        return rows

    def _start_capture(self, action: str) -> None:
        self.capturing = action
        self.enter()

    def capture_key(self, symbol: int, modifiers: int) -> bool:
        from velo.ui import keymap
        act = self.capturing
        if symbol == key.ESCAPE:
            self.capturing = None
            self.enter()
            return True
        name = keymap.name_of(symbol)
        if name is None:
            self.app.message(tr("Essa tecla é de navegação: escolhe uma letra, F1–F12 ou o "
                                "Espaço.", "That key is for navigation: pick a letter, F1–F12 "
                                "or Space."))
            return True
        b = (name, keymap.mods_of(modifiers))
        raw = dict(keymap.custom_map(self.get("keymap", {}) or {}))
        why = keymap.problem(raw, act, b)
        if why is not None:
            self.app.message(why)
            return True
        if b == keymap.default(act):
            raw.pop(act, None)
        else:
            raw[act] = [b[0], list(b[1])]
        self.put("keymap", raw)
        if self._orig.get("keymap") in (None, {}) and not raw:
            self.draft.pop("keymap", None)       # voltou tudo à origem
        self.capturing = None
        self.enter()
        return True

    def _reset_keys(self) -> None:
        self.put("keymap", {})
        if self._orig.get("keymap") in (None, {}):
            self.draft.pop("keymap", None)
        self.enter()

    def draw(self) -> None:
        super().draw()
        if self.group() == ("@sports",):
            self.sport_tabs.draw()
            self.section_tabs.draw()

    def on_mouse(self, x: int, y: int) -> bool:
        if self.group() == ("@sports",):
            i = self.sport_tabs.hit(x, y)
            if i is not None:
                self.set_sport(i)
                return True
            i = self.section_tabs.hit(x, y)
            if i is not None:
                self.set_section(i)
                return True
        return super().on_mouse(x, y)

    def set_sport(self, i: int) -> None:
        self.sport_tab = i % len(self.SPORTS)
        self.section_tab = min(self.section_tab, len(self.sections()) - 1)
        self.list.index = 0
        self.enter()

    def set_section(self, i: int) -> None:
        self.section_tab = i % len(self.sections())
        self.list.index = 0
        self.enter()

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self.sport_tabs.layout(48, self.content_top(h) + 6, w - 96)
        self.section_tabs.layout(48, self.content_top(h) - 38, w - 96)
        self.enter()

    # -------------------------------------------------------------- texto

    def text_input(self, field: str, text: str) -> None:
        if field == "name":
            self.ath.name = ((self.ath.name or "") + text)[:40]
        elif field == "garmin_user":
            from velo.core import garmin_sync as gsync
            cur = self.get("@garmin_user", None)
            if cur is None:
                cur = gsync.credentials(gsync.config_path(self.app.db))[0]
            self.put("@garmin_user", (cur + text)[:120])
        elif field == "garmin_password":
            self.put("@garmin_password", ((self.get("@garmin_password", None) or "") + text)[:120])
        else:
            return
        self.enter()

    def text_backspace(self, field: str) -> None:
        if field == "name":
            self.ath.name = (self.ath.name or "")[:-1]
        elif field == "garmin_user":
            from velo.core import garmin_sync as gsync
            cur = self.get("@garmin_user", None)
            if cur is None:
                cur = gsync.credentials(gsync.config_path(self.app.db))[0]
            self.put("@garmin_user", cur[:-1])
        elif field == "garmin_password":
            cur = self.get("@garmin_password", None) or ""
            if cur[:-1]:
                self.put("@garmin_password", cur[:-1])
            else:
                self.draft.pop("@garmin_password", None)
        else:
            return
        self.enter()

    # -------------------------------------------------------------- setas

    # as linhas de escolha: Enter abre a lista com pesquisa (ou troca, se forem 2)
    CHOICE_ROWS = ("units", "language", "render", "connection", "msaa", "display",
                   "auto_pause", "auto_connect", "pmc_synced")

    def _enter_row(self, item) -> bool:
        d = item.data
        if d == "theme":
            from velo.gfx import theme as theme_mod
            from velo.ui.pickers import ChoicePopup
            keys = list(theme_mod.names())
            cur = self.get("theme", None) or theme_mod.DEFAULT

            def pick_theme(k: int) -> None:
                self.put("theme", keys[k])
                self._preview_theme()
            self.app.push(ChoicePopup(self.app, item.label, [theme_mod.name(k) for k in keys],
                                      keys.index(cur) if cur in keys else 0, pick_theme))
            return True
        from velo.ui.pickers import open_choices
        if d in self.CHOICE_ROWS:
            return open_choices(self, item, lambda s=1, f=d: self._adjust(f, s))
        return False

    def update(self, dt: float) -> None:
        if getattr(self, "_sound_test", None):
            from velo.ui import sound_screens
            sound_screens.tick_test(self, dt)

    def on_key(self, symbol: int, modifiers: int) -> bool:
        item = self.list.selected
        if self.group() == ("@sounds",) and symbol in (key.DELETE, key.BACKSPACE) and \
                item is not None and str(item.data or "").startswith("rule:"):
            from velo.ui import sound_screens
            sound_screens.delete_rule(self, str(item.data)[5:])
            return True
        if self.group() == ("@sports",):
            if symbol in (key.PAGEUP, key.PAGEDOWN):
                self.set_sport(self.sport_tab + (1 if symbol == key.PAGEDOWN else -1))
                return True
            if symbol in (key.LEFT, key.RIGHT) and modifiers & key.MOD_CTRL:
                self.set_section(self.section_tab + (1 if symbol == key.RIGHT else -1))
                return True
            d = str(item.data) if item is not None and item.data else ""
            if d.startswith("metric:") and symbol in (key.LEFT, key.RIGHT):
                self._toggle_metric(d[7:])
                return True
            if d.startswith("lim:") and symbol in (key.LEFT, key.RIGHT):
                self._adjust_limit(d[4:], 1 if symbol == key.RIGHT else -1)
                return True
            if d.startswith("count:") and symbol in (key.LEFT, key.RIGHT):
                self._adjust_count(d[6:], 1 if symbol == key.RIGHT else -1)
                return True
        if item is not None and symbol in (key.ENTER, key.RETURN) and item.action is None \
                and isinstance(item.data, str) and self._enter_row(item):
            return True
        if item is not None and item.data and symbol in (key.LEFT, key.RIGHT) and \
                not str(item.data).startswith("text:"):
            step = 1 if symbol == key.RIGHT else -1
            if modifiers & key.MOD_SHIFT:
                step *= 10
            self._adjust(str(item.data), step)
            return True
        return super().on_key(symbol, modifiers)

    def _levels(self) -> dict:
        from velo.core import workout_meta as wm
        cur = self.get("trainer_levels", None)
        base = wm.levels(self.app.db)
        if isinstance(cur, dict):
            base.update(cur)
        return base

    def _cycle(self, key_: str, options: list, step: int, default) -> None:
        cur = self.get(key_, default)
        i = options.index(cur) if cur in options else 0
        self.put(key_, options[(i + (1 if step > 0 else -1)) % len(options)])

    def _adjust(self, field: str, step: int) -> None:
        a = self.app
        unit = 1 if step > 0 else -1
        ath = self.ath
        if field == "theme":
            from velo.gfx import theme as theme_mod
            self._cycle("theme", list(theme_mod.names()), step, theme_mod.DEFAULT)
            self._preview_theme()               # vê-se logo; grava-se com Guardar
            return
        elif field == "run_pace":
            self.put("run_threshold_pace_s", max(150, min(600, float(
                self.get("run_threshold_pace_s", 300)) + 5 * unit)))
        elif field == "swim_pace":
            self.put("swim_css_s", max(50, min(300, float(self.get("swim_css_s", 120)) + unit)))
        elif field == "row_ftp":
            from velo.core import rowing as rw
            self.put("row_ftp_w", max(50, min(800, int(self.get("row_ftp_w", rw.row_ftp(a.db)))
                                         + step)))
        elif field in ("lv_n", "lv_min", "lv_max"):
            lv = dict(self._levels())
            if field == "lv_n":
                lv["n"] = max(2, min(30, int(lv["n"]) + unit))
            elif field == "lv_min":
                lv["w_min"] = max(20.0, min(lv["w_max"] - 10, lv["w_min"] + step * 5))
            else:
                lv["w_max"] = max(lv["w_min"] + 10, min(2000.0, lv["w_max"] + step * 5))
            self.put("trainer_levels", lv)
            from velo.core import workout_meta as wm
            if self._orig.get("trainer_levels") is None and lv == wm.levels(a.db):
                self.draft.pop("trainer_levels", None)      # voltou ao que estava
        elif field == "pmc_synced":
            self.put("pmc_synced", not self.get("pmc_synced", True))
        elif field == "sound_on":
            self.put("sound_on", not self.get("sound_on", True))
        elif field == "sound_end":
            self.put("sound_end", not self.get("sound_end", True))
        elif field == "lookahead":
            self.put("workout_lookahead", max(0, min(4, int(self.get("workout_lookahead", 2))
                                                    + unit)))
        elif field == "age":
            ath.birth_year = (ath.birth_year or 1990) - unit
        elif field == "weight":
            # passo de 0,1 na unidade mostrada (kg ou lb); Shift dá passos de 1
            unit_kg = 1.0 if self.get("units", a.units) == "metric" else 0.45359237
            shown = round(ath.weight_kg / unit_kg, 1) + step * 0.1
            ath.weight_kg = max(35.0, min(200.0, round(shown, 1) * unit_kg))
        elif field == "ftp":
            ath.ftp_w = max(60, min(600, ath.ftp_w + unit * 5))
        elif field == "lthr":
            ath.lthr = max(100, min(220, (ath.lthr or 160) + unit))
        elif field == "difficulty":
            value = max(0.0, min(1.5, float(self.get("trainer_difficulty", 1.0)) + unit * 0.05))
            self.put("trainer_difficulty", round(value, 2))
        elif field == "units":
            self._cycle("units", ["metric", "imperial"], step, a.units)
        elif field == "language":
            self._cycle("language", [PT, EN], step, PT)
        elif field == "render":
            self._cycle("render_preset", list(PRESET_ORDER), step, "low")
        elif field == "msaa":
            self._cycle("msaa_samples", [4, 2, 0], step, 4)
        elif field == "auto_pause":
            self.put("auto_pause", not self.get("auto_pause", True))
        elif field == "auto_connect":
            self.put("auto_connect", not self.get("auto_connect", True))
        elif field == "feedback":
            self.put("ask_feedback", not self.get("ask_feedback", True))
        elif field == "connection":
            self._cycle("connection_preference", list(autoconnect.PREFERENCES), step,
                        autoconnect.ANT_FIRST)
        elif field == "display":
            opts = a.display_options()
            cur = self._display_now()
            key_ = (True, 0, 0) if cur["fullscreen"] else (False, cur["w"], cur["h"])
            keys = [(o[0], 0, 0) if o[0] else o for o in opts]
            i = keys.index(key_) if key_ in keys else (len(keys) - 1 if cur["fullscreen"] else -1)
            nxt = opts[(i + unit) % len(opts)]
            new = {"fullscreen": nxt[0], "w": nxt[1] or None, "h": nxt[2] or None}
            now = {"fullscreen": bool(a.window.fullscreen), "w": a.window.width,
                   "h": a.window.height}
            if new["fullscreen"] == now["fullscreen"] and (new["fullscreen"] or
                                                           (new["w"], new["h"]) ==
                                                           (now["w"], now["h"])):
                self.draft.pop("display", None)
            else:
                self.draft["display"] = new
        else:
            return
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
    """Liga e desliga métricas. As desligadas não aparecem no editor das caixas.

    Não é uma lista: as métricas espalham-se pelo ecrã todo, em cartões
    (setas mudam de cartão, Enter ou um clique liga/desliga)."""

    def __init__(self, app: "App"):
        super().__init__(app)
        from velo.ui.widgets import GridView
        self.grid = GridView()
        self._layout_grid()

    def _layout_grid(self) -> None:
        w, h = self.app.window.width, self.app.window.height
        self.grid.layout(48, self.content_top(h) + 24, w - 96, 96)
        self.list.y = -3000                  # a lista serve o teclado; vê-se a grelha

    def enter(self) -> None:
        a = self.app
        on = set(boxes_mod.enabled_metrics(a.db, metrics.available()))
        items, cells = [], []
        for mid in metrics.available():
            m = metrics.REGISTRY[mid]
            items.append(Item(("✓ " if mid in on else "   ") + m.label,
                              value=t("common.on") if mid in on else t("common.off"),
                              action=lambda x=mid: self._toggle(x), data=mid))
            cells.append((m.label, t("common.on") if mid in on else t("common.off"),
                          mid in on, True))
        self.chrome.set(t("set.metrics"), f"{len(on)}/{len(items)} · " + tr(
            "Enter ou clique liga/desliga", "Enter or click turns on/off"),
            tr("setas mudar · Enter ligar/desligar · Esc voltar",
               "arrows move · Enter on/off · Esc back"))
        self.list.set_items(items, keep_index=True)
        self.grid.set(cells, self.list.index)

    def _toggle(self, mid: str) -> None:
        on = mid in boxes_mod.enabled_metrics(self.app.db, metrics.available())
        boxes_mod.set_enabled(self.app.db, mid, not on)
        self.enter()

    def on_key(self, symbol: int, modifiers: int) -> bool:
        moves = {key.LEFT: -1, key.RIGHT: 1, key.UP: -self.grid.cols,
                 key.DOWN: self.grid.cols}
        if symbol in moves and self.list.items:
            self.list.index = max(0, min(len(self.list.items) - 1,
                                         self.list.index + moves[symbol]))
            self.list._sync()
            self.enter()
            return True
        return super().on_key(symbol, modifiers)

    def on_mouse(self, x: int, y: int) -> bool:
        k = self.grid.hit(x, y)
        if k is not None:
            self.list.index = k
            self.list.activate()
            return True
        return super().on_mouse(x, y)

    def on_resize(self, w: int, h: int) -> None:
        super().on_resize(w, h)
        self._layout_grid()
        self.enter()

    def draw(self) -> None:
        super().draw()
        self.grid.draw()


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

    def _already_there(self, wk) -> bool:
        """O mesmo treino (nome e passos iguais) já foi importado?"""
        want = [(s.kind, int(s.duration_s), s.target_lo, s.target_hi) for s in wk.steps]
        for w in self.app.db.workouts():
            if w["name"] != wk.name:
                continue
            have = [(r["kind"], int(r["duration_s"] or 0), r["target_lo"], r["target_hi"])
                    for r in self.app.db.workout_steps(w["id"])]
            if have == want:
                return True
        return False

    def _import(self, path: Path) -> None:
        a = self.app
        try:
            wk = workouts.import_workout(path)
            if self._already_there(wk):
                a.message(tr("«{n}» já está na lista de treinos (não o importei outra vez)",
                             "«{n}» is already in the workout list (not imported again)",
                             n=wk.name))
                return
            a.db.insert_workout(wk.name, [s.as_dict() for s in wk.steps],
                                wk.source_format, wk.description,
                                wk.estimated_tss(a.db.athlete().ftp_w))
            a.message(f"«{wk.name}» importado — {len(wk.steps)} passos")
            self.enter()
        except Exception as e:
            a.message(f"{t('common.error')}: {e}")


def WorkoutRouteChoice(app: "App", workout_id: str):            # noqa: N802
    """«Configurar sessão de treino»: a janela da sessão, com a rota opcional."""
    return _setup().SessionSetup(app, "cycling", kind="workout", workout_id=workout_id)


def FtpRouteChoice(app: "App", protocol: str):                  # noqa: N802
    """Um teste de FTP: a janela da sessão (rota opcional)."""
    return _setup().SessionSetup(app, "cycling", kind="ftp_test", ftp_protocol=protocol,
                                 title=t(ftp_mod.CATALOG[protocol].label_key))


# ---------------------------------------------------------------- desafios


class ChallengeScreen(Screen):
    """Os desafios de um desporto: objetivo acumulado e, se tiver, quanto tempo
    falta para a data limite. **Adicionar desafio** (em baixo, à direita)
    abre a janela de edição; Enter num desafio abre-o."""

    HAS_BOARD = True

    def __init__(self, app: "App", sport: str = "cycling"):
        super().__init__(app)
        self.sport = sport

    def side_board(self):
        a = self.app
        item = self.list.selected
        if item is not None and isinstance(item.data, int):
            ch = next((c for c in a.db.challenges(self.sport) if c["id"] == item.data), None)
            if ch is not None:
                return boards.challenge_board(a.db, ch, a.units)
        rows = []
        for ch in a.db.challenges(self.sport):
            att = _sport_ch().refresh(a.db, ch)
            pct = min(100.0, att["progress"] / max(ch["target"], 1e-9) * 100.0)
            rows.append(boards.Row(None, f"{pct:.0f} %", ch["name"]))
        return boards.Board(t("menu.challenges"), rows, t("board.progress"),
                            empty=t("board.empty"))

    def enter(self) -> None:
        a = self.app
        sc = _sport_ch()
        items = []
        for ch in a.db.challenges(self.sport):
            attempt = sc.refresh(a.db, ch)
            target, progress = ch["target"], attempt["progress"]
            done_txt = boards.challenge_progress_text(
                ch["metric"], progress, target, ch["display_unit"], a.units)
            pct = min(100.0, progress / max(target, 1e-9) * 100.0)
            board = a.db.challenge_leaderboard(ch["id"], limit=1)
            best = (t("ch.completed_in", time=boards.long_duration(board[0]["elapsed_s"]))
                    if board else t("ch.in_progress"))
            left = sc.remaining_text(ch)
            items.append(Item(ch["name"], value=f"{pct:.0f} %",
                              detail=" · ".join(x for x in (done_txt, left or best) if x),
                              action=lambda c=ch: a.push(ChallengeDetail(a, dict(c))),
                              data=ch["id"]))
        if not items:
            items = [Item(tr("Ainda sem desafios", "No challenges yet"), enabled=False)]
        items.append(Item(tr("Adicionar desafio", "Add challenge"), button=True, primary=True,
                          action=lambda: a.push(_challenge_popup(a, self.sport))))
        from velo.core import sports as sp
        self.chrome.set(t("menu.challenges") + f" · {sp.name(self.sport)}",
                        tr("Objetivos acumulados, com ou sem data limite",
                           "Cumulative goals, with or without a deadline"), self.footer())
        self.list.set_items(items, keep_index=True)


def ChallengeCreate(app: "App", sport: str = "cycling"):          # noqa: N802 — compatibilidade
    """O novo desafio abre numa janela (`challenge_screens.ChallengePopup`)."""
    return _challenge_popup(app, sport)


def _challenge_popup(app: "App", sport: str, challenge: dict | None = None):
    from velo.ui.challenge_screens import ChallengePopup
    return ChallengePopup(app, sport, challenge)


class ChallengeDetail(Screen):
    """Um desafio: data limite, a tabela das vezes que o cumpriste. Em baixo,
    à direita: Recomeçar · Apagar · Editar (abre a janela de edição)."""

    HAS_BOARD = True

    def __init__(self, app: "App", challenge: dict):
        super().__init__(app)
        self.challenge = challenge
        self._armed = False

    def side_board(self):
        return boards.challenge_board(self.app.db, self.challenge, self.app.units)

    def enter(self) -> None:
        a = self.app
        row = next((c for c in a.db.challenges("*") if c["id"] == self.challenge["id"]), None)
        if row is None:
            a.pop()
            return
        ch = self.challenge = dict(row)
        sc = _sport_ch()
        attempt = sc.refresh(a.db, ch)
        items = []
        left = sc.remaining_text(ch)
        if left:
            items.append(Item(tr("Data limite", "Deadline"),
                              value=sc.deadline_of(ch).strftime("%d/%m/%Y"), detail=left,
                              enabled=False))
        board = a.db.challenge_leaderboard(ch["id"])
        if board:
            items.append(Item(t("ch.leaderboard"), header=True))
            for i, r in enumerate(board, start=1):
                items.append(Item(f"{i}.  {boards.long_duration(r['elapsed_s'])}",
                                  detail=f"{r['started_at'][:10]} → "
                                         f"{(r['completed_at'] or '')[:10]}",
                                  enabled=False))
        else:
            items.append(Item(t("stats.no_data"), enabled=False))
        items.append(Item(t("ch.reset"), action=self._reset, button=True))
        if not ch["is_default"]:
            items.append(Item(t("ch.delete"), action=self._delete, button=True))
        items.append(Item(tr("Editar", "Edit"), button=True, primary=True,
                          action=lambda: a.push(_challenge_popup(
                              a, ch.get("sport") or "cycling", ch))))
        progress = boards.challenge_progress_text(
            ch["metric"], attempt["progress"], ch["target"], ch.get("display_unit"),
            a.units)
        self.chrome.set(ch["name"], progress + (f" · {left}" if left else ""), self.footer())
        self.list.set_items(items, keep_index=True)

    def _reset(self) -> None:
        self.app.db.reset_attempt(self.challenge["id"])
        self.app.message(t("ch.reset"))
        self.enter()

    def _delete(self) -> None:
        def gone() -> None:
            self.app.db.delete_challenge(self.challenge["id"])
            self.app.pop()
        self.app.confirm(tr("Apagar o desafio «{n}»?", "Delete the challenge «{n}»?",
                            n=self.challenge.get("name", "")), tr("Tens a certeza? Não dá para desfazer.", "Are you sure? This cannot be undone."), gone,
                         yes=tr("Apagar", "Delete"))


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


def ChaseRouteChoice(app: "App", level: str):                   # noqa: N802
    """A fuga: a janela da sessão (sem rota, é tudo plano)."""
    return _setup().SessionSetup(app, "cycling", kind="chase", chase_level=level)


# -------------------------------------------------------------- estatísticas


class StatsScreen(Screen):
    """Explorador de estatísticas.

    Quatro linhas de controlo em cima — gráfico, métrica (ou ponto, ou
    tabela), agrupar por, intervalo — que se mudam com ←/→. Por
    baixo, o resumo do período com o percentil em que estás, e o gráfico.

    A curva de potência é sempre do histórico todo; o resto segue o período
    escolhido (dias, semanas, meses, trimestres, semestres ou anos).
    """

    TABBED = True                  # os gráficos por separadores
    VIEW_KEY = "stats.view."
    STATS_SPORT = "cycling"        # o desporto escolhido na linha «Desporto»
    VIEWS = ("general", "power_curve", "evolution", "zones", "zones_period", "load", "eftp",
             "profile", "peaks", "cadence", "balance", "decoupling")
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
        names = {"general": tr("Geral", "Overview"), "peaks": tr("Picos", "Peaks")}
        return [names.get(v) or t(f"{self.VIEW_KEY}{v}") for v in self.VIEWS]

    def on_tab(self) -> None:
        self.view = self.tab % len(self.VIEWS)
        self.point = None

    def sport_row(self) -> Item:
        from velo.core import sports as sp
        name = sp.name(self.STATS_SPORT) if self.STATS_SPORT else tr("Todos", "All")
        if self.hub is not None:
            # entrou-se pelo desporto: fica fixo (muda-se nas Estatísticas gerais)
            return Item(tr("Desporto", "Sport"), value=name, enabled=False,
                        detail=tr("fixo · outros desportos em Estatísticas gerais",
                                  "fixed · other sports in General statistics"))
        return Item(tr("Desporto", "Sport"), value=name, data="sport",
                    detail=tr("←/→ outro desporto · Tab outro gráfico",
                              "←/→ another sport · Tab another chart"))

    def switch_sport(self, step: int) -> None:
        if self.hub is not None:
            return
        order = [None, "cycling", "rowing", "running", "swimming", "gym"]
        cur = order.index(self.STATS_SPORT) if self.STATS_SPORT in order else 0
        nxt = order[(cur + step) % len(order)]
        self.app.replace(_hubs().stats_screen(self.app, nxt))

    # -------------------------------------------------------- geral e picos

    PEAK_RANGES = (None, 7, 30, 90, 365)

    def special_view(self) -> str | None:
        v = self.VIEWS[self.view % len(self.VIEWS)]
        return v if v in ("general", "peaks") else None

    def enter_special(self) -> None:
        """«Geral» (o resumo do desporto, ou de todos) e «Picos» (a tabela)."""
        a = self.app
        view = self.special_view()
        title, sub = self.titles(t("menu.statistics"), "")
        rows = [self.sport_row()]
        if view == "general":
            from velo.ui.stats_screens import overview_items
            rows += overview_items(a, self.STATS_SPORT)
            foot = tr("Tab outro gráfico · Esc voltar", "Tab another chart · Esc back")
        else:
            rng = getattr(self, "peak_range", None)
            rows.append(Item(tr("Período", "Period"),
                             value=tr("desde sempre", "all time") if rng is None else
                             tr("últimos {n} dias", "last {n} days", n=rng),
                             detail=tr("←/→ muda", "←/→ changes"), data="peak_range"))
            foot = tr("←/→ período · Tab outro gráfico · Esc voltar",
                      "←/→ period · Tab another chart · Esc back")
            self._fill_peaks()
        self.chrome.set(title, sub, foot)
        self.list.set_items(rows, keep_index=True)
        self.list.y = self.content_top(self.app.window.height)
        self.list.set_visible_rows(2 if view == "peaks" else
                                   max(4, (self.content_top(self.app.window.height) - 110) // 38))

    def _fill_peaks(self) -> None:
        from velo.core import peaks as pk
        from velo.ui.widgets import Table
        a = self.app
        rng = getattr(self, "peak_range", None)
        since = None
        if rng:
            from datetime import date as _d, timedelta as _td
            since = (_d.today() - _td(days=rng)).isoformat()
        best = pk.all_peaks(a.db, since)
        if getattr(self, "peak_table", None) is None:
            self.peak_table = Table()
        w, h = a.window.width, a.window.height
        top = self.content_top(h) - 2 * 38 - 10
        self.peak_table.layout(48, top, w - 96, 70)
        cols = [tr("Duração", "Duration"), tr("Potência", "Power"), tr("FC", "HR"),
                tr("Cadência", "Cadence"), tr("Velocidade", "Speed")]
        rows = []
        for d in pk.DURATIONS:
            cells = [pk.duration_label(d)]
            for m in pk.METRICS:
                b = best.get(m, {}).get(d)
                cells.append((pk.fmt(m, b["value"], a.units), b["date"][5:].replace("-", "/"))
                             if b else ("—", ""))
            rows.append(cells)
        self.peak_table.set(cols, rows, tr("Picos: a melhor média em cada duração",
                                           "Peaks: the best average for each duration"),
                            empty=tr("Ainda sem sessões com dados.", "No sessions with data yet."))
        self._peaks = best

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
        if self.special_view():
            self.enter_special()
            return
        a = self.app
        tot = stats.totals(a.db)
        dv, du = km(tot["km"] * 1000.0, a.units)
        self.chrome.set(
            *self.titles(t("menu.statistics"), ""), "")
        self.chrome.set(
            self.chrome.title.text if self.hub is not None else t("menu.statistics"),
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
        periodic = view in ("evolution", "zones", "zones_period", "load", "eftp", "balance",
                            "decoupling")
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
        if which == "peak_range":
            rs = list(self.PEAK_RANGES)
            cur = getattr(self, "peak_range", None)
            self.peak_range = rs[(rs.index(cur) + (1 if step > 0 else -1)) % len(rs)]
            self.enter()
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
        if symbol in (key.ENTER, key.RETURN) and which == "apply_eftp":
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
                                     "zones_period", "eftp", "decoupling"):
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
        if view == "decoupling":
            return f"{label}: {value:+.1f} % · {stats.decoupling_label(value)}"
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
        elif view == "decoupling":
            self._decoupling_chart()
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

    def _decoupling_chart(self) -> None:
        """A deriva cardíaca (Pa:HR) de cada sessão longa: quanto a FC sobe, na 2.ª metade,
        para a mesma potência. Menos de 5 % é uma base aeróbia forte."""
        a = self.app
        days = stats.GROUPING_DAYS[self.grouping] * self.count
        hist = stats.decoupling_history(a.db, days=days)
        self._series = [(h["day"][5:], h["decoupling"]) for h in hist]
        self.chart.show_line(t("stats.view.decoupling") + " · Pa:HR", [h["decoupling"] for h in hist],
                             [h["day"][5:] for h in hist],
                             tr("Sem sessões de 40+ min com potência e FC neste período",
                                "No 40+ min sessions with power and HR in this period"),
                             fmt=lambda v: f"{v:+.1f} %")
        if hist:
            self.chart.select(len(hist) - 1, self._bar_tip(len(hist) - 1))
            recent = [h["decoupling"] for h in hist[-5:]]
            avg = sum(recent) / len(recent)
            self.summary[0].text = tr("Últimas {n} sessões: média {v:+.1f} % — {d}",
                                      "Last {n} sessions: average {v:+.1f} % — {d}",
                                      n=len(recent), v=avg, d=stats.decoupling_label(avg))
            last = hist[-1]
            vi = f" · VI {last['vi']:.2f}" if last.get("vi") else ""
            self.summary[1].text = tr("A mais recente ({d}): {v:+.1f} % · eficiência {a:.2f} → "
                                      "{b:.2f} W/bpm{vi}", "Latest ({d}): {v:+.1f} % · efficiency "
                                      "{a:.2f} → {b:.2f} W/bpm{vi}", d=last["day"],
                                      v=last["decoupling"], a=last["ef1"], b=last["ef2"], vi=vi)

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
        special = self.special_view()
        if special == "general":
            return
        if special == "peaks":
            if getattr(self, "peak_table", None) is not None:
                self.peak_table.draw()
            return
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
            from velo.core import session_workouts
            session_workouts.purge(self.db)        # cópias de treinos sem sessão
            from velo.core import segments as seg_mod
            seg_mod.purge(self.db)                 # tempos de sessões descartadas
            if not self.db.get("migr_tp_loads", False):
                # a carga da corrida e da natação passou a ser a do TrainingPeaks
                from velo.core import tss as tss_mod
                tss_mod.recompute_endurance(self.db)
                self.db.set("migr_tp_loads", True)
            if not self.db.get("migr_feedback_always", False):
                self.db.set("ask_feedback", True)  # o feedback deixou de ser opcional
                self.db.set("migr_feedback_always", True)
        except Exception:
            pass
        try:
            from velo.core import workout_library
            workout_library.seed(self.db)          # os treinos que vêm com a aplicação
        except Exception:
            pass
        # a «resistência extra» saiu das Definições: não fica a pesar escondida
        if float(self.db.get("extra_resistance_pct", 0.0) or 0.0):
            self.db.set("extra_resistance_pct", 0.0)
        set_language(self.db.get("language", PT))
        self.units = self.db.get("units", "metric")
        from velo.io.sound import Beeper
        self.beeper = Beeper()               # os bips dos avisos (ver velo.core.cues)
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
            resizable=True, fullscreen=fullscreen, file_drops=True,
            samples=int(self.db.get("msaa_samples", 4)))
        self._windowed_size = (width, height)
        try:
            self.window.set_minimum_size(*MIN_SIZE)
        except Exception:
            pass
        pyglet.gl.glClearColor(BG[0] / 255, BG[1] / 255, BG[2] / 255, 1.0)

        self.hub = SensorHub()
        self.rower = None                 # máquina de remo ligada (velo.io.rower)
        self.treadmill = None             # passadeira ligada (real ou simulada)
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
            on_close=self._on_close,
            on_file_drop=self._on_file_drop)
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
        self._unarchive_once()
        if aborted:
            self.message(f"{aborted} sessão(ões) incompleta(s) foram encerradas")
        if self.db.checkpoints():
            # a aplicação fechou a meio de uma sessão: perguntar o que fazer
            from velo.ui.sport_screens import RecoveryScreen
            self.push(RecoveryScreen(self))
        if self.db.get("auto_connect", True) and self.db.known_devices():
            self.start_auto_connect()

    def _unarchive_once(self) -> None:
        """Já não há «arquivar» nem «desativar»: o que estava escondido assim
        volta a aparecer (uma vez só)."""
        if self.db.get("migr_unarchive", False):
            return
        for sql in ("UPDATE exercises SET archived = 0 WHERE archived = 1",
                    "UPDATE fitness_tests SET active = 1 WHERE active = 0"):
            try:
                self.db.conn.execute(sql)
            except Exception:
                pass                      # a tabela (ou a coluna) ainda não existe
        self.db.conn.commit()
        self.db.set("migr_unarchive", True)

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

    def pop(self, force: bool = False) -> None:
        if len(self.stack) <= 1:
            return
        if not force and not self.stack[-1].MODAL and self.stack[-1].has_unsaved():
            self.ask_unsaved(self.stack[-1])
            return
        top = self.stack.pop()
        top.leave()
        if top.MODAL and self.stack[-1].IN_SESSION:
            return                 # a sessão de baixo nunca deixou de correr
        self.stack[-1].enter()

    def confirm(self, title: str, sub: str, on_yes: Callable, yes: str | None = None,
                no: str | None = None) -> None:
        """Pergunta antes de fazer (apagar, sair…): Cancelar · <sim>. O sim é
        o principal; Esc ou clicar fora cancelam."""
        def go() -> None:
            self.pop()
            on_yes()
        self.push(ConfirmScreen(self, title, sub,
                                [(no or tr("Cancelar", "Cancel"), self.pop),
                                 (yes or tr("Sim", "Yes"), go)],
                                default=1, buttons=True, cancel=self.pop))

    def workout_saved(self, name: str, editor=None) -> None:
        """«Treino guardado» numa janela (com OK). Ao sair com «Sair e guardar»
        basta o aviso curto (a janela ficaria por cima do ecrã seguinte)."""
        if editor is not None and getattr(editor, "_leaving", False):
            self.message(tr("Treino guardado", "Workout saved"))
            return
        self.notify(tr("Treino guardado", "Workout saved"),
                    tr("«{n}» está na lista de treinos.", "«{n}» is in the workout list.",
                       n=name or tr("Treino", "Workout")))

    def _on_file_drop(self, x: int, y: int, paths) -> None:
        """Arrastar um ficheiro para a janela: um backup (.zip) abre a reposição;
        uma atividade (.fit ou .tcx) abre o upload manual."""
        try:
            from velo.ui import upload_screens
            if upload_screens.open_dropped(self, list(paths or [])):
                return
            if not _backups().open_dropped(self, list(paths or [])):
                self.message(tr("Arrasta um backup (.zip) para o repor, ou uma atividade "
                                "(.fit, .tcx) para a carregar",
                                "Drag a backup (.zip) to restore it, or an activity "
                                "(.fit, .tcx) to upload it"))
        except Exception as e:
            self.message(f"{t('common.error')}: {e}")

    def after_restore(self) -> None:
        """Depois de repor um backup: as definições repostas aplicam-se já
        (língua, unidades, tema, ligações) e volta-se ao ecrã inicial."""
        from velo.gfx import theme as theme_mod
        set_language(self.db.get("language", PT))
        self.units = self.db.get("units", "metric")
        theme_mod.apply(str(self.db.get("theme", theme_mod.DEFAULT)))
        bg = theme_mod.P.bg
        pyglet.gl.glClearColor(bg[0] / 255, bg[1] / 255, bg[2] / 255, 1.0)
        self.topbar = TopBar(self.window)
        self._topbar_texts()
        for scr in reversed(self.stack):
            try:
                scr.leave()
            except Exception:
                pass
        self.stack = [HomeScreen(self)]
        self.stack[0].enter()
        try:
            self.apply_connection_preference()
        except Exception:
            pass

    def notify(self, title: str, sub: str = "", then: Callable | None = None) -> None:
        """Um aviso numa janela, com OK (Guardado, Importado…)."""
        def ok() -> None:
            self.pop()
            if then is not None:
                then()
        self.push(ConfirmScreen(self, title, sub, [("OK", ok)], default=0, buttons=True,
                                cancel=ok))

    def ask_unsaved(self, editor: Screen) -> None:
        """Voltar atrás com alterações por guardar: Sair sem guardar · Cancelar ·
        Sair e guardar (Esc ou clicar fora é o mesmo que Cancelar)."""
        def leave() -> None:
            self.pop()                     # a pergunta
            if hasattr(editor, "discard"):
                editor.discard()           # repõe o que estava (janelas de um treino)
            self.pop(force=True)           # o editor, sem gravar

        def stay() -> None:
            self.pop()

        def save() -> None:
            self.pop()
            editor._leaving = True         # ao sair, o «guardado» é só um aviso curto
            editor.on_save()
            editor._leaving = False
            if not editor.has_unsaved() and self.current is editor:
                self.pop(force=True)

        self.push(ConfirmScreen(
            self, tr("Há alterações por guardar", "You have unsaved changes"),
            tr("Fizeste alterações que ainda não foram gravadas.",
               "Some changes have not been saved yet."),
            [(tr("Sair sem guardar", "Leave without saving"), leave),
             (tr("Cancelar", "Cancel"), stay),
             (tr("Sair e guardar", "Save and leave"), save)], default=2, buttons=True,
            cancel=stay))

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

    def set_treadmill(self, treadmill) -> None:
        """Liga (ou desliga, com None) a passadeira."""
        old = self.treadmill
        if old is not None and old is not treadmill:
            try:
                old.disconnect()
            except Exception:
                pass
        self.treadmill = treadmill

    def new_cues(self):
        """Um acompanhante dos avisos sonoros com as regras de Definições → Configurações
        sonoras (ver `velo.core.cues`)."""
        from velo.core import cues
        return cues.CueTracker(cues.rules(self.db), self.beeper.beep,
                               on=cues.enabled(self.db), long_at_end=cues.end_beep(self.db))

    def message(self, text: str) -> None:
        self._message = text
        self._message_at = time.monotonic()

    def _draw_message(self, base) -> None:
        """A mensagem do momento e a pesquisa das tabs, por cima da barra do
        topo. A mensagem fica ao centro, na linha do título (à direita dele)."""
        screen = self.current
        if screen is not None and not screen.MODAL and not screen.counting:
            screen.draw_search_top()
        bar = self.topbar.msg
        if self._message and time.monotonic() - self._message_at < 6.0:
            w = self.window.width
            title = base.chrome.title if base is not None else None
            left = 48.0
            if title is not None and title.text:
                from velo.ui.widgets import text_px
                left = 48.0 + max(getattr(title, "content_width", 0) or 0,
                                  text_px(title.text, title.font_size, True)
                                  if title.font_size < 30 else 0) + 40
            left = min(left, w * 0.55)
            bar.show(self._message, left, w - 48.0 - (190.0 if screen is not None
                                                      and screen.AGENT else 0.0))
            bar.draw()
        else:
            bar.active = False

    # --------------------------------------------------------- faixa do topo

    def set_theme(self, key: str, persist: bool = True, carry=None) -> None:
        """Muda de tema e volta a construir o que está à vista com as cores
        novas (só fora das sessões: as Definições estão fechadas durante).

        `persist=False` é a pré-visualização das Definições: o tema vê-se logo,
        mas só fica gravado com Guardar. `carry` são as Definições abertas, cujo
        rascunho passa para as novas."""
        from velo.gfx import theme as theme_mod
        if persist:
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
        if carry is not None:
            settings.adopt(carry)
        settings.set_tab(tab if isinstance(top, SettingsScreen) else 0)
        settings.enter()
        if carry is not None:
            settings.list.index = min(carry.list.index, max(0, len(settings.list.items) - 1))
            settings.list._sync()

    def _topbar_texts(self) -> None:
        self.topbar.set_texts(tr("Dispositivos", "Devices"), tr("Definições", "Settings"),
                              tr("Desligar", "Power off"),
                              tr("Backups e Sincronização", "Backups and Sync"))

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
        if self.treadmill is not None:
            out.append((self.treadmill.name, "ok" if getattr(self.treadmill, "connected", True)
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

    def open_backups(self, source: str | None = None) -> None:
        """O botão «Backups e Sincronização» da faixa do topo (fora das sessões). Com `source`
        abre logo o separador Sincronização nessa fonte (HRV4Training, Saúde, GarminDB…)."""
        if self.in_session:
            self.message(tr("Os backups não estão disponíveis durante uma sessão de treino.",
                            "Backups are not available during a workout."))
            return
        bs = _backups()
        if isinstance(self.current, bs.BackupScreen) and source is None:
            return
        while self.current is not None and self.current.MODAL:
            self.pop()
        scr = bs.BackupScreen(self, tab=2 if source else 0)
        if source:
            labels = scr.sync.source_labels()
            if source in labels:
                scr.sync_tab = labels.index(source)
        self.push(scr)

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
        self.topbar.set_enabled("backups", not busy)
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

    def effort_now(self) -> float | None:
        """O esforço de agora em fração do limiar (1.0 = no limiar; None =
        parado), para a banda cardíaca simulada seguir a sessão em curso."""
        for scr in reversed(self.stack):
            e = getattr(scr, "engine", None) or getattr(scr, "session", None)
            if e is None:
                continue
            if getattr(e, "paused", False) or getattr(e, "finished", False):
                return None
            st = getattr(e, "state", None)
            if st is not None and hasattr(st, "power_w"):          # ciclismo
                ftp = getattr(getattr(e, "athlete", None), "ftp_w", 0) or 200
                return st.power_w / ftp if st.power_w else None
            sport = getattr(e, "sport", "")
            if sport in ("running", "swimming"):
                if not getattr(e, "started", False):
                    return None
                if sport == "swimming":
                    return 0.8
                if getattr(self, "_thr_kmh", None) is None:
                    from velo.core import intensity as it
                    self._thr_kmh = it.Context.from_db(self.db, "running").speed_mps(100) * 3.6
                return (e.speed_kmh or 0) / max(1.0, self._thr_kmh)
            if hasattr(e, "power_w") and hasattr(e, "ftp"):        # remo
                return e.power_w / max(1, e.ftp) if e.power_w else None
            return 0.6                                             # ginásio e afins
        # fora de uma sessão: segue a potência (o trainer simulado a pedalar)
        try:
            p = self.hub.reading().power_w
        except Exception:
            p = None
        return p / max(1, self.db.athlete().ftp_w) if p else None

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
            if screen.counting:
                # a contagem antes da sessão: os sensores vivos, a sessão parada
                self.hub.tick(dt)
                if screen.start_cd.update(dt):
                    screen.countdown_done()
            else:
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
            # janelas por cima de janelas: desenham-se todas, pela ordem
            start = self.stack.index(below) + 1 if below in self.stack else 0
            for scr in self.stack[start:-1]:
                if scr.MODAL:
                    scr.draw()
            screen.draw()
            self.topbar.draw()
            self._draw_message(below or screen)
            return
        if not isinstance(screen, RideScreen):
            self.window.projection = pyglet.math.Mat4.orthogonal_projection(
                0, self.window.width, 0, self.window.height, -255, 255)
            self.window.view = pyglet.math.Mat4()
        screen.draw()
        if screen.counting:
            if isinstance(screen, RideScreen):
                self.window.projection = pyglet.math.Mat4.orthogonal_projection(
                    0, self.window.width, 0, self.window.height, -255, 255)
                self.window.view = pyglet.math.Mat4()
                pyglet.gl.glDisable(pyglet.gl.GL_DEPTH_TEST)
            screen.start_cd.draw()
        if isinstance(screen, RideScreen):
            self.window.projection = pyglet.math.Mat4.orthogonal_projection(
                0, self.window.width, 0, self.window.height, -255, 255)
            self.window.view = pyglet.math.Mat4()
            pyglet.gl.glDisable(pyglet.gl.GL_DEPTH_TEST)
        self.topbar.draw()
        if not isinstance(screen, RideScreen):
            self._draw_message(screen)
        if self._fps is not None:
            self._fps.draw()

    def _on_key_press(self, symbol: int, modifiers: int) -> bool:
        screen = self.current
        if screen is not None and getattr(screen, "capturing", None):
            # Definições → Atalhos: a tecla seguinte é o atalho novo
            return bool(screen.capture_key(symbol, modifiers))
        from velo.ui import keymap
        mapped = keymap.translate(self.db.get("keymap", {}), getattr(screen, "KEY_SCOPE", None),
                                  symbol, modifiers)
        if mapped is None:
            return True                  # a tecla de origem de um atalho que mudou
        symbol, modifiers = mapped
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
        if symbol == key.S and modifiers & key.MOD_CTRL and screen is not None:
            # Ctrl+S guarda em qualquer ecrã que tenha alguma coisa para guardar
            if screen.on_save():
                return True
            handled = bool(screen.on_key(symbol, modifiers))
            if not handled and not screen.IN_SESSION:
                self.message(tr("Não há nada para guardar neste ecrã.",
                                "Nothing to save on this screen."))
            return True
        if screen is not None and screen.search_active:
            return bool(screen.search_key(symbol, modifiers))
        if screen is not None and (screen.has_search or getattr(
                screen, "SEARCH_ENTER_PICKS", False)) and (
                (symbol == key.F and modifiers & key.MOD_CTRL) or
                (symbol == getattr(key, "SLASH", -1) and not screen._text_field())):
            screen.search_focus(True)
            self._eat_text = symbol == getattr(key, "SLASH", -1)   # o «/» não entra no texto
            return True
        if screen is not None and screen.counting:
            if symbol == key.ESCAPE:
                screen.start_cd = None
                screen.cancel_countdown()
            return True                       # durante a contagem nada mais conta
        if screen is not None:
            return bool(screen.on_key(symbol, modifiers))
        return False

    def _on_text(self, text: str) -> bool:
        screen = self.current
        if getattr(self, "_eat_text", False):
            self._eat_text = False
            if text == "/":
                return True
        if screen is not None and screen.search_active:
            screen.search_text(text)
            return True
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
        if which == "backups":
            self.open_backups()
            return
        if which == "quit":
            self.ask_quit()
            return
        if which == "search":
            screen = self.current
            if screen is not None and not screen.counting and screen.has_search:
                screen.search_focus(True)
            return
        if which == "bar":
            return
        screen = self.current
        if screen is not None and screen.counting:
            return
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
    tenta 2× e depois sem; devolve também o que conseguiu. Com `file_drops`
    aceita ficheiros arrastados (os backups); se o sistema não deixar, abre
    na mesma, sem isso."""
    attempts = [s for s in (samples, 2) if s and s > 1] + [0]
    options = [kw]
    if kw.get("file_drops"):
        options.append({k: v for k, v in kw.items() if k != "file_drops"})
    last_error: Exception | None = None
    for opts in options:
        for s in dict.fromkeys(attempts):
            try:
                if s:
                    config = pyglet.gl.Config(sample_buffers=1, samples=s, depth_size=24,
                                              double_buffer=True)
                    return pyglet.window.Window(config=config, **opts), s
                return pyglet.window.Window(**opts), 0
            except Exception as e:          # NoSuchConfigException e afins
                last_error = e
    raise RuntimeError(f"não foi possível abrir a janela: {last_error}")


def _theme_name(db) -> str:
    from velo.gfx import theme as theme_mod
    return theme_mod.name(str(db.get("theme", theme_mod.DEFAULT)))


def sport_name(sport: str) -> str:
    from velo.core import sports as sp
    return sp.name(sport)


def _theme_name_of(key_) -> str:
    from velo.gfx import theme as theme_mod
    return theme_mod.name(str(key_ or theme_mod.DEFAULT))


def _calendar():
    from velo.ui import calendar_screens
    return calendar_screens


def _brief():
    from velo.ui import brief
    return brief


def _layouts():
    from velo.ui import layout_screens
    return layout_screens


from velo.datadir import database_path as _database_path  # noqa: E402
from velo.datadir import default_data_dir as _default_data_dir  # noqa: E402


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


def _routes():
    from velo.ui import route_screens
    return route_screens


def _segments_ui():
    from velo.ui import segment_screens
    return segment_screens


def _backups():
    from velo.ui import backup_screens
    return backup_screens


def _segments_mod():
    from velo.core import segments
    return segments


def _longevity_ui():
    from velo.ui import longevity_screens
    return longevity_screens


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


def _arrangement():
    from velo.ui import arrangement_screens
    return arrangement_screens


def _setup():
    from velo.ui import session_setup
    return session_setup


def _ride_report():
    from velo.ui import ride_report_screens
    return ride_report_screens


def _sport_ch():
    from velo.core import sport_challenges
    return sport_challenges
