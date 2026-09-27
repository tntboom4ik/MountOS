"""
MountOS — Графики функций.

Построение графиков математических функций:
  • Ввод формул: sin(x), x**2, exp(-x), ln(x) и т.д.
  • Несколько функций одновременно (разные цвета)
  • Зум колёсиком мыши
  • Панорамирование зажатой ЛКМ
  • Сетка и оси с подписями
  • Автомасштаб под функции
  • Сохранение графиков в PNG (в VFS)
  • Предустановки: sin, cos, парабола, гипербола, гауссиана
  • Безопасное вычисление формул (только математика)

Парсер формул: безопасный eval с ограниченным пространством имён
(только math-функции, константы, x).

Установка: apps/plotter.py + перезапуск MountOS.
"""

import json
import math
import os
import time

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QScrollArea, QFrame,
                                QMessageBox, QInputDialog, QSizePolicy,
                                QComboBox, QSlider, QFileDialog)
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QBuffer, QByteArray
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFont,
                            QPainterPath, QLinearGradient, QPixmap, QIcon)

from ui.icons import get_icon
from ui.settings_state import state
from ui.context_menu import make_menu

APP_NAME = "Графики"
APP_ICON = "calculator"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


OUT_DIR = "/Pictures/Plotter"

# Цвета для линий графиков
COLORS = [
    "#6EC6FF",   # голубой
    "#FF6B8A",   # розовый
    "#6EE7B7",   # зелёный
    "#FFB86C",   # оранжевый
    "#B388FF",   # фиолетовый
    "#FBBF24",   # жёлтый
    "#5EEAD4",   # бирюза
    "#F472B6",   # малиновый
]


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
#  Безопасный вычислитель формул
# ============================================================

# Пространство имён — только математика
MATH_NAMESPACE = {
    # Базовые
    "abs": abs, "min": min, "max": max, "round": round, "pow": pow,

    # Math-функции
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "exp": math.exp, "log": math.log, "log10": math.log10, "log2": math.log2,
    "sqrt": math.sqrt, "cbrt": lambda x: x ** (1/3) if x >= 0 else -((-x) ** (1/3)),
    "floor": math.floor, "ceil": math.ceil,
    "factorial": math.factorial,
    "fabs": math.fabs, "copysign": math.copysign,
    "degrees": math.degrees, "radians": math.radians,
    "hypot": math.hypot,
    "sign": lambda x: (x > 0) - (x < 0),

    # Константы
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "nan": math.nan,
}


def safe_eval(expr: str, x: float) -> float:
    """
    Безопасно вычисляет выражение с переменной x.
    Доступны только math-функции и константы.
    """
    # Нормализуем выражение
    expr = expr.strip()
    if not expr:
        raise ValueError("Пустое выражение")

    # Заменяем ^ на ** (привычно для математиков)
    expr = expr.replace("^", "**")

    # Заменяем Implicit умножение: 2x → 2*x, x sin(x) → x*sin(x), 2(3) → 2*(3)
    import re
    # цифра или x перед буквой/скобкой
    expr = re.sub(r"(\d|x|\))\s*([a-zA-Z(])", r"\1*\2", expr)

    try:
        result = eval(expr, {"__builtins__": {}}, {**MATH_NAMESPACE, "x": x})
    except ZeroDivisionError:
        return float("nan")
    except (ValueError, OverflowError):
        return float("nan")
    except Exception as e:
        raise ValueError(f"Ошибка в формуле: {e}")

    if isinstance(result, complex):
        # Если получилось комплексное — берём действительную часть
        return result.real if result.imag == 0 else float("nan")
    try:
        return float(result)
    except (TypeError, ValueError):
        raise ValueError("Результат не число")


# ============================================================
#  Графический холст
# ============================================================

