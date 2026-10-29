"""Sonido de notificacion (usa winsound de Windows)."""
from __future__ import annotations

from app.config import ConfigManager


class SoundManager:
    """Reproduce un aviso sonoro si esta habilitado."""

    def __init__(self, config: ConfigManager) -> None:
        self.config = config

    def notify(self, urgent: bool = False) -> None:
        if not self.config.get("sound_enabled", True):
            return
        try:
            import winsound

            sound = winsound.MB_ICONHAND if urgent else winsound.MB_ICONASTERISK
            winsound.MessageBeep(sound)
        except Exception:  # noqa: BLE001 - nunca debe romper la app
            try:
                from PySide6.QtWidgets import QApplication

                QApplication.beep()
            except Exception:  # noqa: BLE001
                pass
