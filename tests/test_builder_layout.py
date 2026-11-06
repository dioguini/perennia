"""Construtor de treinos (todos os desportos menos o ginásio): Free ride na
paleta, os valores ao centro de cada bloco, a lista do bloco com as
descrições à frente, o nome e o objetivo em cima, e as listas iguais."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from velo.ui import app as app_mod  # noqa: E402
from velo.ui import builder_screens as bs  # noqa: E402

SPORTS = ("cycling", "rowing", "running", "swimming")


class TestPaletteAndBlockLabels(tg.GuiCase):
    def _builder(self, sport="cycling", control="erg"):
        b = bs.BlockBuilder(self.app, sport, None, control=control)
        self.app.push(b)
        return b

    def test_free_ride_is_the_last_tile_in_every_sport(self):
        for sport in SPORTS:
            b = self._builder(sport, "manual")
            names = [b._pal_text(p[0]) for p in b.pal]
            self.assertEqual(names[-1], "Free ride", sport)
            self.assertEqual(names[:6], ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6"])
            self.app.pop(force=True)

    def test_free_ride_block_has_no_target(self):
        b = self._builder()
        b.add_block("free")
        self.assertIsNone(b.block.lo)
        self.assertEqual(b.block_texts(b.block)["zone"], "Free ride")

    def test_values_sit_in_the_middle_of_the_block(self):
        b = self._builder()
        b.sel = 1                                       # o bloco de trabalho
        b.redraw()
        spans, total = b.spans()
        x0, x1 = b.x_of(spans[1][0], total), b.x_of(spans[1][1], total)
        lab = b._labels[1]
        self.assertIn("W", lab["value"].text)            # na vista de potência, watts
        self.assertGreaterEqual(lab["value"].font_size, 16)
        self.assertAlmostEqual(lab["value"].x, (x0 + x1 - 2) / 2, delta=2)
        top = b.y_of(b.blocks[1].lo)
        self.assertTrue(b.cy0 < lab["value"].y < top)    # dentro do bloco, a meio
        self.assertIn(":", lab["dur"].text)

    def test_ramp_shows_the_average_and_cadence_shows_up(self):
        b = self._builder()
        ramp = b.blocks[0]                               # o aquecimento é uma rampa
        self.assertTrue(ramp.ramp)
        texts = b.block_texts(ramp)
        self.assertIn("média", texts["zone"])
        self.assertEqual(texts["value"], b._value(ramp.mid()))
        ramp.extra["cadence_lo"] = ramp.extra["cadence_hi"] = 90
        b.redraw()
        self.assertEqual(b._labels[0]["cad"].text, "90 rpm")

    def test_pace_view_shows_the_unit(self):
        b = self._builder("running", "manual")
        self.assertEqual(b.mode, "pace")
        self.assertTrue(b.block_texts(b.blocks[1])["value"].endswith("/km"))


class TestBlockList(tg.GuiCase):
    def test_name_and_goal_on_top_details_in_front(self):
        b = bs.BlockBuilder(self.app, "cycling", None, control="erg")
        self.app.push(b)
        b.sel = 1
        b.enter()
        lv = b.list
        heads = [lv.items[i].label for i in lv.head_indices()]
        self.assertEqual(heads, ["Nome do treino", "Objetivo do treino"])
        cells = {lv.items[i].label: (x, y) for i, x, y, _w in lv._cells}
        name_y = cells["Nome do treino"][1]
        self.assertGreater(name_y, b.cy1)                  # por cima do gráfico
        self.assertLess(cells["Duração"][1], b.cy0)         # a lista, por baixo
        self.assertFalse(lv.detail_below)
        for hl, label, value, detail in lv._rows:
            if label.text == "Duração":
                self.assertEqual(detail.y, label.y)        # a descrição à frente
                self.assertGreater(detail.x, label.x + 60)

    def test_typing_the_name_still_works(self):
        b = bs.BlockBuilder(self.app, "cycling", None, control="erg")
        self.app.push(b)
        self.select("Nome do treino")
        for _ in range(20):
            self.press(key.BACKSPACE)
        self.type("Teste")
        self.assertEqual(b.name, "Teste")


class TestBuilderRound5(tg.GuiCase):
    def setUp(self):
        super().setUp()
        win = self.app.window                 # num ecrã baixo (< 900 px) passa a 2 colunas
        win.width, win.height = 1920, 1080
        self.app._on_resize(1920, 1080)

    def _open(self, sport="cycling"):
        b = bs.BlockBuilder(self.app, sport, None, control="erg" if sport != "swimming"
                            else "manual")
        self.app.push(b)
        return b

    def test_block_title_and_kind_row(self):
        b = self._open()
        b.sel = 1
        b.enter()
        items = b.list.items
        head = next(i for i in items if i.header)
        self.assertEqual(head.label, "Bloco 2 de 3")
        kind = items[items.index(head) + 1]
        self.assertEqual((kind.label, kind.value), ("Tipo", "Trabalho"))

    def test_list_stays_in_one_column_and_does_not_jump(self):
        b = self._open()
        b.sel = 1
        b.enter()
        cy0, cols = b.cy0, b.list.columns
        self.assertEqual(cols, 1)
        b.add_block("free")                                # o Free ride tem menos linhas
        b.enter()
        self.assertEqual(b.cy0, cy0)                        # o gráfico fica igual
        self.assertEqual(b.list.columns, 1)

    def test_delete_asks_and_cancel_keeps_the_block(self):
        b = self._open()
        b.sel = 1
        b.enter()
        self.press(key.DELETE)
        self.assertIn("Apagar o bloco 2 de 3", self.screen().title_text)
        self.pick("Cancelar")
        self.assertEqual(len(b.blocks), 3)
        self.assertNotIn("Apagar o bloco (Del)", [i.label for i in b.list.items])
        self.assertIn("Del apagar", b.chrome.footer.text)   # só no rodapé
        self.press(key.DELETE)
        self.pick("Apagar o bloco")                         # confirma na janela
        self.assertEqual(len(b.blocks), 2)

    def test_save_shows_a_popup_and_save_and_leave_does_not(self):
        b = self._open()
        self.pick("Guardar")
        pop = self.screen()
        self.assertEqual(pop.title_text, "Treino guardado")
        self.assertEqual([i.label for i in pop.list.items], ["OK"])
        self.press(key.ENTER)
        self.assertIs(self.screen(), b)
        b.add_block("Z2")
        self.press(key.ESCAPE)                              # há alterações: pergunta
        self.pick("Sair e guardar")
        self.assertNotIn(b, self.app.stack)                 # saiu, sem janela por cima
        self.assertFalse(isinstance(self.screen(), app_mod.ConfirmScreen))

    def test_every_sport_uses_the_same_layout(self):
        for sport in SPORTS:
            b = self._open(sport)
            b.sel = 1
            b.enter()
            self.assertEqual(b.list.columns, 1, sport)
            self.assertEqual([b.list.items[i].label for i in b.list.head_indices()],
                             ["Nome do treino", "Objetivo do treino"], sport)
            self.assertTrue(b.list.items[[i.header for i in b.list.items].index(True)]
                            .label.startswith("Bloco 2 de"), sport)
            self.app.pop(force=True)


class TestSameBuilderListEverywhere(tg.GuiCase):
    def test_every_sport_lists_the_same_way(self):
        for sport in SPORTS:
            rows = bs.builder_items(self.app, sport)
            new = rows[-1]
            self.assertEqual(new.label, "+ Novo treino", sport)
            self.assertTrue(new.button and new.primary and not new.top, sport)  # em baixo
            first = rows[0]
            self.assertTrue(first.value, sport)                                # duração
            self.assertTrue(" · ERG" in first.detail or " · Manual" in first.detail, sport)

    def test_new_workout_button_is_at_the_bottom_in_the_hub(self):
        self.pick("Construtor de treinos")
        hub = self.screen()
        lv = hub.list
        idx = next(i for i, it in enumerate(lv.items) if it.label == "+ Novo treino")
        self.app._on_draw()
        rect = next(r for r in lv._button_rects if r[0] == idx)
        self.assertLess(rect[3], 100)                      # a faixa de baixo
        self.assertIn("P passos", hub.chrome.footer_full)


class TestNoDuplicateImports(tg.GuiCase):
    def test_same_file_twice_is_imported_once(self):
        zwo = Path(self.tmp) / "x.zwo"
        zwo.write_text('<workout_file><name>Intervalos 4x4</name><workout>'
                       '<SteadyState Duration="240" Power="1.05"/>'
                       '</workout></workout_file>')
        lib = app_mod.WorkoutLibrary(self.app)
        self.app.push(lib)
        n0 = len(self.app.db.workouts())
        lib._import(zwo)
        lib._import(zwo)
        self.assertEqual(len(self.app.db.workouts()), n0 + 1)
        self.assertIn("já está na lista", self.app._message)


if __name__ == "__main__":
    import unittest
    unittest.main()
