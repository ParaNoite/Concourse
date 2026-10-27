"""多平台凭据安全存储（Windows DPAPI，用户范围）。

密钥由 Windows 依据当前登录用户派生，密文文件即使被复制到其它机器/账户
也无法解密。非 Windows 回退到 chmod 600 明文并打印警告。

存储位置：%LOCALAPPDATA%\\concourse\\credentials\\<platform>.dpapi
payload 为任意 dict（JSON），不限于用户名/密码，OAuth token 也能存。
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

APP_DIR_NAME = "concourse"
CRED_DIR_NAME = "credentials"

# CRYPTPROTECT_UI_FORBIDDEN
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _dpapi_protect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(f"CryptProtectData 失败 (err={ctypes.GetLastError()})")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _Blob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError(
            f"CryptUnprotectData 失败 (err={ctypes.GetLastError()})；"
            "可能是凭据由其它 Windows 账户加密的，请 forget 后重新保存。"
        )
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def cred_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME / CRED_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME}" / CRED_DIR_NAME


def path_for(platform: str) -> Path:
    return cred_dir() / f"{platform}.dpapi"


def save(platform: str, payload: dict[str, Any]) -> Path:
    path = path_for(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob_text = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _is_windows():
        path.write_bytes(_dpapi_protect(blob_text))
    else:
        path.write_bytes(blob_text)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        print(
            "[凭据] 警告：当前不是 Windows，DPAPI 不可用，改用文件权限保护明文。",
            file=sys.stderr,
        )
    return path


def load(platform: str) -> dict[str, Any] | None:
    path = path_for(platform)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        data = _dpapi_unprotect(raw) if _is_windows() else raw
        return json.loads(data.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[凭据] 读取 {platform} 失败，将忽略已保存的凭据：{exc}", file=sys.stderr)
        return None


def has(platform: str) -> bool:
    return path_for(platform).exists()


def forget(platform: str) -> bool:
    path = path_for(platform)
    if path.exists():
        path.unlink()
        return True
    return False
