from __future__ import annotations

import base64
import ctypes
import json
from ctypes import wintypes
from pathlib import Path

from app.runtime_paths import data_path

CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    if not data:
        return DATA_BLOB(0, None)

    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if not blob.cbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect_text(value: str) -> str:
    payload = (value or "").encode("utf-8")
    input_blob = _bytes_to_blob(payload)
    output_blob = DATA_BLOB()

    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "VisionSlidePassword",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()

    try:
        return base64.b64encode(_blob_to_bytes(output_blob)).decode("ascii")
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(output_blob.pbData)


def unprotect_text(value: str) -> str:
    encrypted = base64.b64decode(value.encode("ascii"))
    input_blob = _bytes_to_blob(encrypted)
    output_blob = DATA_BLOB()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()

    try:
        return _blob_to_bytes(output_blob).decode("utf-8")
    finally:
        if output_blob.pbData:
            kernel32.LocalFree(output_blob.pbData)


class CredentialStore:
    def __init__(self, store_path: Path | str | None = None):
        self.store_path = Path(store_path) if store_path else data_path("visionslide_credentials.json")

    def _normalize_identity(self, identity: str) -> str:
        return (identity or "").strip().lower()

    def load(self) -> dict[str, str]:
        if not self.store_path.exists():
            return {}

        try:
            with open(self.store_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}

        return {str(key): str(value) for key, value in data.items()}

    def save(self, credentials: dict[str, str]) -> None:
        with open(self.store_path, "w", encoding="utf-8") as file:
            json.dump(credentials, file, indent=4)

    def set_password(self, identity: str, password: str) -> None:
        cleaned_identity = self._normalize_identity(identity)
        if not cleaned_identity:
            return

        credentials = self.load()
        duplicate_keys = [key for key in credentials.keys() if key.strip().lower() == cleaned_identity and key != cleaned_identity]
        for key in duplicate_keys:
            credentials.pop(key, None)
        credentials[cleaned_identity] = protect_text(password)
        self.save(credentials)

    def get_password(self, identity: str) -> str:
        cleaned_identity = self._normalize_identity(identity)
        if not cleaned_identity:
            return ""

        credentials = self.load()
        encrypted = credentials.get(cleaned_identity)
        if not encrypted:
            for key, value in credentials.items():
                if key.strip().lower() == cleaned_identity:
                    encrypted = value
                    break
        if not encrypted:
            return ""

        try:
            return unprotect_text(encrypted)
        except Exception:
            return ""

    def delete_password(self, identity: str) -> None:
        cleaned_identity = self._normalize_identity(identity)
        if not cleaned_identity:
            return

        credentials = self.load()
        keys_to_remove = [key for key in credentials.keys() if key.strip().lower() == cleaned_identity]
        if keys_to_remove:
            for key in keys_to_remove:
                credentials.pop(key, None)
            self.save(credentials)

    def get_saved_identities(self) -> list[str]:
        credentials = self.load()
        identities = [str(identity).strip().lower() for identity in credentials.keys()]
        return sorted({identity for identity in identities if identity})
