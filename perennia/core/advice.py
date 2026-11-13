"""O formato comum do que o Treinador e o Assistente de saúde dizem.

Um `Advice` é um título, um veredicto curto (com um tom: bom / atenção / mau / informação),
secções de texto, as perguntas que a figura faz ao atleta, os factos em que se baseou (`data`:
é isto que seguiria para um agente de IA, se o pedires) e, quando há um plano, as sessões
propostas (`schedule`), que só vão para o calendário se o atleta carregar no botão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

TONES = ("good", "warn", "bad", "info")


@dataclass
class Planned:
    day: date
    sport: str                    # cycling | rowing | running | swimming | gym
    title: str
    notes: str = ""


@dataclass
class Advice:
    title: str
    verdict: str = ""
    tone: str = "info"
    sections: list[tuple[str, str]] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    schedule: list[Planned] = field(default_factory=list)
    disclaimer: str = ""

    def add(self, title: str, text: str) -> None:
        text = " ".join(str(text).split())
        if text:
            self.sections.append((title, text))

    def worst(self, tone: str) -> None:
        """Piora o tom (nunca o melhora): info < good < warn < bad."""
        order = {"info": 0, "good": 1, "warn": 2, "bad": 3}
        if order.get(tone, 0) > order.get(self.tone, 0):
            self.tone = tone

    def as_text(self) -> str:
        out = [self.title]
        if self.verdict:
            out.append(self.verdict)
        for t, x in self.sections:
            out.append(f"{t}: {x}")
        for q in self.questions:
            out.append(f"? {q}")
        if self.disclaimer:
            out.append(self.disclaimer)
        return "\n".join(out)
