"""O separador «Avançado» das Definições: todas as opções afináveis (ver `core/options.py`).

As linhas são geradas a partir do registo de opções, por isso uma opção nova aparece aqui sem
mais código. Os números mudam com ←/→ (Shift: 10 passos) ou escrevem-se; as escolhas e os
interruptores têm lista pendente (Enter ou um clique); o texto escreve-se. Tudo passa pelo
rascunho das Definições: só fica gravado com **Guardar**.
"""
from __future__ import annotations

from perennia.core import options as opt_mod
from perennia.core.i18n import tr
from perennia.ui.widgets import Dropdown, Item

PREFIX = "opt:"
TEXT_PREFIX = "text:opt_"


def is_numeric(key: str) -> bool:
    opt = opt_mod.BY_KEY.get(key)
    return opt is not None and opt.kind in (opt_mod.INT, opt_mod.FLOAT)


def value_of(screen, opt: opt_mod.Opt):
    """O valor atual (o do rascunho, se houver) já dentro dos limites."""
    return opt_mod.coerce(opt, screen.get(opt.key, opt.default))


def items(screen) -> list[Item]:
    out: list[Item] = []
    on, off = tr("ligado", "on"), tr("desligado", "off")
    for group in opt_mod.GROUPS:
        out.append(Item(opt_mod.group_name(group), header=True))
        for opt in (o for o in opt_mod.OPTIONS if o.group == group):
            value = value_of(screen, opt)
            hint = opt.hint
            changed = value != opt.default
            tail = tr(" · alterado (por omissão: {d})", " · changed (default: {d})",
                      d=opt_mod.shown(opt, opt.default)) if changed else ""
            if opt.kind in (opt_mod.INT, opt_mod.FLOAT):
                detail = (hint + " · " if hint else "") + tr("←/→ muda · ou escreve o valor",
                                                              "←/→ changes · or type the value")
                out.append(Item(opt.label, value=opt_mod.shown(opt, value), detail=detail + tail,
                                data=PREFIX + opt.key, indent=1))
            elif opt.kind == opt_mod.TEXT:
                out.append(Item(opt.label, value=(str(value) or "") + "▏",
                                detail=(hint + " · " if hint else "") +
                                tr("escreve", "type") + tail,
                                data=TEXT_PREFIX + opt.key, indent=1))
            else:
                labels = [on, off] if opt.kind == opt_mod.BOOL else \
                    [opt_mod.choice_label(opt, c[0]) for c in opt.choices]
                keys = [True, False] if opt.kind == opt_mod.BOOL else [c[0] for c in opt.choices]
                cur = keys.index(value) if value in keys else 0
                out.append(Item(opt.label, value=labels[cur], detail=hint + tail,
                                data=PREFIX + opt.key, indent=1,
                                dropdown=Dropdown(
                                    labels, cur,
                                    lambda k, o=opt, ks=keys: screen.put(o.key, ks[k]),
                                    title=opt.label)))
    return out


def adjust(screen, key: str, step: int) -> None:
    """←/→ numa linha: um passo (ou mais, com Shift) para cima/baixo, ou a opção seguinte."""
    opt = opt_mod.BY_KEY.get(key)
    if opt is None:
        return
    screen.put(key, opt_mod.stepped(opt, value_of(screen, opt), step))


def apply_typed(screen, key: str, buf: str) -> None:
    """Um número escrito: só conta quando está dentro dos limites (como as outras linhas)."""
    opt = opt_mod.BY_KEY.get(key)
    if opt is None or opt.kind not in (opt_mod.INT, opt_mod.FLOAT):
        return
    try:
        num = float(buf.replace(",", "."))
    except ValueError:
        return
    if opt.lo is not None and not (opt.lo <= num <= opt.hi):
        return
    screen.put(key, opt_mod.coerce(opt, num))


def text_input(screen, field: str, text: str) -> bool:
    key = field[len("opt_"):]
    opt = opt_mod.BY_KEY.get(key)
    if opt is None or opt.kind != opt_mod.TEXT:
        return False
    cur = str(value_of(screen, opt))
    screen.put(key, (cur + text)[:200])
    return True


def text_backspace(screen, field: str) -> bool:
    key = field[len("opt_"):]
    opt = opt_mod.BY_KEY.get(key)
    if opt is None or opt.kind != opt_mod.TEXT:
        return False
    screen.put(key, str(value_of(screen, opt))[:-1])
    return True
