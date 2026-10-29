"""Dialogo de configuracion (Excel, mapeo de columnas, mensaje y avisos)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Tuple

from PySide6.QtCore import QTime, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout,
                               QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QTimeEdit, QVBoxLayout, QWidget)

from app import autostart
from app.config import DEFAULT_TEMPLATE, ConfigManager
from app.excel_source import ExcelSource
from app.models import Priority, Task, format_message, reason_text

_MAPPING_FIELDS = [
    ("title", "Columna de Tarea / Nombre *"),
    ("detail", "Columna de Detalle (tipo de contrato)"),
    ("date", "Columna de Fecha *"),
    ("notify_date", "Columna de Fecha de notificación (si falta, se calcula)"),
    ("time", "Columna de Hora"),
    ("notes", "Columna de Notas"),
    ("priority", "Columna de Prioridad"),
    ("status", "Columna de Estado"),
]

_NONE = "(ninguna)"

_HELP = (
    "Marcadores: {titulo} {detalle} {fecha} {hora} {dias} {prioridad} {notas} {accion}\n"
    "Ejemplo: {titulo} · {detalle} · {notas}: {accion} el {fecha} (en {dias} días)"
)


class ConfigDialog(QDialog):
    """Permite elegir el Excel, mapear columnas y ajustar los avisos."""

    def __init__(self, config: ConfigManager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.mapping_combos: Dict[str, QComboBox] = {}

        self.setWindowTitle("Configuración · Isla de Avisos")
        # Ventana normal: redimensionable y por encima de la isla flotante.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setMinimumSize(460, 340)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Todo el contenido va dentro de un area con scroll: si la pantalla es
        # pequena se puede encoger y desplazar en vez de salirse por abajo.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(self._build_file_group())
        content_layout.addWidget(self._build_mapping_group())
        content_layout.addWidget(self._build_message_group())
        content_layout.addWidget(self._build_reminders_group())
        content_layout.addWidget(self._build_repeat_group())
        content_layout.addWidget(self._build_options_group())
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.Ok)
        cancel_button = buttons.button(QDialogButtonBox.Cancel)
        if ok_button is not None:
            ok_button.setText("Guardar")
            ok_button.setDefault(True)
        if cancel_button is not None:
            cancel_button.setText("Cancelar")
        root.addWidget(buttons)

        self._reload_headers(suggest=not bool(config.get("column_map", {}).get("title")))
        self._update_preview()
        self._place_on_screen()

    # ------------------------------------------------------------------ ventana
    def _place_on_screen(self) -> None:
        """Centra y ajusta el tamano a la pantalla donde esta el raton."""
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        max_width = max(320, area.width() - 60)
        max_height = max(300, area.height() - 60)
        width = min(600, max_width)
        height = min(680, max_height)
        self.resize(width, height)
        self.move(
            area.x() + (area.width() - width) // 2,
            area.y() + (area.height() - height) // 2,
        )

    def showEvent(self, event) -> None:  # noqa: N802 (API Qt)
        super().showEvent(event)
        # Nunca debe quedar detras de la isla, que tambien esta "siempre encima".
        self.raise_()
        self.activateWindow()

    def raise_over_island(self) -> None:
        """Trae el dialogo al frente por si la isla lo ha tapado."""
        if not self.isVisible():
            return
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------ grupos
    def _build_file_group(self) -> QGroupBox:
        group = QGroupBox("Archivo Excel")
        form = QFormLayout(group)

        row = QHBoxLayout()
        self.path_edit = QLineEdit(str(self.config.get("excel_path", "")))
        browse = QPushButton("Buscar...")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        form.addRow("Ruta:", row)

        sheet_row = QHBoxLayout()
        self.sheet_combo = QComboBox()
        self.sheet_combo.setEditable(True)
        self.sheet_combo.setCurrentText(str(self.config.get("sheet_name", "")))
        detect = QPushButton("Detectar columnas")
        detect.clicked.connect(lambda: self._reload_headers(suggest=True))
        sheet_row.addWidget(self.sheet_combo, 1)
        sheet_row.addWidget(detect)
        form.addRow("Hoja:", sheet_row)

        self.header_row_spin = QSpinBox()
        self.header_row_spin.setMinimum(1)
        self.header_row_spin.setMaximum(50)
        self.header_row_spin.setValue(int(self.config.get("header_row", 1) or 1))
        form.addRow("Fila de encabezados:", self.header_row_spin)

        self.headers_label = QLabel("")
        self.headers_label.setWordWrap(True)
        self.headers_label.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow("", self.headers_label)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("Probar lectura")
        self.test_button.setToolTip("Lee el Excel y comprueba cuántas tareas detecta")
        self.test_button.clicked.connect(self._test_read)
        self.test_label = QLabel("")
        self.test_label.setWordWrap(True)
        self.test_label.setStyleSheet("color: #666; font-size: 11px;")
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_label, 1)
        form.addRow("", test_row)

        return group

    def _build_mapping_group(self) -> QGroupBox:
        group = QGroupBox("Mapeo de columnas")
        form = QFormLayout(group)
        for key, label in _MAPPING_FIELDS:
            combo = QComboBox()
            combo.addItem(_NONE, "")
            self.mapping_combos[key] = combo
            combo.currentIndexChanged.connect(self._update_preview)
            form.addRow(label, combo)
        return group

    def _build_message_group(self) -> QGroupBox:
        group = QGroupBox("Mensaje del aviso")
        form = QFormLayout(group)

        self.template_edit = QLineEdit(
            str(self.config.get("message_template", "") or DEFAULT_TEMPLATE)
        )
        self.template_edit.textChanged.connect(self._update_preview)
        form.addRow("Texto:", self.template_edit)

        help_label = QLabel(_HELP)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow("", help_label)

        self.preview_label = QLabel("")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(
            "background: #1b1b1d; color: #ffffff; border-radius: 10px; padding: 8px;"
        )
        form.addRow("Vista previa:", self.preview_label)

        reset = QPushButton("Restaurar texto por defecto")
        reset.clicked.connect(lambda: self.template_edit.setText(DEFAULT_TEMPLATE))
        form.addRow("", reset)

        return group

    def _build_reminders_group(self) -> QGroupBox:
        group = QGroupBox("Avisos")
        form = QFormLayout(group)

        days = self.config.get("reminders_days", [15, 7, 2]) or []
        self.days_edit = QLineEdit(", ".join(str(int(d)) for d in days))
        form.addRow("Días de anticipación:", self.days_edit)

        self.imminent_spin = QSpinBox()
        self.imminent_spin.setRange(0, 240)
        self.imminent_spin.setSuffix(" min")
        self.imminent_spin.setValue(int(self.config.get("imminent_minutes", 30) or 0))
        form.addRow("Aviso extra antes de vencer:", self.imminent_spin)

        self.notify_offset_spin = QSpinBox()
        self.notify_offset_spin.setRange(0, 365)
        self.notify_offset_spin.setSpecialValueText("Sin aviso de notificación")
        self.notify_offset_spin.setSuffix(" días antes de vencer")
        self.notify_offset_spin.setValue(int(self.config.get("notify_offset_days", 15) or 0))
        self.notify_offset_spin.setToolTip(
            "Si el Excel no trae la fecha de notificación (o la celda está vacía),\n"
            "se calcula sola como el vencimiento menos estos días."
        )
        self.notify_offset_spin.valueChanged.connect(self._update_preview)
        form.addRow("Notificar al empleado:", self.notify_offset_spin)

        self.expand_spin = QSpinBox()
        self.expand_spin.setRange(3, 120)
        self.expand_spin.setSuffix(" s")
        self.expand_spin.setValue(int(self.config.get("expand_seconds", 8) or 8))
        form.addRow("Tiempo abierta tras aviso:", self.expand_spin)

        self.hover_spin = QSpinBox()
        self.hover_spin.setRange(1, 300)
        self.hover_spin.setSuffix(" s")
        self.hover_spin.setValue(int(self.config.get("collapse_after_hover_seconds", 15) or 15))
        self.hover_spin.setToolTip(
            "Tiempo que la isla sigue abierta después de quitar el ratón\n"
            "de encima (mientras el ratón está dentro, no se cierra)."
        )
        form.addRow("Tiempo tras quitar el ratón:", self.hover_spin)

        self.snooze_spin = QSpinBox()
        self.snooze_spin.setRange(5, 480)
        self.snooze_spin.setSuffix(" min")
        self.snooze_spin.setValue(int(self.config.get("snooze_minutes", 60) or 60))
        form.addRow("Duración de «Posponer»:", self.snooze_spin)

        self.ignore_expired_check = QCheckBox("Ocultar lo que ya ha vencido")
        self.ignore_expired_check.setChecked(bool(self.config.get("ignore_expired", True)))
        self.ignore_expired_check.setToolTip(
            "No mostrar ni avisar de fechas que ya pasaron"
        )
        form.addRow(self.ignore_expired_check)

        return group

    def _build_repeat_group(self) -> QGroupBox:
        group = QGroupBox("Insistir hasta descartar")
        form = QFormLayout(group)

        self.repeat_check = QCheckBox("Volver a avisar si no se descarta")
        self.repeat_check.setChecked(bool(self.config.get("repeat.enabled", True)))
        self.repeat_check.toggled.connect(self._sync_repeat_enabled)
        form.addRow(self.repeat_check)

        self.per_day_spin = QSpinBox()
        self.per_day_spin.setRange(1, 24)
        self.per_day_spin.setSuffix(" / día")
        self.per_day_spin.setValue(int(self.config.get("repeat.per_day", 3) or 3))
        form.addRow("Avisos por día:", self.per_day_spin)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setSuffix(" min")
        self.interval_spin.setValue(int(self.config.get("repeat.interval_minutes", 240) or 240))
        form.addRow("Separación mínima:", self.interval_spin)

        window = QHBoxLayout()
        self.window_start = QTimeEdit()
        self.window_start.setDisplayFormat("HH:mm")
        self.window_start.setTime(self._read_time("repeat.window_start", QTime(8, 0)))
        self.window_end = QTimeEdit()
        self.window_end.setDisplayFormat("HH:mm")
        self.window_end.setTime(self._read_time("repeat.window_end", QTime(20, 0)))
        window.addWidget(self.window_start)
        window.addWidget(QLabel("hasta"))
        window.addWidget(self.window_end)
        window.addStretch(1)
        form.addRow("Franja horaria:", window)

        self._sync_repeat_enabled(self.repeat_check.isChecked())
        return group

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox("Opciones")
        form = QFormLayout(group)

        self.sound_check = QCheckBox("Reproducir sonido en los avisos")
        self.sound_check.setChecked(bool(self.config.get("sound_enabled", True)))
        form.addRow(self.sound_check)

        self.autostart_check = QCheckBox("Iniciar con Windows")
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.setEnabled(autostart.is_supported())
        form.addRow(self.autostart_check)

        return group

    # ------------------------------------------------------------------ helpers
    def _read_time(self, key: str, fallback: QTime) -> QTime:
        raw = str(self.config.get(key, "") or "")
        parsed = QTime.fromString(raw, "HH:mm")
        return parsed if parsed.isValid() else fallback

    def _sync_repeat_enabled(self, enabled: bool) -> None:
        for widget in (self.per_day_spin, self.interval_spin,
                       self.window_start, self.window_end):
            widget.setEnabled(enabled)

    def _sample_task(self) -> Task:
        return Task(
            title="ROMERO ALDANA SANTIAGO",
            due_date=date.today() + timedelta(days=30),
            detail="PRODUCCION",
            priority=Priority.MEDIUM,
            notes="5 MESES",
        )

    def _sample_notify_task(self) -> Task:
        return Task(
            title="ROMERO ALDANA SANTIAGO",
            due_date=date.today() + timedelta(days=15),
            detail="PRODUCCION",
            priority=Priority.MEDIUM,
            notes="5 MESES",
            action="notificar",
        )

    def _update_preview(self) -> None:
        template = self.template_edit.text()
        sample = self._sample_task()
        lines = [format_message(template, sample, reason_text(sample, "days", "30"))]
        # El segundo aviso existe si hay columna de notificacion o si la app lo
        # calcula sola (vencimiento menos N dias).
        columna = self.mapping_combos.get("notify_date")
        offset_spin = getattr(self, "notify_offset_spin", None)
        hay_notificacion = bool(columna and columna.currentData()) or bool(
            offset_spin is not None and offset_spin.value() > 0
        )
        if hay_notificacion:
            notify = self._sample_notify_task()
            lines.append(format_message(template, notify, reason_text(notify, "days", "15")))
        self.preview_label.setText("\n".join(lines))

    def _probe_config(self) -> ConfigManager:
        probe = ConfigManager()
        probe.set("excel_path", self.path_edit.text().strip())
        probe.set("sheet_name", self.sheet_combo.currentText().strip())
        probe.set("header_row", self.header_row_spin.value())
        probe.set("column_map", {
            key: (combo.currentData() or "")
            for key, combo in self.mapping_combos.items()
        })
        return probe

    # ------------------------------------------------------------------ acciones
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el Excel de tareas", "",
            "Excel (*.xlsx *.xlsm *.xls);;Todos los archivos (*)",
        )
        if path:
            self.path_edit.setText(path)
            self._reload_headers(suggest=True)

    def _reload_headers(self, suggest: bool = False) -> None:
        path = self.path_edit.text().strip()
        sheet = self.sheet_combo.currentText().strip()
        header_row = self.header_row_spin.value()

        probe = ConfigManager()
        probe.set("excel_path", path)
        probe.set("sheet_name", sheet)
        probe.set("header_row", header_row)
        source = ExcelSource(probe)

        # Rellena la lista de hojas disponibles.
        current = self.sheet_combo.currentText()
        names = source.sheet_names() if source.exists() else []
        if names:
            self.sheet_combo.blockSignals(True)
            self.sheet_combo.clear()
            self.sheet_combo.addItems(names)
            self.sheet_combo.setCurrentText(current or names[0])
            self.sheet_combo.blockSignals(False)

        try:
            headers: List[Tuple[int, str]] = source.read_headers()
        except Exception as exc:  # noqa: BLE001
            headers = []
            self.headers_label.setText(f"No se pudieron leer los encabezados: {exc}")
        else:
            if headers:
                self.headers_label.setText(
                    "Encabezados detectados: " + " | ".join(name for _, name in headers)
                )
            else:
                self.headers_label.setText("No se detectaron encabezados en esa fila.")

        names_only = [name for _, name in headers]
        for key, combo in self.mapping_combos.items():
            previous = combo.currentData() or str(self.config.get("column_map", {}).get(key, ""))
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_NONE, "")
            for name in names_only:
                combo.addItem(name, name)
            index = combo.findData(previous)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

        if suggest and headers:
            suggested = source.suggest_mapping()
            for key, value in suggested.items():
                combo = self.mapping_combos.get(key)
                if combo is None:
                    continue
                index = combo.findData(value)
                if index >= 0:
                    combo.setCurrentIndex(index)

    def _test_read(self) -> None:
        probe = self._probe_config()
        source = ExcelSource(probe)
        try:
            tasks = source.load()
        except Exception as exc:  # noqa: BLE001
            self.test_label.setText("")
            QMessageBox.warning(
                self, "No se pudo leer",
                f"No se han podido leer las tareas:\n\n{exc}",
            )
            return

        pending = [t for t in tasks if not t.done]
        self.test_label.setText(f"Detectadas {len(tasks)} filas ({len(pending)} pendientes).")
        if not tasks:
            QMessageBox.information(
                self, "Sin tareas",
                "Se ha leído el archivo, pero no se ha detectado ninguna tarea.\n"
                "Revisa el mapeo de columnas y la fila de encabezados.",
            )
            return

        preview = []
        for task in pending[:5] or tasks[:5]:
            preview.append("• " + format_message(
                self.template_edit.text(), task, task.countdown_text()
            ))
        QMessageBox.information(
            self, "Lectura correcta",
            f"Se han detectado {len(tasks)} tareas ({len(pending)} pendientes).\n\n"
            + "\n".join(preview),
        )

    def _parse_days(self) -> List[int]:
        raw = self.days_edit.text().replace(";", ",").replace(" ", ",")
        days: List[int] = []
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                value = int(chunk)
            except ValueError:
                continue
            if value > 0 and value not in days:
                days.append(value)
        return sorted(days, reverse=True)

    def _on_accept(self) -> None:
        mapping = {
            key: (combo.currentData() or "")
            for key, combo in self.mapping_combos.items()
        }

        self.config.set("excel_path", self.path_edit.text().strip())
        self.config.set("sheet_name", self.sheet_combo.currentText().strip())
        self.config.set("header_row", self.header_row_spin.value())
        self.config.set("column_map", mapping)
        self.config.set("message_template", self.template_edit.text().strip() or DEFAULT_TEMPLATE)
        self.config.set("reminders_days", self._parse_days())
        self.config.set("imminent_minutes", self.imminent_spin.value())
        self.config.set("notify_offset_days", self.notify_offset_spin.value())
        self.config.set("ignore_expired", self.ignore_expired_check.isChecked())
        self.config.set("expand_seconds", self.expand_spin.value())
        self.config.set("collapse_after_hover_seconds", self.hover_spin.value())
        self.config.set("snooze_minutes", self.snooze_spin.value())
        self.config.set("repeat.enabled", self.repeat_check.isChecked())
        self.config.set("repeat.per_day", self.per_day_spin.value())
        self.config.set("repeat.interval_minutes", self.interval_spin.value())
        self.config.set("repeat.window_start", self.window_start.time().toString("HH:mm"))
        self.config.set("repeat.window_end", self.window_end.time().toString("HH:mm"))
        self.config.set("sound_enabled", self.sound_check.isChecked())

        if autostart.is_supported():
            autostart.apply(self.autostart_check.isChecked())

        self.config.save()
        self.accept()
