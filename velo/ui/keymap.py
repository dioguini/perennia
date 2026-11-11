"""Atalhos de teclado personalizáveis (Definições → Atalhos de teclado).

Cada atalho é uma **ação** com um **âmbito** (qualquer ecrã, a sessão de
ciclismo, a de remo…) e uma tecla de origem. Quem quiser muda a tecla; fica
guardado em `keymap` ({ação: [tecla, [modificadores]]}).

Os ecrãs continuam a ouvir as teclas de origem: à entrada, a aplicação traduz
a tecla nova na de origem (`translate`), e a de origem, se foi trocada, deixa
de fazer essa ação nesse âmbito. As teclas de navegação (setas, Enter, Esc,
Tab…) são fixas.

**Sessões de treino.** As ações que existem em *todos* os desportos — marcar volta,
pausa/retomar, terminar, começar sem contagem e saltar bloco — são uma só definição (âmbito
`session`) que vale no ciclismo, na corrida, na natação, no remo e no ginásio. Só as que fazem
sentido num desporto ficam no âmbito dele: a resistência (ciclismo e remo), a velocidade e o
declive (corrida).
"""
from __future__ import annotations

from pyglet.window import key

from velo.core import shortcuts
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
    # as cinco de qualquer sessão de treino (todos os desportos)
    ("lap", "session", "L", (), "Marcar volta", "Mark a lap"),
    ("pause", "session", "P", (), "Pausa / retomar", "Pause / resume"),
    ("finish", "session", "F10", (), "Terminar", "Finish"),
    ("start_now", "session", "SPACE", (), "Começar sem contagem", "Start without countdown"),
    ("skip_block", "session", "N", (), "Saltar bloco", "Skip block"),
    # ciclismo
    ("ride_res_up", "ride", "PLUS", (), "Aumentar resistência", "Increase resistance"),
    ("ride_res_down", "ride", "MINUS", (), "Diminuir resistência", "Decrease resistance"),
    # remo
    ("row_res_up", "rowing", "PLUS", (), "Aumentar resistência", "Increase resistance"),
    ("row_res_down", "rowing", "MINUS", (), "Diminuir resistência", "Decrease resistance"),
    ("row_fields", "rowing", "V", (), "Outra página de campos", "Next page of fields"),
    # corrida (na natação, + e − são as piscinas)
    ("speed_up", "endurance", "PLUS", (), "Corrida: aumentar velocidade (natação: + piscina)",
     "Running: increase speed (swimming: + length)"),
    ("speed_down", "endurance", "MINUS", (), "Corrida: diminuir velocidade (natação: − piscina)",
     "Running: decrease speed (swimming: − length)"),
    ("incline_up", "endurance", "UP", (), "Corrida: aumentar declive", "Running: increase incline"),
    ("incline_down", "endurance", "DOWN", (), "Corrida: diminuir declive",
     "Running: decrease incline"),
    ("run_total", "endurance", "T", (), "Corrida: escrever o total do visor",
     "Running: type the display total"),
    ("bld_dup", "builder", "D", (), "Duplicar o bloco", "Duplicate the block"),
    ("route_fav", "routes", "F", (), "Rota favorita", "Favourite route"),
    ("cal_today", "calendar", "T", (), "Calendário: hoje", "Calendar: today"),
)

# Nas versões anteriores cada desporto tinha as suas: o que o atleta já tinha mudado passa para a
# definição única (ver velo/core/shortcuts.py, que também arruma a base e os backups antigos).
LEGACY = shortcuts.LEGACY

# As teclas que cada ação ouve de origem (o `+` também é `=` e `Num +`…): ao mudar a ação, todas
# deixam de a fazer.
ALIASES = {"ride_res_up": ("PLUS", "EQUAL", "NUM_ADD", "UP"),
           "ride_res_down": ("MINUS", "NUM_SUBTRACT", "DOWN"),
           "row_res_up": ("PLUS", "EQUAL", "NUM_ADD", "PAGEUP"),
           "row_res_down": ("MINUS", "NUM_SUBTRACT", "PAGEDOWN"),
           "speed_up": ("PLUS", "EQUAL", "NUM_ADD"),
           "speed_down": ("MINUS", "NUM_SUBTRACT")}

# Os âmbitos das sessões de treino: as ações do âmbito `session` valem em todos.
SESSION_SCOPES = ("ride", "rowing", "endurance", "gym")

