"""Arranque automatico con Windows (registro HKCU\\...\\Run)."""
from __future__ import annotations

import sys

from app.paths import execution_command

APP_NAME = "IslaAvisos"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    """Comando a registrar: el .exe instalado o pythonw + main.py en modo script."""
    return execution_command()


def is_supported() -> bool:
    return sys.platform.startswith("win")


def is_enabled() -> bool:
    if not is_supported():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def enable() -> bool:
    if not is_supported():
        return False
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
        return True
    except OSError:
        return False


def disable() -> bool:
    if not is_supported():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except OSError:
        return False


def apply(enabled: bool) -> bool:
    return enable() if enabled else disable()
