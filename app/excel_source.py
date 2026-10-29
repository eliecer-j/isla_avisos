"""Lectura del Excel de tareas (solo lectura) con deteccion de cambios."""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook

from app.config import ConfigManager
from app.models import Priority, Task

# Palabras clave para adivinar las columnas si aun no hay mapeo guardado.
_DATE_HINTS = ("fecha venc", "vencimiento", "venc", "vence", "fecha limite", "límite",
               "fecha", "date", "plazo", "dia", "día")
_TIME_HINTS = ("hora", "time", "hour")
_TITLE_HINTS = ("empleado", "trabajador", "colaborador", "funcionario", "persona",
                "tarea", "titulo", "título", "title", "asunto", "descripcion",
                "descripción", "evento", "nombre")
_DETAIL_HINTS = ("area", "área", "dependencia", "sede", "seccion", "sección",
                 "detalle", "detail", "tipo", "cargo", "puesto", "contrato",
                 "concepto", "categoria", "categoría")
_NOTES_HINTS = ("nota", "note", "observ", "comentario", "observacion",
                "observación", "vigencia")
# Columna opcional con la fecha en la que hay que notificar al empleado.
_NOTIFY_HINTS = ("notificacion", "notificación", "notificar")
_PRIORITY_HINTS = ("prioridad", "priority", "importancia")
_STATUS_HINTS = ("estado", "status", "hecho", "hecha", "completado", "done", "finalizado")

# Columnas que NO son la fecha de vencimiento aunque contengan "fecha".
_DATE_AVOID = ("inicio", "creacion", "creación", "notificacion", "notificación",
               "prorroga", "prórroga", "radicacion", "radicación", "expedicion",
               "expedición", "ingreso", "nacimiento")

# Orden en el que se adivinan las columnas (las mas especificas primero).
_MAPPING_KEYS = ("date", "notify_date", "time", "title", "detail", "priority",
                 "status", "notes")

_DATE_FORMATS = (
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%y", "%m/%d/%Y", "%Y%m%d",
)

# Meses en espanol, para fechas escritas a mano ("11 de diciembre de 2025").
_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Valores que significan "sin fecha" (contratos indefinidos, celdas vacias...).
_NO_DATE_WORDS = {
    "", "n/a", "na", "n.a", "-", "--", "---", "sin fecha", "no aplica",
    "no aplicable", "pendiente", "por definir", "indefinido", "no", "null",
}
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%H.%M", "%H h", "%Hhs")
_DONE_WORDS = {"si", "sí", "s", "x", "1", "true", "hecho", "hecha", "hechas",
               "completado", "completada", "ok", "done", "finalizado", "finalizada"}


# --------------------------------------------------------------------------
# Parseo de valores
# --------------------------------------------------------------------------
def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _clean_header(value: Any) -> str:
    """Nombre de columna sin espacios repetidos ('VIGENCIA  DEL CONTRATO')."""
    return " ".join(_as_text(value).split())


def _normalize(text: str) -> str:
    """Mayusculas, sin puntos y con espacios simples (para comparar textos)."""
    return " ".join(text.upper().replace(".", " ").replace(",", " ").split())