SCOPES = (("global", "Em qualquer ecrã", "On any screen"),
          ("session", "Sessões de treino (todos os desportos)", "Workouts (all sports)"),
          ("ride", "Sessão de ciclismo", "Cycling session"),
          ("rowing", "Sessão de remo", "Rowing session"),
          ("endurance", "Corrida e natação", "Running and swimming"),
          ("builder", "Construtor de treinos", "Workout builder"),
          ("routes", "Rotas e segmentos", "Routes and segments"),
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
# + − e as setas: só nas ações de um desporto (resistência, velocidade, declive)
EXTRA = ("PLUS", "EQUAL", "MINUS", "NUM_ADD", "NUM_SUBTRACT", "UP", "DOWN", "PAGEUP", "PAGEDOWN")
EXTRA_SCOPES = ("ride", "rowing", "endurance")
RESERVED_GLOBAL = ("J", "K", "SPACE")         # navegam nas listas: só com Ctrl/Alt
RESERVED_SESSION = ("J", "K")                 # mudam de linha no ginásio

PRETTY = {"PLUS": "+", "EQUAL": "=", "MINUS": "−", "NUM_ADD": "Num +", "NUM_SUBTRACT": "Num −",
          "UP": "↑", "DOWN": "↓", "PAGEUP": "Pg↑", "PAGEDOWN": "Pg↓"}

_BY_ID = {a[0]: a for a in ACTIONS}


def default(action: str) -> tuple[str, tuple[str, ...]]:
    a = _BY_ID[action]
    return a[2], tuple(a[3])


def label(action: str) -> str:
    a = _BY_ID[action]
    return tr(a[4], a[5])


def custom_map(raw) -> dict:
    """O que está guardado, limpo: só ações conhecidas e teclas válidas. As definições antigas
    (uma por desporto) passam para a única de agora."""
    out = {}
    items = shortcuts.migrate(dict(raw or {}))
    for k, v in items.items():
        if k in _BY_ID and isinstance(v, (list, tuple)) and v and (
                v[0] in NAMES or (v[0] in EXTRA and _BY_ID[k][1] in EXTRA_SCOPES)):
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
    shown = tr("Espaço", "Space") if name == "SPACE" else PRETTY.get(name, name)
    pre = "".join({"ctrl": "Ctrl+", "alt": "Alt+"}[m] for m in sorted(mods))
    return pre + shown


def name_of(symbol: int, extra: bool = False) -> str | None:
    """O nome da tecla (A–Z, F1–F12, Espaço; com `extra`, também + − e as setas)."""
    for n in NAMES + (EXTRA if extra else ()):
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


def _scopes_of(scope: str) -> list[str]:
    """Os âmbitos cujas teclas se podem confundir com as de `scope`."""
    if scope == "global":
        return [s for s, _p, _e in SCOPES] + ["gym"]
    if scope == "session":
        return ["global", "session", *SESSION_SCOPES]
    if scope in SESSION_SCOPES:
        return [scope, "session", "global"]
    return [scope, "global"]


def conflict(raw, action: str, b: tuple[str, tuple[str, ...]]) -> str | None:
    """A ação que já usa esta tecla no mesmo âmbito (ou em qualquer ecrã)."""
    scopes = _scopes_of(_BY_ID[action][1])
    for other in ACTIONS:
        if other[0] != action and other[1] in scopes and binding(raw, other[0]) == b:
            return other[0]
    return None


def problem(raw, action: str, b: tuple[str, tuple[str, ...]]) -> str | None:
    """Porque é que esta tecla não pode ser o atalho (None: pode)."""
    name, mods = b
    scope = _BY_ID[action][1]
    if scope == "global" and name in RESERVED_GLOBAL and not mods:
        return tr("{k} navega nas listas: em qualquer ecrã só com Ctrl ou Alt",
                  "{k} moves in lists: on any screen only with Ctrl or Alt", k=key_text(b))
    if scope == "session" and name in RESERVED_SESSION and not mods:
        return tr("{k} muda de linha no ginásio: usa outra tecla ou Ctrl/Alt",
                  "{k} changes row in the gym: use another key or Ctrl/Alt", k=key_text(b))
    if name in EXTRA and (scope not in EXTRA_SCOPES or mods):
        return tr("{k} só serve para a resistência, a velocidade e o declive",
                  "{k} is only for resistance, speed and incline", k=key_text(b))
    other = conflict(raw, action, b)
    if other is not None:
        return tr("{k} já é «{a}»", "{k} is already «{a}»", k=key_text(b), a=label(other))
    return None


def _live(scope: str | None) -> list[tuple]:
    """As ações em vigor neste ecrã: as de qualquer ecrã, as do âmbito e — se for uma sessão de
    treino — as que valem em todos os desportos."""
    scopes = {"global"}
    if scope is not None:
        scopes.add(scope)
        if scope in SESSION_SCOPES:
            scopes.add("session")
    return [a for a in ACTIONS if a[1] in scopes]


def translate(raw, scope: str | None, symbol: int, modifiers: int):
    """A tecla carregada → a tecla que os ecrãs conhecem. None: não faz nada
    (era a tecla de origem de um atalho que mudou)."""
    custom = custom_map(raw)
    if not custom:
        return symbol, modifiers
    name = name_of(symbol, extra=True)
    if name is None:
        return symbol, modifiers
    pressed = (name, mods_of(modifiers))
    shift = modifiers & key.MOD_SHIFT
    live = _live(scope)
    for a in live:
        b = binding(raw, a[0])
        if b != default(a[0]) and pressed == b:
            return to_key(default(a[0]), shift)
    for a in live:
        if binding(raw, a[0]) != default(a[0]) and not pressed[1] and \
                pressed[0] in ALIASES.get(a[0], (a[2],)) and not a[3]:
            return None
        if binding(raw, a[0]) != default(a[0]) and pressed == default(a[0]):
            return None
    return symbol, modifiers
