"""Editar o objetivo de um treino e o de cada bloco."""
from __future__ import annotations

from velo.core import objectives as ob
from velo.core.i18n import tr
from velo.ui.brief import wrap
from velo.ui.sport_screens import EditScreen
from velo.ui.widgets import Item


class GoalEditor(EditScreen):
    """Escrever o objetivo do treino e o de cada bloco (o nome também)."""

    def __init__(self, app, sport: str, wid: str, brief: ob.Brief):
        super().__init__(app)
        self.sport, self.wid = sport, wid
        saved = ob.stored(app.db, sport, wid)
        self.goal = saved.get("goal") or (brief.goal if brief.goal_written else "")
        self.suggested = brief.goal
        n = len(brief.raw_blocks)
        sb = list(saved.get("blocks") or [])
        sb += [{}] * (n - len(sb))
        self.blocks = [{"name": (x or {}).get("name", ""), "goal": (x or {}).get("goal", "")}
                       for x in sb[:n]]
        self.entries = list(brief.blocks)
        self.brief = brief

    def _indices(self, k: int) -> list[int]:
        """Os blocos reais que este item representa (todos os da repetição)."""
        return list(self.entries[k].indices) or [k]

    def enter(self) -> None:
        items = [Item(tr("Objetivo do treino", "Workout goal"),
                      value=wrap(self.goal, 380, 13, 1) + "▏", data="text:goal",
                      detail=tr("Sugestão: ", "Suggestion: ") + self.suggested)]
        for k, b in enumerate(self.entries):
            start = self._indices(k)[0]
            cur = self.blocks[start] if start < len(self.blocks) else {}
            items.append(Item(f"{k + 1}. " + tr("Nome", "Name") + f" · {b.dur_text}",
                              value=(cur.get("name") or b.name) + "▏", data=f"text:name:{k}",
                              detail=tr("Alvo: {t}", "Target: {t}", t=b.target)))
            items.append(Item("    " + tr("Objetivo do bloco", "Block goal"),
                              value=wrap(cur.get("goal") or b.goal, 300, 13, 1) + "▏",
                              data=f"text:goal:{k}"))
        items += [Item(tr("✓ Guardar", "✓ Save"), action=self._save),
                  Item(tr("Repor as sugestões", "Reset to suggestions"), action=self._reset)]
        self.chrome.set(tr("Objetivos", "Goals"), self.brief.title,
                        tr("Escreve · Backspace apaga · ↑↓ mover · Esc voltar",
                           "Type · Backspace deletes · ↑↓ move · Esc back"))
        self.list.set_items(items, keep_index=True)

    def _target(self, field: str) -> tuple[str, list[int]] | None:
        if field == "goal":
            return ("goal", [])
        part, k = field.split(":")
        return (part, self._indices(int(k)))

    def text_input(self, field: str, text: str) -> None:
        what, idxs = self._target(field)
        if what == "goal" and not idxs:
            self.goal = (self.goal + text)[:300]
        else:
            k = int(field.split(":")[1])
            base = self.blocks[idxs[0]].get(what) or getattr(self.entries[k], what)
            for i in idxs:
                if i < len(self.blocks):
                    self.blocks[i][what] = (base + text)[:160]
        self.enter()

    def text_backspace(self, field: str) -> None:
        what, idxs = self._target(field)
        if what == "goal" and not idxs:
            self.goal = self.goal[:-1]
        else:
            k = int(field.split(":")[1])
            base = self.blocks[idxs[0]].get(what) or getattr(self.entries[k], what)
            for i in idxs:
                if i < len(self.blocks):
                    self.blocks[i][what] = base[:-1]
        self.enter()

    def _save(self) -> None:
        ob.save(self.app.db, self.sport, self.wid, self.goal.strip(), self.blocks)
        self.app.message(tr("Objetivos guardados", "Goals saved"))
        self.app.pop()

    def _reset(self) -> None:
        self.goal = ""
        self.blocks = [{"name": "", "goal": ""} for _ in self.blocks]
        ob.save(self.app.db, self.sport, self.wid, "", self.blocks)
        self.app.pop()
