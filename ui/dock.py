"""
MountOS — Док (v3).

Стиль: iOS 26 / Liquid Glass.
  • Magnify при наведении
  • Большие скругления, блики
  • Одна страница: максимум 7 иконок + 1 виджет (2 иконки ширины)
  • «Остров» — почти прозрачный контейнер вокруг иконок
  • Виджет — фон как у иконки, только шире
  • Правый клик — кастомизация (галочки, порядок, выбор виджета)
  • Drag & drop — перетаскивание иконок мышью для смены порядка
  • Бейджи — кружок с числом в углу иконки
  • Виджеты: Часы, Погода, Батарея, CPU/RAM, Календарь

Сигналы (для desktop.py):
  app_launch_requested(str)
  app_install_requested()
  app_delete_requested(str)
  height_changed(int)
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                                QLabel, QDialog, QComboBox,
                                QListWidget, QListWidgetItem, QDialogButtonBox,
                                QMessageBox)
from PySide6.QtCore import (Qt, QSize, Signal, QTimer, QTime, QDate,
                             QPropertyAnimation, QEasingCurve, QPoint, QRect)
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QPainterPath,
                            QBrush, QPen, QLinearGradient, QFont)

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ============================================================
#  Константы
# ============================================================

MAX_ICONS = 7
ICON_SIZE = 52
WIDGET_WIDTH = ICON_SIZE * 2 + 10
MIN_HEIGHT = 88
MAX_HEIGHT = 140
DEFAULT_HEIGHT = 96
DRAG_THRESHOLD = 12


# ============================================================
#  Иконка приложения
# ============================================================

class DockIcon(QPushButton):
    """Иконка приложения в доке. С поддержкой drag & drop и бейджей."""

    delete_requested = Signal(str)
    drag_started = Signal(str)             # app_id
    drag_moved = Signal(str, QPoint)       # app_id, global pos
    drag_finished = Signal(str, QPoint)    # app_id, global pos

    def __init__(self, app_id, icon_name, name, builtin=True,
                 custom_pixmap=None, parent=None):
        super().__init__("", parent)
        self.app_id = app_id
        self.icon_name = icon_name
        self.builtin = builtin
        self.base_size = ICON_SIZE
        self.setFixedSize(self.base_size, self.base_size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)

        self._active = False
        self._badge_count = 0
        self._custom_pixmap = custom_pixmap
        self._refresh_icon()
        self._apply_style()

        state().changed.connect(self._on_state)

        # Drag state
        self._press_pos = None
        self._dragging = False

    def _on_state(self, key, val):
        if key == "accent":
            self._refresh_icon()
            self._apply_style()

    def _refresh_icon(self):
        if self._custom_pixmap is not None:
            self.setIcon(QIcon(self._custom_pixmap))
        else:
            color = "#FFFFFF" if not self._active else state().get("accent")
            pm = get_icon(self.icon_name, 32, color)
            self.setIcon(QIcon(pm))
        self.setIconSize(QSize(int(self.base_size * 0.58),
                                int(self.base_size * 0.58)))

    def set_active(self, active: bool):
        self._active = active
        self._refresh_icon()
        self._apply_style()

    def set_badge(self, count: int):
        """Установить бейдж. count=0 — убрать."""
        self._badge_count = max(0, int(count))
        self.update()

    def badge_count(self) -> int:
        return self._badge_count

    def _apply_style(self):
        accent = state().get("accent")
        if self._active:
            bg = f"rgba({self._hex_to_rgb(accent)}, 0.28)"
            border = f"rgba({self._hex_to_rgb(accent)}, 0.70)"
        else:
            bg = "rgba(255, 255, 255, 0.10)"
            border = "rgba(255, 255, 255, 0.14)"

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.24);
                border: 1px solid rgba(255, 255, 255, 0.40);
            }}
            QPushButton:pressed {{
                background: rgba({self._hex_to_rgb(accent)}, 0.50);
            }}
        """)

    @staticmethod
    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"

    # ---------- Magnify (только если не dragging) ----------
    def enterEvent(self, e):
        if not self._dragging:
            self._animate(self.base_size + 14)
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._dragging:
            self._animate(self.base_size)
        super().leaveEvent(e)

    def _animate(self, target):
        anim = QPropertyAnimation(self, b"size")
        anim.setDuration(160)
        anim.setStartValue(self.size())
        anim.setEndValue(QSize(target, target))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._anim = anim

    # ---------- Drag & drop ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._dragging = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_pos is None:
            return
        cur = e.globalPosition().toPoint()
        if not self._dragging:
            if (cur - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
                return
            # Начинаем drag
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            # Визуальный отклик — приподнимаем
            self._animate(int(self.base_size * 1.15))
            self.drag_started.emit(self.app_id)
        # Сообщаем о движении
        self.drag_moved.emit(self.app_id, cur)
        e.accept()

    def mouseReleaseEvent(self, e):
        was_dragging = self._dragging
        self._dragging = False
        self._press_pos = None
        self.setCursor(Qt.PointingHandCursor)
        if was_dragging:
            self._animate(self.base_size)
            self.drag_finished.emit(self.app_id, e.globalPosition().toPoint())
            e.accept()
            return
        super().mouseReleaseEvent(e)

    # ---------- Бейдж ----------
    def paintEvent(self, event):
        super().paintEvent(event)
        if self._badge_count <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        text = "99+" if self._badge_count > 99 else str(self._badge_count)

        # Размер бейджа
        badge_size = 20 if len(text) <= 2 else 26
        margin = 2

        # Правый верхний угол
        bx = self.width() - badge_size - margin
        by = margin

        # Фон бейджа
        p.setBrush(QBrush(QColor("#FF3B30")))
        p.setPen(QPen(QColor(255, 255, 255, 180), 1.5))
        p.drawEllipse(bx, by, badge_size, badge_size)

        # Текст
        p.setPen(QColor("white"))
        f = QFont("Segoe UI", 8)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRect(bx, by, badge_size, badge_size),
                   Qt.AlignCenter, text)
        p.end()

    # ---------- Контекстное меню ----------
    def contextMenuEvent(self, e):
        menu = make_menu(self)
        a_open = menu.addAction("Открыть")
        a_open.triggered.connect(self.click)
        menu.addSeparator()
        a_pin = menu.addAction("📌  Убрать из дока")
        a_pin.triggered.connect(lambda: self.delete_requested.emit(self.app_id))
        menu.exec(e.globalPos())


