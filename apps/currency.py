"""
MountOS — Курсы валют.

Реальные данные через открытый API ЦБ РФ:
  • Официальные курсы ЦБ России (cbr-xml-daily.ru)
  • 30+ валют
  • Конвертер валют
  • График изменения курса за 30 дней
  • Сохранение избранных валют в VFS
  • Автообновление каждый час

API работает без ключа, возвращает JSON:
    https://www.cbr-xml-daily.ru/daily_json.js

Установка: apps/currency.py + перезапуск MountOS.
"""

import json
import urllib.request
from datetime import datetime, date, timedelta

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QComboBox, QScrollArea,
                                QFrame, QMessageBox, QSizePolicy, QCheckBox)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath,
                            QLinearGradient, QFont, QIcon)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Курсы валют"
APP_ICON = "calculator"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


FAVORITES_PATH = "/Notes/currency_favorites.json"
LAST_CACHE_PATH = "/Notes/currency_last.json"


# Флаг эмодзи для популярных валют
CURRENCY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "CNY": "🇨🇳",
    "JPY": "🇯🇵", "CHF": "🇨🇭", "KZT": "🇰🇿", "UAH": "🇺🇦",
    "BYN": "🇧🇾", "TRY": "🇹🇷", "KGS": "🇰🇬", "UZS": "🇺🇿",
    "AMD": "🇦🇲", "AZN": "🇦🇿", "GEL": "🇬🇪", "MDL": "🇲🇩",
    "PLN": "🇵🇱", "CZK": "🇨🇿", "SEK": "🇸🇪", "NOK": "🇳🇴",
    "DKK": "🇩🇰", "CAD": "🇨🇦", "AUD": "🇦🇺", "NZD": "🇳🇿",
    "KRW": "🇰🇷", "INR": "🇮🇳", "BRL": "🇧🇷", "ZAR": "🇿🇦",
    "SGD": "🇸🇬", "HKD": "🇭🇰", "AED": "🇦🇪", "ILS": "🇮🇱",
    "RUB": "🇷🇺",
}


# ============================================================
#  Поиск VFS
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


# ============================================================
#  Воркеры
# ============================================================

