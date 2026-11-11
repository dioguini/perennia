"""Um «robô» que percorre a interface: abre todos os menus, passa por todos os
separadores, ativa todas as linhas e carrega nas setas, desenhando cada ecrã.

Não verifica o que cada botão faz (os outros testes tratam disso): apanha o que
rebenta — um menu que levanta uma exceção ao abrir, uma linha cujo botão
referencia um nome que já não existe, um ecrã que não se consegue desenhar.
As ações destrutivas, de rede e de hardware ficam de fora.
"""
from __future__ import annotations

import os
import sys
import traceback
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

from tests import test_gui as tg  # noqa: E402
from perennia.core.i18n import PT, set_language  # noqa: E402
from perennia.ui import app as app_mod  # noqa: E402

# Linhas que não se ativam: sair, apagar, rede, aparelhos reais, abrir o browser…
SKIP = ("sair", "desligar", "quit", "power off", "apagar", "delete", "eliminar", "remover",
        "procurar", "scan", "ligar à", "connect to", "autorizar", "authorize", "strava",
        "garmin", "exportar", "export", "importar", "import", "agente", "coach", "api",
        "repor tudo", "reset all", "limpar", "clear", "terminar", "finish", "reiniciar")
MAX_SCREENS = 4000
SEEDS = tuple(range(1, 1 + int(os.environ.get("SEEDS", "3"))))   # mais: SEEDS=40 python -m unittest …


def _sig(scr) -> tuple:
    labels = tuple(i.label for i in scr.list.items[:6])
    return type(scr).__name__, getattr(scr, "tab", 0), getattr(scr, "sport", ""), labels


class Walker:
    def __init__(self, case: tg.GuiCase):
        self.case = case
        self.app = case.app
        self.seen: set = set()
        self.errors: list[str] = []
        self.visited: list[str] = []
        self.dead: list[str] = []          # linhas ativas em que o Enter não faz nada

    def err(self, where: str) -> None:
        self.errors.append(f"{where}\n{traceback.format_exc()}")

    def safe(self, where: str, fn) -> bool:
        try:
            fn()
            return True
        except Exception:
            self.err(where)
            return False

    def draw(self, where: str) -> None:
        self.safe(f"{where} · desenhar", self.app._on_draw)

    def restore(self, depth: int, stack: list) -> None:
        """Volta à pilha que havia (a ação pode ter empilhado ou trocado ecrãs)."""
        while len(self.app.stack) > depth and self.app.stack[-1] is not stack[depth - 1]:
            self.app.pop()
        if self.app.stack[:depth] != stack[:depth]:
            self.app.stack[:] = stack[:depth]
            self.safe("restaurar", self.app.stack[-1].enter)

    def explore(self, path: str, level: int = 0) -> None:
        app = self.app
        scr = app.current
        if scr is None or len(self.seen) > MAX_SCREENS or level > 5:
            return
        tabs = range(len(scr.tab_labels())) if getattr(scr, "tabs", None) is not None else [None]
        for tab in tabs:
            if tab is not None:
                if not self.safe(f"{path} · separador {tab}", lambda t=tab: scr.set_tab(t)):
                    continue
            subs = [None]
            if getattr(scr, "has_subtabs", False):
                subs = range(len(scr._sport_ids()))
            for sub in subs:
                if sub is not None:
                    self.safe(f"{path} · desporto {sub}", lambda s=sub: scr.set_sport(s))
                sig = _sig(scr)
                if sig in self.seen:
                    continue
                self.seen.add(sig)
                where = f"{path} › {sig[0]}"
                if tab is not None:
                    where += f"[{tab}]"
                if sub is not None:
                    where += f"({sub})"
                self.visited.append(where)
                self.draw(where)
                self.visit_items(where, scr, level)

    def visit_items(self, where: str, scr, level: int) -> None:
        app = self.app
        n = len(scr.list.items)
        stack = list(app.stack)
        depth = len(stack)
        for idx in range(n):
            if idx >= len(scr.list.items):
                break
            item = scr.list.items[idx]
            label = item.label.strip()
            low = label.lower()
            here = f"{where} › «{label}»"
            scr.list.index = idx
            scr.list._sync()
            # setas: ajustar valores
            if isinstance(item.data, str) and not item.data.startswith("text:"):
                for k in (key.RIGHT, key.LEFT):
                    self.safe(here + " · seta", lambda k=k: app._on_key_press(k, 0))
                    if app.current is not scr:
                        self.restore(depth, stack)
                scr.enter() if hasattr(scr, "enter") else None
            if item.enabled and item.action is None and not item.data and \
                    not item.label.startswith(("—", "-", " ")):
                self.dead.append(here)
            if not item.enabled or item.action is None or any(s in low for s in SKIP):
                continue
            ok = self.safe(here, scr.list.activate)
            if not ok:
                self.restore(depth, stack)
                continue
            if app.current is not scr:
                if getattr(app.current, "IN_SESSION", False):
                    self.session(here)
                else:
                    self.explore(here, level + 1)
                self.restore(depth, stack)
            self.safe(here + " · reabrir", scr.enter)
            if idx < len(scr.list.items):
                pass

    def session(self, where: str) -> None:
        scr = self.app.current
        for _ in range(6):
            self.safe(where + " · sessão", lambda: self.app._tick(0.25))
        self.draw(where + " · sessão")


