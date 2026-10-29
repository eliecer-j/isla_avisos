#!/usr/bin/env python3
"""Punto de entrada de Isla de Avisos."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import ConfigManager
from app.excel_source import ExcelSource
from app.island_window import IslandWindow
from app.logsetup import get_logger, setup_logging
from app.paths import APP_DISPLAY_NAME, APP_VERSION, ORG_NAME, icon_path
from app.reminder_engine import ReminderEngine
from app.single_instance import SingleInstance
from app.sound import SoundManager
from app.theme import build_icon
from app.tray import Tray


def app_icon() -> QIcon:
    """Icono del .ico empaquetado o, si no existe, el dibujado por codigo."""
    path = icon_path()
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return build_icon()


class IslaAvisosApp:
    """Orquesta los componentes de la aplicacion."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.log = get_logger()

        self.config = ConfigManager()
        self.source = ExcelSource(self.config)
        self.engine = ReminderEngine(self.config, self.source)
        self.island = IslandWindow(self.config)
        self.sound = SoundManager(self.config)
        self.tray = Tray(self.island, self.engine, self.config, self.app)

        self.engine.tasks_changed.connect(self._on_tasks_changed)
        self.engine.reminder.connect(self._on_reminder)
        self.engine.error.connect(self._on_error)

        self.island.open_excel_requested.connect(self._open_excel)
        self.island.config_requested.connect(self.tray.open_settings)
        self.island.pause_toggled.connect(self._toggle_pause)
        self.island.alert_dismissed.connect(self.engine.dismiss)
        self.island.alert_snoozed.connect(self.engine.snooze)

        self.app.aboutToQuit.connect(self._on_quit)

    # ------------------------------------------------------------------ slots
    def _on_tasks_changed(self, tasks) -> None:
        self.island.set_tasks(tasks)
        if tasks:
            self.island.set_status(None)

    def _on_reminder(self, task, message: str, reason: str) -> None:
        self.log.info("Aviso: %s (%s)", message, reason)
        self.island.show_reminder(task, message)
        # Un aviso no debe tapar el dialogo de configuracion si esta abierto.
        self.tray.raise_settings()
        self.tray.sync_visibility_label()
        self.sound.notify(urgent=task.seconds_left < 86400)

    def _on_error(self, message: str) -> None:
        self.log.warning("Error: %s", message)
        self.island.set_status(message)

    def _toggle_pause(self) -> None:
        paused = not self.engine.paused
        self.engine.set_paused(paused)
        self.island.set_paused(paused)
        self.tray.pause_action.setChecked(paused)
        self.config.save()

    def _on_quit(self) -> None:
        self.log.info("Cerrando Isla de Avisos.")
        self.engine.stop()
        self.config.save()

    def _open_excel(self) -> None:
        path = str(self.config.get("excel_path", "") or "")
        if path and os.path.isfile(path):
            os.startfile(path)  # noqa: S606

    def show_island(self) -> None:
        """Trae la isla al frente (p. ej. al abrir una segunda instancia)."""
        if not self.island.isVisible():
            self.island.show()
        self.island.raise_()
        self.island.expand()
        self.tray.sync_visibility_label()

    # ------------------------------------------------------------------ run
    def _first_run(self) -> None:
        """Primer arranque (o sin Excel): abre la configuracion sola."""
        self.config.set("first_run_done", True)
        self.config.save()
        self.tray.open_settings()

    def run(self) -> int:
        self.island.show()
        self.tray.show()
        self.engine.start()

        needs_setup = (
            not self.config.get("first_run_done", False)
            or not str(self.config.get("excel_path", "") or "").strip()
        )
        if needs_setup:
            QTimer.singleShot(700, self._first_run)

        return self.app.exec()


def _install_excepthook(log) -> None:
    def hook(exc_type, exc_value, exc_tb) -> None:
        log.error(
            "Excepcion no controlada:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def main() -> int:
    log = setup_logging()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    # Estilo Fusion: evita que el estilo nativo de Windows interfiera con el QSS.
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())

    _install_excepthook(log)

    # Una sola instancia: si ya corre, se le pide que muestre la isla.
    guard = SingleInstance()
    if not guard.try_acquire():
        log.info("Otra instancia en ejecucion: se le pidio mostrar la isla.")
        return 0

    try:
        controller = IslaAvisosApp(app)
    except Exception as exc:  # noqa: BLE001
        log.exception("Error al iniciar la aplicacion: %s", exc)
        return 1

    guard.activated.connect(controller.show_island)
    log.info("Arranque correcto (version %s).", APP_VERSION)
    return controller.run()


if __name__ == "__main__":
    sys.exit(main())
