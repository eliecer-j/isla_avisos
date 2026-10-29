"""Motor de recordatorios: decide cuando hay que avisar de una tarea.

Reglas
------
- Cada tarea tiene varios *umbrales*: 15 d, 7 d, 2 d, el vencimiento y (si se
  configura) un aviso en los minutos previos.
- Se avisa siempre del umbral **mas cercano** que ya se ha alcanzado.
- Hasta que el usuario pulsa "Entendido" en un umbral, la app **insiste**:
  como maximo N veces al dia, con una separacion minima y dentro de una franja
  horaria. El contador se reinicia cada dia.
- Pulsar "Entendido" silencia **ese umbral**; la tarea volvera a avisar en el
  umbral siguiente (p. ej. descartar a 15 d -> nuevo aviso a los 7 d).
- "Posponer" silencia solo durante el tiempo indicado.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from app.config import ConfigManager
from app.excel_source import ExcelSource
from app.models import Task, format_message, humanize, reason_text

DEFAULT_REPEAT = {
    "enabled": True,
    "per_day": 3,
    "interval_minutes": 240,
    "window_start": "08:00",
    "window_end": "20:00",
}


@dataclass
class AlertState:
    """Estado de insistencia de un umbral concreto de una tarea."""

    day: Optional[date] = None
    count: int = 0
    last: Optional[datetime] = None
    dismissed: bool = False
    snooze_until: Optional[datetime] = None


def _parse_clock(value: object) -> Optional[time]:
    """'08:00' -> time(8, 0). Devuelve None si esta vacio o es invalido."""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%H.%M", "%H"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


class ReminderEngine(QObject):
    """Vigila el Excel y emite avisos con la anticipacion configurada."""

    tasks_changed = Signal(list)          # list[Task]
    reminder = Signal(object, str, str)   # task, mensaje, motivo
    error = Signal(str)
    alert_cleared = Signal(str)           # identity del aviso descartado/pospuesto

    def __init__(self, config: ConfigManager, source: ExcelSource) -> None:
        super().__init__()
        self.config = config
        self.source = source

        self._tasks: List[Task] = []
        self._state: Dict[str, AlertState] = {}
        self._active: Dict[str, str] = {}   # identity -> clave de umbral vigente
        self._paused = bool(config.get("paused", False))
        self._started = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)

    # -- ciclo de vida ----------------------------------------------------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        interval = max(5, int(self.config.get("check_interval_seconds", 30) or 30))
        self._timer.start(interval * 1000)
        self.reload()
        # Primer barrido casi inmediato: al abrir la app ya se ve lo que vence.
        QTimer.singleShot(600, self.tick)

    def stop(self) -> None:
        self._timer.stop()
        self._started = False

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.config.set("paused", paused)

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def tasks(self) -> List[Task]:
        return list(self._tasks)

    @property
    def active_alerts(self) -> int:
        return len(self._active)

    # -- recarga ----------------------------------------------------------
    def reload(self) -> None:
        """Fuerza la relectura del Excel."""
        try:
            tasks = self.source.load()
        except ValueError as exc:
            self._tasks = []
            self.error.emit(str(exc))
            self.tasks_changed.emit([])
            return
        except Exception as exc:  # noqa: BLE001 - mostrar cualquier error de lectura
            self._tasks = []
            self.error.emit(f"No se pudo leer el Excel: {exc}")
            self.tasks_changed.emit([])
            return

        # Olvida el estado de tareas que ya no existen.
        valid = {t.identity for t in tasks}
        self._state = {
            key: state for key, state in self._state.items()
            if key.split("#", 1)[0] in valid
        }
        self._active = {
            identity: key for identity, key in self._active.items()
            if identity in valid
        }

        self._tasks = tasks
        self.tasks_changed.emit(list(tasks))

    # -- acciones del usuario ---------------------------------------------
    def dismiss(self, identity: str) -> None:
        """El usuario ha descartado el aviso: no insistir en este umbral."""
        key = self._active.get(identity)
        if key is None:
            return
        state = self._state.setdefault(key, AlertState())
        state.dismissed = True
        state.snooze_until = None
        self._active.pop(identity, None)
        self.alert_cleared.emit(identity)

    def snooze(self, identity: str, minutes: Optional[int] = None) -> None:
        """Posponer el aviso: silenciarlo durante un rato."""
        key = self._active.get(identity)
        if key is None:
            return
        try:
            delay = int(minutes if minutes is not None else self.config.get("snooze_minutes", 60))
        except (TypeError, ValueError):
            delay = 60
        delay = max(1, delay)

        now = datetime.now()
        state = self._state.setdefault(key, AlertState())
        state.snooze_until = now + timedelta(minutes=delay)
        # Al expirar el snooze se debe poder avisar de inmediato.
        interval = self._interval()
        state.last = state.snooze_until - interval
        self._active.pop(identity, None)
        self.alert_cleared.emit(identity)

    def forget(self, identity: str) -> None:
        """Descarta el aviso vigente sin marcar el umbral (p. ej. al plegar)."""
        self._active.pop(identity, None)

    # -- configuracion auxiliar -------------------------------------------
    def _template(self) -> str:
        return str(self.config.get("message_template", "") or "").strip()

    def _repeat(self) -> Dict:
        stored = self.config.get("repeat", {}) or {}
        merged = dict(DEFAULT_REPEAT)
        if isinstance(stored, dict):
            merged.update({k: v for k, v in stored.items() if v is not None})
        return merged

    def _interval(self) -> timedelta:
        repeat = self._repeat()
        try:
            minutes = int(repeat.get("interval_minutes", 240))
        except (TypeError, ValueError):
            minutes = 240
        return timedelta(minutes=max(1, minutes))

    def _sorted_leads(self) -> List[int]:
        leads = self.config.get("reminders_days", [15, 7, 2]) or []
        cleaned = []
        for value in leads:
            try:
                days = int(value)
            except (TypeError, ValueError):
                continue
            if days > 0:
                cleaned.append(days)
        return sorted(set(cleaned), reverse=True)

    @staticmethod
    def _in_window(now: datetime, repeat: Dict) -> bool:
        start = _parse_clock(repeat.get("window_start"))
        end = _parse_clock(repeat.get("window_end"))
        if start is None or end is None:
            return True
        current = now.time()
        if start <= end:
            return start <= current <= end
        # Franja que cruza la medianoche (p. ej. 22:00 - 06:00).
        return current >= start or current <= end

    # -- comprobacion periodica -------------------------------------------
    def tick(self) -> None:
        if self.source.changed():
            self.reload()

        if self._paused:
            return

        now = datetime.now()
        leads = self._sorted_leads()
        pending: List[Tuple[Task, str, str, str]] = []

        for task in self._tasks:
            if task.done:
                continue
            found = self._evaluate(task, now, leads)
            if found is not None:
                pending.append(found)

        # No lanzamos varios avisos de golpe: mostramos el mas urgente.
        if not pending:
            return
        pending.sort(key=lambda item: item[0].seconds_left)
        task, key, message, reason = pending[0]
        # Solo el aviso mostrado consume su cupo de insistencia.
        self._commit_alert(key, now)
        self._active[task.identity] = key
        self.reminder.emit(task, message, reason)

    def _evaluate(self, task: Task, now: datetime,
                  leads: List[int]) -> Optional[Tuple[Task, str, str, str]]:
        """Devuelve (task, clave, mensaje, motivo) si hay que avisar ahora."""
        due_at = task.due_at

        minutes = int(self.config.get("imminent_minutes", 0) or 0)
        if minutes > 0 and due_at - timedelta(minutes=minutes) <= now < due_at:
            key = "min"
            reason = reason_text(task, "soon", humanize((due_at - now).total_seconds()))
        elif now >= due_at:
            key = "due"
            reason = reason_text(task, "overdue", humanize((now - due_at).total_seconds()))
        else:
            # El umbral se cuenta por dias naturales: "15 dias antes" es el dia
            # 15, no las 23:59 del dia 16 (si no, el aviso saldria al dia
            # siguiente, a las 08:00, hablando de "14 dias").
            hoy = now.date()
            applicable = [
                lead for lead in leads if hoy >= task.due_date - timedelta(days=lead)
            ]
            if not applicable:
                return None
            imminent = min(applicable)
            key = f"d{imminent}"
            days = task.days_left
            if days <= 0:
                reason = reason_text(task, "today")
            elif days == 1:
                reason = reason_text(task, "tomorrow")
            else:
                reason = reason_text(task, "days", str(days))

        full_key = f"{task.identity}#{key}"
        if not self._should_notify(full_key, now):
            return None

        message = format_message(self._template(), task, reason)
        return (task, full_key, message, reason)

    def _should_notify(self, key: str, now: datetime) -> bool:
        """Decide si toca avisar de un umbral. NO modifica el estado.

        El contador se actualiza en `_commit_alert`, para que solo cuente el
        aviso que de verdad se ha mostrado (de los cercanos se enseña uno).
        """
        state = self._state.get(key)

        if state is not None:
            if state.dismissed:
                return False
            if state.snooze_until is not None and now < state.snooze_until:
                return False

        repeat = self._repeat()

        # La franja horaria se respeta siempre (incluido el primer aviso del dia).
        if not self._in_window(now, repeat):
            return False

        same_day = state is not None and state.day == now.date()
        count = state.count if same_day else 0

        # Primer aviso del dia para este umbral: siempre sale.
        if count == 0:
            return True

        if not repeat.get("enabled", True):
            return False

        try:
            per_day = int(repeat.get("per_day", 3))
        except (TypeError, ValueError):
            per_day = 3
        if per_day <= 1 or count >= per_day:
            return False

        if state.last is not None and now - state.last < self._interval():
            return False

        return True

    def _commit_alert(self, key: str, now: datetime) -> None:
        """Registra que el aviso de este umbral se ha mostrado ahora mismo."""
        state = self._state.get(key)
        if state is None:
            state = AlertState()
            self._state[key] = state

        if state.day != now.date():
            state.day = now.date()
            state.count = 0

        if state.snooze_until is not None and now >= state.snooze_until:
            state.snooze_until = None

        state.count += 1
        state.last = now