FUZZ_KEYS = [getattr(key, n) for n in (
    "SPACE", "ENTER", "ESCAPE", "TAB", "LEFT", "RIGHT", "UP", "DOWN", "PLUS", "MINUS", "EQUAL",
    "NUM_ADD", "NUM_SUBTRACT", "PAGEUP", "PAGEDOWN", "BACKSPACE", "DELETE", "BRACKETLEFT",
    "BRACKETRIGHT", "F4", "F8", "F10", "A", "B", "C", "D", "E", "G", "H", "I", "J", "K", "L",
    "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z") if hasattr(key, n)]


class TestSessionFuzz(tg.GuiCase):
    """Carrega em teclas ao acaso, a meio de cada tipo de sessão, com os menus de
    dispositivos e definições a abrir e a fechar: nada pode rebentar."""

    def run_fuzz(self, label: str, scr, seed: int, steps: int = 400) -> None:
        import random
        rng = random.Random(seed)
        app = self.app
        for i in range(steps):
            k = rng.choice(FUZZ_KEYS)
            mods = key.MOD_SHIFT if rng.random() < 0.1 else 0
            try:
                app._on_key_press(k, mods)
                if rng.random() < 0.3:
                    app._on_text(rng.choice("0123456789,.x"))
                for _ in range(rng.choice((1, 1, 2, 8))):
                    app._tick(0.25)
                if i % 7 == 0:
                    app._on_draw()
            except Exception:
                self.fail(f"{label} (semente {seed}, passo {i}, tecla {k}):\n"
                          f"{traceback.format_exc()}")
            if app.current is not None and not app.in_session:
                return                                  # a sessão acabou (terminar/guardar)

    def test_every_session_survives_random_keys(self):
        from perennia.core import gym
        from perennia.io import rower as rio
        from perennia.ui import endurance_screens as es
        from perennia.ui import rowing_screens as rs
        from perennia.ui import sport_screens as ss

        def cycling():
            wid = self.app.db.workouts()[0]["id"]
            scr = app_mod.RideScreen(self.app, route_id=None, workout_id=wid, kind="workout",
                                     ghosts=[], erg=True)
            self.app.push(scr)
            scr.preparing = False

        def rowing():
            self.app.set_rower(rio.SimulatedRower())
            self.app.push(rs.RowingSessionScreen(self.app))

        def strength():
            wid = gym.workouts(self.app.db, "strength")[0]["id"]
            self.app.push(ss.StrengthSessionScreen(self.app, wid))

        starters = {
            "ciclismo": cycling,
            "corrida": lambda: self.app.push(es.EnduranceSession(self.app, "running")),
            "natação": lambda: self.app.push(es.EnduranceSession(self.app, "swimming")),
            "remo": rowing,
            "força": strength,
            "força livre": lambda: self.app.push(ss.StrengthSessionScreen(
                self.app, gym.workouts(self.app.db, "strength")[0]["id"], free=True)),
            "voltas": lambda: self.app.push(ss.LapSessionScreen(self.app, "free")),
        }
        for name, start in starters.items():
            for seed in SEEDS:
                set_language(PT)                        # o acaso pode mudar o idioma
                self.app.db.set("language", PT)
                self.app.db.set("units", "metric")
                self.app.stack[:] = self.app.stack[:1]
                self.app.stack[0].enter()
                start()
                scr = self.screen()
                self.assertTrue(self.app.in_session, name)
                if getattr(scr, "world", None) is not None:
                    scr.world.build_all()
                    scr.preparing = False
                self.run_fuzz(f"{name}", scr, seed)


class TestUiWalk(tg.GuiCase):
    def test_walk_every_menu(self):
        w = Walker(self)
        self.app.reset_to_menu()
        # começa no ecrã inicial e percorre cada desporto
        home = self.app.stack[0]
        home.enter()
        for sport in ("Ciclismo", "Remo", "Corrida", "Natação", "Ginásio"):
            self.app.stack[:] = self.app.stack[:1]
            self.app.stack[0].enter()
            if not w.safe(f"abrir {sport}", lambda s=sport: self.pick(s)):
                continue
            w.explore(sport)
        # as janelas por cima
        self.app.stack[:] = self.app.stack[:1]
        self.app.stack[0].enter()
        for name, fn in (("Definições", self.app.open_settings),
                         ("Dispositivos", self.app.open_devices)):
            if w.safe(name, fn):
                w.explore(name)
            while len(self.app.stack) > 1:
                self.app.pop()
        kinds = sorted({v.split(" › ")[-1].split("[")[0].split("(")[0] for v in w.visited})
        self.assertGreater(len(w.visited), 80)            # percorreu mesmo a aplicação
        self.assertGreater(len(kinds), 25)
        if w.errors:
            self.fail("\n\n".join(w.errors[:8]))


if __name__ == "__main__":
    unittest.main()
