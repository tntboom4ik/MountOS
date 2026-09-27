"""
MountOS — Базовый виджет рабочего стола.
Перетаскивается мышью внутри Desktop.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import (QPainter, QColor, QPainterPath, QBrush, QPen,
                            QLinearGradient)

from ui.context_menu import make_menu


class DesktopWidget(QWidget):
    """Базовая карточка-виджет на рабочем столе."""

    remove_requested = Signal(object)
    position_changed = Signal(object, int, int)

    def __init__(self, parent, widget_id: str, title: str,
                 width=220, height=140, locked=False):
        super().__init__(parent)
        self.widget_id = widget_id
        self.title = title
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.OpenHandCursor)

        self._drag_offset = QPoint()
        self._locked = locked

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(8)

        # Заголовок
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            color: rgba(255,255,255,0.70);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.4px;
        """)
        head.addWidget(self.title_label)
        head.addStretch(1)
        outer.addLayout(head)

        # Контейнер для содержимого
        self.body = QWidget(self)
        self.body.setStyleSheet("background: transparent;")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        outer.addWidget(self.body, 1)

        # Тень
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(35)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 130))
        self.setGraphicsEffect(shadow)

    # ------------------------------------------------------------
    #  Перетаскивание
    # ------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self._locked:
            self._drag_offset = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            self.raise_()
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and not self._locked:
            new_pos = self.mapToParent(e.pos() - self._drag_offset)
            nx = max(0, min(new_pos.x(), self.parent().width() - self.width()))
            ny = max(40, min(new_pos.y(), self.parent().height() - self.height() - 100))
            self.move(nx, ny)
            e.accept()

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.OpenHandCursor)
        self.position_changed.emit(self, self.x(), self.y())

    # ------------------------------------------------------------
    #  Правый клик
    # ------------------------------------------------------------

    def contextMenuEvent(self, e):
        menu = make_menu(self)
        a_lock = menu.addAction("🔒 Заблокировать" if not self._locked else "🔓 Разблокировать")

        def toggle_lock():
            self._locked = not self._locked
        a_lock.triggered.connect(toggle_lock)

        a_remove = menu.addAction("🗑 Удалить виджет")
        a_remove.triggered.connect(lambda: self.remove_requested.emit(self))

        menu.exec(e.globalPos())

    # ------------------------------------------------------------
    #  Отрисовка стекла
    # ------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        radius = 20

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QBrush(QColor(28, 34, 54, 200)))

        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidth(1)
        p.setPen(pen)
        p.drawPath(path)

        hl = QPainterPath()
        hl.addRoundedRect(rect.adjusted(1, 1, -1, -rect.height() // 2),
                          radius, radius)
        grad = QLinearGradient(0, rect.top(), 0, rect.top() + rect.height() // 2)
        grad.setColorAt(0, QColor(255, 255, 255, 22))
        grad.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(hl, QBrush(grad))