# ============================================================
#  Виджеты для дока
# ============================================================

class DockWidget(QWidget):
    """Базовый виджет в доке (ширина = 2 иконки)."""

    widget_id = "none"
    label = "Нет"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(WIDGET_WIDTH, ICON_SIZE)
        self.setStyleSheet("""
            DockWidget {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 18px;
            }
        """)

    def refresh(self):
        pass


class ClockWidget(DockWidget):
    widget_id = "clock"
    label = "Часы"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)

        self.time_lbl = QLabel("--:--")
        self.time_lbl.setAlignment(Qt.AlignCenter)
        self.time_lbl.setStyleSheet(
            "color: white; font-size: 18px; font-weight: 600; "
            "background: transparent; border: none;")

        self.date_lbl = QLabel("—")
        self.date_lbl.setAlignment(Qt.AlignCenter)
        self.date_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 10px; "
            "background: transparent; border: none;")

        lay.addWidget(self.time_lbl)
        lay.addWidget(self.date_lbl)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)
        self.refresh()

    def refresh(self):
        now = QTime.currentTime()
        self.time_lbl.setText(now.toString("HH:mm"))
        d = QDate.currentDate()
        months = ["янв", "фев", "мар", "апр", "мая", "июн",
                  "июл", "авг", "сен", "окт", "ноя", "дек"]
        self.date_lbl.setText(f"{d.day()} {months[d.month() - 1]}")


class BatteryWidget(DockWidget):
    widget_id = "battery"
    label = "Батарея"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)

        self.pct = QLabel("—%")
        self.pct.setAlignment(Qt.AlignCenter)
        self.pct.setStyleSheet(
            "color: white; font-size: 18px; font-weight: 600; "
            "background: transparent; border: none;")

        self.status = QLabel("—")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 10px; "
            "background: transparent; border: none;")

        lay.addWidget(self.pct)
        lay.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5000)
        self.refresh()

    def refresh(self):
        if not HAS_PSUTIL:
            self.pct.setText("—")
            self.status.setText("нет psutil")
            return
        try:
            bat = psutil.sensors_battery()
            if bat is None:
                self.pct.setText("—")
                self.status.setText("нет батареи")
                return
            self.pct.setText(f"{bat.percent:.0f}%")
            self.status.setText("⚡ зарядка" if bat.power_plugged else "разряд")
        except Exception:
            self.pct.setText("—")
            self.status.setText("ошибка")


