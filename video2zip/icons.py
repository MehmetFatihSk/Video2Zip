"""SF Symbols tarzı ikonlar — Pillow ile runtime'da çizilir.

Tk, SF Symbols'a da SVG'ye de erişemez. Bu yüzden ikonlar geometrik olarak
4x çözünürlükte çizilip küçültülür: Retina'da net, tema ile birlikte renk
değiştirebilen, tek tip (1.6px stroke, yuvarlak uç) bir set.

Her ikon açık ve koyu mod için ayrı renkte üretilip tek bir CTkImage'e
konur; appearance mode değişince CustomTkinter doğru olanı kendisi gösterir.
"""

from __future__ import annotations

from typing import Callable

from PIL import Image, ImageDraw

SS = 4        # supersampling
GRID = 24.0   # tasarım ızgarası (SF Symbols gibi 24pt)
STROKE = 1.6


def _new() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    size = int(GRID * SS)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _box(*vals: float) -> list[float]:
    return [v * SS for v in vals]


def _stroke(d: ImageDraw.ImageDraw, points: list[tuple[float, float]],
            color: str, width: float = STROKE, cap: bool = True) -> None:
    """Yuvarlak uçlu çizgi — PIL'de line-cap olmadığı için uçlara daire konur."""
    w = width * SS
    pts = [(x * SS, y * SS) for x, y in points]
    d.line(pts, fill=color, width=int(round(w)), joint="curve")
    if cap:
        r = w / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse([x - r, y - r, x + r, y + r], fill=color)


# ------------------------------------------------------------ glyph defs ---
def _film(d: ImageDraw.ImageDraw, c: str) -> None:
    d.rounded_rectangle(_box(2.5, 5, 21.5, 19), radius=3 * SS,
                        outline=c, width=int(STROKE * SS))
    for y in (8.0, 12.0, 16.0):
        d.ellipse(_box(5.4, y - 0.75, 6.9, y + 0.75), fill=c)
        d.ellipse(_box(17.1, y - 0.75, 18.6, y + 0.75), fill=c)


def _folder(d: ImageDraw.ImageDraw, c: str) -> None:
    _stroke(d, [(3, 19), (3, 6), (9.5, 6), (11.5, 8.5), (21, 8.5), (21, 19), (3, 19)], c)


def _download(d: ImageDraw.ImageDraw, c: str) -> None:
    _stroke(d, [(12, 3.5), (12, 15)], c)
    _stroke(d, [(7.5, 10.8), (12, 15.3), (16.5, 10.8)], c)
    _stroke(d, [(4.5, 15.5), (4.5, 20), (19.5, 20), (19.5, 15.5)], c)


def _close(d: ImageDraw.ImageDraw, c: str) -> None:
    _stroke(d, [(7, 7), (17, 17)], c)
    _stroke(d, [(17, 7), (7, 17)], c)


def _check(d: ImageDraw.ImageDraw, c: str) -> None:
    _stroke(d, [(5.5, 12.5), (10, 17), (18.5, 7)], c, width=STROKE + 0.3)


def _reveal(d: ImageDraw.ImageDraw, c: str) -> None:
    _stroke(d, [(13.5, 4), (20, 4), (20, 10.5)], c)
    _stroke(d, [(20, 4), (12, 12)], c)
    _stroke(d, [(17, 14.5), (17, 20), (4, 20), (4, 7), (9.5, 7)], c)


def _sun(d: ImageDraw.ImageDraw, c: str) -> None:
    d.ellipse(_box(8.4, 8.4, 15.6, 15.6), outline=c, width=int(STROKE * SS))
    for x1, y1, x2, y2 in ((12, 2.5, 12, 5.2), (12, 18.8, 12, 21.5),
                           (2.5, 12, 5.2, 12), (18.8, 12, 21.5, 12),
                           (5.4, 5.4, 7.3, 7.3), (16.7, 16.7, 18.6, 18.6),
                           (18.6, 5.4, 16.7, 7.3), (7.3, 16.7, 5.4, 18.6)):
        _stroke(d, [(x1, y1), (x2, y2)], c, width=STROKE - 0.1)


def _moon(d: ImageDraw.ImageDraw, c: str) -> None:
    # hilal: dolu daireden kaydırılmış daireyi çıkar
    size = int(GRID * SS)
    layer = Image.new("L", (size, size), 0)
    ld = ImageDraw.Draw(layer)
    ld.ellipse(_box(3.5, 3.5, 20.5, 20.5), fill=255)
    ld.ellipse(_box(8.5, 0.5, 25.5, 17.5), fill=0)
    d.bitmap((0, 0), layer, fill=c)


def _video_large(d: ImageDraw.ImageDraw, c: str) -> None:
    """Boş durum için: film şeridi + oynatma üçgeni."""
    d.rounded_rectangle(_box(2, 4.5, 22, 19.5), radius=3.5 * SS,
                        outline=c, width=int((STROKE - 0.2) * SS))
    _stroke(d, [(2, 8.6), (22, 8.6)], c, width=STROKE - 0.4, cap=False)
    _stroke(d, [(2, 15.4), (22, 15.4)], c, width=STROKE - 0.4, cap=False)
    d.polygon(_pts_poly([(10.4, 10.2), (15.2, 12.0), (10.4, 13.8)]), fill=c)


def _pts_poly(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(x * SS, y * SS) for x, y in points]


_GLYPHS: dict[str, Callable[[ImageDraw.ImageDraw, str], None]] = {
    "film": _film,
    "folder": _folder,
    "download": _download,
    "close": _close,
    "check": _check,
    "reveal": _reveal,
    "sun": _sun,
    "moon": _moon,
    "video-large": _video_large,
}


def render(name: str, color: str, size: int) -> Image.Image:
    img, d = _new()
    _GLYPHS[name](d, color)
    return img.resize((size, size), Image.LANCZOS)


class IconSet:
    """CTkImage üretir ve önbelleğe alır (açık + koyu varyant birlikte)."""

    def __init__(self) -> None:
        self._cache: dict[tuple, object] = {}

    def get(self, name: str, size: int, colors):
        """colors: (açık_mod_rengi, koyu_mod_rengi) çifti ya da tek renk."""
        import customtkinter as ctk

        if isinstance(colors, str):
            colors = (colors, colors)
        key = (name, size, colors)
        if key not in self._cache:
            self._cache[key] = ctk.CTkImage(
                light_image=render(name, colors[0], size * 2),
                dark_image=render(name, colors[1], size * 2),
                size=(size, size),
            )
        return self._cache[key]
