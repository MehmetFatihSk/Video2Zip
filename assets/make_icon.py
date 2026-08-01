#!/usr/bin/env python3
"""Uygulama ikonunu dosyaya yazar: AppIcon.png (1024) + AppIcon.icns.

Çizim mantığı `video2zip/appicon.py` içindedir — arayüzün başlığında
görünen logo ile aynı kaynaktır. Bu betik yalnızca dosyaya döker.

Çalıştır:  ./.venv/bin/python assets/make_icon.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PIL import Image                       # noqa: E402
from video2zip.appicon import render        # noqa: E402

ICNS_SIZES = (16, 32, 128, 256, 512)


def write_icns(icon: Image.Image, out_dir: str) -> str | None:
    if not shutil.which("iconutil"):
        print("iconutil bulunamadı — .icns atlandı (Xcode CLT gerekir)")
        return None

    iconset = os.path.join(out_dir, "AppIcon.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    for base in ICNS_SIZES:
        icon.resize((base, base), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{base}x{base}.png"))
        icon.resize((base * 2, base * 2), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{base}x{base}@2x.png"))

    icns = os.path.join(out_dir, "AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return icns


def main() -> int:
    icon = render(1024)
    png = os.path.join(HERE, "AppIcon.png")
    icon.save(png)
    print("yazıldı:", png)

    icns = write_icns(icon, HERE)
    if icns:
        print("yazıldı:", icns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
