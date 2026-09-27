"""
MountOS — Хаб.

Управление системой + социальные системы через открытые API.

Разделы:
  • Обзор       — CPU/RAM/диски в реальном времени
  • Система     — железо, ОС, процессы
  • Сеть        — IP, интерфейсы, трафик, пинг
  • Погода      — Open-Meteo (поиск города, без ключа)
  • Валюты      — exchangerate.host (базовая RUB, без ключа)
  • Мониторинг  — живой график CPU/RAM

Без заглушек: всё работает по-настоящему.
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                                QPushButton, QStackedWidget, QScrollArea,
                                QFrame, QLineEdit, QListWidget, QListWidgetItem,
                                QComboBox, QMessageBox)
from PySide6.QtCore import Qt, QTimer, QSize, QPointF, QRectF
from PySide6.QtGui import (QPixmap, QPainter, QColor, QPainterPath, QBrush,
                            QPen, QLinearGradient, QIcon, QFont)
import platform
import sys
import time
import socket
import subprocess

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

from ui.settings_state import state
from ui.icons import get_icon
from ui.context_menu import make_menu

APP_NAME = "Хаб"
APP_ICON = "hub"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS"


# ============================================================
#  Иконка-ромб (как логотип MountOS)
# ============================================================

def make_diamond_icon(size=32, color="#6EC6FF"):
    """Рисует ромб ◆ в стиле логотипа MountOS."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    cx, cy = size / 2, size / 2
    r = size * 0.40

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(color))
    grad.setColorAt(1, QColor("#B388FF"))

    path = QPainterPath()
    path.moveTo(cx, cy - r)
    path.lineTo(cx + r, cy)
    path.lineTo(cx, cy + r)
    path.lineTo(cx - r, cy)
    path.closeSubpath()
    p.fillPath(path, QBrush(grad))

    # Блик сверху
    pen = QPen(QColor(255, 255, 255, 90))
    pen.setWidth(1)
    p.setPen(pen)
    p.drawPath(path)
    p.end()
    return pm


# ============================================================
#  Поиск Desktop / Registry (как в settings.py)
# ============================================================

def _get_desktop(widget):
    p = widget
    while p is not None:
        if hasattr(p, "notifications") and hasattr(p, "open_app"):
            return p
        p = p.parent()
    from PySide6.QtWidgets import QApplication
    for top in QApplication.topLevelWidgets():
        ref = getattr(top, "desktop_ref", None)
        if ref is not None and hasattr(ref, "registry"):
            return ref
    for top in QApplication.topLevelWidgets():
        if hasattr(top, "notifications") and hasattr(top, "open_app"):
            return top
    return None


def _notify(widget, title, text):
    d = _get_desktop(widget)
    if d and hasattr(d, "notifications"):
        d.notifications.push(title, text)


# ============================================================
#  Хелперы UI (в стиле settings.py)
# ============================================================

def _section(title):
    l = QLabel(title.upper())
    l.setStyleSheet("""
        color: rgba(255,255,255,0.45);
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        padding: 16px 4px 8px 4px;
    """)
    return l


def _hint(text):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px; padding: 2px 4px 6px 4px;")
    return l


def _card():
    w = QWidget()
    w.setStyleSheet("""
        QWidget {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
        }
    """)
    return w


def _row_card(label, value_label):
    row = _card()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(16, 10, 16, 10)
    kl = QLabel(label)
    kl.setStyleSheet("color: rgba(255,255,255,0.60); font-size: 13px; background: transparent; border: none;")
    rl.addWidget(kl)
    rl.addStretch(1)
    value_label.setStyleSheet("color: rgba(255,255,255,0.95); font-size: 13px; font-weight: 500; background: transparent; border: none;")
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    rl.addWidget(value_label)
    return row


def _scrollable(inner):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setStyleSheet("""
        QScrollArea { background: transparent; }
        QScrollBar:vertical { background: transparent; width: 8px; margin: 4px; }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,0.20);
            border-radius: 4px; min-height: 30px;
        }
        QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.35); }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
    """)
    sc.setWidget(inner)
    return sc


def _human_bytes(n):
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ПБ"


