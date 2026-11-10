"""Definições → Configurações sonoras: os bips dos últimos (ou primeiros) segundos de um bloco,
de uma série ou de um descanso. As regras vêm de `velo.core.cues`; aqui editam-se."""
from __future__ import annotations

from velo.core import cues
from velo.core.i18n import tr
from velo.ui.sport_screens import EditPopup
from velo.ui.widgets import Item


def sound_items(screen) -> list[Item]:
    """As linhas do separador (a `screen` é a das Definições: lê e escreve em rascunho)."""
    on, off = tr("ligado", "on"), tr("desligado", "off")
    items = [
        Item(tr("Avisos sonoros", "Sound alerts"), header=True),
        Item(tr("Bips", "Beeps"), value=on if screen.get("sound_on", True) else off,
             detail=tr("Enter ou ←/→ liga e desliga · os últimos 5 s vêem-se sempre no ecrã",
                       "Enter or ←/→ turns on/off · the last 5 s always show on screen"),
             action=lambda: screen._adjust("sound_on", 1), data="sound_on"),
        Item(tr("Bip longo no fim", "Long beep at the end"),
             value=on if screen.get("sound_end", True) else off,
             detail=tr("um bip mais comprido quando o tempo acaba",
                       "a longer beep when the time runs out"),
             action=lambda: screen._adjust("sound_end", 1), data="sound_end"),
        Item(tr("Regras", "Rules"), header=True)]
    rules = current_rules(screen)
    for r in rules:
        items.append(Item(cues.describe(r), value=f"{r['seconds']} s",
                          detail=tr("Enter edita · Del apaga", "Enter edits · Del deletes"),
                          action=lambda rid=r["id"]: edit_rule(screen, rid),
                          data=f"rule:{r['id']}"))
    if not rules:
        items.append(Item(tr("Nenhuma regra: só se vê o fim no ecrã", "No rules: only the end "
                             "shows on screen"), enabled=False))
    items.append(Item(tr("+ Nova regra", "+ New rule"), button=True,
                      action=lambda: edit_rule(screen, None)))
    items.append(Item(tr("Testar os bips", "Test the beeps"), button=True,
                      action=lambda: start_test(screen)))
    items.append(Item(tr("Repor as de origem", "Restore the defaults"), button=True,
                      action=lambda: reset_rules(screen)))
    return items


def current_rules(screen) -> list[dict]:
    if "sound_rules" in screen.draft:
        return [dict(r) for r in screen.draft["sound_rules"]]
    return cues.rules(screen.app.db)


def put_rules(screen, items: list[dict]) -> None:
    screen.put("sound_rules", [dict(r) for r in items])
    screen.enter()


def edit_rule(screen, rid: str | None) -> None:
    rules = current_rules(screen)
    rule = next((r for r in rules if r["id"] == rid), None)
    screen.app.push(SoundRulePopup(screen.app, rule, lambda r: _saved(screen, r)))


def _saved(screen, rule: dict) -> str:
    """Grava a regra (nova, se não tem id) no rascunho das Definições e devolve o id."""
    rules = current_rules(screen)
    if not rule.get("id"):
        rule = dict(rule, id=cues.new_id(rules))
    if any(r["id"] == rule["id"] for r in rules):
        rules = [rule if r["id"] == rule["id"] else r for r in rules]
    else:
        rules.append(rule)
    put_rules(screen, rules)
    return rule["id"]


def delete_rule(screen, rid: str) -> None:
    put_rules(screen, [r for r in current_rules(screen) if r["id"] != rid])


def reset_rules(screen) -> None:
    put_rules(screen, [dict(r) for r in cues.DEFAULT_RULES])
    screen.app.message(tr("Regras de origem repostas (guarda para ficarem).",
                          "Default rules restored (save to keep them)."))


# ------------------------------------------------------------------ testar


def start_test(screen) -> None:
    """Toca, ao ritmo certo, um bloco de 15 s seguido de um descanso de 12 s com as regras que
    estão no ecrã (mesmo as ainda por guardar)."""
    from velo.io.sound import Beeper
    beeper = getattr(screen.app, "beeper", None) or Beeper()
    tracker = cues.CueTracker(current_rules(screen), beeper.beep,
                              on=bool(screen.get("sound_on", True)),
                              long_at_end=bool(screen.get("sound_end", True)))
    screen._sound_test = {"t": 0.0, "tracker": tracker}
    screen.app.message(tr("A testar: um bloco de 15 s e um descanso de 12 s…",
                          "Testing: a 15 s block and a 12 s rest…"))


