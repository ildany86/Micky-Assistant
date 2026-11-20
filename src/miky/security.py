"""Protección de secretos con DPAPI (Windows).

La API key se guarda cifrada con la cuenta de Windows del usuario, así no queda
en texto plano en el disco. Si DPAPI no está disponible (otro SO, tests), se
degrada a texto plano avisando.
"""

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes

PREFIX = "dpapi:"
_ENTROPY = b"Miky/REAPER/2026"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _crypt32():
    if sys.platform != "win32":
        return None
    try:
        return ctypes.WinDLL("crypt32.dll", use_last_error=True)
    except OSError:
        return None


def _call(protect: bool, data: bytes) -> bytes | None:
    crypt32 = _crypt32()
    if crypt32 is None:
        return None
    in_blob, _in_buf = _make_blob(data)
    entropy_blob, _entropy_buf = _make_blob(_ENTROPY)
    out_blob = _DataBlob()
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "Miky API key",
            ctypes.byref(entropy_blob),
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )
    if not ok:
        return None
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def encrypt_secret(value: str) -> str:
    """Devuelve el valor cifrado con prefijo, o el original si no se puede cifrar."""
    if not value:
        return ""
    if value.startswith(PREFIX):
        return value
    protected = _call(True, value.encode("utf-8"))
    if protected is None:
        return value
    return PREFIX + base64.b64encode(protected).decode("ascii")


def decrypt_secret(value: str) -> str:
    """Revierte encrypt_secret. Si el blob no corresponde a este usuario, devuelve ''."""
    if not value:
        return ""
    if not value.startswith(PREFIX):
        return value
    try:
        raw = base64.b64decode(value[len(PREFIX) :])
    except (ValueError, TypeError):
        return ""
    plain = _call(False, raw)
    if plain is None:
        return ""
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def mask_secret(value: str) -> str:
    """Texto seguro para mostrar en la interfaz."""
    if not value:
        return "(sin configurar)"
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"