class CpuRamWidget(DockWidget):
    widget_id = "cpuram"
    label = "CPU / RAM"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)

        self.cpu = QLabel("CPU —")
        self.cpu.setAlignment(Qt.AlignCenter)
        self.cpu.setStyleSheet(
            "color: #6EC6FF; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;")

        self.ram = QLabel("RAM —")
        self.ram.setAlignment(Qt.AlignCenter)
        self.ram.setStyleSheet(
            "color: #B388FF; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;")

        lay.addWidget(self.cpu)
        lay.addWidget(self.ram)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(2000)
        self.refresh()

    def refresh(self):
        if not HAS_PSUTIL:
            self.cpu.setText("нет psutil")
            self.ram.setText("")
            return
        try:
            c = psutil.cpu_percent(interval=None)
            r = psutil.virtual_memory().percent
            self.cpu.setText(f"CPU {c:.0f}%")
            self.ram.setText(f"RAM {r:.0f}%")
        except Exception:
            pass


class WeatherWidget(DockWidget):
    widget_id = "weather"
    label = "Погода"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)

        self.temp = QLabel("—°C")
        self.temp.setAlignment(Qt.AlignCenter)
        self.temp.setStyleSheet(
            "color: white; font-size: 18px; font-weight: 600; "
            "background: transparent; border: none;")

        self.city = QLabel("погода")
        self.city.setAlignment(Qt.AlignCenter)
        self.city.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 10px; "
            "background: transparent; border: none;")

        lay.addWidget(self.temp)
        lay.addWidget(self.city)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(600000)
        self.refresh()

    def refresh(self):
        if not HAS_REQUESTS:
            self.temp.setText("—°C")
            self.city.setText("нет requests")
            return
        lat = state().get("hub_city_lat")
        lon = state().get("hub_city_lon")
        if lat is None or lon is None:
            self.temp.setText("—°C")
            self.city.setText("нет города")
            return
        try:
            url = ("https://api.open-meteo.com/v1/forecast"
                   f"?latitude={lat}&longitude={lon}&current=temperature_2m")
            r = requests.get(url, timeout=6)
            r.raise_for_status()
            t = r.json().get("current", {}).get("temperature_2m", "—")
            self.temp.setText(f"{t}°C")
            name = state().get("hub_city", "город")
            self.city.setText(name.split(",")[0][:16])
        except Exception:
            self.temp.setText("—°C")
            self.city.setText("ошибка")


class CalendarWidget(DockWidget):
    widget_id = "calendar"
    label = "Календарь"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)

        self.day = QLabel("—")
        self.day.setAlignment(Qt.AlignCenter)
        self.day.setStyleSheet(
            "color: white; font-size: 22px; font-weight: 700; "
            "background: transparent; border: none;")

        self.weekday = QLabel("—")
        self.weekday.setAlignment(Qt.AlignCenter)
        self.weekday.setStyleSheet(
            "color: rgba(255,255,255,0.65); font-size: 10px; "
            "background: transparent; border: none;")

        lay.addWidget(self.day)
        lay.addWidget(self.weekday)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(60000)
        self.refresh()

    def refresh(self):
        d = QDate.currentDate()
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        self.day.setText(str(d.day()))
        self.weekday.setText(days[d.dayOfWeek() - 1])


WIDGETS = {
    "none":     ("Нет",       None),
    "clock":    ("Часы",      ClockWidget),
    "battery":  ("Батарея",   BatteryWidget),
    "cpuram":   ("CPU / RAM", CpuRamWidget),
    "weather":  ("Погода",    WeatherWidget),
    "calendar": ("Календарь", CalendarWidget),
}


# ============================================================
#  Диалог настройки дока
# ============================================================