def _human_uptime(sec):
    d = int(sec // 86400)
    h = int((sec % 86400) // 3600)
    m = int((sec % 3600) // 60)
    if d > 0:
        return f"{d}д {h}ч {m}м"
    if h > 0:
        return f"{h}ч {m}м"
    return f"{m}м"


# ============================================================
#  Страница: Обзор
# ============================================================

def _page_overview():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Система в реальном времени"))
    lay.addWidget(_hint("Обновляется каждые 2 секунды."))

    if not HAS_PSUTIL:
        err = QLabel("⚠  psutil не установлен. Установи: pip install psutil")
        err.setStyleSheet("color:#FFA0B4; padding:12px; font-size:13px;")
        lay.addWidget(err)
        lay.addStretch(1)
        return _scrollable(w)

    cpu_val = QLabel("—")
    ram_val = QLabel("—")
    disk_val = QLabel("—")
    swap_val = QLabel("—")
    uptime_val = QLabel("—")
    battery_val = QLabel("—")
    temps_val = QLabel("—")

    lay.addWidget(_row_card("Загрузка ЦП", cpu_val))
    lay.addWidget(_row_card("Оперативная память", ram_val))
    lay.addWidget(_row_card("Диск (корень)", disk_val))
    lay.addWidget(_row_card("Файл подкачки", swap_val))
    lay.addWidget(_row_card("Время работы", uptime_val))
    lay.addWidget(_row_card("Батарея", battery_val))
    lay.addWidget(_row_card("Температура", temps_val))

    lay.addWidget(_section("Быстрые действия"))
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    def _quick_btn(text, handler):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(38)
        b.setStyleSheet("""
            QPushButton {
                background: rgba(110,198,255,0.18);
                color: white;
                border: 1px solid rgba(110,198,255,0.55);
                border-radius: 10px;
                padding: 8px 18px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(110,198,255,0.35); }
        """)
        b.clicked.connect(handler)
        return b

    def show_summary():
        d = _get_desktop(w)
        if d and hasattr(d, "notifications"):
            msg = (f"ЦП: {cpu_val.text()} | ОЗУ: {ram_val.text()} | "
                   f"Диск: {disk_val.text()}")
            d.notifications.push("Состояние системы", msg)

    btn_row.addWidget(_quick_btn("📋  Сводка в уведомление", show_summary))
    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    lay.addStretch(1)

    # Обновление
    def tick():
        try:
            cpu_val.setText(f"{psutil.cpu_percent(interval=None):.1f}%  "
                            f"({psutil.cpu_count()} ядер)")
            vm = psutil.virtual_memory()
            ram_val.setText(f"{vm.percent:.1f}%  "
                            f"({_human_bytes(vm.used)} / {_human_bytes(vm.total)})")
            try:
                du = psutil.disk_usage("/")
                disk_val.setText(f"{du.percent:.1f}%  "
                                 f"({_human_bytes(du.used)} / {_human_bytes(du.total)})")
            except Exception:
                disk_val.setText("—")
            sw = psutil.swap_memory()
            swap_val.setText(f"{sw.percent:.1f}%  "
                             f"({_human_bytes(sw.used)} / {_human_bytes(sw.total)})")
            uptime_val.setText(_human_uptime(time.time() - psutil.boot_time()))
            try:
                bat = psutil.sensors_battery()
                if bat is None:
                    battery_val.setText("нет данных")
                else:
                    charging = " ⚡" if bat.power_plugged else ""
                    battery_val.setText(f"{bat.percent:.0f}%{charging}")
            except Exception:
                battery_val.setText("нет данных")
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    first = next(iter(temps.values()))
                    t = first[0].current
                    temps_val.setText(f"{t:.1f} °C")
                else:
                    temps_val.setText("нет датчиков")
            except Exception:
                temps_val.setText("нет датчиков")
        except Exception:
            pass

    t = QTimer(w)
    t.timeout.connect(tick)
    t.start(2000)
    w._timer = t
    tick()

    return _scrollable(w)


# ============================================================
#  Страница: Система
# ============================================================

def _page_system():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Железо и ОС"))

    rows = [
        ("ОС",             f"{platform.system()} {platform.release()}"),
        ("Версия ядра",    platform.version()),
        ("Архитектура",    platform.machine()),
        ("Процессор",      platform.processor() or "—"),
        ("Имя ПК",         platform.node()),
        ("Python",         platform.python_version()),
    ]
    if HAS_PSUTIL:
        try:
            freq = psutil.cpu_freq()
            if freq:
                rows.append(("Частота ЦП", f"{freq.current:.0f} МГц"))
        except Exception:
            pass
        try:
            rows.append(("Физических ядер", str(psutil.cpu_count(logical=False) or "—")))
            rows.append(("Логических ядер", str(psutil.cpu_count(logical=True))))
        except Exception:
            pass

    for k, v in rows:
        vl = QLabel(str(v))
        lay.addWidget(_row_card(k, vl))

    lay.addWidget(_section("Процессы (топ-20 по памяти)"))
    lay.addWidget(_hint("Двойной клик — убить процесс."))

    if not HAS_PSUTIL:
        lay.addWidget(_hint("psutil не установлен."))
        lay.addStretch(1)
        return _scrollable(w)

    proc_list = QListWidget()
    proc_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 6px;
            color: white;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 6px 10px; border-radius: 8px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    proc_list.setMinimumHeight(280)
    lay.addWidget(proc_list)

    def rebuild_processes():
        proc_list.clear()
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
            try:
                info = p.info
                mem = info.get("memory_percent") or 0
                procs.append((mem, info))
            except Exception:
                continue
        procs.sort(reverse=True, key=lambda x: x[0])
        for mem, info in procs[:20]:
            text = (f"PID {info['pid']:>6}  |  "
                    f"{info['name'][:40]:<40}  |  "
                    f"RAM {mem:.1f}%")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, info["pid"])
            proc_list.addItem(item)

    def kill_selected(item):
        pid = item.data(Qt.UserRole)
        ok = QMessageBox.question(w, "Завершить процесс",
            f"Завершить процесс PID {pid}?",
            QMessageBox.Yes | QMessageBox.No)
        if ok == QMessageBox.Yes:
            try:
                psutil.Process(pid).terminate()
                _notify(w, "Процесс завершён", f"PID {pid}")
                rebuild_processes()
            except Exception as e:
                QMessageBox.warning(w, "Ошибка", str(e))

    proc_list.itemDoubleClicked.connect(kill_selected)

    btn = QPushButton("⟳  Обновить список процессов")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(36)
    btn.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(255,255,255,0.18); }
    """)
    btn.clicked.connect(rebuild_processes)
    lay.addWidget(btn)

    rebuild_processes()
    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Сеть
# ============================================================

def _page_network():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Интерфейсы"))
    iface_box = QVBoxLayout()
    lay.addLayout(iface_box)

    def rebuild_interfaces():
        for i in reversed(range(iface_box.count())):
            it = iface_box.itemAt(i)
            if it and it.widget():
                it.widget().setParent(None)

        if not HAS_PSUTIL:
            lbl = QLabel("psutil не установлен.")
            lbl.setStyleSheet("color:#FFA0B4;")
            iface_box.addWidget(lbl)
            return

        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for name, addr_list in addrs.items():
            card = _card()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 10, 16, 10)
            title = QLabel(name)
            title.setStyleSheet("color:white; font-size:13px; font-weight:600; background:transparent; border:none;")
            cl.addWidget(title)
            for a in addr_list:
                fam = str(a.family)
                if "AF_INET" in fam and "6" not in fam:
                    ip = QLabel(f"IPv4: {a.address}")
                elif "AF_INET6" in fam:
                    ip = QLabel(f"IPv6: {a.address}")
                else:
                    continue
                ip.setStyleSheet("color:rgba(255,255,255,0.75); font-size:12px; background:transparent; border:none;")
                ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
                cl.addWidget(ip)
            st = stats.get(name)
            if st:
                up = "активен" if st.isup else "выключен"
                sp = QLabel(f"{up} · {st.speed} Мбит/с")
                sp.setStyleSheet("color:rgba(255,255,255,0.55); font-size:11px; background:transparent; border:none;")
                cl.addWidget(sp)
            iface_box.addWidget(card)

    rebuild_interfaces()

    lay.addWidget(_section("Трафик"))
    io_upload = QLabel("—")
    io_download = QLabel("—")
    io_total = QLabel("—")
    lay.addWidget(_row_card("Отправлено", io_upload))
    lay.addWidget(_row_card("Получено", io_download))
    lay.addWidget(_row_card("Всего", io_total))

    lay.addWidget(_section("Пинг"))
    ping_input = QLineEdit("8.8.8.8")
    ping_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-family: Consolas, monospace;
            font-size: 12px;
        }
    """)
    lay.addWidget(ping_input)

    ping_result = QLabel("—")
    ping_result.setStyleSheet("color: rgba(255,255,255,0.75); font-size:12px; padding: 8px 4px;")
    ping_result.setWordWrap(True)
    lay.addWidget(ping_result)

    def do_ping():
        host = ping_input.text().strip()
        if not host:
            return
        ping_result.setText("Пингую…")
        try:
            param = "-n" if platform.system().lower() == "windows" else "-c"
            out = subprocess.run(["ping", param, "1", host],
                                 capture_output=True, text=True, timeout=5)
            ping_result.setText(out.stdout.strip() or out.stderr.strip())
        except Exception as e:
            ping_result.setText(f"Ошибка: {e}")

    ping_btn = QPushButton("▶  Пинговать")
    ping_btn.setCursor(Qt.PointingHandCursor)
    ping_btn.setFixedHeight(36)
    ping_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    ping_btn.clicked.connect(do_ping)
    lay.addWidget(ping_btn)

    lay.addStretch(1)

    def tick_io():
        if not HAS_PSUTIL:
            return
        try:
            io = psutil.net_io_counters()
            io_upload.setText(_human_bytes(io.bytes_sent))
            io_download.setText(_human_bytes(io.bytes_recv))
            io_total.setText(_human_bytes(io.bytes_sent + io.bytes_recv))
        except Exception:
            pass

    t = QTimer(w)
    t.timeout.connect(tick_io)
    t.start(2000)
    w._timer = t
    tick_io()

    return _scrollable(w)


