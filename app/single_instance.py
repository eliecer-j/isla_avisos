"""Garantiza una sola instancia en ejecucion (named pipe via QLocalServer)."""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

KEY = "IslaAvisos.single-instance"


class SingleInstance(QObject):
    """Escucha en un canal local; si ya hay otra copia, se lo comunica.

    Nota: en Windows `QLocalServer.listen()` NO falla si ya hay un servidor con
    el mismo nombre, asi que la deteccion se hace intentando conectar primero.
    """

    activated = Signal()

    def __init__(self, key: str = KEY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def try_acquire(self, timeout_ms: int = 500) -> bool:
        """True si esta es la primera instancia.

        Si ya hay otra corriendo, ademas se le pide que muestre la isla.
        """
        if self._ping(timeout_ms, b"show\n"):
            return False
        if not sys.platform.startswith("win"):
            QLocalServer.removeServer(self.key)
        return self._server.listen(self.key)

    def notify_existing(self, timeout_ms: int = 1200) -> bool:
        """Pide a la instancia que ya corre que muestre la isla."""
        return self._ping(timeout_ms, b"show\n")

    # -- interno ----------------------------------------------------------
    def _ping(self, timeout_ms: int, message: bytes | None = None) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(timeout_ms):
            return False
        if message:
            socket.write(message)
            socket.flush()
            socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        socket.waitForDisconnected(timeout_ms)
        return True

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            connection.readyRead.connect(lambda conn=connection: self._read(conn))
            connection.disconnected.connect(connection.deleteLater)

    def _read(self, connection) -> None:
        data = bytes(connection.readAll())
        if b"show" in data:
            self.activated.emit()
        connection.disconnectFromServer()
