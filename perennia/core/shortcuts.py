"""Atalhos de teclado — a parte que não depende da interface (e por isso serve também ao backup).

Até à ronda 14 cada desporto tinha as suas teclas de volta, pausa, terminar e começar
(`ride_lap`, `row_pause`, `gym_finish`, `run_start`…). Agora é uma só definição para todos os
desportos (`lap`, `pause`, `finish`, `start_now`). O que o atleta já tinha mudado passa para a
definição única — na base de dados (ao abrir) e nos backups antigos (ao repor).
"""
from __future__ import annotations

import json

# antigo → único
LEGACY = {"ride_lap": "lap", "row_lap": "lap", "run_lap": "lap",
          "ride_pause": "pause", "row_pause": "pause", "run_pause": "pause",
          "gym_pause": "pause",
          "ride_finish": "finish", "row_finish": "finish", "run_finish": "finish",
          "gym_finish": "finish", "run_start": "start_now"}


def migrate(raw):
    """As definições com os ids de hoje. A primeira antiga que se encontra fica com o lugar;
    uma definição já nova ganha sempre à antiga; os ids antigos saem. Não mexe no resto."""
    if not isinstance(raw, dict):
        return raw
    items = dict(raw)
    for old, new in LEGACY.items():
        if old in items:
            value = items.pop(old)
            items.setdefault(new, value)
    return items


def migrate_db(conn) -> bool:
    """Reescreve na base o `keymap` com os ids antigos. True se mudou alguma coisa."""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'keymap'").fetchone()
        if row is None:
            return False
        raw = json.loads(row[0])
        new = migrate(raw)
        if new == raw:
            return False
        conn.execute("UPDATE settings SET value = ? WHERE key = 'keymap'", (json.dumps(new),))
        return True
    except Exception:
        return False
