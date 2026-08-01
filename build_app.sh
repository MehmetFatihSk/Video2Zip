#!/usr/bin/env bash
# Video2Zip — bağımsız .app paketi üretir (Uygulamalar klasörüne atılabilir)
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="Video2Zip"
BUNDLE="${APP_NAME}.app"
CONTENTS="${BUNDLE}/Contents"
RES="${CONTENTS}/Resources"

echo "▸ ${BUNDLE} hazırlanıyor"
rm -rf "${BUNDLE}"
mkdir -p "${CONTENTS}/MacOS" "${RES}/app"

# 1) ikon ----------------------------------------------------------------
if [ ! -f assets/AppIcon.icns ]; then
  echo "▸ ikon üretiliyor"
  ./.venv/bin/python assets/make_icon.py >/dev/null
fi
cp assets/AppIcon.icns "${RES}/AppIcon.icns"

# 2) kaynak kod ----------------------------------------------------------
cp main.py "${RES}/app/"
cp -R video2zip "${RES}/app/"
rm -rf "${RES}/app/video2zip/__pycache__"

# 3) bağımlılıklar -------------------------------------------------------
# Bundle kendi kütüphanelerini taşır; proje klasörü silinse de çalışır.
PYVER="$(python3 -c 'import sys;print(f"python{sys.version_info.major}.{sys.version_info.minor}")')"
if [ -d ".venv/lib/${PYVER}/site-packages" ]; then
  echo "▸ mevcut .venv kütüphaneleri paketleniyor"
  mkdir -p "${RES}/lib"
  cp -R ".venv/lib/${PYVER}/site-packages/." "${RES}/lib/"
else
  echo "▸ bağımlılıklar kuruluyor"
  python3 -m pip install -q --target "${RES}/lib" -r requirements.txt
fi
find "${RES}/lib" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# 4) Python ikilisi ------------------------------------------------------
# venv/bin/python yalnızca bir sapdır (stub) ve çalışınca kendini
# Python.framework'e devreder — o zaman macOS uygulamayı "Python" sanır.
# Framework'ün GUI ikilisini doğrudan Contents/MacOS içine kopyalarsak
# süreç .app'in içinde kalır: Dock'ta doğru ad ve ikon görünür.
BASE_PREFIX="$(python3 -c 'import sys;print(sys.base_prefix)')"
GUI_PY="${BASE_PREFIX}/Resources/Python.app/Contents/MacOS/Python"
if [ ! -x "${GUI_PY}" ]; then
  GUI_PY="$(python3 -c 'import os,sys;print(os.path.realpath(sys.executable))')"
  echo "  (framework GUI ikilisi yok, normal ikili kullanılıyor)"
fi
# İkilinin *adı* macOS'un süreç listesinde görünen addır; bu yüzden
# doğrudan uygulama adını taşır. Başlatıcı ayrı bir adla (launch) durur.
cp "${GUI_PY}" "${CONTENTS}/MacOS/${APP_NAME}"
chmod +x "${CONTENTS}/MacOS/${APP_NAME}"

# 5) başlatıcı -----------------------------------------------------------
cat > "${CONTENTS}/MacOS/launch" <<LAUNCHER
#!/bin/bash
HERE="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
RES="\$(cd "\${HERE}/../Resources" && pwd)"
export PYTHONPATH="\${RES}/lib"
export PYTHONNOUSERSITE=1
exec "\${HERE}/${APP_NAME}" "\${RES}/app/main.py" "\$@"
LAUNCHER
chmod +x "${CONTENTS}/MacOS/launch"

# 6) Info.plist ----------------------------------------------------------
cat > "${CONTENTS}/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.local.video2zip</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>launch</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundleDocumentTypes</key>
    <array>
      <dict>
        <key>CFBundleTypeName</key>
        <string>Video</string>
        <key>CFBundleTypeRole</key>
        <string>Viewer</string>
        <key>LSHandlerRank</key>
        <string>Alternate</string>
        <key>LSItemContentTypes</key>
        <array>
          <string>public.movie</string>
          <string>public.video</string>
          <string>com.apple.quicktime-movie</string>
          <string>public.mpeg-4</string>
        </array>
      </dict>
    </array>
</dict>
</plist>
EOF

# 7) imza ----------------------------------------------------------------
echo "▸ ad-hoc imzalanıyor (Apple Developer hesabı gerekmez)"
xattr -cr "${BUNDLE}" 2>/dev/null || true
codesign --force --deep --sign - "${BUNDLE}" 2>/dev/null || \
  echo "  (imzalama atlandı — uygulama yine çalışır)"

SIZE="$(du -sh "${BUNDLE}" | cut -f1)"
echo
echo "✓ Hazır: ${BUNDLE}  (${SIZE})"
echo "  Uygulamalar klasörüne kopyalamak için:"
echo "      cp -R \"$(pwd)/${BUNDLE}\" /Applications/"
