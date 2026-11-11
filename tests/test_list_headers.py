"""Títulos de secção nas listas (sombreados e saltados pelas setas) e as
descrições à frente das opções (por baixo, nas listas grandes)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import pyglet_stub  # noqa: E402

pyglet_stub.install()

from pyglet.window import key  # noqa: E402

tg = sys.modules.get("test_gui") or importlib.import_module("tests.test_gui")
from perennia.ui import widgets as wd  # noqa: E402


class TestHeaderItems(tg.GuiCase):
    def _list(self, items, width=900, rows=10):
        lv = wd.ListView(48, 600, width, rows)
        lv.set_items(items)
        return lv

    def test_old_dash_titles_become_headers(self):
        it = wd.Item("— Recordes —", enabled=False)
        self.assertTrue(it.header)
        self.assertEqual(it.label, "Recordes")
        self.assertFalse(wd.Item("Recordes", enabled=False).header)   # info, não título

    def test_arrows_skip_headers_both_ways(self):
        lv = self._list([wd.Item("Atleta", header=True), wd.Item("Nome"),
                         wd.Item("Idade"), wd.Item("Ligações", header=True),
                         wd.Item("Strava")])
        self.assertEqual(lv.index, 1)                  # nunca começa num título
        lv.move(1)
        self.assertEqual(lv.selected.label, "Idade")
        lv.move(1)
        self.assertEqual(lv.selected.label, "Strava")  # saltou «Ligações»
        lv.move(-1)
        self.assertEqual(lv.selected.label, "Idade")
        lv.move(1)
        lv.move(1)                                     # dá a volta e salta «Atleta»
        self.assertEqual(lv.selected.label, "Nome")

    def test_header_row_is_shaded_and_bold(self):
        lv = self._list([wd.Item("Atleta", header=True), wd.Item("Nome")])
        hl, label, _value, _detail = lv._rows[0]
        self.assertEqual(hl.opacity, 255)
        self.assertEqual(hl.color, wd.PANEL2)
        self.assertEqual(label._head.text, "Atleta")
        self.assertEqual(label.text, "")

    def test_clicking_a_header_does_nothing(self):
        hit = []
        lv = self._list([wd.Item("Título", header=True), wd.Item("A", action=lambda: hit.append(1))])
        _idx, x, y, _w = lv._cells[0]
        lv.on_mouse_press(int(x + 5), int(y))
        self.assertEqual(lv.index, 1)
        self.assertEqual(hit, [])

    def test_details_sit_in_front_of_the_options(self):
        lv = self._list([wd.Item("Tema", value="Perennia", detail="←/→ muda"),
                         wd.Item("Unidades", value="métrico", detail="←/→ muda")])
        _hl, label, _v, detail = lv._rows[0]
        self.assertEqual(label.y, detail.y)            # na mesma linha
        self.assertGreater(detail.x, label.x + 40)     # à frente do rótulo
        _hl2, _l2, _v2, detail2 = lv._rows[1]
        self.assertEqual(detail.x, detail2.x)          # alinhadas numa coluna

    def test_big_lists_keep_details_below(self):
        items = [wd.Item(f"Exercício {i}", detail="kettlebell") for i in range(30)]
        lv = self._list(items, width=1200, rows=8)
        self.assertGreater(lv.columns, 1)
        _hl, label, _v, detail = lv._rows[0]
        self.assertLess(detail.y, label.y)             # por baixo
        lv2 = self._list(items[:3])
        lv2.detail_below = True
        lv2._sync()
        _hl, label, _v, detail = lv2._rows[0]
        self.assertLess(detail.y, label.y)

    def test_settings_garmin_title_is_a_header(self):
        self.pick("Definições")
        scr = self.screen()
        scr.tab_named("Ligações Externas")
        heads = [i for i in scr.list.items if i.header]
        self.assertTrue(any("GarminDB" in i.label for i in heads))
        for _ in range(len(scr.list.items) + 2):
            self.press(key.DOWN)
            self.assertFalse(scr.list.selected.header)


if __name__ == "__main__":
    import unittest
    unittest.main()