class RatesWorker(QThread):
    """Загружает текущие курсы ЦБ РФ."""
    data_ready = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            url = "https://www.cbr-xml-daily.ru/daily_json.js"
            req = urllib.request.Request(
                url, headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.data_ready.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class HistoryWorker(QThread):
    """Загружает историю курса за последние 30 дней для графика."""
    data_ready = Signal(list)  # [(date_str, value), ...]
    error = Signal(str)

    def __init__(self, currency_code: str):
        super().__init__()
        self.currency_code = currency_code

    def run(self):
        try:
            result = []
            today = date.today()
            # Загружаем 30 архивов — по одному на день
            for i in range(30):
                d = today - timedelta(days=i)
                # Пропускаем выходные (ЦБ не публикует)
                if d.weekday() >= 5:
                    continue
                url = f"https://www.cbr-xml-daily.ru/archive/{d.year}/{d.month:02d}/{d.day:02d}/daily_json.js"
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "MountOS/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                    vals = data.get("Valute", {})
                    if self.currency_code in vals:
                        value = vals[self.currency_code].get("Value", 0)
                        result.append((d.isoformat(), value))
                except Exception:
                    continue

            result.sort(key=lambda x: x[0])  # от старых к новым
            self.data_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  График курса
# ============================================================

class RateChart(QWidget):
    """Мини-график изменения курса."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._data = []       # [(date_str, value), ...]
        self._label = ""

    def set_data(self, data: list, label: str = ""):
        self._data = data
        self._label = label
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if not self._data or len(self._data) < 2:
            p.setPen(QColor(255, 255, 255, 80))
            font = QFont()
            font.setPointSize(12)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, "Нет данных для графика")
            return

        w = self.width()
        h = self.height()
        margin_top = 30
        margin_bottom = 40
        margin_left = 50
        margin_right = 15
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        values = [v for _, v in self._data]
        v_min = min(values)
        v_max = max(values)
        v_span = max(0.001, v_max - v_min)

        # Сетка + подписи значений
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)
        for i in range(5):
            y = margin_top + chart_h * i / 4
            p.drawLine(margin_left, int(y), w - margin_right, int(y))
            val = v_max - v_span * i / 4
            p.setPen(QColor(255, 255, 255, 130))
            p.drawText(QRectF(2, y - 8, margin_left - 6, 16),
                       Qt.AlignRight | Qt.AlignVCenter, f"{val:.3f}")
            p.setPen(QPen(QColor(255, 255, 255, 20), 1))

        # Точки
        points = []
        n = len(self._data)
        for i, (d, v) in enumerate(self._data):
            x = margin_left + chart_w * i / (n - 1)
            y = margin_top + chart_h * (1 - (v - v_min) / v_span)
            points.append((x, y, v, d))

        # Область под линией
        accent = state().get("accent", "#6EC6FF")
        area = QPainterPath()
        area.moveTo(points[0][0], margin_top + chart_h)
        for x, y, _, _ in points:
            area.lineTo(x, y)
        area.lineTo(points[-1][0], margin_top + chart_h)
        area.closeSubpath()

        grad = QLinearGradient(0, margin_top, 0, margin_top + chart_h)
        grad.setColorAt(0, QColor(110, 198, 255, 120))
        grad.setColorAt(1, QColor(110, 198, 255, 5))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawPath(area)

        # Линия
        pen = QPen(QColor(accent), 2)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for i in range(len(points) - 1):
            p.drawLine(QPointF(points[i][0], points[i][1]),
                       QPointF(points[i + 1][0], points[i + 1][1]))

        # Точки
        for x, y, v, d in points:
            p.setBrush(QBrush(QColor(accent)))
            p.setPen(QPen(QColor("white"), 1.5))
            p.drawEllipse(QPointF(x, y), 3, 3)

        # Подписи дат (каждые ~7 точек)
        p.setPen(QColor(255, 255, 255, 140))
        step = max(1, n // 6)
        for i in range(0, n, step):
            x, _, _, d = points[i]
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                label = dt.strftime("%d.%m")
            except Exception:
                label = d
            p.drawText(QRectF(x - 20, h - margin_bottom + 8, 40, 16),
                       Qt.AlignCenter, label)

        # Заголовок
        if self._label:
            p.setPen(QColor("white"))
            font2 = QFont()
            font2.setPointSize(11)
            font2.setBold(True)
            p.setFont(font2)
            p.drawText(QRectF(margin_left, 4, w - margin_left - margin_right, 22),
                       Qt.AlignLeft | Qt.AlignVCenter, self._label)

        # Разница за период
        diff = values[-1] - values[0]
        pct = (diff / values[0]) * 100 if values[0] else 0
        if diff > 0:
            color = QColor("#6EE7B7")
            sign = "+"
        elif diff < 0:
            color = QColor("#FF6B8A")
            sign = ""
        else:
            color = QColor(255, 255, 255, 200)
            sign = ""

        p.setPen(color)
        font3 = QFont()
        font3.setPointSize(11)
        font3.setBold(True)
        p.setFont(font3)
        diff_text = f"{sign}{diff:.3f}  ({sign}{pct:.2f}%)"
        p.drawText(QRectF(margin_left, 4, w - margin_left - margin_right, 22),
                   Qt.AlignRight | Qt.AlignVCenter, diff_text)


# ============================================================
#  Основное приложение
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    vfs = _get_vfs(root)

    # ============================================================
    #  Левая панель — список валют
    # ============================================================
    side = QWidget()
    side.setFixedWidth(320)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("💱  Курсы ЦБ РФ")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    # Статус обновления
    status_lbl = QLabel("Загрузка…")
    status_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px; padding: 2px;")
    sl.addWidget(status_lbl)

    # Поиск
    search_input = QLineEdit()
    search_input.setPlaceholderText("Поиск валюты…")
    search_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 12px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    sl.addWidget(search_input)

    # Список валют
    currency_list = QListWidget()
    currency_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 8px 10px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(currency_list, 1)

    # Кнопки
    refresh_btn = QPushButton("🔄  Обновить")
    refresh_btn.setCursor(Qt.PointingHandCursor)
    refresh_btn.setFixedHeight(34)
    refresh_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            font-size: 12px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    sl.addWidget(refresh_btn)

    h.addWidget(side)

    # ============================================================
    #  Правая часть — конвертер + график
    # ============================================================
    right = QWidget()
    rl = QVBoxLayout(right)
    rl.setContentsMargins(24, 20, 24, 20)
    rl.setSpacing(14)

    # ---- Конвертер ----
    conv_box = QWidget()
    conv_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 16px;
        }
    """)
    cbl = QVBoxLayout(conv_box)
    cbl.setContentsMargins(20, 18, 20, 18)
    cbl.setSpacing(12)

    conv_title = QLabel("Конвертер валют")
    conv_title.setStyleSheet("""
        color: white;
        font-size: 14px;
        font-weight: 600;
        background: transparent;
        border: none;
    """)
    cbl.addWidget(conv_title)

    conv_row = QHBoxLayout()
    conv_row.setSpacing(10)

    # Сумма
    amount_input = QLineEdit("1000")
    amount_input.setFixedWidth(130)
    amount_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 10px 14px;
            font-size: 16px;
            font-weight: 600;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    conv_row.addWidget(amount_input)

    # Из валюты
    from_combo = QComboBox()
    from_combo.setFixedWidth(140)
    from_combo.setStyleSheet("""
        QComboBox {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QComboBox:hover { background: rgba(255,255,255,0.14); }
        QComboBox QAbstractItemView {
            background: rgba(28,34,54,0.98);
            color: white;
            selection-background-color: rgba(110,198,255,0.35);
            border: 1px solid rgba(255,255,255,0.15);
        }
    """)
    conv_row.addWidget(from_combo)

    # Стрелка
    arrow = QLabel("→")
    arrow.setStyleSheet("""
        color: #6EC6FF;
        font-size: 20px;
        background: transparent;
        border: none;
    """)
    conv_row.addWidget(arrow)

    # В валюту
    to_combo = QComboBox()
    to_combo.setFixedWidth(140)
    to_combo.setStyleSheet(from_combo.styleSheet())
    conv_row.addWidget(to_combo)

    conv_row.addStretch(1)
    cbl.addLayout(conv_row)

    # Результат
    result_lbl = QLabel("—")
    result_lbl.setStyleSheet("""
        color: #6EE7B7;
        font-size: 28px;
        font-weight: 300;
        padding: 8px 0;
        background: transparent;
        border: none;
    """)
    cbl.addWidget(result_lbl)

    rl.addWidget(conv_box)

    # ---- График ----
    chart_title = QLabel("График изменения курса за 30 дней")
    chart_title.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 4px;")
    rl.addWidget(chart_title)

    chart = RateChart()
    chart.setStyleSheet("""
        RateChart {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
        }
    """)
    rl.addWidget(chart, 1)

    h.addWidget(right, 1)

    # ============================================================
    #  Логика
    # ============================================================

    st = {
        "valutes": {},        # код → {Name, Value, Previous, Nominal}
        "base": {},           # JSON полностью
        "current_currency": "USD",
        "rates_worker": None,
        "history_worker": None,
    }

    def load_rates():
        status_lbl.setText("Загрузка курсов…")
        worker = RatesWorker()
        st["rates_worker"] = worker
        worker.data_ready.connect(on_rates_loaded)
        worker.error.connect(on_rates_error)
        worker.start()

    def on_rates_loaded(data):
        st["base"] = data
        st["valutes"] = data.get("Valute", {})
        try:
            date_str = data.get("Date", "")
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            status_lbl.setText(f"Обновлено: {dt.strftime('%d.%m.%Y %H:%M')}")
        except Exception:
            status_lbl.setText("Обновлено")
        rebuild_list()
        rebuild_combos()
        update_converter()
        # Сохраняем кэш
        if vfs:
            try:
                vfs.mkdir("/Notes")
                vfs.write_text(LAST_CACHE_PATH,
                                json.dumps(data, ensure_ascii=False))
            except Exception:
                pass

    def on_rates_error(err):
        status_lbl.setText(f"⚠ {err}")
        # Пробуем кэш
        if vfs:
            try:
                raw = vfs.read_text(LAST_CACHE_PATH, "")
                if raw.strip():
                    data = json.loads(raw)
                    st["base"] = data
                    st["valutes"] = data.get("Valute", {})
                    status_lbl.setText("Кэш (нет интернета)")
                    rebuild_list()
                    rebuild_combos()
                    update_converter()
            except Exception:
                pass

    def rebuild_list():
        currency_list.clear()
        query = search_input.text().strip().lower()

        for code in sorted(st["valutes"].keys()):
            v = st["valutes"][code]
            name = v.get("Name", "")
            value = v.get("Value", 0)
            previous = v.get("Previous", 0)
            nominal = v.get("Nominal", 1)

            if query and query not in code.lower() and query not in name.lower():
                continue

            # Значение за 1 единицу
            per_unit = value / nominal
            prev_per_unit = previous / nominal

            flag = CURRENCY_FLAGS.get(code, "🏳")
            diff = per_unit - prev_per_unit
            if diff > 0.0001:
                arrow_str = "▲"
                color = "#6EE7B7"
            elif diff < -0.0001:
                arrow_str = "▼"
                color = "#FF6B8A"
            else:
                arrow_str = "—"
                color = "rgba(255,255,255,0.55)"

            item = QListWidgetItem(
                f"{flag} {code:5}  {name[:20]:20}  {per_unit:.4f} ₽  {arrow_str}")
            item.setData(Qt.UserRole, code)
            # Цвет для стрелки — можно только через delegate, оставим просто текст
            currency_list.addItem(item)

    def rebuild_combos():
        from_combo.clear()
        to_combo.clear()

        codes = ["RUB"] + sorted(st["valutes"].keys())
        for code in codes:
            flag = CURRENCY_FLAGS.get(code, "🏳")
            from_combo.addItem(f"{flag} {code}", code)
            to_combo.addItem(f"{flag} {code}", code)

        # Устанавливаем дефолтные
        from_combo.setCurrentIndex(from_combo.findData("USD"))
        to_combo.setCurrentIndex(to_combo.findData("RUB"))

    def get_rate_per_rub(code: str) -> float:
        """Сколько рублей за 1 единицу валюты (или 1 для RUB)."""
        if code == "RUB":
            return 1.0
        v = st["valutes"].get(code)
        if not v:
            return 0.0
        nominal = v.get("Nominal", 1)
        return v.get("Value", 0) / nominal

    def update_converter():
        try:
            amount = float(amount_input.text().replace(",", "."))
        except ValueError:
            amount = 0

        from_code = from_combo.currentData()
        to_code = to_combo.currentData()

        if not from_code or not to_code:
            result_lbl.setText("—")
            return

        from_rate = get_rate_per_rub(from_code)
        to_rate = get_rate_per_rub(to_code)

        if from_rate <= 0 or to_rate <= 0:
            result_lbl.setText("—")
            return

        # В рубли, потом в целевую
        in_rub = amount * from_rate
        result = in_rub / to_rate

        # Красиво форматируем
        if result >= 1000:
            result_text = f"{result:,.2f}".replace(",", " ")
        elif result >= 1:
            result_text = f"{result:.2f}"
        else:
            result_text = f"{result:.4f}"

        to_flag = CURRENCY_FLAGS.get(to_code, "")
        result_lbl.setText(f"{result_text} {to_code}  {to_flag}")

    def on_currency_click(item):
        code = item.data(Qt.UserRole)
        if not code:
            return
        st["current_currency"] = code
        load_history(code)

    def load_history(code: str):
        chart.set_data([], f"Загрузка истории {code}…")
        worker = HistoryWorker(code)
        st["history_worker"] = worker
        worker.data_ready.connect(on_history_loaded)
        worker.error.connect(lambda err: chart.set_data([], f"⚠ {err}"))
        worker.start()

    def on_history_loaded(data):
        code = st["current_currency"]
        v = st["valutes"].get(code, {})
        nominal = v.get("Nominal", 1)
        # Пересчитываем за 1 единицу
        data_per_unit = [(d, val / nominal) for d, val in data]
        name = v.get("Name", code)
        chart.set_data(data_per_unit, f"{code} — {name}")

    # ---- Связи ----
    refresh_btn.clicked.connect(load_rates)
    search_input.textChanged.connect(rebuild_list)
    currency_list.itemClicked.connect(on_currency_click)
    amount_input.textChanged.connect(update_converter)
    from_combo.currentIndexChanged.connect(update_converter)
    to_combo.currentIndexChanged.connect(update_converter)

    # ---- Автообновление каждый час ----
    auto_timer = QTimer(root)
    auto_timer.setInterval(60 * 60 * 1000)  # 1 час
    auto_timer.timeout.connect(load_rates)
    auto_timer.start()

    # ---- Начальная загрузка ----
    # Пробуем кэш сначала
    if vfs:
        try:
            raw = vfs.read_text(LAST_CACHE_PATH, "")
            if raw.strip():
                data = json.loads(raw)
                st["base"] = data
                st["valutes"] = data.get("Valute", {})
                try:
                    dt_str = data.get("Date", "")
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    status_lbl.setText(f"Кэш: {dt.strftime('%d.%m.%Y %H:%M')}")
                except Exception:
                    status_lbl.setText("Из кэша")
                rebuild_list()
                rebuild_combos()
                update_converter()
        except Exception:
            pass

    # Затем — свежие данные
    QTimer.singleShot(300, load_rates)

    return root