class PlotCanvas(QWidget):
    """Холст для отрисовки графиков."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        # Функции — список dict {"expr", "color", "name", "enabled"}
        self.functions = []

        # Область видимости (world coordinates)
        self.x_min = -10.0
        self.x_max = 10.0
        self.y_min = -10.0
        self.y_max = 10.0
        self.auto_scale = True

        # Панорамирование
        self._panning = False
        self._pan_start = QPointF()
        self._pan_x_range = (self.x_min, self.x_max)
        self._pan_y_range = (self.y_min, self.y_max)

    # ------------------------------------------------------------
    #  Публичное API
    # ------------------------------------------------------------

    def set_functions(self, funcs: list):
        """Устанавливает список функций."""
        self.functions = funcs
        if self.auto_scale:
            self.fit_all()
        self.update()

    def fit_all(self):
        """Автомасштаб под все функции."""
        if not self.functions:
            self.x_min, self.x_max = -10.0, 10.0
            self.y_min, self.y_max = -10.0, 10.0
            self.update()
            return

        # Пробегаем x от -20 до 20, считаем y, ищем границы
        y_vals = []
        x_start = -20.0
        x_end = 20.0
        steps = 400
        dx = (x_end - x_start) / steps
        for f in self.functions:
            if not f.get("enabled", True):
                continue
            for i in range(steps + 1):
                x = x_start + i * dx
                try:
                    y = safe_eval(f["expr"], x)
                    if math.isfinite(y):
                        y_vals.append(y)
                except Exception:
                    pass

        if y_vals:
            # Ограничиваем слишком большие значения
            y_min = max(min(y_vals), -100)
            y_max = min(max(y_vals), 100)
            span = y_max - y_min
            if span < 0.5:
                span = 0.5
            padding = span * 0.15
            self.y_min = y_min - padding
            self.y_max = y_max + padding

        self.x_min = -10.0
        self.x_max = 10.0

        # Соотношение сторон
        w = max(1, self.width())
        h = max(1, self.height())
        x_span = self.x_max - self.x_min
        y_span = self.y_max - self.y_min
        aspect = (x_span / y_span) / (w / h)
        if aspect > 1.05 or aspect < 0.95:
            # Подгоняем по Y
            self.y_span_needed = x_span * h / w
            cy = (self.y_min + self.y_max) / 2
            self.y_min = cy - self.y_span_needed / 2
            self.y_max = cy + self.y_span_needed / 2

        self.update()

    def set_zoom(self, factor: float, center: QPointF = None):
        """Зум относительно центра (или середины)."""
        if center is None:
            cx = (self.x_min + self.x_max) / 2
            cy = (self.y_min + self.y_max) / 2
        else:
            cx, cy = self.pixel_to_world(center)

        self.x_min = cx + (self.x_min - cx) * factor
        self.x_max = cx + (self.x_max - cx) * factor
        self.y_min = cy + (self.y_min - cy) * factor
        self.y_max = cy + (self.y_max - cy) * factor
        self.update()

    def reset_zoom(self):
        """Сброс зума и панорамирования."""
        self.auto_scale = True
        self.fit_all()

    # ------------------------------------------------------------
    #  Преобразования
    # ------------------------------------------------------------

    def world_to_pixel(self, x: float, y: float) -> QPointF:
        """Мировые координаты → пиксели."""
        w = self.width()
        h = self.height()
        px = (x - self.x_min) / (self.x_max - self.x_min) * w
        py = h - (y - self.y_min) / (self.y_max - self.y_min) * h
        return QPointF(px, py)

    def pixel_to_world(self, point: QPointF) -> tuple:
        """Пиксели → мировые координаты."""
        w = max(1, self.width())
        h = max(1, self.height())
        x = self.x_min + (point.x() / w) * (self.x_max - self.x_min)
        y = self.y_min + ((h - point.y()) / h) * (self.y_max - self.y_min)
        return (x, y)

    # ------------------------------------------------------------
    #  Мышь
    # ------------------------------------------------------------

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta == 0:
            return
        factor = 0.85 if delta > 0 else 1.0 / 0.85
        self.auto_scale = False
        self.set_zoom(factor, e.position())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._panning = True
            self._pan_start = e.position()
            self._pan_x_range = (self.x_min, self.x_max)
            self._pan_y_range = (self.y_min, self.y_max)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._panning:
            dx_px = e.position().x() - self._pan_start.x()
            dy_px = e.position().y() - self._pan_start.y()
            w = max(1, self.width())
            h = max(1, self.height())

            x_span = self._pan_x_range[1] - self._pan_x_range[0]
            y_span = self._pan_y_range[1] - self._pan_y_range[0]

            dx_world = -dx_px / w * x_span
            dy_world = dy_px / h * y_span

            self.x_min = self._pan_x_range[0] + dx_world
            self.x_max = self._pan_x_range[1] + dx_world
            self.y_min = self._pan_y_range[0] + dy_world
            self.y_max = self._pan_y_range[1] + dy_world
            self.auto_scale = False
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._panning = False
            self.setCursor(Qt.CrossCursor)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.reset_zoom()

    # ------------------------------------------------------------
    #  Отрисовка
    # ------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Фон
        p.fillRect(self.rect(), QColor("#0A0E1A"))

        # Сетка
        self._draw_grid(p)

        # Оси
        self._draw_axes(p)

        # Функции
        for f in self.functions:
            if not f.get("enabled", True):
                continue
            self._draw_function(p, f)

        # Подписи углов
        self._draw_info(p)

    def _draw_grid(self, p: QPainter):
        """Рисует сетку с адаптивным шагом."""
        w = self.width()
        h = self.height()

        # Шаг сетки
        x_range = self.x_max - self.x_min
        y_range = self.y_max - self.y_min

        # Ищем "красивый" шаг: 1, 2, 5, 10, 20, ...
        def nice_step(span, target_lines=10):
            raw = span / target_lines
            mag = 10 ** math.floor(math.log10(raw))
            for m in (1, 2, 5, 10):
                if raw <= m * mag:
                    return m * mag
            return 10 * mag

        x_step = nice_step(x_range, 10)
        y_step = nice_step(y_range, 8)

        # Вертикальные линии
        p.setPen(QPen(QColor(255, 255, 255, 15), 1))
        x0 = math.floor(self.x_min / x_step) * x_step
        x = x0
        while x <= self.x_max:
            px = (x - self.x_min) / x_range * w
            p.drawLine(int(px), 0, int(px), h)
            x += x_step

        # Горизонтальные
        y0 = math.floor(self.y_min / y_step) * y_step
        y = y0
        while y <= self.y_max:
            py = h - (y - self.y_min) / y_range * h
            p.drawLine(0, int(py), w, int(py))
            y += y_step

        # Более толстые — на 0
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))

    def _draw_axes(self, p: QPainter):
        """Оси X и Y с подписями."""
        w = self.width()
        h = self.height()

        # Точка (0, 0) на экране
        origin = self.world_to_pixel(0, 0)

        # Ось X
        p.setPen(QPen(QColor(255, 255, 255, 80), 1.5))
        if 0 <= origin.y() <= h:
            p.drawLine(0, int(origin.y()), w, int(origin.y()))
        # Ось Y
        if 0 <= origin.x() <= w:
            p.drawLine(int(origin.x()), 0, int(origin.x()), h)

        # Подписи
        p.setPen(QColor(255, 255, 255, 100))
        font = QFont()
        font.setPointSize(8)
        p.setFont(font)

        x_range = self.x_max - self.x_min
        y_range = self.y_max - self.y_min

        def nice_step(span, target_lines=10):
            raw = span / target_lines
            mag = 10 ** math.floor(math.log10(abs(raw))) if raw else 1
            for m in (1, 2, 5, 10):
                if raw <= m * mag:
                    return m * mag
            return 10 * mag

        x_step = nice_step(x_range, 10)
        y_step = nice_step(y_range, 8)

        # Подписи по X
        x0 = math.floor(self.x_min / x_step) * x_step
        x = x0
        while x <= self.x_max:
            if abs(x) > 0.0001:
                px = (x - self.x_min) / x_range * w
                # Не рисуем близко к оси Y
                if abs(px - origin.x()) > 15:
                    p.drawText(QRectF(px - 20, origin.y() + 4, 40, 16),
                               Qt.AlignCenter, self._fmt_num(x))
            x += x_step

        # Подписи по Y
        y0 = math.floor(self.y_min / y_step) * y_step
        y = y0
        while y <= self.y_max:
            if abs(y) > 0.0001:
                py = h - (y - self.y_min) / y_range * h
                if abs(py - origin.y()) > 12:
                    p.drawText(QRectF(origin.x() - 44, py - 8, 40, 16),
                               Qt.AlignRight | Qt.AlignVCenter,
                               self._fmt_num(y))
            y += y_step

        # 0 — на пересечении
        if 0 <= origin.x() <= w and 0 <= origin.y() <= h:
            p.drawText(QRectF(origin.x() - 20, origin.y() + 4, 40, 16),
                       Qt.AlignCenter, "0")

    def _fmt_num(self, v: float) -> str:
        """Красиво форматирует число."""
        if abs(v) >= 10000 or (abs(v) < 0.001 and v != 0):
            return f"{v:.0e}"
        if abs(v - round(v)) < 0.001:
            return str(int(round(v)))
        return f"{v:.2f}".rstrip("0").rstrip(".")

    def _draw_function(self, p: QPainter, f: dict):
        """Рисует одну функцию."""
        expr = f["expr"]
        color = QColor(f["color"])
        w = self.width()
        h = self.height()

        pen = QPen(color)
        pen.setWidth(2)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # Идём по пикселям X, считаем Y
        path = QPainterPath()
        prev_py = None
        started = False

        for px in range(w + 1):
            x = self.x_min + (px / w) * (self.x_max - self.x_min)
            try:
                y = safe_eval(expr, x)
                if not math.isfinite(y):
                    raise ValueError()
            except Exception:
                prev_py = None
                continue

            # Преобразуем в пиксель
            try:
                py = h - (y - self.y_min) / (self.y_max - self.y_min) * h
            except ZeroDivisionError:
                continue

            # Ограничиваем вылеты за экран
            if py < -h * 5 or py > h * 6:
                prev_py = None
                continue

            if not started:
                path.moveTo(px, py)
                started = True
            else:
                # Разрыв если большой скачок (асимптота)
                if prev_py is not None and abs(py - prev_py) > h * 1.5:
                    p.drawPath(path)
                    path = QPainterPath()
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            prev_py = py

        if started:
            p.drawPath(path)

        # Метка функции в правом верхнем углу
        # (будет добавлена снаружи через список)

    def _draw_info(self, p: QPainter):
        """Подписи границ."""
        p.setPen(QColor(255, 255, 255, 60))
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)

        text = f"x ∈ [{self.x_min:.2f}, {self.x_max:.2f}]   " \
               f"y ∈ [{self.y_min:.2f}, {self.y_max:.2f}]"
        p.drawText(QRectF(10, self.height() - 22, 400, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, text)

    # ------------------------------------------------------------
    #  Сохранение в PNG
    # ------------------------------------------------------------

    def render_to_pixmap(self, width: int = 1200, height: int = 800) -> QPixmap:
        """Рендерит график в pixmap заданного размера."""
        # Сохраняем размеры
        old_size = self.size()
        self.resize(width, height)
        self.update()
        pm = QPixmap(width, height)
        self.render(pm)
        self.resize(old_size)
        return pm


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
        "functions": [],       # список dict
        "counter": 0,
        "presets": {
            "sin(x)":            "Синус",
            "cos(x)":            "Косинус",
            "tan(x)":            "Тангенс",
            "x**2":              "Парабола",
            "x**3":              "Куб",
            "1/x":               "Гипербола",
            "sqrt(x)":           "Квадратный корень",
            "exp(-x**2)":        "Гауссиана",
            "log(x)":            "Натуральный логарифм",
            "sin(x)/x":          "sinc(x)",
            "abs(x)":            "Модуль",
            "x*sin(1/x)":        "x·sin(1/x)",
        },
    }

    # ============================================================
    #  Левая панель — управление функциями
    # ============================================================
    side = QWidget()
    side.setFixedWidth(360)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(16, 16, 16, 16)
    sl.setSpacing(10)

    title = QLabel("📈  Графики функций")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    # Ввод новой функции
    input_lbl = QLabel("ВВЕДИ ФУНКЦИЮ")
    input_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 4px;
    """)
    sl.addWidget(input_lbl)

    input_row = QHBoxLayout()
    input_row.setSpacing(8)

    expr_input = QLineEdit()
    expr_input.setPlaceholderText("sin(x)  ·  x**2  ·  exp(-x)")
    expr_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px 14px;
            font-family: Consolas, monospace;
            font-size: 14px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    input_row.addWidget(expr_input, 1)

    add_btn = QPushButton("＋")
    add_btn.setFixedSize(44, 44)
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.25);
            color: white;
            border: 1px solid rgba(110,198,255,0.60);
            border-radius: 10px;
            font-size: 20px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.45); }
    """)
    input_row.addWidget(add_btn)
    sl.addLayout(input_row)

    # Предустановки
    presets_lbl = QLabel("ПРЕДУСТАНОВКИ")
    presets_lbl.setStyleSheet(input_lbl.styleSheet())
    sl.addWidget(presets_lbl)

    presets_layout = QVBoxLayout()
    presets_layout.setSpacing(4)

    def add_preset(expr: str, name: str):
        b = QPushButton(f"  {name}    ({expr})")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(28)
        b.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.05);
                color: rgba(255,255,255,0.85);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
                padding: 2px 10px;
                text-align: left;
                font-size: 11px;
                font-family: Consolas, monospace;
            }
            QPushButton:hover {
                background: rgba(110,198,255,0.18);
                color: white;
                border: 1px solid rgba(110,198,255,0.45);
            }
        """)
        b.clicked.connect(lambda _, e=expr: quick_add(e))
        presets_layout.addWidget(b)

    # Показываем 6 предустановок, остальные — в скролле
    for expr, name in list(st["presets"].items())[:8]:
        add_preset(expr, name)

    sl.addLayout(presets_layout)

    # Список активных функций
    active_lbl = QLabel("АКТИВНЫЕ ФУНКЦИИ")
    active_lbl.setStyleSheet(input_lbl.styleSheet())
    sl.addWidget(active_lbl)

    func_list = QListWidget()
    func_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            font-family: Consolas, monospace;
            outline: none;
        }
        QListWidget::item { padding: 6px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(func_list, 1)

    # Кнопки управления
    ctrl_row = QHBoxLayout()
    ctrl_row.setSpacing(6)

    def small_btn(text: str, color: str, callback, tooltip: str = ""):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(32)
        b.setToolTip(tooltip)
        b.setStyleSheet(f"""
            QPushButton {{
                background: rgba({color}, 0.15);
                color: white;
                border: 1px solid rgba({color}, 0.40);
                border-radius: 8px;
                font-size: 11px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{ background: rgba({color}, 0.35); }}
        """)
        b.clicked.connect(callback)
        return b

    clear_all_btn = small_btn("🗑 Очистить", "255,107,138", lambda: clear_all())
    ctrl_row.addWidget(clear_all_btn)

    fit_btn = small_btn("⤢ Автомасштаб", "110,198,255", lambda: canvas.reset_zoom())
    ctrl_row.addWidget(fit_btn)

    save_btn = small_btn("💾 PNG", "110,231,183", lambda: save_png())
    ctrl_row.addWidget(save_btn)

    sl.addLayout(ctrl_row)

    # Подсказка
    hint = QLabel(
        "🖱  Колесо — зум\n"
        "🖱  Зажатая ЛКМ — сдвиг\n"
        "🖱  Двойной клик — сброс"
    )
    hint.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        background: rgba(0,0,0,0.20);
        border-radius: 8px;
        padding: 8px 10px;
        line-height: 1.5;
    """)
    sl.addWidget(hint)

    h.addWidget(side)

    # ============================================================
    #  Центр — холст
    # ============================================================
    canvas = PlotCanvas()
    h.addWidget(canvas, 1)

    # ============================================================
    #  Логика
    # ============================================================

    def next_color() -> str:
        return COLORS[st["counter"] % len(COLORS)]

    def add_function(expr: str):
        expr = expr.strip()
        if not expr:
            return

        # Проверка — вычислимо ли
        try:
            safe_eval(expr, 1.0)
        except Exception as e:
            QMessageBox.warning(root, "Ошибка формулы",
                f"Не удалось вычислить:\n{expr}\n\n{e}")
            return

        # Проверка дубликата
        for f in st["functions"]:
            if f["expr"] == expr:
                QMessageBox.information(root, "Уже добавлена",
                    f"Функция {expr} уже есть в списке.")
                return

        st["counter"] += 1
        func = {
            "expr": expr,
            "color": next_color(),
            "enabled": True,
        }
        st["functions"].append(func)
        refresh_all()
        expr_input.clear()

    def quick_add(expr: str):
        expr_input.setText(expr)
        add_function(expr)

    def clear_all():
        if not st["functions"]:
            return
        ans = QMessageBox.question(root, "Очистить",
            "Удалить все графики?", QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            st["functions"] = []
            refresh_all()

    def refresh_all():
        # Список
        func_list.clear()
        for i, f in enumerate(st["functions"]):
            item = QListWidgetItem(f"●  {f['expr']}")
            item.setData(Qt.UserRole, i)
            # Цветной индикатор
            color = QColor(f["color"])
            item.setForeground(color)
            item.setCheckState(Qt.Checked if f.get("enabled", True)
                                else Qt.Unchecked)
            func_list.addItem(item)
        # Холст
        canvas.set_functions(st["functions"])

    def on_item_changed(item):
        idx = item.data(Qt.UserRole)
        if idx is None or idx >= len(st["functions"]):
            return
        f = st["functions"][idx]
        f["enabled"] = (item.checkState() == Qt.Checked)
        canvas.update()

    func_list.itemChanged.connect(on_item_changed)

    def item_context(pos):
        item = func_list.itemAt(pos)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if idx is None:
            return
        menu = make_menu(func_list)

        f = st["functions"][idx]
        a_edit = menu.addAction("✏️ Редактировать")
        def do_edit():
            new_expr, ok = QInputDialog.getText(
                root, "Редактировать", "Функция:", text=f["expr"])
            if ok and new_expr.strip():
                try:
                    safe_eval(new_expr.strip(), 1.0)
                except Exception as e:
                    QMessageBox.warning(root, "Ошибка", str(e))
                    return
                f["expr"] = new_expr.strip()
                refresh_all()
        a_edit.triggered.connect(do_edit)

        menu.addSeparator()

        a_del = menu.addAction("🗑 Удалить")
        def do_del():
            st["functions"].pop(idx)
            refresh_all()
        a_del.triggered.connect(do_del)

        menu.exec(func_list.mapToGlobal(pos))

    func_list.setContextMenuPolicy(Qt.CustomContextMenu)
    func_list.customContextMenuRequested.connect(item_context)

    def save_png():
        if not st["functions"]:
            QMessageBox.information(root, "Графики",
                "Сначала добавь хотя бы одну функцию.")
            return
        if vfs is None:
            QMessageBox.warning(root, "Ошибка", "VFS недоступна")
            return

        name, ok = QInputDialog.getText(
            root, "Сохранить PNG",
            "Имя файла (без .png):",
            text=f"plot_{int(time.time())}")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".png"):
            name += ".png"

        path = f"{OUT_DIR}/{name}"
        base, dot, ext = name.partition(".")
        n = 1
        while vfs.exists(path):
            path = f"{OUT_DIR}/{base}_{n}.{dot}{ext}"
            n += 1

        try:
            pm = canvas.render_to_pixmap(1200, 800)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QBuffer.WriteOnly)
            pm.save(buf, "PNG")
            buf.close()
            vfs.mkdir(OUT_DIR)
            vfs.write_bytes(path, bytes(ba))

            if desktop and hasattr(desktop, "notifications"):
                desktop.notifications.push("График сохранён", path)
            QMessageBox.information(root, "Сохранено",
                f"PNG сохранён:\n{path}")
        except Exception as e:
            QMessageBox.warning(root, "Ошибка", str(e))

    # Связи
    add_btn.clicked.connect(lambda: add_function(expr_input.text()))
    expr_input.returnPressed.connect(lambda: add_function(expr_input.text()))

    # Стартовые функции — чтобы сразу было красиво
    st["counter"] = 0
    # Не добавляем автоматически, пусть пользователь сам выберет

    refresh_all()

    return root