"""
MountOS — Индикатор батареи для верхней панели.

Рисуется QPainter:
  • Иконка батареи (динамическая заливка)
  • Процент рядом
  • Индикатор зарядки (молния ⚡)
  • Меняет цвет: красный < 15%, жёлтый < 30%, белый > 30%
  • Если батареи нет — скрывается

Автообновление каждые 3 сек через system_monitor.

API:
    from ui.battery_indicator import BatteryIndicator
    ind = BatteryIndicator()
    ind.set_time(...)  # нет, только состояние
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont

from ui.settings_state import state
from system.system_monitor import monitor


class BatteryIcon(QWidget):
    """Иконка батареи, рисуется QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 16)
        self._percent = 100
        self._charging = False

    def set_state(self, percent: int, charging: bool):
        self._percent = max(0, min(100, percent))
        self._charging = charging
        self.update()

    def _color_for_percent(self) -> QColor:
        """Цвет заливки в зависимости от уровня."""
        if self._charging:
            return QColor("#6EE7B7")   # зелёный при зарядке
        if self._percent <= 15:
            return QColor("#FF6B8A")   # красный
        if self._percent <= 30:
            return QColor("#FFB86C")   # оранжевый
        return QColor("#FFFFFF")       # белый

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Корпус батареи (внешний контур)
        body_w = w - 5      # оставляем место для "пипки"
        body_h = h
        pen = QPen(QColor(255, 255, 255, 160))
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        body_rect = QRectF(1, 1, body_w - 2, body_h - 2)
        p.drawRoundedRect(body_rect, 3, 3)

        # "Пипка" справа
        p.setBrush(QBrush(QColor(255, 255, 255, 160)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(body_w, h * 0.3, 3, h * 0.4), 1, 1)

        # Заливка (уровень)
        fill_color = self._color_for_percent()
        fill_w = (body_w - 4) * (self._percent / 100.0)
        if fill_w > 0:
            p.setBrush(QBrush(fill_color))
            fill_rect = QRectF(2, 2, fill_w, body_h - 4)
            p.drawRoundedRect(fill_rect, 2, 2)

        # Молния при зарядке
        if self._charging:
            p.setBrush(QBrush(QColor(0, 0, 0, 200)))
            p.setPen(Qt.NoPen)
            cx = body_w / 2
            cy = h / 2
            lightning = QPainterPath()
            lightning.moveTo(QPointF(cx + 1, cy - 4))
            lightning.lineTo(QPointF(cx - 2, cy + 1))
            lightning.lineTo(QPointF(cx, cy + 1))
            lightning.lineTo(QPointF(cx - 1, cy + 4))
            lightning.lineTo(QPointF(cx + 2, cy - 1))
            lightning.lineTo(QPointF(cx, cy - 1))
            lightning.closeSubpath()
            p.drawPath(lightning)


class BatteryIndicator(QWidget):
    """
    Виджет для верхней панели: иконка + процент.
    Автообновляется через system_monitor.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(4)

        self.icon = BatteryIcon()
        lay.addWidget(self.icon)

        self.percent_lbl = QLabel("100%")
        self.percent_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.85);
            font-size: 12px;
            font-weight: 500;
        """)
        lay.addWidget(self.percent_lbl)

        self._visible = True

        # Обновление
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        # Первое обновление
        self._refresh()

        # Если монитор обновляется — подпишемся
        try:
            monitor().updated.connect(self._on_monitor_update)
        except Exception:
            pass

    def _refresh(self):
        """Читает состояние батареи."""
        try:
            bat = monitor().battery()
        except Exception:
            bat = {"present": False, "percent": -1, "charging": False}

        if not bat.get("present"):
            # Нет батареи — скрываем
            self.hide()
            return

        self.show()
        pct = bat.get("percent", 0)
        charging = bat.get("charging", False)

        self.icon.set_state(pct, charging)
        self.percent_lbl.setText(f"{pct}%")

        # Цвет текста в тон иконке
        if charging:
            color = "#6EE7B7"
        elif pct <= 15:
            color = "#FF6B8A"
        elif pct <= 30:
            color = "#FFB86C"
        else:
            color = "rgba(255,255,255,0.85)"

        self.percent_lbl.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
            font-weight: 500;
        """)

    def _on_monitor_update(self, data):
        """Вызывается при обновлении system_monitor — быстро обновляем."""
        bat = data.get("battery", {})
        if not bat.get("present"):
            self.hide()
            return
        self.show()
        pct = bat.get("percent", 0)
        charging = bat.get("charging", False)
        self.icon.set_state(pct, charging)
        self.percent_lbl.setText(f"{pct}%")

        if charging:
            color = "#6EE7B7"
        elif pct <= 15:
            color = "#FF6B8A"
        elif pct <= 30:
            color = "#FFB86C"
        else:
            color = "rgba(255,255,255,0.85)"

        self.percent_lbl.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
            font-weight: 500;
        """)