"""Video2Zip — native macOS masaüstü arayüzü (CustomTkinter).

Native macOS görünümü: sistem renkleri, ince ayırıcılar, ikincil gri
metinler, sade ikon butonları, açık/koyu mod anahtarı. Menü bar değil —
kendi penceresi olan normal bir uygulama.

Tamamen çevrimdışı: tarayıcı yok, sunucu yok, dışarı veri gitmez.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
from tkinter import TclError, filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from . import prefs, theme
from .extractor import (
    FORMAT_ORDER,
    FORMATS,
    VIDEO_EXTS,
    VIDEO_FILETYPES,
    ExtractionJob,
    ExtractOptions,
    VideoInfo,
    format_duration,
    human_size,
    probe_video,
    tr_number,
)
from .icons import IconSet

# Sürükle-bırak isteğe bağlı: tkinterdnd2 yoksa uygulama normal çalışır,
# yalnızca "Video Seç…" yolu kullanılır.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _DND_MIXIN = TkinterDnD.DnDWrapper
except Exception:  # noqa: BLE001
    DND_FILES = None
    TkinterDnD = None
    _DND_MIXIN = object

APP_NAME = "Video2Zip"
POLL_MS = 60
LABEL_W = 104          # form satırlarındaki etiket sütunu
WINDOW_ALPHA = 0.95    # sistem panellerine yakın hafif saydamlık


class Video2ZipApp(ctk.CTk, _DND_MIXIN):
    def __init__(self) -> None:
        super().__init__(fg_color=theme.WINDOW)

        self.settings = prefs.load()
        self.appearance = self.settings.get("appearance", "light")
        self._apply_appearance(self.appearance)

        self.title(APP_NAME)
        self.minsize(600, 480)
        self.attributes("-alpha", WINDOW_ALPHA)

        self.fonts = theme.Fonts()
        self.icons = IconSet()

        # --- durum -------------------------------------------------------
        self.video: Optional[VideoInfo] = None
        self.job: Optional[ExtractionJob] = None
        self.events: "queue.Queue[dict]" = queue.Queue()
        self.pending_zip: Optional[str] = None
        self.pending_workdir: Optional[str] = None
        self.saved_path: Optional[str] = None
        self.phase = "idle"        # idle | extract | zip | ready | saved
        self.dnd_ready = False

        self.var_format = ctk.StringVar(value=self.settings.get("format", "PNG"))
        self.var_quality = ctk.IntVar(value=95)
        self.var_scale = ctk.IntVar(value=100)
        self.var_step = ctk.IntVar(value=1)
        self.var_prefix = ctk.StringVar(value="frame_")
        self.var_prefix.trace_add("write", lambda *_: self._refresh_estimate())

        self._build_ui()
        self._size_window()
        self._on_format_change()
        self._update_controls()
        self.dnd_ready = self._setup_dnd()
        self._setup_mac_handlers()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Command-o>", lambda _e: self._choose_video())
        self.bind("<Command-Return>", lambda _e: self._primary_action())
        self.after(POLL_MS, self._poll_events)

    # ================================================================ shell
    def _size_window(self) -> None:
        """Pencereyi içeriğe göre boyutla — kaydırmaya gerek kalmasın."""
        self.update_idletasks()
        content = sum(c.winfo_reqheight() for c in self.scroll_body.winfo_children())
        chrome = (self.header_frame.winfo_reqheight() + 2 * theme.SP_4
                  + self.footer_frame.winfo_reqheight() + 2 * theme.SP_4
                  + 2)                                    # iki ayırıcı
        w = 640
        h = max(480, min(content + chrome + theme.SP_5,
                         self.winfo_screenheight() - 140))
        x = (self.winfo_screenwidth() - w) // 2
        y = max(24, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------ macOS köprüleri
    def _setup_mac_handlers(self) -> None:
        """Finder'dan 'Bununla Aç' ve Dock'a bırakma desteği (.app olarak)."""
        try:
            self.createcommand("::tk::mac::OpenDocument", self._on_mac_open)
            self.createcommand("::tk::mac::ReopenApplication", self._on_mac_reopen)
        except Exception:  # noqa: BLE001 — macOS dışında ya da Tk desteklemiyorsa
            pass

    def _on_mac_open(self, *paths: str) -> None:
        video = next((p for p in paths
                      if os.path.splitext(p)[1].lower() in VIDEO_EXTS), None)
        if video and self.phase not in ("extract", "zip"):
            self.after(80, lambda: self._load_video(video))

    def _on_mac_reopen(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    # ------------------------------------------------------- sürükle-bırak
    def _setup_dnd(self) -> bool:
        """Pencereyi dosya bırakma hedefi yapar. tkinterdnd2 yoksa sessizce atlar."""
        if DND_FILES is None:
            return False
        try:
            self.TkdndVersion = TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<DropEnter>>", self._on_drop_enter)
            self.dnd_bind("<<DropLeave>>", self._on_drop_leave)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:  # noqa: BLE001 — DnD olmadan da çalışılabilir
            return False
        return True

    def _on_drop_enter(self, _event=None):
        if self.phase in ("extract", "zip"):
            return
        self.source_card.configure(border_color=theme.ACCENT, border_width=2)
        self.lbl_empty.configure(text="Bırakın", text_color=theme.ACCENT)

    def _on_drop_leave(self, _event=None):
        self.source_card.configure(border_color=theme.BORDER, border_width=1)
        self.lbl_empty.configure(text="Henüz video seçilmedi",
                                 text_color=theme.TEXT)

    def _on_drop(self, event):
        self._on_drop_leave()
        if self.phase in ("extract", "zip"):
            return
        paths = [str(p) for p in self.tk.splitlist(event.data)]
        video = next((p for p in paths
                      if os.path.splitext(p)[1].lower() in VIDEO_EXTS), None)
        if video is None:
            messagebox.showwarning(
                "Desteklenmeyen dosya",
                "Bırakılan dosya bir video değil.\n\n"
                "Desteklenen biçimler: " + ", ".join(sorted(e[1:] for e in VIDEO_EXTS)),
                parent=self)
            return
        self._load_video(video)

    def _divider(self, row: int) -> None:
        ctk.CTkFrame(self, height=1, fg_color=theme.DIVIDER,
                     corner_radius=0).grid(row=row, column=0, sticky="ew")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._divider(1)

        body = self.scroll_body = ctk.CTkScrollableFrame(
            self, fg_color=theme.WINDOW, corner_radius=0,
            scrollbar_button_color=theme.BORDER,
            scrollbar_button_hover_color=theme.TEXT_3,
        )
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)

        self._build_source_section(body, 0)
        self._build_output_section(body, 1)

        self._divider(3)
        self._build_footer()

    # --------------------------------------------------------------- header
    def _build_header(self) -> None:
        header = self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew",
                    padx=theme.SP_5, pady=theme.SP_4)
        header.grid_columnconfigure(2, weight=1)

        # uygulama logosu — appicon.py ile aynı kaynaktan, koda gömülü
        ctk.CTkLabel(header, text="", image=self._logo(26)).grid(
            row=0, column=0, padx=(0, theme.SP_3))

        ctk.CTkLabel(header, text=APP_NAME, font=self.fonts.headline,
                     text_color=theme.TEXT).grid(row=0, column=1, sticky="w")
        self.lbl_header_note = ctk.CTkLabel(
            header, text="Video → kare", font=self.fonts.caption,
            text_color=theme.TEXT_3)
        self.lbl_header_note.grid(row=0, column=2, sticky="e", padx=(0, theme.SP_3))

        self.btn_appearance = self._icon_button(
            header, "sun" if self.appearance == "light" else "moon",
            self._toggle_appearance,
            "Koyu moda geç" if self.appearance == "light" else "Açık moda geç")
        self.btn_appearance.grid(row=0, column=3, sticky="e")

    def _logo(self, size: int, colors=None):
        """Uygulama logosunun monokrom sürümü — temaya göre renklenir.

        Renkli squircle yalnızca Dock/Finder ikonudur; arayüz içinde logo,
        menü bar şablon ikonları gibi tek renk ve şeffaf durur.
        """
        from .appicon import render_glyph

        pair = colors or theme.TEXT
        return ctk.CTkImage(                       # Retina için 2x çiz
            light_image=render_glyph(size * 2, pair[0]),
            dark_image=render_glyph(size * 2, pair[1]),
            size=(size, size))

    def _icon_button(self, parent, icon: str, command, tooltip: str = "") -> ctk.CTkButton:
        """Çerçevesiz, yalnızca ikon içeren düz buton."""
        return ctk.CTkButton(
            parent, text="", image=self.icons.get(icon, 15, theme.TEXT_2),
            command=command, width=26, height=26, corner_radius=theme.R_FIELD,
            fg_color="transparent", hover_color=theme.HOVER, border_width=0)

    # ------------------------------------------------------------- sections
    def _section(self, parent, row: int, title: str):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=row, column=0, sticky="ew",
                  padx=theme.SP_5, pady=(theme.SP_5, 0))
        wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(wrap, text=title.upper(), font=self.fonts.section,
                     text_color=theme.TEXT_3, anchor="w").grid(
            row=0, column=0, sticky="w", padx=theme.SP_2, pady=(0, theme.SP_2))

        card = ctk.CTkFrame(wrap, fg_color=theme.SURFACE, corner_radius=theme.R_CARD,
                            border_width=1, border_color=theme.BORDER)
        card.grid(row=1, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        return card

    def _row(self, card, row: int, label: str, last: bool = False):
        """Etiket + kontrol satırı; satırlar arasında ince ayırıcı."""
        line = ctk.CTkFrame(card, fg_color="transparent")
        line.grid(row=row * 2, column=0, sticky="ew",
                  padx=theme.SP_4, pady=theme.SP_3)
        line.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(line, text=label, font=self.fonts.body, anchor="w",
                     text_color=theme.TEXT, width=LABEL_W).grid(
            row=0, column=0, sticky="w")

        holder = ctk.CTkFrame(line, fg_color="transparent")
        holder.grid(row=0, column=1, sticky="ew")
        holder.grid_columnconfigure(0, weight=1)

        if not last:
            ctk.CTkFrame(card, height=1, fg_color=theme.DIVIDER, corner_radius=0
                         ).grid(row=row * 2 + 1, column=0, sticky="ew",
                                padx=theme.SP_4)
        return holder

    # --------------------------------------------------------- kaynak bölümü
    def _build_source_section(self, parent, row: int) -> None:
        card = self.source_card = self._section(parent, row, "Kaynak")

        # video seçilmeden önceki boş durum — kutunun ortasında
        self.empty_state = ctk.CTkFrame(card, fg_color="transparent")
        self.empty_state.grid(row=0, column=0, pady=theme.SP_7)
        self.empty_state.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.empty_state, text="",
                     image=self._logo(40, theme.TEXT)).grid(
            row=0, column=0, pady=(0, theme.SP_4))
        self.lbl_empty = ctk.CTkLabel(
            self.empty_state, text="Henüz video seçilmedi",
            font=self.fonts.body, text_color=theme.TEXT)
        self.lbl_empty.grid(row=1, column=0)

        # dolu durum
        self.file_state = ctk.CTkFrame(card, fg_color="transparent")
        self.file_state.grid(row=1, column=0, sticky="ew",
                             padx=theme.SP_4, pady=(theme.SP_4, theme.SP_2))
        self.file_state.grid_columnconfigure(1, weight=1)
        self.file_state.grid_remove()

        self.lbl_thumb = ctk.CTkLabel(self.file_state, text="",
                                      image=self.icons.get("film", 22, theme.ACCENT))
        self.lbl_thumb.grid(row=0, column=0, rowspan=2, padx=(0, theme.SP_4))
        self.lbl_filename = ctk.CTkLabel(self.file_state, text="", anchor="w",
                                         font=self.fonts.body, text_color=theme.TEXT)
        self.lbl_filename.grid(row=0, column=1, sticky="w")
        self.lbl_meta = ctk.CTkLabel(self.file_state, text="", anchor="w",
                                     font=self.fonts.callout, text_color=theme.TEXT_2)
        self.lbl_meta.grid(row=1, column=1, sticky="w")

        # seçim butonu
        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew",
                 padx=theme.SP_4, pady=(theme.SP_2, theme.SP_4))
        bar.grid_columnconfigure(0, weight=1)

        self.btn_choose = ctk.CTkButton(
            bar, text="Video Seç…", image=self.icons.get("folder", 15, theme.TEXT),
            compound="left", command=self._choose_video, height=30,
            corner_radius=theme.R_FIELD, font=self.fonts.body,
            fg_color=theme.SURFACE_ALT, hover_color=theme.HOVER,
            text_color=theme.TEXT, border_width=1, border_color=theme.BORDER)
        self.btn_choose.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(bar, text="⌘O", font=self.fonts.caption,
                     text_color=theme.TEXT_3).grid(row=0, column=1, sticky="e")

    # ---------------------------------------------------------- çıktı bölümü
    def _build_output_section(self, parent, row: int) -> None:
        card = self._section(parent, row, "Çıktı")

        # biçim ------------------------------------------------------------
        holder = self._row(card, 0, "Görsel biçimi")
        self.opt_format = ctk.CTkOptionMenu(
            holder, values=FORMAT_ORDER, variable=self.var_format,
            command=self._on_format_change, width=110, height=28,
            corner_radius=theme.R_FIELD, font=self.fonts.body,
            dropdown_font=self.fonts.body,
            fg_color=theme.SURFACE_ALT, button_color=theme.SURFACE_ALT,
            button_hover_color=theme.HOVER, text_color=theme.TEXT,
            dropdown_fg_color=theme.SURFACE, dropdown_hover_color=theme.HOVER,
            dropdown_text_color=theme.TEXT, anchor="w")
        self.opt_format.grid(row=0, column=0, sticky="w")
        self.lbl_format_hint = ctk.CTkLabel(
            holder, text="", font=self.fonts.caption, text_color=theme.TEXT_3,
            anchor="e")
        self.lbl_format_hint.grid(row=0, column=1, sticky="e", padx=(theme.SP_3, 0))

        # kalite -----------------------------------------------------------
        self.sld_quality, self.lbl_quality_value = self._slider_row(
            card, 1, "Kalite", 1, 100, 99, self.var_quality)

        # ölçek ------------------------------------------------------------
        self.sld_scale, self.lbl_scale_value = self._slider_row(
            card, 2, "Ölçek", 10, 200, 38, self.var_scale)

        # kare aralığı ------------------------------------------------------
        self.sld_step, self.lbl_step_value = self._slider_row(
            card, 3, "Kare aralığı", 1, 30, 29, self.var_step)

        # zaman aralığı -----------------------------------------------------
        holder = self._row(card, 4, "Zaman aralığı")
        holder.grid_columnconfigure(0, weight=0)
        self.ent_start = self._entry(holder, 0, "başı", 64)
        ctk.CTkLabel(holder, text="–", font=self.fonts.body,
                     text_color=theme.TEXT_3).grid(row=0, column=1, padx=theme.SP_2)
        self.ent_end = self._entry(holder, 2, "sonu", 64)
        ctk.CTkLabel(holder, text="saniye  ·  boş = tamamı", font=self.fonts.caption,
                     text_color=theme.TEXT_3).grid(row=0, column=3, sticky="w",
                                                   padx=(theme.SP_2, 0))
        self.lbl_range_error = ctk.CTkLabel(
            holder, text="", font=self.fonts.caption, text_color=theme.DANGER,
            anchor="e")
        self.lbl_range_error.grid(row=0, column=4, sticky="e", padx=(theme.SP_3, 0))
        holder.grid_columnconfigure(4, weight=1)

        # ön ek -------------------------------------------------------------
        holder = self._row(card, 5, "Dosya adı ön eki", last=True)
        self.ent_prefix = ctk.CTkEntry(
            holder, textvariable=self.var_prefix, height=28, width=120,
            corner_radius=theme.R_FIELD, font=self.fonts.body,
            fg_color=theme.FIELD, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT)
        self.ent_prefix.grid(row=0, column=0, sticky="w")
        self.lbl_prefix_note = ctk.CTkLabel(
            holder, text="", font=self.fonts.caption, text_color=theme.TEXT_3,
            anchor="e")
        self.lbl_prefix_note.grid(row=0, column=1, sticky="e", padx=(theme.SP_3, 0))
        holder.grid_columnconfigure(1, weight=1)

        # tahmin ------------------------------------------------------------
        self.lbl_estimate = ctk.CTkLabel(
            parent, text="", font=self.fonts.callout, text_color=theme.TEXT_2,
            anchor="w")
        self.lbl_estimate.grid(row=row + 1, column=0, sticky="w",
                               padx=theme.SP_5 + theme.SP_2,
                               pady=(theme.SP_2, theme.SP_5))

    def _slider_row(self, card, row: int, label: str,
                    lo: int, hi: int, steps: int, var):
        holder = self._row(card, row, label)
        slider = ctk.CTkSlider(
            holder, from_=lo, to=hi, number_of_steps=steps, variable=var,
            command=lambda _v: self._on_slider_change(),
            height=16, button_length=0, button_corner_radius=theme.R_PILL,
            progress_color=theme.ACCENT, fg_color=theme.TRACK,
            button_color=("#FFFFFF", "#F2F2F7"),
            button_hover_color=("#FFFFFF", "#FFFFFF"), border_width=5)
        slider.grid(row=0, column=0, sticky="ew", padx=(0, theme.SP_4))
        value = ctk.CTkLabel(holder, text="", font=self.fonts.mono,
                             text_color=theme.TEXT, width=76, anchor="e")
        value.grid(row=0, column=1, sticky="e")
        return slider, value

    def _entry(self, parent, col: int, placeholder: str, width: int) -> ctk.CTkEntry:
        # NOT: textvariable verilirse CustomTkinter placeholder'ı hiç göstermez.
        # Bu yüzden değer doğrudan widget'tan okunur, değişiklik bind ile izlenir.
        entry = ctk.CTkEntry(
            parent, placeholder_text=placeholder,
            width=width, height=28, corner_radius=theme.R_FIELD,
            font=self.fonts.body, justify="center",
            fg_color=theme.FIELD, border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT, placeholder_text_color=theme.TEXT_OFF)
        entry.grid(row=0, column=col, sticky="w")
        entry.bind("<KeyRelease>", lambda _e: self._refresh_estimate())
        entry.bind("<FocusOut>", lambda _e: self._refresh_estimate())
        return entry

    # --------------------------------------------------------------- footer
    def _build_footer(self) -> None:
        footer = self.footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=theme.SP_5, pady=theme.SP_4)
        footer.grid_columnconfigure(0, weight=1)

        status = ctk.CTkFrame(footer, fg_color="transparent")
        status.grid(row=0, column=0, sticky="ew")
        status.grid_columnconfigure(0, weight=1)

        self.lbl_status = ctk.CTkLabel(status, text="", font=self.fonts.body,
                                       text_color=theme.TEXT_2, anchor="w")
        self.lbl_status.grid(row=0, column=0, sticky="w")

        self.progress = ctk.CTkProgressBar(
            status, height=5, corner_radius=theme.R_PILL,
            fg_color=theme.TRACK, progress_color=theme.ACCENT)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(theme.SP_2, 0))
        self.progress.set(0)
        self.progress.grid_remove()

        self.lbl_detail = ctk.CTkLabel(status, text="", font=self.fonts.callout,
                                       text_color=theme.TEXT_3, anchor="w")
        self.lbl_detail.grid(row=2, column=0, sticky="w", pady=(theme.SP_1, 0))

        buttons = ctk.CTkFrame(footer, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="e", padx=(theme.SP_5, 0))

        self.btn_secondary = ctk.CTkButton(
            buttons, text="İptal", command=self._secondary_action,
            width=76, height=30, corner_radius=theme.R_FIELD, font=self.fonts.body,
            fg_color=theme.SURFACE_ALT, hover_color=theme.HOVER,
            text_color=theme.TEXT, border_width=1, border_color=theme.BORDER)
        self.btn_secondary.grid(row=0, column=0, padx=(0, theme.SP_3))
        self.btn_secondary.grid_remove()

        self.btn_primary = ctk.CTkButton(
            buttons, text="Kareleri Çıkar", command=self._primary_action,
            width=136, height=30, corner_radius=theme.R_FIELD,
            font=self.fonts.body_bold, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER, text_color=theme.ON_ACCENT,
            text_color_disabled=theme.ON_ACCENT)
        self.btn_primary.grid(row=0, column=1)

    # ======================================================== görünüm modu
    def _apply_appearance(self, mode: str) -> None:
        """Temayı hem widget'lara hem pencere çerçevesine uygular.

        `set_appearance_mode` yalnızca CustomTkinter'ın kendi çizdiği
        yüzeyleri etkiler; başlık çubuğunu macOS çizer ve uygulamanın
        NSAppearance'ına bakar. Tk 8.7+/9 bunu `-appearance` penceresi
        özelliğiyle açar — aksi hâlde koyu temada başlık çubuğu beyaz kalır.
        """
        ctk.set_appearance_mode(mode)
        try:
            self.attributes("-appearance",
                            "darkaqua" if mode == "dark" else "aqua")
        except TclError:
            pass          # eski Tk sürümlerinde bu özellik yok

    def _toggle_appearance(self) -> None:
        self.appearance = "dark" if self.appearance == "light" else "light"
        self._apply_appearance(self.appearance)
        prefs.save(appearance=self.appearance)
        self.btn_appearance.configure(
            image=self.icons.get("sun" if self.appearance == "light" else "moon",
                                 15, theme.TEXT_2))

    # =========================================================== etkileşim
    def _choose_video(self) -> None:
        if self.phase in ("extract", "zip"):
            return
        path = filedialog.askopenfilename(
            parent=self, title="Video seç", filetypes=VIDEO_FILETYPES)
        if path:
            self._load_video(path)

    def _load_video(self, path: str) -> None:
        try:
            info = probe_video(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Video açılamadı", str(exc), parent=self)
            return

        self.video = info
        self._discard_pending()
        self.saved_path = None
        self.phase = "idle"
        self.progress.set(0)
        self.progress.grid_remove()
        self.lbl_detail.configure(text="")

        self.empty_state.grid_remove()
        self.file_state.grid()
        self.lbl_filename.configure(text=os.path.basename(info.path))
        meta = [f"{info.width}×{info.height}"]
        if info.fps:
            meta.append(f"{info.fps:.0f} fps")
        if info.duration:
            meta.append(format_duration(info.duration))
        meta.append(f"{tr_number(info.frame_count)} kare" if info.frame_count
                    else "kare sayısı bilinmiyor")
        meta.append(human_size(info.size_bytes))
        self.lbl_meta.configure(text="  ·  ".join(meta))

        self._set_status("", theme.TEXT_2)
        self._refresh_estimate()
        self._update_controls()

    def _on_format_change(self, _value: str = "") -> None:
        spec = FORMATS[self.var_format.get()]
        prefs.save(format=spec.key)
        has_quality = spec.quality_kind is not None
        self.lbl_format_hint.configure(
            text="kayıpsız" if spec.quality_kind in (None, "png") else "kayıplı")
        self.sld_quality.configure(state="normal" if has_quality else "disabled")
        self._on_slider_change()

    def _on_slider_change(self) -> None:
        spec = FORMATS[self.var_format.get()]
        quality = int(self.var_quality.get())
        self.lbl_quality_value.configure(
            text=str(quality) if spec.quality_kind else "yok",
            text_color=theme.TEXT if spec.quality_kind else theme.TEXT_OFF)

        scale = int(self.var_scale.get())
        if self.video and scale != 100:
            w = max(1, round(self.video.width * scale / 100))
            h = max(1, round(self.video.height * scale / 100))
            self.lbl_scale_value.configure(text=f"{w}×{h}")
        else:
            self.lbl_scale_value.configure(text=f"%{scale}")

        step = int(self.var_step.get())
        self.lbl_step_value.configure(text="tüm kareler" if step == 1 else f"her {step}.")

        self._refresh_estimate()

    # ------------------------------------------------------------- tahmin
    def _parse_range(self) -> tuple[Optional[float], Optional[float], Optional[str]]:
        def parse(raw: str, name: str):
            raw = raw.strip().replace(",", ".")
            if not raw:
                return None, None
            try:
                value = float(raw)
            except ValueError:
                return None, f"{name} sayı olmalı"
            if value < 0:
                return None, f"{name} negatif olamaz"
            return value, None

        start, err = parse(self.ent_start.get(), "Başlangıç")
        if err:
            return None, None, err
        end, err = parse(self.ent_end.get(), "Bitiş")
        if err:
            return None, None, err
        if start is not None and end is not None and end <= start:
            return None, None, "Bitiş başlangıçtan büyük olmalı"
        return start, end, None

    def _current_options(self) -> Optional[ExtractOptions]:
        start, end, err = self._parse_range()
        if err:
            return None
        prefix = self.var_prefix.get().strip() or "frame_"
        prefix = "".join(c for c in prefix if c not in '/\\:*?"<>|')
        return ExtractOptions(
            fmt=self.var_format.get(),
            quality=int(self.var_quality.get()),
            scale=int(self.var_scale.get()),
            step=max(1, int(self.var_step.get())),
            start_sec=start or 0.0,
            end_sec=end,
            prefix=prefix,
        )

    def _refresh_estimate(self) -> None:
        _, _, err = self._parse_range()
        self.lbl_range_error.configure(text=err or "")

        spec = FORMATS[self.var_format.get()]
        prefix = self.var_prefix.get().strip() or "frame_"
        self.lbl_prefix_note.configure(text=f"{prefix}0001{spec.ext}")

        if not self.video:
            self.lbl_estimate.configure(text="")
        elif err:
            self.lbl_estimate.configure(text="Zaman aralığını düzeltin",
                                        text_color=theme.DANGER)
        else:
            options = self._current_options()
            count = options.estimate(self.video) if options else 0
            self.lbl_estimate.configure(
                text=f"{tr_number(count)} kare çıkacak" if count
                else "Kare sayısı bilinmiyor — işlem yine de çalışır",
                text_color=theme.TEXT_2)

        self._update_controls()

    # -------------------------------------------------------- çalıştır/dur
    def _primary_action(self) -> None:
        if self.phase in ("extract", "zip"):
            return
        if self.phase == "ready" and self.pending_zip:
            self._prompt_save()
            return
        self._start_job()

    def _secondary_action(self) -> None:
        if self.phase in ("extract", "zip"):
            if self.job:
                self.job.cancel()
                self._set_status("İptal ediliyor…", theme.WARNING)
                self.btn_secondary.configure(state="disabled")
            return
        if self.phase == "saved" and self.saved_path:
            subprocess.run(["open", "-R", self.saved_path], check=False)

    def _start_job(self) -> None:
        if not self.video:
            return
        options = self._current_options()
        if options is None:
            return

        self._discard_pending()
        self.saved_path = None
        self.phase = "extract"
        self.progress.set(0)
        self.progress.grid()
        self._set_status("Kareler çıkarılıyor…", theme.TEXT)
        self.lbl_detail.configure(text="Video açılıyor…")

        self.job = ExtractionJob(self.video, options, self.events)
        self.job.start()
        self._update_controls()

    # ----------------------------------------------------------- olay akışı
    def _poll_events(self) -> None:
        if not self.winfo_exists():
            return
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll_events)

    def _handle_event(self, event: dict) -> None:
        kind = event.get("type")

        if kind == "phase":
            self.phase = event["phase"]
            if self.phase == "zip":
                self._set_status("Arşivleniyor…", theme.TEXT)
            self._update_controls()

        elif kind == "progress":
            done, total = event["done"], event["total"]
            if total > 0:
                fraction = min(1.0, done / total)
                self.progress.set(fraction)
                self._set_status(
                    f"{'Arşivleniyor' if self.phase == 'zip' else 'Kareler çıkarılıyor'}"
                    f" — %{fraction * 100:.0f}", theme.TEXT)
            rate = event.get("rate", 0.0)
            if self.phase == "zip":
                self.lbl_detail.configure(
                    text=f"{tr_number(done)} / {tr_number(total)} dosya")
            else:
                parts = [f"{tr_number(done)} / {tr_number(total)} kare" if total
                         else f"{tr_number(done)} kare"]
                if rate > 0:
                    parts.append(f"{rate:.0f} kare/sn")
                    if total > done:
                        parts.append(f"~{format_duration((total - done) / rate)} kaldı")
                self.lbl_detail.configure(text="  ·  ".join(parts))

        elif kind == "done":
            self.job = None
            self.phase = "ready"
            self.pending_zip = event["zip_path"]
            self.pending_workdir = event["workdir"]
            self.progress.set(1.0)
            self._set_status(f"{tr_number(event['frames'])} kare hazır", theme.SUCCESS)
            self.lbl_detail.configure(
                text=f"{human_size(os.path.getsize(self.pending_zip))} arşiv"
                     f"  ·  {event['elapsed']:.1f} sn")
            self._update_controls()
            self._prompt_save()

        elif kind == "cancelled":
            self.job = None
            self.phase = "idle"
            self.progress.set(0)
            self.progress.grid_remove()
            self._set_status("İptal edildi", theme.TEXT_2)
            self.lbl_detail.configure(text="")
            self._update_controls()

        elif kind == "error":
            self.job = None
            self.phase = "idle"
            self.progress.set(0)
            self.progress.grid_remove()
            self._set_status("Hata oluştu", theme.DANGER)
            self.lbl_detail.configure(text=event["message"][:90])
            self._update_controls()
            messagebox.showerror("İşlem başarısız", event["message"], parent=self)

    # --------------------------------------------------------------- kayıt
    def _prompt_save(self) -> None:
        if not self.pending_zip or not self.video:
            return
        self.lift()
        target = filedialog.asksaveasfilename(
            parent=self, title="ZIP dosyasını kaydet", defaultextension=".zip",
            initialfile=f"{self.video.stem}_frames.zip",
            filetypes=[("ZIP arşivi", "*.zip")])
        if not target:
            self._set_status("Kaydedilmedi", theme.WARNING)
            self.lbl_detail.configure(text="Arşiv hazır bekliyor — 'ZIP'i Kaydet'")
            self._update_controls()
            return

        try:
            if os.path.abspath(target) != os.path.abspath(self.pending_zip):
                shutil.move(self.pending_zip, target)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Kaydedilemedi", str(exc), parent=self)
            return

        self.saved_path = target
        self.pending_zip = None
        self._discard_pending()
        self.phase = "saved"
        self.progress.grid_remove()
        self._set_status("Kaydedildi", theme.SUCCESS)
        self.lbl_detail.configure(text=os.path.basename(target))
        self._update_controls()

    def _discard_pending(self) -> None:
        if self.pending_workdir and os.path.isdir(self.pending_workdir):
            shutil.rmtree(self.pending_workdir, ignore_errors=True)
        self.pending_workdir = None
        self.pending_zip = None

    # ------------------------------------------------------- arayüz durumu
    def _set_status(self, text: str, color) -> None:
        self.lbl_status.configure(text=text, text_color=color)

    def _settings_widgets(self):
        return (self.opt_format, self.sld_quality, self.sld_scale, self.sld_step,
                self.ent_start, self.ent_end, self.ent_prefix)

    def _update_controls(self) -> None:
        running = self.phase in ("extract", "zip")
        _, _, range_error = self._parse_range()

        for widget in self._settings_widgets():
            widget.configure(state="disabled" if running else "normal")
        if not running and FORMATS[self.var_format.get()].quality_kind is None:
            self.sld_quality.configure(state="disabled")
        self.btn_choose.configure(state="disabled" if running else "normal")

        if running:
            self.btn_primary.configure(text="İşleniyor…", state="disabled")
            self.btn_secondary.configure(text="İptal", state="normal",
                                         text_color=theme.DANGER)
            self.btn_secondary.grid()
        elif self.phase == "ready":
            self.btn_primary.configure(text="ZIP'i Kaydet", state="normal")
            self.btn_secondary.grid_remove()
        elif self.phase == "saved":
            self.btn_primary.configure(text="Tekrar Çıkar", state="normal")
            self.btn_secondary.configure(text="Finder'da Göster", state="normal",
                                         text_color=theme.TEXT)
            self.btn_secondary.grid()
        else:
            enabled = self.video is not None and range_error is None
            self.btn_primary.configure(text="Kareleri Çıkar",
                                       state="normal" if enabled else "disabled")
            self.btn_secondary.grid_remove()

    # --------------------------------------------------------------- kapat
    def _on_close(self) -> None:
        if self.phase in ("extract", "zip"):
            if not messagebox.askyesno(
                    "Çıkılsın mı?",
                    "İşlem sürüyor. Şimdi çıkarsanız kareler kaybolur.",
                    parent=self):
                return
            if self.job:
                self.job.cancel()
                self.job.join(timeout=2.0)
        self._discard_pending()
        self.destroy()


def main() -> int:
    import importlib.util

    if importlib.util.find_spec("_tkinter") is None:
        print("Tkinter bulunamadı. Kurulum: brew install python-tk@3.14", file=sys.stderr)
        return 1

    app = Video2ZipApp()
    app.mainloop()
    return 0
