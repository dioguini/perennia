#!/usr/bin/env bash
# Perennia — cria a versão para partilhar (macOS, Linux, Raspberry Pi).
#
#   ./build.sh
#
# Corre no sistema para o qual queres a versão: no Mac sai uma app para Mac,
# no Raspberry Pi uma para Raspberry Pi. No fim fica um .zip ou .tar.gz em dist/.
set -euo pipefail
cd "$(dirname "$0")"

echo "== Perennia: a criar o executável =="
PY="${PYTHON:-python3}"
if [ ! -d .build-venv ]; then
  echo "[1/5] A criar um ambiente só para o build..."
  "$PY" -m venv .build-venv
fi
# shellcheck disable=SC1091
source .build-venv/bin/activate

echo "[2/5] A instalar as bibliotecas e o PyInstaller..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt pyinstaller

echo "[3/5] A confirmar que o núcleo funciona..."
python main.py --self-test

echo "[4/5] A empacotar..."
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/perennia.spec

echo "[5/5] A criar o arquivo..."
if [ "$(uname)" = "Darwin" ]; then
  APP="dist/Perennia.app"
  # as pastas de exemplo ficam ao lado da app, dentro de uma pasta comum
  rm -rf dist/Perennia-mac && mkdir -p dist/Perennia-mac
  cp -R "$APP" dist/Perennia-mac/
  cp -R gpx workouts dist/Perennia-mac/
  cp packaging/LEIA-ME.txt dist/Perennia-mac/
  (cd dist && ditto -c -k --keepParent Perennia-mac Perennia-mac.zip)
  echo "Pronto: dist/Perennia-mac.zip"
else
  cp -R gpx workouts dist/Perennia/
  cp packaging/LEIA-ME.txt dist/Perennia/
  ARCH="$(uname -m)"
  tar -C dist -czf "dist/Perennia-linux-$ARCH.tar.gz" Perennia
  echo "Pronto: dist/Perennia-linux-$ARCH.tar.gz"
fi