def tick_test(screen, dt: float) -> None:
    run = getattr(screen, "_sound_test", None)
    if not run:
        return
    run["t"] += dt
    t = run["t"]
    tracker = run["tracker"]
    # o bloco de 15 s e, a seguir, o descanso de 12 s; ao passar de um para o outro, o que
    # acabou recebe primeiro o seu «zero» (é aí que toca o bip longo)
    if t < 15.0:
        tracker.update("work", "work", t, 15.0 - t)
    elif t < 27.0:
        if not run.get("rest"):
            tracker.update("work", "work", 15.0, 0.0)
            run["rest"] = True
        tracker.update("rest", "rest", t - 15.0, 27.0 - t)
    else:
        tracker.update("rest", "rest", 12.0, 0.0)
        screen._sound_test = None


class SoundRulePopup(EditPopup):
    """Uma regra: quando (primeiros ou últimos N segundos), quantos bips por segundo e onde."""

    W = 760

    def __init__(self, app, rule: dict | None, on_save):
        super().__init__(app)
        self.on_save = on_save
        self.rule_id = rule["id"] if rule else None
        r = rule or {"when": "last", "seconds": 10, "per_s": 1, "scope": "all"}
        self.when, self.seconds = r["when"], int(r["seconds"])
        self.per_s, self.scope = int(r["per_s"]), r["scope"]

    def title(self) -> str:
        return tr("Regra de bips", "Beep rule") if self.rule_id else \
            tr("Nova regra de bips", "New beep rule")

    def subtitle(self) -> str:
        return cues.describe({"when": self.when, "seconds": self.seconds, "per_s": self.per_s,
                              "scope": self.scope})

    def state(self):
        return (self.when, self.seconds, self.per_s, self.scope)

    def rows(self) -> list[Item]:
        return [
            Item(tr("Quando", "When"), value=cues.when_label(self.when), data="cyc:when",
                 detail=tr("os primeiros ou os últimos segundos do bloco, da série ou do "
                           "descanso", "the first or the last seconds of the block, set or rest")),
            Item(tr("Segundos", "Seconds"), value=f"{self.seconds} s", data="num:seconds",
                 detail=tr("a duração da janela (1–600) · escreve o número · ←/→ ±1",
                           "the window length (1–600) · type the number · ←/→ ±1")),
            Item(tr("Bips por segundo", "Beeps per second"), value=cues.per_label(self.per_s),
                 data="num:per_s",
                 detail=tr("0 = um só bip, no início da janela · 1 a {m} bips em cada segundo",
                           "0 = a single beep at the start of the window · 1 to {m} beeps "
                           "every second", m=cues.MAX_PER_S)),
            Item(tr("Onde", "Where"), value=cues.scope_label(self.scope), data="cyc:scope",
                 detail=tr("em tudo, só nos blocos e nas séries, ou só nos descansos",
                           "everywhere, only in blocks and sets, or only in rests"))]

    def num_adjust(self, field: str, steps: int, big: bool) -> None:
        if field == "seconds":
            self.seconds = max(1, min(600, self.seconds + steps * (5 if big else 1)))
        elif field == "per_s":
            self.per_s = max(0, min(cues.MAX_PER_S, self.per_s + steps))

    def num_set(self, field: str, value: float | None) -> None:
        if value is None:
            return
        if field == "seconds":
            self.seconds = max(1, min(600, int(value)))
        elif field == "per_s":
            self.per_s = max(0, min(cues.MAX_PER_S, int(value)))

    def cycle(self, field: str, step: int) -> None:
        if field == "when":
            self.when = cues.WHENS[(cues.WHENS.index(self.when) + step) % len(cues.WHENS)]
        elif field == "scope":
            self.scope = cues.SCOPES[(cues.SCOPES.index(self.scope) + step) % len(cues.SCOPES)]

    def commit(self) -> bool:
        self.rule_id = self.on_save({"id": self.rule_id, "when": self.when,
                                     "seconds": self.seconds, "per_s": self.per_s,
                                     "scope": self.scope})
        return True

    def saved_message(self) -> str:
        return tr("Regra guardada (guarda as Definições para ficar)",
                  "Rule saved (save the settings to keep it)")
