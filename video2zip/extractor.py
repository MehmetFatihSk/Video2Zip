"""Video → frame extraction engine.

Pure logic layer: no Tk imports here. The GUI starts an :class:`ExtractionJob`
on a worker thread and consumes progress events from a queue, so the window
never blocks.
"""

from __future__ import annotations

import math
import os
import queue
import shutil
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from typing import Optional

import cv2

# --------------------------------------------------------------- formats ----


@dataclass(frozen=True)
class FormatSpec:
    key: str
    ext: str
    quality_kind: Optional[str]   # "jpeg" | "webp" | "png" | None
    quality_hint: str
    zip_compression: int          # already-compressed pixels → just store


FORMATS: dict[str, FormatSpec] = {
    "PNG": FormatSpec("PNG", ".png", "png",
                      "Kayıpsız · yüksek değer = daha küçük dosya (yavaş)",
                      zipfile.ZIP_STORED),
    "JPG": FormatSpec("JPG", ".jpg", "jpeg",
                      "Kayıplı · 85–95 arası önerilir",
                      zipfile.ZIP_STORED),
    "WEBP": FormatSpec("WEBP", ".webp", "webp",
                       "Kayıplı · 100 = kayıpsız mod",
                       zipfile.ZIP_STORED),
    "BMP": FormatSpec("BMP", ".bmp", None,
                      "Sıkıştırmasız — kalite ayarı yok",
                      zipfile.ZIP_DEFLATED),
    "TIFF": FormatSpec("TIFF", ".tiff", None,
                       "Arşivlik kayıpsız — kalite ayarı yok",
                       zipfile.ZIP_DEFLATED),
}

FORMAT_ORDER = ["PNG", "JPG", "WEBP", "BMP", "TIFF"]

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm",
              ".mpg", ".mpeg", ".wmv", ".flv", ".3gp", ".mts", ".m2ts"}

