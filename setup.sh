#!/usr/bin/env bash
# Video2Zip — tek seferlik kurulum (macOS)
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "▸ Python: $($PY --version) — $(command -v "$PY")"

# 1) Tkinter kontrolü ------------------------------------------------------
if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
  VER="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  cat <<EOF

HATA: Bu Python kurulumunda Tkinter yok.
  Homebrew kullanıyorsanız:

      brew install python-tk@${VER}

  Alternatif: python.org'dan resmi Python yükleyicisini kurun
  (Tcl/Tk dahili gelir), sonra bu betiği tekrar çalıştırın.

EOF
  exit 1
fi
echo "▸ Tkinter: OK (Tk $("$PY" -c 'import tkinter; print(tkinter.TkVersion)'))"

# 2) Sanal ortam -----------------------------------------------------------
if [ ! -d .venv ]; then
  echo "▸ Sanal ortam oluşturuluyor (.venv)"
  "$PY" -m venv .venv
fi

# 3) Bağımlılıklar ---------------------------------------------------------
echo "▸ Bağımlılıklar kuruluyor"
./.venv/bin/python -m pip install --upgrade pip --quiet
./.venv/bin/python -m pip install -r requirements.txt --quiet

echo
echo "Kurulum tamam. Uygulamayı başlatmak için:  ./run.sh"
