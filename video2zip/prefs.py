"""Kalıcı tercihler — oturumlar arasında saklanan kullanıcı ayarları.

~/Library/Application Support/Video2Zip/settings.json
"""

from __future__ import annotations

import json
import os

APP_SUPPORT = os.path.expanduser("~/Library/Application Support/Video2Zip")
SETTINGS_PATH = os.path.join(APP_SUPPORT, "settings.json")

DEFAULTS = {
    "appearance": "light",   # macOS varsayılanıyla uyumlu
    "format": "PNG",
}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return data


def save(**values) -> None:
    data = load()
    data.update({k: v for k, v in values.items() if k in DEFAULTS})
    try:
        os.makedirs(APP_SUPPORT, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass   # tercih kaydedilemezse uygulama yine de çalışsın
