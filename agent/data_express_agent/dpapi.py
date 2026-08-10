from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Protocol


class SecretProtectionError(RuntimeError):
    pass


class SecretProtector(Protocol):
    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(value, len(value))
    return (
        _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))),
        buffer,
    )


class WindowsDpapiProtector:
    """DPAPI protection bound to the Windows service account."""

    _CRYPTPROTECT_UI_FORBIDDEN = 0x1

    @staticmethod
    def _require_windows() -> None:
        if os.name != "nt":
            raise SecretProtectionError("DPAPI solo está disponible en Windows")

    def protect(self, value: bytes) -> bytes:
        self._require_windows()
        return self._transform("CryptProtectData", value, "Data Express Agent")

    def unprotect(self, value: bytes) -> bytes:
        self._require_windows()
        return self._transform("CryptUnprotectData", value, None)

    def _transform(self, operation: str, value: bytes, description: str | None) -> bytes:
        if not value:
            raise SecretProtectionError("No se puede proteger un secreto vacío")
        input_blob, input_buffer = _blob(value)
        output_blob = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        function = getattr(crypt32, operation)
        if operation == "CryptProtectData":
            success = function(
                ctypes.byref(input_blob),
                description,
                None,
                None,
                None,
                self._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output_blob),
            )
        else:
            success = function(
                ctypes.byref(input_blob),
                None,
                None,
                None,
                None,
                self._CRYPTPROTECT_UI_FORBIDDEN,
                ctypes.byref(output_blob),
            )
        _ = input_buffer
        if not success:
            raise SecretProtectionError(f"DPAPI falló con código {ctypes.GetLastError()}")
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)

