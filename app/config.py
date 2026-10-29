"""Gestion de configuracion persistente (JSON en %APPDATA%\\IslaAvisos)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

from app.paths import APP_VERSION, config_path

DEFAULT_TEMPLATE = "{titulo} · {detalle} · {notas}: {accion} el {fecha} (en {dias} días)"

DEFAULTS: Dict[str, Any] = {
    "excel_path": "",
    "sheet_name": "",
    "header_row": 1,
    # Mapeo de columnas: clave semantica -> nombre del encabezado en el Excel
    "column_map": {
        "detail": "Detalle",
        "date": "Fecha",
        # Columna opcional: genera un aviso extra para notificar al empleado
        "notify_date": "",
        "time": "Hora",
        "title": "Tarea",
        "notes": "Notas",
        "priority": "Prioridad",
        "status": "Estado",
    },
    # Texto del aviso. Marcadores: {titulo} {detalle} {fecha} {hora} {dias}
    # {prioridad} {notas} {accion} {motivo}
    "message_template": DEFAULT_TEMPLATE,
    # Anticipaciones en dias (15 dias, 1 semana, 2 dias por defecto)
    "reminders_days": [15, 7, 2],
    # Si el Excel no trae la fecha de notificacion, se calcula sola: el
    # vencimiento menos estos dias. 0 = no generar ese aviso.
    "notify_offset_days": 15,
    # Aviso extra cuando falten pocos minutos
    "imminent_minutes": 30,
    # No mostrar lo que ya vencio (solo genera ruido)
    "ignore_expired": True,
    # Insistir hasta que el usuario descarte el aviso
    "repeat": {
        "enabled": True,
        "per_day": 3,             # avisos como maximo por dia y umbral
        "interval_minutes": 240,  # separacion minima entre avisos (4 h)
        "window_start": "08:00",  # franja en la que se permite insistir
        "window_end": "20:00",
    },
    "snooze_minutes": 60,         # "Posponer 1 h"
    "check_interval_seconds": 30,
    # Segundos que la isla se queda abierta sola tras un aviso
    "expand_seconds": 8,
    # Segundos que se queda abierta despues de quitar el raton de encima
    "collapse_after_hover_seconds": 15,
    "sound_enabled": True,
    "paused": False,
    "first_run_done": False,
    # Posicion / tamano
    "screen_index": 0,
    "offset_y": 10,
    "island": {
        "collapsed_width": 240,
        "collapsed_height": 46,
        "expanded_width": 380,
        "expanded_height": 440,
    },
}


def config_dir() -> Path:
    return config_path().parent


class ConfigManager:
    """Lectura/escritura de la configuracion con soporte de rutas 'a.b'."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else config_path()
        self._data: Dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # -- carga / guardado -------------------------------------------------
    def load(self) -> Dict[str, Any]:
        if self.path.is_file():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    self._merge(self._data, stored)
            except (OSError, ValueError):
                pass
        return self._data

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    @staticmethod
    def _merge(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                ConfigManager._merge(base[key], value)
            else:
                base[key] = value

    # -- acceso -----------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    @property
    def version(self) -> str:
        return APP_VERSION
