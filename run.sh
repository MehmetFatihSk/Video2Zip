#!/usr/bin/env bash
# Video2Zip — uygulamayı başlat
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Sanal ortam yok. Önce ./setup.sh çalıştırın." >&2
  exit 1
fi

exec ./.venv/bin/python main.py
