#!/usr/bin/env bash
# Perennia — instalação num computador novo (macOS, Linux, Raspberry Pi).
#
#   ./perennia_setup.sh            (ou: bash perennia_setup.sh)
#
# Cria o ambiente virtual (.venv), instala os requisitos e corre «main.py --setup»: a pasta
# data/ com a base de dados (treinos de base, exercícios do ginásio, métricas…), os ficheiros
# modelo, o autoteste e, se quiseres, o GarminDB e o atalho. Pode correr-se outra vez: o que já
# existe fica como está.
#
# Python: usa o mais recente que encontrar. A Perennia precisa do 3.11+; o GarminDB precisa do
# 3.12+ (o GarminDB 3.x já não funciona). Se o .venv for de um Python antigo e houver um 3.12+,
# o .venv antigo fica guardado em .venv-antigo e cria-se um novo.
set -e
cd "$(dirname "$0")"

ver_ok() {   # $1 = python, $2 = mínimo (ex.: 12) — 0 se for 3.$2 ou mais recente
  "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, $2) else 1)" 2>/dev/null
}

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.14 python3.13 python3.12 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && ver_ok "$c" 12; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then
  for c in python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1 && ver_ok "$c" 11; then PY="$c"; break; fi
  done
  if [ -n "$PY" ]; then
    echo "Aviso: só encontrei o Python $("$PY" --version 2>&1 | cut -d' ' -f2). A Perennia funciona,"
    echo "  mas o GarminDB precisa do Python 3.12 ou mais recente (python.org)."
  fi
fi
if [ -z "$PY" ]; then
  echo "Não encontrei o Python 3.11+ (recomendado: 3.12 ou mais recente). Instala-o"
  echo "  (https://www.python.org/downloads/ ou, no Linux, sudo apt install python3 python3-venv)"
  echo "  e corre este script outra vez."
  exit 1
fi

if [ -x .venv/bin/python ] && ! ver_ok .venv/bin/python 12 && ver_ok "$PY" 12; then
  echo "O .venv usa o Python $(.venv/bin/python --version 2>&1 | cut -d' ' -f2); passo para o"
  echo "  $("$PY" --version 2>&1) (o GarminDB precisa do 3.12+). O antigo fica em .venv-antigo."
  rm -rf .venv-antigo
  mv .venv .venv-antigo
fi
if [ ! -x .venv/bin/python ]; then
  echo "A criar o ambiente virtual (.venv) com o $("$PY" --version 2>&1)…"
  "$PY" -m venv .venv || {
    echo "Não consegui criar o .venv. No Linux: sudo apt install python3-venv"; exit 1; }
fi
echo "A instalar os requisitos (requirements.txt)…"
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt
chmod +x perennia.sh 2>/dev/null || true

exec .venv/bin/python main.py --setup "$@"
