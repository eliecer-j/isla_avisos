# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado en un solo archivo (onefile): version portable para USB.

Incluye el marcador `assets/portable.marker`, que hace que la configuracion y
el log se guarden junto al .exe en vez de en %APPDATA%.
"""
from pathlib import Path

ROOT = Path(SPECPATH)
ICON = str(ROOT / "assets" / "isla_avisos.ico")
VERSION_FILE = str(ROOT / "build" / "version_info.txt")
MARKER = ROOT / "build" / "portable.marker"

EXCLUDES = [
    "pywin32", "win32", "win32com", "win32api", "win32con", "win32evtlog",
    "win32evtlogutil", "pythoncom", "pywintypes",
    "PyQt5", "PyQt6", "PySide2", "tkinter", "matplotlib", "numpy", "pandas",
    "PIL", "scipy", "IPython", "pytest", "setuptools", "pip",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets" / "isla_avisos.ico"), "assets"),
        (str(MARKER), "assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="IslaAvisos-Portable",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=VERSION_FILE,
)
