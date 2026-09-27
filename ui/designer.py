"""
MountOS — Визуальный дизайнер интерфейса.

Создание приложений MountOS без ручного кода:
  • Палитра элементов (кнопка, поле, метка, список, чекбокс, слайдер, прогресс-бар)
  • Drag&drop с палитры на холст
  • Перетаскивание элементов на холсте
  • Изменение свойств (текст, размер, координаты)
  • Сетка для выравнивания
  • Живой предпросмотр
  • Генерация кода .py для MountOS
  • Сохранение проекта и кода в VFS

API:
    from ui.designer import DesignerWindow
    win = DesignerWindow(host)
    win.show()
"""

import json
import time
import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QLineEdit, QTextEdit, QListWidget,
                                QListWidgetItem, QComboBox, QSpinBox,
                                QCheckBox, QSlider, QProgressBar, QFrame,
                                QSplitter, QScrollArea, QMessageBox, QDialog,
                                QDialogButtonBox, QFormLayout, QSizePolicy,
                                QToolButton, QGroupBox, QInputDialog)
from PySide6.QtCore import Qt, QPoint, QRect, QSize, QTimer, QMimeData, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
                            QDrag, QPixmap, QIcon, QKeySequence, QShortcut)

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Дизайнер"
APP_ICON = "editor"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


DESIGNER_DIR = "/Documents/Designer"


# ============================================================
#  Поиск VFS / Desktop
# ============================================================

def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return getattr(p.desktop_ref, "vfs", None)
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "vfs"):
            return top.vfs
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "vfs"):
            return ref.vfs
    return None


def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        if hasattr(p, "desktop_ref") and p.desktop_ref is not None:
            return p.desktop_ref
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
        ref = getattr(top, "desktop_ref", None)
        if ref is not None:
            return ref
    return None


# ============================================================
#  Палитра элементов
# ============================================================

ELEMENTS = [
    {"type": "label",       "name": "Метка",       "icon": "editor",     "default_w": 120, "default_h": 32,  "default_text": "Текст"},
    {"type": "button",      "name": "Кнопка",      "icon": "plus",       "default_w": 120, "default_h": 40,  "default_text": "Кнопка"},
    {"type": "input",       "name": "Поле ввода",  "icon": "terminal",   "default_w": 200, "default_h": 36,  "default_text": ""},
    {"type": "textedit",    "name": "Текст. поле", "icon": "notes",      "default_w": 240, "default_h": 120, "default_text": ""},
    {"type": "checkbox",    "name": "Чекбокс",     "icon": "star",       "default_w": 160, "default_h": 28,  "default_text": "Опция"},
    {"type": "slider",      "name": "Слайдер",     "icon": "settings",   "default_w": 200, "default_h": 30,  "default_text": ""},
    {"type": "progress",    "name": "Прогресс",    "icon": "taskmgr",    "default_w": 200, "default_h": 16,  "default_text": ""},
    {"type": "list",        "name": "Список",      "icon": "files",      "default_w": 220, "default_h": 160, "default_text": ""},
    {"type": "combobox",    "name": "Выпадающий",  "icon": "grid",       "default_w": 180, "default_h": 36,  "default_text": "Опция 1, Опция 2"},
    {"type": "separator",   "name": "Разделитель", "icon": "back",       "default_w": 240, "default_h": 2,   "default_text": ""},
]


# ============================================================
#  Виджет одного элемента на холсте
# ============================================================

