"""Atalhos de teclado personalizáveis (Definições → Atalhos de teclado).

Cada atalho é uma **ação** com um **âmbito** (qualquer ecrã, a sessão de
ciclismo, a de remo…) e uma tecla de origem. Quem quiser muda a tecla; fica
guardado em `keymap` ({ação: [tecla, [modificadores]]}).

Os ecrãs continuam a ouvir as teclas de origem: à entrada, a aplicação traduz
a tecla nova na de origem (`translate`), e a de origem, se foi trocada, deixa
de fazer essa ação nesse âmbito. As teclas de navegação (setas, Enter, Esc,
Tab…) são fixas.
"""
from __future__ import annotations

from pyglet.window import key

from velo.core.i18n import tr

# (ação, âmbito, tecla de origem, modificadores, PT, EN)
ACTIONS = (
    ("save", "global", "S", ("ctrl",), "Guardar", "Save"),
    ("devices", "global", "F4", (), "Dispositivos", "Devices"),
    ("settings", "global", "F8", (), "Definições", "Settings"),
    ("fullscreen", "global", "F11", (), "Ecrã inteiro", "Full screen"),
    ("quit", "global", "Q", ("ctrl",), "Sair da Perennia", "Quit Perennia"),
    ("agent_page", "global", "F1", (), "Resumo da página (agente)", "Page summary (agent)"),
    ("agent_ctx", "global", "F2", (), "Resumo com contexto (agente)",
     "Summary with context (agent)"),
    ("ride_lap", "ride", "L", (), "Marcar volta (lap)", "Mark a lap"),
    ("ride_pause", "ride", "P", (), "Pausa / retomar", "Pause / resume"),
    ("ride_finish", "ride", "F10", (), "Terminar e guardar", "Finish and save"),
    ("row_lap", "rowing", "L", (), "Marcar volta", "Mark a lap"),
    ("row_pause", "rowing", "P", (), "Pausa / retomar", "Pause / resume"),
    ("row_fields", "rowing", "V", (), "Outra página de campos", "Next page of fields"),
    ("row_finish", "rowing", "F10", (), "Terminar", "Finish"),
    ("run_start", "endurance", "SPACE", (), "Começar (sem contagem)", "Start (no countdown)"),
    ("run_lap", "endurance", "L", (), "Marcar volta", "Mark a lap"),
    ("run_pause", "endurance", "P", (), "Pausa / retomar", "Pause / resume"),
    ("run_total", "endurance", "T", (), "Corrida: escrever o total do visor",
     "Running: type the display total"),
    ("run_finish", "endurance", "F10", (), "Terminar", "Finish"),
    ("gym_pause", "gym", "P", (), "Pausa / retomar", "Pause / resume"),
    ("gym_finish", "gym", "F10", (), "Terminar", "Finish"),
    ("bld_dup", "builder", "D", (), "Duplicar o bloco", "Duplicate the block"),
    ("route_fav", "routes", "F", (), "Rota favorita", "Favourite route"),
    ("cal_today", "calendar", "T", (), "Calendário: hoje", "Calendar: today"),
)

SCOPES = (("global", "Em qualquer ecrã", "On any screen"),
          ("ride", "Sessão de ciclismo", "Cycling session"),
          ("rowing", "Sessão de remo", "Rowing session"),
          ("endurance", "Corrida e natação", "Running and swimming"),
          ("gym", "Ginásio (força e voltas)", "Gym (strength and laps)"),
          ("builder", "Construtor de treinos", "Workout builder"),
          ("routes", "Biblioteca de rotas", "Route library"),
          ("calendar", "Calendário", "Calendar"))

# teclas fixas (navegação): mostram-se, não se mudam
FIXED = (("↑ ↓  ·  J K", "Mover na lista", "Move in the list"),
         ("Enter  ·  Espaço", "Escolher", "Choose"),
         ("← →", "Mudar o valor da linha", "Change the row's value"),
         ("Shift+← →", "Mudar mais depressa", "Change faster"),
         ("Tab  ·  Shift+Tab", "Separador seguinte / anterior", "Next / previous tab"),
         ("Esc", "Voltar (com alterações por guardar, pergunta primeiro)",
          "Back (asks first if there are unsaved changes)"),
         ("Backspace", "Apagar o que se escreveu", "Delete what you typed"),
         ("Del", "Apagar a linha escolhida (duas vezes)", "Delete the chosen row (twice)"))