class DockSettingsDialog(QDialog):
    """Кастомизация дока: приложения + порядок + виджет."""

    def __init__(self, all_apps: dict, selected_ids: list,
                 current_widget: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройка дока")
        self.resize(520, 620)
        self.setStyleSheet("""
            QDialog { background: #1A1F35; }
            QLabel { color: rgba(255,255,255,0.9); }
            QComboBox {
                background: rgba(255,255,255,0.08);
                color: white;
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                padding: 6px 10px;
            }
            QListWidget {
                background: rgba(0,0,0,0.18);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 10px;
                color: white;
                padding: 6px;
                outline: none;
            }
            QListWidget::item { padding: 6px 10px; border-radius: 6px; }
            QListWidget::item:selected { background: rgba(110,198,255,0.30); }
        """)

        self._all_apps = all_apps
        self._selected = list(selected_ids)
        self._result_selected = list(selected_ids)
        self._result_widget = current_widget

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        hint = QLabel(f"Максимум {MAX_ICONS} приложений в доке.\n"
                      "Порядок меняется стрелками ↑ ↓ или перетаскиванием.")
        hint.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 12px;")
        lay.addWidget(hint)

        wl = QHBoxLayout()
        wl.addWidget(QLabel("Виджет в конце дока:"))
        self.widget_combo = QComboBox()
        for wid, (label, _) in WIDGETS.items():
            self.widget_combo.addItem(label, wid)
        idx = self.widget_combo.findData(current_widget)
        if idx >= 0:
            self.widget_combo.setCurrentIndex(idx)
        wl.addWidget(self.widget_combo, 1)
        lay.addLayout(wl)

        lay.addWidget(QLabel("В доке (порядок):"))
        self.selected_list = QListWidget()
        lay.addWidget(self.selected_list, 1)

        arrows = QHBoxLayout()
        up_btn = QPushButton("↑ Вверх")
        dn_btn = QPushButton("↓ Вниз")
        rm_btn = QPushButton("✕ Убрать")
        for b in (up_btn, dn_btn, rm_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.08);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.15);
                    border-radius: 8px;
                    padding: 6px 12px;
                }
                QPushButton:hover { background: rgba(255,255,255,0.18); }
            """)
        arrows.addWidget(up_btn)
        arrows.addWidget(dn_btn)
        arrows.addStretch(1)
        arrows.addWidget(rm_btn)
        lay.addLayout(arrows)

        def move_up():
            i = self.selected_list.currentRow()
            if i > 0:
                self._selected[i - 1], self._selected[i] = \
                    self._selected[i], self._selected[i - 1]
                self._rebuild_selected(i - 1)

        def move_down():
            i = self.selected_list.currentRow()
            if 0 <= i < len(self._selected) - 1:
                self._selected[i + 1], self._selected[i] = \
                    self._selected[i], self._selected[i + 1]
                self._rebuild_selected(i + 1)

        def remove_sel():
            i = self.selected_list.currentRow()
            if 0 <= i < len(self._selected):
                self._selected.pop(i)
                self._rebuild_selected(min(i, len(self._selected) - 1))

        up_btn.clicked.connect(move_up)
        dn_btn.clicked.connect(move_down)
        rm_btn.clicked.connect(remove_sel)

        lay.addWidget(QLabel("Добавить приложение:"))
        self.available_combo = QComboBox()
        lay.addWidget(self.available_combo)

        add_btn = QPushButton("＋ Добавить")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.18);
                color: white;
                border: 1px solid rgba(110,198,255,0.55);
                border-radius: 8px;
                padding: 8px 14px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.35); }
        """)
        add_btn.clicked.connect(self._add_current)
        lay.addWidget(add_btn)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._on_ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self._rebuild_selected(0)
        self._rebuild_available()

    def _rebuild_selected(self, select_row=0):
        self.selected_list.clear()
        for app_id in self._selected:
            info = self._all_apps.get(app_id)
            name = info.name if info else app_id
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, app_id)
            self.selected_list.addItem(item)
        if 0 <= select_row < self.selected_list.count():
            self.selected_list.setCurrentRow(select_row)

    def _rebuild_available(self):
        self.available_combo.clear()
        for app_id, info in self._all_apps.items():
            if app_id in self._selected:
                continue
            self.available_combo.addItem(info.name, app_id)

    def _add_current(self):
        if len(self._selected) >= MAX_ICONS:
            QMessageBox.information(self, "Лимит",
                f"В доке может быть не больше {MAX_ICONS} приложений.")
            return
        app_id = self.available_combo.currentData()
        if not app_id:
            return
        self._selected.append(app_id)
        self._rebuild_selected(len(self._selected) - 1)
        self._rebuild_available()

    def _on_ok(self):
        self._result_selected = list(self._selected)
        self._result_widget = self.widget_combo.currentData()
        self.accept()

    def result_selected(self):
        return self._result_selected

    def result_widget(self):
        return self._result_widget


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
        self.setFixedHeight(DEFAULT_HEIGHT)

        self._all_apps = {}
        self._icons = {}
        self._widget = None
        self._dock_height = DEFAULT_HEIGHT

        self._resizing = False
        self._resize_start_y = 0
        self._resize_start_h = 0

        # Состояние drag
        self._dragging_app = None

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 8, 16, 8)
        self._root.setSpacing(2)

        # Хват для resize
        self._grip = QWidget()
        self._grip.setFixedHeight(5)
        self._grip.setCursor(Qt.SizeVerCursor)
        self._grip.setStyleSheet("""
            QWidget {
                background: rgba(255,255,255,0.10);
                border-radius: 2px;
                margin: 0 45%;
            }
            QWidget:hover { background: rgba(110,198,255,0.50); }
        """)
        self._root.addWidget(self._grip, 0, Qt.AlignHCenter)

        # «Остров»
        self._island = QWidget()
        self._island.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 24px;
            }
        """)
        island_layout = QHBoxLayout(self._island)
        island_layout.setContentsMargins(10, 6, 10, 6)
        island_layout.setSpacing(10)
        island_layout.setAlignment(Qt.AlignCenter)

        self._row = island_layout
        self._root.addWidget(self._island, 1, Qt.AlignHCenter)

        self.setStyleSheet("""
            Dock {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 28px;
            }
        """)

        self._load_settings()

    # ------------------------------------------------------------
    #  Настройки
    # ------------------------------------------------------------

    def _load_settings(self):
        saved = state().get("dock_apps", None)
        if saved is None:
            self._selected_ids = []
        else:
            self._selected_ids = list(saved)

        self._widget_id = state().get("dock_widget", "clock")
        if self._widget_id not in WIDGETS:
            self._widget_id = "none"

    def _save_settings(self):
        state().set("dock_apps", list(self._selected_ids))
        state().set("dock_widget", self._widget_id)

    # ------------------------------------------------------------
    #  Resize
    # ------------------------------------------------------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < 14:
            self._resizing = True
            self._resize_start_y = e.globalPosition().toPoint().y()
            self._resize_start_h = self.height()
            self.setCursor(Qt.SizeVerCursor)
            e.accept()

    def mouseMoveEvent(self, e):
        if self._resizing:
            dy = self._resize_start_y - e.globalPosition().toPoint().y()
            new_h = max(MIN_HEIGHT, min(MAX_HEIGHT, self._resize_start_h + dy))
            self.setFixedHeight(new_h)
            self._dock_height = new_h
            self.height_changed.emit(new_h)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._resizing:
            self._resizing = False
            self.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------
    #  populate / rebuild
    # ------------------------------------------------------------

    def populate(self, apps: dict):
        self._all_apps = dict(apps)

        if not self._selected_ids:
            self._selected_ids = list(apps.keys())[:MAX_ICONS]
            self._save_settings()

        self._selected_ids = [a for a in self._selected_ids if a in apps]
        self._rebuild()

    def _rebuild(self):
        for i in reversed(range(self._row.count())):
            it = self._row.itemAt(i)
            if it and it.widget():
                it.widget().setParent(None)
        self._icons.clear()

        for app_id in self._selected_ids[:MAX_ICONS]:
            info = self._all_apps.get(app_id)
            if info is None:
                continue
            icon = DockIcon(app_id, info.app_id, info.name,
                            builtin=info.builtin)
            icon.clicked.connect(
                lambda _, a=app_id: self.app_launch_requested.emit(a))
            icon.delete_requested.connect(self._on_delete_requested)
            # Drag & drop
            icon.drag_started.connect(self._on_drag_started)
            icon.drag_moved.connect(self._on_drag_moved)
            icon.drag_finished.connect(self._on_drag_finished)
            self._icons[app_id] = icon
            self._row.addWidget(icon)

        # Кнопка «＋»
        if len(self._selected_ids) < MAX_ICONS:
            add = QPushButton("＋")
            add.setToolTip("Установить приложение (.py)")
            add.setFixedSize(ICON_SIZE, ICON_SIZE)
            add.setCursor(Qt.PointingHandCursor)
            accent = state().get("accent")
            add.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({DockIcon._hex_to_rgb(accent)}, 0.15);
                    border: 1px dashed rgba({DockIcon._hex_to_rgb(accent)}, 0.60);
                    border-radius: 18px;
                    color: {accent};
                    font-size: 22px;
                }}
                QPushButton:hover {{
                    background: rgba({DockIcon._hex_to_rgb(accent)}, 0.35);
                    border: 1px solid {accent};
                }}
            """)
            add.clicked.connect(self.app_install_requested.emit)
            self._row.addWidget(add)

        # Виджет
        if self._widget_id != "none":
            _, cls = WIDGETS[self._widget_id]
            if cls is not None:
                self._widget = cls()
                self._row.addWidget(self._widget)

    # ------------------------------------------------------------
    #  Drag & drop
    # ------------------------------------------------------------

    def _on_drag_started(self, app_id):
        self._dragging_app = app_id

    def _on_drag_moved(self, app_id, global_pos):
        """Определяем, над какой позицией курсор, и переставляем."""
        if self._dragging_app != app_id:
            return
        icon = self._icons.get(app_id)
        if icon is None:
            return

        # Локальная позиция курсора в доке
        local = self.mapFromGlobal(global_pos)

        # Определяем, перед какой иконкой вставить
        widgets = []
        for i in range(self._row.count()):
            it = self._row.itemAt(i)
            w = it.widget() if it else None
            if w is None:
                continue
            if isinstance(w, DockIcon):
                widgets.append(w)

        target_index = None
        for i, w in enumerate(widgets):
            if w is icon:
                continue
            center_x = w.x() + w.width() / 2
            if local.x() < center_x:
                target_index = self._row.indexOf(w)
                break

        if target_index is None:
            # В конец (перед кнопкой + или виджетом)
            for i in range(self._row.count()):
                it = self._row.itemAt(i)
                w = it.widget() if it else None
                if w is not None and not isinstance(w, DockIcon):
                    target_index = i
                    break
            if target_index is None:
                target_index = self._row.count()

        current_index = self._row.indexOf(icon)
        if current_index == -1 or current_index == target_index:
            return

        # Переставляем в layout
        self._row.removeWidget(icon)
        if target_index > current_index:
            target_index -= 1
        self._row.insertWidget(target_index, icon)

    def _on_drag_finished(self, app_id, global_pos):
        """Отпустили — сохраняем порядок."""
        self._dragging_app = None

        # Собираем новый порядок из layout
        new_order = []
        for i in range(self._row.count()):
            it = self._row.itemAt(i)
            w = it.widget() if it else None
            if isinstance(w, DockIcon):
                new_order.append(w.app_id)

        if new_order and new_order != self._selected_ids:
            self._selected_ids = new_order
            self._save_settings()

    # ------------------------------------------------------------
    #  Удаление
    # ------------------------------------------------------------

    def _on_delete_requested(self, app_id):
        info = self._all_apps.get(app_id)
        if info is not None and info.builtin:
            if app_id in self._selected_ids:
                self._selected_ids.remove(app_id)
            self._save_settings()
            self._rebuild()
        else:
            self.app_delete_requested.emit(app_id)
            if app_id in self._selected_ids:
                self._selected_ids.remove(app_id)
            self._save_settings()

    # ------------------------------------------------------------
    #  Кастомизация
    # ------------------------------------------------------------

    def contextMenuEvent(self, e):
        menu = make_menu(self)
        a_cfg = menu.addAction("⚙  Настроить док")
        a_cfg.triggered.connect(self.open_settings)
        menu.addSeparator()
        a_install = menu.addAction("＋  Установить приложение")
        a_install.triggered.connect(self.app_install_requested.emit)
        menu.exec(e.globalPos())

    def open_settings(self):
        dlg = DockSettingsDialog(
            self._all_apps, self._selected_ids, self._widget_id, self)
        if dlg.exec() == QDialog.Accepted:
            self._selected_ids = dlg.result_selected()
            self._widget_id = dlg.result_widget()
            self._save_settings()
            self._rebuild()

    # ------------------------------------------------------------
    #  Активные приложения и бейджи
    # ------------------------------------------------------------

    def mark_active(self, app_id, active: bool):
        ic = self._icons.get(app_id)
        if ic:
            ic.set_active(active)

    def set_badge(self, app_id: str, count: int):
        """Установить бейдж на иконке приложения. count=0 — убрать.

        Пример использования из приложения:
            desktop = _get_desktop(self)
            if desktop and hasattr(desktop, "dock"):
                desktop.dock.set_badge("notes", 3)
        """
        ic = self._icons.get(app_id)
        if ic:
            ic.set_badge(count)