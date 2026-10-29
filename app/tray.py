"""Icono y menu de la bandeja del sistema."""
from __future__ import annotations

import os

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app import autostart
from app.config import ConfigManager
from app.island_window import IslandWindow
from app.reminder_engine import ReminderEngine
from app.theme import build_icon


class Tray(QSystemTrayIcon):
    """Gestiona el menu del icono de la bandeja."""

    def __init__(self, island: IslandWindow, engine: ReminderEngine,
                 config: ConfigManager, app) -> None:
        super().__init__(build_icon(), island)
        self.island = island
        self.engine = engine
        self.config = config
        self.app = app

        self.setToolTip("Isla de Avisos")
        self._settings_dialog = None
        self._build_menu()
        self.activated.connect(self._on_activated)
        self.island.hide_requested.connect(self.hide_island)

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        menu = QMenu()

        self.visibility_action = QAction("Ocultar isla", menu)
        self.visibility_action.triggered.connect(self._toggle_visibility)
        menu.addAction(self.visibility_action)

        recenter_action = QAction("Recentrar arriba", menu)
        recenter_action.triggered.connect(self.island.recenter)
        menu.addAction(recenter_action)

        reload_action = QAction("Recargar Excel", menu)
        reload_action.triggered.connect(self.engine.reload)
        menu.addAction(reload_action)

        self.pause_action = QAction("Pausar avisos", menu)
        self.pause_action.setCheckable(True)
        self.pause_action.setChecked(self.engine.paused)
        self.pause_action.toggled.connect(self._toggle_pause)
        menu.addAction(self.pause_action)

        menu.addSeparator()

        config_action = QAction("Configuración…", menu)
        config_action.triggered.connect(self.open_settings)
        menu.addAction(config_action)

        open_excel_action = QAction("Abrir Excel", menu)
        open_excel_action.triggered.connect(self._open_excel)
        menu.addAction(open_excel_action)

        menu.addSeparator()

        self.autostart_action = QAction("Iniciar con Windows", menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.setEnabled(autostart.is_supported())
        self.autostart_action.toggled.connect(self._toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()

        quit_action = QAction("Salir", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        self._menu = menu
        self.setContextMenu(menu)

    # ------------------------------------------------------------------ acciones
    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.island.toggle()

    def _toggle_visibility(self) -> None:
        if self.island.isVisible():
            self.island.hide()
        else:
            self.island.show()
        self.sync_visibility_label()

    def sync_visibility_label(self) -> None:
        self.visibility_action.setText(
            "Ocultar isla" if self.island.isVisible() else "Mostrar isla"
        )

    def hide_island(self) -> None:
        """Quita la isla de la pantalla (peticion del boton de la isla)."""
        self.island.hide()
        self.sync_visibility_label()

    def _toggle_pause(self, paused: bool) -> None:
        self.engine.set_paused(paused)
        self.island.set_paused(paused)
        self.config.save()

    def _toggle_autostart(self, enabled: bool) -> None:
        autostart.apply(enabled)

    def _open_excel(self) -> None:
        path = str(self.config.get("excel_path", "") or "")
        if path and os.path.isfile(path):
            os.startfile(path)  # noqa: S606 - abrir con la app por defecto

    def open_settings(self) -> None:
        from app.config_dialog import ConfigDialog

        # Si ya esta abierto, solo lo trae al frente (no abre dos).
        if self._settings_dialog is not None:
            self.raise_settings()
            return

        dialog = ConfigDialog(self.config)
        self._settings_dialog = dialog
        try:
            accepted = bool(dialog.exec())
        finally:
            self._settings_dialog = None

        if accepted:
            self.engine.set_paused(bool(self.config.get("paused", False)))
            self.island.set_paused(bool(self.config.get("paused", False)))
            self.engine.reload()
            self.island.recenter()

    def raise_settings(self) -> None:
        """Pone el dialogo de configuracion por delante de la isla."""
        dialog = self._settings_dialog
        if dialog is not None and dialog.isVisible():
            dialog.raise_over_island()
