"""
MountOS — Индикатор CPU/RAM для верхней панели.

Рисуется QPainter:
  • Мини-график CPU за последние 30 секунд
  • Процент загрузки в реальном времени
  • Мини-полоска RAM
  • Меняет цвет: зелёный <50%, оранжевый <80%, красный >80%
  • Клик → открывает диспетчер задач

Автообновление через system_monitor.

API:
    from ui.cpu_indicator import CpuIndicator
    ind = CpuIndicator(host)
"""

from collections import deque

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont

from ui.settings_state import state
from system.system_monitor import monitor


HISTORY_LEN = 30   # храним последние 30 точек (по 2 сек = 1 минута)


class CpuGraph(QWidget):
    """Мини-график CPU (полилиния)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 18)
        self._history = deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self._current = 0.0

    def push(self, value: float):
        self._current = max(0.0, min(100.0, value))
        self._history.append(self._current)
        self.update()

    def _color(self) -> QColor:
        if self._current >= 80:
            return QColor("#FF6B8A")
        if self._current >= 50:
            return QColor("#FFB86C")
        return QColor("#6EE7B7")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        color = self._color()

        # Фон
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 15)))
        p.drawRoundedRect(0, 0, w, h, 4, 4)

        # Линия графика
        if len(self._history) > 1:
            pen = QPen(color)
            pen.setWidthF(1.6)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)

            path = QPainterPath()
            n = len(self._history)
            step = w / max(1, n - 1)
            for i, val in enumerate(self._history):
                x = i * step
                y = h - (val / 100.0) * (h - 2) - 1
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.drawPath(path)

        # Точка текущего значения справа
        p.setBrush(QBrush(color))
        p.setPen(Qt.NoPen)
        y_now = h - (self._current / 100.0) * (h - 2) - 1
        p.drawEllipse(QPointF(w - 3, y_now), 2.5, 2.5)


class RamBar(QWidget):
    """Мини-полоска заполнения RAM."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 6)
        self._percent = 0.0

    def set_percent(self, value: float):
        self._percent = max(0.0, min(100.0, value))
        self.update()

    def _color(self) -> QColor:
        if self._percent >= 85:
            return QColor("#FF6B8A")
        if self._percent >= 60:
            return QColor("#FFB86C")
        return QColor("#6EC6FF")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Фон
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 20)))
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)

        # Заполнение
        fill_w = int(w * self._percent / 100.0)
        if fill_w > 0:
            p.setBrush(QBrush(self._color()))
            p.drawRoundedRect(0, 0, fill_w, h, h / 2, h / 2)


class CpuIndicator(QWidget):
    """
    Полный индикатор: график CPU + полоска RAM + проценты.
    Клик → открывает диспетчер задач MountOS.
    """

    def __init__(self, host=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Открыть диспетчер задач")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(6)

        # График CPU
        self.graph = CpuGraph()
        lay.addWidget(self.graph)

        # Проценты
        info_col = QWidget()
        info_col.setFixedWidth(80)
        il = QHBoxLayout(info_col)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(4)

        self.cpu_lbl = QLabel("0%")
        self.cpu_lbl.setStyleSheet("""
            color: rgba(255,255,255,0.85);
            font-size: 11px;
            font-weight: 500;
            min-width: 28px;
        """)
        il.addWidget(self.cpu_lbl)

        self.ram_lbl = QLabel("0%")
        self.ram_lbl.setStyleSheet("""
            color: rgba(110,198,255,0.85);
            font-size: 11px;
            font-weight: 500;
            min-width: 28px;
        """)
        il.addWidget(self.ram_lbl)

        lay.addWidget(info_col)

        # Полоска RAM
        self.ram_bar = RamBar()
        lay.addWidget(self.ram_bar)

        # Обновление
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

        self._refresh()

        # Подписка на монитор — обновление сразу
        try:
            monitor().updated.connect(self._on_monitor_update)
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Обновление
    # ------------------------------------------------------------

    def _apply(self, cpu: float, ram_percent: float):
        self.graph.push(cpu)
        self.cpu_lbl.setText(f"{int(cpu)}%")
        self.ram_lbl.setText(f"{int(ram_percent)}%")
        self.ram_bar.set_percent(ram_percent)

        # Цвет CPU-текста
        if cpu >= 80:
            c = "#FF6B8A"
        elif cpu >= 50:
            c = "#FFB86C"
        else:
            c = "rgba(255,255,255,0.85)"
        self.cpu_lbl.setStyleSheet(f"""
            color: {c};
            font-size: 11px;
            font-weight: 500;
            min-width: 28px;
        """)

    def _refresh(self):
        try:
            cpu = monitor().cpu_percent()
            mem = monitor().memory()
            self._apply(cpu, mem.get("percent", 0.0))
        except Exception:
            pass

    def _on_monitor_update(self, data):
        cpu = data.get("cpu", 0.0)
        mem = data.get("memory", {})
        self._apply(cpu, mem.get("percent", 0.0))

    # ------------------------------------------------------------
    #  Клик → диспетчер задач
    # ------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._open_taskmgr()

    def _open_taskmgr(self):
        # Пытаемся через host.open_app
        try:
            if self.host and hasattr(self.host, "open_app"):
                self.host.open_app("taskmgr")
                return
        except Exception:
            pass

        # Через Desktop
        from PySide6.QtWidgets import QApplication
        for top in QApplication.topLevelWidgets():
            if hasattr(top, "open_app"):
                top.open_app("taskmgr")
                return
            ref = getattr(top, "desktop_ref", None)
            if ref is not None and hasattr(ref, "open_app"):
                ref.open_app("taskmgr")
                return