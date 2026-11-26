#!/usr/bin/env bash
# Perennia — instalação num computador novo (macOS, Linux, Raspberry Pi).
#
#   ./perennia_setup.sh            (ou: bash perennia_setup.sh)
#
# Cria o ambiente virtual (.venv), instala os requisitos e corre «main.py --setup»: a pasta
# data/ com a base de dados (treinos de base, exercícios do ginásio, métricas…), os ficheiros
# modelo, o autoteste e, se quiseres, o GarminDB e o atalho. Pode correr-se outra vez: o que já
# existe fica como está. Precisa do Python 3.11 ou mais recente.
set -e
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "Não encontrei o Python 3. Instala-o (https://www.python.org/downloads/ ou, no Linux,"
  echo "  sudo apt install python3 python3-venv) e corre este script outra vez."
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "O Python encontrado ($("$PY" --version 2>&1)) é antigo: a Perennia precisa do 3.11+."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "A criar o ambiente virtual (.venv)…"
  "$PY" -m venv .venv || {
    echo "Não consegui criar o .venv. No Linux: sudo apt install python3-venv"; exit 1; }
fi
echo "A instalar os requisitos (requirements.txt)…"
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt
chmod +x perennia.sh 2>/dev/null || true

exec .venv/bin/python main.py --setup "$@"
