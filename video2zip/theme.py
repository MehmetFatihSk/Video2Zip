"""Design tokens — macOS native görünüm.

Özel marka paleti yok: SwiftUI'nin semantic renklerinin (labelColor,
secondaryLabelColor, separatorColor, controlAccentColor …) Tk karşılıkları
kullanılır. Her token bir **(açık, koyu)** çiftidir; CustomTkinter appearance
mode değiştiğinde doğru olanı kendisi seçer, tek satır kod gerekmez.
"""

from __future__ import annotations

import tkinter.font as tkfont

Pair = tuple[str, str]

# ------------------------------------------------------------- yüzeyler ----
WINDOW: Pair = ("#ECECEC", "#1E1E1E")      # windowBackgroundColor
SURFACE: Pair = ("#FFFFFF", "#2C2C2E")     # controlBackgroundColor
SURFACE_ALT: Pair = ("#F2F2F7", "#252527")
FIELD: Pair = ("#FFFFFF", "#3A3A3C")       # textBackgroundColor
HOVER: Pair = ("#E9E9ED", "#3A3A3C")       # etkin metin rengi %6 opaklıkta
PRESSED: Pair = ("#DEDEE3", "#48484A")

DIVIDER: Pair = ("#D6D6DA", "#3A3A3C")     # separatorColor
BORDER: Pair = ("#C9C9CC", "#48484A")

# --------------------------------------------------------------- metin -----
TEXT: Pair = ("#000000", "#FFFFFF")        # labelColor
TEXT_2: Pair = ("#6E6E73", "#98989D")      # secondaryLabelColor
TEXT_3: Pair = ("#8E8E93", "#7C7C80")      # tertiaryLabelColor
TEXT_OFF: Pair = ("#B4B4B9", "#5A5A5E")    # disabled

# -------------------------------------------------------------- vurgu ------
ACCENT: Pair = ("#007AFF", "#0A84FF")      # controlAccentColor
ACCENT_HOVER: Pair = ("#0068D9", "#3D9BFF")
ON_ACCENT: Pair = ("#FFFFFF", "#FFFFFF")

SUCCESS: Pair = ("#248A3D", "#30D158")
WARNING: Pair = ("#B25000", "#FF9F0A")
DANGER: Pair = ("#D70015", "#FF453A")

TRACK: Pair = ("#D3D3D8", "#48484A")       # slider yolu

# ------------------------------------------------------------- spacing -----
SP_1, SP_2, SP_3, SP_4, SP_5, SP_6, SP_7 = 4, 6, 8, 10, 12, 16, 20

# -------------------------------------------------------------- radius -----
R_FIELD = 6
R_CARD = 8      # kart ve satır köşesi
R_PILL = 999


def side(pair: Pair, mode: str) -> str:
    """Bir token çiftinden tek renk seç ('light' | 'dark')."""
    return pair[0] if mode.lower() == "light" else pair[1]


# ---------------------------------------------------------- tipografi ------
class Fonts:
    """Sistem fontundan (.AppleSystemUIFont) türetilen ölçek.

    Tk'nin bildirdiği TkDefaultFont boyutu baz alınır; böylece kullanıcının
    sistem metin boyutu ayarına uyum sağlanır ve macOS'un kendi tipografik
    ölçeğine (headline / body / callout / caption) karşılık gelir.
    """

    def __init__(self) -> None:
        import customtkinter as ctk

        default = tkfont.nametofont("TkDefaultFont")
        family = default.actual("family")          # '.AppleSystemUIFont'
        base = int(default.actual("size")) or 10   # macOS'ta ~10pt

        try:
            mono = tkfont.nametofont("TkFixedFont").actual("family")
        except Exception:
            mono = "Menlo"

        self.title = ctk.CTkFont(family=family, size=base + 5, weight="bold")
        self.headline = ctk.CTkFont(family=family, size=base + 1, weight="bold")
        self.body = ctk.CTkFont(family=family, size=base)
        self.body_bold = ctk.CTkFont(family=family, size=base, weight="bold")
        self.callout = ctk.CTkFont(family=family, size=base - 1)
        self.caption = ctk.CTkFont(family=family, size=base - 2)
        self.section = ctk.CTkFont(family=family, size=base - 2, weight="bold")
        self.mono = ctk.CTkFont(family=mono, size=base - 1)
        self.mono_bold = ctk.CTkFont(family=mono, size=base - 1, weight="bold")
        self.percent = ctk.CTkFont(family=mono, size=base + 2, weight="bold")
