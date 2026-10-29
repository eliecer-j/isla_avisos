"""Modelos de datos de Isla de Avisos."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Dict, Optional


# Texto que se muestra para el verbo del aviso ("{accion}").
ACTION_LABELS = {
    "vence": "vence contrato",
    "notificar": "notificar vencimiento",
}


class Priority(Enum):
    """Prioridad de una tarea."""

    LOW = "baja"
    MEDIUM = "media"
    HIGH = "alta"
    CRITICAL = "critica"

    @classmethod
    def from_text(cls, value: object) -> "Priority":
        """Convierte texto libre (o numero) en una prioridad."""
        if value is None:
            return cls.MEDIUM

        text = str(value).strip().lower()
        mapping = {
            "baja": cls.LOW, "bajo": cls.LOW, "low": cls.LOW, "1": cls.LOW,
            "media": cls.MEDIUM, "medio": cls.MEDIUM, "normal": cls.MEDIUM,
            "medium": cls.MEDIUM, "2": cls.MEDIUM, "": cls.MEDIUM,
            "alta": cls.HIGH, "alto": cls.HIGH, "high": cls.HIGH,
            "importante": cls.HIGH, "3": cls.HIGH,
            "critica": cls.CRITICAL, "crítica": cls.CRITICAL,
            "critical": cls.CRITICAL, "urgente": cls.CRITICAL, "4": cls.CRITICAL,
        }
        return mapping.get(text, cls.MEDIUM)

    @property
    def label(self) -> str:
        return {
            "baja": "Baja",
            "media": "Media",
            "alta": "Alta",
            "critica": "Crítica",
        }[self.value]

    @property
    def color(self) -> str:
        return {
            "baja": "#30d158",
            "media": "#0a84ff",
            "alta": "#ff9f0a",
            "critica": "#ff453a",
        }[self.value]

    @property
    def rank(self) -> int:
        """Menor = mas prioritario (para ordenar)."""
        return {"critica": 0, "alta": 1, "media": 2, "baja": 3}[self.value]


def humanize(seconds: float) -> str:
    """Convierte una cantidad de segundos en texto corto (3 h 12 min)."""
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60

    if days >= 1:
        return f"{days} d {hours} h" if hours else f"{days} d"
    if hours >= 1:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    if minutes >= 1:
        return f"{minutes} min"
    return "menos de 1 min"


@dataclass
class Task:
    """Una tarea leida del Excel."""

    title: str
    due_date: date
    due_time: Optional[time] = None
    notes: str = ""
    priority: Priority = Priority.MEDIUM
    done: bool = False
    source_row: int = 0
    detail: str = ""
    # Verbo del aviso: "vence" (vencimiento) o "notificar" (fecha de notificacion).
    action: str = "vence"

    @property
    def due_at(self) -> datetime:
        """Momento exacto de vencimiento (si no hay hora, fin del dia)."""
        if self.due_time is not None:
            return datetime.combine(self.due_date, self.due_time)
        return datetime.combine(self.due_date, time(23, 59))

    @property
    def seconds_left(self) -> float:
        return (self.due_at - datetime.now()).total_seconds()

    @property
    def days_left(self) -> int:
        return (self.due_date - date.today()).days

    @property
    def is_past(self) -> bool:
        return not self.done and self.seconds_left < 0

    @property
    def is_today(self) -> bool:
        return self.due_date == date.today()

    @property
    def urgency_color(self) -> str:
        """Color segun lo cerca que este la tarea."""
        if self.done:
            return "#30d158"
        seconds = self.seconds_left
        if seconds < 0:
            return "#ff453a"
        if seconds <= 86400:
            return "#ff453a"
        if seconds <= 3 * 86400:
            return "#ff9f0a"
        if seconds <= 7 * 86400:
            return "#ffd60a"
        return "#30d158"

    @property
    def sort_key(self) -> tuple:
        return (self.done, self.due_at, self.priority.rank)

    def countdown_text(self) -> str:
        """Texto de cuenta atras para mostrar en la isla."""
        if self.done:
            return "Hecha"

        seconds = self.seconds_left
        if seconds < 0:
            if self.action == "notificar":
                return f"Sin notificar desde hace {humanize(-seconds)}"
            return f"Vencida hace {humanize(-seconds)}"

        if self.due_time is not None and seconds <= 86400:
            return f"En {humanize(seconds)}"

        days = self.days_left
        if days <= 0:
            return "Hoy"
        if days == 1:
            return "Mañana"
        if days < 14:
            return f"En {days} días"
        return f"En {days // 7} semanas"

    def display_date(self) -> str:
        return self.due_date.strftime("%d/%m/%Y")

    def display_time(self) -> str:
        if self.due_time is None:
            return ""
        return self.due_time.strftime("%H:%M")

    def short_countdown(self) -> str:
        """Cuenta atras compacta, para la pastilla plegada."""
        if self.done:
            return "Hecha"
        if self.is_past:
            return "Pendiente" if self.action == "notificar" else "Vencida"
        return self.countdown_text()

    @property
    def identity(self) -> str:
        """Clave estable para saber si es 'la misma' tarea.

        Incluye la accion, porque una misma fila puede dar dos avisos (el
        vencimiento del contrato y la fecha de notificacion).
        """
        return (f"{self.title}|{self.due_date.isoformat()}"
                f"|{self.source_row}|{self.action}")

    @property
    def action_label(self) -> str:
        """Verbo del aviso tal como se escribe en el mensaje."""
        return ACTION_LABELS.get(self.action, self.action)

    def placeholder_values(self, reason: str = "") -> Dict[str, str]:
        """Valores disponibles para la plantilla del mensaje."""
        days = self.days_left
        if self.is_past:
            days_text = "0"
        else:
            days_text = str(max(0, days))
        return {
            "titulo": self.title,
            "detalle": self.detail,
            "fecha": self.display_date(),
            "hora": self.display_time(),
            "dias": days_text,
            "prioridad": self.priority.label,
            "notas": self.notes,
            "motivo": reason,
            "accion": self.action_label,
        }


class _SafeDict(dict):
    """Deja intacto un marcador desconocido en vez de lanzar KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_message(template: str, task: Task, reason: str = "") -> str:
    """Aplica la plantilla del aviso, limpiando separadores huerfanos.

    Si un campo esta vacio (p. ej. 'Detalle'), se elimina tambien el separador
    que lo precede, para no dejar ": " sueltos.
    """
    values = task.placeholder_values(reason)
    text = str(template or "").strip()
    if not text:
        text = "{titulo}: {motivo}"

    for key, value in values.items():
        if value:
            continue
        text = text.replace(": {" + key + "}", "")
        text = text.replace("{ " + key + "}", "")
        text = text.replace("{" + key + "}", "")

    try:
        text = text.format_map(_SafeDict(values))
    except (IndexError, ValueError):
        text = f"{task.title} · {reason}".strip(" ·")

    # Limpia separadores que quedan huerfanos cuando un campo esta vacio:
    # "AREA · : vence" -> "AREA: vence"  |  "JUAN · · 1 AÑO" -> "JUAN · 1 AÑO"
    for _ in range(4):
        previous = text
        text = re.sub(r"\(\s*\)", "", text)
        text = re.sub(r"\s{2,}", " ", text)
        text = re.sub(r"\s*[·•|]\s*(?=[:;,.]|\s*$)", "", text)
        text = re.sub(r"\s*[·•|](\s*[·•|])+", " · ", text)
        text = re.sub(r"([·•|,;])\s*:", r"\1:", text)
        text = re.sub(r":\s*[·•|,;]+\s*", ": ", text)
        text = re.sub(r"\s+([,.;:])", r"\1", text)
        if text == previous:
            break

    text = text.strip(" ··-:;,.")
    return text or task.title


def reason_text(task: Task, kind: str, amount: str = "") -> str:
    """Frase corta del motivo, adaptada al verbo de la tarea.

    `kind` es "today", "tomorrow", "days" (con `amount` = número de días),
    "soon" (con `amount` = tiempo restante) u "overdue".
    """
    notificar = task.action == "notificar"
    if kind == "today":
        return "Notificar hoy" if notificar else "Vence hoy"
    if kind == "tomorrow":
        return "Notificar mañana" if notificar else "Vence mañana"
    if kind == "days":
        return f"Notificar en {amount} días" if notificar else f"Vence en {amount} días"
    if kind == "soon":
        return f"Notificar en {amount}" if notificar else f"Vence en {amount}"
    if kind == "overdue":
        return f"Sin notificar desde hace {amount}" if notificar else f"Vencido hace {amount}"
    return task.action_label.capitalize()

