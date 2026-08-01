#!/usr/bin/env python3
"""Video2Zip uygulama ikonu üretici.

macOS Big Sur+ ikon dilini takip eder:
  · 1024×1024 tuval, görsel alan ortada 824×824
  · Apple'ın "squircle" formu (dairesel köşe değil, süperelips)
  · Yumuşak alt gölge, diyagonal gradyan, tek beyaz sembol
  · Sembol: film şeridi + aşağı ok  →  video, paketlenip indiriliyor

Çıktı:  assets/AppIcon.png, assets/AppIcon.icns
Çalıştır:  ./.venv/bin/python assets/make_icon.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))

SIZE = 1024
CONTENT = 824                      # Apple ikon şablonundaki görsel alan
MARGIN = (SIZE - CONTENT) // 2
SQUIRCLE_N = 5.0                   # süperelips üssü (Apple'a yakın)

TOP_LEFT = (90, 200, 255)          # #5AC8FF
BOTTOM_RIGHT = (94, 92, 230)       # #5E5CE6 (systemIndigo)


# ------------------------------------------------------------------ form ---
def squircle_mask(size: int, n: float = SQUIRCLE_N, ss: int = 4) -> Image.Image:
    """Süperelips maskesi — PIL'in dairesel köşesi yerine Apple formu."""
    s = size * ss
    yy, xx = np.mgrid[0:s, 0:s]
    c = (s - 1) / 2.0
    inside = (np.abs((xx - c) / c) ** n + np.abs((yy - c) / c) ** n) <= 1.0
    mask = Image.fromarray((inside * 255).astype(np.uint8), "L")
    return mask.resize((size, size), Image.LANCZOS)


def diagonal_gradient(size: int, top_left, bottom_right) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size]
    t = ((xx + yy) / (2.0 * (size - 1)))[..., None]
    a = np.array(top_left, dtype=float)
    b = np.array(bottom_right, dtype=float)
    rgb = (a * (1 - t) + b * t).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


# ---------------------------------------------------------------- sembol ---
def draw_symbol(size: int) -> Image.Image:
    """Beyaz film şeridi + aşağı ok. Koordinatlar 824'lük alana göre."""
    ss = 4
    s = size * ss
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k = s / 824.0                                  # ölçek çarpanı

    def px(*v):
        return [x * k for x in v]

    white = (255, 255, 255, 255)
    stroke = int(round(34 * k))

    # film şeridi çerçevesi
    d.rounded_rectangle(px(136, 166, 688, 562), radius=64 * k,
                        outline=white, width=stroke)

    # kenar delikleri (her yanda üç adet)
    for cy in (252, 364, 476):
        d.rounded_rectangle(px(192, cy - 26, 246, cy + 26), radius=14 * k, fill=white)
        d.rounded_rectangle(px(578, cy - 26, 632, cy + 26), radius=14 * k, fill=white)

    # ortadaki aşağı ok — gövde
    d.rounded_rectangle(px(388, 238, 436, 404), radius=24 * k, fill=white)
    # ok başı
    d.polygon([(330 * k, 376 * k), (494 * k, 376 * k), (412 * k, 486 * k)], fill=white)

    # arşiv tepsisi (şeridin altında, "paketlendi" göstergesi)
    d.rounded_rectangle(px(232, 616, 592, 658), radius=21 * k, fill=white)

    return layer.resize((size, size), Image.LANCZOS)


# ------------------------------------------------------------------ ikon ---
def build_icon() -> Image.Image:
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    mask = squircle_mask(CONTENT)

    # gölge — formun bulanık, aşağı kaydırılmış kopyası
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    tint = Image.new("RGBA", (CONTENT, CONTENT), (0, 0, 0, 90))
    shadow.paste(tint, (MARGIN, MARGIN + int(CONTENT * 0.022)), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(CONTENT * 0.028))
    icon = Image.alpha_composite(icon, shadow)

    # gövde
    body = diagonal_gradient(CONTENT, TOP_LEFT, BOTTOM_RIGHT).convert("RGBA")

    # üstte hafif parlaklık (macOS ikonlarındaki yumuşak ışık)
    gloss = Image.new("L", (CONTENT, CONTENT), 0)
    gd = ImageDraw.Draw(gloss)
    gd.ellipse([-CONTENT * 0.35, -CONTENT * 0.75,
                CONTENT * 1.35, CONTENT * 0.42], fill=46)
    body = Image.composite(Image.new("RGBA", body.size, (255, 255, 255, 255)),
                           body, gloss)

    body.putalpha(mask)
    icon.paste(body, (MARGIN, MARGIN), body)

    # sembol
    symbol = draw_symbol(CONTENT)
    icon.paste(symbol, (MARGIN, MARGIN), symbol)
    return icon


# ------------------------------------------------------------------ icns ---
def write_icns(icon: Image.Image, out_dir: str) -> str | None:
    if not shutil.which("iconutil"):
        print("iconutil bulunamadı — .icns atlandı (Xcode CLT gerekir)")
        return None

    iconset = os.path.join(out_dir, "AppIcon.iconset")
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)

    for base in (16, 32, 128, 256, 512):
        icon.resize((base, base), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{base}x{base}.png"))
        icon.resize((base * 2, base * 2), Image.LANCZOS).save(
            os.path.join(iconset, f"icon_{base}x{base}@2x.png"))

    icns = os.path.join(out_dir, "AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return icns


def main() -> int:
    icon = build_icon()
    png = os.path.join(HERE, "AppIcon.png")
    icon.save(png)
    print("yazıldı:", png)

    icns = write_icns(icon, HERE)
    if icns:
        print("yazıldı:", icns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
