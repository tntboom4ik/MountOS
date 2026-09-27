"""
MountOS — Док.

Фичи:
  • Анимация увеличения при наведении
  • Ручной resize — потяни за верхний край
  • Пагинация — максимум 5 приложений на страницу
  • Стрелки ‹ › для переключения страниц
  • Индикатор страниц точками
  • Правый клик — удаление пользовательских приложений
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                                QSizePolicy)
from PySide6.QtCore import (Qt, QSize, Signal, QPropertyAnimation,
                             QEasingCurve, QPoint)
from PySide6.QtGui import QIcon

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu


APPS_PER_PAGE = 5
DEFAULT_ICON_SIZE = 52
MIN_DOCK_HEIGHT = 90
MAX_DOCK_HEIGHT = 160


# ============================================================
#  Иконка приложения
# ============================================================

class DockIcon(QPushButton):
    """Иконка приложения в доке."""

    delete_requested = Signal(str)

    def __init__(self, app_id, icon_name, name, builtin=True, parent=None):
        super().__init__("", parent)
        self.app_id = app_id
        self.icon_name = icon_name
        self.builtin = builtin
        self.base_size = DEFAULT_ICON_SIZE
        self.setFixedSize(self.base_size, self.base_size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)

        self._active = False
        self._refresh_icon()
        self._apply_style()

        state().changed.connect(self._on_state)

    def _on_state(self, key, val):
        if key == "accent":
            self._refresh_icon()
            self._apply_style()

    def _refresh_icon(self):
        color = "#FFFFFF" if not self._active else state().get("accent")
        pm = get_icon(self.icon_name, 32, color)
        self.setIcon(QIcon(pm))
        self.setIconSize(QSize(30, 30))

    def set_active(self, active: bool):
        self._active = active
        self._refresh_icon()
        self._apply_style()

    def _apply_style(self):
        accent = state().get("accent")
        if self._active:
            bg = f"rgba({self._hex_to_rgb(accent)}, 0.30)"
            border = f"rgba({self._hex_to_rgb(accent)}, 0.75)"
        else:
            bg = "rgba(255, 255, 255, 0.10)"
            border = "rgba(255, 255, 255, 0.14)"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.26);
                border: 1px solid rgba(255, 255, 255, 0.40);
            }}
            QPushButton:pressed {{
                background: rgba({self._hex_to_rgb(accent)}, 0.55);
            }}
        """)

    @staticmethod
    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"

    def enterEvent(self, e):
        self._animate(self.base_size + 10)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate(self.base_size)
        super().leaveEvent(e)

    def _animate(self, target):
        anim = QPropertyAnimation(self, b"size")
        anim.setDuration(150)
        anim.setStartValue(self.size())
        anim.setEndValue(QSize(target, target))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim

    def contextMenuEvent(self, e):
        menu = make_menu(self)
        a_open = menu.addAction("Открыть")
        a_open.triggered.connect(self.click)
        if not self.builtin:
            menu.addSeparator()
            a_del = menu.addAction("🗑  Удалить приложение")
            a_del.triggered.connect(lambda: self.delete_requested.emit(self.app_id))
        menu.exec(e.globalPos())


# ============================================================
#  Кнопка-стрелка ‹ ›
# ============================================================