class DesignElement(QWidget):
    """Элемент на холсте дизайнера."""

    selected = Signal(object)
    moved = Signal(object)

    def __init__(self, elem_type: str, name: str, text: str = "",
                 width: int = 120, height: int = 32, parent=None):
        super().__init__(parent)
        self.elem_type = elem_type
        self.elem_name = name
        self.elem_text = text
        self.setFixedSize(width, height)
        self.setCursor(Qt.OpenHandCursor)

        self._dragging = False
        self._drag_offset = QPoint()
        self._selected = False

        self._setup_appearance()

    def _setup_appearance(self):
        """Устанавливает стиль в зависимости от типа."""
        accent = state().get("accent", "#6EC6FF")
        base_style = f"""
            QWidget {{
                background: transparent;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
            }}
        """
        self.setStyleSheet(base_style)

    # ------------------------------------------------------------

    def set_selected(self, value: bool):
        self._selected = value
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            self.selected.emit(self)
            self.raise_()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._dragging:
            new_pos = self.mapToParent(e.pos() - self._drag_offset)
            # Привязка к сетке 10px при зажатом Shift
            if e.modifiers() & Qt.ShiftModifier:
                new_pos.setX((new_pos.x() // 10) * 10)
                new_pos.setY((new_pos.y() // 10) * 10)
            self.move(new_pos)
            self.moved.emit(self)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, e):
        """Двойной клик — редактирование свойств."""
        if self.parent():
            # Открываем диалог через родителя
            parent = self.parent()
            while parent and not hasattr(parent, "edit_element"):
                parent = parent.parent() if parent.parent() else None
            if parent and hasattr(parent, "edit_element"):
                parent.edit_element(self)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        accent = state().get("accent", "#6EC6FF")

        # Цветная подсветка выбранного
        if self._selected:
            p.setBrush(QBrush(QColor(accent)))
            p.setPen(QPen(QColor(accent), 2))
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.NoBrush)
        else:
            p.setBrush(QBrush(QColor(255, 255, 255, 15)))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)

        # Иконка элемента в левом верхнем углу
        p.setPen(QColor(255, 255, 255, 180))
        font = QFont()
        font.setPointSize(10)
        p.setFont(font)

        # Текст
        if self.elem_type == "label":
            p.drawText(rect.adjusted(8, 0, -8, 0),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       self.elem_text or "Метка")
        elif self.elem_type == "button":
            p.setBrush(QBrush(QColor(accent)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            p.setPen(QColor("white"))
            p.drawText(rect, Qt.AlignCenter, self.elem_text or "Кнопка")
        elif self.elem_type == "input":
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(rect.adjusted(8, 0, -8, 0),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       self.elem_text or "Placeholder…")
        elif self.elem_type == "textedit":
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            p.setPen(QColor(255, 255, 255, 100))
            p.drawText(rect.adjusted(8, 8, -8, -8),
                       Qt.AlignTop | Qt.AlignLeft,
                       self.elem_text or "Текстовое поле")
        elif self.elem_type == "checkbox":
            # Квадратик
            box = QRect(2, (rect.height() - 18) // 2, 18, 18)
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(QPen(QColor(255, 255, 255, 100), 1))
            p.drawRoundedRect(box, 4, 4)
            # Галочка
            p.setPen(QPen(QColor(accent), 2))
            p.drawLine(box.left() + 4, box.center().y(),
                       box.center().x() - 1, box.bottom() - 4)
            p.drawLine(box.center().x() - 1, box.bottom() - 4,
                       box.right() - 4, box.top() + 4)
            # Текст
            p.setPen(QColor(255, 255, 255, 200))
            p.drawText(QRect(24, 0, rect.width() - 24, rect.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       self.elem_text or "Опция")
        elif self.elem_type == "slider":
            y = rect.center().y()
            p.setPen(QPen(QColor(255, 255, 255, 60), 3))
            p.drawLine(4, y, rect.width() - 4, y)
            # Заполнение
            p.setPen(QPen(QColor(accent), 3))
            p.drawLine(4, y, rect.width() // 2, y)
            # Ручка
            p.setBrush(QBrush(QColor("white")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(rect.width() // 2, y), 7, 7)
        elif self.elem_type == "progress":
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            fill = QRect(rect.left(), rect.top(),
                         int(rect.width() * 0.6), rect.height())
            p.setBrush(QBrush(QColor(accent)))
            p.drawRoundedRect(fill, 6, 6)
        elif self.elem_type == "list":
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            # Пункты
            for i in range(4):
                y = 14 + i * 22
                if y < rect.height() - 10:
                    p.setPen(QColor(255, 255, 255, 60))
                    p.drawText(QRect(8, y, rect.width() - 16, 20),
                               Qt.AlignLeft | Qt.AlignVCenter,
                               f"  Элемент {i + 1}")
        elif self.elem_type == "combobox":
            p.setBrush(QBrush(QColor(0, 0, 0, 80)))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)
            p.setPen(QColor(255, 255, 255, 200))
            text = self.elem_text.split(",")[0].strip() if self.elem_text else "Опция 1"
            p.drawText(rect.adjusted(8, 0, -30, 0),
                       Qt.AlignLeft | Qt.AlignVCenter, text)
            # Треугольник
            cx = rect.width() - 14
            cy = rect.center().y()
            p.setBrush(QBrush(QColor(255, 255, 255, 150)))
            p.setPen(Qt.NoPen)
            from PySide6.QtGui import QPolygonF
            from PySide6.QtCore import QPointF
            tri = QPolygonF([
                QPointF(cx - 4, cy - 3),
                QPointF(cx + 4, cy - 3),
                QPointF(cx, cy + 3),
            ])
            p.drawPolygon(tri)
        elif self.elem_type == "separator":
            y = rect.center().y()
            p.setPen(QPen(QColor(255, 255, 255, 60), 2))
            p.drawLine(0, y, rect.width(), y)


# ============================================================
#  Холст дизайнера
# ============================================================

class DesignerCanvas(QWidget):
    """Холст для размещения элементов."""

    selection_changed = Signal(object)  # выделенный элемент или None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)

        self.elements = []      # список DesignElement
        self._selected = None

        self.setStyleSheet("""
            DesignerCanvas {
                background: rgba(20, 26, 40, 1);
            }
        """)

        # Делаем холст drag&drop-приёмником
        self.setAcceptDrops(True)

    # ------------------------------------------------------------

    def add_element(self, elem_type: str, x: int = None, y: int = None):
        """Добавляет новый элемент."""
        # Находим описание
        info = None
        for e in ELEMENTS:
            if e["type"] == elem_type:
                info = e
                break
        if not info:
            return

        # Позиция
        if x is None or y is None:
            x = 40 + (len(self.elements) % 8) * 30
            y = 40 + (len(self.elements) % 8) * 30

        elem = DesignElement(
            info["type"], info["name"],
            text=info["default_text"],
            width=info["default_w"],
            height=info["default_h"],
            parent=self,
        )
        elem.move(x, y)
        elem.show()
        elem.selected.connect(self._on_select)
        elem.moved.connect(lambda _: self.update())

        self.elements.append(elem)
        self._on_select(elem)
        return elem

    def remove_element(self, elem: DesignElement):
        if elem in self.elements:
            self.elements.remove(elem)
            if self._selected is elem:
                self._selected = None
                self.selection_changed.emit(None)
            elem.setParent(None)
            self.update()

    def clear(self):
        for e in list(self.elements):
            e.setParent(None)
        self.elements = []
        self._selected = None
        self.selection_changed.emit(None)
        self.update()

    def get_selected(self):
        return self._selected

    # ------------------------------------------------------------

    def _on_select(self, elem):
        # Снимаем выделение со всех
        for e in self.elements:
            e.set_selected(e is elem)
        self._selected = elem
        self.selection_changed.emit(elem)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            # Клик по пустому месту — снять выделение
            self._on_select(None)

    # ------------------------------------------------------------

    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        elem_type = e.mimeData().text()
        pos = e.position().toPoint()
        if elem_type:
            self.add_element(elem_type, pos.x() - 40, pos.y() - 16)
            e.acceptProposedAction()

    # ------------------------------------------------------------

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete and self._selected:
            self.remove_element(self._selected)
            e.accept()
            return

        # Стрелки — точное перемещение
        if self._selected and e.key() in (Qt.Key_Left, Qt.Key_Right,
                                            Qt.Key_Up, Qt.Key_Down):
            step = 1 if not (e.modifiers() & Qt.ControlModifier) else 10
            x = self._selected.x()
            y = self._selected.y()
            if e.key() == Qt.Key_Left:  x -= step
            if e.key() == Qt.Key_Right: x += step
            if e.key() == Qt.Key_Up:    y -= step
            if e.key() == Qt.Key_Down:  y += step
            self._selected.move(max(0, x), max(0, y))
            self.update()
            e.accept()
            return

        super().keyPressEvent(e)

    # ------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Фон
        p.fillRect(self.rect(), QColor("#0E1420"))

        # Сетка 20px
        p.setPen(QPen(QColor(255, 255, 255, 10), 1))
        for x in range(0, self.width(), 20):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 20):
            p.drawLine(0, y, self.width(), y)

        # Сетка 100px — крупнее
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        for x in range(0, self.width(), 100):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 100):
            p.drawLine(0, y, self.width(), y)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)
    desktop = _get_desktop(root)

    st = {
        "project_name": "my_app",
        "window_width": 800,
        "window_height": 600,
        "app_name": "Моё приложение",
        "app_icon": "star",
        "author": "Ты",
    }

    # ============================================================
    #  Левая панель — палитра + свойства
    # ============================================================
    left = QWidget()
    left.setFixedWidth(280)
    left.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    ll = QVBoxLayout(left)
    ll.setContentsMargins(14, 16, 14, 16)
    ll.setSpacing(10)

    title = QLabel("🎨  Дизайнер")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    ll.addWidget(title)

    # ---- Палитра элементов ----
    palette_lbl = QLabel("ПАЛИТРА ЭЛЕМЕНТОВ")
    palette_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    ll.addWidget(palette_lbl)

    palette_list = QListWidget()
    palette_list.setDragEnabled(True)
    palette_list.setDragDropMode(QListWidget.DragOnly)
    palette_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item {
            padding: 8px 10px;
            border-radius: 6px;
        }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    palette_list.setFixedHeight(220)

    for elem in ELEMENTS:
        item = QListWidgetItem(QIcon(get_icon(elem["icon"], 18, "#FFFFFF")),
                                f"  {elem['name']}")
        item.setData(Qt.UserRole, elem["type"])
        palette_list.addItem(item)

    # Кастомный drag&drop
    def start_drag(supported_actions):
        item = palette_list.currentItem()
        if not item:
            return
        elem_type = item.data(Qt.UserRole)
        drag = QDrag(palette_list)
        mime = QMimeData()
        mime.setText(elem_type)
        drag.setMimeData(mime)
        # Иконка при перетаскивании
        pm = get_icon("plus", 32, "#6EC6FF")
        drag.setPixmap(pm)
        drag.exec(Qt.CopyAction)

    palette_list.startDrag = start_drag
    ll.addWidget(palette_list)

    # Двойной клик — быстро добавить в центр
    def quick_add(item):
        elem_type = item.data(Qt.UserRole)
        canvas.add_element(elem_type,
                            canvas.width() // 2 - 60,
                            canvas.height() // 2 - 20)

    palette_list.itemDoubleClicked.connect(quick_add)

    # ---- Свойства выбранного ----
    props_lbl = QLabel("СВОЙСТВА")
    props_lbl.setStyleSheet(palette_lbl.styleSheet())
    ll.addWidget(props_lbl)

    props_box = QWidget()
    props_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
        }
        QLabel {
            color: rgba(255,255,255,0.75);
            font-size: 11px;
            background: transparent;
            border: none;
        }
    """)
    pl = QFormLayout(props_box)
    pl.setContentsMargins(12, 12, 12, 12)
    pl.setSpacing(8)

    type_lbl = QLabel("—")
    type_lbl.setStyleSheet("color: rgba(255,255,255,0.90); font-weight: 600; font-size: 12px; background: transparent; border: none;")
    pl.addRow("Тип:", type_lbl)

    name_lbl = QLabel("—")
    name_lbl.setStyleSheet("color: rgba(255,255,255,0.90); font-size: 12px; background: transparent; border: none;")
    pl.addRow("Имя:", name_lbl)

    text_edit = QLineEdit()
    text_edit.setPlaceholderText("Текст элемента")
    text_edit.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 6px 10px;
            font-size: 12px;
        }
    """)
    def on_text_changed(value):
        elem = canvas.get_selected()
        if elem:
            elem.elem_text = value
            elem.update()
    text_edit.textChanged.connect(on_text_changed)
    pl.addRow("Текст:", text_edit)

    x_spin = QSpinBox()
    x_spin.setRange(0, 5000)
    x_spin.setStyleSheet("""
        QSpinBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            padding: 4px 8px;
            font-size: 12px;
        }
    """)
    def on_x_changed(v):
        elem = canvas.get_selected()
        if elem:
            elem.move(v, elem.y())
    x_spin.valueChanged.connect(on_x_changed)
    pl.addRow("X:", x_spin)

    y_spin = QSpinBox()
    y_spin.setRange(0, 5000)
    y_spin.setStyleSheet(x_spin.styleSheet())
    def on_y_changed(v):
        elem = canvas.get_selected()
        if elem:
            elem.move(elem.x(), v)
    y_spin.valueChanged.connect(on_y_changed)
    pl.addRow("Y:", y_spin)

    w_spin = QSpinBox()
    w_spin.setRange(10, 2000)
    w_spin.setStyleSheet(x_spin.styleSheet())
    def on_w_changed(v):
        elem = canvas.get_selected()
        if elem:
            elem.setFixedWidth(v)
    w_spin.valueChanged.connect(on_w_changed)
    pl.addRow("Ширина:", w_spin)

    h_spin = QSpinBox()
    h_spin.setRange(2, 2000)
    h_spin.setStyleSheet(x_spin.styleSheet())
    def on_h_changed(v):
        elem = canvas.get_selected()
        if elem:
            elem.setFixedHeight(v)
    h_spin.valueChanged.connect(on_h_changed)
    pl.addRow("Высота:", h_spin)

    ll.addWidget(props_box)
    ll.addStretch(1)

    # Кнопки
    clear_btn = QPushButton("🗑  Очистить холст")
    clear_btn.setCursor(Qt.PointingHandCursor)
    clear_btn.setFixedHeight(36)
    clear_btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,107,138,0.15);
            color: #FFA0B4;
            border: 1px solid rgba(255,107,138,0.40);
            border-radius: 10px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,107,138,0.35); color: white; }
    """)
    def do_clear():
        ans = QMessageBox.question(root, "Очистить",
            "Удалить все элементы?", QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            canvas.clear()
    clear_btn.clicked.connect(do_clear)
    ll.addWidget(clear_btn)

    h.addWidget(left)

    # ============================================================
    #  Центр — холст
    # ============================================================
    center = QWidget()
    cl = QVBoxLayout(center)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    # Верхняя панель
    topbar = QWidget()
    topbar.setFixedHeight(52)
    topbar.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-bottom: 1px solid rgba(255,255,255,0.08);
    """)
    tbl = QHBoxLayout(topbar)
    tbl.setContentsMargins(14, 8, 14, 8)
    tbl.setSpacing(8)

    project_lbl = QLabel(f"📁  {st['project_name']}")
    project_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 600;")
    tbl.addWidget(project_lbl)
    tbl.addStretch(1)

    def top_btn(text, callback, accent=False):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(36)
        if accent:
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(110,231,183,0.22);
                    color: white;
                    border: 1px solid rgba(110,231,183,0.60);
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover { background: rgba(110,231,183,0.42); }
            """)
        else:
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.06);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.12);
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 12px;
                }
                QPushButton:hover { background: rgba(255,255,255,0.18); }
            """)
        b.clicked.connect(callback)
        return b

    settings_btn = top_btn("⚙  Настройки проекта", lambda: open_project_settings())
    tbl.addWidget(settings_btn)

    preview_btn = top_btn("👁  Предпросмотр", lambda: preview_app())
    tbl.addWidget(preview_btn)

    code_btn = top_btn("📄  Показать код", lambda: show_code_dialog())
    tbl.addWidget(code_btn)

    save_btn = top_btn("💾  Сохранить .py", lambda: save_code(), accent=True)
    tbl.addWidget(save_btn)

    cl.addWidget(topbar)

    # Холст
    canvas = DesignerCanvas()
    cl.addWidget(canvas, 1)

    # Нижняя строка
    status_lbl = QLabel("Перетащи элемент из палитры или кликни дважды")
    status_lbl.setFixedHeight(24)
    status_lbl.setStyleSheet("""
        background: rgba(0,0,0,0.30);
        color: rgba(255,255,255,0.55);
        font-size: 11px;
        padding: 3px 12px;
        border-top: 1px solid rgba(255,255,255,0.06);
    """)
    cl.addWidget(status_lbl)

    h.addWidget(center, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def on_selection_changed(elem):
        if elem is None:
            type_lbl.setText("—")
            name_lbl.setText("—")
            text_edit.blockSignals(True)
            text_edit.clear()
            text_edit.blockSignals(False)
            return
        type_lbl.setText(elem.elem_type)
        name_lbl.setText(elem.elem_name)
        text_edit.blockSignals(True)
        text_edit.setText(elem.elem_text)
        text_edit.blockSignals(False)
        # Обновляем координаты
        x_spin.blockSignals(True)
        y_spin.blockSignals(True)
        w_spin.blockSignals(True)
        h_spin.blockSignals(True)
        x_spin.setValue(elem.x())
        y_spin.setValue(elem.y())
        w_spin.setValue(elem.width())
        h_spin.setValue(elem.height())
        x_spin.blockSignals(False)
        y_spin.blockSignals(False)
        w_spin.blockSignals(False)
        h_spin.blockSignals(False)

    canvas.selection_changed.connect(on_selection_changed)

    def edit_element(elem):
        """Диалог редактирования."""
        text, ok = QInputDialog.getText(
            root, f"Редактировать {elem.elem_name}",
            "Текст:", text=elem.elem_text)
        if ok:
            elem.elem_text = text
            elem.update()
            if elem is canvas.get_selected():
                text_edit.blockSignals(True)
                text_edit.setText(text)
                text_edit.blockSignals(False)

    canvas.edit_element = edit_element

    # ---- Настройки проекта ----
    def open_project_settings():
        dlg = QDialog(root)
        dlg.setWindowTitle("Настройки проекта")
        dlg.setFixedSize(440, 320)
        dlg.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QLabel { color: rgba(255,255,255,0.85); font-size: 12px; }
            QLineEdit, QSpinBox, QComboBox {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }
        """)

        form = QFormLayout(dlg)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(12)

        proj_name = QLineEdit(st["project_name"])
        form.addRow("Имя проекта:", proj_name)

        app_name = QLineEdit(st["app_name"])
        form.addRow("Название приложения:", app_name)

        icon_combo = QComboBox()
        for icon_key in ["star", "files", "terminal", "notes", "settings",
                          "calculator", "globe", "grid", "browser",
                          "music", "gallery", "taskmgr", "editor"]:
            icon_combo.addItem(icon_key)
        icon_combo.setCurrentText(st["app_icon"])
        form.addRow("Иконка:", icon_combo)

        author_edit = QLineEdit(st["author"])
        form.addRow("Автор:", author_edit)

        win_w = QSpinBox()
        win_w.setRange(300, 3000)
        win_w.setValue(st["window_width"])
        form.addRow("Ширина окна:", win_w)

        win_h = QSpinBox()
        win_h.setRange(200, 3000)
        win_h.setValue(st["window_height"])
        form.addRow("Высота окна:", win_h)

        btns = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        form.addRow(btns)

        if dlg.exec() == QDialog.Accepted:
            st["project_name"] = proj_name.text().strip() or "my_app"
            st["app_name"] = app_name.text().strip() or "Приложение"
            st["app_icon"] = icon_combo.currentText()
            st["author"] = author_edit.text().strip() or "неизвестно"
            st["window_width"] = win_w.value()
            st["window_height"] = win_h.value()
            project_lbl.setText(f"📁  {st['project_name']}")

    # ---- Генерация кода ----
    def generate_code() -> str:
        """Генерирует .py-файл приложения MountOS."""
        lines = []
        lines.append('"""')
        lines.append(f'{st["app_name"]} — приложение MountOS.')
        lines.append(f'Создано в визуальном дизайнере MountOS.')
        lines.append(f'Автор: {st["author"]}')
        lines.append(f'Дата: {time.strftime("%Y-%m-%d %H:%M")}')
        lines.append('"""')
        lines.append("")
        lines.append("from PySide6.QtWidgets import (")
        lines.append("    QWidget, QLabel, QPushButton, QLineEdit, QTextEdit,")
        lines.append("    QCheckBox, QSlider, QProgressBar, QListWidget,")
        lines.append("    QComboBox, QFrame")
        lines.append(")")
        lines.append("from PySide6.QtCore import Qt")
        lines.append("")
        lines.append(f'APP_NAME    = "{st["app_name"]}"')
        lines.append(f'APP_ICON    = "{st["app_icon"]}"')
        lines.append(f'APP_VERSION = "1.0"')
        lines.append(f'APP_AUTHOR  = "{st["author"]}"')
        lines.append("")
        lines.append("")
        lines.append("def build():")
        lines.append("    w = QWidget()")
        lines.append(f"    w.setMinimumSize({st['window_width']}, {st['window_height']})")
        lines.append("")
        lines.append("    # Элементы, созданные в дизайнере")
        lines.append("    elements = []")
        lines.append("")

        # Сортируем элементы по Z-order (порядку добавления)
        for i, elem in enumerate(canvas.elements):
            var_name = f"elem_{i}"
            x, y = elem.x(), elem.y()
            w_, h_ = elem.width(), elem.height()
            text = elem.elem_text.replace('"', '\\"')

            if elem.elem_type == "label":
                lines.append(f"    {var_name} = QLabel({repr(elem.elem_text)}, w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setStyleSheet('color: white; font-size: 14px;')")
            elif elem.elem_type == "button":
                lines.append(f"    {var_name} = QPushButton({repr(elem.elem_text)}, w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setCursor(Qt.PointingHandCursor)")
                lines.append(f"    {var_name}.setStyleSheet('" + """
                    QPushButton {
                        background: rgba(110,198,255,0.25);
                        color: white;
                        border: 1px solid rgba(110,198,255,0.60);
                        border-radius: 10px;
                        font-size: 13px;
                    }
                    QPushButton:hover { background: rgba(110,198,255,0.45); }
                """.replace("\n", " ").replace("  ", " ") + "')")
            elif elem.elem_type == "input":
                placeholder = elem.elem_text or "Введи текст"
                lines.append(f"    {var_name} = QLineEdit(w)")
                lines.append(f"    {var_name}.setPlaceholderText({repr(placeholder)})")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setStyleSheet('" + """
                    QLineEdit {
                        background: rgba(255,255,255,0.08);
                        color: white;
                        border: 1px solid rgba(255,255,255,0.15);
                        border-radius: 8px;
                        padding: 6px 10px;
                    }
                """.replace("\n", " ").replace("  ", " ") + "')")
            elif elem.elem_type == "textedit":
                lines.append(f"    {var_name} = QTextEdit(w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setStyleSheet('" + """
                    QTextEdit {
                        background: rgba(0,0,0,0.22);
                        color: white;
                        border: 1px solid rgba(255,255,255,0.10);
                        border-radius: 10px;
                        padding: 10px;
                    }
                """.replace("\n", " ").replace("  ", " ") + "')")
            elif elem.elem_type == "checkbox":
                lines.append(f"    {var_name} = QCheckBox({repr(elem.elem_text)}, w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setStyleSheet('color: white; font-size: 13px;')")
            elif elem.elem_type == "slider":
                lines.append(f"    {var_name} = QSlider(Qt.Horizontal, w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setRange(0, 100)")
            elif elem.elem_type == "progress":
                lines.append(f"    {var_name} = QProgressBar(w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setRange(0, 100)")
                lines.append(f"    {var_name}.setValue(50)")
                lines.append(f"    {var_name}.setTextVisible(False)")
            elif elem.elem_type == "list":
                lines.append(f"    {var_name} = QListWidget(w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    for i in range(5):")
                lines.append(f"        {var_name}.addItem(f'Элемент {{i + 1}}')")
            elif elem.elem_type == "combobox":
                options = [o.strip() for o in elem.elem_text.split(",")] if elem.elem_text else ["Опция 1"]
                lines.append(f"    {var_name} = QComboBox(w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.addItems({repr(options)})")
            elif elem.elem_type == "separator":
                lines.append(f"    {var_name} = QFrame(w)")
                lines.append(f"    {var_name}.setGeometry({x}, {y}, {w_}, {h_})")
                lines.append(f"    {var_name}.setFrameShape(QFrame.HLine)")
                lines.append(f"    {var_name}.setStyleSheet('background: rgba(255,255,255,0.15); border: none;')")
            else:
                continue

            lines.append(f"    {var_name}.show()")
            lines.append(f"    elements.append({var_name})")
            lines.append("")

        lines.append("    return w")
        lines.append("")
        return "\n".join(lines)

    def show_code_dialog():
        code = generate_code()
        dlg = QDialog(root)
        dlg.setWindowTitle("Сгенерированный код")
        dlg.resize(800, 600)
        dlg.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QTextEdit {
                background: rgba(0,0,0,0.30);
                color: #E0E6F0;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                padding: 12px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
        """)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl = QLabel(f"Файл: {st['project_name']}.py")
        lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 600;")
        lay.addWidget(lbl)

        te = QTextEdit()
        te.setPlainText(code)
        te.setReadOnly(True)
        lay.addWidget(te, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.20);
                color: white;
                border: 1px solid rgba(110,198,255,0.50);
                border-radius: 8px;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.40); }
        """)
        lay.addWidget(btns)
        dlg.exec()

    def save_code():
        if vfs is None:
            QMessageBox.warning(root, "Ошибка", "VFS недоступна")
            return
        if not canvas.elements:
            QMessageBox.information(root, "Дизайнер",
                "Сначала добавь элементы на холст.")
            return

        code = generate_code()

        # Спрашиваем куда сохранять
        choice = QMessageBox.question(
            root, "Сохранить",
            "Куда сохранить .py-файл?\n\n"
            "Да — в system/user_apps (приложение MountOS)\n"
            "Нет — в /Documents/Designer (черновик)",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if choice == QMessageBox.Cancel:
            return

        try:
            if choice == QMessageBox.Yes:
                # Сохраняем как приложение MountOS
                desktop = _get_desktop(root)
                base_dir = None
                if desktop and hasattr(desktop, "base_dir"):
                    base_dir = desktop.base_dir

                if not base_dir:
                    QMessageBox.warning(root, "Ошибка",
                        "Не могу найти папку MountOS.")
                    return

                user_dir = os.path.join(base_dir, "system", "user_apps")
                os.makedirs(user_dir, exist_ok=True)
                filename = st["project_name"] + ".py"
                path = os.path.join(user_dir, filename)

                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)

                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push("Приложение создано",
                        f"{st['app_name']} → {filename}")
                QMessageBox.information(root, "Готово",
                    f"Файл сохранён как приложение:\n{path}\n\n"
                    f"Оно появится в доке MountOS (возможно, "
                    f"нужно перезапустить).")
            else:
                # Сохраняем как черновик
                vfs.mkdir(DESIGNER_DIR)
                filename = st["project_name"] + ".py"
                path = f"{DESIGNER_DIR}/{filename}"
                vfs.write_text(path, code)

                # Также сохраняем JSON-проект
                project = {
                    "name": st["project_name"],
                    "app_name": st["app_name"],
                    "app_icon": st["app_icon"],
                    "author": st["author"],
                    "window": [st["window_width"], st["window_height"]],
                    "elements": [
                        {
                            "type": e.elem_type,
                            "name": e.elem_name,
                            "text": e.elem_text,
                            "x": e.x(), "y": e.y(),
                            "w": e.width(), "h": e.height(),
                        }
                        for e in canvas.elements
                    ],
                    "saved_at": time.time(),
                }
                vfs.write_text(f"{DESIGNER_DIR}/{st['project_name']}.json",
                                json.dumps(project, ensure_ascii=False, indent=2))

                if desktop and hasattr(desktop, "notifications"):
                    desktop.notifications.push("Проект сохранён",
                        f"{path}")
                QMessageBox.information(root, "Сохранено",
                    f"Код: {path}\n"
                    f"Проект: {DESIGNER_DIR}/{st['project_name']}.json")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    def preview_app():
        """Запускает предпросмотр приложения в новом окне."""
        if not canvas.elements:
            QMessageBox.information(root, "Дизайнер",
                "Сначала добавь элементы на холст.")
            return
        code = generate_code()
        try:
            # Компилируем код в отдельное пространство имён
            namespace = {}
            exec(code, namespace)
            if "build" not in namespace:
                raise RuntimeError("Нет build()")
            widget = namespace["build"]()
            # Показываем в диалоге
            dlg = QDialog(root)
            dlg.setWindowTitle(f"Предпросмотр: {st['app_name']}")
            dlg.resize(st["window_width"] + 40, st["window_height"] + 40)
            dlg.setStyleSheet("background: #0E1420;")
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 20, 20, 20)
            widget.setParent(dlg)
            widget.setStyleSheet(widget.styleSheet() + "; background: transparent;")
            lay.addWidget(widget)
            dlg.exec()
        except SyntaxError as e:
            QMessageBox.warning(root, "Ошибка кода",
                f"Синтаксис: строка {e.lineno}: {e.msg}")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка предпросмотра", str(e))

    # ============================================================
    #  Старт
    # ============================================================

    # Добавляем пару примеров
    QTimer.singleShot(200, lambda: canvas.add_element("label", 40, 40))
    QTimer.singleShot(250, lambda: canvas.add_element("button", 40, 100))
    QTimer.singleShot(300, lambda: canvas.add_element("input", 40, 160))

    QTimer.singleShot(400, canvas.setFocus)

    return root