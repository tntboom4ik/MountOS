from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect)
from PySide6.QtCore import Qt, QPoint, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPainterPath, QBrush, QPen, QIcon, QPixmap

from ui.icons import get_icon
from ui.context_menu import make_menu


class Shortcut(QWidget):
    """Ярлык на приложение или файл на рабочем столе."""

    activated = Signal(object)
    remove_requested = Signal(object)
    position_changed = Signal(object, int, int)

    def __init__(self, parent, target_id: str, target_type: str,
                 label: str, icon_name: str, x=0, y=0):
        super().__init__(parent)
        self.target_id = target_id      # app_id или путь в VFS
        self.target_type = target_type  # "app" | "file"
        self.label_text = label
        self.icon_name = icon_name

        self.setFixedSize(96, 106)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.PointingHandCursor)
        self.move(x, y)

        self._drag_offset = QPoint()
        self._moved = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 4)
        lay.setSpacing(6)

        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self._refresh_icon()
        lay.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(label)
        self.text_lbl.setAlignment(Qt.AlignCenter)
        self.text_lbl.setWordWrap(True)
        self.text_lbl.setStyleSheet("""
            color: white;
            font-size: 11px;
            background: transparent;
        """)
        lay.addWidget(self.text_lbl)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        self._selected = False

    def _refresh_icon(self):
        pm = get_icon(self.icon_name, 44, "#FFFFFF")
        self.icon_lbl.setPixmap(pm)

    # --- клики ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.pos()
            self._moved = False
            self._selected = True
            self.update()
            e.accept()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            delta = e.pos() - self._drag_offset
            if delta.manhattanLength() > 4:
                self._moved = True
            new_pos = self.mapToParent(e.pos() - self._drag_offset)
            nx = max(0, min(new_pos.x(), self.parent().width() - self.width()))
            ny = max(40, min(new_pos.y(), self.parent().height() - self.height() - 100))
            self.move(nx, ny)
            e.accept()

    def mouseReleaseEvent(self, e):
        if not self._moved:
            self.activated.emit(self)
            self._selected = False
            self.update()
        else:
            self.position_changed.emit(self, self.x(), self.y())

    def mouseDoubleClickEvent(self, e):
        self.activated.emit(self)

    def contextMenuEvent(self, e):
        menu = make_menu(self)
        a_open = menu.addAction("Открыть")
        a_open.triggered.connect(lambda: self.activated.emit(self))
        a_rename = menu.addAction("Переименовать")
        a_rename.triggered.connect(self._rename)
        menu.addSeparator()
        a_del = menu.addAction("Удалить ярлык")
        a_del.triggered.connect(lambda: self.remove_requested.emit(self))
        menu.exec(e.globalPos())

    def _rename(self):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Переименовать ярлык",
                                         "Новое имя:", text=self.label_text)
        if ok and text.strip():
            self.label_text = text.strip()
            self.text_lbl.setText(self.label_text)

    # --- выделение ---
    def paintEvent(self, event):
        if not self._selected:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.fillPath(path, QBrush(QColor(110, 198, 255, 70)))
        pen = QPen(QColor(110, 198, 255, 180)); pen.setWidth(1)
        p.setPen(pen)
        p.drawPath(path)