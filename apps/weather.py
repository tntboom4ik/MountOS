"""
MountOS — Погода.

Реальные данные через открытый API open-meteo.com (без ключа):
  • Текущая погода
  • Прогноз на 7 дней
  • Почасовой прогноз на 24 часа
  • График температуры
  • Выбор города (поиск через geocoding-api.open-meteo.com)
  • Сохранение последнего города в VFS

Установка: apps/weather.py + перезапуск MountOS.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, date, timedelta

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QLineEdit, QListWidget,
                                QListWidgetItem, QScrollArea, QFrame,
                                QMessageBox, QSizePolicy, QDialog)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QPainterPath,
                            QLinearGradient, QFont, QIcon)

from ui.icons import get_icon
from ui.settings_state import state

APP_NAME = "Погода"
APP_ICON = "globe"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


CONFIG_PATH = "/Notes/weather_city.json"


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


# ============================================================
#  WMO weather codes → текст и иконка
# ============================================================

WMO_CODES = {
    0:  ("Ясно", "☀️"),
    1:  ("Преимущественно ясно", "🌤"),
    2:  ("Переменная облачность", "⛅"),
    3:  ("Пасмурно", "☁️"),
    45: ("Туман", "🌫"),
    48: ("Изморозь", "🌫"),
    51: ("Лёгкая морось", "🌦"),
    53: ("Морось", "🌦"),
    55: ("Сильная морось", "🌧"),
    61: ("Небольшой дождь", "🌦"),
    63: ("Дождь", "🌧"),
    65: ("Сильный дождь", "🌧"),
    71: ("Небольшой снег", "🌨"),
    73: ("Снег", "❄️"),
    75: ("Сильный снег", "❄️"),
    77: ("Снежные зёрна", "🌨"),
    80: ("Ливни", "🌦"),
    81: ("Сильные ливни", "🌧"),
    82: ("Очень сильные ливни", "⛈"),
    85: ("Снегопад", "🌨"),
    86: ("Сильный снегопад", "❄️"),
    95: ("Гроза", "⛈"),
    96: ("Гроза с градом", "⛈"),
    99: ("Сильная гроза с градом", "⛈"),
}


def wmo_info(code: int) -> tuple:
    """Возвращает (текст, эмодзи) для WMO-кода."""
    return WMO_CODES.get(code, ("—", "❓"))


# ============================================================
#  Воркер для запросов (чтобы не блокировать UI)
# ============================================================

class WeatherWorker(QThread):
    """Загружает погоду в отдельном потоке."""

    data_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, lat: float, lon: float):
        super().__init__()
        self.lat = lat
        self.lon = lon

    def run(self):
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={self.lat}&longitude={self.lon}"
                f"&current=temperature_2m,relative_humidity_2m,"
                f"apparent_temperature,is_day,precipitation,"
                f"weather_code,wind_speed_10m,pressure_msl"
                f"&hourly=temperature_2m,weather_code,precipitation_probability"
                f"&daily=weather_code,temperature_2m_max,temperature_2m_min,"
                f"precipitation_sum,sunrise,sunset"
                f"&timezone=auto"
                f"&forecast_days=7"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.data_ready.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class GeocodingWorker(QThread):
    """Ищет город по названию."""

    results = Signal(list)
    error = Signal(str)

    def __init__(self, query: str):
        super().__init__()
        self.query = query

    def run(self):
        try:
            q = urllib.parse.quote(self.query)
            url = (f"https://geocoding-api.open-meteo.com/v1/search?"
                   f"name={q}&count=10&language=ru&format=json")
            req = urllib.request.Request(
                url, headers={"User-Agent": "MountOS/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            self.results.emit(results)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  График температуры (QPainter)
# ============================================================

class TemperatureChart(QWidget):
    """Мини-график температуры на 7 дней."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._days = []       # [(label, tmax, tmin), ...]

    def set_data(self, days: list):
        self._days = days
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        if not self._days:
            p.setPen(QColor(255, 255, 255, 80))
            p.drawText(self.rect(), Qt.AlignCenter, "Нет данных")
            return

        w = self.width()
        h = self.height()
        margin_top = 20
        margin_bottom = 30
        chart_h = h - margin_top - margin_bottom

        # Границы температур
        all_t = []
        for d in self._days:
            all_t.append(d[1])
            all_t.append(d[2])
        t_min = min(all_t)
        t_max = max(all_t)
        span = max(1, t_max - t_min)

        accent = state().get("accent", "#6EC6FF")

        n = len(self._days)
        step = w / (n + 1)

        # Сетка
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        for i in range(5):
            y = margin_top + chart_h * i / 4
            p.drawLine(0, int(y), w, int(y))

        # Точки
        points_max = []
        points_min = []

        for i, (label, tmax, tmin) in enumerate(self._days):
            x = step * (i + 1)
            y_max = margin_top + chart_h * (1 - (tmax - t_min) / span)
            y_min = margin_top + chart_h * (1 - (tmin - t_min) / span)
            points_max.append((x, y_max, tmax))
            points_min.append((x, y_min, tmin))

        # Область между линиями
        area = QPainterPath()
        area.moveTo(points_max[0][0], points_max[0][1])
        for x, y, _ in points_max[1:]:
            area.lineTo(x, y)
        for x, y, _ in reversed(points_min):
            area.lineTo(x, y)
        area.closeSubpath()

        grad = QLinearGradient(0, margin_top, 0, margin_top + chart_h)
        grad.setColorAt(0, QColor(110, 198, 255, 80))
        grad.setColorAt(1, QColor(110, 198, 255, 5))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawPath(area)

        # Линия максимумов
        pen = QPen(QColor(accent), 2)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for i in range(len(points_max) - 1):
            p.drawLine(QPointF(*points_max[i][:2]),
                       QPointF(*points_max[i + 1][:2]))

        # Точки-кружки
        for x, y, t in points_max:
            p.setBrush(QBrush(QColor(accent)))
            p.setPen(QPen(QColor("white"), 1.5))
            p.drawEllipse(QPointF(x, y), 3.5, 3.5)

        # Подписи температур
        p.setPen(QColor(255, 255, 255, 230))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        for x, y, t in points_max:
            p.drawText(QRectF(x - 20, y - 22, 40, 16),
                       Qt.AlignCenter, f"{int(round(t))}°")

        # Подписи дней
        p.setPen(QColor(255, 255, 255, 160))
        font2 = QFont()
        font2.setPointSize(9)
        p.setFont(font2)
        for i, (label, _, _) in enumerate(self._days):
            x = step * (i + 1)
            p.drawText(QRectF(x - 30, h - margin_bottom + 6, 60, 20),
                       Qt.AlignCenter, label)


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
    #  Левая панель — управление городом
    # ============================================================
    side = QWidget()
    side.setFixedWidth(240)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(14, 16, 14, 16)
    sl.setSpacing(10)

    title = QLabel("🌤  Погода")
    title.setStyleSheet("color: white; font-size: 16px; font-weight: 600; padding: 2px;")
    sl.addWidget(title)

    hint = QLabel("Введи название города:")
    hint.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
    sl.addWidget(hint)

    city_input = QLineEdit()
    city_input.setPlaceholderText("Москва, Лондон, Tokyo…")
    city_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    sl.addWidget(city_input)

    search_btn = QPushButton("🔍  Найти")
    search_btn.setCursor(Qt.PointingHandCursor)
    search_btn.setFixedHeight(36)
    search_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.22);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover { background: rgba(110,198,255,0.42); }
    """)
    sl.addWidget(search_btn)

    # ---- Результаты поиска ----
    result_lbl = QLabel("РЕЗУЛЬТАТЫ")
    result_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding-top: 6px;
    """)
    sl.addWidget(result_lbl)

    result_list = QListWidget()
    result_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.20);
            color: white;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 4px;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 6px 8px; border-radius: 6px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    sl.addWidget(result_list, 1)

    # Показать сохранённый город
    saved_city = None
    if vfs:
        try:
            raw = vfs.read_text(CONFIG_PATH, "")
            if raw.strip():
                saved_city = json.loads(raw)
        except Exception:
            pass

    city_lbl = QLabel("—")
    city_lbl.setWordWrap(True)
    city_lbl.setStyleSheet("""
        background: rgba(110,198,255,0.10);
        color: rgba(255,255,255,0.90);
        border: 1px solid rgba(110,198,255,0.30);
        border-radius: 10px;
        padding: 10px 12px;
        font-size: 12px;
    """)
    if saved_city:
        city_lbl.setText(f"📍 {saved_city.get('name', '—')}")
    sl.addWidget(city_lbl)

    h.addWidget(side)

    # ============================================================
    #  Центр — погода
    # ============================================================
    center = QWidget()
    cl = QVBoxLayout(center)
    cl.setContentsMargins(24, 20, 24, 20)
    cl.setSpacing(16)

    # ---- Заголовок с текущей погодой ----
    current_box = QWidget()
    current_box.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 18px;
        }
    """)
    cbl = QHBoxLayout(current_box)
    cbl.setContentsMargins(24, 20, 24, 20)
    cbl.setSpacing(24)

    # Левая часть — большая иконка
    big_icon = QLabel("☀️")
    big_icon.setFixedSize(100, 100)
    big_icon.setAlignment(Qt.AlignCenter)
    big_icon.setStyleSheet("""
        font-size: 68px;
        background: transparent;
        border: none;
    """)
    cbl.addWidget(big_icon)

    # Правая часть — температура + описание
    info_col = QVBoxLayout()
    info_col.setSpacing(4)

    temp_lbl = QLabel("—°")
    temp_lbl.setStyleSheet("""
        color: white;
        font-size: 52px;
        font-weight: 200;
        letter-spacing: -2px;
        background: transparent;
        border: none;
    """)
    info_col.addWidget(temp_lbl)

    desc_lbl = QLabel("Загрузка…")
    desc_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.85);
        font-size: 16px;
        font-weight: 500;
        background: transparent;
        border: none;
    """)
    info_col.addWidget(desc_lbl)

    feels_lbl = QLabel("")
    feels_lbl.setStyleSheet("""
        color: rgba(255,255,255,0.55);
        font-size: 12px;
        background: transparent;
        border: none;
    """)
    info_col.addWidget(feels_lbl)

    info_col.addStretch(1)
    cbl.addLayout(info_col, 1)

    # Дополнительные метрики
    metrics_col = QVBoxLayout()
    metrics_col.setSpacing(6)

    def make_metric(label_text):
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        l1 = QLabel(label_text)
        l1.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px; background: transparent; border: none;")
        rl.addWidget(l1)
        l2 = QLabel("—")
        l2.setStyleSheet("color: white; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        rl.addWidget(l2)
        rl.addStretch(1)
        return row, l2

    humidity_row, humidity_val = make_metric("💧 Влажность")
    wind_row, wind_val = make_metric("💨 Ветер")
    pressure_row, pressure_val = make_metric("📊 Давление")
    precip_row, precip_val = make_metric("☔ Осадки")

    metrics_col.addWidget(humidity_row)
    metrics_col.addWidget(wind_row)
    metrics_col.addWidget(pressure_row)
    metrics_col.addWidget(precip_row)
    metrics_col.addStretch(1)

    cbl.addLayout(metrics_col)

    cl.addWidget(current_box)

    # ---- График 7 дней ----
    chart_lbl = QLabel("Прогноз на 7 дней")
    chart_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; padding: 4px;")
    cl.addWidget(chart_lbl)

    chart = TemperatureChart()
    chart.setStyleSheet("""
        TemperatureChart {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
        }
    """)
    cl.addWidget(chart)

    # ---- Список дней ----
    days_lbl = QLabel("Детали по дням")
    days_lbl.setStyleSheet(chart_lbl.styleSheet())
    cl.addWidget(days_lbl)

    days_scroll = QScrollArea()
    days_scroll.setWidgetResizable(True)
    days_scroll.setFrameShape(QFrame.NoFrame)
    days_scroll.setStyleSheet("""
        QScrollArea { background: transparent; border: none; }
        QScrollBar:vertical {
            background: transparent; width: 6px; margin: 2px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.20);
            border-radius: 3px; min-height: 24px;
        }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    """)
    days_holder = QWidget()
    days_holder.setStyleSheet("background: transparent;")
    days_list = QVBoxLayout(days_holder)
    days_list.setContentsMargins(0, 0, 0, 0)
    days_list.setSpacing(6)
    days_list.addStretch(1)
    days_scroll.setWidget(days_holder)
    cl.addWidget(days_scroll, 1)

    h.addWidget(center, 1)

    # ============================================================
    #  Логика
    # ============================================================

    st = {
        "lat": None,
        "lon": None,
        "city_name": saved_city.get("name") if saved_city else None,
        "worker": None,
    }

    def show_loading(text: str = "Загрузка…"):
        temp_lbl.setText("—°")
        desc_lbl.setText(text)
        feels_lbl.setText("")
        humidity_val.setText("—")
        wind_val.setText("—")
        pressure_val.setText("—")
        precip_val.setText("—")
        big_icon.setText("⏳")

    def do_search():
        query = city_input.text().strip()
        if not query:
            return
        result_list.clear()
        item = QListWidgetItem("Поиск…")
        result_list.addItem(item)
        search_btn.setEnabled(False)

        worker = GeocodingWorker(query)
        st["search_worker"] = worker
        worker.results.connect(on_search_results)
        worker.error.connect(on_search_error)
        worker.start()

    def on_search_results(results):
        search_btn.setEnabled(True)
        result_list.clear()
        if not results:
            item = QListWidgetItem("Ничего не найдено")
            result_list.addItem(item)
            return
        for r in results:
            name = r.get("name", "?")
            country = r.get("country", "")
            admin = r.get("admin1", "")
            full = f"{name}, {admin}, {country}" if admin else f"{name}, {country}"
            item = QListWidgetItem(f"📍 {full}")
            item.setData(Qt.UserRole, {
                "lat": r.get("latitude"),
                "lon": r.get("longitude"),
                "name": name,
                "full": full,
            })
            result_list.addItem(item)

    def on_search_error(err):
        search_btn.setEnabled(True)
        result_list.clear()
        item = QListWidgetItem(f"⚠ {err}")
        result_list.addItem(item)

    def on_city_selected(item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        st["lat"] = data["lat"]
        st["lon"] = data["lon"]
        st["city_name"] = data["name"]
        city_lbl.setText(f"📍 {data['full']}")

        # Сохраняем
        if vfs:
            try:
                vfs.mkdir("/Notes")
                vfs.write_text(CONFIG_PATH, json.dumps({
                    "name": data["name"],
                    "full": data["full"],
                    "lat": data["lat"],
                    "lon": data["lon"],
                }, ensure_ascii=False, indent=2))
            except Exception:
                pass

        load_weather()

    def load_weather():
        if st["lat"] is None or st["lon"] is None:
            return
        show_loading("Загрузка погоды…")
        # Очищаем старый
        for i in reversed(range(days_list.count())):
            it = days_list.itemAt(i)
            w = it.widget() if it else None
            if w:
                w.setParent(None)

        worker = WeatherWorker(st["lat"], st["lon"])
        st["weather_worker"] = worker
        worker.data_ready.connect(on_weather_loaded)
        worker.error.connect(on_weather_error)
        worker.start()

    def on_weather_loaded(data):
        try:
            current = data.get("current", {})
            daily = data.get("daily", {})
            hourly = data.get("hourly", {})

            temp = current.get("temperature_2m", 0)
            feels = current.get("apparent_temperature", 0)
            humidity = current.get("relative_humidity_2m", 0)
            wind = current.get("wind_speed_10m", 0)
            pressure = current.get("pressure_msl", 0)
            precip = current.get("precipitation", 0)
            code = current.get("weather_code", 0)

            text, emoji = wmo_info(code)

            big_icon.setText(emoji)
            temp_lbl.setText(f"{int(round(temp))}°")
            desc_lbl.setText(text)
            feels_lbl.setText(f"Ощущается как {int(round(feels))}°")
            humidity_val.setText(f"{humidity}%")
            wind_val.setText(f"{wind:.1f} м/с")
            pressure_val.setText(f"{int(round(pressure))} гПа")
            precip_val.setText(f"{precip:.1f} мм" if precip > 0 else "нет")

            # ---- Прогноз на 7 дней ----
            dates = daily.get("time", [])
            codes = daily.get("weather_code", [])
            tmax = daily.get("temperature_2m_max", [])
            tmin = daily.get("temperature_2m_min", [])
            precip_sum = daily.get("precipitation_sum", [])

            # График
            chart_data = []
            for i, d in enumerate(dates[:7]):
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    label = dt.strftime("%a")
                    chart_data.append((
                        label,
                        float(tmax[i]) if i < len(tmax) else 0,
                        float(tmin[i]) if i < len(tmin) else 0,
                    ))
                except Exception:
                    continue
            chart.set_data(chart_data)

            # Список дней
            for i, d in enumerate(dates[:7]):
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][dt.weekday()]
                    label = f"{weekday}, {dt.day:02d}.{dt.month:02d}"
                except Exception:
                    label = d

                code_d = codes[i] if i < len(codes) else 0
                text_d, emoji_d = wmo_info(code_d)

                tmax_d = tmax[i] if i < len(tmax) else 0
                tmin_d = tmin[i] if i < len(tmin) else 0
                precip_d = precip_sum[i] if i < len(precip_sum) else 0

                row = QWidget()
                row.setStyleSheet("""
                    QWidget {
                        background: rgba(255,255,255,0.04);
                        border-radius: 10px;
                    }
                    QWidget:hover {
                        background: rgba(255,255,255,0.08);
                    }
                """)
                rl = QHBoxLayout(row)
                rl.setContentsMargins(14, 10, 14, 10)
                rl.setSpacing(14)

                day_lbl = QLabel(label)
                day_lbl.setFixedWidth(90)
                day_lbl.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 13px; background: transparent; border: none;")
                rl.addWidget(day_lbl)

                emoji_lbl = QLabel(emoji_d)
                emoji_lbl.setFixedWidth(30)
                emoji_lbl.setStyleSheet("font-size: 20px; background: transparent; border: none;")
                emoji_lbl.setAlignment(Qt.AlignCenter)
                rl.addWidget(emoji_lbl)

                desc_day = QLabel(text_d)
                desc_day.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px; background: transparent; border: none;")
                rl.addWidget(desc_day, 1)

                if precip_d and precip_d > 0:
                    precip_lbl = QLabel(f"☔ {precip_d:.1f}мм")
                    precip_lbl.setStyleSheet("color: #6EC6FF; font-size: 11px; background: transparent; border: none;")
                    rl.addWidget(precip_lbl)

                temps_lbl = QLabel(f"{int(round(tmax_d))}°  /  {int(round(tmin_d))}°")
                temps_lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; background: transparent; border: none; min-width: 80px;")
                temps_lbl.setAlignment(Qt.AlignRight)
                rl.addWidget(temps_lbl)

                days_list.insertWidget(days_list.count() - 1, row)

        except Exception as e:
            show_loading(f"Ошибка разбора: {e}")

    def on_weather_error(err):
        show_loading(f"⚠ {err}")

    # ---- Связи ----
    search_btn.clicked.connect(do_search)
    city_input.returnPressed.connect(do_search)
    result_list.itemClicked.connect(on_city_selected)

    # ---- Автозагрузка сохранённого города ----
    if saved_city and saved_city.get("lat"):
        st["lat"] = saved_city["lat"]
        st["lon"] = saved_city["lon"]
        QTimer.singleShot(200, load_weather)
    else:
        show_loading("Введи город слева")
        # Пробуем Москву по умолчанию
        st["lat"] = 55.7558
        st["lon"] = 37.6173
        st["city_name"] = "Москва"
        city_lbl.setText("📍 Москва (по умолчанию)")
        QTimer.singleShot(200, load_weather)

    return root