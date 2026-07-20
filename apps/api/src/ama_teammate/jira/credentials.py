from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Protocol


class JiraTokenProvider(Protocol):
    def get_token(self) -> str: ...


class JiraCredentialError(RuntimeError):
    """A sanitized credential availability error."""


class WindowsDpapiTokenProvider:
    """Loads a PowerShell ConvertFrom-SecureString value using current-user DPAPI."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def get_token(self) -> str:
        if sys.platform != "win32":
            raise JiraCredentialError("jira_dpapi_unavailable")
        try:
            encoded = self.path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise JiraCredentialError("jira_token_not_configured") from exc
        try:
            encrypted = bytes.fromhex(encoded)
        except ValueError as exc:
            raise JiraCredentialError("jira_token_format_invalid") from exc
        if not encrypted:
            raise JiraCredentialError("jira_token_format_invalid")
        token = _crypt_unprotect(encrypted).rstrip("\x00")
        if not token:
            raise JiraCredentialError("jira_token_empty")
        return token


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt_unprotect(encrypted: bytes) -> str:
    buffer = ctypes.create_string_buffer(encrypted)
    input_blob = _DataBlob(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    success = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
    )
    if not success:
        raise JiraCredentialError("jira_token_decryption_failed")
    try:
        raw = ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)
    try:
        return raw.decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise JiraCredentialError("jira_token_decryption_failed") from exc
