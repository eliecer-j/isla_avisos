"""Icono de la bandeja y estilos de la isla.

El fondo de la isla NO se define aqui: se pinta con QPainter en
`island_window._Surface` para no depender del estilo nativo de Windows.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap

# Radio y color del fondo de la isla (compartido con el paintEvent).
# La isla se pinta opaca, como la Dynamic Island real (negro OLED): nada de
# transparencia, si no se ve el escritorio a traves y deja de parecer macOS.
ISLAND_RADIUS = 24                      # radio de partida (se anima)
ISLAND_RADIUS_EXPANDED = 40             # radio al desplegar
ISLAND_COLOR = "#000000"
ISLAND_OPACITY = 255

# Valores del sistema iOS (modo oscuro) que usa la Dynamic Island.
_LABEL = "#ffffff"                      # label
_LABEL_2 = "rgba(235, 235, 245, 153)"   # secondaryLabel (60 %)
_LABEL_3 = "rgba(235, 235, 245, 102)"   # tertiaryLabel (40 %)
_LABEL_4 = "rgba(235, 235, 245, 77)"    # quaternaryLabel (30 %)
_FILL_1 = "rgba(120, 120, 128, 82)"     # fill secundario (32 %)
_FILL_2 = "rgba(120, 120, 128, 61)"     # fill cuaternario (24 %)
_SYSTEM_RED = "#FF453A"                 # systemRed
_CARD = "#1C1C1E"                       # secondarySystemBackground

ISLAND_STYLE = """
QLabel {
    background: transparent;
}
#primary {
    color: %(label)s;
    font-size: 13px;
    font-weight: 600;
}
#secondary {
    color: %(label_2)s;
    font-size: 12px;
}
#dot {
    font-size: 13px;
}
#badge {
    background-color: %(red)s;
    color: %(label)s;
    font-size: 11px;
    font-weight: 700;
    border-radius: 9px;
    padding: 0px 7px;
}
#iconButton {
    background-color: %(fill_1)s;
    color: %(label)s;
    border: none;
    border-radius: 11px;
    font-size: 15px;
    font-weight: 700;
    padding: 0px;
}
#iconButton:hover {
    background-color: %(red)s;
}
#sectionTitle {
    color: %(label_4)s;
    font-size: 11px;
    font-weight: 700;
}
#body, #listHost {
    background: transparent;
}
QScrollArea, QScrollArea > #qt_scrollarea_viewport, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QPushButton {
    background-color: %(fill_2)s;
    color: %(label)s;
    border: none;
    border-radius: 12px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: rgba(120, 120, 128, 92);
}
QPushButton:pressed {
    background-color: rgba(120, 120, 128, 120);
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: %(label_4)s;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
""" % {
    "label": _LABEL,
    "label_2": _LABEL_2,
    "label_3": _LABEL_3,
    "label_4": _LABEL_4,
    "fill_1": _FILL_1,
    "fill_2": _FILL_2,
    "red": _SYSTEM_RED,
}

TASK_ROW_STYLE = """
#taskRow {
    background-color: %(card)s;
    border-radius: 14px;
}
#taskTitle {
    color: %(label)s;
    font-size: 13px;
    font-weight: 600;
}
#taskMeta {
    color: %(label_2)s;
    font-size: 11px;
}
#taskDetail {
    color: %(label_2)s;
    font-size: 11px;
    font-weight: 600;
}
#taskNotes {
    color: %(label_3)s;
    font-size: 11px;
    font-style: italic;
}
#alertBanner {
    background-color: rgba(255, 69, 58, 31);
    border: 1px solid rgba(255, 69, 58, 77);
    border-radius: 14px;
}
#alertText {
    color: %(label)s;
    font-size: 13px;
    font-weight: 700;
}
#alertReason {
    color: %(label_2)s;
    font-size: 11px;
}
#primaryButton {
    background-color: %(red)s;
    color: %(label)s;
    font-weight: 700;
}
#primaryButton:hover {
    background-color: #FF6155;
}
#primaryButton:pressed {
    background-color: #E03B31;
}
""" % {
    "card": _CARD,
    "label": _LABEL,
    "label_2": _LABEL_2,
    "label_3": _LABEL_3,
    "red": _SYSTEM_RED,
}


def build_icon(size: int = 64) -> QIcon:
    """Dibuja una pequena 'isla' negra con un punto de estado."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    painter.setBrush(QBrush(QColor(0, 0, 0)))
    painter.setPen(Qt.NoPen)
    rect = QRectF(size * 0.12, size * 0.30, size * 0.76, size * 0.40)
    painter.drawRoundedRect(rect, size * 0.20, size * 0.20)

    painter.setBrush(QBrush(QColor(48, 209, 88)))
    dot = QRectF(size * 0.24, size * 0.44, size * 0.12, size * 0.12)
    painter.drawEllipse(dot)

    painter.end()
    return QIcon(pixmap)