VIDEO_FILETYPES = [
    ("Video dosyaları", " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))),
    ("Tüm dosyalar", "*.*"),
]


def encode_params(spec: FormatSpec, quality: int) -> list[int]:
    if spec.quality_kind == "jpeg":
        return [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    if spec.quality_kind == "webp":
        return [cv2.IMWRITE_WEBP_QUALITY, int(quality)]
    if spec.quality_kind == "png":
        # PNG is lossless: map the slider onto the zlib compression level.
        level = int(round((100 - quality) / 100 * 9))
        return [cv2.IMWRITE_PNG_COMPRESSION, max(0, min(9, level))]
    return []


# ------------------------------------------------------------ video probe ---


@dataclass
class VideoInfo:
    path: str
    width: int
    height: int
    fps: float
    frame_count: int          # 0 when the container does not report it
    size_bytes: int

    @property
    def stem(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]

    @property
    def duration(self) -> float:
        if self.fps > 0 and self.frame_count > 0:
            return self.frame_count / self.fps
        return 0.0


def probe_video(path: str) -> VideoInfo:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(
            "Video açılamadı. Dosya bozuk olabilir veya codec desteklenmiyor olabilir."
        )
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if not math.isfinite(fps) or fps <= 0 or fps > 1000:
            fps = 0.0
        if count < 0:
            count = 0
        if width <= 0 or height <= 0:
            raise ValueError("Video çözünürlüğü okunamadı; dosya desteklenmiyor.")
    finally:
        cap.release()

    return VideoInfo(
        path=path,
        width=width,
        height=height,
        fps=fps,
        frame_count=count,
        size_bytes=os.path.getsize(path),
    )


# ---------------------------------------------------------------- options ---


@dataclass
class ExtractOptions:
    fmt: str = "PNG"
    quality: int = 95
    scale: int = 100                  # percent
    step: int = 1                     # keep every Nth frame
    start_sec: float = 0.0
    end_sec: Optional[float] = None   # None = end of video
    prefix: str = "frame_"

    def frame_range(self, info: VideoInfo) -> tuple[int, Optional[int]]:
        """Return (start_index, end_index_inclusive_or_None)."""
        fps = info.fps or 0.0
        start = int(round(self.start_sec * fps)) if fps > 0 and self.start_sec > 0 else 0
        end: Optional[int] = None
        if self.end_sec is not None and fps > 0:
            end = int(round(self.end_sec * fps)) - 1
        if info.frame_count > 0:
            last = info.frame_count - 1
            start = min(start, last)
            end = last if end is None else min(end, last)
        return max(0, start), end

    def estimate(self, info: VideoInfo) -> int:
        """Estimated number of output frames (0 = unknown)."""
        start, end = self.frame_range(info)
        if end is None:
            return 0
        span = end - start + 1
        return max(0, math.ceil(span / max(1, self.step)))


# ------------------------------------------------------------------- job ----


class Cancelled(Exception):
    pass


class ExtractionJob(threading.Thread):
    """Extracts frames into a temp folder, then zips them.

    Emits dict events on ``events``:
        {"type": "phase",    "phase": "extract"|"zip"}
        {"type": "progress", "done": int, "total": int, "rate": float}
        {"type": "done",     "zip_path": str, "workdir": str, "frames": int, "elapsed": float}
        {"type": "cancelled"}
        {"type": "error",    "message": str}
    """

    def __init__(self, info: VideoInfo, options: ExtractOptions, events: "queue.Queue[dict]"):
        super().__init__(daemon=True)
        self.info = info
        self.options = options
        self.events = events
        self._cancel = threading.Event()
        self._workdir: Optional[str] = None

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # ----------------------------------------------------------- internals --
    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled()

    def _emit(self, **payload) -> None:
        self.events.put(payload)

    def run(self) -> None:  # noqa: D102
        started = time.monotonic()
        try:
            self._workdir = tempfile.mkdtemp(prefix="video2zip_")
            frames_dir = os.path.join(self._workdir, "frames")
            os.makedirs(frames_dir, exist_ok=True)

            written = self._extract(frames_dir)
            if written == 0:
                raise ValueError(
                    "Seçilen aralıkta hiç kare bulunamadı. Zaman aralığını kontrol edin."
                )
            zip_path = self._make_zip(frames_dir, written)
            self._emit(type="done", zip_path=zip_path, workdir=self._workdir,
                       frames=written, elapsed=time.monotonic() - started)
        except Cancelled:
            self._cleanup()
            self._emit(type="cancelled")
        except Exception as exc:  # noqa: BLE001 — surfaced in the UI
            self._cleanup()
            self._emit(type="error", message=str(exc) or exc.__class__.__name__)

    def _cleanup(self) -> None:
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    # ------------------------------------------------------------ extract --
    def _extract(self, frames_dir: str) -> int:
        opts = self.options
        spec = FORMATS[opts.fmt]
        params = encode_params(spec, opts.quality)
        start_idx, end_idx = opts.frame_range(self.info)
        total = opts.estimate(self.info)
        pad = max(4, len(str(total or 0)))

        self._emit(type="phase", phase="extract")
        self._emit(type="progress", done=0, total=total, rate=0.0)

        cap = cv2.VideoCapture(self.info.path)
        if not cap.isOpened():
            raise ValueError("Video açılamadı.")

        try:
            if start_idx > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_idx))
                actual = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
                if actual != start_idx:  # container refused the seek → rewind
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0.0)
                    skipped = 0
                    while skipped < start_idx:
                        self._check_cancel()
                        if not cap.grab():
                            break
                        skipped += 1

            idx = start_idx - 1
            written = 0
            t0 = time.monotonic()
            last_emit = 0.0

            while True:
                self._check_cancel()
                if not cap.grab():          # grab() advances without decoding
                    break
                idx += 1
                if end_idx is not None and idx > end_idx:
                    break
                if (idx - start_idx) % opts.step != 0:
                    continue

                ok, frame = cap.retrieve()  # decode only the frames we keep
                if not ok or frame is None:
                    break

                if opts.scale != 100:
                    factor = opts.scale / 100.0
                    new_w = max(1, int(round(frame.shape[1] * factor)))
                    new_h = max(1, int(round(frame.shape[0] * factor)))
                    interp = cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC
                    frame = cv2.resize(frame, (new_w, new_h), interpolation=interp)

                written += 1
                name = f"{opts.prefix}{written:0{pad}d}{spec.ext}"
                # imencode + manual write keeps non-ASCII paths safe.
                ok, buf = cv2.imencode(spec.ext, frame, params)
                if not ok:
                    raise ValueError(f"{opts.fmt} formatında kare kodlanamadı.")
                with open(os.path.join(frames_dir, name), "wb") as fh:
                    fh.write(buf.tobytes())

                now = time.monotonic()
                if now - last_emit > 0.08:
                    elapsed = max(1e-6, now - t0)
                    self._emit(type="progress", done=written, total=total,
                               rate=written / elapsed)
                    last_emit = now

            elapsed = max(1e-6, time.monotonic() - t0)
            self._emit(type="progress", done=written, total=written or total,
                       rate=written / elapsed)
            return written
        finally:
            cap.release()

    # ---------------------------------------------------------------- zip --
    def _make_zip(self, frames_dir: str, written: int) -> str:
        assert self._workdir
        spec = FORMATS[self.options.fmt]
        zip_path = os.path.join(self._workdir, f"{self.info.stem}_frames.zip")

        self._emit(type="phase", phase="zip")
        names = sorted(os.listdir(frames_dir))
        total = len(names)
        step = max(1, total // 100)

        with zipfile.ZipFile(zip_path, "w", compression=spec.zip_compression) as zf:
            for i, name in enumerate(names, start=1):
                self._check_cancel()
                zf.write(os.path.join(frames_dir, name), arcname=name)
                if i % step == 0 or i == total:
                    self._emit(type="progress", done=i, total=total, rate=0.0)

        shutil.rmtree(frames_dir, ignore_errors=True)
        return zip_path


# -------------------------------------------------------------- helpers -----


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


def format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def tr_number(value: int) -> str:
    """1234567 → '1.234.567' (Turkish thousands separator)."""
    return f"{value:,}".replace(",", ".")
