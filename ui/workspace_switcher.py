"""
MountOS — Полноэкранный переключатель рабочих столов.

Открывается: Ctrl+Tab, Ctrl+Alt+Space или клик по индикатору
правой кнопкой. Показывает превью всех столов, как в KDE/GNOME.

Возможности:
  • Полноэкранный оверлей с затемнением
  • Плитки всех рабочих столов с превью
  • Клик по плитке → перейти на стол
  • Двойной клик → переименовать стол
  • Показывает список окон и виджетов на каждом столе
  • Ctrl+Tab — циклический обход
  • Esc — закрыть

API:
    from ui.workspace_switcher import WorkspaceSwitcher
    switcher = WorkspaceSwitcher(host)
    switcher.show_overlay()
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QGridLayout, QFrame, QScrollArea,
                                QInputDialog, QGraphicsDropShadowEffect,
                                QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF, QPointF, Signal
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath,
                            QLinearGradient, QFont, QIcon)

from ui.icons import get_icon
from ui.settings_state import state
from system.workspace import workspace


# ============================================================
#  Плитка одного стола
# ============================================================

class WorkspaceTile(QWidget):
    """Плитка-превью одного рабочего стола."""

    clicked = Signal(int)
    rename_requested = Signal(int)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self._is_active = False
        self._window_count = 0
        self._widget_count = 0
        self._shortcut_count = 0

        self.setFixedSize(280, 180)
        self.setCursor(Qt.PointingHandCursor)

    def update_info(self, is_active: bool, window_count: int,
                    widget_count: int, shortcut_count: int):
        self._is_active = is_active
        self._window_count = window_count
        self._widget_count = widget_count
        self._shortcut_count = shortcut_count
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 2, -2, -2)
        radius = 16

        accent = state().get("accent", "#6EC6FF")

        # Фон плитки
        if self._is_active:
            # Активная — с акцентной рамкой
            bg = QLinearGradient(0, 0, 0, rect.height())
            bg.setColorAt(0, QColor(28, 34, 54, 240))
            bg.setColorAt(1, QColor(22, 28, 44, 240))
            p.setBrush(QBrush(bg))
            p.setPen(QPen(QColor(accent), 3))
        else:
            bg = QLinearGradient(0, 0, 0, rect.height())
            bg.setColorAt(0, QColor(22, 28, 44, 200))
            bg.setColorAt(1, QColor(18, 22, 36, 200))
            p.setBrush(QBrush(bg))
            p.setPen(QPen(QColor(255, 255, 255, 30), 1))

        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        p.drawPath(path)

        # Внутренний "превью" — мини-рабочий стол
        preview_rect = QRectF(rect.left() + 12, rect.top() + 40,
                               rect.width() - 24, rect.height() - 90)
        p.setBrush(QBrush(QColor(10, 14, 26, 200)))
        p.setPen(Qt.NoPen)
        preview_path = QPainterPath()
        preview_path.addRoundedRect(preview_rect, 8, 8)
        p.drawPath(preview_path)

        # Мини-иконки окон внутри превью
        n = self._window_count
        if n > 0:
            icons_per_row = 5
            icon_size = 18
            gap = 6
            total_w = min(n, icons_per_row) * (icon_size + gap) - gap
            start_x = preview_rect.center().x() - total_w / 2
            start_y = preview_rect.center().y() - icon_size / 2

            for i in range(min(n, 10)):
                col = i % icons_per_row
                row = i // icons_per_row
                x = start_x + col * (icon_size + gap)
                y = start_y + row * (icon_size + gap) - (5 if row else 0)

                # Иконка окна
                p.setBrush(QBrush(QColor(accent)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x, y, icon_size, icon_size), 4, 4)

        elif self._widget_count == 0 and self._shortcut_count == 0:
            # Пустой стол — надпись
            p.setPen(QColor(255, 255, 255, 50))
            font = QFont()
            font.setPointSize(10)
            p.setFont(font)
            p.drawText(preview_rect, Qt.AlignCenter, "Пусто")

        # Заголовок стола
        p.setPen(QColor(255, 255, 255, 240))
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        p.setFont(font)
        title_rect = QRectF(rect.left() + 14, rect.top() + 12,
                             rect.width() - 28, 24)
        p.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   workspace().name_for(self.index))

        # Бейдж "активный"
        if self._is_active:
            badge_text = "АКТИВЕН"
            font2 = QFont()
            font2.setPointSize(8)
            font2.setBold(True)
            p.setFont(font2)
            badge_rect = QRectF(rect.right() - 80, rect.top() + 14, 70, 20)

            p.setBrush(QBrush(QColor(accent)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(badge_rect, 10, 10)

            p.setPen(QColor("white"))
            p.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # Статистика снизу
        stats_text = []
        if self._window_count > 0:
            stats_text.append(f"🪟 {self._window_count} окон")
        if self._widget_count > 0:
            stats_text.append(f"📊 {self._widget_count} виджетов")
        if self._shortcut_count > 0:
            stats_text.append(f"🔗 {self._shortcut_count} ярлыков")
        if not stats_text:
            stats_text.append("— пусто —")

        font3 = QFont()
        font3.setPointSize(9)
        p.setFont(font3)
        p.setPen(QColor(255, 255, 255, 140))
        stats_rect = QRectF(rect.left() + 14, rect.bottom() - 36,
                             rect.width() - 28, 24)
        p.drawText(stats_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   "  ·  ".join(stats_text))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.rename_requested.emit(self.index)


# ============================================================
#  Полноэкранный оверлей
# ============================================================

class WorkspaceSwitcher(QWidget):
    """
    Полноэкранный оверлей переключения рабочих столов.
    Показывает сетку превью, позволяет переключаться и переименовывать.
    """

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()

        self._visible = False

        # Layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(60, 60, 60, 60)
        outer.setSpacing(24)
        outer.setAlignment(Qt.AlignCenter)

        # Заголовок
        header = QWidget()
        header.setMaximumWidth(1100)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        title = QLabel("Рабочие столы")
        title.setStyleSheet("""
            color: white;
            font-size: 28px;
            font-weight: 300;
            letter-spacing: 2px;
        """)
        title.setAlignment(Qt.AlignCenter)
        hl.addWidget(title)

        hint = QLabel("Клик — перейти    ·    Двойной клик — переименовать    ·    Esc — закрыть")
        hint.setStyleSheet("""
            color: rgba(255, 255, 255, 0.55);
            font-size: 12px;
            letter-spacing: 0.5px;
        """)
        hint.setAlignment(Qt.AlignCenter)
        hl.addWidget(hint)

        outer.addWidget(header)

        # Контейнер для плиток (создаётся заново при показе)
        self._tiles_holder = QWidget()
        self._tiles_holder.setMaximumWidth(1200)
        self._grid = QGridLayout(self._tiles_holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(20)
        self._grid.setAlignment(Qt.AlignCenter)

        outer.addWidget(self._tiles_holder, 1)

        # Кнопки внизу
        bottom = QWidget()
        bottom.setMaximumWidth(1100)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        bl.setAlignment(Qt.AlignCenter)

        add_btn = QPushButton("＋  Добавить стол")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setFixedHeight(40)
        add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110, 198, 255, 0.20);
                color: white;
                border: 1px solid rgba(110, 198, 255, 0.55);
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: rgba(110, 198, 255, 0.40); }
        """)
        add_btn.clicked.connect(self._add_workspace)
        bl.addWidget(add_btn)

        remove_btn = QPushButton("−  Убрать последний")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setFixedHeight(40)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 107, 138, 0.15);
                color: #FFA0B4;
                border: 1px solid rgba(255, 107, 138, 0.45);
                border-radius: 10px;
                padding: 8px 20px;
                font-size: 13px;
            }
            QPushButton:hover { background: rgba(255, 107, 138, 0.35); color: white; }
        """)
        remove_btn.clicked.connect(self._remove_workspace)
        bl.addWidget(remove_btn)

        outer.addWidget(bottom)

        # Подписка на workspace
        try:
            workspace().switched.connect(lambda _: self._refresh())
            workspace().windows_changed.connect(self._refresh)
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Показ / скрытие
    # ------------------------------------------------------------

    def show_overlay(self):
        if self._visible:
            return
        self.setGeometry(self.host.rect())
        self._refresh()

        self.show()
        self.raise_()
        self.setFocus()

        # Fade-in
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim
        self._visible = True

    def hide_overlay(self):
        if not self._visible:
            return
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim
        self._visible = False

    def _after_hide(self):
        if not self._visible:
            self.hide()

    def toggle(self):
        if self._visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    def resizeEvent(self, e):
        if self._visible:
            self.setGeometry(self.host.rect())
        super().resizeEvent(e)

    # ------------------------------------------------------------
    #  Обновление плиток
    # ------------------------------------------------------------

    def _refresh(self):
        # Очищаем сетку
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)

        try:
            ws = workspace()
            n = ws.count()
            cur = ws.current()
        except Exception:
            n, cur = 4, 0

        # Подбираем колонки: 2 или 3
        if n <= 2:
            cols = n
        elif n <= 6:
            cols = 3
        else:
            cols = 4

        for i in range(n):
            tile = WorkspaceTile(i)
            try:
                w_count = ws.window_count_of(i)
                widget_count = len(ws._desktops[i].get("widget_ids", []))
                shortcut_count = len(ws._desktops[i].get("shortcut_ids", []))
            except Exception:
                w_count = widget_count = shortcut_count = 0

            tile.update_info(
                is_active=(i == cur),
                window_count=w_count,
                widget_count=widget_count,
                shortcut_count=shortcut_count,
            )
            tile.clicked.connect(self._on_tile_click)
            tile.rename_requested.connect(self._on_tile_rename)

            row = i // cols
            col = i % cols
            self._grid.addWidget(tile, row, col)

    # ------------------------------------------------------------
    #  Действия
    # ------------------------------------------------------------

    def _on_tile_click(self, index: int):
        try:
            workspace().switch(index)
        except Exception:
            pass
        self.hide_overlay()

    def _on_tile_rename(self, index: int):
        # Просто диалог (в будущем можно хранить имена)
        name, ok = QInputDialog.getText(
            self, "Переименовать стол",
            "Новое имя:",
            text=workspace().name_for(index))
        if ok and name.strip():
            # Сохраняем в объекте workspace — добавим поддержку имён
            try:
                ws = workspace()
                if not hasattr(ws, "_names"):
                    ws._names = {}
                ws._names[index] = name.strip()
                ws.save()
                self._refresh()
            except Exception:
                pass

    def _add_workspace(self):
        try:
            ws = workspace()
            if ws.count() < 9:
                ws.set_count(ws.count() + 1)
                self._refresh()
        except Exception:
            pass

    def _remove_workspace(self):
        try:
            ws = workspace()
            if ws.count() > 1:
                ws.set_count(ws.count() - 1)
                self._refresh()
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Клавиши
    # ------------------------------------------------------------

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide_overlay()
            e.accept()
            return
        # Стрелки — навигация
        try:
            ws = workspace()
            n = ws.count()
            cur = ws.current()
        except Exception:
            n, cur = 4, 0

        if e.key() == Qt.Key_Right:
            ws.switch((cur + 1) % n)
            self._refresh()
            e.accept()
            return
        if e.key() == Qt.Key_Left:
            ws.switch((cur - 1) % n)
            self._refresh()
            e.accept()
            return
        # Цифры — переход
        if Qt.Key_1 <= e.key() <= Qt.Key_9:
            idx = e.key() - Qt.Key_1
            if idx < n:
                ws.switch(idx)
                self.hide_overlay()
            e.accept()
            return

        super().keyPressEvent(e)

    # ------------------------------------------------------------
    #  Отрисовка подложки
    # ------------------------------------------------------------

    def paintEvent(self, e):
        p = QPainter(self)
        # Тёмная подложка с размытием
        p.fillRect(self.rect(), QColor(8, 12, 22, 230))