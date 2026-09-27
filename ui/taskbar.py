from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QMenu
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon

from ui.icons import get_icon
from ui.settings_state import state


class TaskButton(QPushButton):
    """Кнопка одного открытого окна на панели задач."""

    def __init__(self, win, icon_name, name, parent=None):
        super().__init__(name, parent)
        self.win = win
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)
        self.setMinimumWidth(160)

        self.setIcon(QIcon(get_icon(icon_name, 18, state().get("accent"))))
        self.setIconSize(QSize(16, 16))

        self.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 12px;
                padding: 6px 14px;
                text-align: left;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.20);
                border: 1px solid rgba(255,255,255,0.30);
            }
            QPushButton:pressed {
                background: rgba(110,198,255,0.35);
            }
        """)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(30, 36, 56, 0.98);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item { padding: 6px 18px; border-radius: 6px; }
            QMenu::item:selected { background: rgba(110,198,255,0.30); }
        """)
        a1 = QAction("Свернуть", self)
        a1.triggered.connect(self.win.showMinimized)

        a2 = QAction("Развернуть", self)
        a2.triggered.connect(self.win._maximize)

        a3 = QAction("Закрыть", self)
        a3.triggered.connect(self.win.close)

        menu.addAction(a1)
        menu.addAction(a2)
        menu.addSeparator()
        menu.addAction(a3)
        menu.exec(e.globalPos())


class Taskbar(QWidget):
    """Плавающая панель открытых окон над доком."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)

        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(14, 8, 14, 8)
        self.lay.setSpacing(8)
        self.lay.addStretch(1)

        self.buttons = {}   # win -> button

        self.setStyleSheet("""
            Taskbar {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 18px;
            }
        """)
        self.hide()  # пока нет окон — не показываемся

    def add_window(self, win, icon_name, name):
        btn = TaskButton(win, icon_name, name)
        btn.clicked.connect(lambda: self._focus(win))
        self.lay.insertWidget(self.lay.count() - 1, btn)
        self.buttons[win] = btn
        self.show()

    def remove_window(self, win):
        btn = self.buttons.pop(win, None)
        if btn:
            btn.setParent(None)
        if not self.buttons:
            self.hide()

    def _focus(self, win):
        try:
            if win.isMinimized():
                win.showNormal()
            win.raise_()
            win.activateWindow()
        except RuntimeError:
            # окно уже удалено Qt
            self.remove_window(win)