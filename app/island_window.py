"""Ventana 'isla' flotante al estilo Dynamic Island."""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPropertyAnimation,
                            QRect, QRectF, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from app.config import ConfigManager
from app.models import Task
from app.theme import (ISLAND_COLOR, ISLAND_OPACITY, ISLAND_RADIUS,
                       ISLAND_RADIUS_EXPANDED, ISLAND_STYLE, TASK_ROW_STYLE)

# Tiempos de la animacion (la isla real usa un muelle corto con rebote minimo).
_EXPAND_MS = 400
_COLLAPSE_MS = 260
_FADE_IN_MS = 180
_FADE_IN_DELAY_MS = 120


class _Surface(QFrame):
    """Contenedor que pinta su propio fondo redondeado (independiente del tema)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("container")
        color = QColor(ISLAND_COLOR)
        color.setAlpha(ISLAND_OPACITY)
        self._fill = color
        self._border = QColor(255, 255, 255, 34)
        self.radius = float(ISLAND_RADIUS)

    def set_radius(self, radius: float) -> None:
        if abs(self.radius - radius) < 0.01:
            return
        self.radius = radius
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        painter.fillPath(path, self._fill)
        painter.setPen(QPen(self._border, 1))
        painter.drawPath(path)
        painter.end()


class IslandWindow(QWidget):
    """Pastilla flotante que se expande para mostrar avisos."""

    open_excel_requested = Signal()
    config_requested = Signal()
    pause_toggled = Signal()
    hide_requested = Signal()
    alert_dismissed = Signal(str)      # identity de la tarea
    alert_snoozed = Signal(str, int)   # identity, minutos

    def __init__(self, config: ConfigManager) -> None:
        super().__init__(None)
        self.config = config

        self._tasks: List[Task] = []
        self._expanded = False
        self._paused = False
        self._alert: Optional[Task] = None
        self._alert_message: str = ""
        self._status: Optional[str] = None
        self._expanded_height: Optional[int] = None
        self._fade_token = 0

        self._anchor: Optional[Tuple[int, int]] = None  # (centro_x, arriba_y)
        self._drag_offset: Optional[QPoint] = None
        self._drag_moved = False

        self._setup_window()
        self._build_ui()
        self._setup_animations()

        self._retract_timer = QTimer(self)
        self._retract_timer.setSingleShot(True)
        self._retract_timer.timeout.connect(self.collapse)

        self._clock = QTimer(self)
        self._clock.setInterval(15000)
        self._clock.timeout.connect(self._refresh_labels)
        self._clock.start()

        self._apply_geometry(expanded=False, animated=False)
        self.set_paused(bool(self.config.get("paused", False)))
        self._refresh_labels()

    # ------------------------------------------------------------------ setup
    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle("Isla de Avisos")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.container = _Surface()
        self.container.setStyleSheet(ISLAND_STYLE + TASK_ROW_STYLE)
        root.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        # Cabecera (siempre visible, es la "pastilla")
        header = QHBoxLayout()
        header.setSpacing(8)
        header.setContentsMargins(0, 0, 0, 0)

        self.dot = QLabel("●")
        self.dot.setObjectName("dot")

        self.primary = QLabel("Isla de Avisos")
        self.primary.setObjectName("primary")

        self.secondary = QLabel("")
        self.secondary.setObjectName("secondary")

        self.badge = QLabel("0")
        self.badge.setObjectName("badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedHeight(20)

        self.hide_button = QPushButton("—")
        self.hide_button.setObjectName("iconButton")
        self.hide_button.setFixedSize(22, 22)
        self.hide_button.setCursor(Qt.PointingHandCursor)
        self.hide_button.setToolTip("Quitar de la pantalla")
        self.hide_button.clicked.connect(self.hide_requested.emit)

        self.close_button = QPushButton("✕")
        self.close_button.setObjectName("iconButton")
        self.close_button.setFixedSize(22, 22)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.setToolTip("Plegar")
        self.close_button.clicked.connect(self.collapse)
        self.close_button.hide()

        for widget in (self.dot, self.primary, self.secondary, self.badge):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        header.addWidget(self.dot, 0, Qt.AlignVCenter)
        header.addWidget(self.primary, 0, Qt.AlignVCenter)
        header.addWidget(self.secondary, 0, Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(self.badge, 0, Qt.AlignVCenter)
        header.addWidget(self.hide_button, 0, Qt.AlignVCenter)
        header.addWidget(self.close_button, 0, Qt.AlignVCenter)
        layout.addLayout(header)
        # La cabecera queda SIEMPRE arriba, aunque el cuerpo este oculto.
        layout.setAlignment(header, Qt.AlignTop)

        # Cuerpo (solo visible al expandir)
        self.body = QWidget()
        self.body.setObjectName("body")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 4, 0, 0)
        body_layout.setSpacing(8)

        # Banner del aviso: muestra el contenido real y los botones de accion.
        self.banner = self._build_banner()
        body_layout.addWidget(self.banner)

        section = QLabel("PRÓXIMAS TAREAS")
        section.setObjectName("sectionTitle")
        section.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        body_layout.addWidget(section)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.viewport().installEventFilter(self)

        self.list_host = QWidget()
        self.list_host.setObjectName("listHost")
        self.list_host.setAutoFillBackground(False)
        self.list_host.installEventFilter(self)
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_host)
        body_layout.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        footer.setContentsMargins(0, 0, 0, 0)
        self.excel_button = QPushButton("Abrir Excel")
        self.excel_button.setCursor(Qt.PointingHandCursor)
        self.excel_button.clicked.connect(self.open_excel_requested.emit)
        self.config_button = QPushButton("Configurar")
        self.config_button.setCursor(Qt.PointingHandCursor)
        self.config_button.clicked.connect(self.config_requested.emit)
        self.pause_button = QPushButton("Pausar")
        self.pause_button.setCursor(Qt.PointingHandCursor)
        self.pause_button.clicked.connect(self.pause_toggled.emit)
        footer.addWidget(self.excel_button)
        footer.addWidget(self.config_button)
        footer.addStretch(1)
        footer.addWidget(self.pause_button)
        body_layout.addLayout(footer)

        self.body.hide()
        self.body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout.addWidget(self.body, 1)

    def _build_banner(self) -> QFrame:
        """Tarjeta con el texto del aviso y los botones Entendido / Posponer."""
        banner = QFrame()
        # Se asigna ya para que eventFilter nunca lo busque inexistente.
        self.banner = banner
        banner.setObjectName("alertBanner")

        layout = QVBoxLayout(banner)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.banner_label = QLabel("")
        self.banner_label.setObjectName("alertText")
        self.banner_label.setWordWrap(True)
        self.banner_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.banner_label)

        self.banner_reason = QLabel("")
        self.banner_reason.setObjectName("alertReason")
        self.banner_reason.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.banner_reason)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.setContentsMargins(0, 0, 0, 0)

        self.dismiss_button = QPushButton("Entendido")
        self.dismiss_button.setObjectName("primaryButton")
        self.dismiss_button.setCursor(Qt.PointingHandCursor)
        self.dismiss_button.setToolTip("Descartar este aviso hasta el próximo umbral")
        self.dismiss_button.clicked.connect(self._dismiss_alert)

        self.snooze_button = QPushButton("Posponer 1 h")
        self.snooze_button.setCursor(Qt.PointingHandCursor)
        self.snooze_button.setToolTip("Volver a avisar más tarde")
        self.snooze_button.clicked.connect(self._snooze_alert)

        buttons.addWidget(self.dismiss_button)
        buttons.addWidget(self.snooze_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        banner.installEventFilter(self)
        banner.hide()
        return banner

    def _setup_animations(self) -> None:
        # Geometria: al abrir, un muelle con rebote minimo (estilo Apple);
        # al plegar, una salida corta y sin rebote.
        self._expand_curve = QEasingCurve(QEasingCurve.OutBack)
        self._expand_curve.setOvershoot(1.05)
        self._collapse_curve = QEasingCurve(QEasingCurve.InOutCubic)

        self._geom_anim = QPropertyAnimation(self, b"geometry", self)
        self._geom_anim.setDuration(_EXPAND_MS)
        self._geom_anim.setEasingCurve(self._expand_curve)
        self._geom_anim.finished.connect(self._on_geometry_finished)

        # El radio de las esquinas acompana al tamano (23 -> 40).
        self._radius_anim = QVariantAnimation(self)
        self._radius_anim.valueChanged.connect(self._on_radius_tick)

        # El contenido entra con un fundido suave, no de golpe.
        self._fade = QGraphicsOpacityEffect(self.body)
        self._fade.setOpacity(0.0)
        self.body.setGraphicsEffect(self._fade)
        self._fade_anim = QPropertyAnimation(self._fade, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _on_radius_tick(self, value) -> None:
        self.container.set_radius(float(value))

    def _collapsed_radius(self) -> float:
        return self._collapsed_size()[1] / 2.0

    def _expanded_radius(self) -> float:
        return float(ISLAND_RADIUS_EXPANDED)

    def _fade_to(self, token: int, target: float, duration: int) -> None:
        """Arranca el fundido, salvo que otro mas reciente lo haya invalidado."""
        if token != self._fade_token:
            return
        self._fade_anim.stop()
        self._fade_anim.setDuration(duration)
        self._fade_anim.setStartValue(self._fade.opacity())
        self._fade_anim.setEndValue(target)
        self._fade_anim.start()

    # ------------------------------------------------------------------ geometry
    def _collapsed_size(self) -> Tuple[int, int]:
        return (int(self.config.get("island.collapsed_width", 240)),
                int(self.config.get("island.collapsed_height", 46)))

    def _expanded_size(self) -> Tuple[int, int]:
        width = int(self.config.get("island.expanded_width", 380))
        height = self._expanded_height or int(self.config.get("island.expanded_height", 440))
        return (width, int(height))

    def _banner_height(self, width: int) -> int:
        """Alto que necesita el banner del aviso, medido con la fuente real."""
        if not self._alert_message:
            return 0
        inner = max(140, width - 56)
        metrics = QFontMetrics(self.banner_label.font())
        bounds = metrics.boundingRect(
            QRect(0, 0, inner, 0), int(Qt.TextFlag.TextWordWrap), self._alert_message
        )
        # margenes (10+10) + espaciado (6) + motivo (~16) + botones (~30)
        return int(bounds.height()) + 10 + 10 + 6 + 16 + 32

    def _compute_expanded_height(self) -> int:
        """Altura justa para el contenido (evita cajas grandes y vacias)."""
        self.list_host.adjustSize()
        list_height = self.list_host.sizeHint().height()
        width = int(self.config.get("island.expanded_width", 380))
        extra = 152 + self._banner_height(width)
        max_height = int(self.config.get("island.expanded_height", 440) or 440)
        minimum = 220 if not self._alert_message else 260
        return int(min(max_height, max(minimum, extra + list_height)))

    def _screen_rect(self) -> QRect:
        screens = QApplication.screens()
        index = int(self.config.get("screen_index", 0) or 0)
        screen = screens[index] if 0 <= index < len(screens) else QApplication.primaryScreen()
        return screen.availableGeometry()

    def _target_geometry(self, expanded: bool) -> QRect:
        rect = self._screen_rect()
        width, height = self._expanded_size() if expanded else self._collapsed_size()

        if self._anchor is not None:
            center_x, top_y = self._anchor
        else:
            center_x = rect.x() + rect.width() // 2
            top_y = rect.y() + int(self.config.get("offset_y", 10))

        return QRect(int(center_x - width / 2), top_y, width, height)

    def _apply_geometry(self, expanded: bool, animated: bool) -> None:
        target = self._target_geometry(expanded)
        radius_target = self._expanded_radius() if expanded else self._collapsed_radius()

        self._geom_anim.stop()
        self._radius_anim.stop()
        self._fade_anim.stop()
        self._fade_token += 1
        token = self._fade_token

        if not animated:
            self.setGeometry(target)
            self.container.set_radius(radius_target)
            self.body.setVisible(expanded)
            self.close_button.setVisible(expanded)
            self._fade.setOpacity(1.0 if expanded else 0.0)
            return

        duration = _EXPAND_MS if expanded else _COLLAPSE_MS
        curve = self._expand_curve if expanded else self._collapse_curve

        if expanded:
            self.body.setVisible(True)
            self.close_button.setVisible(True)
            self._fade.setOpacity(0.0)
            QTimer.singleShot(
                _FADE_IN_DELAY_MS,
                lambda: self._fade_to(token, 1.0, _FADE_IN_MS),
            )
        else:
            self._fade.setOpacity(0.0)

        self._geom_anim.setDuration(duration)
        self._geom_anim.setEasingCurve(curve)
        self._geom_anim.setStartValue(self.geometry())
        self._geom_anim.setEndValue(target)
        self._geom_anim.start()

        self._radius_anim.setDuration(duration)
        self._radius_anim.setEasingCurve(curve)
        self._radius_anim.setStartValue(float(self.container.radius))
        self._radius_anim.setEndValue(float(radius_target))
        self._radius_anim.start()

    def recenter(self) -> None:
        self._anchor = None
        self._apply_geometry(self._expanded, animated=False)

    def _on_geometry_finished(self) -> None:
        # La visibilidad del cuerpo SIEMPRE debe coincidir con el estado.
        self.body.setVisible(self._expanded)
        self.close_button.setVisible(self._expanded)
        self._fade.setOpacity(1.0 if self._expanded else 0.0)

    # ------------------------------------------------------------------ estado
    def set_tasks(self, tasks: List[Task]) -> None:
        self._tasks = list(tasks)
        if self._alert is not None and all(t.identity != self._alert.identity for t in self._tasks):
            self._clear_alert()
        if self._expanded:
            self._rebuild_list()
            self._expanded_height = self._compute_expanded_height()
        self._refresh_labels()

    def set_status(self, message: str) -> None:
        self._status = message
        self._refresh_labels()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.pause_button.setText("Reanudar" if paused else "Pausar")
        self._refresh_labels()

    def show_reminder(self, task: Task, message: str) -> None:
        """Muestra el aviso con su contenido real y expande la isla."""
        self._status = None
        self._alert = task
        self._alert_message = message or task.title
        self.banner_label.setText(self._alert_message)
        self.banner_reason.setText(task.countdown_text())
        self.snooze_button.setText(f"Posponer {self._snooze_label()}")
        self.banner.show()
        self._refresh_labels()
        if not self.isVisible():
            # Primero se muestra la pastilla y en el siguiente frame se expande,
            # para que se vea crecer (si no, aparece ya desplegada de golpe).
            self.show()
            self.raise_()
            QTimer.singleShot(16, self.expand)
        else:
            self.expand()
            self.raise_()

    def _snooze_label(self) -> str:
        try:
            minutes = int(self.config.get("snooze_minutes", 60) or 60)
        except (TypeError, ValueError):
            minutes = 60
        if minutes % 60 == 0 and minutes >= 60:
            hours = minutes // 60
            return "1 h" if hours == 1 else f"{hours} h"
        return f"{minutes} min"

    def _clear_alert(self) -> None:
        self._alert = None
        self._alert_message = ""
        self.banner_label.setText("")
        self.banner_reason.setText("")
        self.banner.hide()

    # ------------------------------------------------------------------ acciones
    def _dismiss_alert(self) -> None:
        if self._alert is None:
            return
        identity = self._alert.identity
        self._clear_alert()
        self.collapse()
        self.alert_dismissed.emit(identity)

    def _snooze_alert(self) -> None:
        if self._alert is None:
            return
        identity = self._alert.identity
        try:
            minutes = int(self.config.get("snooze_minutes", 60) or 60)
        except (TypeError, ValueError):
            minutes = 60
        self._clear_alert()
        self.collapse()
        self.alert_snoozed.emit(identity, minutes)

    def toggle(self) -> None:
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self) -> None:
        self._expanded = True
        self._rebuild_list()
        self._expanded_height = self._compute_expanded_height()
        self.banner.setVisible(bool(self._alert_message))
        self._refresh_labels()
        self._apply_geometry(True, animated=True)
        self._retract_timer.start(self._seconds())

    def collapse(self) -> None:
        if not self._expanded:
            return
        self._expanded = False
        self._retract_timer.stop()
        # El cuerpo se oculta de inmediato: si siguiera visible, su tamano
        # minimo impediria que la ventana encogiera hasta la pastilla.
        self.body.hide()
        self.close_button.hide()
        self._refresh_labels()
        self._apply_geometry(False, animated=True)

    def _seconds(self) -> int:
        return max(3, int(self.config.get("expand_seconds", 8) or 8)) * 1000

    def _hover_seconds(self) -> int:
        raw = self.config.get("collapse_after_hover_seconds", 15)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 15
        return max(1, value) * 1000

    # ------------------------------------------------------------------ pintado
    def _elide(self, text: str, limit: int = 34) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "..."

    def _pending(self) -> List[Task]:
        return [t for t in self._tasks if not t.done]

    def _refresh_labels(self) -> None:
        pending = self._pending()

        if self._paused:
            self.dot.setStyleSheet("color: #8e8e93;")
            self.primary.setText("Avisos en pausa")
            self.secondary.setText("")
            self.badge.setText(str(len(pending)))
            self.badge.setVisible(bool(pending))
            return

        if self._status:
            self.dot.setStyleSheet("color: #ff453a;")
            self.primary.setText(self._elide(self._status, 40))
            self.secondary.setText("")
            self.badge.setVisible(False)
            return

        task = self._alert or (pending[0] if pending else None)
        if task is None:
            self.dot.setStyleSheet("color: #30d158;")
            self.primary.setText("Sin tareas próximas")
            self.secondary.setText("")
            self.badge.setVisible(False)
            return

        self.dot.setStyleSheet(f"color: {task.urgency_color};")
        if self._alert_message and not self._expanded:
            # Plegada: aun asi se ve el contenido del aviso.
            self.primary.setText(self._elide(self._alert_message, 26))
        else:
            limit = 34 if self._expanded else 20
            self.primary.setText(self._elide(task.title, limit))
        self.secondary.setText(task.countdown_text() if self._expanded else task.short_countdown())
        self.badge.setText(str(len(pending)))
        self.badge.setVisible(len(pending) > 1)

    def _rebuild_list(self) -> None:
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        pending = self._pending()
        if not pending:
            empty = QLabel("No hay tareas pendientes.")
            empty.setObjectName("taskMeta")
            empty.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.list_layout.insertWidget(0, empty)
            return

        for index, task in enumerate(pending[:12]):
            self.list_layout.insertWidget(index, self._build_task_row(task))

    def _build_task_row(self, task: Task) -> QWidget:
        row = QFrame()
        row.setObjectName("taskRow")
        row.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        marker = QLabel("●")
        marker.setStyleSheet(f"color: {task.priority.color}; font-size: 12px; background: transparent;")
        layout.addWidget(marker, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(2)

        title = QLabel(self._elide(task.title, 46))
        title.setObjectName("taskTitle")
        title.setWordWrap(True)
        info.addWidget(title)

        meta_parts = [task.display_date()]
        if task.display_time():
            meta_parts.append(task.display_time())
        meta_parts.append(task.countdown_text())
        meta_parts.append(task.priority.label)
        meta = QLabel("  ·  ".join(meta_parts))
        meta.setObjectName("taskMeta")
        info.addWidget(meta)

        if task.detail or task.action != "vence":
            # En los avisos de notificacion se indica el verbo delante del area.
            texto = task.detail
            if task.action and task.action != "vence":
                etiqueta = task.action_label
                etiqueta = etiqueta[:1].upper() + etiqueta[1:]
                texto = f"{etiqueta} · {texto}" if texto else etiqueta
            detail = QLabel(self._elide(texto, 60))
            detail.setObjectName("taskDetail")
            detail.setWordWrap(True)
            info.addWidget(detail)

        if task.notes:
            notes = QLabel(self._elide(task.notes, 60))
            notes.setObjectName("taskNotes")
            notes.setWordWrap(True)
            info.addWidget(notes)

        layout.addLayout(info, 1)
        return row

    # ------------------------------------------------------------------ eventos
    def _handle_click(self) -> None:
        """Clic simple: pliega si esta abierta, expande si esta compacta."""
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (API Qt)
        # Los clics sobre el banner del aviso no pliegan la isla.
        banner = getattr(self, "banner", None)
        if banner is not None and obj is banner and event.type() == QEvent.MouseButtonRelease:
            return True
        # La zona de la lista tambien debe plegar la isla al hacer clic.
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._handle_click()
            return True
        return super().eventFilter(obj, event)

    def enterEvent(self, event) -> None:  # noqa: N802 (API Qt)
        self._retract_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (API Qt)
        if self._expanded:
            self._retract_timer.start(self._hover_seconds())
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (API Qt)
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_moved = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (API Qt)
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            if (new_pos - self.pos()).manhattanLength() > 4:
                self._drag_moved = True
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (API Qt)
        if self._drag_offset is None:
            return
        if self._drag_moved:
            self._anchor = (self.x() + self.width() // 2, self.y())
            self.config.set("offset_y", self.y() - self._screen_rect().y())
            self.config.save()
        else:
            self._handle_click()
        self._drag_offset = None
        event.accept()
