from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "VisionSlide"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return _bundle_root()


def resource_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)


def user_data_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            target = Path(base) / APP_NAME
            target.mkdir(parents=True, exist_ok=True)
            return target
    target = Path.home() / f".{APP_NAME.lower()}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def data_path(filename: str) -> Path:
    target = user_data_dir() / filename
    if target.exists():
        return target

    source = project_root() / filename
    if source.exists():
        try:
            target.write_bytes(source.read_bytes())
        except Exception:
            pass
    return target