# ============================================================
#  Страница: Погода (Open-Meteo, без ключа)
# ============================================================

WEATHER_CODES = {
    0: "Ясно", 1: "Преим. ясно", 2: "Переменная облачность", 3: "Пасмурно",
    45: "Туман", 48: "Изморозь", 51: "Лёгкая морось", 53: "Морось",
    55: "Сильная морось", 61: "Небольшой дождь", 63: "Дождь",
    65: "Сильный дождь", 71: "Небольшой снег", 73: "Снег",
    75: "Сильный снег", 77: "Снежные зёрна", 80: "Ливень",
    81: "Сильный ливень", 82: "Очень сильный ливень",
    85: "Снегопад", 86: "Сильный снегопад", 95: "Гроза",
    96: "Гроза с градом", 99: "Сильная гроза с градом",
}


def _page_weather():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Поиск города"))
    lay.addWidget(_hint("Введи название города и нажми «Найти»."))

    row = QHBoxLayout()
    row.setSpacing(8)

    city_input = QLineEdit(state().get("hub_city", ""))
    city_input.setPlaceholderText("Например: Москва")
    city_input.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.60); }
    """)
    row.addWidget(city_input, 1)

    find_btn = QPushButton("🔍  Найти")
    find_btn.setCursor(Qt.PointingHandCursor)
    find_btn.setFixedHeight(38)
    find_btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 8px 16px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    row.addWidget(find_btn)
    lay.addLayout(row)

    result_list = QListWidget()
    result_list.setStyleSheet("""
        QListWidget {
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 6px;
            color: white;
            font-size: 12px;
            outline: none;
        }
        QListWidget::item { padding: 6px 10px; border-radius: 8px; }
        QListWidget::item:hover { background: rgba(255,255,255,0.08); }
        QListWidget::item:selected { background: rgba(110,198,255,0.30); }
    """)
    result_list.setMaximumHeight(140)
    lay.addWidget(result_list)

    lay.addWidget(_section("Текущая погода"))

    weather_box = QVBoxLayout()
    lay.addLayout(weather_box)

    if not HAS_REQUESTS:
        warn = QLabel("⚠  requests не установлен. Установи: pip install requests")
        warn.setStyleSheet("color:#FFA0B4; padding:12px; font-size:13px;")
        lay.addWidget(warn)
        lay.addStretch(1)
        return _scrollable(w)

    def show_weather(lat, lon, city_name):
        try:
            url = ("https://api.open-meteo.com/v1/forecast"
                   f"?latitude={lat}&longitude={lon}"
                   "&current=temperature_2m,relative_humidity_2m,"
                   "apparent_temperature,weather_code,wind_speed_10m")
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json().get("current", {})
        except Exception as e:
            QMessageBox.warning(w, "Ошибка погоды", str(e))
            return

        for i in reversed(range(weather_box.count())):
            it = weather_box.itemAt(i)
            if it and it.widget():
                it.widget().setParent(None)

        code = data.get("weather_code", 0)
        desc = WEATHER_CODES.get(code, f"код {code}")
        rows = [
            ("Город",        city_name),
            ("Погода",       desc),
            ("Температура",  f"{data.get('temperature_2m', '—')} °C"),
            ("Ощущается",    f"{data.get('apparent_temperature', '—')} °C"),
            ("Влажность",    f"{data.get('relative_humidity_2m', '—')} %"),
            ("Ветер",        f"{data.get('wind_speed_10m', '—')} м/с"),
        ]
        for k, v in rows:
            vl = QLabel(str(v))
            weather_box.addWidget(_row_card(k, vl))

        state().set("hub_city", city_name)
        state().set("hub_city_lat", lat)
        state().set("hub_city_lon", lon)

    def do_search():
        name = city_input.text().strip()
        if not name:
            return
        result_list.clear()
        try:
            url = ("https://geocoding-api.open-meteo.com/v1/search"
                   f"?name={name}&count=8&language=ru&format=json")
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            QMessageBox.warning(w, "Ошибка поиска", str(e))
            return

        if not results:
            item = QListWidgetItem("Ничего не найдено")
            item.setForeground(Qt.gray)
            result_list.addItem(item)
            return

        for c in results:
            label = f"{c['name']}, {c.get('admin1', '')}, {c.get('country', '')}".strip(", ")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, c)
            result_list.addItem(item)

    def on_choice(item):
        c = item.data(Qt.UserRole)
        if not c:
            return
        label = f"{c['name']}, {c.get('country', '')}".strip(", ")
        show_weather(c["latitude"], c["longitude"], label)

    find_btn.clicked.connect(do_search)
    city_input.returnPressed.connect(do_search)
    result_list.itemDoubleClicked.connect(on_choice)

    # Если город уже сохранён — показать сразу
    lat = state().get("hub_city_lat")
    lon = state().get("hub_city_lon")
    if lat is not None and lon is not None:
        show_weather(lat, lon, state().get("hub_city", "—"))

    lay.addStretch(1)
    return _scrollable(w)


# ============================================================
#  Страница: Валюты (exchangerate.host, базовая RUB)
# ============================================================

def _page_currency():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Курсы валют"))
    lay.addWidget(_hint("Базовая валюта — RUB. Источник: exchangerate.host (без ключа)."))

    if not HAS_REQUESTS:
        warn = QLabel("⚠  requests не установлен.")
        warn.setStyleSheet("color:#FFA0B4; padding:12px; font-size:13px;")
        lay.addWidget(warn)
        lay.addStretch(1)
        return _scrollable(w)

    base_label = QLabel(f"1 RUB = …")
    base_label.setStyleSheet("color:white; font-size:16px; font-weight:600; padding: 8px 0;")
    lay.addWidget(base_label)

    currencies = ["USD", "EUR", "CNY", "GBP", "JPY", "KZT", "BYN", "UAH", "TRY"]
    rows = {}
    for c in currencies:
        vl = QLabel("—")
        rows[c] = vl
        lay.addWidget(_row_card(c, vl))

    updated = QLabel("—")
    updated.setStyleSheet("color: rgba(255,255,255,0.45); font-size:11px; padding-top:8px;")
    lay.addWidget(updated)

    def refresh():
        base_label.setText("1 RUB = … (загрузка)")
        updated.setText("…")
        try:
            url = "https://api.exchangerate.host/latest?base=RUB&symbols=" + ",".join(currencies)
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()
            rates = data.get("rates", {})
            for c in currencies:
                v = rates.get(c)
                rows[c].setText(f"{v:.4f}" if isinstance(v, (int, float)) else "—")
            updated.setText(f"Обновлено: {data.get('date', '—')}")
        except Exception as e:
            updated.setText(f"Ошибка: {e}")

    btn = QPushButton("⟳  Обновить курсы")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(36)
    btn.setStyleSheet("""
        QPushButton {
            background: rgba(110,198,255,0.18);
            color: white;
            border: 1px solid rgba(110,198,255,0.55);
            border-radius: 10px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton:hover { background: rgba(110,198,255,0.35); }
    """)
    btn.clicked.connect(refresh)
    lay.addWidget(btn)

    lay.addStretch(1)
    refresh()
    return _scrollable(w)


# ============================================================
#  Страница: Мониторинг (живой график CPU/RAM)
# ============================================================

class GraphWidget(QWidget):
    """Простой живой график CPU/RAM."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.cpu_history = [0] * 60
        self.ram_history = [0] * 60

    def push(self, cpu, ram):
        self.cpu_history.append(cpu)
        self.cpu_history.pop(0)
        self.ram_history.append(ram)
        self.ram_history.pop(0)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(10, 10, -10, -10)

        # Фон
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, QBrush(QColor(0, 0, 0, 60)))

        # Сетка
        pen = QPen(QColor(255, 255, 255, 25))
        pen.setWidth(1)
        p.setPen(pen)
        for i in range(1, 4):
            y = r.top() + r.height() * i / 4
            p.drawLine(r.left(), int(y), r.right(), int(y))

        def draw_line(history, color):
            if len(history) < 2:
                return
            path = QPainterPath()
            step = r.width() / (len(history) - 1)
            for i, v in enumerate(history):
                x = r.left() + i * step
                y = r.bottom() - (v / 100.0) * r.height()
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            pen = QPen(QColor(color))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawPath(path)

        draw_line(self.cpu_history, "#6EC6FF")
        draw_line(self.ram_history, "#B388FF")

        # Легенда
        p.setPen(QColor("#6EC6FF"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(r.left() + 10, r.top() + 20, "CPU")
        p.setPen(QColor("#B388FF"))
        p.drawText(r.left() + 60, r.top() + 20, "RAM")


def _page_monitor():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 20, 30, 30)
    lay.setSpacing(6)

    lay.addWidget(_section("Живой график"))
    lay.addWidget(_hint("CPU — голубая, RAM — фиолетовая. Обновление раз в секунду."))

    graph = GraphWidget()
    lay.addWidget(graph)

    cpu_label = QLabel("CPU: —")
    ram_label = QLabel("RAM: —")
    cpu_label.setStyleSheet("color:#6EC6FF; font-size:14px; font-weight:600;")
    ram_label.setStyleSheet("color:#B388FF; font-size:14px; font-weight:600;")
    lay.addWidget(cpu_label)
    lay.addWidget(ram_label)

    lay.addStretch(1)

    if not HAS_PSUTIL:
        warn = QLabel("⚠  psutil не установлен.")
        warn.setStyleSheet("color:#FFA0B4; padding:12px;")
        lay.addWidget(warn)
        return _scrollable(w)

    def tick():
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            graph.push(cpu, ram)
            cpu_label.setText(f"CPU: {cpu:.1f}%")
            ram_label.setText(f"RAM: {ram:.1f}%")
        except Exception:
            pass

    t = QTimer(w)
    t.timeout.connect(tick)
    t.start(1000)
    w._timer = t
    tick()

    return _scrollable(w)


# ============================================================
#  Главный build()
# ============================================================

def build():
    root = QWidget()
    h = QHBoxLayout(root)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(0)

    # ---------- Сайдбар ----------
    side = QWidget()
    side.setFixedWidth(200)
    side.setStyleSheet("""
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    """)
    sl = QVBoxLayout(side)
    sl.setContentsMargins(12, 14, 12, 14)
    sl.setSpacing(2)

    # Ромб + название
    head = QWidget()
    hl = QHBoxLayout(head)
    hl.setContentsMargins(8, 4, 4, 12)
    hl.setSpacing(10)

    diamond = QLabel()
    diamond.setPixmap(make_diamond_icon(28, state().get("accent", "#6EC6FF")))
    hl.addWidget(diamond)

    title = QLabel("Хаб")
    title.setStyleSheet("color: white; font-size: 15px; font-weight: 600; letter-spacing: 1px;")
    hl.addWidget(title)
    hl.addStretch(1)
    sl.addWidget(head)

    # Кнопки разделов
    stack = QStackedWidget()
    pages = []

    def add_page(label, builder):
        b = QPushButton(label)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(36)
        b.setCheckable(True)
        b.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(255,255,255,0.78);
                border: none;
                border-radius: 8px;
                padding: 6px 12px;
                text-align: left;
                font-size: 13px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.08); color: white; }
            QPushButton:checked {
                background: rgba(110,198,255,0.20);
                color: white;
                border-left: 3px solid #6EC6FF;
            }
        """)
        sl.addWidget(b)
        idx = stack.count()
        stack.addWidget(builder())
        pages.append(b)

        def on_click(_, i=idx):
            stack.setCurrentIndex(i)
            for j, pb in enumerate(pages):
                pb.setChecked(j == i)

        b.clicked.connect(on_click)
        return b

    add_page("📊  Обзор",       _page_overview)
    add_page("💻  Система",     _page_system)
    add_page("🌐  Сеть",        _page_network)
    add_page("🌤  Погода",      _page_weather)
    add_page("💱  Валюты",      _page_currency)
    add_page("📈  Мониторинг",  _page_monitor)

    sl.addStretch(1)

    if pages:
        pages[0].setChecked(True)
        stack.setCurrentIndex(0)

    h.addWidget(side)
    h.addWidget(stack, 1)

    return root