# as teclas que podem ser atalho
NAMES = tuple(chr(c) for c in range(ord("A"), ord("Z") + 1)) + \
    tuple(f"F{i}" for i in range(1, 13)) + ("SPACE",)
RESERVED_GLOBAL = ("J", "K", "SPACE")         # navegam nas listas: só com Ctrl/Alt

_BY_ID = {a[0]: a for a in ACTIONS}


def default(action: str) -> tuple[str, tuple[str, ...]]:
    a = _BY_ID[action]
    return a[2], tuple(a[3])


def label(action: str) -> str:
    a = _BY_ID[action]
    return tr(a[4], a[5])


def custom_map(raw) -> dict:
    """O que está guardado, limpo: só ações conhecidas e teclas válidas."""
    out = {}
    for k, v in dict(raw or {}).items():
        if k in _BY_ID and isinstance(v, (list, tuple)) and v and v[0] in NAMES:
            mods = tuple(sorted(m for m in (v[1] if len(v) > 1 else ()) if m in ("ctrl",
                                                                                  "alt")))
            out[k] = [v[0], list(mods)]
    return out


def binding(raw, action: str) -> tuple[str, tuple[str, ...]]:
    v = custom_map(raw).get(action)
    if v is None:
        return default(action)
    return v[0], tuple(v[1])


def key_text(b: tuple[str, tuple[str, ...]]) -> str:
    name, mods = b
    shown = tr("Espaço", "Space") if name == "SPACE" else name
    pre = "".join({"ctrl": "Ctrl+", "alt": "Alt+"}[m] for m in sorted(mods))
    return pre + shown


def name_of(symbol: int) -> str | None:
    for n in NAMES:
        if getattr(key, n, None) == symbol:
            return n
    return None


def mods_of(modifiers: int) -> tuple[str, ...]:
    out = []
    if modifiers & key.MOD_CTRL:
        out.append("ctrl")
    if modifiers & key.MOD_ALT:
        out.append("alt")
    return tuple(out)


def to_key(b: tuple[str, tuple[str, ...]], shift: int = 0) -> tuple[int, int]:
    name, mods = b
    m = shift
    if "ctrl" in mods:
        m |= key.MOD_CTRL
    if "alt" in mods:
        m |= key.MOD_ALT
    return getattr(key, name), m


def actions_in(scope: str) -> list[str]:
    return [a[0] for a in ACTIONS if a[1] == scope]


def conflict(raw, action: str, b: tuple[str, tuple[str, ...]]) -> str | None:
    """A ação que já usa esta tecla no mesmo âmbito (ou em qualquer ecrã)."""
    scope = _BY_ID[action][1]
    scopes = [s for s, _p, _e in SCOPES] if scope == "global" else [scope, "global"]
    for other in ACTIONS:
        if other[0] != action and other[1] in scopes and binding(raw, other[0]) == b:
            return other[0]
    return None


def problem(raw, action: str, b: tuple[str, tuple[str, ...]]) -> str | None:
    """Porque é que esta tecla não pode ser o atalho (None: pode)."""
    name, mods = b
    if _BY_ID[action][1] == "global" and name in RESERVED_GLOBAL and not mods:
        return tr("{k} navega nas listas: em qualquer ecrã só com Ctrl ou Alt",
                  "{k} moves in lists: on any screen only with Ctrl or Alt", k=key_text(b))
    other = conflict(raw, action, b)
    if other is not None:
        return tr("{k} já é «{a}»", "{k} is already «{a}»", k=key_text(b), a=label(other))
    return None


def translate(raw, scope: str | None, symbol: int, modifiers: int):
    """A tecla carregada → a tecla que os ecrãs conhecem. None: não faz nada
    (era a tecla de origem de um atalho que mudou)."""
    custom = custom_map(raw)
    if not custom:
        return symbol, modifiers
    name = name_of(symbol)
    if name is None:
        return symbol, modifiers
    pressed = (name, mods_of(modifiers))
    shift = modifiers & key.MOD_SHIFT
    live = [a for a in ACTIONS if a[1] == "global" or a[1] == scope]
    for a in live:
        b = binding(raw, a[0])
        if b != default(a[0]) and pressed == b:
            return to_key(default(a[0]), shift)
    for a in live:
        if binding(raw, a[0]) != default(a[0]) and pressed == default(a[0]):
            return None
    return symbol, modifiers