def _parse_spanish_date(text: str) -> Optional[date]:
    """Entiende '11 de diciembre de 2025' o '13 DE FEBRERO 2026'."""
    parts = text.split()
    try:
        day_index = next(i for i, part in enumerate(parts) if part.isdigit())
    except StopIteration:
        return None

    day = int(parts[day_index])
    month_word = next(
        (part.lower() for part in parts[day_index + 1:] if part.lower() in _MESES_ES),
        None,
    )
    if month_word is None:
        return None

    year = next(
        (int(part) for part in parts[day_index + 1:]
         if part.isdigit() and len(part) == 4),
        None,
    )
    if year is None:
        return None

    try:
        return date(year, _MESES_ES[month_word], day)
    except ValueError:
        return None


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
        except (OverflowError, ValueError):
            return None

    text = _as_text(value)
    if not text:
        return None

    normalized = _normalize(text)
    if normalized.lower() in _NO_DATE_WORDS:
        return None

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # "2027-12-10 00:00:00" o "10/12/2027 08:30": probar solo la fecha.
    head = text.split()[0]
    if head != text:
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(head, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(head).date()
        except ValueError:
            pass

    # Fecha escrita a mano en espanol ("09 DE MARZO DE 2027").
    return _parse_spanish_date(normalized)


def parse_time(value: Any) -> Optional[time]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)
    if isinstance(value, (int, float)):
        fraction = float(value) % 1
        total_minutes = round(fraction * 24 * 60)
        return time((total_minutes // 60) % 24, total_minutes % 60)

    text = _as_text(value).lower()
    if not text:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    if text.isdigit() and len(text) <= 2:
        return time(int(text) % 24, 0)
    return None


def _guess_column(headers: List[Tuple[int, str]], hints: Tuple[str, ...]) -> Optional[int]:
    """Devuelve el indice de la primera columna cuyo encabezado encaje."""
    lowered = [(idx, name.lower()) for idx, name in headers]
    for hint in hints:
        for idx, name in lowered:
            if hint in name:
                return idx
    return None


# --------------------------------------------------------------------------
# Fuente de datos
# --------------------------------------------------------------------------
class ExcelSource:
    """Lee las tareas del Excel indicado en la configuracion."""

    def __init__(self, config: ConfigManager) -> None:
        self.config = config
        self._last_mtime: Optional[float] = None

    # -- estado del archivo ----------------------------------------------
    @property
    def path(self) -> str:
        return str(self.config.get("excel_path", "") or "")

    def exists(self) -> bool:
        return bool(self.path) and Path(self.path).is_file()

    def current_mtime(self) -> float:
        try:
            return os.path.getmtime(self.path)
        except OSError:
            return 0.0

    def changed(self) -> bool:
        mtime = self.current_mtime()
        if mtime == 0.0:
            return False
        if self._last_mtime is None:
            return True
        return mtime != self._last_mtime

    # -- acceso al libro --------------------------------------------------
    def _open(self):
        wb = load_workbook(self.path, read_only=True, data_only=True)
        sheet_name = str(self.config.get("sheet_name", "") or "")
        if sheet_name and sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            ws = wb.active
        return wb, ws

    def read_headers(self) -> List[Tuple[int, str]]:
        """Devuelve [(indice, nombre)] de la fila de encabezados."""
        header_row = int(self.config.get("header_row", 1) or 1)
        wb, ws = self._open()
        try:
            row = next(
                ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True),
                None,
            )
        finally:
            wb.close()
        if not row:
            return []
        headers: List[Tuple[int, str]] = []
        for idx, value in enumerate(row):
            name = _clean_header(value)
            if name:
                headers.append((idx, name))
        return headers

    def sheet_names(self) -> List[str]:
        if not self.exists():
            return []
        wb = load_workbook(self.path, read_only=True, data_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def suggest_mapping(self) -> Dict[str, str]:
        """Sugiere un mapeo de columnas a partir de los encabezados.

        Se puntua cada encabezado segun el orden de las palabras clave (las
        primeras pesan mas) y se descartan los que no pueden serlo, como
        "FECHA INICIO CONTRATO" para la columna de vencimiento.
        """
        headers = self.read_headers()
        suggestion: Dict[str, str] = {}
        used: set[int] = set()

        def pick(hints: Tuple[str, ...], avoid: Tuple[str, ...] = ()) -> Optional[int]:
            best: Optional[Tuple[int, int]] = None
            for idx, name in headers:
                if idx in used:
                    continue
                low = name.lower()
                if any(word in low for word in avoid):
                    continue
                score = 0
                for position, hint in enumerate(hints):
                    if hint in low:
                        score = max(score, len(hints) - position)
                if score and (best is None or score > best[1]):
                    best = (idx, score)
            if best is None:
                return None
            used.add(best[0])
            return best[0]

        for key, hints in (
            ("time", _TIME_HINTS),
            ("title", _TITLE_HINTS),
            ("detail", _DETAIL_HINTS),
            ("priority", _PRIORITY_HINTS),
            ("status", _STATUS_HINTS),
            ("notes", _NOTES_HINTS),
        ):
            idx = pick(hints)
            if idx is not None:
                suggestion[key] = dict(headers)[idx]

        # La fecha va al final: es la que mas se puede confundir.
        idx = pick(_DATE_HINTS, _DATE_AVOID)
        if idx is None:
            idx = pick(_DATE_HINTS)
        if idx is not None:
            suggestion["date"] = dict(headers)[idx]

        # Fecha de notificacion (opcional), despues de la de vencimiento.
        idx = pick(_NOTIFY_HINTS)
        if idx is not None:
            suggestion["notify_date"] = dict(headers)[idx]

        return suggestion

    # -- lectura de tareas ------------------------------------------------
    def _resolve_columns(self, headers: List[Tuple[int, str]]) -> Dict[str, int]:
        by_name = {_clean_header(name).lower(): idx for idx, name in headers}
        column_map = self.config.get("column_map", {}) or {}
        resolved: Dict[str, int] = {}
        for key in ("date", "notify_date", "time", "title", "detail", "notes",
                    "priority", "status"):
            wanted = _clean_header(column_map.get(key, ""))
            if not wanted:
                continue
            if wanted.isdigit():
                resolved[key] = int(wanted)
            elif wanted.lower() in by_name:
                resolved[key] = by_name[wanted.lower()]
        return resolved

    def load(self) -> List[Task]:
        """Devuelve la lista de tareas ordenada. Lanza ValueError si falta algo."""
        if not self.path:
            raise ValueError("No hay ninguna ruta de Excel configurada.")
        if not self.exists():
            raise ValueError(f"No se encuentra el archivo Excel:\n{self.path}")

        header_row = int(self.config.get("header_row", 1) or 1)
        ignore_expired = bool(self.config.get("ignore_expired", True))
        today = date.today()
        wb, ws = self._open()
        try:
            headers = [
                (idx, _clean_header(value))
                for idx, value in enumerate(
                    next(ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True), ())
                )
                if _clean_header(value)
            ]
            columns = self._resolve_columns(headers)
            if "title" not in columns or "date" not in columns:
                raise ValueError(
                    "El mapeo de columnas está incompleto: se necesita al menos "
                    "una columna de Tarea y una de Fecha. Abre 'Configuración' "
                    "para asignarlas."
                )

            tasks: List[Task] = []
            for row_number, row in enumerate(
                ws.iter_rows(min_row=header_row + 1, values_only=True),
                start=header_row + 1,
            ):
                title = _as_text(row[columns["title"]]) if columns["title"] < len(row) else ""
                if not title:
                    continue

                raw_date = row[columns["date"]] if columns["date"] < len(row) else None
                due_date = parse_date(raw_date)
                if due_date is None:
                    continue
                # Los contratos ya vencidos solo generan ruido: se omiten.
                if ignore_expired and due_date < today:
                    continue

                due_time = None
                if "time" in columns and columns["time"] < len(row):
                    due_time = parse_time(row[columns["time"]])

                notes = ""
                if "notes" in columns and columns["notes"] < len(row):
                    notes = _as_text(row[columns["notes"]])

                detail = ""
                if "detail" in columns and columns["detail"] < len(row):
                    detail = _as_text(row[columns["detail"]])

                priority = Priority.MEDIUM
                if "priority" in columns and columns["priority"] < len(row):
                    priority = Priority.from_text(row[columns["priority"]])

                done = False
                if "status" in columns and columns["status"] < len(row):
                    done = _as_text(row[columns["status"]]).lower() in _DONE_WORDS

                tasks.append(
                    Task(
                        title=title,
                        due_date=due_date,
                        due_time=due_time,
                        notes=notes,
                        priority=priority,
                        done=done,
                        source_row=row_number,
                        detail=detail,
                        action="vence",
                    )
                )

                # Aviso extra: la fecha en la que hay que notificar al empleado.
                if "notify_date" in columns and columns["notify_date"] < len(row):
                    notify_date = parse_date(row[columns["notify_date"]])
                    if (notify_date is not None and notify_date != due_date
                            and not (ignore_expired and notify_date < today)):
                        tasks.append(
                            Task(
                                title=title,
                                due_date=notify_date,
                                notes=notes,
                                priority=priority,
                                done=done,
                                source_row=row_number,
                                detail=detail,
                                action="notificar",
                            )
                        )
        finally:
            wb.close()

        tasks.sort(key=lambda t: t.sort_key)
        self._last_mtime = self.current_mtime()
        return tasks
