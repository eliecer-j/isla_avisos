"""Registro de diagnostico en %APPDATA%\\IslaAvisos\\isla.log (rotado)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.paths import ensure_data_dir, log_path

LOGGER_NAME = "isla_avisos"
_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configura el log una sola vez y devuelve el logger de la app."""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger
    _configured = True
    logger.setLevel(level)
    logger.propagate = False

    ensure_data_dir()
    try:
        handler = RotatingFileHandler(
            log_path(), maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    except OSError:
        # Sin log no pasa nada: la app debe seguir funcionando.
        pass

    logger.info("--- Isla de Avisos iniciada ---")
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
