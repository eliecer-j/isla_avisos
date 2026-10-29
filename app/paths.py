"""Rutas de la aplicacion (config, log, recursos) y deteccion de modo portable.

Funciona igual ejecutando `main.py` con Python o desde el `.exe` empaquetado
con PyInstaller (`sys.frozen` / `sys._MEIPASS`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "IslaAvisos"
APP_DISPLAY_NAME = "Isla de Avisos"
APP_VERSION = "0.1.0"
ORG_NAME = "IslaAvisos"


def is_frozen() -> bool:
    """True si estamos dentro de un ejecutable de PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Carpeta del ejecutable (o la raiz del proyecto en modo script)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """Ruta a un recurso empaquetado, compatible con PyInstaller (onedir/onefile)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return app_dir() / relative


def is_portable() -> bool:
    """Modo portable: build 'portable' o un `portable.txt` junto al ejecutable.

    En ese caso la configuracion y el log se guardan al lado del .exe, para
    poder llevarlo en un USB sin dejar rastro en %APPDATA%.
    """
    if not is_frozen():
        return False
    if resource_path("assets/portable.marker").is_file():
        return True
    return (app_dir() / "portable.txt").is_file()


def data_dir() -> Path:
    """Carpeta de datos: config.json y isla.log."""
    if is_portable():
        return app_dir() / "IslaAvisos-data"
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def ensure_data_dir() -> Path:
    directory = data_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return directory


def config_path() -> Path:
    return data_dir() / "config.json"


def log_path() -> Path:
    return data_dir() / "isla.log"


def icon_path() -> Path:
    """Icono de la aplicacion (assets/isla_avisos.ico dentro del paquete)."""
    return resource_path("assets/isla_avisos.ico")


def execution_command() -> str:
    """Comando para registrar el arranque automatico.

    - Empaquetado (.exe): la propia ruta del ejecutable.
    - Script: pythonw.exe + main.py.
    """
    if is_frozen():
        return f'"{Path(sys.executable).resolve()}"'

    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        executable = pythonw
    entry = app_dir() / "main.py"
    return f'"{executable}" "{entry}"'
