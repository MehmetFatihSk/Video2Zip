"""Uygulama logosunu kodla üretir — tek kaynak, her boyutta net.

macOS Big Sur+ ikon dilini takip eder:
  · Görsel alan, tuvalin %80'i (Apple şablonu: 1024 içinde 824)
  · Apple'ın "squircle" formu — dairesel köşe değil, süperelips
  · Diyagonal gradyan, üstte yumuşak ışık, altta gölge
  · Tek beyaz sembol: film şeridi + aşağı ok + arşiv tepsisi

Hem `assets/make_icon.py` (1024 px + .icns) hem arayüzün başlığı (24 px)
bu modülü kullanır; ikon iki yerde ayrı ayrı tanımlanmaz.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

GRID = 824.0                       # sembol koordinatlarının referans ızgarası
CONTENT_RATIO = 824.0 / 1024.0     # görsel alanın tuvale oranı
SQUIRCLE_N = 5.0                   # süperelips üssü (Apple formuna yakın)

TOP_LEFT = (90, 200, 255)          # #5AC8FF
BOTTOM_RIGHT = (94, 92, 230)       # #5E5CE6 (systemIndigo)


def _squircle_mask(size: int, ss: int = 4) -> Image.Image:
    """Süperelips maskesi — PIL'in dairesel köşesi yerine Apple formu."""
    s = max(1, size * ss)
    yy, xx = np.mgrid[0:s, 0:s]
    c = (s - 1) / 2.0
    inside = (np.abs((xx - c) / c) ** SQUIRCLE_N
              + np.abs((yy - c) / c) ** SQUIRCLE_N) <= 1.0
    return Image.fromarray((inside * 255).astype(np.uint8), "L").resize(
        (size, size), Image.LANCZOS)


def _diagonal_gradient(size: int) -> Image.Image:
    yy, xx = np.mgrid[0:size, 0:size]
    t = ((xx + yy) / (2.0 * max(1, size - 1)))[..., None]
    a = np.array(TOP_LEFT, dtype=float)
    b = np.array(BOTTOM_RIGHT, dtype=float)
    return Image.fromarray((a * (1 - t) + b * t).astype(np.uint8), "RGB")


def _symbol(size: int, color="#FFFFFF", ss: int = 4) -> Image.Image:
    """Sembol siluetı. Koordinatlar GRID (824) tabanlı, size'a ölçeklenir."""
    s = max(1, size * ss)
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k = s / GRID

    def px(*v):
        return [x * k for x in v]

    white = color
    stroke = max(1, int(round(34 * k)))

    # film şeridi çerçevesi
    d.rounded_rectangle(px(136, 166, 688, 562), radius=64 * k,
                        outline=white, width=stroke)
    # kenar delikleri (her yanda üç adet)
    for cy in (252, 364, 476):
        d.rounded_rectangle(px(192, cy - 26, 246, cy + 26), radius=14 * k, fill=white)
        d.rounded_rectangle(px(578, cy - 26, 632, cy + 26), radius=14 * k, fill=white)
    # aşağı ok: gövde + baş
    d.rounded_rectangle(px(388, 238, 436, 404), radius=24 * k, fill=white)
    d.polygon([(330 * k, 376 * k), (494 * k, 376 * k), (412 * k, 486 * k)], fill=white)
    # arşiv tepsisi
    d.rounded_rectangle(px(232, 616, 592, 658), radius=21 * k, fill=white)

    return layer.resize((size, size), Image.LANCZOS)


def render(size: int = 1024, shadow: bool = True) -> Image.Image:
    """Uygulama ikonunu `size`×`size` RGBA görsel olarak üretir."""
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    content = max(8, round(size * CONTENT_RATIO))
    margin = (size - content) // 2
    mask = _squircle_mask(content)

    if shadow:
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        layer.paste(Image.new("RGBA", (content, content), (0, 0, 0, 90)),
                    (margin, margin + int(content * 0.022)), mask)
        icon = Image.alpha_composite(
            icon, layer.filter(ImageFilter.GaussianBlur(content * 0.028)))

    body = _diagonal_gradient(content).convert("RGBA")

    # üstte yumuşak ışık
    gloss = Image.new("L", (content, content), 0)
    ImageDraw.Draw(gloss).ellipse(
        [-content * 0.35, -content * 0.75, content * 1.35, content * 0.42], fill=46)
    body = Image.composite(Image.new("RGBA", body.size, (255, 255, 255, 255)),
                           body, gloss)
    body.putalpha(mask)
    icon.paste(body, (margin, margin), body)

    symbol = _symbol(content)
    icon.paste(symbol, (margin, margin), symbol)
    return icon


def render_glyph(size: int, color: str = "#FFFFFF") -> Image.Image:
    """Logonun tek renkli, şeffaf zeminli sürümü — menü bar şablon ikonu dili.

    Gradyan gövde ve squircle yok, yalnızca sembolün silueti. Arayüz içinde
    diğer ikonlarla aynı görsel ağırlıkta durur ve temaya göre renklenir.
    Sembol kendi sınırlarına kırpılıp kare tuvale ortalanır; böylece dosya
    ikonundaki kenar boşluğu burada logoyu küçültmez.
    """
    work = max(64, size * 4)
    layer = _symbol(work, color)
    bbox = layer.getbbox()
    if bbox:
        layer = layer.crop(bbox)
    w, h = layer.size
    side = max(w, h, 1)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(layer, ((side - w) // 2, (side - h) // 2), layer)
    return square.resize((size, size), Image.LANCZOS)


def render_tight(size: int) -> Image.Image:
    """Kenar boşluğu ve gölge olmadan yalnızca squircle gövdesi.

    Dosya ikonunda tuvalin %80'ini kullanmak doğru; ama arayüzde 24 px'lik
    bir alana koyarken o boşluk logoyu gereksiz küçültür. Burada tam kenara
    kadar dolu bir sürüm üretilir.
    """
    full = max(8, round(size / CONTENT_RATIO))
    icon = render(full, shadow=False)
    m = (full - size) // 2
    return icon.crop((m, m, m + size, m + size))
