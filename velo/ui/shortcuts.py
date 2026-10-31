"""Definições → Atalhos de teclado: todas as teclas da aplicação, por grupo.

A lista é a mesma que os ecrãs usam; quando se junta uma tecla a um ecrã,
junta-se também aqui (há um teste que confirma as principais).
"""
from __future__ import annotations

from velo.core.i18n import tr
from velo.ui.widgets import Item

# (grupo PT, grupo EN, [(tecla, PT, EN)])
SHORTCUTS = (
    ("Em qualquer ecrã", "On any screen", (
        ("Ctrl+S", "Guardar", "Save"),
        ("Esc", "Voltar (com alterações por guardar, pergunta primeiro)",
         "Back (asks first if there are unsaved changes)"),
        ("↑ ↓  ·  J K", "Mover na lista", "Move in the list"),
        ("Enter  ·  Espaço", "Escolher", "Choose"),
        ("← →", "Mudar o valor da linha", "Change the row's value"),
        ("Shift+← →", "Mudar mais depressa", "Change faster"),
        ("Tab  ·  Shift+Tab", "Separador seguinte / anterior", "Next / previous tab"),
        ("Backspace", "Apagar o que se escreveu", "Delete what you typed"),
        ("Del", "Apagar a linha escolhida (duas vezes)", "Delete the chosen row (twice)"),
        ("F1", "Resumo da página (agente)", "Page summary (agent)"),
        ("F2", "Resumo com contexto (agente)", "Summary with context (agent)"),
        ("F4", "Dispositivos", "Devices"),
        ("F8", "Definições", "Settings"),
        ("F11", "Ecrã inteiro", "Full screen"),
        ("Ctrl+Q", "Sair da Perennia", "Quit Perennia"),
    )),
    ("Sessão de ciclismo", "Cycling session", (
        ("L", "Marcar volta (lap)", "Mark a lap"),
        ("P", "Pausa / retomar", "Pause / resume"),
        ("+ −  ·  ↑ ↓", "Resistência", "Resistance"),
        ("F10", "Terminar e guardar", "Finish and save"),
        ("Esc", "Pausa (não termina)", "Pause (does not finish)"),
        ("Enter · S  /  N · Esc", "Terminar: sim / não", "Finish: yes / no"),
        ("D", "Terminar sem guardar", "Finish without saving"),
    )),
    ("Sessão de remo", "Rowing session", (
        ("L", "Marcar volta", "Mark a lap"),
        ("P", "Pausa / retomar", "Pause / resume"),
        ("+ −  ·  PgUp PgDn", "Resistência da máquina", "Machine resistance"),
        ("V", "Outra página de campos", "Next page of fields"),
        ("Esc  ·  F10", "Terminar", "Finish"),
    )),
    ("Corrida e natação", "Running and swimming", (
        ("Espaço", "Começar", "Start"),
        ("L", "Marcar volta", "Mark a lap"),
        ("P", "Pausa / retomar", "Pause / resume"),
        ("+ −", "Corrida: velocidade (Shift: ×2) · natação: piscina (− corrige)",
         "Running: speed (Shift: ×2) · swimming: length (− corrects)"),
        ("T", "Corrida: escrever o total do visor", "Running: type the display total"),
        ("Esc  ·  F10", "Terminar", "Finish"),
    )),
    ("Ginásio (força e voltas)", "Gym (strength and laps)", (
        ("Espaço", "Série: começar / acabar · voltas: trabalho ↔ descanso",
         "Set: start / end · laps: work ↔ rest"),
        ("P", "Pausa / retomar", "Pause / resume"),
        ("0–9", "Escrever reps, carga, RPE", "Type reps, load, RPE"),
        ("Esc  ·  F10", "Terminar", "Finish"),
    )),
    ("Construtor de treinos (blocos)", "Workout builder (blocks)", (
        ("← →", "Bloco anterior / seguinte", "Previous / next block"),
        ("+ −", "Duração do bloco", "Block duration"),
        ("D", "Duplicar o bloco", "Duplicate the block"),
        ("Del", "Apagar o bloco", "Delete the block"),
        ("Tab", "Vista: potência, FC, RPE, ritmo", "View: power, HR, RPE, pace"),
    )),
    ("Construtor de força", "Strength builder", (
        ("Setas", "Mudar de célula", "Move between cells"),
        ("0–9", "Preencher a célula", "Fill the cell"),
        ("Enter", "Abrir o que está escolhido", "Open the chosen item"),
        ("M", "Menu ⋮ do bloco / exercício", "Block / exercise ⋮ menu"),
        ("Alt+↑ ↓", "Mudar o bloco de sítio", "Move the block"),
    )),
    ("Listas e calendário", "Lists and calendar", (
        ("E", "Treino de ciclismo: exportar · ginásio: editar", "Cycling workout: export · gym: "
         "edit"),
        ("P", "Treino de ciclismo ou remo: editar os passos", "Cycling or rowing workout: edit "
         "the steps"),
        ("F", "Rota favorita", "Favourite route"),
        ("PgUp PgDn  ·  [ ]", "Calendário: mês anterior / seguinte", "Calendar: previous / next "
         "month"),
        ("T", "Calendário: hoje", "Calendar: today"),
        ("R", "Ecrã da sessão: repor (duas vezes)", "Session screen: reset (twice)"),
    )),
)


def items() -> list[Item]:
    rows: list[Item] = []
    for gpt, gen, keys in SHORTCUTS:
        rows.append(Item(f"— {tr(gpt, gen)} —", enabled=False))
        for k, pt, en in keys:
            rows.append(Item(tr(pt, en), value=k, enabled=False))
    return rows
