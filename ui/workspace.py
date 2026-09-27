"""
MountOS — Индикатор рабочих столов для верхней панели.

Рисуется QPainter:
  • Точки-индикаторы (как в macOS Mission Control)
  • Активная точка — больше и акцентного цвета
  • Клик по точке → переключение на стол
  • Подсветка столов с открытыми окнами
  • Плавная анимация при переключении

API:
    from ui.workspace import WorkspaceIndicator
    ind = WorkspaceIndicator()
"""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

from ui.settings_state import state
from system.workspace import workspace


class WorkspaceIndicator(QWidget):
    """
    Точки-индикаторы рабочих столов в верхней панели.
    """

    DOT_SIZE = 8          # обычная точка
    DOT_ACTIVE = 11       # активная
    DOT_SPACING = 6       # расстояние между точками

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Виртуальные рабочие столы\nCtrl+1..4 — переключение")
        self.setFixedHeight(24)

        self._hover_index = -1
        self._pulse = 0.0
        self._pulse_index = -1

        # Анимация появления
        self._anim_value = 0.0
        self._fade_anim = None

        # Подписка
        try:
            ws = workspace()
            ws.switched.connect(self._on_switched)
            ws.windows_changed.connect(self._on_windows_changed)
        except Exception as e:
            print(f"[WorkspaceIndicator] subscribe: {e}")

        # Плавная пульсация при переключении
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(30)
        self._pulse_timer.timeout.connect(self._pulse_tick)

        self._update_size()

    # ------------------------------------------------------------
    #  Размер
    # ------------------------------------------------------------

    def _update_size(self):
        try:
            n = workspace().count()
        except Exception:
            n = 4
        total = n * self.DOT_ACTIVE + (n - 1) * self.DOT_SPACING + 20
        self.setFixedWidth(max(60, total))

    # ------------------------------------------------------------
    #  Реакция на события
    # ------------------------------------------------------------

    def _on_switched(self, index: int):
        self._pulse = 1.0
        self._pulse_index = index
        self._pulse_timer.start()
        self.update()

    def _on_windows_changed(self):
        self.update()

    def _pulse_tick(self):
        if self._pulse > 0:
            self._pulse = max(0.0, self._pulse - 0.08)
            self.update()
        else:
            self._pulse_timer.stop()
            self._pulse_index = -1

    # ------------------------------------------------------------
    #  Размер виджета
    # ------------------------------------------------------------

    def resizeEvent(self, e):
        self._update_size()
        super().resizeEvent(e)

    # ------------------------------------------------------------
    #  Позиции точек (для клика и отрисовки)
    # ------------------------------------------------------------

    def _dot_positions(self):
        """
        Возвращает список (x_center, y_center, size) для каждой точки.
        """
        try:
            n = workspace().count()
            cur = workspace().current()
        except Exception:
            n, cur = 4, 0

        positions = []
        total_width = n * self.DOT_ACTIVE + (n - 1) * self.DOT_SPACING
        start_x = (self.width() - total_width) / 2
        cy = self.height() / 2

        x = start_x
        for i in range(n):
            is_active = (i == cur)
            size = self.DOT_ACTIVE if is_active else self.DOT_SIZE
            cx = x + self.DOT_ACTIVE / 2
            positions.append((cx, cy, size, i))
            x += self.DOT_ACTIVE + self.DOT_SPACING

        return positions

    # ------------------------------------------------------------
    #  Отрисовка
    # ------------------------------------------------------------

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        accent = state().get("accent", "#6EC6FF")
        positions = self._dot_positions()

        try:
            ws = workspace()
            cur = ws.current()
        except Exception:
            cur = 0

        for cx, cy, size, idx in positions:
            is_active = (idx == cur)
            is_hover = (idx == self._hover_index)
            has_windows = False
            try:
                has_windows = workspace().window_count_of(idx) > 0
            except Exception:
                pass

            # Пульсация при переключении
            extra = 0
            if idx == self._pulse_index and self._pulse > 0:
                extra = int(self._pulse * 8)

            r = (size + extra) / 2

            # Цвет
            if is_active:
                color = QColor(accent)
                color.setAlpha(255)
            elif is_hover:
                color = QColor(accent)
                color.setAlpha(180)
            elif has_windows:
                color = QColor(255, 255, 255, 120)
            else:
                color = QColor(255, 255, 255, 60)

            # Тень/свечение для активной точки
            if is_active:
                glow = QColor(accent)
                glow.setAlpha(70)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(cx, cy), r + 4, r + 4)

            # Основная точка
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), r, r)

            # Тонкий контур для неактивных
            if not is_active:
                p.setPen(QPen(QColor(255, 255, 255, 40), 1))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r, r)

    # ------------------------------------------------------------
    #  Мышь
    # ------------------------------------------------------------

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        new_hover = -1
        for cx, cy, size, idx in self._dot_positions():
            r = (size + 10) / 2
            dx = pos.x() - cx
            dy = pos.y() - cy
            if dx * dx + dy * dy <= r * r:
                new_hover = idx
                break
        if new_hover != self._hover_index:
            self._hover_index = new_hover
            self.update()

    def leaveEvent(self, e):
        self._hover_index = -1
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        for cx, cy, size, idx in self._dot_positions():
            r = (size + 10) / 2
            dx = pos.x() - cx
            dy = pos.y() - cy
            if dx * dx + dy * dy <= r * r:
                try:
                    workspace().switch(idx)
                except Exception as err:
                    print(f"[WorkspaceIndicator] switch: {err}")
                return