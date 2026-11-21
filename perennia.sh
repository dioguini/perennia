#!/usr/bin/env bash
# Perennia — abre a aplicação sem o PyCharm (macOS, Linux, Raspberry Pi).
#
#   ./perennia.sh            (ou duplo clique, se o teu gestor de ficheiros o permitir)
#
# Usa o ambiente virtual do projeto (.venv ou venv); sem ele, o python3 do sistema.
cd "$(dirname "$0")" || exit 1
for py in .venv/bin/python venv/bin/python; do
  if [ -x "$py" ]; then exec "$py" main.py "$@"; fi
done
exec python3 main.py "$@"