class PageArrow(QPushButton):
    def __init__(self, direction: str, parent=None):
        super().__init__(parent)
        self.direction = direction
        self.setFixedSize(28, 52)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("‹" if direction == "left" else "›")
        self.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.75);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                font-size: 22px;
                font-weight: 300;
            }
            QPushButton:hover {
                background: rgba(110,198,255,0.28);
                color: white;
                border: 1px solid rgba(110,198,255,0.60);
            }
            QPushButton:pressed {
                background: rgba(110,198,255,0.45);
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.02);
                color: rgba(255,255,255,0.20);
                border: 1px solid rgba(255,255,255,0.04);
            }
        """)

    def set_enabled(self, enabled: bool):
        self.setEnabled(enabled)


# ============================================================
#  Точки-индикаторы страниц
# ============================================================

class PageDots(QWidget):
    """Точки-индикаторы страниц."""

    dot_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)
        self._pages = 1
        self._current = 0

    def set_pages(self, total: int, current: int):
        self._pages = max(1, total)
        self._current = current
        self.update()

    def sizeHint(self):
        return QSize(self._pages * 14 + 10, 10)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QBrush
        from PySide6.QtCore import QPointF

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        accent = state().get("accent", "#6EC6FF")
        n = self._pages
        w = self.width()
        h = self.height()

        if n == 0:
            return

        spacing = 14
        total_w = (n - 1) * spacing
        start_x = (w - total_w) / 2
        cy = h / 2

        for i in range(n):
            cx = start_x + i * spacing
            if i == self._current:
                p.setBrush(QBrush(QColor(accent)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(cx, cy), 4, 4)
            else:
                p.setBrush(QBrush(QColor(255, 255, 255, 60)))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(cx, cy), 3, 3)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        n = self._pages
        if n <= 1:
            return
        spacing = 14
        total_w = (n - 1) * spacing
        start_x = (self.width() - total_w) / 2
        x = e.position().x()
        idx = round((x - start_x) / spacing)
        if 0 <= idx < n:
            self.dot_clicked.emit(idx)


# ============================================================
#  Док
# ============================================================

class Dock(QWidget):
    app_launch_requested = Signal(str)
    app_install_requested = Signal()
    app_delete_requested = Signal(str)
    height_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(MIN_DOCK_HEIGHT)

        self._all_apps = {}
        self._icons = {}
        self._current_page = 0
        self._icon_size = DEFAULT_ICON_SIZE

        self._resizing = False
        self._resize_start_y = 0
        self._resize_start_h = 0

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(14, 6, 14, 6)
        self._root.setSpacing(2)

        # Верхний "хват"
        self._grip = QWidget()
        self._grip.setFixedHeight(6)
        self._grip.setCursor(Qt.SizeVerCursor)
        self._grip.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.08);
                border-radius: 3px;
                margin: 0 40%;
            }
            QWidget:hover {
                background: rgba(110,198,255,0.50);
            }
        """)
        self._root.addWidget(self._grip, 0, Qt.AlignHCenter)

        # Основной ряд
        self._main_row = QHBoxLayout()
        self._main_row.setContentsMargins(0, 0, 0, 0)
        self._main_row.setSpacing(6)

        self._left_arrow = PageArrow("left")
        self._left_arrow.clicked.connect(self._prev_page)
        self._main_row.addWidget(self._left_arrow)

        self._icons_container = QWidget()
        self._icons_layout = QHBoxLayout(self._icons_container)
        self._icons_layout.setContentsMargins(0, 0, 0, 0)
        self._icons_layout.setSpacing(10)
        self._icons_layout.setAlignment(Qt.AlignCenter)
        self._main_row.addWidget(self._icons_container, 1)

        self._right_arrow = PageArrow("right")
        self._right_arrow.clicked.connect(self._next_page)
        self._main_row.addWidget(self._right_arrow)

        self._root.addLayout(self._main_row, 1)

        # Точки
        self._dots = PageDots()
        self._dots.dot_clicked.connect(self._goto_page)
        self._root.addWidget(self._dots, 0, Qt.AlignHCenter)

        self.setStyleSheet("""
            Dock {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 26px;
            }
        """)

        self._update_arrows()

    # ------------------------------------------------------------
    #  Resize
    # ------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            y = e.position().y()
            if y < 12:
                self._resizing = True
                self._resize_start_y = e.globalPosition().toPoint().y()
                self._resize_start_h = self.height()
                self.setCursor(Qt.SizeVerCursor)
                e.accept()

    def mouseMoveEvent(self, e):
        if self._resizing:
            dy = self._resize_start_y - e.globalPosition().toPoint().y()
            new_h = max(MIN_DOCK_HEIGHT, min(MAX_DOCK_HEIGHT,
                                              self._resize_start_h + dy))
            self.setFixedHeight(new_h)
            ratio = (new_h - MIN_DOCK_HEIGHT) / (MAX_DOCK_HEIGHT - MIN_DOCK_HEIGHT)
            self._icon_size = int(DEFAULT_ICON_SIZE + ratio * 30)
            for ic in self._icons.values():
                ic.base_size = self._icon_size
                ic.setFixedSize(self._icon_size, self._icon_size)
                icon_size = int(self._icon_size * 0.6)
                ic.setIconSize(QSize(icon_size, icon_size))
            self.height_changed.emit(new_h)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._resizing:
            self._resizing = False
            self.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------
    #  populate
    # ------------------------------------------------------------

    def populate(self, apps: dict):
        self._all_apps = dict(apps)

        for i in reversed(range(self._icons_layout.count())):
            w = self._icons_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        self._icons.clear()

        for app_id, info in apps.items():
            ic = DockIcon(app_id, info.app_id, info.name,
                          builtin=info.builtin)
            ic.base_size = self._icon_size
            ic.setFixedSize(self._icon_size, self._icon_size)
            icon_size = int(self._icon_size * 0.6)
            ic.setIconSize(QSize(icon_size, icon_size))
            ic.clicked.connect(
                lambda _, a=app_id: self.app_launch_requested.emit(a))
            ic.delete_requested.connect(self.app_delete_requested.emit)
            self._icons[app_id] = ic

        self._current_page = 0
        self._rebuild_page()

    def _rebuild_page(self):
        for i in reversed(range(self._icons_layout.count())):
            w = self._icons_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        app_ids = list(self._icons.keys())
        total_pages = max(1, (len(app_ids) + APPS_PER_PAGE - 1) // APPS_PER_PAGE)
        self._current_page = max(0, min(self._current_page, total_pages - 1))

        start = self._current_page * APPS_PER_PAGE
        end = min(start + APPS_PER_PAGE, len(app_ids))

        for app_id in app_ids[start:end]:
            ic = self._icons[app_id]
            ic.setParent(self._icons_container)
            self._icons_layout.addWidget(ic)
            ic.show()

        is_last = (self._current_page == total_pages - 1)
        if is_last:
            add = QPushButton("")
            add.setToolTip("Установить приложение (.py)")
            add.setFixedSize(self._icon_size, self._icon_size)
            add.setCursor(Qt.PointingHandCursor)
            accent = state().get("accent")
            add.setIcon(QIcon(get_icon("plus", 26, accent)))
            icon_size = int(self._icon_size * 0.46)
            add.setIconSize(QSize(icon_size, icon_size))
            add.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({DockIcon._hex_to_rgb(accent)}, 0.15);
                    border: 1px dashed rgba({DockIcon._hex_to_rgb(accent)}, 0.60);
                    border-radius: 16px;
                }}
                QPushButton:hover {{
                    background: rgba({DockIcon._hex_to_rgb(accent)}, 0.35);
                    border: 1px solid {accent};
                }}
            """)
            add.clicked.connect(self.app_install_requested.emit)
            self._icons_layout.addWidget(add)

        self._dots.set_pages(total_pages, self._current_page)
        self._update_arrows()

    def _update_arrows(self):
        app_ids = list(self._icons.keys())
        total_pages = max(1, (len(app_ids) + APPS_PER_PAGE - 1) // APPS_PER_PAGE)
        self._left_arrow.setEnabled(self._current_page > 0)
        self._right_arrow.setEnabled(self._current_page < total_pages - 1)
        self._left_arrow.setVisible(total_pages > 1)
        self._right_arrow.setVisible(total_pages > 1)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._rebuild_page()

    def _next_page(self):
        app_ids = list(self._icons.keys())
        total_pages = max(1, (len(app_ids) + APPS_PER_PAGE - 1) // APPS_PER_PAGE)
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._rebuild_page()

    def _goto_page(self, idx):
        self._current_page = idx
        self._rebuild_page()

    def mark_active(self, app_id, active: bool):
        ic = self._icons.get(app_id)
        if ic:
            ic.set_active(active)